from django.db import migrations

# Django adds a column with its default and then drops the default, so 0003
# left these NOT NULL with nothing to fill them. Code from before 0003, still
# run against the shared database from other branches, inserts history
# without them and failed. A database default of '' lets those inserts work.
COLUMNS = ['hstr_alarm_level', 'hstr_property_category', 'hstr_property_subcategory', 'hstr_location_text']


class Migration(migrations.Migration):

    dependencies = [
        ('history', '0003_bfp_fields'),
    ]

    operations = [
        migrations.RunSQL(
            sql=f"ALTER TABLE historical_record ALTER COLUMN {column} SET DEFAULT ''",
            reverse_sql=f'ALTER TABLE historical_record ALTER COLUMN {column} DROP DEFAULT',
        )
        for column in COLUMNS
    ]
