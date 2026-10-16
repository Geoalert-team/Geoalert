from .base import *
import os
os.environ.setdefault('PROJ_LIB', r'C:\...\venv\Lib\site-packages\osgeo\data\proj')

DEBUG = True

ALLOWED_HOSTS = ['*']

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {'console': {'class': 'logging.StreamHandler'}},
    'root': {'handlers': ['console'], 'level': 'DEBUG'},
}

SESSION_COOKIE_SAMESITE = 'Lax'
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_SECURE = False