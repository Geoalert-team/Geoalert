"""
The shared database runs code from more than one branch. A column that older
code doesn't know about must have a database default, or that code's inserts
fail: Django adds a column with its default and then drops the default, so
0003's text columns were left NOT NULL with nothing to fill them.
"""
from importlib import import_module

from django.test import SimpleTestCase


class BfpColumnDefaultsTests(SimpleTestCase):
    def test_text_columns_older_code_never_sends_have_a_database_default(self):
        migration = import_module('apps.history.migrations.0004_bfp_text_defaults').Migration
        sql = ' '.join(op.sql for op in migration.operations)
        for column in ('hstr_alarm_level', 'hstr_property_category', 'hstr_property_subcategory',
                       'hstr_location_text'):
            self.assertIn(f"ALTER COLUMN {column} SET DEFAULT ''", sql)
