"""
Training the landslide susceptibility model (spec 4.1-4.3, 5.1-5.2, 5.4): a
presence-absence model of where slides start. Mapped typhoon slides are "yes";
ground sampled around them is "no" (3 per slide), so a score is a ranking on
0-1, not a calibrated chance.

Three candidates with fixed settings (the neural network is the default):
  neural_network       five MLPs (32, 16), ReLU, Adam, averaged
  logistic_regression  ridge (C = 1) on the standardised inputs
  xgboost              shallow boosted trees with monotone constraints; it
                       reads a missing road distance as missing

Leave one typhoon out: Egay, Mangkhut, Paeng and Agaton are the folds (plus
Talisay's own spots in the January job). World rows are training-only and
never scored. Rule 1 lets the world rows join only when they help on a held-out
Philippine typhoon; rule 2 keeps the neural network unless another candidate
is clearly better. AUC and its bootstrap are unweighted; the row weights (1
outside, 10 own) enter only the fits and the cut-off walk.

Plain functions on arrays and dicts; no database, no files. The refit loops
take an optional Deadline (the January job's own time limit) and check it
before each fit.
"""
import os
import time
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from apps.history.flood_rules import Cutoffs, auc_gain, auc_score, classify, cutoff_walk
from apps.history.flood_training import in_range
from apps.history.landslide_features import CLIP_COLUMNS, LOG_COLUMNS, TERRAIN_COLUMNS

CANDIDATES = ('neural_network', 'logistic_regression', 'xgboost')
PH_FOLDS = ('egay', 'mangkhut', 'paeng', 'agaton')
WORLD = 'world'
CHALLENGERS = ('logistic_regression', 'xgboost')  # in tie order: on an exact AUC tie the first wins
MONOTONE = {'slope_deg': 1, 'relief_m': 1, 'twi': 1, 'dist_stream_m': -1, 'dist_road_m': -1}  # every other input 0
ROAD = 'dist_road_m'
ROAD_UNKNOWN = 'road_unknown'
MLP_SEEDS = range(5)
# Ruling R59: worker processes that fit the network's seeds side by side (same seeds, same networks); 1 = one by one
def _jobs(value) -> int:
    try:
        return max(1, int(value or 1))
    except ValueError:  # a setting that is not a number: one by one
        return 1


MLP_JOBS = _jobs(os.environ.get('LANDSLIDE_MLP_JOBS'))
ASSESSED_SHARE = 0.5
P90 = 90

NO_POINTS = 'No buildings or roads in this area'
UNLIKE = 'Its ground is unlike the areas the model learned from'
PAST_LIMIT = 'the run passed its {minutes}-minute limit'


class PastDeadline(RuntimeError):
    """
    The run's own time limit passed (final review B3). GitHub stops the
    January job at 360 minutes and then nothing is posted, so the job stops
    itself first and posts a Failed attempt in these words.
    """
    own_words = True  # model_job.failed_reason gives the message without the error's type


@dataclass(frozen=True)
class Deadline:
    """`at` on `clock` (time.monotonic by default); `minutes` is the limit as the error words it."""
    at: float
    minutes: int
    clock: Callable[[], float] = time.monotonic

    def check(self) -> None:
        """Raises PastDeadline once the clock has reached `at`."""
        if self.clock() >= self.at:
            raise PastDeadline(PAST_LIMIT.format(minutes=self.minutes))


def _check(deadline: Deadline | None) -> None:
    if deadline is not None:
        deadline.check()


def design_matrix(table: dict, columns: tuple, medians: dict | None) -> tuple[np.ndarray, tuple]:
    """
    (X, column names): the inputs in column order, distances read as log(1 + m).
    `medians=None` keeps a missing road distance as NaN (xgboost reads it
    natively); otherwise missing values are filled from `medians` and a 0/1
    `road_unknown` input is appended after them. A column `medians` has no
    value for (the training rows had no road distance at all) keeps its NaN;
    `fit` then drops it (ruling R19).
    """
    names, cols = list(columns), []
    for c in columns:
        v = np.asarray(table[c], float)
        if medians is not None and c in medians:
            v = np.where(np.isnan(v), medians[c], v)
        cols.append(np.log1p(v) if c in LOG_COLUMNS else v)
    if medians is not None and ROAD in columns:
        cols.append(np.isnan(np.asarray(table[ROAD], float)).astype(float))
        names.append(ROAD_UNKNOWN)
    return np.column_stack(cols), tuple(names)


def medians_for(name: str, table: dict, columns: tuple, rows=None) -> dict | None:
    """
    `design_matrix`'s `medians` for a candidate: None for xgboost; for the
    others, the median road distance of the training `rows` (all rows if None).
    When no training row has a road distance (every event in them failed the
    road check), there is no median: `{}`, and the fit drops the road (R19).
    """
    if name == 'xgboost':
        return None
    if ROAD not in columns:
        return {}
    road = np.asarray(table[ROAD], float)
    road = road if rows is None else road[rows]
    if np.isnan(road).all():
        return {}
    return {ROAD: float(np.nanmedian(road))}


class _Averaged:
    """Several fitted pipelines whose predicted probabilities are averaged."""

    def __init__(self, models):
        self.models = models

    def predict_proba(self, X):
        return np.mean([m.predict_proba(X) for m in self.models], axis=0)


@dataclass(frozen=True)
class Fitted:
    """
    A fitted candidate and the inputs it reads. `given` is the column list of
    the design matrix `fit` was handed; `columns` is the part the estimator
    was fitted on. `score` takes a matrix in the `given` layout and reads the
    same `columns`, so every caller builds one layout whatever a fit dropped.
    """
    estimator: object
    given: tuple
    columns: tuple

    def matrix(self, X) -> np.ndarray:
        X = np.asarray(X, float)
        if X.ndim != 2 or X.shape[1] != len(self.given):
            raise ValueError(f'Expected a matrix with the {len(self.given)} columns the fit was given '
                             f'({", ".join(self.given)}); got shape {X.shape}')
        return X[:, [self.given.index(c) for c in self.columns]]


def _read_columns(name: str, X: np.ndarray, columns: tuple) -> tuple:
    """
    The inputs a fit reads: all of them, except that a neural-network or
    logistic fit whose training rows have no road distance at all drops
    `dist_road_m` and `road_unknown` for that fit only (ruling R19: the January
    job runs unattended, so one fold without the road clue beats a crash).
    xgboost reads a missing road as missing and keeps it.
    """
    if name == 'xgboost' or ROAD not in columns:
        return columns
    unknown = np.isnan(X[:, columns.index(ROAD)])
    if ROAD_UNKNOWN in columns:
        unknown |= X[:, columns.index(ROAD_UNKNOWN)] == 1
    if not unknown.all():
        return columns
    return tuple(c for c in columns if c not in (ROAD, ROAD_UNKNOWN))


def fit(name: str, X: np.ndarray, y: np.ndarray, w: np.ndarray, columns: tuple, seed: int = 0) -> Fitted:
    """
    One candidate fitted to slides (y = 1) and "no" points (y = 0) with row
    weights w. `columns` names X's columns; the result carries the ones the
    estimator reads (`Fitted.columns`).
    """
    X, columns = np.asarray(X, float), tuple(columns)
    if X.ndim != 2 or X.shape[1] != len(columns):
        raise ValueError(f'X has shape {X.shape} but {len(columns)} column names were given')
    read = _read_columns(name, X, columns)
    estimator = _estimator(name, X[:, [columns.index(c) for c in read]], y, w, read, seed)
    return Fitted(estimator, columns, read)


def _estimator(name: str, X: np.ndarray, y: np.ndarray, w: np.ndarray, columns: tuple, seed: int):
    """The candidate's estimator with its fixed settings, fitted on X (whose columns are `columns`)."""
    y = np.asarray(y, int)
    if name == 'neural_network':
        from apps.history.mlp_fit import fit_one

        states = [10 * seed + s for s in MLP_SEEDS]
        if MLP_JOBS > 1:  # R59: in worker processes, returned in seed order
            from joblib import Parallel, delayed

            models = Parallel(n_jobs=min(MLP_JOBS, len(states)))(delayed(fit_one)(X, y, w, r) for r in states)
        else:
            models = [fit_one(X, y, w, r) for r in states]
        return _Averaged(models)
    if name == 'logistic_regression':
        model = make_pipeline(StandardScaler(), LogisticRegression(C=1.0, max_iter=5000))
        return model.fit(X, y, logisticregression__sample_weight=w)
    if name == 'xgboost':
        from xgboost import XGBClassifier

        constraints = '(' + ','.join(str(MONOTONE.get(c, 0)) for c in columns) + ')'
        model = XGBClassifier(max_depth=3, n_estimators=400, learning_rate=0.05, subsample=0.8, random_state=seed,
                              n_jobs=1, monotone_constraints=constraints, verbosity=0)
        return model.fit(X, y, sample_weight=w)
    raise ValueError(f'Unknown candidate: {name}')


def score(name: str, model: Fitted, X: np.ndarray) -> np.ndarray:
    """
    The candidate's 0-1 output (its predicted probability of a slide). X is in
    the layout `fit` was given; the model reads the columns it was fitted on.
    """
    return np.clip(model.estimator.predict_proba(model.matrix(X))[:, 1], 0, 1)


def _rows(table: dict, mask) -> dict:
    return {k: np.asarray(v)[mask] for k, v in table.items()}


def out_of_fold(name: str, table: dict, columns: tuple, folds_scored: tuple, w: np.ndarray,
                seed: int = 0, deadline: Deadline | None = None) -> np.ndarray:
    """
    A score per row: each fold in `folds_scored` scored by the candidate fitted
    on every other row. Rows of any other fold (the world) stay NaN and are
    always in training. `deadline` is checked before each fit.
    """
    folds, y, w = np.asarray(table['fold']), np.asarray(table['label']), np.asarray(w, float)
    out = np.full(len(y), np.nan)
    for f in folds_scored:
        held = folds == f
        if not held.any():
            continue
        _check(deadline)
        train = ~held
        X, cols = design_matrix(table, columns, medians_for(name, table, columns, train))
        model = fit(name, X[train], y[train], w[train], cols, seed)
        out[held] = score(name, model, X[held])
    return out


def _gain_args(a, b, y, folds, mask):
    """auc_gain's arguments for the gain of score `a` over score `b` on the rows in `mask`."""
    p, n = mask & (y == 1), mask & (y == 0)
    return folds[p], folds[n], a[p], a[n], b[p], b[n]


def world_test(table: dict, columns: tuple, seed: int = 0, reps: int = 1000,
               deadline: Deadline | None = None) -> dict:
    """
    Rule 1: for each held-out Philippine typhoon, the NN fitted on the other
    Philippine folds alone (A) and on them plus every world row (B), every row
    weight 1. The world joins when the pooled AUC gain of B over A has its
    2.5% bound above zero. `deadline` is checked before each fit.
    """
    folds, y = np.asarray(table['fold']), np.asarray(table['label'])
    world = folds == WORLD
    alone = np.full(len(y), np.nan)
    alone[~world] = out_of_fold('neural_network', _rows(table, ~world), columns, PH_FOLDS,
                                np.ones(int((~world).sum())), seed, deadline=deadline)
    joined = out_of_fold('neural_network', table, columns, PH_FOLDS, np.ones(len(y)), seed, deadline=deadline)
    gain, lo, hi = auc_gain(*_gain_args(joined, alone, y, folds, np.isin(folds, PH_FOLDS)),
                            reps=reps, seed=seed)
    return {'joined': bool(lo > 0), 'gain': gain, 'lo': lo, 'hi': hi}


def choose(oof: dict, y, folds, reps: int = 1000, seed: int = 0) -> tuple[str, dict]:
    """
    Rule 2: (chosen, {candidate: {auc, gain_over_nn, lo, hi}}) on the rows
    every candidate scored out of fold (the Philippine and own folds). The NN
    is kept unless logistic regression or xgboost beats it with the 2.5% bound
    of its AUC gain above zero; if both do, the higher pooled AUC wins, and on
    an exact tie logistic regression.
    """
    y, folds = np.asarray(y), np.asarray(folds)
    names = [n for n in CANDIDATES if n in oof]
    scored = np.isfinite(np.column_stack([np.asarray(oof[n], float) for n in names])).all(axis=1)
    nn = np.asarray(oof['neural_network'], float)
    per = {}
    for name in names:
        s = np.asarray(oof[name], float)
        auc = auc_score(s[scored & (y == 1)], s[scored & (y == 0)])
        if name == 'neural_network':
            per[name] = {'auc': auc, 'gain_over_nn': 0.0, 'lo': 0.0, 'hi': 0.0}
            continue
        gain, lo, hi = auc_gain(*_gain_args(s, nn, y, folds, scored), reps=reps, seed=seed)
        per[name] = {'auc': auc, 'gain_over_nn': gain, 'lo': lo, 'hi': hi}
    beaters = [n for n in CHALLENGERS if n in per and per[n]['lo'] > 0]
    if not beaters:
        return 'neural_network', per
    return max(beaters, key=lambda n: per[n]['auc']), per  # max keeps the first of a tie


def point_cutoffs(scores: np.ndarray, y: np.ndarray, w: np.ndarray) -> Cutoffs:
    """
    `cutoff_walk` with each out-of-fold point as a unit: its score as the unit's
    score, its slide weight (1 outside, 10 own, 0 for a "no" point) as the
    spots it holds. Rows without a score (the world) are left out.
    """
    scores, y, w = np.asarray(scores, float), np.asarray(y), np.asarray(w, float)
    keep = np.flatnonzero(np.isfinite(scores))
    return cutoff_walk({int(i): float(scores[i]) for i in keep},
                       {int(i): float(w[i]) if y[i] == 1 else 0.0 for i in keep})


def clip_ranges(train_table: dict, columns: tuple) -> dict:
    """
    {column: (1st, 99th percentile)} of the training rows, for each of
    `columns` in CLIP_COLUMNS. A column no training row has (road distance
    when every event failed the road check) is skipped: the fit does not read
    it (R19), so there is nothing to clip to.
    """
    out = {}
    for c in (c for c in CLIP_COLUMNS if c in columns):
        v = np.asarray(train_table[c], float)
        if not np.isnan(v).all():
            out[c] = tuple(float(p) for p in np.nanpercentile(v, [1, 99]))
    return out


def prepare_talisay(points: dict, train_table: dict, columns: tuple) -> tuple[dict, np.ndarray]:
    """
    (clipped points, in-range mask). A point is in range when every terrain
    input lies inside the training rows' 1st-99th percentile; land cover and
    road distance are clipped to that range instead, so built-up homes and
    road points are scored, not dropped.
    """
    terrain = tuple(c for c in TERRAIN_COLUMNS if c in columns)
    valid = in_range(np.column_stack([np.asarray(points[c], float) for c in terrain]),
                     np.column_stack([np.asarray(train_table[c], float) for c in terrain]))
    clipped = dict(points)
    for c, (lo, hi) in clip_ranges(train_table, columns).items():
        clipped[c] = np.clip(np.asarray(points[c], float), lo, hi)
    return clipped, valid


def purok_scores(point_scores, membership, valid, total_per_purok: dict) -> dict:
    """
    {purok id: {score, valid, total, assessed}}: the 90th percentile of a
    purok's valid points' scores; assessed when at least half its points are
    valid.
    """
    point_scores, valid = np.asarray(point_scores, float), np.asarray(valid, bool)
    idx, pids = (np.asarray(a) for a in membership)
    order = np.argsort(pids, kind='stable')
    uniq, starts = np.unique(pids[order], return_index=True)
    groups = dict(zip(uniq.tolist(), np.split(idx[order], starts[1:])))
    out = {}
    for pid, total in total_per_purok.items():
        members = groups.get(pid, np.zeros(0, int))
        vals = point_scores[members[valid[members]]]
        out[pid] = {'score': float(np.percentile(vals, P90)) if len(vals) else None, 'valid': int(len(vals)),
                    'total': total, 'assessed': bool(total > 0 and len(vals) >= ASSESSED_SHARE * total)}
    return out


def not_assessed_reason(total: int, valid: int) -> str | None:
    """Why a purok gets no class, or None when it is assessed."""
    if total == 0:
        return NO_POINTS
    if valid < ASSESSED_SHARE * total:
        return UNLIKE
    return None


def _resample(rng, folds, y) -> np.ndarray:
    """Bootstrap rows: each fold's slides and its "no" points resampled with replacement to their own sizes."""
    parts = []
    for f in np.unique(folds):
        for label in (1, 0):
            idx = np.flatnonzero((folds == f) & (y == label))
            if len(idx):
                parts.append(rng.choice(idx, size=len(idx), replace=True))
    return np.concatenate(parts)


def stability(name: str, table: dict, columns: tuple, w: np.ndarray, point_X: np.ndarray, membership, valid,
              totals: dict, cutoffs: Cutoffs, reps: int = 200, seed: int = 0,
              deadline: Deadline | None = None) -> list:
    """
    The classes `reps` bootstrap refits give the assessed puroks, with the
    published cut-offs kept fixed. `point_X` is Talisay's design matrix as the
    published model read it (its roads are never missing, so the training
    median does not change it). `deadline` is checked before each refit.
    """
    folds, y, w = np.asarray(table['fold']), np.asarray(table['label']), np.asarray(w, float)
    rng = np.random.default_rng(seed)
    out = []
    for r in range(reps):
        _check(deadline)
        rows = _resample(rng, folds, y)
        X, cols = design_matrix(table, columns, medians_for(name, table, columns, rows))
        model = fit(name, X[rows], y[rows], w[rows], cols, seed=r)
        per = purok_scores(score(name, model, point_X), membership, valid, totals)
        out.append({pid: classify(v['score'], cutoffs) for pid, v in per.items() if v['assessed']})
    return out
