import environ
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env()
environ.Env.read_env(BASE_DIR / '.env')

SECRET_KEY = env('SECRET_KEY')
ALLOWED_HOSTS = env.list('ALLOWED_HOSTS', default=['localhost'])

DJANGO_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.gis',
]

THIRD_PARTY_APPS = [
    'rest_framework',
    'rest_framework_gis',
    'corsheaders',
]

LOCAL_APPS = [
    'apps.accounts',
    'apps.hazards',
    'apps.notifications',
    'apps.guidance',
    'apps.history',
    'apps.reports',
    'apps.barangays',
    'apps.admin_dashboard',
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    # Turns an unhandled error on /api/ into a short JSON message instead of
    # a 280 KB HTML debug page the frontend can only call "status code 500".
    'utils.errors.ApiErrorMiddleware',
    # F1: sign out after 30 minutes idle or 12 hours in total
    'utils.session_limits.SessionLimitMiddleware',
    # F1: an admin-set password must be replaced before the account is used
    'utils.password_change.PasswordChangeRequiredMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [{
    'BACKEND': 'django.template.backends.django.DjangoTemplates',
    'DIRS': [BASE_DIR / 'templates'],
    'APP_DIRS': True,
    'OPTIONS': {
        'context_processors': [
            'django.template.context_processors.debug',
            'django.template.context_processors.request',
            'django.contrib.auth.context_processors.auth',
            'django.contrib.messages.context_processors.messages',
        ],
    },
}]

WSGI_APPLICATION = 'config.wsgi.application'

DATABASES = {
    'default': {
        # PostGIS, plus one retry when the pooler drops a connect mid-handshake.
        'ENGINE': 'utils.db_backend',
        'NAME': env('DB_NAME'),
        'USER': env('DB_USER'),
        'PASSWORD': env('DB_PASSWORD'),
        'HOST': env('DB_HOST', default='localhost'),
        'PORT': env('DB_PORT', default='5432'),
        # Supabase sits behind a connection pooler that drops idle or
        # half-open connections. Keepalives notice a dead socket instead of
        # waiting on it, and connect_timeout stops a request hanging when
        # the pooler is unreachable.
        'OPTIONS': {
            'connect_timeout': 10,
            'keepalives': 1,
            'keepalives_idle': 30,
            'keepalives_interval': 10,
            'keepalives_count': 5,
            'sslmode': 'require',
        },
        # Reuse a connection for up to a minute instead of a fresh SSL
        # handshake per request. Health checks replace one the pooler has
        # closed before it is used. The dev server opens a thread per request and
        # never reuses a thread's connection, so development.py turns it off.
        'CONN_MAX_AGE': env.int('DB_CONN_MAX_AGE', default=60),
        'CONN_HEALTH_CHECKS': True,
    }
}

# Supabase's pooler has two modes on the same host. Port 5432 is session
# mode: one pooler client per open connection, at most 15, shared by every
# developer and server. Port 6543 is transaction mode: a server connection
# is borrowed only for each transaction, so many short-lived clients fit.
# Set DB_PORT=6543 (or DB_TRANSACTION_POOLER=true) to use it. Two things
# don't survive between transactions there, so they are switched off:
#   * server-side cursors (named cursors live in the session), and
#   * holding connections open, which only helps when the pooler keeps
#     the session; here each request takes a fresh slot anyway.
DB_TRANSACTION_POOLER = env.bool(
    'DB_TRANSACTION_POOLER', default=str(DATABASES['default']['PORT']) == '6543',
)
if DB_TRANSACTION_POOLER:
    DATABASES['default']['DISABLE_SERVER_SIDE_CURSORS'] = True
    DATABASES['default']['CONN_MAX_AGE'] = 0

# Sessions are read from a cache first and the database only on a miss.
# Every request reads the session to know who is signed in, including the
# notification bell's poll every 30 seconds per open tab, so that was one
# Supabase round trip per request for a row that rarely changes. Writes
# still go to the database, so nobody is signed out when the cache is
# cleared or the server restarts.
#
# File-based rather than in-memory on purpose: every gunicorn worker on the
# machine shares the same files, so signing out (or an admin deactivating
# an account) takes effect in all of them at once. An in-memory cache would
# keep a signed-out session alive in the other workers. A deployment across
# several machines needs a shared cache such as Redis instead.
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.filebased.FileBasedCache',
        'LOCATION': env('CACHE_DIR', default=str(BASE_DIR / '.cache' / 'django')),
        'TIMEOUT': 300,
        'OPTIONS': {'MAX_ENTRIES': 5000},
    }
}
SESSION_ENGINE = 'django.contrib.sessions.backends.cached_db'
# The cookie never outlives the 12-hour cap in utils/session_limits.py
SESSION_COOKIE_AGE = 12 * 60 * 60

AUTH_USER_MODEL = 'accounts.User'

# F1: passwords are hashed with bcrypt. The first hasher is used for every
# new or changed password. The PBKDF2 one stays listed only so accounts
# created before this change can still sign in; Django re-hashes each of
# those with bcrypt the next time its password is entered correctly.
# BCryptSHA256 runs the password through SHA-256 first, so passwords
# longer than bcrypt's 72-byte limit aren't silently cut short.
PASSWORD_HASHERS = [
    'django.contrib.auth.hashers.BCryptSHA256PasswordHasher',
    'django.contrib.auth.hashers.PBKDF2PasswordHasher',
]

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Manila'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# ---------------------------------------------------------------------------
# Where uploaded files live
#
# Incident report photos go to Supabase Storage when the keys below are set,
# and to backend/media/ on this machine when they are not.
#
# The fallback is deliberate. The team shares one database but each person
# runs their own server, so with local files a photo one of us uploads is
# invisible to everyone else -- the path travels in the database, the file
# does not. Supabase Storage fixes that. Keeping the local path working means
# a teammate who has not added the keys yet still has a system that runs,
# rather than a 500 on every upload.
#
# The bucket is private and URLs are signed, with a one-hour life. An
# incident photo shows somebody's house, their street and how bad the damage
# is; a public bucket URL is readable by anyone who ever sees it, forever.
#
# Values come from the Supabase dashboard: Project Settings -> Storage ->
# S3 access keys. Those keys bypass row-level security, so they belong in
# .env on the server and nowhere near the frontend.
# ---------------------------------------------------------------------------
SUPABASE_S3_ENDPOINT = env('SUPABASE_S3_ENDPOINT', default='')
SUPABASE_S3_BUCKET   = env('SUPABASE_S3_BUCKET',   default='')
SUPABASE_S3_KEY      = env('SUPABASE_S3_KEY',      default='')
SUPABASE_S3_SECRET   = env('SUPABASE_S3_SECRET',   default='')
SUPABASE_S3_REGION   = env('SUPABASE_S3_REGION',   default='')

USE_SUPABASE_STORAGE = all([
    SUPABASE_S3_ENDPOINT, SUPABASE_S3_BUCKET,
    SUPABASE_S3_KEY, SUPABASE_S3_SECRET, SUPABASE_S3_REGION,
])

if USE_SUPABASE_STORAGE:
    STORAGES = {
        'default': {'BACKEND': 'storages.backends.s3boto3.S3Boto3Storage'},
        'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
    }

    AWS_S3_ENDPOINT_URL     = SUPABASE_S3_ENDPOINT
    AWS_STORAGE_BUCKET_NAME = SUPABASE_S3_BUCKET
    AWS_ACCESS_KEY_ID       = SUPABASE_S3_KEY
    AWS_SECRET_ACCESS_KEY   = SUPABASE_S3_SECRET
    AWS_S3_REGION_NAME      = SUPABASE_S3_REGION

    AWS_S3_SIGNATURE_VERSION = 's3v4'
    # The Supabase endpoint already carries a path (/storage/v1/s3), so the
    # bucket cannot go in the hostname the way it does on real S3.
    AWS_S3_ADDRESSING_STYLE = 'path'
    # Private bucket: every URL is signed and expires.
    AWS_QUERYSTRING_AUTH   = True
    AWS_QUERYSTRING_EXPIRE = 3600
    # Supabase Storage does not implement S3 ACLs. Sending one makes every
    # upload fail, so django-storages must be told not to.
    AWS_DEFAULT_ACL = None
    # Each report's photo is named after the report id, so a collision would
    # mean two photos for one report. Keep both rather than overwrite.
    AWS_S3_FILE_OVERWRITE = False

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 25,
}

CORS_ALLOWED_ORIGINS = env.list('CORS_ORIGIN', default=['http://localhost:3000'])
CORS_ALLOW_CREDENTIALS = True
# The bell and the approval card mark their timed polls with this header,
# so a tab left open doesn't count as someone working (see session_limits).
from corsheaders.defaults import default_headers  # noqa: E402
CORS_ALLOW_HEADERS = (*default_headers, 'x-geoalert-background')
# Lets the frontend read "your session just ended" on a public page, and
# the map's ETag so a refresh that found nothing new skips re-rendering
CORS_EXPOSE_HEADERS = ['x-geoalert-session-expired', 'etag']

# A reverse proxy in front of Django: trust the address it adds to
# X-Forwarded-For. Off by default, because without a proxy that header is
# whatever the client sends. See utils/login_throttle.py.
BEHIND_PROXY = env.bool('BEHIND_PROXY', default=False)

EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = env('EMAIL_HOST', default='smtp.gmail.com')
EMAIL_PORT = env.int('EMAIL_PORT', default=587)
EMAIL_USE_TLS = True
EMAIL_HOST_USER = env('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = env('EMAIL_HOST_PASSWORD', default='')
DEFAULT_FROM_EMAIL = env('DEFAULT_FROM_EMAIL', default='GeoAlert <no-reply@geoalert.local>')

# Forgot password: a reset link works for 1 hour (and only once, since it
# stops working when the password changes). FRONTEND_URL is where the
# emailed link points: the React app's /reset-password page.
PASSWORD_RESET_TIMEOUT = 3600
FRONTEND_URL = env('FRONTEND_URL', default='http://localhost:3000')


GDAL_LIBRARY_PATH = env('GDAL_LIBRARY_PATH', default=str(
    BASE_DIR / 'venv' / 'Lib' / 'site-packages' / 'osgeo' / 'gdal.dll'
))
GEOS_LIBRARY_PATH = env('GEOS_LIBRARY_PATH', default=str(
    BASE_DIR / 'venv' / 'Lib' / 'site-packages' / 'osgeo' / 'geos_c.dll'
))


CSRF_TRUSTED_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]