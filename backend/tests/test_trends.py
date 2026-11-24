"""
Trend Analysis' hazard history: GET /api/reports/trends/ counts the archive
by period, calendar month, severity and barangay, following every filter.
"""
from datetime import date, datetime, timezone as dt_timezone
from zoneinfo import ZoneInfo

from django.contrib.gis.geos import MultiPolygon
from django.test import SimpleTestCase, TestCase
from rest_framework.test import APIClient

from apps.accounts.models import Role, User
from apps.admin_dashboard.models import AuditLog
from apps.barangays.models import Barangay, Purok
from apps.hazards.models import HazardType
from apps.history.models import HistoricalRecord
from apps.reports.trends import buckets, pick_granularity, previous_window
from tests.fire_setup import box

MANILA = ZoneInfo('Asia/Manila')
URL = '/api/reports/trends/'


class TrendHelperTests(SimpleTestCase):
    def test_granularity_follows_the_range(self):
        self.assertEqual(pick_granularity(date(2025, 1, 1), date(2026, 12, 31)), 'month')
        self.assertEqual(pick_granularity(date(2024, 12, 1), date(2026, 12, 31)), 'quarter')  # 25 months
        self.assertEqual(pick_granularity(date(2021, 1, 1), date(2026, 12, 31)), 'quarter')
        self.assertEqual(pick_granularity(date(2015, 1, 1), date(2026, 12, 31)), 'year')

    def test_month_buckets_cross_the_new_year(self):
        out = buckets(date(2025, 11, 5), date(2026, 2, 1), 'month')
        self.assertEqual([k for k, _ in out], ['2025-11', '2025-12', '2026-01', '2026-02'])
        self.assertEqual(out[0][1], 'Nov 2025')

    def test_quarter_and_year_buckets(self):
        out = buckets(date(2025, 8, 1), date(2026, 1, 1), 'quarter')
        self.assertEqual([k for k, _ in out], ['2025-Q3', '2025-Q4', '2026-Q1'])
        self.assertEqual(out[0][1], 'Q3 2025')
        self.assertEqual(buckets(date(2024, 6, 1), date(2026, 1, 1), 'year'),
                         [('2024', '2024'), ('2025', '2025'), ('2026', '2026')])

    def test_previous_window_is_the_same_length_before(self):
        self.assertEqual(previous_window(date(2026, 1, 1), date(2026, 1, 31)), (date(2025, 12, 1), date(2025, 12, 31)))
        self.assertEqual(previous_window(date(2026, 1, 1), date(2026, 12, 31)), (date(2025, 1, 1), date(2025, 12, 31)))


def at(y, m, d, hour=12):
    return datetime(y, m, d, hour, tzinfo=MANILA)


class TrendsApiTests(TestCase):
    def setUp(self):
        officer = Role.objects.create(name='DRRMO_Officer')
        self.officer = User.objects.create_user(email='officer@test.ph', password='x', full_name='Officer',
                                                role=officer)
        self.home = Barangay.objects.create(name='Home', municipality='Talisay',
                                            boundary=MultiPolygon(box(-500, -500, 500, 500), srid=4326))
        self.next = Barangay.objects.create(name='Next door', municipality='Talisay',
                                            boundary=MultiPolygon(box(500, -500, 1500, 500), srid=4326))
        self.near = Purok.objects.create(barangay=self.home, name='Purok Near', kind='purok', source='estimated',
                                         boundary=MultiPolygon(box(-100, -100, 100, 100), srid=4326))
        self.fire = HazardType.objects.create(name='Fire', logo_class='fire')
        self.flood = HazardType.objects.create(name='Flood', logo_class='flood')
        rec = self.record
        rec(at(2026, 3, 10), self.fire, self.home, total_casualties=2)
        rec(at(2026, 3, 20), self.fire, self.home, severity='Red')
        rec(at(2026, 7, 5), self.flood, self.next, severity='Orange')
        rec(at(2026, 5, 1), self.fire, None)
        rec(at(2025, 8, 15), self.flood, self.home)
        rec(at(2026, 4, 1), self.fire, self.next).puroks.add(self.near)  # filed next door, in Home's purok
        self.client = APIClient()
        self.client.force_login(self.officer)

    def record(self, when, hazard, barangay, severity='Green', **kw):
        return HistoricalRecord.objects.create(barangay=barangay, hazard_type=hazard, severity_level=severity,
                                               occurred_at=when, **kw)

    def get(self, **params):
        return self.client.get(URL, params)

    def year_2026(self, **params):
        res = self.get(date_from='2026-01-01', date_to='2026-12-31', **params)
        self.assertEqual(res.status_code, 200, res.content)
        return res.json()

    def test_totals(self):
        data = self.year_2026()
        self.assertEqual(data['range'], {'from': '2026-01-01', 'to': '2026-12-31', 'granularity': 'month',
                                         'all_records': False})
        self.assertEqual(data['filters'], {'hazard_type': None, 'barangay': None})
        self.assertEqual(data['totals']['events'], 5)
        self.assertEqual(data['totals']['casualties'], 2)
        self.assertEqual(data['totals']['by_type'], [{'hazard': 'Fire', 'count': 4}, {'hazard': 'Flood', 'count': 1}])
        self.assertEqual(data['generated_by'], 'Officer')

    def test_series_is_zero_filled(self):
        series = self.year_2026()['series']
        self.assertEqual([s['period'] for s in series], [f'2026-{m:02d}' for m in range(1, 13)])
        self.assertEqual(series[0], {'period': '2026-01', 'label': 'Jan 2026', 'partial': False,
                                     'counts': {'Fire': 0, 'Flood': 0}, 'total': 0})
        self.assertEqual(series[2]['counts'], {'Fire': 2, 'Flood': 0})
        self.assertEqual(sum(s['total'] for s in series), 5)

    def test_granularity_can_be_chosen(self):
        series = self.year_2026(granularity='quarter')['series']
        self.assertEqual([(s['period'], s['total']) for s in series],
                         [('2026-Q1', 2), ('2026-Q2', 2), ('2026-Q3', 1), ('2026-Q4', 0)])

    def test_previous_period_counts_the_window_before(self):
        self.assertEqual(self.year_2026()['totals']['previous'], {
            'from': '2025-01-01', 'to': '2025-12-31', 'events': 1,
            'by_type': [{'hazard': 'Flood', 'count': 1}],
            'barangays': [{'id': self.home.id, 'name': 'Home', 'total': 1}],
        })

    def test_all_records_start_at_the_earliest(self):
        data = self.get(date_to='2026-12-31').json()
        self.assertEqual(data['range'], {'from': '2025-08-01', 'to': '2026-12-31', 'granularity': 'month',
                                         'all_records': True})
        self.assertIsNone(data['totals']['previous'])
        self.assertEqual(data['totals']['events'], 6)

    def test_month_of_year_has_twelve_rows(self):
        rows = self.year_2026()['month_of_year']
        self.assertEqual([r['month'] for r in rows], list(range(1, 13)))
        self.assertEqual(rows[0]['label'], 'Jan')
        self.assertEqual(rows[2], {'month': 3, 'label': 'Mar', 'counts': {'Fire': 2, 'Flood': 0}, 'total': 2})

    def test_severity_mix(self):
        self.assertEqual(self.year_2026()['severity'], [
            {'hazard': 'Fire', 'counts': {'Red': 1, 'Orange': 0, 'Green': 3}},
            {'hazard': 'Flood', 'counts': {'Red': 0, 'Orange': 1, 'Green': 0}},
        ])

    def test_shares_include_unspecified(self):
        rows = self.year_2026()['barangays']
        self.assertEqual([(r['name'], r['total']) for r in rows], [('Home', 2), ('Next door', 2), ('Unspecified', 1)])
        self.assertEqual(rows[0]['id'], self.home.id)
        self.assertIsNone(rows[2]['id'])
        self.assertEqual(rows[1]['counts'], {'Fire': 1, 'Flood': 1})
        self.assertAlmostEqual(sum(r['share'] for r in rows), 1.0, delta=0.002)

    def test_empty_range(self):
        res = self.get(date_from='2020-01-01', date_to='2020-03-31')
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data['totals']['events'], 0)
        self.assertEqual(data['totals']['casualties'], 0)
        self.assertEqual(data['totals']['by_type'], [])
        self.assertEqual(data['totals']['previous']['events'], 0)
        self.assertEqual([(s['period'], s['total']) for s in data['series']],
                         [('2020-01', 0), ('2020-02', 0), ('2020-03', 0)])
        self.assertEqual(data['barangays'], [])
        self.assertTrue(all(r['total'] == 0 for r in data['month_of_year']))

    def test_coverage_ignores_dates(self):
        data = self.get(date_from='2020-01-01', date_to='2020-03-31').json()
        self.assertEqual(data['coverage'], [
            {'hazard': 'Fire', 'first': '2026-03-10', 'last': '2026-05-01', 'records': 4},
            {'hazard': 'Flood', 'first': '2025-08-15', 'last': '2026-07-05', 'records': 2},
        ])

    def test_buckets_in_manila_time(self):
        self.record(datetime(2025, 12, 31, 16, 30, tzinfo=dt_timezone.utc), self.flood, self.home)  # 00:30 1 Jan
        data = self.get(date_from='2026-01-01', date_to='2026-01-31').json()
        self.assertEqual(data['series'], [{'period': '2026-01', 'label': 'Jan 2026', 'partial': False, 'counts': {'Flood': 1},
                                           'total': 1}])
        self.assertEqual(data['month_of_year'][0]['total'], 1)

    def test_hazard_and_barangay_filters(self):
        flood = self.year_2026(hazard_type=self.flood.id)
        self.assertEqual(flood['filters']['hazard_type'], {'id': self.flood.id, 'name': 'Flood'})
        self.assertEqual(flood['totals']['events'], 1)
        self.assertEqual(flood['series'][0]['counts'], {'Flood': 0})
        self.assertEqual([c['hazard'] for c in flood['coverage']], ['Flood'])

        home = self.year_2026(barangay=self.home.id)
        self.assertEqual(home['totals']['events'], 3)  # the purok-linked record counts for Home
        self.assertEqual(home['barangays'], [{'id': self.home.id, 'name': 'Home', 'total': 3,
                                              'counts': {'Fire': 3}, 'share': 1.0}])

    def test_filtered_hazard_with_no_records_still_has_a_series(self):
        landslide = HazardType.objects.create(name='Landslide', logo_class='landslide')
        data = self.year_2026(hazard_type=landslide.id)
        self.assertEqual(data['series'][0]['counts'], {'Landslide': 0})
        self.assertEqual(data['totals']['events'], 0)

    def test_bad_input_is_a_400_with_a_sentence(self):
        cases = [
            ({'date_from': '2026-02-01', 'date_to': '2026-01-01'}, 'The start date is after the end date.'),
            ({'barangay': '99999'}, 'Unknown barangay.'),
            ({'hazard_type': '99999'}, 'Unknown hazard type.'),
            ({'granularity': 'hour'}, 'granularity must be day, week, month, quarter or year.'),
            ({'date_to': 'tomorrow'}, 'date_to must be a date like 2026-01-31.'),
        ]
        for params, message in cases:
            with self.subTest(params=params):
                res = self.get(**params)
                self.assertEqual(res.status_code, 400)
                self.assertEqual(res.json(), {'error': message})

    def test_only_drrmo_and_admin(self):
        for name in ('Barangay_Personnel', 'BFP_Personnel'):
            user = User.objects.create_user(email=f'{name}@test.ph', password='x', full_name=name,
                                            role=Role.objects.get_or_create(name=name)[0],
                                            assigned_barangay=self.home)
            client = APIClient()
            client.force_login(user)
            self.assertEqual(client.get(URL).status_code, 403, name)
        self.assertEqual(APIClient().get(URL).status_code, 403)

    def test_partial_buckets(self):
        rows = self.get(date_from='2025-12-01', date_to='2026-11-24', granularity='year').json()['series']
        self.assertEqual([(r['period'], r['partial']) for r in rows], [('2025', True), ('2026', True)])
        whole = self.year_2026()['series']
        self.assertFalse(any(r['partial'] for r in whole))
        mid = self.get(date_from='2026-01-15', date_to='2026-03-31').json()['series']
        self.assertEqual([r['partial'] for r in mid], [True, False, False])

    def test_day_and_week_steps(self):
        weeks = self.get(date_from='2026-03-09', date_to='2026-03-22', granularity='week').json()['series']
        self.assertEqual([(r['period'], r['label'], r['total']) for r in weeks],
                         [('2026-W11', 'Week of 9 Mar 2026', 1), ('2026-W12', 'Week of 16 Mar 2026', 1)])
        days = self.get(date_from='2026-03-10', date_to='2026-03-12', granularity='day').json()['series']
        self.assertEqual([(r['period'], r['label'], r['total']) for r in days],
                         [('2026-03-10', '10 Mar 2026', 1), ('2026-03-11', '11 Mar 2026', 0),
                          ('2026-03-12', '12 Mar 2026', 0)])

    def test_too_many_periods(self):
        res = self.get(date_from='2026-01-01', date_to='2026-12-31', granularity='day')
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json(), {'error': 'Too many periods: choose a longer step.'})

    def test_calendar_and_weekday(self):
        data = self.year_2026()
        self.assertEqual(data['calendar'], [{'year': 2026, 'months': [0, 0, 2, 1, 1, 0, 1, 0, 0, 0, 0, 0], 'total': 5}])
        self.assertEqual([r['label'] for r in data['weekday']], ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'])
        self.assertEqual([r['total'] for r in data['weekday']], [0, 1, 1, 0, 2, 0, 1])

    def test_month_average_per_year(self):
        data = self.get(date_from='2025-01-01', date_to='2026-12-31').json()
        rows = {r['hazard']: r for r in data['month_average']}
        # Each month is divided by the years it was covered: from the hazard's first record month
        # (Flood: Aug 2025) to today, inside the range. July: 2026 only; August: 2025 and 2026.
        self.assertEqual(rows['Flood']['month_years'][6:8], [1, 2])
        self.assertEqual(rows['Flood']['months'][6:8], [1.0, 0.5])
        self.assertEqual(rows['Flood']['years'], 2)
        self.assertIsNone(rows['Fire']['months'][1])  # February: before the first fire, not "0 a year"
        self.assertEqual(rows['Fire']['months'][2], 2.0)

    def test_severity_by_year(self):
        self.assertEqual(self.year_2026()['severity_by_year'],
                         [{'year': 2026, 'counts': {'Red': 1, 'Orange': 1, 'Green': 3}}])

    def test_load_is_audited(self):
        self.year_2026(barangay=self.home.id)
        log = AuditLog.objects.get(action='GENERATE_REPORT')
        self.assertEqual(log.user, self.officer)
        self.assertEqual(log.details,
                         'Trend analysis — date_from=2026-01-01 date_to=2026-12-31 barangay=Home hazard_type=all')
