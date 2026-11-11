# Employee IDs stop being typed and are given by the system (see
# EMPLOYEE_ID_PREFIXES in models.py). This numbers every account that already
# exists the same way: per role, in the order the accounts were created. Any
# ID typed by hand before is replaced, so every ID follows one format.
#
# The prefixes are copied here rather than imported, so this migration keeps
# doing what it did if models.py changes later.

from django.db import migrations

PREFIXES = {
    'System_Admin':       'ADMIN',
    'DRRMO_Officer':      'DRRMO',
    'Barangay_Personnel': 'BRGY',
    'BFP_Personnel':      'BFP',
}


def number_accounts(apps, schema_editor):
    User = apps.get_model('accounts', 'User')
    # Cleared first, so a number handed out below never meets an old copy of itself
    User.objects.update(employee_id=None)

    counters = {}
    for user in User.objects.select_related('role').order_by('created_at', 'id'):
        if user.role is None:
            continue  # gets one when an administrator gives it a role
        prefix = PREFIXES.get(user.role.name, 'USER')
        counters[prefix] = counters.get(prefix, 0) + 1
        User.objects.filter(pk=user.pk).update(employee_id=f'{prefix}-{counters[prefix]:04d}')


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0004_bfp_role'),
    ]

    operations = [
        # Not reversible in content: the IDs typed by hand before are gone
        migrations.RunPython(number_accounts, migrations.RunPython.noop),
    ]
