from datetime import datetime, timezone

from django.core.management.base import BaseCommand, CommandError

from apps.history import storms
from apps.history.hazard_data import MANILA
from apps.history.rain import ARCHIVE_FIRST_DAY


class Command(BaseCommand):
    help = ('Download IBTrACS storm tracks and write data/storm_days.csv (days with a storm centre within 300 km of '
            'Talisay in the 72 hours to the end of the day). Without --recent: the West Pacific file from '
            '2006-12-18, then the last-3-years file merged in. With --recent: only the last-3-years file, merged '
            'into the existing file. Reads the database only for the city centre.')

    def add_arguments(self, parser):
        parser.add_argument('--recent', action='store_true',
                            help='Read only the last-3-years file and merge it into the existing file.')

    def handle(self, *args, **options):
        try:
            centre = storms.talisay_centre()
        except ValueError as exc:
            raise CommandError(f'{exc} Load the barangays first.') from exc
        now = datetime.now(timezone.utc)
        recent_since = storms._recent_since(now.astimezone(MANILA).date())
        try:
            if options['recent']:
                try:
                    sd = storms.read_storm_days(storms.STORM_FILE, storms.META_FILE)
                except FileNotFoundError:
                    raise CommandError('No storm file yet. Run fetch_storms without --recent first.')
                sd = storms.merge(sd, storms.download(storms.LAST3_URL, centre, recent_since))
                source = 'IBTrACS v04r01 (previous file + last3years)'
            else:
                sd = storms.download(storms.WP_URL, centre, ARCHIVE_FIRST_DAY)
                sd = storms.merge(sd, storms.download(storms.LAST3_URL, centre, recent_since))
                source = 'IBTrACS v04r01 WP + last3years'
        except CommandError:
            raise
        except Exception as exc:
            raise CommandError(f'IBTrACS download failed: {exc}') from exc
        storms.write_storm_days(sd, source, now, centre, storms.STORM_FILE, storms.META_FILE)
        self.stdout.write(f'Storm days flagged: {len(sd.days)}')
        self.stdout.write(f'First covered day: {sd.first_day}')
        self.stdout.write(f'Last covered day: {sd.last_day}')
        self.stdout.write(f'Centre: {centre[0]:.4f}, {centre[1]:.4f}')
        self.stdout.write(self.style.SUCCESS(f'Written to {storms.STORM_FILE}'))
