from datetime import date, datetime, timedelta

from django.test import SimpleTestCase

from apps.reports.analytics import (
    barangay_activity, hazard_type_param, median_minutes, month_starts, share,
)
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


class HazardTypeParamTests(SimpleTestCase):
    def test_reads_a_positive_id(self):
        self.assertEqual(hazard_type_param('3'), 3)

    def test_anything_else_means_all_types(self):
        for raw in (None, '', 'abc', '0', '-2', '3.5', '²'):
            self.assertIsNone(hazard_type_param(raw), raw)


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
