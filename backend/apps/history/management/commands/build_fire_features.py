"""
manage.py build_fire_features [--refresh]

Describes every purok area for the fire risk model: buildings, roads, the road
distance to a fire station, land cover, population and distance to the coast
and rivers (fire_features.FEATURE_COLUMNS). Writes
apps/history/data/fire_purok_features.csv and fire_purok_features.meta.json,
stamped with the purok map's version so train_fire_model and the website can
tell when the map has changed since.

Run it on a developer machine after a purok reload (load_puroks), then run
train_fire_model. Downloads are saved in backend/.hazard_cache; --refresh
downloads them again. It reads the purok table only, never a fire record.
"""
from pathlib import Path

import requests
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.barangays.models import Purok
from apps.barangays.purok_estimate import BUILDINGS_INDEX, BUILDINGS_TILE
from apps.history import fire_features as ff
from apps.history import fire_sources

POINTS_CSV = Path(settings.BASE_DIR) / 'apps' / 'barangays' / 'data' / 'puroks' / 'purok_points.csv'
PAD_DEG = 0.01  # about 1 km of context around the puroks, for roads and stations just outside


class Command(BaseCommand):
    help = 'Measure every purok area for the fire risk model and write fire_purok_features.csv.'

    def add_arguments(self, parser):
        parser.add_argument('--refresh', action='store_true', help='Download every source again.')
        parser.add_argument('--cache-dir', default=None, help='Where downloads are saved (default backend/.hazard_cache).')
        parser.add_argument('--output-dir', default=None, help='Where the feature file goes (default apps/history/data).')

    def handle(self, *args, **options):
        log = self.stdout.write
        cache = Path(options['cache_dir'] or Path(settings.BASE_DIR) / '.hazard_cache')
        out = Path(options['output_dir'] or ff.DATA_DIR)
        refresh = options['refresh']

        version = Purok.outlines_version()
        puroks = list(Purok.objects.select_related('barangay').order_by('id'))
        if not puroks:
            raise CommandError('No purok areas are loaded; run load_puroks first.')
        named = ff.fire_log_names(POINTS_CSV) if POINTS_CSV.exists() else set()
        areas = [{
            'purok_id': p.id, 'barangay_id': p.barangay_id, 'barangay': p.barangay.name, 'name': p.name,
            'confidence': p.confidence, 'from_fire_log': (p.barangay.name, p.name) in named,
            'polygons': p.boundary.coords, 'point': p.boundary.point_on_surface.coords,
        } for p in puroks]
        extents = [p.boundary.extent for p in puroks]
        bbox = (min(e[1] for e in extents) - PAD_DEG, min(e[0] for e in extents) - PAD_DEG,
                max(e[3] for e in extents) + PAD_DEG, max(e[2] for e in extents) + PAD_DEG)
        log(f'{len(areas)} purok areas')

        try:
            buildings = fire_sources.footprints(cache, bbox, refresh, log)
            osm = fire_sources.osm(cache)
            landcover = fire_sources.worldcover(cache, bbox, refresh, log)
            population = fire_sources.worldpop(cache, bbox, refresh, log)
        except (RuntimeError, OSError, requests.RequestException) as exc:
            raise CommandError(str(exc)) from exc
        log(f'  {len(buildings[0])} buildings, {len(osm["roads"])} roads, {len(osm["fire_stations"])} fire stations')

        rows = ff.area_rows(areas, {'buildings': buildings, 'osm': osm, 'landcover': landcover,
                                    'population': population}, log)
        if Purok.outlines_version() != version:
            raise CommandError('The purok map changed while the features were being built; run it again.')

        sources = {
            'buildings': {'name': 'Microsoft Global ML Building Footprints', 'licence': 'ODbL',
                          'url': BUILDINGS_INDEX, 'tile': BUILDINGS_TILE},
            'roads_stations_water': {'name': 'OpenStreetMap (roads, fire stations, coastline, waterways)',
                                     'licence': 'ODbL', 'note': 'saved by build_purok_estimates'},
            'landcover': {'name': 'ESA WorldCover 2021 v200', 'licence': 'CC BY 4.0',
                          'url': fire_sources.WORLDCOVER_URL.format(tile=fire_sources.worldcover_tile(bbox[0], bbox[1]))},
        }
        if population is not None:
            sources['population'] = {'used': True, 'licence': 'CC BY 4.0',
                                     'name': fire_sources.worldpop_label(cache) or 'WorldPop constrained 100 m'}
        else:
            sources['population'] = {'used': False, 'licence': 'CC BY 4.0',
                                     'reason': 'No WorldPop download worked without an account.'}
        table = ff.FeatureTable(rows=rows, outlines_version=version,
                                built_at=timezone.localtime().isoformat(timespec='seconds'), sources=sources,
                                dropped=() if population is not None else ('population',))
        csv_path, meta_path = out / ff.FEATURES_FILE.name, out / ff.FEATURES_META.name
        ff.write_features(table, csv_path, meta_path)

        empty = sum(1 for r in rows if r['buildings_in_area'] == 0)
        log(self.style.SUCCESS(f'Wrote {len(rows)} areas to {csv_path}'))
        log(f'{empty} areas have no building in them; {sum(r["from_fire_log"] for r in rows)} were drawn '
            'because a fire address named them (report only, not an input).')
        if population is None:
            log('Population was left out: no WorldPop download worked without an account.')
