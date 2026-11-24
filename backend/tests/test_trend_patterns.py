"""
Trend Analysis' key changes (GET /api/reports/trends/patterns/) and places
(GET /api/reports/trends/places/). Years are counted back from today so the
tests do not go stale.
"""
from datetime import datetime
from zoneinfo import ZoneInfo

from django.contrib.gis.geos import MultiPolygon
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import Role, User
from apps.admin_dashboard.models import AuditLog
from apps.barangays.models import Barangay
from apps.hazards.models import HazardType
from apps.history.models import HistoricalRecord
from tests.fire_setup import box

MANILA = ZoneInfo('Asia/Manila')
LAST = timezone.localdate().year - 1  # the last complete year
FIRE_YEARS = list(range(LAST - 5, LAST + 1))  # six complete years


def at(y, m, d=15):
    return datetime(y, m, d, 12, tzinfo=MANILA)


class TrendPatternsTests(TestCase):
    def setUp(self):
        role = Role.objects.create(name='DRRMO_Officer')
        self.officer = User.objects.create_user(email='o@test.ph', password='x', full_name='Officer', role=role)
        self.home = Barangay.objects.create(name='Home', municipality='Talisay',
                                            boundary=MultiPolygon(box(-500, -500, 500, 500), srid=4326))
        self.next = Barangay.objects.create(name='Next door', municipality='Talisay',
                                            boundary=MultiPolygon(box(500, -500, 1500, 500), srid=4326))
        self.nowhere = Barangay.objects.create(name='No outline', municipality='Talisay')
        self.fire = HazardType.objects.create(name='Fire', logo_class='fire')
        self.flood = HazardType.objects.create(name='Flood', logo_class='flood')
        # Fire: 1, 2, 3, 4, 5, 6 events in June of six complete years, all in Home
        for i, y in enumerate(FIRE_YEARS):
            for _ in range(i + 1):
                self.record(at(y, 6), self.fire, self.home)
        # and an unusual March in the last year
        for _ in range(8):
            self.record(at(LAST, 3), self.fire, self.home)
        # Flood: three complete years, 2, 0, 1 events, next door
        self.record(at(LAST - 2, 8), self.flood, self.next)
        self.record(at(LAST - 2, 9), self.flood, self.next)
        self.record(at(LAST, 8), self.flood, self.next)
        self.client = APIClient()
        self.client.force_login(self.officer)

    def record(self, when, hazard, barangay):
        return HistoricalRecord.objects.create(barangay=barangay, hazard_type=hazard, severity_level='Green',
                                               occurred_at=when)

    def patterns(self, **params):
        res = self.client.get('/api/reports/trends/patterns/', params)
        self.assertEqual(res.status_code, 200, res.content)
        return res.json()

    def places(self, **params):
        res = self.client.get('/api/reports/trends/places/', params)
        self.assertEqual(res.status_code, 200, res.content)
        return res.json()

    def hazard(self, data, name):
        return next(h for h in data['hazards'] if h['hazard'] == name)

    def test_rising_fire_is_increasing(self):
        fire = self.hazard(self.patterns(), 'Fire')
        self.assertEqual([y['year'] for y in fire['years']], FIRE_YEARS)
        self.assertEqual([y['count'] for y in fire['years']], [1, 2, 3, 4, 5, 14])
        self.assertEqual(fire['complete_years'], 6)
        self.assertEqual(fire['verdict'], 'increasing')
        self.assertGreater(fire['slope'], 0)
        self.assertIn('rising', fire['sentence'])

    def test_three_years_are_too_few_for_a_direction(self):
        flood = self.hazard(self.patterns(), 'Flood')
        self.assertEqual([y['count'] for y in flood['years']], [2, 0, 1])
        self.assertEqual(flood['verdict'], 'too_few_years')
        for word in ('rising', 'falling', 'increasing', 'decreasing'):
            self.assertNotIn(word, flood['sentence'])
        self.assertIn('too few', flood['sentence'])
        self.assertIn(f'{LAST - 1}', flood['sentence'])  # the empty year is named as a possible gap
        self.assertIn('gap', flood['sentence'])

    def test_years_after_the_last_record_are_not_a_fall(self):
        slide = HazardType.objects.create(name='Landslide', logo_class='landslide')
        for i, n in enumerate([8, 9, 7, 8]):  # then nothing for two years
            for _ in range(n):
                self.record(at(LAST - 5 + i, 7), slide, self.home)
        row = self.hazard(self.patterns(), 'Landslide')
        self.assertNotIn(row['verdict'], ('increasing', 'decreasing'))
        self.assertEqual(row['quiet_since'], LAST - 2)
        self.assertIn(f'No records since {LAST - 2}', row['sentence'])

    def test_a_year_with_no_records_inside_the_series_names_no_direction(self):
        storm = HazardType.objects.create(name='Storm', logo_class='storm')
        for i, n in enumerate([3, 0, 4, 5, 6, 7]):
            for _ in range(n):
                self.record(at(LAST - 5 + i, 9), storm, self.home)
        row = self.hazard(self.patterns(), 'Storm')
        self.assertEqual(row['verdict'], 'gaps')
        for word in ('rising', 'falling'):
            self.assertNotIn(word, row['sentence'])

    def test_unusual_month(self):
        months = self.patterns()['unusual_months']
        march = [m for m in months if m['hazard'] == 'Fire' and m['month'] == 3]
        self.assertEqual(len(march), 1)
        self.assertEqual((march[0]['year'], march[0]['count'], march[0]['baseline_mean']), (LAST, 8, 0.0))
        # The Marches after the first record (June, six years ago), this year's included since it has ended
        self.assertEqual(march[0]['baseline_years'], 5)
        self.assertFalse([m for m in months if m['month'] == 6])  # a steady rise is not an anomaly

    def test_hazard_filter(self):
        data = self.patterns(hazard_type=self.flood.id)
        self.assertEqual([h['hazard'] for h in data['hazards']], ['Flood'])

    def test_places_list_every_barangay_with_density(self):
        data = self.places()
        rows = {r['name']: r for r in data['barangays']}
        self.assertEqual(set(rows), {'Home', 'Next door', 'No outline'})
        self.assertEqual(rows['Home']['total'], 29)
        self.assertAlmostEqual(rows['Home']['area_km2'], 1.0, delta=0.05)
        self.assertAlmostEqual(rows['Home']['per_km2'], 29, delta=1.5)
        self.assertEqual(rows['Home']['recurrence'], 'every_year')
        self.assertEqual(rows['No outline']['total'], 0)
        self.assertIsNone(rows['No outline']['area_km2'])
        self.assertIsNone(rows['No outline']['per_km2'])
        self.assertEqual(rows['No outline']['recurrence'], 'none')
        self.assertEqual(data['barangays'][0]['name'], 'Home')  # most events first

    def test_places_follow_hazard_and_mark_the_selected_barangay(self):
        data = self.places(hazard_type=self.flood.id, barangay=self.next.id)
        rows = {r['name']: r for r in data['barangays']}
        self.assertEqual(rows['Next door']['total'], 3)
        self.assertEqual(rows['Home']['total'], 0)
        self.assertEqual(data['selected'], self.next.id)

    def test_bad_filters_and_permissions(self):
        for url in ('/api/reports/trends/patterns/', '/api/reports/trends/places/'):
            self.assertEqual(self.client.get(url, {'barangay': '99999'}).json(), {'error': 'Unknown barangay.'})
            self.assertEqual(APIClient().get(url).status_code, 403)

    def test_loads_are_audited(self):
        self.patterns()
        self.places()
        details = sorted(AuditLog.objects.filter(action='GENERATE_REPORT').values_list('details', flat=True))
        self.assertEqual(len(details), 2)
        self.assertTrue(details[0].startswith('Trend patterns — '))
        self.assertTrue(details[1].startswith('Trend places — '))
