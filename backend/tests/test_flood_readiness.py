"""
Flood data readiness (the "Predictive models" tab): located flood days on
record against what flood forecasting needs, and new located floods since the
flood map was published against the review threshold. It only counts; it
never changes a prediction, and it shows no location.
"""
import json
from datetime import datetime, timedelta

from django.contrib.gis.geos import Point
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.hazards.models import HazardType, ZoneFieldMark
from apps.history import flood_purok
from apps.history.models import HistoricalRecord
from tests.fire_setup import FireSetupMixin
from tests.flood_model_file import flood_model_files

NOT_TRAINED = 'The flood model has not been trained yet.'
STALE = 'The purok map changed since the flood model was trained; rerun build_flood_features and train_flood_model.'
URL = '/api/history/forecast/readiness/'


@override_settings(HAZARD_LOG_WRITER=False)
class FloodReadinessTests(FireSetupMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.landslide = HazardType.objects.create(name='Landslide', logo_class='landslide', is_active=True)
        self.tz = timezone.get_current_timezone()
        self.day1, self.day2, self.day3, self.day4, self.day5 = (
            datetime(2025, 6, d, 9, tzinfo=self.tz) for d in (1, 2, 3, 4, 5))

    def record(self, hazard_type, purok, when, location=True):
        return HistoricalRecord.objects.create(
            barangay=purok.barangay, hazard_type=hazard_type, severity_level='Orange', occurred_at=when,
            location=purok.boundary.point_on_surface if location else None)

    def flood_at(self, purok, when):
        return self.record(self.flood, purok, when)

    def mark(self, kind, hazard_type=None, on=None):
        """A field mark on a zone (flood by default); `on` moves it to its own day (created_at is auto_now_add)."""
        zone = self.zone(self.far, hazard_type=hazard_type or self.flood)
        mark = ZoneFieldMark.objects.create(zone=zone, kind=kind, created_by=self.officer,
                                            location=Point(*self.far.boundary.point_on_surface, srid=4326))
        if on is not None:
            ZoneFieldMark.objects.filter(pk=mark.pk).update(created_at=on)
        return mark

    def test_days_are_distinct_local_dates(self):
        for when in (datetime(2026, 8, 12, 9, tzinfo=self.tz), datetime(2026, 8, 12, 15, tzinfo=self.tz),  # 1 day
                     datetime(2026, 9, 1, 23, 30, tzinfo=self.tz), datetime(2026, 9, 2, 0, 30, tzinfo=self.tz)):  # 2
            self.flood_at(self.near, when)
        with flood_model_files(None):
            self.assertEqual(flood_purok.readiness()['located_flood_days'], 3)

    def test_only_located_floods_count(self):
        self.flood_at(self.near, self.day1)                             # counted
        self.record(self.fire, self.near, self.day2)                    # fire with a point: no
        self.record(self.landslide, self.near, self.day3)               # landslide: no
        self.record(self.flood, self.near, self.day4, location=False)   # no point, no purok: no
        linked = self.record(self.flood, self.far, self.day5, location=False)
        linked.puroks.add(self.far)                                     # a purok only: counted
        self.mark('Affected')                                           # counted (today)
        # Each on a day of its own, so counting it would show as an extra day
        self.mark('Clear', on=datetime(2025, 6, 6, 9, tzinfo=self.tz))  # "Clear here": no
        self.mark('Affected', hazard_type=self.fire, on=datetime(2025, 6, 7, 9, tzinfo=self.tz))  # fire zone: no
        with flood_model_files(None):
            self.assertEqual(flood_purok.readiness()['located_flood_days'], 3)

    def test_counts_without_a_usable_model(self):
        self.flood_at(self.near, self.day1)
        for files, reason in ((flood_model_files(None), NOT_TRAINED),
                              (flood_model_files({self.near: 'Red'}, outlines_version='old'), STALE)):
            with files:
                r = self.client.get(URL)
                self.assertEqual(r.status_code, 200)
                self.assertEqual(r.data['located_flood_days'], 1)
                self.assertEqual(r.data['flood_map'], {'available': False, 'reason': reason})
                self.assertIsNone(r.data['since_publishing'])
                self.assertFalse(r.data['enough_for_forecasting'])
                self.assertIn('public', r['Cache-Control'])

    def test_since_publishing_and_the_map(self):  # the test model is built 2026-11-01
        self.flood_at(self.near, datetime(2026, 11, 25, 6, tzinfo=self.tz))  # after: in n
        self.flood_at(self.far, datetime(2025, 1, 5, 6, tzinfo=self.tz))     # before: a day, not in n
        with flood_model_files({self.near: 'Red', self.far: 'Green'}):
            r = flood_purok.readiness()
        self.assertEqual(r['located_flood_days'], 2)
        self.assertEqual(r['since_publishing'], {'n': 1, 'review_after': 10, 'under_review': False})
        self.assertEqual(r['forecast_days_needed'], {'min': 20, 'max': 30})
        fm = r['flood_map']
        self.assertTrue(fm['available'])
        self.assertIsNone(fm['reason'])
        self.assertEqual(fm['trained_on'], '2017 UP Mananga flood survey')
        self.assertEqual(fm['survey_spots'], 105)
        self.assertEqual(fm['version'], 'logistic_regression@0123456789ab')
        self.assertEqual(fm['built_at'], '2026-11-01T00:00:00+08:00')

    def test_enough_days_at_the_minimum(self):
        start = datetime(2024, 1, 1, 9, tzinfo=self.tz)
        for i in range(19):
            self.flood_at(self.near, start + timedelta(days=i))
        with flood_model_files(None):
            self.assertFalse(flood_purok.readiness()['enough_for_forecasting'])
            self.flood_at(self.near, start + timedelta(days=19))
            r = flood_purok.readiness()
        self.assertEqual(r['located_flood_days'], 20)
        self.assertTrue(r['enough_for_forecasting'])

    def test_report_missing_leaves_survey_spots_empty(self):
        with flood_model_files({self.near: 'Red'}, report=False):
            fm = flood_purok.readiness()['flood_map']
        self.assertTrue(fm['available'])
        self.assertIsNone(fm['survey_spots'])

    def test_no_location_in_the_response(self):
        self.flood_at(self.near, self.day1)
        self.mark('Affected')
        with flood_model_files({self.near: 'Red'}):
            text = json.dumps(self.client.get(URL).data)
        self.assertNotIn('POINT', text)
        for p in (self.near.boundary.point_on_surface, self.far.boundary.point_on_surface):
            self.assertNotIn(f'{p.x:.4f}', text)
            self.assertNotIn(f'{p.y:.4f}', text)

    def test_landslide_line_counts_located_landslide_spots_and_shows_no_location(self):
        self.record(self.landslide, self.near, self.day1)
        self.record(self.landslide, self.far, self.day2, location=False)  # no map point: not counted
        self.flood_at(self.near, self.day3)                                # flood: not counted
        with flood_model_files(None):
            data = self.client.get(URL).data
        self.assertEqual(data['landslide_spots'],
                         {'n': 1, 'barangays': 1, 'needed': 30, 'barangays_needed': 3, 'enough': False})
        self.assertEqual(data['located_flood_days'], 1)  # flood's own figures are unchanged
        self.assertNotRegex(json.dumps(data), r'\d+\.\d{4}')
