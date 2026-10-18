"""
One optional photo per incident report.

A nullable varchar holding the path under MEDIA_ROOT; the file itself is not
in the database. Additive and nullable, so the shared Supabase database takes
it without touching existing rows, and a teammate who has not pulled the code
keeps working.
"""

from django.db import migrations, models

import apps.reports.models


class Migration(migrations.Migration):

    dependencies = [
        ('reports', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='incidentreport',
            name='photo',
            field=models.ImageField(
                blank=True,
                db_column='incr_photo',
                null=True,
                upload_to=apps.reports.models.report_photo_path,
            ),
        ),
    ]
