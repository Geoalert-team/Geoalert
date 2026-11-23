"""
Stop using HazardZone.is_sample without dropping its column yet.

The live site shares this database and may still run code that reads
hzzn_is_sample, so the column stays for now with a database default of
false: older code keeps working, and code without the field can still
insert rows. A later migration drops the column once the live site runs
code without it.
"""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('hazards', '0012_status_check_allows_resolving'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.RemoveField(model_name='hazardzone', name='is_sample'),
            ],
            database_operations=[
                migrations.RunSQL(
                    'ALTER TABLE hazard_zone ALTER COLUMN hzzn_is_sample SET DEFAULT false',
                    reverse_sql='ALTER TABLE hazard_zone ALTER COLUMN hzzn_is_sample DROP DEFAULT',
                ),
            ],
        ),
    ]
