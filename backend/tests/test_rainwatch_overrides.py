"""DRRMO overrides: set a minimum colour by hand, list, cancel."""
from datetime import timedelta
from unittest import mock

from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import Role, User
from apps.rainwatch import assess
from apps.rainwatch.models import RainWatchOverride

URL = '/api/rain-watch/overrides/'


def make_user(role_name, email):
    role, _ = Role.objects.get_or_create(name=role_name)
    return User.objects.create_user(email=email, password='pw-12345-xyz', role=role, full_name=f'{role_name} Person')


def body(**over):
    data = {'hazard': 'Flood', 'level': 'Orange',
            'ends_at': (timezone.now() + timedelta(hours=24)).isoformat(),
            'note': 'PAGASA advisory 5pm'}
    data.update(over)
    return data


class OverrideTests(TestCase):
    def setUp(self):
        cache.clear()
        self.drrmo = make_user('DRRMO_Officer', 'drrmo@example.com')

    def client_for(self, user):
        c = APIClient()
        if user:
            c.force_authenticate(user)
        return c

    def test_drrmo_and_admin_can_create(self):
        admin = make_user('System_Admin', 'admin@example.com')
        for user in (self.drrmo, admin):
            before = cache.get(assess.VERSION_KEY, 0)
            r = self.client_for(user).post(URL, body(), format='json')
            self.assertEqual(r.status_code, 201, r.content)
            self.assertEqual(cache.get(assess.VERSION_KEY), before + 1)
        self.assertEqual(RainWatchOverride.objects.count(), 2)
        row = RainWatchOverride.objects.first()
        self.assertEqual(row.created_by, self.drrmo)
        self.assertEqual(r.json()['created_by_name'], 'System_Admin Person')

    def test_barangay_bfp_and_anonymous_get_403_or_401(self):
        for role in ('Barangay_Official', 'BFP_Personnel'):
            u = make_user(role, f'{role}@example.com')
            self.assertIn(self.client_for(u).post(URL, body(), format='json').status_code, (401, 403))
            self.assertIn(self.client_for(u).get(URL).status_code, (401, 403))
        self.assertIn(self.client_for(None).post(URL, body(), format='json').status_code, (401, 403))
        self.assertIn(self.client_for(None).get(URL).status_code, (401, 403))
        self.assertEqual(RainWatchOverride.objects.count(), 0)

    def test_validation(self):
        now = timezone.now()
        bad = [
            body(ends_at=(now - timedelta(hours=1)).isoformat()),
            body(ends_at=(now + timedelta(hours=73)).isoformat()),
            body(note='   '),
            body(note='x' * 301),
            body(level='Green'),
            body(hazard='Fire'),
        ]
        c = self.client_for(self.drrmo)
        for data in bad:
            self.assertEqual(c.post(URL, data, format='json').status_code, 400, data)
        self.assertEqual(RainWatchOverride.objects.count(), 0)
        self.assertEqual(c.post(URL, body(note='x' * 300), format='json').status_code, 201)

    def test_list_active_and_last_20(self):
        c = self.client_for(self.drrmo)
        now = timezone.now()
        for i in range(25):
            RainWatchOverride.objects.create(
                hazard='Both', level='Red', starts_at=now - timedelta(days=5),
                ends_at=now - timedelta(days=4, hours=i), note='old', created_by=self.drrmo)
        active = RainWatchOverride.objects.create(
            hazard='Flood', level='Yellow', ends_at=now + timedelta(hours=5), note='now', created_by=self.drrmo)
        # the active one was made long ago, so it is outside the last 20 but still listed
        RainWatchOverride.objects.filter(pk=active.pk).update(created_at=now - timedelta(days=30))
        rows = c.get(URL).json()
        self.assertEqual(len(rows), 21)
        self.assertEqual(rows[0]['id'], active.id)
        self.assertEqual(set(rows[0]), {'id', 'hazard', 'level', 'starts_at', 'ends_at', 'note',
                                        'created_by_name', 'cancelled_at'})

    def test_cancel_and_double_cancel_409(self):
        c = self.client_for(self.drrmo)
        oid = c.post(URL, body(), format='json').json()['id']
        before = cache.get(assess.VERSION_KEY)
        r = c.post(f'{URL}{oid}/cancel/')
        self.assertEqual(r.status_code, 200, r.content)
        self.assertIsNotNone(r.json()['cancelled_at'])
        self.assertEqual(cache.get(assess.VERSION_KEY), before + 1)
        row = RainWatchOverride.objects.get(pk=oid)
        self.assertEqual(row.cancelled_by, self.drrmo)
        self.assertEqual(c.post(f'{URL}{oid}/cancel/').status_code, 409)
        self.assertEqual(c.post(f'{URL}999999/cancel/').status_code, 404)

    def test_a_failing_cache_does_not_fail_a_saved_override(self):
        # The row is saved before the cache is told; a 500 then would make an officer submit twice
        broken = mock.Mock()
        broken.incr.side_effect = ConnectionError('cache down')
        broken.set.side_effect = ConnectionError('cache down')
        c = self.client_for(self.drrmo)
        with mock.patch('apps.rainwatch.assess.cache', broken),                 self.assertLogs('apps.rainwatch.assess', 'WARNING') as logs:
            r = c.post(URL, body(), format='json')
            self.assertEqual(r.status_code, 201, r.content)
            self.assertEqual(c.post(f"{URL}{r.json()['id']}/cancel/").status_code, 200)
        self.assertEqual(RainWatchOverride.objects.count(), 1)
        self.assertIsNotNone(RainWatchOverride.objects.get().cancelled_at)
        self.assertTrue(all('cache down' in line for line in logs.output))

    def test_active_overrides_excludes_cancelled_and_ended(self):
        now = timezone.now()

        def make(**kw):
            d = dict(hazard='Flood', level='Red', starts_at=now - timedelta(hours=1),
                     ends_at=now + timedelta(hours=1), note='n', created_by=self.drrmo)
            d.update(kw)
            return RainWatchOverride.objects.create(**d)

        ok = make()
        make(cancelled_at=now, cancelled_by=self.drrmo)
        make(ends_at=now - timedelta(minutes=1))
        make(ends_at=now)  # ends exactly now: not active
        make(starts_at=now + timedelta(minutes=5))
        self.assertEqual(assess.active_overrides(now), [ok])
