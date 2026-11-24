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
from apps.history import fire_features, flood_features, flood_own, model_job
from apps.history.fire_run import FIRE_STALE_FEATURES
from apps.history.fire_training import FireRecord
from tests.fire_setup import FireSetupMixin

ENV = {'MODEL_JOB_API_URL': 'http://geo.test', 'MODEL_JOB_TOKEN': 's3cret'}
WORKFLOW = Path(__file__).resolve().parents[2] / '.github' / 'workflows' / 'model-retrain.yml'
TODAY = date(2027, 1, 5)  # the flood run: the 2026 wet season is held back


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
        self.assertEqual(re.findall(r"cron:\s*'([^']+)'", text), ['17 19 1 * *', '17 19 4 1 *'])
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
        self.assertIn('timeout-minutes: 120', text)
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
