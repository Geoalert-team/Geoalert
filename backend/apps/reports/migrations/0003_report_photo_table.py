"""
Move incident report photos onto their own table, one row per photo.

0002 put a single photo in incident_report.incr_photo. The ERD already had
incident_report_photo, designed for several photos per report, and a report
usually needs more than one -- a wide shot of how far the water reaches and
a close one of how deep it is. That table is the design of record, so the
single column goes and the table gets used.

The table already exists on the shared Supabase database, created by hand
from the ERD, but Django has never known about it. A plain CreateModel
would be correct for a fresh database and would fail on Supabase with
"relation already exists". SeparateDatabaseAndState covers both: Django's
model state is told the table exists, while the database is given a CREATE
TABLE IF NOT EXISTS that does nothing where the table is already there.

Anyone who ran 0002 has an incr_photo column; it is dropped here. Any photo
already uploaded through 0002 is not carried over -- there were only test
photos, and the files lived on one laptop rather than in the bucket.
"""

import uuid

from django.db import migrations, models
import django.db.models.deletion

import apps.reports.models


CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS incident_report_photo (
    inrp_id          uuid        NOT NULL PRIMARY KEY,
    inrp_incr_id     uuid        NOT NULL
                     REFERENCES incident_report (incr_id)
                     DEFERRABLE INITIALLY DEFERRED,
    inrp_url         varchar(200) NOT NULL,
    inrp_uploaded_at timestamptz NOT NULL
);
CREATE INDEX IF NOT EXISTS incident_report_photo_inrp_incr_id_idx
    ON incident_report_photo (inrp_incr_id);
"""

DROP_TABLE = 'DROP TABLE IF EXISTS incident_report_photo;'


class Migration(migrations.Migration):

    dependencies = [
        ('reports', '0002_incident_report_photo'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name='ReportPhoto',
                    fields=[
                        ('id', models.UUIDField(
                            db_column='inrp_id', default=uuid.uuid4,
                            editable=False, primary_key=True, serialize=False)),
                        ('image', models.ImageField(
                            db_column='inrp_url', max_length=200,
                            upload_to=apps.reports.models.report_photo_path)),
                        ('uploaded_at', models.DateTimeField(
                            auto_now_add=True, db_column='inrp_uploaded_at')),
                        ('report', models.ForeignKey(
                            db_column='inrp_incr_id',
                            on_delete=django.db.models.deletion.CASCADE,
                            related_name='photos', to='reports.incidentreport')),
                    ],
                    options={
                        'db_table': 'incident_report_photo',
                        'ordering': ['uploaded_at'],
                    },
                ),
            ],
            database_operations=[
                migrations.RunSQL(sql=CREATE_TABLE, reverse_sql=DROP_TABLE),
            ],
        ),
        migrations.RemoveField(
            model_name='incidentreport',
            name='photo',
        ),
    ]
