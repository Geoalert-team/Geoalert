from datetime import datetime
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import DatabaseError

from apps.history import fire_purok, flood_purok, landslide_purok, prediction_log

MANILA = ZoneInfo('Asia/Manila')
LOGGING_OFF = ('Prediction logging is off on this machine, so nothing was written. Only the one machine that writes '
               'the log (the deployed server) sets HAZARD_LOG_WRITER=true in its .env.')


class Command(BaseCommand):
    help = ("Add today's snapshot of every purok's fire chance for this month to the fire purok prediction log "
            '(fire_purok_prediction_log), and the flood model\'s classes, once per version, to the flood '
            'susceptibility log and the landslide model\'s the same way; rows are only added, so a rerun adds nothing. Runs only where HAZARD_LOG_WRITER is '
            'on (the deployed server).')

    def handle(self, *args, **options):
        if not settings.HAZARD_LOG_WRITER:
            raise CommandError(LOGGING_OFF)
        today = datetime.now(MANILA).date()
        model = fire_purok.load()
        hazard = 'fire'  # the log being written, so a failure names its own migration
        try:
            if isinstance(model, str):
                self.stdout.write(f'Fire: nothing was logged: {model}')
            else:
                rows = prediction_log.write_month_rows(today)
                self.stdout.write(self.style.SUCCESS(
                    f'Fire purok log for {today.isoformat()} ({model.version}): {rows} new rows.'))
            flood = flood_purok.load()
            if isinstance(flood, str):
                self.stdout.write(f'Flood: nothing was logged: {flood}')
            else:
                hazard = 'flood'
                rows = prediction_log.write_flood_rows(today)
                self.stdout.write(self.style.SUCCESS(
                    f'Flood susceptibility log ({flood.version}): {rows} new rows.'))
            landslide = landslide_purok.load()
            if isinstance(landslide, str):
                self.stdout.write(f'Landslide: nothing was logged: {landslide}')
            else:
                hazard = 'landslide'
                rows = prediction_log.write_landslide_rows(today)
                self.stdout.write(self.style.SUCCESS(
                    f'Landslide susceptibility log ({landslide.version}): {rows} new rows.'))
        except DatabaseError as exc:
            raise CommandError(prediction_log.write_failure(exc, hazard)) from exc
