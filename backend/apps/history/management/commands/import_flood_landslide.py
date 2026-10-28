from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.barangays.models import Barangay, Purok
from apps.hazards.models import HazardType
from apps.history import flood_landslide as fl
from apps.history.bfp_link import load_variants
from apps.history.models import HistoricalRecord

PUROK_DATA = Path(__file__).resolve().parents[3] / 'barangays' / 'data' / 'puroks'
# Other spellings of purok names (barangay,variant,name), hand-edited
VARIANTS_FILE = PUROK_DATA / 'name_variants.csv'


class Command(BaseCommand):
    help = ('Import the flood and landslide log (.xlsx) as history: one record per event per barangay it hit, '
            'linked to a purok where the log names one on the purok list. Re-running adds only new rows; '
            '--replace swaps in a corrected log.')

    def add_arguments(self, parser):
        parser.add_argument('file', help='The flood and landslide log .xlsx (sheets Flood, Landslide, By Barangay).')
        parser.add_argument('--dry-run', action='store_true', help='Report without saving.')
        parser.add_argument('--include-warnings', action='store_true',
                            help='Also import rows that are warnings only (pre-emptive evacuations, risk '
                                 'advisories, a rising river, a ground crack), not confirmed events.')
        parser.add_argument('--replace', action='store_true',
                            help='Delete every record an earlier run of this import made, then import the file.')

    def handle(self, *args, **options):
        types = {t.name: t for t in HazardType.objects.filter(name__in=fl.HAZARDS.values())}
        missing = sorted(set(fl.HAZARDS.values()) - set(types))
        if missing:
            raise CommandError(f'No hazard type named {", ".join(missing)}. Run seed_data first.')
        path = Path(options['file'])
        if not path.exists():
            raise CommandError(f'File not found: {path}')
        try:
            events, splits = fl.read_workbook(path)
        except ValueError as e:
            raise CommandError(str(e))

        barangays = list(Barangay.objects.all())
        variants = load_variants(VARIANTS_FILE) if VARIANTS_FILE.exists() else {}
        by_barangay, ids = {}, {}
        for pk, barangay_id, name in Purok.objects.values_list('id', 'barangay_id', 'name'):
            by_barangay.setdefault(barangay_id, []).append(name)
            ids[(barangay_id, name)] = pk
        earlier = HistoricalRecord.objects.filter(source_ref__startswith=fl.REF_PREFIX)
        existing = set() if options['replace'] else set(earlier.values_list('source_ref', flat=True))

        records, report = fl.plan_import(events, splits, existing, barangays, by_barangay, variants,
                                         include_warnings=options['include_warnings'])
        self.print_report(report)
        if options['dry_run']:
            replaced = f' (would replace {earlier.count()})' if options['replace'] else ''
            self.stdout.write(self.style.SUCCESS(f'Dry run: nothing saved{replaced}.'))
            return

        with transaction.atomic():
            removed = earlier.delete()[1].get('history.HistoricalRecord', 0) if options['replace'] else 0
            for rec in records:
                purok_names = rec.pop('purok_names')
                record = HistoricalRecord.objects.create(hazard_type=types[rec.pop('hazard')], **rec)
                if purok_names:
                    record.puroks.add(*(ids[(rec['barangay'].id, n)] for n in purok_names))
        replaced = f', replacing {removed}' if options['replace'] else ''
        self.stdout.write(self.style.SUCCESS(f'Imported {len(records)} records{replaced}.'))

    def print_report(self, report):
        for key in ('read', 'imported', 'skipped_existing', 'linked', 'barangay_only'):
            self.stdout.write(f'{key} {report[key]}')
        for key, label in (('warnings_skipped', 'warnings left out'), ('no_barangay', 'no barangay named'),
                           ('outside_city', 'outside city'), ('bad_date', 'bad dates'),
                           ('unknown_hazards', 'unknown hazards'), ('duplicate_events', 'duplicate events'),
                           ('splits_without_event', 'By Barangay rows with no event'),
                           ('unknown_barangays', 'unknown barangays')):
            if report[key]:
                self.stdout.write(f'{label}: {", ".join(report[key])}')
        if report['unlinked']:
            self.stdout.write('Places that matched no purok (filed under the barangay):')
        for barangay in sorted(report['unlinked']):
            for place, close in sorted(report['unlinked'][barangay].items()):
                hint = f' - close: {", ".join(close)}' if close else ''
                self.stdout.write(f'  {barangay}: {place}{hint}')
        if report['to_check']:
            self.stdout.write('Marked CHECK in the log (to confirm with CDRRMO):')
        for line in report['to_check']:
            self.stdout.write(f'  {line}')
