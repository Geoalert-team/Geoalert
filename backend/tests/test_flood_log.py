"""
The flood susceptibility log (plan Task 7): one row per purok per published
model version, written only on the writer machine, never changed afterwards
(spec 8.3).
"""
from datetime import date
from io import StringIO

from django.core.management import call_command
from django.db import DatabaseError, transaction
from django.test import TestCase, override_settings

from apps.history.models import FloodPurokSusceptibilityLog
from apps.history.prediction_log import write_flood_rows
from tests.fire_model_file import model_files
from tests.fire_setup import FireSetupMixin
from tests.flood_model_file import VERSION, flood_model_files


class FloodLogTests(FireSetupMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.levels = {self.near: 'Red', self.far: None}

    def test_rows_once_per_version(self):
        with self.settings(HAZARD_LOG_WRITER=True), flood_model_files(self.levels):
            self.assertEqual(write_flood_rows(date(2026, 12, 1)), 2)
            self.assertEqual(write_flood_rows(date(2026, 12, 2)), 0)
        near = FloodPurokSusceptibilityLog.objects.get(purok_id=self.near.id)
        far = FloodPurokSusceptibilityLog.objects.get(purok_id=self.far.id)
        self.assertEqual((near.level, near.model_version, near.source, near.purok_name), ('Red', VERSION, 'model',
                                                                                          'Purok Near'))
        self.assertEqual(near.published_on, date(2026, 12, 1))
        self.assertIsNone(far.level)
        self.assertEqual(far.not_assessed_reason, 'Outside the surveyed floodplain')

    def test_nothing_without_the_writer_setting(self):
        with self.settings(HAZARD_LOG_WRITER=False), flood_model_files(self.levels):
            self.assertEqual(write_flood_rows(date(2026, 12, 1)), 0)
        self.assertFalse(FloodPurokSusceptibilityLog.objects.exists())

    def test_nothing_without_a_model(self):
        with self.settings(HAZARD_LOG_WRITER=True), flood_model_files(None):
            self.assertEqual(write_flood_rows(date(2026, 12, 1)), 0)

    def test_rows_cannot_change(self):
        with self.settings(HAZARD_LOG_WRITER=True), flood_model_files(self.levels):
            write_flood_rows(date(2026, 12, 1))
        row = FloodPurokSusceptibilityLog.objects.get(purok_id=self.near.id)
        with self.assertRaises(DatabaseError), transaction.atomic():
            FloodPurokSusceptibilityLog.objects.filter(pk=row.pk).update(level='Green')
        with self.assertRaises(DatabaseError), transaction.atomic():
            FloodPurokSusceptibilityLog.objects.filter(pk=row.pk).delete()

    @override_settings(HAZARD_LOG_WRITER=True)
    def test_the_command_logs_flood_even_without_a_fire_model(self):
        out = StringIO()
        with flood_model_files(self.levels), model_files(None):
            call_command('log_hazard_predictions', stdout=out)
        self.assertEqual(FloodPurokSusceptibilityLog.objects.count(), 2)
        self.assertIn('Flood susceptibility log', out.getvalue())
