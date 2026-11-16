"""The two-part flood and landslide model: p(b, d) = q(d) * a_b.

q(d) is a city-wide "is today an event day?" chance from a small Firth/FLIC logistic regression on
rain (and, for flood, a storm flag); a_b is a fixed per-barangay share. NumPy only: no scikit-learn,
and no Django at import time (hazard_data is imported lazily where a rain window is needed).
"""
import math
from dataclasses import dataclass
from datetime import date
from typing import Mapping, Optional, Sequence

import numpy as np

from apps.history.firth import firth_conditional_logit, firth_logit, flic

FEATURES = {'Flood': ('log1p_r3', 'storm72'), 'Landslide': ('log1p_r3', 'log1p_r14')}
ERA_ORDER = ('geoalert', 'catalogue')
NO_EXPOSURE = 'No exposure figures for this barangay yet.'


def raw_rain(rain: Mapping[date, Optional[float]], day: date) -> Optional[dict]:
    """The r0..r14 sums ending on `day`, or None when a day of the 14 is missing."""
    from apps.history.hazard_data import rain_windows
    return rain_windows(rain, day)


def when_row(hazard: str, rain, storms, day: date) -> Optional[list]:
    """Feature values for one city-day, in FEATURES[hazard] order; None when an input is missing."""
    windows = raw_rain(rain, day)
    if windows is None:
        return None
    row = []
    for name in FEATURES[hazard]:
        if name == 'log1p_r3':
            row.append(math.log1p(windows['r3']))
        elif name == 'log1p_r14':
            row.append(math.log1p(windows['r14']))
        elif name == 'storm72':
            flag = storms.flag(day) if storms is not None else None
            if flag is None:
                return None
            row.append(float(flag))
        else:
            raise ValueError(f'unknown feature {name}')
    return row


def _sigmoid(z):
    return 0.5 * (1.0 + np.tanh(0.5 * z))


@dataclass
class WhenFit:
    features: tuple
    coef: np.ndarray
    intercepts: dict

    def chance(self, X: np.ndarray, era: str = 'geoalert') -> np.ndarray:
        X = np.asarray(X, dtype=float)
        return _sigmoid(self.intercepts[era] + X @ np.asarray(self.coef, dtype=float))


def fit_when(X: np.ndarray, y: np.ndarray, era: Optional[np.ndarray] = None, features: tuple = ()) -> WhenFit:
    """Firth then FLIC with one intercept indicator per era present, then the feature columns."""
    X = np.asarray(X, dtype=float)
    y = np.asarray(y, dtype=float)
    labels = np.array(['geoalert'] * len(y)) if era is None else np.asarray(era)
    present = [e for e in ERA_ORDER if np.any(labels == e)]
    unknown = set(labels.tolist()) - set(ERA_ORDER)
    if unknown:
        raise ValueError(f'unknown era {sorted(unknown)}')
    indicators = np.column_stack([(labels == e).astype(float) for e in present])
    design = np.hstack([indicators, X])
    cols = list(range(len(present)))
    fit = flic(design, y, firth_logit(design, y), cols)
    return WhenFit(features=tuple(features), coef=fit.coef[len(present):].copy(),
                   intercepts={e: float(fit.coef[i]) for i, e in enumerate(present)})


def _total(scores, lam):
    return sum(1.0 - math.exp(-lam * s) for s in scores if s > 0)


def solve_lambda(scores: Mapping[int, float], k: float) -> float:
    """The lambda with sum_b (1 - exp(-lambda * score_b)) = k, by bisection."""
    positive = [s for s in scores.values() if s > 0]
    if k <= 0 or k >= len(positive):
        raise ValueError(f'target {k} must be above 0 and below the {len(positive)} barangays with a positive score')
    lo, hi = 0.0, 1.0
    while _total(positive, hi) <= k:
        hi *= 2.0
        if hi > 1e300:
            raise ValueError('lambda did not bracket')
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if _total(positive, mid) < k:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def _shares(scores: Mapping[int, float], lam: float) -> dict:
    return {b: (1.0 - math.exp(-lam * s) if s > 0 else 0.0) for b, s in scores.items()}


def flood_shares(exposure: Mapping[int, float], k: float):
    lam = solve_lambda(exposure, k)
    return _shares(exposure, lam), lam


def landslide_shares(steep: Mapping[int, float], events: Sequence[set], k: float):
    """(shares, lambda, beta). A day with m hit barangays becomes m groups, each holding that day's
    barangays with one hit, since the conditional logit takes exactly one hit per group."""
    ids = sorted(steep)
    s = np.array([steep[b] for b in ids], dtype=float)
    groups, rows_s, hit = [], [], []
    g = 0
    for hits in events:
        for h in sorted(hits):
            if h not in steep:
                continue
            groups.extend([g] * len(ids))
            rows_s.extend(s)
            hit.extend(b == h for b in ids)
            g += 1
    beta = firth_conditional_logit(np.array(groups), np.array(rows_s), np.array(hit))
    scores = {b: math.exp(beta * steep[b]) for b in ids}
    lam = solve_lambda(scores, k)
    return _shares(scores, lam), lam, beta


@dataclass
class TwoPartFit:
    hazard: str
    when: WhenFit
    shares: dict
    lam: float
    beta: Optional[float]
    training_max: dict

    def to_json(self) -> dict:
        return {
            'kind': 'two_part',
            'hazard': self.hazard,
            'when': {'features': list(self.when.features),
                     'coef': [float(c) for c in self.when.coef],
                     'intercepts': {str(e): float(v) for e, v in self.when.intercepts.items()}},
            'shares': {str(b): float(v) for b, v in self.shares.items()},
            'lam': float(self.lam),
            'beta': None if self.beta is None else float(self.beta),
            'training_max': {str(k): float(v) for k, v in self.training_max.items()},
        }

    @classmethod
    def from_json(cls, data: dict) -> 'TwoPartFit':
        w = data['when']
        return cls(
            hazard=data['hazard'],
            when=WhenFit(features=tuple(w['features']), coef=np.array(w['coef'], dtype=float),
                         intercepts={str(e): float(v) for e, v in w['intercepts'].items()}),
            shares={int(b): float(v) for b, v in data['shares'].items()},
            lam=float(data['lam']),
            beta=None if data.get('beta') is None else float(data['beta']),
            training_max={str(k): float(v) for k, v in data.get('training_max', {}).items()},
        )
