from django.db import migrations, models


class Migration(migrations.Migration):
    """
    Province and region beside the municipality, for the incident report's
    location (the BFP fire log's columns C-E). Every barangay loaded so far
    is in Talisay City, so the defaults fill them in.
    """

    dependencies = [
        ('barangays', '0002_purok'),
    ]

    operations = [
        migrations.AddField(
            model_name='barangay',
            name='province',
            field=models.CharField(db_column='brgy_province', default='Cebu', max_length=100),
        ),
        migrations.AddField(
            model_name='barangay',
            name='region',
            field=models.CharField(db_column='brgy_region', default='Region VII (Central Visayas)', max_length=100),
        ),
    ]
