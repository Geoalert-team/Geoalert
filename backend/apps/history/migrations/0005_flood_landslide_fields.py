from django.db import migrations, models

# The text columns get a database default of '' as in 0004, so code from
# before this migration, still run against the shared database from other
# branches, can insert history without them.
TEXT_COLUMNS = ['hstr_hazard_subcategory', 'hstr_cause']


class Migration(migrations.Migration):

    dependencies = [
        ('history', '0004_bfp_text_defaults'),
    ]

    operations = [
        migrations.AddField(
            model_name='historicalrecord',
            name='hazard_subcategory',
            field=models.CharField(blank=True, db_column='hstr_hazard_subcategory', default='', max_length=60),
        ),
        migrations.AddField(
            model_name='historicalrecord',
            name='cause',
            field=models.CharField(blank=True, db_column='hstr_cause', default='', max_length=200),
        ),
        migrations.AddField(
            model_name='historicalrecord',
            name='injured',
            field=models.IntegerField(blank=True, db_column='hstr_injured', null=True),
        ),
        migrations.AddField(
            model_name='historicalrecord',
            name='fatalities',
            field=models.IntegerField(blank=True, db_column='hstr_fatalities', null=True),
        ),
        migrations.AddField(
            model_name='historicalrecord',
            name='families_affected',
            field=models.IntegerField(blank=True, db_column='hstr_families_affected', null=True),
        ),
        migrations.AddField(
            model_name='historicalrecord',
            name='persons_affected',
            field=models.IntegerField(blank=True, db_column='hstr_persons_affected', null=True),
        ),
        *(
            migrations.RunSQL(
                sql=f"ALTER TABLE historical_record ALTER COLUMN {column} SET DEFAULT ''",
                reverse_sql=f'ALTER TABLE historical_record ALTER COLUMN {column} DROP DEFAULT',
            )
            for column in TEXT_COLUMNS
        ),
    ]
