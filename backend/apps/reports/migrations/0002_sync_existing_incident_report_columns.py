"""
State-only migration.

The shared Supabase table `incident_report` already has these columns (they were
added outside this branch), so we must NOT run any DDL here. This migration only
teaches Django's migration state about them so the model and the table agree.
"""
import uuid
import django.core.validators
import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('reports', '0001_initial'),
        ('hazards', '0002_hazardzone_verification_note_and_more'),
        ('history', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    state_operations = [
        migrations.AddField('incidentreport', 'reporter_name', models.CharField(blank=True, default='', max_length=150)),
        migrations.AddField('incidentreport', 'agency', models.CharField(blank=True, default='', max_length=150)),
        migrations.AddField('incidentreport', 'position', models.CharField(blank=True, default='', max_length=150)),
        migrations.AddField('incidentreport', 'severity_estimate', models.CharField(blank=True, default='', max_length=50)),
        migrations.AddField('incidentreport', 'submitted_at', models.DateTimeField(default=django.utils.timezone.now)),
        migrations.AddField('incidentreport', 'validated_at', models.DateTimeField(blank=True, null=True)),
        migrations.AddField('incidentreport', 'validated_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='validated_reports', to=settings.AUTH_USER_MODEL)),
        migrations.AddField('incidentreport', 'hazard_zone', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='hazards.hazardzone')),
        migrations.AddField('incidentreport', 'historical_record', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='history.historicalrecord')),
        migrations.AddField('incidentreport', 'casualties_dead', models.IntegerField(blank=True, default=0, null=True, validators=[django.core.validators.MinValueValidator(0)])),
        migrations.AddField('incidentreport', 'casualties_injured', models.IntegerField(blank=True, default=0, null=True, validators=[django.core.validators.MinValueValidator(0)])),
        migrations.AddField('incidentreport', 'casualties_missing', models.IntegerField(blank=True, default=0, null=True, validators=[django.core.validators.MinValueValidator(0)])),
        migrations.AddField('incidentreport', 'displaced', models.IntegerField(blank=True, default=0, null=True, validators=[django.core.validators.MinValueValidator(0)])),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=state_operations,
        ),
    ]
