"""
manage.py train_fire_model [--today YYYY-MM-DD] [--window fixed|moving]

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
developer machine after build_fire_features; it only reads the database. The pipeline itself
is apps/history/fire_run.py; --window moving tests on the newest 12 full months instead of 2026
and adds the switch verdict against the model now in use.
"""
import json
from datetime import date
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.barangays.models import Barangay, Purok
from apps.history import fire_evaluation as fe
from apps.history import fire_features as ff
from apps.history import fire_purok
from apps.history import fire_run
from apps.history import fire_training as ft
from apps.history.fire_run import (CAVEAT, FIRST_MONTH, TEST_START, _json_default, barangay_months,  # noqa: F401
                                   month_name, sig, write_pair)


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
        parser.add_argument('--window', choices=('fixed', 'moving'), default='fixed',
                            help='fixed: test on 2026 to the last full month. moving: test on the newest 12 full '
                                 'months and judge the new fit against the model in use (default %(default)s).')

    def handle(self, *args, **options):
        folder = Path(options['output_dir'] or ff.DATA_DIR)
        csv_path, meta_path = folder / ff.FEATURES_FILE.name, folder / ff.FEATURES_META.name
        if not csv_path.exists() or not meta_path.exists():
            raise CommandError(f'No feature file in {folder}; run build_fire_features first.')
        table = ff.read_features(csv_path, meta_path)
        if table.outlines_version != Purok.outlines_version():
            raise CommandError('The purok map changed since the features were built; '
                               'rerun build_fire_features, then train_fire_model.')
        today = date.fromisoformat(options['today']) if options['today'] else timezone.localdate()
        live = None
        if options['window'] == 'moving':
            current = fire_purok.load()
            live = getattr(current, 'model', None) if not isinstance(current, str) else None
        try:
            model, report = fire_run.train(
                ft.fire_records(), table, dict(Barangay.objects.values_list('id', 'name')), today,
                window=options['window'], live=live, csv_bytes=csv_path.read_bytes(),
                boot_reps=options['boot_reps'], interval_reps=options['interval_reps'], log=self.stdout.write)
        except ValueError as exc:
            raise CommandError(str(exc)) from exc
        if Purok.outlines_version() != table.outlines_version:
            raise CommandError('The purok map changed while the model was training; rerun build_fire_features.')
        write_pair(folder, {
            ff.MODEL_FILE.name: json.dumps(model, separators=(',', ':'), default=_json_default) + '\n',
            ff.REPORT_FILE.name: json.dumps(report, indent=1, ensure_ascii=False, default=_json_default) + '\n'})
        self.summary(model, report, today)

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
