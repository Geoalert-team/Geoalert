"""
The timed alert jobs: send Extreme alerts (and raises to Extreme) that waited
past the approval window, remind barangays that haven't opened an Extreme
alert, and nudge publishers about zones with no update for a day.

The map and the notification bell also run these on their requests, but only
while someone has them open. Schedule this so they happen on time at 2 AM too:

  One run, once a minute, from a scheduler:
    Windows Task Scheduler   see the README, "Alert jobs"
    cron    * * * * *  cd /path/to/backend && venv/bin/python manage.py release_pending_alerts

  Or keep it running as a worker:
    python manage.py release_pending_alerts --loop              every 60 seconds
    python manage.py release_pending_alerts --loop --every 30

Running it in more than one place is safe: every job locks what it sends
(SKIP LOCKED), so nothing goes out twice.
"""
import logging
import time

from django.core.management.base import BaseCommand
from django.db import close_old_connections
from django.utils import timezone

from apps.hazards.alerts import nudge_stale_zones, release_overdue_approvals, remind_unread_extreme

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = ('Send held Extreme alerts that are due, follow up unread Extreme alerts and flag stale zones. '
            'Run it once a minute from a scheduler, or with --loop as a worker.')

    def add_arguments(self, parser):
        parser.add_argument('--loop', action='store_true', help='Keep running, once every --every seconds.')
        parser.add_argument('--every', type=int, default=60, help='Seconds between runs with --loop (default 60).')

    def handle(self, *args, **options):
        if not options['loop']:
            self.stdout.write(summary(*run_jobs()))
            return

        every = max(options['every'], 10)
        self.stdout.write(f'Running the alert jobs every {every} seconds. Ctrl+C stops.')
        try:
            while True:
                # The pooler drops idle connections: never carry one across the wait
                close_old_connections()
                try:
                    counts = run_jobs()
                    if any(counts):
                        self.stdout.write(f'{timezone.localtime():%Y-%m-%d %H:%M} {summary(*counts)}')
                except Exception:
                    # One failed run (the database briefly unreachable) must not stop the worker
                    logger.exception('Alert jobs failed; trying again on the next run')
                time.sleep(every)
        except KeyboardInterrupt:
            self.stdout.write('Stopped.')


def run_jobs():
    return release_overdue_approvals(), remind_unread_extreme(), nudge_stale_zones()


def summary(sent, reminded, stale):
    return f'{sent} alert(s) sent, {reminded} unread alert(s) followed up, {stale} stale zone(s) flagged.'
