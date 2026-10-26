"""
A fire report says when the fire started and which puroks it is in. The map
shows a pin at each purok's centre.
"""
from importlib import import_module

from django.contrib.gis.geos import MultiPolygon, Polygon
from django.db import migrations
from django.test import SimpleTestCase

from apps.barangays.models import Purok
from apps.reports.serializers import IncidentReportSerializer, ReportPurokSerializer


def square(x0, y0, x1, y1):
    return Polygon(((x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)), srid=4326)


class FireReportFieldsTests(SimpleTestCase):
    def test_purok_other_has_a_database_default(self):
        # Code from other branches writes reports to the shared database
        # without this column; Django drops the default after adding it.
        migration = import_module('apps.reports.migrations.0005_fire_report_fields').Migration
        sql = ' '.join(op.sql for op in migration.operations if isinstance(op, migrations.RunSQL))
        self.assertIn("ALTER COLUMN incr_purok_other SET DEFAULT ''", sql)

    def test_report_output_carries_start_time_and_puroks(self):
        fields = set(IncidentReportSerializer.Meta.fields)
        self.assertTrue({'started_at', 'puroks'} <= fields)
        self.assertFalse({'purok', 'purok_name', 'purok_other'} & fields)

    def test_a_purok_is_shown_with_its_centre(self):
        purok = Purok(id=3, name='Purok Sambag', boundary=MultiPolygon(square(123.85, 10.25, 123.86, 10.26)))
        data = ReportPurokSerializer(purok).data
        self.assertEqual((data['id'], data['name']), (3, 'Purok Sambag'))
        self.assertTrue(10.25 <= data['lat'] <= 10.26 and 123.85 <= data['lng'] <= 123.86)

    def test_old_columns_stay_in_the_database(self):
        # The shared database also serves copies of the app that read them
        ops = import_module('apps.reports.migrations.0006_fire_report_puroks').Migration.operations
        split = [op for op in ops if isinstance(op, migrations.SeparateDatabaseAndState)]
        self.assertEqual(len(split), 1)
        self.assertEqual(split[0].database_operations, [])
        self.assertEqual(sorted(op.name for op in split[0].state_operations), ['purok', 'purok_other'])
        sql = ' '.join(op.sql for op in ops if isinstance(op, migrations.RunSQL))
        self.assertIn('INSERT INTO incident_report_purok', sql)  # round-1 puroks carried over

    def test_deleting_a_purok_or_report_never_trips_a_foreign_key(self):
        # Django no longer manages incr_prk_id, and teammates' copies don't
        # know the link table, so the database itself must clear or cascade
        ops = import_module('apps.reports.migrations.0007_report_purok_on_delete').Migration.operations
        sql = ' '.join(op.sql for op in ops if isinstance(op, migrations.RunSQL))
        for column, target, rule in (('incr_prk_id', r'purok\(prk_id\)', 'SET NULL'),
                                     ('incidentreport_id', r'incident_report\(incr_id\)', 'CASCADE'),
                                     ('purok_id', r'purok\(prk_id\)', 'CASCADE')):
            self.assertRegex(sql, rf'FOREIGN KEY \({column}\) REFERENCES {target} ON DELETE {rule}')
