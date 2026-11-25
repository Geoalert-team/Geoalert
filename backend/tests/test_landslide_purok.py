"""
Serving the landslide susceptibility model (plan Task 8): Landslide in the
forecast API (the same for every period, never monthly), the stale-map,
missing and unreadable cases, the accuracy entry, "since publishing"
monitoring and the own-data constants. No coordinate leaves any of it.
"""
import json
from datetime import datetime, timedelta
from unittest import mock

from django.contrib.gis.geos import Point
from django.core.cache import cache
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient

from apps.hazards.models import HazardType, ZoneFieldMark
from apps.history import flood_purok, landslide_own, landslide_purok
from apps.history.models import HistoricalRecord, ModelFit
from apps.history.views import landslide_accuracy_entry
from tests.fire_model_file import model_files
from tests.fire_setup import FireSetupMixin
from tests.flood_model_file import flood_model_files
from tests.landslide_model_file import REPORT as LANDSLIDE_REPORT
from tests.landslide_model_file import VERSION, landslide_model_files
from tests.landslide_model_file import model_document as landslide_model_document

NOT_TRAINED = 'The landslide model has not been trained yet.'
STALE = ('The purok map changed since the landslide model was trained; rerun build_landslide_features and '
         'train_landslide_model.')
UNREADABLE = 'The landslide model file could not be read; rerun train_landslide_model.'
REPORT_MISSING = "The landslide model's report is missing; rerun train_landslide_model."
NOT_BY_MONTH = 'Landslide susceptibility does not change by month.'
SUSCEPTIBILITY_NOT_BY_MONTH = 'Flood and landslide susceptibility do not change by month.'
FORECAST_ONLY = 'Only fire, flood and landslide have prediction models.'
BASIS_MODEL = ('From a machine-learning model of where landslides started after Philippine typhoons (mapped from '
               "satellite images), applied to Talisay's terrain, land cover and roads. It shows how prone an area is "
               'to sliding, not whether a landslide is coming, and it is the same in every month.')
BASIS_NOAH = ("From UP NOAH's landslide hazard map, classed by where landslides started after Philippine typhoons. "
              'It shows how prone an area is to sliding, not whether a landslide is coming, and it is the same in '
              'every month.')
BASIS_GEOALERT = ('From a machine-learning model of where landslides started after Philippine typhoons and in '
                  "GeoAlert's own located landslide records, applied to Talisay's terrain, land cover and roads. It "
                  'shows how prone an area is to sliding, not whether a landslide is coming, and it is the same in '
                  'every month.')


class LandslideSetup(FireSetupMixin):
    def setUp(self):
        super().setUp()
        cache.clear()
        self.client = APIClient()
        self.landslide = HazardType.objects.create(name='Landslide', logo_class='landslide', is_active=True)
        HistoricalRecord.objects.create(barangay=self.home, hazard_type=self.fire, severity_level='Orange',
                                        occurred_at=timezone.now() - timedelta(days=60))
        self.levels = {self.near: 'Red', self.far: None}

    def get(self, query):
        return self.client.get('/api/history/forecast/' + query)


@override_settings(HAZARD_LOG_WRITER=False)
class LandslideForecastApiTests(LandslideSetup, TestCase):
    def test_landslide_only_request(self):
        with landslide_model_files(self.levels):
            data = self.get('?hazards=Landslide&month=7').data
        self.assertEqual(data['results'], [])
        self.assertEqual(data['purok_results'], [])
        self.assertEqual(data['profile_method'], 'unavailable')
        self.assertEqual(data['profile_reason'], NOT_BY_MONTH)
        self.assertEqual(data['hazard_type'], 'Landslide')
        self.assertTrue(data['landslide']['available'])
        self.assertFalse(data['landslide']['varies_by_month'])
        self.assertEqual(data['landslide']['source'], 'model')
        self.assertEqual(data['basis']['method'], BASIS_MODEL)
        self.assertNotIn('flood_results', data)
        rows = {r['purok_id']: r for r in data['landslide_results']}
        self.assertEqual(set(rows), {self.near.id, self.far.id})
        self.assertEqual(rows[self.near.id]['level'], 'Red')
        self.assertIsNone(rows[self.far.id]['level'])
        self.assertEqual(rows[self.far.id]['not_assessed_reason'], 'No buildings or roads in this area')

    def test_flood_and_landslide_without_fire(self):
        with landslide_model_files(self.levels), flood_model_files({self.near: 'Green'}):
            data = self.get('?hazards=Flood,Landslide').data
        self.assertEqual(data['profile_reason'], SUSCEPTIBILITY_NOT_BY_MONTH)
        self.assertEqual(data['results'], [])
        self.assertIn('flood_results', data)
        self.assertIn('landslide_results', data)
        self.assertEqual(data['basis']['method'], flood_purok.BASIS_MODEL)

    def test_flood_alone_keeps_its_own_reason(self):
        with flood_model_files({self.near: 'Green'}):
            data = self.get('?hazards=Flood').data
        self.assertEqual(data['profile_reason'], 'Flood susceptibility does not change by month.')
        self.assertNotIn('landslide', data)

    def test_landslide_is_the_same_for_every_period(self):
        with landslide_model_files(self.levels), model_files(None):
            a = self.get('?hazards=Fire,Landslide&month=1').data['landslide_results']
            b = self.get('?hazards=Fire,Landslide&date=2027-11-15').data['landslide_results']
            c = self.get('?hazards=Fire,Landslide&month=7&year=2022').data['landslide_results']
        self.assertEqual(a, b)
        self.assertEqual(a, c)
        self.assertTrue(a)

    def test_stale_outlines_make_landslide_unavailable_only(self):
        with landslide_model_files(self.levels, outlines_version='old'), flood_model_files({self.near: 'Red'}):
            data = self.get('?hazards=Fire,Flood,Landslide').data
        self.assertEqual((data['landslide']['available'], data['landslide']['reason']), (False, STALE))
        self.assertEqual(data['landslide_results'], [])
        self.assertNotEqual(data['results'], [])
        self.assertTrue(data['flood']['available'])
        self.assertNotEqual(data['flood_results'], [])

    def test_missing_and_unreadable_files(self):
        with landslide_model_files(None):
            self.assertEqual(self.get('?hazards=Landslide').data['landslide']['reason'], NOT_TRAINED)
        with landslide_model_files(self.levels) as path:
            path.write_text('{"version": ', encoding='utf-8')
            landslide_purok.clear_cache()
            self.assertEqual(self.get('?hazards=Landslide').data['landslide']['reason'], UNREADABLE)

    def test_unknown_names_are_refused_and_no_names_still_means_fire(self):
        r = self.get('?hazards=Tsunami')
        self.assertEqual((r.status_code, r.data['error']), (400, FORECAST_ONLY))
        data = self.get('').data
        self.assertNotIn('landslide_results', data)
        self.assertNotIn('landslide', data)

    def test_accuracy_lists_fire_flood_landslide(self):
        with landslide_model_files(self.levels), model_files(None):
            hazards = self.get('accuracy/').data['hazards']
        self.assertEqual([h['kind'] for h in hazards], ['fire_purok', 'flood_purok', 'landslide_purok'])
        self.assertEqual(hazards[2]['status'], 'in_use')
        self.assertEqual(hazards[2]['since_publishing']['n'], 0)

    def test_report_missing_keeps_the_forecast(self):
        with landslide_model_files(self.levels, report=False):
            entry = landslide_accuracy_entry()
            self.assertEqual((entry['status'], entry['reason']), ('unavailable', REPORT_MISSING))
            self.assertTrue(self.get('?hazards=Landslide').data['landslide']['available'])

    def test_accuracy_entry_carries_the_basis(self):
        for source, text in (('model', BASIS_MODEL), ('noah', BASIS_NOAH), ('geoalert', BASIS_GEOALERT)):
            with landslide_model_files(self.levels, source=source):
                entry = landslide_accuracy_entry()
                self.assertEqual(entry['basis'], landslide_purok.basis(landslide_purok.load()))
                self.assertEqual(entry['basis'], text)
        with landslide_model_files(None):
            self.assertNotIn('basis', landslide_accuracy_entry())

    def test_unavailable_accuracy_entry(self):
        with landslide_model_files(None):
            entry = landslide_accuracy_entry()
        self.assertEqual(entry, {'hazard': 'Landslide', 'kind': 'landslide_purok', 'status': 'unavailable',
                                 'reason': NOT_TRAINED})


@override_settings(HAZARD_LOG_WRITER=False)
class LandslideModuleTests(LandslideSetup, TestCase):
    def test_basis_by_source(self):
        for source, text in (('model', BASIS_MODEL), ('noah', BASIS_NOAH), ('geoalert', BASIS_GEOALERT)):
            with landslide_model_files(self.levels, source=source):
                model = landslide_purok.load()
                self.assertEqual(landslide_purok.basis(model), text)
                self.assertEqual(landslide_purok.landslide_block(model)['basis'], text)

    def test_purok_rows_and_load_cache(self):
        with landslide_model_files(self.levels, uncertain={self.near}, estimated={self.far}):
            model = landslide_purok.load()
            self.assertIs(landslide_purok.load(), model)
            rows = {r['purok_id']: r for r in landslide_purok.purok_rows(model)}
        self.assertEqual(set(rows[self.near.id]), {'purok_id', 'barangay_id', 'level', 'uncertain',
                                                   'not_assessed_reason', 'estimated_outline'})
        self.assertTrue(rows[self.near.id]['uncertain'])
        self.assertTrue(rows[self.far.id]['estimated_outline'])

    def test_a_bad_level_is_unreadable(self):
        with landslide_model_files(self.levels) as path:
            doc = json.loads(path.read_text(encoding='utf-8'))
            doc['areas'][str(self.near.id)]['level'] = 'Purple'
            path.write_text(json.dumps(doc), encoding='utf-8')
            landslide_purok.clear_cache()
            self.assertEqual(landslide_purok.load(), UNREADABLE)

    def test_block_without_a_model(self):
        self.assertEqual(landslide_purok.landslide_block(STALE),
                         {'available': False, 'reason': STALE, 'source': None, 'model_version': None,
                          'built_at': None, 'basis': None, 'varies_by_month': False})

    def test_located_functions_only_see_landslide(self):
        when = timezone.datetime(2026, 11, 25, 6, tzinfo=timezone.get_current_timezone())
        HistoricalRecord.objects.create(barangay=self.home, hazard_type=self.landslide, severity_level='Orange',
                                        occurred_at=when, location=self.near.boundary.point_on_surface)
        HistoricalRecord.objects.create(barangay=self.home, hazard_type=self.flood, severity_level='Orange',
                                        occurred_at=when, location=self.near.boundary.point_on_surface)
        self.assertEqual(len(landslide_purok.located_landslides()), 1)
        self.assertEqual(len(landslide_purok.located_spots()), 1)
        self.assertEqual(len(flood_purok.located_floods()), 1)
        self.assertEqual(len(flood_purok.located_spots()), 1)

    def test_since_publishing_checks_the_published_class(self):
        after = timezone.datetime(2026, 11, 25, 6, tzinfo=timezone.get_current_timezone())
        HistoricalRecord.objects.create(barangay=self.home, hazard_type=self.landslide, severity_level='Orange',
                                        occurred_at=after, location=self.near.boundary.point_on_surface)
        HistoricalRecord.objects.create(barangay=self.next, hazard_type=self.landslide, severity_level='Orange',
                                        occurred_at=after - timedelta(days=400),
                                        location=self.far.boundary.point_on_surface)
        zone = self.zone(self.far, hazard_type=self.landslide)
        ZoneFieldMark.objects.create(zone=zone, kind='Affected', created_by=self.officer,
                                     location=Point(*self.far.boundary.point_on_surface, srid=4326))
        with landslide_model_files({self.near: 'Red', self.far: 'Green'}):
            summary = landslide_purok.since_publishing(landslide_purok.load())
        self.assertEqual(summary['n'], 2)
        self.assertEqual(summary['in_red_orange'], 1)
        self.assertEqual([m['purok'] for m in summary['misses']], ['Purok Far'])
        self.assertFalse(summary['under_review'])

    def test_a_file_missing_a_key_the_site_reads_is_unreadable(self):
        for where, key in (('area', 'barangay_id'), ('area', 'uncertain'), ('area', 'estimated_outline'),
                           ('top', 'built_at')):
            with self.subTest(key=key), landslide_model_files(self.levels) as path:
                doc = json.loads(path.read_text(encoding='utf-8'))
                del (doc['areas'][str(self.near.id)] if where == 'area' else doc)[key]
                path.write_text(json.dumps(doc), encoding='utf-8')
                landslide_purok.clear_cache()
                self.assertEqual(landslide_purok.load(), UNREADABLE)
                self.assertEqual(self.get('?hazards=Landslide').data['landslide']['reason'], UNREADABLE)

    def test_a_flood_zone_mark_is_not_a_located_landslide(self):
        zone = self.zone(self.far, hazard_type=self.flood)
        ZoneFieldMark.objects.create(zone=zone, kind='Affected', created_by=self.officer,
                                     location=Point(*self.far.boundary.point_on_surface, srid=4326))
        self.assertEqual(landslide_purok.located_landslides(), [])
        self.assertEqual(landslide_purok.located_spots(), [])
        self.assertEqual(len(flood_purok.located_floods()), 1)
        with landslide_model_files(self.levels):
            summary = landslide_purok.since_publishing(landslide_purok.load())
        self.assertEqual((summary['n'], summary['misses']), (0, []))

    def test_ten_landslides_mostly_in_green_put_it_under_review(self):
        first = timezone.datetime(2026, 11, 10, 6, tzinfo=timezone.get_current_timezone())
        for i in range(10):
            HistoricalRecord.objects.create(barangay=self.home, hazard_type=self.landslide, severity_level='Orange',
                                            occurred_at=first + timedelta(hours=i),
                                            location=self.far.boundary.point_on_surface)
            with landslide_model_files({self.near: 'Red', self.far: 'Green'}):
                summary = landslide_purok.since_publishing(landslide_purok.load())
            self.assertEqual(summary['n'], i + 1)
            self.assertEqual(summary['under_review'], i + 1 >= 10)
        self.assertEqual(len(summary['misses']), 10)

    def test_readiness_line_counts_only(self):
        when = timezone.datetime(2026, 11, 25, 6, tzinfo=timezone.get_current_timezone())
        HistoricalRecord.objects.create(barangay=self.home, hazard_type=self.landslide, severity_level='Orange',
                                        occurred_at=when, location=self.near.boundary.point_on_surface)
        self.assertEqual(landslide_purok.readiness_line(),
                         {'n': 1, 'barangays': 1, 'needed': 30, 'barangays_needed': 3, 'enough': False})


@override_settings(HAZARD_LOG_WRITER=False)
class LandslideLiveFitTests(LandslideSetup, TestCase):
    """
    The newer of the live landslide fit (the January job's, history 0014) and
    the committed file is served (carried from Task 8's review).
    """

    def live_fit(self, built_at='2027-02-02T03:00:00+08:00', outlines_version=None, version='neural_network@own'):
        doc = landslide_model_document({self.near: 'Orange', self.far: 'Green'}, source='geoalert',
                                       outlines_version=outlines_version)
        doc.update(version=version, built_at=built_at)
        return ModelFit.objects.create(
            hazard='landslide', result='switched', reason='r', version=version,
            outlines_version=doc['outlines_version'], built_at=datetime.fromisoformat(built_at), model=doc,
            report={**LANDSLIDE_REPORT, 'version': version, 'source': 'geoalert'}, is_live=True)

    def test_a_newer_live_fit_beats_the_file(self):
        with landslide_model_files(self.levels):  # the file was built on 2026-11-01
            fit = self.live_fit()
            model = landslide_purok.load()
        self.assertEqual((model.version, model.source), (fit.version, 'geoalert'))
        self.assertEqual(model.areas[self.near.id]['level'], 'Orange')
        self.assertEqual(model.report['version'], fit.version)
        self.assertEqual(landslide_purok.basis(model), BASIS_GEOALERT)

    def test_the_file_wins_when_it_is_newer(self):
        with landslide_model_files(self.levels):
            self.live_fit(built_at='2026-10-01T03:00:00+08:00')
            model = landslide_purok.load()
        self.assertEqual((model.version, model.source), (VERSION, 'model'))
        self.assertEqual(model.areas[self.near.id]['level'], 'Red')

    def test_a_live_fit_alone_loads_with_no_file(self):
        with landslide_model_files(None):
            fit = self.live_fit()
            self.assertEqual(landslide_purok.load().version, fit.version)
            self.assertTrue(self.get('?hazards=Landslide').data['landslide']['available'])

    def test_a_stale_live_fit_gives_the_stale_reason(self):
        with landslide_model_files(self.levels):
            self.live_fit(outlines_version='an-older-map')
            self.assertEqual(landslide_purok.load(), STALE)

    def test_a_recheck_with_the_same_live_fit_reads_no_model_body(self):
        with landslide_model_files(self.levels):
            fit = self.live_fit()
            self.assertEqual(landslide_purok.load().version, fit.version)
            with mock.patch.object(landslide_purok, 'RECHECK_SECONDS', 0), \
                    CaptureQueriesContext(connection) as queries:
                self.assertEqual(landslide_purok.load().version, fit.version)
        sql = [q['sql'] for q in queries.captured_queries]
        self.assertTrue(any('"model_fit"' in s for s in sql), sql)
        self.assertEqual([s for s in sql if '"mfit_model"' in s or '"mfit_report"' in s], [])


class LandslideOwnTests(TestCase):
    def test_constants_and_sentences(self):
        self.assertEqual((landslide_own.OWN_MIN_SPOTS, landslide_own.OWN_MIN_BARANGAYS, landslide_own.HELD_MIN,
                          landslide_own.OWN_WEIGHT), (30, 3, 5, 10))
        self.assertEqual(landslide_own.LANDSLIDE_FLOOR.format(n=4, b=2),
                         '4 of 30 located landslide spots, 2 of 3 barangays')
        self.assertEqual(landslide_own.LANDSLIDE_HELD.format(n=2),
                         'Too few new spots to test (2 of 5); tries again next January')
        self.assertEqual(landslide_own.LANDSLIDE_WORSE.format(season=2026, new=1, live=3),
                         "Fewer of the 2026 wet season's spots in Red or Orange than the map in use (1 vs 3)")
        self.assertEqual(landslide_own.LANDSLIDE_SWITCHED.format(hits=4, n=5),
                         'Passed all four checks; 4 of 5 held-back spots in Red or Orange')

    def test_floor(self):
        spots = [{'barangay': 'A'}] * 20 + [{'barangay': 'B'}] * 9 + [{'barangay': 'C'}]
        self.assertEqual(landslide_own.floor(spots), {'n': 30, 'barangays': 3, 'enough': True})
        self.assertEqual(landslide_own.floor(spots[:29]), {'n': 29, 'barangays': 2, 'enough': False})
        self.assertFalse(landslide_own.floor([{'barangay': 'A'}] * 30)['enough'])
        self.assertEqual(landslide_own.floor([]), {'n': 0, 'barangays': 0, 'enough': False})
