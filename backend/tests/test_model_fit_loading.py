"""The fire and flood loaders read the newer of the live fit and the committed file."""
import json
from datetime import date, datetime, timezone as dt_timezone
from unittest import mock

from django.db import connection, transaction
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from apps.barangays.models import Purok
from apps.history import fire_purok, flood_purok, model_fits, prediction_log
from apps.history.models import FloodPurokSusceptibilityLog, ModelFit
from tests import fire_model_file, flood_model_file
from tests.fire_model_file import model_files
from tests.fire_setup import FireSetupMixin
from tests.flood_model_file import flood_model_files

FIT_BUILT = '2027-02-02T03:00:00+08:00'
FIT_VERSION = 'xgboost@fitfitfitfit'


def assert_no_body_read(test, queries):
    """The recheck looked at the live fit but fetched neither its model nor its report."""
    sql = [q['sql'] for q in queries.captured_queries]
    test.assertTrue(any('"model_fit"' in s for s in sql), sql)
    test.assertEqual([s for s in sql if '"mfit_model"' in s or '"mfit_report"' in s], [])


def break_model_fit_table():
    """The model_fit table missing, as before migration 0012 (undone with the test's transaction)."""
    with connection.cursor() as cursor:
        cursor.execute('ALTER TABLE model_fit RENAME TO model_fit_not_migrated')


def set_file_built_at(path, value):
    doc = json.loads(path.read_text(encoding='utf-8'))
    doc['built_at'] = value
    path.write_text(json.dumps(doc), encoding='utf-8')
    fire_purok.clear_cache()
    flood_purok.clear_cache()


class FireLoadingTests(FireSetupMixin, TestCase):
    def setUp(self):
        super().setUp()
        fire_purok.clear_cache()
        flood_purok.clear_cache()
        self.addCleanup(fire_purok.clear_cache)
        self.addCleanup(flood_purok.clear_cache)

    def make_fit(self, outlines_version=None, built_at=FIT_BUILT, chances=None, months=None):
        doc = fire_model_file.model_document(chances or {self.near: 0.2, self.far: 0.001},
                                             outlines_version=outlines_version)
        doc.update(version=FIT_VERSION, built_at=built_at)
        doc['model'] = {'family': 'logistic', 'settings': {'label': 'fit'}}
        if months is not None:
            doc['areas'][str(self.near.id)]['months'] = doc['areas'][str(self.near.id)]['months'][:months]
        return ModelFit.objects.create(
            hazard='fire', result='switched', reason='r', version=FIT_VERSION, outlines_version=doc['outlines_version'],
            built_at=datetime.fromisoformat(built_at), model=doc, report={**fire_model_file.REPORT, 'version': FIT_VERSION},
            is_live=True)

    def test_fire_uses_a_newer_live_fit(self):
        with model_files({self.near: 0.08}) as path:
            set_file_built_at(path, '2026-11-01T00:00:00+08:00')
            self.make_fit()
            model = fire_purok.load()
        self.assertEqual(model.version, FIT_VERSION)

    def test_fire_file_wins_when_newer(self):
        with model_files({self.near: 0.08}) as path:
            set_file_built_at(path, '2027-03-01T00:00:00+08:00')
            self.make_fit()
            model = fire_purok.load()
        self.assertEqual(model.version, fire_model_file.REPORT['version'])

    def test_fire_file_without_built_at_loses_to_a_fit(self):
        with model_files({self.near: 0.08}):
            self.make_fit()
            model = fire_purok.load()
        self.assertEqual(model.version, FIT_VERSION)

    def test_fit_alone_loads_with_no_file(self):
        with model_files(None):
            self.make_fit()
            model = fire_purok.load()
        self.assertEqual(model.version, FIT_VERSION)

    def test_stale_live_fit_falls_back_to_reason(self):
        with model_files({self.near: 0.08}):
            self.make_fit(outlines_version='some-older-map')
            self.assertEqual(fire_purok.load(), fire_purok.STALE)

    def test_fire_model_keeps_family_and_settings(self):
        with model_files({self.near: 0.08}):
            self.assertEqual(fire_purok.load().model, {'family': 'xgboost', 'settings': {'label': 'pittsburgh'}})
            fire_purok.clear_cache()
            self.make_fit()
            self.assertEqual(fire_purok.load().model, {'family': 'logistic', 'settings': {'label': 'fit'}})

    def test_unreadable_fit_is_refused(self):
        before = self.make_fit()
        doc = fire_model_file.model_document({self.near: 0.2}, outlines_version=Purok.outlines_version())
        doc.update(version='x@bad', built_at='2027-03-03T03:00:00+08:00')
        doc['areas'][str(self.near.id)]['months'] = doc['areas'][str(self.near.id)]['months'][:11]
        attempt = {'hazard': 'fire', 'result': 'switched', 'reason': 'r', 'model': doc,
                   'report': {'version': 'x@bad'}}
        with self.assertRaises(ValueError):
            model_fits.record_attempt(attempt, Purok.outlines_version(), check=model_fits.site_check)
        self.assertEqual(model_fits.live_fit('fire').pk, before.pk)
        self.assertEqual(ModelFit.objects.count(), 1)

    def test_a_recheck_with_the_same_live_fit_reads_no_model_body(self):
        # Final review I2: each recheck reads the live fit's id and time only
        with model_files({self.near: 0.08}):
            self.make_fit()
            self.assertEqual(fire_purok.load().version, FIT_VERSION)
            with mock.patch.object(fire_purok, 'RECHECK_SECONDS', 0), CaptureQueriesContext(connection) as queries:
                self.assertEqual(fire_purok.load().version, FIT_VERSION)
        assert_no_body_read(self, queries)

    def test_make_live_refuses_a_fit_the_site_cannot_read(self):
        unreadable = self.make_fit(months=11)
        unreadable.is_live = False
        unreadable.save()
        current = ModelFit.objects.create(
            hazard='fire', result='switched', reason='r', version='x@2', outlines_version=Purok.outlines_version(),
            built_at=datetime(2027, 3, 3, tzinfo=dt_timezone.utc), model=fire_model_file.model_document({self.near: 0.2}),
            report=None, is_live=True)
        with self.assertRaises(ValueError):
            model_fits.make_live(unreadable, Purok.outlines_version(), check=model_fits.site_check)
        unreadable.refresh_from_db()
        current.refresh_from_db()
        self.assertFalse(unreadable.is_live)
        self.assertTrue(current.is_live)
        self.assertEqual(model_fits.live_fit('fire').pk, current.pk)


class FloodLoadingTests(FireSetupMixin, TestCase):
    def setUp(self):
        super().setUp()
        flood_purok.clear_cache()
        self.addCleanup(flood_purok.clear_cache)

    def geoalert_fit(self, own_spots=120, note=None):
        doc = flood_model_file.model_document({self.near: 'Red', self.far: 'Green'}, source='geoalert')
        doc.update(version='geoalert@fitfitfitfit', built_at='2027-02-02T03:00:00+08:00')
        if note:
            doc['areas'][str(self.near.id)]['note'] = note
        report = {**flood_model_file.REPORT, 'version': doc['version'], 'source': 'geoalert', 'own_spots': own_spots}
        return ModelFit.objects.create(
            hazard='flood', result='switched', reason='r', version=doc['version'],
            outlines_version=doc['outlines_version'], built_at=datetime.fromisoformat(doc['built_at']),
            model=doc, report=report, is_live=True)

    def test_flood_geoalert_source_is_read(self):
        with flood_model_files({self.near: 'Orange'}):
            self.geoalert_fit()
            model = flood_purok.load()
        self.assertEqual(model.source, 'geoalert')
        self.assertEqual(flood_purok.basis(model), flood_purok.BASIS_GEOALERT)

    def test_purok_rows_carry_the_note(self):
        with flood_model_files({self.near: 'Orange'}):
            self.geoalert_fit(note='n1')
            rows = {r['purok_id']: r for r in flood_purok.purok_rows(flood_purok.load())}
        self.assertEqual(rows[self.near.id]['note'], 'n1')
        self.assertIsNone(rows[self.far.id]['note'])

    def test_a_recheck_with_the_same_live_fit_reads_no_model_body(self):
        with flood_model_files({self.near: 'Orange'}):
            fit = self.geoalert_fit()
            self.assertEqual(flood_purok.load().version, fit.version)
            with mock.patch.object(flood_purok, 'RECHECK_SECONDS', 0), CaptureQueriesContext(connection) as queries:
                self.assertEqual(flood_purok.load().version, fit.version)
        assert_no_body_read(self, queries)

    def test_readiness_names_geoalert_records(self):
        with flood_model_files({self.near: 'Orange'}):
            self.geoalert_fit(own_spots=120)
            flood_map = flood_purok.readiness()['flood_map']
        self.assertEqual(flood_map['trained_on'], flood_purok.TRAINED_ON_GEOALERT)
        self.assertEqual(flood_map['source'], 'geoalert')
        self.assertEqual(flood_map['own_spots'], 120)

    def test_readiness_keeps_the_survey_wording_for_the_file(self):
        with flood_model_files({self.near: 'Orange'}):
            flood_map = flood_purok.readiness()['flood_map']
        self.assertEqual(flood_map['trained_on'], flood_purok.TRAINED_ON)
        self.assertEqual(flood_map['source'], 'model')
        self.assertIsNone(flood_map['own_spots'])

    def test_flood_log_takes_a_geoalert_fit(self):
        # Final review I1: the log's source check must allow an own-data fit's rows
        with self.settings(HAZARD_LOG_WRITER=True), flood_model_files({self.near: 'Orange'}):
            fit = self.geoalert_fit()
            self.assertEqual(prediction_log.write_flood_rows(date(2027, 2, 3)), 2)
        rows = FloodPurokSusceptibilityLog.objects.all()
        self.assertEqual({(r.source, r.model_version) for r in rows}, {('geoalert', fit.version)})

    def test_unreadable_flood_fit_is_refused(self):
        before = self.geoalert_fit()
        doc = flood_model_file.model_document({self.near: 'Red'}, source='model')
        doc.update(source='other', version='x@bad', built_at='2027-03-03T03:00:00+08:00')
        attempt = {'hazard': 'flood', 'result': 'switched', 'reason': 'r', 'model': doc,
                   'report': {'version': 'x@bad'}}
        with self.assertRaises(ValueError):
            model_fits.record_attempt(attempt, Purok.outlines_version(), check=model_fits.site_check)
        self.assertEqual(model_fits.live_fit('flood').pk, before.pk)


class LoaderDatabaseErrorTests(FireSetupMixin, TestCase):
    """
    Final review I2: a refused model_fit query (the table not migrated yet,
    say) serves the committed file, and a transaction the caller is in (a
    fire report's approval) stays usable.
    """

    def setUp(self):
        super().setUp()
        fire_purok.clear_cache()
        flood_purok.clear_cache()
        self.addCleanup(fire_purok.clear_cache)
        self.addCleanup(flood_purok.clear_cache)

    def test_fire_serves_the_file(self):
        with model_files({self.near: 0.08}):
            break_model_fit_table()
            with self.assertLogs('apps.history', 'WARNING'):
                model = fire_purok.load()
        self.assertEqual(model.version, fire_model_file.REPORT['version'])

    def test_flood_serves_the_file(self):
        with flood_model_files({self.near: 'Orange'}):
            break_model_fit_table()
            with self.assertLogs('apps.history', 'WARNING'):
                model = flood_purok.load()
        self.assertEqual(model.version, flood_model_file.VERSION)

    def test_fire_keeps_the_callers_transaction_usable(self):
        with model_files({self.near: 0.08}), transaction.atomic():
            break_model_fit_table()
            with self.assertLogs('apps.history', 'WARNING'):
                fire_purok.load()
            self.assertTrue(Purok.objects.filter(pk=self.near.pk).exists())

    def test_flood_keeps_the_callers_transaction_usable(self):
        with flood_model_files({self.near: 'Orange'}), transaction.atomic():
            break_model_fit_table()
            with self.assertLogs('apps.history', 'WARNING'):
                flood_purok.load()
            self.assertTrue(Purok.objects.filter(pk=self.near.pk).exists())
