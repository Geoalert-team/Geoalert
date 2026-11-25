"""
The landslide susceptibility log (Task 9): one row per purok per published
model version, written only on the writer machine, never changed afterwards.
"""
from datetime import date
from io import StringIO

from django.core.management import call_command
from django.db import DatabaseError, transaction
from django.test import TestCase, override_settings

from apps.history.models import FloodPurokSusceptibilityLog, LandslidePurokSusceptibilityLog
from apps.history.prediction_log import write_landslide_rows
from tests.fire_model_file import model_files
from tests.fire_setup import FireSetupMixin
from tests.flood_model_file import flood_model_files
from tests.landslide_model_file import VERSION, landslide_model_files


class LandslideLogTests(FireSetupMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.levels = {self.near: 'Red', self.far: None}

    def test_rows_once_per_version(self):
        with self.settings(HAZARD_LOG_WRITER=True), landslide_model_files(self.levels):
            self.assertEqual(write_landslide_rows(date(2026, 12, 1)), 2)
            self.assertEqual(write_landslide_rows(date(2026, 12, 2)), 0)
        near = LandslidePurokSusceptibilityLog.objects.get(purok_id=self.near.id)
        far = LandslidePurokSusceptibilityLog.objects.get(purok_id=self.far.id)
        self.assertEqual((near.level, near.model_version, near.source, near.purok_name),
                         ('Red', VERSION, 'model', 'Purok Near'))
        self.assertEqual(near.published_on, date(2026, 12, 1))
        self.assertEqual(near.score, 0.9)
        self.assertTrue(near.outlines_version)
        self.assertIsNone(far.level)
        self.assertEqual(far.not_assessed_reason, 'No buildings or roads in this area')

    def test_nothing_without_the_writer_setting(self):
        with self.settings(HAZARD_LOG_WRITER=False), landslide_model_files(self.levels):
            self.assertEqual(write_landslide_rows(date(2026, 12, 1)), 0)
        self.assertFalse(LandslidePurokSusceptibilityLog.objects.exists())

    def test_nothing_without_a_model(self):
        with self.settings(HAZARD_LOG_WRITER=True), landslide_model_files(None):
            self.assertEqual(write_landslide_rows(date(2026, 12, 1)), 0)

    def test_rows_cannot_change(self):
        with self.settings(HAZARD_LOG_WRITER=True), landslide_model_files(self.levels):
            write_landslide_rows(date(2026, 12, 1))
        row = LandslidePurokSusceptibilityLog.objects.get(purok_id=self.near.id)
        with self.assertRaises(DatabaseError), transaction.atomic():
            LandslidePurokSusceptibilityLog.objects.filter(pk=row.pk).update(level='Green')
        with self.assertRaises(DatabaseError), transaction.atomic():
            LandslidePurokSusceptibilityLog.objects.filter(pk=row.pk).delete()

    def test_an_unknown_source_is_refused(self):
        with self.assertRaises(DatabaseError), transaction.atomic():
            LandslidePurokSusceptibilityLog.objects.create(
                purok_id=self.near.id, purok_name='x', barangay_id=self.near.barangay_id, model_version='v',
                source='mystery', uncertain=False, outlines_version='o', published_on=date(2026, 12, 1))

    @override_settings(HAZARD_LOG_WRITER=True)
    def test_the_command_logs_landslide_even_without_fire_or_flood_models(self):
        out = StringIO()
        with landslide_model_files(self.levels), model_files(None), flood_model_files(None):
            call_command('log_hazard_predictions', stdout=out)
        self.assertEqual(LandslidePurokSusceptibilityLog.objects.count(), 2)
        self.assertIn('Landslide susceptibility log', out.getvalue())

    @override_settings(HAZARD_LOG_WRITER=True)
    def test_a_missing_landslide_model_never_stops_flood(self):
        out = StringIO()
        with landslide_model_files(None), flood_model_files(self.levels), model_files(None):
            call_command('log_hazard_predictions', stdout=out)
        self.assertEqual(FloodPurokSusceptibilityLog.objects.count(), 2)
        self.assertFalse(LandslidePurokSusceptibilityLog.objects.exists())
        self.assertIn('Landslide: nothing was logged', out.getvalue())

    # Final review B5: a missing table names the migration that makes it (fire 0010, flood 0011, landslide 0013)
    def test_a_missing_table_names_its_own_migration(self):
        from django.db import ProgrammingError

        from apps.history import prediction_log

        missing = ProgrammingError('relation "x" does not exist')
        self.assertEqual(prediction_log.write_failure(missing),  # fire's words, exactly as before
                         'The fire purok log was not written (is migration history 0010 applied?): '
                         'relation "x" does not exist')
        self.assertEqual(prediction_log.write_failure(missing, 'fire'), prediction_log.write_failure(missing))
        self.assertEqual(prediction_log.write_failure(missing, 'flood'),
                         'The flood susceptibility log was not written (is migration history 0011 applied?): '
                         'relation "x" does not exist')
        self.assertEqual(prediction_log.write_failure(missing, 'landslide'),
                         'The landslide susceptibility log was not written (is migration history 0013 applied?): '
                         'relation "x" does not exist')
        refused = DatabaseError('permission denied')
        self.assertEqual(prediction_log.write_failure(refused, 'landslide'),
                         'The landslide susceptibility log was not written (the database refused it): '
                         'permission denied')

    @override_settings(HAZARD_LOG_WRITER=True)
    def test_the_command_and_the_daily_log_name_the_landslide_migration(self):
        from unittest import mock

        from django.core.cache import cache
        from django.core.management.base import CommandError
        from django.db import ProgrammingError

        from apps.history import prediction_log

        missing = ProgrammingError('relation "history_landslidepuroksusceptibilitylog" does not exist')
        with landslide_model_files(self.levels), model_files(None), flood_model_files(None), \
                mock.patch.object(prediction_log, 'write_landslide_rows', side_effect=missing):
            with self.assertRaises(CommandError) as caught:
                call_command('log_hazard_predictions', stdout=StringIO())
            self.assertIn('landslide susceptibility log was not written (is migration history 0013 applied?)',
                          str(caught.exception))
            cache.clear()
            with self.assertLogs('apps.history.prediction_log', 'WARNING') as logs:
                self.assertFalse(prediction_log.log_once_today(date(2026, 12, 1)))
            self.assertIn('is migration history 0013 applied?', logs.output[0])

    @override_settings(HAZARD_LOG_WRITER=True)
    def test_a_failed_flood_write_names_flood_not_the_next_log(self):
        from unittest import mock

        from django.core.cache import cache
        from django.core.management.base import CommandError
        from django.db import ProgrammingError

        from apps.history import prediction_log

        missing = ProgrammingError('relation "history_floodpuroksusceptibilitylog" does not exist')
        flood_words = 'The flood susceptibility log was not written (is migration history 0011 applied?)'
        with landslide_model_files(self.levels), flood_model_files(self.levels), model_files(None), \
                mock.patch.object(prediction_log, 'write_flood_rows', side_effect=missing), \
                mock.patch.object(prediction_log, 'write_landslide_rows', return_value=0) as landslide:
            with self.assertRaises(CommandError) as caught:
                call_command('log_hazard_predictions', stdout=StringIO())
            self.assertIn(flood_words, str(caught.exception))
            cache.clear()
            with self.assertLogs('apps.history.prediction_log', 'WARNING') as logs:
                self.assertFalse(prediction_log.log_once_today(date(2026, 12, 1)))
            self.assertIn(flood_words, logs.output[0])
        landslide.assert_not_called()  # the flood failure stopped both before the landslide log
