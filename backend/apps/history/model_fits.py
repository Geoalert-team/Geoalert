"""
Stores each automatic retraining attempt as a ModelFit and decides which fit
is live. At most one fit per hazard is live; only a `switched` fit trained on
the current purok map can be. A flood or landslide fit goes live only between
January and May, never in the middle of a wet season.
"""
import logging
from datetime import datetime

from django.db import DatabaseError, transaction
from django.utils import timezone

from apps.history.models import MODEL_FIT_HAZARDS, MODEL_FIT_RESULTS, ModelFit

logger = logging.getLogger(__name__)

STALE_FIT = 'The purok map changed while it trained; the fit was not used'
FLOOD_SEASON_LOCK = 'Flood maps change only between January and May'
FLOOD_OPEN_MONTHS = range(1, 6)  # January to May, in Manila: between wet seasons
LANDSLIDE_SEASON_LOCK = 'Landslide maps change only between January and May'
LANDSLIDE_OPEN_MONTHS = range(1, 6)  # as flood: rain-triggered slides come in the wet season
SEASON_LOCKS = {'flood': (FLOOD_OPEN_MONTHS, FLOOD_SEASON_LOCK),
                'landslide': (LANDSLIDE_OPEN_MONTHS, LANDSLIDE_SEASON_LOCK)}  # {hazard: (open months, sentence)}
MAX_REASON = 500
NOT_READ = 'The live %s fit could not be read, so the committed file is used: %s'


def live_fit(hazard):
    return ModelFit.objects.filter(hazard=hazard, is_live=True).first()


def live_fit_head(hazard):
    """
    The loaders' recheck: the live fit with only its id and built_at read, or
    None. Read in a savepoint, so a database error (the model_fit table not
    migrated yet, say) is logged and counts as no live fit: the committed
    file is served, and a transaction the caller is in (a fire report's
    approval) stays usable.
    """
    try:
        with transaction.atomic():
            return ModelFit.objects.filter(hazard=hazard, is_live=True).only('id', 'hazard', 'built_at').first()
    except DatabaseError as exc:
        logger.warning(NOT_READ, hazard, exc)
        return None


def fit_body(fit):
    """(model, report) of a fit, read only when the loader's key changed; None when the database refuses."""
    try:
        with transaction.atomic():
            return ModelFit.objects.filter(pk=fit.pk).values_list('model', 'report').first()
    except DatabaseError as exc:
        logger.warning(NOT_READ, fit.hazard, exc)
        return None


def parse_built_at(value):
    """A timezone-aware datetime, or None when the value is missing or unreadable."""
    if not value or not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else None


def newer_is_fit(file_model, fit):
    """True when the fit in the database should be served over the model file."""
    if fit is None:
        return False
    if not file_model:
        return True
    file_built = parse_built_at(file_model.get('built_at'))
    if file_built is None or fit.built_at is None:
        return True
    return fit.built_at >= file_built


def record_attempt(payload, outlines_version, check=None):
    if not isinstance(payload, dict):
        raise ValueError('The attempt must be an object')
    hazard, result = payload.get('hazard'), payload.get('result')
    if hazard not in MODEL_FIT_HAZARDS:
        raise ValueError('Unknown hazard')
    if result not in MODEL_FIT_RESULTS:
        raise ValueError('Unknown result')
    reason = payload.get('reason')
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError('A reason is required')
    if len(reason) > MAX_REASON:
        raise ValueError(f'The reason is over {MAX_REASON} characters')
    model, report = payload.get('model'), payload.get('report')
    for name, body in (('model', model), ('report', report)):
        if body is not None and not isinstance(body, dict):
            raise ValueError(f'The {name} must be an object')
    if result in ('switched', 'kept') and not model:
        raise ValueError('A model is required')
    if model and report and model.get('version') != report.get('version'):
        raise ValueError('The model and report versions differ')
    built_at = None
    if model and model.get('built_at') is not None:
        built_at = parse_built_at(model['built_at'])
        if built_at is None:
            raise ValueError('built_at is not a date and time with a zone')
    version = str((model or {}).get('version') or '')
    fit_outlines = str((model or {}).get('outlines_version') or '')

    reason = reason.strip()
    if result == 'switched':
        if fit_outlines != outlines_version:
            result, reason = 'skipped', STALE_FIT
        else:
            if check is not None:
                refusal = check(hazard, model, report, outlines_version)
                if refusal:
                    raise ValueError(refusal)
            if hazard in SEASON_LOCKS and timezone.localtime().month not in SEASON_LOCKS[hazard][0]:
                result, reason = 'kept', SEASON_LOCKS[hazard][1]  # make_live (an admin's undo) is not locked

    with transaction.atomic():
        live = result == 'switched'
        if live:
            list(ModelFit.objects.select_for_update().filter(hazard=hazard, is_live=True))
            ModelFit.objects.filter(hazard=hazard, is_live=True).update(is_live=False)
        return ModelFit.objects.create(
            hazard=hazard, result=result, reason=reason, version=version,
            outlines_version=fit_outlines, built_at=built_at, model=model, report=report,
            is_live=live,
        )


def site_check(hazard, model, report, outlines):
    """None when the site can read the model, else the sentence saying why not."""
    from apps.history import fire_purok, flood_purok, landslide_purok

    loader = {'fire': fire_purok, 'flood': flood_purok, 'landslide': landslide_purok}[hazard]
    parsed = loader.parse(model, report, outlines)
    return parsed if isinstance(parsed, str) else None


def make_live(fit, outlines_version, check=None):
    """
    Undo: make an earlier switched fit on the current purok map the live one.
    With `check`, a fit the site can't read is refused and nothing changes.
    """
    if fit.result != 'switched':
        raise ValueError('Only a fit that was switched in can be made live')
    if fit.outlines_version != outlines_version:
        raise ValueError('That fit was trained on an older purok map')
    if check is not None:
        refusal = check(fit.hazard, fit.model, fit.report, outlines_version)
        if refusal:
            raise ValueError(refusal)
    with transaction.atomic():
        list(ModelFit.objects.select_for_update().filter(hazard=fit.hazard, is_live=True))
        ModelFit.objects.filter(hazard=fit.hazard, is_live=True).exclude(pk=fit.pk).update(is_live=False)
        ModelFit.objects.filter(pk=fit.pk).update(is_live=True)
    fit.is_live = True


def attempts(limit=24):
    rows = ModelFit.objects.only('hazard', 'result', 'reason', 'version', 'created_at', 'is_live')[:limit]
    return [{
        'hazard': r.hazard, 'result': r.result, 'reason': r.reason, 'version': r.version,
        'created_at': r.created_at.isoformat(), 'is_live': r.is_live,
    } for r in rows]


class OutlinesChanged(Exception):
    """The purok map was reloaded while the training data was being read."""


def _geojson(geometry):
    import json
    return json.loads(geometry.geojson) if geometry is not None else None


def training_data(hazard, outlines=False):
    """
    What the retraining job needs: fire records by purok, or flood or
    landslide spots (and on request every outline). Served only on the token
    endpoint; fire data holds no coordinate, flood and landslide spots carry
    their point (the job needs it).
    """
    from django.utils import timezone

    from apps.barangays.models import Barangay, Purok
    from apps.history import fire_purok, flood_own, flood_purok, landslide_own, landslide_purok

    before = Purok.outlines_version()
    if hazard == 'fire':
        from apps.history.fire_training import fire_records

        fires = [{'record_id': f.record_id, 'when': timezone.localtime(f.when).isoformat(timespec='seconds'),
                  'purok_ids': list(f.purok_ids), 'barangay_id': f.barangay_id} for f in fire_records()]
        loaded = fire_purok.load()
        live = None
        chosen = None if isinstance(loaded, str) else loaded.model
        if isinstance(chosen, dict) and 'family' in chosen and 'settings' in chosen:
            live = {'version': loaded.version, 'family': chosen['family'], 'settings': chosen['settings']}
        data = {'hazard': 'fire', 'outlines_version': before,
                'barangays': {b.id: b.name for b in Barangay.objects.only('id', 'name')},
                'fires': fires, 'live': live}
    else:
        # Flood and landslide alike: located spots, the floor, and the map in use (its classes, no point)
        serving, own = {'flood': (flood_purok, flood_own), 'landslide': (landslide_purok, landslide_own)}[hazard]
        spots = serving.located_spots()
        loaded = serving.load()
        live = None
        if not isinstance(loaded, str):
            live = {'version': loaded.version, 'source': loaded.source,
                    'areas': {pid: {'level': a['level'], 'score': a.get('score'),
                                    'not_assessed_reason': a['not_assessed_reason']}
                              for pid, a in loaded.areas.items()}}
        data = {'hazard': hazard, 'outlines_version': before, 'spots': spots,
                'floor': own.floor(spots), 'live': live}
        if outlines:
            data['barangays'] = [{'id': b.id, 'name': b.name, 'boundary': _geojson(b.boundary)}
                                 for b in Barangay.objects.order_by('id')]
            data['puroks'] = [{'id': p.id, 'barangay_id': p.barangay_id, 'name': p.name, 'kind': p.kind,
                               'parent': p.parent, 'source': p.source, 'confidence': p.confidence,
                               'boundary': _geojson(p.boundary)} for p in Purok.objects.order_by('id')]
    if Purok.outlines_version() != before:
        raise OutlinesChanged()
    return data
