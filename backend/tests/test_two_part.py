import json
import math
import os
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
from django.test import SimpleTestCase

from apps.history.storms import StormDays
from apps.history.two_part import (
    FEATURES, NO_EXPOSURE, TwoPartFit, WhenFit, fit_when, flood_shares, landslide_shares, raw_rain,
    solve_lambda, when_row)


def make_rain(first, last, value=1.0, overrides=None):
    out, d = {}, first
    while d <= last:
        out[d] = value
        d += timedelta(days=1)
    out.update(overrides or {})
    return out


def storms(first, last, stormy=()):
    return StormDays(days={d: ('S1', 'KIKO', 100.0) for d in stormy}, first_day=first, last_day=last)


class WhenRowTests(SimpleTestCase):
    def setUp(self):
        self.rain = make_rain(date(2025, 10, 1), date(2025, 11, 4), 2.0,
                              {date(2025, 11, 2): 10.0, date(2025, 11, 3): 20.0, date(2025, 11, 4): 5.0})

    def test_when_row_uses_trailing_windows_and_the_storm_flag(self):
        st = storms(date(2025, 10, 1), date(2025, 11, 4), [date(2025, 11, 4)])
        row = when_row('Flood', self.rain, st, date(2025, 11, 4))
        self.assertEqual(row, [math.log1p(35.0), 1.0])
        st_short = storms(date(2025, 10, 1), date(2025, 11, 3))
        self.assertIsNone(when_row('Flood', self.rain, st_short, date(2025, 11, 4)))

    def test_landslide_when_row_needs_14_days(self):
        row = when_row('Landslide', self.rain, None, date(2025, 11, 4))
        self.assertEqual(row, [math.log1p(35.0), math.log1p(35.0 + 11 * 2.0)])
        self.assertIsNone(when_row('Landslide', self.rain, None, date(2025, 10, 10)))
        self.assertEqual(raw_rain(self.rain, date(2025, 11, 4))['r3'], 35.0)
        self.assertEqual(FEATURES['Flood'], ('log1p_r3', 'storm72'))


class FitWhenTests(SimpleTestCase):
    def data(self, n=600, seed=1):
        rng = np.random.default_rng(seed)
        X = np.c_[rng.normal(2, 1, n), rng.integers(0, 2, n)]
        y = (rng.random(n) < 1 / (1 + np.exp(-(-5 + 0.8 * X[:, 0] + 1.0 * X[:, 1])))).astype(float)
        return X, y

    def test_fit_when_flood_has_one_intercept_and_reproduces_the_rate(self):
        X, y = self.data()
        fit = fit_when(X, y)
        self.assertEqual(list(fit.intercepts), ['geoalert'])
        self.assertAlmostEqual(float(fit.chance(X).mean()), float(y.mean()), places=6)

    def test_fit_when_landslide_has_an_intercept_per_era_and_uses_geoalert_by_default(self):
        X, y = self.data()
        era = np.array(['catalogue'] * 300 + ['geoalert'] * 300)
        fit = fit_when(X, y, era)
        self.assertEqual(list(fit.intercepts), ['geoalert', 'catalogue'])
        for name, rows in (('geoalert', era == 'geoalert'), ('catalogue', era == 'catalogue')):
            self.assertAlmostEqual(float(fit.chance(X[rows], name).mean()), float(y[rows].mean()), places=6)
        np.testing.assert_allclose(fit.chance(X), fit.chance(X, 'geoalert'))


class SharesTests(SimpleTestCase):
    def test_solve_lambda_hits_the_target_and_keeps_the_ranking(self):
        shares, lam = flood_shares({1: 10.0, 2: 40.0, 3: 0.0, 4: 100.0}, k=1.5)
        self.assertAlmostEqual(sum(shares.values()), 1.5, places=9)
        self.assertEqual(shares[3], 0.0)
        self.assertEqual(sorted(shares, key=shares.get), [3, 1, 2, 4])
        self.assertGreater(lam, 0)

    def test_solve_lambda_refuses_an_impossible_target(self):
        with self.assertRaises(ValueError):
            solve_lambda({1: 1.0, 2: 2.0, 3: 3.0, 4: 0.0}, 3.0)

    def test_landslide_shares_rank_steeper_barangays_higher(self):
        steep = {1: 0.0, 2: 0.1, 3: 0.3, 4: 0.8}
        shares, lam, beta = landslide_shares(steep, [{4}, {4}, {3}, {4}], k=1.0)
        self.assertGreater(beta, 0)
        self.assertAlmostEqual(sum(shares.values()), 1.0, places=9)
        self.assertEqual(sorted(shares, key=shares.get), [1, 2, 3, 4])

    def test_a_day_with_several_barangays_becomes_several_groups(self):
        steep = {1: 0.0, 2: 0.1, 3: 0.3, 4: 0.8}
        shares, _, beta = landslide_shares(steep, [{3, 4}, {4}], k=1.5)
        self.assertGreater(beta, 0)
        self.assertAlmostEqual(sum(shares.values()), 1.5, places=9)


class SavedFitTests(SimpleTestCase):
    def test_round_trip_json(self):
        when = WhenFit(('log1p_r3', 'storm72'), np.array([0.7, 1.1]), {'geoalert': -6.0, 'catalogue': -5.0})
        fit = TwoPartFit('Flood', when, {1: 0.2, 2: 0.9}, 0.05, None, {'r3': 120.0, 'r14': 300.0})
        text = json.dumps(fit.to_json(), allow_nan=False)
        data = json.loads(text)
        self.assertEqual(data['kind'], 'two_part')
        self.assertEqual(set(data['shares']), {'1', '2'})
        back = TwoPartFit.from_json(data)
        self.assertEqual(back.shares, {1: 0.2, 2: 0.9})
        self.assertIsNone(back.beta)
        self.assertEqual(back.training_max, {'r3': 120.0, 'r14': 300.0})
        X = np.array([[3.0, 1.0], [5.0, 0.0]])
        np.testing.assert_allclose(back.when.chance(X), fit.when.chance(X))
        np.testing.assert_allclose(back.when.chance(X, 'catalogue'), fit.when.chance(X, 'catalogue'))

    def test_no_sklearn_import(self):
        backend = Path(__file__).resolve().parent.parent
        code = ("import django; django.setup(); import sys; import apps.history.two_part; "
                "print('sklearn' in sys.modules)")
        env = dict(os.environ, PYTHONPATH=os.pathsep.join(filter(None, [str(backend), os.environ.get('PYTHONPATH', '')])))
        out = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True, env=env, cwd=backend)
        self.assertEqual(out.stdout.strip(), 'False', out.stderr)

    def test_message_constant(self):
        self.assertEqual(NO_EXPOSURE, 'No exposure figures for this barangay yet.')
