from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.history import rain
from apps.history.hazard_data import DATA_DIR


class Command(BaseCommand):
    help = ('Download daily rain for every barangay from NASA POWER (2016-12-18 to the last day POWER has filled, '
            'a few days back) and write data/rain_daily.csv. One series for the city\'s grid cell, one request '
            'per year, newest first; no account or key needed. Reads the database only.')

    def handle(self, *args, **options):
        points = rain.representative_points()
        if not points:
            raise CommandError('No barangay boundaries in the database. Load the barangays first.')
        end = timezone.localdate() - timedelta(days=1)
        stats = {}
        series, cells = rain.download_archive(points, rain.ARCHIVE_FIRST_DAY, end, log=self.stdout.write, stats=stats)
        out = DATA_DIR / 'rain_daily.csv'
        rain.write_rain_csv(out, series, cells)
        rf = rain.read_rain_csv(out)
        self.stdout.write(f'First day: {rf.first_day}')
        self.stdout.write(f'Last day: {rf.last_day}')
        self.stdout.write(f'Distinct grid cells: {len(set(cells.values()))}')
        self.stdout.write(f'Retries: {stats["retries"]}')
        self.stdout.write(f'Failed spans: {", ".join(stats["failed"]) or "none"}')
        self.stdout.write(self.style.SUCCESS(f'{len(series)} barangays written to {out}'))
