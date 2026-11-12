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
"""
import hashlib
from calendar import monthrange
from collections import Counter, defaultdict
from datetime import date
from math import exp, log

import numpy as np
from django.core.cache import cache

from apps.history import forecast

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
CACHE_SECONDS = 6 * 60 * 60
AREA_SRID = 32651  # UTM 51N, metres over Cebu

# Why a hazard type has no figures; the forecast shows these on its unavailable rows
TOO_FEW = 'Too few {} records to train and test its model.'
RECORDS_START = '{} records start in {:%B %Y}.'
MODEL_DOWN = 'The fire model could not run right now.'


def chance(rate):
    """The chance of at least one event, given how many are expected."""
    return 1 - exp(-rate)


def level_for(share):
    if share >= HIGH_CHANCE:
        return 'High'
    if share >= MODERATE_CHANCE:
        return 'Moderate'
    return 'Low'


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


def evaluate(events, places, today):
    """
    Hold back the last TEST_MONTHS of the record, train on the months before
    them and score the model and counting on them. 'status' says what follows:
    in_use, in_use_not_better (the model is still used; never counting) or
    too_few_records (no figures).
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

    table = rates_table(train, places, until=date(split // 12, split % 12 + 1, 1), today=today)
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


def _real_by_hazard(events):
    kinds = defaultdict(list)
    for e in events:
        if e.get('hazard') and e.get('when') is not None and not e['is_sample']:
            kinds[e['hazard']].append(e)
    return kinds


def _fitted(hazard, events, until, today):
    """
    The test result and the table for one hazard type, cached until its record
    changes: {'places', 'report', 'table', 'in_training', 'reason'}. The table
    is trained on the months before `until` (a period that has started), or on
    the whole record when they hold too few events, with `in_training` set. It
    is None, with `reason`, when the record is too small to train and test, or
    when the period comes before the record began.
    """
    last = max(e['when'] for e in events)
    tag = f'{hazard}|{len(events)}|{last.isoformat()}|{until}|{_label(_index(today))}'
    # v2: the cached value gained in_training and reason, and a table whenever the record allows one
    key = 'forecast-model-v2:' + hashlib.sha1(tag.encode('utf-8')).hexdigest()

    def build():
        where = places()
        out = {'places': where, 'report': evaluate(events, where, today), 'table': None, 'in_training': False,
               'reason': TOO_FEW.format(hazard.lower())}
        if out['report']['status'] == 'too_few_records':
            return out
        table = rates_table(events, where, until=until, today=today)
        if table is None and until is not None:
            first = min(e['when'] for e in _known(events, where))
            if until < date(first.year, first.month, 1):
                out['reason'] = RECORDS_START.format(hazard, first)
                return out
            table, out['in_training'] = rates_table(events, where, until=None, today=today), True
        if table is not None:
            out.update(table=table, reason=None)
        return out
    return cache.get_or_set(key, build, CACHE_SECONDS)


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
    unavailable, never counting.
    """
    today = today or date.today()
    window = result.get('window')
    until = window['start'] if window and window['start'] <= today else None
    kinds = {name: rows for name, rows in _real_by_hazard(events).items()
             if not hazard or name.lower() == hazard.lower()}
    tables, unavailable = {}, {}
    for name, rows in kinds.items():
        fitted = _fitted(name, rows, until, today)
        if fitted['table'] is None:
            unavailable[name] = fitted['reason']
            continue
        apply_table(result, name, fitted['table'], fitted['places'], month, day, in_training=fitted['in_training'])
        tables[name] = fitted['table']
    if tables and len(tables) == len(kinds):
        apply_profile(result, _added(tables), barangay)
    result['model_hazards'] = list(tables)
    return unavailable


def accuracy_reports(events, today):
    """The test result for every hazard type with real records, for the panel and the thesis."""
    kinds = _real_by_hazard(events)
    return [{'hazard': name, **_fitted(name, kinds[name], None, today)['report']} for name in sorted(kinds)]
