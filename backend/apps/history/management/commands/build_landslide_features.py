"""
manage.py build_landslide_features [--refresh] [--cache-dir DIR] [--output-dir DIR]

Measures the landslide clues (apps/history/landslide_features.py, FEATURE_COLUMNS)
at every building and every 20 m of road in Talisay for the landslide
susceptibility model: terrain from the Copernicus DEM, distance to roads, Esri
land cover and the UP NOAH landslide class. Writes
apps/history/data/landslide_purok_features.csv (one row per purok area, no
coordinates) and its meta file (stamped with the purok map's version), and the
points table and clue grids to the cache folder (backend/.hazard_cache).

Run it on a developer machine after a purok reload, then run train_landslide_model.
It reads the barangay and purok tables and static maps only.
"""
from datetime import date
from pathlib import Path

import numpy as np
import requests
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.barangays.models import Barangay, Purok
from apps.hazards import susceptibility as sus
from apps.history import fire_sources
from apps.history import flood_features as ff
from apps.history import landslide_features as lf
from apps.history import landslide_sources as ls

NOAH_PROVINCES = ('Cebu',)
STEEP_DEG = 10  # the road check compares event areas with Talisay's roads on ground this steep or steeper


class Command(BaseCommand):
    help = 'Measure the landslide clues at every building and road point for the landslide susceptibility model.'

    def add_arguments(self, parser):
        parser.add_argument('--refresh', action='store_true', help='Download the building footprints again.')
        parser.add_argument('--cache-dir', default=None, help='Where downloads go (default backend/.hazard_cache).')
        parser.add_argument('--output-dir', default=None, help='Where the area file goes (default apps/history/data).')

    def handle(self, *args, **options):
        log = self.stdout.write
        cache = Path(options['cache_dir'] or Path(settings.BASE_DIR) / '.hazard_cache')
        out = Path(options['output_dir'] or lf.DATA_DIR)

        version = Purok.outlines_version()
        barangays = list(Barangay.objects.exclude(boundary__isnull=True))
        puroks = list(Purok.objects.select_related('barangay').order_by('id'))
        if not barangays or not puroks:
            raise CommandError('No barangay or purok outlines are loaded; load them first.')

        polygons = []
        west = south = float('inf')
        east = north = float('-inf')
        for b in barangays:
            x0, y0, x1, y1 = b.boundary.extent
            west, south, east, north = min(west, x0), min(south, y0), max(east, x1), max(north, y1)
            for poly in b.boundary:
                polygons.append((b.id, [list(ring.coords) for ring in poly]))
        # 2 km of context, so upstream areas are cut no closer than the training tiles' are
        grid, bbox = sus.city_grid((west, south, east, north), pad_m=2000)
        log(f'{len(barangays)} barangays, {len(puroks)} purok areas; grid {grid.width} x {grid.height}, '
            f'{grid.res:.1f} m cells')

        try:
            dem = ls.dem_for(grid, cache, log)
            roads = ls.roads(bbox, cache, log)
            centres, _ = fire_sources.footprints(cache, bbox, options['refresh'], log)
            noah = ls.noah_landslide_grid(grid, NOAH_PROVINCES, cache, log)
            year, classes = self.newest_landcover(grid, cache, log)
        except (RuntimeError, OSError, requests.RequestException) as exc:
            raise CommandError(str(exc)) from exc

        city = sus.draw_polygons(grid, polygons) > 0
        if not (dem[city] > 0).any():
            raise CommandError(sus.NO_HEIGHT)

        log('  Terrain clues (the sink fill takes a minute)...')
        grids = lf.terrain_grids(dem, grid.res)
        grids['dist_road_m'] = lf.road_distance(grid, roads).astype(np.float32)
        if classes is not None:
            grids.update(lf.landcover_shares(classes, grid.res))
        else:
            for name in lf.LANDCOVER_CLASSES.values():
                grids[name] = np.full(grid.shape, np.nan, np.float32)
        grids['noah_class'] = noah
        steep_density = ls.road_density_km_per_km2(grid, roads, city & (grids['slope_deg'] >= STEEP_DEG))
        lf.write_grids(bbox, grid.zoom, grids, cache)

        pts, kind = lf.scoring_points(centres, roads, (grid, city))
        points = {'lon': pts[:, 0], 'lat': pts[:, 1], 'kind': kind}
        points.update(lf.sample(grid, grids, pts))
        buildings, on_road = int((kind == lf.BUILDING).sum()), int((kind == lf.ROAD).sum())
        log(f'  {buildings} buildings and {on_road} road points inside the city')
        if not len(pts):
            raise CommandError('No building or road point fell inside the city.')

        areas_in = [{'purok_id': p.id, 'polygons': p.boundary.coords} for p in puroks]
        member = ff.membership(areas_in, pts)
        areas = self.area_rows(puroks, member, kind, points['noah_class'])
        if Purok.outlines_version() != version:
            raise CommandError('The purok map changed while the features were being built; run it again.')

        meta = {
            'outlines_version': version,
            'built_at': timezone.localtime().isoformat(timespec='seconds'),
            'grid_cell_m': round(grid.res, 2),
            'points': int(len(pts)),
            'buildings': buildings,
            'road_points': on_road,
            'landcover_year': year,
            'landcover_ok': classes is not None,
            'talisay_steep_road_density': round(steep_density, 4),
            'sources': {
                'elevation': sus.COPERNICUS_NOTICE,
                'roads': 'OpenStreetMap highway lines (ODbL)',
                'landcover': 'Esri / Impact Observatory 10 m annual land cover (CC BY 4.0)',
                'noah': 'UP NOAH landslide hazard map, Cebu (ODbL), bettergovph mirror on Hugging Face',
                'buildings': 'Microsoft Global ML Building Footprints (ODbL)',
            },
        }
        lf.write_features(lf.LandslideFeatures(points=points, membership=member, areas=areas, meta=meta),
                          out / lf.FEATURES_FILE.name, out / lf.FEATURES_META.name, cache_dir=cache)
        empty = sum(1 for a in areas if a['points'] == 0)
        log(self.style.SUCCESS(f'Wrote {len(areas)} areas to {out / lf.FEATURES_FILE.name} ({empty} with no point) '
                               f'and the points to {cache / lf.POINTS_FILE}.'))
        log(f'Points: {buildings} buildings, {on_road} road points.')
        log(f'Land cover year: {year}.' if classes is not None else
            'Land cover could not be read; the model will not use it.')

    @staticmethod
    def newest_landcover(grid, cache, log):
        """(year, classes) for the newest year the Esri blob answers, probing down from last year; (None, None) if none."""
        for year in range(date.today().year - 1, ls.LANDCOVER_FIRST_YEAR - 1, -1):
            classes = ls.landcover_classes(grid, year, cache, log)
            if classes is not None:
                return year, classes
        return None, None

    @staticmethod
    def area_rows(puroks, member, kind, noah_class):
        """One row per purok area: its point counts and the 90th percentile of its NOAH class / 3."""
        by_purok = {}
        for point, purok in zip(member[0].tolist(), member[1].tolist()):
            by_purok.setdefault(purok, []).append(point)
        rows = []
        for p in puroks:
            idx = np.asarray(by_purok.get(p.id, []), int)
            rows.append({
                'purok_id': p.id, 'barangay_id': p.barangay_id, 'barangay': p.barangay.name, 'name': p.name,
                'confidence': p.confidence, 'points': int(len(idx)),
                'buildings': int((kind[idx] == lf.BUILDING).sum()), 'road_points': int((kind[idx] == lf.ROAD).sum()),
                'noah_p90': round(float(np.percentile(noah_class[idx] / 3, 90)), 6) if len(idx) else 0.0,
            })
        return rows
