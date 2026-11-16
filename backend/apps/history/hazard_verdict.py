"""The flood and landslide test designs (spec Section 2), part 2: scores, level tables, the event table, the
landslide outside test, the rule for replacing the current model, and evaluate(), which runs them all.

Every log score clips p to [CLIP, 1 - CLIP], so a rule that gives a barangay
exactly 0 meets an event at a finite cost. "When" is scored on city days against data.city_y (any kept record
that day, barangay known or not), with the city chance 1 - prod_b (1 - p(b, d)) over the day's barangay rows.
"Where", levels, per-year counts and rule (b) use the barangay-day rows (data.rows.y).
"""
import math

import numpy as np
from scipy.special import expit
from scipy.stats import chi2, norm
from sklearn.metrics import average_precision_score

from apps.history.firth import FitFailed
from apps.history.hazard_data import RAIN_FEATURES, build_dataset
from apps.history.hazard_models import CannotEvaluate, _auc, to_json_safe
from apps.history.hazard_scoring import score_logistic
from apps.history.hazard_tests import (
    BOOTSTRAP_REPS, BUFFER_DAYS, PAGASA_BANDS, LogisticContender, TwoPartContender, baselines, blocks_for,
    cluster_bootstrap, out_of_fold, yearly_folds)
from apps.history.model_forecast import HIGH_CHANCE, MODERATE_CHANCE, plain_number
from apps.history.two_part import FEATURES, fit_when

CLIP = 1e-6
CUTOFFS = (HIGH_CHANCE, MODERATE_CHANCE)    # model_forecast.level_for: High >= 0.25, Moderate >= 0.15
TOP_N = 5                                   # the lift ratio's top barangays
Z95 = float(norm.ppf(0.975))
NEW, CURRENT = TwoPartContender.name, LogisticContender.name
MAX_ITER = 100
BAND_LABELS = (f'under {PAGASA_BANDS[0]:g} mm',          # the PAGASA 24-hour bands, for the event table
               *(f'{lo:g}-{hi:g} mm' for lo, hi in zip(PAGASA_BANDS, PAGASA_BANDS[1:])),
               f'{PAGASA_BANDS[-1]:g} mm or more')


def _clip(p) -> np.ndarray:
    return np.clip(np.asarray(p, dtype=float), CLIP, 1 - CLIP)


def row_log_loss(y, p) -> np.ndarray:
    """Each row's log loss, with p clipped to [CLIP, 1 - CLIP]."""
    y, q = np.asarray(y, dtype=float), _clip(p)
    return -(y * np.log(q) + (1 - y) * np.log1p(-q))


def _num(x: float) -> str:
    """A short plain number: 4.0, 2.5, 2.33, 0.04."""
    text = f'{x:.2f}'.rstrip('0')
    return text + '0' if text.endswith('.') else text


# ---- Barangay-day scores ----

def calibration_slope(y, p) -> float | None:
    """The slope of an unpenalised maximum-likelihood logistic fit of y on logit(p) (p clipped) with an
    intercept: 1 is ideal, below 1 means the chances spread too far. None with one class, a constant p, or a
    fit that does not converge (separated classes)."""
    y = np.asarray(y, dtype=float)
    q = _clip(p)
    x = np.log(q) - np.log1p(-q)
    if not 0 < y.sum() < len(y) or np.ptp(x) == 0:
        return None
    design = np.column_stack([np.ones(len(y)), x])

    def loglik(b):
        eta = design @ b
        return float(np.sum(y * eta - np.logaddexp(0.0, eta)))

    beta, current = np.zeros(2), loglik(np.zeros(2))
    for _ in range(MAX_ITER):
        mu = expit(design @ beta)
        info = design.T @ (design * (mu * (1 - mu))[:, None])
        try:
            step = np.linalg.solve(info, design.T @ (y - mu))
        except np.linalg.LinAlgError:
            return None
        scale = 1.0
        for _ in range(30):
            candidate = beta + scale * step
            value = loglik(candidate)
            if value >= current - 1e-12:
                break
            scale /= 2.0
        else:
            return None
        change = float(np.max(np.abs(candidate - beta)))
        beta, current = candidate, value
        if change < 1e-10:
            return float(beta[1])
    return None


def _skill(brier: float, y: np.ndarray, reference) -> float | None:
    if reference is None:
        return None
    ref = float(np.mean((np.asarray(reference, dtype=float) - y) ** 2))
    return 1.0 - brier / ref if ref > 0 else None


def model_scores(y, p, p_climatology=None, p_rate=None) -> dict:
    """Barangay-day scores. Brier skill is 1 - Brier / the reference's Brier (None without a reference);
    no_skill_pr_auc is the event rate, the PR-AUC of a model with no skill."""
    y = np.asarray(y).astype(int)
    p = np.asarray(p, dtype=float)
    brier = float(np.mean((p - y) ** 2))
    both = 0 < y.sum() < len(y)
    return {
        'log_loss': float(row_log_loss(y, p).mean()),
        'brier': brier,
        'brier_skill_climatology': _skill(brier, y, p_climatology),
        'brier_skill_rate': _skill(brier, y, p_rate),
        'pr_auc': float(average_precision_score(y, p)) if both else None,
        'no_skill_pr_auc': float(y.mean()),
        'roc_auc': _auc(y, p),
        'calibration_slope': calibration_slope(y, p),
        'rows': int(len(y)),
        'events': int(y.sum()),
    }


def poisson_interval(k: int) -> tuple[float, float]:
    """The exact 95% interval of a Poisson count k."""
    low = 0.0 if k == 0 else float(chi2.ppf(0.025, 2 * k) / 2)
    return low, float(chi2.ppf(0.975, 2 * k + 2) / 2)


def per_year(data, p) -> list[dict]:
    """Observed barangay-day events per year against the expected number (the sum of p)."""
    p = np.asarray(p, dtype=float)
    years = data.rows.years
    out = []
    for year in np.unique(years):
        on = years == year
        k = int(data.rows.y[on].sum())
        low, high = poisson_interval(k)
        out.append({'year': int(year), 'observed': k, 'expected': float(p[on].sum()), 'low': low, 'high': high})
    return out


# ---- "When" and "where" ----

def city_chance(data, p) -> np.ndarray:
    """1 - prod_b (1 - p(b, d)) for each city day, over that day's barangay rows."""
    keep = np.ones(len(data.city_day))
    np.multiply.at(keep, np.searchsorted(data.city_day, data.rows.day), 1.0 - np.asarray(p, dtype=float))
    return 1.0 - keep


def when_scores(data, p) -> dict:
    city = city_chance(data, p)
    return {'auc': _auc(data.city_y, city), 'log_loss': float(row_log_loss(data.city_y, city).mean()),
            'days': int(len(city)), 'event_days': int(data.city_y.sum())}


def _top_credit(p: np.ndarray, top: int) -> np.ndarray:
    """1 for a row inside the day's `top` highest chances, 0 outside; rows tied at the boundary share the
    places left evenly (the expected count under a random tie-break)."""
    cut = np.sort(p)[::-1][top - 1]
    above, tied = p > cut, p == cut
    credit = above.astype(float)
    credit[tied] = (top - above.sum()) / tied.sum()
    return credit


def where_scores(data, p) -> dict:
    """On each day with a hit barangay-day: the ROC-AUC of chance against hit (the mean over the days with
    both outcomes), and the lift ratio: the share of hit barangay-days among their day's TOP_N highest
    chances, divided by TOP_N / n (n barangays; 5/22 for Talisay). An even spread has lift 1."""
    p = np.asarray(p, dtype=float)
    y, day = data.rows.y, data.rows.day
    n = len(data.place)
    top = min(TOP_N, n)
    aucs, caught, hits = [], 0.0, 0
    for d in np.unique(day[y == 1]):
        on = day == d
        auc = _auc(y[on], p[on])
        if auc is not None:
            aucs.append(auc)
        caught += float(_top_credit(p[on], top)[y[on] == 1].sum())
        hits += int(y[on].sum())
    return {'auc': float(np.mean(aucs)) if aucs else None, 'auc_days': len(aucs),
            'lift': (caught / hits) / (top / n) if hits else None, 'hit_rows': hits}


# ---- Levels ----

def _barangay_months(data, p):
    """(month index, chance, observed) per barangay-month: chance 1 - prod (1 - p) over the month's days."""
    month = data.rows.day.astype('datetime64[M]').astype(int)
    keys, inverse = np.unique(np.column_stack([month, data.rows.barangay_id]), axis=0, return_inverse=True)
    inverse = inverse.ravel()
    keep = np.ones(len(keys))
    np.multiply.at(keep, inverse, 1.0 - np.asarray(p, dtype=float))
    seen = np.zeros(len(keys), dtype=int)
    np.maximum.at(seen, inverse, data.rows.y)
    return keys[:, 0], 1.0 - keep, seen


def _sedi(H, F) -> float | None:
    if H is None or F is None or not (0 < H < 1 and 0 < F < 1):
        return None
    lf, lh, lnf, lnh = math.log(F), math.log(H), math.log(1 - F), math.log(1 - H)
    return (lf - lh - lnf + lnh) / (lf + lh + lnf + lnh)


def _table(hits: int, misses: int, false_alarms: int, correct_negatives: int) -> dict:
    """The contingency table with POD, FAR, the Peirce skill score, SEDI and false alarms per real event,
    each None when undefined."""
    events, quiet, warned = hits + misses, false_alarms + correct_negatives, hits + false_alarms
    H = hits / events if events else None
    F = false_alarms / quiet if quiet else None
    return {'hits': hits, 'misses': misses, 'false_alarms': false_alarms, 'correct_negatives': correct_negatives,
            'pod': H, 'far': false_alarms / warned if warned else None,
            'peirce': H - F if H is not None and F is not None else None, 'sedi': _sedi(H, F),
            'false_alarms_per_event': false_alarms / events if events else None}


def level_tables(data, p, cutoffs=CUTOFFS) -> list[dict]:
    """Per cut-off, barangay-months warned (month chance >= cut-off) against barangay-months with an event."""
    _, chance, seen = _barangay_months(data, p)
    event = seen == 1
    out = []
    for c in cutoffs:
        warn = chance >= c
        out.append({'cutoff': float(c), **_table(int((warn & event).sum()), int((~warn & event).sum()),
                                                 int((warn & ~event).sum()), int((~warn & ~event).sum()))})
    return out


def breakeven(cutoffs=CUTOFFS) -> list[dict]:
    """What a cut-off c implies at break-even: (1 - c) / c false alarms per real event."""
    return [{'cutoff': float(c), 'false_alarms_per_event': (1 - c) / c} for c in cutoffs]


# ---- The event table ----

def event_table(data, preds: dict) -> list[dict]:
    """One entry per event day (a city day with a kept record), in date order:
      day, subtypes (the day's record subtypes), storm (the storm's name when the flag is on; flood only, None
      for landslide), rain_1day (the day's own rain, hazard_data's r0 window: the rain the PAGASA band reads),
      rain_3day (the r3 window), band (the PAGASA band of rain_1day), and per model in `preds` ({name: chance per
      data.rows row}):
        hit_chance          the mean chance of the day's hit barangays (None when no record names one)
        hit_chance_before   the same barangays' mean chance the day before (None without hits or a day before)
        city_chance         1 - prod_b (1 - p) on the day
        high_barangays      barangays at High (month chance >= HIGH_CHANCE) in the day's month
    """
    rows = data.rows
    storms = data.storms if data.hazard == 'Flood' else None
    r0, r3 = data.window('r0'), data.window('r3')
    band = np.digitize(r0, PAGASA_BANDS)
    subtypes: dict = {}
    for r in data.records:
        subtypes.setdefault(r.day, set()).add(r.subtype)
    city, high = {}, {}
    for name, p in preds.items():
        city[name] = city_chance(data, p)
        month, chance, _ = _barangay_months(data, p)
        m, counts = np.unique(month[chance >= HIGH_CHANCE], return_counts=True)
        high[name] = dict(zip(m.tolist(), counts.tolist()))
    out = []
    for i in np.flatnonzero(data.city_y == 1):
        d = data.city_day[i]
        day = d.astype(object)
        hit = (rows.day == d) & (rows.y == 1)
        before = (rows.day == d - 1) & np.isin(rows.barangay_id, rows.barangay_id[hit])
        month = int(d.astype('datetime64[M]').astype(int))
        models = {}
        for name, p in preds.items():
            p = np.asarray(p, dtype=float)
            models[name] = {'hit_chance': float(p[hit].mean()) if hit.any() else None,
                            'hit_chance_before': float(p[before].mean()) if before.any() else None,
                            'city_chance': float(city[name][i]),
                            'high_barangays': int(high[name].get(month, 0))}
        out.append({'day': day.isoformat(), 'subtypes': sorted(subtypes.get(day, ())),
                    'storm': storms.name(day) if storms is not None else None, 'rain_1day': float(r0[i]),
                    'rain_3day': float(r3[i]), 'band': BAND_LABELS[band[i]], 'models': models})
    return out


# ---- The landslide outside test ----

def _catalogue_rows(data):
    """The current model's features on catalogue-era barangay-days, built as the study rows are
    (build_dataset): every barangay reads the city rain series, with its terrain from the study rows."""
    rows, n_rain = data.rows, len(RAIN_FEATURES)
    terrain = {}
    for b in sorted(data.place):
        i = int(np.flatnonzero(rows.barangay_id == b)[0])
        terrain[b] = dict(zip(rows.features[n_rain:], rows.X[i, n_rain:].tolist()))
    first, last = data.extra_day[0].astype(object), data.extra_day[-1].astype(object)
    ds, _ = build_dataset(data.hazard, terrain, {b: data.rain for b in terrain}, set(), first, last)
    ds = ds.subset(np.isin(ds.day, data.extra_day))
    per_day = np.bincount(np.searchsorted(data.extra_day, ds.day), minlength=len(data.extra_day))
    if (per_day != len(terrain)).any():
        raise ValueError(f'Catalogue day {data.extra_day[per_day != len(terrain)][0]} lacks barangay rows.')
    return ds


def wald_slopes(when, X, era: str) -> dict:
    """Each slope of a single-era "when" fit with its Wald 95% interval, from the inverse Fisher information
    at the FLIC coefficients (None when the information cannot be inverted or a variance is not positive)."""
    X = np.asarray(X, dtype=float)
    design = np.column_stack([np.ones(len(X)), X])
    p = when.chance(X, era)
    info = design.T @ (design * (p * (1 - p))[:, None])
    try:
        variance = np.diag(np.linalg.inv(info))[1:]
    except np.linalg.LinAlgError:
        variance = np.full(len(when.coef), np.nan)
    out = {}
    for f, c, v in zip(when.features, when.coef, variance):
        s = math.sqrt(v) if np.isfinite(v) and v > 0 else None
        out[f] = {'coef': float(c), 'low': None if s is None else float(c - Z95 * s),
                  'high': None if s is None else float(c + Z95 * s)}
    return out


def _cross_era(hazard, X, y, era, X_test, y_test) -> dict:
    when = fit_when(X, y, era=np.array([era] * len(y)), features=FEATURES[hazard])
    return {'auc': _auc(y_test, when.chance(X_test, era)), 'slopes': wald_slopes(when, X, era)}


def outside_test(data, current_fit: dict) -> dict | None:
    """Landslide only (None for flood); spec 2.1 item 3. `current_fit` is the current model's exported fit on
    the whole study period. 'current' scores its city chance on the catalogue-era days it never saw: ROC-AUC
    against catalogue landslide days, and observed (catalogue event days) against expected (the sum of the
    city chance); no log score, since the catalogue's wider area makes its base rate incomparable. The new
    "when" model is fitted on one era and scored on the other by ROC-AUC, with the training era's slopes.
    Without a catalogue era: {'unavailable': reason}."""
    if data.hazard != 'Landslide':
        return None
    if data.extra_day is None:
        return {'unavailable': 'No catalogue era was given, so there are no days outside the study period to '
                               'test on.'}
    ds = _catalogue_rows(data)
    if tuple(current_fit['features']) != tuple(ds.features):
        raise ValueError(f'The current fit reads {current_fit["features"]}, not {list(ds.features)}.')
    keep = np.ones(len(data.extra_day))
    np.multiply.at(keep, np.searchsorted(data.extra_day, ds.day), 1.0 - score_logistic(current_fit, ds.X))
    city = 1.0 - keep
    return {
        'current': {'auc': _auc(data.extra_y, city), 'observed': int(data.extra_y.sum()),
                    'expected': float(city.sum())},
        'catalogue_to_geoalert': _cross_era(data.hazard, data.extra_X, data.extra_y, 'catalogue', data.city_X,
                                            data.city_y),
        'geoalert_to_catalogue': _cross_era(data.hazard, data.city_X, data.city_y, 'geoalert', data.extra_X,
                                            data.extra_y),
    }


# ---- The rule (spec 2.5) ----

LEAKAGE_PASSED = (f'The leakage check passed: every training day lay more than {BUFFER_DAYS} days from the '
                  f'block it predicted.')


def _high_false_alarms(levels: list[dict]):
    for t in levels:
        if t['cutoff'] == HIGH_CHANCE:
            return t['false_alarms_per_event']
    raise ValueError(f'The level tables have no High row (cut-off {HIGH_CHANCE}); rule (b) needs it.')


def _rule_b(data, p_new, p_cur, levels_new, levels_cur) -> tuple[bool, list[str]]:
    """Every compared event day no worse for the new model (hit barangays' mean log score), a better one on
    more than half of them, and no more false alarms per real event at High. Compared: the event days with at
    least one hit row."""
    rows = data.rows
    hit = rows.y == 1
    compared = np.unique(rows.day[hit])
    skipped = int(data.city_y.sum()) - len(compared)
    reasons = []
    if skipped:
        one = skipped == 1
        reasons.append(f'{skipped} event day{"" if one else "s"} named no barangay, so {"it" if one else "they"} '
                       f'had no hit barangay to compare and {"was" if one else "were"} left out of rule (b).')
    if not len(compared):
        reasons.append('No event day had a hit barangay to compare, so rule (b) cannot be met.')
        return False, reasons
    loss_new, loss_cur = -np.log(_clip(p_new)), -np.log(_clip(p_cur))
    worse, better = [], 0
    for d in compared:
        on = hit & (rows.day == d)
        new, cur = float(loss_new[on].mean()), float(loss_cur[on].mean())
        if new > cur:
            worse.append(d)
        better += new < cur
    reasons += [f'It gave a lower chance to the hit barangays on {d.astype(object).isoformat()}.' for d in worse]
    most = better > len(compared) / 2
    if not most:
        reasons.append(f'It gave the hit barangays a better log score on only {better} of the {len(compared)} '
                       f'event days, not more than half.')
    fa_new, fa_cur = _high_false_alarms(levels_new), _high_false_alarms(levels_cur)
    if fa_new is None or fa_cur is None:
        reasons.append('False alarms per real event at High are undefined (no barangay-month held a real '
                       'event), so they cannot be compared.')
        return False, reasons
    if fa_new > fa_cur:
        reasons.append(f'It raised more false alarms per real event at High ({_num(fa_new)} against '
                       f'{_num(fa_cur)}).')
        return False, reasons
    if worse or not most:
        return False, reasons
    reasons.append(f'On each of the {len(compared)} event days with a hit barangay it gave the hit barangays a '
                   f'log score no worse than the current model, a better one on {better}, and no more false '
                   f'alarms per real event at High ({_num(fa_new)} against {_num(fa_cur)}).')
    return True, reasons


def verdict(data, p_new, p_cur, differences, levels_new, levels_cur) -> dict:
    """Whether the new model replaces the current one: (a) or (b), and (c).

    p_new, p_cur        out-of-fold chances on the leave-one-storm-out rows (data.rows)
    differences         cluster_bootstrap's 'differences'; (NEW, CURRENT) holds (observed, low, high)
    levels_new/_cur     level_tables of each model; rule (b) reads the High (HIGH_CHANCE) row
    (a) the interval of the paired log-score difference (new - current) lies wholly below zero (checked first);
    (b) see _rule_b; (c) the leakage check: out_of_fold raises LeakageError before any verdict can be reached,
    so here it has passed (`leakage_checked`). `rule` is 'a', 'b' or None; `reasons` are plain sentences.
    """
    _, low, high = differences[(NEW, CURRENT)]
    interval = f'({plain_number(low)} to {plain_number(high)})'
    if high < 0:
        rule = 'a'
        reasons = [f'The 95% interval of the log-score difference (new minus current) lies wholly below zero '
                   f'{interval}.']
    else:
        reasons = [f'The interval of the log-score difference does not lie wholly below zero {interval}.']
        holds, more = _rule_b(data, p_new, p_cur, levels_new, levels_cur)
        reasons += more
        rule = 'b' if holds else None
    return {'adopted': rule is not None, 'rule': rule, 'reasons': reasons + [LEAKAGE_PASSED],
            'leakage_checked': True}


# ---- Everything ----

def _fold(fold: dict, y: np.ndarray) -> dict:
    return {'train_years': list(fold['train_years']), 'test_year': fold['test_year'],
            'train_event_days': fold['train_event_days'], 'test_event_days': fold['test_event_days'],
            'scores': None if fold['p'] is None else model_scores(y[fold['rows']], fold['p']),
            'reason': fold['reason']}


def evaluate(data, reps: int = BOOTSTRAP_REPS) -> dict:
    """Both models and every baseline on the same rows, the rule, and which model is in use. Strict JSON.

    A contender's CannotEvaluate or FitFailed propagates (no partial report), as does LeakageError. A baseline
    that cannot be fitted is recorded as {'unavailable': reason} and left out of the bootstrap.

    {'tests': {
       'loso': {'rows', 'days', 'event_days', 'hit_rows', 'blocks': {'event', 'month'}, 'reps',
                'models': {name: {'scores': model_scores (Brier skill against 'climatology' and 'rate'),
                                  'log_loss_interval': [low, high], 'when': when_scores, 'where': where_scores,
                                  'levels': level_tables, 'per_year': per_year}
                                 | {'unavailable': reason}},       # 'two_part', 'logistic_regression', baselines
                'differences': {'a - b': {'difference', 'low', 'high'}},   # new - current, each contender - baseline
                'breakeven': breakeven()},
       'yearly': {contender: [{'train_years', 'test_year', 'train_event_days', 'test_event_days',
                               'scores': model_scores | None, 'reason': str | None}]},
       'events': event_table (the two contenders),
       'outside': outside_test (None for flood)},
     'verdict': {'adopted', 'rule', 'reasons', 'leakage_checked'},
     'in_use': 'two_part' | 'logistic_regression'}
    """
    hazard, y = data.hazard, data.rows.y
    blocks = blocks_for(data)
    contenders = [TwoPartContender(hazard), LogisticContender(hazard)]
    preds = {m.name: out_of_fold(m, data, blocks) for m in contenders}
    order, unavailable = [m.name for m in contenders], {}
    for model in baselines(hazard):
        order.append(model.name)
        try:
            preds[model.name] = out_of_fold(model, data, blocks)
        except (CannotEvaluate, FitFailed) as exc:
            unavailable[model.name] = str(exc)
    boot = cluster_bootstrap(data.rows.day, blocks, {n: row_log_loss(y, p) for n, p in preds.items()}, reps)
    clim, rate = preds.get('climatology'), preds.get('rate')
    models = {}
    for name in order:
        if name in unavailable:
            models[name] = {'unavailable': unavailable[name]}
            continue
        p = preds[name]
        models[name] = {'scores': model_scores(y, p, clim, rate), 'log_loss_interval': boot['intervals'][name],
                        'when': when_scores(data, p), 'where': where_scores(data, p),
                        'levels': level_tables(data, p), 'per_year': per_year(data, p)}
    pairs = [(NEW, CURRENT)] + [(a, b) for a in (NEW, CURRENT) for b in order[2:] if b in preds]
    differences = {f'{a} - {b}': dict(zip(('difference', 'low', 'high'), boot['differences'][(a, b)]))
                   for a, b in pairs}
    outside = (outside_test(data, LogisticContender(hazard).fit(data, np.ones(len(data.city_day), bool)))
               if hazard == 'Landslide' else None)    # the current model on the whole study period
    decided = verdict(data, preds[NEW], preds[CURRENT], boot['differences'], models[NEW]['levels'],
                      models[CURRENT]['levels'])
    return to_json_safe({
        'tests': {
            'loso': {'rows': len(y), 'days': len(data.city_day), 'event_days': int(data.city_y.sum()),
                     'hit_rows': int(y.sum()),
                     'blocks': {k: sum(b.kind == k for b in blocks) for k in ('event', 'month')},
                     'reps': reps, 'models': models, 'differences': differences, 'breakeven': breakeven()},
            'yearly': {m.name: [_fold(f, y) for f in yearly_folds(m, data)] for m in contenders},
            'events': event_table(data, {n: preds[n] for n in (NEW, CURRENT)}),
            'outside': outside,
        },
        'verdict': decided,
        'in_use': NEW if decided['adopted'] else CURRENT,
    })
