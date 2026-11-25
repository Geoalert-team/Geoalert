"""
The automatic retraining job (spec docs/design/specs/2026-11-24-automatic-retraining-design.md,
section 6), run by manage.py run_model_job on a throw-away GitHub runner:

  1. fetch the training data from GeoAlert's token-only endpoint (retrying
     while Render wakes up);
  2. fire, every month: train on a moving test window and judge the new fit
     against the model in use (fire_run.train, window='moving');
     flood, every January: try the own-data model (flood_own) once there are
     enough located spots, building the features from outlines loaded into
     the runner's own empty database;
     landslide, every January a day later: the same for GeoAlert's own
     located landslides (landslide_own), added to the committed outside
     training table;
  3. post the attempt back. GeoAlert saves every attempt and makes a fit live
     only when it passed.

Environment: MODEL_JOB_API_URL (the site's base URL, no trailing slash),
MODEL_JOB_TOKEN, and MODEL_JOB_SCRATCH_DB=true only in the workflow, where the
database is the runner's own. The job prints counts, results and reasons only,
never a spot.
"""
import hashlib
import json
import math
import os
import re
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import requests
from django.contrib.gis.geos import GEOSGeometry, MultiPolygon
from django.core.management import call_command
from django.db import transaction

from apps.barangays.models import Barangay, Purok
from apps.history import fire_features, fire_run, flood_own, landslide_own
from apps.history import flood_features as ff
from apps.history import landslide_features as lf
from apps.history.fire_training import FireRecord
from apps.history.model_fits import MAX_REASON

FAILED = 'Failed: {detail}'
SCRATCH_ONLY = "Outlines are loaded only into the job's own empty database (MODEL_JOB_SCRATCH_DB=true)."
DATA_PATH = '/api/history/model-job/data/'
ATTEMPTS_PATH = '/api/history/model-job/attempts/'
DECIMAL = re.compile(r'\d+\.\d+')  # a failure's text may quote a point (a GEOS error does); never post or print one


def _base_url() -> str:
    url = os.environ.get('MODEL_JOB_API_URL', '').strip().rstrip('/')
    if not url:
        raise RuntimeError('MODEL_JOB_API_URL is not set.')
    return url


def _auth() -> dict:
    token = os.environ.get('MODEL_JOB_TOKEN', '').strip()
    if not token:
        raise RuntimeError('MODEL_JOB_TOKEN is not set.')
    return {'Authorization': f'Bearer {token}'}


def _detail(response) -> str:
    try:
        detail = response.json().get('detail', '')
    except (ValueError, AttributeError):
        detail = ''
    return str(detail)[:200]


def fetch(hazard: str, outlines: bool = False, tries: int | None = None, wait: float = 30, timeout: float = 90) -> dict:
    """
    The training data for one hazard. Retries a connection error, a timeout, a 5xx and a 409 (the purok map
    changed while it was read), `wait` seconds apart; any other refusal stops at once.
    """
    tries = int(os.environ.get('MODEL_JOB_TRIES', '5')) if tries is None else tries
    url, headers = _base_url() + DATA_PATH, _auth()
    params = {'hazard': hazard, **({'outlines': '1'} if outlines else {})}
    for attempt in range(tries):
        if attempt:
            time.sleep(wait)
        try:
            response = requests.get(url, params=params, headers=headers, timeout=timeout)
        except (requests.ConnectionError, requests.Timeout):
            continue
        if response.status_code == 409 or response.status_code >= 500:
            continue
        if response.status_code != 200:
            raise RuntimeError(f'GeoAlert refused the data request ({response.status_code}): {_detail(response)}')
        return response.json()
    raise RuntimeError(f'GeoAlert did not answer after {tries} tries.')


def _plain(value):
    """JSON-ready: numpy values as Python ones, a NaN or infinity as null (the server's parser refuses them)."""
    if isinstance(value, dict):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    if isinstance(value, np.ndarray):
        return _plain(value.tolist())
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def post(attempt: dict, timeout: float = 90) -> dict:
    """Send one attempt; the server's answer {'id', 'result', 'is_live'}. The reason is cut to the server's limit."""
    body = _plain({**attempt, 'reason': str(attempt.get('reason', ''))[:MAX_REASON]})
    response = requests.post(_base_url() + ATTEMPTS_PATH, data=json.dumps(body, separators=(',', ':'), allow_nan=False),
                             headers={**_auth(), 'Content-Type': 'application/json'}, timeout=timeout)
    if response.status_code != 201:
        raise RuntimeError(f'GeoAlert refused the attempt ({response.status_code}): {_detail(response)}')
    return response.json()


def mask_decimals(text: str) -> str:
    """The text with every decimal number (a point a library quoted) as #."""
    return DECIMAL.sub('#', text)


def failed_reason(exc: BaseException) -> str:
    """
    The failed attempt's reason, with any decimal number (a point a library
    quoted) taken out. An error worded for the card (`own_words`, as
    landslide_training.PastDeadline, a passed time limit) comes without its type.
    """
    detail = mask_decimals(str(exc))[:200]
    if getattr(exc, 'own_words', False) is True:
        return FAILED.format(detail=detail)
    return FAILED.format(detail=f'{type(exc).__name__}: {detail}')


# Fire

def fire_records_from(data: dict) -> list:
    """The server's fires as the FireRecords fire_run.train reads."""
    return [FireRecord(when=datetime.fromisoformat(f['when']), purok_ids=list(f['purok_ids']),
                       barangay_id=f['barangay_id'], record_id=str(f['record_id'])) for f in data['fires']]


def fire_attempt(data: dict, today, features_dir: Path, boot_reps: int, interval_reps: int, log) -> dict:
    """The fire attempt: skipped when the committed features were built on another purok map, else trained."""
    features_dir = Path(features_dir)
    csv_path = features_dir / fire_features.FEATURES_FILE.name
    table = fire_features.read_features(csv_path, features_dir / fire_features.FEATURES_META.name)
    if table.outlines_version != data['outlines_version']:
        return {'hazard': 'fire', 'result': 'skipped', 'reason': fire_run.FIRE_STALE_FEATURES}
    names = {int(k): v for k, v in data['barangays'].items()}  # JSON keys are strings
    model, report = fire_run.train(fire_records_from(data), table, names, today, window='moving', live=data['live'],
                                   csv_bytes=csv_path.read_bytes(), boot_reps=boot_reps, interval_reps=interval_reps,
                                   log=log)
    switch = report['switch']
    return {'hazard': 'fire', 'result': 'switched' if switch['passed'] else 'kept', 'reason': switch['reason'],
            'model': model, 'report': report}


# Flood

def load_outlines(data: dict) -> None:
    """
    The server's barangays, then its puroks, with their ids, into the runner's own database. Refused unless
    MODEL_JOB_SCRATCH_DB=true and both tables are empty, so a laptop whose .env points at the shared database
    never writes there.
    """
    if not (os.environ.get('MODEL_JOB_SCRATCH_DB') == 'true' and Purok.objects.count() == 0
            and Barangay.objects.count() == 0):
        raise RuntimeError(SCRATCH_ONLY)

    def shape(geojson):
        if geojson is None:
            return None
        geom = GEOSGeometry(json.dumps(geojson), srid=4326)
        return MultiPolygon(geom, srid=4326) if geom.geom_type == 'Polygon' else geom

    with transaction.atomic():
        Barangay.objects.bulk_create([Barangay(id=b['id'], name=b['name'], boundary=shape(b['boundary']))
                                      for b in data['barangays']])
        Purok.objects.bulk_create([Purok(id=p['id'], barangay_id=p['barangay_id'], name=p['name'], kind=p['kind'],
                                         parent=p['parent'], source=p['source'], confidence=p['confidence'],
                                         boundary=shape(p['boundary'])) for p in data['puroks']])


def flood_attempt(data: dict, today, cache: Path, workdir: Path, reps: int, stability_reps: int, log,
                  fetch=fetch) -> dict:
    """
    The flood attempt: not tried below the floor, with too few held-back spots or too few training barangays;
    otherwise the own-data model, kept or switched by its four checks and, over a GeoAlert map in use, by how
    many of the held-back season's spots each puts in Red or Orange. The Tino (EOS-RS) map is never read here:
    it must not go to GitHub (spec section 4), so the own-data report has no Tino check; the hand-run
    train_flood_model keeps it.
    """
    spots = data['spots']
    floor = flood_own.floor(spots)
    if not floor['enough']:
        return {'hazard': 'flood', 'result': 'not_tried',
                'reason': flood_own.FLOOD_FLOOR.format(n=floor['n'], b=floor['barangays'])}
    train_spots, held, season = flood_own.season_split(spots, today)
    if len(held) < flood_own.HELD_MIN:
        return {'hazard': 'flood', 'result': 'not_tried', 'reason': flood_own.FLOOD_HELD.format(n=len(held))}
    if len({s['barangay'] for s in train_spots if s.get('barangay')}) < 2:
        return {'hazard': 'flood', 'result': 'not_tried', 'reason': flood_own.FLOOD_FOLDS.format(season=season)}

    load_outlines(fetch('flood', outlines=True))
    cache, workdir = Path(cache), Path(workdir)
    cache.mkdir(parents=True, exist_ok=True)
    call_command('build_flood_features', cache_dir=str(cache), output_dir=str(workdir))
    csv_path, meta_path = workdir / ff.FEATURES_FILE.name, workdir / ff.FEATURES_META.name
    features = ff.read_features(csv_path, meta_path, cache_dir=cache)
    fingerprint = hashlib.sha1(csv_path.read_bytes() + meta_path.read_bytes()).hexdigest()
    inputs = ff.features_at(np.array([[s['lon'], s['lat']] for s in train_spots]), cache)
    training = [{**s, 'positive': True, 'inputs': {c: float(inputs[c][i]) for c in ff.FEATURE_COLUMNS}}
                for i, s in enumerate(train_spots)]
    city = None
    for b in Barangay.objects.exclude(boundary__isnull=True):
        city = b.boundary if city is None else city.union(b.boundary)
    live = data['live']
    outside = {int(k): v for k, v in live['areas'].items()} if live else {}  # JSON keys are strings
    log(f'{len(training)} training spots before the {season} wet season, {len(held)} held back')
    model, report = flood_own.train_own(features, training, held, city, outside, season, fingerprint,
                                        eosrs_flagged=None, reps=reps, stability_reps=stability_reps, log=log,
                                        outside_source=live['source'] if live else None)
    # The runner's own database gives its own map version; the fit is on the server's map
    model['outlines_version'] = data['outlines_version']

    def attempt(result, reason):
        return {'hazard': 'flood', 'result': result, 'reason': reason, 'model': model, 'report': report}

    acceptance = report['acceptance']
    if not acceptance['adopted']:
        return attempt('kept', ' '.join(acceptance['reasons']))
    held_back = report['temporal_test']['held_back']
    new_levels = [h['level'] for h in held_back]
    if live and live['source'] == 'geoalert':
        live_levels = [live['areas'].get(str(h['purok_id']), {}).get('level') for h in held_back]
        new_hits, live_hits = flood_own.compare(new_levels, live_levels)
        if new_hits < live_hits:
            return attempt('kept', flood_own.FLOOD_WORSE.format(season=season, new=new_hits, live=live_hits))
    hits = flood_own.compare(new_levels, [])[0]
    return attempt('switched', flood_own.FLOOD_SWITCHED.format(hits=hits, n=len(new_levels)))


# Landslide

def talisay_ground(cache: Path, log):
    """
    on_ground(points) -> bool array: True where Talisay's Copernicus height is
    above 0 (the sea is not ground, ruling R21), on the grid
    build_landslide_features saved its clue grids on; the height is the one
    that command cached (landslide_sources.dem_for). A point off that grid is
    not ground, whatever the nearest edge cell holds.
    """
    from apps.hazards.susceptibility import Grid
    from apps.history import landslide_sources

    with np.load(Path(cache) / lf.GRIDS_FILE, allow_pickle=False) as z:
        grid = Grid(*(float(v) for v in z['bbox']), int(z['zoom']))  # as landslide_features.features_at reads it
    dem = landslide_sources.dem_for(grid, cache, log)

    def on_ground(points):
        pts = np.asarray(points, float).reshape(-1, 2)
        return lf.on_grid(grid, pts) & (ff.sample_grid(grid, dem, pts) > 0)

    return on_ground


def landslide_attempt(data: dict, today, cache: Path, workdir: Path, reps: int, stability_reps: int, log,
                      fetch=fetch, deadline=None) -> dict:
    """
    The landslide attempt: not tried below the floor (30 located spots in 3
    barangays), with fewer than 5 spots in the held-back wet season, or with
    no own slide to train on (ruling R43: none before that season, or none
    left on ground); otherwise the committed outside training table plus
    GeoAlert's own spots from before that season (landslide_own.own_rows, the
    Talisay fold, weight 10), trained by landslide_run.run in own mode on
    clues built from outlines loaded into the runner's own database. Kept
    when a check fails, or when it puts fewer of the held-back season's spots
    in Red or Orange than the map in use, whatever its source (spec 6.3 check
    5, ruling R44; a tie switches); else switched. Prints and returns counts,
    classes and reasons only, never a spot. `deadline` (a
    landslide_training.Deadline, the job's own time limit) goes to the run's
    refit loops, which raise PastDeadline once it has passed.
    """
    from apps.history import landslide_run
    from apps.history import landslide_training_table as ltt

    spots = data['spots']
    floor = landslide_own.floor(spots)
    if not floor['enough']:
        return {'hazard': 'landslide', 'result': 'not_tried',
                'reason': landslide_own.LANDSLIDE_FLOOR.format(n=floor['n'], b=floor['barangays'])}
    train_spots, held, season = flood_own.season_split(spots, today)
    if len(held) < landslide_own.HELD_MIN:
        return {'hazard': 'landslide', 'result': 'not_tried',
                'reason': landslide_own.LANDSLIDE_HELD.format(n=len(held))}
    no_training = {'hazard': 'landslide', 'result': 'not_tried', 'reason': landslide_own.LANDSLIDE_NO_TRAINING}
    if not train_spots:  # ruling R43: a fit without GeoAlert's rows must never carry the GeoAlert basis
        return no_training

    load_outlines(fetch('landslide', outlines=True))
    cache, workdir = Path(cache), Path(workdir)
    cache.mkdir(parents=True, exist_ok=True)
    call_command('build_landslide_features', cache_dir=str(cache), output_dir=str(workdir))
    inputs = {  # name in the model file -> path: the committed outside table and the clues just built
        lf.TRAINING_FILE.name: lf.TRAINING_FILE,
        lf.TRAINING_META.name: lf.TRAINING_META,
        lf.FEATURES_FILE.name: workdir / lf.FEATURES_FILE.name,
        lf.FEATURES_META.name: workdir / lf.FEATURES_META.name,
        lf.POINTS_FILE: cache / lf.POINTS_FILE,
    }
    table, table_meta = ltt.read_table(inputs[lf.TRAINING_FILE.name], inputs[lf.TRAINING_META.name])
    features = lf.read_features(inputs[lf.FEATURES_FILE.name], inputs[lf.FEATURES_META.name], cache_dir=cache)
    # As train_landslide_model: base names only, and the training table is in it (the run adds the own rows)
    files = {name: hashlib.sha1(path.read_bytes()).hexdigest() for name, path in inputs.items()}
    fingerprint = hashlib.sha1(json.dumps(files, sort_keys=True).encode('utf-8')).hexdigest()
    own = landslide_own.own_rows(train_spots, lambda points: lf.features_at(points, cache),
                                 on_ground=talisay_ground(cache, log))
    log(f'{len(train_spots)} training spots before the {season} wet season, {len(held)} held back; '
        f'{int(own["label"].sum())} own slides and {int((own["label"] == 0).sum())} "no" points in the Talisay fold')
    if not int(own['label'].sum()):  # every training spot was at sea or off the clue grids (no clues): no own rows
        return no_training

    def load_tests():  # one test purok per held-back spot (ruling R30), read only after the cut-offs
        return {'test_puroks': [s['purok_id'] for s in held], 'season': season}

    model, report = landslide_run.run(table, table_meta, features, load_tests, log=log, fingerprint=fingerprint,
                                      reps=reps, stability_reps=stability_reps, mode='own', own_rows=own,
                                      deadline=deadline)
    # The runner's own database gives its own map version; the fit is on the server's map
    model['outlines_version'] = data['outlines_version']
    model['inputs']['files'] = files

    def attempt(result, reason):
        return {'hazard': 'landslide', 'result': result, 'reason': reason, 'model': model, 'report': report}

    acceptance = report['acceptance']
    if not acceptance['adopted']:
        return attempt('kept', ' '.join(acceptance['reasons']))
    new_levels = [h['level'] for h in report['temporal_test']['held_back']]
    live = data['live']
    if live:  # the map in use, from the outside model, the NOAH fallback or GeoAlert's own (ruling R44)
        live_levels = [live['areas'].get(str(h['purok_id']), {}).get('level')
                       for h in report['temporal_test']['held_back']]
        new_hits, live_hits = flood_own.compare(new_levels, live_levels)
        if new_hits < live_hits:
            return attempt('kept', landslide_own.LANDSLIDE_WORSE.format(season=season, new=new_hits, live=live_hits))
    hits = flood_own.compare(new_levels, [])[0]
    return attempt('switched', landslide_own.LANDSLIDE_SWITCHED.format(hits=hits, n=len(new_levels)))
