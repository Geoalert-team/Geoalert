"""
The filters every Reports & Analytics endpoint shares: period, hazard type
and barangay, read once, in Manila time, with the History page's barangay rule.
"""
from datetime import date, datetime, timezone as dt_timezone

from django.contrib.gis.geos import MultiPolygon
from django.test import TestCase

from apps.barangays.models import Barangay, Purok
from apps.hazards.models import HazardType
from apps.history.models import HistoricalRecord
from apps.reports.filters import (
    FilterError, ReportFilters, criteria_text, day_end, day_start, filter_records, parse_report_filters,
)
from tests.fire_setup import box


class ReportFiltersTests(TestCase):
    def setUp(self):
        self.home = Barangay.objects.create(name='Home', municipality='Talisay',
                                            boundary=MultiPolygon(box(-500, -500, 500, 500), srid=4326))
        self.next = Barangay.objects.create(name='Next door', municipality='Talisay',
                                            boundary=MultiPolygon(box(500, -500, 1500, 500), srid=4326))
        self.near = Purok.objects.create(barangay=self.home, name='Purok Near', kind='purok', source='estimated',
                                         boundary=MultiPolygon(box(-100, -100, 100, 100), srid=4326))
        self.flood = HazardType.objects.create(name='Flood', logo_class='flood')

    def record(self, when, barangay=None, **kw):
        return HistoricalRecord.objects.create(barangay=barangay or self.home, hazard_type=self.flood,
                                               severity_level='Green', occurred_at=when, **kw)

    def test_empty_params_mean_no_filters(self):
        self.assertEqual(parse_report_filters({}), ReportFilters(None, None, None, None))

    def test_values_are_read(self):
        f = parse_report_filters({'date_from': '2026-01-01', 'date_to': '2026-06-30',
                                  'hazard_type': str(self.flood.id), 'barangay': str(self.home.id)})
        self.assertEqual(f, ReportFilters(date(2026, 1, 1), date(2026, 6, 30), self.flood, self.home))

    def test_date_to_with_a_time_is_read_as_its_day(self):
        self.assertEqual(parse_report_filters({'date_to': '2026-01-31T23:59:59'}).date_to, date(2026, 1, 31))

    def test_bad_values_raise_sentences(self):
        cases = [
            ({'date_from': '2026-13-01'}, 'date_from must be a date like 2026-01-31.'),
            ({'date_to': 'soon'}, 'date_to must be a date like 2026-01-31.'),
            ({'date_from': '2026-02-01', 'date_to': '2026-01-01'}, 'The start date is after the end date.'),
            ({'hazard_type': 'x'}, 'hazard_type must be an id.'),
            ({'hazard_type': '0'}, 'hazard_type must be an id.'),
            ({'hazard_type': '3.5'}, 'hazard_type must be an id.'),
            ({'hazard_type': '²'}, 'hazard_type must be an id.'),
            ({'hazard_type': '99999'}, 'Unknown hazard type.'),
            ({'barangay': '-3'}, 'barangay must be an id.'),
            ({'barangay': '99999'}, 'Unknown barangay.'),
        ]
        for params, message in cases:
            with self.subTest(params=params):
                with self.assertRaises(FilterError) as caught:
                    parse_report_filters(params)
                self.assertEqual(str(caught.exception), message)

    def test_dates_are_bounded(self):
        for params in ({'date_from': '0202-01-01'}, {'date_to': '2101-01-01'}, {'date_to': '9999-12-31'}):
            with self.subTest(params=params):
                with self.assertRaises(FilterError) as caught:
                    parse_report_filters(params)
                self.assertEqual(str(caught.exception), 'Dates must be between 1900 and 2100.')

    def test_future_start_without_end(self):
        with self.assertRaises(FilterError) as caught:
            parse_report_filters({'date_from': '2099-01-01'})
        self.assertEqual(str(caught.exception), 'The start date is in the future.')
        # with an end date it is only a range, checked as before
        self.assertEqual(parse_report_filters({'date_from': '2099-01-01', 'date_to': '2099-02-01'}).date_from,
                         date(2099, 1, 1))

    def test_day_bounds_are_manila(self):
        self.assertEqual(day_start(date(2026, 1, 1)).isoformat(), '2026-01-01T00:00:00+08:00')
        self.assertEqual(day_end(date(2026, 1, 1)).isoformat(), '2026-01-01T23:59:59.999999+08:00')

    def test_new_year_in_manila(self):
        rec = self.record(datetime(2025, 12, 31, 16, 30, tzinfo=dt_timezone.utc))  # 00:30 on 1 Jan in Manila
        records = HistoricalRecord.objects.all()
        self.assertIn(rec, filter_records(records, ReportFilters(date(2026, 1, 1), None, None, None)))
        self.assertNotIn(rec, filter_records(records, ReportFilters(None, date(2025, 12, 31), None, None)))

    def test_date_to_includes_the_whole_day(self):
        rec = self.record(datetime(2026, 1, 31, 15, 59, tzinfo=dt_timezone.utc))  # 23:59 Manila
        self.assertIn(rec, filter_records(HistoricalRecord.objects.all(),
                                          ReportFilters(None, date(2026, 1, 31), None, None)))

    def test_barangay_rule_counts_linked_puroks(self):
        rec = self.record(datetime(2026, 3, 1, tzinfo=dt_timezone.utc), barangay=self.next)
        rec.puroks.add(self.near)  # filed under Next door, but in one of Home's puroks
        other = self.record(datetime(2026, 3, 2, tzinfo=dt_timezone.utc), barangay=self.next)
        picked = filter_records(HistoricalRecord.objects.all(), ReportFilters(None, None, None, self.home))
        self.assertEqual(list(picked), [rec])
        self.assertNotIn(other, picked)

    def test_hazard_filter(self):
        fire = HazardType.objects.create(name='Fire', logo_class='fire')
        flood = self.record(datetime(2026, 3, 1, tzinfo=dt_timezone.utc))
        HistoricalRecord.objects.create(barangay=self.home, hazard_type=fire, severity_level='Green',
                                        occurred_at=datetime(2026, 3, 1, tzinfo=dt_timezone.utc))
        picked = filter_records(HistoricalRecord.objects.all(), ReportFilters(None, None, self.flood, None))
        self.assertEqual(list(picked), [flood])

    def test_criteria_text(self):
        self.assertEqual(criteria_text(ReportFilters(date(2026, 1, 1), date(2026, 6, 30), self.flood, self.home)),
                         'date_from=2026-01-01 date_to=2026-06-30 barangay=Home hazard_type=Flood')
        self.assertEqual(criteria_text(ReportFilters(None, None, None, None)),
                         'date_from=- date_to=- barangay=all hazard_type=all')
