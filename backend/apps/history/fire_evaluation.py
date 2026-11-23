"""
How good the fire risk model is, and how its chances become levels (spec
sections 5 and 6): the Red / Orange / Green cut-offs, the scores with 95%
intervals from resampling barangays, the comparison baselines, the barangay
sums and the 80% intervals that set the "Limited data" flag.

Part of the fire model adapted from the City of Pittsburgh Bureau of Fire /
Carnegie Mellon Metro21 fire risk model (github.com/CityofPittsburgh/
fire_risk_analysis, MIT License, © 2017 mmadaio). Pittsburgh reported a
confusion matrix, kappa, AUC, recall, precision and F1 at a 0.5 cut-off; at a
fire rate under 1% a 0.5 cut-off flags nothing, so here the cut-offs come from
validation and log loss, Brier, PR-AUC and calibration are added.

The comparison_* baselines are the only place past fires of an area are
tallied, and only to show what the model is measured against; they never
feed a prediction.
"""
import math
from dataclasses import dataclass

import numpy as np

from apps.history import fire_training as ft

LEVELS = ('Red', 'Orange', 'Green')
RECALL = 0.80        # Orange or higher must catch this share of fires
RED_RATIO = 2.0      # Red: at least this many times the city-average rate...
RED_MIN_FIRES = 10   # ...with at least this many fires at or above the cut-off
LIMITED_RATIO = 3    # an 80% interval whose top is more than this many times its bottom is "Limited data"
BOOT_REPS = 1000
INTERVAL_REPS = 50


@dataclass
class Cutoffs:
    orange: float
    red: object        # float, or None when nothing qualifies
    red_reason: object  # why nothing is Red, else None


def _at_or_above(p, y):
    """(distinct p ascending, fires at or above each, rows at or above each)."""
    vals, inv = np.unique(np.asarray(p, float), return_inverse=True)
    fires = np.bincount(inv, weights=np.asarray(y, float), minlength=len(vals))
    rows = np.bincount(inv, minlength=len(vals)).astype(float)
    return vals, np.cumsum(fires[::-1])[::-1], np.cumsum(rows[::-1])[::-1]


def cutoffs(p, y, recall=RECALL, red_ratio=RED_RATIO, red_min_fires=RED_MIN_FIRES):
    """
    Orange: the highest chance at which Orange and Red together hold at least
    `recall` of the fires. Red: the lowest chance, not below Orange, at which the
    rows at or above it have at least red_ratio times the overall fire rate and
    at least red_min_fires fires; None, with the reason, when no chance does.
    """
    y = np.asarray(y, int)
    total = int(y.sum())
    if total == 0:
        raise ValueError('There is no fire in these predictions, so no cut-off can be set.')
    vals, fires, rows = _at_or_above(p, y)
    i_orange = int(np.flatnonzero(fires >= recall * total - 1e-9).max())
    city = total / len(y)
    ok = np.flatnonzero((np.arange(len(vals)) >= i_orange) & (fires >= red_min_fires)
                        & (fires / rows >= red_ratio * city - 1e-12))
    if len(ok):
        return Cutoffs(orange=float(vals[i_orange]), red=float(vals[ok.min()]), red_reason=None)
    if fires[i_orange] < red_min_fires:
        reason = f'Fewer than {red_min_fires} fires fall at or above the Orange cut-off, so nothing is Red.'
    else:
        reason = (f'No cut-off at or above Orange has at least {red_ratio:g} times the city-average fire rate '
                  f'with {red_min_fires} or more fires, so nothing is Red.')
    return Cutoffs(orange=float(vals[i_orange]), red=None, red_reason=reason)


def level(p, c):
    """'Red', 'Orange' or 'Green' for a chance."""
    if c.red is not None and p >= c.red:
        return 'Red'
    return 'Orange' if p >= c.orange else 'Green'


def _kappa(y, flag):
    from sklearn.metrics import cohen_kappa_score

    if len(set(np.asarray(y).tolist()) | set(np.asarray(flag, int).tolist())) < 2:
        return None
    k = cohen_kappa_score(y, np.asarray(flag, int))
    return None if math.isnan(k) else float(k)


def level_table(y, p, c):
    """
    One row per level: its area-months (`rows`, `share`) and fires, then
    recall, precision, F1 and kappa of calling "this level or higher". The
    Green row's `fires` are the fires the levels missed.
    """
    y = np.asarray(y, int)
    p = np.asarray(p, float)
    names = np.array([level(v, c) for v in p])
    total = max(int(y.sum()), 1)
    out = []
    for i, name in enumerate(LEVELS):
        here = names == name
        flagged = np.isin(names, LEVELS[:i + 1])
        caught = int(y[flagged].sum())
        rec = caught / total
        prec = caught / int(flagged.sum()) if flagged.any() else 0.0
        out.append({'level': name, 'rows': int(here.sum()), 'share': float(here.mean()) if len(p) else 0.0,
                    'fires': int(y[here].sum()), 'recall': rec, 'precision': prec,
                    'f1': 2 * rec * prec / (rec + prec) if rec + prec else 0.0, 'kappa': _kappa(y, flagged)})
    return out


def _calibration(y, p):
    """(intercept, slope) of a logistic regression of y on logit(p), or (None, None) when it can't be fitted."""
    from sklearn.linear_model import LogisticRegression

    z = ft.logit(p)
    if y.min() == y.max() or np.ptp(z) == 0:
        return None, None
    m = LogisticRegression(C=np.inf, max_iter=5000).fit(z.reshape(-1, 1), y)
    return float(m.intercept_[0]), float(m.coef_[0, 0])


def _top_share(y, p, share):
    fires = y.sum()
    if not fires:
        return None
    n = max(1, int(math.ceil(share * len(p))))
    top = np.argsort(-p, kind='stable')[:n]
    return float(y[top].sum() / fires)


def _all_scores(y, p, orange):
    from sklearn.metrics import average_precision_score, roc_auc_score

    one_class = y.min() == y.max()
    intercept, slope = _calibration(y, p)
    return {
        'log_loss': float(ft.row_log_loss(y, p).mean()),
        'brier': ft.brier(y, p),
        'roc_auc': None if one_class else float(roc_auc_score(y, p)),
        'pr_auc': float(average_precision_score(y, p)) if y.any() else None,
        'calibration_intercept': intercept,
        'calibration_slope': slope,
        'top10_share': _top_share(y, p, 0.10),
        'top20_share': _top_share(y, p, 0.20),
        'kappa_at_orange': _kappa(y, p >= orange) if orange is not None else None,
    }


def scores(y, p, groups, orange=None, reps=BOOT_REPS, seed=ft.BOOT_SEED):
    """
    Log loss, Brier, ROC-AUC, PR-AUC, calibration intercept and slope, the
    share of fires in the top 10% and 20% of rows, and kappa at the Orange
    cut-off (when given). Each is {value, low, high}: the 95% interval from
    `reps` resamples of whole `groups` (barangays). A score that is undefined
    (an AUC with no fire) is None.
    """
    y, p, groups = np.asarray(y, int), ft.clip(p), np.asarray(groups)
    point = _all_scores(y, p, orange)
    ids, inverse = np.unique(groups, return_inverse=True)
    members = [np.flatnonzero(inverse == g) for g in range(len(ids))]
    rng = np.random.default_rng(seed)
    draws = {k: [] for k in point}
    for _ in range(reps):
        idx = np.concatenate([members[g] for g in rng.integers(0, len(ids), len(ids))])
        for k, v in _all_scores(y[idx], p[idx], orange).items():
            if v is not None:
                draws[k].append(v)
    out = {}
    for k, v in point.items():
        d = draws[k]
        out[k] = {'value': v, 'low': float(np.percentile(d, 2.5)) if d and v is not None else None,
                  'high': float(np.percentile(d, 97.5)) if d and v is not None else None}
    return out


def reliability(y, p, bins=10):
    """
    Rows ranked by chance and cut into `bins` equal groups (tenths): each
    group's rows, mean chance and the share that had a fire. A calibrated model
    has the two close in every group.
    """
    y, p = np.asarray(y, int), np.asarray(p, float)
    order = np.argsort(p, kind='stable')
    return [{'rows': int(len(part)), 'mean_chance': float(p[part].mean()) if len(part) else None,
             'fire_share': float(y[part].mean()) if len(part) else None}
            for part in np.array_split(order, bins)]


def comparison_baselines(panel_train, panel_test, buildings):
    """
    What the model is measured against (spec 6.2), for the test rows, each
    learned from the training rows only:
      comparison_same_everywhere       the training fire rate for every row;
      comparison_buildings             that rate in proportion to the area's buildings (+1);
      comparison_historical_frequency  the area's own share of training months with a fire,
                                       nudged by one month at the city rate: the counting the
                                       brief rules out, kept here only as a yardstick.
    buildings: {area id: buildings_in_area}.
    """
    rate = float(panel_train.y.mean())
    b_train = np.array([buildings[int(a)] for a in panel_train.purok], float) + 1
    b_test = np.array([buildings[int(a)] for a in panel_test.purok], float) + 1
    ids, inverse = np.unique(panel_train.purok, return_inverse=True)
    fires = np.bincount(inverse, weights=panel_train.y.astype(float))
    months = np.bincount(inverse).astype(float)
    freq = dict(zip(ids.tolist(), ((fires + rate) / (months + 1)).tolist()))
    return {
        'comparison_same_everywhere': ft.clip(np.full(len(panel_test.y), rate)),
        'comparison_buildings': ft.clip(rate * b_test / b_train.mean()),
        'comparison_historical_frequency': ft.clip([freq.get(int(a), rate) for a in panel_test.purok]),
    }


def barangay_rates(p_by_area, area_barangay):
    """{barangay id: Σ −ln(1 − p) over its areas}: the expected number of area-months with a fire."""
    out = {}
    for area, p in p_by_area.items():
        b = area_barangay[area]
        out[b] = out.get(b, 0.0) - math.log(1 - p)
    return out


def calendar_rows(panel):
    """
    (area ids in panel order, X): each area's inputs with the month waves of
    January to December, area by area, 12 rows each.
    """
    ids, first = np.unique(panel.purok, return_index=True)
    order = np.argsort(first)
    ids, first = ids[order], first[order]
    waves = [panel.columns.index(c) for c in ft.MONTH_COLUMNS]
    keep = [j for j in range(panel.X.shape[1]) if j not in waves]
    inputs = panel.X[first][:, keep]
    X = np.zeros((len(ids) * 12, panel.X.shape[1]))
    X[:, keep] = np.repeat(inputs, 12, axis=0)
    X[:, waves] = np.tile(ft.month_waves(np.arange(12)), (len(ids), 1))
    return ids, X


def intervals(panel, choice, reps=INTERVAL_REPS, seed=ft.BOOT_SEED):
    """
    {area id: [(10th, 90th percentile) for January..December]} of the chosen
    model's calibrated chance over `reps` refits on barangay-resampled rows.
    The calibration is the chosen model's own (from its leave-one-year-out
    predictions), so the spread is the model's.
    """
    platt = ft.fit_platt(choice.oof, panel.y)
    ids, X = calendar_rows(panel)
    b_ids, inverse = np.unique(panel.barangay, return_inverse=True)
    members = [np.flatnonzero(inverse == g) for g in range(len(b_ids))]
    rng = np.random.default_rng(seed)
    draws = []
    for _ in range(reps):
        idx = np.concatenate([members[g] for g in rng.integers(0, len(b_ids), len(b_ids))])
        raw = ft.fit_predict(choice.family, choice.settings, panel.X[idx], panel.y[idx], X)
        draws.append(ft.clip(ft.apply_platt(ft.clip(raw), *platt)))
    low, high = np.percentile(draws, 10, axis=0), np.percentile(draws, 90, axis=0)
    return {int(a): [(float(low[i * 12 + m]), float(high[i * 12 + m])) for m in range(12)]
            for i, a in enumerate(ids)}


def limited_data(confidence, low, high):
    """An area's figures are "Limited data" when its point is low-confidence or its 80% interval is wide."""
    return confidence == 'low' or high > LIMITED_RATIO * low
