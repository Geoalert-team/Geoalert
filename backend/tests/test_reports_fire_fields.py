"""
A fire report says when the fire started and which purok it is in, or the
name the reporter typed when theirs is not on the list.
"""
from importlib import import_module

from django.db import migrations
from django.test import SimpleTestCase

from apps.reports.serializers import IncidentReportSerializer


class FireReportFieldsTests(SimpleTestCase):
    def test_purok_other_has_a_database_default(self):
        # Code from other branches writes reports to the shared database
        # without this column; Django drops the default after adding it.
        migration = import_module('apps.reports.migrations.0005_fire_report_fields').Migration
        sql = ' '.join(op.sql for op in migration.operations if isinstance(op, migrations.RunSQL))
        self.assertIn("ALTER COLUMN incr_purok_other SET DEFAULT ''", sql)

    def test_report_output_carries_start_time_and_place(self):
        fields = set(IncidentReportSerializer.Meta.fields)
        self.assertTrue({'started_at', 'purok', 'purok_name', 'purok_other'} <= fields)
