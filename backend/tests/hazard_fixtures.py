"""Synthetic inputs for the hazard model tests (not collected as tests)."""
import hashlib
import json
from datetime import date, timedelta
from pathlib import Path

import numpy as np

from apps.history.hazard_data import (
    HAZARDS, STUDY_END, STUDY_START, TERRAIN_COLUMNS, Record, records_signature, write_terrain)
from apps.history.rain import write_rain_csv

HEAVY_DAYS_PER_YEAR = 4


def toy_inputs(n_barangays=3, start=date(2021, 1, 1), end=date(2025, 12, 31), seed=0):
    """(terrain, rain, pos) for barangays 1..n, with barangay 1 the most hazard-prone.

    Rain covers 13 days before `start` through `end`; most days are light and a few per calendar year
    are heavy. Positives fall only on heavy days, and every calendar year in the range has at least one.
    """
    rng = np.random.default_rng(seed)
    ids = range(1, n_barangays + 1)
    all_days = [start - timedelta(days=13) + timedelta(days=i) for i in range((end - start).days + 14)]
    base = {d: float(rng.uniform(0, 5)) for d in all_days}
    heavy = []
    for year in range(start.year, end.year + 1):
        first, last = max(start, date(year, 1, 1)), min(end, date(year, 12, 31))
        span = (last - first).days + 1
        picks = sorted(rng.choice(span, size=min(HEAVY_DAYS_PER_YEAR, span), replace=False))
        heavy.append([first + timedelta(days=int(i)) for i in picks])
    heavy_mm = {d: float(rng.uniform(60, 120)) for days in heavy for d in days}

    rain, pos = {}, set()
    for b in ids:
        scale = float(rng.uniform(0.9, 1.1))
        rain[b] = {d: heavy_mm[d] * scale if d in heavy_mm else base[d] * scale for d in all_days}
        for days in heavy:
            # barangay 1 floods on every heavy day, later ones on fewer, but each on at least one
            for d in days[:max(1, HEAVY_DAYS_PER_YEAR + 1 - b)]:
                pos.add((b, d))

    terrain = {}
    for b in ids:
        t = (b - 1) / max(n_barangays - 1, 1)        # 0 for barangay 1 (most prone) up to 1
        terrain[b] = {'cells': 1000 + 500 * b}
        for i, col in enumerate(TERRAIN_COLUMNS):
            terrain[b][col] = 100.0 * (1 - t) + 20.0 + i if col == 'relief' else 0.7 - 0.5 * t - 0.01 * i
    return terrain, rain, pos


def toy_source_ref(hazard, barangay_id, day):
    """The source_ref of a toy event, so a test's database records match the toy report's data_signature."""
    return f'toy-{hazard}-{barangay_id}-{day.isoformat()}'


def toy_event_records(hazard, pos):
    """The toy events of one hazard as hazard_data Records, one per (barangay, day) in `pos`."""
    return [Record(toy_source_ref(hazard, b, d), hazard, b, d, 'TOY', False) for b, d in sorted(pos)]


def _sha1(path):
    return hashlib.sha1(Path(path).read_bytes()).hexdigest()


def write_toy_files(dirpath, barangay_ids, winner='logistic_regression', calibrated=False):
    """Write the model's four data files into `dirpath` from toy_inputs and return (terrain, rain, pos).

    Toy barangay i becomes barangay_ids[i - 1], each in its own grid cell. The files are rain_daily.csv,
    barangay_terrain.csv, hazard_model_exclusions.csv (no record left out) and hazard_model_report.json, a
    minimal report in test_hazard_models' shape: for both hazards the `winner`, `calibrated_all_folds` and the
    `data_signature` of toy_event_records(hazard, pos), and the three files' sha1s. `pos` serves both hazards and
    lies in the study period.
    """
    dirpath = Path(dirpath)
    toy_terrain, toy_rain, toy_pos = toy_inputs(n_barangays=len(barangay_ids))
    real = dict(zip(range(1, len(barangay_ids) + 1), barangay_ids))
    terrain = {real[t]: row for t, row in toy_terrain.items()}
    rain = {real[t]: series for t, series in toy_rain.items()}
    pos = {(real[t], d) for t, d in toy_pos}
    cells = {real[t]: (10.25 + 0.1 * t, 123.85) for t in toy_rain}
    write_rain_csv(dirpath / 'rain_daily.csv', rain, cells)
    write_terrain(dirpath / 'barangay_terrain.csv', terrain, {b: f'Toy {b}' for b in terrain})
    with open(dirpath / 'hazard_model_exclusions.csv', 'w', newline='', encoding='utf-8') as f:
        f.write('source_ref,reason\r\n')
    report = {
        'generated': '2026-11-12T00:00:00+08:00',
        'study': {'start': STUDY_START.isoformat(), 'end': STUDY_END.isoformat()},
        'files': {'rain_sha1': _sha1(dirpath / 'rain_daily.csv'),
                  'terrain_sha1': _sha1(dirpath / 'barangay_terrain.csv'),
                  'exclusions_sha1': _sha1(dirpath / 'hazard_model_exclusions.csv')},
        'hazards': {h: {'hazard': h, 'winner': winner, 'calibrated_all_folds': calibrated,
                        'data_signature': records_signature(toy_event_records(h, pos), STUDY_START, STUDY_END)}
                    for h in HAZARDS},
    }
    with open(dirpath / 'hazard_model_report.json', 'w', encoding='utf-8', newline='\n') as f:
        f.write(json.dumps(report, indent=2) + '\n')
    return terrain, rain, pos
