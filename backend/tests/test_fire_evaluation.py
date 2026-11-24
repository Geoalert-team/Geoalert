"""
Levels, scores, comparison baselines and intervals for the fire risk model
(plan Task B3, spec sections 5 and 6) on hand-made predictions.
"""
import math

import numpy as np
from django.test import SimpleTestCase

from apps.history import fire_evaluation as fe
from apps.history import fire_training as ft
from tests.test_fire_training import MONTHS, SMALL, feature_table, noise_labels


def ranked(n_rows, fire_ranks):
    """p falling from 0.5 by row; y = 1 on the rows (0-based ranks) given."""
    p = np.linspace(0.5, 0.001, n_rows)
    y = np.zeros(n_rows, int)
    y[list(fire_ranks)] = 1
    return p, y


class CutoffTests(SimpleTestCase):
    def test_orange_catches_80_percent(self):
        p, y = ranked(100, [0, 3, 7, 12, 20, 33, 41, 58, 77, 95])
        c = fe.cutoffs(p, y)
        self.assertGreaterEqual(int(y[p >= c.orange].sum()), 8)
        higher = p[p > c.orange].min()
        self.assertLess(int(y[p >= higher].sum()), 8)

    def test_red_is_twice_the_city_rate(self):
        p, y = ranked(400, list(range(0, 24, 2)) + [150, 200, 250, 300, 330, 360, 380, 399])  # 12 near the top
        c = fe.cutoffs(p, y)
        self.assertIsNotNone(c.red)
        self.assertGreater(c.red, c.orange)
        top = p >= c.red
        self.assertGreaterEqual(y[top].mean(), 2 * y.mean())
        self.assertGreaterEqual(int(y[top].sum()), 10)
        lower = p[p < c.red].max()  # the next cut down fails one of the two tests
        rows = p >= lower
        self.assertFalse(y[rows].mean() >= 2 * y.mean() and y[rows].sum() >= 10 and lower >= c.orange)

    def test_red_empty_when_too_few_fires(self):
        p, y = ranked(200, range(0, 18, 2))  # 9 fires
        c = fe.cutoffs(p, y)
        self.assertIsNone(c.red)
        self.assertIn('fewer than 10 fires', c.red_reason.lower())

    def test_red_is_never_below_orange(self):
        p, y = ranked(60, list(range(0, 60, 3)))  # 20 fires spread evenly: rate is flat
        c = fe.cutoffs(p, y)
        self.assertTrue(c.red is None or c.red >= c.orange)

    def test_level_boundaries(self):
        c = fe.Cutoffs(orange=0.02, red=0.05, red_reason=None)
        self.assertEqual(fe.level(0.02, c), 'Orange')
        self.assertEqual(fe.level(0.05, c), 'Red')
        self.assertEqual(fe.level(0.0199, c), 'Green')
        self.assertEqual(fe.level(0.9, fe.Cutoffs(orange=0.02, red=None, red_reason='none')), 'Orange')

    def test_level_table(self):
        p = np.array([0.9, 0.8, 0.5, 0.4, 0.1, 0.05])
        y = np.array([1, 0, 1, 0, 1, 0])
        table = {r['level']: r for r in fe.level_table(y, p, fe.Cutoffs(orange=0.4, red=0.8, red_reason=None))}
        self.assertEqual([table[k]['rows'] for k in ('Red', 'Orange', 'Green')], [2, 2, 2])
        self.assertEqual([table[k]['fires'] for k in ('Red', 'Orange', 'Green')], [1, 1, 1])
        self.assertAlmostEqual(table['Orange']['recall'], 2 / 3)  # Orange or higher
        self.assertAlmostEqual(table['Orange']['precision'], 2 / 4)
        self.assertAlmostEqual(table['Red']['share'], 2 / 6)
        self.assertIn('kappa', table['Red'])


class ScoreTests(SimpleTestCase):
    def test_scores_handle_one_class(self):
        y = np.zeros(40, int)
        s = fe.scores(y, np.full(40, 0.05), np.repeat([1, 2, 3, 4], 10))
        self.assertIsNone(s['roc_auc']['value'])
        self.assertIsNone(s['pr_auc']['value'])
        self.assertTrue(math.isfinite(s['brier']['value']))
        self.assertTrue(math.isfinite(s['log_loss']['value']))

    def test_scores_have_intervals(self):
        rng = np.random.default_rng(0)
        p = rng.uniform(0.01, 0.4, 600)
        y = (rng.random(600) < p).astype(int)
        s = fe.scores(y, p, np.repeat(np.arange(12), 50), orange=0.1)
        self.assertEqual(set(s), {'log_loss', 'brier', 'roc_auc', 'pr_auc', 'calibration_intercept',
                                  'calibration_slope', 'top10_share', 'top20_share', 'kappa_at_orange'})
        for name, v in s.items():
            self.assertTrue(math.isfinite(v['value']) and v['low'] <= v['high'], name)
        self.assertGreater(s['roc_auc']['value'], 0.6)
        self.assertAlmostEqual(s['calibration_slope']['value'], 1.0, delta=0.4)

    def test_top_shares(self):
        p = np.arange(10, 0, -1) / 20
        y = np.array([1, 0, 1, 0, 0, 0, 0, 0, 0, 1])
        s = fe.scores(y, p, np.arange(10))
        self.assertAlmostEqual(s['top10_share']['value'], 1 / 3)  # the top row of ten
        self.assertAlmostEqual(s['top20_share']['value'], 1 / 3)
        self.assertIsNone(s['kappa_at_orange']['value'])  # no cut-off given


class ReliabilityTests(SimpleTestCase):
    def test_reliability_by_tenths(self):
        p = np.repeat(np.arange(1, 11) / 20, 10)  # ten rows at each of ten chances
        y = np.zeros(100, int)
        y[-10:-5] = 1  # half of the top tenth
        rows = fe.reliability(y, p)
        self.assertEqual(len(rows), 10)
        self.assertEqual([r['rows'] for r in rows], [10] * 10)
        self.assertAlmostEqual(rows[-1]['mean_chance'], 0.5)
        self.assertAlmostEqual(rows[-1]['fire_share'], 0.5)
        self.assertEqual(rows[0]['fire_share'], 0.0)


class BaselineTests(SimpleTestCase):
    def test_baseline_names_say_comparison(self):
        table = feature_table()
        train = ft.build_panel(table, noise_labels(), MONTHS[:24])
        test = ft.build_panel(table, noise_labels(), MONTHS[24:])
        buildings = {r['purok_id']: r['buildings_in_area'] for r in table.rows}
        base = fe.comparison_baselines(train, test, buildings)
        self.assertEqual(set(base), {'comparison_same_everywhere', 'comparison_buildings',
                                     'comparison_historical_frequency'})
        for name, p in base.items():
            self.assertTrue(name.startswith('comparison_'))
            self.assertEqual(len(p), len(test.y))
            self.assertTrue(((p > 0) & (p < 1)).all(), name)
        self.assertTrue(np.allclose(base['comparison_same_everywhere'], train.y.mean()))

    def test_historical_frequency_follows_each_area(self):
        table = feature_table()
        labels = {(100, m): 1 for m in MONTHS[:24]}  # area 100 burned every training month
        train = ft.build_panel(table, labels, MONTHS[:24])
        test = ft.build_panel(table, {}, MONTHS[24:])
        base = fe.comparison_baselines(train, test, {r['purok_id']: 1.0 for r in table.rows})
        freq = base['comparison_historical_frequency']
        self.assertGreater(freq[test.purok == 100].min(), freq[test.purok == 101].max())


class RateTests(SimpleTestCase):
    def test_barangay_rate_sum(self):
        rates = fe.barangay_rates({1: 0.1, 2: 0.2, 3: 0.5}, {1: 7, 2: 7, 3: 8})
        self.assertAlmostEqual(rates[7], -math.log(0.9) - math.log(0.8))
        self.assertAlmostEqual(rates[8], -math.log(0.5))

    def test_limited_data_rule(self):
        self.assertTrue(fe.limited_data('low', .1, .1))
        self.assertTrue(fe.limited_data('high', .01, .04))  # 4 times
        self.assertFalse(fe.limited_data('high', .01, .02))


class IntervalTests(SimpleTestCase):
    def test_calendar_rows(self):
        panel = ft.build_panel(feature_table(), {}, MONTHS)
        ids, X = fe.calendar_rows(panel)
        self.assertEqual(list(ids), list(range(100, 112)))
        self.assertEqual(X.shape, (12 * 12, panel.X.shape[1]))
        march = X[2]  # area 100, March
        self.assertAlmostEqual(march[-2], math.sin(2 * math.pi * 3 / 12))
        self.assertTrue(np.array_equal(X[12, :-2], panel.X[1, :-2]))  # area 101's inputs

    def test_intervals_per_area_and_month(self):
        panel = ft.build_panel(feature_table(), noise_labels(0.1), MONTHS)
        choice = ft.choose(panel, {'logistic_regression': SMALL['logistic_regression']})
        out = fe.intervals(panel, choice, reps=8)
        self.assertEqual(sorted(out), list(range(100, 112)))
        for months in out.values():
            self.assertEqual(len(months), 12)
            self.assertTrue(all(0 < low <= high < 1 for low, high in months))
        self.assertEqual(out, fe.intervals(panel, choice, reps=8))  # seeded
