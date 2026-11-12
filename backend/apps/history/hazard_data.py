"""Records, exclusions and rain windows for the flood and landslide models."""
import csv
import hashlib
import json
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Mapping
from zoneinfo import ZoneInfo

import numpy as np

from apps.history.models import HistoricalRecord

STUDY_START = date(2021, 1, 1)
STUDY_END = date(2025, 12, 31)
HAZARDS = ('Flood', 'Landslide')
RAIN_FEATURES = ('r0', 'r1', 'r3', 'r7', 'r14')
TERRAIN_FEATURES = {
    'Flood': ('hand_lt2', 'hand_lt5', 'elev_lt10', 'water_200', 'coast_500', 'built_density'),
    'Landslide': ('slope_gt18', 'slope_gt30', 'relief', 'road_50', 'stream_150'),
}
DATA_DIR = Path(__file__).parent / 'data'
MANILA = ZoneInfo('Asia/Manila')


@dataclass(frozen=True)
class Record:
    source_ref: str
    hazard: str
    barangay_id: int | None
    day: date
    subtype: str
    is_sample: bool


def load_records(hazard: str) -> list[Record]:
    rows = (HistoricalRecord.objects.filter(hazard_type__name=hazard)
            .values_list('source_ref', 'barangay_id', 'occurred_at', 'hazard_subcategory', 'is_sample'))
    return [Record(ref or '', hazard, brgy, at.astimezone(MANILA).date(), sub, sample)
            for ref, brgy, at, sub, sample in rows]


def load_exclusions(path: Path = DATA_DIR / 'hazard_model_exclusions.csv') -> dict[str, str]:
    with open(path, newline='', encoding='utf-8') as f:
        return {row['source_ref']: row['reason'] for row in csv.DictReader(f)}


def positives(records, barangay_ids: set[int], start: date, end: date, excluded: set[str]) -> set[tuple[int, date]]:
    """Distinct (barangay, day) pairs: real records with a known barangay in the study range."""
    return {(r.barangay_id, r.day) for r in records
            if not r.is_sample and r.barangay_id in barangay_ids
            and start <= r.day <= end and r.source_ref not in excluded}


def rain_windows(daily: Mapping[date, float | None], day: date) -> dict[str, float] | None:
    """Inclusive rain sums ending on `day`; None if any day of the 14 is missing."""
    values = [daily.get(day - timedelta(days=i)) for i in range(14)]   # values[0] is day d
    if any(v is None for v in values):
        return None
    return {'r0': values[0], 'r1': values[1], 'r3': sum(values[:3]),
            'r7': sum(values[:7]), 'r14': sum(values)}


TERRAIN_COLUMNS = TERRAIN_FEATURES['Flood'] + TERRAIN_FEATURES['Landslide']


def terrain_shares(labels, factors, barangay_ids) -> dict[int, dict[str, float]]:
    """Per-barangay terrain features from the grid. Cells labelled 0 belong to no barangay."""
    out = {}
    for bid in barangay_ids:
        m = labels == bid

        def share(name, test):
            return float(np.mean(test(factors[name][m])))

        out[bid] = {
            'cells': int(m.sum()),
            'hand_lt2': share('hand', lambda v: v < 2),
            'hand_lt5': share('hand', lambda v: v < 5),
            'elev_lt10': share('elevation', lambda v: v < 10),
            'water_200': share('dist_water', lambda v: v < 200),
            'coast_500': share('dist_coast', lambda v: v < 500),
            'built_density': float(np.mean(factors['building_density'][m])),
            'slope_gt18': share('slope', lambda v: v > 18),
            'slope_gt30': share('slope', lambda v: v > 30),
            'relief': float(np.mean(factors['relief'][m])),
            'road_50': share('dist_road', lambda v: v < 50),
            'stream_150': share('dist_water', lambda v: v < 150),
        }
    return out


def write_terrain(path, rows: dict[int, dict], names: dict[int, str]):
    with open(path, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['barangay_id', 'barangay', 'cells', *TERRAIN_COLUMNS])
        for bid in sorted(rows):
            r = rows[bid]
            w.writerow([bid, names.get(bid, ''), r['cells'], *(repr(float(r[k])) for k in TERRAIN_COLUMNS)])


def read_terrain(path=DATA_DIR / 'barangay_terrain.csv') -> dict[int, dict[str, float]]:
    with open(path, newline='', encoding='utf-8') as f:
        return {int(row['barangay_id']): {'cells': int(row['cells']),
                                          **{k: float(row[k]) for k in TERRAIN_COLUMNS}}
                for row in csv.DictReader(f)}


@dataclass
class Dataset:
    X: np.ndarray
    y: np.ndarray
    barangay_id: np.ndarray
    day: np.ndarray            # datetime64[D]
    features: tuple[str, ...]

    def subset(self, mask) -> 'Dataset':
        return Dataset(self.X[mask], self.y[mask], self.barangay_id[mask], self.day[mask], self.features)

    @property
    def years(self) -> np.ndarray:
        return self.day.astype('datetime64[Y]').astype(int) + 1970


def build_dataset(hazard: str, terrain, rain, pos: set[tuple[int, date]], start: date, end: date):
    """One row per barangay per day in start..end. Rows without a full 14-day rain window are dropped.

    `rain` is {barangay_id: {date: mm | None}}; only barangays in both `terrain` and `rain` are used.
    Returns (Dataset, number of rows dropped for missing rain).
    """
    terrain_names = TERRAIN_FEATURES[hazard]
    features = RAIN_FEATURES + terrain_names
    days = [start + timedelta(days=i) for i in range((end - start).days + 1)]
    rows, ys, ids, dates = [], [], [], []
    dropped = 0
    for bid in sorted(set(terrain) & set(rain)):
        t = [terrain[bid][k] for k in terrain_names]
        for d in days:
            w = rain_windows(rain[bid], d)
            if w is None:
                dropped += 1
                continue
            rows.append([w[k] for k in RAIN_FEATURES] + t)
            ys.append(1 if (bid, d) in pos else 0)
            ids.append(bid)
            dates.append(d)
    return Dataset(X=np.array(rows, dtype=np.float64).reshape(len(rows), len(features)),
                   y=np.array(ys, dtype=int),
                   barangay_id=np.array(ids, dtype=int),
                   day=np.array(dates, dtype='datetime64[D]'),
                   features=features), dropped


def records_signature(records, start: date, end: date) -> str:
    """sha1 of the real records dated start..end, so a changed record set is noticed."""
    keys = sorted(((r.source_ref, -1 if r.barangay_id is None else r.barangay_id, r.day.isoformat())
                   for r in records if not r.is_sample and start <= r.day <= end))
    return hashlib.sha1(json.dumps(keys).encode('utf-8')).hexdigest()
