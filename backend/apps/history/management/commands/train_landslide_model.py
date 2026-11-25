"""
manage.py train_landslide_model [--cache-dir DIR] [--output-dir DIR] [--reps N] [--stability-reps N]

Trains the landslide susceptibility model (apps/history/landslide_run.py) on
the table build_landslide_training wrote (landslides mapped after Philippine
typhoons, plus the world events if they help), scores the buildings and road
points build_landslide_features measured in Talisay, tests it on GeoAlert's
located landslides, and writes apps/history/data/landslide_purok_model.json
and landslide_purok_report.json. When the model fails a gate, the files hold
classes from UP NOAH's landslide map instead.

Run on a developer machine after both build commands. It reads the shared
database only, and only after the training set, the choice and the cut-offs
are fixed (the purok map's version is checked first): Landslide records,
"Affected here" marks on Landslide zones and barangay outlines. NASA's Global
Landslide Catalog (.hazard_cache/nasa_global_landslide_catalog.csv; its
licence is unstated, so it stays private) is a shown-only check: only the
classes of its points placed exactly or within 1 km inside the city reach the
report.
"""
import csv
import hashlib
import json
import math
from collections import Counter
from pathlib import Path

from django.conf import settings
from django.contrib.gis.geos import Point
from django.core.management.base import BaseCommand, CommandError
from django.db import close_old_connections

from apps.barangays.models import Barangay, Purok
from apps.history import landslide_features as lf
from apps.history.landslide_run import run
from apps.history.landslide_training_table import read_table
from apps.history.management.commands.train_flood_model import write_atomically

HAZARD = 'Landslide'
CATALOGUE_FILE = 'nasa_global_landslide_catalog.csv'
CATALOGUE_ACCURACY = ('exact', '1km')
MISSING_CATALOGUE = ("{path} is missing: it is NASA's Global Landslide Catalog export, a private test shown on the "
                     'report. Put the file there and run again (nothing was trained).')


def read_catalogue(path) -> list[tuple[float, float]]:
    """(lon, lat) of the catalogue's landslides placed exactly or within 1 km; rows without a position are skipped."""
    out = []
    with open(path, newline='', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            if (row.get('location_accuracy') or '').strip().lower() not in CATALOGUE_ACCURACY:
                continue
            try:
                lon, lat = float(row['longitude']), float(row['latitude'])
            except (KeyError, TypeError, ValueError):
                continue
            if math.isfinite(lon) and math.isfinite(lat):
                out.append((lon, lat))
    return out


def smallest_purok(point) -> int | None:
    """The id of the smallest purok area holding the point (sitios sit inside their puroks); None outside every one."""
    found = list(Purok.objects.filter(boundary__contains=point))
    return min(found, key=lambda p: p.boundary.area).id if found else None


def catalogue_puroks(points, city, place=None) -> list:
    """The purok (or None) of each catalogue point inside the city; points outside it are left out."""
    place = place or smallest_purok
    if city is None:
        return []
    x0, y0, x1, y1 = city.extent
    out = []
    for lon, lat in points:
        if not (x0 <= lon <= x1 and y0 <= lat <= y1):
            continue
        pt = Point(lon, lat, srid=4326)
        if city.contains(pt):
            out.append(place(pt))
    return out


def located_test_puroks() -> list[int]:
    """
    Puroks holding a located GeoAlert landslide (spec 3.4): a Landslide
    record's map point (its smallest purok), else the puroks the record is
    linked to, and "Affected here" marks on Landslide zones. Read only.
    """
    from apps.hazards.models import ZoneFieldMark
    from apps.history.models import HistoricalRecord

    found = set()
    for record in HistoricalRecord.objects.filter(hazard_type__name=HAZARD).prefetch_related('puroks'):
        if record.location is not None:
            found.add(smallest_purok(record.location))
        else:
            found.update(p.id for p in record.puroks.all())
    for mark in ZoneFieldMark.objects.filter(kind='Affected', zone__hazard_type__name=HAZARD):
        found.add(smallest_purok(mark.location))
    found.discard(None)
    return sorted(found)


def landslide_barangays() -> list[dict]:
    """Each barangay with a Landslide record and how many, for the barangay check. Read only."""
    from apps.history.models import HistoricalRecord

    counts = Counter(HistoricalRecord.objects.filter(hazard_type__name=HAZARD, barangay__isnull=False)
                     .values_list('barangay_id', 'barangay__name'))
    return [{'barangay_id': b, 'barangay': name, 'records': n}
            for (b, name), n in sorted(counts.items(), key=lambda kv: kv[0][1])]


def city_outline():
    """The union of the barangay outlines, or None when none is loaded. Read only."""
    city = None
    for b in Barangay.objects.exclude(boundary__isnull=True):
        city = b.boundary if city is None else city.union(b.boundary)
    return city


def _plain(value):
    """A numpy number as a plain one; anything else fails, so a bad value never reaches a file the map reads."""
    if hasattr(value, 'item'):
        return value.item()
    raise TypeError(f'{type(value).__name__} is not JSON serializable')


class Command(BaseCommand):
    help = 'Train and test the landslide susceptibility model and write landslide_purok_model.json and its report.'

    def add_arguments(self, parser):
        parser.add_argument('--cache-dir', default=None, help='The cache folder (default backend/.hazard_cache).')
        parser.add_argument('--output-dir', default=None,
                            help='Where the tables are read and the files written (default apps/history/data).')
        parser.add_argument('--reps', type=int, default=1000, help='Bootstrap repeats (default 1000).')
        parser.add_argument('--stability-reps', type=int, default=200, help='Stability refits (default 200).')

    def handle(self, *args, **options):
        log = self.stdout.write
        cache = Path(options['cache_dir'] or Path(settings.BASE_DIR) / '.hazard_cache')
        out = Path(options['output_dir'] or lf.DATA_DIR)
        inputs = {  # name in the model file -> (path, the command that writes it)
            lf.TRAINING_FILE.name: (out / lf.TRAINING_FILE.name, 'build_landslide_training'),
            lf.TRAINING_META.name: (out / lf.TRAINING_META.name, 'build_landslide_training'),
            lf.FEATURES_FILE.name: (out / lf.FEATURES_FILE.name, 'build_landslide_features'),
            lf.FEATURES_META.name: (out / lf.FEATURES_META.name, 'build_landslide_features'),
            lf.POINTS_FILE: (cache / lf.POINTS_FILE, 'build_landslide_features'),
        }
        for path, command in inputs.values():
            if not path.exists():
                raise CommandError(f'{path} is missing; run {command} first.')
        catalogue = cache / CATALOGUE_FILE
        if not catalogue.exists():  # checked before training, so a missing file never costs a run
            raise CommandError(MISSING_CATALOGUE.format(path=catalogue))
        try:
            table, table_meta = read_table(inputs[lf.TRAINING_FILE.name][0], inputs[lf.TRAINING_META.name][0])
            features = lf.read_features(inputs[lf.FEATURES_FILE.name][0], inputs[lf.FEATURES_META.name][0],
                                        cache_dir=cache)
        except (OSError, ValueError, KeyError) as exc:
            raise CommandError(str(exc)) from exc
        if features.meta.get('outlines_version') != Purok.outlines_version():
            raise CommandError('The purok map changed since build_landslide_features ran; run it again.')

        # Base names only: a full path would put this machine's folders in a committed file
        files = {name: hashlib.sha1(path.read_bytes()).hexdigest() for name, (path, _) in inputs.items()}
        fingerprint = hashlib.sha1(json.dumps(files, sort_keys=True).encode('utf-8')).hexdigest()
        slides = int(table['label'].sum())
        log(f'{len(table["label"])} training rows ({slides} slides); {len(features.areas)} purok areas, '
            f'{len(features.points.get("lon", []))} Talisay scoring points')

        def load_tests():
            # The connection opened for the purok map's version sat idle through the fits; the server may have
            # dropped it, and a dropped connection must not cost the run (ruling R29)
            close_old_connections()
            puroks = located_test_puroks()
            records = landslide_barangays()
            catalogue_ids = catalogue_puroks(read_catalogue(catalogue), city_outline())
            log(f'Test data: {len(puroks)} puroks with a located landslide, {len(records)} barangays with landslide '
                f'records, {len(catalogue_ids)} catalogue points in the city')
            return {'test_puroks': puroks, 'barangay_records': records, 'catalogue_purok_ids': catalogue_ids}

        try:
            model, report = run(table, table_meta, features, load_tests, log=log, fingerprint=fingerprint,
                                reps=options['reps'], stability_reps=options['stability_reps'])
        except (RuntimeError, OSError) as exc:
            raise CommandError(str(exc)) from exc
        except ValueError as exc:  # a bad value in a fit (a NaN input, say): named, never a bare traceback
            raise CommandError(f'The run stopped on a bad value ({exc}); nothing was written.') from exc
        model['inputs']['files'] = files
        try:  # both texts are made before either file is touched
            texts = {name: json.dumps(body, indent=1, default=_plain, allow_nan=False)
                     for name, body in ((lf.MODEL_FILE.name, model), (lf.REPORT_FILE.name, report))}
        except (TypeError, ValueError) as exc:
            raise CommandError(f'The model or report holds a value JSON cannot carry ({exc}); nothing was written.') \
                from exc
        write_atomically(out, texts)
        log(self.style.SUCCESS(f'Wrote {out / lf.MODEL_FILE.name} and {out / lf.REPORT_FILE.name} '
                               f'({model["version"]}, source: {model["source"]}).'))
