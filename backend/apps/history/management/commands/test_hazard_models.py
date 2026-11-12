"""Test the flood and landslide models on held-out years and write data/hazard_model_report.json."""
import hashlib
import json
import os
from datetime import datetime

from django.core.management.base import BaseCommand, CommandError

from apps.history import hazard_data, hazard_models
from apps.history.hazard_data import (
    HAZARDS, MANILA, STUDY_END, STUDY_START, build_dataset, load_exclusions, load_records, positives, read_terrain)
from apps.history.rain import read_rain_csv


def _sha1(path) -> str:
    return hashlib.sha1(path.read_bytes()).hexdigest()


class Command(BaseCommand):
    help = ('Test the flood and landslide models on 2023-2025, each year trained only on the years before it, '
            'and write data/hazard_model_report.json. Reads the database only. Takes several minutes.')

    def add_arguments(self, parser):
        parser.add_argument('--hazard', choices=HAZARDS,
                            help='Test one hazard and merge it into the existing report. Refused unless that '
                                 'report has the same study period and the same rain, terrain and exclusions '
                                 'files.')

    def handle(self, *args, **options):
        # Paths are read here, not at import, so they follow hazard_data.DATA_DIR and REPORT_PATH.
        data_dir, report_path = hazard_data.DATA_DIR, hazard_models.REPORT_PATH
        rain_path = data_dir / 'rain_daily.csv'
        terrain_path = data_dir / 'barangay_terrain.csv'
        exclusions_path = data_dir / 'hazard_model_exclusions.csv'
        for path, fix in ((rain_path, 'Run fetch_rain first.'), (terrain_path, 'Run build_hazard_features first.'),
                          (exclusions_path, 'It lists the records left out of the main run.')):
            if not path.exists():
                raise CommandError(f'{path} is missing. {fix}')
        rain = read_rain_csv(rain_path)
        terrain = read_terrain(terrain_path)
        excluded = load_exclusions(exclusions_path)
        study = {'start': STUDY_START.isoformat(), 'end': STUDY_END.isoformat()}
        files = {'rain_sha1': _sha1(rain_path), 'terrain_sha1': _sha1(terrain_path),
                 'exclusions_sha1': _sha1(exclusions_path)}

        hazards = [options['hazard']] if options.get('hazard') else list(HAZARDS)
        results = {}
        if options.get('hazard'):
            existing = hazard_models.read_report(report_path)
            if (existing is None or existing.get('study') != study or existing.get('files') != files
                    or not isinstance(existing.get('hazards'), dict)):
                raise CommandError(
                    f'--hazard {options["hazard"]} merges into an existing report built from the same study period '
                    f'and the same rain, terrain and exclusions files, and {report_path} is missing, unreadable or '
                    f'built from other ones. Run test_hazard_models without --hazard so both hazards are tested '
                    f'together.')
            results = dict(existing['hazards'])

        ids = set(terrain) & set(rain.rain)
        if not ids:
            raise CommandError('No barangay has both a terrain row and a rain series.')
        for hazard in hazards:
            records = load_records(hazard)
            pos = positives(records, ids, STUDY_START, STUDY_END, set(excluded))
            ds, dropped = build_dataset(hazard, terrain, rain.rain, pos, STUDY_START, STUDY_END)
            sensitivity = None
            if hazard == 'Flood':     # spec C.4 run 2: the same rows with no record left out
                every = positives(records, ids, STUDY_START, STUDY_END, set())
                sensitivity, _ = build_dataset(hazard, terrain, rain.rain, every, STUDY_START, STUDY_END)
            self.stdout.write(f'{hazard}: {len(ds.y):,} barangay-days, {int(ds.y.sum())} with an event, '
                              f'{dropped} left out for missing rain. Testing...')
            try:
                results[hazard] = hazard_models.evaluate_hazard(
                    hazard, ds, rain, terrain, records, sensitivity, excluded=excluded, dropped=dropped,
                    reps=hazard_models.BOOTSTRAP_REPS)
            except hazard_models.CannotEvaluate as exc:
                raise CommandError(str(exc)) from exc

        report = {'generated': datetime.now(MANILA).isoformat(timespec='seconds'), 'study': study, 'files': files,
                  'hazards': {h: results[h] for h in HAZARDS if h in results}}
        text = json.dumps(report, indent=2, allow_nan=False)
        partial = report_path.with_name(report_path.name + '.partial')
        with open(partial, 'w', encoding='utf-8', newline='\n') as f:
            f.write(text + '\n')
        os.replace(partial, report_path)     # never leave a half-written report behind

        for hazard in hazards:
            r = results[hazard]
            self.stdout.write(f"{hazard}: winner {r['winner']}, beats_benchmark {r['beats_benchmark']}")
        self.stdout.write(self.style.SUCCESS(f'Report written to {report_path}'))
