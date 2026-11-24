"""
The flood susceptibility model's fixed rules (spec 4.3-4.4, 5.2, 5.4 and 6),
written down before any model is fitted so no number on the card can be
tuned after the fact:

- the continuous Boyce index (Hirzel et al. 2006), the score for
  presence-only data: how much more often floods fall where the score is high
  than an even spread would put them;
- the bootstrap gain of one score over another, resampling within the
  spatial folds;
- the choice rule (simplest model first, on the Boyce gain) and the
  acceptance gates against the NOAH-only map (gate 1 on the AUC gain);
- the Red / Orange cut-off walk (Red holds half the field spots, Red + Orange
  nine in ten; the lowest score is never flagged);
- the uncertain mark and the "since publishing" monitoring rule.

Plain functions on arrays and dicts, no Django, no model library.
"""
import math
from dataclasses import dataclass

import numpy as np
from scipy.stats import spearmanr

ORDER = ('logistic_regression', 'maxent_hinge', 'xgboost', 'neural_network')
RED_SHARE = 0.5
ORANGE_SHARE = 0.9
FLAGGED_MAX = 0.5
TEST_HITS_NEEDED = 3      # of the 4 GeoAlert Mananga test points
UNCERTAIN_LIMIT = 0.2
MONITOR_MIN = 10
MONITOR_TARGET = 0.8
# Dated, located flood days a flood forecast would need before it could be trained and checked
# (docs/research/2026-11-24-flood-prediction-assessment.md, Strategy A: "about 20-30")
FORECAST_DAYS_MIN = 20
FORECAST_DAYS_MAX = 30
FLAGGED = ('Red', 'Orange')


def boyce_index(presence, background, window_frac: float = 0.1, n_points: int = 101) -> float:
    """
    Continuous Boyce index: the Spearman correlation between a moving window's
    centre and its predicted-to-expected ratio (the share of presences in the
    window over the share of background), as ecospat.boyce computes it
    (repeated ratios dropped). NaN when the scores cannot be ranked.
    """
    p = np.asarray(presence, float)
    b = np.asarray(background, float)
    if not len(p) or not len(b):
        return float('nan')
    lo, hi = float(min(p.min(), b.min())), float(max(p.max(), b.max()))
    if hi <= lo:
        return float('nan')
    half = window_frac * (hi - lo) / 2
    centres, ratios = [], []
    for c in np.linspace(lo, hi, n_points):
        e = np.count_nonzero((b >= c - half) & (b <= c + half)) / len(b)
        if e == 0:
            continue
        ratio = (np.count_nonzero((p >= c - half) & (p <= c + half)) / len(p)) / e
        if ratios and ratio == ratios[-1]:
            continue
        centres.append(c)
        ratios.append(ratio)
    if len(ratios) < 3 or len(set(ratios)) < 2:
        return float('nan')
    return float(spearmanr(centres, ratios).correlation)


def _within_folds(rng, folds):
    """Bootstrap indices: each fold resampled with replacement to its own size."""
    parts = []
    for f in np.unique(folds):
        idx = np.flatnonzero(folds == f)
        parts.append(rng.choice(idx, size=len(idx), replace=True))
    return np.concatenate(parts) if parts else np.zeros(0, int)


def boyce_gain(folds_p, folds_b, a_p, a_b, b_p, b_b, reps: int = 1000, seed: int = 0):
    """(gain of score A over score B, 2.5%, 97.5%): Boyce(A) − Boyce(B), bootstrapped within folds."""
    folds_p, folds_b = np.asarray(folds_p), np.asarray(folds_b)
    a_p, a_b, b_p, b_b = (np.asarray(x, float) for x in (a_p, a_b, b_p, b_b))
    gain = boyce_index(a_p, a_b) - boyce_index(b_p, b_b)
    rng = np.random.default_rng(seed)
    draws = []
    for _ in range(reps):
        ip, ib = _within_folds(rng, folds_p), _within_folds(rng, folds_b)
        draws.append(boyce_index(a_p[ip], a_b[ib]) - boyce_index(b_p[ip], b_b[ib]))
    draws = np.asarray(draws, float)
    if np.isnan(draws).all():
        return float(gain), float('nan'), float('nan')
    low, high = np.nanpercentile(draws, [2.5, 97.5])
    return float(gain), float(low), float(high)


def auc_score(presence, background) -> float:
    """The chance a flood spot outranks a background building (ties count half): the Mann-Whitney AUC."""
    from scipy.stats import rankdata

    p, b = np.asarray(presence, float), np.asarray(background, float)
    if not len(p) or not len(b):
        return float('nan')
    ranks = rankdata(np.r_[p, b])
    return float((ranks[:len(p)].sum() - len(p) * (len(p) + 1) / 2) / (len(p) * len(b)))


def auc_gain(folds_p, folds_b, a_p, a_b, b_p, b_b, reps: int = 1000, seed: int = 0):
    """
    (AUC of score A − AUC of score B, 2.5%, 97.5%), bootstrapped within folds.
    Gate 1 uses this, not the Boyce gain: UP NOAH's map has only four values,
    and a continuous Boyce index over four values swings from draw to draw.
    """
    folds_p, folds_b = np.asarray(folds_p), np.asarray(folds_b)
    a_p, a_b, b_p, b_b = (np.asarray(x, float) for x in (a_p, a_b, b_p, b_b))
    gain = auc_score(a_p, a_b) - auc_score(b_p, b_b)
    rng = np.random.default_rng(seed)
    draws = []
    for _ in range(reps):
        ip, ib = _within_folds(rng, folds_p), _within_folds(rng, folds_b)
        draws.append(auc_score(a_p[ip], a_b[ib]) - auc_score(b_p[ip], b_b[ib]))
    low, high = np.nanpercentile(np.asarray(draws, float), [2.5, 97.5])
    return float(gain), float(low), float(high)


def boyce_interval(folds_p, folds_b, p, b, reps: int = 1000, seed: int = 0):
    """(Boyce index, 2.5%, 97.5%) of one score, bootstrapped within folds."""
    folds_p, folds_b = np.asarray(folds_p), np.asarray(folds_b)
    p, b = np.asarray(p, float), np.asarray(b, float)
    rng = np.random.default_rng(seed)
    draws = np.asarray([boyce_index(p[_within_folds(rng, folds_p)], b[_within_folds(rng, folds_b)])
                        for _ in range(reps)], float)
    value = boyce_index(p, b)
    if np.isnan(draws).all():
        return float(value), float('nan'), float('nan')
    low, high = np.nanpercentile(draws, [2.5, 97.5])
    return float(value), float(low), float(high)


def choose(scores: dict, folds_p, folds_b, order=ORDER, reps: int = 1000, seed: int = 0):
    """
    (chosen candidate, comparisons). Walks `order` from the simplest; a more
    complex candidate replaces the current choice only when its Boyce gain
    over it has a bootstrap interval wholly above zero.
    """
    names = [n for n in order if n in scores]
    current = names[0]
    comparisons = []
    for name in names[1:]:
        gain, low, high = boyce_gain(folds_p, folds_b, *scores[name], *scores[current], reps=reps, seed=seed)
        adopted = bool(low > 0)
        comparisons.append({'candidate': name, 'against': current, 'gain': gain, 'low': low, 'high': high,
                            'adopted': adopted})
        if adopted:
            current = name
    return current, comparisons


@dataclass
class Cutoffs:
    red: float | None
    orange: float | None
    red_recall: float
    orange_recall: float
    target_reached: bool


def cutoff_walk(purok_scores: dict, spots_in: dict, red: float = RED_SHARE, orange: float = ORANGE_SHARE) -> Cutoffs:
    """
    Cut-offs on the purok score. Walk the assessed puroks' distinct scores from
    the top, adding up the field spots they hold (spots in puroks that are not
    assessed count in the total and can never be caught). Red stops at the
    first score holding `red` of them, Orange at the first holding `orange`.
    The lowest distinct score is never flagged, so a tie at the bottom can't
    turn the whole map orange; when a target needs it, the walk stops one
    score above and says the target was not reached.
    """
    total = sum(spots_in.values())
    levels = sorted(set(purok_scores.values()), reverse=True)
    flaggable = levels[:-1]
    if not flaggable or not total:
        return Cutoffs(red=None, orange=None, red_recall=0.0, orange_recall=0.0, target_reached=False)
    held = {s: 0 for s in levels}
    for pid, s in purok_scores.items():
        held[s] += spots_in.get(pid, 0)
    shares, cum = [], 0
    for s in flaggable:
        cum += held[s]
        shares.append((s, round(cum / total, 6)))
    red_hit = next(((s, sh) for s, sh in shares if sh >= red), None)
    if red_hit is None:
        # Half the spots are never held above the bottom score: every flaggable score is Red
        s, sh = shares[-1]
        return Cutoffs(red=s, orange=None, red_recall=sh, orange_recall=sh, target_reached=False)
    orange_hit = next(((s, sh) for s, sh in shares if sh >= orange), None)
    if orange_hit is None:
        s, sh = shares[-1]
        return Cutoffs(red=red_hit[0], orange=s if s != red_hit[0] else None, red_recall=red_hit[1],
                       orange_recall=sh, target_reached=False)
    return Cutoffs(red=red_hit[0], orange=orange_hit[0], red_recall=red_hit[1], orange_recall=orange_hit[1],
                   target_reached=True)


def classify(score: float, cutoffs: Cutoffs) -> str:
    if cutoffs.red is not None and score >= cutoffs.red:
        return 'Red'
    if cutoffs.orange is not None and score >= cutoffs.orange:
        return 'Orange'
    return 'Green'


def test_hits_needed(n: int) -> int:
    """Gate 2's bar for n GeoAlert Mananga test points: 3 of the 4, the same share of any other count, at least 1."""
    return TEST_HITS_NEEDED if n == 4 else max(1, math.ceil(0.75 * n))


def test_gate_passed(test_levels: list) -> bool:
    """Gate 2: enough GeoAlert Mananga test points in Red or Orange; no points is no evidence, so a fail."""
    return sum(1 for lv in test_levels if lv in FLAGGED) >= test_hits_needed(len(test_levels))


def acceptance(gain_low: float, test_levels: list, flagged_share: float, *, own: bool = False):
    """
    (adopted, reasons) for gates 1-3 (spec 4.4); each failed gate is one plain sentence. `own`: the test spots
    are GeoAlert's held-back wet season and the area is the one its records cover (automatic retraining).
    """
    reasons = []
    if not (gain_low is not None and not math.isnan(gain_low) and gain_low > 0):
        reasons.append('It did not clearly beat UP NOAH\'s map on its own: the lower end of its AUC gain was '
                       f'{gain_low:.3f}, not above zero.' if gain_low is not None and not math.isnan(gain_low)
                       else 'Its AUC gain over UP NOAH\'s map could not be measured.')
    hits = sum(1 for lv in test_levels if lv in FLAGGED)
    needed = test_hits_needed(len(test_levels))
    if not test_levels:
        reasons.append('No held-back wet season spot was available to test it on.' if own
                       else 'No GeoAlert Mananga flood point was available to test it on.')
    elif hits < needed:
        reasons.append(f'Only {hits} of the {len(test_levels)} held-back wet season spots fell in a Red or Orange '
                       f'area ({needed} needed).' if own
                       else f'Only {hits} of the {len(test_levels)} GeoAlert Mananga flood points fell in a Red or '
                            f'Orange area ({needed} needed).')
    if flagged_share > FLAGGED_MAX:
        reasons.append(f"Red and Orange would cover {flagged_share:.0%} of the buildings in the area GeoAlert's "
                       'records cover, more than half.' if own
                       else f'Red and Orange would cover {flagged_share:.0%} of the floodplain\'s buildings, more '
                            'than half.')
    return not reasons, reasons


def uncertain_puroks(published: dict, refits: list, limit: float = UNCERTAIN_LIMIT) -> set:
    """The puroks whose class differs from the published one in more than `limit` of the refits."""
    if not refits:
        return set()
    return {pid for pid, level in published.items()
            if sum(1 for r in refits if r.get(pid) != level) / len(refits) > limit}


def monitoring(levels: list, min_n: int = MONITOR_MIN, target: float = MONITOR_TARGET) -> dict:
    """New located floods' classes since publishing: under review when ≥ min_n and under `target` were flagged."""
    n = len(levels)
    flagged = sum(1 for lv in levels if lv in FLAGGED)
    return {'n': n, 'in_red_orange': flagged, 'under_review': bool(n >= min_n and flagged / n < target)}
