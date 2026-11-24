"""
manage.py train_flood_model [--cache-dir DIR] [--output-dir DIR] [--reps N] [--stability-reps N]

Trains the flood susceptibility model (apps/history/flood_run.py) on the 2017
UP Mananga survey's flood spots and the features build_flood_features wrote,
tests it on GeoAlert's own flood points and the Tino satellite map, and writes
apps/history/data/flood_purok_model.json and flood_purok_report.json. When the
learned model fails a gate, the files hold the NOAH-based classes instead.

Run on a developer machine after build_flood_features. It reads the shared
database only (purok and barangay outlines, flood records); the survey points
and the satellite map stay in the git-ignored cache folder.
"""
import hashlib
import json
import os
from pathlib import Path

import numpy as np
import requests
from django.conf import settings
from django.contrib.gis.geos import Point
from django.core.management.base import BaseCommand, CommandError

from apps.barangays.models import Barangay, Purok
from apps.history import flood_features as ff
from apps.history import flood_labels as fl
from apps.history.fire_features import points_inside, polygons_to_metres, to_metres
from apps.history.flood_run import run


def place(lon: float, lat: float):
    """(purok id, barangay name) of a point: the smallest area holding it, and its barangay; None where none."""
    pt = Point(lon, lat, srid=4326)
    areas = list(Purok.objects.filter(boundary__contains=pt))
    purok = min(areas, key=lambda p: p.boundary.area).id if areas else None
    barangay = Barangay.objects.filter(boundary__contains=pt).values_list('name', flat=True).first()
    return purok, barangay


def write_atomically(folder: Path, texts: dict):
    """Each file to a .tmp beside it, then swapped in, so the site never reads a half-written pair."""
    temps = {name: folder / (name + '.tmp') for name in texts}
    try:
        for name, text in texts.items():
            temps[name].write_text(text, encoding='utf-8')
        for name, tmp in temps.items():
            os.replace(tmp, folder / name)
    finally:
        for tmp in temps.values():
            tmp.unlink(missing_ok=True)


def _plain(value):
    return value.item() if hasattr(value, 'item') else str(value)


class Command(BaseCommand):
    help = 'Train and test the flood susceptibility model and write flood_purok_model.json and its report.'

    def add_arguments(self, parser):
        parser.add_argument('--cache-dir', default=None, help='The cache folder (default backend/.hazard_cache).')
        parser.add_argument('--output-dir', default=None, help='Where the files go (default apps/history/data).')
        parser.add_argument('--reps', type=int, default=1000, help='Bootstrap repeats (default 1000).')
        parser.add_argument('--stability-reps', type=int, default=200, help='Stability refits (default 200).')

    def handle(self, *args, **options):
        log = self.stdout.write
        cache = Path(options['cache_dir'] or Path(settings.BASE_DIR) / '.hazard_cache')
        out = Path(options['output_dir'] or ff.DATA_DIR)
        csv_path, meta_path = out / ff.FEATURES_FILE.name, out / ff.FEATURES_META.name
        if not csv_path.exists():
            raise CommandError(f'{csv_path} is missing; run build_flood_features first.')
        features = ff.read_features(csv_path, meta_path, cache_dir=cache)
        if features.meta.get('outlines_version') != Purok.outlines_version():
            raise CommandError('The purok map changed since build_flood_features ran; run it again.')

        try:
            points = fl.annex_points(cache)
        except (RuntimeError, OSError, ValueError, requests.RequestException) as exc:
            raise CommandError(str(exc)) from exc
        spots = fl.spots(points)
        inputs = ff.features_at(np.array([[s['lon'], s['lat']] for s in spots]), cache)
        for i, s in enumerate(spots):
            s['purok_id'], s['barangay'] = place(s['lon'], s['lat'])
            s['inputs'] = {c: float(inputs[c][i]) for c in ff.FEATURE_COLUMNS}
        city = None
        for b in Barangay.objects.exclude(boundary__isnull=True):
            city = b.boundary if city is None else city.union(b.boundary)
        log(f'{len(points)} survey reports at {len(spots)} spots ({sum(s["positive"] for s in spots)} flooded)')

        def load_tests():
            from apps.history.models import HistoricalRecord

            geo = fl.geoalert_flood_points()
            for p in geo:
                p['purok_id'] = place(p['lon'], p['lat'])[0]
            lon, lat = features.buildings['lon'], features.buildings['lat']
            x0, y0, x1, y1 = city.extent
            rings = []
            for poly in fl.eosrs_polygons(cache):
                px0, py0, px1, py1 = poly.extent
                if px1 >= x0 and px0 <= x1 and py1 >= y0 and py0 <= y1:
                    rings.append([list(r.coords) for r in poly])
            flagged = (points_inside(polygons_to_metres(rings), to_metres(np.c_[lon, lat])) if rings
                       else np.zeros(len(lon), bool))
            floods = HistoricalRecord.objects.filter(hazard_type__name='Flood', barangay__isnull=False)
            tino = sorted(set(floods.filter(occurred_at__date='2025-11-04').values_list('barangay__name', flat=True)))
            any_flood = sorted(set(floods.values_list('barangay__name', flat=True)))
            log(f'Test data: {len(geo)} GeoAlert flood points, {int(flagged.sum())} buildings under the Tino map')
            return {'geoalert_points': geo, 'eosrs_flagged': flagged,
                    'barangay_records': {'tino': tino, 'any': any_flood}}

        digest = hashlib.sha1()
        for path in (csv_path, meta_path, cache / fl.ANNEX_FILE):
            digest.update(path.read_bytes())
        try:
            model, report = run(features, spots, city, load_tests, log=log, fingerprint=digest.hexdigest(),
                                reps=options['reps'], stability_reps=options['stability_reps'])
        except (RuntimeError, OSError, requests.RequestException) as exc:
            raise CommandError(str(exc)) from exc
        write_atomically(out, {
            ff.MODEL_FILE.name: json.dumps(model, indent=1, default=_plain),
            ff.REPORT_FILE.name: json.dumps(report, indent=1, default=_plain),
        })
        log(self.style.SUCCESS(f'Wrote {out / ff.MODEL_FILE.name} and {out / ff.REPORT_FILE.name} ({model["version"]}, '
                               f'source: {model["source"]}).'))
