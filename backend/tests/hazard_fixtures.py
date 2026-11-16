"""Synthetic inputs for the hazard model tests (not collected as tests)."""
import hashlib
import json
import math
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np

from apps.history.hazard_data import (
    RAIN_FEATURES, STUDY_END, STUDY_START, TERRAIN_COLUMNS, TERRAIN_FEATURES, Record, read_terrain,
    records_signature, write_terrain)
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


def _placed(barangay_ids):
    """toy_inputs with toy barangay i renamed barangay_ids[i - 1]: (terrain, rain, pos)."""
    toy_terrain, toy_rain, toy_pos = toy_inputs(n_barangays=len(barangay_ids))
    real = dict(zip(range(1, len(barangay_ids) + 1), barangay_ids))
    return ({real[t]: row for t, row in toy_terrain.items()}, {real[t]: series for t, series in toy_rain.items()},
            {(real[t], d) for t, d in toy_pos})


TOY_STORM_THROUGH = date(2026, 12, 31)     # past the toy rain file, so the tests' late days have a storm flag
TOY_STORM = ('TOY2021', 'TOY', 120.0)      # (storm id, name, closest km) on every toy storm day


def write_toy_storms(dirpath, first_day, last_day, days=()):
    """storm_days.csv and storm_days.meta.json in `dirpath`, as fetch_storms writes them: TOY_STORM on each of
    `days`, every other day of first_day..last_day without a storm. Returns the StormDays written."""
    from apps.history.storms import META_FILE, STORM_FILE, StormDays, write_storm_days
    dirpath = Path(dirpath)
    sd = StormDays({d: TOY_STORM for d in days}, first_day, last_day)
    write_storm_days(sd, 'toy', datetime(2026, 11, 13, tzinfo=timezone.utc), (10.25, 123.85),
                     dirpath / STORM_FILE.name, dirpath / META_FILE.name)
    return sd


def write_toy_files(dirpath, barangay_ids, in_use='two_part', shares=None):
    """Write the forecast's data files into `dirpath` from toy_inputs and return (terrain, rain, pos).

    Toy barangay i becomes barangay_ids[i - 1], each in its own grid cell. The files are rain_daily.csv,
    barangay_terrain.csv, hazard_model_exclusions.csv (no record left out), storm_days.csv and its meta file (a
    storm on every toy event day, coverage from the rain file's first day to TOY_STORM_THROUGH) and
    hazard_model_report.json, toy_report_v2(in_use=in_use, shares=shares) for both hazards. `pos` serves both
    hazards and lies in the study period.
    """
    dirpath = Path(dirpath)
    terrain, rain, pos = _placed(barangay_ids)
    cells = {b: (10.25 + 0.1 * (i + 1), 123.85) for i, b in enumerate(barangay_ids)}
    write_rain_csv(dirpath / 'rain_daily.csv', rain, cells)
    write_terrain(dirpath / 'barangay_terrain.csv', terrain, {b: f'Toy {b}' for b in terrain})
    with open(dirpath / 'hazard_model_exclusions.csv', 'w', newline='', encoding='utf-8') as f:
        f.write('source_ref,reason\r\n')
    first = min(min(series) for series in rain.values())
    write_toy_storms(dirpath, first, TOY_STORM_THROUGH, sorted({d for _, d in pos}))
    toy_report_v2(dirpath / 'hazard_model_report.json', in_use=in_use, shares=shares)
    return terrain, rain, pos


def toy_report_v1(path) -> dict:
    """Write the report test_hazard_models wrote before version 2 to `path` and return it: no `version`, and a
    `winner` per hazard instead of `in_use` and saved fits. What an old report left on disk looks like."""
    report = {'generated': '2026-11-12T00:00:00+08:00',
              'study': {'start': STUDY_START.isoformat(), 'end': STUDY_END.isoformat()},
              'hazards': {h: {'hazard': h, 'winner': 'logistic_regression', 'calibrated_all_folds': False}
                          for h in ('Flood', 'Landslide')}}
    with open(path, 'w', encoding='utf-8', newline='\n') as f:
        f.write(json.dumps(report, indent=2) + '\n')
    return report


# ---- A version 2 report (test_hazard_models' shape since hazard models v2) ----

TOY_V2_GENERATED = '2026-11-13T00:00:00+08:00'
TOY_V2_FILES = {'rain_sha1': 'rain_daily.csv', 'terrain_sha1': 'barangay_terrain.csv',
                'exclusions_sha1': 'hazard_model_exclusions.csv', 'exposure_sha1': None, 'storms_sha1': None,
                'catalogue_sha1': None, 'catalogue_exclusions_sha1': None}
_TOY_WHEN = {   # hand-set "when" fits: (coefficients, intercepts by era, lambda, beta)
    'Flood': ([1.4, 1.8], {'geoalert': -9.5}, 0.004, None),
    'Landslide': ([0.9, 0.7], {'geoalert': -11.0, 'catalogue': -9.0}, 0.8, 2.5),
}
_TOY_TOP = {'log1p_r3': 5.5, 'storm72': 1.0, 'log1p_r14': 6.2}


def _toy_two_part(hazard, shares) -> dict:
    from apps.history.two_part import FEATURES, TwoPartFit, WhenFit
    coef, intercepts, lam, beta = _TOY_WHEN[hazard]
    when = WhenFit(FEATURES[hazard], np.array(coef), dict(intercepts))
    return TwoPartFit(hazard, when, dict(shares), lam, beta, {f: _TOY_TOP[f] for f in FEATURES[hazard]}).to_json()


def _toy_logistic(hazard) -> dict:
    """A hand-set fit in export_logistic's shape, which hazard_scoring.score_logistic accepts."""
    rain_medians = [3.0, 3.0, 9.0, 21.0, 42.0]
    terrain = TERRAIN_FEATURES[hazard]
    middle = [70.0 if f == 'relief' else 0.5 for f in terrain]       # toy_inputs' relief runs 20-120 m
    return {'kind': 'logistic_regression', 'features': [*RAIN_FEATURES, *terrain],
            'medians': rain_medians + middle, 'log_columns': list(range(len(RAIN_FEATURES))),
            'mean': [math.log1p(m) for m in rain_medians] + middle,
            'scale': [1.0] * len(RAIN_FEATURES) + [40.0 if f == 'relief' else 0.2 for f in terrain],
            'coef': [0.2, 0.1, 0.9, 0.3, 0.2] + [0.3] * len(terrain), 'intercept': -7.0,
            'training_max': {**{f: 150.0 for f in RAIN_FEATURES}, **{f: 2 * m for f, m in zip(terrain, middle)}}}


def _toy_levels(events) -> list[dict]:
    """hazard_verdict.level_tables' shape: High (0.25) then Moderate (0.15) barangay-month tables."""
    out = []
    for cutoff, hits, false_alarms in ((0.25, events // 2, 6), (0.15, events // 2 + 1, 12)):
        misses, quiet = events - hits, false_alarms + 150
        out.append({'cutoff': cutoff, 'hits': hits, 'misses': misses, 'false_alarms': false_alarms,
                    'correct_negatives': 150, 'pod': hits / events, 'far': false_alarms / (hits + false_alarms),
                    'peirce': hits / events - false_alarms / quiet, 'sedi': 0.6,
                    'false_alarms_per_event': false_alarms / events})
    return out


def _toy_model(log_loss, auc, rows, days, events, event_days, years) -> dict:
    return {'scores': {'log_loss': log_loss, 'brier': 0.004, 'brier_skill_climatology': 0.05,
                       'brier_skill_rate': 0.02, 'pr_auc': 0.08, 'no_skill_pr_auc': events / rows, 'roc_auc': auc,
                       'calibration_slope': 0.9, 'rows': rows, 'events': events},
            'log_loss_interval': [log_loss * 0.8, log_loss * 1.2],
            'when': {'auc': auc, 'log_loss': 0.02, 'days': days, 'event_days': event_days},
            'where': {'auc': 0.7, 'auc_days': event_days, 'lift': 2.1, 'hit_rows': events},
            'levels': _toy_levels(events),
            'per_year': [{'year': y, 'observed': n, 'expected': n * 0.8, 'low': 0.0, 'high': n + 3.7}
                         for y, n in years]}


def _toy_tests(hazard, pos, rows, days) -> dict:
    """hazard_verdict.evaluate's `tests` with every field the accuracy card reads: both contenders and two
    baselines, an event-table row per toy event day, and landslide's outside test."""
    event_days = sorted({d for _, d in pos})
    years = [(y, sum(1 for _, d in pos if d.year == y)) for y in range(STUDY_START.year, STUDY_END.year + 1)]
    names = ('two_part', 'logistic_regression', 'climatology', 'rate')
    models = {n: _toy_model(0.010 + 0.001 * i, 0.9 - 0.05 * i, rows, days, len(pos), len(event_days), years)
              for i, n in enumerate(names)}
    events = [{'day': d.isoformat(), 'subtypes': ['TOY'], 'storm': 'TOY' if hazard == 'Flood' else None,
               'rain_1day': 80.0, 'rain_3day': 95.0, 'band': '50-100 mm',
               'models': {n: {'hit_chance': 0.2 - 0.05 * i, 'hit_chance_before': 0.01, 'city_chance': 0.5 - 0.1 * i,
                              'high_barangays': sum(1 for _, e in pos if e == d)} for i, n in enumerate(names[:2])}}
              for d in event_days]
    pairs = [names[:2]] + [(a, b) for a in names[:2] for b in names[2:]]
    across = {'auc': 0.8, 'slopes': {'log1p_r3': {'coef': 0.9, 'low': 0.2, 'high': 1.6},
                                     'log1p_r14': {'coef': 0.7, 'low': -0.1, 'high': 1.5}}}
    return {
        'loso': {'rows': rows, 'days': days, 'event_days': len(event_days), 'hit_rows': len(pos),
                 'blocks': {'event': len(event_days), 'month': 60}, 'reps': 20, 'models': models,
                 'differences': {f'{a} - {b}': {'difference': -0.001, 'low': -0.003, 'high': 0.001} for a, b in pairs},
                 'breakeven': [{'cutoff': 0.25, 'false_alarms_per_event': 3.0},
                               {'cutoff': 0.15, 'false_alarms_per_event': 0.85 / 0.15}]},
        'yearly': {n: [{'train_years': list(range(STUDY_START.year, test)), 'test_year': test,
                        'train_event_days': sum(1 for d in event_days if d.year < test),
                        'test_event_days': sum(1 for d in event_days if d.year == test),
                        'scores': models[n]['scores'], 'reason': None} for test in (2023, 2024, 2025)]
                   for n in names[:2]},
        'events': events,
        'outside': (None if hazard == 'Flood' else
                    {'current': {'auc': 0.7, 'observed': 6, 'expected': 4.2},
                     'catalogue_to_geoalert': across, 'geoalert_to_catalogue': across}),
    }


def _toy_verdict(in_use, lost_on) -> dict:
    from apps.history.hazard_verdict import LEAKAGE_PASSED
    interval = 'The interval of the log-score difference does not lie wholly below zero (-0.003 to 0.001).'
    if in_use == 'two_part':
        return {'adopted': True, 'rule': 'b', 'leakage_checked': True, 'reasons': [
            interval, 'On each of the 20 event days with a hit barangay it gave the hit barangays a log score no '
                      'worse than the current model, a better one on 14, and no more false alarms per real event '
                      'at High (2.0 against 3.0).', LEAKAGE_PASSED]}
    return {'adopted': False, 'rule': None, 'leakage_checked': True, 'reasons': [
        interval, f'It gave a lower chance to the hit barangays on {lost_on.isoformat()}.', LEAKAGE_PASSED]}


def toy_report_v2(path, hazards=('Flood', 'Landslide'), in_use='two_part', shares=None) -> dict:
    """Write a minimal valid version 2 report to `path` and return it (spec 3.1; test_hazard_models' shape).

    Meant to sit beside write_toy_files' files: the barangay ids are those of the barangay_terrain.csv next to
    `path` (1, 2 and 3 without one), and each hazard's data_signature is that of the toy events write_toy_files
    placed on them, so database records made with toy_source_ref are not stale. `files` holds the sha1s of the
    rain, terrain and exclusions files beside `path` (None for a missing one and for the inputs it does not
    write). in_use 'two_part' gives a verdict adopted under rule (b); 'logistic_regression' one not adopted,
    naming the last toy event day. `shares` ({barangay_id: a_b}) replaces both two-part fits' shares (default
    0.6, 0.3, 0.2, ... down the ids); leave a barangay out to give it no share. The fits are hand-set numbers
    that TwoPartFit.from_json and hazard_scoring.score_logistic accept; limits and credits come from
    hazard_models.
    """
    from apps.history.hazard_models import REPORT_MODELS, REPORT_VERSION, credits_for, report_limits
    if in_use not in REPORT_MODELS:
        raise ValueError(f'in_use must be one of {REPORT_MODELS}, not {in_use!r}')
    path = Path(path)
    terrain_file = path.parent / 'barangay_terrain.csv'
    ids = sorted(read_terrain(terrain_file)) if terrain_file.exists() else [1, 2, 3]
    _, _, pos = _placed(ids)
    if shares is None:
        shares = {b: round(0.6 / (i + 1), 4) for i, b in enumerate(ids)}
    days = (STUDY_END - STUDY_START).days + 1
    event_days = sorted({d for _, d in pos})
    entries = {}
    for hazard in hazards:
        entry = {
            'hazard': hazard, 'in_use': in_use, 'verdict': _toy_verdict(in_use, event_days[-1]),
            'fits': {'two_part': _toy_two_part(hazard, shares), 'logistic_regression': _toy_logistic(hazard)},
            'rows': len(ids) * days, 'positives': len(pos), 'positive_days': len(event_days),
            'event_days': len(event_days), 'tests': _toy_tests(hazard, pos, len(ids) * days, days),
            'limits': [], 'credits': credits_for(hazard),
            'data_signature': records_signature(toy_event_records(hazard, pos), STUDY_START, STUDY_END),
            'excluded': [], 'logged': None,
        }
        entry['limits'] = report_limits(hazard, entry, barangays=len(ids))
        entries[hazard] = entry
    report = {
        'version': REPORT_VERSION, 'generated': TOY_V2_GENERATED,
        'study': {'start': STUDY_START.isoformat(), 'end': STUDY_END.isoformat()},
        'files': {key: (_sha1(path.parent / name) if name and (path.parent / name).exists() else None)
                  for key, name in TOY_V2_FILES.items()},
        'hazards': entries,
    }
    with open(path, 'w', encoding='utf-8', newline='\n') as f:
        f.write(json.dumps(report, indent=2, allow_nan=False) + '\n')
    return report
