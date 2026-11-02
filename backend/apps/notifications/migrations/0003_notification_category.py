# Each notification stores the bell tab it belongs to, instead of the bell
# guessing it from the wording (which a reworded message could quietly move).
# The column gets a database default too, so teammates' branches that insert
# notifications without this field keep working. Rows already there are
# filed the way the bell used to guess them.

from django.db import migrations, models

SECURITY_WORDS = ('password', 'two-factor', 'sign in', 'login', 'locked')


def category_for(content, about_hazard):
    """The bell's old guess, kept here as it was for the rows written before this field."""
    if about_hazard:
        return 'hazard'
    text = (content or '').lower()
    if 'withdrawn' in text:
        return 'hazard'
    if 'report' in text:
        return 'report'
    if any(word in text for word in SECURITY_WORDS):
        return 'security'
    return 'account'


def backfill(apps, schema_editor):
    Notification = apps.get_model('notifications', 'Notification')
    rows = Notification.objects.filter(hazard_alert__isnull=True, hazard_zone__isnull=True)
    for row in rows.only('id', 'content').iterator():
        category = category_for(row.content, False)
        if category != 'hazard':
            Notification.objects.filter(pk=row.pk).update(category=category)


class Migration(migrations.Migration):

    dependencies = [
        ('notifications', '0002_approval_and_zone_notices'),
    ]

    operations = [
        migrations.AddField(
            model_name='notification',
            name='category',
            field=models.CharField(
                choices=[('hazard', 'Hazard'), ('report', 'Report'), ('security', 'Security'), ('account', 'Account')],
                db_column='notf_category', default='hazard', max_length=20,
            ),
        ),
        migrations.RunSQL(
            sql="ALTER TABLE notification ALTER COLUMN notf_category SET DEFAULT 'hazard';",
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.RunPython(backfill, migrations.RunPython.noop),
    ]
