from django.db import migrations

# hazard_zone carries a hand-written CHECK constraint on status (see 0004).
# 0011 added the Resolving choice (a fire that is out, figures pending), but
# choices never reach the database, so putting a fire out failed with a
# CheckViolation. Same fix as 0004 and 0005: rewrite the constraint.
# A database built from migrations alone has no such constraint; DROP ... IF
# EXISTS then ADD gives it one, which matches what the model allows.
TABLE = 'hazard_zone'
NAME = 'hazard_zone_hzzn_status_check'
BEFORE = ['Active', 'Resolved', 'Archived', 'Retracted', 'Awaiting_Approval']


def status_check(values):
    allowed = ', '.join(f"'{v}'" for v in values)
    return (
        f'ALTER TABLE {TABLE} DROP CONSTRAINT IF EXISTS {NAME}; '
        f'ALTER TABLE {TABLE} ADD CONSTRAINT {NAME} CHECK (hzzn_status IN ({allowed}));'
    )


class Migration(migrations.Migration):

    dependencies = [
        ('hazards', '0011_fire_out'),
    ]

    operations = [
        migrations.RunSQL(
            sql=status_check(BEFORE + ['Resolving']),
            # Fails while any zone is still Resolving, which is right: rolling
            # back must not leave rows the old constraint forbids
            reverse_sql=status_check(BEFORE),
        ),
    ]
