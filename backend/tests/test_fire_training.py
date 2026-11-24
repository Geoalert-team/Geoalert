"""
Labels, the area-month panel, the candidate models and the choice rule for the
fire risk model (plan Task B2, spec 4.4-4.5). Synthetic panels: 12 areas in 3
barangays over 36 months.
"""
import math
from datetime import datetime, timedelta, timezone as dt_timezone
from unittest import mock

import numpy as np
from django.contrib.gis.geos import MultiPolygon
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from apps.history import fire_features as ff
from apps.history import fire_training as ft
from apps.history.models import HistoricalRecord
from tests.fire_setup import FireSetupMixin, box

FIRST = 2023 * 12  # January 2023 as a month index
MONTHS = range(FIRST, FIRST + 36)

# One setting per family and small ensembles, so the rule's tests run quickly;
# test_fold_without_fires_scores_finite runs the full grid once
SMALL = {
    'logistic_regression': [{'label': 'C=0.01', 'C': 0.01}],
    'random_forest': [{'label': 'small', 'n_estimators': 60, 'max_depth': 5, 'min_samples_leaf': 5,
                       'max_features': 'log2'}],
    'adaboost': [{'label': 'small', 'n_estimators': 50, 'learning_rate': 1.0}],
    'xgboost': [{'label': 'small', 'learning_rate': 0.1, 'n_estimators': 100, 'max_depth': 3,
                 'min_child_weight': 1, 'gamma': 0.0, 'colsample_bytree': 1.0}],
    'neural_network': [{'label': 'h8', 'hidden': 8, 'alpha': 1.0}],
}


def feature_table(values=None):
    """12 areas in 3 barangays; `values(i)` gives area i's feature dict (default: a smooth spread)."""
    rows = []
    for i in range(12):
        row = {'purok_id': 100 + i, 'barangay_id': 1 + i // 4, 'barangay': f'B{i // 4}', 'name': f'P{i}',
               'confidence': 'medium', 'from_fire_log': False}
        row.update({c: float((i * 7 + j * 3) % 11 + 1) for j, c in enumerate(ff.FEATURE_COLUMNS)})
        if values:
            row.update(values(i))
        rows.append(row)
    return ff.FeatureTable(rows=rows, outlines_version='v', built_at='t', sources={})


def noise_labels(rate=0.08, seed=1):
    rng = np.random.default_rng(seed)
    return {(100 + i, m): 1 for i in range(12) for m in MONTHS if rng.random() < rate}


def xor_table_and_labels(seed=2):
    """Fires depend on an XOR of two inputs, present in every barangay: no linear model can see it."""
    def values(i):
        k = i % 4
        flat = {c: 1.0 for c in ff.FEATURE_COLUMNS}  # every other input the same everywhere
        return dict(flat, share_built_up=float(k & 1), share_tree_cover=float((k >> 1) & 1))
    rng = np.random.default_rng(seed)
    hot = {100 + i for i in range(12) if ((i % 4) & 1) ^ (((i % 4) >> 1) & 1)}
    labels = {(p, m): 1 for p in range(100, 112) for m in MONTHS if rng.random() < (0.6 if p in hot else 0.02)}
    return feature_table(values), labels


class Spy:
    """An estimator that remembers which years it was trained and asked on (X's first column holds the year)."""
    fitted, asked = [], []

    def fit(self, X, y):
        Spy.fitted.append(set(X[:, 0].astype(int)))
        return self

    def predict_proba(self, X):
        Spy.asked.append(set(X[:, 0].astype(int)))
        return np.c_[np.full(len(X), 0.9), np.full(len(X), 0.1)]


class LabelTests(SimpleTestCase):
    def fire(self, when, puroks, barangay=1):
        return ft.FireRecord(when=when, purok_ids=puroks, barangay_id=barangay)

    def test_labels_mark_each_linked_area_once(self):
        july = datetime(2024, 7, 3, 10, 0)
        fires = [self.fire(july, [1, 2]), self.fire(july + timedelta(days=5), [2]), self.fire(july, [])]
        marks, unplaced = ft.labels(fires, {1, 2, 3}, FIRST, FIRST + 48)
        m = 2024 * 12 + 6
        self.assertEqual(marks, {(1, m): 1, (2, m): 1})
        self.assertEqual(unplaced, [fires[2]])

    def test_fires_outside_the_window_are_ignored(self):
        fires = [self.fire(datetime(2022, 12, 31, 23, 0), [1]), self.fire(datetime(2027, 1, 1), [])]
        self.assertEqual(ft.labels(fires, {1}, FIRST, FIRST + 48), ({}, []))

    def test_month_index(self):
        self.assertEqual(ft.month_index(datetime(2024, 2, 1)), 2024 * 12 + 1)


class FireRecordTests(FireSetupMixin, TestCase):
    def test_month_is_manila(self):
        rec = HistoricalRecord.objects.create(barangay=self.home, hazard_type=self.fire, severity_level='Orange',
                                              occurred_at=datetime(2024, 1, 31, 17, 0, tzinfo=dt_timezone.utc))
        rec.puroks.add(self.near)
        HistoricalRecord.objects.create(barangay=self.home, hazard_type=self.flood, severity_level='Orange',
                                        occurred_at=timezone.now())
        fires = ft.fire_records()
        self.assertEqual(len(fires), 1)  # fire only
        self.assertEqual(ft.month_index(fires[0].when), 2024 * 12 + 1)  # 01:00 on 1 February in Manila
        self.assertEqual((fires[0].purok_ids, fires[0].barangay_id), ([self.near.id], self.home.id))
        marks, _ = ft.labels(fires, {self.near.id}, FIRST, FIRST + 48)
        self.assertEqual(marks, {(self.near.id, 2024 * 12 + 1): 1})


class PanelTests(SimpleTestCase):
    def test_panel_columns_are_allowlist_plus_months(self):
        panel = ft.build_panel(feature_table(), {}, MONTHS)
        self.assertEqual(panel.columns, list(ff.FEATURE_COLUMNS) + ['month_sin', 'month_cos'])
        self.assertEqual(panel.X.shape, (12 * 36, len(ff.FEATURE_COLUMNS) + 2))

    def test_panel_rows_and_transforms(self):
        table = feature_table()
        panel = ft.build_panel(table, {(103, FIRST + 5): 1}, MONTHS)
        row = int(np.flatnonzero((panel.purok == 103) & (panel.month == FIRST + 5))[0])
        self.assertEqual(panel.y[row], 1)
        self.assertEqual(int(panel.y.sum()), 1)
        self.assertEqual(panel.barangay[row], 1)
        col = panel.columns.index('buildings_in_area')
        self.assertAlmostEqual(panel.X[row, col], math.log1p(table.rows[3]['buildings_in_area']))
        col = panel.columns.index('median_footprint_m2')
        self.assertEqual(panel.X[row, col], table.rows[3]['median_footprint_m2'])  # not logged
        june = 2 * math.pi * 6 / 12
        self.assertAlmostEqual(panel.X[row, panel.columns.index('month_sin')], math.sin(june))
        self.assertAlmostEqual(panel.X[row, panel.columns.index('month_cos')], math.cos(june))

    def test_dropped_input_is_left_out(self):
        table = feature_table(lambda i: {'population': float('nan')})
        table.dropped = ('population',)
        panel = ft.build_panel(table, {}, MONTHS)
        self.assertNotIn('population', panel.columns)
        self.assertTrue(np.isfinite(panel.X).all())

    def test_missing_value_is_an_error(self):
        table = feature_table(lambda i: {'main_road_m': float('nan')} if i == 2 else {})
        with self.assertRaisesRegex(ValueError, 'main_road_m'):
            ft.build_panel(table, {}, MONTHS)


class CandidateTests(SimpleTestCase):
    def test_grids_follow_the_spec(self):
        c = ft.CANDIDATES
        self.assertEqual(sorted(c), ['adaboost', 'logistic_regression', 'neural_network', 'random_forest', 'xgboost'])
        self.assertEqual([s['C'] for s in c['logistic_regression']], [0.01, 0.1, 1])
        pitt = {f: [s for s in c[f] if s['label'] == 'pittsburgh'] for f in ('random_forest', 'adaboost', 'xgboost')}
        self.assertEqual(len(c['random_forest']), 5)
        self.assertEqual(len(c['adaboost']), 3)
        self.assertEqual(len(c['xgboost']), 17)
        self.assertEqual(len(c['neural_network']), 4)
        xgb = pitt['xgboost'][0]
        self.assertEqual((xgb['learning_rate'], xgb['n_estimators'], xgb['max_depth'], xgb['gamma'],
                          xgb['colsample_bytree'], xgb['min_child_weight']), (0.13, 1500, 3, 0.5, 0.6, 1))
        rf = pitt['random_forest'][0]
        self.assertEqual((rf['n_estimators'], rf['max_depth'], rf['max_features']), (500, 10, 'log2'))
        self.assertEqual(pitt['adaboost'][0]['n_estimators'], 1000)

    def test_no_resampling_or_class_weights(self):
        for family, grid in ft.CANDIDATES.items():
            model = ft.make_model(family, grid[0])
            params = model.get_params(deep=True)
            weights = {k: v for k, v in params.items() if k.endswith('class_weight') or k.endswith('scale_pos_weight')}
            self.assertTrue(all(v in (None, 1) for v in weights.values()), (family, weights))

    def test_every_model_gives_probabilities(self):
        panel = ft.build_panel(feature_table(), noise_labels(), MONTHS)
        for family, grid in SMALL.items():
            p = ft.make_model(family, grid[0]).fit(panel.X, panel.y).predict_proba(panel.X)[:, 1]
            self.assertTrue(((p >= 0) & (p <= 1)).all(), family)


class OofTests(SimpleTestCase):
    def test_oof_never_trains_on_its_own_year(self):
        panel = ft.build_panel(feature_table(), noise_labels(), MONTHS)
        panel.X[:, 0] = panel.month // 12  # the spy reads the year from here
        Spy.fitted, Spy.asked = [], []
        with mock.patch.object(ft, 'make_model', return_value=Spy()):
            p = ft.oof(panel, 'logistic_regression', {'label': 'spy'})
        self.assertEqual(len(Spy.fitted), 3)
        for seen, asked in zip(Spy.fitted, Spy.asked):
            self.assertEqual(len(asked), 1)
            self.assertFalse(seen & asked)
        self.assertTrue(np.allclose(p, 0.1))

    def test_fold_without_fires_scores_finite(self):
        labels = {k: v for k, v in noise_labels(0.1).items() if k[1] // 12 != 2024}  # 2024 has no fire
        panel = ft.build_panel(feature_table(), labels, MONTHS)
        choice = ft.choose(panel)  # the full grid, once
        self.assertEqual(len(choice.candidates), sum(len(g) for g in ft.CANDIDATES.values()))
        for row in choice.candidates:
            self.assertTrue(math.isfinite(row['log_loss']) and math.isfinite(row['brier']), row)

    def test_training_years_without_fires_give_the_base_rate(self):
        labels = {k: v for k, v in noise_labels(0.1).items() if k[1] // 12 == 2025}  # fires only in 2025
        panel = ft.build_panel(feature_table(), labels, MONTHS)
        p = ft.oof(panel, 'xgboost', SMALL['xgboost'][0])
        self.assertTrue(np.isfinite(p).all())
        held_2025 = panel.month // 12 == 2025
        self.assertTrue(np.all(p[held_2025] <= 1e-6 + 1e-12))  # trained on years with no fire


class ChoiceTests(SimpleTestCase):
    def test_tie_keeps_logistic_regression(self):
        panel = ft.build_panel(feature_table(), noise_labels(), MONTHS)
        choice = ft.choose(panel, SMALL)
        self.assertEqual(choice.family, 'logistic_regression')
        self.assertIs(choice.verdict['adopted'], False)
        self.assertTrue(choice.verdict['reasons'])

    def test_clear_signal_can_be_adopted(self):
        table, labels = xor_table_and_labels()
        choice = ft.choose(ft.build_panel(table, labels, MONTHS), SMALL)
        # A tree family or the neural network: both can see an interaction; the point is a real gain is adopted
        self.assertNotEqual(choice.family, 'logistic_regression')
        self.assertIs(choice.verdict['adopted'], True)
        self.assertLess(choice.verdict['high'], 0)
        self.assertLess(choice.verdict['low'], choice.verdict['mean'])

    def test_choice_is_deterministic(self):
        table, labels = xor_table_and_labels()
        panel = ft.build_panel(table, labels, MONTHS)
        a, b = ft.choose(panel, SMALL), ft.choose(panel, SMALL)
        self.assertEqual((a.family, a.settings), (b.family, b.settings))
        self.assertTrue(np.array_equal(a.oof, b.oof))
        self.assertEqual(a.verdict, b.verdict)

    def test_candidate_rows(self):
        panel = ft.build_panel(feature_table(), noise_labels(), MONTHS)
        choice = ft.choose(panel, SMALL)
        self.assertEqual([(r['family'], r['label']) for r in choice.candidates],
                         [(f, s['label']) for f, grid in SMALL.items() for s in grid])
        self.assertEqual(set(choice.candidates[0]), {'family', 'label', 'log_loss', 'brier'})


class CalibrationTests(SimpleTestCase):
    def test_platt_recovers_scale(self):
        rng = np.random.default_rng(3)
        true = rng.uniform(0.01, 0.3, 20000)
        y = (rng.random(20000) < true).astype(int)
        a, b = ft.fit_platt(0.5 * true, y)
        calibrated = ft.apply_platt(0.5 * true, a, b)
        self.assertLess(abs(calibrated.mean() - y.mean()) / y.mean(), 0.10)

    def test_fit_final_predicts_calibrated(self):
        table, labels = xor_table_and_labels()
        panel = ft.build_panel(table, labels, MONTHS)
        choice = ft.choose(panel, SMALL)
        fitted = ft.fit_final(panel, choice)
        p = fitted.predict(panel.X)
        self.assertEqual((fitted.family, fitted.settings), (choice.family, choice.settings))
        self.assertTrue(((p > 0) & (p < 1)).all())
        self.assertLess(abs(p.mean() - panel.y.mean()), 0.05)
