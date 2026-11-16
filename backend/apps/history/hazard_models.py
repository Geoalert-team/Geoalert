"""The current flood and landslide model (pooled logistic regression) and its export, the counting benchmark,
and the version 2 test report: reading it, the accuracy entries, its plain limits sentences and its credits."""
import json
import logging
import math
from datetime import date

import numpy as np
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.pipeline import make_pipeline as _make_pipeline
from sklearn.preprocessing import FunctionTransformer, StandardScaler

from apps.history.hazard_data import (
    DATA_DIR, HAZARDS, RAIN_FEATURES, STUDY_END, STUDY_START, Dataset, load_records, records_signature)
from apps.history.model_forecast import HIGH_CHANCE, MODERATE_CHANCE

logger = logging.getLogger(__name__)

FOLDS = [((2021, 2022), 2023), ((2021, 2022, 2023), 2024), ((2021, 2022, 2023, 2024), 2025)]
PRIOR_DAYS = 30

LR_SETTINGS = dict(C=1.0, l1_ratio=0.0, solver='lbfgs', max_iter=2000)   # l1_ratio=0 is plain L2


def _imputer():
    # keep_empty_features: an all-NaN training column must stay, or later columns shift out of line.
    return SimpleImputer(strategy='median', keep_empty_features=True)


def make_logistic():
    """Median imputer, log1p on the rain columns, scaler, logistic regression: the current model."""
    log_rain = ColumnTransformer(
        [('log_rain', FunctionTransformer(np.log1p), list(range(len(RAIN_FEATURES))))],
        remainder='passthrough')
    return _make_pipeline(_imputer(), log_rain, StandardScaler(), LogisticRegression(**LR_SETTINGS))


def export_logistic(pipeline, features, X_train) -> dict:
    """The fitted pipeline as plain numbers, for hazard_scoring.score_logistic (NumPy only)."""
    imputer, _, scaler, lr = pipeline[0], pipeline[1], pipeline[2], pipeline[3]
    X_train = np.asarray(X_train, dtype=float)
    with np.errstate(all='ignore'):
        top = np.nanmax(X_train, axis=0) if len(X_train) else np.full(X_train.shape[1], np.nan)
    return to_json_safe({
        'kind': 'logistic_regression',
        'features': list(features),
        'medians': imputer.statistics_,
        'log_columns': list(range(len(RAIN_FEATURES))),
        'mean': scaler.mean_,
        'scale': scaler.scale_,
        'coef': lr.coef_[0],
        'intercept': float(lr.intercept_[0]),
        'training_max': {f: top[i] for i, f in enumerate(features)},
    })


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


class CannotEvaluate(Exception):
    """The data cannot support the test (a fold with no event to learn from); the message says why."""


def _auc(y, score) -> float | None:
    """ROC-AUC, or None when only one class is present."""
    y = np.asarray(y).astype(int)
    return float(roc_auc_score(y, score)) if 0 < y.sum() < len(y) else None


# ---- The report (spec 3.1) ----

REPORT_PATH = DATA_DIR / 'hazard_model_report.json'
REPORT_VERSION = 2
REPORT_MODELS = ('two_part', 'logistic_regression')     # what a version 2 entry's `in_use` may name
REPORT_UNREADABLE = 'The model report is missing or cannot be read; run manage.py test_hazard_models.'
REPORT_OLD = 'The model report is from an older version; run manage.py test_hazard_models.'
LOGGED_SECONDS = 10 * 60        # the accuracy answer's public max-age: the log is read at most this often


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


def _logged(hazard, records, saved, today):
    """
    The hazard's `logged` block scored now from the prediction log, as fire's is (spec 2.1(4): the season is
    scored as it happens), kept LOGGED_SECONDS so the log is not read on every request. When the log cannot be
    read, the block test_hazard_models saved in the report (`saved`, spec 3.5).
    """
    from django.core.cache import cache
    from apps.history.prediction_log import logged_summary

    def score():
        try:
            return logged_summary(hazard, records, today, fallback=saved)
        except Exception:
            logger.exception("The %s prediction log could not be scored; the report's saved block is shown.",
                             hazard.lower())
            return saved

    return cache.get_or_set(f'hazard-logged:{hazard}', score, LOGGED_SECONDS)


def accuracy_entries(today) -> list[dict]:
    """Flood's and landslide's entries for the accuracy card (spec 5.1), from the saved report.

    Each entry is the report's entry for the hazard without its `fits`, with `kind: 'rain_terrain'`,
    `status: 'in_use'` (the report names the model in use, and the verdict says whether the two-part model was
    adopted), the report's study period, its `tested_at` (when it was written), and
      stale   True when the study-period records no longer match the report's data_signature (a record was
              added, changed or deleted). A record dated after the study period changes nothing.
      logged  scored live from the prediction log (_logged), or the report's saved block when the log cannot
              be read.
    A hazard is 'unavailable', with only a `reason` besides, when there is no report or it cannot be read
    (REPORT_UNREADABLE), when the report is not version 2 (REPORT_OLD) or when it has no result for the hazard.
    The report is read at call time (REPORT_PATH), never a path bound at import. `today` mirrors
    model_forecast.accuracy_reports; the saved report does not depend on it.
    """
    report = read_report()
    out = []
    for hazard in HAZARDS:
        entry, reason = None, None
        if report is None:
            reason = REPORT_UNREADABLE
        elif report.get('version') != REPORT_VERSION:
            reason = REPORT_OLD
        else:
            tested = report.get('hazards')
            entry = tested.get(hazard) if isinstance(tested, dict) else None
            if not isinstance(entry, dict) or entry.get('in_use') not in REPORT_MODELS:
                reason = f'The model report has no {hazard.lower()} result; run manage.py test_hazard_models.'
        if reason is not None:
            out.append({'hazard': hazard, 'kind': 'rain_terrain', 'status': 'unavailable', 'reason': reason})
            continue
        records = load_records(hazard)
        stale = records_signature(records, STUDY_START, STUDY_END) != entry.get('data_signature')
        out.append({**{k: v for k, v in entry.items() if k != 'fits'}, 'hazard': hazard, 'kind': 'rain_terrain',
                    'status': 'in_use', 'stale': stale, 'study': report.get('study'),
                    'tested_at': report.get('generated'),
                    'logged': _logged(hazard, records, entry.get('logged'), today)})
    return out


# ---- Limits and credits (spec 5.6 and 5.1) ----

SIGN_TEST_LEVEL = 0.05
RAIN_CREDIT = 'Rain: NASA POWER (CC BY 4.0).'
HAZARD_CREDITS = {
    'Flood': ('Storm tracks: IBTrACS v04r01 (NOAA NCEI).',
              'Flood exposure: UP NOAH flood hazard maps (ODbL), via the bettergovph mirror.',
              'Buildings: Microsoft Global ML Building Footprints (ODbL).'),
    'Landslide': ('Landslide timing also learned from NASA Global Landslide Catalog days near Talisay, 2007–2017.',),
}
SOURCE_LIMITS = {
    'Flood': ("The two-part model's flood shares use UP NOAH flood hazard maps, which are labelled beta, rest on "
              "about 30 years of rain and come from a community mirror; the Mananga River works planned for 2026 "
              "would change river-flood hazard, and the maps do not show them."),
    'Landslide': ("The two-part model also learns landslide timing from NASA's Global Landslide Catalog, which "
                  "states no licence, often places an event only to within 5–25 km, and covers 2007–2017, not the "
                  "years the forecast is for."),
}


def credits_for(hazard: str) -> list[str]:
    """The data credits the accuracy card shows for a hazard."""
    return [RAIN_CREDIT, *HAZARD_CREDITS[hazard]]


def _count(n: int, word: str) -> str:
    return f'{n:,} {word}' + ('' if n == 1 else 's')


def sign_test_p(days: int) -> float:
    """The two-sided sign-test p-value of a model that does better on every one of `days` days."""
    return min(1.0, 2 * 0.5 ** days)


def _sign_test(noun: str, days: int) -> str:
    if days == 0:
        return f'No reported {noun} named a barangay, so the models cannot be compared event day by event day.'
    p = sign_test_p(days)
    every = 'that day' if days == 1 else f'all {days} days'
    if p > SIGN_TEST_LEVEL:
        return (f"With {_count(days, 'such day')}, no model can be shown statistically better day by day: one that "
                f"does better on {every} reaches at best p = {p:.4g} on a two-sided sign test.")
    reaches = f'p = {p:.4g}' if p >= 0.001 else 'p < 0.001'      # plain numbers, never 1.9e-06
    return (f"With {_count(days, 'such day')}, a model that does better on {every} reaches {reaches} on a "
            f"two-sided sign test; doing better on fewer of them is weaker evidence.")


def report_limits(hazard: str, entry: dict, *, barangays: int) -> list[str]:
    """Plain sentences for the accuracy card (spec 5.6), from the entry's numbers; each must be literally true.

    Reads `positives` (barangay-days with a reported event), `positive_days` (the distinct days they fall on, the
    days rule (b) compares), `rows` and, when present, `dropped` (barangay-days left out for missing rain).
    """
    noun = hazard.lower()
    positives, days = entry['positives'], entry['positive_days']
    first = (f"From {STUDY_START.year} to {STUDY_END.year}, {_count(positives, f'reported {noun} barangay-day')} "
             f"{'falls' if positives == 1 else 'fall'} on {_count(days, 'distinct day')}, so the evidence is closer "
             f"to {_count(days, 'day')} than to {_count(entry['rows'], 'row')}")
    dropped = entry.get('dropped') or 0
    if dropped:
        first += (f" ({_count(dropped, 'more barangay-day')} {'was' if dropped == 1 else 'were'} left out because "
                  f"a day of the 14-day rain window was missing)")
    return [
        first + '.',
        _sign_test(noun, days),
        f"Rain comes from one NASA POWER grid cell (about 55 by 69 km) for the city's "
        f"{_count(barangays, 'barangay')}, and the cell's edge at 10.25° N runs through Talisay, so part of the city "
        f"lies outside the cell it reads and local downpours can be missed.",
        f'An empty barangay-day means no {noun} was reported, not that none happened: every chance is of a reported '
        f'{noun} and reads lower than how often {noun}s really happen.',
        SOURCE_LIMITS[hazard],
        f'The {MODERATE_CHANCE:.0%} and {HIGH_CHANCE:.0%} cut-offs and several earlier choices were made after '
        f'seeing {FOLDS[0][1]}–{FOLDS[-1][1]}, so the {STUDY_END.year + 1} season is the clean test.',
    ]
