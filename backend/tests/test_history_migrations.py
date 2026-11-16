"""
The shared database runs code from more than one branch. A column that older
code doesn't know about must have a database default, or that code's inserts
fail: Django adds a column with its default and then drops the default, so
0003's text columns were left NOT NULL with nothing to fill them.
"""
from importlib import import_module

from django.apps import apps
from django.db.migrations.autodetector import MigrationAutodetector
from django.db.migrations.loader import MigrationLoader
from django.db.migrations.state import ProjectState
from django.test import SimpleTestCase

from apps.history.models import HazardPredictionLog, HistoricalRecord


class BfpColumnDefaultsTests(SimpleTestCase):
    def test_text_columns_older_code_never_sends_have_a_database_default(self):
        migration = import_module('apps.history.migrations.0004_bfp_text_defaults').Migration
        sql = ' '.join(op.sql for op in migration.operations)
        for column in ('hstr_alarm_level', 'hstr_property_category', 'hstr_property_subcategory',
                       'hstr_location_text'):
            self.assertIn(f"ALTER COLUMN {column} SET DEFAULT ''", sql)

    def test_the_location_text_columns_have_a_database_default(self):
        migration = import_module('apps.history.migrations.0006_location').Migration
        sql = ' '.join(op.sql for op in migration.operations if hasattr(op, 'sql'))
        for column in ('hstr_location_precision', 'hstr_location_basis'):
            self.assertIn(f"ALTER COLUMN {column} SET DEFAULT ''", sql)

    def test_the_source_column_has_a_database_default(self):
        migration = import_module('apps.history.migrations.0007_source').Migration
        sql = ' '.join(op.sql for op in migration.operations if hasattr(op, 'sql'))
        self.assertIn("ALTER COLUMN hstr_source SET DEFAULT ''", sql)


class PredictionLogColumnTests(SimpleTestCase):
    def test_every_prediction_log_column_carries_the_table_prefix(self):
        columns = [f.column for f in HazardPredictionLog._meta.concrete_fields]
        self.assertEqual(len(columns), 12)
        self.assertEqual([c for c in columns if not c.startswith('hzpl_')], [])
        # the barangay key is named like the history app's other keys to a barangay
        self.assertEqual(HistoricalRecord._meta.get_field('barangay').column, 'hstr_brgy_id')
        self.assertEqual(HazardPredictionLog._meta.get_field('barangay').column, 'hzpl_brgy_id')

    def test_migration_0008_matches_the_model(self):
        # what makemigrations --check sees, read from the migration files alone (no database)
        loader = MigrationLoader(None, ignore_no_migrations=True)
        changes = MigrationAutodetector(loader.project_state(), ProjectState.from_apps(apps)).changes(
            graph=loader.graph, trim_to_apps={'history'})
        self.assertNotIn('history', changes)
