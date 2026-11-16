from datetime import datetime

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import DatabaseError, ProgrammingError

from apps.history import prediction_log
from apps.history.hazard_data import MANILA

LOGGING_OFF = ('Prediction logging is off on this machine, so nothing was written. Only the one machine that writes '
               'the log (the deployed server) sets HAZARD_LOG_WRITER=true in its .env.')


class Command(BaseCommand):
    help = ("Add today's chances to the prediction log (hazard_prediction_log, spec 3.4): flood's and landslide's "
            'chance for each rain day not yet logged under the model in use (at most 30 days back), and every '
            "hazard's chance and level for this month in each barangay, as the forecast shows them. Rows are only "
            'added, so a rerun adds nothing. Run it once a day; the warm-up thread also runs it once a Manila day. '
            'Runs only where HAZARD_LOG_WRITER is on (the deployed server).')

    def handle(self, *args, **options):
        if not settings.HAZARD_LOG_WRITER:
            raise CommandError(LOGGING_OFF)
        today = datetime.now(MANILA).date()
        try:
            days = prediction_log.write_day_rows(today)
            months = prediction_log.write_month_rows(today)
        except DatabaseError as exc:
            hint = ' Has migration history 0008 been applied?' if isinstance(exc, ProgrammingError) else ''
            raise CommandError(f'The prediction log could not be written ({exc}).{hint}') from exc
        self.stdout.write(self.style.SUCCESS(
            f'Prediction log for {today.isoformat()}: {days} new day rows and {months} new month rows.'))
