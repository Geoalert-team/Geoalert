"""
Reports & Analytics' Summary (GET /api/reports/summary/), the operations
figures' zones by status, and the Prediction models export key.
"""
from datetime import datetime
from zoneinfo import ZoneInfo

from django.test import TestCase
from rest_framework.test import APIClient

from apps.admin_dashboard.models import AuditLog
from apps.hazards.models import HazardAlert, HazardZone
from apps.history.models import HistoricalRecord
from tests.fire_setup import FireSetupMixin


def manila(y, m, d):
    return datetime(y, m, d, 12, tzinfo=ZoneInfo('Asia/Manila'))


class SummaryTests(FireSetupMixin, TestCase):
    def setUp(self):
        super().setUp()
        rec = HistoricalRecord.objects.create
        self.burnt = rec(barangay=self.home, hazard_type=self.fire, severity_level='Red', occurred_at=manila(2026, 3, 1),
                         injured_civ_male=2, fatal_civ_female=1, damage_cost=50000, structures_affected=3,
                         property_category='Residential', alarm_level='1st Alarm')
        self.burnt.puroks.add(self.near)
        rec(barangay=self.next, hazard_type=self.fire, severity_level='Green', occurred_at=manila(2026, 4, 1))
        rec(barangay=None, hazard_type=self.fire, severity_level='Green', occurred_at=manila(2026, 5, 1))
        rec(barangay=self.home, hazard_type=self.flood, severity_level='Orange', occurred_at=manila(2026, 7, 1),
            injured=1, fatalities=2, families_affected=10, persons_affected=40, hazard_subcategory='FLASH FLOOD',
            cause='Heavy rain')
        self.client = APIClient()
        self.client.force_login(self.officer)

    def summary(self, **params):
        res = self.client.get('/api/reports/summary/', params)
        self.assertEqual(res.status_code, 200, res.content)
        return res.json()

    def test_impact_counts_fire_cells_and_flood_fields_with_how_many_recorded(self):
        impact = self.summary()['impact']
        self.assertEqual(impact['deaths'], {'value': 3, 'recorded_on': 2, 'of': 4})
        self.assertEqual(impact['injured'], {'value': 3, 'recorded_on': 2, 'of': 4})
        self.assertEqual(impact['families_affected'], {'value': 10, 'recorded_on': 1, 'of': 4})
        self.assertEqual(impact['persons_affected'], {'value': 40, 'recorded_on': 1, 'of': 4})
        self.assertEqual(impact['structures_affected'], {'value': 3, 'recorded_on': 1, 'of': 4})
        self.assertEqual(impact['damage_cost'], {'value': 50000.0, 'recorded_on': 1, 'of': 4})

    def test_casualties_the_bfp_gave_only_as_a_total(self):
        # Column T of the BFP log: everyone hurt or killed, kept when the split cells are blank or fewer
        HistoricalRecord.objects.create(barangay=self.home, hazard_type=self.fire, severity_level='Green',
                                        occurred_at=manila(2026, 6, 1), total_casualties=4)
        HistoricalRecord.objects.filter(pk=self.burnt.pk).update(total_casualties=5)  # cells say 3
        data = self.summary()
        self.assertEqual(data['impact']['unsplit_casualties'], {'value': 6, 'recorded_on': 2, 'of': 5})
        self.assertEqual(data['impact']['deaths']['value'], 3)  # unchanged: the split figures only
        rows = {r['key']: (r['count'], r['of']) for r in data['completeness']}
        self.assertEqual(rows['casualties'], (3, 5))

    def test_nothing_recorded_is_null_not_zero(self):
        data = self.summary(barangay=self.next.id)
        self.assertEqual(data['events'], 1)
        self.assertEqual(data['impact']['deaths'], {'value': None, 'recorded_on': 0, 'of': 1})
        self.assertIsNone(data['displaced'])

    def test_breakdowns(self):
        data = self.summary()
        hazards = {r['hazard']: r for r in data['by_hazard']}
        self.assertEqual((hazards['Fire']['events'], hazards['Fire']['deaths'], hazards['Fire']['damage_cost']),
                         (3, 1, 50000.0))
        self.assertEqual((hazards['Flood']['deaths'], hazards['Flood']['families_affected']), (2, 10))
        self.assertIsNone(hazards['Flood']['damage_cost'])
        self.assertEqual([(r['name'], r['events']) for r in data['by_barangay']],
                         [('Home', 2), ('Next door', 1), ('Unspecified', 1)])
        self.assertEqual(data['by_purok'], [])  # only with one barangay picked
        self.assertEqual(data['severity'], [{'severity': 'Red', 'count': 1}, {'severity': 'Orange', 'count': 1},
                                            {'severity': 'Green', 'count': 2}])

    def test_purok_breakdown_for_one_barangay(self):
        self.assertEqual(self.summary(barangay=self.home.id)['by_purok'],
                         [{'id': self.near.id, 'name': 'Purok Near', 'events': 1}])

    def test_hazard_details_follow_the_scope(self):
        everything = self.summary()
        self.assertEqual(everything['fire']['property_category'], [{'label': 'Residential', 'count': 1}])
        self.assertEqual(everything['fire']['alarm_level'], [{'label': '1st Alarm', 'count': 1}])
        self.assertEqual(everything['flood_landslide']['subcategory'], [{'label': 'FLASH FLOOD', 'count': 1}])
        floods = self.summary(hazard_type=self.flood.id)
        self.assertIsNone(floods['fire'])
        self.assertEqual(floods['flood_landslide']['cause'], [{'label': 'Heavy rain', 'count': 1}])

    def test_completeness(self):
        rows = {r['key']: (r['count'], r['of']) for r in self.summary()['completeness']}
        self.assertEqual(rows['barangay'], (3, 4))
        self.assertEqual(rows['purok'], (1, 4))
        self.assertEqual(rows['damage'], (1, 3))  # fires only
        self.assertEqual(rows['families'], (1, 1))  # floods and landslides only

    def test_holdings_ignore_the_filters(self):
        held = self.summary(date_from='2020-01-01', date_to='2020-12-31')['holdings']
        self.assertEqual([(a['hazard'], a['records']) for a in held['archive']], [('Fire', 3), ('Flood', 1)])
        self.assertEqual(held['barangays'], 2)
        self.assertEqual(held['puroks'], 2)

    def test_permission_audit_and_bad_filter(self):
        self.summary()
        self.assertTrue(AuditLog.objects.get(action='GENERATE_REPORT').details.startswith('Hazard Summary — 4 record(s).'))
        self.assertEqual(self.client.get('/api/reports/summary/', {'hazard_type': 'x'}).json(),
                         {'error': 'hazard_type must be an id.'})
        self.assertEqual(APIClient().get('/api/reports/summary/').status_code, 403)

    def test_operations_count_zones_by_status(self):
        for status in ('Active', 'Resolved', 'Resolved', 'Retracted'):
            zone = self.zone(self.near, status=status)
            HazardZone.objects.filter(pk=zone.pk).update(activated_at=manila(2026, 3, 2))
        res = self.client.get('/api/reports/analytics/', {'date_from': '2026-01-01', 'date_to': '2026-12-31'})
        self.assertEqual(res.json()['zones_by_status'], {'Active': 1, 'Resolved': 2, 'Archived': 0, 'Retracted': 1})

    def test_models_export_is_logged(self):
        res = self.client.post('/api/reports/printed/', {'report': 'models', 'criteria': '', 'via': 'pdf'},
                               format='json')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(AuditLog.objects.get(action='EXPORT_REPORT').details, 'Prediction models saved as PDF.')
