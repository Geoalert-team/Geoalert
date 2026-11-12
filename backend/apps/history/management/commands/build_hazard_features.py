from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.barangays.models import Barangay
from apps.hazards import susceptibility
from apps.history.hazard_data import DATA_DIR, TERRAIN_COLUMNS, terrain_shares, write_terrain


class Command(BaseCommand):
    help = ('Compute per-barangay terrain features (HAND, slope, water, roads, buildings) for the '
            'flood and landslide models and write data/barangay_terrain.csv. Reads the database only.')

    def add_arguments(self, parser):
        parser.add_argument('--refresh', action='store_true',
                            help='Download elevation and OpenStreetMap data again instead of reusing saved copies.')

    def handle(self, *args, **options):
        barangays = list(Barangay.objects.exclude(boundary__isnull=True))
        if not barangays:
            raise CommandError('No barangay boundaries in the database. Load the barangays first.')

        polygons, names = [], {}
        west = south = float('inf')
        east = north = float('-inf')
        for b in barangays:
            names[b.id] = b.name
            x0, y0, x1, y1 = b.boundary.extent
            west, south, east, north = min(west, x0), min(south, y0), max(east, x1), max(north, y1)
            for poly in b.boundary:
                polygons.append((b.id, [list(ring.coords) for ring in poly]))

        log = self.stdout.write
        try:
            grid, bbox = susceptibility.city_grid((west, south, east, north), zoom=14, pad_m=500)
            dem, osm = susceptibility.load_inputs(
                grid, bbox, log, cache_dir=Path(settings.BASE_DIR) / '.hazard_cache',
                refresh=options['refresh'])
            labels = susceptibility.draw_polygons(grid, polygons)
            factors = susceptibility.compute_factors(grid, dem, osm, labels > 0, log)
        except Exception as exc:  # network problems are the usual cause
            raise CommandError(f'Feature build failed: {exc}') from exc

        rows = terrain_shares(labels, factors, sorted(names))
        out = DATA_DIR / 'barangay_terrain.csv'
        write_terrain(out, rows, names)
        for bid in sorted(rows, key=lambda i: names[i]):
            r = rows[bid]
            log(f"{names[bid]}: cells={r['cells']} " + ' '.join(f'{k}={r[k]:.3f}' for k in TERRAIN_COLUMNS))
        self.stdout.write(self.style.SUCCESS(f'{len(rows)} barangays written to {out}'))
