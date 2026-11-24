from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from django.test import SimpleTestCase, TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.hazards.models import HazardAlert, HazardZone
from apps.history.models import HistoricalRecord
from apps.reports.analytics import (
    barangay_activity, median_minutes, month_starts, months_between, share,
)
from apps.reports.models import IncidentReport
from tests.fire_setup import FireSetupMixin
from utils.system_settings import SETTINGS, validate


class MonthStartsTests(SimpleTestCase):
    def test_counts_back_across_the_new_year(self):
        self.assertEqual(
            month_starts(date(2026, 2, 17), 4),
            [date(2025, 11, 1), date(2025, 12, 1), date(2026, 1, 1), date(2026, 2, 1)],
        )

    def test_window_of_one_is_this_month(self):
        self.assertEqual(month_starts(date(2026, 10, 19), 1), [date(2026, 10, 1)])


class MedianTests(SimpleTestCase):
    def test_median_in_minutes(self):
        t = datetime(2026, 10, 1, 8, 0)
        pairs = [(t, t + timedelta(minutes=10)), (t, t + timedelta(minutes=30)), (t, t + timedelta(hours=5))]
        self.assertEqual(median_minutes(pairs), 30.0)

    def test_ignores_missing_and_backwards_pairs(self):
        t = datetime(2026, 10, 1, 8, 0)
        self.assertEqual(median_minutes([(t, None), (t, t - timedelta(minutes=5))]), None)

    def test_share_of_nothing_is_none(self):
        self.assertIsNone(share(3, 0))
        self.assertEqual(share(1, 4), 0.25)


class SettingsValidationTests(SimpleTestCase):
    def test_every_default_is_within_its_own_range(self):
        for key, (dflt, lo, hi, *_rest) in SETTINGS.items():
            self.assertEqual(validate(key, dflt), dflt, key)
            self.assertTrue(lo <= dflt <= hi, key)

    def test_rejects_out_of_range_fractions_and_words(self):
        for bad in ('500', '2.5', 'ten', ''):
            with self.assertRaises(ValueError):
                validate('auth.lock_minutes', bad)

    def test_rejects_unknown_key(self):
        with self.assertRaises(ValueError):
            validate('debug.everything', 1)


class BarangayActivityTests(SimpleTestCase):
    def test_joins_both_lists_with_zero_for_the_missing_side(self):
        rows = barangay_activity(
            [{'barangay__name': 'Tabunok', 'count': 4}],
            [{'barangay__name': 'Bulacao', 'count': 9}, {'barangay__name': 'Tabunok', 'count': 2}],
        )
        self.assertEqual(rows, [
            {'barangay': 'Tabunok', 'zones': 4, 'incidents': 2},
            {'barangay': 'Bulacao', 'zones': 0, 'incidents': 9},
        ])

    def test_orders_by_zones_then_incidents_then_name(self):
        rows = barangay_activity(
            [{'barangay__name': n, 'count': 1} for n in ('Pooc', 'Linao', 'Dumlog')],
            [{'barangay__name': 'Pooc', 'count': 3}],
        )
        self.assertEqual([r['barangay'] for r in rows], ['Pooc', 'Dumlog', 'Linao'])

    def test_missing_name_reads_unspecified(self):
        self.assertEqual(barangay_activity([{'barangay__name': None, 'count': 2}], [])[0]['barangay'], 'Unspecified')


class MonthsBetweenTests(SimpleTestCase):
    def test_months_between_spans_the_new_year(self):
        self.assertEqual(months_between(date(2025, 11, 15), date(2026, 2, 3)),
                         [date(2025, 11, 1), date(2025, 12, 1), date(2026, 1, 1), date(2026, 2, 1)])

    def test_one_month(self):
        self.assertEqual(months_between(date(2026, 3, 9), date(2026, 3, 20)), [date(2026, 3, 1)])


def manila(y, m, d):
    return datetime(y, m, d, 12, tzinfo=ZoneInfo('Asia/Manila'))


class AnalyticsRangeTests(FireSetupMixin, TestCase):
    """GET /api/reports/analytics/ with dates and a barangay (Trend Analysis' Response section)."""

    def setUp(self):
        super().setUp()
        self.z_home = self.activated(self.zone(self.near), manila(2026, 3, 10))
        self.z_next = self.activated(self.zone(self.far), manila(2026, 6, 10))
        self.z_old = self.activated(self.zone(self.near), manila(2025, 6, 1))
        for zone in (self.z_home, self.z_next, self.z_old):
            alert = HazardAlert.objects.create(hazard_zone=zone, issued_by=self.officer,
                                               hazard_type=zone.hazard_type, severity=zone.severity)
            HazardAlert.objects.filter(pk=alert.pk).update(created_at=zone.activated_at)
        mine = self.report(self.near)
        theirs = IncidentReport.objects.create(submitted_by=self.neighbour, barangay=self.next,
                                               hazard_type=self.fire, description='Smoke')
        IncidentReport.objects.filter(pk=mine.pk).update(submitted_at=manila(2026, 3, 11))
        IncidentReport.objects.filter(pk=theirs.pk).update(submitted_at=manila(2026, 6, 11))
        linked = HistoricalRecord.objects.create(barangay=self.next, hazard_type=self.fire, severity_level='Green',
                                                 occurred_at=manila(2026, 4, 1))
        linked.puroks.add(self.near)  # filed next door, in Home's purok
        HistoricalRecord.objects.create(barangay=self.next, hazard_type=self.fire, severity_level='Green',
                                        occurred_at=manila(2026, 4, 2))
        self.client = APIClient()
        self.client.force_login(self.officer)

    @staticmethod
    def activated(zone, when):
        HazardZone.objects.filter(pk=zone.pk).update(activated_at=when)
        return HazardZone.objects.get(pk=zone.pk)

    def get(self, **params):
        res = self.client.get('/api/reports/analytics/', params)
        self.assertEqual(res.status_code, 200, res.content)
        return res.json()

    def test_date_range_replaces_the_window(self):
        data = self.get(date_from='2026-01-01', date_to='2026-06-30', months=3)
        self.assertEqual(data['kpis']['zones_published'], 2)
        self.assertEqual(data['kpis']['alerts_issued'], 2)
        self.assertEqual([m['month'] for m in data['monthly']],
                         ['2026-01', '2026-02', '2026-03', '2026-04', '2026-05', '2026-06'])
        self.assertEqual(data['months'], 6)

    def test_date_to_is_inclusive(self):
        self.assertEqual(self.get(date_from='2026-03-10', date_to='2026-03-10')['kpis']['zones_published'], 1)

    def test_barangay_filters_every_count(self):
        data = self.get(date_from='2026-01-01', date_to='2026-12-31', barangay=self.home.id)
        k = data['kpis']
        self.assertEqual((k['zones_published'], k['alerts_issued'], k['incidents_submitted']), (1, 1, 1))
        self.assertEqual(k['recorded_events'], 1)  # only the record in Home's purok
        self.assertEqual([r['barangay'] for r in data['barangays']], ['Home'])

    def test_active_now_ignores_dates(self):
        self.assertEqual(self.get(date_from='2020-01-01', date_to='2020-01-31')['kpis']['active_zones_now'], 3)
        self.assertEqual(self.get(date_from='2020-01-01', date_to='2020-01-31',
                                  barangay=self.home.id)['kpis']['active_zones_now'], 2)

    def test_filters_in_answer(self):
        """Exports describe the figures from the answer itself, so it names its filters as the others do."""
        data = self.get(date_from='2026-01-01', date_to='2026-06-30', barangay=self.home.id, hazard_type=self.fire.id)
        self.assertEqual(data['filters'], {'hazard_type': {'id': self.fire.id, 'name': 'Fire'},
                                           'barangay': {'id': self.home.id, 'name': 'Home'}})
        self.assertEqual(self.get()['filters'], {'hazard_type': None, 'barangay': None})

    def test_range_and_first_record_in_response(self):
        data = self.get(date_from='2026-01-01', date_to='2026-06-30')
        self.assertEqual(data['range'], {'from': '2026-01-01', 'to': '2026-06-30'})
        self.assertEqual(data['first_record'], '2025-06-01')

    def test_no_start_date_begins_at_the_first_record(self):
        data = self.get(date_to='2026-06-30')
        self.assertEqual(data['range'], {'from': '2025-06-01', 'to': '2026-06-30'})
        self.assertEqual(data['kpis']['zones_published'], 3)

    def test_bad_dates_are_a_400(self):
        res = self.client.get('/api/reports/analytics/', {'date_from': '2026-02-30'})
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json(), {'error': 'date_from must be a date like 2026-01-31.'})
        res = self.client.get('/api/reports/analytics/', {'barangay': '99999'})
        self.assertEqual(res.json(), {'error': 'Unknown barangay.'})

    def test_months_still_works(self):
        data = self.get(months=3)
        self.assertEqual(len(data['monthly']), 3)
        self.assertEqual(data['range']['to'], timezone.localdate().isoformat())
        self.assertEqual(data['range']['from'], data['since'])
