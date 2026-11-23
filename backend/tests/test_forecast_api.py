"""
GET /api/history/forecast/ and /api/history/forecast/accuracy/ after the
clean-up (plan Task A2): fire is the only hazard with a prediction model, and
until train_fire_model has run its rows say the model is not trained yet.
"""
from datetime import timedelta

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.history.models import HistoricalRecord
from tests.fire_model_file import model_files
from tests.fire_setup import FireSetupMixin

NOT_TRAINED = 'The fire model has not been trained yet.'
FIRE_ONLY = 'Only fire has a prediction model for now.'


@override_settings(HAZARD_LOG_WRITER=False)
class ForecastApiTests(FireSetupMixin, TestCase):
    def setUp(self):
        super().setUp()
        cache.clear()
        self.client = APIClient()
        HistoricalRecord.objects.create(barangay=self.home, hazard_type=self.fire, severity_level='Orange',
                                        occurred_at=timezone.now() - timedelta(days=60))

    def test_default_is_fire_only(self):
        r = self.client.get('/api/history/forecast/')
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.data['results'])
        self.assertEqual({row['hazard_type'] for row in r.data['results']}, {'Fire'})
        self.assertNotIn('combined', r.data)

    def test_flood_is_a_400(self):
        for query in ('?hazards=Flood', '?hazard_type_name=Landslide', '?hazards=Fire,Flood'):
            r = self.client.get('/api/history/forecast/' + query)
            self.assertEqual(r.status_code, 400, query)
            self.assertEqual(r.data['error'], FIRE_ONLY, query)

    def test_fire_any_case_is_accepted(self):
        r = self.client.get('/api/history/forecast/?hazards=fire')
        self.assertEqual(r.status_code, 200)

    def test_fire_is_unavailable_before_training(self):
        with model_files(None):  # no model file, whatever the repo holds
            r = self.client.get('/api/history/forecast/?hazards=Fire')
        self.assertEqual(r.status_code, 200)
        rows = [row for row in r.data['results'] if row['hazard_type'] == 'Fire']
        self.assertTrue(rows)
        for row in rows:
            self.assertEqual(row['method'], 'unavailable')
            self.assertEqual(row['reason'], NOT_TRAINED)
        self.assertEqual(r.data['unavailable_hazards'], ['Fire'])
        self.assertEqual(r.data['purok_results'], [])

    def test_accuracy_has_fire_only(self):
        with model_files(None):
            r = self.client.get('/api/history/forecast/accuracy/')
        self.assertEqual(r.status_code, 200)
        hazards = r.data['hazards']
        self.assertEqual([h['hazard'] for h in hazards], ['Fire'])
        self.assertEqual(hazards[0]['status'], 'unavailable')
        self.assertEqual(hazards[0]['kind'], 'fire_purok')
        self.assertEqual(hazards[0]['reason'], NOT_TRAINED)
