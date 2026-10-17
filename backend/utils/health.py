"""
What "Operational" on the admin dashboard actually means.

The status used to be the literal string 'Operational', which answered no
question at all: the only thing that could ever change it was the request
for it failing. This runs five checks and says which one is unhappy.

Honest about its own limits, because the dashboard shows this to the person
who has to trust it:

  * It observes from inside the Django process. It cannot see whether
    residents can reach the site, whether SMS left the building, or whether
    Supabase is slow for someone else.
  * It cannot report "database down" from inside a reply, because
    authenticating the request already needs the database. Total loss of the
    database surfaces as this request failing, and the dashboard renders
    that as Down — see SystemHealthView.
  * The migration check compares Django's migration files against the
    django_migrations table. It cannot see hand-written schema drift: a
    CHECK constraint added directly in Supabase is invisible to Django and
    will still pass this check.

States: ok / warn / fail per check; a fail makes the system Down, a warn
makes it Degraded, otherwise Operational.
"""

import time

from django.db import connection

OPERATIONAL = 'Operational'
DEGRADED    = 'Degraded'
DOWN        = 'Down'

# A Supabase round trip from Cebu is normally well under this. Past it the
# dashboard is still usable but something is wrong worth looking at.
SLOW_QUERY_MS = 1500


def _check(key, label, state, detail):
    return {'key': key, 'label': label, 'state': state, 'detail': detail}


def _database():
    """Can we reach the database at all, and how slow is the round trip?"""
    start = time.perf_counter()
    with connection.cursor() as cur:
        cur.execute('SELECT 1')
        cur.fetchone()
    ms = round((time.perf_counter() - start) * 1000, 1)

    if ms > SLOW_QUERY_MS:
        return _check('database', 'Database', 'warn',
                      f'Reachable but slow — a trivial query took {ms} ms.')
    return _check('database', 'Database', 'ok', f'Round trip {ms} ms.')


def _spatial():
    """
    PostGIS, separately from the connection.

    A plain Postgres connection says nothing about whether the extension is
    loaded, and without it every hazard zone, every map query and every
    "which barangays does this touch" lookup fails.
    """
    with connection.cursor() as cur:
        cur.execute('SELECT PostGIS_Lib_Version()')
        version = cur.fetchone()[0]
    return _check('spatial', 'PostGIS', 'ok', f'Version {version}.')


def _migrations():
    """
    Is the database schema the one this code expects?

    The team shares one Supabase database, so a teammate can push models
    whose migration nobody has run yet. That mismatch shows up later as a
    column error in the middle of a real request.
    """
    from django.db.migrations.executor import MigrationExecutor

    executor = MigrationExecutor(connection)
    plan = executor.migration_plan(executor.loader.graph.leaf_nodes())
    if plan:
        names = ', '.join(f'{m.app_label}.{m.name}' for m, _ in plan[:4])
        more = f' and {len(plan) - 4} more' if len(plan) > 4 else ''
        return _check('migrations', 'Database schema', 'warn',
                      f'{len(plan)} migration(s) not applied: {names}{more}. '
                      f'Run python manage.py migrate.')
    return _check('migrations', 'Database schema', 'ok', 'All migrations applied.')


def _alert_routing():
    """
    If a hazard were published right now, would anyone on the ground hear?

    Alerts always reach DRRMO and admins, so an alert is never literally
    unsent. What matters is whether the barangay carrying an active hazard
    has anyone assigned to act on it. Checked against barangays that
    currently hold an active zone, so it stays quiet while barangays without
    hazards are still waiting for their accounts.
    """
    from apps.barangays.models import Barangay

    unstaffed = list(
        Barangay.objects
        .filter(hazardzone__status='Active')
        .exclude(personnel__is_active=True,
                 personnel__role__name='Barangay_Personnel')
        .distinct()
        .values_list('name', flat=True)[:5]
    )
    if unstaffed:
        return _check('alert_routing', 'Alert routing', 'warn',
                      'Active hazards in barangays with no active personnel to '
                      'receive them: ' + ', '.join(unstaffed) + '.')
    return _check('alert_routing', 'Alert routing', 'ok',
                  'Every barangay with an active hazard has personnel assigned.')


def _guidance():
    """
    Does every live hazard have safety guidance to show?

    A resident who taps an active hazard and finds an empty "What to do" tab
    has been given a warning and nothing to do about it.
    """
    from apps.guidance.models import GuidanceContent
    from apps.hazards.models import HazardZone

    live = set(
        HazardZone.objects
        .filter(status='Active')
        .exclude(hazard_type__isnull=True)
        .values_list('hazard_type_id', 'hazard_type__name')
    )
    covered = set(
        GuidanceContent.objects
        .filter(is_published=True)
        .values_list('hazard_type_id', flat=True)
    )
    missing = sorted(name for type_id, name in live if type_id not in covered)

    if missing:
        return _check('guidance', 'Safety guidance', 'warn',
                      'Active hazards with no published guidance: '
                      + ', '.join(missing) + '.')
    if not live:
        return _check('guidance', 'Safety guidance', 'ok', 'No active hazards.')
    return _check('guidance', 'Safety guidance', 'ok',
                  'Published guidance exists for every active hazard type.')


def _file_storage():
    """
    Can an uploaded photo actually be written and read back?

    Worth its own check because the failure is invisible until someone tries.
    With the Supabase keys wrong or the bucket missing, every report submitted
    with a photo fails at the moment a barangay is trying to send one -- which
    is the worst time to find out.

    Only a metadata lookup, so it costs one small request and uploads nothing.
    """
    from django.conf import settings
    from django.core.files.storage import default_storage

    if not getattr(settings, 'USE_SUPABASE_STORAGE', False):
        return _check('storage', 'Photo storage', 'ok',
                      'Local disk. Photos are on this machine only, so another '
                      'server running against the same database cannot show them.')

    bucket = getattr(settings, 'AWS_STORAGE_BUCKET_NAME', '?')

    # HeadBucket, not exists(). Looking for a key that should not be there
    # answers 404 whether the key is missing or the whole bucket is, so a
    # wrong bucket name reads as healthy right up until the first upload
    # fails. HeadBucket distinguishes them, and still costs one request and
    # uploads nothing.
    client = default_storage.connection.meta.client
    client.head_bucket(Bucket=default_storage.bucket_name)

    return _check('storage', 'Photo storage', 'ok',
                  f'Supabase Storage, bucket "{bucket}", reachable.')


def system_health():
    """
    Run every check and fold the results into one status.

    Never raises. A check that blows up is reported as a failed check, not
    as a failed request — a health endpoint that 500s tells you only that
    the health endpoint is broken.
    """
    # Everything after the database needs it, so a dead connection is
    # reported once rather than as five separate failures. Built here rather
    # than at module level so the functions are looked up when the check
    # runs — a list of references captured at import cannot be substituted,
    # which makes each check untestable in isolation.
    dependent = [
        ('spatial',       'PostGIS',         _spatial),
        ('migrations',    'Database schema', _migrations),
        ('alert_routing', 'Alert routing',   _alert_routing),
        ('guidance',      'Safety guidance', _guidance),
    ]

    checks = []

    try:
        checks.append(_database())
        database_ok = True
    except Exception as exc:
        checks.append(_check('database', 'Database', 'fail',
                             f'{type(exc).__name__}: {exc}'.strip()[:200]))
        database_ok = False

    for key, label, fn in dependent:
        if not database_ok:
            checks.append(_check(key, label, 'unknown',
                                 'Not checked — no database connection.'))
            continue
        try:
            checks.append(fn())
        except Exception as exc:
            checks.append(_check(key, label, 'fail',
                                 f'{type(exc).__name__}: {exc}'.strip()[:200]))

    # Outside the loop above: file storage is the one check that does not go
    # through the database, so it is still worth answering when the database
    # is the thing that is down.
    try:
        checks.append(_file_storage())
    except Exception as exc:
        checks.append(_check('storage', 'Photo storage', 'fail',
                             f'Photos cannot be stored or read: '
                             f'{type(exc).__name__}: {exc}'.strip()[:200]))

    states = {c['state'] for c in checks}
    if 'fail' in states:
        status = DOWN
    elif 'warn' in states:
        status = DEGRADED
    else:
        status = OPERATIONAL

    return {
        'status': status,
        'checks': checks,
        'failing': [c['label'] for c in checks if c['state'] in ('fail', 'warn')],
    }
