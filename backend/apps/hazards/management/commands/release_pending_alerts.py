"""
Send Extreme alerts that waited past the approval window.

The map and the notification bell already do this on every request, so in
normal use nothing needs to run. On a quiet night with nobody signed in and
nobody looking at the map, schedule this every minute so a held alert still
goes out on time:

    * * * * *  cd /path/to/backend && venv/bin/python manage.py release_pending_alerts
"""

from django.core.management.base import BaseCommand

from apps.hazards.alerts import release_overdue_approvals, remind_unread_extreme


class Command(BaseCommand):
    help = 'Send Extreme alerts that nobody approved within the approval window.'

    def handle(self, *args, **options):
        sent = release_overdue_approvals()
        reminded = remind_unread_extreme()
        self.stdout.write(f'{sent} alert(s) sent, {reminded} unread alert(s) followed up.')
