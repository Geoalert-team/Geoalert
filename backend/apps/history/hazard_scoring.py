"""Scores saved flood and landslide fits with NumPy only: no scikit-learn, no xgboost.

The saved fits come from hazard_models.export_logistic and two_part.TwoPartFit.to_json.
"""
import numpy as np

from apps.history.two_part import TwoPartFit


class FitError(Exception):
    """A saved fit cannot score the rows it was given; the message says why."""


def _sigmoid(z):
    return 0.5 * (1.0 + np.tanh(0.5 * z))


def score_logistic(fit: dict, X: np.ndarray) -> np.ndarray:
    """Median imputation, log1p on the rain columns, standardising, then the logistic regression."""
    X = np.array(X, dtype=float)
    medians = np.asarray(fit['medians'], dtype=float)
    if X.ndim != 2 or X.shape[1] != len(medians):
        raise FitError(f'expected {len(medians)} feature columns, got shape {X.shape}')
    missing = np.isnan(X)
    X = np.where(missing, medians, X)
    cols = list(fit['log_columns'])
    X[:, cols] = np.log1p(X[:, cols])
    Z = (X - np.asarray(fit['mean'], dtype=float)) / np.asarray(fit['scale'], dtype=float)
    return _sigmoid(float(fit['intercept']) + Z @ np.asarray(fit['coef'], dtype=float))


def score_two_part(fit: dict, when_X: np.ndarray, day_index: np.ndarray, barangay_ids: np.ndarray) -> np.ndarray:
    """q(day) from the city-wide 'when' part, times the barangay's share, one value per row."""
    model = TwoPartFit.from_json(fit)
    q = model.when.chance(np.asarray(when_X, dtype=float))
    day_index = np.asarray(day_index, dtype=int)
    ids = np.asarray(barangay_ids, dtype=int)
    absent = sorted({int(b) for b in ids.tolist()} - set(model.shares))
    if absent:
        raise FitError(f'no share for barangay {absent[0]}')
    share = np.array([model.shares[int(b)] for b in ids.tolist()], dtype=float)
    return q[day_index] * share
