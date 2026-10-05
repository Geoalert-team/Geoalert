import json
from pathlib import Path

from django.contrib.gis.geos import GEOSGeometry, MultiPolygon
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.barangays.models import Barangay

DATA_FILE = Path(__file__).resolve().parents[2] / 'data' / 'talisay_barangays.geojson'

# Other spellings the team may already have in the database
ALIASES = {
    'Tabunoc': ['Tabunok'],
    'Camp IV': ['Camp 4', 'Camp Four'],
    'Lawaan I': ['Lawaan 1'],
    'Lawaan II': ['Lawaan 2'],
    'Lawaan III': ['Lawaan 3'],
    'Poblacion': ['Poblacion (Talisay)'],
}


class Command(BaseCommand):
    help = 'Load the 22 Talisay City barangay boundaries (PSA PSGC 2023) into the barangay table.'

    def add_arguments(self, parser):
        parser.add_argument('--file', default=str(DATA_FILE), help='GeoJSON file to load.')
        parser.add_argument('--dry-run', action='store_true', help='Show what would change without saving.')

    def handle(self, *args, **options):
        path = Path(options['file'])
        if not path.exists():
            raise CommandError(f'File not found: {path}')
        features = json.loads(path.read_text(encoding='utf-8'))['features']

        created = updated = 0
        with transaction.atomic():
            for f in features:
                props = f['properties']
                name = props.get('name') or props['adm4_en']  # adm4_en: name field in the PSA source file
                geom = GEOSGeometry(json.dumps(f['geometry']), srid=4326)
                if geom.geom_type == 'Polygon':
                    geom = MultiPolygon(geom, srid=4326)

                barangay = None
                for candidate in [name, *ALIASES.get(name, [])]:
                    barangay = Barangay.objects.filter(name__iexact=candidate).first()
                    if barangay:
                        break

                if barangay:
                    barangay.boundary = geom
                    if not options['dry_run']:
                        barangay.save(update_fields=['boundary'])
                    updated += 1
                    self.stdout.write(f'  updated  {barangay.name}')
                else:
                    if not options['dry_run']:
                        Barangay.objects.create(name=name, municipality='Talisay City', boundary=geom)
                    created += 1
                    self.stdout.write(f'  created  {name}')

            if options['dry_run']:
                transaction.set_rollback(True)

        verb = 'Would load' if options['dry_run'] else 'Loaded'
        self.stdout.write(self.style.SUCCESS(f'{verb} {created + updated} barangays ({created} new, {updated} updated).'))