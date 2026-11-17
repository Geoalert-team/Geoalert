"""
The trained model behind the hazard likelihood: a Poisson regression on the
historical record, one for each hazard type, refitted from the records as they
stand (nothing is saved, so there is nothing to retrain or go stale).

For each barangay and month of the year it learns how many events to expect
from the barangay itself, the month, the barangay's land area and how many
puroks it has for that area. Fitting them together lets a barangay with few
records borrow from the others: its own record says how it differs, and the
penalty ALPHA pulls that difference back toward what its size and puroks
suggest. The chance of at least one event follows from the expected number,
1 - e^-rate, and sets the level (level_for).

Why this model: it was the best of 37 candidates on rolling forecasts inside
2023-2025, then beat counting on the fires of January to September 2026, which
it had never seen. Boosted trees, random forests and rainfall did no better;
nor did small neural networks with a Poisson loss (2026-11-12: the best tied
it on February to October 2026, and only when penalised into a nearly linear
fit), nor neighbouring barangays' or recent fires as inputs.
Fires per barangay-month fit a Poisson spread almost exactly (dispersion 0.99),
so a negative binomial adds nothing.

Its test: evaluate() holds back the last TEST_MONTHS of a hazard type's
record, trains on what came before, and scores the model and the counting in
forecast.py on what it held back. Counting is only the benchmark: a model that
does not beat it stays in use and its status says so (in_use_not_better); a
type with too few records to train and test gets no figures, and the forecast
shows it unavailable. Only real records count: seeded samples never train or
test anything.

A period that has started is estimated from the months before it. When they
hold fewer than MIN_TRAIN_EVENTS, the whole record's model gives the figures
and the rows say `in_training`, since that model learned from the period
itself (as flood and landslide do for their study years). A period from before
the record began gets no figures.

Fire has a contender (fire_candidate.py, spec Section 4): a pooled Poisson
model with each barangay's building count as its exposure. Each fit of fire
compares the two one month ahead, and the contender is used only when the
rule says it forecast better (_fitted); the test against counting then runs
on whichever is in use.
"""
import functools
import hashlib
import logging
import threading
import time
from calendar import monthrange
from collections import Counter, defaultdict
from datetime import date
from math import exp, log

import numpy as np
from django.core.cache import cache

from apps.history import forecast

logger = logging.getLogger(__name__)

ALPHA = 0.01
TEST_MONTHS = 9
MIN_TRAIN_EVENTS = 100
MIN_TEST_EVENTS = 20
HIGH_CHANCE = 0.25
MODERATE_CHANCE = 0.15
# Scoring floor: a forecast of exactly zero that meets a fire would otherwise cost infinity
MIN_RATE = 0.01
TOP_BARANGAYS = 5
TIE_DRAWS = 50
# The keys change with the records, the month and the building counts (_record_tag), so a fit never goes
# stale and the time limit only bounds the cache. Refitting takes minutes on a small server.
CACHE_SECONDS = 7 * 24 * 60 * 60
AREA_SRID = 32651  # UTM 51N, metres over Cebu
NEIGHBOUR_METRES = 1  # boundaries that touch or lie this close make neighbours (spec 4.5)

# Why a hazard type has no figures; the forecast shows these on its unavailable rows
TOO_FEW = 'Too few {} records to train and test its model.'
RECORDS_START = '{} records start in {:%B %Y}.'
MODEL_DOWN = 'The fire model could not run right now.'
NOT_COMPARED = "The comparison with the pooled exposure model could not run; today's model stays."
PREPARING = 'The {} model is being prepared; try again in a minute.'

# What no period changes (_chosen) is built by one request while the others wait, as in hazard_forecast
CHOICE_KEY = 'forecast-model-choice-v1:'
CHOICE_LOCK = 'forecast-model-choice-lock-v1:'
LOCK_SECONDS = 300
WAIT_SECONDS = 60
POLL_SECONDS = 0.5
# Swapped by the tests, so the wait runs on a fake clock
_sleep = time.sleep
_monotonic = time.monotonic
# cache.add is not atomic in the file cache, so threads of one process take turns at the lock key
_LOCK = threading.Lock()


class Preparing(Exception):
    """Another request is building the model and it was not ready in time (the page says PREPARING)."""


def chance(rate):
    """The chance of at least one event, given how many are expected."""
    return 1 - exp(-rate)


def level_for(share):
    if share >= HIGH_CHANCE:
        return 'High'
    if share >= MODERATE_CHANCE:
        return 'Moderate'
    return 'Low'


def plain_number(x) -> str:
    """
    x to 3 significant figures as a plain decimal, never in e-notation, for
    the sentences the accuracy card shows (the flood, landslide and fire
    verdicts): 8.81e-05 gives 0.0000881, -2.89e-05 gives -0.0000289.
    """
    return np.format_float_positional(x, precision=3, unique=False, fractional=False, trim='-')


def _index(day):
    """A month as one number, so months subtract and sort."""
    return day.year * 12 + day.month - 1


def _label(index):
    return f'{index // 12}-{index % 12 + 1:02d}'


def _span(events, until, today):
    """
    The months to read, first included, last not: from the first record to the
    last one's month, the month still running left out. A log stops when it was
    last updated, so the months after its last record are unknown, not quiet.
    """
    months = [_index(e['when']) for e in events]
    end = min(max(months) + 1, _index(today))
    return min(months), end if until is None else min(end, _index(until))


def _known(events, places):
    ids = {p['id'] for p in places}
    return [e for e in events if e['barangay_id'] in ids]


def _matrix(cases, order):
    """One row per (place, month of the year): barangay, month, then area and puroks."""
    x = np.zeros((len(cases), len(order) - 1 + 11 + 3))
    spot = {pid: i - 1 for i, pid in enumerate(order)}
    for row, (place, month) in enumerate(cases):
        if spot[place['id']] >= 0:
            x[row, spot[place['id']]] = 1
        if month > 1:
            x[row, len(order) - 1 + month - 2] = 1
        x[row, -3:] = log(place['area_km2']), log(max(place['puroks'], 1)), place['puroks'] / place['area_km2']
    return x


def rates_table(events, places, *, until=None, today):
    """
    {barangay id: [events expected in January, ..., December]}, trained on the
    months before `until` (all of the record without it), or None when they
    hold fewer than MIN_TRAIN_EVENTS.
    """
    from sklearn.linear_model import PoissonRegressor

    known = _known(events, places)
    if not known:
        return None
    first, end = _span(known, until, today)
    counts = Counter((e['barangay_id'], _index(e['when'])) for e in known if _index(e['when']) < end)
    if sum(counts.values()) < MIN_TRAIN_EVENTS:
        return None

    order = sorted((p['id'] for p in places), key=str)
    months = range(first, end)
    x = _matrix([(p, m % 12 + 1) for p in places for m in months], order)
    y = np.array([counts[(p['id'], m)] for p in places for m in months])
    centre, spread = x[:, -3:].mean(axis=0), x[:, -3:].std(axis=0, ddof=1)
    spread[spread == 0] = 1
    x[:, -3:] = (x[:, -3:] - centre) / spread
    model = PoissonRegressor(alpha=ALPHA, max_iter=2000).fit(x, y)

    grid = _matrix([(p, m) for p in places for m in range(1, 13)], order)
    grid[:, -3:] = (grid[:, -3:] - centre) / spread
    rates = model.predict(grid).reshape(len(places), 12)
    return {p['id']: [float(r) for r in row] for p, row in zip(places, rates)}


def _counting(counts, places, month_index, first_event):
    """What forecast.py said for this month beforehand: {barangay id: (share of years, expected)}."""
    year, month = month_index // 12, month_index % 12 + 1
    years = forecast.years_for_period(month, None, date(year, month, 1), first_event)
    weights = forecast.year_weights(years)
    said = {}
    for p in places:
        by_year = {y: counts[(p['id'], y * 12 + month - 1)] for y in years}
        share, expected, _ = forecast.likelihood(by_year, weights)
        said[p['id']] = (share, expected)
    return said


def _top_share(months, y, rates):
    """The share of events in the TOP_BARANGAYS ranked highest each month; ties broken at random."""
    rng = np.random.default_rng(1)
    caught = 0
    for month in np.unique(months):
        inside = months == month
        for _ in range(TIE_DRAWS):
            ranked = np.lexsort((rng.random(inside.sum()), -rates[inside]))
            caught += y[inside][ranked[:TOP_BARANGAYS]].sum()
    return caught / TIE_DRAWS / y.sum()


def _scores(months, y, rates, chances):
    from sklearn.metrics import roc_auc_score

    floored = np.maximum(rates, MIN_RATE)
    with np.errstate(divide='ignore', invalid='ignore'):
        log_ratio = np.where(y > 0, y * np.log(y / floored), 0.0)
    hit = y > 0
    return {
        'deviance': round(float((2 * (log_ratio - (y - floored))).mean()), 4),
        'brier': round(float(((chances - hit) ** 2).mean()), 4),
        'auc': round(float(roc_auc_score(hit, rates)), 4) if 0 < hit.sum() < len(hit) else None,
        'top_share': round(float(_top_share(months, y, rates)), 4),
    }


def beats(model, counting):
    """The test: better on both the expected number and the chance, never a trade of one for the other."""
    return model['deviance'] < counting['deviance'] and model['brier'] < counting['brier']


def evaluate(events, places, today, table_fn=rates_table):
    """
    Hold back the last TEST_MONTHS of the record, train on the months before
    them and score the model and counting on them. 'status' says what follows:
    in_use, in_use_not_better (the model is still used; never counting) or
    too_few_records (no figures). `table_fn` is the model, with rates_table's
    arguments and result: fire's contender when it is the one in use.
    """
    known = _known(events, places)
    if not known:
        return {'status': 'too_few_records', 'train': None, 'test': None}
    first, end = _span(known, None, today)
    split = end - TEST_MONTHS
    train = [e for e in known if _index(e['when']) < split]
    test = [e for e in known if split <= _index(e['when']) < end]
    out = {
        'train': {'start': _label(first), 'end': _label(split - 1), 'events': len(train)},
        'test': {'start': _label(split), 'end': _label(end - 1), 'events': len(test)},
    }
    if len(train) < MIN_TRAIN_EVENTS or len(test) < MIN_TEST_EVENTS:
        return {**out, 'status': 'too_few_records'}

    table = table_fn(train, places, until=date(split // 12, split % 12 + 1, 1), today=today)
    counts = Counter((e['barangay_id'], _index(e['when'])) for e in known)
    first_event = min(e['when'] for e in known)
    months, y, rates, shares, expected = [], [], [], [], []
    for month in range(split, end):
        said = _counting(counts, places, month, first_event)
        for p in places:
            months.append(month)
            y.append(counts[(p['id'], month)])
            rates.append(table[p['id']][month % 12])
            shares.append(said[p['id']][0])
            expected.append(said[p['id']][1])
    months, y, rates = np.array(months), np.array(y), np.array(rates)
    chances = 1 - np.exp(-rates)
    model = _scores(months, y, rates, chances)
    counting = _scores(months, y, np.array(expected), np.array(shares))

    levels = []
    picked = np.array([level_for(c) for c in chances])
    for level in ('High', 'Moderate', 'Low'):
        inside = picked == level
        levels.append({
            'level': level,
            'rows': int(inside.sum()),
            'events': int(y[inside].sum()),
            'chance': round(float(chances[inside].mean()), 3) if inside.any() else None,
            'happened': round(float((y[inside] > 0).mean()), 3) if inside.any() else None,
        })
    return {**out, 'status': 'in_use' if beats(model, counting) else 'in_use_not_better',
            'model': model, 'counting': counting, 'levels': levels}


def apply_table(result, hazard, table, places, month, day=None, in_training=False):
    """
    Give this hazard type's rows in a seasonal_forecast result the model's
    chance and level. Every barangay gets a row, since the model has a figure
    for each; the row's history (years hit, events, what happened) stays. An
    exact date's chance is for its week, but the level stays the month's: a
    week's chance is small everywhere, which would call every barangay Low.
    `in_training` marks rows whose model learned from the period itself.
    """
    rows = {r['barangay_id']: r for r in result['results'] if r['hazard_type'] == hazard}
    week = (2 * forecast.DAY_WINDOW + 1) / monthrange(result.get('year') or 2001, month)[1] if day else 1
    for place in places:
        if place['id'] not in table:
            continue
        row = rows.get(place['id'])
        if row is None:
            row = {'barangay_id': place['id'], 'barangay': place['name'], 'hazard_type': hazard, 'years_hit': 0,
                   'years_considered': len(result['years']), 'limited': result['limited'], 'typical_severity': None,
                   'events': 0, 'last_occurred': None}
            if result.get('outcome') is not None:
                row['actual'] = 0
            result['results'].append(row)
        rate = table[place['id']][month - 1]
        row.update(probability=round(chance(rate * week), 3), expected_events=round(rate * week, 2),
                   level=level_for(chance(rate)), method='model')
        if in_training:
            row['in_training'] = True
        else:
            row.pop('in_training', None)
    forecast.rank_rows(result['results'])
    result['by_barangay'] = forecast.summarize_by_barangay(result['results'])


def apply_profile(result, table, barangay_id):
    """
    The 12-month chart from the model: this barangay's year, or the average
    barangay's. A barangay the model has no figure for leaves the chart empty
    and unavailable.
    """
    result['profile_method'] = 'unavailable'
    if barangay_id is None:
        monthly = [sum(rates[m] for rates in table.values()) / len(table) for m in range(12)]
    elif barangay_id in table:
        monthly = table[barangay_id]
    else:
        return
    for entry, rate in zip(result['profile'], monthly):
        entry.update(probability=round(chance(rate), 3), expected_events=round(rate, 2), level=level_for(chance(rate)))
    result['profile_method'] = 'model'


def places():
    """Every barangay the model reads. One with no boundary is not a place on the map."""
    from django.contrib.gis.db.models.functions import Area, Transform
    from django.db.models import Count
    from apps.barangays.models import Barangay, Purok

    puroks = dict(Purok.objects.values_list('barangay_id').annotate(n=Count('id')).order_by())
    rows = (Barangay.objects.exclude(boundary__isnull=True)
            .annotate(area=Area(Transform('boundary', AREA_SRID))).values_list('id', 'name', 'area'))
    return [{'id': pid, 'name': name, 'area_km2': area.sq_km, 'puroks': puroks.get(pid, 0)}
            for pid, name, area in rows]


def neighbours():
    """
    {barangay id: the barangays that share a border with it}, for every
    barangay with a boundary: boundaries that touch or lie within
    NEIGHBOUR_METRES of each other in UTM 51N (PostGIS).
    """
    from django.db import connection
    from apps.barangays.models import Barangay

    q = connection.ops.quote_name
    table, pk, geom = (q(Barangay._meta.db_table), q(Barangay._meta.pk.column),
                       q(Barangay._meta.get_field('boundary').column))
    out = {pid: set() for pid in Barangay.objects.exclude(boundary__isnull=True).values_list('id', flat=True)}
    with connection.cursor() as cursor:
        cursor.execute(
            f'WITH b AS (SELECT {pk} AS id, ST_Transform({geom}, %s) AS g FROM {table} WHERE {geom} IS NOT NULL) '
            'SELECT x.id, y.id FROM b x JOIN b y ON x.id < y.id AND ST_DWithin(x.g, y.g, %s)',
            [AREA_SRID, NEIGHBOUR_METRES])
        for a, b in cursor.fetchall():
            out[a].add(b)
            out[b].add(a)
    return out


def _exposure_path():
    """The building counts fire's contender reads, where the other hazard inputs are (hazard_data.DATA_DIR)."""
    from apps.history import hazard_data
    from apps.history.exposure import EXPOSURE_FILE
    return hazard_data.DATA_DIR / EXPOSURE_FILE.name


def _file_sha1(path):
    try:
        return hashlib.sha1(path.read_bytes()).hexdigest()
    except OSError:
        return 'missing'


def _buildings(path):
    """
    Each barangay's building count, or None when the exposure file is missing
    (it is built by a command) or cannot be read: only the contender reads it,
    so a bad file leaves the contender untested and never stops today's model.
    """
    from apps.history.fire_candidate import read_buildings
    try:
        return read_buildings(path)
    except OSError:
        return None
    except Exception:
        logger.warning('The building counts in %s could not be read; the pooled exposure model is not tested.', path,
                       exc_info=True)
        return None


def _fire_choice(events, where, today):
    """
    (the comparison's result, the building counts) for fire (spec 4.4, 4.6).
    A comparison that fails leaves today's model in use, with the reason: it
    never takes fire's forecast down.
    """
    from apps.history import fire_candidate

    buildings = _buildings(_exposure_path())
    try:
        return fire_candidate.compare(events, where, buildings, neighbours(), today), buildings
    except Exception:
        logger.exception("Fire's two models could not be compared; today's model stays.")
        return fire_candidate.untested(NOT_COMPARED), None


def _table_fn(in_use, buildings):
    """The model named `in_use` as a function with rates_table's arguments and result."""
    from apps.history import fire_candidate
    if in_use == fire_candidate.F1_NAME:
        return functools.partial(fire_candidate.exposure_rates_table, buildings=buildings)
    return rates_table


def _once(key, lock, build):
    """
    The value cached at `key`, or built now by one caller while the others poll
    the cache, as hazard_forecast.deployed does; one that waits WAIT_SECONDS
    gives up with Preparing. A build that fails releases the lock, so the next
    caller tries.
    """
    deadline = _monotonic() + WAIT_SECONDS
    while True:
        hit = cache.get(key)
        if hit is not None:
            return hit
        with _LOCK:
            mine = cache.add(lock, 1, LOCK_SECONDS)
        if mine:
            try:
                hit = cache.get(key)        # set while this caller was taking the lock
                if hit is not None:
                    return hit
                built = build()
                cache.set(key, built, CACHE_SECONDS)
                return built
            finally:
                with _LOCK:
                    cache.delete(lock)
        if _monotonic() >= deadline:
            raise Preparing()
        _sleep(POLL_SECONDS)


def _record_tag(hazard, events, today):
    """
    What a hazard type's models learn from, whatever the period asked for: its
    records, the month they are read in (the month still running is left out)
    and the building counts fire's contender reads.
    """
    last = max(e['when'] for e in events)
    return f'{hazard}|{len(events)}|{last.isoformat()}|{_label(_index(today))}|{_file_sha1(_exposure_path())}'


def _chosen(hazard, events, today, tag):
    """
    What no period changes, built once for `tag` and shared by every `until`:
    {'places', 'in_use', 'buildings', 'candidate', 'report', 'version'}. For
    fire that is the comparison (about 200 small fits), the model it puts in
    use and that model's test against counting; for the other types, today's
    model and its test. `version` is '<model>@<sha1 of the tag, 12
    characters>' (spec 3.4).
    """
    from apps.history import fire_candidate

    digest = hashlib.sha1(tag.encode('utf-8')).hexdigest()

    def build():
        where = places()
        candidate, buildings = _fire_choice(events, where, today) if hazard == 'Fire' else (None, None)
        in_use = candidate['in_use'] if candidate else fire_candidate.F0_NAME
        return {'places': where, 'in_use': in_use, 'buildings': buildings, 'candidate': candidate,
                'report': evaluate(events, where, today, table_fn=_table_fn(in_use, buildings)),
                'version': f'{in_use}@{digest[:12]}'}
    return _once(CHOICE_KEY + digest, CHOICE_LOCK + digest, build)


def _real_by_hazard(events):
    kinds = defaultdict(list)
    for e in events:
        if e.get('hazard') and e.get('when') is not None and not e['is_sample']:
            kinds[e['hazard']].append(e)
    return kinds


def _fitted(hazard, events, until, today):
    """
    The test result and the table for one hazard type, cached until its record
    or the building counts change: {'places', 'report', 'table',
    'in_training', 'reason', 'version', 'candidate'}. The table is trained on
    the months before `until` (a period that has started), or on the whole
    record when they hold too few events, with `in_training` set. It is None,
    with `reason`, when the record is too small to train and test, or when the
    period comes before the record began.

    Fire's model in use is the winner of fire_candidate.compare (its result is
    `candidate`; None for the other types, which hold too few records). The
    comparison, the test and `version` do not depend on `until`: they are
    built once per records, month and building counts (_chosen) and shared by
    every period, so a period only adds the fit of its own table.
    """
    tag = _record_tag(hazard, events, today)
    # v3: the cached value gained version and candidate; fire's model is chosen by the comparison
    key = 'forecast-model-v3:' + hashlib.sha1(f'{tag}|{until}'.encode('utf-8')).hexdigest()

    def build():
        chosen = _chosen(hazard, events, today, tag)
        where, table_fn = chosen['places'], _table_fn(chosen['in_use'], chosen['buildings'])
        out = {'places': where, 'report': chosen['report'], 'table': None, 'in_training': False,
               'reason': TOO_FEW.format(hazard.lower()), 'version': chosen['version'],
               'candidate': chosen['candidate']}
        if out['report']['status'] == 'too_few_records':
            return out
        table = table_fn(events, where, until=until, today=today)
        if table is None and until is not None:
            first = min(e['when'] for e in _known(events, where))
            if until < date(first.year, first.month, 1):
                out['reason'] = RECORDS_START.format(hazard, first)
                return out
            table, out['in_training'] = table_fn(events, where, until=None, today=today), True
        if table is not None:
            out.update(table=table, reason=None)
        return out
    return cache.get_or_set(key, build, CACHE_SECONDS)


def warm_fire(today):
    """
    Fit fire now, so the cache holds its comparison, which every period
    shares, and the table the forecast for a period not yet started and the
    accuracy card read (spec 4.6). The records are read as the forecast reads
    them, so the cache keys are the ones its requests make.
    """
    from apps.history.views import _forecast_events     # the forecast's own reading of the records

    fires = _real_by_hazard(_forecast_events()).get('Fire')
    if fires:
        _fitted('Fire', fires, None, today)


def _added(tables):
    """One table from several hazard types: the events expected of any of them."""
    first = next(iter(tables.values()))
    return {pid: [sum(t[pid][m] for t in tables.values()) for m in range(12)] for pid in first}


def use_models(result, events, month, day=None, hazard=None, barangay=None, today=None):
    """
    Put the model's figures on a seasonal_forecast result for each hazard type
    whose model can run (_fitted). A period that has started is estimated from
    what came before it, or from the whole record, flagged, when that is too
    little. The year chart follows the models only when every hazard type it
    covers has one, so it never leaves a type out. Returns {hazard type: why it
    has no figures} for the types left as they were; the caller marks those
    unavailable, never counting; one whose model another request is still
    building after WAIT_SECONDS is unavailable with PREPARING.
    """
    today = today or date.today()
    window = result.get('window')
    until = window['start'] if window and window['start'] <= today else None
    kinds = {name: rows for name, rows in _real_by_hazard(events).items()
             if not hazard or name.lower() == hazard.lower()}
    tables, unavailable = {}, {}
    for name, rows in kinds.items():
        try:
            fitted = _fitted(name, rows, until, today)
        except Preparing:
            unavailable[name] = PREPARING.format(name.lower())
            continue
        if fitted['table'] is None:
            unavailable[name] = fitted['reason']
            continue
        apply_table(result, name, fitted['table'], fitted['places'], month, day, in_training=fitted['in_training'])
        tables[name] = fitted['table']
    if tables and len(tables) == len(kinds):
        apply_profile(result, _added(tables), barangay)
    result['model_hazards'] = list(tables)
    return unavailable


def _fire_logged(fires):
    """
    Fire's `logged` block: its prediction log's month rows scored against
    these fires (prediction_log.logged_summary, spec 3.5). None when nothing
    is logged or the log cannot be read: it never takes the accuracy card down.
    """
    from apps.history.hazard_data import Record
    from apps.history.prediction_log import logged_summary

    records = [Record('', 'Fire', e['barangay_id'], e['when'].date(), '', e['is_sample']) for e in fires]
    try:
        return logged_summary('Fire', records)
    except Exception:
        logger.exception("Fire's prediction log could not be scored; the accuracy card goes without it.")
        return None


def accuracy_reports(events, today):
    """
    The test result for every hazard type with real records, for the panel and
    the thesis, with `candidate`: fire's comparison of its two models (None
    for the other types). Fire's entry also has `logged`, its logged month
    chances against the fires since (_fire_logged).
    """
    kinds = _real_by_hazard(events)
    reports = []
    for name in sorted(kinds):
        fitted = _fitted(name, kinds[name], None, today)
        entry = {'hazard': name, **fitted['report'], 'candidate': fitted['candidate']}
        if name == 'Fire':
            entry['logged'] = _fire_logged(kinds[name])
        reports.append(entry)
    return reports
