"""
The landslide susceptibility model on the website: each purok's landslide
class (Red, Orange, Green, or not assessed with the reason), read from
data/landslide_purok_model.json, which `manage.py train_landslide_model`
writes on a developer machine. Nothing here fits or imports a model library.

Susceptibility says how prone ground is to sliding, from where landslides
started after Philippine typhoons. It is the same in every month and never
says a landslide is coming. When the learned model failed its tests, the file
holds UP NOAH-based classes instead (source 'noah').

Landslide has no classes, with the reason, when the file is missing (not
trained yet), cannot be read, or was built on another version of the purok
map. Every coordinate stays out: nothing here returns a point.
"""
import json
import threading
import time
from dataclasses import dataclass
from datetime import datetime

from apps.history import flood_purok
from apps.history import landslide_features as lf

NOT_TRAINED = 'The landslide model has not been trained yet.'
STALE = ('The purok map changed since the landslide model was trained; rerun build_landslide_features and '
         'train_landslide_model.')
UNREADABLE = 'The landslide model file could not be read; rerun train_landslide_model.'
REPORT_MISSING = "The landslide model's report is missing; rerun train_landslide_model."
NOT_BY_MONTH = 'Landslide susceptibility does not change by month.'
UNDER_REVIEW = 'Under review: recent landslides fall outside the flagged areas'
BASIS_MODEL = ('From a machine-learning model of where landslides started after Philippine typhoons (mapped from '
               "satellite images), applied to Talisay's terrain, land cover and roads. It shows how prone an area is "
               'to sliding, not whether a landslide is coming, and it is the same in every month.')
BASIS_NOAH = ("From UP NOAH's landslide hazard map, classed by where landslides started after Philippine typhoons. "
              'It shows how prone an area is to sliding, not whether a landslide is coming, and it is the same in '
              'every month.')
BASIS_GEOALERT = ('From a machine-learning model of where landslides started after Philippine typhoons and in '
                  "GeoAlert's own located landslide records, applied to Talisay's terrain, land cover and roads. It "
                  'shows how prone an area is to sliding, not whether a landslide is coming, and it is the same in '
                  'every month.')
LEVEL_WORDS = {'Red': 'High landslide susceptibility', 'Orange': 'Moderate landslide susceptibility',
               'Green': 'Low landslide susceptibility', None: 'Not assessed yet'}
SOURCES = ('model', 'noah', 'geoalert')
LEVELS = ('Red', 'Orange', 'Green')
HAZARD = 'Landslide'

MODEL_FILE = lf.MODEL_FILE
REPORT_FILE = lf.REPORT_FILE
RECHECK_SECONDS = 60


@dataclass
class LandslideModel:
    version: str
    source: str      # 'model', 'noah' or 'geoalert'
    built_at: str
    areas: dict      # {purok id: {barangay_id, level, score, uncertain, not_assessed_reason, estimated_outline, points}}
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


def parse(model, report, outlines):
    """The LandslideModel from a model document (a file's or a saved fit's) and its report, or the reason there is none."""
    if not isinstance(model, dict):
        return UNREADABLE
    if model.get('outlines_version') != outlines:
        return STALE
    try:
        if not isinstance(report, dict) or report.get('version') != model['version']:
            report = None
        areas = {int(k): v for k, v in model['areas'].items()}
        datetime.fromisoformat(model['built_at'])
        for area in areas.values():
            area['barangay_id'], area['uncertain'], area['estimated_outline']
            if area['level'] not in (*LEVELS, None) or (area['level'] is None and not area['not_assessed_reason']):
                return UNREADABLE
        if model['source'] not in SOURCES:
            return UNREADABLE
        return LandslideModel(version=model['version'], source=model['source'], built_at=model['built_at'],
                              areas=areas, cutoffs=model['cutoffs'], report=report)
    except (KeyError, TypeError, ValueError, AttributeError):
        return UNREADABLE


def _read_json(path):
    """(contents, None), or (None, the reason): a missing file is NOT_TRAINED, an unreadable one UNREADABLE."""
    try:
        return json.loads(path.read_text(encoding='utf-8')), None
    except FileNotFoundError:
        return None, NOT_TRAINED
    except (OSError, ValueError):
        return None, UNREADABLE


def load():
    """
    The LandslideModel, or the sentence saying why landslide has no classes.
    The newer of the live fit in the database and the committed file is used;
    when the live fit can't be read (the model_fit table not migrated yet, or
    no landslide fits), the file. Rechecked at most every RECHECK_SECONDS,
    reading only the live fit's id and built_at; its model is read only when
    they change.
    """
    from apps.barangays.models import Purok
    from apps.history.model_fits import fit_body, live_fit_head, newer_is_fit

    now = time.monotonic()
    with _lock:
        if _cache['at'] is not None and now - _cache['at'] < RECHECK_SECONDS:
            return _cache['value']
    model_path, report_path = MODEL_FILE, REPORT_FILE
    fit = live_fit_head('landslide')
    mtime = _mtime(model_path)
    if mtime is None and fit is None:
        value, key = NOT_TRAINED, None
    else:
        outlines = Purok.outlines_version()
        key = (str(model_path), mtime, _mtime(report_path), outlines, (fit.pk, fit.built_at) if fit else None)
        with _lock:
            cached = _cache['value'] if _cache['key'] == key else None
        if cached is not None:
            value = cached
        else:
            data, reason = _read_json(model_path)
            body = None
            if fit is not None and newer_is_fit(data if isinstance(data, dict) else None, fit):
                body = fit_body(fit)
                if body is None:
                    key = None  # not read: try again at the next recheck
            if body is not None:
                value = parse(*body, outlines)
            elif reason:
                value = reason
            else:
                report, _ = _read_json(report_path)
                value = parse(data, report, outlines)
    with _lock:
        _cache.update(at=now, key=key, value=value)
    return value


def basis(model) -> str:
    source = getattr(model, 'source', None)
    return BASIS_NOAH if source == 'noah' else BASIS_GEOALERT if source == 'geoalert' else BASIS_MODEL


def purok_rows(model: LandslideModel) -> list:
    """One row per purok: {purok_id, barangay_id, level (None when not assessed), uncertain, not_assessed_reason, estimated_outline}."""
    return [{'purok_id': pid, 'barangay_id': a['barangay_id'], 'level': a['level'], 'uncertain': bool(a['uncertain']),
             'not_assessed_reason': a['not_assessed_reason'], 'estimated_outline': bool(a['estimated_outline'])}
            for pid, a in sorted(model.areas.items())]


def landslide_block(model) -> dict:
    """What the forecast says about landslide as a whole: whether it has classes, from what, and that it is not monthly."""
    if isinstance(model, str):
        return {'available': False, 'reason': model, 'source': None, 'model_version': None, 'built_at': None,
                'basis': None, 'varies_by_month': False}
    return {'available': True, 'reason': None, 'source': model.source, 'model_version': model.version,
            'built_at': model.built_at, 'basis': basis(model), 'varies_by_month': False}


def located_landslides(since: datetime | None = None) -> list:
    """The located landslides on record, as (when, source), by the flood rules: records with a point or a purok, then "Affected here" marks on landslide zones."""
    return flood_purok.located_floods(since, hazard_name=HAZARD)


def located_spots() -> list:
    """Every located landslide spot with a map point, oldest first, for the retraining job (the points never leave except through the token endpoint)."""
    return flood_purok.located_spots(hazard_name=HAZARD)


def since_publishing(model: LandslideModel) -> dict:
    """
    New located landslides since the model was built, each checked against its
    purok's published class (flood's rules, flood_purok.since_publishing); one
    in Green or not assessed is a miss.
    """
    return flood_purok.since_publishing(model, hazard_name=HAZARD)


def readiness_line() -> dict:
    """{n, barangays, needed, barangays_needed, enough}: located landslide spots with a map point against the floor for own data. Counts only."""
    from apps.history.landslide_own import OWN_MIN_BARANGAYS, OWN_MIN_SPOTS, floor

    counted = floor(located_spots())
    return {'n': counted['n'], 'barangays': counted['barangays'], 'needed': OWN_MIN_SPOTS,
            'barangays_needed': OWN_MIN_BARANGAYS, 'enough': counted['enough']}
