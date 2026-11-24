"""
One training run of the flood susceptibility model (spec 4-6), as
`manage.py train_flood_model` runs it:

1. Inputs at the survey's positive spots (presences) and at every building in
   the evidence domain (background); a building is valid when it is in the
   domain and its inputs lie in the background's range.
2. Each candidate scored out of fold (spatial blocks by barangay); the
   NOAH-only map scored beside them; the simplest candidate kept unless a more
   complex one is clearly better (flood_rules.choose).
3. Red / Orange cut-offs from the out-of-fold purok scores. Only then are the
   test data loaded (gate 4: `load_tests` is called after `report['choice']`
   and `report['cutoffs']` are written).
4. The chosen candidate refitted on everything; purok classes, the uncertain
   mark (bootstrap refits) and the reasons for areas not assessed.
5. The acceptance gates; when any fails, the NOAH-based classes ship instead.

Returns (model JSON, report JSON). Neither holds a survey coordinate, nor the
domain's outline (its 300 m arcs are centred on survey spots): only fitted
numbers, classes and counts.
"""
import hashlib
import json
from dataclasses import asdict
from pathlib import Path

import numpy as np
from sklearn.metrics import roc_auc_score

from apps.history import flood_rules as rules
from apps.history.flood_purok import BASIS_MODEL, BASIS_NOAH
from apps.history import flood_training as tr

CREDITS = [
    'Flood survey points: E. C. Paringit and R. S. Otadoy (eds.) (2017), LiDAR Surveys and Flood Mapping of Mananga '
    'River, UP Training Center for Applied Geodesy and Photogrammetry / University of San Carlos (Phil-LiDAR 1), used '
    'for research and education with acknowledgement',
    'UP NOAH flood hazard maps (ODbL), via the bettergovph mirror',
    'Tino flood proxy map: Earth Observatory of Singapore – Remote Sensing Lab (EOS-RS); contains modified Copernicus '
    'Sentinel data (2025)',
    'produced using Copernicus WorldDEM-30 © DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018 provided '
    'under COPERNICUS by the European Union and ESA; all rights reserved',
    'ESA WorldCover 2021 (CC BY 4.0)',
    '© OpenStreetMap contributors',
    'Microsoft building footprints (ODbL)',
]
LIMITS = [
    'The survey points are places where residents remembered floods (typhoons of 1990-2014). The other buildings are '
    'not known to be dry, so the levels show how flood-prone an area is compared with the rest, not a chance of '
    'flooding.',
    'Every survey point lies along the lower Mananga River, so areas away from it are not assessed.',
    'Purok outlines are estimates; areas with a low-confidence outline are marked.',
    'The Mananga River works planned for 2026 may change where floods reach; the model learned from the river '
    'before them.',
    "UP NOAH's flood maps are labelled beta.",
    'This is not a forecast: it is the same in every month and does not say a flood is coming.',
]
SETTINGS = {
    'candidates': list(tr.CANDIDATES), 'folds': tr.FOLDS, 'buffer_m': tr.BUFFER_M, 'red': rules.RED_SHARE,
    'orange': rules.ORANGE_SHARE, 'flagged_max': rules.FLAGGED_MAX, 'test_hits': rules.TEST_HITS_NEEDED,
    'uncertain': rules.UNCERTAIN_LIMIT, 'boyce': {'window': 0.1, 'points': 101},
}
FLAGGED = ('Red', 'Orange')


def columns_for(meta: dict) -> tuple:
    """The model inputs in order: noah5_class only when its map passed the consistency check."""
    used = meta.get('noah_layers_used', ['noah25_class'])
    return tuple(['noah25_class'] + (['noah5_class'] if 'noah5_class' in used else [])
                 + ['rel_height_river_m', 'dist_river_m', 'depression_m', 'built_share'])


def _table(spots, columns):
    return {c: np.array([s['inputs'][c] for s in spots], float) for c in columns}


def _auc(p, b):
    if not len(p) or not len(b):
        return None
    return float(roc_auc_score(np.r_[np.ones(len(p)), np.zeros(len(b))], np.r_[p, b]))


def _round(x, digits=4):
    return None if x is None or (isinstance(x, float) and np.isnan(x)) else round(float(x), digits)


CODE_FILES = ('flood_rules.py', 'flood_training.py', 'flood_run.py')
GATE1_WHY = ("Judged on AUC: UP NOAH's map has only four levels, which a continuous Boyce index cannot compare fairly "
             'with a continuous score.')
DOMAIN_RULE = 'Convex hull of the flooded survey spots, buffered 300 m, clipped to the city'


def code_digest() -> str:
    """The training code's fingerprint, part of the version: changed code can give other classes."""
    h = hashlib.sha1()
    for name in CODE_FILES:
        h.update(Path(__file__).with_name(name).read_bytes().replace(b'\r\n', b'\n'))
    return h.hexdigest()


def _per_purok(membership, mask):
    out = {}
    for b, p in zip(*membership):
        if mask[b]:
            out[int(p)] = out.get(int(p), 0) + 1
    return out


def _flagged_buildings(membership, levels, n):
    flagged = np.zeros(n, bool)
    for b, p in zip(*membership):
        if levels.get(int(p)) in FLAGGED:
            flagged[b] = True
    return flagged


def _classes_table(areas, spots_in):
    table = {lv: {'puroks': 0, 'buildings': 0, 'field_spots': 0} for lv in ('Red', 'Orange', 'Green')}
    reasons = {}
    for pid, a in areas.items():
        if a['level']:
            row = table[a['level']]
            row['puroks'] += 1
            row['buildings'] += a['buildings']
            row['field_spots'] += spots_in.get(pid, 0)
        else:
            reasons[a['not_assessed_reason']] = reasons.get(a['not_assessed_reason'], 0) + 1
    return {'levels': table, 'not_assessed': reasons}


def run(features, train_spots: list, city, load_tests, log=print, report=None, fingerprint: str = '',
        reps: int = 1000, stability_reps: int = 200, built_at: str | None = None):
    """(model JSON, report JSON). `report`, when given, is filled in place as the run goes."""
    from django.utils import timezone

    report = {} if report is None else report
    b = features.buildings
    n = len(b['lon'])
    columns = columns_for(features.meta)
    positives = [s for s in train_spots if s['positive']]
    dry = [s for s in train_spots if not s['positive']]
    totals = {a['purok_id']: int(a['buildings']) for a in features.areas}
    spots_in = {}
    for s in positives:
        if s.get('purok_id') is not None:
            spots_in[s['purok_id']] = spots_in.get(s['purok_id'], 0) + 1

    # 1. presences, background, validity
    X_p = tr.design_matrix(_table(positives, columns), columns)
    X_all = tr.design_matrix(b, columns)
    in_dom, _hull = tr.domain(b['lon'], b['lat'], train_spots, city)
    X_b = X_all[in_dom]
    valid = in_dom & tr.in_range(X_all, X_b)
    folds_p = np.array([tr.FOLDS.get(s.get('barangay'), -1) for s in positives])
    folds_b = np.array([tr.FOLDS.get(str(name), -1) for name in b['barangay']])[in_dom]
    log(f'{len(positives)} survey spots, {int(in_dom.sum())} buildings in the surveyed floodplain '
        f'({int(valid.sum())} in range); inputs: {", ".join(columns)}')

    # 2. candidates out of fold, the NOAH-only map beside them, the choice
    oof = {}
    for name in tr.CANDIDATES:
        log(f'  scoring {name} out of fold...')
        oof[name] = tr.out_of_fold(name, X_p, X_b, folds_p, folds_b, columns)
    noah_idx = columns.index('noah25_class')
    oof_noah = (X_p[:, noah_idx] / 3, X_b[:, noah_idx] / 3)
    candidates = []
    for name, (sp, sb) in [*oof.items(), ('noah_only', oof_noah)]:
        value, low, high = rules.boyce_interval(folds_p, folds_b, sp, sb, reps=reps)
        candidates.append({'name': name, 'boyce': _round(value), 'boyce_low': _round(low), 'boyce_high': _round(high),
                           'auc': _round(_auc(sp, sb))})
    chosen, comparisons = rules.choose(oof, folds_p, folds_b, reps=reps)
    report['candidates'] = candidates
    report['choice'] = {'chosen': chosen, 'comparisons': [{k: (_round(v) if isinstance(v, float) else v)
                                                           for k, v in c.items()} for c in comparisons]}
    log(f'  chosen: {chosen}')

    # 3. cut-offs from out-of-fold purok scores, then (and only then) the test data
    oof_buildings = np.full(n, np.nan)
    oof_buildings[in_dom] = oof[chosen][1]
    oof_puroks = tr.purok_scores(oof_buildings, features.membership, valid, totals)
    cut = rules.cutoff_walk({p: v['score'] for p, v in oof_puroks.items() if v['assessed']}, spots_in)
    report['cutoffs'] = asdict(cut)
    tests = load_tests()

    # 4. the final fit, classes, reasons, the uncertain mark
    y = np.r_[np.ones(len(X_p)), np.zeros(len(X_b))]
    model = tr.fit(chosen, np.r_[X_p, X_b], y, tr.weights(len(X_p), len(X_b)), columns)
    scores = np.zeros(n)
    scores[valid] = tr.score(chosen, model, X_all[valid])
    final = tr.purok_scores(scores, features.membership, valid, totals)
    in_domain_count = _per_purok(features.membership, in_dom)
    levels = {p: rules.classify(v['score'], cut) for p, v in final.items() if v['assessed']}
    log(f'  stability: {stability_reps} refits...')
    refits = tr.stability(chosen, X_p, X_b, X_all, features.membership, valid, totals, cut, columns,
                          reps=stability_reps)
    uncertain = rules.uncertain_puroks(levels, refits)

    # 5. tests and gates
    pts = tests['geoalert_points']
    if pts:
        pts_in = tr.domain(np.array([p['lon'] for p in pts]), np.array([p['lat'] for p in pts]), train_spots, city)[0]
    else:
        pts_in = np.zeros(0, bool)
    mananga = [p for p, inside in zip(pts, pts_in) if inside]
    elsewhere = [p for p, inside in zip(pts, pts_in) if not inside]
    test_levels = [levels.get(p.get('purok_id')) for p in mananga]
    flagged_b = _flagged_buildings(features.membership, levels, n)
    flagged_share = float(flagged_b[valid].mean()) if valid.any() else 0.0
    # Gate 1 on the AUC gain: the NOAH-only score has four values, which a continuous Boyce index can't rank
    gain, g_low, g_high = rules.auc_gain(folds_p, folds_b, *oof[chosen], *oof_noah, reps=reps)
    b_gain, b_low, b_high = rules.boyce_gain(folds_p, folds_b, *oof[chosen], *oof_noah, reps=reps)
    adopted, reasons = rules.acceptance(g_low, test_levels, flagged_share)
    hits = sum(1 for lv in test_levels if lv in FLAGGED)
    gates = [
        {'gate': "Better than UP NOAH's map on its own", 'passed': bool(g_low > 0),
         'detail': f'AUC gain {gain:.3f} (95% interval {g_low:.3f} to {g_high:.3f}); Boyce gain {b_gain:.3f} '
                   f'({b_low:.3f} to {b_high:.3f}), shown only. {GATE1_WHY}'},
        {'gate': 'GeoAlert Mananga flood points in Red or Orange', 'passed': rules.test_gate_passed(test_levels),
         'detail': f'{hits} of {len(test_levels)}'},
        {'gate': 'Red and Orange cover at most half the buildings', 'passed': flagged_share <= rules.FLAGGED_MAX,
         'detail': f'{flagged_share:.0%} of the floodplain buildings'},
        {'gate': 'Test data seen last', 'passed': True,
         'detail': 'The choice and the cut-offs were fixed before any test point was loaded.'},
    ]
    flags = np.asarray(tests.get('eosrs_flagged', np.zeros(n, bool)), bool)
    eos_p, eos_b = scores[valid & flags], scores[valid & ~flags]
    dry_scores = (tr.score(chosen, model, tr.design_matrix(_table(dry, columns), columns)).tolist() if dry else [])
    pres_scores = tr.score(chosen, model, X_p)
    records = tests.get('barangay_records', {})
    by_barangay = {}
    for i in np.flatnonzero(valid):
        name = str(b['barangay'][i])
        row = by_barangay.setdefault(name, [0, 0])
        row[0] += 1
        row[1] += int(flagged_b[i])
    report['temporal_test'] = {
        'mananga_points': [{'day': p['day'], 'barangay': p['barangay'], 'purok_id': p.get('purok_id'),
                            'level': levels.get(p.get('purok_id'))} for p in mananga],
        'elsewhere': [{'day': p['day'], 'barangay': p['barangay'],
                       'note': 'Not assessed: upland road runoff is a different kind of flood'
                       if p['barangay'] == 'Manipis' else 'Not assessed: outside the surveyed floodplain'}
                      for p in elsewhere],
        'eosrs': {'boyce': _round(rules.boyce_index(eos_p, eos_b)), 'auc': _round(_auc(eos_p, eos_b)),
                  'flagged_buildings': int(len(eos_p)),
                  'note': 'The satellite map is preliminary and less reliable over built-up and vegetated ground.'},
        'dry_spots': [{'score': _round(s), 'share_of_flood_spots_scoring_lower': _round(float((pres_scores < s).mean()))}
                      for s in dry_scores],
    }
    report['barangay_check'] = [{'barangay': name, 'buildings': row[0],
                                 'share_red_orange': _round(row[1] / row[0]) if row[0] else None,
                                 'tino_record': name in records.get('tino', []),
                                 'any_flood_record': name in records.get('any', [])}
                                for name, row in sorted(by_barangay.items())]
    report['acceptance'] = {'adopted': bool(adopted), 'gates': gates, 'reasons': reasons}

    # 6. what ships
    def area_row(pid, level, score, reason, is_uncertain):
        info = next(a for a in features.areas if a['purok_id'] == pid)
        return {'barangay_id': info['barangay_id'], 'level': level, 'score': _round(score, 6),
                'uncertain': bool(is_uncertain), 'not_assessed_reason': reason,
                'estimated_outline': info['confidence'] == 'low', 'buildings': info['buildings']}

    areas = {}
    if adopted:
        source, prefix, ship_cut = 'model', chosen, cut
        valid_count = _per_purok(features.membership, valid)
        for pid, v in final.items():
            reason = None if v['assessed'] else tr.not_assessed_reason(v['total'], in_domain_count.get(pid, 0),
                                                                         valid_count.get(pid, 0))
            if not v['assessed'] and reason is None:
                reason = tr.UNLIKE
            areas[pid] = area_row(pid, levels.get(pid), v['score'] if v['assessed'] else None, reason,
                                  pid in uncertain)
    else:
        source, prefix = 'noah', 'noah_fallback'
        fallback = tr.noah_fallback(b['noah25_class'], b['noah25_within_300m'], features.membership, totals, spots_in)
        ship_cut = fallback['cutoffs']
        for pid, a in fallback['areas'].items():
            areas[pid] = area_row(pid, a['level'], a['score'], a['not_assessed_reason'], False)
        report['fallback'] = {'cutoffs': asdict(ship_cut),
                              'note': "UP NOAH's map missed about a third of the survey's flood spots."}

    # The level each GeoAlert Mananga point's area has on the map that ships (the fallback's, when it ships)
    for p in report['temporal_test']['mananga_points']:
        p['published_level'] = areas.get(p['purok_id'], {}).get('level')

    run_settings = {**SETTINGS, 'reps': reps, 'stability_reps': stability_reps, 'code': code_digest()}
    sha = hashlib.sha1((fingerprint + json.dumps(run_settings, sort_keys=True)).encode('utf-8')).hexdigest()[:12]
    version = f'{prefix}@{sha}'
    built_at = built_at or timezone.localtime().isoformat(timespec='seconds')
    report.update({
        'version': version, 'source': source, 'built_at': built_at, 'basis': BASIS_MODEL if adopted else BASIS_NOAH,
        'columns': list(columns), 'survey_spots': len(positives), 'dry_spots': len(dry),
        'domain_buildings': int(in_dom.sum()), 'valid_buildings': int(valid.sum()),
        'classes': _classes_table(areas, spots_in), 'limits': LIMITS, 'credits': CREDITS,
    })
    if not adopted:
        # The user's ruling (2026-11-24): the fallback keeps its breadth, and the card says how broad it is
        counts = report['classes']['levels']
        total = sum(v['buildings'] for v in counts.values())
        share = sum(counts[k]['buildings'] for k in FLAGGED if k in counts) / total if total else 0.0
        report['fallback']['flagged_share'] = _round(share)
        report['fallback']['note'] += (f' It flags about {share:.0%} of the assessed buildings as Red or Orange, '
                                       'more than the half the machine-learning model was allowed.')
    model_json = {
        'version': version, 'source': source, 'chosen': chosen, 'built_at': built_at,
        'outlines_version': features.meta.get('outlines_version'), 'cutoffs': asdict(ship_cut),
        'domain': {'buffer_m': tr.BUFFER_M, 'rule': DOMAIN_RULE},
        'inputs': {'columns': list(columns), 'noah_layers_used': features.meta.get('noah_layers_used', [])},
        'areas': areas,
    }
    log(f'Verdict: {"model adopted" if adopted else "NOAH fallback"} ({version})'
        + ('' if adopted else ': ' + ' '.join(reasons)))
    return model_json, report
