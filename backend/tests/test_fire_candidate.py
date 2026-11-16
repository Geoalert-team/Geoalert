"""
Fire's contender (spec Section 4): the pooled Poisson model with building
exposure, the statistics that compare it with today's model one month ahead,
and the rule that decides which one the forecast uses.
"""
import math
from datetime import date, datetime, timezone
from unittest import mock

import numpy as np
from django.test import SimpleTestCase

from apps.history import fire_candidate as fc
from apps.history import model_forecast as mf

TZ = timezone.utc
TODAY = date(2026, 11, 5)
MONTHS = [(y, m) for y in range(2023, 2027) for m in range(1, 13) if (y, m) <= (2026, 9)]


def city(seed=5):
    """Fires across eight barangays, more where more buildings stand, with a dry-season peak around March."""
    rng = np.random.default_rng(seed)
    places = [{'id': i, 'name': f'B{i}', 'area_km2': 1.0 + i / 4, 'puroks': 8 + i} for i in range(1, 9)]
    buildings = {p['id']: 200 * p['id'] for p in places}
    events = []
    for y, m in MONTHS:
        season = 1 + 0.5 * math.cos(2 * math.pi * (m - 3) / 12)
        for p in places:
            for _ in range(rng.poisson(0.0006 * buildings[p['id']] * season)):
                events.append({'barangay_id': p['id'], 'barangay': p['name'], 'hazard': 'Fire', 'severity': 'Orange',
                               'is_sample': False, 'when': datetime(y, m, 10, tzinfo=TZ)})
    return events, places, buildings


class ExposureModelTests(SimpleTestCase):
    def test_offset_trick_matches_a_true_offset(self):
        rng = np.random.default_rng(0)
        exposure = rng.integers(50, 3000, 200).astype(float)
        y = rng.poisson(exposure * 0.002)
        # intercept only (one all-zero column, no penalty to speak of): with a log offset the fit is
        # total fires / total building-months, the rate per building
        expected = fc.fit_with_exposure(np.zeros((200, 1)), y, exposure, 1e-12)
        self.assertAlmostEqual(expected(np.zeros((1, 1)), [1.0])[0] / (y.sum() / exposure.sum()), 1, places=6)
        # one dummy: each group's own total over its own building-months, as a true offset gives
        group = (np.arange(200) % 2).astype(float)[:, None]
        expected = fc.fit_with_exposure(group, y, exposure, 1e-12)
        for g in (0, 1):
            inside = group[:, 0] == g
            true_rate = y[inside].sum() / exposure[inside].sum()
            self.assertAlmostEqual(expected(np.array([[g]], float), [1.0])[0] / true_rate, 1, places=4)

    def test_scaling_buildings_scales_rates_exactly(self):
        events, places, buildings = city()
        table = fc.exposure_rates_table(events, places, buildings, today=TODAY)
        # eight times the buildings everywhere: the same fires expected, so each building's rate is
        # exactly an eighth (a power of two, so the floats are exact too)
        eight = fc.exposure_rates_table(events, places, {b: 8 * n for b, n in buildings.items()}, today=TODAY)
        self.assertEqual(eight, table)
        # and the expected fires follow each barangay's buildings
        rows = np.zeros((2, len(places) + 4))
        rows[:, 0] = 1
        y = np.array([3, 5])
        expected = fc.fit_with_exposure(rows, y, np.array([100.0, 200.0]), 0.01)
        self.assertAlmostEqual(expected(rows[:1], [300.0])[0], 3 * expected(rows[:1], [100.0])[0], places=12)
        # a barangay-month gets a figure for every place and month
        self.assertEqual(set(table), {p['id'] for p in places})
        self.assertTrue(all(len(r) == 12 and min(r) > 0 for r in table.values()))

    def test_penalty_is_chosen_without_the_test_months(self):
        events, places, buildings = city()
        until = date(2025, 7, 1)
        cut = mf._index(until)
        fitted, scored = [], []
        real_table, real_observed = fc._table, fc._observed

        def table(counts, places, buildings, months, penalty):
            fitted.append(months)
            return real_table(counts, places, buildings, months, penalty)

        def observed(counts, places, months):
            scored.append(months)
            return real_observed(counts, places, months)

        with mock.patch.object(fc, '_table', side_effect=table), \
                mock.patch.object(fc, '_observed', side_effect=observed):
            penalty = fc.choose_penalty(events, places, buildings, until, TODAY)
        self.assertIn(penalty, fc.PENALTIES)
        self.assertEqual(len(fitted), len(fc.PENALTIES))
        # each penalty is fitted on the training months but the last six and scored on those six; no count read
        # reaches the month `until` starts
        self.assertTrue(all(m < cut for months in fitted + scored for m in months))
        inner = (mf._index(date(2023, 1, 1)), cut - fc.INNER_MONTHS)
        self.assertEqual({(f.start, f.stop) for f in fitted}, {inner})
        self.assertEqual({(s.start, s.stop) for s in scored}, {inner, (cut - fc.INNER_MONTHS, cut)})
        # what came after `until` changes nothing, the table included
        before = [e for e in events if e['when'].date() < until]
        self.assertEqual(fc.choose_penalty(before, places, buildings, until, TODAY), penalty)
        self.assertEqual(fc.exposure_rates_table(events, places, buildings, until=until, today=TODAY),
                         fc.exposure_rates_table(before, places, buildings, until=until, today=TODAY))
        # six training months or fewer leave nothing to fit on: no penalty, never a failed fit
        self.assertIsNone(fc.choose_penalty(events, places, buildings, date(2023, 7, 1), TODAY))
        self.assertIsNone(fc.choose_penalty([], places, buildings, None, TODAY))
        self.assertIn(fc.choose_penalty(events, places, buildings, date(2023, 8, 1), TODAY), fc.PENALTIES)


class StatisticsTests(SimpleTestCase):
    def test_dm_hln_on_a_known_series(self):
        # d = 1..5: mean 3, autocovariance at lag 0 = 2, DM = 3 / sqrt(2 / 5); HLN (h = 1) multiplies by
        # sqrt((5 + 1 - 2) / 5), so the statistic is 3 * sqrt(2); t with 4 degrees of freedom, two-sided
        out = fc.dm_hln(np.array([1.0, 2, 3, 4, 5]))
        self.assertAlmostEqual(out['statistic'], 3 * math.sqrt(2), places=12)
        self.assertAlmostEqual(out['p'], 0.0132356, places=6)
        self.assertAlmostEqual(fc.dm_hln(-np.array([1.0, 2, 3, 4, 5]))['statistic'], -3 * math.sqrt(2), places=12)
        # a series with no spread has no test, never an infinite statistic
        self.assertEqual(fc.dm_hln(np.array([0.5, 0.5, 0.5])), {'statistic': None, 'p': None})

    def test_coverage_and_pit_on_known_counts(self):
        # Poisson(1): the 10th percentile is 0 and the 90th is 2, so 3 falls outside
        y, ones = np.array([0, 1, 2, 3]), np.ones(4)
        self.assertEqual(fc.coverage80(y, ones), 0.75)
        # Pearson: (1 + 0 + 1 + 4) / 1 over 4 rows less 1 parameter
        self.assertEqual(fc.dispersion(y, ones, 1), 2.0)
        # randomised PIT: a 0 at rate ln 10 lands in [0, P(0) = 0.1), the first bin; a 3 at rate 0.01 in
        # [P(2), P(3)], just under 1, the last
        y = np.array([0] * 5 + [3] * 5)
        rates = np.array([math.log(10)] * 5 + [0.01] * 5)
        self.assertEqual(fc.pit_histogram(y, rates), [5, 0, 0, 0, 0, 0, 0, 0, 0, 5])
        self.assertEqual(fc.pit_histogram(y, rates, bins=5), [5, 0, 0, 0, 5])
        # the same seed gives the same histogram
        spread = np.random.default_rng(3).poisson(2.0, 400)
        self.assertEqual(fc.pit_histogram(spread, np.full(400, 2.0)), fc.pit_histogram(spread, np.full(400, 2.0)))
        self.assertEqual(sum(fc.pit_histogram(spread, np.full(400, 2.0))), 400)

    def test_morans_i_finds_a_clustered_pattern(self):
        def line(n):
            return {i: {j for j in (i - 1, i + 1) if 1 <= j <= n} for i in range(1, n + 1)}

        # 4 barangays in a line, [3, 3, -3, -3]: I = (4 / 6) * (18 / 36) = 1/3, clustered
        four = fc.morans_i({1: 3, 2: 3, 3: -3, 4: -3}, line(4))
        self.assertAlmostEqual(four['i'], 1 / 3, places=12)
        # with four values only 6 arrangements exist and 2 are this clustered, so no permutation test can
        # reach 0.05 here; a line of 8 has 2 such arrangements in 70
        self.assertGreater(four['p'], 0.2)
        eight = fc.morans_i({i: 3 if i <= 4 else -3 for i in range(1, 9)}, line(8))
        self.assertGreater(eight['i'], 0)
        self.assertLess(eight['p'], fc.MORAN_FLAG_P)
        # alternating values are the opposite of clustered
        alternating = fc.morans_i({i: (-1) ** i for i in range(1, 9)}, line(8))
        self.assertLess(alternating['i'], 0)
        self.assertGreater(alternating['p'], 0.5)
        # seed 0 every time; no neighbours or no spread: no figure
        self.assertEqual(fc.morans_i({i: 3 if i <= 4 else -3 for i in range(1, 9)}, line(8)), eight)
        self.assertEqual(fc.morans_i({1: 3, 2: -3}, {}), {'i': None, 'p': None})
        self.assertEqual(fc.morans_i({1: 2, 2: 2}, line(2)), {'i': None, 'p': None})


class RuleTests(SimpleTestCase):
    def test_rule_keeps_current_unless_the_interval_is_below_zero(self):
        adopted = fc.verdict({'mean': -0.02, 'low': -0.03, 'high': -0.01})
        self.assertTrue(adopted['adopted'])
        self.assertEqual(len(adopted['reasons']), 1)
        for mean, low, high in ((-0.02, -0.05, 0.01),     # better on average, but the interval reaches zero
                                (-0.02, -0.05, 0.0),      # touching zero is not wholly below it
                                (0.0, -0.01, 0.01),
                                (0.01, 0.002, 0.02)):     # worse
            with self.subTest(mean=mean, low=low, high=high):
                kept = fc.verdict({'mean': mean, 'low': low, 'high': high})
                self.assertFalse(kept['adopted'])
                self.assertIn('Tested, not better', kept['reasons'][0])
        # a small difference reads as a plain decimal on the card, never in e-notation such as 5.1e-05
        small = fc.verdict({'mean': 5.1e-05, 'low': -2.893e-05, 'high': 0.00012345})
        self.assertEqual(small['reasons'], ['Tested, not better: mean log-score difference 0.000051 per '
                                            'barangay-month, 95% interval -0.0000289 to 0.000123, not wholly '
                                            'below zero.'])

    def test_untestable_without_buildings_keeps_current_with_a_reason(self):
        events, places, buildings = city()
        # this record's last fire is in August 2026: the window is the nine months up to it
        self.assertEqual(max(e['when'] for e in events).date(), date(2026, 8, 10))
        cases = {
            'no file': (None, [fc.NO_BUILDINGS]),
            'one missing': ({b: n for b, n in buildings.items() if b != 3},
                            [fc.MISSING_BUILDINGS.format('B3')]),
            'a zero count': ({**buildings, 5: 0, 7: 0}, [fc.MISSING_BUILDINGS.format('B5, B7')]),
        }
        for name, (counts, reasons) in cases.items():
            with self.subTest(name), mock.patch.object(fc, 'exposure_rates_table') as never:
                out = fc.compare(events, places, counts, {}, TODAY)
                never.assert_not_called()
                self.assertEqual(out['in_use'], fc.F0_NAME)
                self.assertEqual(out['verdict'], {'adopted': False, 'reasons': reasons})
                self.assertIsNone(out['models'][fc.F1_NAME])
                self.assertIsNone(out['difference'])
                self.assertIsNone(out['secondary'])
                # today's model is still scored, and its checks reported
                self.assertEqual(out['window'], {'start': '2025-12', 'end': '2026-08'})
                self.assertEqual(sum(out['models'][fc.F0_NAME]['pit']), len(places) * mf.TEST_MONTHS)
                self.assertGreater(out['dispersion'], 0)
        # too few records to test anything: nothing is fitted
        out = fc.compare(events[:30], places, buildings, {}, TODAY)
        self.assertEqual((out['in_use'], out['verdict']),
                         (fc.F0_NAME, {'adopted': False, 'reasons': [fc.TOO_FEW_TO_COMPARE]}))
        self.assertEqual(out['models'], {fc.F0_NAME: None, fc.F1_NAME: None})
