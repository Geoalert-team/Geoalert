from django.db import migrations, models
import django.db.models.deletion


# The landslide susceptibility log: one new table, plus a trigger that refuses
# any UPDATE or DELETE of its rows (copied from 0011), so a logged class is
# never changed afterwards. Row triggers do not fire on TRUNCATE, so test
# teardown still empties it. The purok is a plain id (no foreign key), so a
# purok reload never touches the log. Additive only; applied to the shared
# database only after a backup and the user's go-ahead.
FROZEN = """
CREATE FUNCTION landslide_purok_susceptibility_log_frozen() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'landslide_purok_susceptibility_log rows are never changed'; END $$;
CREATE TRIGGER landslide_purok_susceptibility_log_frozen BEFORE UPDATE OR DELETE ON landslide_purok_susceptibility_log
FOR EACH ROW EXECUTE FUNCTION landslide_purok_susceptibility_log_frozen();
"""
UNFROZEN = ('DROP TRIGGER landslide_purok_susceptibility_log_frozen ON landslide_purok_susceptibility_log; '
            'DROP FUNCTION landslide_purok_susceptibility_log_frozen();')


class Migration(migrations.Migration):

    dependencies = [
        ('barangays', '0003_barangay_province_region'),
        ('history', '0012_model_fit'),
    ]

    operations = [
        migrations.CreateModel(
            name='LandslidePurokSusceptibilityLog',
            fields=[
                ('id', models.BigAutoField(db_column='lpsl_id', primary_key=True, serialize=False)),
                ('purok_id', models.BigIntegerField(db_column='lpsl_purok_id')),
                ('purok_name', models.TextField(db_column='lpsl_purok_name')),
                ('model_version', models.TextField(db_column='lpsl_model_version')),
                ('source', models.TextField(db_column='lpsl_source')),
                ('level', models.TextField(db_column='lpsl_level', null=True)),
                ('score', models.FloatField(db_column='lpsl_score', null=True)),
                ('uncertain', models.BooleanField(db_column='lpsl_uncertain')),
                ('not_assessed_reason', models.TextField(blank=True, db_column='lpsl_not_assessed_reason', default='')),
                ('outlines_version', models.TextField(db_column='lpsl_outlines_version')),
                ('published_on', models.DateField(db_column='lpsl_published_on')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_column='lpsl_created_at')),
                ('barangay', models.ForeignKey(db_column='lpsl_brgy_id', on_delete=django.db.models.deletion.PROTECT, to='barangays.barangay')),
            ],
            options={
                'db_table': 'landslide_purok_susceptibility_log',
                'indexes': [models.Index(fields=['model_version'], name='lpsl_model_version_idx')],
            },
        ),
        migrations.AddConstraint(
            model_name='landslidepuroksusceptibilitylog',
            constraint=models.UniqueConstraint(fields=('purok_id', 'model_version'), name='landslide_purok_susceptibility_log_unique'),
        ),
        migrations.AddConstraint(
            model_name='landslidepuroksusceptibilitylog',
            constraint=models.CheckConstraint(check=models.Q(('level__isnull', True), ('level__in', ['Red', 'Orange', 'Green']), _connector='OR'), name='landslide_purok_susceptibility_log_level'),
        ),
        migrations.AddConstraint(
            model_name='landslidepuroksusceptibilitylog',
            constraint=models.CheckConstraint(check=models.Q(('source__in', ['model', 'noah', 'geoalert'])), name='landslide_purok_susceptibility_log_source'),
        ),
        migrations.RunSQL(sql=FROZEN, reverse_sql=UNFROZEN),
    ]
