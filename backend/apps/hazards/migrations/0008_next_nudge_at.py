# F2: remind the publisher about a zone left Active with no update for 24 hours.
#
# hzzn_next_nudge_at is when the next reminder is due. Publishing, any
# officer update, and each reminder push it 24 hours on. Zones already live
# are given their activation time + 24 hours, so a zone that has sat
# untouched for days is flagged once, on the first check after this runs.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('hazards', '0007_pending_raise_and_reminders'),
    ]

    operations = [
        migrations.AddField(
            model_name='hazardzone',
            name='next_nudge_at',
            field=models.DateTimeField(blank=True, null=True, db_column='hzzn_next_nudge_at'),
        ),
        migrations.RunSQL(
            sql="UPDATE hazard_zone SET hzzn_next_nudge_at = hzzn_activated_at + interval '24 hours' "
                "WHERE hzzn_status = 'Active' AND hzzn_next_nudge_at IS NULL;",
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.AddIndex(
            model_name='hazardzone',
            index=models.Index(fields=['status', 'next_nudge_at'], name='hzzn_nudge_due_idx'),
        ),
    ]
