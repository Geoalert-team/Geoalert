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

AUTH_USER_MODEL = 'accounts.User'

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

EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = env('EMAIL_HOST', default='smtp.gmail.com')
EMAIL_PORT = env.int('EMAIL_PORT', default=587)
EMAIL_USE_TLS = True
EMAIL_HOST_USER = env('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = env('EMAIL_HOST_PASSWORD', default='')


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