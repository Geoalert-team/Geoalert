"""
manage.py release_pending_alerts: the timed alert jobs, once (for a scheduler)
or in a loop (as a worker), so a held Extreme alert goes out on time with
nobody looking at the map. Against a real database.
"""
import io
from datetime import timedelta
from unittest import mock

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from apps.hazards.models import HazardAlert, HazardZone
from tests.fire_setup import FireSetupMixin

COMMAND = 'apps.hazards.management.commands.release_pending_alerts'


class AlertJobsTests(FireSetupMixin, TestCase):
    def held_too_long(self):
        zone = self.zone(self.near, severity='Red', status='Awaiting_Approval')
        HazardZone.objects.filter(pk=zone.pk).update(activated_at=timezone.now() - timedelta(minutes=30))
        return zone

    def jobs(self, **options):
        out = io.StringIO()
        # The worker drops its connection between runs; here that would end
        # the test's own transaction, so it is left open
        with mock.patch(f'{COMMAND}.close_old_connections'):
            call_command('release_pending_alerts', stdout=out, **options)
        return out.getvalue()

    def test_one_run_sends_a_held_alert_that_is_due(self):
        zone = self.held_too_long()
        self.assertIn('1 alert(s) sent', self.jobs())
        zone.refresh_from_db()
        self.assertEqual((zone.status, zone.auto_released), ('Active', True))
        self.assertTrue(HazardAlert.objects.filter(hazard_zone=zone).exists())

    def test_nothing_due_sends_nothing(self):
        self.zone(self.near, severity='Red', status='Awaiting_Approval')  # just held
        self.assertIn('0 alert(s) sent', self.jobs())
        self.assertFalse(HazardAlert.objects.exists())

    def test_the_loop_runs_until_stopped(self):
        zone = self.held_too_long()
        with mock.patch(f'{COMMAND}.time.sleep', side_effect=KeyboardInterrupt):
            out = self.jobs(loop=True)
        self.assertIn('1 alert(s) sent', out)
        self.assertTrue(out.rstrip().endswith('Stopped.'))
        self.assertEqual(HazardZone.objects.get(pk=zone.pk).status, 'Active')

    def test_a_failed_run_does_not_stop_the_loop(self):
        failing = mock.patch(f'{COMMAND}.release_overdue_approvals', side_effect=[RuntimeError('database away'), 0])
        sleeps = mock.patch(f'{COMMAND}.time.sleep', side_effect=[None, KeyboardInterrupt])
        with failing as release, sleeps, self.assertLogs(COMMAND, 'ERROR'):
            self.jobs(loop=True)
        self.assertEqual(release.call_count, 2)
