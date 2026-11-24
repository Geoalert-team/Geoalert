"""
The flood susceptibility model's training core (plan Task 4): the evidence
domain, the in-range check, the four candidates, out-of-fold scoring, purok
scores and reasons, the NOAH fallback and the stability refits (spec 3.4,
4.2-4.3, 5.1-5.4). Small synthetic arrays only; no database.
"""
import numpy as np
from django.contrib.gis.geos import Polygon
from django.test import SimpleTestCase

from apps.history.flood_rules import Cutoffs
from apps.history.flood_training import (CANDIDATES, design_matrix, domain, fit, in_range, noah_fallback,
                                         not_assessed_reason, out_of_fold, purok_scores, score, stability)

COLS = ('noah25_class', 'rel_height_river_m', 'built_share')


def synthetic(seed=0, n_p=100, n_b=1000):
    rng = np.random.default_rng(seed)
    Xp = np.c_[rng.integers(1, 4, n_p), rng.uniform(0, 2, n_p), rng.uniform(size=n_p)]
    Xb = np.c_[rng.integers(0, 3, n_b), rng.uniform(0, 8, n_b), rng.uniform(size=n_b)]
    return Xp.astype(float), Xb.astype(float)


class DomainTests(SimpleTestCase):
    def test_domain_is_the_buffered_hull(self):
        spots = [{'lat': 10.250, 'lon': 123.830, 'positive': True}, {'lat': 10.254, 'lon': 123.830, 'positive': True},
                 {'lat': 10.252, 'lon': 123.834, 'positive': True}, {'lat': 10.300, 'lon': 123.900, 'positive': False}]
        city = Polygon.from_bbox((123.80, 10.22, 123.90, 10.32))
        city.srid = 4326
        lon = np.array([123.831, 123.8325, 123.845])
        lat = np.array([10.252, 10.2555, 10.252])  # inside; ~160 m outside the hull; ~1.2 km outside
        mask, hull = domain(lon, lat, spots, city, buffer_m=300)
        self.assertEqual(mask.tolist(), [True, True, False])
        self.assertEqual(hull.srid, 4326)

    def test_in_range_uses_the_background_percentiles(self):
        Xb = np.arange(100.).reshape(-1, 1)
        np.testing.assert_array_equal(in_range(np.array([[50.], [-5.], [200.]]), Xb), [True, False, False])

    def test_design_matrix_logs_the_distance(self):
        table = {'dist_river_m': np.array([0., np.e - 1]), 'built_share': np.array([.2, .4])}
        np.testing.assert_allclose(design_matrix(table, ('dist_river_m', 'built_share')), [[0., .2], [1., .4]])


class CandidateTests(SimpleTestCase):
    def setUp(self):
        self.Xp, self.Xb = synthetic()
        self.X = np.r_[self.Xp, self.Xb]
        self.y = np.r_[np.ones(len(self.Xp)), np.zeros(len(self.Xb))]
        self.w = np.r_[np.full(len(self.Xp), len(self.Xb) / len(self.Xp)), np.ones(len(self.Xb))]

    def test_every_candidate_scores_between_0_and_1_and_ranks_a_clear_signal(self):
        self.assertEqual(CANDIDATES, ('logistic_regression', 'maxent_hinge', 'xgboost', 'neural_network'))
        for name in CANDIDATES:
            m = fit(name, self.X, self.y, self.w, columns=COLS)
            s = score(name, m, self.X)
            self.assertTrue(((s >= 0) & (s <= 1)).all(), name)
            self.assertGreater(s[self.y == 1].mean(), s[self.y == 0].mean() + 0.1, name)

    def test_the_separation_guard_refits_with_a_light_penalty(self):
        X = np.r_[np.ones((20, 1)), np.zeros((200, 1))]  # perfectly separated
        y = np.r_[np.ones(20), np.zeros(200)]
        m = fit('logistic_regression', X, y, np.r_[np.full(20, 10.), np.ones(200)], columns=('built_share',))
        self.assertTrue(m.separation_guard)

    def test_out_of_fold_never_scores_a_fold_with_a_model_that_saw_it(self):
        rng = np.random.default_rng(5)
        Xp, Xb = synthetic(seed=5)
        fp, fb = np.repeat(np.arange(5), 20), rng.integers(0, 5, len(Xb))
        marker_p = (fp == 0).astype(float)
        Xp_marked, Xb_marked = np.c_[Xp, marker_p], np.c_[Xb, np.zeros(len(Xb))]
        cols = COLS + ('depression_m',)
        p, b = out_of_fold('logistic_regression', Xp_marked, Xb_marked, fp, fb, columns=cols)
        X_all = np.r_[Xp_marked, Xb_marked]
        y_all = np.r_[np.ones(len(Xp)), np.zeros(len(Xb))]
        w_all = np.r_[np.full(len(Xp), len(Xb) / len(Xp)), np.ones(len(Xb))]
        seen = score('logistic_regression', fit('logistic_regression', X_all, y_all, w_all, columns=cols), Xp_marked)
        fold0 = fp == 0
        self.assertLess(p[fold0].mean(), seen[fold0].mean() - 0.2)
        self.assertEqual(p.shape, (len(Xp),))
        self.assertEqual(b.shape, (len(Xb),))


class PurokTests(SimpleTestCase):
    def test_purok_assessed_only_with_half_its_buildings_valid_and_reasons(self):
        out = purok_scores(np.array([.9, .8, .1]), (np.array([0, 1, 2]), np.array([7, 7, 8])),
                           np.array([True, False, True]), {7: 2, 8: 1, 9: 0})
        self.assertTrue(out[7]['assessed'])
        self.assertAlmostEqual(out[7]['score'], .9)
        self.assertTrue(out[8]['assessed'])
        self.assertFalse(out[9]['assessed'])
        self.assertIsNone(out[9]['score'])
        self.assertEqual(not_assessed_reason(0, 0, 0), 'No buildings in this area')
        self.assertEqual(not_assessed_reason(10, 2, 2), 'Outside the surveyed floodplain')
        self.assertEqual(not_assessed_reason(10, 10, 3), 'Its ground is unlike the surveyed floodplain')
        self.assertIsNone(not_assessed_reason(10, 10, 10))

    def test_noah_fallback_covers_only_puroks_near_noah(self):
        noah25 = np.array([3, 3, 0, 0, 1, 0])
        near = np.array([True, True, False, False, True, True])
        member = (np.arange(6), np.array([1, 1, 2, 2, 3, 3]))
        out = noah_fallback(noah25, near, member, {1: 2, 2: 2, 3: 2, 4: 0}, {1: 6, 3: 3, 2: 1})
        self.assertEqual(out['areas'][2]['not_assessed_reason'], 'No NOAH flood model information here')
        self.assertEqual(out['areas'][4]['not_assessed_reason'], 'No buildings in this area')
        self.assertEqual(out['areas'][1]['level'], 'Red')
        self.assertIn(out['areas'][3]['level'], ('Orange', 'Green'))
        self.assertIsInstance(out['cutoffs'], Cutoffs)

    def test_stability_refits_return_one_class_map_each(self):
        Xp, Xb = synthetic(seed=7, n_p=60, n_b=400)
        building_X = Xb
        member = (np.arange(len(Xb)), np.arange(len(Xb)) % 20)
        totals = {pid: int((member[1] == pid).sum()) for pid in range(20)}
        cut = Cutoffs(red=0.6, orange=0.3, red_recall=.5, orange_recall=.9, target_reached=True)
        refits = stability('logistic_regression', Xp, Xb, building_X, member, np.ones(len(Xb), bool), totals, cut,
                           columns=COLS, reps=5)
        self.assertEqual(len(refits), 5)
        self.assertEqual(set(refits[0]), set(range(20)))
        self.assertTrue(set(refits[0].values()) <= {'Red', 'Orange', 'Green'})
