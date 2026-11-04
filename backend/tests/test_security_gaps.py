"""
The security review's gaps (2026-11-04), each closed:

- Wrong 2FA codes add up to the usual lockout: the password step no longer
  clears the failed-sign-in count for a 2FA account; a correct code does.
- Barangay personnel report only for the barangay their account is assigned to.
- A resolved or archived hazard can't be put back on the map by an edit.
"""
from datetime import timedelta

import pyotp
from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.accounts.models import Role, User
from apps.hazards.views import HazardZoneDetailView
from apps.reports.models import IncidentReport
from apps.reports.views import IncidentReportListCreateView
from tests.fire_setup import FireSetupMixin
from utils.system_settings import get_setting

PASSWORD = 'Correct-horse-9'


@override_settings(CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}})
class TwoFactorLockoutTests(TestCase):
    def setUp(self):
        cache.clear()
        role = Role.objects.get_or_create(name='DRRMO_Officer')[0]
        self.secret = pyotp.random_base32()
        self.user = User.objects.create_user(email='twofa@test.ph', password=PASSWORD, full_name='Two Factor',
                                             role=role, two_factor_enabled=True, two_factor_secret=self.secret)
        self.client = Client()

    def password(self):
        return self.client.post('/api/auth/login/', {'email': self.user.email, 'password': PASSWORD},
                                content_type='application/json')

    def code(self, code):
        return self.client.post('/api/auth/2fa/verify/', {'code': code}, content_type='application/json')

    def wrong_code(self):
        totp = pyotp.TOTP(self.secret)
        valid = {totp.at(timezone.now() + timedelta(seconds=s)) for s in (-30, 0, 30)}
        return next(c for c in (f'{n:06d}' for n in range(1000000)) if c not in valid)

    def failed_round(self):
        """The right password, then five wrong codes."""
        self.assertEqual(self.password().status_code, 200)
        for _ in range(5):
            response = self.code(self.wrong_code())
        cache.clear()  # the per-address throttle is a separate guard; this is about the account
        return response

    def test_rounds_of_wrong_codes_lock_the_account(self):
        for _ in range(get_setting('auth.max_failed_logins')):
            self.assertEqual(self.failed_round().status_code, 429)
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_locked())
        self.assertEqual(self.password().status_code, 423)

    def test_a_full_sign_in_clears_the_count(self):
        self.failed_round()
        self.user.refresh_from_db()
        self.assertEqual(self.user.failed_login_count, 1)
        self.assertEqual(self.password().status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.failed_login_count, 1)  # the password alone doesn't clear it
        self.assertEqual(self.code(pyotp.TOTP(self.secret).now()).status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.failed_login_count, 0)


class ReportBarangayTests(FireSetupMixin, TestCase):
    def file(self, user, barangay, purok):
        body = {'hazard_type': self.fire.id, 'barangay': barangay.id, 'puroks': [purok.id],
                'description': 'Smoke from a house', 'started_at': (timezone.now() - timedelta(minutes=10)).isoformat()}
        request = APIRequestFactory().post('/api/reports/incidents/', body, format='json')
        force_authenticate(request, user=user)
        return IncidentReportListCreateView.as_view()(request)

    def test_barangay_personnel_report_only_for_their_own_barangay(self):
        response = self.file(self.reporter, self.next, self.far)  # assigned to Home
        self.assertEqual(response.status_code, 400)
        self.assertIn('Home', str(response.data['barangay']))
        self.assertFalse(IncidentReport.objects.exists())
        self.assertEqual(self.file(self.reporter, self.home, self.near).status_code, 201)

    def test_drrmo_can_still_file_for_any_barangay(self):
        self.assertEqual(self.file(self.officer, self.next, self.far).status_code, 201)


class NoReopeningTests(FireSetupMixin, TestCase):
    def patch(self, zone, body):
        request = APIRequestFactory().patch('/', body, format='json')
        force_authenticate(request, user=self.officer)
        return HazardZoneDetailView.as_view()(request, pk=zone.pk)

    def test_a_resolved_hazard_cannot_go_back_on_the_map(self):
        for status in ('Resolved', 'Archived'):
            zone = self.zone(self.near, hazard_type=self.flood, status=status)
            for body in ({'status': 'Active', 'severity': 'Red'}, {'status': 'Active'}):
                self.assertEqual(self.patch(zone, body).status_code, 400, (status, body))
                zone.refresh_from_db()
                self.assertEqual(zone.status, status)

    def test_system_statuses_cannot_be_set_by_hand(self):
        zone = self.zone(self.near, hazard_type=self.flood)
        for status in ('Awaiting_Approval', 'Resolving'):
            self.assertEqual(self.patch(zone, {'status': status}).status_code, 400, status)
        zone.refresh_from_db()
        self.assertEqual(zone.status, 'Active')

    def test_a_resolved_hazard_can_still_be_archived(self):
        zone = self.zone(self.near, hazard_type=self.flood, status='Resolved')
        self.assertEqual(self.patch(zone, {'status': 'Archived'}).status_code, 200)
