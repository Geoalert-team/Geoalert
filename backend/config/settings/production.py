from .base import *

DEBUG = False

SECURE_SSL_REDIRECT = True
# The proxy in front (Nginx or Render) ends HTTPS and passes requests on over
# plain HTTP. Only it can set this header, so it is believed only behind a
# proxy (BEHIND_PROXY in base.py).
if BEHIND_PROXY:
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

# Behind Vercel and then Render, the last X-Forwarded-For entry is one of their
# addresses, shared by every visitor, so one person's typos would block
# everyone's sign-in (utils/login_throttle.py). Vercel overwrites the header
# with the visitor's address, which makes the first entry the visitor.
FORWARDED_FOR_TRUST_FIRST = env.bool('FORWARDED_FOR_TRUST_FIRST', default=False)

# Free hosting counts every byte sent, and the map's purok layer is about 1 MB
MIDDLEWARE = ['django.middleware.gzip.GZipMiddleware', *MIDDLEWARE]

# With DEBUG off, Django's own settings print nothing to the console, so a 500
# would leave no trace in the server's log.
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {'console': {'class': 'logging.StreamHandler'}},
    'loggers': {'django.request': {'handlers': ['console'], 'level': 'ERROR', 'propagate': False}},
}