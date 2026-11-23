"""
The fire purok prediction log (plan Task B6, spec 8.3): each Manila day's
snapshot of every purok's chance for the month, kept unchanged so the model
can be scored on fires that came after each row was issued.
"""
from datetime import date, datetime, timedelta
from io import StringIO
from unittest import mock

from django.core.cache import cache
from django.core.management import call_command
from django.db import DatabaseError, transaction
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.history import prediction_log
from apps.history.models import FirePurokPredictionLog, HistoricalRecord
from tests.fire_model_file import model_files
from tests.fire_setup import FireSetupMixin

SEPT_10 = date(2026, 9, 10)


@override_settings(HAZARD_LOG_WRITER=True)
class FirePurokLogTests(FireSetupMixin, TestCase):
    def setUp(self):
        super().setUp()
        cache.clear()

    def write(self, today=SEPT_10, chances=None):
        with model_files(chances or {self.near: 0.08, self.far: 0.004}):
            return prediction_log.write_month_rows(today)

    def burn(self, purok, when):
        rec = HistoricalRecord.objects.create(barangay=purok.barangay, hazard_type=self.fire, severity_level='Orange',
                                              occurred_at=when)
        rec.puroks.add(purok)

    def test_writes_one_row_per_purok(self):
        self.assertEqual(self.write(), 2)
        row = FirePurokPredictionLog.objects.get(purok_id=self.near.id)
        self.assertEqual((row.purok_name, row.barangay_id, row.period_start, row.issued_on),
                         ('Purok Near', self.home.id, date(2026, 9, 1), SEPT_10))
        self.assertEqual((row.probability, row.level, row.limited_data, row.model_version),
                         (0.08, 'Red', False, 'xgboost@0123456789ab'))

    def test_rerun_adds_nothing(self):
        self.write()
        self.assertEqual(self.write(), 0)
        self.assertEqual(FirePurokPredictionLog.objects.count(), 2)

    def test_next_day_is_a_new_snapshot(self):
        self.write()
        self.assertEqual(self.write(SEPT_10 + timedelta(days=1)), 2)

    @override_settings(HAZARD_LOG_WRITER=False)
    def test_writer_flag_off_writes_nothing(self):
        self.assertEqual(self.write(), 0)
        self.assertFalse(FirePurokPredictionLog.objects.exists())

    def test_nothing_logged_without_a_usable_model(self):
        with model_files(None):
            self.assertEqual(prediction_log.write_month_rows(SEPT_10), 0)
        self.assertFalse(FirePurokPredictionLog.objects.exists())

    def test_rows_are_insert_only(self):
        self.write()
        row = FirePurokPredictionLog.objects.first()
        with self.assertRaises(DatabaseError), transaction.atomic():
            FirePurokPredictionLog.objects.filter(pk=row.pk).update(probability=0.5)
        with self.assertRaises(DatabaseError), transaction.atomic():
            FirePurokPredictionLog.objects.filter(pk=row.pk).delete()
        self.assertEqual(FirePurokPredictionLog.objects.get(pk=row.pk).probability, row.probability)

    def test_purok_reload_keeps_log(self):
        self.write()
        self.near.history.clear()
        self.near.delete()
        self.assertEqual(FirePurokPredictionLog.objects.filter(purok_name='Purok Near').count(), 1)

    def test_prospective_counts_only_later_fires(self):
        self.write()
        tz = timezone.get_current_timezone()
        self.burn(self.near, datetime(2026, 9, 10, 8, 0, tzinfo=tz))  # the issue day: not after the row
        self.burn(self.far, datetime(2026, 9, 11, 8, 0, tzinfo=tz))   # the day after: scored
        self.burn(self.near, datetime(2026, 10, 2, 8, 0, tzinfo=tz))  # another month: no row for it
        summary = prediction_log.prospective_summary(date(2026, 11, 23))
        self.assertEqual((summary['rows'], summary['months'], summary['fires_after']), (2, 1, 1))
        self.assertEqual((summary['first'], summary['last']), ('2026-09', '2026-09'))
        self.assertIn('log_loss', summary['scores'])
        self.assertAlmostEqual(summary['expected'],
                               (1 - 0.92 ** (20 / 30)) + (1 - 0.996 ** (20 / 30)), places=4)

    def test_month_in_progress_is_not_scored(self):
        self.write(date(2026, 11, 3))
        self.assertIsNone(prediction_log.prospective_summary(date(2026, 11, 23)))

    def test_earliest_snapshot_counts(self):
        self.write()
        self.write(SEPT_10 + timedelta(days=5), chances={self.near: 0.5, self.far: 0.5})
        summary = prediction_log.prospective_summary(date(2026, 11, 23))
        self.assertEqual(summary['rows'], 2)
        self.assertLess(summary['expected'], 0.2)

    def test_log_once_today(self):
        with model_files({self.near: 0.08}):
            self.assertTrue(prediction_log.log_once_today(SEPT_10))
            self.assertFalse(prediction_log.log_once_today(SEPT_10))  # already written today
        self.assertEqual(FirePurokPredictionLog.objects.count(), 1)

    def test_background_start_runs_once_a_day(self):
        with mock.patch.object(prediction_log.threading, 'Thread') as thread:
            prediction_log.log_in_background(SEPT_10)
            prediction_log.log_in_background(SEPT_10)
        self.assertEqual(thread.call_count, 1)
        self.assertEqual(thread.call_args.kwargs['args'], (SEPT_10,))

    @override_settings(HAZARD_LOG_WRITER=False)
    def test_background_start_needs_the_writer_flag(self):
        with mock.patch.object(prediction_log.threading, 'Thread') as thread:
            prediction_log.log_in_background(SEPT_10)
        thread.assert_not_called()

    def test_hazard_list_starts_the_daily_log(self):
        with mock.patch.object(prediction_log, 'log_in_background') as start:
            self.client.get('/api/hazards/')
        start.assert_called_once_with(timezone.localdate())

    def test_command(self):
        out = StringIO()
        with model_files({self.near: 0.08}):
            call_command('log_hazard_predictions', stdout=out)
        self.assertIn('1 new rows', out.getvalue())

    def test_command_says_why_nothing_was_logged(self):
        out = StringIO()
        with model_files(None):
            call_command('log_hazard_predictions', stdout=out)
        self.assertIn('The fire model has not been trained yet.', out.getvalue())

    def test_accuracy_entry_has_logged(self):
        self.write()
        with model_files({self.near: 0.08, self.far: 0.004}):
            entry = self.client.get('/api/history/forecast/accuracy/').data['hazards'][0]
        self.assertIn('logged', entry)

    def test_every_column_carries_the_table_prefix(self):
        columns = [f.column for f in FirePurokPredictionLog._meta.concrete_fields]
        self.assertEqual([c for c in columns if not c.startswith('fppl_')], [])
        self.assertFalse(FirePurokPredictionLog._meta.get_field('purok_id').is_relation)  # no key to purok

    def test_migration_matches_model(self):
        out = StringIO()
        call_command('makemigrations', 'history', '--check', '--dry-run', stdout=out)
        self.assertIn('No changes detected', out.getvalue())
