"""
The token-only training-data and attempt endpoints, the public attempts list
and the flood spots count. No coordinate may leave in a public answer.
"""
import importlib
import os
from datetime import datetime, timezone as dt_timezone
from itertools import chain, repeat
from unittest import mock

from django.contrib.gis.geos import Point
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.barangays.models import Purok
from apps.hazards.models import ZoneFieldMark
from apps.history import fire_purok, flood_purok, model_fits
from apps.history.models import HistoricalRecord, ModelFit
from tests import fire_model_file
from tests.fire_setup import FireSetupMixin
from tests.flood_model_file import flood_model_files

DATA = '/api/history/model-job/data/'
ATTEMPTS = '/api/history/model-job/attempts/'
UPDATES = '/api/history/forecast/updates/'
AUTH = {'HTTP_AUTHORIZATION': 'Bearer t0k'}


@override_settings(MODEL_JOB_TOKEN='t0k', HAZARD_LOG_WRITER=False)
class ModelJobApiTests(FireSetupMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.client = APIClient()
        fire_purok.clear_cache()
        flood_purok.clear_cache()
        self.addCleanup(fire_purok.clear_cache)
        self.addCleanup(flood_purok.clear_cache)

    def flood_record(self, purok, when, located=True):
        rec = HistoricalRecord.objects.create(
            barangay=purok.barangay, hazard_type=self.flood, severity_level='Orange', occurred_at=when,
            location=purok.boundary.point_on_surface if located else None)
        rec.puroks.add(purok)
        return rec

    def affected_mark(self):
        zone = self.zone(self.far, hazard_type=self.flood)
        return ZoneFieldMark.objects.create(zone=zone, kind='Affected', created_by=self.officer,
                                            location=Point(*self.far.boundary.point_on_surface, srid=4326))

    def test_token_required(self):
        calls = ((lambda **h: self.client.get(DATA + '?hazard=fire', **h)),
                 (lambda **h: self.client.post(ATTEMPTS, {}, format='json', **h)))
        for call in calls:
            self.assertEqual(call().status_code, 403)
            self.assertEqual(call(HTTP_AUTHORIZATION='Bearer wrong').status_code, 403)
            with override_settings(MODEL_JOB_TOKEN=''):
                self.assertEqual(call(HTTP_AUTHORIZATION='Bearer ').status_code, 403)
                self.assertEqual(call().status_code, 403)

    def test_a_padded_token_setting_still_matches(self):
        # Final review P7: a token pasted into Render with a space or a line break still works
        import config.settings.base as base
        self.addCleanup(importlib.reload, base)
        with mock.patch.dict(os.environ, {'MODEL_JOB_TOKEN': '  t0k \n'}):
            importlib.reload(base)
        with override_settings(MODEL_JOB_TOKEN=base.MODEL_JOB_TOKEN):
            res = self.client.get(DATA + '?hazard=neither', **AUTH)
        self.assertEqual(res.status_code, 400)  # past the token, refused only for the hazard

    def test_fire_data_has_no_coordinates(self):
        rec = HistoricalRecord.objects.create(
            barangay=self.home, hazard_type=self.fire, severity_level='Green', occurred_at=timezone.now(),
            location=self.near.boundary.point_on_surface)
        rec.puroks.add(self.near)
        res = self.client.get(DATA + '?hazard=fire', **AUTH)
        self.assertEqual(res.status_code, 200)
        self.assertIn('no-store', res['Cache-Control'])
        body = res.json()
        self.assertEqual(body['fires'][0]['purok_ids'], [self.near.id])
        self.assertEqual(body['outlines_version'], Purok.outlines_version())
        self.assertEqual(body['barangays'][str(self.home.id)], 'Home')
        self.assertIsNone(body['live'])
        text = res.content.decode()
        self.assertNotIn('POINT', text)
        x, y = self.near.boundary.point_on_surface
        self.assertNotIn(f'{x:.4f}', text)
        self.assertNotIn(f'{y:.4f}', text)

    def test_flood_data_spots_and_outlines(self):
        self.flood_record(self.near, datetime(2025, 6, 1, 9, tzinfo=dt_timezone.utc))
        self.flood_record(self.near, datetime(2025, 6, 2, 9, tzinfo=dt_timezone.utc), located=False)  # purok only
        mark = self.affected_mark()
        with flood_model_files(None):
            body = self.client.get(DATA + '?hazard=flood', **AUTH).json()
            full = self.client.get(DATA + '?hazard=flood&outlines=1', **AUTH).json()
        self.assertEqual(len(body['spots']), 2)
        self.assertTrue(body['spots'][0]['id'].startswith('r:'))
        self.assertEqual(body['spots'][0]['purok_id'], self.near.id)
        self.assertEqual(body['spots'][0]['barangay'], 'Home')
        self.assertEqual(body['spots'][1]['id'], f'm:{mark.id}')
        self.assertEqual(body['spots'][1]['purok_id'], self.far.id)
        self.assertEqual(body['spots'][1]['barangay'], 'Next door')
        lon, lat = self.near.boundary.point_on_surface
        self.assertAlmostEqual(body['spots'][0]['lon'], lon, places=6)
        self.assertAlmostEqual(body['spots'][0]['lat'], lat, places=6)
        self.assertIn('lon', body['spots'][1])
        self.assertEqual(body['floor'], {'n': 2, 'barangays': 2, 'enough': False})
        self.assertNotIn('puroks', body)
        self.assertEqual({p['id'] for p in full['puroks']}, {self.near.id, self.far.id})
        self.assertEqual(full['puroks'][0]['boundary']['type'], 'MultiPolygon')
        self.assertEqual({b['name'] for b in full['barangays']}, {'Home', 'Next door'})
        self.assertIn('barangay_id', full['puroks'][0])

    def test_readiness_json_has_no_spot_coordinates(self):
        self.flood_record(self.near, datetime(2025, 6, 1, 9, tzinfo=dt_timezone.utc))
        with flood_model_files(None):
            res = self.client.get('/api/history/forecast/readiness/')
        lon, lat = self.near.boundary.point_on_surface
        text = res.content.decode()
        self.assertNotIn(f'{lon:.4f}', text)
        self.assertNotIn(f'{lat:.4f}', text)

    def test_fire_live_ignores_a_non_dict_model(self):
        doc = fire_model_file.model_document({self.near: 0.2})
        doc.update(version='x@odd', built_at='2027-03-03T03:00:00+08:00', model='not a dict')
        ModelFit.objects.create(hazard='fire', result='switched', reason='r', version='x@odd',
                                outlines_version=doc['outlines_version'],
                                built_at=datetime(2027, 3, 3, tzinfo=dt_timezone.utc), model=doc,
                                report={**fire_model_file.REPORT, 'version': 'x@odd'}, is_live=True)
        with fire_model_file.model_files(None):
            res = self.client.get(DATA + '?hazard=fire', **AUTH)
        self.assertEqual(res.status_code, 200)
        self.assertIsNone(res.json()['live'])

    def test_bad_hazard_400(self):
        res = self.client.get(DATA + '?hazard=landslide', **AUTH)
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json(), {'detail': 'hazard must be fire or flood.'})
        self.assertEqual(self.client.get(DATA, **AUTH).status_code, 400)

    def test_outlines_changed_409(self):
        with mock.patch.object(Purok, 'outlines_version', side_effect=chain(['a'], repeat('b'))):
            res = self.client.get(DATA + '?hazard=fire', **AUTH)
        self.assertEqual(res.status_code, 409)

    def fire_attempt(self, months=12):
        doc = fire_model_file.model_document({self.near: 0.2})
        doc.update(version='x@new', built_at='2027-03-03T03:00:00+08:00')
        doc['areas'][str(self.near.id)]['months'] = doc['areas'][str(self.near.id)]['months'][:months]
        return {'hazard': 'fire', 'result': 'switched', 'reason': 'Scored better', 'model': doc,
                'report': {**fire_model_file.REPORT, 'version': 'x@new'}}

    def test_post_switched_goes_live(self):
        with flood_model_files(None), fire_model_file.model_files(None):
            res = self.client.post(ATTEMPTS, self.fire_attempt(), format='json', **AUTH)
            self.assertEqual(res.status_code, 201)
            self.assertEqual(res.json()['result'], 'switched')
            self.assertTrue(res.json()['is_live'])
            fire_purok.clear_cache()
            self.assertEqual(fire_purok.load().version, 'x@new')
            live = self.client.get(DATA + '?hazard=fire', **AUTH).json()['live']
            self.assertEqual(live['version'], 'x@new')
            self.assertEqual(live['family'], 'xgboost')

    def test_post_unreadable_400(self):
        res = self.client.post(ATTEMPTS, self.fire_attempt(months=11), format='json', **AUTH)
        self.assertEqual(res.status_code, 400)
        self.assertIn('detail', res.json())
        self.assertIsNone(model_fits.live_fit('fire'))
        self.assertEqual(ModelFit.objects.count(), 0)

    def test_updates_public_and_bare(self):
        model_fits.record_attempt(self.fire_attempt(), Purok.outlines_version())
        res = self.client.get(UPDATES)
        self.assertEqual(res.status_code, 200)
        self.assertIn('public', res['Cache-Control'])
        updates = res.json()['updates']
        self.assertEqual(len(updates), 1)
        self.assertTrue(updates[0]['is_live'])
        for key in ('model', 'report'):
            self.assertNotIn(key, updates[0])
        self.assertNotIn('POINT', res.content.decode())

    def test_readiness_own_spots(self):
        self.flood_record(self.near, datetime(2025, 6, 1, 9, tzinfo=dt_timezone.utc))
        self.flood_record(self.near, datetime(2025, 6, 2, 9, tzinfo=dt_timezone.utc))
        with flood_model_files(None):
            self.assertEqual(flood_purok.readiness()['own_spots'],
                             {'n': 2, 'barangays': 1, 'needed': 100, 'barangays_needed': 5, 'enough': False})
