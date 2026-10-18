# F1: a password an administrator set (new account or reset) must be
# replaced at the next sign-in. The column gets a database default too, so
# teammates' branches that insert users without this field keep working.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0002_user_profile_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='must_change_password',
            field=models.BooleanField(default=False, db_column='user_must_change_password'),
        ),
        migrations.RunSQL(
            sql='ALTER TABLE app_user ALTER COLUMN user_must_change_password SET DEFAULT false;',
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
