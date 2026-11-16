"""Test the flood and landslide models (spec Section 2) and write data/hazard_model_report.json, version 2."""
import hashlib
import json
import os
from datetime import datetime
from pathlib import Path

import numpy as np
import requests
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.barangays.models import Barangay
from apps.history import (
    exposure, hazard_data, hazard_models, hazard_tests, hazard_verdict, landslide_catalogue, prediction_log, storms)
from apps.history.firth import FitFailed
from apps.history.hazard_data import (
    HAZARDS, MANILA, STUDY_END, STUDY_START, load_exclusions, load_records, read_terrain, records_signature)
from apps.history.hazard_models import REPORT_VERSION, CannotEvaluate, credits_for, report_limits, to_json_safe
from apps.history.hazard_tests import LeakageError, LogisticContender, TwoPartContender, build_hazard_data
from apps.history.rain import ARCHIVE_FIRST_DAY, read_rain_csv


def cache_dir() -> Path:
    """The git-ignored folder the raw NASA catalogue is cached in (read at call time; tests replace it)."""
    return Path(settings.BASE_DIR) / '.hazard_cache'


def _sha1(*paths) -> str:
    """sha1 of the files' bytes, one after another."""
    digest = hashlib.sha1()
    for path in paths:
        digest.update(Path(path).read_bytes())
    return digest.hexdigest()


def _excluded(hazard, records, excluded: dict) -> list[dict]:
    """The hazard's records left out by hazard_model_exclusions.csv, with the reason."""
    return sorted(({'source_ref': r.source_ref, 'reason': excluded[r.source_ref], 'barangay_id': r.barangay_id,
                    'day': r.day.isoformat()} for r in records if r.hazard == hazard and r.source_ref in excluded),
                  key=lambda e: e['source_ref'])


class Command(BaseCommand):
    help = ('Test the flood and landslide models (leave one storm out, yearly folds, baselines, the replacing '
            'rule), fit both on the whole study period and write data/hazard_model_report.json (version 2). '
            'Needs fetch_rain (from 2006-12-18), fetch_storms and build_hazard_features first; downloads the '
            'NASA Global Landslide Catalog into .hazard_cache when it is not there. Takes several minutes.')

    def add_arguments(self, parser):
        parser.add_argument('--hazard', choices=HAZARDS,
                            help='Test one hazard and merge it into the existing report. Refused unless that '
                                 'report is version 2, with the same study period and the same input files.')

    def handle(self, *args, **options):
        # Paths are read here, not at import, so they follow hazard_data.DATA_DIR, REPORT_PATH and cache_dir().
        data_dir, report_path = hazard_data.DATA_DIR, hazard_models.REPORT_PATH
        paths = {   # in the order the README runs the commands that make them
            'rain': (data_dir / 'rain_daily.csv', 'Run fetch_rain first.'),
            'storms': (data_dir / storms.STORM_FILE.name, 'Run fetch_storms first.'),
            'storms_meta': (data_dir / storms.META_FILE.name, 'Run fetch_storms first.'),
            'terrain': (data_dir / 'barangay_terrain.csv', 'Run build_hazard_features first.'),
            'exposure': (data_dir / exposure.EXPOSURE_FILE.name, 'Run build_hazard_features first.'),
            'exclusions': (data_dir / 'hazard_model_exclusions.csv', 'It lists the records left out of the main run.'),
            'catalogue_exclusions': (data_dir / landslide_catalogue.EXCLUSIONS_FILE.name,
                                     'It lists the NASA catalogue events left out by hand.'),
        }
        for path, fix in paths.values():
            if not path.exists():
                raise CommandError(f'{path} is missing. {fix}')
        path = {name: p for name, (p, _) in paths.items()}
        rain = read_rain_csv(path['rain'])
        if rain.first_day is None or rain.first_day > ARCHIVE_FIRST_DAY:
            raise CommandError(f'{path["rain"]} starts on {rain.first_day}, after {ARCHIVE_FIRST_DAY.isoformat()}. '
                               f'Run fetch_rain to fetch the rain from {ARCHIVE_FIRST_DAY.isoformat()}.')
        cache = cache_dir()
        try:
            catalogue_path = landslide_catalogue.ensure_catalogue(cache)
        except (requests.RequestException, ValueError, OSError) as exc:
            raise CommandError(f'The NASA Global Landslide Catalog is not in {cache} and could not be downloaded '
                               f'from {landslide_catalogue.CATALOGUE_URL}: {exc}') from exc

        study = {'start': STUDY_START.isoformat(), 'end': STUDY_END.isoformat()}
        files = {'rain_sha1': _sha1(path['rain']), 'terrain_sha1': _sha1(path['terrain']),
                 'exclusions_sha1': _sha1(path['exclusions']), 'exposure_sha1': _sha1(path['exposure']),
                 'storms_sha1': _sha1(path['storms'], path['storms_meta']), 'catalogue_sha1': _sha1(catalogue_path),
                 'catalogue_exclusions_sha1': _sha1(path['catalogue_exclusions'])}
        hazards = [options['hazard']] if options.get('hazard') else list(HAZARDS)
        results = {}
        if options.get('hazard'):
            existing = hazard_models.read_report(report_path)
            if (existing is None or existing.get('version') != REPORT_VERSION or existing.get('study') != study
                    or existing.get('files') != files or not isinstance(existing.get('hazards'), dict)):
                raise CommandError(
                    f'--hazard {options["hazard"]} merges into an existing version {REPORT_VERSION} report built from '
                    f'the same study period and the same input files, and {report_path} is missing, unreadable, from '
                    f'an older version or built from other ones. Run test_hazard_models without --hazard so both '
                    f'hazards are tested together.')
            results = dict(existing['hazards'])

        terrain = read_terrain(path['terrain'])
        excluded = load_exclusions(path['exclusions'])
        exposure_rows = exposure.read_exposure(path['exposure'])
        storm_days = storms.read_storm_days(path['storms'], path['storms_meta'])
        try:
            centre = storms.talisay_centre()
        except ValueError as exc:
            raise CommandError(str(exc)) from exc
        every = landslide_catalogue.read_catalogue(catalogue_path)
        # the era ends with the whole catalogue's last record (spec 1.4), not the last one near Talisay
        catalogue_end = landslide_catalogue.era_end(every) if every else None
        catalogue = landslide_catalogue.near(every, centre,
                                             landslide_catalogue.load_exclusions(path['catalogue_exclusions']))
        names = dict(Barangay.objects.values_list('id', 'name'))

        for hazard in hazards:
            flood = hazard == 'Flood'
            records = load_records(hazard)
            try:
                data = build_hazard_data(hazard, terrain, rain, storm_days if flood else None,
                                         exposure_rows if flood else None, records, excluded,
                                         catalogue=None if flood else catalogue, names=None if flood else names,
                                         catalogue_end=None if flood else catalogue_end)
            except ValueError as exc:
                raise CommandError(f'{hazard}: {exc}') from exc
            y = data.rows.y
            counts = {'rows': int(len(y)), 'positives': int(y.sum()),
                      'positive_days': int(len(np.unique(data.rows.day[y == 1]))),   # the days rule (b) compares
                      'event_days': int(data.city_y.sum())}                          # any kept record that day
            extra = ''
            if not flood:
                extra = f', {len(catalogue)} NASA catalogue records within the radius'
                if catalogue and catalogue_end is not None:
                    era = min(catalogue_end, hazard_tests.CATALOGUE_LAST)
                    extra += f' (catalogue era {hazard_tests.CATALOGUE_START.isoformat()} to {era.isoformat()})'
            self.stdout.write(f"{hazard}: {counts['rows']:,} barangay-days on {len(data.city_day):,} days, "
                              f"{counts['positives']} with an event on {counts['positive_days']} days{extra}. "
                              f"Testing...")
            try:
                result = hazard_verdict.evaluate(data, reps=hazard_tests.BOOTSTRAP_REPS)
                everything = np.ones(len(data.city_day), dtype=bool)     # the whole study period
                fits = {TwoPartContender.name: TwoPartContender(hazard).fit(data, everything).to_json(),
                        LogisticContender.name: LogisticContender(hazard).fit(data, everything)}
            except (CannotEvaluate, FitFailed, LeakageError) as exc:
                raise CommandError(f'{hazard}: {exc}') from exc
            entry = {'hazard': hazard, 'in_use': result['in_use'], 'verdict': result['verdict'], 'fits': fits,
                     **counts, 'tests': result['tests'], 'limits': [], 'credits': credits_for(hazard),
                     'data_signature': records_signature(records, STUDY_START, STUDY_END),
                     'excluded': _excluded(hazard, records, excluded),
                     'logged': prediction_log.logged_summary(hazard, records)}
            entry['limits'] = report_limits(hazard, entry, barangays=len(data.place))
            results[hazard] = to_json_safe(entry)

        report = {'version': REPORT_VERSION, 'generated': datetime.now(MANILA).isoformat(timespec='seconds'),
                  'study': study, 'files': files, 'hazards': {h: results[h] for h in HAZARDS if h in results}}
        text = json.dumps(report, indent=2, allow_nan=False)
        partial = report_path.with_name(report_path.name + '.partial')
        with open(partial, 'w', encoding='utf-8', newline='\n') as f:
            f.write(text + '\n')
        os.replace(partial, report_path)     # never leave a half-written report behind

        for hazard in hazards:
            r = results[hazard]
            verdict = r['verdict']
            outcome = (f"the two-part model was adopted under rule ({verdict['rule']})" if verdict['adopted']
                       else 'the two-part model was not adopted')
            self.stdout.write(f"{hazard}: in use {r['in_use']}; {outcome}.")
            for reason in verdict['reasons']:
                self.stdout.write(f'  {reason}')
        self.stdout.write(self.style.SUCCESS(f'Report written to {report_path}'))
