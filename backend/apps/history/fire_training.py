"""
Training the fire risk model: the yes/no label, the area-month panel, the
candidate models and the rule that picks one (spec sections 4.2-4.5).

Adapted from the City of Pittsburgh Bureau of Fire / Carnegie Mellon Metro21
fire risk model (github.com/CityofPittsburgh/fire_risk_analysis, MIT License,
© 2017 mmadaio). Pittsburgh labelled each property 1 if it had a fire in the
year and compared XGBoost, a random forest and AdaBoost (riskmodel.py,
Allmodels.py). Here each row is an area in a month, labelled `fire_occurred`
(1 if any fire is linked to the area that month, else 0), and the same three
families, with Pittsburgh's own settings among their candidates, are tried
beside logistic regression and a small neural network. Their code is Python 2
and uses removed scikit-learn modules, so the recipe is ported, not run.

Fire records are read in one place, fire_records(), and become only the 1/0
label: no count, rate or past fire of an area is ever a model input. The
inputs are the area's features (fire_features.FEATURE_COLUMNS) and the two
month-of-year waves.

Offline only (manage.py train_fire_model): the website reads the model file and
never imports this module, so the server needs neither scikit-learn nor xgboost.
"""
import math
import warnings
from dataclasses import dataclass

import numpy as np

from apps.history import fire_features as ff

MONTH_COLUMNS = ('month_sin', 'month_cos')
SEED = 27  # Pittsburgh's random_state
CLIP = 1e-6
BOOT_REPS = 1000
BOOT_SEED = 0
MLP_SEEDS = range(5)


@dataclass
class FireRecord:
    when: object          # Manila local datetime
    purok_ids: list
    barangay_id: object   # int or None
    record_id: str = ''   # the HistoricalRecord id, for the model's version stamp


def month_index(when):
    """Months since year 0: year × 12 + month − 1."""
    return when.year * 12 + when.month - 1


def fire_records():
    """
    Every recorded fire, oldest first, in Manila time as the forecast reads
    months (views._forecast_events). The only place this model reads fire
    records; they become the yes/no label and nothing else.
    """
    from django.utils import timezone

    from apps.history.forecast import as_local
    from apps.history.models import HistoricalRecord

    tz = timezone.get_current_timezone()
    records = (HistoricalRecord.objects.filter(hazard_type__name__iexact='fire')
               .prefetch_related('puroks').order_by('occurred_at', 'id'))
    return [FireRecord(when=as_local(r.occurred_at, tz), purok_ids=sorted(p.id for p in r.puroks.all()),
                       barangay_id=r.barangay_id, record_id=str(r.id)) for r in records]


def labels(fires, purok_ids, first, end):
    """
    ({(area id, month index): 1} for every area with a fire linked to it that
    month, the fires in [first, end) linked to none of purok_ids). A fire in two
    areas marks both; two fires in one area-month still mark it once.
    """
    marks, unplaced = {}, []
    for fire in fires:
        m = month_index(fire.when)
        if not first <= m < end:
            continue
        linked = [p for p in fire.purok_ids if p in purok_ids]
        if not linked:
            unplaced.append(fire)
        for p in linked:
            marks[(p, m)] = 1
    return marks, unplaced


@dataclass
class Panel:
    X: np.ndarray
    y: np.ndarray        # fire_occurred, 1 or 0
    purok: np.ndarray
    barangay: np.ndarray
    month: np.ndarray    # month index
    columns: list
    fold: np.ndarray | None = None  # the leave-one-out group of each row; None means the calendar year


def month_waves(months):
    """sin and cos of 2π × month of year / 12, as an (n, 2) array."""
    of_year = np.asarray(months) % 12 + 1
    angle = 2 * math.pi * of_year / 12
    return np.c_[np.sin(angle), np.cos(angle)]


def feature_matrix(table):
    """(columns, (areas, inputs) array) from a FeatureTable: log(1 + x) on LOG_COLUMNS, dropped inputs left out."""
    columns = [c for c in ff.FEATURE_COLUMNS if c not in table.dropped]
    A = np.array([[float(r[c]) for c in columns] for r in table.rows], float).reshape(len(table.rows), len(columns))
    for j, c in enumerate(columns):
        if c in ff.LOG_COLUMNS:
            A[:, j] = np.log1p(A[:, j])
    bad = [c for j, c in enumerate(columns) if not np.isfinite(A[:, j]).all()]
    if bad:
        raise ValueError(f'Some areas have no value for {", ".join(bad)}; rerun build_fire_features.')
    return columns, A


def build_panel(table, label_map, months, fold_end=None):
    """One row per area per month in `months` (month indexes), month by month.
    With fold_end, the folds count back from it in blocks of 12 months (0 = the 12 months before fold_end)."""
    columns, A = feature_matrix(table)
    months = list(months)
    n = len(table.rows)
    ids = np.array([r['purok_id'] for r in table.rows], int)
    brgy = np.array([r['barangay_id'] for r in table.rows], int)
    month = np.repeat(np.array(months, int), n)
    purok = np.tile(ids, len(months))
    X = np.hstack([np.tile(A, (len(months), 1)), month_waves(month)])
    y = np.array([label_map.get((int(p), int(m)), 0) for p, m in zip(purok, month)], int)
    fold = None if fold_end is None else (fold_end - 1 - month) // 12
    return Panel(X=X, y=y, purok=purok, barangay=np.tile(brgy, len(months)), month=month,
                 columns=columns + list(MONTH_COLUMNS), fold=fold)


def _grid(**axes):
    keys = list(axes)
    out = [{}]
    for k in keys:
        out = [dict(d, **{k: v}) for d in out for v in axes[k]]
    return out


# Spec 4.4. Pittsburgh's own settings are one candidate in each of their three families.
CANDIDATES = {
    'logistic_regression': [{'label': f'C={c}', 'C': c} for c in (0.01, 0.1, 1)],
    'random_forest': (
        [{'label': 'pittsburgh', 'n_estimators': 500, 'max_depth': 10, 'max_features': 'log2', 'min_samples_leaf': 1}]
        + [dict(s, label=f'depth {s["max_depth"]}, leaf {s["min_samples_leaf"]}', n_estimators=500,
                max_features='log2') for s in _grid(max_depth=(3, 5), min_samples_leaf=(20, 100))]),
    'adaboost': (
        [{'label': 'pittsburgh', 'n_estimators': 1000, 'learning_rate': 1.0}]
        + [{'label': f'100 trees, rate {r}', 'n_estimators': 100, 'learning_rate': r} for r in (0.1, 1)]),
    'xgboost': (
        [{'label': 'pittsburgh', 'learning_rate': 0.13, 'n_estimators': 1500, 'max_depth': 3, 'gamma': 0.5,
          'colsample_bytree': 0.6, 'min_child_weight': 1}]
        + [dict(s, label=(f'rate {s["learning_rate"]}, {s["n_estimators"]} trees, depth {s["max_depth"]}, '
                          f'min child {s["min_child_weight"]}'), gamma=0.0, colsample_bytree=1.0)
           for s in _grid(learning_rate=(0.03, 0.1), n_estimators=(100, 300), max_depth=(2, 3),
                          min_child_weight=(5, 20))]),
    'neural_network': [{'label': f'{h} hidden, decay {a}', 'hidden': h, 'alpha': a} for h in (8, 32) for a in (1, 10)],
}
FAMILY_NAMES = {'logistic_regression': 'logistic regression', 'random_forest': 'random forest',
                'adaboost': 'AdaBoost', 'xgboost': 'XGBoost', 'neural_network': 'neural network'}


class SeedAverage:
    """The mean predict_proba of the same model fitted from several seeds (the neural network's candidates)."""

    def __init__(self, build, seeds=MLP_SEEDS):
        self.build, self.seeds = build, list(seeds)

    def get_params(self, deep=True):
        return self.build(self.seeds[0]).get_params(deep) if deep else {'seeds': self.seeds}

    def fit(self, X, y):
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')  # a small network stopping at max_iter is expected and harmless
            self.models_ = [self.build(s).fit(X, y) for s in self.seeds]
        return self

    def predict_proba(self, X):
        return np.mean([m.predict_proba(X) for m in self.models_], axis=0)


def make_model(family, settings, seed=SEED):
    """An unfitted estimator with predict_proba. No resampling and no class weights (spec 4.4)."""
    from sklearn.ensemble import AdaBoostClassifier, RandomForestClassifier
    from sklearn.linear_model import LogisticRegression
    from sklearn.neural_network import MLPClassifier
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    if family == 'logistic_regression':
        return make_pipeline(StandardScaler(), LogisticRegression(C=settings['C'], max_iter=5000))
    if family == 'random_forest':
        return RandomForestClassifier(n_estimators=settings['n_estimators'], max_depth=settings['max_depth'],
                                      max_features=settings['max_features'],
                                      min_samples_leaf=settings['min_samples_leaf'], random_state=seed, n_jobs=-1)
    if family == 'adaboost':
        return AdaBoostClassifier(n_estimators=settings['n_estimators'], learning_rate=settings['learning_rate'],
                                  random_state=seed)
    if family == 'xgboost':
        from xgboost import XGBClassifier
        return XGBClassifier(learning_rate=settings['learning_rate'], n_estimators=settings['n_estimators'],
                             max_depth=settings['max_depth'], gamma=settings['gamma'],
                             colsample_bytree=settings['colsample_bytree'],
                             min_child_weight=settings['min_child_weight'], objective='binary:logistic',
                             eval_metric='logloss', scale_pos_weight=1, tree_method='hist', random_state=seed,
                             n_jobs=4)
    if family == 'neural_network':
        return SeedAverage(lambda s: make_pipeline(StandardScaler(), MLPClassifier(
            hidden_layer_sizes=(settings['hidden'],), alpha=settings['alpha'], max_iter=500, random_state=s)))
    raise ValueError(f'Unknown model family: {family}')


def clip(p):
    return np.clip(np.asarray(p, float), CLIP, 1 - CLIP)


def fit_predict(family, settings, X_train, y_train, X_test):
    """
    The chance of a fire for X_test from a model fitted on the training rows.
    Training rows with no fire (or only fires) can't fit a classifier, so their
    rate is the answer.
    """
    if y_train.min() == y_train.max():
        return np.full(len(X_test), float(y_train.mean()))
    model = make_model(family, settings)
    model.fit(X_train, y_train)
    return model.predict_proba(X_test)[:, 1]


def oof(panel, family, settings):
    """Leave-one-fold-out predictions (calendar years unless the panel has folds), clipped to [1e-6, 1 − 1e-6]."""
    years = panel.month // 12 if panel.fold is None else panel.fold
    p = np.zeros(len(panel.y))
    for year in np.unique(years):
        held = years == year
        p[held] = fit_predict(family, settings, panel.X[~held], panel.y[~held], panel.X[held])
    return clip(p)


def row_log_loss(y, p):
    p = clip(p)
    return -(y * np.log(p) + (1 - y) * np.log(1 - p))


def brier(y, p):
    return float(np.mean((np.asarray(p, float) - y) ** 2))


def cluster_bootstrap(values, groups, reps=BOOT_REPS, seed=BOOT_SEED):
    """Means of `values` over `reps` resamples of whole groups (barangays), with replacement."""
    ids, inverse = np.unique(groups, return_inverse=True)
    sums = np.bincount(inverse, weights=values, minlength=len(ids))
    sizes = np.bincount(inverse, minlength=len(ids)).astype(float)
    pick = np.random.default_rng(seed).integers(0, len(ids), size=(reps, len(ids)))
    return sums[pick].sum(axis=1) / sizes[pick].sum(axis=1)


@dataclass
class Choice:
    family: str
    settings: dict
    oof: np.ndarray
    candidates: list   # {family, label, log_loss, brier} for every setting tried
    verdict: dict      # {adopted, mean, low, high, reasons}


def _best(rows):
    """The lowest log loss, Brier breaking ties, then the first listed."""
    return min(enumerate(rows), key=lambda t: (round(t[1]['log_loss'], 12), round(t[1]['brier'], 12), t[0]))[1]


def choose(panel, candidates=None):
    """
    The rule fixed in advance (spec 4.4): each family keeps its setting with the
    lowest leave-one-year-out log loss; the best family replaces logistic
    regression only if its paired log-loss gain has a 95% interval, from 1000
    resamples of barangays, wholly below zero. Otherwise logistic regression stays.
    """
    candidates = candidates or CANDIDATES
    rows, preds = [], {}
    for family, grid in candidates.items():
        for settings in grid:
            p = oof(panel, family, settings)
            preds[(family, settings['label'])] = p
            rows.append({'family': family, 'label': settings['label'],
                         'log_loss': float(row_log_loss(panel.y, p).mean()), 'brier': brier(panel.y, p)})
    per_family = {f: _best([r for r in rows if r['family'] == f]) for f in candidates}
    base = per_family['logistic_regression']
    best = _best(list(per_family.values()))

    def settings_of(row):
        return next(s for s in candidates[row['family']] if s['label'] == row['label'])

    base_p = preds[(base['family'], base['label'])]
    if best['family'] == 'logistic_regression':
        verdict = {'adopted': False, 'mean': 0.0, 'low': 0.0, 'high': 0.0,
                   'reasons': ['Logistic regression had the lowest leave-one-year-out log loss, so it is used.']}
        chosen = base
    else:
        best_p = preds[(best['family'], best['label'])]
        diff = row_log_loss(panel.y, best_p) - row_log_loss(panel.y, base_p)
        boots = cluster_bootstrap(diff, panel.barangay)
        mean, low, high = float(diff.mean()), float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))
        adopted = high < 0
        name = FAMILY_NAMES[best['family']]
        gain = (f'{name} ({best["label"]}) scored {mean:+.5f} log loss per area-month against logistic regression '
                f'(95% interval {low:+.5f} to {high:+.5f}, resampling barangays)')
        reasons = [gain + (': wholly below zero, so it replaces logistic regression.' if adopted else
                           ': the interval reaches zero or above, so the simpler logistic regression is kept.')]
        verdict = {'adopted': adopted, 'mean': mean, 'low': low, 'high': high, 'reasons': reasons}
        chosen = best if adopted else base
    return Choice(family=chosen['family'], settings=settings_of(chosen),
                  oof=preds[(chosen['family'], chosen['label'])], candidates=rows, verdict=verdict)


def logit(p):
    p = clip(p)
    return np.log(p / (1 - p))


def fit_platt(p, y):
    """(a, b) of the Platt recalibration P = 1 / (1 + e^−(a + b·logit p)), fitted by maximum likelihood."""
    from sklearn.linear_model import LogisticRegression

    y = np.asarray(y, int)
    if y.min() == y.max():
        return 0.0, 1.0  # nothing to calibrate against
    model = LogisticRegression(C=np.inf, max_iter=5000).fit(logit(p).reshape(-1, 1), y)
    return float(model.intercept_[0]), float(model.coef_[0, 0])


def apply_platt(p, a, b):
    return 1 / (1 + np.exp(-(a + b * logit(p))))


@dataclass
class Fitted:
    family: str
    settings: dict
    model: object
    platt: tuple

    def predict(self, X):
        """Calibrated chance of at least one fire in the area-month."""
        return clip(apply_platt(self.model.predict_proba(X)[:, 1], *self.platt))


def fit_final(panel, choice):
    """The chosen model fitted on the whole panel, with Platt's recalibration from its leave-one-year-out predictions."""
    if panel.y.min() == panel.y.max():
        raise ValueError('The training months need both months with a fire and months without one.')
    model = make_model(choice.family, choice.settings)
    model.fit(panel.X, panel.y)
    return Fitted(choice.family, choice.settings, model, fit_platt(choice.oof, panel.y))
