from django.db import migrations, models

# A database default of '' as in 0004, so code from before this migration,
# still run against the shared database from other branches, can insert
# history without the column.


class Migration(migrations.Migration):

    dependencies = [
        ('history', '0006_location'),
    ]

    operations = [
        migrations.AddField(
            model_name='historicalrecord',
            name='source',
            field=models.CharField(blank=True, db_column='hstr_source', default='', max_length=300),
        ),
        migrations.RunSQL(
            sql="ALTER TABLE historical_record ALTER COLUMN hstr_source SET DEFAULT ''",
            reverse_sql='ALTER TABLE historical_record ALTER COLUMN hstr_source DROP DEFAULT',
        ),
    ]
