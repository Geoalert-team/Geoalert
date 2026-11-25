"""
The automatic retraining job (plan Task 6): fetch retries while GeoAlert
wakes, the fire attempt (stale features, switched or kept), the flood attempt
(not tried, kept, switched), the outlines that load only into the job's own
empty database, the command's dry run and its failed post, no coordinate in
its output, and the workflow file. HTTP is mocked; nothing leaves the machine.
"""
import hashlib
import io
import json
import logging
import os
import re
from datetime import date, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

import numpy as np
import requests
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase

from apps.barangays.models import Barangay, Purok
from apps.history import fire_features, flood_features, flood_own, landslide_own, model_job
from apps.history import landslide_features as lf
from apps.history.fire_run import FIRE_STALE_FEATURES
from apps.history.fire_training import FireRecord
from tests.fire_setup import FireSetupMixin
from tests.test_landslide_own import clues_at
from tests.test_landslide_own import spots as landslide_spots

ENV = {'MODEL_JOB_API_URL': 'http://geo.test', 'MODEL_JOB_TOKEN': 's3cret'}
WORKFLOW = Path(__file__).resolve().parents[2] / '.github' / 'workflows' / 'model-retrain.yml'
TODAY = date(2027, 1, 5)  # the flood run: the 2026 wet season is held back
LANDSLIDE_TODAY = date(2027, 1, 6)  # the landslide run, a day after flood's
LANDSLIDE_CRON = '17 19 5 1 *'
COORDINATE = r'\b1[0-9]\.\d{4}|\b12[0-9]\.\d{4}'  # a Talisay latitude or longitude to 4 decimals


def answer(status, body=None):
    response = mock.Mock(status_code=status)
    response.json.return_value = body if body is not None else {}
    return response


def env(**extra):
    """The job's environment, started (stop() puts the old one back), with nothing else of the job's set."""
    values = {**ENV, **extra}
    patcher = mock.patch.dict(os.environ, values)
    patcher.start()
    for name in ('MODEL_JOB_TRIES', 'MODEL_JOB_SCRATCH_DB'):
        if name not in values:
            os.environ.pop(name, None)
    return patcher


def flood_spots(n_train=110, n_held=10, barangays=6):
    """Located flood spots: n_train before June 2026 over `barangays` barangays, then n_held in the 2026 season."""
    spots = []
    for i in range(n_train):
        spots.append({'id': f'r:t{i}', 'when': f'2025-{1 + i % 12:02d}-10T08:00:00+08:00',
                      'lon': 123.9012345 + i * 1e-4, 'lat': 10.2456789 + i * 1e-4,
                      'purok_id': 100 + i % barangays, 'barangay': f'Brgy {i % barangays}'})
    for i in range(n_held):
        spots.append({'id': f'r:h{i}', 'when': f'2026-{6 + i % 6:02d}-15T08:00:00+08:00',
                      'lon': 123.8765432 + i * 1e-4, 'lat': 10.2123456 + i * 1e-4,
                      'purok_id': 200 + i, 'barangay': f'Brgy {i % barangays}'})
    return spots


def flood_data(spots, live=None):
    return {'hazard': 'flood', 'outlines_version': 'server-map-v7', 'spots': spots,
            'floor': flood_own.floor(spots), 'live': live}


def fire_data(outlines_version):
    return {'hazard': 'fire', 'outlines_version': outlines_version, 'barangays': {'5': 'Home', '6': 'Next door'},
            'fires': [{'record_id': 'a', 'when': '2025-03-04T21:15:00+08:00', 'purok_ids': [11], 'barangay_id': 5},
                      {'record_id': 'b', 'when': '2025-07-01T02:00:00+08:00', 'purok_ids': [], 'barangay_id': 6}],
            'live': {'version': 'logistic@abc', 'family': 'logistic', 'settings': {'label': 'C=1'}}}


def write_fire_table(folder, outlines_version):
    row = {'purok_id': 11, 'barangay_id': 5, 'barangay': 'Home', 'name': 'Purok Near', 'confidence': 'high',
           'from_fire_log': False, **{c: 1.0 for c in fire_features.FEATURE_COLUMNS}}
    table = fire_features.FeatureTable(rows=[row], outlines_version=outlines_version, built_at='2026-11-01',
                                       sources={})
    fire_features.write_features(table, Path(folder) / fire_features.FEATURES_FILE.name,
                                 Path(folder) / fire_features.FEATURES_META.name)


class FetchAndPostTests(SimpleTestCase):
    def setUp(self):
        self.addCleanup(env().stop)

    @mock.patch('time.sleep')
    @mock.patch('requests.get', side_effect=requests.Timeout('slow'))
    def test_fetch_retries_then_raises(self, get, sleep):
        with self.assertRaisesMessage(RuntimeError, 'GeoAlert did not answer after 5 tries.'):
            model_job.fetch('fire')
        self.assertEqual(get.call_count, 5)
        self.assertEqual(sleep.call_count, 4)
        sleep.assert_called_with(30)

    @mock.patch('time.sleep')
    @mock.patch('requests.get')
    def test_fetch_retries_on_409_then_succeeds(self, get, sleep):
        get.side_effect = [answer(409), answer(503), requests.ConnectionError('asleep'), answer(200, {'fires': []})]
        self.assertEqual(model_job.fetch('fire', wait=2), {'fires': []})
        self.assertEqual(get.call_count, 4)
        self.assertEqual(sleep.call_count, 3)

    @mock.patch('time.sleep')
    @mock.patch('requests.get', return_value=answer(200, {'spots': []}))
    def test_fetch_sends_the_bearer_token(self, get, sleep):
        model_job.fetch('flood', outlines=True)
        args, kwargs = get.call_args
        self.assertEqual(args[0], 'http://geo.test/api/history/model-job/data/')
        self.assertEqual(kwargs['headers']['Authorization'], 'Bearer s3cret')
        self.assertEqual(kwargs['params'], {'hazard': 'flood', 'outlines': '1'})
        self.assertEqual(kwargs['timeout'], 90)
        sleep.assert_not_called()

    @mock.patch('time.sleep')
    @mock.patch('requests.get', return_value=answer(403, {'detail': 'no'}))
    def test_fetch_does_not_retry_a_refusal(self, get, sleep):
        with self.assertRaises(RuntimeError):
            model_job.fetch('fire')
        self.assertEqual(get.call_count, 1)

    @mock.patch('time.sleep')
    @mock.patch('requests.get', side_effect=requests.Timeout('slow'))
    def test_fetch_tries_from_the_environment(self, get, sleep):
        os.environ['MODEL_JOB_TRIES'] = '1'
        with self.assertRaisesMessage(RuntimeError, 'GeoAlert did not answer after 1 tries.'):
            model_job.fetch('fire')
        sleep.assert_not_called()

    @mock.patch('requests.post')
    def test_post_sends_json_and_cuts_the_reason(self, post):
        post.return_value = answer(201, {'id': 3, 'result': 'kept', 'is_live': False})
        out = model_job.post({'hazard': 'fire', 'result': 'kept', 'reason': 'x' * 600,
                              'model': {'n': np.int64(4), 'p': np.float64(0.5), 'gap': float('nan')}})
        self.assertEqual(out['id'], 3)
        args, kwargs = post.call_args
        self.assertEqual(args[0], 'http://geo.test/api/history/model-job/attempts/')
        self.assertEqual(kwargs['headers']['Authorization'], 'Bearer s3cret')
        body = json.loads(kwargs['data'])
        self.assertEqual(len(body['reason']), 500)
        self.assertEqual(body['model'], {'n': 4, 'p': 0.5, 'gap': None})

    @mock.patch('requests.post', return_value=answer(400, {'detail': 'A model is required'}))
    def test_post_raises_on_a_refusal(self, post):
        with self.assertRaisesMessage(RuntimeError, 'A model is required'):
            model_job.post({'hazard': 'fire', 'result': 'kept', 'reason': 'r'})

    def test_failed_reason_hides_numbers(self):
        self.assertEqual(model_job.failed_reason(OSError('disk')), 'Failed: OSError: disk')
        reason = model_job.failed_reason(ValueError('Self-intersection near point 589123.4567 1187654.3210'))
        self.assertNotIn('589123', reason)
        self.assertNotIn('1187654', reason)
        self.assertLessEqual(len(model_job.failed_reason(ValueError('y' * 900))), len('Failed: ValueError: ') + 200)


class FireAttemptTests(SimpleTestCase):
    def test_fire_records_from(self):
        records = model_job.fire_records_from(fire_data('v1'))
        self.assertEqual(records[0], FireRecord(when=datetime.fromisoformat('2025-03-04T21:15:00+08:00'),
                                                purok_ids=[11], barangay_id=5, record_id='a'))
        self.assertEqual(records[1].purok_ids, [])

    def test_fire_attempt_skips_on_stale_features(self):
        with TemporaryDirectory() as d, mock.patch('apps.history.fire_run.train') as train:
            write_fire_table(d, 'built-on-old-map')
            attempt = model_job.fire_attempt(fire_data('the-current-map'), TODAY, Path(d), 10, 2, log=lambda m: None)
        self.assertEqual(attempt['result'], 'skipped')
        self.assertEqual(attempt['reason'], FIRE_STALE_FEATURES)
        self.assertNotIn('model', attempt)
        train.assert_not_called()

    def test_fire_attempt_switch_and_kept(self):
        model = {'version': 'logistic@new', 'outlines_version': 'v1'}
        for passed, result in ((True, 'switched'), (False, 'kept')):
            report = {'version': 'logistic@new', 'switch': {'passed': passed, 'reason': f'reason {passed}'}}
            with TemporaryDirectory() as d, mock.patch('apps.history.fire_run.train',
                                                       return_value=(model, report)) as train:
                write_fire_table(d, 'v1')
                attempt = model_job.fire_attempt(fire_data('v1'), TODAY, Path(d), 10, 2, log=lambda m: None)
                csv_bytes = (Path(d) / fire_features.FEATURES_FILE.name).read_bytes()
            self.assertEqual(attempt, {'hazard': 'fire', 'result': result, 'reason': f'reason {passed}',
                                       'model': model, 'report': report})
            args, kwargs = train.call_args
            fires, table, names, today = args
            self.assertEqual([f.record_id for f in fires], ['a', 'b'])
            self.assertEqual(names, {5: 'Home', 6: 'Next door'})
            self.assertEqual(today, TODAY)
            self.assertEqual(table.outlines_version, 'v1')
            self.assertEqual(kwargs['window'], 'moving')
            self.assertEqual(kwargs['live'], fire_data('v1')['live'])
            self.assertEqual(kwargs['csv_bytes'], csv_bytes)
            self.assertEqual((kwargs['boot_reps'], kwargs['interval_reps']), (10, 2))


class FloodPatches:
    """Everything below the decision patched: the outlines, the features build, the inputs and the training."""

    def flood_patches(self, report_levels, adopted=True, reasons=(), held=None):
        held = held if held is not None else flood_spots()[-10:]
        self.trained_model = {'version': 'xgboost@own', 'source': 'geoalert', 'outlines_version': 'scratch-db-map',
                              'areas': {}}
        report = {'version': 'xgboost@own', 'acceptance': {'adopted': adopted, 'gates': [], 'reasons': list(reasons)},
                  'temporal_test': {'season': 2026, 'eosrs': None, 'held_back': [
                      {'day': '2026-07-01', 'barangay': s['barangay'], 'purok_id': s['purok_id'], 'level': lv}
                      for s, lv in zip(held, report_levels)]}}

        def build(name, cache_dir, output_dir):
            (Path(output_dir) / flood_features.FEATURES_FILE.name).write_text('purok_id\n1\n', encoding='utf-8')
            (Path(output_dir) / flood_features.FEATURES_META.name).write_text('{"m": 1}', encoding='utf-8')

        features = mock.Mock(buildings={'lon': np.zeros(3), 'lat': np.zeros(3)})
        patches = {
            'load': mock.patch('apps.history.model_job.load_outlines'),
            'build': mock.patch('apps.history.model_job.call_command', side_effect=build),
            'read': mock.patch('apps.history.flood_features.read_features', return_value=features),
            'at': mock.patch('apps.history.flood_features.features_at',
                             side_effect=lambda pts, cache: {c: np.full(len(pts), 0.5)
                                                             for c in flood_features.FEATURE_COLUMNS}),
            # Spec 4: the Tino (EOS-RS) map never goes to GitHub, so the job never reads it
            'eosrs': mock.patch('apps.history.flood_labels.eosrs_polygons',
                                side_effect=AssertionError('the job read the Tino map')),
            'train': mock.patch('apps.history.flood_own.train_own', return_value=(self.trained_model, report)),
        }
        self.mocks = {name: p.start() for name, p in patches.items()}
        for p in patches.values():
            self.addCleanup(p.stop)


class FloodAttemptTests(FloodPatches, TestCase):
    def attempt(self, data, fetch=None):
        fetch = fetch or mock.Mock(return_value={**data, 'barangays': [], 'puroks': []})
        with TemporaryDirectory() as cache, TemporaryDirectory() as work:
            self.workdir = Path(work)
            out = model_job.flood_attempt(data, TODAY, Path(cache), Path(work), 7, 3, log=lambda m: None, fetch=fetch)
            self.fingerprint = None
            csv = self.workdir / flood_features.FEATURES_FILE.name
            if csv.exists():
                meta = self.workdir / flood_features.FEATURES_META.name
                self.fingerprint = hashlib.sha1(csv.read_bytes() + meta.read_bytes()).hexdigest()
        return out, fetch

    def test_flood_attempt_not_tried_below_floor(self):
        fetch = mock.Mock()
        out, _ = self.attempt(flood_data(flood_spots(n_train=7, n_held=0, barangays=1)), fetch=fetch)
        self.assertEqual(out, {'hazard': 'flood', 'result': 'not_tried',
                               'reason': '7 of 100 located flood spots, 1 of 5 barangays'})
        fetch.assert_not_called()

    def test_flood_attempt_not_tried_few_held(self):
        fetch = mock.Mock()
        out, _ = self.attempt(flood_data(flood_spots(n_train=116, n_held=4)), fetch=fetch)
        self.assertEqual(out['result'], 'not_tried')
        self.assertEqual(out['reason'], flood_own.FLOOD_HELD.format(n=4))
        fetch.assert_not_called()

    def test_flood_attempt_not_tried_few_training_barangays(self):
        spots = flood_spots(n_train=110, n_held=0, barangays=1)
        spots += [{**s, 'barangay': f'Brgy {i}'} for i, s in enumerate(flood_spots(n_train=0, n_held=12))]
        out, fetch = self.attempt(flood_data(spots), fetch=mock.Mock())
        self.assertEqual(out['result'], 'not_tried')
        self.assertEqual(out['reason'], flood_own.FLOOD_FOLDS.format(season=2026))
        fetch.assert_not_called()

    def test_flood_attempt_kept_when_fewer_hits(self):
        held = flood_spots()[-10:]
        self.flood_patches(['Red', 'Orange', 'Red'] + ['Green'] * 7)
        live_levels = ['Red', 'Red', 'Orange', 'Orange', 'Red'] + ['Green'] * 4 + [None]
        areas = {str(s['purok_id']): {'level': lv, 'score': 0.5, 'not_assessed_reason': None if lv else 'x'}
                 for s, lv in zip(held, live_levels)}
        live = {'version': 'xgboost@old', 'source': 'geoalert', 'areas': areas}
        data = flood_data(flood_spots(), live=live)
        out, fetch = self.attempt(data)
        self.assertEqual(out['result'], 'kept')
        self.assertEqual(out['reason'], "Fewer of the 2026 wet season's spots in Red or Orange than the map in use "
                                        '(3 vs 5)')
        self.assertIs(out['model'], self.trained_model)
        fetch.assert_called_once_with('flood', outlines=True)
        self.mocks['load'].assert_called_once_with(fetch.return_value)
        args, kwargs = self.mocks['train'].call_args
        features, training, held_spots, city, outside, season, fingerprint = args
        self.assertEqual(len(training), 110)
        self.assertTrue(all(s['positive'] and set(s['inputs']) == set(flood_features.FEATURE_COLUMNS)
                            for s in training))
        self.assertEqual([s['id'] for s in held_spots], [s['id'] for s in held])
        self.assertEqual(set(outside), {s['purok_id'] for s in held})
        self.assertEqual(outside[held[0]['purok_id']]['level'], 'Red')
        self.assertEqual(season, 2026)
        self.assertEqual(fingerprint, self.fingerprint)
        self.assertEqual(kwargs['outside_source'], 'geoalert')
        self.assertIsNone(kwargs['eosrs_flagged'])
        self.assertEqual((kwargs['reps'], kwargs['stability_reps']), (7, 3))

    def test_flood_attempt_sets_server_outlines_version(self):
        self.flood_patches(['Red'] * 8 + ['Green'] * 2)
        out, _ = self.attempt(flood_data(flood_spots()))
        self.assertEqual(out['result'], 'switched')
        self.assertEqual(out['reason'], flood_own.FLOOD_SWITCHED.format(hits=8, n=10))
        self.assertEqual(out['model']['outlines_version'], 'server-map-v7')
        args, kwargs = self.mocks['train'].call_args
        self.assertEqual(args[4], {})
        self.assertIsNone(kwargs['outside_source'])

    def test_flood_attempt_kept_when_a_gate_fails(self):
        self.flood_patches(['Green'] * 10, adopted=False, reasons=['One reason.', 'Another.'])
        out, _ = self.attempt(flood_data(flood_spots()))
        self.assertEqual(out['result'], 'kept')
        self.assertEqual(out['reason'], 'One reason. Another.')
        self.assertIn('report', out)

    def test_flood_attempt_never_reads_the_tino_map(self):
        self.flood_patches(['Red'] * 8 + ['Green'] * 2)
        out, _ = self.attempt(flood_data(flood_spots()))
        self.assertEqual(out['result'], 'switched')
        self.mocks['eosrs'].assert_not_called()
        self.assertIsNone(self.mocks['train'].call_args.kwargs['eosrs_flagged'])

    def test_flood_attempt_switches_over_a_noah_map(self):
        held = flood_spots()[-10:]
        self.flood_patches(['Orange'] * 2 + ['Green'] * 8)
        live = {'version': 'noah_fallback@x', 'source': 'noah',
                'areas': {str(s['purok_id']): {'level': 'Red', 'score': 1.0, 'not_assessed_reason': None}
                          for s in held}}
        out, _ = self.attempt(flood_data(flood_spots(), live=live))
        self.assertEqual(out['result'], 'switched')  # only a geoalert map in use is compared on the season
        self.assertEqual(self.mocks['train'].call_args.kwargs['outside_source'], 'noah')


# Landslide

def landslide_data(spots, live=None):
    return {'hazard': 'landslide', 'outlines_version': 'server-map-v7', 'spots': spots,
            'floor': landslide_own.floor(spots), 'live': live}


def live_map(held, hits, source):
    """A landslide map in use whose first `hits` held-back puroks are Red or Orange (JSON keys, as fetched)."""
    return {'version': 'neural_network@old', 'source': source,
            'areas': {str(s['purok_id']): {'level': 'Orange' if i < hits else 'Green', 'score': 0.5,
                                           'not_assessed_reason': None} for i, s in enumerate(held)}}


class LandslidePatches:
    """
    Everything below the decision patched: the outlines, the features build
    and read, the committed table, the ground check and the run (which calls
    load_tests, as the real one does after its cut-offs).
    """

    def landslide_patches(self, new_levels=(), adopted=True, reasons=()):
        self.trained_model = {'version': 'neural_network@own', 'source': 'geoalert',
                              'outlines_version': 'scratch-db-map',
                              'inputs': {'columns': [], 'landcover_ok': True, 'files': {}}, 'areas': {}}
        self.table = ({'label': np.zeros(0, int)}, {'landcover_ok': True})
        self.tests_seen = []

        def run(table, table_meta, features, load_tests, log=print, **kwargs):
            tests = load_tests()
            self.tests_seen.append(tests)
            log('Verdict: passed all four checks (neural_network@own)')
            held_back = [{'purok_id': p, 'level': lv} for p, lv in zip(tests['test_puroks'], new_levels)]
            report = {'version': 'neural_network@own', 'source': 'geoalert', 'own_spots': 0,
                      'acceptance': {'adopted': adopted, 'gates': {}, 'reasons': list(reasons)},
                      'temporal_test': {'season': tests.get('season'), 'held_back': held_back}}
            return self.trained_model, report

        def build(name, cache_dir, output_dir):
            (Path(output_dir) / lf.FEATURES_FILE.name).write_text('purok_id\n1\n', encoding='utf-8')
            (Path(output_dir) / lf.FEATURES_META.name).write_text('{"m": 1}', encoding='utf-8')
            (Path(cache_dir) / lf.POINTS_FILE).write_bytes(b'points')

        patches = {
            'load': mock.patch('apps.history.model_job.load_outlines'),
            'build': mock.patch('apps.history.model_job.call_command', side_effect=build),
            'read': mock.patch('apps.history.landslide_features.read_features',
                               return_value=mock.Mock(meta={'outlines_version': 'scratch-db-map'})),
            'table': mock.patch('apps.history.landslide_training_table.read_table', return_value=self.table),
            'at': mock.patch('apps.history.landslide_features.features_at',
                             side_effect=lambda pts, cache: clues_at(pts)),
            'ground': mock.patch('apps.history.model_job.talisay_ground',
                                 return_value=lambda pts: np.ones(len(pts), bool)),
            'run': mock.patch('apps.history.landslide_run.run', side_effect=run),
        }
        self.mocks = {name: p.start() for name, p in patches.items()}
        for p in patches.values():
            self.addCleanup(p.stop)

    def attempt(self, data, fetch=None, table_bytes=b'notice\nrows\n', **deadline):
        """(the attempt, the fetch mock); self.files: the checksums of the five inputs, read before they go."""
        self.lines = []
        fetch = fetch or mock.Mock(return_value={**data, 'barangays': [], 'puroks': []})
        with TemporaryDirectory() as cache, TemporaryDirectory() as work, TemporaryDirectory() as committed:
            training, meta = Path(committed) / lf.TRAINING_FILE.name, Path(committed) / lf.TRAINING_META.name
            training.write_bytes(table_bytes)
            meta.write_text('{"rows": 1}', encoding='utf-8')
            self.cache, self.work = Path(cache), Path(work)
            with mock.patch.object(lf, 'TRAINING_FILE', training), mock.patch.object(lf, 'TRAINING_META', meta):
                out = model_job.landslide_attempt(data, LANDSLIDE_TODAY, self.cache, self.work, 7, 3,
                                                  log=self.lines.append, fetch=fetch, **deadline)
            paths = {training.name: training, meta.name: meta,
                     lf.FEATURES_FILE.name: self.work / lf.FEATURES_FILE.name,
                     lf.FEATURES_META.name: self.work / lf.FEATURES_META.name,
                     lf.POINTS_FILE: self.cache / lf.POINTS_FILE}
            self.files = {name: hashlib.sha1(p.read_bytes()).hexdigest() for name, p in paths.items() if p.exists()}
        return out, fetch

    def attempt_with(self, new_hits, live_hits, live_source, n_held=5):
        spots = landslide_spots(40, barangays=4, season_2026=n_held)
        self.landslide_patches(new_levels=['Red'] * new_hits + ['Green'] * (n_held - new_hits))
        return self.attempt(landslide_data(spots, live=live_map(spots[-n_held:], live_hits, live_source)))[0]


class LandslideAttemptTests(LandslidePatches, TestCase):
    def spots(self, n, barangays, season_2026=0):
        return landslide_spots(n, barangays=barangays, season_2026=season_2026)

    def data(self, spots, live=None):
        return landslide_data(spots, live=live)

    def test_below_the_floor_is_not_tried_and_trains_nothing(self):
        self.landslide_patches()
        fetch = mock.Mock()
        a, _ = self.attempt({'spots': self.spots(2, barangays=1), 'live': None, 'outlines_version': 'v'}, fetch=fetch)
        self.assertEqual((a['result'], a['reason']), ('not_tried', '2 of 30 located landslide spots, 1 of 3 barangays'))
        self.assertNotIn('model', a)
        self.assertEqual(a, {'hazard': 'landslide', 'result': 'not_tried',
                             'reason': '2 of 30 located landslide spots, 1 of 3 barangays'})
        fetch.assert_not_called()
        self.mocks['build'].assert_not_called()
        self.mocks['run'].assert_not_called()

    def test_too_few_held_back_spots(self):
        self.landslide_patches()
        fetch = mock.Mock()
        a, _ = self.attempt(self.data(spots=self.spots(40, barangays=4, season_2026=4)), fetch=fetch)
        self.assertEqual(a['reason'], 'Too few new spots to test (4 of 5); tries again next January')
        self.assertEqual(a['result'], 'not_tried')
        self.assertNotIn('model', a)
        fetch.assert_not_called()
        self.mocks['run'].assert_not_called()

    def test_fewer_season_hits_is_kept(self):  # live own-data map catches 5 of 5, the new fit 4 of 5
        a = self.attempt_with(new_hits=4, live_hits=5, live_source='geoalert')
        self.assertEqual(a['result'], 'kept')
        self.assertEqual(a['reason'], "Fewer of the 2026 wet season's spots in Red or Orange than the map in use "
                                      '(4 vs 5)')
        self.assertIs(a['model'], self.trained_model)

    def test_a_tie_switches(self):
        a = self.attempt_with(new_hits=5, live_hits=5, live_source='geoalert')
        self.assertEqual(a['result'], 'switched')
        self.assertEqual(a['reason'], 'Passed all four checks; 5 of 5 held-back spots in Red or Orange')

    def test_more_season_hits_switch(self):
        a = self.attempt_with(new_hits=4, live_hits=3, live_source='geoalert')
        self.assertEqual((a['result'], a['reason']),
                         ('switched', 'Passed all four checks; 4 of 5 held-back spots in Red or Orange'))

    # Ruling R44: spec 6.3 check 5, "no fewer ... than the live map", whatever the live map's source
    def test_a_live_outside_model_map_with_more_hits_is_kept(self):
        a = self.attempt_with(new_hits=3, live_hits=5, live_source='model')
        self.assertEqual((a['result'], a['reason']),
                         ('kept', "Fewer of the 2026 wet season's spots in Red or Orange than the map in use (3 vs 5)"))

    def test_a_live_outside_model_map_with_as_many_hits_switches(self):
        a = self.attempt_with(new_hits=4, live_hits=4, live_source='model')
        self.assertEqual((a['result'], a['reason']),
                         ('switched', 'Passed all four checks; 4 of 5 held-back spots in Red or Orange'))

    def test_every_live_source_is_compared_on_the_season(self):
        for source in ('model', 'noah', 'geoalert'):
            with self.subTest(source=source):
                self.assertEqual(self.attempt_with(new_hits=3, live_hits=5, live_source=source)['result'], 'kept')
                self.assertEqual(self.attempt_with(new_hits=5, live_hits=5, live_source=source)['result'], 'switched')

    # Ruling R43: no GeoAlert rows, no fit (BASIS_GEOALERT never labels a fit without them)
    def test_no_spots_before_the_season_trains_nothing(self):
        self.landslide_patches()
        fetch = mock.Mock()
        a, _ = self.attempt(self.data(self.spots(30, barangays=3, season_2026=30)), fetch=fetch)  # all in 2026
        self.assertEqual(a, {'hazard': 'landslide', 'result': 'not_tried',
                             'reason': 'No located spots before the newest season to train on; tries again next '
                                       'January'})
        self.assertEqual(landslide_own.LANDSLIDE_NO_TRAINING, a['reason'])
        fetch.assert_not_called()
        self.mocks['build'].assert_not_called()
        self.mocks['run'].assert_not_called()

    def test_no_own_slide_left_on_ground_trains_nothing(self):
        self.landslide_patches(new_levels=['Red'] * 5)
        self.mocks['ground'].return_value = lambda pts: np.zeros(len(pts), bool)  # every own point at sea
        a, _ = self.attempt(self.data(self.spots(40, barangays=4, season_2026=5)))
        self.assertEqual((a['result'], a['reason']), ('not_tried', landslide_own.LANDSLIDE_NO_TRAINING))
        self.assertNotIn('model', a)
        self.mocks['run'].assert_not_called()

    def test_a_failed_gate_is_kept_with_the_reasons(self):
        spots = self.spots(40, barangays=4, season_2026=5)
        self.landslide_patches(new_levels=['Red'] * 5, adopted=False, reasons=['One reason.', 'Another.'])
        a, _ = self.attempt(self.data(spots))
        self.assertEqual((a['result'], a['reason']), ('kept', 'One reason. Another.'))
        self.assertIn('report', a)

    def test_the_run_gets_own_rows_the_held_back_season_and_the_job_settings(self):
        spots = self.spots(40, barangays=4, season_2026=5)
        self.landslide_patches(new_levels=['Red'] * 5)
        a, fetch = self.attempt(self.data(spots))
        self.assertEqual(a['result'], 'switched')
        fetch.assert_called_once_with('landslide', outlines=True)
        self.mocks['load'].assert_called_once_with(fetch.return_value)
        self.mocks['build'].assert_called_once_with('build_landslide_features', cache_dir=str(self.cache),
                                                    output_dir=str(self.work))
        self.mocks['read'].assert_called_once_with(self.work / lf.FEATURES_FILE.name,
                                                   self.work / lf.FEATURES_META.name, cache_dir=self.cache)
        args, kwargs = self.mocks['run'].call_args
        self.assertEqual(args[:3], (*self.table, self.mocks['read'].return_value))
        self.assertEqual((kwargs['mode'], kwargs['reps'], kwargs['stability_reps']), ('own', 7, 3))
        own = kwargs['own_rows']
        self.assertEqual(int(own['label'].sum()), 35)  # the spots before June 2026 only
        self.assertEqual(int((own['label'] == 0).sum()), 105)
        self.assertEqual(set(own['fold'].tolist()), {'talisay'})
        self.assertTrue((own['weight'] == 10).all())
        # One test purok per held-back spot (ruling R30), with the season, only when the run asks
        self.assertEqual(self.tests_seen, [{'test_puroks': [s['purok_id'] for s in spots[-5:]], 'season': 2026}])
        self.assertEqual(a['model']['outlines_version'], 'server-map-v7')  # the server's map, not the runner's

    def test_the_fingerprint_covers_the_committed_training_table(self):
        spots = self.spots(40, barangays=4, season_2026=5)
        prints = []
        for table_bytes in (b'notice\nrows\n', b'notice\nother rows\n'):
            self.landslide_patches(new_levels=['Red'] * 5)
            a, _ = self.attempt(self.data(spots), table_bytes=table_bytes)
            fingerprint = self.mocks['run'].call_args.kwargs['fingerprint']
            self.assertEqual(set(self.files), {'landslide_training.csv', 'landslide_training.meta.json',
                                               'landslide_purok_features.csv', 'landslide_purok_features.meta.json',
                                               'landslide_points.npz'})
            self.assertEqual(fingerprint, hashlib.sha1(json.dumps(self.files, sort_keys=True).encode()).hexdigest())
            self.assertEqual(a['model']['inputs']['files'], self.files)  # base names only, as the hand-run command
            prints.append(fingerprint)
        self.assertNotEqual(prints[0], prints[1])

    def test_the_ground_check_reads_the_cache(self):
        spots = self.spots(40, barangays=4, season_2026=5)
        self.landslide_patches(new_levels=['Red'] * 5)
        self.mocks['ground'].return_value = lambda pts: np.arange(len(pts)) % 2 == 0  # every other point at sea
        self.attempt(self.data(spots))
        self.assertEqual(self.mocks['ground'].call_args.args[0], self.cache)
        own = self.mocks['run'].call_args.kwargs['own_rows']
        # Every other point at sea by its place in each read: 18 of the 35 training spots kept, then (review m1)
        # 54 "no" points drawn around those 18 only, 27 of them kept
        self.assertEqual((int(own['label'].sum()), len(own['label'])), (18, 45))

    # Final review B3: the job's own limit reaches the run's refit loops; without one, none
    def test_the_run_gets_the_deadline_and_none_without_one(self):
        from apps.history.landslide_training import Deadline

        spots = self.spots(40, barangays=4, season_2026=5)
        self.landslide_patches(new_levels=['Red'] * 5)
        deadline = Deadline(at=12345.0, minutes=330)
        self.attempt(self.data(spots), deadline=deadline)
        self.assertIs(self.mocks['run'].call_args.kwargs['deadline'], deadline)
        self.landslide_patches(new_levels=['Red'] * 5)
        self.attempt(self.data(spots))
        self.assertIsNone(self.mocks['run'].call_args.kwargs['deadline'])

    def test_job_prints_and_posts_no_coordinate(self):
        spots = self.spots(40, barangays=4, season_2026=5)
        self.landslide_patches(new_levels=['Red'] * 5)
        self.data_enough = self.data(spots, live=live_map(spots[-5:], 5, 'geoalert'))
        a, _ = self.attempt(self.data_enough)
        lines = self.lines
        self.assertEqual(a['result'], 'switched')
        self.assertTrue(lines)
        self.assertNotRegex(' '.join(lines) + json.dumps(model_job._plain(a)), COORDINATE)


REAL_FEATURES_AT = lf.features_at        # before any test patches them
REAL_TALISAY_GROUND = model_job.talisay_ground


class LandslideFarSpotTests(LandslidePatches, TestCase):
    """
    Final review B1: a located spot off Talisay's padded clue grids (a map point
    85 km away, say) read the edge cells' clues and went in with its three "no"
    points at weight 10. Here the real features_at and ground check read saved
    grids whose edge ring has a slope no inner cell has.
    """
    BBOX, ZOOM = (10.24, 123.81, 10.30, 123.89), 12
    EDGE_SLOPE = 99.0

    def real_clues(self):
        from apps.hazards.susceptibility import Grid

        grid = Grid(*self.BBOX, self.ZOOM)
        grids = {c: np.full(grid.shape, 1.0, np.float32) for c in lf.FEATURE_COLUMNS}
        grids['slope_deg'][:] = 20.0
        for edge in (np.s_[0, :], np.s_[-1, :], np.s_[:, 0], np.s_[:, -1]):
            grids['slope_deg'][edge] = self.EDGE_SLOPE
        grids['noah_class'] = np.full(grid.shape, 2, np.uint8)
        build = self.mocks['build'].side_effect

        def build_with_grids(name, cache_dir, output_dir):
            build(name, cache_dir, output_dir)
            lf.write_grids(self.BBOX, self.ZOOM, grids, cache_dir)

        self.mocks['build'].side_effect = build_with_grids
        self.mocks['at'].side_effect = REAL_FEATURES_AT
        self.mocks['ground'].side_effect = REAL_TALISAY_GROUND
        dem = mock.patch('apps.history.landslide_sources.dem_for',
                         side_effect=lambda g, cache, log=print: np.full(g.shape, 50.0, np.float32))
        dem.start()
        self.addCleanup(dem.stop)

    def test_a_far_spot_and_its_no_points_never_reach_training(self):
        spots = landslide_spots(40, barangays=4, season_2026=5)
        spots[0] = {**spots[0], 'lon': spots[0]['lon'] + 0.78}  # a training spot 85 km east
        self.landslide_patches(new_levels=['Red'] * 5)
        self.real_clues()
        a, _ = self.attempt(landslide_data(spots))
        self.assertEqual(a['result'], 'switched')
        own = self.mocks['run'].call_args.kwargs['own_rows']
        self.assertEqual(int(own['label'].sum()), 34)  # the 35 training spots less the far one
        self.assertNotIn(self.EDGE_SLOPE, own['slope_deg'].tolist())  # nor any "no" point around it
        np.testing.assert_array_equal(own['slope_deg'], np.full(len(own['label']), 20.0))
        self.assertTrue((own['weight'] == 10).all())

    def test_a_far_spot_alone_before_the_season_is_not_tried(self):
        spots = landslide_spots(31, barangays=3, season_2026=30)  # one spot before the 2026 season
        spots[0] = {**spots[0], 'lon': spots[0]['lon'] + 0.78}
        self.landslide_patches(new_levels=['Red'] * 30)
        self.real_clues()
        a, _ = self.attempt(landslide_data(spots))
        self.assertEqual(a, {'hazard': 'landslide', 'result': 'not_tried',
                             'reason': landslide_own.LANDSLIDE_NO_TRAINING})  # ruling R43
        self.mocks['run'].assert_not_called()


class LandslideRealRunTests(TestCase):
    """
    The job's wiring through the real run (own mode) on the synthetic typhoon
    table and city of the run's tests: the spots' points appear nowhere in
    what the job prints or would post.
    """

    def real_attempt(self, spots, lines, **deadline):
        """The job's landslide attempt on the run's synthetic table and city, the runner's steps stubbed."""
        from tests.test_landslide_run import talisay, training_table
        from tests.test_landslide_training import ground, valley_floor

        features, table = talisay(), training_table()
        rng = np.random.default_rng(5)

        def build(name, cache_dir, output_dir):
            lf.write_features(features, Path(output_dir) / lf.FEATURES_FILE.name,
                              Path(output_dir) / lf.FEATURES_META.name, cache_dir=cache_dir)

        def clues(points, cache):
            n = len(points)
            slides, n_no = 35, n - 35
            yes, no = ground(rng, slides, 32, 5), valley_floor(rng, n_no)
            values = {c: np.r_[yes[c], no[c]] for c in lf.FEATURE_COLUMNS}
            values['noah_class'] = np.r_[np.full(slides, 2.0), np.zeros(n_no)]
            return values

        with TemporaryDirectory() as cache, TemporaryDirectory() as work, TemporaryDirectory() as committed, \
                mock.patch('apps.history.model_job.load_outlines'), \
                mock.patch('apps.history.model_job.call_command', side_effect=build), \
                mock.patch('apps.history.landslide_training_table.read_table', return_value=table), \
                mock.patch('apps.history.landslide_features.features_at', side_effect=clues), \
                mock.patch('apps.history.model_job.talisay_ground', return_value=lambda pts: np.ones(len(pts), bool)):
            training, meta = Path(committed) / lf.TRAINING_FILE.name, Path(committed) / lf.TRAINING_META.name
            training.write_text('table', encoding='utf-8')
            meta.write_text('{}', encoding='utf-8')
            with mock.patch.object(lf, 'TRAINING_FILE', training), mock.patch.object(lf, 'TRAINING_META', meta):
                return model_job.landslide_attempt(landslide_data(spots), LANDSLIDE_TODAY, Path(cache), Path(work),
                                                   20, 2, log=lines.append, fetch=mock.Mock(return_value={}),
                                                   **deadline)

    # Final review B3: a tiny deadline stops the real run at its first refit loop, with the limit in the words
    def test_a_tiny_deadline_stops_the_real_run(self):
        import time

        from apps.history.landslide_training import Deadline, PastDeadline

        spots = landslide_spots(40, barangays=4, season_2026=5)
        with self.assertRaisesMessage(PastDeadline, 'the run passed its 330-minute limit'):
            self.real_attempt(spots, [], deadline=Deadline(at=time.monotonic(), minutes=330))

    def test_a_real_own_run_prints_and_posts_no_spot(self):
        from tests.test_landslide_run import STEEP

        spots = landslide_spots(40, barangays=4, season_2026=5)
        for s, pid in zip(spots[-5:], (STEEP * 2)[:5]):
            s['purok_id'] = pid
        lines = []
        a = self.real_attempt(spots, lines)
        self.assertIn(a['result'], ('switched', 'kept'))
        self.assertEqual(a['model']['outlines_version'], 'server-map-v7')
        self.assertEqual(a['model']['source'], 'geoalert')
        self.assertEqual(a['report']['own_spots'], 35)
        self.assertEqual(a['report']['temporal_test']['season'], 2026)
        self.assertEqual([h['purok_id'] for h in a['report']['temporal_test']['held_back']],
                         [s['purok_id'] for s in spots[-5:]])
        self.assertEqual(a['model']['version'].split('@')[0], a['model']['chosen'])
        text = ' '.join(lines) + json.dumps(model_job._plain(a))
        for s in spots:
            self.assertNotIn(f'{s["lon"]:.4f}', text)
            self.assertNotIn(f'{s["lat"]:.4f}', text)


class TalisayGroundTests(SimpleTestCase):
    def test_ground_is_height_above_zero_on_the_saved_grid(self):
        from apps.hazards.susceptibility import Grid

        bbox, zoom = (10.20, 123.80, 10.30, 123.90), 14
        grid = Grid(*bbox, zoom)
        dem = np.full(grid.shape, 50.0)
        dem[:, : grid.width // 2] = 0.0  # the west half is sea
        with TemporaryDirectory() as cache:
            np.savez_compressed(Path(cache) / lf.GRIDS_FILE, bbox=np.asarray(bbox, float), zoom=np.asarray(zoom))
            with mock.patch('apps.history.landslide_sources.dem_for', return_value=dem) as dem_for:
                on_ground = model_job.talisay_ground(Path(cache), log=lambda m: None)
        used = dem_for.call_args.args[0]
        self.assertEqual((used.px0, used.py0, used.width, used.height), (grid.px0, grid.py0, grid.width, grid.height))
        self.assertEqual(dem_for.call_args.args[1], Path(cache))
        np.testing.assert_array_equal(on_ground(np.array([[123.81, 10.25], [123.89, 10.25]])), [False, True])
        # Final review B1: off the grid is not ground, though the nearest edge cell is land
        np.testing.assert_array_equal(on_ground(np.array([[123.89 + 0.78, 10.25], [123.89, 10.25 + 0.5]])),
                                      [False, False])


class LoadOutlinesTests(FireSetupMixin, TestCase):
    def payload(self):
        return {'barangays': [{'id': b.id, 'name': b.name, 'boundary': json.loads(b.boundary.geojson)}
                              for b in Barangay.objects.order_by('id')],
                'puroks': [{'id': p.id, 'barangay_id': p.barangay_id, 'name': p.name, 'kind': p.kind,
                            'parent': p.parent, 'source': p.source, 'confidence': p.confidence,
                            'boundary': json.loads(p.boundary.geojson)} for p in Purok.objects.order_by('id')]}

    def test_load_outlines_refuses_without_scratch_flag(self):
        payload = self.payload()
        Barangay.objects.all().delete()
        patcher = env()
        self.addCleanup(patcher.stop)
        with self.assertRaisesMessage(RuntimeError, "Outlines are loaded only into the job's own empty database "
                                                    '(MODEL_JOB_SCRATCH_DB=true).'):
            model_job.load_outlines(payload)
        self.assertEqual((Barangay.objects.count(), Purok.objects.count()), (0, 0))

    def test_load_outlines_refuses_when_puroks_exist(self):
        before = Purok.objects.count()
        patcher = env(MODEL_JOB_SCRATCH_DB='true')
        self.addCleanup(patcher.stop)
        with self.assertRaises(RuntimeError):
            model_job.load_outlines(self.payload())
        self.assertEqual(Purok.objects.count(), before)

    def test_load_outlines_refuses_when_only_barangays_exist(self):
        payload = self.payload()
        Purok.objects.all().delete()
        patcher = env(MODEL_JOB_SCRATCH_DB='true')
        self.addCleanup(patcher.stop)
        with self.assertRaises(RuntimeError):
            model_job.load_outlines(payload)
        self.assertEqual(Purok.objects.count(), 0)

    def test_load_outlines_keeps_ids(self):
        payload = self.payload()
        Barangay.objects.all().delete()
        patcher = env(MODEL_JOB_SCRATCH_DB='true')
        self.addCleanup(patcher.stop)
        model_job.load_outlines(payload)
        self.assertEqual(list(Barangay.objects.order_by('id').values_list('id', 'name')),
                         [(b['id'], b['name']) for b in payload['barangays']])
        self.assertEqual(list(Purok.objects.order_by('id').values_list('id', 'barangay_id', 'name')),
                         [(p['id'], p['barangay_id'], p['name']) for p in payload['puroks']])
        near = Purok.objects.get(id=self.near.id)
        self.assertEqual(near.boundary.geom_type, 'MultiPolygon')
        self.assertTrue(near.boundary.equals_exact(self.near.boundary, 1e-9))


class CommandTests(SimpleTestCase):
    def setUp(self):
        self.addCleanup(env().stop)
        self.fetch = self.start(mock.patch('apps.history.model_job.fetch', return_value=fire_data('v1')))
        self.post = self.start(mock.patch('apps.history.model_job.post',
                                          return_value={'id': 9, 'result': 'kept', 'is_live': False}))

    def start(self, patcher):
        self.addCleanup(patcher.stop)
        return patcher.start()

    def run_job(self, *args):
        out = io.StringIO()
        call_command('run_model_job', *args, stdout=out, stderr=io.StringIO())
        return out.getvalue()

    def test_command_dry_run_posts_nothing(self):
        attempt = {'hazard': 'fire', 'result': 'kept', 'reason': 'The new fit scored worse (0.1 vs 0.09)',
                   'model': {'version': 'v'}, 'report': {'version': 'v'}}
        with mock.patch('apps.history.model_job.fire_attempt', return_value=attempt) as fire:
            out = self.run_job('--hazard', 'fire', '--dry-run', '--today', '2026-12-02')
        self.assertIn('kept: The new fit scored worse (0.1 vs 0.09)', out)
        self.post.assert_not_called()
        args, kwargs = fire.call_args
        self.assertEqual(args[1], date(2026, 12, 2))
        self.assertEqual(args[2], fire_features.DATA_DIR)

    def test_command_posts_and_prints_the_answer(self):
        attempt = {'hazard': 'fire', 'result': 'kept', 'reason': 'Worse', 'model': {}, 'report': {}}
        with mock.patch('apps.history.model_job.fire_attempt', return_value=attempt):
            out = self.run_job('--hazard', 'fire')
        self.post.assert_called_once_with(attempt)
        self.assertIn('kept', out)
        self.assertIn('9', out)

    def test_command_posts_failed_on_error(self):
        with mock.patch('apps.history.model_job.fire_attempt', side_effect=OSError('disk')):
            with self.assertRaisesMessage(CommandError, 'Failed: OSError: disk'):
                self.run_job('--hazard', 'fire')
        self.post.assert_called_once_with({'hazard': 'fire', 'result': 'failed', 'reason': 'Failed: OSError: disk'})

    def test_command_posts_failed_when_the_fetch_fails(self):
        self.fetch.side_effect = RuntimeError('GeoAlert did not answer after 5 tries.')
        with self.assertRaises(CommandError):
            self.run_job('--hazard', 'flood')
        self.post.assert_called_once_with({'hazard': 'flood', 'result': 'failed',
                                           'reason': 'Failed: RuntimeError: GeoAlert did not answer after 5 tries.'})

    def test_command_dry_run_error_posts_nothing(self):
        self.fetch.side_effect = RuntimeError('GeoAlert did not answer after 1 tries.')
        with self.assertRaisesMessage(CommandError, 'GeoAlert did not answer after 1 tries.'):
            self.run_job('--hazard', 'fire', '--dry-run')
        self.post.assert_not_called()

    def test_gis_log_lines_lose_their_numbers(self):
        # Final review P3: GEOS and GDAL quote points through this logger, which the job's console prints
        def noisy(*args, **kwargs):
            logging.getLogger('django.contrib.gis').error(
                'GEOS_ERROR: %s\n', 'Self-intersection at or near point 123.9012345 10.2456789')
            return {'hazard': 'fire', 'result': 'kept', 'reason': 'r', 'model': {}, 'report': {}}

        with mock.patch('apps.history.model_job.fire_attempt', side_effect=noisy), \
                self.assertLogs('django.contrib.gis', 'ERROR') as logs:
            self.run_job('--hazard', 'fire', '--dry-run')
        self.assertEqual(len(logs.output), 1)
        self.assertIn('at or near point # #', logs.output[0])
        self.assertNotRegex(logs.output[0], r'\d+\.\d+')

    def test_command_raises_even_when_the_failed_post_fails(self):
        self.post.side_effect = RuntimeError('still asleep')
        with mock.patch('apps.history.model_job.fire_attempt', side_effect=OSError('disk')):
            with self.assertRaisesMessage(CommandError, 'Failed: OSError: disk'):
                self.run_job('--hazard', 'fire')

    def test_command_runs_the_landslide_attempt(self):
        spots = landslide_spots(2, barangays=1)
        self.fetch.return_value = landslide_data(spots)
        attempt = {'hazard': 'landslide', 'result': 'not_tried',
                   'reason': '2 of 30 located landslide spots, 1 of 3 barangays'}
        with mock.patch('apps.history.model_job.landslide_attempt', return_value=attempt) as landslide:
            out = self.run_job('--hazard', 'landslide', '--dry-run', '--today', '2027-01-06')
        self.fetch.assert_called_once_with('landslide')
        self.assertIn('GeoAlert sent 2 located landslide spots in 1 barangays.', out)
        self.assertIn('not_tried: 2 of 30 located landslide spots, 1 of 3 barangays', out)
        self.post.assert_not_called()
        args, kwargs = landslide.call_args
        data, today, cache, workdir, reps, stability_reps, log = args
        self.assertEqual((today, reps, stability_reps), (date(2027, 1, 6), 1000, 20))  # 20 refits in the job (R60)
        self.assertIs(kwargs['fetch'], model_job.fetch)

    # Final review B3: GitHub stops the landslide job at 360 minutes and then nothing is posted, so the job keeps a
    # limit of its own 330 minutes after it starts; fire and flood get none
    def test_the_landslide_run_gets_a_330_minute_deadline_and_fire_and_flood_none(self):
        import time

        self.fetch.return_value = landslide_data([])
        attempt = {'hazard': 'landslide', 'result': 'not_tried', 'reason': 'r'}
        before = time.monotonic()
        with mock.patch('apps.history.model_job.landslide_attempt', return_value=attempt) as landslide:
            self.run_job('--hazard', 'landslide', '--dry-run')
        after = time.monotonic()
        deadline = landslide.call_args.kwargs['deadline']
        self.assertEqual(deadline.minutes, 330)
        self.assertGreaterEqual(deadline.at, before + 330 * 60)
        self.assertLessEqual(deadline.at, after + 330 * 60)
        self.fetch.return_value = flood_data([])
        with mock.patch('apps.history.model_job.flood_attempt',
                        return_value={'hazard': 'flood', 'result': 'not_tried', 'reason': 'r'}) as flood:
            self.run_job('--hazard', 'flood', '--dry-run')
        self.assertNotIn('deadline', flood.call_args.kwargs)
        self.fetch.return_value = fire_data('v1')
        with mock.patch('apps.history.model_job.fire_attempt',
                        return_value={'hazard': 'fire', 'result': 'kept', 'reason': 'r'}) as fire:
            self.run_job('--hazard', 'fire', '--dry-run')
        self.assertNotIn('deadline', fire.call_args.kwargs)

    def test_a_passed_deadline_posts_failed_with_the_limit(self):  # a tiny limit, through the real deadline
        self.fetch.return_value = landslide_data([])

        def slow(*args, deadline, **kwargs):
            deadline.check()  # the first refit loop's check

        with mock.patch('apps.history.management.commands.run_model_job.LANDSLIDE_LIMIT_MINUTES', 0), \
                mock.patch('apps.history.model_job.landslide_attempt', side_effect=slow):
            with self.assertRaisesMessage(CommandError, 'Failed: the run passed its 0-minute limit'):
                self.run_job('--hazard', 'landslide')
        self.post.assert_called_once_with({'hazard': 'landslide', 'result': 'failed',
                                           'reason': 'Failed: the run passed its 0-minute limit'})

    def test_the_330_minute_limit_is_the_reason_posted(self):
        from apps.history.landslide_training import PastDeadline

        self.fetch.return_value = landslide_data([])
        with mock.patch('apps.history.model_job.landslide_attempt',
                        side_effect=PastDeadline('the run passed its 330-minute limit')):
            with self.assertRaises(CommandError):
                self.run_job('--hazard', 'landslide')
        self.post.assert_called_once_with({'hazard': 'landslide', 'result': 'failed',
                                           'reason': 'Failed: the run passed its 330-minute limit'})

    def test_command_stability_reps_option(self):
        self.fetch.return_value = landslide_data([])
        attempt = {'hazard': 'landslide', 'result': 'not_tried', 'reason': 'r'}
        with mock.patch('apps.history.model_job.landslide_attempt', return_value=attempt) as landslide:
            self.run_job('--hazard', 'landslide', '--stability-reps', '7', '--dry-run')
        self.assertEqual(landslide.call_args.args[5], 7)

    def test_command_flood_keeps_its_settings(self):
        self.fetch.return_value = flood_data([])
        attempt = {'hazard': 'flood', 'result': 'not_tried', 'reason': 'r'}
        with mock.patch('apps.history.model_job.flood_attempt', return_value=attempt) as flood:
            out = self.run_job('--hazard', 'flood', '--dry-run')
        self.assertIn('GeoAlert sent 0 located flood spots in 0 barangays.', out)
        self.assertEqual(flood.call_args.args[4:6], (1000, 200))


class CommandOutputTests(FloodPatches, TestCase):
    def test_command_prints_no_coordinates(self):
        spots = flood_spots()
        self.flood_patches(['Red'] * 8 + ['Green'] * 2)
        self.mocks['train'].side_effect = lambda *a, log, **kw: (log('110 GeoAlert flood spots'),
                                                                  self.mocks['train'].return_value)[1]
        data = flood_data(spots)
        out, err = io.StringIO(), io.StringIO()
        self.addCleanup(env().stop)
        with TemporaryDirectory() as cache, \
                mock.patch('apps.history.model_job.fetch', return_value={**data, 'barangays': [], 'puroks': []}), \
                mock.patch('apps.history.model_job.post') as post:
            call_command('run_model_job', '--hazard', 'flood', '--dry-run', '--today', '2027-01-05',
                         '--cache-dir', cache, stdout=out, stderr=err)
        text = out.getvalue() + err.getvalue()
        self.assertIn('switched: Passed all four checks; 8 of 10 held-back spots in Red or Orange', text)
        post.assert_not_called()
        for s in spots:
            self.assertNotIn(f'{s["lon"]:.4f}', text)
            self.assertNotIn(f'{s["lat"]:.4f}', text)


class WorkflowFileTests(SimpleTestCase):
    """PyYAML is not a requirement, so the workflow is checked as text (controller ruling R4)."""

    def test_workflow_file(self):
        text = WORKFLOW.read_text(encoding='utf-8')
        # Final review P5: :17, since GitHub may delay or drop runs scheduled on the hour
        self.assertEqual(re.findall(r"cron:\s*'([^']+)'", text), ['17 19 1 * *', '17 19 4 1 *', LANDSLIDE_CRON])
        self.assertNotIn('0 19', text)
        self.assertIn("MODEL_JOB_SCRATCH_DB: 'true'", text)
        block = re.search(r'\npermissions:[ \t]*\n((?:[ \t]+.*\n)+)', text).group(1)
        self.assertEqual([line.strip() for line in block.splitlines()], ['contents: read'])
        self.assertNotIn(': write', text)
        self.assertNotIn('${{ secrets.DB_PASSWORD }}', text)
        self.assertNotIn('secrets.DB_', text)
        # Final review I4: the job's secrets reach only the step that runs the job
        job_env = re.search(r'\n    env:\n((?:      .*\n)+)', text).group(1)
        self.assertNotIn('secrets.', job_env)
        step = re.search(r'\n      - name: Retrain\n((?:        .*\n)+)', text).group(1)
        step_env = re.search(r'\n        env:\n((?:          .*\n)+)', '\n' + step).group(1)
        self.assertEqual([line.strip() for line in step_env.splitlines()],
                         ['MODEL_JOB_API_URL: ${{ secrets.MODEL_JOB_API_URL }}',
                          'MODEL_JOB_TOKEN: ${{ secrets.MODEL_JOB_TOKEN }}'])
        for name in ('MODEL_JOB_API_URL', 'MODEL_JOB_TOKEN'):
            self.assertEqual(text.count(f'secrets.{name}'), 1, name)
        self.assertIn("github.event.schedule == '17 19 4 1 *'", text)
        self.assertRegex(text, r'\nconcurrency:\s*model-retrain\s*\n')
        # Fire and flood keep 120 minutes; the landslide run gets GitHub's limit for a job
        self.assertIn("timeout-minutes: ${{ (inputs.hazard == 'landslide' || github.event.schedule == "
                      "'17 19 5 1 *') && 360 || 120 }}", text)
        self.assertIn('runs-on: ubuntu-24.04', text)
        self.assertIn('image: postgis/postgis:16-3.4', text)
        # Actions are pinned to a commit, the version in a comment (a tag can be moved)
        self.assertRegex(text, r'uses: actions/cache@[0-9a-f]{40} # v4\n')
        self.assertNotRegex(text, r'uses: [\w./-]+@v\d')
        self.assertIn('path: backend/.hazard_cache', text)
        self.assertIn('key: model-job-cache-v1', text)
        self.assertIn('python manage.py migrate --noinput', text)
        self.assertIn('python manage.py run_model_job --hazard', text)
        for name in ('hazard:', 'dry_run:', 'workflow_dispatch:', 'type: choice', 'type: boolean'):
            self.assertIn(name, text)

    def test_workflow_runs_landslide_on_6_january_with_20_refits_and_parallel_seeds(self):
        text = WORKFLOW.read_text(encoding='utf-8')
        options = re.search(r'\n        options:\n((?:          - .*\n)+)', text).group(1)
        self.assertEqual([line.strip() for line in options.splitlines()], ['- fire', '- flood', '- landslide'])
        hazard = re.search(r'\n      HAZARD: (.*)\n', text).group(1)
        self.assertEqual(hazard, "${{ inputs.hazard || (github.event.schedule == '17 19 4 1 *' && 'flood' || "
                                 "(github.event.schedule == '17 19 5 1 *' && 'landslide' || 'fire')) }}")
        stability = re.search(r'\n      STABILITY_REPS: (.*)\n', text).group(1)
        self.assertEqual(stability, "${{ (inputs.hazard == 'landslide' || github.event.schedule == '17 19 5 1 *') "
                                    "&& '--stability-reps 20' || '' }}")
        self.assertRegex(text, r"\n      LANDSLIDE_MLP_JOBS: '4'\n")  # R60: the network's seeds side by side
        self.assertIn('python manage.py run_model_job --hazard "$HAZARD" $STABILITY_REPS $DRY_RUN', text)
        self.assertIn("    - cron: '17 19 5 1 *'   # landslide: 03:17 Manila on 6 January", text)
