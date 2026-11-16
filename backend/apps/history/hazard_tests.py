"""The flood and landslide test designs (spec Section 2), part 1.

The data bundle (HazardData), the leave-one-storm-out blocks with their 14-day buffer, out-of-fold prediction
with a leakage guard, the yearly folds, the two contenders, the seven baselines and the cluster bootstrap.

Contenders and baselines share one protocol:
  name                          'two_part', 'logistic_regression', or a baseline name in BASELINES
  fit(data, train) -> fitted    `train` is a boolean mask over data.city_day; nothing else of the study is seen
  predict(fitted, data, days)   the chance for every data.rows row whose day is in `days`, in row order
The landslide two-part model also always trains on the catalogue era (2007-2017), which lies years before
any study day. Every other model trains on study days only.
"""
import math
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Sequence

import numpy as np

from apps.history.firth import FitFailed
from apps.history.hazard_data import STUDY_END, STUDY_START, Dataset, build_dataset, positives, rain_windows
from apps.history.hazard_models import FOLDS, CannotEvaluate, benchmark_probs, export_logistic, make_logistic
from apps.history.hazard_scoring import score_logistic, score_two_part
from apps.history.landslide_catalogue import named_barangay
from apps.history.two_part import FEATURES, TwoPartFit, fit_when, flood_shares, landslide_shares, when_row

BUFFER_DAYS = 14          # the longest rain window: no training window overlaps a held-out day
CLUSTER_GAP_DAYS = 14     # event days less than this far apart form one cluster
CLUSTER_PAD_DAYS = 7      # a cluster's block runs from 7 days before its first day to 7 days after its last
BOOTSTRAP_REPS = 1000
BOOTSTRAP_SEED = 0
STEEP_GATE = 0.10         # landslide rules: only barangays with slope_gt18 >= 0.10 get a chance
PAGASA_BANDS = (50.0, 100.0, 200.0)   # 1-day rain (mm): [0, 50), [50, 100), [100, 200), [200, inf)
EULER_GAMMA = 0.5772
CATALOGUE_START = date(2007, 1, 1)
CATALOGUE_LAST = date(2017, 12, 31)   # 2018-2020 are never rows
BASELINES = {
    'Flood': ('climatology', 'rate', 'pagasa_bands', 'rain_only', 'persistence'),
    'Landslide': ('climatology', 'rate', 'persistence', 'return_level', 'p95_7day'),
}


class LeakageError(Exception):
    """A training day lies within BUFFER_DAYS of the block it is meant to predict."""


def _d64(days) -> np.ndarray:
    return np.asarray(days, dtype='datetime64[D]')


def _dates(days) -> list[date]:
    return _d64(days).astype(object).tolist()


def _span(first: date, last: date) -> list[date]:
    return [first + timedelta(days=i) for i in range((last - first).days + 1)]


def _years(days) -> np.ndarray:
    return _d64(days).astype('datetime64[Y]').astype(int) + 1970


# ---- The data bundle ----

@dataclass(eq=False)
class HazardData:
    hazard: str
    rows: Dataset                   # study barangay-days on city days, the current model's features
    city_day: np.ndarray            # datetime64[D], sorted: study days with complete "when" inputs
    city_X: np.ndarray              # FEATURES[hazard] per city day
    city_y: np.ndarray              # 1 when any kept record is dated that day, barangay known or not
    extra_day: np.ndarray | None    # landslide catalogue era (else None)
    extra_X: np.ndarray | None
    extra_y: np.ndarray | None
    place: dict                     # {barangay_id: E_b (flood) or slope_gt18 (landslide)}
    named_events: list              # [(day, {barangay_id, ...})]: city days with records naming a barangay
    extra_named: list               # the same for catalogue records that name a Talisay barangay
    rain: dict                      # the city rain series {date: mm | None}
    records: list                   # the kept study-period records of this hazard
    storms: object = None           # the StormDays used (flood), for the event table
    _windows: dict = field(default_factory=dict, repr=False)

    def window(self, key: str) -> np.ndarray:
        """The rain sum `key` ('r0', 'r1', 'r3', 'r7' or 'r14') ending on each city day."""
        if not self._windows:
            sums = [rain_windows(self.rain, d) for d in _dates(self.city_day)]
            self._windows.update({k: np.array([s[k] for s in sums], dtype=float) for k in sums[0]})
        return self._windows[key]


def build_hazard_data(hazard, terrain, rain_file, storms, exposure, records, excluded, catalogue=None,
                      names=None, catalogue_end=None) -> HazardData:
    """Everything the tests need for one hazard, from the files the command reads.

    terrain    read_terrain rows; rain_file a RainFile; storms StormDays (flood; landslide does not use it)
    exposure   read_exposure rows (flood); every study barangay must have one
    records    hazard_data Records; real ones dated in the study period and not in `excluded` are kept
    catalogue  the landslide catalogue records `near()` kept; names {barangay_id: name} to match them
    catalogue_end  landslide_catalogue.era_end over the WHOLE catalogue, near Talisay or not, so where the last
               event fell never moves the era's end (spec 1.4); needed with a catalogue
    Study barangays are those with both a terrain row and a rain series. The city rain series is the lowest
    such barangay id's: every barangay reads the one NASA POWER city cell, so the series are identical.
    Rows are kept only on city days (all barangays present, "when" inputs complete), so every model and
    baseline is scored on the same rows.
    """
    if hazard not in FEATURES:
        raise ValueError(f'unknown hazard {hazard}')
    ids = sorted(set(terrain) & set(rain_file.rain))
    if not ids:
        raise ValueError('No barangay has both a terrain row and a rain series.')
    if hazard == 'Flood':
        missing = [b for b in ids if not exposure or b not in exposure]
        if missing:
            raise ValueError(f'No exposure figures for barangay {missing[0]}; run build_hazard_features.')
        place = {b: float(exposure[b]['exposure']) for b in ids}
    else:
        place = {b: float(terrain[b]['slope_gt18']) for b in ids}
    excluded = set(excluded)
    kept = sorted((r for r in records if r.hazard == hazard and not r.is_sample and r.source_ref not in excluded
                   and STUDY_START <= r.day <= STUDY_END), key=lambda r: (r.day, r.source_ref))
    rain = rain_file.rain[ids[0]]
    pos = positives(kept, set(ids), STUDY_START, STUDY_END, set())
    ds, _ = build_dataset(hazard, {b: terrain[b] for b in ids}, rain_file.rain, pos, STUDY_START, STUDY_END)
    found, counts = np.unique(ds.day, return_counts=True)
    whole = set(_dates(found[counts == len(ids)]))
    days, X = [], []
    for d in _span(STUDY_START, STUDY_END):
        row = when_row(hazard, rain, storms, d) if d in whole else None
        if row is not None:
            days.append(d)
            X.append(row)
    if not days:
        raise ValueError(f'{hazard}: no study day has complete rain and "when" inputs.')
    event_days = {r.day for r in kept}
    on_city = set(days)
    named: dict = {}
    for b, d in pos:
        if d in on_city:
            named.setdefault(d, set()).add(b)
    extra_day = extra_X = extra_y = None
    extra_named: list = []
    if hazard == 'Landslide' and catalogue:
        extra_day, extra_X, extra_y, extra_named = _catalogue_era(catalogue, rain, names, set(ids), catalogue_end)
    city_day = _d64(days)
    return HazardData(
        hazard=hazard, rows=ds.subset(np.isin(ds.day, city_day)), city_day=city_day,
        city_X=np.array(X, dtype=float).reshape(len(days), len(FEATURES[hazard])),
        city_y=np.array([int(d in event_days) for d in days], dtype=int),
        extra_day=extra_day, extra_X=extra_X, extra_y=extra_y, place=place,
        named_events=sorted(named.items()), extra_named=extra_named, rain=rain, records=kept, storms=storms)


def _catalogue_era(catalogue, rain, names, ids, catalogue_end):
    """Catalogue-era days (2007-01-01 to `catalogue_end`, the end of the whole catalogue's last record's month,
    never past 2017) with their "when" rows, whether a nearby catalogue record is dated that day, and the days
    whose records name a barangay."""
    if names is None:
        raise ValueError('Barangay names are needed to read which barangay a catalogue record names.')
    if catalogue_end is None:
        raise ValueError("The catalogue era's end (era_end over the whole catalogue) is needed with a catalogue.")
    last = min(catalogue_end, CATALOGUE_LAST)
    in_era = [r for r in catalogue if CATALOGUE_START <= r.day <= last]
    hit_days = {r.day for r in in_era}
    days, X = [], []
    for d in _span(CATALOGUE_START, last):
        row = when_row('Landslide', rain, None, d)
        if row is not None:
            days.append(d)
            X.append(row)
    if not days:
        raise ValueError('No catalogue-era day has 14 days of rain; run fetch_rain.')
    named: dict = {}
    for r in in_era:
        b = named_barangay(r, names)
        if b in ids:
            named.setdefault(r.day, set()).add(b)
    return (_d64(days), np.array(X, dtype=float), np.array([int(d in hit_days) for d in days], dtype=int),
            sorted(named.items()))


# ---- Leave one storm out ----

@dataclass(frozen=True)
class Block:
    label: str
    kind: str       # 'event' or 'month'
    start: date
    end: date


def event_clusters(event_days: Sequence[date]) -> list[list[date]]:
    """Event days in date order; a day less than CLUSTER_GAP_DAYS after the previous one joins its cluster."""
    out: list[list[date]] = []
    for d in sorted(set(_dates(event_days))):
        if out and (d - out[-1][-1]).days < CLUSTER_GAP_DAYS:
            out[-1].append(d)
        else:
            out.append([d])
    return out


def loso_blocks(days: Sequence[date], event_days: Sequence[date]) -> list[Block]:
    """Each cluster's block runs from CLUSTER_PAD_DAYS before its first day to CLUSTER_PAD_DAYS after its
    last; when two blocks would share a day (clusters exactly 14 days apart) the later one starts a day
    later. Every other day of `days` belongs to its calendar month's block, which spans what is left of
    the month (assign_blocks gives a day inside an event block's dates to that event block)."""
    pad = timedelta(days=CLUSTER_PAD_DAYS)
    events: list[Block] = []
    for cluster in event_clusters(event_days):
        start, end = cluster[0] - pad, cluster[-1] + pad
        if events and start <= events[-1].end:
            start = events[-1].end + timedelta(days=1)
        label = cluster[0].isoformat() if len(cluster) == 1 else f'{cluster[0].isoformat()}..{cluster[-1].isoformat()}'
        events.append(Block(label, 'event', start, end))
    months: dict = {}
    for d in sorted(set(_dates(days))):
        if not any(b.start <= d <= b.end for b in events):
            months.setdefault((d.year, d.month), []).append(d)
    blocks = events + [Block(f'{y}-{m:02d}', 'month', ds[0], ds[-1]) for (y, m), ds in months.items()]
    return sorted(blocks, key=lambda b: b.start)


def assign_blocks(days, blocks: list[Block]) -> np.ndarray:
    """The index in `blocks` of each day's block, -1 for none. A day inside an event block's dates belongs
    to it; any other day to the month block whose dates cover it. Overlapping blocks of one kind raise."""
    d = _d64(days)
    owner = {'month': np.full(len(d), -1), 'event': np.full(len(d), -1)}
    for i, b in enumerate(blocks):
        inside = (d >= np.datetime64(b.start)) & (d <= np.datetime64(b.end))
        taken = owner[b.kind]
        if (taken[inside] >= 0).any():
            raise ValueError(f'block {b.label} overlaps block {blocks[taken[inside].max()].label}')
        taken[inside] = i
    return np.where(owner['event'] >= 0, owner['event'], owner['month'])


def blocks_for(data: HazardData) -> list[Block]:
    """The leave-one-storm-out blocks over the city days; event days are the city days with a kept record."""
    return loso_blocks(data.city_day, data.city_day[data.city_y == 1])


def train_mask(days: np.ndarray, block: Block) -> np.ndarray:
    """True for days more than BUFFER_DAYS from the block's dates."""
    d = _d64(days)
    return (d < np.datetime64(block.start) - BUFFER_DAYS) | (d > np.datetime64(block.end) + BUFFER_DAYS)


def _check_buffer(days, train, block: Block, held):
    """LeakageError if a training day lies within BUFFER_DAYS of the block's dates or of any held-out day
    (so a block whose dates do not cover its held-out days is caught too)."""
    t = _d64(days)[np.asarray(train, dtype=bool)]
    near = (t >= np.datetime64(block.start) - BUFFER_DAYS) & (t <= np.datetime64(block.end) + BUFFER_DAYS)
    h = np.sort(_d64(held))
    if len(h) and len(t):
        i = np.searchsorted(h, t)
        before, after = h[np.clip(i - 1, 0, len(h) - 1)], h[np.clip(i, 0, len(h) - 1)]
        gap = np.minimum(np.abs(t - before), np.abs(t - after)).astype(int)
        near |= gap <= BUFFER_DAYS
    if near.any():
        raise LeakageError(f'Block {block.label}: training day {t[near][0]} lies within {BUFFER_DAYS} days of the '
                           f'held-out days ({block.start.isoformat()}..{block.end.isoformat()}).')


def out_of_fold(contender, data: HazardData, blocks: list[Block]) -> np.ndarray:
    """One out-of-fold chance per data.rows row: each block is predicted by a fit on the days more than
    BUFFER_DAYS away from it. Raises LeakageError if a training mask reaches into a block's buffer."""
    day_owner = assign_blocks(data.city_day, blocks)
    if (day_owner < 0).any():
        raise ValueError(f'City day {data.city_day[day_owner < 0][0]} is in no block.')
    row_owner = day_owner[np.searchsorted(data.city_day, data.rows.day)]
    out = np.full(len(data.rows.y), np.nan)
    for i, block in enumerate(blocks):
        held = day_owner == i
        if not held.any():
            continue
        train = train_mask(data.city_day, block)
        _check_buffer(data.city_day, train, block, data.city_day[held])
        p = np.asarray(contender.predict(contender.fit(data, train), data, data.city_day[held]), dtype=float)
        rows = row_owner == i
        if p.shape != (int(rows.sum()),):
            raise ValueError(f'{contender.name} gave {p.shape} chances for the {int(rows.sum())} rows of '
                             f'{block.label}.')
        out[rows] = p
    if np.isnan(out).any():
        raise ValueError(f'{contender.name} left a row without a chance.')
    return out


def yearly_folds(contender, data: HazardData) -> list[dict]:
    """FOLDS: train on the earlier years, test the next (no buffer, as before; not used by the rule).
    A fold that cannot be fitted keeps p None and says why in `reason`."""
    city_years, row_years = _years(data.city_day), data.rows.years
    out = []
    for train_years, test_year in FOLDS:
        train, test = np.isin(city_years, train_years), city_years == test_year
        fold = {'train_years': list(train_years), 'test_year': test_year, 'rows': row_years == test_year,
                'train_event_days': int(data.city_y[train].sum()), 'test_event_days': int(data.city_y[test].sum()),
                'p': None, 'reason': None}
        try:
            fold['p'] = np.asarray(contender.predict(contender.fit(data, train), data, data.city_day[test]))
        except (CannotEvaluate, FitFailed) as exc:
            fold['reason'] = str(exc)
        out.append(fold)
    return out


# ---- Contenders ----

def _train_rows(data: HazardData, train) -> np.ndarray:
    return np.isin(data.rows.day, data.city_day[np.asarray(train, dtype=bool)])


def _training_events(data: HazardData, train) -> list[set]:
    """Named event days on training days plus every named catalogue day (always in training): the
    landslide two-part model's beta fit."""
    kept = set(_dates(data.city_day[np.asarray(train, dtype=bool)]))
    return [set(s) for d, s in data.named_events if d in kept] + [set(s) for _, s in data.extra_named]


def mean_hits(data: HazardData, train, catalogue: bool = False) -> float:
    """k, the mean number of barangays hit per event day in training: barangay-day positives on the training
    days over the training event days (city_y == 1), so an event day whose records name no barangay counts
    with 0 hits. With `catalogue` (the landslide two-part model only), the named catalogue days join both
    counts. Raises CannotEvaluate when the training rows hold no event."""
    train = np.asarray(train, dtype=bool)
    hits = float(data.rows.y[_train_rows(data, train)].sum())
    days = int(data.city_y[train].sum())
    if catalogue:
        hits += sum(len(s) for _, s in data.extra_named)
        days += len(data.extra_named)
    if hits == 0:
        raise CannotEvaluate(f'{data.hazard}: the training rows hold no event with a known barangay, so the '
                             f'number of barangays per event day is unknown.')
    return hits / days


def _check_hazard(model, data: HazardData):
    if data.hazard != model.hazard:
        raise ValueError(f'{model.name} for {model.hazard} was given {data.hazard} data.')


class TwoPartContender:
    """The new model: q(d) from Firth/FLIC on the "when" features, times the barangay's share a_b, with
    lambda (and landslide's beta) refitted from the training events only."""
    name = 'two_part'

    def __init__(self, hazard: str):
        self.hazard = hazard
        self.features = FEATURES[hazard]

    def _cols(self) -> list[int]:
        return [FEATURES[self.hazard].index(f) for f in self.features]

    def fit(self, data: HazardData, train) -> TwoPartFit:
        _check_hazard(self, data)
        train = np.asarray(train, dtype=bool)
        X, y = data.city_X[train][:, self._cols()], data.city_y[train]
        if not y.any():
            raise CannotEvaluate(f'{data.hazard}: the training days hold no reported event, so "when" cannot be '
                                 f'fitted.')
        era = np.array(['geoalert'] * len(y))
        if data.extra_day is not None:
            X = np.vstack([X, data.extra_X[:, self._cols()]])
            y = np.concatenate([y, data.extra_y])
            era = np.concatenate([era, np.array(['catalogue'] * len(data.extra_y))])
        when = fit_when(X, y, era=era, features=self.features)
        k = mean_hits(data, train, catalogue=True)       # flood has no catalogue days, so this is GeoAlert only
        beta = None
        if self.hazard == 'Flood':
            shares, lam = flood_shares(data.place, k)
        else:
            shares, lam, beta = landslide_shares(data.place, _training_events(data, train), k)
        top = {f: float(X[:, j].max()) for j, f in enumerate(self.features)}
        return TwoPartFit(self.hazard, when, shares, lam, beta, top)

    def predict(self, fitted: TwoPartFit, data: HazardData, days) -> np.ndarray:
        rows = np.isin(data.rows.day, _d64(days))
        index = np.searchsorted(data.city_day, data.rows.day[rows])
        return score_two_part(fitted.to_json(), data.city_X[:, self._cols()], index, data.rows.barangay_id[rows])


class RainOnly(TwoPartContender):
    """Flood baseline: the two-part model without the storm flag, with the same "where" shares."""
    name = 'rain_only'

    def __init__(self, hazard: str = 'Flood'):
        super().__init__(hazard)
        self.features = ('log1p_r3',)


class LogisticContender:
    """The current model: pooled logistic regression on rain and terrain, study barangay-days only."""
    name = 'logistic_regression'

    def __init__(self, hazard: str):
        self.hazard = hazard

    def fit(self, data: HazardData, train) -> dict:
        _check_hazard(self, data)
        rows = _train_rows(data, train)
        X, y = data.rows.X[rows], data.rows.y[rows]
        if not 0 < y.sum() < len(y):
            raise CannotEvaluate(f'{data.hazard}: the training rows need both event and non-event barangay-days.')
        return export_logistic(make_logistic().fit(X, y), data.rows.features, X)

    def predict(self, fitted: dict, data: HazardData, days) -> np.ndarray:
        return score_logistic(fitted, data.rows.X[np.isin(data.rows.day, _d64(days))])


# ---- Baselines ----

class BarangayRate:
    """The shrunken barangay-by-calendar-month rate (benchmark_probs). A benchmark, never a forecast."""
    name = 'rate'

    def fit(self, data: HazardData, train) -> Dataset:
        rows = data.rows.subset(_train_rows(data, train))
        if not rows.y.any():
            raise CannotEvaluate(f'{data.hazard}: the training rows hold no event, so the rate is not a benchmark.')
        return rows

    def predict(self, fitted: Dataset, data: HazardData, days) -> np.ndarray:
        return benchmark_probs(fitted, data.rows.subset(np.isin(data.rows.day, _d64(days))))


def _class_chances(classes: np.ndarray, y: np.ndarray, train: np.ndarray, n: int) -> list[float]:
    """(training event days in the class + 0.5) / (training days in the class + 1), for classes 0..n-1."""
    c, hit = classes[train], y[train]
    return [(float(hit[c == j].sum()) + 0.5) / (float((c == j).sum()) + 1.0) for j in range(n)]


class _CityRule:
    """A baseline with a city chance q(d) and no "where" of its own. Each barangay gets q x k / n (n study
    barangays), or for a gated rule q x k / (number gated) if slope_gt18 >= STEEP_GATE and 0 otherwise;
    capped at 1. k is mean_hits on the GeoAlert training days (never the catalogue); q comes from training
    city-days only. Raises CannotEvaluate when the training rows hold no event."""
    name = ''
    gated = False

    def fit(self, data: HazardData, train) -> dict:
        if self.gated and data.hazard != 'Landslide':
            raise ValueError(f'{self.name} is a landslide rule.')
        train = np.asarray(train, dtype=bool)
        k = mean_hits(data, train)
        fitted = self._fit_city(data, train)
        fitted['k'] = k
        fitted['factor'] = self._factors(data, k)
        return fitted

    def _factors(self, data: HazardData, k: float) -> dict:
        if not self.gated:
            return {b: k / len(data.place) for b in data.place}
        steep = [b for b, s in data.place.items() if s >= STEEP_GATE]
        if not steep:
            raise CannotEvaluate(f'No barangay has slope_gt18 of at least {STEEP_GATE}.')
        return {b: (k / len(steep) if b in steep else 0.0) for b in data.place}

    def predict(self, fitted: dict, data: HazardData, days) -> np.ndarray:
        rows = np.isin(data.rows.day, _d64(days))
        q = self._city(fitted, data)[np.searchsorted(data.city_day, data.rows.day[rows])]
        factor = np.array([fitted['factor'][int(b)] for b in data.rows.barangay_id[rows]], dtype=float)
        return np.minimum(1.0, q * factor)


class Climatology(_CityRule):
    """The training city-day event rate, spread evenly; with k as above this equals the training
    barangay-day event rate."""
    name = 'climatology'

    def _fit_city(self, data, train):
        return {'rate': float(data.city_y[train].mean())}

    def _city(self, fitted, data):
        return np.full(len(data.city_day), fitted['rate'])


class _ClassRule(_CityRule):
    """City chance per class of the day's rain, as _class_chances on the training days."""
    n_classes = 0

    def _fit_city(self, data, train):
        fitted = self._threshold(data, train)
        fitted['chances'] = _class_chances(self._classes(fitted, data), data.city_y, train, self.n_classes)
        return fitted

    def _city(self, fitted, data):
        return np.asarray(fitted['chances'], dtype=float)[self._classes(fitted, data)]


class Persistence(_ClassRule):
    """Two classes, other days (0) and days after an event day (1), each with the class chance (events + 0.5)
    / (days + 1) on training days, so it is never exactly 0. An event day is a day with a kept record."""
    name = 'persistence'
    n_classes = 2

    def _threshold(self, data, train):
        return {}

    def _classes(self, fitted, data):
        return np.isin(data.city_day - 1, _d64(sorted({r.day for r in data.records}))).astype(int)


class PagasaBands(_ClassRule):
    """Flood: PAGASA 24-hour bands of the day's rain (r0)."""
    name = 'pagasa_bands'
    n_classes = len(PAGASA_BANDS) + 1

    def _threshold(self, data, train):
        return {}

    def _classes(self, fitted, data):
        return np.digitize(data.window('r0'), PAGASA_BANDS)


class ReturnLevel(_ClassRule):
    """Landslide (Dynaslope style): T2, the 2-year return level of the annual maximum 1-day rain (Gumbel by
    moments on complete training years: every day of the year a training day); classes r0 >= T2, >= T2/2,
    below."""
    name = 'return_level'
    gated = True
    n_classes = 3

    def _threshold(self, data, train):
        r0, years = data.window('r0'), _years(data.city_day)
        complete = [int(y) for y in np.unique(years)
                    if int((train & (years == y)).sum()) == (date(int(y), 12, 31) - date(int(y), 1, 1)).days + 1]
        if len(complete) < 2:
            raise CannotEvaluate(f'The 2-year return level needs at least two complete training years, not '
                                 f'{len(complete)}.')
        maxima = np.array([r0[years == y].max() for y in complete])
        beta = float(maxima.std(ddof=1)) * math.sqrt(6) / math.pi
        mu = float(maxima.mean()) - EULER_GAMMA * beta
        return {'t2': mu - beta * math.log(-math.log(0.5)), 'years': complete}

    def _classes(self, fitted, data):
        r0 = data.window('r0')
        return (r0 >= fitted['t2'] / 2).astype(int) + (r0 >= fitted['t2']).astype(int)


class SevenDayP95(_ClassRule):
    """Landslide (LHASA v1 style): the 95th percentile of 7-day rain on training days; classes r7 >= it, below."""
    name = 'p95_7day'
    gated = True
    n_classes = 2

    def _threshold(self, data, train):
        return {'p95': float(np.percentile(data.window('r7')[train], 95))}

    def _classes(self, fitted, data):
        return (data.window('r7') >= fitted['p95']).astype(int)


BASELINE_TYPES = {c.name: c for c in (Climatology, BarangayRate, PagasaBands, RainOnly, Persistence, ReturnLevel,
                                      SevenDayP95)}


def baselines(hazard: str) -> list:
    return [BASELINE_TYPES[name]() for name in BASELINES[hazard]]


# ---- Intervals ----

def _interval(values) -> tuple[float, float]:
    low, high = np.percentile(values, [2.5, 97.5])
    return float(low), float(high)


def cluster_bootstrap(row_day: np.ndarray, blocks: list[Block], losses: dict, reps: int = BOOTSTRAP_REPS,
                      seed: int = BOOTSTRAP_SEED) -> dict:
    """95% intervals of each model's mean row loss and of paired differences (a - b). Event blocks and month
    blocks are resampled separately, with replacement, each keeping its count; a block's rows (all the
    barangays of its days) stay together. A difference's first number is the observed one."""
    owner = assign_blocks(row_day, blocks)
    if (owner < 0).any():
        raise ValueError(f'Row day {_d64(row_day)[owner < 0][0]} is in no block.')
    names = list(losses)
    loss = np.column_stack([np.asarray(losses[n], dtype=float) for n in names])
    if loss.shape[0] != len(owner):
        raise ValueError(f'{loss.shape[0]} losses for {len(owner)} row days.')
    sums = np.zeros((len(blocks), len(names)))
    np.add.at(sums, owner, loss)
    counts = np.bincount(owner, minlength=len(blocks)).astype(float)
    rng = np.random.default_rng(seed)
    total, size = np.zeros((reps, len(names))), np.zeros(reps)
    for kind in ('event', 'month'):
        pool = np.array([i for i, b in enumerate(blocks) if b.kind == kind and counts[i] > 0], dtype=int)
        if len(pool):
            picks = pool[rng.integers(0, len(pool), size=(reps, len(pool)))]
            total += sums[picks].sum(axis=1)
            size += counts[picks].sum(axis=1)
    means = total / size[:, None]
    observed = loss.mean(axis=0)
    return {
        'intervals': {n: _interval(means[:, j]) for j, n in enumerate(names)},
        'differences': {(a, b): (float(observed[i] - observed[j]), *_interval(means[:, i] - means[:, j]))
                        for i, a in enumerate(names) for j, b in enumerate(names) if i != j},
    }
