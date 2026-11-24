"""
The flood susceptibility model on the website: each purok's flood class (Red,
Orange, Green, or not assessed with the reason), read from
data/flood_purok_model.json, which `manage.py train_flood_model` writes on a
developer machine. Nothing here fits or imports a model library.

Susceptibility says how flood-prone an area is, from where floods reached in
the 2017 UP Mananga survey. It is the same in every month and never says a
flood is coming. When the learned model failed its test, the file holds UP
NOAH-based classes instead (source 'noah').

Flood has no classes, with the reason, when the file is missing (not trained
yet), cannot be read, or was built on another version of the purok map.
"""
import json
import threading
import time
from dataclasses import dataclass
from datetime import datetime

from apps.history import flood_features as ff

NOT_TRAINED = 'The flood model has not been trained yet.'
STALE = 'The purok map changed since the flood model was trained; rerun build_flood_features and train_flood_model.'
UNREADABLE = 'The flood model file could not be read; rerun train_flood_model.'
REPORT_MISSING = "The flood model's report is missing; rerun train_flood_model."
NOT_BY_MONTH = 'Flood susceptibility does not change by month.'
BASIS_MODEL = ('From a machine-learning model of where floods reached in the 2017 UP Mananga flood survey (typhoons '
               'of 1990-2014), with UP NOAH flood depths and terrain. It shows how flood-prone an area is, not whether '
               'a flood is coming, and it is the same in every month.')
BASIS_NOAH = ("From UP NOAH's 25-year flood model, classed by where floods reached in the 2017 UP Mananga flood "
              'survey. It shows how flood-prone an area is, not whether a flood is coming, and it is the same in every '
              'month.')
LEVELS = ('Red', 'Orange', 'Green')
RANK = {'Green': 1, 'Orange': 2, 'Red': 3}

MODEL_FILE = ff.MODEL_FILE
REPORT_FILE = ff.REPORT_FILE
RECHECK_SECONDS = 60


@dataclass
class FloodModel:
    version: str
    source: str      # 'model' or 'noah'
    built_at: str
    areas: dict      # {purok id: {barangay_id, level, score, uncertain, not_assessed_reason, estimated_outline, buildings}}
    cutoffs: dict
    report: object   # the report file's contents, or None


_lock = threading.Lock()
_cache = {'at': None, 'key': None, 'value': None}


def clear_cache():
    """Forget the loaded file, so the next load() reads it again (tests, and after a retrain)."""
    with _lock:
        _cache.update(at=None, key=None, value=None)


def _mtime(path):
    try:
        return path.stat().st_mtime_ns
    except FileNotFoundError:
        return None


def _read(model_path, report_path, outlines):
    """The FloodModel, or the reason there is none; a file that can't be read is UNREADABLE, never an error."""
    try:
        data = json.loads(model_path.read_text(encoding='utf-8'))
    except FileNotFoundError:
        return NOT_TRAINED
    except (OSError, ValueError):
        return UNREADABLE
    if not isinstance(data, dict):
        return UNREADABLE
    if data.get('outlines_version') != outlines:
        return STALE
    report = None
    try:
        report = json.loads(report_path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        pass
    try:
        if not isinstance(report, dict) or report.get('version') != data['version']:
            report = None
        areas = {int(k): v for k, v in data['areas'].items()}
        for area in areas.values():
            if area['level'] not in (*LEVELS, None) or (area['level'] is None and not area['not_assessed_reason']):
                return UNREADABLE
        if data['source'] not in ('model', 'noah'):
            return UNREADABLE
        return FloodModel(version=data['version'], source=data['source'], built_at=data['built_at'], areas=areas,
                          cutoffs=data['cutoffs'], report=report)
    except (KeyError, TypeError, ValueError, AttributeError):
        return UNREADABLE


def load():
    """The FloodModel, or the sentence saying why flood has no classes. Rechecked at most every RECHECK_SECONDS."""
    from apps.barangays.models import Purok

    now = time.monotonic()
    with _lock:
        if _cache['at'] is not None and now - _cache['at'] < RECHECK_SECONDS:
            return _cache['value']
    model_path, report_path = MODEL_FILE, REPORT_FILE
    mtime = _mtime(model_path)
    if mtime is None:
        value, key = NOT_TRAINED, None
    else:
        outlines = Purok.outlines_version()
        key = (str(model_path), mtime, _mtime(report_path), outlines)
        with _lock:
            cached = _cache['value'] if _cache['key'] == key else None
        value = cached if cached is not None else _read(model_path, report_path, outlines)
    with _lock:
        _cache.update(at=now, key=key, value=value)
    return value


def basis(model) -> str:
    return BASIS_NOAH if getattr(model, 'source', None) == 'noah' else BASIS_MODEL


def purok_rows(model: FloodModel) -> list:
    """One row per purok: {purok_id, barangay_id, level (None when not assessed), uncertain, not_assessed_reason, estimated_outline}."""
    return [{'purok_id': pid, 'barangay_id': a['barangay_id'], 'level': a['level'], 'uncertain': bool(a['uncertain']),
             'not_assessed_reason': a['not_assessed_reason'], 'estimated_outline': bool(a['estimated_outline'])}
            for pid, a in sorted(model.areas.items())]


def flood_block(model) -> dict:
    """What the forecast says about flood as a whole: whether it has classes, from what, and that it is not monthly."""
    if isinstance(model, str):
        return {'available': False, 'reason': model, 'source': None, 'model_version': None, 'built_at': None,
                'basis': None, 'varies_by_month': False}
    return {'available': True, 'reason': None, 'source': model.source, 'model_version': model.version,
            'built_at': model.built_at, 'basis': basis(model), 'varies_by_month': False}


def _smallest_purok(point):
    from apps.barangays.models import Purok

    found = list(Purok.objects.filter(boundary__contains=point))
    return min(found, key=lambda p: p.boundary.area) if found else None


def located_floods(since: datetime | None = None) -> list:
    """
    The located floods on record, as (when, source): Flood records with a map
    point or at least one purok (by occurred_at), then "Affected here" marks on
    flood zones (by created_at); only those after `since` when it is given.
    One definition for "since publishing" and the readiness counts.
    """
    from apps.hazards.models import ZoneFieldMark
    from apps.history.models import HistoricalRecord

    records = HistoricalRecord.objects.filter(hazard_type__name='Flood').prefetch_related('puroks')
    marks = ZoneFieldMark.objects.filter(kind='Affected', zone__hazard_type__name='Flood')
    if since is not None:
        records, marks = records.filter(occurred_at__gt=since), marks.filter(created_at__gt=since)
    found = [(r.occurred_at, r) for r in records.order_by('occurred_at')
             if r.location is not None or r.puroks.exists()]
    found += [(m.created_at, m) for m in marks.order_by('created_at')]
    return found


def _puroks_of(source) -> list:
    """The puroks a located flood counts in: its point's smallest purok, else a record's linked puroks."""
    if source.location is not None:
        return [_smallest_purok(source.location)]
    return list(source.puroks.all())


def since_publishing(model: FloodModel) -> dict:
    """
    New located floods since the model was built, each checked against its
    purok's published class: Flood records with a map point or puroks, and
    "Affected here" marks on flood zones (located_floods). A flood in Green or
    not assessed is a miss. flood_rules.monitoring decides "under review".
    """
    from apps.history.flood_rules import monitoring

    built = datetime.fromisoformat(model.built_at)
    found = [(when, _puroks_of(source)) for when, source in located_floods(built)]
    levels, misses = [], []
    for when, puroks in found:
        best, name = None, None
        for p in puroks:
            level = model.areas.get(p.id, {}).get('level') if p is not None else None
            if name is None or RANK.get(level, 0) > RANK.get(best, 0):
                best, name = level, p.name if p is not None else 'Outside every purok'
        levels.append(best)
        if best not in ('Red', 'Orange'):
            misses.append({'day': when.date().isoformat(), 'purok': name, 'level': best or 'Not assessed'})
    return {**monitoring(levels), 'misses': misses}


TRAINED_ON = '2017 UP Mananga flood survey'


def readiness() -> dict:
    """
    Whether there is enough located flood data to improve the flood predictions
    (the "Predictive models" tab): located flood days on record against what a
    flood forecast would need, and new located floods since the flood map was
    published against the review threshold. Only counts and the map's
    metadata, never a location; it changes nothing.
    """
    from django.utils import timezone

    from apps.history.flood_rules import FORECAST_DAYS_MAX, FORECAST_DAYS_MIN, MONITOR_MIN

    days = len({timezone.localtime(when).date() for when, _ in located_floods()})
    model = load()
    if isinstance(model, str):
        flood_map, since = {'available': False, 'reason': model}, None
    else:
        flood_map = {'available': True, 'reason': None, 'version': model.version, 'built_at': model.built_at,
                     'trained_on': TRAINED_ON, 'survey_spots': (model.report or {}).get('survey_spots')}
        summary = since_publishing(model)
        since = {'n': summary['n'], 'review_after': MONITOR_MIN, 'under_review': summary['under_review']}
    return {
        'located_flood_days': days,
        'forecast_days_needed': {'min': FORECAST_DAYS_MIN, 'max': FORECAST_DAYS_MAX},
        'enough_for_forecasting': days >= FORECAST_DAYS_MIN,
        'flood_map': flood_map,
        'since_publishing': since,
    }
