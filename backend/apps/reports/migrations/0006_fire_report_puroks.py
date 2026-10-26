from django.db import migrations, models


class Migration(migrations.Migration):
    """
    A fire report names one or more puroks instead of one (or a typed name).

    The single `purok` and `purok_other` fields leave the model but not the
    database: the shared database also serves copies of the app from before
    this change, which still read incr_prk_id and incr_purok_other. They can
    be dropped once those copies are gone. Any purok already set is carried
    over to the new link table.
    """

    dependencies = [
        ('barangays', '0002_purok'),
        ('reports', '0005_fire_report_fields'),
    ]

    operations = [
        # First, so the old field's `incident_reports` reverse name is gone
        # before the new one takes it
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.RemoveField(model_name='incidentreport', name='purok'),
                migrations.RemoveField(model_name='incidentreport', name='purok_other'),
            ],
            database_operations=[],
        ),
        migrations.AddField(
            model_name='incidentreport',
            name='puroks',
            field=models.ManyToManyField(blank=True, db_table='incident_report_purok',
                                         related_name='incident_reports', to='barangays.purok'),
        ),
        migrations.RunSQL(
            sql='INSERT INTO incident_report_purok (incidentreport_id, purok_id) '
                'SELECT incr_id, incr_prk_id FROM incident_report WHERE incr_prk_id IS NOT NULL',
            reverse_sql='DELETE FROM incident_report_purok',
        ),
    ]
