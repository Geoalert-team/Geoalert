"""
manage.py train_fire_model [--today YYYY-MM-DD]

Trains the fire risk model on the recorded fires and the purok features, tests
it once, and writes the two files the website reads:

  apps/history/data/fire_purok_model.json   every area's chance and level for each month of the year
  apps/history/data/fire_purok_report.json  the candidates, the rule's verdict and every score

Adapted from the City of Pittsburgh Bureau of Fire / Carnegie Mellon Metro21
fire risk model (github.com/CityofPittsburgh/fire_risk_analysis, MIT License,
© 2017 mmadaio). The steps (spec sections 4-6):

  1. Development, on 2023-2025: each candidate scored leaving one year out;
     the rule picks the model; Platt recalibration and the level cut-offs come
     from its leave-one-year-out predictions.
  2. The test, once, on 2026-01 to the last full month: that model refitted
     on 2023-2025, scored with 95% intervals (resampling barangays), its
     levels, the comparison baselines, the barangay check against BFP's own
     barangay field, the 151 / 519-style sensitivity split, and leave one
     barangay out.
  3. Deployment: the same steps on every month to the last full one, then
     each area's chance for January to December with an 80% interval.

Fires that name no purok are left out and listed, never guessed. Run on a
developer machine after build_fire_features; it only reads the database.
"""
import hashlib
import json
import math
import os
from dataclasses import asdict
from datetime import date
from pathlib import Path

import numpy as np
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.barangays.models import Barangay, Purok
from apps.history import fire_evaluation as fe
from apps.history import fire_features as ff
from apps.history import fire_training as ft

FIRST_MONTH = 2023 * 12  # Fire records start in January 2023
TEST_START = 2026 * 12   # the test: January 2026 to the last full month, used once
CAVEAT = ('Purok-level scores from past fires are probably optimistic: {named} of the {total} areas were drawn '
          'because a fire address named them. Honest purok scores come from fires after the map was frozen '
          '(the prediction log).')


def month_name(m):
    """A month index as YYYY-MM."""
    return f'{m // 12:04d}-{m % 12 + 1:02d}'


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


class Command(BaseCommand):
    help = 'Train the fire risk model on recorded fires and write fire_purok_model.json and fire_purok_report.json.'

    def add_arguments(self, parser):
        parser.add_argument('--output-dir', default=None,
                            help='Folder with the feature file, and where the model and report go (default apps/history/data).')
        parser.add_argument('--today', default=None, help='Train as on this date (YYYY-MM-DD); default today in Manila.')
        parser.add_argument('--interval-reps', type=int, default=fe.INTERVAL_REPS,
                            help='Refits for the 80%% intervals (default %(default)s).')
        parser.add_argument('--boot-reps', type=int, default=fe.BOOT_REPS,
                            help='Barangay resamples for the 95%% intervals (default %(default)s).')

    def handle(self, *args, **options):
        log = self.stdout.write
        folder = Path(options['output_dir'] or ff.DATA_DIR)
        csv_path, meta_path = folder / ff.FEATURES_FILE.name, folder / ff.FEATURES_META.name
        if not csv_path.exists() or not meta_path.exists():
            raise CommandError(f'No feature file in {folder}; run build_fire_features first.')
        table = ff.read_features(csv_path, meta_path)
        if table.outlines_version != Purok.outlines_version():
            raise CommandError('The purok map changed since the features were built; '
                               'rerun build_fire_features, then train_fire_model.')
        today = date.fromisoformat(options['today']) if options['today'] else timezone.localdate()
        end = today.year * 12 + today.month - 1  # the current month isn't over: train on the months before it
        if end <= TEST_START:
            raise CommandError('The test needs at least one full month of 2026.')
        self.boot = options['boot_reps']

        fires = ft.fire_records()
        area_ids = {r['purok_id'] for r in table.rows}
        label_map, unplaced = ft.labels(fires, area_ids, FIRST_MONTH, end)
        in_window = [f for f in fires if FIRST_MONTH <= ft.month_index(f.when) < end]
        used = [f for f in in_window if any(p in area_ids for p in f.purok_ids)]
        names = dict(Barangay.objects.values_list('id', 'name'))
        unplaced_list = [{'date': f.when.date().isoformat(), 'barangay': names.get(f.barangay_id, '')}
                         for f in unplaced]
        log(f'{len(table.rows)} areas; {len(used)} fires placed in a purok from {month_name(FIRST_MONTH)} to '
            f'{month_name(end - 1)}; {len(unplaced)} name no purok and are left out')

        dev = ft.build_panel(table, label_map, range(FIRST_MONTH, TEST_START))
        test = ft.build_panel(table, label_map, range(TEST_START, end))
        whole = ft.build_panel(table, label_map, range(FIRST_MONTH, end))
        try:
            log('Development (2023-2025, leaving one year out): scoring every candidate...')
            dev_choice = ft.choose(dev)
            dev_fit = ft.fit_final(dev, dev_choice)
            dev_cut = fe.cutoffs(ft.apply_platt(dev_choice.oof, *dev_fit.platt), dev.y)
            log('The test (2026, once)...')
            test_section, p_test = self.test_section(table, dev, test, dev_choice, dev_fit, dev_cut, end)
            check = self.barangay_check(table, dev, test, p_test, in_window)
            sensitivity = self.sensitivity(table, test, p_test, dev_cut)
            lobo = self.leave_one_barangay_out(whole, dev_choice, dev_fit, dev_cut)
            log('Deployment (every month): choosing and fitting again, then the 80% intervals...')
            choice = ft.choose(whole)
            fitted = ft.fit_final(whole, choice)
            cut = fe.cutoffs(ft.apply_platt(choice.oof, *fitted.platt), whole.y)
            ids, X12 = fe.calendar_rows(whole)
            p12 = fitted.predict(X12)
            spans = fe.intervals(whole, choice, reps=options['interval_reps'])
        except ValueError as exc:
            raise CommandError(str(exc)) from exc

        version = self.version(csv_path, used, choice)
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
                 'trained': trained, 'outlines_version': table.outlines_version, 'areas': areas}
        named = sum(1 for r in table.rows if r['from_fire_log'])
        report = {'version': version, 'credit': ff.CREDIT,
                  'model': {'family': choice.family, 'settings': choice.settings},
                  'candidates': choice.candidates, 'verdict': choice.verdict, 'cutoffs': asdict(cut),
                  'trained': trained, 'test': test_section, 'barangay_check': check, 'sensitivity': sensitivity,
                  'leave_one_barangay_out': lobo, 'caveat': CAVEAT.format(named=named, total=len(table.rows)),
                  'unplaced': unplaced_list,
                  'features': {'built_at': table.built_at, 'sources': table.sources, 'dropped': list(table.dropped)}}
        if Purok.outlines_version() != table.outlines_version:
            raise CommandError('The purok map changed while the model was training; rerun build_fire_features.')
        write_pair(folder, {
            ff.MODEL_FILE.name: json.dumps(model, separators=(',', ':'), default=_json_default) + '\n',
            ff.REPORT_FILE.name: json.dumps(report, indent=1, ensure_ascii=False, default=_json_default) + '\n'})
        self.summary(model, report, today)

    def scores(self, y, p, groups, orange=None):
        return fe.scores(y, p, groups, orange=orange, reps=self.boot)

    def test_section(self, table, dev, test, dev_choice, dev_fit, dev_cut, end):
        """(the report's test section, the test chances) for the development model on 2026."""
        p = dev_fit.predict(test.X)
        levels = fe.level_table(test.y, p, dev_cut)
        buildings = {r['purok_id']: r['buildings_in_area'] for r in table.rows}
        comparison = {name: self.scores(test.y, cp, test.barangay)
                      for name, cp in fe.comparison_baselines(dev, test, buildings).items()}
        return {'window': {'start': month_name(TEST_START), 'end': month_name(end - 1)},
                'rows': int(len(test.y)), 'fires': int(test.y.sum()),
                'chosen': {'family': dev_choice.family, 'label': dev_choice.settings['label'],
                           'verdict': dev_choice.verdict},
                'cutoffs': asdict(dev_cut), 'scores': self.scores(test.y, p, test.barangay, dev_cut.orange),
                'levels': levels, 'green_fires': levels[2]['fires'], 'reliability': fe.reliability(test.y, p),
                'comparison': comparison}, p

    def barangay_check(self, table, dev, test, p_test, in_window):
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
        return {'rows': len(keys), 'fires': int(y.sum()), 'scores': self.scores(y, p, groups),
                'comparison': {k: self.scores(y, v, groups) for k, v in comparison.items()}}

    def sensitivity(self, table, test, p, cut):
        """The test scored apart for areas drawn because a fire address named them and for the rest (spec 6.5)."""
        named = {r['purok_id'] for r in table.rows if r['from_fire_log']}
        mask = np.isin(test.purok, list(named))

        def part(m):
            return self.scores(test.y[m], p[m], test.barangay[m], cut.orange) if m.any() else None
        return {'fire_log_named': part(mask), 'others': part(~mask), 'named_areas': len(named),
                'other_areas': len(table.rows) - len(named)}

    def leave_one_barangay_out(self, whole, choice, fitted, cut):
        """Each barangay predicted by the development model refitted without it, over every month."""
        p = np.zeros(len(whole.y))
        for b in np.unique(whole.barangay):
            held = whole.barangay == b
            p[held] = ft.fit_predict(choice.family, choice.settings, whole.X[~held], whole.y[~held], whole.X[held])
        p = ft.clip(ft.apply_platt(ft.clip(p), *fitted.platt))
        return self.scores(whole.y, p, whole.barangay, cut.orange)

    def version(self, csv_path, used, choice):
        """<family>@<sha1 of the features, the fires and their puroks, and the settings>, 12 characters."""
        h = hashlib.sha1(csv_path.read_bytes())
        for f in sorted(used, key=lambda f: (f.record_id, f.when.isoformat())):
            h.update(f'{f.record_id}|{f.when.isoformat()}|{f.purok_ids}\n'.encode())
        h.update(json.dumps({'family': choice.family, 'settings': choice.settings}, sort_keys=True).encode())
        return f'{choice.family}@{h.hexdigest()[:12]}'

    def summary(self, model, report, today):
        log = self.stdout.write
        test = report['test']['scores']['log_loss']
        month = today.month - 1
        levels = [a['months'][month]['level'] for a in model['areas'].values()]
        n = max(len(levels), 1)
        log(self.style.SUCCESS(f'Model: {model["model"]["family"]} ({model["model"]["settings"]["label"]}), '
                               f'version {model["version"]}'))
        for reason in report['verdict']['reasons']:
            log(f'  {reason}')
        log(f'  2026 test log loss {test["value"]:.5f} (95% interval {test["low"]} to {test["high"]})')
        log(f'  This month: {sum(lv != "Green" for lv in levels) / n:.0%} of areas Orange or Red, '
            f'{sum(lv == "Red" for lv in levels) / n:.0%} Red')
        if model['cutoffs']['red'] is None:
            log(f'  {model["cutoffs"]["red_reason"]}')
        if report['unplaced']:
            log(f'  {len(report["unplaced"])} fires name no purok and were left out (listed in the report)')
