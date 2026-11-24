"""
Serving the fire model (plan Task B5): the forecast's purok rows and barangay
sums from the model file, the stale-map and not-trained cases, the week and
date periods, the training flag, the accuracy card and the purok level used
when a fire report is approved.
"""
import math
from datetime import date

from django.contrib.gis.geos import MultiPolygon
from django.core.cache import cache
from django.db import transaction
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.barangays.models import Purok
from apps.history import fire_purok
from tests.fire_model_file import CUTOFFS, model_files
from tests.fire_setup import FireSetupMixin, box

NOT_TRAINED = 'The fire model has not been trained yet.'
STALE = 'The purok map changed since the fire model was trained; rerun build_fire_features and train_fire_model.'
BEFORE = 'Fire records start in January 2023.'
UNREADABLE = 'The fire model file could not be read; rerun train_fire_model.'


@override_settings(HAZARD_LOG_WRITER=False)
class FirePurokApiTests(FireSetupMixin, TestCase):
    def setUp(self):
        super().setUp()
        cache.clear()
        self.client = APIClient()
        self.third = Purok.objects.create(barangay=self.home, name='Purok Third', kind='purok', source='estimated',
                                          boundary=MultiPolygon(box(200, 200, 300, 300), srid=4326))
        # near is Red, third Orange in June only, far Green
        june = [0.01] * 12
        june[5] = 0.03
        self.chances = {self.near: 0.08, self.third: june, self.far: 0.004}

    def get(self, query=''):
        return self.client.get('/api/history/forecast/' + query)

    def purok_rows(self, data):
        return {r['purok_id']: r for r in data['purok_results']}

    def fire_rows(self, data):
        return {r['barangay_id']: r for r in data['results'] if r['hazard_type'] == 'Fire'}

    def test_rows_from_model(self):
        with model_files(self.chances, limited=[self.third]):
            data = self.get('?month=6').data
        rows = self.purok_rows(data)
        self.assertEqual(set(rows), {self.near.id, self.third.id, self.far.id})
        self.assertEqual((rows[self.near.id]['probability'], rows[self.near.id]['level']), (0.08, 'Red'))
        self.assertEqual((rows[self.third.id]['probability'], rows[self.third.id]['level']), (0.03, 'Orange'))
        self.assertEqual(rows[self.far.id]['level'], 'Green')
        self.assertTrue(rows[self.third.id]['limited_data'])
        self.assertFalse(rows[self.near.id]['limited_data'])
        self.assertEqual(rows[self.near.id]['barangay_id'], self.home.id)
        self.assertEqual(rows[self.near.id]['interval'], [0.04, 0.12])
        self.assertEqual(data['model_hazards'], ['Fire'])
        self.assertEqual(data['unavailable_hazards'], [])
        self.assertIn('City of Pittsburgh', data['basis']['method'])

    def test_barangay_sum(self):
        with model_files(self.chances):
            data = self.get('?month=6').data
        home = self.fire_rows(data)[self.home.id]
        rate = -math.log(1 - 0.08) - math.log(1 - 0.03)
        self.assertEqual(home['method'], 'model')
        self.assertAlmostEqual(home['probability'], round(1 - math.exp(-rate), 3))
        self.assertAlmostEqual(home['expected_events'], round(rate, 2))
        self.assertEqual(home['level'], 'Low')  # about 11%: under the barangay's 15% Moderate line
        self.assertEqual(self.fire_rows(data)[self.next.id]['probability'], round(1 - (1 - 0.004), 3))

    def test_barangay_profile(self):
        with model_files(self.chances):
            data = self.get(f'?month=6&barangay={self.home.id}').data
        self.assertEqual(data['profile_method'], 'model')
        june = data['profile'][5]
        rate = -math.log(1 - 0.08) - math.log(1 - 0.03)
        self.assertAlmostEqual(june['probability'], round(1 - math.exp(-rate), 3))

    def test_week_scales_chance_keeps_month_level(self):
        with model_files(self.chances):
            month = self.get('?month=6&year=2027').data
            week = self.get('?date=2027-06-15').data
        for pid in (self.near.id, self.third.id):
            self.assertLess(self.purok_rows(week)[pid]['probability'], self.purok_rows(month)[pid]['probability'])
            self.assertEqual(self.purok_rows(week)[pid]['level'], self.purok_rows(month)[pid]['level'])
        p = 0.08
        self.assertAlmostEqual(self.purok_rows(week)[self.near.id]['probability'], round(1 - (1 - p) ** (7 / 30), 4))
        self.assertLess(self.fire_rows(week)[self.home.id]['probability'],
                        self.fire_rows(month)[self.home.id]['probability'])
        self.assertEqual(self.fire_rows(week)[self.home.id]['level'], self.fire_rows(month)[self.home.id]['level'])

    def test_stale_outlines_make_fire_unavailable(self):
        with model_files(self.chances):
            self.assertTrue(self.get('?month=6').data['purok_results'])
            # A reload gives the rows a new xmin (a new version of the map); inside a test a savepoint stands in
            with transaction.atomic():
                self.near.name = 'Purok Near Renamed'
                self.near.save()
            fire_purok.clear_cache()
            data = self.get('?month=6').data
        self.assertEqual(data['purok_results'], [])
        for row in self.fire_rows(data).values():
            self.assertEqual((row['method'], row['reason']), ('unavailable', STALE))
        self.assertEqual(data['unavailable_hazards'], ['Fire'])

    def test_missing_file_is_not_trained(self):
        with model_files(None):
            data = self.get('?month=6').data
        self.assertEqual(data['purok_results'], [])
        self.assertTrue(all(r['reason'] == NOT_TRAINED for r in self.fire_rows(data).values()))

    def test_unreadable_file_is_unavailable(self):
        with model_files(self.chances) as path:
            path.write_text('{"version": "x", "areas": {', encoding='utf-8')  # cut short mid-write
            fire_purok.clear_cache()
            data = self.get('?month=6').data
            level = fire_purok.purok_level(self.near.id, date(2027, 6, 1))
            entry = self.client.get('/api/history/forecast/accuracy/').data['hazards'][0]
        self.assertEqual(data['purok_results'], [])
        self.assertTrue(all(r['reason'] == UNREADABLE for r in self.fire_rows(data).values()))
        self.assertIsNone(level)  # so a fire report's approval falls back to Moderate, never fails
        self.assertEqual((entry['status'], entry['reason']), ('unavailable', UNREADABLE))

    def test_unknown_purok_has_no_row(self):
        with model_files({self.near: 0.08, self.far: 0.004}):  # trained without Purok Third
            data = self.get('?month=6').data
        self.assertNotIn(self.third.id, self.purok_rows(data))
        self.assertAlmostEqual(self.fire_rows(data)[self.home.id]['probability'], 0.08)

    def test_before_records_unavailable(self):
        with model_files(self.chances):
            data = self.get('?month=6&year=2022').data
        self.assertEqual(data['purok_results'], [])
        self.assertTrue(all(r['reason'] == BEFORE for r in self.fire_rows(data).values()))

    def test_in_training_flag(self):
        with model_files(self.chances):
            inside = self.get('?month=6&year=2024').data
            after = self.get('?month=6&year=2027').data
            upcoming = self.get('?month=6').data
        self.assertTrue(all(r.get('in_training') for r in self.fire_rows(inside).values()))
        self.assertFalse(any(r.get('in_training') for r in self.fire_rows(after).values()))
        self.assertFalse(any(r.get('in_training') for r in self.fire_rows(upcoming).values()))

    def test_accuracy_reads_report(self):
        with model_files(self.chances):
            entry = self.client.get('/api/history/forecast/accuracy/').data['hazards'][0]
        self.assertEqual((entry['hazard'], entry['kind'], entry['status']), ('Fire', 'fire_purok', 'in_use'))
        self.assertEqual(entry['version'], 'xgboost@0123456789ab')
        self.assertEqual(entry['caveat'], 'test caveat')

    def test_accuracy_without_model(self):
        with model_files(None):
            entry = self.client.get('/api/history/forecast/accuracy/').data['hazards'][0]
        self.assertEqual((entry['status'], entry['reason']), ('unavailable', NOT_TRAINED))


class PurokLevelTests(FireSetupMixin, TestCase):
    def test_purok_level_is_this_months(self):
        march = [0.01] * 12
        march[2] = 0.06
        with model_files({self.near: march}):
            self.assertEqual(fire_purok.purok_level(self.near.id, date(2027, 3, 9)), 'Red')
            self.assertEqual(fire_purok.purok_level(self.near.id, date(2027, 4, 9)), 'Green')
            self.assertIsNone(fire_purok.purok_level(self.far.id, date(2027, 3, 9)))

    def test_no_level_without_a_usable_model(self):
        with model_files(None):
            self.assertIsNone(fire_purok.purok_level(self.near.id, timezone.localdate()))
        with model_files({self.near: 0.08}, outlines_version='an-older-map'):
            self.assertIsNone(fire_purok.purok_level(self.near.id, timezone.localdate()))


class BarangayLevelTests(SimpleTestCase):
    def test_barangay_level_lines(self):
        self.assertEqual([fire_purok.barangay_level(c) for c in (0.149, 0.15, 0.249, 0.25)],
                         ['Low', 'Moderate', 'Moderate', 'High'])

    def test_rows_scale_by_week(self):
        model = fire_purok.FireModel(version='v', areas={1: {'barangay_id': 9, 'limited_data': False, 'months': [
            {'p': 0.1, 'level': 'Red', 'low': 0.05, 'high': 0.2}] * 12}}, cutoffs=CUTOFFS, trained={}, report=None)
        row = fire_purok.purok_rows(model, 4, week_fraction=0.25)[0]
        self.assertAlmostEqual(row['probability'], round(1 - 0.9 ** 0.25, 4))
        self.assertEqual(row['level'], 'Red')
        self.assertEqual(fire_purok.barangay_table(model)[9][3], -math.log(0.9))
