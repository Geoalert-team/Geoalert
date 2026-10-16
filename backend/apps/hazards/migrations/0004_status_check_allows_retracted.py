"""
Let the database accept 'Retracted'.

0003 widened HazardZone.STATUS_CHOICES, but Django choices are validated in
Python only — they never create or alter a database constraint. This schema
was built from the ERD by hand, and hazard_zone carries a CHECK constraint
Django knows nothing about:

    hazard_zone_hzzn_status_check  CHECK (hzzn_status IN
        ('Active', 'Resolved', 'Archived'))

so the column itself rejected the new value and every retract failed with
CheckViolation. This rewrites the constraint to include 'Retracted'.

DROP ... IF EXISTS on purpose: a database created by `migrate` alone has no
such constraint, and this migration has to run on both. Afterwards every
environment carries the same one.
"""

from django.db import migrations

TABLE = 'hazard_zone'
NAME = 'hazard_zone_hzzn_status_check'
COLUMN = 'hzzn_status'


def constraint(values):
    allowed = ', '.join(f"'{v}'" for v in values)
    return (
        f'ALTER TABLE {TABLE} DROP CONSTRAINT IF EXISTS {NAME};\n'
        f'ALTER TABLE {TABLE} ADD CONSTRAINT {NAME} '
        f'CHECK ({COLUMN} IN ({allowed}));'
    )


class Migration(migrations.Migration):

    dependencies = [
        ('hazards', '0003_retract_hazard_zone'),
    ]

    operations = [
        migrations.RunSQL(
            sql=constraint(['Active', 'Resolved', 'Archived', 'Retracted']),
            # Reversing is refused by Postgres while any row is still
            # Retracted, which is the right answer: rolling the constraint
            # back would leave rows the schema says cannot exist.
            reverse_sql=constraint(['Active', 'Resolved', 'Archived']),
        ),
    ]
