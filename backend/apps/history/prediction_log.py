"""
The fire purok prediction log (spec 8.3 and 6.6): each purok's fire chance
and level for the current month as the map shows it, kept in
fire_purok_prediction_log so the model can be scored honestly on fires that
came after each row was issued. A trigger (migration 0010) keeps every row
as it was written.

One snapshot per Manila day: `manage.py log_hazard_predictions` writes it,
and so does the hazard list (the busiest public call) in a background thread,
at most once a day (log_in_background). Both write only on the one machine
with settings.HAZARD_LOG_WRITER on (the deployed server). Rows are only
added (bulk_create with ignore_conflicts on the unique key), so a rerun adds
nothing.

The flood susceptibility log (flood_purok_susceptibility_log, migration
0011) gets one row per purok per published flood model version
(write_flood_rows), by the same command and the same daily hook; a rerun adds
nothing, and a trigger keeps every row as it was written.

The older hazard_prediction_log (migration 0008) held the flood, landslide
and barangay fire chances of the models removed on 2026-11-22; its rows stay
unchanged and nothing writes to it.
"""
import logging
import math
import threading
from calendar import monthrange
from datetime import datetime, timedelta

import numpy as np
from django.conf import settings
from django.core.cache import cache
from django.db import DatabaseError, ProgrammingError, connection, transaction

logger = logging.getLogger(__name__)

MARKER_SECONDS = 2 * 24 * 60 * 60  # the once-a-day marker outlives its Manila day, then goes
RUNNING_SECONDS = 5 * 60           # one background run at a time
NO_TABLE = 'is migration history 0010 applied?'
NOT_WRITTEN = 'The fire purok log was not written (%s): %s'
NOT_READ = 'The fire purok log could not be read (%s): %s'


def _why(exc):
    return NO_TABLE if isinstance(exc, ProgrammingError) else 'the database refused it'


def write_failure(exc) -> str:
    """What to say of a refused write: the migration hint only for a missing table, else the database's words."""
    return NOT_WRITTEN % (_why(exc), exc)


def write_month_rows(today) -> int:
    """
    One row per purok in the fire model for today's month, issued today under
    the model's version; returns how many were new. Nothing is written unless
    settings.HAZARD_LOG_WRITER is on and the model can be used.
    """
    from apps.barangays.models import Purok
    from apps.history import fire_purok
    from apps.history.models import FirePurokPredictionLog

    if not settings.HAZARD_LOG_WRITER:
        return 0
    model = fire_purok.load()
    if isinstance(model, str):
        return 0
    names = dict(Purok.objects.filter(id__in=list(model.areas)).values_list('id', 'name'))
    start = today.replace(day=1)
    rows = []
    for pid, area in model.areas.items():
        m = area['months'][today.month - 1]
        rows.append(FirePurokPredictionLog(
            purok_id=pid, purok_name=names.get(pid, ''), barangay_id=area['barangay_id'], period_start=start,
            issued_on=today, model_version=model.version, probability=m['p'], level=m['level'],
            limited_data=bool(area['limited_data'])))
    issued = FirePurokPredictionLog.objects.filter(issued_on=today, model_version=model.version)
    before = issued.count()
    FirePurokPredictionLog.objects.bulk_create(rows, ignore_conflicts=True)
    return issued.count() - before


def write_flood_rows(today) -> int:
    """
    One row per purok of the flood model in use, published today under its
    version; returns how many were new (0 once the version is logged). Nothing
    is written unless settings.HAZARD_LOG_WRITER is on and the model can be used.
    """
    from apps.barangays.models import Purok
    from apps.history import flood_purok
    from apps.history.models import FloodPurokSusceptibilityLog

    if not settings.HAZARD_LOG_WRITER:
        return 0
    model = flood_purok.load()
    if isinstance(model, str):
        return 0
    names = dict(Purok.objects.filter(id__in=list(model.areas)).values_list('id', 'name'))
    outlines = Purok.outlines_version()
    rows = [FloodPurokSusceptibilityLog(
        purok_id=pid, purok_name=names.get(pid, ''), barangay_id=area['barangay_id'], model_version=model.version,
        source=model.source, level=area['level'], score=area.get('score'), uncertain=bool(area['uncertain']),
        not_assessed_reason=area['not_assessed_reason'] or '', outlines_version=outlines, published_on=today)
        for pid, area in model.areas.items()]
    logged = FloodPurokSusceptibilityLog.objects.filter(model_version=model.version)
    before = logged.count()
    FloodPurokSusceptibilityLog.objects.bulk_create(rows, ignore_conflicts=True)
    return logged.count() - before


def _done_marker(today):
    return f'fire-purok-log-done:{today.isoformat()}'


def log_once_today(today) -> bool:
    """
    Today's rows, at most once a Manila day (a cache marker, set once they are
    written): the fire model's month rows and, once per version, the flood
    model's classes. True when this call wrote them; False when they were
    written already, neither model can be used yet, or the database refused
    (a table not migrated yet, say: logged, and tried again on a later call).
    The map never depends on it.
    """
    from apps.history import fire_purok, flood_purok

    if not settings.HAZARD_LOG_WRITER or cache.get(_done_marker(today)):
        return False
    fire_ready = not isinstance(fire_purok.load(), str)
    flood_ready = not isinstance(flood_purok.load(), str)
    if not fire_ready and not flood_ready:
        return False
    try:
        if fire_ready:
            write_month_rows(today)
        if flood_ready:
            write_flood_rows(today)
    except DatabaseError as exc:
        logger.warning('%s', write_failure(exc))
        return False
    cache.set(_done_marker(today), True, MARKER_SECONDS)
    return True


def _run(today):
    try:
        log_once_today(today)
    except Exception:
        logger.exception('The daily fire purok log failed.')
    finally:
        connection.close()  # this thread's own connection


def log_in_background(today):
    """Start today's log in a background thread, once: only on the writer machine and only if not done yet."""
    if not settings.HAZARD_LOG_WRITER:
        return
    try:
        if cache.get(_done_marker(today)) or not cache.add(f'fire-purok-log-running:{today.isoformat()}', 1,
                                                            RUNNING_SECONDS):
            return
    except Exception:
        logger.warning('Cache unavailable; the daily fire purok log waits for it')
        return
    threading.Thread(target=_run, args=(today,), daemon=True).start()


def _auc(y, p):
    """ROC-AUC by ranks (Mann-Whitney), or None with one class."""
    pos, neg = int(y.sum()), int(len(y) - y.sum())
    if not pos or not neg:
        return None
    order = np.argsort(p, kind='stable')
    ranks = np.empty(len(p))
    ranks[order] = np.arange(1, len(p) + 1)
    for v in np.unique(p):  # ties share their mean rank
        same = p == v
        ranks[same] = ranks[same].mean()
    return float((ranks[y == 1].sum() - pos * (pos + 1) / 2) / (pos * neg))


def prospective_summary(today) -> dict | None:
    """
    How the logged chances did on fires that came after them (spec 6.6), for
    months that ended before `today`. Each purok-month counts once, at its
    earliest-issued row (the chance given at the time), and only for the days
    after that row was issued: its chance is scaled to those days,
    1 − (1 − p)^(days left / days in month), and a fire counts when it is
    linked to the purok on one of them. None before any month can be scored,
    or when the log can't be read (the table not migrated yet, say).

    {first, last (YYYY-MM), rows, months, fires_after, expected,
     scores: {log_loss, brier, roc_auc}}; point values, no intervals: the
    first verdict is due after about 12 months (spec 6.6).
    """
    from apps.history.models import FirePurokPredictionLog, HistoricalRecord

    this_month = today.replace(day=1)
    try:
        with transaction.atomic():  # a refused query never spoils a transaction the caller is in
            logged = list(FirePurokPredictionLog.objects.filter(period_start__lt=this_month)
                          .order_by('purok_id', 'period_start', 'issued_on', 'id')
                          .distinct('purok_id', 'period_start')
                          .values_list('purok_id', 'period_start', 'issued_on', 'probability'))
    except DatabaseError as exc:
        logger.warning(NOT_READ, _why(exc), exc)
        return None
    if not logged:
        return None
    from django.utils import timezone

    first = min(start for _, start, _, _ in logged)
    tz = timezone.get_current_timezone()
    links = (HistoricalRecord.puroks.through.objects
             .filter(historicalrecord__hazard_type__name__iexact='fire',
                     historicalrecord__occurred_at__gte=timezone.make_aware(datetime(first.year, first.month, 1), tz))
             .values_list('purok_id', 'historicalrecord__occurred_at'))
    burned = {(pid, timezone.localtime(when, tz).date()) for pid, when in links}  # (purok, Manila day) with a fire
    y, p = [], []
    for pid, start, issued, chance in logged:
        days = monthrange(start.year, start.month)[1]
        end = start.replace(day=days)
        left = (end - issued).days  # the row covers the days after it was issued, to the month's end
        if left <= 0:
            continue
        y.append(1 if any((pid, end - timedelta(days=k)) in burned for k in range(left)) else 0)
        p.append(1 - (1 - chance) ** (left / days))
    if not y:
        return None
    y, p = np.array(y), np.clip(np.array(p), 1e-6, 1 - 1e-6)
    starts = sorted({start for _, start, _, _ in logged})
    return {
        'first': f'{starts[0]:%Y-%m}', 'last': f'{starts[-1]:%Y-%m}', 'rows': int(len(y)), 'months': len(starts),
        'fires_after': int(y.sum()), 'expected': round(float(p.sum()), 4),
        'scores': {'log_loss': float(-(y * np.log(p) + (1 - y) * np.log(1 - p)).mean()),
                   'brier': float(((p - y) ** 2).mean()), 'roc_auc': _auc(y, p)},
    }
