"""
The prediction log (spec 3.4-3.5): the chances the app shows, kept in
hazard_prediction_log so the 2026 wet season and after can be scored against
what happened. A trigger (migration 0008) keeps every row as it was written.

Two kinds of row:
- `day`: flood's and landslide's chance for each rain day, from the model in
  use, with the inputs it read (hazard_forecast.recorded): every day with a
  chance after the last day logged under that model version, at most
  BACKFILL_DAYS back, up to yesterday.
- `month`: every hazard's chance and level for the current month in each
  barangay, exactly as the forecast page shows them (views.forecast_result),
  one snapshot per Manila day.

Rows are only added (bulk_create with ignore_conflicts on the unique key), so
a rerun adds nothing. A barangay with no figure (an unavailable row) is never
logged. `manage.py log_hazard_predictions` writes the rows; the warm-up thread
does too, at most once a Manila day (log_once_today). Both write only on the
one machine with settings.HAZARD_LOG_WRITER on (the deployed server).
logged_summary scores them for test_hazard_models' `logged` block.
"""
import logging
from datetime import datetime, time, timedelta

from django.conf import settings
from django.core.cache import cache
from django.db import DatabaseError, ProgrammingError, transaction
from django.db.models import Max

from apps.history.hazard_data import HAZARDS, MANILA, RAIN_FEATURES, TERRAIN_FEATURES, rain_windows
from apps.history.models import HazardPredictionLog
from apps.history.two_part import FEATURES, when_row

logger = logging.getLogger(__name__)

BACKFILL_DAYS = 30
RAIN_SOURCE = 'NASA POWER PRECTOTCORR'
DAY, MONTH = 'day', 'month'
MARKER_SECONDS = 2 * 24 * 60 * 60       # the once-a-day marker outlives its Manila day, then goes
NO_TABLE = 'is migration history 0008 applied?'
NOT_WRITTEN = 'The prediction log was not written (%s): %s'
NOT_READ = 'The prediction log could not be read (%s): %s'


def write_failure(exc) -> str:
    """What to say of a refused write: the migration hint only for a missing table, else the database's own words."""
    return NOT_WRITTEN % (NO_TABLE if isinstance(exc, ProgrammingError) else 'the database refused it', exc)


def _insert(rows, kind, today) -> int:
    """Add the rows, skipping any the unique key already holds; returns how many were new."""
    if not rows:
        return 0
    issued = HazardPredictionLog.objects.filter(kind=kind, issued_on=today)
    before = issued.count()
    HazardPredictionLog.objects.bulk_create(rows, ignore_conflicts=True)
    return issued.count() - before


def _day_inputs(dep, rec, barangay_id, day) -> dict:
    """
    What the day's chance was read from, from the same rain and storm days it
    was scored with (rec): the rain sums the model reads (the city's for the
    two-part model, the barangay's own for the logistic regression), the
    rain source, for flood's two-part model the storm flag and name, and
    whether any input lay above its training maximum.
    """
    storm_days = rec.storms_on(day)
    if dep.name == 'two_part':
        series = rec.rain[dep.city()]
        values = dict(zip(FEATURES[dep.hazard], when_row(dep.hazard, series, storm_days, day)))
        used = [f.removeprefix('log1p_') for f in FEATURES[dep.hazard] if f.startswith('log1p_')]
        windows = rain_windows(series, day)
    else:
        windows = rain_windows(rec.rain[barangay_id], day)
        values = {**windows, **{f: dep.terrain[barangay_id][f] for f in TERRAIN_FEATURES[dep.hazard]}}
        used = RAIN_FEATURES
    out = {'rain_mm': {k: windows[k] for k in used}, 'rain_source': RAIN_SOURCE}
    if dep.storms is not None:                  # flood's two-part model reads the storm flag; no other model does
        out.update(storm72=None if storm_days is None else storm_days.flag(day),
                   storm=None if storm_days is None else storm_days.name(day))
    top = dep.fit.get('training_max') or {}
    out['outside_training'] = any(top.get(f) is not None and v > top[f] for f, v in values.items())
    return out


def write_day_rows(today) -> int:
    """
    Flood's and landslide's chance for every day with one, after the last day
    logged under the model version in use and at most BACKFILL_DAYS back, up
    to yesterday. A model that cannot run is skipped (the warm-up says why).
    Returns how many rows were added.
    """
    from apps.barangays.models import Barangay
    from apps.history import hazard_forecast

    rows = []
    for hazard in HAZARDS:
        try:
            dep = hazard_forecast.deployed(hazard)
        except hazard_forecast.Unavailable as exc:
            logger.info('No %s day rows logged: %s', hazard.lower(), exc)
            continue
        first = today - timedelta(days=BACKFILL_DAYS)
        last = (HazardPredictionLog.objects.filter(hazard=hazard, kind=DAY, model_version=dep.version)
                .aggregate(last=Max('period_start'))['last'])
        if last is not None:
            first = max(first, last + timedelta(days=1))
        period = [first + timedelta(days=i) for i in range((today - first).days)]
        if not period:
            continue
        rec = hazard_forecast.recorded(dep, period, today)
        known = set(Barangay.objects.filter(id__in=list(rec.chances)).values_list('id', flat=True))
        for b in sorted(known):
            for d, p in sorted(rec.chances[b].items()):
                rows.append(HazardPredictionLog(hazard=hazard, barangay_id=b, kind=DAY, period_start=d,
                                                issued_on=today, model_version=dep.version, probability=p,
                                                inputs=_day_inputs(dep, rec, b, d)))
    return _insert(rows, DAY, today)


def write_month_rows(today) -> int:
    """
    Every hazard's chance and level for the current month in each barangay
    with a figure, as the forecast shows them (views.forecast_result for this
    month and year), under the version of the model each came from. Fire's
    rows also carry the events its table expects in the month. One snapshot
    per issued_on; returns how many rows were added.
    """
    from apps.history import hazard_forecast
    from apps.history.forecast import MAX_YEARS
    from apps.history.views import _forecast_events, forecast_result

    result = forecast_result(month=today.month, day=None, year=today.year,
                             included=list(hazard_forecast.FORECAST_HAZARDS), barangay=None, years=MAX_YEARS,
                             exclude_samples=False, now=datetime.combine(today, time(12), tzinfo=MANILA))
    versions, fire_table = {}, None
    for hazard in result['model_hazards']:
        if hazard == 'Fire':
            fit = hazard_forecast.fire_fit(result, _forecast_events(), today)
            if fit is not None:         # None only if the fires went between the two readings
                versions[hazard], fire_table = fit['version'], fit['table']
        else:
            versions[hazard] = hazard_forecast.deployed(hazard).version
    rows = []
    for r in result['results']:
        hazard, b = r['hazard_type'], r['barangay_id']
        if hazard not in versions or r.get('method') != 'model' or r.get('probability') is None or b is None:
            continue
        inputs = {'method': r['method'], 'in_training': bool(r.get('in_training'))}
        if 'rain_years' in r:
            inputs['scenario_years'] = r['rain_years']
        rows.append(HazardPredictionLog(
            hazard=hazard, barangay_id=b, kind=MONTH, period_start=today.replace(day=1), issued_on=today,
            model_version=versions[hazard], probability=r['probability'], level=r['level'],
            expected_events=fire_table[b][today.month - 1] if hazard == 'Fire' else None, inputs=inputs))
    return _insert(rows, MONTH, today)


def log_once_today(today) -> bool:
    """
    The day and month rows for `today`, at most once a Manila day (a cache
    marker, set only once both are written): the warm-up thread's run. True
    when this call wrote them; False when they were already written today, or
    the database refused (the table not migrated yet, say), which is logged
    once and tried again on the next warm-up. The forecast never depends on it.
    Only the one machine with settings.HAZARD_LOG_WRITER on writes; on any
    other this writes nothing and returns False.
    """
    if not settings.HAZARD_LOG_WRITER:
        return False
    marker = f'hazard-log-done:{today.isoformat()}'
    if cache.get(marker):
        return False
    try:
        write_day_rows(today)
        write_month_rows(today)
    except DatabaseError as exc:
        logger.warning('%s', write_failure(exc))
        return False
    cache.set(marker, True, MARKER_SECONDS)
    return True


def logged_summary(hazard: str, records, today=None, fallback=None) -> dict | None:
    """
    The `logged` block for one hazard (spec 3.5): test_hazard_models' for
    flood and landslide (and their live accuracy entries,
    hazard_models.accuracy_entries), fire's accuracy entry for fire
    (model_forecast.accuracy_reports). None before anything is logged;
    `fallback` (default None) when the log cannot be read (before the table
    exists, say). Flood and landslide are scored on their `day` rows, fire on
    its `month` rows. When a barangay's day (or month) was logged more than
    once, under a new model version or in a later snapshot, the earliest-issued
    row counts: the chance given at the time.

    The events are the real records with a barangay (hazard_data.Record).
    `events` counts those on logged rows, set against `expected`, the sum of
    the rows' chances (fire: of the events they expected), with the exact
    95% Poisson interval of the count. `new_events` lists every event from
    the first logged day (month) to the last, with its barangay's id and
    name, its logged chance, the chance the day before (not for fire) and the
    model version, or None where its barangay had no chance logged.

    Fire scores only months that have ended before `today` (default: today's
    Manila date), so a month in progress, whose events are still coming in, is
    never set against its full-month expectation.
    """
    fire = hazard == 'Fire'
    if today is None:
        today = datetime.now(MANILA).date()
    try:
        # in a savepoint, so a refused query (no table yet) never spoils a transaction the caller is in
        with transaction.atomic():
            logged = list(HazardPredictionLog.objects.filter(hazard=hazard, kind=MONTH if fire else DAY)
                          .order_by('issued_on', 'id')
                          .values_list('barangay_id', 'period_start', 'probability', 'expected_events',
                                       'model_version'))
    except DatabaseError as exc:
        logger.warning(NOT_READ, NO_TABLE if isinstance(exc, ProgrammingError) else 'the database refused it', exc)
        return fallback
    first_given = {}
    for b, start, p, expected, version in logged:
        if fire and start >= today.replace(day=1):
            continue
        first_given.setdefault((b, start), (p, expected, version))
    if not first_given:
        return None
    from apps.history.hazard_verdict import poisson_interval

    starts = sorted({start for _, start in first_given})
    first, last = starts[0], starts[-1]

    def period(day):
        """The period_start of the row that covers `day`."""
        return day.replace(day=1) if fire else day

    real = [r for r in records if not r.is_sample and r.barangay_id is not None and first <= period(r.day) <= last]
    # every fire counts; a flood or landslide counts once per barangay-day, as the models' rows do
    new = sorted((r.day, r.barangay_id) for r in real) if fire else sorted({(r.day, r.barangay_id) for r in real})
    events = sum(1 for d, b in new if (b, period(d)) in first_given)
    expected = sum((e if fire else p) or 0.0 for p, e, _ in first_given.values())
    from apps.barangays.models import Barangay
    names = dict(Barangay.objects.filter(id__in={b for _, b in new}).values_list('id', 'name'))
    listed = []
    for d, b in new:
        p, _, version = first_given.get((b, period(d)), (None, None, None))
        entry = {'day': d.isoformat(), 'barangay_id': b, 'barangay': names.get(b), 'chance': p}
        if not fire:
            entry['chance_before'] = first_given.get((b, d - timedelta(days=1)), (None,))[0]
        listed.append({**entry, 'model_version': version})
    return {'first': first.isoformat(), 'last': last.isoformat(), 'rows': len(first_given), 'events': events,
            'expected': round(expected, 4), 'events_interval': [round(x, 4) for x in poisson_interval(events)],
            'new_events': listed}
