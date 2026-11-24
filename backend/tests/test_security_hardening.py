"""
The fixes from the 2026-11-24 security audit, each pinned by a test.

  GA-01  a forged X-Forwarded-For can't pick the throttle's address or drop an
         audit row; Vercel's proxy secret decides whose first entry is believed
  GA-02  Django's admin site is off unless DJANGO_ADMIN_ENABLED
  GA-06  2FA: locked or deactivated accounts stop at the code step, wrong codes
         count per account across attempts, a code signs in only once
  GA-07  the public map stores one copy of its answer, not one per query string
  GA-09  guidance changes and report submissions are audited
  GA-10  the signed-in account views check the CSRF token
  GA-11  the public map and history list leave staff-only fields out
  GA-12  passwords are at least 12 characters
  GA-16  an admin can't deactivate or demote themselves by sending "false"
"""
from unittest import mock

import pyotp
from django.contrib.auth.password_validation import validate_password
from django.contrib.gis.geos import MultiPolygon, Polygon
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.test import Client, RequestFactory, SimpleTestCase, TestCase, override_settings
from django.urls import Resolver404, resolve

from apps.accounts.models import Role, User
from apps.admin_dashboard.models import AuditLog
from apps.guidance.models import GuidanceContent
from apps.hazards.models import HazardType, HazardZone
from apps.history.models import HistoricalRecord
from utils import login_throttle, proxy
from utils.audit import log_event
from utils.health import _proxy
from utils.login_throttle import throttle_ip, valid_ip

LOCMEM = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache', 'LOCATION': 'hardening'}}
PASSWORD = 'Correct-horse-9!x'
SECRET = 's3cret-from-vercel'


def request(forwarded=None, remote='10.0.0.1', secret=None, path='/api/auth/login/'):
    extra = {'REMOTE_ADDR': remote}
    if forwarded is not None:
        extra['HTTP_X_FORWARDED_FOR'] = forwarded
    if secret is not None:
        extra['HTTP_X_GEOALERT_PROXY'] = secret
    return RequestFactory().post(path, **extra)


# ---------------------------------------------------------------- GA-01

@override_settings(BEHIND_PROXY=True, FORWARDED_FOR_TRUST_FIRST=True, PROXY_SECRET=SECRET)
class ProxySecretTests(SimpleTestCase):
    def test_the_first_entry_is_believed_with_the_secret(self):
        self.assertEqual(throttle_ip(request('203.0.113.9, 76.76.21.21', secret=SECRET)), '203.0.113.9')

    def test_without_it_the_entry_the_proxy_added_is_used(self):
        # A request sent straight to Render: the client wrote the first entry
        self.assertEqual(throttle_ip(request('6.6.6.6, 198.51.100.20')), '198.51.100.20')

    def test_a_wrong_secret_is_no_secret(self):
        self.assertEqual(throttle_ip(request('6.6.6.6, 198.51.100.20', secret='guess')), '198.51.100.20')

    def test_rotating_forged_entries_still_get_blocked(self):
        with override_settings(CACHES=LOCMEM):
            cache.clear()
            reqs = [request(f'10.9.{i}.1, 198.51.100.20') for i in range(login_throttle.MAX_FAILS)]
            for r in reqs:
                login_throttle.record_failure(r)
            self.assertTrue(login_throttle.is_blocked(request('1.1.1.1, 198.51.100.20')))

    @override_settings(PROXY_SECRET='')
    def test_without_a_configured_secret_nothing_changes(self):
        # Deployed before the secret is set on both sides: as before
        self.assertEqual(throttle_ip(request('203.0.113.9, 76.76.21.21')), '203.0.113.9')

    def test_an_entry_that_is_not_an_address_is_never_used(self):
        self.assertEqual(throttle_ip(request('not-an-ip', secret=SECRET)), '10.0.0.1')
        self.assertEqual(throttle_ip(request('"><script>', secret=SECRET)), '10.0.0.1')

    def test_ports_are_dropped(self):
        self.assertEqual(valid_ip('203.0.113.5:4711'), '203.0.113.5')
        self.assertEqual(valid_ip('[2001:db8::1]:443'), '2001:db8::1')
        self.assertIsNone(valid_ip('example.com:80'))


@override_settings(PROXY_SECRET=SECRET, REQUIRE_PROXY_SECRET=True)
class ProxySecretMiddlewareTests(SimpleTestCase):
    def call(self, path, method='get', secret=None):
        rf = getattr(RequestFactory(), method)
        extra = {'HTTP_X_GEOALERT_PROXY': secret} if secret else {}
        return proxy.ProxySecretMiddleware(lambda r: 'passed')(rf(path, **extra))

    def test_direct_api_calls_are_refused(self):
        self.assertEqual(self.call('/api/auth/login/', 'post').status_code, 403)

    def test_the_website_gets_through(self):
        self.assertEqual(self.call('/api/auth/login/', 'post', secret=SECRET), 'passed')

    def test_the_keep_awake_job_gets_through(self):
        self.assertEqual(self.call('/api/hazards/'), 'passed')

    def test_exempt_paths_are_exact_not_prefixes(self):
        # /api/hazards/ is exempt; the officers' hazard endpoints under it are not
        self.assertEqual(self.call('/api/hazards/resolved/').status_code, 403)
        self.assertEqual(self.call('/api/hazards/00000000-0000-0000-0000-000000000000/retract/', 'post').status_code, 403)

    def test_the_retraining_job_gets_through_with_its_own_token_check(self):
        # The view still demands MODEL_JOB_TOKEN; only the proxy secret is waived
        self.assertEqual(self.call('/api/history/model-job/data/'), 'passed')
        self.assertEqual(self.call('/api/history/model-job/attempts/', 'post'), 'passed')

    def test_non_api_paths_are_untouched(self):
        self.assertEqual(self.call('/'), 'passed')

    @override_settings(REQUIRE_PROXY_SECRET=False)
    def test_off_unless_asked_for(self):
        self.assertEqual(self.call('/api/auth/login/', 'post'), 'passed')


@override_settings(BEHIND_PROXY=True, FORWARDED_FOR_TRUST_FIRST=True, PROXY_SECRET='')
class AuditRowTests(TestCase):
    def test_a_header_that_is_not_an_address_still_leaves_a_row(self):
        log_event(request('not-an-ip'), 'TEST_ROW', details='x')
        self.assertEqual(AuditLog.objects.get(action='TEST_ROW').ip_address, '10.0.0.1')

    def test_a_refused_row_is_written_again_without_the_address(self):
        real = AuditLog.objects.create
        calls = []

        def flaky(**fields):
            calls.append(fields)
            if len(calls) == 1:
                raise ValueError('refused')
            return real(**fields)

        with mock.patch.object(AuditLog.objects, 'create', side_effect=flaky):
            log_event(request('203.0.113.9'), 'TEST_RETRY')
        row = AuditLog.objects.get(action='TEST_RETRY')
        self.assertIsNone(row.ip_address)
        self.assertEqual(len(calls), 2)


@override_settings(BEHIND_PROXY=True, FORWARDED_FOR_TRUST_FIRST=True)
class ProxyHealthCheckTests(SimpleTestCase):
    @override_settings(PROXY_SECRET='')
    def test_no_secret_is_a_warning(self):
        self.assertEqual(_proxy(request())['state'], 'warn')

    @override_settings(PROXY_SECRET=SECRET)
    def test_the_secret_arriving_is_ok(self):
        self.assertEqual(_proxy(request(secret=SECRET))['state'], 'ok')

    @override_settings(PROXY_SECRET=SECRET)
    def test_the_secret_missing_from_the_website_is_a_warning(self):
        self.assertEqual(_proxy(request())['state'], 'warn')


# ---------------------------------------------------------------- GA-02

class DjangoAdminTests(SimpleTestCase):
    def test_the_admin_site_is_not_served(self):
        with self.assertRaises(Resolver404):
            resolve('/django-admin/')


# ---------------------------------------------------------------- GA-06

@override_settings(CACHES=LOCMEM)
class TwoFactorHardeningTests(TestCase):
    def setUp(self):
        cache.clear()
        role = Role.objects.get_or_create(name='DRRMO_Officer')[0]
        self.secret = pyotp.random_base32()
        self.user = User.objects.create_user(email='hardening@test.ph', password=PASSWORD, full_name='H',
                                             role=role, two_factor_enabled=True, two_factor_secret=self.secret)

    n = 0

    def address(self):
        # A new address per request: the per-address throttle is a separate
        # guard, and these tests are about the account
        self.n += 1
        return f'10.{self.n // 250}.{self.n % 250}.1'

    def attempt(self):
        c = Client()
        r = c.post('/api/auth/login/', {'email': self.user.email, 'password': PASSWORD},
                   content_type='application/json', REMOTE_ADDR=self.address())
        self.assertEqual(r.json(), {'require_2fa': True})
        return c

    def code(self, c, code):
        return c.post('/api/auth/2fa/verify/', {'code': code}, content_type='application/json',
                      REMOTE_ADDR=self.address())

    def wrong(self):
        good = pyotp.TOTP(self.secret).now()
        return f'{(int(good) + 500000) % 1000000:06d}'

    def test_a_locked_account_stops_at_the_code_step(self):
        c = self.attempt()
        self.user.failed_login_count = 5
        self.user.locked_until = self.user.created_at.replace(year=2999)
        self.user.save()
        self.assertEqual(self.code(c, pyotp.TOTP(self.secret).now()).status_code, 423)

    def test_a_deactivated_account_stops_at_the_code_step(self):
        c = self.attempt()
        User.objects.filter(pk=self.user.pk).update(is_active=False)
        self.assertEqual(self.code(c, pyotp.TOTP(self.secret).now()).status_code, 400)

    def test_wrong_codes_count_across_attempts(self):
        # Four wrong codes per attempt never reached the per-attempt limit,
        # so they used to never count as a failed sign-in
        for _ in range(5):
            c = self.attempt()
            for _ in range(4):
                self.assertEqual(self.code(c, self.wrong()).status_code, 401)
        self.user.refresh_from_db()
        self.assertEqual(self.user.failed_login_count, 4)  # 20 wrong codes

    def test_guessing_in_parallel_ends_in_the_lockout(self):
        # All opened before any lock: a correct password never counts as a failure
        attempts = [self.attempt() for _ in range(8)]
        for c in attempts[:7]:
            for _ in range(4):
                self.code(c, self.wrong())  # 28 in all; the 25th locks
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_locked())
        # The attempt still open can't sign in now, not even with the right code
        self.assertEqual(self.code(attempts[7], pyotp.TOTP(self.secret).now()).status_code, 423)

    def test_a_code_signs_in_only_once(self):
        code = pyotp.TOTP(self.secret).now()
        self.assertEqual(self.code(self.attempt(), code).status_code, 200)
        second = self.code(self.attempt(), code)
        self.assertEqual(second.status_code, 401)
        self.assertIn('already used', second.json()['error'])

    def test_a_full_sign_in_clears_the_wrong_codes(self):
        c = self.attempt()
        for _ in range(3):
            self.code(c, self.wrong())
        self.assertEqual(self.code(c, pyotp.TOTP(self.secret).now()).status_code, 200)
        c = self.attempt()
        for _ in range(4):
            self.code(c, self.wrong())
        self.user.refresh_from_db()
        self.assertEqual(self.user.failed_login_count, 0)  # 4 since the sign-in, not 7


# ---------------------------------------------------------------- GA-10

@override_settings(CACHES=LOCMEM)
class AccountCsrfTests(TestCase):
    def setUp(self):
        role = Role.objects.get_or_create(name='DRRMO_Officer')[0]
        self.user = User.objects.create_user(email='csrf@test.ph', password=PASSWORD, full_name='C', role=role)
        self.client = Client(enforce_csrf_checks=True)
        self.client.force_login(self.user)

    def test_two_factor_setup_needs_the_token(self):
        self.assertEqual(self.client.post('/api/auth/2fa/setup/', {'x': '1'}).status_code, 403)
        self.client.get('/api/auth/csrf/')
        token = self.client.cookies['csrftoken'].value
        self.assertEqual(self.client.post('/api/auth/2fa/setup/', HTTP_X_CSRFTOKEN=token).status_code, 200)

    def test_change_password_needs_the_token(self):
        r = self.client.post('/api/auth/change-password/',
                             {'current_password': PASSWORD, 'new_password': 'Another-horse-10!x'})
        self.assertEqual(r.status_code, 403)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(PASSWORD))


# ---------------------------------------------------------------- GA-07, GA-11

@override_settings(CACHES=LOCMEM)
class PublicMapTests(TestCase):
    def setUp(self):
        cache.clear()
        role = Role.objects.get_or_create(name='DRRMO_Officer')[0]
        self.officer = User.objects.create_user(email='officer@test.ph', password=PASSWORD, full_name='Officer Name',
                                                role=role)
        self.zone = HazardZone.objects.create(
            hazard_type=HazardType.objects.get_or_create(name='Flood')[0], severity='Orange', status='Active',
            description='Test zone', approved_by=self.officer, pending_severity='Red',
            geometry=MultiPolygon(Polygon.from_bbox((123.85, 10.24, 123.851, 10.241)), srid=4326),
        )

    def properties(self, client):
        [feature] = client.get('/api/hazards/').json()['features']
        return feature['properties']

    def test_the_public_copy_leaves_staff_fields_out(self):
        props = self.properties(Client())
        for name in ('approved_by_name', 'pending_severity', 'pending_at', 'outline'):
            self.assertNotIn(name, props)
        self.assertEqual(props['severity'], 'Orange')

    def test_staff_still_get_them(self):
        c = Client()
        c.force_login(self.officer)
        props = self.properties(c)
        self.assertEqual(props['approved_by_name'], 'Officer Name')
        self.assertEqual(props['pending_severity'], 'Red')

    def test_a_query_string_doesnt_store_another_copy(self):
        Client().get('/api/hazards/')
        stored = len([k for k in cache._cache if 'map-body' in k])
        for i in range(5):
            self.assertEqual(Client().get(f'/api/hazards/?r={i}').status_code, 200)
        self.assertEqual(len([k for k in cache._cache if 'map-body' in k]), stored)

    def test_a_barangay_that_is_not_an_id_is_a_400(self):
        self.assertEqual(Client().get('/api/hazards/?barangay=abc').status_code, 400)

    def test_the_public_history_list_leaves_the_zone_out(self):
        HistoricalRecord.objects.create(hazard_zone=self.zone, hazard_type=self.zone.hazard_type,
                                        severity_level='Orange', description='x',
                                        occurred_at=self.zone.activated_at)
        [row] = Client().get('/api/history/').json()
        self.assertNotIn('hazard_zone', row)
        c = Client()
        c.force_login(self.officer)
        [row] = c.get('/api/history/').json()
        self.assertEqual(row['hazard_zone'], str(self.zone.id))


# ---------------------------------------------------------------- GA-09, GA-12, GA-16

@override_settings(CACHES=LOCMEM)
class AdminAndAuditTests(TestCase):
    def setUp(self):
        self.admin_role = Role.objects.get_or_create(name='System_Admin')[0]
        self.drrmo_role = Role.objects.get_or_create(name='DRRMO_Officer')[0]
        self.admin = User.objects.create_user(email='admin@test.ph', password=PASSWORD, full_name='A',
                                              role=self.admin_role)
        self.client = Client()
        self.client.force_login(self.admin)

    def put(self, user, body):
        return self.client.put(f'/api/admin-dashboard/users/{user.id}/', body, content_type='application/json')

    def test_false_as_text_cant_deactivate_yourself(self):
        for value in (False, 'false', 0, 'no'):
            self.assertEqual(self.put(self.admin, {'is_active': value}).status_code, 400, value)
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_active)

    def test_you_cant_remove_your_own_admin_role(self):
        self.assertEqual(self.put(self.admin, {'role_id': self.drrmo_role.id}).status_code, 400)

    def test_another_admin_can_still_be_changed(self):
        other = User.objects.create_user(email='other@test.ph', password=PASSWORD, full_name='O',
                                         role=self.admin_role)
        self.assertEqual(self.put(other, {'role_id': self.drrmo_role.id}).status_code, 200)

    def test_guidance_changes_are_audited(self):
        flood = HazardType.objects.get_or_create(name='Flood')[0]
        r = self.client.post('/api/guidance/', {'hazard_type': flood.id, 'title': 'Sandbags', 'body': 'Stack them',
                                                'timeline_phase': 'Before'}, content_type='application/json')
        self.assertEqual(r.status_code, 201)
        article = GuidanceContent.objects.get(title='Sandbags')
        self.client.delete(f'/api/guidance/{article.id}/')
        self.assertEqual(set(AuditLog.objects.filter(target_id=str(article.id)).values_list('action', flat=True)),
                         {'ADD_GUIDANCE', 'UNPUBLISH_GUIDANCE'})

    def test_passwords_are_at_least_twelve_characters(self):
        with self.assertRaises(ValidationError):
            validate_password('Tr1cky-Pass')  # 11
        validate_password('Tr1cky-Pass!')  # 12
