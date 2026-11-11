# Separate from 0005 so the renumbering is committed before the index is
# built: PostgreSQL can refuse an ALTER TABLE on rows changed earlier in the
# same transaction.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0005_number_employee_ids'),
    ]

    operations = [
        migrations.AlterField(
            model_name='user',
            name='employee_id',
            field=models.CharField(blank=True, db_column='user_employee_id', max_length=30, null=True, unique=True),
        ),
    ]
