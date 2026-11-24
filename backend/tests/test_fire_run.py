"""
fire_run.train (automatic retraining, Task 3): the moved pipeline, the moving
test window with folds counted back from it, and the switch rule.
"""
import hashlib
import json
import shutil
import tempfile
from datetime import date, datetime
from pathlib import Path
from unittest import mock

import numpy as np
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase

from apps.barangays.models import Barangay, Purok
from apps.history import fire_evaluation as fe
from apps.history import fire_features as ff
from apps.history import fire_run
from apps.history import fire_training as ft
from tests.test_fire_training import SMALL
from tests.test_train_fire_model import TODAY, make_world, run, write_table

MOVING_TODAY = date(2027, 2, 2)


def train(folder, today, window='fixed', live=None, boot_reps=20, interval_reps=3, candidates=SMALL):
    table = ff.read_features(Path(folder) / ff.FEATURES_FILE.name, Path(folder) / ff.FEATURES_META.name)
    csv_bytes = (Path(folder) / ff.FEATURES_FILE.name).read_bytes()
    names = dict(Barangay.objects.values_list('id', 'name'))
    with mock.patch.object(ft, 'CANDIDATES', candidates):
        return fire_run.train(ft.fire_records(), table, names, today, window=window, live=live, csv_bytes=csv_bytes,
                              boot_reps=boot_reps, interval_reps=interval_reps, log=lambda *a: None)


def version_before_the_final_review(folder, model, today):
    """A fixed run's version as fire_run._version made it before the final review (P4): the features file, the
    placed fires up to the last full month and the chosen settings, with no training end month."""
    csv_bytes = (Path(folder) / ff.FEATURES_FILE.name).read_bytes()
    area_ids = {int(k) for k in model['areas']}
    end = today.year * 12 + today.month - 1
    used = [f for f in ft.fire_records() if fire_run.FIRST_MONTH <= ft.month_index(f.when) < end
            and any(p in area_ids for p in f.purok_ids)]
    h = hashlib.sha1(csv_bytes)
    for f in sorted(used, key=lambda f: (f.record_id, f.when.isoformat())):
        h.update(f'{f.record_id}|{f.when.isoformat()}|{f.purok_ids}\n'.encode())
    h.update(json.dumps(model['model'], sort_keys=True).encode())
    return f"{model['model']['family']}@{h.hexdigest()[:12]}"


class FoldTests(SimpleTestCase):
    def _table(self):
        rows = []
        for i in range(2):
            row = {'purok_id': i + 1, 'barangay_id': 1, 'barangay': 'A', 'name': f'P{i}', 'confidence': 'medium',
                   'from_fire_log': False}
            row.update({c: 1.0 + i for c in ff.FEATURE_COLUMNS})
            rows.append(row)
        return ff.FeatureTable(rows=rows, outlines_version='v', built_at='x', sources={})

    def test_build_panel_counts_folds_back_from_the_window(self):
        months = range(2023 * 12, 2026 * 12 + 1)
        panel = ft.build_panel(self._table(), {}, months, fold_end=2026 * 12 + 1)
        by_month = dict(zip(panel.month.tolist(), panel.fold.tolist()))
        for m in range(2025 * 12 + 1, 2026 * 12 + 1):  # Feb 2025 - Jan 2026
            self.assertEqual(by_month[m], 0)
        for m in range(2024 * 12 + 1, 2025 * 12 + 1):
            self.assertEqual(by_month[m], 1)
        for m in range(2023 * 12 + 1, 2024 * 12 + 1):  # Feb 2023 - Jan 2024
            self.assertEqual(by_month[m], 2)
        self.assertEqual(by_month[2023 * 12], 3)  # the one month left over, Jan 2023

    def test_default_folds_are_calendar_years(self):
        panel = ft.build_panel(self._table(), {}, range(2023 * 12, 2025 * 12))
        self.assertIsNone(panel.fold)
        years = panel.month // 12
        self.assertEqual(sorted(set(years.tolist())), [2023, 2024])


class FireRunTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        make_world(cls)
        cls.folder = Path(tempfile.mkdtemp())
        write_table(cls.folder, Purok.outlines_version())

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.folder, ignore_errors=True)
        super().tearDownClass()

    def moving(self, live=None):
        return train(self.folder, MOVING_TODAY, window='moving', live=live)

    def test_fixed_window_matches_the_command(self):
        model, report = train(self.folder, date.fromisoformat(TODAY), boot_reps=50, interval_reps=5)  # as run() does
        with tempfile.TemporaryDirectory() as d:
            for name in (ff.FEATURES_FILE.name, ff.FEATURES_META.name):
                shutil.copy(self.folder / name, Path(d) / name)
            run(d)
            cmd_model = json.loads((Path(d) / ff.MODEL_FILE.name).read_text(encoding='utf-8'))
            cmd_report = json.loads((Path(d) / ff.REPORT_FILE.name).read_text(encoding='utf-8'))
        self.assertEqual(model['version'], cmd_model['version'])
        self.assertEqual(json.loads(json.dumps(model['areas'], default=fire_run._json_default)), cmd_model['areas'])
        self.assertEqual(report['test']['window'], cmd_report['test']['window'])
        self.assertNotIn('switch', report)

    def test_moving_version_follows_the_training_end_month(self):
        # Final review P4: a monthly refit with no new fires still gets a new version, so the log takes its rows
        one = {'logistic_regression': SMALL['logistic_regression']}  # the same choice both months
        first, _ = train(self.folder, MOVING_TODAY, window='moving', candidates=one)
        second, _ = train(self.folder, date(2027, 3, 2), window='moving', candidates=one)
        self.assertEqual(first['trained']['fires'], second['trained']['fires'])
        self.assertEqual(first['model'], second['model'])
        self.assertNotEqual(first['version'], second['version'])

    def test_fixed_version_is_unchanged(self):
        model, _ = train(self.folder, date.fromisoformat(TODAY))
        self.assertEqual(model['version'],
                         version_before_the_final_review(self.folder, model, date.fromisoformat(TODAY)))

    def test_model_has_built_at(self):
        model, _ = train(self.folder, date.fromisoformat(TODAY))
        stamp = datetime.fromisoformat(model['built_at'])
        self.assertIsNotNone(stamp.utcoffset())

    def test_moving_window_tests_the_newest_12_months(self):
        _, report = self.moving()
        self.assertEqual(report['test']['window'], {'start': '2026-02', 'end': '2027-01'})
        self.assertEqual(report['switch']['window'], {'start': 'Feb 2026', 'end': 'Jan 2027'})

    def test_moving_needs_13_months(self):
        with self.assertRaisesMessage(ValueError, 'The moving window needs at least 13 months before the test window.'):
            train(self.folder, date(2024, 1, 15), window='moving')

    def test_same_settings_switch(self):
        _, first = self.moving()
        chosen = first['test']['chosen']  # the development fit's own family and settings
        settings = next(s for s in SMALL[chosen['family']] if s['label'] == chosen['label'])
        _, report = self.moving(live={'family': chosen['family'], 'settings': settings})
        switch = report['switch']
        self.assertEqual(switch['new_log_loss'], switch['live_log_loss'])
        self.assertEqual(switch['passed'], switch['new_log_loss'] < switch['same_everywhere_log_loss'])

    def test_first_fit_reason(self):
        _, report = self.moving()
        switch = report['switch']
        self.assertIsNone(switch['live_log_loss'])
        base = report['test']['comparison']['comparison_same_everywhere']['log_loss']['value']
        self.assertEqual(switch['same_everywhere_log_loss'], base)
        if switch['passed']:
            self.assertEqual(switch['reason'], fire_run.FIRE_SWITCHED_FIRST.format(
                new=switch['new_log_loss'], start='Feb 2026', end='Jan 2027'))
        else:
            self.assertTrue(switch['reason'].startswith('No better than the same chance everywhere'))

    def _patched(self, new, live):
        def score(dev, test, family, settings, choice=None):
            return new if choice is not None else live
        with mock.patch.object(fire_run, '_window_log_loss', side_effect=score):
            return self.moving(live={'family': 'logistic_regression', 'settings': SMALL['logistic_regression'][0]})[1]

    def test_worse_new_fit_is_kept(self):
        switch = self._patched(0.05, 0.04)['switch']
        self.assertFalse(switch['passed'])
        self.assertEqual(switch['reason'], 'The new fit scored worse (0.0500 vs 0.0400)')

    def test_baseline_blocks(self):
        switch = self._patched(50.0, 40.0)['switch']
        self.assertFalse(switch['passed'])
        self.assertTrue(switch['reason'].startswith('No better than the same chance everywhere'))

    def test_better_new_fit_switches(self):
        switch = self._patched(0.03, 0.04)['switch']
        self.assertTrue(switch['passed'])
        self.assertEqual(switch['reason'], 'Scored 0.0300 vs 0.0400 on Feb 2026 to Jan 2027')

    def test_command_moving_flag(self):
        with tempfile.TemporaryDirectory() as d:
            for name in (ff.FEATURES_FILE.name, ff.FEATURES_META.name):
                shutil.copy(self.folder / name, Path(d) / name)
            with mock.patch.object(ft, 'CANDIDATES', SMALL):
                call_command('train_fire_model', output_dir=d, today=MOVING_TODAY.isoformat(), window='moving',
                             interval_reps=3, boot_reps=20, stdout=mock.MagicMock())
            report = json.loads((Path(d) / ff.REPORT_FILE.name).read_text(encoding='utf-8'))
        self.assertIn('switch', report)
