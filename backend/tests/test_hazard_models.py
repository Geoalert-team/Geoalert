import hashlib
import json
import shutil
import tempfile
import warnings
from datetime import date, datetime, timedelta
from functools import lru_cache
from io import StringIO
from pathlib import Path
from unittest import mock

import numpy as np
import requests
from django.contrib.gis.geos import MultiPolygon, Polygon
from django.core.cache import cache
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.test import SimpleTestCase, TestCase

from apps.barangays.models import Barangay
from apps.hazards.models import HazardType
from apps.history import hazard_data, hazard_models, hazard_tests, landslide_catalogue
from apps.history.exposure import read_exposure, write_exposure
from apps.history.firth import FitFailed
from apps.history.hazard_data import (
    HAZARDS, MANILA, RAIN_FEATURES, STUDY_END, STUDY_START, TERRAIN_FEATURES, Dataset, build_dataset,
    load_exclusions, load_records, read_terrain, records_signature, write_terrain)
from apps.history.hazard_models import (
    FOLDS, REPORT_OLD, REPORT_UNREADABLE, CannotEvaluate, benchmark_probs, credits_for, make_logistic, no_skill,
    report_limits)
from apps.history.hazard_scoring import score_logistic, score_two_part
from apps.history.hazard_tests import LogisticContender, TwoPartContender, build_hazard_data
from apps.history.management.commands import test_hazard_models as command
from apps.history.models import HazardPredictionLog, HistoricalRecord
from apps.history.rain import ARCHIVE_FIRST_DAY, read_rain_csv, write_rain_csv
from apps.history.storms import StormDays, read_storm_days, write_storm_days
from apps.history.two_part import FEATURES, TwoPartFit
from tests.hazard_fixtures import (
    toy_event_records, toy_inputs, toy_report_v1, toy_report_v2, toy_source_ref, write_toy_files)


def hand_dataset(rows):
    """rows: (barangay, date, y)"""
    n = len(rows)
    return Dataset(X=np.zeros((n, 2)), y=np.array([r[2] for r in rows], dtype=int),
                   barangay_id=np.array([r[0] for r in rows]),
                   day=np.array([np.datetime64(r[1], 'D') for r in rows]), features=('a', 'b'))


class HazardModelTests(SimpleTestCase):
    def test_fixed_settings_are_used_exactly(self):
        lr = make_logistic()[-1]
        self.assertEqual((lr.C, lr.l1_ratio, lr.solver, lr.max_iter), (1.0, 0.0, 'lbfgs', 2000))

    def test_read_report_is_none_when_missing_or_unreadable(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        path = tmp / 'report.json'
        self.assertIsNone(hazard_models.read_report(path))
        path.write_bytes(b'not json')
        self.assertIsNone(hazard_models.read_report(path))
        path.write_bytes(b'\xff\xfe\x00broken')
        self.assertIsNone(hazard_models.read_report(path))
        path.write_bytes(b'[1, 2]')
        self.assertIsNone(hazard_models.read_report(path))
        path.write_text(json.dumps({'hazards': {}}), encoding='utf-8')
        self.assertEqual(hazard_models.read_report(path), {'hazards': {}})
        with mock.patch.object(hazard_models, 'REPORT_PATH', path):       # the default is read at call time
            self.assertEqual(hazard_models.read_report(), {'hazards': {}})
        self.assertEqual(hazard_models.REPORT_PATH.name, 'hazard_model_report.json')
        self.assertEqual(hazard_models.REPORT_PATH.parent, hazard_data.DATA_DIR)

    def test_folds_never_train_on_their_test_year_or_later(self):
        for train, test in FOLDS:
            self.assertTrue(max(train) < test)

    def test_the_logistic_regression_fits_and_predicts_without_warnings(self):
        terrain, rain, pos = toy_inputs()
        for hazard in ('Flood', 'Landslide'):
            ds, _ = build_dataset(hazard, terrain, rain, pos, date(2021, 1, 1), date(2025, 12, 31))
            self.assertEqual(ds.features, RAIN_FEATURES + TERRAIN_FEATURES[hazard])
            X = ds.X.copy()
            X[:5, -1] = np.nan
            with warnings.catch_warnings():
                warnings.simplefilter('error')
                p = make_logistic().fit(X, ds.y).predict_proba(X)[:, 1]
            self.assertEqual(p.shape, (len(ds.y),))
            self.assertTrue(((p >= 0) & (p <= 1)).all())

    def test_all_nan_training_column_keeps_columns_aligned(self):
        terrain, rain, pos = toy_inputs()
        ds, _ = build_dataset('Flood', terrain, rain, pos, date(2021, 1, 1), date(2025, 12, 31))
        X = ds.X.copy()
        X[:, 3] = np.nan
        pipe = make_logistic().fit(X, ds.y)
        self.assertEqual(pipe[-1].n_features_in_, X.shape[1])

    def test_benchmark_reads_training_years_only(self):
        # two training years, so January has 2 x 31 = 62 distinct days
        rows = []
        for year in (2021, 2022):
            for d in range(1, 32):
                rows.append((1, date(year, 1, d), 1 if (year, d) == (2021, 5) else 0))
                rows.append((2, date(year, 1, d), 0))
        train = hand_dataset(rows)
        pi = train.y.mean()
        test = hand_dataset([(1, date(2023, 1, 10), 0), (2, date(2023, 1, 10), 0), (3, date(2023, 1, 10), 0),
                             (1, date(2023, 2, 10), 0)])
        p = benchmark_probs(train, test)
        self.assertAlmostEqual(p[0], (1 + pi * 30) / (62 + 30))
        self.assertAlmostEqual(p[1], (0 + pi * 30) / (62 + 30))
        self.assertAlmostEqual(p[2], (0 + pi * 30) / (62 + 30))   # unseen barangay
        self.assertAlmostEqual(p[3], (0 + pi * 30) / (0 + 30))    # February never seen in training
        self.assertAlmostEqual(no_skill(train), pi)
        flipped = hand_dataset([(1, date(2023, 1, 10), 1), (2, date(2023, 1, 10), 1),
                                (3, date(2023, 1, 10), 1), (1, date(2023, 2, 10), 1)])
        np.testing.assert_array_equal(benchmark_probs(train, flipped), p)

    def test_to_json_safe_gives_strict_json_values(self):
        safe = hazard_models.to_json_safe({'a': (np.float64('nan'), np.inf, np.int64(3), np.bool_(True),
                                                 np.array([1.5, 2.0]), date(2025, 1, 2),
                                                 np.datetime64('2025-03-04'), None, 'x'),
                                           7: {'k': np.float32(0.5)}})
        self.assertEqual(safe, {'a': [None, None, 3, True, [1.5, 2.0], '2025-01-02', '2025-03-04', None, 'x'],
                                '7': {'k': 0.5}})
        self.assertIs(type(safe['a'][2]), int)
        self.assertIs(type(safe['a'][3]), bool)


# ---- Task 10: limits, credits and the toy version 2 report ----

FLOOD_ENTRY = {'positives': 18, 'positive_days': 5, 'rows': 40172}
FLOOD_LIMITS = [
    'From 2021 to 2025, 18 reported flood barangay-days fall on 5 distinct days, so the evidence is closer to 5 '
    'days than to 40,172 rows.',
    'With 5 such days, no model can be shown statistically better day by day: one that does better on all 5 days '
    'reaches at best p = 0.0625 on a two-sided sign test.',
    "Rain comes from one NASA POWER grid cell (about 55 by 69 km) for the city's 22 barangays, and the cell's "
    'edge at 10.25° N runs through Talisay, so part of the city lies outside the cell it reads and local '
    'downpours can be missed.',
    'An empty barangay-day means no flood was reported, not that none happened: every chance is of a reported '
    'flood and reads lower than how often floods really happen.',
    "The two-part model's flood shares use UP NOAH flood hazard maps, which are labelled beta, rest on about 30 "
    'years of rain and come from a community mirror; the Mananga River works planned for 2026 would change '
    'river-flood hazard, and the maps do not show them.',
    'The 15% and 25% cut-offs and several earlier choices were made after seeing 2023–2025, so the 2026 season is '
    'the clean test.',
]
CATALOGUE_LIMIT = ("The two-part model also learns landslide timing from NASA's Global Landslide Catalog, which "
                   'states no licence, often places an event only to within 5–25 km, and covers 2007–2017, not the '
                   'years the forecast is for.')


class LimitsTests(SimpleTestCase):
    def test_limits_are_plain_sentences_from_the_numbers(self):
        self.assertEqual(report_limits('Flood', FLOOD_ENTRY, barangays=22), FLOOD_LIMITS)
        slide = report_limits('Landslide', {'positives': 1, 'positive_days': 1, 'rows': 1, 'dropped': 0},
                              barangays=1)
        self.assertEqual(slide, [
            'From 2021 to 2025, 1 reported landslide barangay-day falls on 1 distinct day, so the evidence is closer '
            'to 1 day than to 1 row.',
            'With 1 such day, no model can be shown statistically better day by day: one that does better on that '
            'day reaches at best p = 1 on a two-sided sign test.',
            "Rain comes from one NASA POWER grid cell (about 55 by 69 km) for the city's 1 barangay, and the cell's "
            'edge at 10.25° N runs through Talisay, so part of the city lies outside the cell it reads and local '
            'downpours can be missed.',
            'An empty barangay-day means no landslide was reported, not that none happened: every chance is of a '
            'reported landslide and reads lower than how often landslides really happen.',
            CATALOGUE_LIMIT,
            FLOOD_LIMITS[-1],
        ])
        self.assertTrue(all(isinstance(s, str) and s.endswith('.') for s in FLOOD_LIMITS + slide))
        self.assertFalse(any('NOAH' in s for s in slide))
        self.assertFalse(any('Catalog' in s for s in FLOOD_LIMITS))

    def test_the_sign_test_follows_the_number_of_days(self):
        self.assertEqual([hazard_models.sign_test_p(n) for n in (0, 1, 5, 6)], [1.0, 1.0, 0.0625, 0.03125])
        six = report_limits('Flood', {'positives': 9, 'positive_days': 6, 'rows': 100}, barangays=3)[1]
        self.assertEqual(six, 'With 6 such days, a model that does better on all 6 days reaches p = 0.03125 on a '
                              'two-sided sign test; doing better on fewer of them is weaker evidence.')
        twenty = report_limits('Flood', {'positives': 45, 'positive_days': 20, 'rows': 100}, barangays=3)[1]
        self.assertEqual(twenty, 'With 20 such days, a model that does better on all 20 days reaches p < 0.001 on a '
                                 'two-sided sign test; doing better on fewer of them is weaker evidence.')
        none = report_limits('Flood', {'positives': 0, 'positive_days': 0, 'rows': 100}, barangays=3)
        self.assertEqual(none[0], 'From 2021 to 2025, 0 reported flood barangay-days fall on 0 distinct days, so the '
                                  'evidence is closer to 0 days than to 100 rows.')
        self.assertEqual(none[1], 'No reported flood named a barangay, so the models cannot be compared event day '
                                  'by event day.')

    def test_rows_left_out_join_the_first_sentence(self):
        first = report_limits('Flood', {**FLOOD_ENTRY, 'dropped': 5}, barangays=22)[0]
        self.assertTrue(first.endswith('than to 40,172 rows (5 more barangay-days were left out because a day of '
                                       'the 14-day rain window was missing).'), first)
        one = report_limits('Flood', {**FLOOD_ENTRY, 'dropped': 1}, barangays=22)[0]
        self.assertIn('(1 more barangay-day was left out because', one)

    def test_credits_are_the_exact_lines(self):
        self.assertEqual(credits_for('Flood'), [
            'Rain: NASA POWER (CC BY 4.0).',
            'Storm tracks: IBTrACS v04r01 (NOAA NCEI).',
            'Flood exposure: UP NOAH flood hazard maps (ODbL), via the bettergovph mirror.',
            'Buildings: Microsoft Global ML Building Footprints (ODbL).',
        ])
        self.assertEqual(credits_for('Landslide'), [
            'Rain: NASA POWER (CC BY 4.0).',
            'Landslide timing also learned from NASA Global Landslide Catalog days near Talisay, 2007–2017.',
        ])
        self.assertEqual(REPORT_OLD, 'The model report is from an older version; run manage.py test_hazard_models.')


HAZARD_KEYS = {'hazard', 'in_use', 'verdict', 'fits', 'rows', 'positives', 'positive_days', 'event_days', 'tests',
               'limits', 'credits', 'data_signature', 'excluded', 'logged'}
REPORT_KEYS = {'version', 'generated', 'study', 'files', 'hazards'}
FILE_KEYS = {'rain_sha1', 'terrain_sha1', 'exclusions_sha1', 'exposure_sha1', 'storms_sha1', 'catalogue_sha1',
             'catalogue_exclusions_sha1'}


def _no_nan(constant):
    raise ValueError(f'not strict JSON: {constant}')


class ToyReportTests(SimpleTestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def test_toy_report_v2_is_a_valid_report_its_fits_score(self):
        path = self.tmp / 'hazard_model_report.json'
        terrain, rain, pos = write_toy_files(self.tmp, [11, 12, 13])
        report = toy_report_v2(path)
        self.assertEqual(json.loads(path.read_text(encoding='utf-8'), parse_constant=_no_nan), report)
        self.assertEqual((set(report), report['version']), (REPORT_KEYS, 2))
        self.assertEqual(set(report['files']), FILE_KEYS)
        self.assertEqual(report['files']['rain_sha1'], hashlib.sha1((self.tmp / 'rain_daily.csv').read_bytes()).hexdigest())
        self.assertIsNone(report['files']['storms_sha1'])
        for hazard, entry in report['hazards'].items():
            self.assertEqual(set(entry), HAZARD_KEYS)
            self.assertEqual(entry['in_use'], 'two_part')
            self.assertEqual((entry['verdict']['adopted'], entry['verdict']['rule']), (True, 'b'))
            self.assertEqual(entry['data_signature'],
                             records_signature(toy_event_records(hazard, pos), STUDY_START, STUDY_END))
            self.assertEqual(entry['limits'], report_limits(hazard, entry, barangays=3))
            self.assertEqual(entry['credits'], credits_for(hazard))
            self.assertEqual(set(entry['tests']), {'loso', 'yearly', 'events', 'outside'})
            self.assertEqual(len(entry['tests']['events']), entry['positive_days'])
            fit = TwoPartFit.from_json(entry['fits']['two_part'])
            self.assertEqual((fit.hazard, fit.when.features, set(fit.shares)), (hazard, FEATURES[hazard], {11, 12, 13}))
            p = score_two_part(entry['fits']['two_part'], np.array([[4.0, 1.0], [1.0, 0.0]]), np.array([0, 1, 0]),
                               np.array([11, 12, 13]))
            self.assertTrue(((p > 0) & (p < 1)).all())
            ds, _ = build_dataset(hazard, terrain, rain, pos, date(2025, 1, 1), date(2025, 1, 31))
            q = score_logistic(entry['fits']['logistic_regression'], ds.X)
            self.assertEqual(entry['fits']['logistic_regression']['features'], list(ds.features))
            self.assertTrue(((q > 0) & (q < 1)).all())
        self.assertIsNone(report['hazards']['Flood']['tests']['outside'])
        self.assertIn('current', report['hazards']['Landslide']['tests']['outside'])
        self.assertEqual(report['hazards']['Landslide']['fits']['two_part']['when']['intercepts'].keys(),
                         {'geoalert', 'catalogue'})

    def test_toy_report_v2_options(self):
        path = self.tmp / 'hazard_model_report.json'
        report = toy_report_v2(path, hazards=('Flood',), in_use='logistic_regression', shares={1: 0.5, 2: 0.25})
        entry = report['hazards']['Flood']
        self.assertEqual(list(report['hazards']), ['Flood'])
        self.assertEqual((entry['in_use'], entry['verdict']['adopted'], entry['verdict']['rule']),
                         ('logistic_regression', False, None))
        self.assertTrue(any(r.startswith('It gave a lower chance to the hit barangays on ')
                            for r in entry['verdict']['reasons']))
        self.assertEqual(entry['fits']['two_part']['shares'], {'1': 0.5, '2': 0.25})     # barangay 3 has none
        self.assertEqual(set(report['files'].values()), {None})                            # no files beside it
        with self.assertRaises(ValueError):
            toy_report_v2(path, in_use='random_forest')


class AccuracyEntryTests(TestCase):
    def setUp(self):
        cache.clear()                       # the live `logged` blocks are kept in the cache
        self.addCleanup(cache.clear)
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.ids = [Barangay.objects.create(name=f'Toy {i}').id for i in range(3)]
        _, _, self.pos = write_toy_files(self.tmp, self.ids)
        self.report_path = self.tmp / 'hazard_model_report.json'
        patcher = mock.patch.object(hazard_models, 'REPORT_PATH', self.report_path)
        patcher.start()
        self.addCleanup(patcher.stop)

    def write(self, report):
        self.report_path.write_text(json.dumps(report), encoding='utf-8')

    def unavailable(self):
        entries = hazard_models.accuracy_entries(date(2026, 11, 13))
        self.assertEqual([(e['hazard'], e['kind'], e['status']) for e in entries],
                         [('Flood', 'rain_terrain', 'unavailable'), ('Landslide', 'rain_terrain', 'unavailable')])
        for e in entries:
            self.assertEqual(set(e), {'hazard', 'kind', 'status', 'reason'})
        return [e['reason'] for e in entries]

    def test_accuracy_entries_flag_an_old_report(self):
        v2 = toy_report_v2(self.report_path)
        old = {k: v for k, v in v2.items() if k != 'version'}
        self.write({'generated': old['generated'], 'hazards': old['hazards']})     # no version at all
        self.assertEqual(self.unavailable(), [REPORT_OLD, REPORT_OLD])
        self.write({**old, 'version': 1})
        self.assertEqual(self.unavailable(), [REPORT_OLD, REPORT_OLD])
        # the report test_hazard_models wrote before version 2 (a `winner`, no version) is old too, never read as v1
        toy_report_v1(self.report_path)
        self.assertEqual(self.unavailable(), [REPORT_OLD, REPORT_OLD])
        # a version 2 report without one hazard, then no report at all
        self.write({**v2, 'hazards': {'Flood': v2['hazards']['Flood']}})
        entries = hazard_models.accuracy_entries(date(2026, 11, 13))
        self.assertEqual(entries[0]['status'], 'in_use')
        self.assertEqual(entries[1], {'hazard': 'Landslide', 'kind': 'rain_terrain', 'status': 'unavailable',
                                      'reason': 'The model report has no landslide result; run manage.py '
                                                'test_hazard_models.'})
        self.write({**v2, 'hazards': {**v2['hazards'], 'Landslide': {'in_use': 'random_forest'}}})
        self.assertEqual(hazard_models.accuracy_entries(date(2026, 11, 13))[1]['status'], 'unavailable')
        self.report_path.unlink()
        self.assertEqual(self.unavailable(), [REPORT_UNREADABLE, REPORT_UNREADABLE])

    def test_accuracy_entries_drop_the_fits_and_keep_stale(self):
        for in_use in ('two_part', 'logistic_regression'):
            report = toy_report_v2(self.report_path, in_use=in_use)
            entries = hazard_models.accuracy_entries(date(2026, 11, 13))
            for entry, hazard in zip(entries, HAZARDS):
                saved = report['hazards'][hazard]
                self.assertNotIn('fits', entry)
                self.assertEqual(entry, {**{k: v for k, v in saved.items() if k != 'fits'}, 'kind': 'rain_terrain',
                                         'status': 'in_use', 'stale': True, 'study': report['study'],
                                         'tested_at': report['generated']})
        # the records the report was built from: no longer stale
        kind = {h: HazardType.objects.create(name=h, logo_class='x') for h in HAZARDS}
        for hazard in HAZARDS:
            HistoricalRecord.objects.bulk_create([
                HistoricalRecord(barangay_id=b, hazard_type=kind[hazard], severity_level='Green',
                                 source_ref=toy_source_ref(hazard, b, d), hazard_subcategory='TOY',
                                 occurred_at=datetime(d.year, d.month, d.day, 12, tzinfo=MANILA))
                for b, d in sorted(self.pos)])
        self.assertEqual([e['stale'] for e in hazard_models.accuracy_entries(date(2026, 11, 13))], [False, False])
        HistoricalRecord.objects.create(barangay_id=self.ids[0], hazard_type=kind['Landslide'], severity_level='Red',
                                        source_ref='late-entry', occurred_at=datetime(2024, 3, 1, 12, tzinfo=MANILA))
        self.assertEqual([e['stale'] for e in hazard_models.accuracy_entries(date(2026, 11, 13))], [False, True])

    def test_logged_block_is_scored_live_or_read_from_the_report_when_the_log_cannot_be_read(self):
        report = toy_report_v2(self.report_path, in_use='logistic_regression')
        saved = {'first': '2026-06-01', 'last': '2026-06-02', 'rows': 6, 'events': 0, 'expected': 0.01,
                 'events_interval': [0.0, 3.6889], 'new_events': []}
        report['hazards']['Flood']['logged'] = saved
        self.write(report)
        today = date(2026, 11, 13)

        def logged():
            return [e['logged'] for e in hazard_models.accuracy_entries(today)]

        # the log can be read but holds nothing yet: nothing logged, whatever the report saved
        self.assertEqual(logged(), [None, None])
        cache.clear()
        # rows present: the block is scored from the log now, as fire's is, with the events reported since
        july = date(2026, 7, 1)
        for b, p in zip(self.ids, (0.2, 0.05, 0.01)):
            HazardPredictionLog.objects.create(hazard='Flood', barangay_id=b, kind='day', period_start=july,
                                               issued_on=july + timedelta(days=1),
                                               model_version='logistic_regression@x', probability=p, inputs={})
        flood = HazardType.objects.create(name='Flood', logo_class='x')
        HistoricalRecord.objects.create(barangay_id=self.ids[0], hazard_type=flood, severity_level='Orange',
                                        source_ref='flood-2026', occurred_at=datetime(2026, 7, 1, 12, tzinfo=MANILA))
        live = logged()[0]
        self.assertEqual((live['first'], live['last'], live['rows'], live['events']),
                         ('2026-07-01', '2026-07-01', 3, 1))
        self.assertEqual(live['expected'], 0.26)
        self.assertEqual(live['new_events'], [{'day': '2026-07-01', 'barangay_id': self.ids[0], 'barangay': 'Toy 0',
                                               'chance': 0.2, 'chance_before': None,
                                               'model_version': 'logistic_regression@x'}])
        self.assertIsNone(logged()[1])                                  # no landslide row logged
        # kept for LOGGED_SECONDS: a row added since is not read until then
        HazardPredictionLog.objects.create(hazard='Flood', barangay_id=self.ids[0], kind='day',
                                           period_start=july + timedelta(days=1), issued_on=july + timedelta(days=2),
                                           model_version='logistic_regression@x', probability=0.3, inputs={})
        self.assertEqual(logged()[0], live)
        self.assertEqual(hazard_models.LOGGED_SECONDS, 600)
        # the log cannot be read (the table is not there): the block test_hazard_models saved in the report
        cache.clear()
        with connection.cursor() as cursor:
            cursor.execute(f'ALTER TABLE {HazardPredictionLog._meta.db_table} RENAME TO prediction_log_away')
        with self.assertLogs('apps.history.prediction_log', level='WARNING'):
            self.assertEqual(logged(), [saved, None])


# ---- Task 10: the command ----

REPS = 20
NAMES = {1: 'Manipis', 2: 'Lagtang', 3: 'Tapul'}
CENTRE = (10.25, 123.847)
EXCLUDED_REF = 'excl-1'
EXCLUDED_ROW = (2, date(2022, 7, 8))
CATALOGUE_HEADER = ('event_id,event_date,event_title,location_description,location_accuracy,admin_division_name,'
                    'gazeteer_closest_point,latitude,longitude')
CATALOGUE_LATEST = date(2017, 9, 28)      # as in the real catalogue, the latest record is far from Talisay


@lru_cache(maxsize=None)
def command_inputs():
    """Toy terrain and rain from 2006-12-18 (13 days before 2006-12-31) to the study's end, with every toy
    event (the catalogue's days come from them) and the study's own."""
    terrain, rain, every = toy_inputs(start=date(2006, 12, 31), end=STUDY_END)
    return terrain, rain, every, frozenset((b, d) for b, d in every if STUDY_START <= d <= STUDY_END)


def catalogue_csv(every):
    heavy = sorted({d for _, d in every if 2008 <= d.year <= 2016})

    def line(eid, d, title, lat=CENTRE[0]):
        return f'{eid},{d:%m/%d/%Y} 12:00:00 AM,{title},{title},5km,Cebu,Talisay,{lat},{CENTRE[1]}'

    lines = [CATALOGUE_HEADER]
    for i, d in enumerate(heavy[::3]):
        lines.append(line(f'c{i}', d, 'Landslide in Manipis Talisay City' if i % 2 == 0 else 'Landslide near Cebu City'))
    lines += [line('c-last', date(2017, 3, 9), 'Slide'),
              line('c-listed', heavy[1], 'Listed slide'),                 # in the exclusion file
              line('c-negros', heavy[2], 'Slide in Negros'),              # Negros is never Talisay
              line('c-far', heavy[4], 'Far slide', lat=CENTRE[0] + 1.0),  # about 111 km away
              # the whole catalogue's latest record, far away: it still ends the catalogue era (spec 1.4)
              line('c-far-latest', CATALOGUE_LATEST, 'Far slide', lat=CENTRE[0] + 1.0)]
    return '\n'.join(lines) + '\n'


def write_inputs(data_dir: Path, cache: Path):
    """Every file the command reads: the six data files and the cached catalogue."""
    terrain, rain, every, pos = command_inputs()
    write_rain_csv(data_dir / 'rain_daily.csv', rain, {b: (10.5, 123.75) for b in rain})
    write_terrain(data_dir / 'barangay_terrain.csv', terrain, NAMES)
    (data_dir / 'hazard_model_exclusions.csv').write_text(f'source_ref,reason\n{EXCLUDED_REF},Date uncertain\n',
                                                          encoding='utf-8')
    write_exposure(data_dir / 'barangay_exposure.csv',
                   {b: {'buildings': 1000.0, 'noah25_mh': 300.0 / b, 'noah100_mh': 300.0 / b,
                        'hand_lt2_buildings': 300.0 / b, 'exposure': 300.0 / b} for b in terrain}, NAMES)
    first = min(rain[1])
    stormy = {d for _, d in every} | {first + timedelta(days=i) for i in range(0, (STUDY_END - first).days, 40)}
    write_storm_days(StormDays({d: ('S1', 'TOY', 100.0) for d in stormy if first <= d <= STUDY_END}, first, STUDY_END),
                     'toy', datetime(2026, 11, 13, tzinfo=MANILA), CENTRE, data_dir / 'storm_days.csv',
                     data_dir / 'storm_days.meta.json')
    (data_dir / 'landslide_catalogue_exclusions.csv').write_text('event_id,reason\nc-listed,Duplicate\n',
                                                                  encoding='utf-8')
    cache.mkdir(parents=True, exist_ok=True)
    (cache / landslide_catalogue.CACHE_NAME).write_text(catalogue_csv(every), encoding='utf-8')


def expected_files(data_dir: Path, cache: Path) -> dict:
    def sha1(*names, root=data_dir):
        return hashlib.sha1(b''.join((root / n).read_bytes() for n in names)).hexdigest()
    return {'rain_sha1': sha1('rain_daily.csv'), 'terrain_sha1': sha1('barangay_terrain.csv'),
            'exclusions_sha1': sha1('hazard_model_exclusions.csv'), 'exposure_sha1': sha1('barangay_exposure.csv'),
            'storms_sha1': sha1('storm_days.csv', 'storm_days.meta.json'),
            'catalogue_sha1': sha1(landslide_catalogue.CACHE_NAME, root=cache),
            'catalogue_exclusions_sha1': sha1('landslide_catalogue_exclusions.csv')}


def create_records():
    """Barangays 1-3 near Talisay (boundaries for talisay_centre) and every toy event of the study period as a
    flood and a landslide record, plus an excluded, a later and a sample flood record that never count."""
    for b, name in NAMES.items():
        west = 123.84 + 0.005 * (b - 1)
        Barangay.objects.create(id=b, name=name, municipality='Talisay',
                                boundary=MultiPolygon(Polygon.from_bbox((west, 10.245, west + 0.004, 10.255)),
                                                      srid=4326))
    _, _, _, pos = command_inputs()
    for hazard in HAZARDS:
        kind = HazardType.objects.create(name=hazard, logo_class='x')
        rows = [(b, d, toy_source_ref(hazard, b, d), False) for b, d in sorted(pos)]
        if hazard == 'Flood':
            rows += [(*EXCLUDED_ROW, EXCLUDED_REF, False), (1, date(2026, 3, 1), 'after-study', False),
                     (1, date(2023, 5, 5), 'sample-row', True)]
        HistoricalRecord.objects.bulk_create(
            [HistoricalRecord(barangay_id=b, hazard_type=kind, severity_level='Green', source_ref=ref,
                              occurred_at=datetime(d.year, d.month, d.day, 12, tzinfo=MANILA),
                              hazard_subcategory='RIVER OVERFLOW', is_sample=sample)
             for b, d, ref, sample in rows])


def command_patches(data_dir: Path, cache: Path, report_path: Path):
    """Paths read at call time, few bootstrap resamples, and a catalogue download that must never happen."""
    return [mock.patch.object(hazard_data, 'DATA_DIR', data_dir),
            mock.patch.object(hazard_models, 'REPORT_PATH', report_path),
            mock.patch.object(hazard_tests, 'BOOTSTRAP_REPS', REPS),
            mock.patch.object(command, 'cache_dir', lambda: cache),
            mock.patch.object(landslide_catalogue, 'get', mock.Mock(side_effect=AssertionError('no download')))]


class CommandInputTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        create_records()

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.data, self.cache = self.tmp / 'data', self.tmp / 'cache'
        self.data.mkdir()
        write_inputs(self.data, self.cache)
        self.report_path = self.data / 'hazard_model_report.json'
        for patcher in command_patches(self.data, self.cache, self.report_path):
            patcher.start()
            self.addCleanup(patcher.stop)

    def refused(self, *words, **options):
        """The command stops with a message holding every word, and the report stays as it was."""
        before = self.report_path.read_bytes() if self.report_path.exists() else None
        with self.assertRaises(CommandError) as caught:
            call_command('test_hazard_models', stdout=StringIO(), **options)
        for word in words:
            self.assertIn(word, str(caught.exception))
        self.assertEqual(self.report_path.read_bytes() if self.report_path.exists() else None, before)
        self.assertFalse(self.report_path.with_name(self.report_path.name + '.partial').exists())
        return str(caught.exception)

    def test_command_refuses_a_rain_file_that_starts_after_2006(self):
        self.report_path.write_bytes(b'{"generated": "the old report"}\n')
        terrain, rain, _ = toy_inputs(start=date(2016, 12, 31), end=STUDY_END)
        write_rain_csv(self.data / 'rain_daily.csv', rain, {b: (10.5, 123.75) for b in rain})
        self.assertEqual(read_rain_csv(self.data / 'rain_daily.csv').first_day, date(2016, 12, 18))
        self.refused('fetch_rain', '2016-12-18', ARCHIVE_FIRST_DAY.isoformat())
        (self.data / 'rain_daily.csv').unlink()
        self.refused('fetch_rain')

    def test_command_refuses_missing_exposure_storms_or_catalogue(self):
        for name, fix in (('barangay_exposure.csv', 'build_hazard_features'), ('storm_days.csv', 'fetch_storms'),
                          ('storm_days.meta.json', 'fetch_storms'), ('barangay_terrain.csv', 'build_hazard_features'),
                          ('landslide_catalogue_exclusions.csv', 'landslide_catalogue_exclusions.csv')):
            with self.subTest(missing=name):
                path = self.data / name
                kept = path.read_bytes()
                path.unlink()
                self.refused(fix, name)
                path.write_bytes(kept)
        self.assertFalse(self.report_path.exists())
        # the catalogue: not cached, and the download fails or is not the catalogue
        (self.cache / landslide_catalogue.CACHE_NAME).unlink()
        for get, why in ((mock.Mock(side_effect=requests.ConnectionError('network is down')), 'network is down'),
                         (mock.Mock(return_value=b'<html>moved</html>'), 'not the landslide catalogue')):
            with self.subTest(why=why), mock.patch.object(landslide_catalogue, 'get', get):
                self.refused('NASA Global Landslide Catalog', why)
                get.assert_called_once_with(landslide_catalogue.CATALOGUE_URL)
        self.assertFalse(self.report_path.exists())

    def test_command_stops_on_leakage_or_a_model_that_cannot_be_fitted(self):
        self.report_path.write_bytes(b'{"generated": "the old report"}\n')
        # spec 2.5(c): a training day inside a held-out block's 14-day buffer stops the run
        with mock.patch.object(hazard_tests, 'train_mask', lambda days, block: np.ones(len(days), bool)):
            self.refused('Flood', 'within 14 days')
        for error in (CannotEvaluate('the training days hold no reported event'), FitFailed('no convergence')):
            with self.subTest(error=type(error).__name__), \
                    mock.patch.object(TwoPartContender, 'fit', side_effect=error):
                self.refused('Flood', str(error))

    def test_single_hazard_run_merges_only_into_a_matching_v2_report(self):
        self.refused('--hazard Landslide', hazard='Landslide')          # nothing to merge into
        study = {'start': '2021-01-01', 'end': '2025-12-31'}
        files = expected_files(self.data, self.cache)
        kept = {'hazard': 'Flood', 'in_use': 'logistic_regression', 'marker': 'kept'}
        old = {'generated': 'x', 'study': study, 'files': files, 'hazards': {'Flood': kept}}
        self.report_path.write_text(json.dumps(old), encoding='utf-8')
        self.refused('older version', hazard='Landslide')                # a version 1 report is never merged into
        self.report_path.write_text(json.dumps({**old, 'version': 2}), encoding='utf-8')
        out = StringIO()
        call_command('test_hazard_models', hazard='Landslide', stdout=out)
        report = hazard_models.read_report()
        self.assertEqual((report['version'], report['files'], report['study']), (2, files, study))
        self.assertEqual(report['hazards']['Flood'], kept)
        self.assertEqual(set(report['hazards']['Landslide']), HAZARD_KEYS)
        self.assertNotIn('Flood: in use', out.getvalue())
        # a changed input file: Flood would stay described against the old one, so it is refused
        for name in ('hazard_model_exclusions.csv', 'storm_days.csv', 'barangay_exposure.csv',
                     'landslide_catalogue_exclusions.csv'):
            with self.subTest(changed=name):
                path = self.data / name
                original = path.read_bytes()
                path.write_bytes(original + b'extra,row\n')
                self.refused('--hazard Flood', hazard='Flood')
                path.write_bytes(original)


class CommandRunTests(TestCase):
    """One full run on the toy inputs, shared by the tests."""

    @classmethod
    def setUpTestData(cls):
        create_records()

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        tmp = Path(tempfile.mkdtemp())
        cls.addClassCleanup(shutil.rmtree, tmp, ignore_errors=True)
        cls.data, cls.cache = tmp / 'data', tmp / 'cache'
        cls.data.mkdir()
        write_inputs(cls.data, cls.cache)
        cls.report_path = cls.data / 'hazard_model_report.json'
        for patcher in command_patches(cls.data, cls.cache, cls.report_path):
            patcher.start()
            cls.addClassCleanup(patcher.stop)
        out = StringIO()
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter('always')
            call_command('test_hazard_models', stdout=out)
        cls.warnings = [f'{w.category.__name__}: {w.message}' for w in caught]
        cls.output = out.getvalue()
        cls.text = cls.report_path.read_text(encoding='utf-8')
        cls.report = json.loads(cls.text, parse_constant=_no_nan)

    def rebuilt(self, hazard):
        """The command's HazardData, rebuilt here from the same files."""
        excluded = load_exclusions(self.data / 'hazard_model_exclusions.csv')
        rain = read_rain_csv(self.data / 'rain_daily.csv')
        terrain = read_terrain(self.data / 'barangay_terrain.csv')
        if hazard == 'Flood':
            return build_hazard_data('Flood', terrain, rain, read_storm_days(self.data / 'storm_days.csv',
                                                                             self.data / 'storm_days.meta.json'),
                                     read_exposure(self.data / 'barangay_exposure.csv'), load_records('Flood'),
                                     excluded)
        records = landslide_catalogue.read_catalogue(self.cache / landslide_catalogue.CACHE_NAME)
        near = landslide_catalogue.near(records, CENTRE, landslide_catalogue.load_exclusions(
            self.data / 'landslide_catalogue_exclusions.csv'))
        return build_hazard_data('Landslide', terrain, rain, None, None, load_records('Landslide'), excluded,
                                 catalogue=near, names=NAMES, catalogue_end=landslide_catalogue.era_end(records))

    def test_command_writes_version_2_with_fits_and_verdict(self):
        report = self.report
        self.assertEqual(set(report), REPORT_KEYS)
        self.assertEqual(report['version'], 2)
        self.assertEqual(report['study'], {'start': '2021-01-01', 'end': '2025-12-31'})
        self.assertEqual(report['files'], expected_files(self.data, self.cache))
        self.assertEqual(datetime.fromisoformat(report['generated']).utcoffset().total_seconds(), 8 * 3600)
        self.assertEqual(list(report['hazards']), ['Flood', 'Landslide'])
        _, _, _, pos = command_inputs()
        for hazard, entry in report['hazards'].items():
            data = self.rebuilt(hazard)
            self.assertEqual(set(entry), HAZARD_KEYS, hazard)
            self.assertEqual(entry['hazard'], hazard)
            verdict = entry['verdict']
            self.assertEqual(set(verdict), {'adopted', 'rule', 'reasons', 'leakage_checked'})
            self.assertTrue(verdict['leakage_checked'])
            self.assertEqual(entry['in_use'], 'two_part' if verdict['adopted'] else 'logistic_regression')
            self.assertEqual(set(entry['fits']), {'two_part', 'logistic_regression'})
            self.assertEqual(set(entry['tests']), {'loso', 'yearly', 'events', 'outside'})
            # the excluded, later and sample flood records are not events
            self.assertEqual(entry['positives'], len(pos))
            self.assertEqual(entry['positive_days'], len({d for _, d in pos}))
            self.assertEqual(entry['event_days'], len({d for _, d in pos}))
            self.assertEqual(entry['rows'], len(data.rows.y))
            self.assertEqual(entry['rows'], 3 * len(data.city_day))
            self.assertEqual(entry['tests']['loso']['event_days'], entry['event_days'])
            self.assertEqual(entry['limits'], report_limits(hazard, entry, barangays=3))
            self.assertEqual(entry['credits'], credits_for(hazard))
            self.assertEqual(entry['data_signature'], records_signature(load_records(hazard), STUDY_START, STUDY_END))
            self.assertIsNone(entry['logged'])
            self.assertIn(f"{hazard}: in use {entry['in_use']}", self.output)
            for reason in verdict['reasons']:
                self.assertIn(reason, self.output)
        flood, slide = report['hazards']['Flood'], report['hazards']['Landslide']
        self.assertEqual(flood['excluded'], [{'source_ref': EXCLUDED_REF, 'reason': 'Date uncertain',
                                              'barangay_id': 2, 'day': '2022-07-08'}])
        self.assertEqual(slide['excluded'], [])
        self.assertIsNone(flood['tests']['outside'])
        self.assertIn('current', slide['tests']['outside'])
        self.assertEqual(flood['fits']['two_part']['when']['features'], ['log1p_r3', 'storm72'])
        self.assertEqual(set(flood['fits']['two_part']['when']['intercepts']), {'geoalert'})
        # landslide's two-part fit learned from the catalogue era too, which ends with the whole catalogue's latest
        # record (far from Talisay), not with the last record near it (2017-03-09)
        self.assertEqual(set(slide['fits']['two_part']['when']['intercepts']), {'geoalert', 'catalogue'})
        self.assertIsNotNone(slide['fits']['two_part']['beta'])
        self.assertIn('(catalogue era 2007-01-01 to 2017-09-30)', self.output)
        self.assertEqual(self.rebuilt('Landslide').extra_day[-1], np.datetime64('2017-09-30'))
        self.assertIn('Report written to', self.output)
        self.assertEqual(self.warnings, [])

    def test_report_is_strict_json_and_reloads_into_fits(self):
        self.assertEqual(json.loads(json.dumps(self.report, allow_nan=False)), self.report)
        self.assertEqual(hazard_models.read_report(), self.report)
        for hazard, entry in self.report['hazards'].items():
            data = self.rebuilt(hazard)
            everything = np.ones(len(data.city_day), bool)
            # both fits are on every study row (landslide's two-part one with the catalogue era as well)
            saved = TwoPartFit.from_json(entry['fits']['two_part'])
            self.assertEqual(saved.to_json(), entry['fits']['two_part'])
            self.assertEqual(entry['fits']['two_part'], TwoPartContender(hazard).fit(data, everything).to_json())
            self.assertEqual(set(saved.shares), {1, 2, 3})
            current = entry['fits']['logistic_regression']
            self.assertEqual(current, json.loads(json.dumps(LogisticContender(hazard).fit(data, everything))))
            self.assertEqual(current['features'], list(RAIN_FEATURES + TERRAIN_FEATURES[hazard]))
            p = score_logistic(current, data.rows.X)
            self.assertTrue(((p > 0) & (p < 1)).all())
