from .base import *
import os
from pathlib import Path

# GDAL needs PROJ's data files to convert between coordinate systems. This
# pointed at a placeholder path ("C:\\...\\venv"), so any conversion failed
# with "Cannot find proj.db". Use the copy that ships with the GDAL wheel in
# this project's venv, wherever the project lives; an existing PROJ_LIB in
# the environment still wins.
_proj = Path(BASE_DIR) / 'venv' / 'Lib' / 'site-packages' / 'osgeo' / 'data' / 'proj'
if _proj.is_dir():
    os.environ.setdefault('PROJ_LIB', str(_proj))
    os.environ.setdefault('PROJ_DATA', str(_proj))

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
# No persistent database connections under runserver. It handles each
# request on a new thread and never closes that thread's connection, so
# with CONN_MAX_AGE every request strands one until it expires. The
# Supabase pooler allows 15 clients in session mode, shared by everyone
# on the team, and a few seconds of map polling used all of them
# (EMAXCONNSESSION). Gunicorn in production reuses its threads, so the
# setting stays on there.
DATABASES['default']['CONN_MAX_AGE'] = 0
