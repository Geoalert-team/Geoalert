"""
Builds the team's development database from the live one, with the personal
data scrubbed out (security audit GA-04, deploy/SEPARATE_DATABASES.md).

Run it from the backend folder, with its venv:

    python ..\\deploy\\make_dev_database.py --target-env .env.devdb

  source  the live database, from backend/.env (or the file GEOALERT_ENV_FILE
          names). Only ever read: the connection is set read-only first.
  target  the development database, from the file --target-env names (the new
          Supabase project's DB_NAME, DB_USER, DB_PASSWORD, DB_HOST, DB_PORT).
          Its tables are created by the migrations, then emptied and filled.

What the copy leaves out or changes:
  * accounts      every account kept (other rows point at them) but with a
                  made-up name and email, no phone, an unusable password, no
                  2FA, not staff. Nobody can sign in until a password is set:
                  python manage.py changepassword <email>  (against the dev db)
  * incident reports   description, reporter, position, agency and review
                  note replaced
  * left out      sessions, the audit log, notifications, report photos,
                  uploaded tutorial videos and news photos (the files are in
                  the live project's storage, which the dev project can't read)
Everything else (barangays, puroks, hazards, history, models' logs, guidance,
news text, settings) is copied as it is.

Afterwards row-level security is turned on for every table, as on the live
database. Prints counts only, never a value.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from collections import Counter
from io import StringIO
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / 'backend'
sys.path.insert(0, str(BACKEND))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')

# Left out entirely (personal, per-session, or files the dev project can't read)
EXCLUDE = [
    'contenttypes', 'auth.permission', 'auth.group', 'sessions', 'admin',
    'admin_dashboard.auditlog', 'notifications', 'reports.reportphoto',
]
SCRUBBED_REPORT = 'Scrubbed copy of a report (development database).'


def read_env_file(path):
    values = {}
    for line in Path(path).read_text(encoding='utf-8', errors='replace').splitlines():
        m = re.match(r'\s*([A-Z0-9_]+)\s*=(.*)$', line)
        if m and not line.lstrip().startswith('#'):
            values[m.group(1)] = m.group(2).strip().strip('"').strip("'")
    return values


def project_ref(user):
    """'postgres.abcd1234' -> 'abcd1234' (Supabase pooler logins), else ''."""
    return user.split('.', 1)[1] if '.' in user else ''


def scrub(objects):
    """The dumped rows with personal data replaced; returns (rows, dropped counts)."""
    kept, dropped = [], Counter()
    users = 0
    for obj in objects:
        model, f = obj['model'], obj['fields']
        if model == 'accounts.user':
            users += 1
            f.update(
                first_name='Dev', middle_initial=None, last_name=f'User {users}', suffix=None,
                full_name=f'Dev User {users}', email=f'user{users}@dev.geoalert.local', phone=None,
                position=None, password='!dev-copy-no-password', two_factor_enabled=False,
                two_factor_secret=None, is_staff=False, is_superuser=False,
                failed_login_count=0, locked_until=None, must_change_password=False,
                groups=[], user_permissions=[],
            )
        elif model == 'reports.incidentreport':
            f.update(description=SCRUBBED_REPORT, reporter_name='', position='', agency='',
                     review_note='Scrubbed review note.' if f.get('review_note') else '')
        elif model == 'news.announcement':
            f['photo'] = ''
        elif model == 'tutorials.tutorialvideo' and f.get('file'):
            dropped[model] += 1
            continue
        kept.append(obj)
    return kept, dropped


def main():
    parser = argparse.ArgumentParser(description='Build the development database from the live one, scrubbed.')
    parser.add_argument('--target-env', required=True,
                        help='settings file with the development database login (relative to backend/)')
    parser.add_argument('--replace', action='store_true',
                        help='empty a development database that already has GeoAlert data in it')
    parser.add_argument('--yes', action='store_true', help="don't ask before writing to the target")
    args = parser.parse_args()

    target_file = BACKEND / args.target_env
    if not target_file.is_file():
        raise SystemExit(f'{target_file} not found.')
    t = read_env_file(target_file)
    missing = [k for k in ('DB_NAME', 'DB_USER', 'DB_PASSWORD', 'DB_HOST') if not t.get(k)]
    if missing:
        raise SystemExit(f'{target_file.name} is missing: {", ".join(missing)}')

    import django
    from django.conf import settings
    django.setup()
    src = settings.DATABASES['default']
    same = (src['HOST'], str(src['PORT']), src['NAME'], src['USER']) ==            (t['DB_HOST'], t.get('DB_PORT', '5432'), t['DB_NAME'], t['DB_USER'])
    same_project = project_ref(src['USER']) and project_ref(src['USER']) == project_ref(t['DB_USER'])
    if same or same_project:
        raise SystemExit('The target is the live database. Nothing was done.')

    from django.core.management import call_command
    from django.db.backends.signals import connection_created

    # This process only ever reads the source. (Some of the project's data
    # migrations write through the default connection whatever database they
    # are run on, so the target is built in a separate process below, where
    # the development database is the only one configured.)
    def read_only(sender, connection, **kwargs):
        with connection.cursor() as cursor:
            cursor.execute('SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY')
    connection_created.connect(read_only)

    import psycopg2

    def target_db():
        return psycopg2.connect(dbname=t['DB_NAME'], user=t['DB_USER'], password=t['DB_PASSWORD'],
                                host=t['DB_HOST'], port=t.get('DB_PORT', '5432'),
                                sslmode=t.get('DB_SSLMODE', 'require'), connect_timeout=15,
                                application_name='geoalert-make-dev-database')

    def manage(*command):
        """manage.py with the development database as the only database (and no photo storage)."""
        env = {**os.environ, 'DJANGO_SETTINGS_MODULE': 'config.settings.development',
               'DB_NAME': t['DB_NAME'], 'DB_USER': t['DB_USER'], 'DB_PASSWORD': t['DB_PASSWORD'],
               'DB_HOST': t['DB_HOST'], 'DB_PORT': t.get('DB_PORT', '5432'),
               'DB_SSLMODE': t.get('DB_SSLMODE', 'require'), 'DB_CONN_MAX_AGE': '0',
               'HAZARD_LOG_WRITER': 'false', 'SUPABASE_S3_ENDPOINT': '', 'SUPABASE_S3_BUCKET': '',
               'SUPABASE_S3_KEY': '', 'SUPABASE_S3_SECRET': '', 'SUPABASE_S3_REGION': '',
               'PYTHONDONTWRITEBYTECODE': '1'}
        done = subprocess.run([sys.executable, 'manage.py', *command, '-v', '0'], cwd=BACKEND, env=env,
                              capture_output=True, text=True)
        if done.returncode:
            sys.stderr.write(done.stdout[-3000:] + done.stderr[-3000:])
            raise SystemExit(f'manage.py {command[0]} failed on the target; the source was not touched.')

    print(f'Source (read only): project {project_ref(src["USER"]) or src["NAME"]}')
    print(f'Target:             project {project_ref(t["DB_USER"]) or t["DB_NAME"]}')

    with target_db() as conn, conn.cursor() as cursor:
        cursor.execute("SELECT to_regclass('public.app_user') IS NOT NULL")
        has_rows = False
        if cursor.fetchone()[0]:
            cursor.execute('SELECT EXISTS (SELECT 1 FROM app_user)')
            has_rows = cursor.fetchone()[0]
    if has_rows and not args.replace:
        raise SystemExit('The target already has GeoAlert data. Run again with --replace to empty it first.')
    if not args.yes and input('Create the tables and copy the scrubbed data into the target? [y/N] ').lower() != 'y':
        raise SystemExit('Nothing was done.')

    print('1/5 Reading the live database ...')
    out = StringIO()
    call_command('dumpdata', exclude=EXCLUDE, format='json', stdout=out, verbosity=0)
    rows, dropped = scrub(json.loads(out.getvalue()))
    del out

    path = None
    try:
        # Only the scrubbed copy is ever written to disk
        with tempfile.NamedTemporaryFile('w', suffix='.json', delete=False, encoding='utf-8') as f:
            json.dump(rows, f)
            path = f.name

        print('2/5 Creating the tables (migrations) ...')
        with target_db() as conn, conn.cursor() as cursor:
            # As on the live project: Supabase keeps extensions in their own
            # schema, which its postgres login has on the search path. A plain
            # PostgreSQL has no such schema, and gets it in public.
            cursor.execute("SELECT to_regnamespace('extensions') IS NOT NULL")
            where = ' WITH SCHEMA extensions' if cursor.fetchone()[0] else ''
            cursor.execute(f'CREATE EXTENSION IF NOT EXISTS postgis{where}')
        manage('migrate', '--noinput')

        print('3/5 Emptying what the migrations put in ...')
        manage('flush', '--noinput')

        print('4/5 Loading the scrubbed copy ...')
        manage('loaddata', path)
    finally:
        if path:
            os.unlink(path)

    print('5/5 Turning on row-level security for every table ...')
    with target_db() as conn, conn.cursor() as cursor:
        cursor.execute("""SELECT quote_ident(relname) FROM pg_class
                          WHERE relnamespace = 'public'::regnamespace AND relkind IN ('r','p')
                          AND NOT relrowsecurity""")
        for (name,) in cursor.fetchall():
            cursor.execute(f'ALTER TABLE public.{name} ENABLE ROW LEVEL SECURITY')

    roles = {r['pk']: r['fields']['name'] for r in rows if r['model'] == 'accounts.role'}
    print('\nDevelopment accounts (made-up; set a password for the ones you need):')
    for r in rows:
        if r['model'] == 'accounts.user' and r['fields'].get('is_active'):
            print(f"  {r['fields']['email']:36} {roles.get(r['fields'].get('role'), 'no role')}")

    counts = Counter(r['model'] for r in rows)
    print('\nCopied:')
    for model, n in sorted(counts.items()):
        print(f'  {model:40} {n}')
    for model, n in sorted(dropped.items()):
        print(f'  {model:40} {n} left out (uploaded files)')
    print(f'\nDone. Every account has an unusable password. Set one for yours with\n'
          f'  $env:GEOALERT_ENV_FILE="{args.target_env}"; python manage.py changepassword <email>')


if __name__ == '__main__':
    main()
