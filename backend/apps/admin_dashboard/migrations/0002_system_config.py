# F8 System configuration panel: settings a System Administrator can change.
#
# The ERD already defines system_config, and the Supabase database built
# from it has the table (empty). So the table is only created when it is
# missing (a database built by `migrate` alone); on Supabase this migration
# just records the model. The columns match the ERD exactly.

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import uuid

CREATE_SQL = """
CREATE TABLE IF NOT EXISTS system_config (
    sysc_id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    sysc_key        varchar(100) NOT NULL UNIQUE,
    sysc_value      text NOT NULL DEFAULT '',
    sysc_updated_by uuid NULL REFERENCES app_user(user_id) ON DELETE SET NULL DEFERRABLE INITIALLY DEFERRED,
    sysc_updated_at timestamp with time zone NOT NULL DEFAULT now()
);
"""


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('admin_dashboard', '0001_initial'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(CREATE_SQL, reverse_sql=migrations.RunSQL.noop),
            ],
            state_operations=[
                migrations.CreateModel(
                    name='SystemConfig',
                    fields=[
                        ('id', models.UUIDField(db_column='sysc_id', default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                        ('key', models.CharField(db_column='sysc_key', max_length=100, unique=True)),
                        ('value', models.TextField(db_column='sysc_value', default='')),
                        ('updated_at', models.DateTimeField(auto_now=True, db_column='sysc_updated_at')),
                        ('updated_by', models.ForeignKey(blank=True, db_column='sysc_updated_by', null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
                    ],
                    options={
                        'db_table': 'system_config',
                        'ordering': ['key'],
                    },
                ),
            ],
        ),
    ]
