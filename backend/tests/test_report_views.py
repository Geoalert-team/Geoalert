"""
The Reports view's two reports on the shared filters: Hazard Summary
(the archive) and Response Status (zones and alerts).
"""
from datetime import datetime
from zoneinfo import ZoneInfo

from django.test import TestCase
from rest_framework.test import APIClient

from apps.admin_dashboard.models import AuditLog
from apps.hazards.models import HazardAlert, HazardZone
from apps.history.models import HistoricalRecord
from tests.fire_setup import FireSetupMixin

NO_DATA = 'Insufficient data available for selected criteria. Please expand the date range or modify filters.'


def manila(y, m, d, hour=12):
    return datetime(y, m, d, hour, tzinfo=ZoneInfo('Asia/Manila'))


class ReportViewTests(FireSetupMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.client.force_login(self.officer)

    def record(self, when, hazard, barangay, **kw):
        return HistoricalRecord.objects.create(barangay=barangay, hazard_type=hazard, severity_level='Green',
                                               occurred_at=when, **kw)

    def zone_at(self, purok, when, **kw):
        zone = self.zone(purok, **kw)
        HazardZone.objects.filter(pk=zone.pk).update(activated_at=when)
        alert = HazardAlert.objects.create(hazard_zone=zone, issued_by=self.officer, hazard_type=zone.hazard_type,
                                           severity=zone.severity)
        HazardAlert.objects.filter(pk=alert.pk).update(created_at=when)
        return zone

    def summary(self, **params):
        res = self.client.get('/api/reports/hazard-summary/', params)
        self.assertEqual(res.status_code, 200, res.content)
        return res.json()

    def response_status(self, **params):
        res = self.client.get('/api/reports/response-status/', params)
        self.assertEqual(res.status_code, 200, res.content)
        return res.json()

    # Hazard Summary

    def test_summary_counts_with_aggregates(self):
        self.record(manila(2026, 3, 1), self.fire, self.home, total_casualties=2)
        self.record(manila(2026, 3, 2), self.fire, self.home)
        self.record(manila(2026, 3, 3), self.flood, self.home, total_casualties=1)
        self.record(manila(2026, 3, 4), self.fire, self.next)
        data = self.summary()
        self.assertEqual(data['total_occurrences'], 4)
        self.assertEqual(data['total_casualties'], 3)
        self.assertEqual(data['breakdown_by_type'], [{'hazard_type__name': 'Fire', 'count': 3},
                                                     {'hazard_type__name': 'Flood', 'count': 1}])
        self.assertEqual(data['affected_barangays'], [{'barangay__name': 'Home', 'count': 3},
                                                      {'barangay__name': 'Next door', 'count': 1}])

    def test_displaced_is_null_when_never_recorded(self):
        self.record(manila(2026, 3, 1), self.fire, self.home)
        self.assertIsNone(self.summary()['total_displaced'])
        self.record(manila(2026, 3, 2), self.fire, self.home, total_displaced=5)
        self.assertEqual(self.summary()['total_displaced'], 5)

    def test_summary_barangay_rule(self):
        self.record(manila(2026, 3, 1), self.fire, self.next).puroks.add(self.near)  # in Home's purok
        self.record(manila(2026, 3, 2), self.fire, self.next)
        self.assertEqual(self.summary(barangay=self.home.id)['total_occurrences'], 1)

    def test_date_to_covers_the_whole_day(self):
        self.record(manila(2026, 3, 10, hour=18), self.fire, self.home)
        self.assertEqual(self.summary(date_from='2026-03-10', date_to='2026-03-10')['total_occurrences'], 1)
        self.assertEqual(self.summary(date_to='2026-03-10T23:59:59')['total_occurrences'], 1)

    def test_summary_audit_names_the_filters(self):
        self.record(manila(2026, 3, 1), self.fire, self.home)
        self.summary(barangay=self.home.id, hazard_type=self.fire.id, date_from='2026-01-01')
        log = AuditLog.objects.get(action='GENERATE_REPORT')
        self.assertEqual(log.details, 'Hazard Summary — 1 record(s). '
                                      'date_from=2026-01-01 date_to=- barangay=Home hazard_type=Fire')

    def test_no_data_answer_unchanged(self):
        self.assertEqual(self.summary(date_from='2020-01-01', date_to='2020-01-31'), {'error': NO_DATA})
        self.assertEqual(self.response_status(date_from='2020-01-01', date_to='2020-01-31'), {'error': NO_DATA})

    # Response Status

    def test_response_status_filters_hazard_type(self):
        self.zone_at(self.near, manila(2026, 3, 1))
        self.zone_at(self.far, manila(2026, 3, 2))
        self.zone_at(self.near, manila(2026, 3, 3), hazard_type=self.flood)
        data = self.response_status(hazard_type=self.flood.id)
        self.assertEqual((data['total_hazard_events'], data['total_alerts_issued']), (1, 1))
        self.assertEqual(self.response_status()['total_alerts_issued'], 3)

    def test_response_status_alerts_follow_barangay(self):
        self.zone_at(self.near, manila(2026, 3, 1))
        self.zone_at(self.far, manila(2026, 3, 2))
        data = self.response_status(barangay=self.home.id)
        self.assertEqual((data['total_hazard_events'], data['total_alerts_issued']), (1, 1))

    def test_response_status_counts_withdrawn_separately(self):
        self.zone_at(self.near, manila(2026, 3, 1))
        self.zone_at(self.near, manila(2026, 3, 2), status='Retracted')
        data = self.response_status()
        self.assertEqual((data['active_hazards'], data['retracted_hazards'], data['total_hazard_events']), (1, 1, 1))

    # Both

    def test_bad_dates_are_a_400(self):
        for url in ('/api/reports/hazard-summary/', '/api/reports/response-status/'):
            with self.subTest(url=url):
                res = self.client.get(url, {'date_from': 'last week'})
                self.assertEqual(res.status_code, 400)
                self.assertEqual(res.json(), {'error': 'date_from must be a date like 2026-01-31.'})
                res = self.client.get(url, {'date_from': '2026-02-01', 'date_to': '2026-01-01'})
                self.assertEqual(res.json(), {'error': 'The start date is after the end date.'})

    def test_printed_analytics_says_trend_analysis(self):
        res = self.client.post('/api/reports/printed/', {'report': 'analytics', 'criteria': 'x', 'via': 'csv'},
                               format='json')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(AuditLog.objects.get(action='EXPORT_REPORT').details, 'Trend Analysis downloaded as CSV. x')
