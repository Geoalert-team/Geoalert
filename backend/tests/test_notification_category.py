"""
A notification stores the bell tab it belongs to. Notices about a hazard are
filed under it however they are worded; rows from before the field are
filed the way the bell used to guess them (migration 0003).
"""
import importlib

from django.test import SimpleTestCase, TestCase

from apps.hazards.alerts import issue_alert, notify
from apps.notifications.models import Notification
from apps.notifications.serializers import NotificationSerializer
from tests.fire_setup import FireSetupMixin

backfill = importlib.import_module('apps.notifications.migrations.0003_notification_category')


class StoredCategoryTests(FireSetupMixin, TestCase):
    def test_an_alert_and_a_notice_about_a_zone_are_hazards_whatever_they_say(self):
        zone = self.zone(self.near)
        issue_alert(zone, issued_by=self.officer)
        # Wording the old guess would have filed under "report"
        notify([self.reporter], 'The fire you reported is out.', zone)
        categories = {NotificationSerializer(n).data['category'] for n in Notification.objects.all()}
        self.assertEqual(categories, {'hazard'})

    def test_the_category_given_is_the_one_kept(self):
        notify([self.reporter], 'Your password was changed.', category=Notification.SECURITY)
        self.assertEqual(Notification.objects.get().category, 'security')


class BackfillTests(SimpleTestCase):
    def test_rows_from_before_are_filed_as_the_bell_guessed(self):
        guess = backfill.category_for
        self.assertEqual(guess('anything', True), 'hazard')
        self.assertEqual(guess('WITHDRAWN: the flood alert was published in error', False), 'hazard')
        self.assertEqual(guess('Your report was validated.', False), 'report')
        self.assertEqual(guess('Your account was locked after failed sign-ins.', False), 'security')
        self.assertEqual(guess('Welcome to GeoAlert.', False), 'account')
