from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.history.models import HistoricalRecord
from apps.history.places import read_places

PLACES_FILE = Path(__file__).resolve().parents[2] / 'data' / 'history_places.csv'
FIELDS = ['location', 'location_precision', 'location_basis']
# Same spot: closer than about a millimetre
SAME = 1e-8


class Command(BaseCommand):
    help = ('Give past events their map point from history_places.csv: the pin of the purok or sitio, or the '
            'landmark, that the source names. A ref with no record stops the run before anything is written. '
            'Records not in the file are left as they are.')

    def add_arguments(self, parser):
        parser.add_argument('--file', default=str(PLACES_FILE), help='The places CSV (default: %(default)s).')
        parser.add_argument('--dry-run', action='store_true', help='Report without saving.')

    def handle(self, *args, **options):
        path = Path(options['file'])
        if not path.exists():
            raise CommandError(f'File not found: {path}')
        try:
            places = read_places(path.read_text(encoding='utf-8-sig'))
        except ValueError as e:
            raise CommandError(f'{path.name}: {e}')

        records = {r.source_ref: r for r in HistoricalRecord.objects.select_related('barangay')
                   .filter(source_ref__in=[p.ref for p in places])}
        missing = [p.ref for p in places if p.ref not in records]
        if missing:
            raise CommandError(f'No history record for: {", ".join(missing)}. Nothing written.')

        changed = []
        for place in places:
            record = records[place.ref]
            boundary = record.barangay.boundary if record.barangay else None
            if boundary is not None and not boundary.contains(place.point):
                self.stdout.write(self.style.WARNING(
                    f'  outside its barangay ({record.barangay.name}): {place.ref} at '
                    f'{place.point.y:.6f}, {place.point.x:.6f}'))
            same = (record.location is not None and record.location.equals_exact(place.point, SAME)
                    and record.location_precision == place.precision and record.location_basis == place.basis)
            if not same:
                record.location, record.location_precision, record.location_basis = (
                    place.point, place.precision, place.basis)
                changed.append(record)

        if not options['dry_run']:
            with transaction.atomic():
                for record in changed:
                    record.save(update_fields=FIELDS)
        self.stdout.write(f'Placed {len(changed)}, unchanged {len(places) - len(changed)}.')
        if options['dry_run']:
            self.stdout.write(self.style.SUCCESS('Dry run: nothing written.'))
