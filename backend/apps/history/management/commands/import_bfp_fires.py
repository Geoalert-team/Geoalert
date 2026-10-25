import csv
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.barangays.aliases import match_barangay
from apps.barangays.models import Barangay, Purok
from apps.hazards.models import HazardType
from apps.history import bfp
from apps.history.bfp_import import plan_import
from apps.history.bfp_link import link_address, load_variants
from apps.history.models import HistoricalRecord

PUROK_DATA = Path(__file__).resolve().parents[3] / 'barangays' / 'data' / 'puroks'
# Other spellings of purok names (barangay,variant,name), hand-edited
VARIANTS_FILE = PUROK_DATA / 'name_variants.csv'


class Command(BaseCommand):
    help = ('Import the BFP fire log (.xlsx) as fire history: one record per fire, linked to its purok where '
            'the address names one. Re-running adds only new fires. --relink re-links imported fires after '
            'the purok list changes.')

    def add_arguments(self, parser):
        parser.add_argument('file', nargs='?', help='The BFP fire log .xlsx.')
        parser.add_argument('--dry-run', action='store_true', help='Report without saving.')
        parser.add_argument('--relink', action='store_true',
                            help='Re-link every imported fire to its purok from its address (no file).')
        parser.add_argument('--names-from', metavar='CSV',
                            help='Take purok names from a purok_points.csv instead of the database. '
                                 'Implies --dry-run and never reads fire history, so it works before '
                                 'the migration and before a purok reload.')

    def handle(self, *args, **options):
        fire = HazardType.objects.filter(name__iexact='Fire').first()
        if fire is None:
            raise CommandError('No "Fire" hazard type.')
        barangays = list(Barangay.objects.all())
        variants = load_variants(VARIANTS_FILE) if VARIANTS_FILE.exists() else {}

        if options['relink']:
            self.relink(barangays, variants, options['dry_run'])
            return
        if not options['file']:
            raise CommandError('Give the BFP .xlsx file, or --relink.')
        path = Path(options['file'])
        if not path.exists():
            raise CommandError(f'File not found: {path}')
        rows = bfp.read_sheet(path)

        if options['names_from']:
            puroks_by_barangay, ids = self.puroks_from_csv(Path(options['names_from']), barangays)
            existing, dry_run = set(), True
        else:
            puroks_by_barangay, ids = self.puroks_from_db()
            existing = set(HistoricalRecord.objects.filter(source_ref__isnull=False)
                           .values_list('source_ref', flat=True))
            dry_run = options['dry_run']

        records, report = plan_import(rows, existing, barangays, puroks_by_barangay, variants)
        self.print_report(report)
        if dry_run:
            self.stdout.write(self.style.SUCCESS('Dry run: nothing saved.'))
            return

        with transaction.atomic():
            for rec in records:
                purok_name = rec.pop('purok_name')
                record = HistoricalRecord.objects.create(hazard_type=fire, **rec)
                if purok_name:
                    record.puroks.add(ids[(rec['barangay'].id, purok_name)])
        self.stdout.write(self.style.SUCCESS(f'Imported {len(records)} fires.'))

    def puroks_from_db(self):
        by_barangay, ids = {}, {}
        for pk, barangay_id, name in Purok.objects.values_list('id', 'barangay_id', 'name'):
            by_barangay.setdefault(barangay_id, []).append(name)
            ids[(barangay_id, name)] = pk
        return by_barangay, ids

    def puroks_from_csv(self, path, barangays):
        if not path.exists():
            raise CommandError(f'File not found: {path}')
        by_barangay = {}
        with open(path, encoding='utf-8', newline='') as fh:
            for row in csv.DictReader(fh):
                barangay = match_barangay(row['barangay'], barangays)
                if barangay is not None:
                    by_barangay.setdefault(barangay.id, []).append(row['name'])
        return by_barangay, {}

    def relink(self, barangays, variants, dry_run):
        puroks_by_barangay, ids = self.puroks_from_db()
        linked = barangay_only = changed = 0
        with transaction.atomic():
            for record in (HistoricalRecord.objects.filter(source_ref__startswith='bfp:')
                           .prefetch_related('puroks')):
                barangay, purok_name = link_address(record.location_text, barangays, puroks_by_barangay, variants)
                new = {ids[(barangay.id, purok_name)]} if purok_name else set()
                linked += bool(new)
                barangay_only += bool(barangay and not new)
                if new == {p.id for p in record.puroks.all()} and record.barangay_id == (barangay and barangay.id):
                    continue
                changed += 1
                if not dry_run:
                    record.barangay = barangay
                    record.save(update_fields=['barangay'])
                    record.puroks.set(new)
        self.stdout.write(f'linked {linked}\nbarangay_only {barangay_only}\nchanged {changed}')
        self.stdout.write(self.style.SUCCESS('Dry run: nothing saved.' if dry_run else 'Relinked.'))

    def print_report(self, report):
        for key in ('read', 'imported', 'skipped_existing', 'linked', 'barangay_only'):
            self.stdout.write(f'{key} {report[key]}')
        for key, label in (('outside_city', 'outside city'), ('duplicates', 'duplicates'),
                           ('bad_date', 'bad dates'), ('no_barangay', 'no barangay')):
            self.stdout.write(f'{label}: {report[key]}')
        self.stdout.write(f'unknown alarms: {report["unknown_alarms"]}')
        if report['unlinked']:
            self.stdout.write('Place names that matched no purok:')
        for barangay in sorted(report['unlinked']):
            names = sorted(report['unlinked'][barangay].items(), key=lambda kv: (-kv[1]['fires'], kv[0]))
            for name, entry in names:
                fires = f'{entry["fires"]} fire{"s" if entry["fires"] != 1 else ""}'
                close = f' - close: {", ".join(entry["close"])}' if entry['close'] else ''
                self.stdout.write(f'  {barangay}: {name} ({fires}){close}')
