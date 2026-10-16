"""
Retracting a hazard zone published in error.

Three new nullable columns and one widened choice list. Additive and
nullable on purpose: the team shares one Supabase database, so whoever
runs this applies it for everybody, and a teammate who has not pulled the
code yet keeps working — their models simply don't know the new columns.
"""

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('hazards', '0002_is_sample'),
    ]

    operations = [
        # choices only — Postgres stores this as the same varchar either way,
        # so this operation touches no data.
        migrations.AlterField(
            model_name='hazardzone',
            name='status',
            field=models.CharField(
                choices=[
                    ('Active', 'Active'),
                    ('Resolved', 'Resolved'),
                    ('Archived', 'Archived'),
                    ('Retracted', 'Retracted'),
                ],
                db_column='hzzn_status',
                default='Active',
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='hazardzone',
            name='retracted_by',
            field=models.ForeignKey(
                blank=True,
                db_column='hzzn_retracted_by',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='retracted_hazard_zones',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name='hazardzone',
            name='retracted_at',
            field=models.DateTimeField(blank=True, db_column='hzzn_retracted_at', null=True),
        ),
        migrations.AddField(
            model_name='hazardzone',
            name='retraction_reason',
            field=models.TextField(blank=True, db_column='hzzn_retraction_reason', default=''),
        ),
    ]
