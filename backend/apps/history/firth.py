"""Firth-penalised logistic regression, FLIC and the Firth conditional logit.

NumPy only (no Django, no scikit-learn). Firth's method maximises the log-likelihood plus
0.5 * log|X'WX| (the Jeffreys penalty), which keeps coefficients finite when events are rare or
the classes separate. FLIC (Puhr et al. 2017) keeps the Firth slopes and re-fits each intercept by
ordinary maximum likelihood so the mean predicted chance equals the observed rate.
"""
from dataclasses import dataclass
from typing import Optional, Sequence

import numpy as np

TOL = 1e-8
MAX_ITER = 100
MAX_HALVINGS = 30


class FitFailed(Exception):
    """A fit did not converge or cannot be made."""


@dataclass(frozen=True)
class LogitFit:
    coef: np.ndarray
    iterations: int


def _sigmoid(z):
    return 0.5 * (1.0 + np.tanh(0.5 * z))


def _penalised_loglik(X, y, offset, beta):
    eta = X @ beta + offset
    p = _sigmoid(eta)
    loglik = float(np.sum(y * eta - np.logaddexp(0.0, eta)))
    info = X.T @ (X * (p * (1.0 - p))[:, None])
    sign, logdet = np.linalg.slogdet(info)
    if sign <= 0:
        return -np.inf
    return loglik + 0.5 * logdet


def firth_logit(X: np.ndarray, y: np.ndarray, offset: Optional[np.ndarray] = None) -> LogitFit:
    X = np.asarray(X, dtype=float)
    y = np.asarray(y, dtype=float)
    offset = np.zeros(len(y)) if offset is None else np.asarray(offset, dtype=float)
    beta = np.zeros(X.shape[1])
    current = _penalised_loglik(X, y, offset, beta)
    for iteration in range(1, MAX_ITER + 1):
        p = _sigmoid(X @ beta + offset)
        w = p * (1.0 - p)
        info = X.T @ (X * w[:, None])
        try:
            info_inv = np.linalg.inv(info)
        except np.linalg.LinAlgError as exc:
            raise FitFailed("singular information matrix") from exc
        h = w * np.einsum("ij,jk,ik->i", X, info_inv, X)
        step = info_inv @ (X.T @ (y - p + h * (0.5 - p)))
        scale = 1.0
        for _ in range(MAX_HALVINGS):
            candidate = beta + scale * step
            value = _penalised_loglik(X, y, offset, candidate)
            if np.isfinite(value) and value >= current - 1e-12:
                break
            scale /= 2.0
        else:
            raise FitFailed("step-halving could not improve the penalised likelihood")
        change = float(np.max(np.abs(candidate - beta)))
        beta, current = candidate, value
        if change < TOL:
            return LogitFit(coef=beta, iterations=iteration)
    raise FitFailed(f"no convergence in {MAX_ITER} iterations")


def _ml_intercept(y, offset):
    """Plain maximum-likelihood intercept given an offset (1-D Newton)."""
    rate = y.mean()
    c = float(np.log(rate / (1.0 - rate))) - float(offset.mean())
    for _ in range(MAX_ITER):
        p = _sigmoid(c + offset)
        step = float(np.sum(y - p)) / float(np.sum(p * (1.0 - p)))
        step = max(-5.0, min(5.0, step))
        c += step
        if abs(step) < 1e-13:
            return c
    raise FitFailed("intercept did not converge")


def flic(X: np.ndarray, y: np.ndarray, fit: LogitFit, intercept_columns: Sequence[int]) -> LogitFit:
    X = np.asarray(X, dtype=float)
    y = np.asarray(y, dtype=float)
    intercepts = list(intercept_columns)
    slopes = [j for j in range(X.shape[1]) if j not in intercepts]
    coef = fit.coef.copy()
    shift = X[:, slopes] @ coef[slopes]
    for j in intercepts:
        rows = X[:, j] == 1
        yj = y[rows]
        if yj.sum() == 0 or yj.sum() == len(yj):
            raise FitFailed(f"column {j} rows hold no event or no non-event")
        coef[j] = _ml_intercept(yj, shift[rows])
    return LogitFit(coef=coef, iterations=fit.iterations)


def _group_terms(beta, parts):
    """Sum over groups of (log-likelihood, score, information, d information / d beta)."""
    loglik = score = info = d_info = 0.0
    for s, hit in parts:
        z = beta * s
        top = z.max()
        w = np.exp(z - top)
        total = w.sum()
        q = w / total
        mean = float(q @ s)
        centred = s - mean
        loglik += float(z[hit] - top - np.log(total))
        score += float(s[hit] - mean)
        info += float(q @ centred ** 2)
        d_info += float(q @ centred ** 3)
    return loglik, score, info, d_info


def firth_conditional_logit(groups: np.ndarray, s: np.ndarray, hit: np.ndarray) -> float:
    """Rows are (event day, barangay); on each day the hit row beats the others by exp(beta*s)."""
    groups = np.asarray(groups)
    s = np.asarray(s, dtype=float)
    hit = np.asarray(hit).astype(bool)
    parts = []
    for g in np.unique(groups):
        rows = groups == g
        hits = np.flatnonzero(hit[rows])
        if len(hits) != 1:
            raise FitFailed("each group must have exactly one hit row")
        parts.append((s[rows], int(hits[0])))

    def penalised(beta):
        loglik, _, info, _ = _group_terms(beta, parts)
        return loglik + 0.5 * np.log(info) if info > 0 else -np.inf

    beta = 0.0
    current = penalised(beta)
    if not np.isfinite(current):
        raise FitFailed("scores do not vary within the groups")
    for _ in range(MAX_ITER):
        _, score, info, d_info = _group_terms(beta, parts)
        step = (score + 0.5 * d_info / info) / info
        scale = 1.0
        for _ in range(MAX_HALVINGS):
            candidate = beta + scale * step
            value = penalised(candidate)
            if np.isfinite(value) and value >= current - 1e-12:
                break
            scale /= 2.0
        else:
            raise FitFailed("step-halving could not improve the penalised likelihood")
        change = abs(candidate - beta)
        beta, current = candidate, value
        if change < TOL:
            return float(beta)
    raise FitFailed(f"no convergence in {MAX_ITER} iterations")
