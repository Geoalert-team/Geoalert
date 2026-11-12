import hashlib
import json
import shutil
import tempfile
import warnings
from calendar import monthrange
from datetime import date, datetime
from io import StringIO
from pathlib import Path
from unittest import mock

import numpy as np
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase
from sklearn.metrics import roc_auc_score

from apps.barangays.models import Barangay
from apps.hazards.models import HazardType
from apps.history import hazard_data, hazard_models
from apps.history.hazard_data import (
    MANILA, STUDY_END, STUDY_START, Dataset, RAIN_FEATURES, Record, TERRAIN_FEATURES, build_dataset, load_records,
    records_signature, write_terrain)
from apps.history.hazard_models import (
    ALARM_RATE, CANDIDATES, FOLDS, Fitted, benchmark_probs, bootstrap, calibration, day_blocks, fit_candidate,
    make_pipeline, no_skill, predict, scores, select_winner, threshold_metrics)
from apps.history.models import HistoricalRecord
from apps.history.rain import RainFile, complete_years, write_rain_csv
from tests.hazard_fixtures import toy_inputs

FAST = {'random_forest': {'n_estimators': 10, 'min_samples_leaf': 5}, 'xgboost': {'n_estimators': 10}}


def hand_dataset(rows):
    """rows: (barangay, date, y)"""
    n = len(rows)
    return Dataset(X=np.zeros((n, 2)), y=np.array([r[2] for r in rows], dtype=int),
                   barangay_id=np.array([r[0] for r in rows]),
                   day=np.array([np.datetime64(r[1], 'D') for r in rows]), features=('a', 'b'))


class HazardModelTests(SimpleTestCase):
    def test_fixed_settings_are_used_exactly(self):
        lr = make_pipeline('logistic_regression', 'Flood')[-1]
        self.assertEqual((lr.C, lr.l1_ratio, lr.solver, lr.max_iter), (1.0, 0.0, 'lbfgs', 2000))
        rf = make_pipeline('random_forest', 'Flood')[-1]
        self.assertEqual((rf.n_estimators, rf.max_depth, rf.min_samples_leaf, rf.max_features, rf.random_state),
                         (500, 3, 200, 'sqrt', 0))
        self.assertEqual(list(rf.monotonic_cst), [1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 1])
        xgb = make_pipeline('xgboost', 'Landslide')[-1].get_params()
        for k, v in dict(n_estimators=200, max_depth=2, learning_rate=0.05, subsample=0.8, reg_lambda=1,
                         min_child_weight=0.1, scale_pos_weight=1, random_state=0).items():
            self.assertEqual(xgb[k], v)
        self.assertEqual(tuple(xgb['monotone_constraints']), (1,) * 10)

    def test_speed_overrides_are_merged(self):
        with mock.patch.dict(hazard_models.SPEED_OVERRIDES, {'random_forest': {'n_estimators': 5}}):
            self.assertEqual(make_pipeline('random_forest', 'Flood')[-1].n_estimators, 5)
        self.assertEqual(make_pipeline('random_forest', 'Flood')[-1].n_estimators, 500)

    def test_folds_never_train_on_their_test_year_or_later(self):
        for train, test in FOLDS:
            self.assertTrue(max(train) < test)

    def test_every_candidate_fits_and_predicts_without_warnings(self):
        terrain, rain, pos = toy_inputs()
        for hazard in ('Flood', 'Landslide'):
            ds, _ = build_dataset(hazard, terrain, rain, pos, date(2021, 1, 1), date(2025, 12, 31))
            self.assertEqual(ds.features, RAIN_FEATURES + TERRAIN_FEATURES[hazard])
            X = ds.X.copy()
            X[:5, -1] = np.nan
            for name in CANDIDATES:
                with mock.patch.dict(hazard_models.SPEED_OVERRIDES, FAST):
                    with warnings.catch_warnings():
                        warnings.simplefilter('error')
                        p = make_pipeline(name, hazard).fit(X, ds.y).predict_proba(X)[:, 1]
                self.assertEqual(p.shape, (len(ds.y),))
                self.assertTrue(((p >= 0) & (p <= 1)).all())

    def test_all_nan_training_column_keeps_columns_aligned(self):
        terrain, rain, pos = toy_inputs()
        ds, _ = build_dataset('Flood', terrain, rain, pos, date(2021, 1, 1), date(2025, 12, 31))
        X = ds.X.copy()
        X[:, 3] = np.nan
        for name in CANDIDATES:
            with mock.patch.dict(hazard_models.SPEED_OVERRIDES, FAST):
                pipe = make_pipeline(name, 'Flood').fit(X, ds.y)
            self.assertEqual(pipe[-1].n_features_in_, X.shape[1])

    def test_benchmark_reads_training_years_only(self):
        # two training years, so January has 2 x 31 = 62 distinct days
        rows = []
        for year in (2021, 2022):
            for d in range(1, 32):
                rows.append((1, date(year, 1, d), 1 if (year, d) == (2021, 5) else 0))
                rows.append((2, date(year, 1, d), 0))
        train = hand_dataset(rows)
        pi = train.y.mean()
        test = hand_dataset([(1, date(2023, 1, 10), 0), (2, date(2023, 1, 10), 0), (3, date(2023, 1, 10), 0),
                             (1, date(2023, 2, 10), 0)])
        p = benchmark_probs(train, test)
        self.assertAlmostEqual(p[0], (1 + pi * 30) / (62 + 30))
        self.assertAlmostEqual(p[1], (0 + pi * 30) / (62 + 30))
        self.assertAlmostEqual(p[2], (0 + pi * 30) / (62 + 30))   # unseen barangay
        self.assertAlmostEqual(p[3], (0 + pi * 30) / (0 + 30))    # February never seen in training
        self.assertAlmostEqual(no_skill(train), pi)
        flipped = hand_dataset([(1, date(2023, 1, 10), 1), (2, date(2023, 1, 10), 1),
                                (3, date(2023, 1, 10), 1), (1, date(2023, 2, 10), 1)])
        np.testing.assert_array_equal(benchmark_probs(train, flipped), p)

    def test_scores_are_undefined_without_events(self):
        s = scores(np.zeros(50, bool), np.full(50, 0.01))
        self.assertIsNone(s['roc_auc'])
        self.assertIsNone(s['pr_auc'])
        self.assertTrue(np.isfinite(s['log_loss']))
        self.assertEqual((s['n'], s['positives'], s['prevalence']), (50, 0, 0.0))

    def test_scores_with_both_classes_are_plain_numbers(self):
        y = np.array([0, 0, 0, 1, 1, 0, 1, 0])
        p = np.array([0.1, 0.2, 0.1, 0.9, 0.6, 0.3, 0.7, 0.0])
        s = scores(y, p)
        self.assertEqual(set(s), {'log_loss', 'brier', 'roc_auc', 'pr_auc', 'n', 'positives', 'prevalence'})
        self.assertEqual(s['roc_auc'], 1.0)
        for k in ('log_loss', 'brier', 'roc_auc', 'pr_auc', 'prevalence'):
            self.assertIs(type(s[k]), float)
        self.assertIs(type(s['n']), int)
        self.assertIs(type(s['positives']), int)
        self.assertTrue(np.isfinite(s['log_loss']))

    def test_threshold_is_set_on_training_predictions(self):
        p_train = np.linspace(0, 1, 101)          # 99th percentile = 0.99
        y_test = np.array([1, 0, 1, 0, 0])
        p_test = np.array([0.995, 0.99, 0.5, 0.2, 1.0])
        m = threshold_metrics(p_train, y_test, p_test)
        self.assertAlmostEqual(m['cutoff'], 0.99)
        self.assertEqual((m['tp'], m['fp'], m['fn'], m['tn']), (1, 2, 1, 1))
        self.assertAlmostEqual(m['precision'], 1 / 3)
        self.assertAlmostEqual(m['recall'], 0.5)
        self.assertEqual(ALARM_RATE, 0.01)
        for k in ('tp', 'fp', 'fn', 'tn'):
            self.assertIs(type(m[k]), int)

    def test_threshold_undefined_cases(self):
        m = threshold_metrics(np.linspace(0, 1, 101), np.zeros(3), np.array([0.1, 0.2, 0.3]))
        self.assertIsNone(m['precision'])
        self.assertIsNone(m['recall'])

    # ---- Task 6: calibration, bootstrap, selection ----

    def _toy_train(self, hazard='Flood'):
        terrain, rain, pos = toy_inputs()
        ds, _ = build_dataset(hazard, terrain, rain, pos, date(2021, 1, 1), date(2025, 12, 31))
        return ds

    def _with_y(self, ds, y):
        return Dataset(ds.X, y, ds.barangay_id, ds.day, ds.features)

    def test_platt_is_skipped_when_the_calibration_year_has_no_events(self):
        ds = self._toy_train()
        y = np.where(ds.years == 2025, 0, ds.y)
        with mock.patch.dict(hazard_models.SPEED_OVERRIDES, FAST):
            f = fit_candidate('random_forest', 'Flood', self._with_y(ds, y))
        self.assertIsNone(f.platt)
        self.assertEqual(f.pipeline.predict_proba(ds.X).shape[1], 2)

    def test_platt_is_skipped_when_earlier_years_have_no_events(self):
        ds = self._toy_train()
        y = np.where(ds.years == 2025, ds.y, 0)
        with mock.patch.dict(hazard_models.SPEED_OVERRIDES, FAST):
            f = fit_candidate('xgboost', 'Flood', self._with_y(ds, y))
        self.assertIsNone(f.platt)

    def test_platt_is_fitted_for_trees_only(self):
        ds = self._toy_train()
        with mock.patch.dict(hazard_models.SPEED_OVERRIDES, FAST):
            for name in ('random_forest', 'xgboost'):
                with warnings.catch_warnings():
                    warnings.simplefilter('error')
                    f = fit_candidate(name, 'Flood', ds)
                self.assertEqual(len(f.platt), 2)
                self.assertTrue(all(type(v) is float for v in f.platt))
                p = predict(f, ds.X)
                self.assertEqual(p.shape, (len(ds.y),))
                self.assertTrue(((p >= 0) & (p <= 1)).all())
            lr = fit_candidate('logistic_regression', 'Flood', ds)
        self.assertIsNone(lr.platt)

    def test_predict_applies_the_platt_mapping(self):
        ds = self._toy_train()
        with mock.patch.dict(hazard_models.SPEED_OVERRIDES, FAST):
            f = fit_candidate('random_forest', 'Flood', ds)
        raw = f.pipeline.predict_proba(ds.X)[:, 1]
        c = np.clip(raw, 1e-6, 1 - 1e-6)
        a, b = f.platt
        np.testing.assert_allclose(predict(f, ds.X), 1 / (1 + np.exp(-(a * np.log(c / (1 - c)) + b))))
        np.testing.assert_array_equal(predict(Fitted(f.name, f.pipeline, None), ds.X), raw)

    def test_tie_rule_prefers_the_simpler_model(self):
        means = {'logistic_regression': 0.0105, 'random_forest': 0.0100, 'xgboost': 0.0110}
        self.assertEqual(select_winner(means, {('logistic_regression', 'random_forest'): (-0.0002, 0.0012)}),
                         'logistic_regression')
        self.assertEqual(select_winner(means, {('logistic_regression', 'random_forest'): (0.0001, 0.0009)}),
                         'random_forest')

    def test_tie_rule_reverse_pair_and_missing_names(self):
        means = {'logistic_regression': 0.0105, 'random_forest': 0.0100, 'xgboost': 0.0110}
        # only (leader, c) given: rf - lr = (-0.0012, 0.0002) includes 0, so lr wins
        self.assertEqual(select_winner(means, {('random_forest', 'logistic_regression'): (-0.0012, 0.0002)}),
                         'logistic_regression')
        # rf - lr = (-0.0012, -0.0001) excludes 0, so rf stays
        self.assertEqual(select_winner(means, {('random_forest', 'logistic_regression'): (-0.0012, -0.0001)}),
                         'random_forest')
        # no pair at all: the leader wins
        self.assertEqual(select_winner(means, {}), 'random_forest')
        # a name that was not scored is ignored
        self.assertEqual(select_winner({'xgboost': 0.01, 'random_forest': 0.02},
                                       {('random_forest', 'xgboost'): (0.0, 0.01)}), 'random_forest')
        # the simplest ties with the leader even though the middle one does not
        means2 = {'logistic_regression': 0.02, 'random_forest': 0.03, 'xgboost': 0.01}
        diff = {('logistic_regression', 'xgboost'): (-0.001, 0.02), ('random_forest', 'xgboost'): (0.01, 0.03)}
        self.assertEqual(select_winner(means2, diff), 'logistic_regression')

    def test_blocks_are_7_days_and_never_cross_a_year(self):
        d = np.arange(np.datetime64('2022-12-20'), np.datetime64('2023-01-12'))   # 2022 tail, 2023 head
        days = np.concatenate([d, d])                                              # two barangays
        blocks = day_blocks(days)
        years = days.astype('datetime64[Y]').astype(int) + 1970
        starts = set()
        for blk in blocks:
            ds = days[blk]
            self.assertEqual(len(set(years[blk])), 1)
            self.assertEqual(len(blk), 14)                    # 7 days x 2 barangays, kept together
            self.assertEqual((ds.max() - ds.min()).astype(int), 6)
            starts.add(ds.min())
        # 2022: Dec 20..31 gives starts Dec 20..25; 2023: Jan 1..11 gives starts Jan 1..5
        self.assertEqual(len(blocks), 6 + 5)
        self.assertIn(np.datetime64('2022-12-25'), starts)
        self.assertNotIn(np.datetime64('2022-12-26'), starts)

    def test_short_year_is_one_block_of_all_its_rows(self):
        days = np.array(['2023-03-01', '2023-03-02', '2023-03-02'], dtype='datetime64[D]')
        blocks = day_blocks(days)
        self.assertEqual(len(blocks), 1)
        self.assertEqual(sorted(blocks[0]), [0, 1, 2])

    def _bootstrap_inputs(self):
        rng = np.random.default_rng(1)
        days = np.concatenate([np.arange(np.datetime64(f'{y}-01-01'), np.datetime64(f'{y}-12-31') + 1)
                               for y in (2023, 2024)])
        n = len(days)
        p_true = np.where(rng.random(n) < 0.1, 0.4, 0.02)
        y = (rng.random(n) < p_true).astype(int)
        return days, y, {'good': np.clip(p_true, 0.01, 0.99), 'weak': np.full(n, y.mean())}

    def test_bootstrap_intervals_and_differences(self):
        days, y, preds = self._bootstrap_inputs()
        out = bootstrap(days, y, preds, reps=60, seed=3)
        self.assertEqual(set(out['intervals']), {'good', 'weak'})
        for name in preds:
            point = scores(y, preds[name])
            for metric in ('log_loss', 'brier', 'pr_auc'):
                lo, hi = out['intervals'][name][metric]
                self.assertIs(type(lo), float)
                self.assertIs(type(hi), float)
                self.assertLessEqual(lo, hi)
                self.assertLess(lo, point[metric] + 0.05)
                self.assertGreater(hi, point[metric] - 0.05)
        self.assertEqual(set(out['diff']), {('good', 'weak'), ('weak', 'good')})
        lo, hi = out['diff'][('good', 'weak')]
        nlo, nhi = out['diff'][('weak', 'good')]
        self.assertAlmostEqual(lo, -nhi)
        self.assertAlmostEqual(hi, -nlo)
        self.assertLess(hi, 0)          # the informed predictor has the lower log loss in every replicate

    def test_bootstrap_is_reproducible_and_seeded(self):
        days, y, preds = self._bootstrap_inputs()
        a = bootstrap(days, y, preds, reps=30, seed=5)
        self.assertEqual(a, bootstrap(days, y, preds, reps=30, seed=5))
        self.assertNotEqual(a['diff'], bootstrap(days, y, preds, reps=30, seed=6)['diff'])

    def test_bootstrap_pr_auc_is_none_without_events(self):
        days, _, preds = self._bootstrap_inputs()
        out = bootstrap(days, np.zeros(len(days), int), preds, reps=10)
        self.assertIsNone(out['intervals']['good']['pr_auc'])
        self.assertIsNotNone(out['intervals']['good']['log_loss'])

    def test_calibration_compares_observed_and_expected_per_year(self):
        rng = np.random.default_rng(2)
        years = np.repeat([2024, 2023, 2025], 40)
        p = rng.uniform(0.05, 0.5, len(years))
        y = (rng.random(len(years)) < p).astype(int)
        cal = calibration(y, p, years)
        self.assertEqual([r['year'] for r in cal['per_year']], [2023, 2024, 2025])
        for r in cal['per_year']:
            m = years == r['year']
            self.assertEqual(r['observed'], int(y[m].sum()))
            self.assertIs(type(r['observed']), int)
            self.assertAlmostEqual(r['expected'], float(p[m].sum()))
            self.assertIs(type(r['expected']), float)
        self.assertIs(type(cal['slope']), float)
        self.assertIsNone(cal['slope_ci'])

    def test_calibration_slope_and_interval(self):
        rng = np.random.default_rng(4)
        days = np.repeat(np.arange(np.datetime64('2024-01-01'), np.datetime64('2025-12-31') + 1), 3)
        p = rng.uniform(0.02, 0.6, len(days))
        y = (rng.random(len(days)) < p).astype(int)
        years = days.astype('datetime64[Y]').astype(int) + 1970
        cal = calibration(y, p, years, days=days, reps=40, seed=1)
        lo, hi = cal['slope_ci']
        self.assertLessEqual(lo, hi)
        self.assertTrue(0.5 < cal['slope'] < 1.6)
        flat = calibration(np.zeros(len(y), int), p, years, days=days, reps=5)   # one class: nothing to fit
        self.assertIsNone(flat['slope'])
        self.assertIsNone(flat['slope_ci'])
        self.assertEqual(flat['per_year'][0]['observed'], 0)

    def test_platt_with_a_non_positive_slope_is_discarded(self):
        ds = self._toy_train()
        last = ds.years == 2025
        with mock.patch.dict(hazard_models.SPEED_OVERRIDES, FAST):
            base = make_pipeline('random_forest', 'Flood').fit(ds.X[~last], ds.y[~last])
            p_last = base.predict_proba(ds.X[last])[:, 1]
            y = np.where(ds.years == 2025, 0, ds.y)
            rows = np.flatnonzero(last)
            y[rows[np.argmin(p_last)]] = 1        # the only event of the year is the one the base ranks last
            train = self._with_y(ds, y)
            self.assertLess(hazard_models._platt_fit(p_last, y[last])[0], 0)
            with warnings.catch_warnings():
                warnings.simplefilter('error')
                f = fit_candidate('random_forest', 'Flood', train)
            self.assertIsNone(f.platt)
            fresh = make_pipeline('random_forest', 'Flood').fit(train.X, train.y)
        np.testing.assert_array_equal(f.pipeline.predict_proba(ds.X), fresh.predict_proba(ds.X))

    def test_platt_comes_from_the_inner_base_and_the_pipeline_is_the_full_refit(self):
        ds = self._toy_train()
        last = ds.years == 2025
        with mock.patch.dict(hazard_models.SPEED_OVERRIDES, FAST):
            for name in ('random_forest', 'xgboost'):
                f = fit_candidate(name, 'Flood', ds)
                inner = make_pipeline(name, 'Flood').fit(ds.X[~last], ds.y[~last])
                a, b = hazard_models._platt_fit(inner.predict_proba(ds.X[last])[:, 1], ds.y[last])
                self.assertAlmostEqual(f.platt[0], a, delta=1e-9)
                self.assertAlmostEqual(f.platt[1], b, delta=1e-9)
                full = make_pipeline(name, 'Flood').fit(ds.X, ds.y)
                np.testing.assert_array_equal(f.pipeline.predict_proba(ds.X), full.predict_proba(ds.X))
                self.assertFalse(np.array_equal(f.pipeline.predict_proba(ds.X), inner.predict_proba(ds.X)))

    def test_calibration_slope_is_none_for_constant_predictions(self):
        rng = np.random.default_rng(7)
        days = np.repeat(np.arange(np.datetime64('2024-01-01'), np.datetime64('2025-12-31') + 1), 2)
        y = (rng.random(len(days)) < 0.2).astype(int)
        years = days.astype('datetime64[Y]').astype(int) + 1970
        cal = calibration(y, np.full(len(y), 0.2), years, days=days, reps=5)
        self.assertIsNone(cal['slope'])
        self.assertIsNone(cal['slope_ci'])
        self.assertAlmostEqual(cal['per_year'][0]['expected'], 0.2 * (years == 2024).sum())


# ---- Task 8: the test report ----

REPS = 20
SPEC_KEYS = ('rows', 'positives', 'prevalence', 'positive_days', 'winner', 'calibrated_all_folds', 'candidates',
             'benchmark', 'no_skill', 'beats_benchmark', 'threshold', 'calibration', 'timing_auc', 'place_auc',
             'lobo_auc', 'camp_iv', 'sensitivity', 'by_type', 'monthly_levels', 'monthly_brier',
             'scenario_years_by_fold', 'data_signature', 'limits', 'excluded')
SCORED_KEYS = {'mean_log_loss', 'pooled', 'intervals', 'per_year'}
YEAR_KEYS = {'year', 'positives', 'expected', 'log_loss', 'brier', 'roc_auc', 'pr_auc'}
EXCLUDED_REF = 'excl-1'
EXCLUDED_REF_2 = 'excl-2'
EXCLUDED_ROW = (2, date(2022, 7, 8))   # a flood row only the sensitivity run sees


def report_inputs():
    """Toy rain through 2026, so complete rain years exist after every test year; positives in the study only.

    Flood: barangay 3 never floods and 2024 has no flood (a test year without events, as in the real data).
    Landslide: barangay 3's first landslide is in 2025, the time-ordered test of an unseen barangay.
    """
    terrain, rain, pos = toy_inputs(end=date(2026, 12, 31))
    pos = {(b, d) for b, d in pos if d <= STUDY_END}
    flood = {(b, d) for b, d in pos if b != 3 and d.year != 2024}
    slide = {(b, d) for b, d in pos if b != 3 or d.year == 2025}
    every = [d for series in rain.values() for d in series]
    rf = RainFile(rain, {1: (10.25, 123.85), 2: (10.25, 123.85), 3: (10.33, 123.93)}, min(every), max(every))
    return terrain, rf, {'Flood': flood, 'Landslide': slide}


def toy_records(hazard, pos):
    subtypes = ('RIVER OVERFLOW', 'FLASH FLOOD')
    return [Record(f'{hazard}-{b}-{d}', hazard, b, d, subtypes[(b + d.day) % 2], False) for b, d in sorted(pos)]


def _datasets(terrain, rf, pos):
    return {h: build_dataset(h, terrain, rf.rain, pos[h], STUDY_START, STUDY_END)[0] for h in pos}


class ReportTests(SimpleTestCase):
    """One evaluation per hazard on toy data, shared by the tests; spies record what each fit saw."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        terrain, rf, pos = report_inputs()
        cls.terrain, cls.rain = terrain, rf
        cls.ds = _datasets(terrain, rf, pos)
        flood_records = toy_records('Flood', pos['Flood'])
        b0, d0 = max(p for p in pos['Flood'] if p[1].year == 2025)
        flood_records += [
            Record('extra-road', 'Flood', b0, d0, 'ROAD FLOODING', False),     # a second type on one row
            Record('sample-1', 'Flood', b0, d0, 'SAMPLE TYPE', True),          # samples never count
            Record(EXCLUDED_REF, 'Flood', b0, d0, 'EXCLUDED TYPE', False),     # excluded records never count
            # unplaced: two count (no barangay; a barangay with no terrain or rain), three do not
            Record('no-barangay', 'Flood', None, date(2023, 6, 1), 'RIVER OVERFLOW', False),
            Record('no-data', 'Flood', 99, date(2025, 1, 5), 'RIVER OVERFLOW', False),
            Record('no-barangay-sample', 'Flood', None, date(2023, 6, 2), 'RIVER OVERFLOW', True),
            Record(EXCLUDED_REF_2, 'Flood', None, date(2023, 6, 3), 'RIVER OVERFLOW', False),
            Record('no-barangay-late', 'Flood', None, date(2026, 1, 1), 'RIVER OVERFLOW', False),
        ]
        cls.records = {'Flood': flood_records, 'Landslide': toy_records('Landslide', pos['Landslide'])}
        cls.excluded = {EXCLUDED_REF: 'Date uncertain', EXCLUDED_REF_2: 'No barangay named'}
        cls.sens_ds = build_dataset('Flood', terrain, rf.rain, pos['Flood'] | {EXCLUDED_ROW},
                                    STUDY_START, STUDY_END)[0]

        cls.fit_calls, cls.scenario_calls = [], []
        real_fit, real_scenarios = hazard_models.fit_candidate, hazard_models.scenario_dates

        def fit_spy(name, hazard, train):
            cls.fit_calls.append({'name': name, 'hazard': hazard, 'years': frozenset(np.unique(train.years).tolist()),
                                  'barangays': frozenset(np.unique(train.barangay_id).tolist()),
                                  'positives': int(train.y.sum())})
            return real_fit(name, hazard, train)

        def scenario_spy(month, day, year, complete):
            out = real_scenarios(month, day, year, complete)
            cls.scenario_calls.append((year, list(out), [d for dates in out.values() for d in dates]))
            return out

        cls.reports = {}
        with warnings.catch_warnings(record=True) as caught, \
                mock.patch.dict(hazard_models.SPEED_OVERRIDES, FAST), \
                mock.patch.object(hazard_models, 'fit_candidate', fit_spy), \
                mock.patch.object(hazard_models, 'scenario_dates', scenario_spy):
            warnings.simplefilter('always')
            for hazard in ('Flood', 'Landslide'):
                cls.reports[hazard] = hazard_models.evaluate_hazard(
                    hazard, cls.ds[hazard], rf, terrain, cls.records[hazard],
                    cls.sens_ds if hazard == 'Flood' else None, excluded=cls.excluded, dropped=0, reps=REPS)
        cls.warnings = [f'{w.category.__name__}: {w.message}' for w in caught]
        cls.flood, cls.landslide = cls.reports['Flood'], cls.reports['Landslide']

    def _fold(self, hazard, i, ds=None):
        ds = self.ds[hazard] if ds is None else ds
        train_years, test_year = FOLDS[i]
        return ds.subset(np.isin(ds.years, train_years)), ds.subset(ds.years == test_year)

    def _pooled_test(self, hazard):
        ds = self.ds[hazard]
        return ds.subset(np.isin(ds.years, [t for _, t in FOLDS]))

    def test_report_has_every_field_the_card_reads(self):
        for hazard, rep in self.reports.items():
            self.assertLessEqual(set(SPEC_KEYS), set(rep), hazard)
            self.assertIn(rep['winner'], CANDIDATES)
            for name in CANDIDATES:
                c = rep['candidates'][name]
                self.assertLessEqual(SCORED_KEYS | {'calibrated', 'calibration_reason'}, set(c))
                self.assertEqual(set(c['pooled']), {'log_loss', 'brier', 'roc_auc', 'pr_auc'})
                self.assertEqual(set(c['intervals']), {'log_loss', 'brier', 'pr_auc'})
                self.assertEqual(len(c['calibrated']), len(FOLDS))
                self.assertTrue(all(type(v) is bool for v in c['calibrated']))
                self.assertEqual(c['calibrated'], [r == 'platt' for r in c['calibration_reason']])
                self.assertTrue(set(c['calibration_reason']) <= set(hazard_models.CALIBRATION_REASONS))
                self.assertEqual([r['year'] for r in c['per_year']], [t for _, t in FOLDS])
                for r in c['per_year']:
                    self.assertLessEqual(YEAR_KEYS, set(r))
            for name in ('benchmark', 'no_skill'):
                self.assertLessEqual(SCORED_KEYS, set(rep[name]))
                self.assertNotIn('calibrated', rep[name])
            self.assertEqual(rep['calibrated_all_folds'], all(rep['candidates'][rep['winner']]['calibrated']))
            self.assertEqual(rep['rows'], len(self.ds[hazard].y))
            self.assertEqual(rep['positives'], int(self.ds[hazard].y.sum()))
            self.assertEqual(rep['positive_days'], len(np.unique(self.ds[hazard].day[self.ds[hazard].y == 1])))
            self.assertAlmostEqual(rep['prevalence'], float(self.ds[hazard].y.mean()))
            self.assertEqual(rep['data_signature'], records_signature(self.records[hazard], STUDY_START, STUDY_END))
        self.assertIsNone(self.flood['camp_iv'])
        self.assertIsInstance(self.landslide['camp_iv'], list)
        self.assertIsInstance(self.flood['sensitivity'], dict)
        self.assertIsNone(self.landslide['sensitivity'])
        self.assertIsInstance(self.flood['by_type'], list)
        self.assertIsNone(self.landslide['by_type'])
        by_ref = {r.source_ref: r for r in self.records['Flood']}
        self.assertEqual(self.flood['excluded'],
                         [{'source_ref': ref, 'reason': self.excluded[ref], 'barangay_id': by_ref[ref].barangay_id,
                           'day': by_ref[ref].day.isoformat()} for ref in (EXCLUDED_REF, EXCLUDED_REF_2)])
        self.assertEqual(self.landslide['excluded'], [])
        self.assertEqual(self.landslide['bootstrap'], {'reps': REPS, 'block_days': hazard_models.BLOCK_DAYS,
                                                       'seed': 0})

    def test_unplaced_counts_kept_study_records_no_row_can_carry(self):
        # 'no-barangay' and 'no-data' (barangay 99 has no terrain or rain); the sample, the excluded and the
        # 2026 record without a barangay are not counted
        self.assertEqual(self.flood['unplaced'], 2)
        self.assertEqual(self.landslide['unplaced'], 0)

    def test_report_is_strict_json(self):
        for rep in self.reports.values():
            text = json.dumps(rep, allow_nan=False)
            self.assertEqual(json.loads(text), rep)
        # flood's 2024 test year has no events: its undefined scores are null, never a number
        lr_2024 = self.flood['candidates']['logistic_regression']['per_year'][1]
        self.assertEqual((lr_2024['year'], lr_2024['positives']), (2024, 0))
        self.assertIsNone(lr_2024['roc_auc'])
        self.assertIsNone(lr_2024['pr_auc'])
        safe = hazard_models.to_json_safe({'a': (np.float64('nan'), np.inf, np.int64(3), np.bool_(True),
                                                 np.array([1.5, 2.0]), date(2025, 1, 2),
                                                 np.datetime64('2025-03-04'), None, 'x'),
                                           7: {'k': np.float32(0.5)}})
        self.assertEqual(safe, {'a': [None, None, 3, True, [1.5, 2.0], '2025-01-02', '2025-03-04', None, 'x'],
                                '7': {'k': 0.5}})
        self.assertIs(type(safe['a'][2]), int)
        self.assertIs(type(safe['a'][3]), bool)

    def test_evaluation_raises_no_warnings(self):
        self.assertEqual(self.warnings, [])

    def test_each_fold_is_scored_on_its_test_year_only(self):
        full = frozenset({1, 2, 3})
        fold_years = [frozenset(train) for train, _ in FOLDS]
        flood_fits = [c for c in self.fit_calls if c['hazard'] == 'Flood']
        # the fold fits come first: each candidate of each fold gets exactly that fold's training years
        n = len(FOLDS) * len(CANDIDATES)
        self.assertEqual([(c['name'], c['years'], c['barangays']) for c in flood_fits[:n]],
                         [(name, years, full) for years in fold_years for name in CANDIDATES])
        on_all = [c for c in flood_fits if c['barangays'] == full]
        for c in on_all:
            self.assertIn(c['years'], fold_years)       # never a test year, never a later one
        for (train, test), years in zip(FOLDS, fold_years):
            self.assertTrue(max(years) < test)
            for name in CANDIDATES:
                self.assertTrue(any(c['name'] == name and c['years'] == years for c in on_all), (name, test))
        # leave-one-barangay-out: only the winner, over the whole study, each time without one barangay
        lobo = [c for c in flood_fits if c['barangays'] != full]
        self.assertEqual(sorted(tuple(full - c['barangays']) for c in lobo), [(1,), (2,), (3,)])
        for c in lobo:
            self.assertEqual((c['name'], c['years']), (self.flood['winner'], frozenset(range(2021, 2026))))
        # each per-year score is the fold's own test year, recomputed here from scratch
        for i, entry in enumerate(self.flood['candidates']['logistic_regression']['per_year']):
            train, test = self._fold('Flood', i)
            p = predict(fit_candidate('logistic_regression', 'Flood', train), test.X)
            self.assertEqual(entry['year'], FOLDS[i][1])
            self.assertEqual((entry['rows'], entry['positives']), (len(test.y), int(test.y.sum())))
            self.assertAlmostEqual(entry['log_loss'], scores(test.y, p)['log_loss'], places=12)
            self.assertAlmostEqual(entry['expected'], float(p.sum()), places=8)
        bench = self.flood['benchmark']['per_year'][2]
        train, test = self._fold('Flood', 2)
        self.assertAlmostEqual(bench['log_loss'], scores(test.y, benchmark_probs(train, test))['log_loss'], places=12)
        lr = self.flood['candidates']['logistic_regression']
        self.assertAlmostEqual(lr['mean_log_loss'], float(np.mean([r['log_loss'] for r in lr['per_year']])))

    def test_beats_benchmark_needs_the_whole_interval_below_zero(self):
        beats = hazard_models.beats_benchmark
        self.assertTrue(beats(0.010, 0.012, (-0.003, -0.0001)))
        self.assertFalse(beats(0.010, 0.012, (-0.003, 0.0001)))     # the interval reaches above 0
        self.assertFalse(beats(0.010, 0.012, (-0.003, 0.0)))        # touching 0 is not below it
        self.assertFalse(beats(0.013, 0.012, (-0.003, -0.0001)))    # the mean log loss is not lower
        self.assertFalse(beats(0.010, 0.012, None))
        for rep in self.reports.values():
            w = rep['winner']
            interval = rep['winner_minus_benchmark']
            self.assertEqual(len(interval), 2)
            self.assertEqual(rep['beats_benchmark'], beats(rep['candidates'][w]['mean_log_loss'],
                                                           rep['benchmark']['mean_log_loss'], interval))
            pair = [d for d in rep['differences'] if (d['a'], d['b']) == (w, 'benchmark')]
            self.assertEqual([[pair[0]['low'], pair[0]['high']]], [interval])

    def test_monthly_levels_use_scenario_years_before_the_test_year(self):
        self.assertEqual(complete_years(self.rain), [2021, 2022, 2023, 2024, 2025, 2026])
        expected_years = [{'test_year': 2023, 'scenario_years': [2021, 2022]},
                          {'test_year': 2024, 'scenario_years': [2021, 2022, 2023]},
                          {'test_year': 2025, 'scenario_years': [2021, 2022, 2023, 2024]}]
        self.assertTrue(self.scenario_calls)
        for year, keys, dates in self.scenario_calls:
            self.assertIn(year, (2023, 2024, 2025))
            self.assertTrue(keys and all(s < year for s in keys))
            self.assertTrue(all(d.year < year for d in dates))
        for hazard, rep in self.reports.items():
            self.assertEqual(rep['scenario_years_by_fold'], expected_years)
            levels, brier = rep['monthly_levels'], rep['monthly_brier']
            self.assertEqual([lv['level'] for lv in levels], ['High', 'Moderate', 'Low'])
            for lv in levels:
                self.assertEqual(set(lv), {'level', 'rows', 'events', 'chance', 'happened', 'chance_sum',
                                           'months_with_event'})
            self.assertEqual(sum(lv['rows'] for lv in levels), brier['barangay_months'])
            self.assertEqual(brier['barangay_months'] + sum(brier['skipped'].values()), len(FOLDS) * 3 * 12)
            pooled = self._pooled_test(hazard)
            self.assertEqual(sum(lv['events'] for lv in levels), int(pooled.y.sum()))         # barangay-days
            hit_months = {(d.year, int(b), d.month) for b, d in zip(pooled.barangay_id[pooled.y == 1],
                                                                    pooled.day[pooled.y == 1].astype(object))}
            self.assertEqual(sum(lv['months_with_event'] for lv in levels), len(hit_months))  # barangay-months
            self.assertLess(len(hit_months), int(pooled.y.sum()))     # the toy has months with several events
            for key in ('scenario', 'recorded_rain', 'benchmark'):
                self.assertTrue(0 <= brier[key] <= 1)
            # Recomputed without scenario_dates or period_chance: the fold's winner over each earlier complete
            # year's own month (29 February only when both years have it), 1 - prod(1 - p), averaged over
            # those years. The test year's own rain never enters.
            total = 0.0
            for i, (_, test_year) in enumerate(FOLDS):
                train, _ = self._fold(hazard, i)
                with mock.patch.dict(hazard_models.SPEED_OVERRIDES, FAST):
                    fit = fit_candidate(rep['winner'], hazard, train)
                per_s = {}
                for s in [s for s in complete_years(self.rain) if s < test_year]:
                    sd = build_dataset(hazard, self.terrain, self.rain.rain, set(), date(s, 1, 1), date(s, 12, 31))[0]
                    days = sd.day.astype(object)
                    per_s[s] = (sd.barangay_id, np.array([d.month for d in days]), np.array([d.day for d in days]),
                                predict(fit, sd.X))
                for b in (1, 2, 3):
                    for m in range(1, 13):
                        chances = []
                        for s, (ids, months, mdays, p) in per_s.items():
                            last = min(monthrange(test_year, m)[1], monthrange(s, m)[1])
                            chances.append(1 - np.prod(1 - p[(ids == b) & (months == m) & (mdays <= last)]))
                        total += float(np.mean(chances))
            self.assertAlmostEqual(sum(lv['chance_sum'] for lv in levels), total, places=8)

    def test_monthly_levels_group_by_the_fire_cutoffs(self):
        for rep in self.reports.values():
            for lv in rep['monthly_levels']:
                if lv['rows'] == 0:
                    self.assertEqual((lv['chance'], lv['happened'], lv['events'], lv['months_with_event']),
                                     (None, None, 0, 0))
                    continue
                mean = lv['chance_sum'] / lv['rows']
                self.assertEqual(lv['chance'], round(mean, 3))
                self.assertEqual(hazard_models.level_for(mean), lv['level'])
                self.assertEqual(lv['happened'], round(lv['months_with_event'] / lv['rows'], 3))
                self.assertIs(type(lv['months_with_event']), int)

    def test_threshold_reports_the_realised_training_flag_share(self):
        rep = self.flood
        t = rep['threshold']
        self.assertEqual(t['rate'], ALARM_RATE)
        self.assertEqual([f['year'] for f in t['folds']], [y for _, y in FOLDS])
        for i, f in enumerate(t['folds']):
            train, test = self._fold('Flood', i)
            with mock.patch.dict(hazard_models.SPEED_OVERRIDES, FAST):
                fit = fit_candidate(rep['winner'], 'Flood', train)
            p_train = predict(fit, train.X)
            m = threshold_metrics(p_train, test.y, predict(fit, test.X))
            self.assertAlmostEqual(f['cutoff'], m['cutoff'], places=12)
            self.assertEqual((f['tp'], f['fp'], f['fn'], f['tn']), (m['tp'], m['fp'], m['fn'], m['tn']))
            self.assertAlmostEqual(f['train_flagged_share'], float(np.mean(p_train >= m['cutoff'])))
        self.assertIsNone(t['folds'][1]['recall'])             # 2024: no flood to find
        for k in ('tp', 'fp', 'fn', 'tn'):
            self.assertEqual(t['pooled'][k], sum(f[k] for f in t['folds']))

    def test_calibration_has_pooled_observed_and_expected(self):
        for hazard, rep in self.reports.items():
            cal = rep['calibration']
            per_year = rep['candidates'][rep['winner']]['per_year']
            self.assertEqual([r['year'] for r in cal['per_year']], [y for _, y in FOLDS])
            self.assertEqual(cal['pooled']['observed'], int(self._pooled_test(hazard).y.sum()))
            self.assertAlmostEqual(cal['pooled']['expected'], sum(r['expected'] for r in per_year), places=8)
            self.assertEqual(cal['pooled']['observed'], sum(r['observed'] for r in cal['per_year']))
            self.assertIn('slope', cal)
            self.assertIn('slope_ci', cal)

    def test_ranking_checks_on_hand_data(self):
        days = np.repeat(np.array(['2025-01-01', '2025-01-02', '2025-01-03', '2025-01-04'], dtype='datetime64[D]'), 2)
        y = np.array([0, 0, 1, 0, 0, 1, 1, 1])
        p = np.array([0.1, 0.2, 0.5, 0.3, 0.6, 0.05, 0.2, 0.1])
        t = hazard_models.timing_auc(days, y, p)
        # city tops 0.2, 0.5, 0.6, 0.2 against events no, yes, yes, yes: 2.5 of 3 pairs ranked right
        self.assertEqual((t['days'], t['event_days']), (4, 3))
        self.assertAlmostEqual(t['auc'], 2.5 / 3)
        pl = hazard_models.place_auc(days, y, p)
        self.assertEqual([(r['day'], r['auc'], r['hit']) for r in pl['per_day']],
                         [('2025-01-02', 1.0, 1), ('2025-01-03', 0.0, 1)])     # every barangay hit on the 4th
        self.assertEqual(pl['skipped_days'], 1)
        self.assertAlmostEqual(pl['mean'], 0.5)
        self.assertIsNone(hazard_models.timing_auc(days, np.ones(8, int), p)['auc'])
        none = hazard_models.place_auc(days, np.zeros(8, int), p)
        self.assertEqual((none['mean'], none['per_day']), (None, []))

    def test_ranking_checks_in_the_report(self):
        pooled = self._pooled_test('Flood')
        t = self.flood['timing_auc']
        self.assertEqual(t['days'], len(np.unique(pooled.day)))
        self.assertEqual(t['event_days'], len(np.unique(pooled.day[pooled.y == 1])))
        self.assertTrue(0 <= t['auc'] <= 1)
        for r in self.flood['place_auc']['per_day']:
            self.assertTrue(r['hit'] >= 1)

    def test_lobo_ranks_barangays_never_trained_on(self):
        lobo = self.flood['lobo_auc']
        per = lobo['per_barangay']
        self.assertEqual([(r['barangay_id'], r['had_event']) for r in per], [(1, True), (2, True), (3, False)])
        self.assertAlmostEqual(lobo['auc'], roc_auc_score([1, 1, 0], [r['mean_chance'] for r in per]))
        self.assertIsNone(self.landslide['lobo_auc']['auc'])     # every barangay had a landslide: one class

    def test_camp_iv_lists_test_positives_in_barangays_unseen_with_an_event(self):
        rows = self.landslide['camp_iv']
        ds = self.ds['Landslide']
        expect = sorted(d.astype(object).isoformat() for d in ds.day[(ds.barangay_id == 3) & (ds.y == 1)])
        self.assertTrue(expect)
        self.assertEqual(sorted(r['day'] for r in rows), expect)
        self.assertTrue(all(r['barangay_id'] == 3 for r in rows))
        train, test = self._fold('Landslide', 2)
        with mock.patch.dict(hazard_models.SPEED_OVERRIDES, FAST):
            p = predict(fit_candidate(self.landslide['winner'], 'Landslide', train), test.X)
        for r in rows:
            i = np.flatnonzero((test.barangay_id == 3) & (test.day == np.datetime64(r['day'])))[0]
            self.assertAlmostEqual(r['chance'], float(p[i]), places=12)
            self.assertAlmostEqual(r['percentile'], 100 * float(np.mean(p < p[i])))

    def test_by_type_counts_each_subtype_behind_test_positives(self):
        pooled = self._pooled_test('Flood')
        behind = {}
        for r in self.records['Flood']:
            if not r.is_sample and r.source_ref != EXCLUDED_REF:
                behind.setdefault((r.barangay_id, r.day), set()).add(r.subtype)
        counts = {}
        for b, d in zip(pooled.barangay_id[pooled.y == 1], pooled.day[pooled.y == 1].astype(object)):
            for s in behind[(int(b), d)]:
                counts[s] = counts.get(s, 0) + 1
        got = {r['subtype']: r['positives'] for r in self.flood['by_type']}
        self.assertEqual(got, counts)
        self.assertEqual(got['ROAD FLOODING'], 1)
        self.assertNotIn('SAMPLE TYPE', got)
        self.assertNotIn('EXCLUDED TYPE', got)
        self.assertTrue(all(0 < r['mean_chance'] < 1 for r in self.flood['by_type']))

    def test_sensitivity_refits_the_winner_without_exclusions(self):
        sens = self.flood['sensitivity']
        ys, ps = [], []
        for i in range(len(FOLDS)):
            train, test = self._fold('Flood', i, self.sens_ds)
            with mock.patch.dict(hazard_models.SPEED_OVERRIDES, FAST):
                ps.append(predict(fit_candidate(self.flood['winner'], 'Flood', train), test.X))
            ys.append(test.y)
        s = scores(np.concatenate(ys), np.concatenate(ps))
        for k in ('log_loss', 'brier', 'roc_auc', 'pr_auc', 'positives'):
            self.assertAlmostEqual(sens[k], s[k], places=12)
        self.assertEqual(sens['study_positives'], self.flood['positives'] + 1)
        self.assertTrue(any(c['positives'] == int(self._fold('Flood', 0, self.sens_ds)[0].y.sum())
                            and c['hazard'] == 'Flood' for c in self.fit_calls))

    SELECTION = ('The model was chosen from three candidates on these same test years, so its scores may be '
                 'slightly optimistic.')

    def test_limits_are_plain_sentences_from_the_data(self):
        for hazard, rep in self.reports.items():
            limits = rep['limits']
            self.assertTrue(7 <= len(limits) <= 8, limits)
            self.assertTrue(all(isinstance(s, str) and s.endswith('.') for s in limits))
            self.assertIn(f"{rep['positives']} reported {hazard.lower()}", limits[0])
            self.assertIn(f"{rep['positive_days']} distinct days", limits[0])
            self.assertTrue(any('counting benchmark' in s for s in limits))
            self.assertTrue(any('2 NASA POWER grid cells' in s for s in limits))
            self.assertIn(self.SELECTION, limits)
            # the test years are held out from every fit but not from the choice of model: nothing may say
            # the model "never saw" them
            self.assertFalse(any('never saw' in s for s in limits))
        self.assertIn('The 2024 test year had no reported flood, so ROC-AUC, PR-AUC and recall are undefined for it; '
                      'its log loss and Brier score still count, and only 2023 and 2025 can show whether the model '
                      'ranks events above non-events.', self.flood['limits'])
        self.assertFalse(any('undefined' in s for s in self.landslide['limits']))

    def _realistic_flood(self, winner_mean, interval):
        """The real flood shape: quiet 2023 and 2024, 11 rows = 1 in 2025, 18 on 5 days, 22 barangays."""
        rep = json.loads(json.dumps(self.flood))
        rep.update(rows=40172, positives=18, positive_days=5, dropped=0, winner='logistic_regression',
                   winner_minus_benchmark=interval)
        for r, n in zip(rep['candidates']['logistic_regression']['per_year'], (0, 0, 11)):
            r['positives'] = n
        for f in rep['folds']:
            f['train_positive_days'] = 1
        rep['no_skill']['mean_log_loss'] = 0.0050
        rep['differences'] = [d for d in rep['differences'] if not (d['a'] == 'logistic_regression'
                                                                    and d['b'] == 'no_skill')]
        rep['differences'].append({'a': 'logistic_regression', 'b': 'no_skill', 'low': -0.0010, 'high': -0.0001})
        rep['candidates']['logistic_regression']['mean_log_loss'] = winner_mean
        rep['benchmark']['mean_log_loss'] = 0.0040
        rep['beats_benchmark'] = hazard_models.beats_benchmark(winner_mean, 0.0040, interval)
        return rep

    def test_limits_for_a_flood_that_did_not_beat_counting_with_two_quiet_years(self):
        rep = self._realistic_flood(0.0046, [-0.0003, 0.0021])
        self.assertFalse(rep['beats_benchmark'])
        self.assertEqual(hazard_models.report_limits('Flood', rep, cells=3, barangays=22), [
            '18 reported flood barangay-days from 2021 to 2025 fall on 5 distinct days, so the evidence is closer '
            'to 5 days than to 40,172 rows.',
            'The model learned from reported floods on 1 distinct day in the training years before each test '
            'year.',
            'The 2023 and 2024 test years had no reported flood, so ROC-AUC, PR-AUC and recall are undefined for '
            'them; their log loss and Brier score still count, and only 2025 can show whether the model ranks '
            'events above non-events.',
            'The logistic regression model did not beat the counting benchmark on test years it was not trained on '
            '(its mean log loss is not lower); it still supplies the forecast.',
            "It also beat always guessing the training years' average chance (no skill): the 95% interval of "
            "that difference lies below zero too.",
            self.SELECTION,
            'Rain comes from 3 NASA POWER grid cells (about 55 km across) for 22 barangays, so barangays in one cell '
            'share the same rain and small storms can be missed.',
            'The records come from news reports, so an empty barangay-day means nothing was reported, not that '
            'nothing happened: the chances describe reported floods and read lower than the true rate.'])

    def test_limits_other_branches(self):
        lower = hazard_models.report_limits('Flood', self._realistic_flood(0.0035, [-0.0012, 0.0004]),
                                            cells=3, barangays=22)
        self.assertIn('The logistic regression model did not beat the counting benchmark on test years it was not '
                      'trained on (its mean log loss is lower, but the 95% interval of the difference does not lie '
                      'wholly below zero); it still supplies the forecast.', lower)
        beat = hazard_models.report_limits('Flood', self._realistic_flood(0.0030, [-0.0015, -0.0002]),
                                           cells=3, barangays=22)
        self.assertIn('The logistic regression model beat the counting benchmark on test years it was not trained '
                      'on: its mean log loss is lower and the 95% interval of the difference lies below zero.', beat)
        quiet = self._realistic_flood(0.0046, [-0.0003, 0.0021])
        quiet['candidates']['logistic_regression']['per_year'][2]['positives'] = 0
        self.assertIn('The 2023, 2024 and 2025 test years had no reported flood, so ROC-AUC, PR-AUC and recall are '
                      'undefined for them; their log loss and Brier score still count, but no test year can show '
                      'whether the model ranks events above non-events.',
                      hazard_models.report_limits('Flood', quiet, cells=3, barangays=22))
        # rows dropped for missing rain join the first sentence, so even the longest list stays at six
        most = hazard_models.report_limits('Flood', {**self._realistic_flood(0.0046, [-0.0003, 0.0021]),
                                                     'dropped': 5}, cells=1, barangays=1)
        self.assertEqual(len(most), 8)
        self.assertTrue(most[0].endswith('than to 40,172 rows (5 more barangay-days were left out because a day '
                                         'of the 14-day rain window was missing).'))
        self.assertIn('Rain comes from 1 NASA POWER grid cell (about 55 km across) for 1 barangay,', most[6])

    NS_BEAT = ("It also beat always guessing the training years' average chance (no skill): the 95% interval of "
               "that difference lies below zero too.")
    NS_NOT_LOWER = "Its mean log loss is not lower than always guessing the training years' average chance (no skill)."
    NS_UNSURE = ("Against always guessing the training years' average chance (no skill), the 95% interval of the "
                 "difference does not lie wholly below zero, so its gain over that simpler guess is not certain.")

    def _limits_with(self, winner_mean, no_skill_mean, interval, counts=(1, 1, 1), hazard='Flood'):
        rep = self._realistic_flood(0.0046, [-0.0003, 0.0021])
        rep['candidates']['logistic_regression']['mean_log_loss'] = winner_mean
        rep['no_skill']['mean_log_loss'] = no_skill_mean
        rep['differences'] = [d for d in rep['differences'] if not (d['a'] == 'logistic_regression'
                                                                    and d['b'] == 'no_skill')]
        if interval is not None:
            rep['differences'].append({'a': 'logistic_regression', 'b': 'no_skill',
                                       'low': interval[0], 'high': interval[1]})
        for f, n in zip(rep['folds'], counts):
            f['train_positive_days'] = n
        return hazard_models.report_limits(hazard, rep, cells=3, barangays=22)

    def test_limits_say_what_the_model_learned_from_equal_counts(self):
        limits = self._limits_with(0.0046, 0.0050, (-0.001, -0.0001))
        self.assertEqual(limits[1], 'The model learned from reported floods on 1 distinct day in the training '
                                    'years before each test year.')
        again = self._limits_with(0.0046, 0.0050, (-0.001, -0.0001), counts=(3, 3, 3))
        self.assertEqual(again[1], 'The model learned from reported floods on 3 distinct days in the training '
                                   'years before each test year.')

    def test_limits_say_what_the_model_learned_from_unequal_counts(self):
        limits = self._limits_with(0.0046, 0.0050, (-0.001, -0.0001), counts=(3, 4, 5), hazard='Landslide')
        self.assertEqual(limits[1], 'The model learned from reported landslides on 3, 4 and 5 distinct days in '
                                    'the training years before 2023, 2024 and 2025 respectively.')

    def test_limits_compare_the_winner_with_no_skill(self):
        beat = self._limits_with(0.0046, 0.0050, (-0.001, -0.0001))
        self.assertIn(self.NS_BEAT, beat)
        self.assertNotIn(self.NS_NOT_LOWER, beat)
        self.assertNotIn(self.NS_UNSURE, beat)
        worse = self._limits_with(0.0055, 0.0050, (0.0001, 0.001))
        self.assertIn(self.NS_NOT_LOWER, worse)
        self.assertNotIn(self.NS_BEAT, worse)
        self.assertNotIn(self.NS_UNSURE, worse)
        equal = self._limits_with(0.0050, 0.0050, (-0.001, -0.0001))
        self.assertIn(self.NS_NOT_LOWER, equal)
        for interval in ((-0.001, 0.0002), (-0.001, 0.0), None):
            unsure = self._limits_with(0.0046, 0.0050, interval)
            self.assertIn(self.NS_UNSURE, unsure)
            self.assertNotIn(self.NS_BEAT, unsure)
            self.assertNotIn(self.NS_NOT_LOWER, unsure)

    def test_limits_keep_their_order(self):
        rep = self._realistic_flood(0.0046, [-0.0003, 0.0021])
        limits = hazard_models.report_limits('Flood', rep, cells=3, barangays=22)
        marks = ['distinct day', 'The model learned from', 'test years had no reported', 'counting benchmark',
                 'average chance (no skill)', 'was chosen from', 'NASA POWER grid cell', 'news reports']
        at = [next(i for i, s in enumerate(limits) if m in s) for m in marks]
        self.assertEqual(at, sorted(at))
        self.assertEqual(len(set(at)), len(marks))
        self.assertEqual(len(limits), 8)

    def test_folds_carry_the_training_evidence(self):
        for hazard, rep in self.reports.items():
            ds = self.ds[hazard]
            self.assertEqual([(f['train_years'], f['test_year']) for f in rep['folds']],
                             [(list(t), y) for t, y in FOLDS])
            for f, (train_years, _) in zip(rep['folds'], FOLDS):
                train = ds.subset(np.isin(ds.years, train_years))
                self.assertIs(type(f['train_positives']), int)
                self.assertIs(type(f['train_positive_days']), int)
                self.assertEqual(f['train_positives'], int(train.y.sum()))
                self.assertEqual(f['train_positive_days'], len(np.unique(train.day[train.y == 1])))

    def test_calibration_reason_says_why_each_fold_is_or_is_not_calibrated(self):
        flood = self.flood['candidates']
        self.assertEqual(flood['logistic_regression']['calibration_reason'], ['not_applicable'] * 3)
        for name in ('random_forest', 'xgboost'):
            # toy flood: 2024, fold 3's calibration year, has no flood; 2022 and 2023 do
            self.assertEqual(flood[name]['calibration_reason'][2], 'no_event_in_calibration_year')
            self.assertIn(flood[name]['calibration_reason'][0], ('platt', 'sign_guard'))
        reasons = {r for rep in self.reports.values() for c in rep['candidates'].values()
                   for r in c['calibration_reason']}
        self.assertIn('platt', reasons)
        # the other two, from fit_candidate itself on toy rows built to need them
        ds = self._toy_train()
        with mock.patch.dict(hazard_models.SPEED_OVERRIDES, FAST):
            early = self._with_y(ds, np.where(ds.years == 2025, ds.y, 0))          # events only in 2025
            f = fit_candidate('xgboost', 'Flood', early)
            self.assertEqual(hazard_models.calibration_reason('xgboost', early, f), 'no_event_in_earlier_years')
            last = ds.years == 2025
            base = make_pipeline('random_forest', 'Flood').fit(ds.X[~last], ds.y[~last])
            y = np.where(last, 0, ds.y)
            y[np.flatnonzero(last)[np.argmin(base.predict_proba(ds.X[last])[:, 1])]] = 1   # Platt slope < 0
            flipped = self._with_y(ds, y)
            f = fit_candidate('random_forest', 'Flood', flipped)
            self.assertEqual(hazard_models.calibration_reason('random_forest', flipped, f), 'sign_guard')
            f = fit_candidate('random_forest', 'Flood', ds)
            self.assertEqual(hazard_models.calibration_reason('random_forest', ds, f), 'platt')
        lr = Fitted('logistic_regression', None, None)
        self.assertEqual(hazard_models.calibration_reason('logistic_regression', ds, lr), 'not_applicable')
        # a mapping the rule does not allow is never reported as anything
        with self.assertRaises(RuntimeError):
            hazard_models.calibration_reason('xgboost', early, Fitted('xgboost', None, (1.0, 0.0)))

    def _toy_train(self):
        terrain, rain, pos = toy_inputs()
        return build_dataset('Flood', terrain, rain, pos, date(2021, 1, 1), date(2025, 12, 31))[0]

    def _with_y(self, ds, y):
        return Dataset(ds.X, y, ds.barangay_id, ds.day, ds.features)

    def test_read_report_is_none_when_missing_or_unreadable(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        path = tmp / 'report.json'
        self.assertIsNone(hazard_models.read_report(path))
        path.write_bytes(b'not json')
        self.assertIsNone(hazard_models.read_report(path))
        path.write_bytes(b'\xff\xfe\x00broken')
        self.assertIsNone(hazard_models.read_report(path))
        path.write_bytes(b'[1, 2]')
        self.assertIsNone(hazard_models.read_report(path))
        path.write_text(json.dumps({'hazards': {}}), encoding='utf-8')
        self.assertEqual(hazard_models.read_report(path), {'hazards': {}})
        with mock.patch.object(hazard_models, 'REPORT_PATH', path):       # the default is read at call time
            self.assertEqual(hazard_models.read_report(), {'hazards': {}})
        self.assertEqual(hazard_models.REPORT_PATH.name, 'hazard_model_report.json')
        self.assertEqual(hazard_models.REPORT_PATH.parent, hazard_data.DATA_DIR)


def _sha1(path):
    return hashlib.sha1(path.read_bytes()).hexdigest()


def _no_nan(constant):
    raise ValueError(f'not strict JSON: {constant}')


class ReportCommandTests(TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        terrain, rf, pos = report_inputs()
        write_terrain(self.tmp / 'barangay_terrain.csv', terrain, {b: f'Toy {b}' for b in terrain})
        write_rain_csv(self.tmp / 'rain_daily.csv', rf.rain, rf.cells)
        with open(self.tmp / 'hazard_model_exclusions.csv', 'w', newline='', encoding='utf-8') as f:
            f.write(f'source_ref,reason\r\n{EXCLUDED_REF},Date uncertain\r\n')
        for b in sorted(terrain):
            Barangay.objects.create(id=b, name=f'Toy {b}')
        for hazard, rows in pos.items():
            kind = HazardType.objects.create(name=hazard, logo_class='x')
            extra = []
            if hazard == 'Flood':
                extra = [(EXCLUDED_ROW, EXCLUDED_REF, False), ((1, date(2026, 3, 1)), 'after-study', False),
                         ((1, date(2023, 5, 5)), 'sample-row', True)]
            HistoricalRecord.objects.bulk_create(
                [HistoricalRecord(barangay_id=b, hazard_type=kind, severity_level='Green', source_ref=ref,
                                  occurred_at=datetime(d.year, d.month, d.day, 12, tzinfo=MANILA),
                                  hazard_subcategory='RIVER OVERFLOW', is_sample=sample)
                 for (b, d), ref, sample in [(p, f'{hazard}-{p[0]}-{p[1]}', False) for p in sorted(rows)] + extra])
        self.report_path = self.tmp / 'hazard_model_report.json'
        for patcher in (mock.patch.object(hazard_data, 'DATA_DIR', self.tmp),
                        mock.patch.object(hazard_models, 'REPORT_PATH', self.report_path),
                        mock.patch.object(hazard_models, 'BOOTSTRAP_REPS', REPS),
                        mock.patch.dict(hazard_models.SPEED_OVERRIDES, FAST)):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.study = {'start': '2021-01-01', 'end': '2025-12-31'}

    def _files(self):
        return {'rain_sha1': _sha1(self.tmp / 'rain_daily.csv'),
                'terrain_sha1': _sha1(self.tmp / 'barangay_terrain.csv'),
                'exclusions_sha1': _sha1(self.tmp / 'hazard_model_exclusions.csv')}

    def test_command_writes_the_report_with_signatures(self):
        out = StringIO()
        call_command('test_hazard_models', stdout=out)
        report = json.loads(self.report_path.read_text(encoding='utf-8'), parse_constant=_no_nan)
        self.assertLessEqual({'generated', 'study', 'files', 'hazards'}, set(report))
        self.assertEqual(report['study'], self.study)
        self.assertEqual(report['files'], self._files())
        self.assertEqual(datetime.fromisoformat(report['generated']).utcoffset().total_seconds(), 8 * 3600)
        self.assertEqual(list(report['hazards']), ['Flood', 'Landslide'])
        _, _, pos = report_inputs()
        for hazard, rep in report['hazards'].items():
            self.assertLessEqual(set(SPEC_KEYS), set(rep))
            self.assertEqual(rep['data_signature'], records_signature(load_records(hazard), STUDY_START, STUDY_END))
            self.assertEqual(rep['positives'], len(pos[hazard]))      # the excluded and sample rows are not events
            self.assertIn(f"{hazard}: winner {rep['winner']}, beats_benchmark {rep['beats_benchmark']}", out.getvalue())
        flood = report['hazards']['Flood']
        self.assertEqual([e['source_ref'] for e in flood['excluded']], [EXCLUDED_REF])
        self.assertEqual(flood['unplaced'], 0)        # the 2026 record is outside the study; samples never count
        self.assertEqual(flood['sensitivity']['study_positives'], flood['positives'] + 1)
        self.assertEqual(hazard_models.read_report(), report)

    def test_single_hazard_run_merges_only_into_a_matching_report(self):
        with self.assertRaises(CommandError):                       # nothing to merge into
            call_command('test_hazard_models', hazard='Landslide', stdout=StringIO())
        self.assertFalse(self.report_path.exists())
        kept = {'winner': 'logistic_regression', 'marker': 'kept'}
        self.report_path.write_text(json.dumps({'generated': 'x', 'study': self.study, 'files': self._files(),
                                                'hazards': {'Flood': kept}}), encoding='utf-8')
        call_command('test_hazard_models', hazard='Landslide', stdout=StringIO())
        report = hazard_models.read_report()
        self.assertEqual(report['hazards']['Flood'], kept)
        self.assertLessEqual(set(SPEC_KEYS), set(report['hazards']['Landslide']))
        self.assertEqual(report['files'], self._files())
        # a changed input file: a single-hazard run would leave Flood described against the old one, so it is
        # refused and the report stays as it was
        before = self.report_path.read_bytes()
        for name, row in (('hazard_model_exclusions.csv', 'Flood-1-2021-01-01,Another reason\r\n'),
                          ('rain_daily.csv', '1,10.25,123.85,2027-01-01,0.0\r\n')):
            path = self.tmp / name
            original = path.read_bytes()
            with open(path, 'a', newline='') as f:
                f.write(row)
            with self.assertRaises(CommandError, msg=name):
                call_command('test_hazard_models', hazard='Flood', stdout=StringIO())
            self.assertEqual(self.report_path.read_bytes(), before)
            path.write_bytes(original)
