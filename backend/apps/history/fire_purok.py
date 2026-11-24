"""
The fire risk model on the website: each purok's chance of a fire and its
Red / Orange / Green level, read from data/fire_purok_model.json, which
`manage.py train_fire_model` writes on a developer machine. Nothing here
fits or imports a model library: it reads numbers from the file.

The fire model is adapted from the City of Pittsburgh Bureau of Fire /
Carnegie Mellon Metro21 fire risk model (github.com/CityofPittsburgh/
fire_risk_analysis, MIT License, © 2017 mmadaio).

Fire has no figures, with the reason, when the file is missing (not trained
yet) or was trained on another version of the purok map: a reloaded map may
keep an id for a different place, so a stale file is never shown.
"""
import json
import math
import threading
import time
from calendar import monthrange
from dataclasses import dataclass

from apps.history import fire_features as ff

NOT_TRAINED = 'The fire model has not been trained yet.'
STALE = 'The purok map changed since the fire model was trained; rerun build_fire_features and train_fire_model.'
BEFORE_RECORDS = 'Fire records start in January 2023.'
NO_AREAS = 'The fire model has no purok areas in this barangay.'
UNREADABLE = 'The fire model file could not be read; rerun train_fire_model.'
FIRST_RECORD_MONTH = (2023, 1)
BASIS = ("From a fire risk model adapted from the City of Pittsburgh Bureau of Fire's, trained on BFP fires with "
         'building, road and land-cover features.')

# A barangay's level keeps the forecast's monthly lines: 25% and over is High, 15% Moderate
BARANGAY_HIGH = 0.25
BARANGAY_MODERATE = 0.15

MODEL_FILE = ff.MODEL_FILE
REPORT_FILE = ff.REPORT_FILE
RECHECK_SECONDS = 60


@dataclass
class FireModel:
    version: str
    areas: dict      # {purok id: {barangay_id, limited_data, months: [{p, level, low, high} × 12]}}
    cutoffs: dict
    trained: dict    # {start: 'YYYY-MM', end: 'YYYY-MM', fires, unplaced}
    report: object   # the report file's contents, or None
    model: dict | None = None  # {family, settings} the fit was chosen with


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


def parse(data, report, outlines):
    """
    The FireModel from a model document (a file's or a saved fit's) and its
    report, or the reason there is none. A document that isn't the shape
    train_fire_model writes makes fire unavailable with UNREADABLE, never an
    error: the forecast, the accuracy card and a fire report's approval all
    read it.
    """
    if not isinstance(data, dict):
        return UNREADABLE
    if data.get('outlines_version') != outlines:
        return STALE
    try:
        if not isinstance(report, dict) or report.get('version') != data['version']:
            report = None  # from another training run
        areas = {int(k): v for k, v in data['areas'].items()}
        for area in areas.values():
            if len(area['months']) != 12 or not all(0 < m['p'] < 1 for m in area['months']):
                return UNREADABLE
        return FireModel(version=data['version'], areas=areas, cutoffs=data['cutoffs'], trained=data['trained'],
                         report=report, model=data.get('model'))
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


def _read(model_path, report_path, outlines):
    """The FireModel from the files, or the reason there is none."""
    data, reason = _read_json(model_path)
    if reason:
        return reason
    report, _ = _read_json(report_path)  # missing or unreadable: the report is reported missing
    return parse(data, report, outlines)


def load():
    """
    The FireModel, or the sentence saying why fire has no figures
    (NOT_TRAINED or STALE). The newer of the live fit in the database and the
    committed file is used; when the live fit can't be read (the model_fit
    table not migrated yet, say), the file. Kept per process, keyed by the
    files' times, the live fit's id and built_at and the purok map's version,
    which are checked at most every RECHECK_SECONDS; the fit's model is read
    only when that key changes.
    """
    from apps.barangays.models import Purok
    from apps.history.model_fits import fit_body, live_fit_head, newer_is_fit

    now = time.monotonic()
    with _lock:
        if _cache['at'] is not None and now - _cache['at'] < RECHECK_SECONDS:
            return _cache['value']
    model_path, report_path = MODEL_FILE, REPORT_FILE
    fit = live_fit_head('fire')
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


def barangay_level(chance):
    """'High', 'Moderate' or 'Low' for a barangay's monthly chance."""
    if chance >= BARANGAY_HIGH:
        return 'High'
    return 'Moderate' if chance >= BARANGAY_MODERATE else 'Low'


def week_fraction(month, day, year):
    """The share of the month a week period covers (DAY_WINDOW days either side of `day`), else 1."""
    from apps.history.forecast import DAY_WINDOW

    return (2 * DAY_WINDOW + 1) / monthrange(year or 2001, month)[1] if day else 1.0


def purok_rows(model, month, week_fraction=1.0):
    """
    One row per purok in the model for `month` (1-12): {purok_id,
    barangay_id, probability, level, interval, limited_data}. For a week the
    chance is 1 − (1 − p)^week_fraction (and its interval likewise); the level
    stays the month's.
    """
    def scale(p):
        return round(1 - (1 - p) ** week_fraction, 4)

    rows = []
    for pid, area in model.areas.items():
        m = area['months'][month - 1]
        rows.append({'purok_id': pid, 'barangay_id': area['barangay_id'], 'probability': scale(m['p']),
                     'level': m['level'], 'interval': [scale(m['low']), scale(m['high'])],
                     'limited_data': bool(area['limited_data'])})
    rows.sort(key=lambda r: (-r['probability'], r['purok_id']))
    return rows


def barangay_table(model):
    """{barangay id: [rate for January..December]}: Σ −ln(1 − p) over the barangay's puroks."""
    table = {}
    for area in model.areas.values():
        rates = table.setdefault(area['barangay_id'], [0.0] * 12)
        for i, m in enumerate(area['months']):
            rates[i] -= math.log(1 - m['p'])
    return table


def _chance(rate):
    return 1 - math.exp(-rate)


def _in_training(model, month, year):
    if year is None:
        return False
    period = f'{year:04d}-{month:02d}'
    return model.trained['start'] <= period <= model.trained['end']


def apply(result, model, month, day, year, today):
    """
    Fire's figures on a forecast result (views.forecast_result): each
    barangay row's chance from its puroks, the 12-month chart, and
    `purok_results`. A period before fire records begin has no figures.
    """
    from apps.history import forecast_rows

    where = forecast_rows.places()
    if year is not None and (year, month) < FIRST_RECORD_MONTH:
        forecast_rows.mark_unavailable(result, 'Fire', where, BEFORE_RECORDS)
        forecast_rows.mark_profile_unavailable(result)
        result['purok_results'] = []
        return
    week = week_fraction(month, day, year)
    table = barangay_table(model)
    training = _in_training(model, month, year)
    for bid, row in forecast_rows.hazard_rows(result, 'Fire', where).items():
        if bid not in table:
            forecast_rows.set_unavailable(row, NO_AREAS)
            continue
        rate = table[bid][month - 1]
        row.pop('reason', None)
        row.update(probability=round(_chance(rate * week), 3), expected_events=round(rate * week, 2),
                   level=barangay_level(_chance(rate)), method='model')
        if training:
            row['in_training'] = True
        else:
            row.pop('in_training', None)
    forecast_rows.rerank(result)
    result['model_hazards'] = ['Fire']
    result['unavailable_hazards'] = [h for h in result.get('unavailable_hazards', []) if h != 'Fire']
    result['purok_results'] = purok_rows(model, month, week)
    _profile(result, table)


def _profile(result, table):
    """The 12-month chart: the chosen barangay's year, or the average barangay's."""
    from apps.history import forecast_rows

    chosen = result.get('profile_barangay')
    if chosen is None:
        monthly = [sum(rates[m] for rates in table.values()) / len(table) for m in range(12)] if table else None
    else:
        monthly = table.get(chosen)
    if monthly is None:
        forecast_rows.mark_profile_unavailable(result)
        return
    for entry, rate in zip(result['profile'], monthly):
        entry.update(probability=round(_chance(rate), 3), expected_events=round(rate, 2),
                     level=barangay_level(_chance(rate)))
    result['profile_method'] = 'model'


def purok_level(purok_id, today):
    """The model's level ('Red', 'Orange' or 'Green') for the purok in today's month, or None when it has none."""
    model = load()
    if isinstance(model, str):
        return None
    area = model.areas.get(purok_id)
    return area['months'][today.month - 1]['level'] if area else None
