"""
Keeping seeded sample data out of reports.

`manage.py seed_fake_hazards` fills the map and the archive with Faker events
so the layers, trends and outlook have something to work with. Those rows are
real database rows, flagged `is_sample`.

Only the reports exclude them. Everywhere else already says what it is showing:
the map carries an "Includes sample data" notice, and the History page labels
the count and badges each sample row. A report does not — it is read as an
official figure, printed and handed over — so a Hazard Summary that counts
invented casualties as DRRMO numbers is the one place this does real damage.

Pass ?include_samples=true to see them anyway; the response says which way it
went so the screen can label itself.
"""

TRUTHY = ('1', 'true', 'yes', 'on')


def include_samples(request):
    """Did the caller explicitly ask for sample rows? Default is no."""
    value = request.query_params.get('include_samples') or ''
    return value.strip().lower() in TRUTHY


def without_samples(queryset, request, field='is_sample'):
    """
    Drop sample rows unless the caller opted in.

    `field` is the lookup from the queryset's model to the flag, so a model
    that has it directly passes 'is_sample' and one that reaches it through a
    relation passes something like 'hazard_zone__is_sample'.
    """
    if include_samples(request):
        return queryset
    return queryset.filter(**{field: False})