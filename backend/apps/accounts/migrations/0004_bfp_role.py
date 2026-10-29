# BFP personnel: a role for the Bureau of Fire Protection, who see fires,
# close them with the BFP figures and export the fire history, and nothing
# else. The role row is created here rather than left to seed_data, so an
# administrator can pick it as soon as the migration runs.

from django.db import migrations, models


# The shared database was first built from SQL that also put a CHECK on the
# role names, which Django never made and doesn't know about. Where it is
# there, let it take the new role too; a database Django built has none.
WIDEN_CHECK = """
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_constraint
               WHERE conname = 'role_role_name_check' AND conrelid = 'role'::regclass) THEN
        ALTER TABLE role DROP CONSTRAINT role_role_name_check;
        ALTER TABLE role ADD CONSTRAINT role_role_name_check CHECK (role_name IN
            ('System_Admin', 'DRRMO_Officer', 'Barangay_Personnel', 'BFP_Personnel'));
    END IF;
END $$;
"""


def add_role(apps, schema_editor):
    Role = apps.get_model('accounts', 'Role')
    Role.objects.get_or_create(name='BFP_Personnel')


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0003_user_must_change_password'),
    ]

    operations = [
        migrations.AlterField(
            model_name='role',
            name='name',
            field=models.CharField(
                choices=[('System_Admin', 'System Administrator'), ('DRRMO_Officer', 'DRRMO Officer'),
                         ('Barangay_Personnel', 'Barangay Personnel'), ('BFP_Personnel', 'BFP Personnel')],
                db_column='role_name', max_length=40, unique=True,
            ),
        ),
        migrations.RunSQL(WIDEN_CHECK, reverse_sql=migrations.RunSQL.noop),
        # Kept on reversal: deleting the row would strip the role from every BFP account
        migrations.RunPython(add_role, migrations.RunPython.noop),
    ]
