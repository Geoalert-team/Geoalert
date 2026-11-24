"""
Training the flood susceptibility model (spec 3.4, 4.1-4.3, 5.1-5.4): a
presence-background model. Presences are the places floods were reported in
the 2017 UP Mananga survey; the background is every building in the surveyed
floodplain, which the survey could have visited ("target-group background",
Phillips et al. 2009). Background buildings are unknown, not dry, so a score
is a relative susceptibility on 0-1, never a probability of a flood.

Four candidates with fixed settings, the simplest first:
  logistic_regression  presence vs background, unpenalised; refit with a light
                       ridge penalty (C = 1) when the fit separates
  maxent_hinge         hinge features in a ridge logistic regression: the
                       logistic form of MaxEnt (Fithian & Hastie 2013)
  xgboost              shallow boosted trees with monotone constraints
  neural_network       five small MLPs (8 hidden units), averaged

Presences and background carry equal total weight. Inputs are standardised
on each training set only. Plain functions on arrays; no database.
"""
import warnings

import numpy as np
from sklearn.exceptions import ConvergenceWarning
from sklearn.linear_model import LogisticRegression
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import SplineTransformer, StandardScaler

from apps.history.fire_features import points_inside, polygons_to_metres, to_metres
from apps.history.flood_rules import classify, cutoff_walk

CANDIDATES = ('logistic_regression', 'maxent_hinge', 'xgboost', 'neural_network')
FOLDS = {'Lawaan III': 0, 'Biasong': 1, 'Lawaan II': 2, 'Pooc': 3, 'Dumlog': 4, 'San Isidro': 4}
MONOTONE = {'noah25_class': 1, 'noah5_class': 1, 'depression_m': 1, 'rel_height_river_m': -1, 'dist_river_m': -1,
            'built_share': 0}
LOG_COLUMNS = ('dist_river_m',)
METRIC_SRID = 32651
BUFFER_M = 300
ASSESSED_SHARE = 0.5
SEPARATION_COEF = 20
MLP_SEEDS = range(5)

NO_BUILDINGS = 'No buildings in this area'
OUTSIDE = 'Outside the surveyed floodplain'
UNLIKE = 'Its ground is unlike the surveyed floodplain'
NO_NOAH = 'No NOAH flood model information here'


def design_matrix(table: dict, columns: tuple) -> np.ndarray:
    """The model inputs in column order; the river distance is read as log(1 + m)."""
    return np.column_stack([np.log1p(np.asarray(table[c], float)) if c in LOG_COLUMNS
                            else np.asarray(table[c], float) for c in columns])


def domain(lon, lat, spots: list, city, buffer_m: float = BUFFER_M):
    """
    (mask, area): which points lie in the evidence domain, the convex hull of
    the positive spots buffered by buffer_m (metres, UTM 51N) and clipped to
    the city, and that area (SRID 4326).
    """
    from django.contrib.gis.geos import MultiPoint, Point

    hull = MultiPoint([Point(s['lon'], s['lat'], srid=4326) for s in spots if s['positive']], srid=4326).convex_hull
    hull.srid = 4326
    area = hull.transform(METRIC_SRID, clone=True).buffer(buffer_m, 16)
    area = area.intersection(city.transform(METRIC_SRID, clone=True))
    area.srid = METRIC_SRID
    area.transform(4326)
    polys = [area] if area.geom_type == 'Polygon' else list(area)
    rings = [[list(ring.coords) for ring in poly] for poly in polys]
    pts = np.c_[np.asarray(lon, float), np.asarray(lat, float)]
    return points_inside(polygons_to_metres(rings), to_metres(pts)), area


def in_range(X: np.ndarray, X_background: np.ndarray, lo: float = 1, hi: float = 99) -> np.ndarray:
    """Rows whose every input lies within the background's lo-hi percentile range."""
    low = np.percentile(X_background, lo, axis=0)
    high = np.percentile(X_background, hi, axis=0)
    return ((X >= low) & (X <= high)).all(axis=1)


class _Averaged:
    """Several fitted pipelines whose predicted probabilities are averaged."""

    def __init__(self, models):
        self.models = models

    def predict_proba(self, X):
        return np.mean([m.predict_proba(X) for m in self.models], axis=0)


def _logistic(X, y, w):
    model = make_pipeline(StandardScaler(), LogisticRegression(C=np.inf, max_iter=5000))  # C = inf: no penalty
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter('always', ConvergenceWarning)
        model.fit(X, y, logisticregression__sample_weight=w)
    fitted = model.predict_proba(X)[:, 1]
    separated = (any(issubclass(c.category, ConvergenceWarning) for c in caught)
                 or np.abs(model[-1].coef_).max() > SEPARATION_COEF
                 or fitted[y == 1].min() > fitted[y == 0].max())  # the fit splits the two groups completely
    if separated:
        model = make_pipeline(StandardScaler(), LogisticRegression(C=1.0, max_iter=5000))
        model.fit(X, y, logisticregression__sample_weight=w)
    model.separation_guard = bool(separated)
    return model


def fit(name: str, X: np.ndarray, y: np.ndarray, w: np.ndarray, columns: tuple, seed: int = 0):
    """One candidate fitted to presences (y = 1) and background (y = 0) with weights w."""
    if name == 'logistic_regression':
        return _logistic(X, y, w)
    if name == 'maxent_hinge':
        model = make_pipeline(StandardScaler(), SplineTransformer(degree=1, n_knots=5, knots='quantile'),
                              LogisticRegression(C=1.0, max_iter=5000))
        return model.fit(X, y, logisticregression__sample_weight=w)
    if name == 'xgboost':
        from xgboost import XGBClassifier

        constraints = '(' + ','.join(str(MONOTONE.get(c, 0)) for c in columns) + ')'
        model = XGBClassifier(max_depth=2, n_estimators=300, learning_rate=0.05, subsample=0.8, random_state=seed,
                              monotone_constraints=constraints, n_jobs=1, verbosity=0)
        return model.fit(X, y, sample_weight=w)
    if name == 'neural_network':
        models = []
        for s in MLP_SEEDS:
            m = make_pipeline(StandardScaler(), MLPClassifier(hidden_layer_sizes=(8,), alpha=1e-3,
                                                              early_stopping=False, max_iter=2000,
                                                              random_state=seed * 10 + s))
            with warnings.catch_warnings():
                warnings.simplefilter('ignore', ConvergenceWarning)
                m.fit(X, y, mlpclassifier__sample_weight=w)
            models.append(m)
        return _Averaged(models)
    raise ValueError(f'Unknown candidate: {name}')


def score(name: str, model, X: np.ndarray) -> np.ndarray:
    """The candidate's 0-1 output (its predicted probability from the weighted fit)."""
    return np.clip(model.predict_proba(X)[:, 1], 0, 1)


def weights(n_presence: int, n_background: int) -> np.ndarray:
    """Presences and background with equal total weight."""
    return np.r_[np.full(n_presence, n_background / max(n_presence, 1)), np.ones(n_background)]


def out_of_fold(name, X_p, X_b, folds_p, folds_b, columns: tuple, seed: int = 0):
    """Each fold's presences and background scored by the candidate fitted without that fold."""
    s_p, s_b = np.zeros(len(X_p)), np.zeros(len(X_b))
    for f in np.unique(np.r_[folds_p, folds_b]):
        tp, tb = folds_p != f, folds_b != f
        X = np.r_[X_p[tp], X_b[tb]]
        y = np.r_[np.ones(tp.sum()), np.zeros(tb.sum())]
        model = fit(name, X, y, weights(int(tp.sum()), int(tb.sum())), columns, seed)
        if (~tp).any():
            s_p[~tp] = score(name, model, X_p[~tp])
        if (~tb).any():
            s_b[~tb] = score(name, model, X_b[~tb])
    return s_p, s_b


def purok_scores(building_scores, membership, valid, total_per_purok: dict) -> dict:
    """
    {purok id: {score, valid, total, assessed}}: the mean score of a purok's
    valid buildings; assessed when at least half its buildings are valid.
    """
    b_idx, p_ids = membership
    sums, counts = {}, {}
    for b, p in zip(b_idx, p_ids):
        if valid[b]:
            sums[p] = sums.get(p, 0.0) + float(building_scores[b])
            counts[p] = counts.get(p, 0) + 1
    out = {}
    for pid, total in total_per_purok.items():
        n = counts.get(pid, 0)
        out[pid] = {'score': sums[pid] / n if n else None, 'valid': n, 'total': total,
                    'assessed': bool(total > 0 and n >= ASSESSED_SHARE * total)}
    return out


def not_assessed_reason(total: int, in_domain: int, valid: int):
    """Why a purok gets no class, or None when it is assessed."""
    if total == 0:
        return NO_BUILDINGS
    if in_domain < ASSESSED_SHARE * total:
        return OUTSIDE
    if valid < ASSESSED_SHARE * total:
        return UNLIKE
    return None


def noah_fallback(noah25, near_noah, membership, total_per_purok: dict, spot_purok: dict) -> dict:
    """
    NOAH-based classes (spec 5.3): a purok's score is its buildings' mean NOAH
    25-year class / 3; it is covered when at least half its buildings are in
    or within 300 m of a NOAH polygon; cut-offs by the same walk on the spots.
    """
    noah25 = np.asarray(noah25, float)
    covered = (noah25 > 0) | np.asarray(near_noah, bool)
    b_idx, p_ids = membership
    sums, near = {}, {}
    for b, p in zip(b_idx, p_ids):
        sums[p] = sums.get(p, 0.0) + noah25[b] / 3
        near[p] = near.get(p, 0) + int(covered[b])
    scores, areas = {}, {}
    for pid, total in total_per_purok.items():
        if total == 0:
            areas[pid] = {'score': None, 'level': None, 'not_assessed_reason': NO_BUILDINGS}
        elif near.get(pid, 0) < ASSESSED_SHARE * total:
            areas[pid] = {'score': None, 'level': None, 'not_assessed_reason': NO_NOAH}
        else:
            scores[pid] = round(sums.get(pid, 0.0) / total, 6)
    cutoffs = cutoff_walk(scores, spot_purok)
    for pid, s in scores.items():
        areas[pid] = {'score': s, 'level': classify(s, cutoffs), 'not_assessed_reason': None}
    return {'areas': areas, 'cutoffs': cutoffs}


def stability(name, X_p, X_b, building_X, membership, valid, total_per_purok: dict, cutoffs, columns: tuple,
              reps: int = 200, seed: int = 0) -> list:
    """
    The classes each of `reps` bootstrap refits gives the assessed puroks,
    with the published cut-offs kept fixed (spec 5.4).
    """
    rng = np.random.default_rng(seed)
    out = []
    for r in range(reps):
        ip = rng.choice(len(X_p), size=len(X_p), replace=True)
        ib = rng.choice(len(X_b), size=len(X_b), replace=True)
        X = np.r_[X_p[ip], X_b[ib]]
        y = np.r_[np.ones(len(ip)), np.zeros(len(ib))]
        model = fit(name, X, y, weights(len(ip), len(ib)), columns, seed=r)
        per = purok_scores(score(name, model, building_X), membership, valid, total_per_purok)
        out.append({pid: classify(v['score'], cutoffs) for pid, v in per.items() if v['assessed']})
    return out
