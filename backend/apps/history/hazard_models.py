"""Candidate models, rolling-origin folds, the counting benchmark and scores for flood and landslide."""
import json
import math
from calendar import monthrange
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime

import numpy as np
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, log_loss, roc_auc_score
from sklearn.pipeline import make_pipeline as _make_pipeline
from sklearn.preprocessing import FunctionTransformer, StandardScaler
from xgboost import XGBClassifier

from apps.history.hazard_data import (
    DATA_DIR, HAZARDS, MANILA, RAIN_FEATURES, STUDY_END, STUDY_START, TERRAIN_FEATURES, Dataset, build_dataset,
    load_records, records_signature)
from apps.history.hazard_scenarios import period_chance, scenario_dates
from apps.history.model_forecast import level_for
from apps.history.rain import complete_years

CANDIDATES = ('logistic_regression', 'random_forest', 'xgboost')
FOLDS = [((2021, 2022), 2023), ((2021, 2022, 2023), 2024), ((2021, 2022, 2023, 2024), 2025)]
PRIOR_DAYS = 30
ALARM_RATE = 0.01
BLOCK_DAYS = 7      # bootstrap block length in days; the report states this same value

# Feature name -> sign the model must respect (0 = free).
MONOTONE: dict[str, dict[str, int]] = {
    'Flood': {**{f: 1 for f in RAIN_FEATURES},
              'hand_lt2': 1, 'hand_lt5': 1, 'elev_lt10': 1, 'water_200': 1, 'coast_500': 0,
              'built_density': 1},
    'Landslide': {f: 1 for f in RAIN_FEATURES + TERRAIN_FEATURES['Landslide']},
}

RF_SETTINGS = dict(n_estimators=500, max_depth=3, min_samples_leaf=200, max_features='sqrt', random_state=0)
XGB_SETTINGS = dict(n_estimators=200, max_depth=2, learning_rate=0.05, subsample=0.8, reg_lambda=1,
                    min_child_weight=0.1, scale_pos_weight=1, random_state=0, objective='binary:logistic')
LR_SETTINGS = dict(C=1.0, l1_ratio=0.0, solver='lbfgs', max_iter=2000)   # l1_ratio=0 is plain L2

# Merged over a model's settings by make_pipeline. Empty in production; tests shrink the trees with it.
SPEED_OVERRIDES: dict[str, dict] = {}


def _monotone_vector(hazard: str) -> list[int]:
    signs = MONOTONE[hazard]
    return [signs[f] for f in RAIN_FEATURES + TERRAIN_FEATURES[hazard]]


def _imputer():
    # keep_empty_features: an all-NaN training column must stay, or later columns shift out of line.
    return SimpleImputer(strategy='median', keep_empty_features=True)


def make_pipeline(name: str, hazard: str):
    settings = {'logistic_regression': LR_SETTINGS, 'random_forest': RF_SETTINGS,
                'xgboost': XGB_SETTINGS}[name]
    settings = {**settings, **SPEED_OVERRIDES.get(name, {})}
    if name == 'logistic_regression':
        log_rain = ColumnTransformer(
            [('log_rain', FunctionTransformer(np.log1p), list(range(len(RAIN_FEATURES))))],
            remainder='passthrough')
        return _make_pipeline(_imputer(), log_rain, StandardScaler(), LogisticRegression(**settings))
    if name == 'random_forest':
        return _make_pipeline(_imputer(),
                              RandomForestClassifier(monotonic_cst=_monotone_vector(hazard), **settings))
    if name == 'xgboost':
        return _make_pipeline(_imputer(),
                              XGBClassifier(monotone_constraints=tuple(_monotone_vector(hazard)), **settings))
    raise ValueError(f'Unknown candidate: {name}')


def _months(ds: Dataset) -> np.ndarray:
    return ds.day.astype('datetime64[M]').astype(int) % 12


def no_skill(train: Dataset) -> float:
    return float(train.y.mean())


def benchmark_probs(train: Dataset, test: Dataset) -> np.ndarray:
    """Barangay-by-calendar-month event rate, shrunk toward the training prevalence. Training rows only."""
    pi = no_skill(train)
    months = _months(train)
    days_in_month = {m: len(np.unique(train.day[months == m])) for m in np.unique(months)}
    events: dict[tuple[int, int], int] = {}
    for b, m, y in zip(train.barangay_id, months, train.y):
        if y == 1:
            events[(int(b), int(m))] = events.get((int(b), int(m)), 0) + 1
    return np.array([(events.get((int(b), int(m)), 0) + pi * PRIOR_DAYS) / (days_in_month.get(m, 0) + PRIOR_DAYS)
                     for b, m in zip(test.barangay_id, _months(test))])


def scores(y, p) -> dict:
    y = np.asarray(y).astype(int)
    p = np.asarray(p, dtype=float)
    both = len(np.unique(y)) == 2
    return {
        'log_loss': float(log_loss(y, np.clip(p, 1e-6, 1 - 1e-6), labels=[0, 1])),
        'brier': float(brier_score_loss(y, p)),
        'roc_auc': float(roc_auc_score(y, p)) if both else None,
        'pr_auc': float(average_precision_score(y, p)) if both else None,
        'n': int(len(y)),
        'positives': int(y.sum()),
        'prevalence': float(y.mean()),
    }


def threshold_metrics(p_train, y_test, p_test, rate: float = ALARM_RATE) -> dict:
    """Flag the top `rate` share by the training-set cutoff, then count on the test rows."""
    cutoff = float(np.quantile(p_train, 1 - rate))
    y = np.asarray(y_test).astype(int)
    flagged = np.asarray(p_test) >= cutoff
    tp = int((flagged & (y == 1)).sum())
    fp = int((flagged & (y == 0)).sum())
    fn = int((~flagged & (y == 1)).sum())
    tn = int((~flagged & (y == 0)).sum())
    return {'cutoff': cutoff, 'tp': tp, 'fp': fp, 'fn': fn, 'tn': tn,
            'precision': tp / (tp + fp) if tp + fp else None,
            'recall': tp / (tp + fn) if tp + fn else None}


# ---- Calibration, bootstrap and selection ----

@dataclass
class Fitted:
    name: str
    pipeline: object
    platt: tuple[float, float] | None


def _logit(p) -> np.ndarray:
    c = np.clip(np.asarray(p, dtype=float), 1e-6, 1 - 1e-6)
    return np.log(c / (1 - c))


def _platt_fit(p, y) -> tuple[float, float]:
    lr = LogisticRegression(C=1e6, max_iter=1000).fit(_logit(p).reshape(-1, 1), np.asarray(y).astype(int))
    return float(lr.coef_[0, 0]), float(lr.intercept_[0])


def fit_candidate(name: str, hazard: str, train: Dataset) -> Fitted:
    """Fit on all training years. Trees also get a Platt mapping fitted on the last training year."""
    if name == 'logistic_regression':
        return Fitted(name, make_pipeline(name, hazard).fit(train.X, train.y), None)
    years = train.years
    last = years.max()
    in_last = years == last
    if train.y[in_last].sum() > 0 and train.y[~in_last].sum() > 0:
        before, calib = train.subset(~in_last), train.subset(in_last)
        base = make_pipeline(name, hazard).fit(before.X, before.y)
        a, b = _platt_fit(base.predict_proba(calib.X)[:, 1], calib.y)
        if a > 0:      # a flat or reversed mapping would flip the model's ranking, so run uncalibrated
            return Fitted(name, make_pipeline(name, hazard).fit(train.X, train.y), (a, b))
    return Fitted(name, make_pipeline(name, hazard).fit(train.X, train.y), None)


def predict(f: Fitted, X) -> np.ndarray:
    p = f.pipeline.predict_proba(X)[:, 1]
    if f.platt is None:
        return p
    a, b = f.platt
    return 1 / (1 + np.exp(-(a * _logit(p) + b)))


def _year_blocks(days) -> list[tuple[int, int, list[np.ndarray]]]:
    """Per calendar year: (year, distinct days, moving BLOCK_DAYS-day blocks of row indices)."""
    days = np.asarray(days).astype('datetime64[D]')
    years = days.astype('datetime64[Y]').astype(int) + 1970
    out = []
    for year in np.unique(years):
        rows = np.flatnonzero(years == year)
        order = rows[np.argsort(days[rows], kind='stable')]
        sorted_days = days[order]
        distinct = np.unique(sorted_days)
        if len(distinct) < BLOCK_DAYS:
            blocks = [rows]
        else:
            last_day = distinct[-1]      # never past the data, so a partial year gets no truncated blocks
            blocks = []
            for s in distinct[distinct + (BLOCK_DAYS - 1) <= last_day]:
                lo = np.searchsorted(sorted_days, s, side='left')
                hi = np.searchsorted(sorted_days, s + BLOCK_DAYS, side='left')
                blocks.append(order[lo:hi])
        out.append((int(year), len(distinct), blocks))
    return out


def day_blocks(days, block: int = BLOCK_DAYS) -> list[np.ndarray]:
    """Moving blocks of `block` consecutive days inside one year; all barangays of those days stay together."""
    if block != BLOCK_DAYS:
        raise ValueError(f'only {BLOCK_DAYS}-day blocks are supported')
    return [b for _, _, blocks in _year_blocks(days) for b in blocks]


def _resample(rng, year_blocks) -> list[np.ndarray]:
    """One replicate: per year, ceil(distinct days / BLOCK_DAYS) blocks drawn with replacement; rows per year."""
    draws = []
    for _, n_days, blocks in year_blocks:
        picks = rng.integers(0, len(blocks), size=-(-n_days // BLOCK_DAYS))
        draws.append(np.concatenate([blocks[i] for i in picks]))
    return draws


def _interval(values) -> tuple[float, float] | None:
    if len(values) == 0:
        return None
    lo, hi = np.percentile(values, [2.5, 97.5])
    return float(lo), float(hi)


def bootstrap(days, y, preds: dict[str, np.ndarray], reps: int = 1000, seed: int = 0) -> dict:
    y = np.asarray(y).astype(int)
    rng = np.random.default_rng(seed)
    year_blocks = _year_blocks(days)
    names = list(preds)
    p = {n: np.asarray(preds[n], dtype=float) for n in names}
    ll = {n: -(y * np.log(np.clip(p[n], 1e-6, 1 - 1e-6)) + (1 - y) * np.log(1 - np.clip(p[n], 1e-6, 1 - 1e-6)))
          for n in names}
    br = {n: (p[n] - y) ** 2 for n in names}
    pooled = {n: {'log_loss': [], 'brier': [], 'pr_auc': []} for n in names}
    per_year = {n: np.empty((reps, len(year_blocks))) for n in names}
    for r in range(reps):
        draws = _resample(rng, year_blocks)
        idx = np.concatenate(draws)
        yr = y[idx]
        has_both = 0 < yr.sum() < len(yr)
        for n in names:
            pooled[n]['log_loss'].append(ll[n][idx].mean())
            pooled[n]['brier'].append(br[n][idx].mean())
            if has_both:
                pooled[n]['pr_auc'].append(average_precision_score(yr, p[n][idx]))
            per_year[n][r] = [ll[n][d].mean() for d in draws]
    intervals = {n: {m: _interval(v) for m, v in pooled[n].items()} for n in names}
    diff = {(a, b): _interval(per_year[a].mean(axis=1) - per_year[b].mean(axis=1))
            for a in names for b in names if a != b}
    return {'intervals': intervals, 'diff': diff}


def select_winner(mean_log_loss: dict[str, float], diff: dict) -> str:
    """The simplest candidate whose log loss is not distinguishable from the best one."""
    leader = min(mean_log_loss, key=mean_log_loss.get)
    for c in CANDIDATES:
        if c not in mean_log_loss:
            continue
        if c == leader:
            return leader
        if (c, leader) in diff:
            lo, hi = diff[(c, leader)]
        elif (leader, c) in diff:
            lo, hi = -diff[(leader, c)][1], -diff[(leader, c)][0]
        else:
            continue
        if lo <= 0 <= hi:
            return c
    return leader


def calibration(y, p, years, days=None, reps: int = 1000, seed: int = 0) -> dict:
    y = np.asarray(y).astype(int)
    p = np.asarray(p, dtype=float)
    years = np.asarray(years)
    per_year = [{'year': int(yr), 'observed': int(y[years == yr].sum()), 'expected': float(p[years == yr].sum())}
                for yr in np.unique(years)]
    slope, slope_ci = None, None
    if len(np.unique(y)) == 2 and np.ptp(_logit(p)) > 0:      # constant p leaves the slope unidentified
        slope = _platt_fit(p, y)[0]
        if days is not None:
            rng = np.random.default_rng(seed)
            year_blocks = _year_blocks(days)
            slopes = []
            for _ in range(reps):
                idx = np.concatenate(_resample(rng, year_blocks))
                if len(np.unique(y[idx])) == 2:
                    slopes.append(_platt_fit(p[idx], y[idx])[0])
            slope_ci = _interval(slopes)
    return {'per_year': per_year, 'slope': slope, 'slope_ci': slope_ci}


# ---- The test report (spec D.1-D.7, 4.1-4.2) ----

REPORT_PATH = DATA_DIR / 'hazard_model_report.json'
BOOTSTRAP_REPS = 1000
BOOTSTRAP_SEED = 0
LEVELS =('High', 'Moderate', 'Low')
LABELS = {'logistic_regression': 'logistic regression', 'random_forest': 'random forest', 'xgboost': 'XGBoost'}
_POOLED = ('log_loss', 'brier', 'roc_auc', 'pr_auc')


CALIBRATION_REASONS = ('not_applicable', 'platt', 'no_event_in_calibration_year', 'no_event_in_earlier_years',
                       'sign_guard')


class CannotEvaluate(Exception):
    """The data cannot support the test (a fold with no event to learn from); the message says why."""


def calibration_reason(name: str, train: Dataset, fitted: Fitted) -> str:
    """Spec D.5, 'the report says which': why a fold's model is or is not Platt-calibrated.

    Read from the training rows and the fit, following fit_candidate's rule (which is unchanged):
    logistic regression is never recalibrated; a tree needs an event in its last training year (the
    calibration year) and one in the years before it; a Platt slope <= 0 is dropped by the sign guard.
    """
    if name == 'logistic_regression':
        reason = 'not_applicable'
    else:
        in_last = train.years == train.years.max()
        if not train.y[in_last].any():
            reason = 'no_event_in_calibration_year'
        elif not train.y[~in_last].any():
            reason = 'no_event_in_earlier_years'
        else:
            reason = 'platt' if fitted.platt is not None else 'sign_guard'
    if (reason == 'platt') != (fitted.platt is not None):
        raise RuntimeError(f'{name}: its Platt mapping does not follow the rule ({reason}); fit_candidate changed.')
    return reason


def beats_benchmark(winner_mean: float, benchmark_mean: float, interval) -> bool:
    """Spec 4.1: a lower mean log loss, and a 95% interval of (winner - benchmark) entirely below 0."""
    return interval is not None and winner_mean < benchmark_mean and interval[1] < 0


def to_json_safe(obj):
    """Strict JSON values: tuples and arrays become lists, numpy numbers Python ones, NaN and inf null, dates ISO."""
    if isinstance(obj, dict):
        return {str(k): to_json_safe(v) for k, v in obj.items()}
    if isinstance(obj, np.ndarray):
        return [to_json_safe(v) for v in obj.tolist()]
    if isinstance(obj, (list, tuple)):
        return [to_json_safe(v) for v in obj]
    if obj is None or isinstance(obj, str):
        return obj
    if isinstance(obj, (bool, np.bool_)):
        return bool(obj)
    if isinstance(obj, (int, np.integer)):
        return int(obj)
    if isinstance(obj, (float, np.floating)):
        value = float(obj)
        return value if math.isfinite(value) else None
    if isinstance(obj, np.datetime64):
        return str(obj.astype('datetime64[D]'))
    if isinstance(obj, date):
        return obj.isoformat()
    raise TypeError(f'not JSON-serialisable: {type(obj).__name__}')


def read_report(path=None) -> dict | None:
    """The saved report, or None when it is missing or unreadable. `path` defaults to REPORT_PATH at call time."""
    path = REPORT_PATH if path is None else path
    try:
        with open(path, encoding='utf-8') as f:
            report = json.load(f)
    except (OSError, ValueError):      # ValueError covers malformed JSON and bytes that are not UTF-8
        return None
    return report if isinstance(report, dict) else None


REPORT_UNREADABLE = 'The model report is missing or cannot be read; run manage.py test_hazard_models.'


def accuracy_entries(today) -> list[dict]:
    """Flood's and landslide's held-out test for the accuracy card (spec 4.1), from the saved report.

    Each entry is the report's entry for the hazard with `kind: 'rain_terrain'`, the report's study period, its
    `tested_at` (when the report was written), and:
      status  'in_use' when the winner beat the counting benchmark (beats_benchmark), else 'in_use_not_better':
              the model is used either way. 'unavailable' when there is no report, it cannot be read or it has no
              result for the hazard; such an entry has only a `reason` besides.
      stale   True when the study-period records no longer match the report's data_signature (a record was
              added, changed or deleted). A record dated after the study period changes nothing.
    The report is read at call time (REPORT_PATH), never a path bound at import. `today` mirrors
    model_forecast.accuracy_reports; the saved report does not depend on it.
    """
    report = read_report()
    tested = report.get('hazards') if report is not None else None
    out = []
    for hazard in HAZARDS:
        entry = tested.get(hazard) if isinstance(tested, dict) else None
        if not isinstance(entry, dict) or entry.get('winner') not in CANDIDATES:
            reason = (REPORT_UNREADABLE if report is None
                      else f'The model report has no {hazard.lower()} result; run manage.py test_hazard_models.')
            out.append({'hazard': hazard, 'kind': 'rain_terrain', 'status': 'unavailable', 'reason': reason})
            continue
        stale = records_signature(load_records(hazard), STUDY_START, STUDY_END) != entry.get('data_signature')
        out.append({**entry, 'hazard': hazard, 'kind': 'rain_terrain',
                    'status': 'in_use' if entry.get('beats_benchmark') else 'in_use_not_better',
                    'stale': stale, 'study': report.get('study'), 'tested_at': report.get('generated')})
    return out


def _auc(y, score) -> float | None:
    """ROC-AUC, or None when only one class is present."""
    y = np.asarray(y).astype(int)
    return float(roc_auc_score(y, score)) if 0 < y.sum() < len(y) else None


def timing_auc(days, y, p) -> dict:
    """D.7 'when': per day, the city's highest chance against whether any barangay had an event."""
    days = np.asarray(days).astype('datetime64[D]')
    y = np.asarray(y).astype(int)
    unique, inverse = np.unique(days, return_inverse=True)
    top = np.full(len(unique), -np.inf)
    np.maximum.at(top, inverse, np.asarray(p, dtype=float))
    hit = np.zeros(len(unique), dtype=int)
    np.maximum.at(hit, inverse, y)
    return {'auc': _auc(hit, top), 'days': int(len(unique)), 'event_days': int(hit.sum())}


def place_auc(days, y, p) -> dict:
    """D.7 'where': on each day with an event, the barangays ranked by chance against which were hit.

    A day on which every barangay was hit has nothing to rank; it is skipped and counted.
    """
    days = np.asarray(days).astype('datetime64[D]')
    y = np.asarray(y).astype(int)
    p = np.asarray(p, dtype=float)
    per_day, skipped = [], 0
    for d in np.unique(days[y == 1]):
        on = days == d
        auc = _auc(y[on], p[on])
        if auc is None:
            skipped += 1
            continue
        per_day.append({'day': str(d), 'auc': auc, 'hit': int(y[on].sum()), 'barangays': int(on.sum())})
    aucs = [r['auc'] for r in per_day]
    return {'mean': float(np.mean(aucs)) if aucs else None, 'per_day': per_day, 'skipped_days': skipped}


@dataclass
class _Fold:
    train_years: tuple
    year: int
    train: Dataset
    test: Dataset
    fits: dict      # candidate -> Fitted, fitted on the training years only
    p: dict         # name -> chances for the test year: the candidates, 'benchmark' and 'no_skill'


def _fit_folds(hazard: str, ds: Dataset) -> list[_Fold]:
    years = ds.years
    folds = []
    for train_years, test_year in FOLDS:
        train, test = ds.subset(np.isin(years, train_years)), ds.subset(years == test_year)
        if len(test.y) == 0:
            raise CannotEvaluate(f'{hazard}: there are no rows for the test year {test_year}.')
        if train.y.sum() == 0:
            raise CannotEvaluate(f'{hazard}: the training years {train_years[0]} to {train_years[-1]} hold no '
                                 f'reported event, so no model can be fitted to test {test_year}.')
        fits = {c: fit_candidate(c, hazard, train) for c in CANDIDATES}
        p = {c: predict(fits[c], test.X) for c in CANDIDATES}
        p['benchmark'] = benchmark_probs(train, test)
        p['no_skill'] = np.full(len(test.y), no_skill(train))
        folds.append(_Fold(train_years, test_year, train, test, fits, p))
    return folds


def _year_scores(year: int, y, p) -> dict:
    s = scores(y, p)
    return {'year': int(year), 'rows': s['n'], 'positives': s['positives'], 'expected': float(np.sum(p)),
            'log_loss': s['log_loss'], 'brier': s['brier'], 'roc_auc': s['roc_auc'], 'pr_auc': s['pr_auc']}


def _threshold(folds: list[_Fold], winner: str) -> dict:
    """D.2's alarm cutoff per fold, with the share of training rows it really flags (tied scores flag more)."""
    per_fold = []
    for f in folds:
        p_train = predict(f.fits[winner], f.train.X)
        m = threshold_metrics(p_train, f.test.y, f.p[winner], ALARM_RATE)
        per_fold.append({'year': f.year, **m, 'train_flagged_share': float(np.mean(p_train >= m['cutoff']))})
    total = {k: sum(r[k] for r in per_fold) for k in ('tp', 'fp', 'fn', 'tn')}
    flagged, events = total['tp'] + total['fp'], total['tp'] + total['fn']
    return {'rate': ALARM_RATE, 'folds': per_fold,
            'pooled': {**total, 'precision': total['tp'] / flagged if flagged else None,
                       'recall': total['tp'] / events if events else None}}


def _lobo(hazard: str, winner: str, ds: Dataset) -> dict:
    """D.4: the winner trained on every other barangay's study rows predicts the one left out."""
    per = []
    for b in np.unique(ds.barangay_id):
        held = ds.barangay_id == b
        rest = ds.subset(~held)
        # with no event left in the other barangays there is nothing to learn from, so no number is given
        chance = float(predict(fit_candidate(winner, hazard, rest), ds.X[held]).mean()) if rest.y.sum() else None
        per.append({'barangay_id': int(b), 'mean_chance': chance, 'had_event': bool(ds.y[held].any())})
    scored = [r for r in per if r['mean_chance'] is not None]
    return {'auc': _auc([r['had_event'] for r in scored], [r['mean_chance'] for r in scored]), 'per_barangay': per}


def _unseen_barangay_events(fold: _Fold, winner: str) -> list[dict]:
    """D.4: the last fold's test events in barangays with no event in its training years (Camp IV in 2025)."""
    seen = set(fold.train.barangay_id[fold.train.y == 1].tolist())
    p = fold.p[winner]
    return [{'barangay_id': int(fold.test.barangay_id[i]), 'day': fold.test.day[i], 'chance': float(p[i]),
             'percentile': 100.0 * float(np.mean(p < p[i]))}
            for i in np.flatnonzero(fold.test.y == 1) if int(fold.test.barangay_id[i]) not in seen]


def _by_type(hazard, records, excluded, ids, days, y, p) -> list[dict]:
    """Test events and their mean chance per subtype of the records behind them; a row of two types counts twice."""
    behind = defaultdict(set)
    for r in records:
        if r.hazard == hazard and not r.is_sample and r.source_ref not in excluded and r.barangay_id is not None:
            behind[(r.barangay_id, r.day)].add(r.subtype)
    chances = defaultdict(list)
    for i in np.flatnonzero(y == 1):
        # None: no record behind the row, which cannot happen when the rows come from these records
        for subtype in behind.get((int(ids[i]), days[i].astype(object))) or {None}:
            chances[subtype].append(float(p[i]))
    return [{'subtype': s, 'positives': len(v), 'mean_chance': float(np.mean(v))}
            for s, v in sorted(chances.items(), key=lambda kv: (-len(kv[1]), kv[0] or ''))]


def _sensitivity(hazard: str, winner: str, sds: Dataset) -> dict:
    """C.4 run 2: the winner refitted per fold on the rows built without exclusions; pooled scores only."""
    years = sds.years
    ys, ps = [], []
    for train_years, test_year in FOLDS:
        train, test = sds.subset(np.isin(years, train_years)), sds.subset(years == test_year)
        ps.append(predict(fit_candidate(winner, hazard, train), test.X))
        ys.append(test.y)
    s = scores(np.concatenate(ys), np.concatenate(ps))
    return {'model': winner, **{k: s[k] for k in _POOLED}, 'positives': s['positives'],
            'study_positives': int(sds.y.sum())}


def _monthly_check(hazard, winner, folds, ds, rain, terrain):
    """Spec 4.2: each barangay-month of each test year, as the forecast page would have shown it.

    The fold's winner replays the rain of every complete year before the test year (the Month-and-year
    view); the recorded-rain and benchmark chances use the test year's own days.
    """
    complete = complete_years(rain)
    ids = sorted(set(ds.barangay_id.tolist()))
    scen_terrain, scen_rain = {b: terrain[b] for b in ids}, {b: rain.rain[b] for b in ids}
    built, rows, by_fold = {}, [], []
    skipped = {'no_scenario': 0, 'incomplete_month': 0}
    for f in folds:
        chance_of = {b: {} for b in ids}
        for s in complete:
            if s >= f.year:
                continue
            if s not in built:
                built[s] = build_dataset(hazard, scen_terrain, scen_rain, set(), date(s, 1, 1), date(s, 12, 31))[0]
            sd = built[s]
            for b, d, p in zip(sd.barangay_id.tolist(), sd.day.tolist(), predict(f.fits[winner], sd.X).tolist()):
                chance_of[b][d] = p
        months = f.test.day.astype('datetime64[M]').astype(int) % 12 + 1
        used = set()
        for m in range(1, 13):
            dates_by_s = scenario_dates(m, None, f.year, complete)
            for b in ids:
                pc = period_chance(chance_of[b].get, dates_by_s)
                if pc is None:
                    skipped['no_scenario'] += 1
                    continue
                own = (f.test.barangay_id == b) & (months == m)
                if own.sum() != monthrange(f.year, m)[1]:     # a test-year day without rain: no fair month
                    skipped['incomplete_month'] += 1
                    continue
                used.update(pc.years)
                rows.append((pc.probability, int(f.test.y[own].sum()),
                             1.0 - float(np.prod(1.0 - f.p[winner][own])),
                             1.0 - float(np.prod(1.0 - f.p['benchmark'][own]))))
        by_fold.append({'test_year': f.year, 'scenario_years': sorted(used)})

    chance = np.array([r[0] for r in rows], dtype=float)
    events = np.array([r[1] for r in rows], dtype=int)
    picked = [level_for(c) for c in chance]
    levels = []
    for level in LEVELS:           # fire's table layout and rounding (model_forecast.evaluate)
        inside = np.array([lv == level for lv in picked], dtype=bool)
        found = bool(inside.any())
        levels.append({'level': level, 'rows': int(inside.sum()), 'events': int(events[inside].sum()),
                       'chance': round(float(chance[inside].mean()), 3) if found else None,
                       'happened': round(float((events[inside] > 0).mean()), 3) if found else None,
                       # unrounded, and like for like: the chances of at least one event per barangay-month
                       # summed, against the barangay-months that had one (`events` counts barangay-days)
                       'chance_sum': float(chance[inside].sum()),
                       'months_with_event': int((events[inside] > 0).sum())})
    hit = (events > 0).astype(float)

    def brier(col):
        return float(np.mean((np.array([r[col] for r in rows], dtype=float) - hit) ** 2)) if rows else None

    monthly_brier = {'scenario': brier(0), 'recorded_rain': brier(2), 'benchmark': brier(3),
                     'barangay_months': len(rows), 'skipped': skipped}
    return levels, monthly_brier, by_fold


def _count(n: int, word: str) -> str:
    return f'{n:,} {word}' + ('' if n == 1 else 's')


def _years_text(years) -> str:
    years = [str(y) for y in years]
    return years[0] if len(years) == 1 else ', '.join(years[:-1]) + ' and ' + years[-1]


_NUMBER_WORDS = {2: 'two', 3: 'three', 4: 'four'}


def report_limits(hazard: str, report: dict, *, cells: int, barangays: int,
                  years=(STUDY_START.year, STUDY_END.year)) -> list[str]:
    """Plain sentences for the accuracy card, from the report's own numbers (7 or 8 of them).

    Each must be literally true: the test years are held out from every fit, but the winner is chosen on
    those same years, and the last-but-one sentence says so.
    """
    noun = hazard.lower()
    winner = report['winner']
    positives, days = report['positives'], report['positive_days']
    first = (f"{_count(positives, f'reported {noun} barangay-day')} from {years[0]} to {years[1]} "
             f"{'falls' if positives == 1 else 'fall'} on {_count(days, 'distinct day')}, so the evidence is "
             f"closer to {_count(days, 'day')} than to {_count(report['rows'], 'row')}")
    dropped = report.get('dropped') or 0
    if dropped:
        first += (f" ({_count(dropped, 'more barangay-day')} {'was' if dropped == 1 else 'were'} left out because "
                  f"a day of the 14-day rain window was missing)")
    out = [first + '.']
    counts = [f['train_positive_days'] for f in report['folds']]
    tests = [f['test_year'] for f in report['folds']]
    if len(set(counts)) == 1:
        out.append(f"The model learned from reported {noun}s on {_count(counts[0], 'distinct day')} in the "
                   f"training years before each test year.")
    else:
        out.append(f"The model learned from reported {noun}s on {_years_text(counts)} distinct days in the "
                   f"training years before {_years_text(tests)} respectively.")
    per_year = report['candidates'][winner]['per_year']
    quiet = [r['year'] for r in per_year if r['positives'] == 0]
    if quiet:
        rest = [r['year'] for r in per_year if r['positives'] > 0]
        many = len(quiet) > 1
        text = (f"The {_years_text(quiet)} test year{'s' if many else ''} had no reported {noun}, so ROC-AUC, "
                f"PR-AUC and recall are undefined for {'them' if many else 'it'}; {'their' if many else 'its'} "
                f"log loss and Brier score still count, ")
        out.append(text + (f"and only {_years_text(rest)} can show whether the model ranks events above non-events."
                           if rest else 'but no test year can show whether the model ranks events above non-events.'))
    label = LABELS.get(winner, winner)
    if report['beats_benchmark']:
        out.append(f'The {label} model beat the counting benchmark on test years it was not trained on: its mean '
                   f'log loss is lower and the 95% interval of the difference lies below zero.')
    else:
        lower = report['candidates'][winner]['mean_log_loss'] < report['benchmark']['mean_log_loss']
        why = ('its mean log loss is lower, but the 95% interval of the difference does not lie wholly below zero'
               if lower else 'its mean log loss is not lower')
        out.append(f'The {label} model did not beat the counting benchmark on test years it was not trained on '
                   f'({why}); it still supplies the forecast.')
    no_skill = next((d for d in report['differences'] if d['a'] == winner and d['b'] == 'no_skill'), None)
    if report['candidates'][winner]['mean_log_loss'] >= report['no_skill']['mean_log_loss']:
        out.append("Its mean log loss is not lower than always guessing the training years' average chance "
                   "(no skill).")
    elif no_skill is not None and no_skill['high'] < 0:
        out.append("It also beat always guessing the training years' average chance (no skill): the 95% interval "
                   "of that difference lies below zero too.")
    else:
        out.append("Against always guessing the training years' average chance (no skill), the 95% interval of "
                   "the difference does not lie wholly below zero, so its gain over that simpler guess is not "
                   "certain.")
    n = len(report['candidates'])
    out.append(f'The model was chosen from {_NUMBER_WORDS.get(n, str(n))} candidates on these same test years, '
               f'so its scores may be slightly optimistic.')
    out.append(f"Rain comes from {_count(cells, 'NASA POWER grid cell')} (about 55 km across) for "
               f"{_count(barangays, 'barangay')}, so barangays in one cell share the same rain and small storms "
               f"can be missed.")
    out.append(f'The records come from news reports, so an empty barangay-day means nothing was reported, not that '
               f'nothing happened: the chances describe reported {noun}s and read lower than the true rate.')
    return out


def evaluate_hazard(hazard: str, ds: Dataset, rain, terrain, records, sensitivity_ds: Dataset | None = None, *,
                    excluded: dict[str, str] | None = None, dropped: int = 0, reps: int = BOOTSTRAP_REPS) -> dict:
    """The held-out test of one hazard, as strict-JSON values for the report.

    `ds` holds the study rows built with this run's exclusions, `rain` is the RainFile and `terrain` the
    terrain rows it was built from, `records` the hazard's records (for by_type, the exclusion list and the
    signature) and `sensitivity_ds` the flood rows built without exclusions. Every fit sees its fold's
    training years only; the test years are scored once. Raises CannotEvaluate when a fold has no event
    to learn from.
    """
    excluded = dict(excluded or {})
    if len(ds.y) == 0:
        raise CannotEvaluate(f'{hazard}: the dataset has no rows.')
    folds = _fit_folds(hazard, ds)
    names = CANDIDATES + ('benchmark', 'no_skill')
    y = np.concatenate([f.test.y for f in folds])
    days = np.concatenate([f.test.day for f in folds])
    ids = np.concatenate([f.test.barangay_id for f in folds])
    pooled = {n: np.concatenate([f.p[n] for f in folds]) for n in names}
    boot = bootstrap(days, y, pooled, reps=reps, seed=BOOTSTRAP_SEED)

    scored = {}
    for n in names:
        per_year = [_year_scores(f.year, f.test.y, f.p[n]) for f in folds]
        s = scores(y, pooled[n])
        scored[n] = {'mean_log_loss': float(np.mean([r['log_loss'] for r in per_year])),
                     'pooled': {k: s[k] for k in _POOLED}, 'intervals': boot['intervals'][n], 'per_year': per_year}
    for c in CANDIDATES:
        reasons = [calibration_reason(c, f.train, f.fits[c]) for f in folds]
        scored[c]['calibrated'] = [r == 'platt' for r in reasons]    # a Platt mapping was fitted and kept
        scored[c]['calibration_reason'] = reasons
    mean_ll = {c: scored[c]['mean_log_loss'] for c in CANDIDATES}
    winner = select_winner(mean_ll, boot['diff'])
    versus = boot['diff'][(winner, 'benchmark')]
    p_win = pooled[winner]
    pairs = ([(a, b) for i, a in enumerate(CANDIDATES) for b in CANDIDATES[i + 1:]]
             + [(c, 'benchmark') for c in CANDIDATES] + [(c, 'no_skill') for c in CANDIDATES])
    cal = calibration(y, p_win, days.astype('datetime64[Y]').astype(int) + 1970, days=days, reps=reps,
                      seed=BOOTSTRAP_SEED)
    levels, monthly_brier, scenario_years = _monthly_check(hazard, winner, folds, ds, rain, terrain)
    barangays = sorted(set(ds.barangay_id.tolist()))
    years = ds.years
    placeable = set(terrain) & set(rain.rain)
    # the gap between the records and the positives: real, kept study records that no row can carry
    unplaced = sum(1 for r in records
                   if r.hazard == hazard and not r.is_sample and r.source_ref not in excluded
                   and STUDY_START <= r.day <= STUDY_END and r.barangay_id not in placeable)

    report = {
        'hazard': hazard,
        'tested_at': datetime.now(MANILA).isoformat(timespec='seconds'),
        'rows': int(len(ds.y)),
        'positives': int(ds.y.sum()),
        'prevalence': float(ds.y.mean()),
        'positive_days': int(len(np.unique(ds.day[ds.y == 1]))),
        'dropped': int(dropped),
        'unplaced': unplaced,
        'features': list(ds.features),
        'folds': [{'train_years': list(train), 'test_year': test,
                   'train_positives': int(f.train.y.sum()),
                   'train_positive_days': int(len(np.unique(f.train.day[f.train.y == 1])))}
                  for (train, test), f in zip(FOLDS, folds)],
        'winner': winner,
        'leader': min(mean_ll, key=mean_ll.get),
        'calibrated_all_folds': all(scored[winner]['calibrated']),
        'candidates': {c: scored[c] for c in CANDIDATES},
        'benchmark': scored['benchmark'],
        'no_skill': scored['no_skill'],
        'beats_benchmark': beats_benchmark(mean_ll[winner], scored['benchmark']['mean_log_loss'], versus),
        'winner_minus_benchmark': versus,
        'differences': [{'a': a, 'b': b, 'low': boot['diff'][(a, b)][0], 'high': boot['diff'][(a, b)][1]}
                        for a, b in pairs],
        'bootstrap': {'reps': reps, 'block_days': BLOCK_DAYS, 'seed': BOOTSTRAP_SEED},
        'threshold': _threshold(folds, winner),
        'calibration': {'model': winner, **cal,
                        'pooled': {'observed': int(y.sum()), 'expected': float(p_win.sum())}},
        'timing_auc': timing_auc(days, y, p_win),
        'place_auc': place_auc(days, y, p_win),
        'lobo_auc': _lobo(hazard, winner, ds),
        'camp_iv': _unseen_barangay_events(folds[-1], winner) if hazard == 'Landslide' else None,
        'sensitivity': (_sensitivity(hazard, winner, sensitivity_ds)
                        if hazard == 'Flood' and sensitivity_ds is not None else None),
        'by_type': _by_type(hazard, records, excluded, ids, days, y, p_win) if hazard == 'Flood' else None,
        'monthly_levels': levels,
        'monthly_brier': monthly_brier,
        'scenario_years_by_fold': scenario_years,
        'data_signature': records_signature(records, STUDY_START, STUDY_END),
        'excluded': sorted(({'source_ref': r.source_ref, 'reason': excluded[r.source_ref],
                             'barangay_id': r.barangay_id, 'day': r.day}
                            for r in records if r.hazard == hazard and r.source_ref in excluded),
                           key=lambda e: e['source_ref']),
    }
    report['limits'] = report_limits(hazard, report, cells=len({rain.cells[b] for b in barangays if b in rain.cells}),
                                     barangays=len(barangays), years=(int(years.min()), int(years.max())))
    return to_json_safe(report)
