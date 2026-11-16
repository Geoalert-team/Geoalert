"""
Fire's contender and the test that decides between it and today's model
(spec Section 4).

F0, 'current', is today's Poisson regression (model_forecast.rates_table).
F1, 'pooled_exposure', is fixed in advance:

  expected fires(b, m) = buildings_b × exp(μ + u_b + Σ_{k=1,2} [a_k·sin(2πkm/12) + c_k·cos(2πkm/12)])

the barangay's building count as its exposure (in place of area and
puroks), two yearly waves for the season (in place of 11 month terms), and a
term u_b for every barangay pulled toward the city level by a penalty that is
chosen inside the training months only (choose_penalty).

The test (compare): both models are refitted on every month before each of
the last TEST_MONTHS full months and forecast it, one month ahead. Each
barangay-month is scored with the Poisson log score; F1 replaces F0 only when
the mean difference (F1 - F0) and its whole 95% month-block bootstrap
interval are below zero (verdict). A barangay with no building count makes
F1 untestable, and F0 stays with the reason. Two checks on the model in use
are reported, not built on: the Pearson dispersion of its training fit, and
Moran's I of each barangay's leftover error over the window.

Model fitting and the statistics live here; the database (the barangays'
neighbours) and the cache stay in model_forecast.py, which calls compare.
"""
import math
from collections import Counter
from datetime import date
from functools import partial

import numpy as np

from apps.history.exposure import EXPOSURE_FILE, read_exposure
from apps.history.model_forecast import (
    MIN_RATE, MIN_TEST_EVENTS, MIN_TRAIN_EVENTS, TEST_MONTHS, _index, _known, _label, _matrix, _scores, _span,
    plain_number, rates_table)

F1_NAME = 'pooled_exposure'
F0_NAME = 'current'
PENALTIES = (0.001, 0.003, 0.01, 0.03, 0.1, 0.3, 1.0)
INNER_MONTHS = 6
DISPERSION_FLAG = 1.5
MORAN_PERMUTATIONS = 999
MORAN_FLAG_P = 0.05
BOOTSTRAP_REPS = 1000
BOOTSTRAP_SEED = 0
HARMONICS = 2           # yearly waves: 2πm/12 and 4πm/12

TOO_FEW_TO_COMPARE = 'Too few fire records to compare the two models.'
NO_BUILDINGS = ('The building counts (barangay_exposure.csv) are missing or cannot be read; run manage.py '
                'build_hazard_features. The pooled exposure model was not tested.')
MISSING_BUILDINGS = 'No building count for {}; the pooled exposure model was not tested.'
SECONDARY_NOTE = ("Less clean: from the first month with 100 earlier fires, months on which today's model's "
                  'settings were chosen.')


def read_buildings(path=EXPOSURE_FILE) -> dict[int, int]:
    """Each barangay's building count (Microsoft footprints), from the exposure file."""
    return {bid: int(round(row['buildings'])) for bid, row in read_exposure(path).items()}


def missing_buildings(places, buildings) -> list[str]:
    """The places with no building count or a count of 0: F1's log offset is undefined there."""
    return [p['name'] for p in places if buildings.get(p['id'], 0) <= 0]


# ---- F1 ----

def fit_with_exposure(x, y, exposure, penalty):
    """
    A Poisson regression with log(exposure) as an offset, by the offset trick:
    the target is count ÷ exposure and the sample weight is the exposure,
    which has the same likelihood. Returns expected(rows, exposure), the
    expected counts. The exposure enters in units of its mean: scikit-learn
    divides the loss by the sum of the weights, so in raw building counts the
    targets (a few fires per ten thousand building-months) leave the loss too
    flat for its tolerance and no coefficient moves from 0. In mean units the
    loss is on the count scale, as in F0, and the fit is unchanged otherwise:
    the unit only shifts the intercept.
    """
    from sklearn.linear_model import PoissonRegressor

    exposure = np.asarray(exposure, float)
    unit = exposure.mean()
    weight = exposure / unit
    model = PoissonRegressor(alpha=penalty, max_iter=2000).fit(x, np.asarray(y, float) / weight, sample_weight=weight)
    return lambda rows, at: model.predict(rows) * np.asarray(at, float) / unit


def _season(month):
    return [f(2 * math.pi * k * month / 12) for k in range(1, HARMONICS + 1) for f in (math.sin, math.cos)]


def _design(places, months_of_year):
    """One row per (place, month of the year), place by place: a term per barangay, then the yearly waves."""
    x = np.zeros((len(places) * len(months_of_year), len(places) + 2 * HARMONICS))
    for row, (i, month) in enumerate((i, m) for i in range(len(places)) for m in months_of_year):
        x[row, i] = 1
        x[row, len(places):] = _season(month)
    return x


def _observed(counts, places, months) -> np.ndarray:
    """Fires per (month, place): one row per month of `months`, one column per place."""
    return np.array([[counts[(p['id'], m)] for p in places] for m in months])


def _table(counts, places, buildings, months, penalty):
    """F1 fitted on the month indexes `months`: {barangay id: [fires expected in January, ..., December]}."""
    size = np.array([float(buildings[p['id']]) for p in places])
    x = _design(places, [m % 12 + 1 for m in months])
    y = _observed(counts, places, months).T.ravel()            # place by place, as the design's rows
    expected = fit_with_exposure(x, y, np.repeat(size, len(months)), penalty)
    rates = expected(_design(places, range(1, 13)), np.repeat(size, 12)).reshape(len(places), 12)
    return {p['id']: [float(r) for r in row] for p, row in zip(places, rates)}


def _log_score(y, rates) -> np.ndarray:
    """The Poisson log score of each count (minus its log chance; lower is better), the rate floored at MIN_RATE."""
    from scipy.stats import poisson
    return -poisson.logpmf(y, np.maximum(rates, MIN_RATE))


def _training(events, places, until, today):
    """(counts, first, end): fires per (barangay, month) in the months first..end-1, those before `until`."""
    known = _known(events, places)
    if not known:
        return Counter(), 0, 0
    first, end = _span(known, until, today)
    return Counter((e['barangay_id'], _index(e['when'])) for e in known if _index(e['when']) < end), first, end


def _penalty(counts, places, buildings, first, end):
    """Each penalty fitted on the months first..end-1 except the last INNER_MONTHS and scored on those; the best."""
    inner = end - INNER_MONTHS
    scored = range(inner, end)
    y = _observed(counts, places, scored)
    losses = []
    for penalty in PENALTIES:
        table = _table(counts, places, buildings, range(first, inner), penalty)
        rates = np.array([[table[p['id']][m % 12] for p in places] for m in scored])
        losses.append(_log_score(y, rates).mean())
    return PENALTIES[int(np.argmin(losses))]


def choose_penalty(events, places, buildings, until, today) -> float | None:
    """
    F1's penalty for the months before `until` (all of the record without
    it), chosen on those months only. None when they are INNER_MONTHS or
    fewer: no months would be left to fit on.
    """
    counts, first, end = _training(events, places, until, today)
    if end - first <= INNER_MONTHS:
        return None
    return _penalty(counts, places, buildings, first, end)


def exposure_rates_table(events, places, buildings, *, until=None, today):
    """
    F1 as {barangay id: [fires expected in January, ..., December]}, trained
    on the months before `until` (all of the record without it), as
    model_forecast.rates_table. None when they hold fewer than
    MIN_TRAIN_EVENTS, or too few months to choose the penalty.
    """
    counts, first, end = _training(events, places, until, today)
    if sum(counts.values()) < MIN_TRAIN_EVENTS or end - first <= INNER_MONTHS:
        return None
    return _table(counts, places, buildings, range(first, end), _penalty(counts, places, buildings, first, end))


# ---- The comparison's statistics ----

def one_month_ahead(table_fn, events, places, months: range, today) -> np.ndarray:
    """
    Each month in `months` forecast by `table_fn` refitted on every month
    before it: fires expected per (month, place), one row per month.
    """
    out = np.zeros((len(months), len(places)))
    for row, month in enumerate(months):
        table = table_fn(events, places, until=date(month // 12, month % 12 + 1, 1), today=today)
        if table is None:
            raise ValueError(f'Too few fire records before {_label(month)} to forecast it.')
        out[row] = [table[p['id']][month % 12] for p in places]
    return out


def dm_hln(d: np.ndarray, h: int = 1) -> dict:
    """
    The Diebold-Mariano test of a loss difference series with the
    Harvey-Leybourne-Newbold small-sample correction: DM × √((T + 1 − 2h +
    h(h − 1)/T)/T), against Student's t with T − 1 degrees of freedom,
    two-sided. No figures for a series too short or with no spread.
    """
    from scipy.stats import t

    d = np.asarray(d, float)
    n = len(d)
    if n < 2:
        return {'statistic': None, 'p': None}
    centred = d - d.mean()
    variance = (centred @ centred + 2 * sum(centred[k:] @ centred[:-k] for k in range(1, h))) / n
    if not variance > 0:
        return {'statistic': None, 'p': None}
    statistic = d.mean() / math.sqrt(variance / n) * math.sqrt((n + 1 - 2 * h + h * (h - 1) / n) / n)
    return {'statistic': float(statistic), 'p': float(2 * t.sf(abs(statistic), n - 1))}


def coverage80(y, rates) -> float:
    """The share of counts inside their Poisson 80% range, the 10th to the 90th percentile."""
    from scipy.stats import poisson

    mu = np.maximum(rates, MIN_RATE)
    y = np.asarray(y)
    return float(((y >= poisson.ppf(0.1, mu)) & (y <= poisson.ppf(0.9, mu))).mean())


def pit_histogram(y, rates, bins=10, seed=0) -> list[int]:
    """The randomised probability integral transform of each count, in `bins` equal bins: flat when calibrated."""
    from scipy.stats import poisson

    mu = np.maximum(rates, MIN_RATE)
    y = np.asarray(y)
    below, upto = poisson.cdf(y - 1, mu), poisson.cdf(y, mu)
    u = below + np.random.default_rng(seed).random(len(y)) * (upto - below)
    return np.histogram(u, bins=bins, range=(0, 1))[0].tolist()


def dispersion(y, rates, n_params) -> float:
    """Pearson dispersion, Σ (y − μ)² / μ over (rows − parameters fitted): near 1 for a Poisson spread."""
    y, mu = np.asarray(y, float), np.asarray(rates, float)
    return float(((y - mu) ** 2 / mu).sum() / (len(y) - n_params))


def morans_i(values: dict[int, float], neighbours: dict[int, set[int]], permutations=MORAN_PERMUTATIONS,
             seed=0) -> dict:
    """
    Moran's I of the values over barangays that are neighbours (weight 1, else
    0) and its one-sided permutation p-value for clustering: the share of
    random reassignments of the values with an I at least as large, counting
    the observed one. No figures without neighbours or without spread.
    """
    ids = sorted(values)
    spot = {b: i for i, b in enumerate(ids)}
    w = np.zeros((len(ids), len(ids)))
    for b in ids:
        for other in neighbours.get(b, ()):
            if other in spot and other != b:
                w[spot[b], spot[other]] = 1
    z = np.array([values[b] for b in ids], float)
    z -= z.mean()
    if not w.sum() > 0 or not z @ z > 0:
        return {'i': None, 'p': None}

    def statistic(v):
        return len(v) / w.sum() * (v @ w @ v) / (v @ v)

    observed = statistic(z)
    rng = np.random.default_rng(seed)
    shuffled = np.array([statistic(rng.permutation(z)) for _ in range(permutations)])
    at_least = int((shuffled >= observed - 1e-12).sum())
    return {'i': float(observed), 'p': (at_least + 1) / (permutations + 1)}


# ---- The comparison and the rule ----

def verdict(difference: dict) -> dict:
    """
    The rule (spec 4.4): F1 replaces F0 only when the mean paired log-score
    difference (F1 − F0) is below zero and its 95% interval lies wholly below.
    """
    mean, low, high = difference['mean'], difference['low'], difference['high']
    figures = (f'mean log-score difference {plain_number(mean)} per barangay-month, 95% interval '
               f'{plain_number(low)} to {plain_number(high)}')
    if mean < 0 and high < 0:
        return {'adopted': True, 'reasons': [f'The pooled exposure model forecast better: {figures}, wholly below '
                                             'zero.']}
    return {'adopted': False, 'reasons': [f'Tested, not better: {figures}, not wholly below zero.']}


def _difference(y, f0, f1):
    """
    The paired log-score difference (F1 − F0) as month means: their mean, its
    month-block bootstrap 95% interval and the DM test.
    """
    by_month = (_log_score(y, f1) - _log_score(y, f0)).mean(axis=1)
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    means = by_month[rng.integers(0, len(by_month), size=(BOOTSTRAP_REPS, len(by_month)))].mean(axis=1)
    low, high = np.percentile(means, [2.5, 97.5])
    return {'mean': float(by_month.mean()), 'low': float(low), 'high': float(high), 'dm': dm_hln(by_month)}


def _rounded(difference):
    return {**{k: round(difference[k], 5) for k in ('mean', 'low', 'high')}, 'dm': difference['dm']}


def _model_scores(y, rates):
    """A model's scores on (month, place) counts: log score, model_forecast's four, 80% coverage and PIT."""
    flat_y, flat_rates = y.ravel(), rates.ravel()
    months = np.repeat(np.arange(len(y)), y.shape[1])
    return {'log_score': round(float(_log_score(flat_y, flat_rates).mean()), 4),
            **_scores(months, flat_y, flat_rates, 1 - np.exp(-flat_rates)),
            'coverage80': round(coverage80(flat_y, flat_rates), 4),
            'pit': pit_histogram(flat_y, flat_rates)}


def untested(reason, window=None) -> dict:
    """The comparison's result when it did not run: today's model stays, with the reason."""
    return {'in_use': F0_NAME, 'verdict': {'adopted': False, 'reasons': [reason]}, 'window': window,
            'models': {F0_NAME: None, F1_NAME: None}, 'difference': None, 'secondary': None,
            'dispersion': None, 'dispersion_flag': False, 'morans_i': None}


def _first_trainable(known, first, start):
    """The first month with MIN_TRAIN_EVENTS fires and more than INNER_MONTHS months before it, at most `start`."""
    by_month = Counter(_index(e['when']) for e in known)
    month, before = first, 0
    while month < start and (before < MIN_TRAIN_EVENTS or month - first <= INNER_MONTHS):
        before += by_month[month]
        month += 1
    return month


def compare(events, places, buildings, neighbours, today) -> dict:
    """
    Test F1 against F0 one month ahead on the last TEST_MONTHS full months and
    apply the rule (spec 4.3-4.5). `buildings` is None when there are no
    building counts. Returns {in_use, verdict: {adopted, reasons}, window,
    models: {current, pooled_exposure}, difference: {mean, low, high, dm},
    secondary, dispersion, dispersion_flag, morans_i}.
    """
    known = _known(events, places)
    if not known:
        return untested(TOO_FEW_TO_COMPARE)
    first, end = _span(known, None, today)
    start = end - TEST_MONTHS
    window = {'start': _label(start), 'end': _label(end - 1)}
    before = sum(1 for e in known if _index(e['when']) < start)
    if before < MIN_TRAIN_EVENTS or sum(1 for e in known if start <= _index(e['when']) < end) < MIN_TEST_EVENTS:
        return untested(TOO_FEW_TO_COMPARE, window)
    untestable = None
    if buildings is None:
        untestable = NO_BUILDINGS
    elif missing := missing_buildings(places, buildings):
        untestable = MISSING_BUILDINGS.format(', '.join(missing))
    testable = untestable is None
    out = untested(untestable, window)      # filled in below; the verdict too when F1 is tested

    # The secondary window starts earlier and ends with the main one, so one run of forecasts serves both
    lead = _first_trainable(known, first, start) if testable else start
    months = range(lead, end)
    counts = Counter((e['barangay_id'], _index(e['when'])) for e in known)
    y = _observed(counts, places, months)
    main = slice(start - lead, None)
    f0 = one_month_ahead(rates_table, events, places, months, today)
    out['models'][F0_NAME] = _model_scores(y[main], f0[main])
    in_use, in_use_fn, in_use_rates = F0_NAME, rates_table, f0
    if testable:
        f1_fn = partial(exposure_rates_table, buildings=buildings)
        f1 = one_month_ahead(f1_fn, events, places, months, today)
        out['models'][F1_NAME] = _model_scores(y[main], f1[main])
        difference = _difference(y[main], f0[main], f1[main])
        out['verdict'], out['difference'] = verdict(difference), _rounded(difference)
        out['secondary'] = {'window': {'start': _label(lead), 'end': _label(end - 1)}, 'note': SECONDARY_NOTE,
                            'models': {F0_NAME: _model_scores(y, f0), F1_NAME: _model_scores(y, f1)},
                            'difference': _rounded(_difference(y, f0, f1))}
        if out['verdict']['adopted']:
            in_use, in_use_fn, in_use_rates = F1_NAME, f1_fn, f1
    out['in_use'] = in_use

    # Checks on the model in use, reported and not built on (spec 4.5)
    table = in_use_fn(events, places, today=today)
    trained = range(first, end)
    fitted = np.array([[table[p['id']][m % 12] for p in places] for m in trained])
    # parameters: a coefficient per column of the model's design, and its intercept
    columns = _matrix([], [p['id'] for p in places]) if in_use == F0_NAME else _design(places, [])
    n_params = columns.shape[1] + 1
    out['dispersion'] = round(dispersion(_observed(counts, places, trained).ravel(), fitted.ravel(), n_params), 3)
    out['dispersion_flag'] = out['dispersion'] > DISPERSION_FLAG
    leftover = (y[main] - in_use_rates[main]).sum(axis=0)
    moran = morans_i({p['id']: float(r) for p, r in zip(places, leftover)}, neighbours)
    out['morans_i'] = {**moran, 'flag': moran['p'] is not None and moran['p'] < MORAN_FLAG_P}
    return out
