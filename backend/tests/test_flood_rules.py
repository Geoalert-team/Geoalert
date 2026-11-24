"""
The flood susceptibility model's metrics and fixed rules (plan Task 3): the
continuous Boyce index, the bootstrap gain, the choice and acceptance rules,
the Red / Orange cut-off walk, the uncertain mark and monitoring (spec 4-6).
"""
import numpy as np
from django.test import SimpleTestCase

from apps.history.flood_rules import (ORDER, Cutoffs, acceptance, boyce_gain, boyce_index, choose, classify,
                                      cutoff_walk, monitoring, uncertain_puroks)


class BoyceTests(SimpleTestCase):
    def test_boyce_positive_for_a_good_ranking_and_near_zero_for_noise(self):
        rng = np.random.default_rng(0)
        bg = rng.uniform(size=5000)
        self.assertGreater(boyce_index(rng.beta(5, 1, 300), bg), 0.8)
        self.assertLess(abs(boyce_index(rng.uniform(size=300), bg)), 0.5)

    def test_boyce_negative_when_floods_sit_where_the_score_is_low(self):
        rng = np.random.default_rng(1)
        self.assertLess(boyce_index(rng.beta(1, 5, 300), rng.uniform(size=5000)), -0.8)

    def test_gain_interval_is_above_zero_only_for_a_clearly_better_score(self):
        rng = np.random.default_rng(2)
        n_p, n_b = 200, 4000
        folds_p, folds_b = rng.integers(0, 5, n_p), rng.integers(0, 5, n_b)
        good_p, good_b = rng.beta(5, 1, n_p), rng.uniform(size=n_b)
        flat_p, flat_b = rng.uniform(size=n_p), rng.uniform(size=n_b)
        gain, low, high = boyce_gain(folds_p, folds_b, good_p, good_b, flat_p, flat_b, reps=200)
        self.assertGreater(low, 0)
        self.assertLessEqual(low, gain)
        self.assertLessEqual(gain, high)
        _, low, high = boyce_gain(folds_p, folds_b, good_p, good_b, good_p, good_b, reps=200)
        self.assertLessEqual(low, 0)
        self.assertGreaterEqual(high, 0)


class BoyceIntervalTests(SimpleTestCase):
    def test_interval_brackets_the_index(self):
        from apps.history.flood_rules import boyce_interval
        rng = np.random.default_rng(6)
        fp, fb = rng.integers(0, 5, 200), rng.integers(0, 5, 3000)
        value, low, high = boyce_interval(fp, fb, rng.beta(5, 1, 200), rng.uniform(size=3000), reps=100)
        self.assertLessEqual(low, value)
        self.assertLessEqual(value, high)
        self.assertGreater(low, 0.5)


class AucGainTests(SimpleTestCase):
    def test_auc_gain_is_stable_against_a_four_level_score(self):
        from apps.history.flood_rules import auc_gain, auc_score
        rng = np.random.default_rng(8)
        n_p, n_b = 150, 3000
        fp, fb = rng.integers(0, 5, n_p), rng.integers(0, 5, n_b)
        good_p, good_b = rng.beta(5, 1, n_p), rng.uniform(size=n_b)
        four_p, four_b = rng.integers(0, 4, n_p) / 3, rng.integers(0, 4, n_b) / 3  # no signal, ties
        gain, low, high = auc_gain(fp, fb, good_p, good_b, four_p, four_b, reps=200)
        self.assertGreater(low, 0.2)
        self.assertLessEqual(low, gain)
        self.assertLessEqual(gain, high)
        self.assertAlmostEqual(auc_score(np.array([1., 1.]), np.array([1., 0.])), 0.75)  # ties count half


class ChoiceTests(SimpleTestCase):
    def setUp(self):
        rng = np.random.default_rng(3)
        self.fp, self.fb = rng.integers(0, 5, 150), rng.integers(0, 5, 3000)
        self.p, self.b = rng.beta(3, 1, 150), rng.uniform(size=3000)

    def test_choice_keeps_the_simpler_model_unless_clearly_better(self):
        name, comparisons = choose({n: (self.p, self.b) for n in ORDER}, self.fp, self.fb)
        self.assertEqual(name, 'logistic_regression')
        self.assertEqual([c['candidate'] for c in comparisons], list(ORDER[1:]))
        self.assertFalse(any(c['adopted'] for c in comparisons))

    def test_a_clearly_better_complex_model_wins(self):
        rng = np.random.default_rng(4)
        flat = (rng.uniform(size=150), rng.uniform(size=3000))
        name, _ = choose({'logistic_regression': flat, 'xgboost': (self.p, self.b)}, self.fp, self.fb)
        self.assertEqual(name, 'xgboost')


class CutoffTests(SimpleTestCase):
    def test_cutoff_walk(self):
        c = cutoff_walk({1: .9, 2: .8, 3: .5, 4: .2, 5: .1}, {1: 5, 2: 1, 3: 3, 4: 1})
        self.assertEqual((c.red, c.orange), (.9, .5))  # 5 of 10 spots, then 9 of 10
        self.assertTrue(c.target_reached)
        self.assertEqual((c.red_recall, c.orange_recall), (.5, .9))

    def test_cutoff_walk_stops_at_the_last_distinct_score(self):
        c = cutoff_walk({1: .9, 2: 0., 3: 0.}, {1: 5, 2: 3, 3: 2})
        self.assertIsNone(c.orange)
        self.assertFalse(c.target_reached)
        self.assertEqual(c.red_recall, .5)
        self.assertEqual(c.orange_recall, .5)

    def test_spots_in_unassessed_puroks_still_count_against_recall(self):
        c = cutoff_walk({1: .9, 2: .5, 3: .1}, {1: 5, 2: 2, 99: 3})  # purok 99 is not assessed
        self.assertEqual(c.red, .9)
        self.assertEqual(c.orange, .5)  # the bottom score (.1) is never flagged
        self.assertEqual(c.orange_recall, .7)
        self.assertFalse(c.target_reached)

    def test_classify(self):
        c = Cutoffs(red=.9, orange=.5, red_recall=.5, orange_recall=.9, target_reached=True)
        self.assertEqual([classify(s, c) for s in (.95, .9, .6, .5, .2)], ['Red', 'Red', 'Orange', 'Orange', 'Green'])
        no_orange = Cutoffs(red=.9, orange=None, red_recall=.5, orange_recall=.5, target_reached=False)
        self.assertEqual([classify(s, no_orange) for s in (.95, .6)], ['Red', 'Green'])


class AcceptanceTests(SimpleTestCase):
    def test_acceptance_gates(self):
        ok, why = acceptance(0.01, ['Red', 'Orange', 'Green', 'Red'], 0.4)
        self.assertTrue(ok)
        self.assertEqual(why, [])
        ok, why = acceptance(-0.01, ['Red', None, 'Green', 'Red'], 0.6)
        self.assertFalse(ok)
        self.assertEqual(len(why), 3)

    def test_no_test_points_is_a_failed_gate(self):
        # Gate 2 needs evidence: with no GeoAlert Mananga point there is no temporal test to pass
        ok, why = acceptance(0.01, [], 0.4)
        self.assertFalse(ok)
        self.assertEqual(why, ['No GeoAlert Mananga flood point was available to test it on.'])


class UncertainAndMonitoringTests(SimpleTestCase):
    def test_uncertain_and_monitoring(self):
        refits = [{1: 'Red', 2: 'Orange'}] * 3 + [{1: 'Red', 2: 'Green'}] * 7
        self.assertEqual(uncertain_puroks({1: 'Red', 2: 'Green'}, refits), {2})
        self.assertFalse(monitoring(['Red'] * 8 + ['Green'] * 2)['under_review'])  # 80%: not below the target
        self.assertTrue(monitoring(['Red'] * 7 + ['Green'] * 4)['under_review'])  # 64%
        self.assertFalse(monitoring(['Green'] * 9)['under_review'])  # fewer than 10
        self.assertEqual(monitoring(['Red', None, 'Orange']), {'n': 3, 'in_red_orange': 2, 'under_review': False})
