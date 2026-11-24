"""
The fire model's whole training pipeline as one function, train(), so the
hand-run command (manage.py train_fire_model) and the scheduled job run the
same code. It reads no database: the fires, the feature table and the barangay
names are passed in.

Adapted from the City of Pittsburgh Bureau of Fire / Carnegie Mellon Metro21
fire risk model (github.com/CityofPittsburgh/fire_risk_analysis, MIT License,
© 2017 mmadaio). The steps (spec sections 4-6):

  1. Development: each candidate scored leaving one fold out (a calendar year in
     the fixed window, a block of 12 months counted back from the test window in
     the moving one); the rule picks the model; Platt recalibration and the level
     cut-offs come from its leave-one-fold-out predictions.
  2. The test, once: that model refitted on the development months, scored with
     95% intervals (resampling barangays), its levels, the comparison baselines,
     the barangay check against BFP's own barangay field, the 151 / 519-style
     sensitivity split, and leave one barangay out.
  3. Deployment: the same steps on every month to the last full one, then each
     area's chance for January to December with an 80% interval.

Fires that name no purok are left out and listed, never guessed.
"""
import hashlib
import json
import math
import os
from dataclasses import asdict
from datetime import datetime, timedelta, timezone

import numpy as np

from apps.history import fire_evaluation as fe
from apps.history import fire_features as ff
from apps.history import fire_training as ft

FIRST_MONTH = 2023 * 12  # Fire records start in January 2023
TEST_START = 2026 * 12   # the fixed test: January 2026 to the last full month, used once
WINDOW_MONTHS = 12       # the moving test: the newest 12 full months
CAVEAT = ('Purok-level scores from past fires are probably optimistic: {named} of the {total} areas were drawn '
          'because a fire address named them. Honest purok scores come from fires after the map was frozen '
          '(the prediction log).')

FIRE_SWITCHED = 'Scored {new:.4f} vs {live:.4f} on {start} to {end}'
FIRE_SWITCHED_FIRST = 'Scored {new:.4f} on {start} to {end}; no model was in use'
FIRE_WORSE = 'The new fit scored worse ({new:.4f} vs {live:.4f})'
FIRE_BASELINE = 'No better than the same chance everywhere ({new:.4f} vs {base:.4f})'
FIRE_STALE_FEATURES = 'The purok map changed; rebuild the fire features by hand'

MANILA = timezone(timedelta(hours=8))


def month_name(m):
    """A month index as YYYY-MM."""
    return f'{m // 12:04d}-{m % 12 + 1:02d}'


def pretty_month(m):
    """A month index as 'Feb 2026'."""
    return datetime(m // 12, m % 12 + 1, 1).strftime('%b %Y')


def sig(x):
    """Six significant figures: enough for a chance, and a smaller file."""
    return float(f'{float(x):.6g}')


def _json_default(o):
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, np.floating):
        return float(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    raise TypeError(f'{type(o).__name__} is not JSON serializable')


def write_pair(folder, texts):
    """Write every file to a .tmp beside it, then swap them in, so the site never
    reads a half-written file and a failed write leaves the old pair in place."""
    temps = {name: folder / (name + '.tmp') for name in texts}
    try:
        for name, text in texts.items():
            temps[name].write_text(text, encoding='utf-8')
        for name, tmp in temps.items():
            os.replace(tmp, folder / name)
    finally:
        for tmp in temps.values():
            tmp.unlink(missing_ok=True)


def barangay_months(panel, p):
    """{(barangay id, month index): chance of a fire in the barangay}, from its areas: 1 − e^(−Σ −ln(1 − p))."""
    rate = {}
    for b, m, pi in zip(panel.barangay.tolist(), panel.month.tolist(), p):
        rate[(b, m)] = rate.get((b, m), 0.0) - math.log(1 - pi)
    return {k: 1 - math.exp(-v) for k, v in rate.items()}


def _window_log_loss(dev, test, family, settings, choice=None):
    """Mean row log loss on `test` of the family and settings refitted on `dev`.
    Without a choice, its leave-one-fold-out predictions are made here (the live model's refit)."""
    if choice is None:
        choice = ft.Choice(family, settings, ft.oof(dev, family, settings), [], {})
    fitted = ft.fit_final(dev, choice)
    return float(ft.row_log_loss(test.y, fitted.predict(test.X)).mean())


def train(fires, table, names, today, window='fixed', live=None, csv_bytes=b'', boot_reps=fe.BOOT_REPS,
          interval_reps=fe.INTERVAL_REPS, log=print):
    """
    (model document, report) from the recorded fires and the feature table.
    names maps barangay id to name; csv_bytes is the features file, for the version stamp.
    window 'fixed' tests on January 2026 to the last full month; 'moving' on the newest
    WINDOW_MONTHS full months, and adds report['switch'] against `live` ({family, settings} or None).
    Raises ValueError where the data cannot support the run.
    """
    end = today.year * 12 + today.month - 1  # the current month isn't over: train on the months before it
    if window == 'moving':
        test_start = end - WINDOW_MONTHS
        if test_start - FIRST_MONTH < WINDOW_MONTHS + 1:
            raise ValueError('The moving window needs at least 13 months before the test window.')
        fold_end = test_start
    else:
        test_start, fold_end = TEST_START, None
        if end <= TEST_START:
            raise ValueError('The test needs at least one full month of 2026.')

    area_ids = {r['purok_id'] for r in table.rows}
    label_map, unplaced = ft.labels(fires, area_ids, FIRST_MONTH, end)
    in_window = [f for f in fires if FIRST_MONTH <= ft.month_index(f.when) < end]
    used = [f for f in in_window if any(p in area_ids for p in f.purok_ids)]
    unplaced_list = [{'date': f.when.date().isoformat(), 'barangay': names.get(f.barangay_id, '')}
                     for f in unplaced]
    log(f'{len(table.rows)} areas; {len(used)} fires placed in a purok from {month_name(FIRST_MONTH)} to '
        f'{month_name(end - 1)}; {len(unplaced)} name no purok and are left out')

    def scores(y, p, groups, orange=None):
        return fe.scores(y, p, groups, orange=orange, reps=boot_reps)

    dev = ft.build_panel(table, label_map, range(FIRST_MONTH, test_start), fold_end=fold_end)
    test = ft.build_panel(table, label_map, range(test_start, end))
    whole = ft.build_panel(table, label_map, range(FIRST_MONTH, end))
    if window == 'fixed':
        dev_label, test_label = 'Development (2023-2025, leaving one year out)', 'The test (2026, once)'
    else:
        dev_label = f'Development ({month_name(FIRST_MONTH)} to {month_name(test_start - 1)}, leaving 12 months out)'
        test_label = f'The test ({month_name(test_start)} to {month_name(end - 1)}, once)'
    log(f'{dev_label}: scoring every candidate...')
    dev_choice = ft.choose(dev)
    dev_fit = ft.fit_final(dev, dev_choice)
    dev_cut = fe.cutoffs(ft.apply_platt(dev_choice.oof, *dev_fit.platt), dev.y)
    log(f'{test_label}...')
    test_section, p_test = _test_section(table, dev, test, dev_choice, dev_fit, dev_cut, test_start, end, scores)
    check = _barangay_check(table, dev, test, p_test, in_window, scores)
    sensitivity = _sensitivity(table, test, p_test, dev_cut, scores)
    lobo = _leave_one_barangay_out(whole, dev_choice, dev_fit, dev_cut, scores)
    log('Deployment (every month): choosing and fitting again, then the 80% intervals...')
    choice = ft.choose(whole)
    fitted = ft.fit_final(whole, choice)
    cut = fe.cutoffs(ft.apply_platt(choice.oof, *fitted.platt), whole.y)
    ids, X12 = fe.calendar_rows(whole)
    p12 = fitted.predict(X12)
    spans = fe.intervals(whole, choice, reps=interval_reps)
    switch = None
    if window == 'moving':
        switch = _switch(dev, test, dev_choice, live, test_section, test_start, end)

    version = _version(csv_bytes, used, choice, end_month=month_name(end - 1) if window == 'moving' else None)
    confidence = {r['purok_id']: r['confidence'] for r in table.rows}
    barangay_of = {r['purok_id']: r['barangay_id'] for r in table.rows}
    areas = {}
    for i, a in enumerate(ids.tolist()):
        months = []
        for m in range(12):
            p = sig(p12[i * 12 + m])
            low, high = spans[a][m]
            months.append({'p': p, 'level': fe.level(p, cut), 'low': sig(low), 'high': sig(high)})
        areas[str(a)] = {'barangay_id': barangay_of[a],
                         'limited_data': any(fe.limited_data(confidence[a], lo, hi) for lo, hi in spans[a]),
                         'months': months}
    trained = {'start': month_name(FIRST_MONTH), 'end': month_name(end - 1), 'fires': len(used),
               'unplaced': unplaced_list}
    model = {'version': version, 'credit': ff.CREDIT,
             'model': {'family': choice.family, 'settings': choice.settings},
             'calibration': {'a': fitted.platt[0], 'b': fitted.platt[1]}, 'cutoffs': asdict(cut),
             'trained': trained, 'outlines_version': table.outlines_version, 'areas': areas,
             'built_at': datetime.now(MANILA).isoformat(timespec='seconds')}
    named = sum(1 for r in table.rows if r['from_fire_log'])
    report = {'version': version, 'credit': ff.CREDIT,
              'model': {'family': choice.family, 'settings': choice.settings},
              'candidates': choice.candidates, 'verdict': choice.verdict, 'cutoffs': asdict(cut),
              'trained': trained, 'test': test_section, 'barangay_check': check, 'sensitivity': sensitivity,
              'leave_one_barangay_out': lobo, 'caveat': CAVEAT.format(named=named, total=len(table.rows)),
              'unplaced': unplaced_list,
              'features': {'built_at': table.built_at, 'sources': table.sources, 'dropped': list(table.dropped)}}
    if switch is not None:
        report['switch'] = switch
    return model, report


def _switch(dev, test, dev_choice, live, test_section, test_start, end):
    """The rule for the moving window: the new fit goes live only if it beats the same chance everywhere
    and scores at least as well as the model in use on the same window."""
    new = _window_log_loss(dev, test, dev_choice.family, dev_choice.settings, choice=dev_choice)
    old = None if live is None else _window_log_loss(dev, test, live['family'], live['settings'])
    base = test_section['comparison']['comparison_same_everywhere']['log_loss']['value']
    window = {'start': pretty_month(test_start), 'end': pretty_month(end - 1)}
    passed = new < base and (old is None or new <= old)
    if new >= base:
        reason = FIRE_BASELINE.format(new=new, base=base)
    elif old is not None and new > old:
        reason = FIRE_WORSE.format(new=new, live=old)
    elif old is None:
        reason = FIRE_SWITCHED_FIRST.format(new=new, **window)
    else:
        reason = FIRE_SWITCHED.format(new=new, live=old, **window)
    return {'passed': bool(passed), 'new_log_loss': new, 'live_log_loss': old, 'same_everywhere_log_loss': base,
            'window': window, 'reason': reason}


def _test_section(table, dev, test, dev_choice, dev_fit, dev_cut, test_start, end, scores):
    """(the report's test section, the test chances) for the development model on the test months."""
    p = dev_fit.predict(test.X)
    levels = fe.level_table(test.y, p, dev_cut)
    buildings = {r['purok_id']: r['buildings_in_area'] for r in table.rows}
    comparison = {name: scores(test.y, cp, test.barangay)
                  for name, cp in fe.comparison_baselines(dev, test, buildings).items()}
    return {'window': {'start': month_name(test_start), 'end': month_name(end - 1)},
            'rows': int(len(test.y)), 'fires': int(test.y.sum()),
            'chosen': {'family': dev_choice.family, 'label': dev_choice.settings['label'],
                       'verdict': dev_choice.verdict},
            'cutoffs': asdict(dev_cut), 'scores': scores(test.y, p, test.barangay, dev_cut.orange),
            'levels': levels, 'green_fires': levels[2]['fires'], 'reliability': fe.reliability(test.y, p),
            'comparison': comparison}, p


def _barangay_check(table, dev, test, p_test, in_window, scores):
    """The test's chances summed to barangay-months, scored against BFP's own barangay field (spec 6.4)."""
    burned = {(f.barangay_id, ft.month_index(f.when)) for f in in_window if f.barangay_id is not None}
    chance = barangay_months(test, p_test)
    keys = sorted(chance)
    y = np.array([1 if k in burned else 0 for k in keys])
    p = np.array([chance[k] for k in keys])
    groups = np.array([k[0] for k in keys])

    # The comparison baselines, learned at barangay level from the development months
    brgys = sorted({b for b, _ in keys})
    dev_months = sorted(set(dev.month.tolist()))
    dev_y = {b: [1 if (b, m) in burned else 0 for m in dev_months] for b in brgys}
    rate = float(np.mean([v for ys in dev_y.values() for v in ys]))
    houses = {b: 0.0 for b in brgys}
    for r in table.rows:
        if r['barangay_id'] in houses:
            houses[r['barangay_id']] += r['buildings_in_area']
    mean_houses = float(np.mean([houses[b] + 1 for b in brgys]))
    comparison = {
        'comparison_same_everywhere': ft.clip(np.full(len(keys), rate)),
        'comparison_buildings': ft.clip([rate * (houses[b] + 1) / mean_houses for b, _ in keys]),
        'comparison_historical_frequency': ft.clip([(sum(dev_y[b]) + rate) / (len(dev_months) + 1)
                                                    for b, _ in keys]),
    }
    return {'rows': len(keys), 'fires': int(y.sum()), 'scores': scores(y, p, groups),
            'comparison': {k: scores(y, v, groups) for k, v in comparison.items()}}


def _sensitivity(table, test, p, cut, scores):
    """The test scored apart for areas drawn because a fire address named them and for the rest (spec 6.5)."""
    named = {r['purok_id'] for r in table.rows if r['from_fire_log']}
    mask = np.isin(test.purok, list(named))

    def part(m):
        return scores(test.y[m], p[m], test.barangay[m], cut.orange) if m.any() else None
    return {'fire_log_named': part(mask), 'others': part(~mask), 'named_areas': len(named),
            'other_areas': len(table.rows) - len(named)}


def _leave_one_barangay_out(whole, choice, fitted, cut, scores):
    """Each barangay predicted by the development model refitted without it, over every month."""
    p = np.zeros(len(whole.y))
    for b in np.unique(whole.barangay):
        held = whole.barangay == b
        p[held] = ft.fit_predict(choice.family, choice.settings, whole.X[~held], whole.y[~held], whole.X[held])
    p = ft.clip(ft.apply_platt(ft.clip(p), *fitted.platt))
    return scores(whole.y, p, whole.barangay, cut.orange)


def _version(csv_bytes, used, choice, end_month=None):
    """
    <family>@<sha1 of the features, the fires and their puroks, and the settings>, 12 characters.
    The moving window adds its training end month (YYYY-MM): a monthly refit with no new fires is
    still a new model, so the insert-only log takes its rows. The fixed window adds nothing.
    """
    h = hashlib.sha1(csv_bytes)
    for f in sorted(used, key=lambda f: (f.record_id, f.when.isoformat())):
        h.update(f'{f.record_id}|{f.when.isoformat()}|{f.purok_ids}\n'.encode())
    h.update(json.dumps({'family': choice.family, 'settings': choice.settings}, sort_keys=True).encode())
    if end_month is not None:
        h.update(f'end|{end_month}\n'.encode())
    return f'{choice.family}@{h.hexdigest()[:12]}'
