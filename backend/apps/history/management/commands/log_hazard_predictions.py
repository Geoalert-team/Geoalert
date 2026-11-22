from datetime import datetime
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import DatabaseError

from apps.history import prediction_log

MANILA = ZoneInfo('Asia/Manila')
LOGGING_OFF = ('Prediction logging is off on this machine, so nothing was written. Only the one machine that writes '
               'the log (the deployed server) sets HAZARD_LOG_WRITER=true in its .env.')


class Command(BaseCommand):
    help = ("Add this month's figures to the prediction log, once a day; rows are only added, so a rerun adds "
            'nothing. Since 2026-11-22 nothing is logged until the fire purok log is built (plan Task B6). '
            'Runs only where HAZARD_LOG_WRITER is on (the deployed server).')

    def handle(self, *args, **options):
        if not settings.HAZARD_LOG_WRITER:
            raise CommandError(LOGGING_OFF)
        today = datetime.now(MANILA).date()
        try:
            months = prediction_log.write_month_rows(today)
        except DatabaseError as exc:
            raise CommandError(f'The prediction log could not be written ({exc}).') from exc
        self.stdout.write(self.style.SUCCESS(f'Prediction log for {today.isoformat()}: {months} new rows.'))
