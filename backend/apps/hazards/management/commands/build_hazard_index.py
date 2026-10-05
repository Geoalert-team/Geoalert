from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.barangays.models import Barangay
from apps.hazards import susceptibility


class Command(BaseCommand):
    help = (
        'Build the flood, landslide and fire susceptibility maps shown on the public map, '
        'from elevation data and OpenStreetMap, clipped to the barangay boundaries.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--zoom', type=int, default=14,
                            help='Grid detail: 14 = about 9 m cells (default), 13 = about 19 m and faster.')
        parser.add_argument('--pad', type=float, default=500,
                            help='Meters of context to include around the city (default 500).')
        parser.add_argument('--out', default=None,
                            help='Output folder (default: frontend/public/hazard-index).')
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
            for poly in b.boundary:  # MultiPolygon -> Polygon -> rings of (lng, lat)
                polygons.append((b.id, [list(ring.coords) for ring in poly]))

        out = Path(options['out']) if options['out'] else Path(settings.BASE_DIR).parent / 'frontend' / 'public' / 'hazard-index'
        self.stdout.write(f'{len(barangays)} barangays, writing to {out}')

        try:
            susceptibility.build(
                polygons, names, (west, south, east, north), out,
                zoom=options['zoom'], pad_m=options['pad'], log=self.stdout.write,
                cache_dir=Path(settings.BASE_DIR) / '.hazard_cache', refresh=options['refresh'],
            )
        except Exception as exc:  # network problems are the usual cause
            raise CommandError(f'Build failed: {exc}') from exc

        self.stdout.write(self.style.SUCCESS('Hazard susceptibility maps built.'))