from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.history.importing import ImportProblem, import_floods


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
        path = Path(options['file'])
        if not path.exists():
            raise CommandError(f'File not found: {path}')
        # The History page's Import saves through the same function (apps/history/importing.py)
        try:
            report = import_floods(path, save=not options['dry_run'],
                                   include_warnings=options['include_warnings'], replace=options['replace'])
        except ImportProblem as e:
            raise CommandError(str(e))
        self.print_report(report)
        if options['dry_run']:
            replaced = f' (would replace {report["replaced"]})' if options['replace'] else ''
            self.stdout.write(self.style.SUCCESS(f'Dry run: nothing saved{replaced}.'))
            return
        replaced = f', replacing {report["replaced"]}' if options['replace'] else ''
        self.stdout.write(self.style.SUCCESS(f'Imported {report["imported"]} records{replaced}.'))

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
