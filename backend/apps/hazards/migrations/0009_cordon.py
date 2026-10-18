# Stage 2: a safety cordon around a hazard zone, as metadata on the zone.
#
# hzzn_cordon_m is the cordon width in meters, or NULL for no cordon. It is
# nullable with no default, so every existing zone reads as "no cordon" and
# code from before this migration, which never sets it, keeps inserting.
#
# hazard_zone carries one hand-written CHECK from the ERD, on hzzn_status
# (see 0004). It does not mention this column, so adding it is safe on both
# a Supabase database and one built by `migrate` alone.
#
# The 10-100 m range is enforced in the publish serializer, not by a CHECK,
# so the limits can be tuned without another migration.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('hazards', '0008_next_nudge_at'),
    ]

    operations = [
        migrations.AddField(
            model_name='hazardzone',
            name='cordon_m',
            field=models.IntegerField(blank=True, null=True, db_column='hzzn_cordon_m'),
        ),
    ]
