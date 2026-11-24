"""The statistics behind Trend Analysis' key changes and places."""
from django.test import SimpleTestCase

from apps.reports.stats import (
    change_vs_earlier, mann_kendall, recurrence, sens_slope, trend_verdict, unusual,
)


class MannKendallTests(SimpleTestCase):
    def test_steady_rise_is_significant(self):
        r = mann_kendall([1, 2, 3, 4, 5, 6])
        self.assertEqual(r['s'], 15)
        self.assertLess(r['p'], 0.05)
        self.assertGreater(r['z'], 0)

    def test_ties_count_zero(self):
        self.assertEqual(mann_kendall([1, 1, 2, 2, 3, 3])['s'], 12)

    def test_flat_series_has_no_trend(self):
        r = mann_kendall([5, 5, 5, 5, 5])
        self.assertEqual((r['s'], r['z'], r['p']), (0, 0.0, 1.0))

    def test_too_short(self):
        self.assertEqual(mann_kendall([4, 9]), {'s': 0, 'z': 0.0, 'p': 1.0})


class SlopeAndVerdictTests(SimpleTestCase):
    def test_sens_slope_is_the_median_pairwise_slope(self):
        self.assertEqual(sens_slope([1, 3, 5]), 2.0)
        self.assertEqual(sens_slope([7]), 0.0)

    def test_verdicts(self):
        self.assertEqual(trend_verdict([3, 1, 4]), 'too_few_years')
        self.assertEqual(trend_verdict([1, 2, 3, 4, 5, 6]), 'increasing')
        self.assertEqual(trend_verdict([9, 8, 6, 5, 3, 1]), 'decreasing')
        self.assertEqual(trend_verdict([5, 5, 5, 5, 5]), 'no_clear_trend')
        self.assertEqual(trend_verdict([4, 7, 3, 8, 2]), 'no_clear_trend')


class UnusualTests(SimpleTestCase):
    def test_above_two_standard_deviations(self):
        self.assertTrue(unusual(14, [5, 6, 7]))
        self.assertFalse(unusual(8, [5, 6, 7]))

    def test_needs_three_baseline_years_and_three_events(self):
        self.assertFalse(unusual(14, [5, 6]))
        self.assertFalse(unusual(2, [0, 0, 0]))
        self.assertTrue(unusual(3, [0, 0, 0]))


class RecurrenceTests(SimpleTestCase):
    def test_classes(self):
        self.assertEqual(recurrence([1, 2]), 'too_few_years')
        self.assertEqual(recurrence([1, 2, 1]), 'every_year')
        self.assertEqual(recurrence([1, 0, 2, 1]), 'most_years')
        self.assertEqual(recurrence([1, 0, 0, 0]), 'some_years')
        self.assertEqual(recurrence([0, 0, 0, 3]), 'latest_only')
        self.assertEqual(recurrence([0, 0, 0]), 'none')


class ChangeTests(SimpleTestCase):
    def test_latest_against_earlier_average(self):
        self.assertEqual(change_vs_earlier([4, 6, 10]), {'latest': 10, 'earlier_mean': 5.0, 'pct': 100})
        self.assertEqual(change_vs_earlier([0, 0, 3]), {'latest': 3, 'earlier_mean': 0.0, 'pct': None})
        self.assertEqual(change_vs_earlier([3]), {'latest': 3, 'earlier_mean': None, 'pct': None})
        self.assertEqual(change_vs_earlier([]), {'latest': None, 'earlier_mean': None, 'pct': None})
