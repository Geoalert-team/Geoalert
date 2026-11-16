import math
from unittest import mock

import numpy as np
from django.test import SimpleTestCase

from apps.history import firth
from apps.history.firth import FitFailed, firth_conditional_logit, firth_logit, flic


def _expit(z):
    return 1 / (1 + np.exp(-z))


class FirthLogitTests(SimpleTestCase):
    def test_intercept_only_matches_the_closed_form(self):
        for k, n, want in ((0, 20, math.log(0.5 / 20.5)), (3, 10, math.log(3.5 / 7.5))):
            y = np.r_[np.ones(k), np.zeros(n - k)]
            fit = firth_logit(np.ones((n, 1)), y)
            self.assertAlmostEqual(fit.coef[0], want, places=6)

    def test_two_by_two_adds_a_half_to_each_cell_even_when_separated(self):
        # a=4 (x=1,y=1), b=0 (x=1,y=0), c=1 (x=0,y=1), d=5 (x=0,y=0)
        x = np.r_[np.ones(4), np.zeros(1), np.zeros(5)]
        y = np.r_[np.ones(4), np.ones(1), np.zeros(5)]
        fit = firth_logit(np.c_[np.ones(10), x], y)
        self.assertAlmostEqual(fit.coef[1], math.log(33), places=6)
        self.assertAlmostEqual(fit.coef[0], math.log(1.5 / 5.5), places=6)

    def test_offset_shifts_the_linear_predictor(self):
        # A column with a known coefficient of 0.7 equals that column moved into the offset.
        # Intercept-only 2x2 with the x column fixed at 0.7 is exact: compare against the
        # model where the same effect is carried by the offset.
        rng = np.random.default_rng(1)
        n = 300
        z = rng.normal(size=n)
        X = np.c_[np.ones(n), z]
        y = (rng.random(n) < _expit(-1 + 0.7 * z)).astype(float)
        plain = firth_logit(X, y)
        # zero offset is no offset
        np.testing.assert_allclose(firth_logit(X, y, offset=np.zeros(n)).coef, plain.coef)
        # a constant offset moves the intercept only: coef[0] falls by exactly that constant
        shifted = firth_logit(X, y, offset=np.full(n, 0.5))
        self.assertAlmostEqual(shifted.coef[0], plain.coef[0] - 0.5, places=6)
        self.assertAlmostEqual(shifted.coef[1], plain.coef[1], places=6)

    def test_non_convergence_raises(self):
        y = np.r_[np.ones(3), np.zeros(7)]
        with mock.patch.object(firth, "MAX_ITER", 1):
            with self.assertRaises(FitFailed):
                firth_logit(np.ones((10, 1)), y)


class FlicTests(SimpleTestCase):
    def test_flic_reproduces_the_observed_rate(self):
        rng = np.random.default_rng(0)
        X = np.c_[np.ones(2000), rng.normal(size=(2000, 2))]
        y = np.zeros(2000)
        y[np.argsort(X[:, 1])[-6:]] = 1           # 6 events, all at high x1
        fixed = flic(X, y, firth_logit(X, y), [0])
        p = _expit(X @ fixed.coef)
        self.assertAlmostEqual(p.mean(), y.mean(), places=10)
        np.testing.assert_allclose(fixed.coef[1:], firth_logit(X, y).coef[1:])

    def test_flic_fits_each_era_intercept_on_its_own_rows(self):
        rng = np.random.default_rng(2)
        n = 1500
        era = np.r_[np.ones(500), np.zeros(1000)]          # 1 = geoalert, 0 = catalogue
        X = np.c_[era, 1 - era, rng.normal(size=n)]
        y = np.zeros(n)
        y[rng.choice(500, 12, replace=False)] = 1
        y[500 + rng.choice(1000, 4, replace=False)] = 1
        fixed = flic(X, y, firth_logit(X, y), [0, 1])
        p = _expit(X @ fixed.coef)
        self.assertAlmostEqual(p[era == 1].mean(), y[era == 1].mean(), places=10)
        self.assertAlmostEqual(p[era == 0].mean(), y[era == 0].mean(), places=10)

    def test_flic_refuses_an_era_without_events(self):
        n = 400
        era = np.r_[np.ones(200), np.zeros(200)]
        X = np.c_[era, 1 - era, np.linspace(-1, 1, n)]
        y = np.zeros(n)
        y[:5] = 1                                           # every event is in the first era
        with self.assertRaises(FitFailed):
            flic(X, y, firth_logit(X, y), [0, 1])


class ConditionalLogitTests(SimpleTestCase):
    GROUPS = np.repeat([0, 1], 3)
    S = np.tile([0.0, 0.5, 1.0], 2)

    def _penalised(self, beta, hit):
        ll = info = 0.0
        for g in (0, 1):
            rows = self.GROUPS == g
            sg = self.S[rows]
            e = np.exp(beta * sg)
            q = e / e.sum()
            ll += beta * sg[hit[rows].astype(bool)][0] - np.log(e.sum())
            info += q @ (sg - q @ sg) ** 2
        return ll + 0.5 * np.log(info)

    def test_conditional_logit_is_stationary_and_finite(self):
        hit = np.array([0, 0, 1, 0, 1, 0])      # day 1 hits s=1.0, day 2 hits s=0.5
        beta = firth_conditional_logit(self.GROUPS, self.S, hit)
        self.assertTrue(np.isfinite(beta) and beta > 0)
        h = 1e-5
        slope = (self._penalised(beta + h, hit) - self._penalised(beta - h, hit)) / (2 * h)
        self.assertLess(abs(slope), 1e-6)

    def test_conditional_logit_stays_finite_when_the_steepest_is_always_hit(self):
        hit = np.array([0, 0, 1, 0, 0, 1])
        beta = firth_conditional_logit(self.GROUPS, self.S, hit)
        self.assertTrue(np.isfinite(beta) and beta > 0)
