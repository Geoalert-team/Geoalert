# Adds personnel profile fields to app_user. Every column is nullable, so
# rows created before this migration (and code on branches without these
# fields) keep working against the shared database.
#
# user_brgy_id already existed in the shared Supabase table (bigint, nullable)
# before this migration was written, so it is added with IF NOT EXISTS and the
# foreign key / index are only created when missing. Reversing this migration
# leaves that column alone, since it isn't ours to drop.

from django.db import migrations, models
import django.db.models.deletion


ADD_BARANGAY_COLUMN = """
ALTER TABLE app_user ADD COLUMN IF NOT EXISTS user_brgy_id bigint NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON kcu.constraint_name = tc.constraint_name
         AND kcu.table_schema = tc.table_schema
        WHERE tc.constraint_type = 'FOREIGN KEY'
          AND tc.table_schema = current_schema()
          AND tc.table_name = 'app_user'
          AND kcu.column_name = 'user_brgy_id'
    ) THEN
        ALTER TABLE app_user
            ADD CONSTRAINT app_user_user_brgy_id_fk_barangay_brgy_id
            FOREIGN KEY (user_brgy_id) REFERENCES barangay (brgy_id)
            DEFERRABLE INITIALLY DEFERRED;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS app_user_user_brgy_id_idx ON app_user (user_brgy_id);
"""


class Migration(migrations.Migration):

    dependencies = [
        ('barangays', '0001_initial'),
        ('accounts', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='first_name',
            field=models.CharField(blank=True, db_column='user_first_name', max_length=60, null=True),
        ),
        migrations.AddField(
            model_name='user',
            name='middle_initial',
            field=models.CharField(blank=True, db_column='user_middle_initial', max_length=3, null=True),
        ),
        migrations.AddField(
            model_name='user',
            name='last_name',
            field=models.CharField(blank=True, db_column='user_last_name', max_length=60, null=True),
        ),
        migrations.AddField(
            model_name='user',
            name='suffix',
            field=models.CharField(blank=True, db_column='user_suffix', max_length=10, null=True),
        ),
        migrations.AddField(
            model_name='user',
            name='phone',
            field=models.CharField(blank=True, db_column='user_phone', max_length=20, null=True),
        ),
        migrations.AddField(
            model_name='user',
            name='employee_id',
            field=models.CharField(blank=True, db_column='user_employee_id', max_length=30, null=True),
        ),
        migrations.AddField(
            model_name='user',
            name='position',
            field=models.CharField(blank=True, db_column='user_position', max_length=100, null=True),
        ),
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(ADD_BARANGAY_COLUMN, reverse_sql=migrations.RunSQL.noop),
            ],
            state_operations=[
                migrations.AddField(
                    model_name='user',
                    name='assigned_barangay',
                    field=models.ForeignKey(blank=True, db_column='user_brgy_id', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='personnel', to='barangays.barangay'),
                ),
            ],
        ),
    ]