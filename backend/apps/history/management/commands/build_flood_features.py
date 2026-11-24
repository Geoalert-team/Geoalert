"""
manage.py build_flood_features [--refresh] [--cache-dir DIR] [--output-dir DIR]

Measures the ground under every building in Talisay for the flood
susceptibility model (apps/history/flood_features.py, FEATURE_COLUMNS): UP NOAH
flood depth classes, height and distance above the nearest river, sink depth
and built-up cover. Writes apps/history/data/flood_purok_features.csv and its
meta file (stamped with the purok map's version), and the per-building table
to the cache folder (backend/.hazard_cache), which is too big to keep with the
code.

Run it on a developer machine after a purok reload, then run train_flood_model.
It reads the barangay and purok tables and static maps only.
"""
from pathlib import Path

import numpy as np
import requests
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from scipy import ndimage

from apps.barangays.models import Barangay, Purok
from apps.hazards import susceptibility as sus
from apps.history import fire_sources
from apps.history import flood_features as ff


class Command(BaseCommand):
    help = 'Measure the ground under every building for the flood susceptibility model.'

    def add_arguments(self, parser):
        parser.add_argument('--refresh', action='store_true', help='Download the maps again.')
        parser.add_argument('--cache-dir', default=None, help='Where downloads go (default backend/.hazard_cache).')
        parser.add_argument('--output-dir', default=None, help='Where the area file goes (default apps/history/data).')

    def handle(self, *args, **options):
        log = self.stdout.write
        cache = Path(options['cache_dir'] or Path(settings.BASE_DIR) / '.hazard_cache')
        out = Path(options['output_dir'] or ff.DATA_DIR)
        refresh = options['refresh']

        version = Purok.outlines_version()
        barangays = list(Barangay.objects.exclude(boundary__isnull=True))
        puroks = list(Purok.objects.select_related('barangay').order_by('id'))
        if not barangays or not puroks:
            raise CommandError('No barangay or purok outlines are loaded; load them first.')

        polygons, names = [], {}
        west = south = float('inf')
        east = north = float('-inf')
        for b in barangays:
            names[b.id] = b.name
            x0, y0, x1, y1 = b.boundary.extent
            west, south, east, north = min(west, x0), min(south, y0), max(east, x1), max(north, y1)
            for poly in b.boundary:
                polygons.append((b.id, [list(ring.coords) for ring in poly]))
        grid, bbox = sus.city_grid((west, south, east, north))
        log(f'{len(barangays)} barangays, {len(puroks)} purok areas; grid {grid.width} x {grid.height}, '
            f'{grid.res:.1f} m cells')

        try:
            dem, osm = sus.load_inputs(grid, bbox, log, cache_dir=cache, refresh=refresh)
            centres, _ = fire_sources.footprints(cache, bbox, refresh, log)
            landcover = fire_sources.worldcover(cache, bbox, refresh, log)
            zips = {years: ff.fetch_noah(cache, years) for years in ff.NOAH}
        except (RuntimeError, OSError, requests.RequestException) as exc:
            raise CommandError(str(exc)) from exc

        labels = sus.draw_polygons(grid, polygons)
        city = labels > 0
        if not (dem[city] > 0).any():
            raise CommandError(sus.NO_HEIGHT)

        log('  Terrain: river heights, distances and sinks (the sink fill takes a minute)...')
        smooth = ndimage.gaussian_filter(dem, sigma=1.0)
        rivers = sus.draw_lines(grid, [w['coords'] for w in osm['waterways'] if w['kind'] == 'river'], width=1)
        if not rivers.any():
            raise CommandError('No river is mapped in the saved OpenStreetMap data.')
        rel_height, dist = ff.river_relative(smooth, rivers, grid.res)
        sink = ff.depression_depth(smooth)

        log('  UP NOAH flood maps (5, 25 and 100-year)...')
        (gs, gw, gn, ge) = bbox
        noah_grids, flooded = {}, {}
        for years, path in zips.items():
            noah_grids[years] = ff.noah_class_grid(grid, ff.noah_polygons(path, years, (gw, gs, ge, gn)))
            flooded[years] = round(float(((noah_grids[years] > 0) & city).sum()) * grid.res ** 2)
        consistent = ff.noah_consistent(flooded)
        used = ['noah25_class'] + (['noah5_class'] if consistent.get(5) else [])
        for years, ok in sorted(consistent.items()):
            if not ok:
                log(self.style.WARNING(f'  NOAH {years}-year map dropped: its flooded area ({flooded[years]:,} m²) '
                                       f'disagrees with the 25-year map ({flooded[25]:,} m²).'))
        near_noah = sus.distance_to(noah_grids[25] > 0, grid.res) <= ff.NOAH_NEAR_M
        ff.write_grids(bbox, grid.zoom, {'noah25_class': noah_grids[25], 'noah5_class': noah_grids[5],
                                         'rel_height_river_m': rel_height, 'dist_river_m': dist,
                                         'depression_m': sink}, cache)

        b_barangay = ff.sample_grid(grid, labels, centres)
        keep = b_barangay > 0
        pts = centres[keep]
        b_barangay = b_barangay[keep]
        log(f'  {len(pts)} buildings inside the city')
        buildings = {
            'lon': pts[:, 0], 'lat': pts[:, 1], 'barangay_id': b_barangay.astype(int),
            'barangay': np.array([names[int(i)] for i in b_barangay]),
            'noah25_class': ff.sample_grid(grid, noah_grids[25], pts).astype(np.uint8),
            'noah5_class': ff.sample_grid(grid, noah_grids[5], pts).astype(np.uint8),
            'rel_height_river_m': ff.sample_grid(grid, rel_height, pts),
            'dist_river_m': ff.sample_grid(grid, dist, pts),
            'depression_m': ff.sample_grid(grid, sink, pts),
            'built_share': ff.built_share_at(landcover[0], landcover[1], pts),
            'noah25_within_300m': ff.sample_grid(grid, near_noah, pts).astype(bool),
        }

        areas_in = [{'purok_id': p.id, 'polygons': p.boundary.coords} for p in puroks]
        member = ff.membership(areas_in, pts)
        counts = np.bincount(member[1], minlength=max(p.id for p in puroks) + 1) if len(member[1]) else None
        areas = [{'purok_id': p.id, 'barangay_id': p.barangay_id, 'barangay': p.barangay.name, 'name': p.name,
                  'confidence': p.confidence, 'buildings': int(counts[p.id]) if counts is not None else 0}
                 for p in puroks]
        if Purok.outlines_version() != version:
            raise CommandError('The purok map changed while the features were being built; run it again.')

        meta = {
            'outlines_version': version,
            'built_at': timezone.localtime().isoformat(timespec='seconds'),
            'grid_cell_m': round(grid.res, 2),
            'buildings': int(len(pts)),
            'noah_check': {'flooded_city_m2': {str(k): v for k, v in flooded.items()},
                           'consistent': {str(k): bool(v) for k, v in consistent.items()},
                           'slack': ff.NOAH_SLACK},
            'noah_layers_used': used,
            'sources': {
                'noah': 'UP NOAH flood hazard maps, 5/25/100-year (ODbL), bettergovph mirror on Hugging Face',
                'elevation': sus.COPERNICUS_NOTICE,
                'rivers': 'OpenStreetMap waterway=river (ODbL)',
                'landcover': 'ESA WorldCover 2021 v200 (CC BY 4.0)',
                'buildings': 'Microsoft Global ML Building Footprints (ODbL)',
            },
        }
        ff.write_features(ff.FloodFeatures(buildings=buildings, membership=member, areas=areas, meta=meta),
                          out / ff.FEATURES_FILE.name, out / ff.FEATURES_META.name, cache_dir=cache)
        empty = sum(1 for a in areas if a['buildings'] == 0)
        log(self.style.SUCCESS(f'Wrote {len(areas)} areas to {out / ff.FEATURES_FILE.name} '
                               f'({empty} with no building) and the building table to {cache / ff.BUILDINGS_FILE}.'))
        log(f'NOAH layers used as inputs: {", ".join(used)}.')
