"""
One training run of the landslide susceptibility model (spec 4-6), as
`manage.py train_landslide_model` runs it, in this order:

1. Rule 1, the world test: the world events join the training set only when
   they help the neural network on a held-out Philippine typhoon
   (report['training_set']).
2. Each candidate and UP NOAH's map alone (B0) scored out of fold, one typhoon
   held out at a time; rule 2 keeps the neural network unless another
   candidate is clearly better (report['candidates'], report['choice']).
3. The chosen candidate refitted on the whole training set. Talisay's scoring
   points are checked against the training range on their terrain clues and
   clipped to it on land cover and road distance (report['in_range']); purok
   scores are the 90th percentile of the points in range.
4. The Red / Orange cut-offs from the chosen candidate's out-of-fold points
   (report['cutoffs']); the classes; gates 1 and 3.
5. Only then are the Talisay test data loaded (`load_tests`; gate 4), and
   gate 2 judged. When any gate fails, classes from UP NOAH's map ship instead.
6. The uncertain mark from bootstrap refits of the classes that ship (the NOAH
   fallback has none), then the two files.

Returns (model JSON, report JSON): fitted numbers, classes and counts only,
never a coordinate. AUC and its bootstrap are unweighted; the own rows' weight
of 10 enters only the fits and the cut-off walk.

`mode='own'` (the January job) adds GeoAlert's own slides and their "no"
points (`own_rows`, the 'talisay' fold, weight 10) to the training set rule 1
chose on the outside table. The Talisay fold is scored out of fold beside the
typhoons, gate 1 is judged on all those folds, and gate 2 reads the held-back
season's puroks. It never falls back to NOAH: a fit that fails a gate is
simply not made live by the job.
"""
import hashlib
import json
import math
from dataclasses import asdict
from pathlib import Path

import numpy as np

from apps.hazards.susceptibility import COPERNICUS_NOTICE
from apps.history import flood_rules as rules
from apps.history import landslide_training as lt
from apps.history.landslide_features import FEATURE_COLUMNS, LANDCOVER_CLASSES, TERRAIN_COLUMNS
from apps.history.landslide_training_table import TABLE_COLUMNS, TEXT_COLUMNS

MODES = ('outside', 'own')
# The code a run's classes depend on: the cut-off walk and auc_gain (flood_rules), in_range (flood_training) and
# the "no" sampling (landslide_training_table, landslide_own) among it
CODE_FILES = ('landslide_training.py', 'landslide_run.py', 'landslide_features.py', 'flood_rules.py',
              'flood_training.py', 'landslide_training_table.py', 'landslide_own.py', 'mlp_fit.py')
OWN_FOLD = 'talisay'
OWN_WEIGHT = 10
SEED = 0
NOAH_ONLY = 'noah_only'
FLAGGED = ('Red', 'Orange')
LEVELS = ('Red', 'Orange', 'Green')
LANDCOVER_COLUMNS = tuple(LANDCOVER_CLASSES.values())
NAMES = {'neural_network': 'Neural network', 'logistic_regression': 'Logistic regression', 'xgboost': 'XGBoost'}

CREDITS = [
    'Landslide inventories: NASA Cooperative Open Online Landslide Repository, Vershel et al. (2025), Open inventories '
    'of rainfall-triggered landslides, Figshare doi 10.6084/m9.figshare.26972467 (CC BY 4.0)',
    'Abancó, C.; Jones, J.N. (2023). Areas affected by landslides following Typhoon Mangkhut in Itogon, Philippines, '
    'September 2018. NERC EDS Environmental Information Data Centre. doi 10.5285/32765a61-8510-4dfc-b7c7-58bad12f8497 '
    '(Open Government Licence)',
    'UP NOAH landslide hazard maps (ODbL), via the bettergovph mirror',
    'Esri / Impact Observatory 10 m annual land cover (CC BY 4.0)',
    COPERNICUS_NOTICE,
    '© OpenStreetMap contributors (ODbL)',
    'Microsoft building footprints (ODbL)',
]
LIMITS = [
    'The model learned where landslides started after typhoons elsewhere in the Philippines (northern Luzon, Benguet, '
    'Maguindanao and Leyte) and is applied to Talisay, whose ground and rain differ.',
    'Terrain comes from a 30 m elevation model, so small road cuts and steep banks are smoothed out.',
    "Geology differs: Cebu's limestone is not the Cordillera's volcanic and sedimentary rock, and the model has no "
    'rock or soil map.',
    'The "no landslide" ground was sampled at three points per mapped slide, so a score ranks how prone ground is to '
    'sliding; it is not a chance of a landslide.',
    'Few located Talisay landslides exist to test it on, all on the Manipis road side.',
    "Agaton's 23 slides make its held-out typhoon test noisy.",
    'This is not a forecast: it is the same in every month and does not say a landslide is coming.',
]
LIMITS_OWN = [
    "GeoAlert's own located landslides were added to the typhoon slides, each with its sampled \"no landslide\" "
    'ground, and counted ten times in the fit and the cut-offs.',
    *(line for line in LIMITS if not line.startswith('Few located Talisay')),
]
LANDCOVER_DROPPED = ('Land cover could not be read for every area, so the model learned from terrain and roads '
                     'alone.')
WORLD_RULE = ('For each held-out Philippine typhoon, the neural network trained on the other Philippine typhoons '
              'alone and with every world event; the world events join only when the AUC gain has its 95% interval '
              'wholly above zero.')
CHOICE_RULE = ('The neural network is kept unless logistic regression or XGBoost beats it on pooled out-of-fold AUC '
               'with a 95% interval wholly above zero; if both do, the higher pooled AUC wins.')
GATE_LABELS = {
    'better_than_noah': "Better than UP NOAH's landslide map on its own",
    'talisay_test': 'Talisay puroks with a located landslide in Red or Orange',
    'not_everything_flagged': 'Red and Orange hold at most half of the in-range scoring points of assessed puroks',
    'tests_seen_last': 'Test data seen last',
}
GATE_LABELS_OWN = {**GATE_LABELS, 'talisay_test': "The held-back wet season's spots in Red or Orange"}
TESTS_LAST = ('The training set, the choice and the cut-offs were in the report before any Talisay test record or '
              'catalogue point was loaded.')
SETTINGS = {
    'candidates': list(lt.CANDIDATES), 'folds': list(lt.PH_FOLDS), 'red': rules.RED_SHARE,
    'orange': rules.ORANGE_SHARE, 'flagged_max': rules.FLAGGED_MAX, 'uncertain': rules.UNCERTAIN_LIMIT,
    'assessed_share': lt.ASSESSED_SHARE, 'percentile': lt.P90, 'own_weight': OWN_WEIGHT, 'seed': SEED,
}


def code_digest() -> str:
    """The training code's fingerprint, part of the version: changed code can give other classes."""
    h = hashlib.sha1()
    for name in CODE_FILES:
        h.update(Path(__file__).with_name(name).read_bytes().replace(b'\r\n', b'\n'))
    return h.hexdigest()


def columns_for(table_meta: dict, features_meta: dict) -> tuple:
    """
    The model inputs: every FEATURE_COLUMNS clue, without land cover unless
    both the training tiles and Talisay read it.
    """
    if table_meta.get('landcover_ok') is True and features_meta.get('landcover_ok') is True:
        return FEATURE_COLUMNS
    return tuple(c for c in FEATURE_COLUMNS if c not in LANDCOVER_COLUMNS)


def _round(x, digits: int = 4):
    if x is None:
        return None
    x = float(x)
    return None if not math.isfinite(x) else round(x, digits)


def _number(x):
    """A weight as JSON shows it: 10, not 10.0."""
    x = float(x)
    return int(x) if x.is_integer() else x


def _rows(table: dict, mask) -> dict:
    return {k: np.asarray(v)[mask] for k, v in table.items()}


def _clean(rows: dict, fill_text: str | None = None) -> dict:
    """TABLE_COLUMNS only (text as str, label as int, the rest float); a missing text column takes `fill_text`."""
    n = len(rows['label'])
    out = {}
    for c in TABLE_COLUMNS:
        if c in TEXT_COLUMNS:
            out[c] = np.asarray(rows[c] if c in rows or fill_text is None else np.full(n, fill_text), dtype=str)
        elif c == 'label':
            out[c] = np.asarray(rows[c], int)
        else:
            out[c] = np.asarray(rows[c], float)
    return out


def _gain_args(a, b, y, folds, mask):
    """auc_gain's arguments for the gain of score `a` over score `b` on the rows in `mask`."""
    p, n = mask & (y == 1), mask & (y == 0)
    return folds[p], folds[n], a[p], a[n], b[p], b[n]


def _auc_interval(s, y, folds, mask, reps: int):
    """
    (AUC, 2.5%, 97.5%) of one score on the rows in `mask`, unweighted, with
    slides and "no" points resampled within each fold. A constant score's AUC
    is exactly 0.5 (ties count half), so this is the gain over a constant plus
    0.5: the same bootstrap the gates use.
    """
    if not (mask & (y == 1)).any() or not (mask & (y == 0)).any():
        return None, None, None
    gain, lo, hi = rules.auc_gain(*_gain_args(s, np.zeros(len(s)), y, folds, mask), reps=reps, seed=SEED)
    return gain + 0.5, lo + 0.5, hi + 0.5


def _candidate_row(name, s, y, folds, scored_folds, reps):
    s = np.asarray(s, float)
    scored = np.isin(folds, scored_folds) & np.isfinite(s)
    auc, lo, hi = _auc_interval(s, y, folds, scored, reps)
    per_fold = []
    for f in scored_folds:
        rows = scored & (folds == f)
        if not rows.any():
            continue
        f_auc, f_lo, f_hi = _auc_interval(s, y, folds, rows, reps)
        per_fold.append({'fold': f, 'slides': int((rows & (y == 1)).sum()), 'no_points': int((rows & (y == 0)).sum()),
                         'auc': _round(f_auc), 'lo': _round(f_lo), 'hi': _round(f_hi)})
    return {'name': name, 'auc': _round(auc), 'lo': _round(lo), 'hi': _round(hi), 'folds': per_fold}


def _events(table: dict, w: np.ndarray, joined: bool, table_meta: dict) -> list:
    """Each event in the table (first-seen order): fold, region, slides, "no" points, weight, whether it trained."""
    meta = {e.get('key'): e for e in table_meta.get('events', [])}
    events, folds, regions, y = (np.asarray(table[c]) for c in ('event', 'fold', 'region', 'label'))
    out = []
    for key in dict.fromkeys(events.tolist()):
        rows = events == key
        fold = str(folds[rows][0])
        row = {'event': key, 'fold': fold, 'region': str(regions[rows][0]), 'slides': int(y[rows].sum()),
               'no_points': int((y[rows] == 0).sum()), 'weight': _number(w[rows][0]),
               'used': fold != lt.WORLD or bool(joined)}
        for extra in ('landcover_year', 'road_kept'):
            if extra in meta.get(key, {}):
                row[extra] = meta[key][extra]
        out.append(row)
    return out


def _world_verdict(world: dict, has_world: bool, table_meta: dict | None = None) -> str:
    if not has_world:
        if (table_meta or {}).get('world_left_out'):  # ruling R57: built with --philippines-only
            return ('The world events were left out of this build (it was built from the Philippine typhoons only), '
                    'so the world test did not run.')
        return 'No world events are in the training table.'
    if world['joined']:
        return (f"The world events joined: they raised the AUC on held-out Philippine typhoons by {world['gain']:.3f} "
                f"(95% interval {world['lo']:.3f} to {world['hi']:.3f}).")
    return (f"The world events did not join: their AUC gain on held-out Philippine typhoons was {world['gain']:.3f} "
            f"(95% interval {world['lo']:.3f} to {world['hi']:.3f}), not wholly above zero.")


def _choice_verdict(chosen: str, per: dict) -> str:
    if chosen == 'neural_network':
        return ('Neural network kept: neither logistic regression nor XGBoost beat it clearly (the lower end of each '
                'AUC gain over it was not above zero).')
    c = per[chosen]
    return (f"{NAMES[chosen]} chosen: its AUC gain over the neural network was {c['gain_over_nn']:.3f} (95% interval "
            f"{c['lo']:.3f} to {c['hi']:.3f}), wholly above zero.")


def _in_range_block(points: dict, valid: np.ndarray, train: dict, columns: tuple, final: dict) -> dict:
    """
    How Talisay's scoring points sit against the chosen training set: the share
    in range on the terrain clues, the points below or above each clue's
    1st-99th percentile, and the points whose land cover or road distance was
    clipped. Counts only.
    """
    n = int(len(valid))
    outside = {}
    for c in (c for c in TERRAIN_COLUMNS if c in columns):
        lo, hi = np.percentile(np.asarray(train[c], float), [1, 99])  # as flood_training.in_range reads the range
        v = np.asarray(points[c], float)
        outside[c] = {'below': int((v < lo).sum()), 'above': int((v > hi).sum())}
    ranges = lt.clip_ranges(train, columns)
    clipped = {}
    for c, (lo, hi) in ranges.items():
        v = np.asarray(points[c], float)
        clipped[c] = int(((v < lo) | (v > hi)).sum())
    unlike = sum(1 for v in final.values() if v['total'] > 0 and not v['assessed'])
    return {'points': n, 'in_range': int(valid.sum()), 'share': _round(valid.mean(), 4) if n else None,
            'outside_by_column': outside, 'clipped': clipped,
            'clip_ranges': {c: [_round(lo, 6), _round(hi, 6)] for c, (lo, hi) in ranges.items()},
            'unlike_puroks': int(unlike)}


def _log_in_range(block: dict, log):
    share = f" ({block['share']:.1%})" if block['share'] is not None else ''
    log(f"In range: {block['in_range']} of {block['points']} Talisay scoring points{share}; "
        f"{block['unlike_puroks']} puroks not assessed as unlike the training ground")
    log('  Outside the training range: ' + ('; '.join(f"{c} {v['below']} below, {v['above']} above"
                                                       for c, v in block['outside_by_column'].items()) or 'none'))
    log('  Clipped to the training range: ' + (', '.join(f'{c} {k}' for c, k in block['clipped'].items()) or 'none'))


def _point_counts(membership, levels: dict, valid) -> tuple[int, int]:
    """
    (scoring points in range in an assessed purok, of them in a Red or Orange
    purok); a point in two areas counts once. Gate 3 reads these (ruling R27:
    the unique in-range scoring points of assessed puroks), as flood counts its
    valid buildings only. The NOAH fallback passes every point as in range.
    """
    idx, pids = (np.asarray(a) for a in membership)
    keep = np.asarray(valid, bool)[idx]
    assessed = keep & np.isin(pids, np.asarray(list(levels), int))
    flagged = keep & np.isin(pids, np.asarray([p for p, lv in levels.items() if lv in FLAGGED], int))
    return int(np.unique(idx[assessed]).size), int(np.unique(idx[flagged]).size)


def _flagged_share(membership, levels: dict, valid) -> float:
    assessed, flagged = _point_counts(membership, levels, valid)
    return flagged / assessed if assessed else 0.0


def _barangay_check(records: list, membership, barangay_of: dict, model_levels: dict, published_levels: dict) -> dict:
    """
    The share of each recorded barangay's scoring points in a Red or Orange
    purok, against the rest of the city's points in a purok (spec 6.6), on the
    model's classes and on the map that ships. Shown on the card only.
    """
    idx, pids = (np.asarray(a) for a in membership)
    brgy = np.array([barangay_of.get(int(p), -1) for p in pids], int)

    def counts(pairs):
        pts = np.unique(idx[pairs])
        out = {'points': int(pts.size)}
        for key, levels in (('share_red_orange', model_levels), ('published_share_red_orange', published_levels)):
            hot = pairs & np.isin(pids, np.asarray([p for p, lv in levels.items() if lv in FLAGGED], int))
            k = int(np.unique(idx[hot]).size)
            if key == 'share_red_orange':
                out['red_orange'] = k
            out[key] = _round(k / pts.size) if pts.size else None
        return out

    rows, recorded = [], set()
    for r in records:
        b = int(r['barangay_id'])
        recorded.add(b)
        rows.append({'barangay_id': b, 'barangay': r.get('barangay'), 'records': int(r.get('records', 0)),
                     **counts(brgy == b)})
    in_recorded = np.isin(idx, idx[np.isin(brgy, np.asarray(sorted(recorded), int))])
    return {'barangays': rows, 'rest': counts(~in_recorded & (brgy >= 0))}


def _classes(areas: dict, membership, valid) -> dict:
    table = {lv: {'puroks': 0, 'points': 0} for lv in LEVELS}
    reasons = {}
    for a in areas.values():
        if a['level']:
            table[a['level']]['puroks'] += 1
            table[a['level']]['points'] += a['points']
        else:
            reasons[a['not_assessed_reason']] = reasons.get(a['not_assessed_reason'], 0) + 1
    levels = {pid: a['level'] for pid, a in areas.items() if a['level']}
    return {'levels': table, 'not_assessed': reasons, 'assessed_puroks': len(levels),
            'flagged_point_share': _round(_flagged_share(membership, levels, valid))}


def _own_digest(rows: dict, weight: np.ndarray) -> str:
    """
    The own rows' fingerprint (label, weight, clues rounded to 6 decimals), in
    an order that does not depend on the caller's.
    """
    def cell(v):
        v = float(v)
        return None if not math.isfinite(v) else round(v, 6)

    lines = sorted(json.dumps([int(rows['label'][i]), cell(weight[i])]
                              + [cell(rows[c][i]) for c in FEATURE_COLUMNS + ('noah_class',)])
                   for i in range(len(rows['label'])))
    return hashlib.sha1(json.dumps(lines).encode('utf-8')).hexdigest()


def run(table: dict, table_meta: dict, features, load_tests, log=print, report=None, fingerprint: str = '',
        reps: int = 1000, stability_reps: int = 200, built_at: str | None = None, mode: str = 'outside',
        own_rows: dict | None = None, deadline: lt.Deadline | None = None) -> tuple[dict, dict]:
    """
    (model JSON, report JSON); `report`, when given, is filled in place as the
    run goes. `table`, `table_meta` = landslide_training_table.read_table();
    `features` = landslide_features.read_features(..., cache_dir=...).
    `load_tests()` returns {'test_puroks': [purok id], 'barangay_records':
    [{barangay_id, barangay, records}], 'catalogue_purok_ids': [purok id or
    None]} (the last two may be left out); in own mode `test_puroks` holds the
    held-back season's spots' puroks (one per spot) and it may add 'season'.
    `own_rows` (own mode) is a table like `table` with the clues and NOAH class
    of GeoAlert's slides and their "no" points; its fold is always 'talisay'
    and its weight OWN_WEIGHT unless it carries a 'weight' column.
    `fingerprint` should cover the input files; the model's
    inputs['files'] is left for the caller to fill with their checksums.
    `deadline` (the January job's own time limit; None offline) is checked
    before every fit of the world test, the out-of-fold scoring and the
    stability refits, and raises landslide_training.PastDeadline once passed.
    """
    from django.utils import timezone

    if mode not in MODES:
        raise ValueError(f'Unknown landslide training mode: {mode}')
    own = mode == 'own'
    if own and own_rows is None:
        raise ValueError("The own mode needs GeoAlert's own rows (landslide_own.own_rows).")
    report = {} if report is None else report
    columns = columns_for(table_meta, features.meta)
    landcover_ok = len(columns) == len(FEATURE_COLUMNS)

    outside = _clean(table)
    if own:
        mine = _clean(own_rows, fill_text=OWN_FOLD)
        mine['fold'] = np.full(len(mine['label']), OWN_FOLD)
        n_own = len(mine['label'])
        own_w = np.asarray(own_rows.get('weight', np.full(n_own, OWN_WEIGHT)), float)
        everything = {c: np.concatenate([outside[c], mine[c]]) for c in TABLE_COLUMNS}
        w_all = np.r_[np.ones(len(outside['label'])), own_w]
    else:
        everything, w_all = outside, np.ones(len(outside['label']))
    scored_folds = lt.PH_FOLDS + ((OWN_FOLD,) if own else ())

    # 1. Rule 1 on the outside table: do the world events join?
    has_world = bool((outside['fold'] == lt.WORLD).any())
    if has_world:
        log('Rule 1: the world test (the neural network with and without the world events)...')
        world = lt.world_test(outside, columns, seed=SEED, reps=reps, deadline=deadline)
    else:
        world = {'joined': False, 'gain': None, 'lo': None, 'hi': None}
    keep = (everything['fold'] != lt.WORLD) | bool(world['joined'])
    train, w = _rows(everything, keep), w_all[keep]
    y, folds = train['label'], train['fold']
    training_set = 'ph+world' if world['joined'] else 'ph'
    report['training_set'] = {
        'chosen': training_set, 'events': _events(everything, w_all, world['joined'], table_meta),
        'world': {'joined': bool(world['joined']), 'gain': _round(world['gain']), 'lo': _round(world['lo']),
                  'hi': _round(world['hi']), 'rule': WORLD_RULE, 'verdict': _world_verdict(world, has_world, table_meta)},
        'rows': int(len(y)), 'slides': int(y.sum()), 'columns': list(columns), 'landcover_ok': landcover_ok,
    }
    log(f'Training set: {training_set} ({int(y.sum())} slides, {int((y == 0).sum())} no points); '
        f'inputs: {", ".join(columns)}')

    # 2. Every candidate and NOAH's map alone out of fold; rule 2
    oof = {}
    for name in lt.CANDIDATES:
        log(f'  scoring {name} out of fold...')
        oof[name] = lt.out_of_fold(name, train, columns, scored_folds, w, seed=SEED, deadline=deadline)
    scored = np.isin(folds, scored_folds)
    noah = np.asarray(train['noah_class'], float)
    if np.isnan(noah[scored]).any():
        raise RuntimeError('Some Philippine or own rows have no UP NOAH class; rebuild the training table.')
    b0 = np.where(scored, noah / 3, np.nan)
    report['candidates'] = [_candidate_row(name, s, y, folds, scored_folds, reps)
                            for name, s in [*oof.items(), (NOAH_ONLY, b0)]]
    chosen, per = lt.choose(oof, y, folds, reps=reps, seed=SEED)
    report['choice'] = {'chosen': chosen, 'rule': CHOICE_RULE, 'verdict': _choice_verdict(chosen, per),
                        'comparisons': {n: {k: _round(v) for k, v in c.items()} for n, c in per.items()}}
    log(f'  chosen: {chosen}')

    # 3. The final fit; Talisay's points in range, clipped, scored; purok scores
    medians = lt.medians_for(chosen, train, columns)
    X, cols = lt.design_matrix(train, columns, medians)
    fitted = lt.fit(chosen, X, y, w, cols, seed=SEED)
    points = features.points
    clipped, valid = lt.prepare_talisay(points, train, columns)
    point_X, _ = lt.design_matrix(clipped, columns, medians)
    point_scores = lt.score(chosen, fitted, point_X)
    totals = {int(a['purok_id']): int(a['points']) for a in features.areas}
    final = lt.purok_scores(point_scores, features.membership, valid, totals)
    report['in_range'] = _in_range_block(points, valid, train, columns, final)
    _log_in_range(report['in_range'], log)

    # 4. Cut-offs from the chosen candidate's out-of-fold points; classes; gates 1 and 3
    cut = lt.point_cutoffs(oof[chosen], y, w)
    report['cutoffs'] = asdict(cut)
    levels = {pid: rules.classify(v['score'], cut) for pid, v in final.items() if v['assessed']}
    gain, g_lo, g_hi = rules.auc_gain(*_gain_args(np.asarray(oof[chosen], float), b0, y, folds,
                                                  scored & np.isfinite(oof[chosen])), reps=reps, seed=SEED)
    gate1 = bool(math.isfinite(g_lo) and g_lo > 0)
    flagged_share = _flagged_share(features.membership, levels, valid)
    gate3 = flagged_share <= rules.FLAGGED_MAX

    # 5. Only now the test data, then gate 2
    tests = load_tests()
    test_puroks = [None if p is None else int(p) for p in tests.get('test_puroks', [])]
    test_levels = [levels.get(p) for p in test_puroks]
    gate2 = rules.test_gate_passed(test_levels)
    hits, needed = sum(1 for lv in test_levels if lv in FLAGGED), rules.test_hits_needed(len(test_levels))
    gates = {'better_than_noah': gate1, 'talisay_test': gate2, 'not_everything_flagged': gate3,
             'tests_seen_last': True}
    where = 'the held-out folds, Talisay\'s own among them' if own else 'the held-out Philippine typhoons'
    details = {
        'better_than_noah': (f"AUC gain over UP NOAH's map alone {gain:.3f} (95% interval {g_lo:.3f} to {g_hi:.3f}) "
                             f'on {where}'),
        'talisay_test': f'{hits} of {len(test_levels)} in Red or Orange ({needed} needed)',
        'not_everything_flagged': (f'{flagged_share:.0%} of the in-range scoring points of assessed puroks in Red '
                                   'or Orange'),
        'tests_seen_last': TESTS_LAST,
    }
    reasons = []
    if not gate1:
        reasons.append(f"It did not clearly beat UP NOAH's landslide map on {where}: the lower end of its AUC gain "
                       f'was {g_lo:.3f}, not above zero.' if math.isfinite(g_lo)
                       else "Its AUC gain over UP NOAH's landslide map could not be measured.")
    if not test_levels:
        reasons.append('No held-back wet season spot was available to test it on.' if own
                       else 'No Talisay purok with a located landslide was available to test it on.')
    elif not gate2:
        reasons.append(f'Only {hits} of the {len(test_levels)} held-back wet season spots fell in a Red or Orange '
                       f'purok ({needed} needed).' if own
                       else f'Only {hits} of the {len(test_levels)} Talisay puroks with a located landslide were Red '
                            f'or Orange ({needed} needed).')
    if not gate3:
        reasons.append(f"Red and Orange would cover {flagged_share:.0%} of the in-range scoring points of Talisay's "
                       'assessed puroks, more than half.')
    adopted = all(gates.values())
    report['acceptance'] = {'adopted': adopted, 'gates': gates, 'labels': GATE_LABELS_OWN if own else GATE_LABELS,
                            'details': details, 'reasons': reasons}

    info = {int(a['purok_id']): a for a in features.areas}

    def area_row(pid, level, score, reason, uncertain):
        a = info[pid]
        return {'barangay_id': int(a['barangay_id']), 'level': level, 'score': _round(score, 6),
                'uncertain': bool(uncertain), 'not_assessed_reason': reason,
                'estimated_outline': a['confidence'] == 'low', 'points': int(a['points'])}

    # 6. What ships: the model's classes (own mode: always, the job decides), else NOAH's; the uncertain mark
    everywhere = np.ones(len(valid), bool)  # the fallback reads every scoring point
    if own or adopted:
        source, prefix, ship_cut = ('geoalert' if own else 'model'), chosen, cut
        log(f'  stability: {stability_reps} refits...')
        refits = lt.stability(chosen, train, columns, w, point_X, features.membership, valid, totals, cut,
                              reps=stability_reps, seed=SEED, deadline=deadline)
        uncertain = rules.uncertain_puroks(levels, refits)
        areas = {pid: area_row(pid, levels.get(pid), v['score'] if v['assessed'] else None,
                               None if v['assessed'] else lt.not_assessed_reason(v['total'], v['valid']),
                               pid in uncertain)
                 for pid, v in final.items()}
        report['stability'] = {'refits': int(stability_reps), 'uncertain_puroks': len(uncertain)}
    else:
        source, prefix = 'noah', 'noah_fallback'
        ship_cut = lt.point_cutoffs(b0, y, w)
        noah_scores = lt.purok_scores(np.asarray(points['noah_class'], float) / 3, features.membership, everywhere,
                                      totals)
        fb_levels = {pid: rules.classify(v['score'], ship_cut) for pid, v in noah_scores.items() if v['assessed']}
        areas = {pid: area_row(pid, fb_levels.get(pid), v['score'] if v['assessed'] else None,
                               None if v['assessed'] else lt.not_assessed_reason(v['total'], v['valid']), False)
                 for pid, v in noah_scores.items()}
        report['stability'] = None
        report['fallback'] = {
            'cutoffs': asdict(ship_cut),
            'flagged_share': _round(_flagged_share(features.membership, fb_levels, everywhere)),
            'note': ("UP NOAH's landslide map ships because the model failed a gate. Its cut-offs come from the same "
                     'walk on its classes at the held-out typhoon points, and every purok with a building or road '
                     'is classed.'),
        }
    published = {pid: a['level'] for pid, a in areas.items() if a['level']}

    def named(pid):
        a = info.get(pid, {})
        return {'purok_id': pid, 'name': a.get('name'), 'barangay': a.get('barangay'), 'level': levels.get(pid),
                'published_level': areas.get(pid, {}).get('level')}

    report['talisay_test'] = {
        'puroks': [named(p) for p in test_puroks],
        'barangay_check': _barangay_check(tests.get('barangay_records', []), features.membership,
                                          {pid: int(a['barangay_id']) for pid, a in info.items()}, levels, published),
        'catalogue': [{'level': levels.get(p) if p is not None else None,
                       'published_level': areas.get(int(p), {}).get('level') if p is not None else None}
                      for p in tests.get('catalogue_purok_ids', [])],
    }
    if own:
        report['own_spots'] = int(mine['label'].sum())
        report['season'] = tests.get('season')
        report['temporal_test'] = {
            'season': tests.get('season'),
            'held_back': [{'purok_id': p, 'level': lv} for p, lv in zip(test_puroks, test_levels)],
        }

    road = np.asarray(train['dist_road_m'], float)
    in_training = set(np.unique(train['event']).tolist())
    report['road_check'] = {
        **(table_meta.get('road_check') or {}),
        'rows': int(len(road)), 'rows_with_road': int(np.isfinite(road).sum()),
        'events_without_road': sorted(e['key'] for e in table_meta.get('events', [])
                                      if e.get('road_kept') is False and e.get('key') in in_training),
    }

    run_settings = {**SETTINGS, 'mode': mode, 'reps': reps, 'stability_reps': stability_reps, 'code': code_digest()}
    if own:
        run_settings['own_rows'] = _own_digest(mine, own_w)  # the caller's fingerprint need not cover them
    sha = hashlib.sha1((fingerprint + json.dumps(run_settings, sort_keys=True)).encode('utf-8')).hexdigest()[:12]
    version = f'{prefix}@{sha}'
    built_at = built_at or timezone.localtime().isoformat(timespec='seconds')
    limits = list(LIMITS_OWN if own else LIMITS) + ([] if landcover_ok else [LANDCOVER_DROPPED])
    report.update({
        'version': version, 'source': source, 'built_at': built_at, 'columns': list(columns),
        'classes': _classes(areas, features.membership, everywhere if source == 'noah' else valid),
        'limits': limits, 'credits': list(CREDITS),
    })
    model_json = {
        'version': version, 'source': source, 'chosen': chosen, 'training_set': training_set, 'built_at': built_at,
        'outlines_version': features.meta.get('outlines_version'), 'cutoffs': asdict(ship_cut),
        'clip_ranges': {c: list(r) for c, r in report['in_range']['clip_ranges'].items()},
        'inputs': {'columns': list(columns), 'landcover_ok': landcover_ok, 'files': {}},
        'areas': areas,
    }
    if own:
        log(f'Verdict: {"passed all four checks" if adopted else "failed a check"} ({version})'
            + ('' if adopted else ': ' + ' '.join(reasons)))
    else:
        log(f'Verdict: {"model adopted" if adopted else "NOAH fallback"} ({version})'
            + ('' if adopted else ': ' + ' '.join(reasons)))
    return model_json, report
