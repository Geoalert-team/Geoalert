"""
The landslide susceptibility model's training core (plan Task 6): the design
matrix and its missing-road handling, the three candidates, leave-one-typhoon-
out scoring, the world test (rule 1), the NN-unless-clearly-worse choice
(rule 2), the point cut-offs, Talisay's in-range check and clipping, purok
scores and reasons, and the stability refits. Small synthetic arrays only; no
database, no files.
"""
from unittest import mock

import numpy as np
from django.test import SimpleTestCase

from apps.history.flood_rules import classify, uncertain_puroks
from apps.history.landslide_features import FEATURE_COLUMNS, LOG_COLUMNS
from apps.history.landslide_training import (
    ASSESSED_SHARE, CANDIDATES, NO_POINTS, P90, PH_FOLDS, UNLIKE, choose, clip_ranges, design_matrix, fit,
    medians_for, not_assessed_reason, out_of_fold, point_cutoffs, prepare_talisay, purok_scores, score, stability,
    world_test,
)

COLS = ('slope_deg', 'relief_m', 'twi', 'dist_road_m', 'marker')


def ground(rng, n: int, slope_mean: float, slope_sd: float) -> dict:
    """Every model input for n points; only the slope carries the signal."""
    return {
        'slope_deg': np.clip(rng.normal(slope_mean, slope_sd, n), 0, 70),
        'relief_m': rng.uniform(5, 120, n),
        'profile_curv': rng.normal(0, 0.01, n),
        'plan_curv': rng.normal(0, 0.01, n),
        'hand_m': rng.uniform(0, 80, n),
        'twi': rng.normal(6, 2, n),
        'dist_stream_m': rng.exponential(200, n),
        'dist_road_m': 5 + rng.exponential(500, n),
        'lc_trees': rng.uniform(0, 1, n),
        'lc_rangeland': rng.uniform(0, 1, n),
        'lc_crops': rng.uniform(0, 1, n),
        'lc_built': rng.uniform(0, 0.3, n),
        'lc_bare': rng.uniform(0, 1, n),
    }


def valley_floor(rng, n: int) -> dict:
    """
    Flat valley-floor ground: slope under 2.5 degrees, relief 1-12 m, high
    TWI, low above a channel. Land cover and roads as anywhere else.
    """
    out = ground(rng, n, 1, 1)
    out.update(slope_deg=rng.uniform(0, 2.5, n), relief_m=rng.uniform(1, 12, n),
               profile_curv=rng.normal(0, 0.002, n), plan_curv=rng.normal(0, 0.002, n),
               hand_m=rng.uniform(0, 6, n), twi=rng.uniform(9, 16, n), dist_stream_m=rng.exponential(80, n))
    return out


def block(rng, fold: str, region: str, slides: int, slide_slope=(30, 8), no_slope=(15, 10),
          valley_floors: bool = False) -> dict:
    """
    One event's slides and its three "no" points per slide; with
    `valley_floors`, one of each three lies on a flat valley floor.
    """
    yes = ground(rng, slides, *slide_slope)
    if valley_floors:
        hill, flat = ground(rng, 2 * slides, *no_slope), valley_floor(rng, slides)
        no = {c: np.r_[hill[c], flat[c]] for c in FEATURE_COLUMNS}
    else:
        no = ground(rng, 3 * slides, *no_slope)
    n = 4 * slides
    out = {c: np.r_[yes[c], no[c]] for c in FEATURE_COLUMNS}
    out.update(event=np.full(n, fold, dtype=object), fold=np.full(n, fold, dtype=object),
               region=np.full(n, region, dtype=object), label=np.r_[np.ones(slides), np.zeros(3 * slides)],
               noah_class=(rng.integers(0, 4, n).astype(float) if region == 'ph' else np.full(n, np.nan)),
               marker=np.zeros(n))
    return out


def stack(*blocks) -> dict:
    return {k: np.concatenate([b[k] for b in blocks]) for k in blocks[0]}


def mountains(seed: int = 0, slides: int = 30, valley_floors: bool = True) -> dict:
    """
    The four Philippine typhoon folds, slides on steeper ground than their
    "no" points. As the spec expects of the real sample (5.2), the "no" points
    include flat valley floors (one in three) unless `valley_floors=False`.
    """
    rng = np.random.default_rng(seed)
    return stack(*(block(rng, f, 'ph', slides, valley_floors=valley_floors) for f in PH_FOLDS))


class DesignMatrixTests(SimpleTestCase):
    def setUp(self):
        self.table_with_nan_road = mountains(slides=5)
        self.table_with_nan_road['dist_road_m'][:7] = np.nan  # an event that failed the road check

    def test_missing_roads_are_filled_with_an_indicator_except_for_xgboost(self):
        X, cols = design_matrix(self.table_with_nan_road, FEATURE_COLUMNS, medians={'dist_road_m': 50.0})
        self.assertIn('road_unknown', cols); self.assertFalse(np.isnan(X).any())
        X2, cols2 = design_matrix(self.table_with_nan_road, FEATURE_COLUMNS, medians=None)
        self.assertNotIn('road_unknown', cols2); self.assertTrue(np.isnan(X2).any())

    def test_distances_are_read_as_log1p_and_the_fill_marks_only_missing_roads(self):
        t = self.table_with_nan_road
        X, cols = design_matrix(t, FEATURE_COLUMNS, medians={'dist_road_m': 50.0})
        self.assertEqual(cols, FEATURE_COLUMNS + ('road_unknown',))
        for c in LOG_COLUMNS:
            expected = np.log1p(np.where(np.isnan(t[c]), 50.0, t[c]))
            np.testing.assert_allclose(X[:, cols.index(c)], expected)
        np.testing.assert_array_equal(X[:, -1], np.isnan(t['dist_road_m']).astype(float))
        np.testing.assert_allclose(X[:, cols.index('slope_deg')], t['slope_deg'])

    def test_medians_come_from_the_training_rows_and_xgboost_gets_none(self):
        t = self.table_with_nan_road
        rows = np.arange(len(t['label'])) >= 40
        self.assertIsNone(medians_for('xgboost', t, FEATURE_COLUMNS, rows))
        self.assertEqual(medians_for('neural_network', t, FEATURE_COLUMNS, rows),
                         {'dist_road_m': float(np.nanmedian(t['dist_road_m'][rows]))})


class CandidateTests(SimpleTestCase):
    def setUp(self):
        self.table = mountains(seed=3)
        self.table['dist_road_m'][::9] = np.nan
        self.y = self.table['label']
        self.w = np.ones(len(self.y))

    def test_every_candidate_scores_between_0_and_1_and_ranks_slides_higher(self):
        self.assertEqual(CANDIDATES, ('neural_network', 'logistic_regression', 'xgboost'))
        for name in CANDIDATES:
            X, cols = design_matrix(self.table, FEATURE_COLUMNS, medians_for(name, self.table, FEATURE_COLUMNS))
            s = score(name, fit(name, X, self.y, self.w, cols), X)
            self.assertTrue(((s >= 0) & (s <= 1)).all(), name)
            self.assertGreater(s[self.y == 1].mean(), s[self.y == 0].mean() + 0.1, name)

    def test_xgboost_keeps_its_monotone_directions(self):
        X, cols = design_matrix(self.table, FEATURE_COLUMNS, None)
        model = fit('xgboost', X, self.y, self.w, cols)
        base = np.nanmedian(X, axis=0)
        for column, direction in (('slope_deg', 1), ('relief_m', 1), ('twi', 1),
                                  ('dist_stream_m', -1), ('dist_road_m', -1)):
            j = cols.index(column)
            grid = np.tile(base, (50, 1))
            grid[:, j] = np.linspace(X[:, j][~np.isnan(X[:, j])].min(), np.nanmax(X[:, j]), 50)
            s = score('xgboost', model, grid)
            self.assertTrue((np.diff(s) * direction >= -1e-7).all(), column)
            if column == 'slope_deg':  # the clue that carries the signal is used, not flattened
                self.assertGreater(s[-1], s[0] + 0.1)


class MissingRoadTests(SimpleTestCase):
    """
    Ruling R19: the road check blanks dist_road_m for whole events. Here Egay,
    Mangkhut and Paeng failed it, so a fit with Agaton held out has training
    rows with no road distance at all.
    """

    def setUp(self):
        self.table = mountains(seed=12, slides=8)
        self.blank = self.table['fold'] != 'agaton'
        self.table['dist_road_m'][self.blank] = np.nan
        self.y = self.table['label']
        self.w = np.ones(len(self.y))

    def test_a_fold_whose_training_rows_have_no_road_is_still_scored(self):
        for name in CANDIDATES:
            s = out_of_fold(name, self.table, FEATURE_COLUMNS, PH_FOLDS, self.w)
            self.assertTrue(np.isfinite(s).all(), name)
            self.assertTrue(((s >= 0) & (s <= 1)).all(), name)

    def test_that_fit_drops_the_road_inputs_and_scores_the_same_columns(self):
        train, held = self.blank, ~self.blank
        no_road = tuple(c for c in FEATURE_COLUMNS if c != 'dist_road_m')
        self.assertEqual(medians_for('logistic_regression', self.table, FEATURE_COLUMNS, train), {})  # no median
        for name in ('neural_network', 'logistic_regression'):
            X, cols = design_matrix(self.table, FEATURE_COLUMNS, medians_for(name, self.table, FEATURE_COLUMNS, train))
            model = fit(name, X[train], self.y[train], self.w[train], cols)
            self.assertEqual(model.columns, no_road, name)
            moved = X[held].copy()  # the dropped inputs change nothing in the score
            moved[:, cols.index('dist_road_m')] += 3.0
            moved[:, cols.index('road_unknown')] = 1.0
            np.testing.assert_array_equal(score(name, model, X[held]), score(name, model, moved), name)
        X, cols = design_matrix(self.table, FEATURE_COLUMNS, None)  # xgboost reads a missing road as missing
        self.assertEqual(fit('xgboost', X[train], self.y[train], self.w[train], cols).columns, FEATURE_COLUMNS)

    def test_a_fit_with_some_roads_keeps_both_road_inputs(self):
        X, cols = design_matrix(self.table, FEATURE_COLUMNS,
                                medians_for('logistic_regression', self.table, FEATURE_COLUMNS))
        model = fit('logistic_regression', X, self.y, self.w, cols)
        self.assertEqual(model.columns, FEATURE_COLUMNS + ('road_unknown',))
        with self.assertRaises(ValueError):  # score takes the layout the fit was given, not another
            score('logistic_regression', model, X[:, :-1])

    def test_a_training_set_without_roads_scores_talisay_and_leaves_its_roads_unclipped(self):
        hills = {k: np.asarray(v)[self.blank] for k, v in self.table.items()}  # every event failed the check
        ranges = clip_ranges(hills, FEATURE_COLUMNS)
        self.assertNotIn('dist_road_m', ranges); self.assertIn('lc_built', ranges)
        points = ground(np.random.default_rng(13), 20, 20, 5)
        clipped, _ = prepare_talisay(points, hills, FEATURE_COLUMNS)
        np.testing.assert_array_equal(clipped['dist_road_m'], points['dist_road_m'])
        medians = medians_for('logistic_regression', hills, FEATURE_COLUMNS)
        X, cols = design_matrix(hills, FEATURE_COLUMNS, medians)
        model = fit('logistic_regression', X, hills['label'], np.ones(len(hills['label'])), cols)
        point_X, point_cols = design_matrix(clipped, FEATURE_COLUMNS, medians)
        self.assertEqual(point_cols, cols)
        s = score('logistic_regression', model, point_X)
        self.assertTrue(((s >= 0) & (s <= 1)).all())


class OutOfFoldTests(SimpleTestCase):
    def setUp(self):
        rng = np.random.default_rng(11)
        self.marked = stack(*(block(rng, f, 'ph', 25) for f in PH_FOLDS), block(rng, 'world', 'world', 20))
        self.egay_slides = (self.marked['fold'] == 'egay') & (self.marked['label'] == 1)
        self.marked['marker'][self.egay_slides] = 1.0  # a clue that only Egay's own slides carry
        self.world_rows = self.marked['fold'] == 'world'
        self.cols = COLS
        self.w = np.ones(len(self.marked['label']))
        X, cols = design_matrix(self.marked, self.cols, medians_for('logistic_regression', self.marked, self.cols))
        seen = fit('logistic_regression', X, self.marked['label'], self.w, cols)
        self.seen_egay_mean = score('logistic_regression', seen, X)[self.egay_slides].mean()

    def test_out_of_fold_never_scores_a_fold_with_a_model_that_saw_it(self):  # a marker column true only in egay slides
        s = out_of_fold('logistic_regression', self.marked, self.cols, PH_FOLDS, self.w)
        self.assertLess(np.nanmean(s[self.egay_slides]), self.seen_egay_mean - 0.2)
        self.assertTrue(np.isnan(s[self.world_rows]).all())

    def test_every_philippine_row_gets_a_score(self):
        s = out_of_fold('logistic_regression', self.marked, self.cols, PH_FOLDS, self.w)
        self.assertFalse(np.isnan(s[~self.world_rows]).any())


class ChoiceTests(SimpleTestCase):
    def setUp(self):
        table = stack(mountains(seed=5, slides=25), block(np.random.default_rng(6), 'world', 'world', 20))
        self.y, self.folds = table['label'], table['fold']
        rng = np.random.default_rng(7)
        world = self.folds == 'world'
        self.oof_good = np.where(world, np.nan, 0.5 * self.y + rng.uniform(0, 0.6, len(self.y)))
        self.oof_noise = np.where(world, np.nan, rng.uniform(0, 1, len(self.y)))
        self.oof_a_little_worse = np.where(world, np.nan, self.oof_good + rng.normal(0, 0.03, len(self.y)))

    def test_the_nn_is_kept_unless_clearly_worse(self):
        same = {n: self.oof_good.copy() for n in CANDIDATES}
        self.assertEqual(choose(same, self.y, self.folds)[0], 'neural_network')
        better_lr = {**same, 'neural_network': self.oof_noise}
        self.assertEqual(choose(better_lr, self.y, self.folds)[0], 'logistic_regression')

    def test_a_slightly_worse_nn_is_still_kept(self):
        oof = {'neural_network': self.oof_a_little_worse, 'logistic_regression': self.oof_good,
               'xgboost': self.oof_noise}
        chosen, per = choose(oof, self.y, self.folds, reps=300)
        self.assertEqual(chosen, 'neural_network')
        self.assertGreater(per['logistic_regression']['gain_over_nn'], 0)
        self.assertLessEqual(per['logistic_regression']['lo'], 0)

    def test_when_both_beat_the_nn_the_higher_pooled_auc_wins(self):
        rng = np.random.default_rng(8)
        best = np.where(self.folds == 'world', np.nan, self.y + rng.uniform(0, 0.2, len(self.y)))
        oof = {'neural_network': self.oof_noise, 'logistic_regression': self.oof_good, 'xgboost': best}
        chosen, per = choose(oof, self.y, self.folds, reps=300)
        self.assertEqual(chosen, 'xgboost')
        self.assertEqual(set(per), set(CANDIDATES))
        self.assertEqual(set(per['xgboost']), {'auc', 'gain_over_nn', 'lo', 'hi'})
        self.assertGreater(per['xgboost']['auc'], per['logistic_regression']['auc'])
        self.assertGreater(per['logistic_regression']['lo'], 0)


class TalisayTests(SimpleTestCase):
    def setUp(self):
        self.mountain_table = mountains(seed=1)
        rng = np.random.default_rng(2)
        n = 40
        self.flat_city_points = {  # flat lowland: slope 0-2 degrees, relief 2-10 m, high TWI, low above a channel
            'slope_deg': rng.uniform(0, 2, n), 'relief_m': rng.uniform(2, 10, n),
            'profile_curv': rng.normal(0, 0.002, n), 'plan_curv': rng.normal(0, 0.002, n),
            'hand_m': rng.uniform(0.5, 5, n), 'twi': rng.uniform(10, 14, n),
            'dist_stream_m': rng.uniform(20, 300, n),
            'dist_road_m': np.r_[np.zeros(n // 2), rng.uniform(0, 3, n - n // 2)],  # road points sit on their road
            'lc_trees': np.zeros(n), 'lc_rangeland': np.zeros(n), 'lc_crops': np.zeros(n),
            'lc_built': rng.uniform(0.9, 1.0, n), 'lc_bare': np.zeros(n),  # homes in built-up ground
            'noah_class': np.zeros(n), 'kind': np.r_[np.zeros(n // 2), np.ones(n - n // 2)],
        }
        self.one_purok_membership = (np.arange(n), np.full(n, 7))
        y = self.mountain_table['label']
        self.w = np.ones(len(y))
        oof = out_of_fold('logistic_regression', self.mountain_table, FEATURE_COLUMNS, PH_FOLDS, self.w)
        self.cutoffs_from_mountains = point_cutoffs(oof, y, self.w)

    def test_flat_built_up_purok_is_green_not_grey(self):
        clipped, valid = prepare_talisay(self.flat_city_points, self.mountain_table, FEATURE_COLUMNS)
        self.assertTrue(valid.all())  # terrain is in range; built-up share and road distance are clipped
        self.assertLessEqual(clipped['lc_built'].max(), np.percentile(self.mountain_table['lc_built'], 99) + 1e-9)
        out = purok_scores(np.full(len(valid), 0.01), self.one_purok_membership, valid, {7: len(valid)})
        self.assertTrue(out[7]['assessed'])
        self.assertEqual(classify(out[7]['score'], self.cutoffs_from_mountains), 'Green')

    def test_a_mountain_model_scores_the_clipped_flat_city_green(self):
        clipped, valid = prepare_talisay(self.flat_city_points, self.mountain_table, FEATURE_COLUMNS)
        self.assertGreaterEqual(clipped['dist_road_m'].min(), np.percentile(self.mountain_table['dist_road_m'], 1))
        self.assertTrue((self.flat_city_points['lc_built'] > 0.9 - 1e-9).all())  # the input is not changed
        medians = medians_for('logistic_regression', self.mountain_table, FEATURE_COLUMNS)
        X, cols = design_matrix(self.mountain_table, FEATURE_COLUMNS, medians)
        model = fit('logistic_regression', X, self.mountain_table['label'], self.w, cols)
        point_X, _ = design_matrix(clipped, FEATURE_COLUMNS, medians)
        out = purok_scores(score('logistic_regression', model, point_X), self.one_purok_membership, valid,
                           {7: len(valid)})
        self.assertEqual(classify(out[7]['score'], self.cutoffs_from_mountains), 'Green')

    def test_a_flat_purok_is_greyed_when_the_training_set_has_no_flat_ground(self):
        # Out of range is two-sided (spec 3.5): flat ground is scored only because the "no" points include
        # valley floors (spec 5.2). Without them, the same truly flat purok is "not assessed", with UNLIKE.
        city = self.flat_city_points
        self.assertTrue((city['slope_deg'] <= 2).all() and (city['relief_m'] <= 10).all())
        self.assertTrue((city['twi'] >= 10).all())
        hills_only = mountains(seed=1, valley_floors=False)
        too_flat = ((city['relief_m'] < np.percentile(hills_only['relief_m'], 1))
                    | (city['twi'] > np.percentile(hills_only['twi'], 99)))
        _, valid = prepare_talisay(city, hills_only, FEATURE_COLUMNS)
        self.assertFalse(valid[too_flat].any())
        self.assertLess(valid.sum(), ASSESSED_SHARE * len(valid))
        out = purok_scores(np.full(len(valid), 0.01), self.one_purok_membership, valid, {7: len(valid)})
        self.assertFalse(out[7]['assessed'])
        self.assertEqual(not_assessed_reason(out[7]['total'], out[7]['valid']), UNLIKE)

    def test_terrain_outside_the_training_range_is_not_valid(self):
        steep = {**self.flat_city_points, 'slope_deg': np.full(40, 85.0)}
        _, valid = prepare_talisay(steep, self.mountain_table, FEATURE_COLUMNS)
        self.assertFalse(valid.any())
        out = purok_scores(np.full(40, 0.5), self.one_purok_membership, valid, {7: 40})
        self.assertFalse(out[7]['assessed']); self.assertIsNone(out[7]['score'])
        self.assertEqual(not_assessed_reason(out[7]['total'], out[7]['valid']), UNLIKE)

    def test_purok_score_is_the_90th_percentile(self):
        self.assertEqual((P90, ASSESSED_SHARE), (90, 0.5))
        out = purok_scores(np.arange(10) / 10, (np.arange(10), np.full(10, 3)), np.ones(10, bool), {3: 10})
        self.assertAlmostEqual(out[3]['score'], np.percentile(np.arange(10) / 10, 90))
        self.assertEqual(not_assessed_reason(0, 0), NO_POINTS); self.assertEqual(not_assessed_reason(10, 4), UNLIKE)
        self.assertIsNone(not_assessed_reason(10, 5))

    def test_purok_scores_use_only_valid_points_and_list_every_purok(self):
        scores = np.array([.9, .1, .2, .3, .8])
        valid = np.array([False, True, True, True, True])
        out = purok_scores(scores, (np.arange(5), np.array([1, 1, 1, 2, 2])), valid, {1: 3, 2: 2, 9: 0})
        self.assertAlmostEqual(out[1]['score'], np.percentile([.1, .2], 90))
        self.assertEqual((out[1]['valid'], out[1]['total'], out[1]['assessed']), (2, 3, True))
        self.assertEqual(out[9], {'score': None, 'valid': 0, 'total': 0, 'assessed': False})


class CutoffTests(SimpleTestCase):
    def test_point_cutoffs_weight_own_slides(self):
        c = point_cutoffs(np.array([.9, .8, .7, .1]), np.array([1, 1, 0, 0]), np.array([1., 10., 1., 1.]))
        self.assertEqual(c.red, .8)  # the weight-10 slide at .8 holds half the weighted slides

    def test_rows_without_a_score_are_left_out(self):  # world rows are never scored out of fold
        with_world = point_cutoffs(np.array([.9, .8, np.nan, .7, .1, np.nan]), np.array([1, 1, 1, 0, 0, 0]),
                                   np.ones(6))
        self.assertEqual(with_world, point_cutoffs(np.array([.9, .8, .7, .1]), np.array([1, 1, 0, 0]), np.ones(4)))


class WorldTests(SimpleTestCase):
    def setUp(self):
        rng = np.random.default_rng(4)
        ph = [block(rng, f, 'ph', 20) for f in PH_FOLDS]
        # World ground where slides follow the opposite slope rule: rows that can only mislead
        world = block(rng, 'world', 'world', 60, slide_slope=(12, 8), no_slope=(28, 10))
        self.table_world_noise = stack(*ph, world)
        self.cols = COLS

    def test_world_rows_join_only_when_they_help(self):
        result = world_test(self.table_world_noise, self.cols, reps=300)
        self.assertFalse(result['joined'])
        self.assertLess(result['hi'], 0)  # the gain is "with the world over without": these rows clearly hurt
        self.assertEqual(set(result), {'joined', 'gain', 'lo', 'hi'})


class StabilityTests(SimpleTestCase):
    def setUp(self):
        self.table = mountains(seed=9)
        self.w = np.ones(len(self.table['label']))
        rng = np.random.default_rng(10)
        points = ground(rng, 30, 2, 0.5)  # purok 1: flat
        steep = ground(rng, 30, 45, 1)  # purok 2: steep
        cliff = ground(rng, 30, 85, 1)  # purok 3: steeper than any training ground
        points = {c: np.r_[points[c], steep[c], cliff[c]] for c in FEATURE_COLUMNS}
        self.membership = (np.arange(90), np.repeat([1, 2, 3], 30))
        self.totals = {1: 30, 2: 30, 3: 30}
        clipped, self.valid = prepare_talisay(points, self.table, FEATURE_COLUMNS)
        medians = medians_for('logistic_regression', self.table, FEATURE_COLUMNS)
        X, cols = design_matrix(self.table, FEATURE_COLUMNS, medians)
        model = fit('logistic_regression', X, self.table['label'], self.w, cols)
        self.point_X, _ = design_matrix(clipped, FEATURE_COLUMNS, medians)
        oof = out_of_fold('logistic_regression', self.table, FEATURE_COLUMNS, PH_FOLDS, self.w)
        self.cutoffs = point_cutoffs(oof, self.table['label'], self.w)
        per = purok_scores(score('logistic_regression', model, self.point_X), self.membership, self.valid,
                           self.totals)
        self.published = {pid: classify(v['score'], self.cutoffs) for pid, v in per.items() if v['assessed']}

    def test_refits_reclassify_the_assessed_puroks_with_the_fixed_cutoffs(self):
        self.assertEqual(self.published, {1: 'Green', 2: 'Red'})
        refits = stability('logistic_regression', self.table, FEATURE_COLUMNS, self.w, self.point_X,
                           self.membership, self.valid, self.totals, self.cutoffs, reps=5)
        self.assertEqual(len(refits), 5)
        self.assertTrue(all(set(r) == {1, 2} for r in refits))  # purok 3 is not assessed
        self.assertEqual(uncertain_puroks(self.published, refits), set())

    # Final review B3: the January job's own limit stops the refits between two fits, with a clear error
    def test_a_passed_deadline_stops_the_refits(self):
        from unittest import mock

        from apps.history import landslide_training as lt

        args = ('logistic_regression', self.table, FEATURE_COLUMNS, self.w, self.point_X, self.membership,
                self.valid, self.totals, self.cutoffs)
        with self.assertRaisesMessage(lt.PastDeadline, 'the run passed its 330-minute limit'):
            stability(*args, reps=5, deadline=lt.Deadline(at=0.0, minutes=330))
        clock = iter([0.0, 0.0, 1e9])  # read before each refit: the limit passes during the second
        with mock.patch.object(lt, 'fit', wraps=lt.fit) as fits, self.assertRaises(lt.PastDeadline):
            stability(*args, reps=5, deadline=lt.Deadline(at=100.0, minutes=330, clock=lambda: next(clock)))
        self.assertEqual(fits.call_count, 2)
        far = lt.Deadline(at=lt.time.monotonic() + 3600, minutes=330)  # a deadline not reached changes nothing
        self.assertEqual(stability(*args, reps=3, deadline=far), stability(*args, reps=3))


class DeadlineTests(SimpleTestCase):
    def setUp(self):
        rng = np.random.default_rng(4)
        self.table = stack(*(block(rng, f, 'ph', 20) for f in PH_FOLDS), block(rng, 'world', 'world', 20))
        self.w = np.ones(len(self.table['label']))

    def test_out_of_fold_and_the_world_test_check_the_deadline_before_each_fit(self):
        from unittest import mock

        from apps.history import landslide_training as lt

        passed = lt.Deadline(at=0.0, minutes=330)
        with mock.patch.object(lt, 'fit') as fits:
            with self.assertRaises(lt.PastDeadline):
                out_of_fold('logistic_regression', self.table, COLS, PH_FOLDS, self.w, deadline=passed)
            with self.assertRaises(lt.PastDeadline):
                world_test(self.table, COLS, reps=10, deadline=passed)
        fits.assert_not_called()
        far = lt.Deadline(at=lt.time.monotonic() + 3600, minutes=330)
        np.testing.assert_array_equal(
            out_of_fold('logistic_regression', self.table, COLS, PH_FOLDS, self.w, deadline=far),
            out_of_fold('logistic_regression', self.table, COLS, PH_FOLDS, self.w))


class ParallelSeedTests(SimpleTestCase):
    """Ruling R59: the network's five seeds fitted side by side in worker processes give the same network."""

    def test_seeds_fitted_side_by_side_give_the_same_network(self):
        from apps.history import landslide_training

        rng = np.random.default_rng(0)
        X = rng.normal(size=(300, 4))
        y = (X[:, 0] + 0.5 * rng.normal(size=300) > 0).astype(int)
        w = np.ones(300)
        from joblib import Parallel

        one_by_one = landslide_training._estimator('neural_network', X, y, w, (), 1)
        jobs = mock.patch.object(landslide_training, 'MLP_JOBS', 3)
        with jobs, mock.patch('joblib.Parallel', wraps=Parallel) as parallel:
            side_by_side = landslide_training._estimator('neural_network', X, y, w, (), 1)
        parallel.assert_called_once_with(n_jobs=3)  # the side-by-side branch really ran
        self.assertEqual(len(side_by_side.models), 5)
        for n, (a, b) in enumerate(zip(side_by_side.models, one_by_one.models)):  # each seed, in seed order
            np.testing.assert_allclose(a.predict_proba(X), b.predict_proba(X), rtol=0, atol=1e-9, err_msg=f'seed {n}')

    def test_a_bad_jobs_setting_fits_one_by_one(self):
        from apps.history import landslide_training

        for value, jobs in ((None, 1), ('', 1), ('abc', 1), ('0', 1), ('4', 4)):
            self.assertEqual(landslide_training._jobs(value), jobs, value)

