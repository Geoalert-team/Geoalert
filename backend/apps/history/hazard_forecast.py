"""
Flood and landslide on the forecast: the model in use, and the rows, levels
and chart it gives.

deployed() scores the saved fit that `manage.py test_hazard_models` wrote into
its report (version 2, spec 3.1-3.2) for every barangay-day of the rain file:
the model in use, `two_part` or `logistic_regression`, is never refitted here,
only scored with NumPy (hazard_scoring.py). The result is kept until an input
file changes (its cache key covers them all) and built behind a lock, so one
request builds it while the others wait.
use_hazard_models() turns those daily chances into each period's chance by
replaying past years' rain (hazard_scenarios.py) and puts them on a
seasonal_forecast result (spec 2.3-2.6). A model that cannot run gives
"unavailable" rows with a reason: no hazard falls back to counting, and the
combined chance counts model figures only. Fire's model (model_forecast.py)
and the counting history (forecast.py) are read, never changed.

Flood's two-part model reads the storm flag (storms.py): a day the storm days
do not reach gets no flood chance, like a day with missing rain. Landslide
and the logistic regression never read the storm days, so while flood's model
in use is the logistic regression it needs neither the storm file nor IBTrACS.
"""
import hashlib
import json
import logging
import threading
import time
from calendar import monthrange
from collections import ChainMap
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from math import prod

import numpy as np
from django.core.cache import cache
from django.db import connections

from apps.history import forecast, hazard_data, model_forecast, storms
from apps.history.hazard_data import (
    HAZARDS, MANILA, RAIN_FEATURES, STUDY_END, STUDY_START, TERRAIN_FEATURES, build_dataset, read_terrain)
from apps.history.hazard_scenarios import (
    any_chance, pair_chance, period_chance, period_dates, scenario_dates, shift_dates)
from apps.history.hazard_scoring import score_logistic, score_two_part
from apps.history.model_forecast import chance, level_for
from apps.history.rain import RainFile, complete_years, read_rain_csv, recent_rain
from apps.history.two_part import FEATURES, NO_EXPOSURE, when_row

logger = logging.getLogger(__name__)

# The key changes with every input file (_inputs), so a build never goes stale and the time limit only
# bounds the cache. Each rebuild takes minutes on a small server and slows every request meanwhile.
CACHE_SECONDS = 7 * 24 * 60 * 60
# Except a build that read the live storm days (flood's two-part model): those are not in the key, so it
# is redone this often, and a storm that came near since reaches the flood chances
LIVE_STORMS_CACHE_SECONDS = 6 * 60 * 60
# The warm-up's daily jobs (the storm refresh, the prediction log) ran on this Manila day
WARMED_DAY_KEY = 'geoalert:hazard-warm-day'
WARMED_DAY_SECONDS = 2 * 24 * 60 * 60
LOCK_SECONDS = 300
WAIT_SECONDS = 60
POLL_SECONDS = 0.5
WARM_THREAD_NAME = 'hazard-model-warm-up'

PREPARING = 'The model is being prepared; try again in a minute.'
REPORT_MISSING = 'The model report is missing; run manage.py test_hazard_models.'
FILE_MISSING = {
    'rain': 'The rain data (rain_daily.csv) is missing; run manage.py fetch_rain.',
    'terrain': 'The terrain figures (barangay_terrain.csv) are missing; run manage.py build_hazard_features.',
    'storms': 'The storm days (storm_days.csv) are missing; run manage.py fetch_storms.',
}
NO_TERRAIN = 'No terrain figures for this barangay yet.'
NO_RAIN = 'No rain series for this barangay yet.'
NO_DAYS = 'No day with a complete 14-day rain record for this barangay yet.'
NO_RAIN_YEARS = 'no rain years before this period'
NO_SCENARIO = 'No complete rain year for this barangay before this period.'
MODELS_DOWN = 'The flood and landslide models are unavailable right now.'
# Why a barangay the two-part fit has no share for gets no chance: its "where" part reads the exposure
# figures (flood) or the terrain figures (landslide).
NO_SHARE = {'Flood': NO_EXPOSURE, 'Landslide': NO_TERRAIN}

# Every hazard on the forecast, in the order the API lists them
FORECAST_HAZARDS = ('Fire', *HAZARDS)
BOTH_PARAMETERS = 'Use hazards or hazard_type_name, not both.'

# Swapped by the tests, so the wait for another request's build runs on a fake clock.
_sleep = time.sleep
_monotonic = time.monotonic
# cache.add is not atomic in the file cache, so threads of one process take turns at the lock key.
_LOCK = threading.Lock()


class Unavailable(Exception):
    """The model cannot run; the message is a plain sentence for the page."""


@dataclass
class Deployed:
    """The model in use for one hazard and its chance for every barangay-day of the rain file."""
    hazard: str
    name: str               # the model in use, as the report names it: 'two_part' or 'logistic_regression'
    version: str            # f'{name}@{the report's sha1, 12 characters}'
    fit: dict               # its saved fit, from the report
    daily: dict             # {barangay_id: {date: chance}}, the days whose inputs are complete
    reasons: dict           # {barangay_id: why it has no chances}: in only one of the two files, or no share
    complete_years: list    # the rain file's complete years: the scenario years
    rain: RainFile
    terrain: dict           # {barangay_id: terrain figures}
    storms: object          # flood's two-part model: the StormDays its storm flag was read from; otherwise None

    def city(self):
        """
        The barangay whose rain the two-part model reads as the city's: the
        lowest one with terrain figures and a rain series (every barangay reads
        the one NASA POWER cell, as test_hazard_models does).
        """
        return min(set(self.terrain) & set(self.rain.rain))

    def reason(self, barangay_id):
        """None when the barangay has chances, else why not."""
        if self.daily.get(barangay_id):
            return None
        if barangay_id in self.reasons:
            return self.reasons[barangay_id]
        if barangay_id not in self.terrain:
            return NO_TERRAIN
        if barangay_id not in self.rain.rain:
            return NO_RAIN
        return NO_DAYS

    def score(self, rain, storm_days, first, last):
        """
        [(barangay id, day, chance)] from the saved fit, for the barangays in
        `daily` on the days first..last whose inputs are complete. `rain` is
        {barangay id: {date: mm}} for every barangay with terrain figures and
        a rain series. The two-part model reads the city's rain (city()) and,
        for flood, the storm flag in `storm_days`; the logistic regression
        reads each barangay's rain sums and terrain figures.
        """
        ids = sorted(self.daily)
        if not ids:
            return []
        if self.name == 'logistic_regression':
            ds, _ = build_dataset(self.hazard, {b: self.terrain[b] for b in ids}, rain, set(), first, last)
            return list(zip(ds.barangay_id.tolist(), ds.day.tolist(), score_logistic(self.fit, ds.X).tolist()))
        city = rain[self.city()]
        days, X = [], []
        for i in range((last - first).days + 1):
            d = first + timedelta(days=i)
            row = when_row(self.hazard, city, storm_days, d)
            if row is not None:
                days.append(d)
                X.append(row)
        if not days:
            return []
        index = np.repeat(np.arange(len(days)), len(ids))
        barangays = np.tile(np.array(ids), len(days))
        chances = score_two_part(self.fit, np.array(X, dtype=float), index, barangays)
        return [(b, days[i], p) for b, i, p in zip(barangays.tolist(), index.tolist(), chances.tolist())]


# ---- The deployed model: cache key, lock and build ----

@dataclass
class _Inputs:
    key: str
    lock: str
    report_sha1: str
    entry: dict             # the report's entry for the hazard
    paths: dict


def _sha1(missing, *paths):
    """sha1 of the files' bytes, one after another, as test_hazard_models hashes them; Unavailable(missing) when
    one cannot be read."""
    digest = hashlib.sha1()
    try:
        for path in paths:
            digest.update(path.read_bytes())
    except OSError as exc:
        raise Unavailable(missing) from exc
    return digest.hexdigest()


def _reads_storms(hazard, name):
    """Whether model `name`, in use for the hazard, reads the storm flag: only flood's two-part model does."""
    return name == 'two_part' and 'storm72' in FEATURES[hazard]


def _features(hazard, name):
    """The inputs, in order, that this code builds for a saved fit of model `name`."""
    return list(FEATURES[hazard]) if name == 'two_part' else [*RAIN_FEATURES, *TERRAIN_FEATURES[hazard]]


def _inputs(hazard) -> _Inputs:
    """
    What the build depends on and the cache key over it: the hazard, the
    report's bytes, the rain and terrain files as they are now (a refreshed
    rain file changes the daily chances) and, when the model in use reads the
    storm flag (flood's two-part model), the storm days (storm_days.csv, then
    its meta file). The records and the exclusions play no part: only
    test_hazard_models reads them. Paths are read here, never bound at import,
    so they follow DATA_DIR and REPORT_PATH.
    """
    if hazard not in HAZARDS:
        raise ValueError(f'No rain-and-terrain model for {hazard}.')
    from apps.history import hazard_models      # it loads scikit-learn, which only test_hazard_models fits with
    data = hazard_data.DATA_DIR
    paths = {'report': hazard_models.REPORT_PATH, 'rain': data / 'rain_daily.csv',
             'terrain': data / 'barangay_terrain.csv'}
    report_sha1 = _sha1(REPORT_MISSING, paths['report'])
    report = hazard_models.read_report(paths['report'])
    if report is None:
        raise Unavailable(REPORT_MISSING)
    if report.get('version') != hazard_models.REPORT_VERSION:
        raise Unavailable(hazard_models.REPORT_OLD)
    entries = report.get('hazards')
    entry = entries.get(hazard) if isinstance(entries, dict) else None
    name = entry.get('in_use') if isinstance(entry, dict) else None
    fits = entry.get('fits') if isinstance(entry, dict) else None
    fit = fits.get(name) if isinstance(fits, dict) and name in hazard_models.REPORT_MODELS else None
    if not isinstance(fit, dict):
        raise Unavailable(f'The model report has no {hazard.lower()} result; run manage.py test_hazard_models.')
    saved = fit['when'].get('features') if name == 'two_part' else fit.get('features')
    if saved != _features(hazard, name):
        raise Unavailable(hazard_models.REPORT_OLD)     # fitted on inputs this code no longer builds
    files = [_sha1(FILE_MISSING[part], paths[part]) for part in ('rain', 'terrain')]
    if _reads_storms(hazard, name):
        paths.update(storms=data / storms.STORM_FILE.name, storms_meta=data / storms.META_FILE.name)
        files.append(_sha1(FILE_MISSING['storms'], paths['storms'], paths['storms_meta']))
    digest = hashlib.sha1(json.dumps([hazard, report_sha1, *files]).encode('utf-8')).hexdigest()
    return _Inputs(f'hazard-model:{digest}', f'hazard-model-lock:{digest}', report_sha1, entry, paths)


def cache_key(hazard: str) -> str:
    """The cache key the hazard's deployed model is kept under now."""
    return _inputs(hazard).key


def _live_storms(base, today):
    """
    The storm days with the recent and active IBTrACS files merged in
    (storms.live_storm_days), or the file's alone when that fails: a storm
    data problem only leaves the latest days without a flood chance.
    """
    try:
        return storms.live_storm_days(base, today)
    except Exception:
        logger.exception('The live storm days could not be read; the storm file, to %s, is used alone.',
                         base.last_day)
        return base


def _build(hazard, inputs: _Inputs) -> Deployed:
    """Score the saved fit for every barangay-day of the rain file. Nothing is fitted here."""
    rf = read_rain_csv(inputs.paths['rain'])
    terrain = read_terrain(inputs.paths['terrain'])
    ids = set(terrain) & set(rf.rain)
    if not ids:
        raise Unavailable('No barangay has both terrain figures and a rain series yet.')
    name = inputs.entry['in_use']
    storm_days = None
    if _reads_storms(hazard, name):
        try:
            base = storms.read_storm_days(inputs.paths['storms'], inputs.paths['storms_meta'])
        except OSError as exc:              # removed since the cache key was made
            raise Unavailable(FILE_MISSING['storms']) from exc
        storm_days = _live_storms(base, datetime.now(MANILA).date())
    fit = inputs.entry['fits'][name]
    reasons = {b: NO_TERRAIN for b in set(rf.rain) - set(terrain)}
    reasons.update({b: NO_RAIN for b in set(terrain) - set(rf.rain)})
    if name == 'two_part':
        # a barangay the fit has no share for gets no chance at all, never a chance of 0
        shares = {int(b) for b in fit['shares']}
        reasons.update({b: NO_SHARE[hazard] for b in ids - shares})
        ids &= shares
    dep = Deployed(hazard, name, f'{name}@{inputs.report_sha1[:12]}', fit, {b: {} for b in sorted(ids)}, reasons,
                   complete_years(rf), rf, terrain, storm_days)
    for b, d, p in dep.score(rf.rain, storm_days, rf.first_day, rf.last_day):
        dep.daily[b][d] = p
    return dep


def deployed(hazard: str) -> Deployed:
    """
    The hazard's model in use, from the cache or built now. One request builds
    while the others poll the cache; one that waits WAIT_SECONDS gives up with
    Unavailable. A build that fails releases the lock, so the next request tries.
    """
    inputs = _inputs(hazard)
    deadline = _monotonic() + WAIT_SECONDS
    while True:
        hit = cache.get(inputs.key)
        if hit is not None:
            return hit
        with _LOCK:
            mine = cache.add(inputs.lock, 1, LOCK_SECONDS)
        if mine:
            try:
                hit = cache.get(inputs.key)      # set while this request was taking the lock
                if hit is not None:
                    return hit
                built = _build(hazard, inputs)
                keep = CACHE_SECONDS if built.storms is None else LIVE_STORMS_CACHE_SECONDS
                cache.set(inputs.key, built, keep)
                return built
            finally:
                with _LOCK:
                    cache.delete(inputs.lock)
        if _monotonic() >= deadline:
            raise Unavailable(PREPARING)
        _sleep(POLL_SECONDS)


def _today():
    """Today in Manila, the day the daily jobs and the prediction log count by."""
    return datetime.now(MANILA).date()


def warm_in_background() -> bool:
    """
    Start the warm-up in a daemon thread when either model is missing from the
    cache, or once a Manila day for its daily jobs (the storm refresh and the
    prediction log, where the builds are cache hits), and no build is running.
    True only when a thread was started. A hazard that cannot run (flood
    without its storm days, say) is logged and left out of the check, so the
    other is still warmed.
    """
    ready = []
    for hazard in HAZARDS:
        try:
            ready.append(_inputs(hazard))
        except Unavailable as exc:
            logger.warning('The %s model cannot be warmed: %s', hazard.lower(), exc)
        except Exception:
            logger.exception('Could not tell whether the %s model is ready.', hazard.lower())
    if not ready or any(cache.has_key(i.lock) for i in ready):
        return False
    today = _today().isoformat()
    if all(cache.has_key(i.key) for i in ready) and cache.get(WARMED_DAY_KEY) == today:
        return False
    # Marked before the thread starts, so the checks while it runs start no second one
    cache.set(WARMED_DAY_KEY, today, WARMED_DAY_SECONDS)
    threading.Thread(target=_warm, name=WARM_THREAD_NAME, daemon=True).start()
    return True


def _warm():
    today = _today()
    try:
        # the last-3-years storm tracks first, at most once a Manila day; without them the models are still
        # built, and only the latest days may go without a flood chance
        try:
            if not storms.refresh_recent():
                logger.warning('The recent storm tracks could not be refreshed; the latest days may have no '
                               'flood chance.')
        except Exception:
            logger.exception('Refreshing the recent storm tracks failed; the models are warmed without them.')
        for hazard in HAZARDS:
            try:
                deployed(hazard)
            except Unavailable as exc:
                logger.warning('The %s model could not be warmed: %s', hazard.lower(), exc)
            except Exception:
                logger.exception('Warming the %s model failed.', hazard.lower())
        # then fire's, refitted with its comparison (spec 4.6); a failure stops nothing
        try:
            model_forecast.warm_fire(today)
        except Exception:
            logger.exception('Warming the fire model failed.')
        # last, today's chances into the prediction log, from the models just warmed (at most once a Manila day,
        # and only on the machine with HAZARD_LOG_WRITER on)
        try:
            from apps.history import prediction_log     # it reads the history models, so not at import
            prediction_log.log_once_today(today)
        except Exception:
            logger.exception('Writing the prediction log failed.')
    finally:
        connections.close_all()          # this thread's own connections; it would leak one per warm-up


# ---- Rows on a seasonal_forecast result ----

def _rounded(x, digits):
    """
    round(x, digits), except that a positive value it would send as 0 keeps 2
    significant figures (0.00041234 gives 0.00041), so a positive chance is
    never sent as 0. An exact 0 stays 0 and None stays None.
    """
    if x is None:
        return None
    value = round(x, digits)
    if value != 0 or x <= 0:
        return value
    return float(f'{x:.2g}')


def _rank_key(row):
    """forecast.rank_rows' order, worst first, with a missing figure ranked lowest instead of failing."""
    def down(value):
        return float('inf') if value is None else -value
    return (-forecast.LEVELS.index(row['level']), down(row['probability']), down(row['expected_events']),
            row['barangay'])


def _rerank(result):
    result['results'].sort(key=_rank_key)
    result['by_barangay'] = forecast.summarize_by_barangay(
        [r for r in result['results'] if r['probability'] is not None and r['expected_events'] is not None])


def _listed(result, key, hazard):
    names = result.setdefault(key, [])
    if hazard not in names:
        names.append(hazard)


def _hazard_rows(result, hazard, places):
    """
    {barangay id: row} for this hazard, one per place. A missing row is made
    with the history defaults model_forecast.apply_table uses; a row for a
    barangay that is not a place (no boundary, or no barangay at all) is
    removed, since it has no terrain and so no figure. Its events still count
    in `outcome`.
    """
    ids = {p['id'] for p in places}
    rows, kept = {}, []
    for r in result['results']:
        if r['hazard_type'] == hazard:
            if r['barangay_id'] not in ids or r['barangay_id'] in rows:
                continue
            rows[r['barangay_id']] = r
        kept.append(r)
    result['results'][:] = kept
    for place in places:
        if place['id'] in rows:
            continue
        row = {'barangay_id': place['id'], 'barangay': place['name'], 'hazard_type': hazard, 'years_hit': 0,
               'years_considered': len(result['years']), 'limited': result['limited'], 'typical_severity': None,
               'events': 0, 'last_occurred': None}
        if result.get('outcome') is not None:
            row['actual'] = 0
        result['results'].append(row)
        rows[place['id']] = row
    return rows


def _set_unavailable(row, reason):
    for key in ('model', 'range', 'rain_years', 'recorded_rain_probability', 'in_training'):
        row.pop(key, None)
    row.update(method='unavailable', probability=None, expected_events=None, level='None', reason=reason)


def _set_model(row, name, pc, month_pc):
    for key in ('reason', 'recorded_rain_probability', 'in_training'):
        row.pop(key, None)
    row.update(method='model', model=name, probability=_rounded(pc.probability, 3),
               expected_events=_rounded(pc.expected, 2), level=level_for(month_pc.probability),
               range=[_rounded(pc.low, 3), _rounded(pc.high, 3)], rain_years=list(pc.years))


def mark_unavailable(result, hazard, places, reason):
    """Every place's row of this hazard unavailable with `reason`, and the hazard in `unavailable_hazards`."""
    for row in _hazard_rows(result, hazard, places).values():
        _set_unavailable(row, reason)
    _listed(result, 'unavailable_hazards', hazard)
    _rerank(result)


def mark_profile_unavailable(result):
    """No figure in the 12-month chart, rather than a counting one."""
    if result.get('profile') is None:
        return
    for entry in result['profile']:
        entry.update(probability=None, expected_events=None, level='None')
    result['profile_method'] = 'unavailable'


@dataclass
class Recorded:
    """A period's days with recorded rain: their chances and the inputs they were scored from."""
    chances: dict           # {barangay id: {day: chance}}
    rain: Mapping           # {barangay id: {day: mm}}: the rain file's days, then the live feed's after them
    file_storms: object     # flood's two-part model: the storm days the rain file's days were scored with; else None
    late_storms: object     # flood's two-part model: those the days after the rain file were scored with; else None
    last_file_day: object   # the rain file's last day

    def storms_on(self, day):
        """The storm days `day`'s chance read its storm flag from (None when the model reads no storm flag)."""
        late = self.last_file_day is not None and day > self.last_file_day
        return self.late_storms if late else self.file_storms


def recorded(dep, period, today) -> Recorded:
    """
    The period's days with recorded rain: the rain file's days, then the days
    after it that the live feed has, scored as the file's days are, from
    windows of file and live rain together and, for flood's two-part model,
    the live storm days. When the live feed is down those days are not
    recorded; a day the storm days do not reach has no two-part flood chance.
    """
    out = {b: {d: series[d] for d in period if d in series} for b, series in dep.daily.items()}
    rf = dep.rain
    rec = Recorded(out, rf.rain, dep.storms, dep.storms, rf.last_day)
    late = [d for d in period if rf.last_day is not None and rf.last_day < d < today]
    if not late:
        return rec
    try:
        recent = recent_rain(rf.cells, after=rf.last_day, today=today)
    except Exception:
        logger.exception('The recent rain could not be read; the days after the rain file count as not recorded.')
        recent = None
    if not recent:
        return rec
    rec.rain = {b: ChainMap(recent.get(b) or {}, rf.rain[b]) for b in set(dep.terrain) & set(rf.rain)}
    rec.late_storms = None if dep.storms is None else _live_storms(dep.storms, today)
    for b, d, p in dep.score(rec.rain, rec.late_storms, late[0], late[-1]):
        out[b][d] = p
    return rec


def _recorded_chances(dep, period, today):
    """{barangay id: {day: chance}} for the period's days with recorded rain (recorded())."""
    return recorded(dep, period, today).chances


def _moved(days, period, scenario, s, day, year):
    """
    Scenario year s's dates for some of the period's days, laid out as
    scenario_dates lays them: by place in the week, or by shift_dates in a
    month (29 February onto 28 February, counted once).
    """
    if day is not None:
        at = dict(zip(period, scenario))
        moved = [at[d] for d in days]
    else:
        moved = [shift_dates([d], year, s)[0] for d in days]
    return list(dict.fromkeys(moved))


def _recorded_rain_probability(actual, daily, period, dates_by_s, day, year):
    """
    The chance with the rain recorded so far: the recorded days with their own
    chance, the others with each scenario's, averaged over the scenarios.
    None when no day of the period is recorded.
    """
    if not actual:
        return None
    kept = prod(1.0 - actual[d] for d in period if d in actual)
    rest = [d for d in period if d not in actual]
    if not rest:
        return _rounded(1.0 - kept, 3)
    values = []
    for s, dates in dates_by_s.items():
        ps = [daily.get(d) for d in _moved(rest, period, dates, s, day, year)]
        if any(p is None for p in ps):
            continue
        values.append(1.0 - kept * prod(1.0 - p for p in ps))
    return _rounded(sum(values) / len(values), 3) if values else None


def _apply(result, hazard, dep, *, month, day, year, places, today):
    dates_by_s = scenario_dates(month, day, year, dep.complete_years)
    month_dates_by_s = scenario_dates(month, None, year, dep.complete_years) if day is not None else dates_by_s
    out = {'deployed': dep, 'chances': {}, 'dates_by_s': dates_by_s, 'month_dates_by_s': month_dates_by_s}
    if not dates_by_s:
        mark_unavailable(result, hazard, places, NO_RAIN_YEARS)
        return out
    period = period_dates(month, day, year) if year is not None else None
    recorded = _recorded_chances(dep, period, today) if period else {}
    in_training = period is not None and STUDY_START <= period[0] <= STUDY_END
    for b, row in _hazard_rows(result, hazard, places).items():
        reason = dep.reason(b)
        if reason is None:
            pc = period_chance(dep.daily[b].get, dates_by_s)
            month_pc = pc if month_dates_by_s is dates_by_s else period_chance(dep.daily[b].get, month_dates_by_s)
            if pc is None or month_pc is None:
                reason = NO_SCENARIO
        if reason is not None:
            _set_unavailable(row, reason)
            _listed(result, 'unavailable_hazards', hazard)
            continue
        _set_model(row, dep.name, pc, month_pc)
        if period:
            value = _recorded_rain_probability(recorded.get(b), dep.daily[b], period, dates_by_s, day, year)
            if value is not None:
                row['recorded_rain_probability'] = value
        if in_training:
            row['in_training'] = True
        out['chances'][b] = pc
    if out['chances']:
        _listed(result, 'model_hazards', hazard)
    return out


def _apply_profile(result, dep, barangay, places):
    """The 12-month chart: each month's chance for the barangay, or the mean over the barangays."""
    if result.get('profile') is None:
        return
    if barangay is not None:
        ids = [barangay] if dep.reason(barangay) is None else []
    else:
        ids = [p['id'] for p in places if dep.reason(p['id']) is None]
    shown = False
    for entry in result['profile']:
        dates_by_s = scenario_dates(entry['month'], None, result.get('year'), dep.complete_years)
        chances = [pc for pc in (period_chance(dep.daily[b].get, dates_by_s) for b in ids) if pc is not None]
        if not chances:
            entry.update(probability=None, expected_events=None, level='None')
            continue
        p = sum(pc.probability for pc in chances) / len(chances)
        expected = sum(pc.expected for pc in chances) / len(chances)
        entry.update(probability=_rounded(p, 3), expected_events=_rounded(expected, 2), level=level_for(p))
        shown = True
    result['profile_method'] = 'model' if shown else 'unavailable'


def use_hazard_models(result, *, month, day, year, hazards, barangay, places, today):
    """
    Put the flood and landslide models' figures on a seasonal_forecast result:
    every place gets a model row or an unavailable row for each of them that
    is in `hazards` (spec 2.5, 2.6). Their counting rows are replaced, never
    kept. With exactly one of them asked for, the 12-month chart is its own
    (spec 2.4). Returns {hazard: {'deployed', 'chances', 'dates_by_s',
    'month_dates_by_s'}} for the combined chance.
    """
    out = {}
    for hazard in [h for h in hazards if h in HAZARDS]:
        dep = reason = None
        try:
            dep = deployed(hazard)
        except Unavailable as exc:
            logger.warning('The %s model is unavailable: %s', hazard.lower(), exc)
            reason = str(exc)
        except Exception:
            logger.exception('The %s model could not run.', hazard.lower())
            reason = f'The {hazard.lower()} model could not run right now.'
        if dep is None:
            mark_unavailable(result, hazard, places, reason)
            out[hazard] = {'deployed': None, 'chances': {}, 'dates_by_s': {}, 'month_dates_by_s': {}}
        else:
            out[hazard] = _apply(result, hazard, dep, month=month, day=day, year=year, places=places, today=today)
        if list(hazards) == [hazard]:
            if dep is None:
                mark_profile_unavailable(result)
            else:
                _apply_profile(result, dep, barangay, places)
    if out:
        _rerank(result)
    return out


# ---- Every hazard together: the request's hazards and the combined chance (spec 3.2, 3.3) ----

def parse_hazards(params, valid):
    """
    The hazards a forecast request covers, in the order of `valid`: from
    ?hazards=Fire,Flood, a comma list read without regard to case, spaces or
    repeats, or from ?hazard_type_name=Flood, the same as hazards=Flood.
    Neither, or an empty list, means every hazard. Raises ValueError with a
    sentence for the page when both are given or a name is unknown.
    """
    listed = (params.get('hazards') or '').strip()
    single = (params.get('hazard_type_name') or '').strip()
    if listed and single:
        raise ValueError(BOTH_PARAMETERS)
    names = [n.strip() for n in (listed or single).split(',') if n.strip()]
    known = {v.lower(): v for v in valid}
    unknown = list(dict.fromkeys(n for n in names if n.lower() not in known))
    if unknown:
        raise ValueError(f'Unknown hazard: {", ".join(unknown)}. Use one or more of {", ".join(valid)}.')
    wanted = {known[n.lower()] for n in names}
    return [v for v in valid if not wanted or v in wanted]


def fire_fit(result, events, today):
    """
    Fire's cached fit (model_forecast._fitted) that fire's rows on this result
    came from, read with the events, `until` and day that use_models used, or
    None when fire's model put no figures on it. Read only.
    """
    if 'Fire' not in result.get('model_hazards', []):
        return None
    fires = model_forecast._real_by_hazard(events).get('Fire')
    if not fires:
        return None
    window = result.get('window')
    until = window['start'] if window and window['start'] <= today else None
    return model_forecast._fitted('Fire', fires, until, today)


def fire_month_table(result, events, today):
    """
    Fire's table of events expected per month, {barangay id: [January, ...,
    December]}, from the fit its rows on this result came from (fire_fit),
    else None.
    """
    fit = fire_fit(result, events, today)
    return None if fit is None else fit['table']


def _counts(row, table=None, b=None):
    """
    A row with a model figure. A row with no model behind it (a counting
    share) never counts: every hazard's chance comes from its model. Fire's
    also needs its month table to hold the barangay.
    """
    if row is None or row.get('method') != 'model' or row.get('probability') is None:
        return False
    return row['hazard_type'] != 'Fire' or (table is not None and b in table)


def _fire_part(table, b, month, week):
    """
    Fire's (period chance, month chance, expected events) for barangay b from
    its table, as apply_table reads it (the week is rate x 7 / days in the month).
    """
    rate = table[b][month - 1]
    return chance(rate * week), chance(rate), rate * week


def _rain_chance(gets, dates_by_s):
    """
    The PeriodChance of any of one or two rain hazards, from their daily
    chances `gets`. Two share the storms, so they are combined day by day
    inside each rain scenario (pair_chance); one is its own period chance.
    """
    if len(gets) == 2:
        return pair_chance(gets[0], gets[1], dates_by_s)
    return period_chance(gets[0], dates_by_s)


def _rain_part(scen, rain, b):
    """(period chance, month chance) of the counted rain hazards for barangay b, or None."""
    first = scen[rain[0]]
    gets = [scen[h]['deployed'].daily[b].get for h in rain]
    pc = _rain_chance(gets, first['dates_by_s'])
    same = first['month_dates_by_s'] is first['dates_by_s']
    month_pc = pc if same else _rain_chance(gets, first['month_dates_by_s'])
    if pc is None or month_pc is None:
        return None
    return pc.probability, month_pc.probability


def _combined_key(row):
    """Worst first: the level, then the chance (none last), then the name."""
    down = float('inf') if row['probability'] is None else -row['probability']
    return -forecast.LEVELS.index(row['level']), down, row['barangay']


def _combined_profile(profile, scen, fire_table, included, year, barangay, places):
    """
    Each month's combined chance, as (chance, expected events) or None: the
    barangay's, or the mean over the barangays with a figure. Fire gives its
    table's month chance (it has none when its model is not in use); flood
    and landslide give their scenario chance for the month.
    """
    ids = [barangay] if barangay is not None else [p['id'] for p in places]
    deps = [scen[h]['deployed'] for h in HAZARDS if h in included and scen.get(h, {}).get('deployed') is not None]
    out = []
    for entry in profile:
        m = entry['month']
        values = []
        for b in ids:
            parts, expected = [], 0.0
            if 'Fire' in included and fire_table is not None and b in fire_table:
                rate = fire_table[b][m - 1]
                parts.append(chance(rate))
                expected += rate
            here = [d for d in deps if d.reason(b) is None]
            if here:
                dates_by_s = scenario_dates(m, None, year, here[0].complete_years)
                pc = _rain_chance([d.daily[b].get for d in here], dates_by_s)
                if pc is not None:
                    parts.append(pc.probability)
                    expected += pc.expected
            if parts:
                values.append((any_chance(parts), expected))
        out.append((sum(p for p, _ in values) / len(values), sum(e for _, e in values) / len(values))
                   if values else None)
    return out


def combine(result, scen, fire_table, included, month, day, year, barangay, places, today):
    """
    The chance that at least one of the included hazards is reported in each
    barangay in the period (spec 3.2), as `combined`, with `by_barangay` in
    its old shape built from it, `hazards_included`, and `results` limited to
    the included hazards. With more than one hazard, the 12-month chart is
    the combined chance month by month.

    Flood and landslide share the storms, so when both count they are
    combined day by day inside each rain scenario (pair_chance over Task 9's
    scenario dates); fire has no rain input and is treated as independent of
    them (any_chance). A hazard with no figure for a barangay (no row, or an
    unavailable one) is left out of its chance and named in `missing`. The
    level comes from the combined chance for the MONTH, as every level does.
    `scen` is use_hazard_models' return value, read and never changed;
    `fire_table` is fire_month_table's. Nothing on `result` changes until
    every figure is worked out, so a failure leaves it as it was.
    """
    included = list(included)
    week = (2 * forecast.DAY_WINDOW + 1) / monthrange(year or 2001, month)[1] if day else 1
    results = [r for r in result['results'] if r['hazard_type'] in included]
    rows = {}
    for r in results:
        rows.setdefault((r['hazard_type'], r['barangay_id']), r)

    combined = []
    for place in places:
        b = place['id']
        # a flood or landslide figure only ever comes from its model, never from counting
        missing = [h for h in included if not _counts(rows.get((h, b)), fire_table, b)
                   or (h in HAZARDS and b not in scen.get(h, {}).get('chances', {}))]
        period, month_parts, single, expected = [], [], {}, 0.0
        if 'Fire' in included and 'Fire' not in missing:
            p, pm, e = _fire_part(fire_table, b, month, week)
            period.append(p)
            month_parts.append(pm)
            single['Fire'] = p
            expected += e
        rain = [h for h in HAZARDS if h in included and h not in missing]
        if rain:
            part = _rain_part(scen, rain, b)
            if part is None:
                missing = [h for h in included if h in missing or h in rain]
            else:
                period.append(part[0])
                month_parts.append(part[1])
                for h in rain:
                    pc = scen[h]['chances'][b]
                    single[h] = pc.probability
                    expected += pc.expected
        counted = [h for h in included if h not in missing]
        hazards = [{'hazard_type': h, 'probability': rows[(h, b)]['probability'], 'level': rows[(h, b)]['level']}
                   if h in counted else {'hazard_type': h, 'probability': None, 'level': 'None'}
                   for h in included]
        if counted:
            figures = {'probability': _rounded(any_chance(period), 3), 'expected_events': _rounded(expected, 2),
                       'level': level_for(any_chance(month_parts)), 'top_hazard': max(counted, key=single.get)}
        else:
            figures = {'probability': None, 'expected_events': None, 'level': 'None', 'top_hazard': None}
        combined.append({'barangay_id': b, 'barangay': place['name'], **figures, 'hazards': hazards,
                         'missing': missing})
    combined.sort(key=_combined_key)

    # the old shape for the existing callers: names of the hazards with a level, now from the combined chance
    by_barangay = [{'barangay_id': r['barangay_id'], 'barangay': r['barangay'], 'level': r['level'],
                    'top_hazard': r['top_hazard'], 'probability': r['probability'],
                    'hazards': sorted(h['hazard_type'] for h in r['hazards']
                                      if h['hazard_type'] not in r['missing'] and h['level'] != 'None')}
                   for r in combined if r['probability'] is not None]

    profile = None
    if len(included) > 1 and result.get('profile') is not None:
        profile = _combined_profile(result['profile'], scen, fire_table, included, year, barangay, places)

    result['results'][:] = results
    result['hazards_included'] = included
    result['combined'] = combined
    result['by_barangay'] = by_barangay
    if profile is not None:
        for entry, value in zip(result['profile'], profile):
            if value is None:
                entry.update(probability=None, expected_events=None, level='None')
            else:
                entry.update(probability=_rounded(value[0], 3), expected_events=_rounded(value[1], 2),
                             level=level_for(value[0]))
        result['profile_method'] = 'model' if any(v is not None for v in profile) else 'unavailable'
