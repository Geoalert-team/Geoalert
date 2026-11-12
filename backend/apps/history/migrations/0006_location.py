import django.contrib.gis.db.models.fields
from django.db import migrations, models

# The text columns get a database default of '' as in 0004, so code from
# before this migration, still run against the shared database from other
# branches, can insert history without them. The point is nullable.
TEXT_COLUMNS = ['hstr_location_precision', 'hstr_location_basis']


class Migration(migrations.Migration):

    dependencies = [
        ('history', '0005_flood_landslide_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='historicalrecord',
            name='location',
            field=django.contrib.gis.db.models.fields.PointField(blank=True, db_column='hstr_location', null=True,
                                                                 srid=4326),
        ),
        migrations.AddField(
            model_name='historicalrecord',
            name='location_precision',
            field=models.CharField(blank=True, choices=[('place', 'Named purok or sitio'),
                                                        ('landmark', 'Named landmark')],
                                   db_column='hstr_location_precision', default='', max_length=20),
        ),
        migrations.AddField(
            model_name='historicalrecord',
            name='location_basis',
            field=models.CharField(blank=True, db_column='hstr_location_basis', default='', max_length=300),
        ),
        *(
            migrations.RunSQL(
                sql=f"ALTER TABLE historical_record ALTER COLUMN {column} SET DEFAULT ''",
                reverse_sql=f'ALTER TABLE historical_record ALTER COLUMN {column} DROP DEFAULT',
            )
            for column in TEXT_COLUMNS
        ),
    ]
