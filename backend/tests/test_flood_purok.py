"""
Serving the flood susceptibility model (plan Task 6): Flood in the forecast
API (the same for every period, never monthly), the stale-map, missing and
unreadable cases, the accuracy card entry and "since publishing" monitoring.
"""
from datetime import timedelta

from django.contrib.gis.geos import Point
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.hazards.models import ZoneFieldMark
from apps.history import flood_purok
from apps.history.models import HistoricalRecord
from apps.history.views import flood_accuracy_entry
from tests.fire_model_file import model_files
from tests.fire_setup import FireSetupMixin
from tests.flood_model_file import flood_model_files

NOT_TRAINED = 'The flood model has not been trained yet.'
STALE = 'The purok map changed since the flood model was trained; rerun build_flood_features and train_flood_model.'
UNREADABLE = 'The flood model file could not be read; rerun train_flood_model.'
REPORT_MISSING = "The flood model's report is missing; rerun train_flood_model."
NOT_BY_MONTH = 'Flood susceptibility does not change by month.'
FORECAST_ONLY = 'Only fire and flood have prediction models for now.'


@override_settings(HAZARD_LOG_WRITER=False)
class FloodForecastApiTests(FireSetupMixin, TestCase):
    def setUp(self):
        super().setUp()
        cache.clear()
        self.client = APIClient()
        HistoricalRecord.objects.create(barangay=self.home, hazard_type=self.fire, severity_level='Orange',
                                        occurred_at=timezone.now() - timedelta(days=60))
        self.levels = {self.near: 'Red', self.far: None}

    def get(self, query):
        return self.client.get('/api/history/forecast/' + query)

    def test_flood_only_request(self):
        with flood_model_files(self.levels):
            data = self.get('?hazards=Flood&month=7').data
        self.assertEqual(data['results'], [])
        self.assertEqual(data['purok_results'], [])
        self.assertEqual(data['profile_method'], 'unavailable')
        self.assertEqual(data['profile_reason'], NOT_BY_MONTH)
        self.assertTrue(data['flood']['available'])
        self.assertFalse(data['flood']['varies_by_month'])
        self.assertEqual(data['flood']['source'], 'model')
        rows = {r['purok_id']: r for r in data['flood_results']}
        self.assertEqual(set(rows), {self.near.id, self.far.id})
        self.assertEqual(rows[self.near.id]['level'], 'Red')
        self.assertIsNone(rows[self.far.id]['level'])
        self.assertEqual(rows[self.far.id]['not_assessed_reason'], 'Outside the surveyed floodplain')

    def test_flood_is_the_same_for_every_period(self):
        with flood_model_files(self.levels), model_files(None):
            a = self.get('?hazards=Fire,Flood&month=1').data['flood_results']
            b = self.get('?hazards=Fire,Flood&month=7&year=2022').data['flood_results']
            c = self.get('?hazards=Fire,Flood&date=2027-11-15').data['flood_results']
        self.assertEqual(a, b)
        self.assertEqual(a, c)
        self.assertTrue(a)

    def test_stale_outlines_make_flood_unavailable_not_fire(self):
        with flood_model_files(self.levels, outlines_version='old'):
            data = self.get('?hazards=Fire,Flood').data
        self.assertFalse(data['flood']['available'])
        self.assertEqual(data['flood']['reason'], STALE)
        self.assertEqual(data['flood_results'], [])
        self.assertNotEqual(data['results'], [])  # fire rows still there

    def test_missing_and_unreadable_files(self):
        with flood_model_files(None):
            self.assertEqual(self.get('?hazards=Flood').data['flood']['reason'], NOT_TRAINED)
        with flood_model_files(self.levels) as path:
            path.write_text('{"version": ', encoding='utf-8')
            flood_purok.clear_cache()
            self.assertEqual(self.get('?hazards=Flood').data['flood']['reason'], UNREADABLE)

    def test_other_names_are_refused_and_no_names_still_means_fire(self):
        r = self.get('?hazards=Landslide')
        self.assertEqual((r.status_code, r.data['error']), (400, FORECAST_ONLY))
        data = self.get('').data
        self.assertNotIn('flood_results', data)
        self.assertNotIn('flood', data)
        self.assertEqual({row['hazard_type'] for row in data['results']}, {'Fire'})

    def test_accuracy_lists_fire_then_flood(self):
        with flood_model_files(self.levels), model_files(None):
            hazards = self.client.get('/api/history/forecast/accuracy/').data['hazards']
        self.assertEqual([h['kind'] for h in hazards], ['fire_purok', 'flood_purok'])
        self.assertEqual(hazards[1]['status'], 'in_use')
        self.assertEqual(hazards[1]['since_publishing']['n'], 0)

    def test_report_missing_keeps_the_forecast(self):
        with flood_model_files(self.levels, report=False):
            self.assertEqual(flood_accuracy_entry()['reason'], REPORT_MISSING)
            self.assertTrue(self.get('?hazards=Flood').data['flood']['available'])


@override_settings(HAZARD_LOG_WRITER=False)
class SincePublishingTests(FireSetupMixin, TestCase):
    def test_new_located_floods_are_checked_against_the_published_class(self):
        after = timezone.datetime(2026, 11, 25, 6, 0, tzinfo=timezone.get_current_timezone())
        rec = HistoricalRecord.objects.create(barangay=self.home, hazard_type=self.flood, severity_level='Orange',
                                              occurred_at=after,
                                              location=self.near.boundary.point_on_surface)
        old = HistoricalRecord.objects.create(barangay=self.next, hazard_type=self.flood, severity_level='Orange',
                                              occurred_at=after - timedelta(days=400),
                                              location=self.far.boundary.point_on_surface)
        zone = self.zone(self.far, hazard_type=self.flood)
        ZoneFieldMark.objects.create(zone=zone, kind='Affected', location=Point(*self.far.boundary.point_on_surface,
                                                                                    srid=4326), created_by=self.officer)
        with flood_model_files({self.near: 'Red', self.far: 'Green'}):
            model = flood_purok.load()
            summary = flood_purok.since_publishing(model)
        self.assertEqual(summary['n'], 2)  # the old record predates the model
        self.assertEqual(summary['in_red_orange'], 1)
        self.assertEqual([m['purok'] for m in summary['misses']], ['Purok Far'])
        self.assertFalse(summary['under_review'])
        self.assertIsNotNone(rec.pk)
        self.assertIsNotNone(old.pk)
