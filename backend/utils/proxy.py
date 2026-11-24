"""
Telling the website's traffic from requests sent straight to the backend.

Vercel serves the website and forwards /api/ to Render (frontend/vercel.json),
writing the visitor's address as the first X-Forwarded-For entry. But the
Render address is public too, and a request sent straight to it writes that
first entry itself: believing it let anyone pick a new "address" per try and
get past the sign-in throttle, or put a fake address in the audit log
(security audit GA-01).

So Vercel also adds a secret header (X-GeoAlert-Proxy, from its
GEOALERT_PROXY_SECRET project variable) that a visitor can't supply: Vercel
replaces any copy the visitor sends. With settings.PROXY_SECRET set to the
same value, only requests carrying it are taken as the website's.

  * from_trusted_proxy(): may this request's first X-Forwarded-For entry be
    believed? Without PROXY_SECRET it answers True, as before, so deploying
    this before the secret is configured on both sides changes nothing.
  * ProxySecretMiddleware: with REQUIRE_PROXY_SECRET on as well, /api/
    requests without the secret are refused, except PROXY_SECRET_EXEMPT (the
    keep-awake cron job calls /api/hazards/ on Render directly, and the
    retraining job may call its two token-guarded endpoints there too).
"""
from django.conf import settings
from django.http import JsonResponse
from django.utils.crypto import constant_time_compare

HEADER = 'HTTP_X_GEOALERT_PROXY'

DIRECT_REFUSED = {
    'error': 'Use the GeoAlert website.',
    'code': 'direct_access_refused',
}


def secret_configured():
    return bool(getattr(settings, 'PROXY_SECRET', ''))


def carries_secret(request):
    """The request carries the configured secret (False when none is configured)."""
    secret = getattr(settings, 'PROXY_SECRET', '')
    return bool(secret) and constant_time_compare(request.META.get(HEADER, ''), secret)


def from_trusted_proxy(request):
    """Whether the first X-Forwarded-For entry was written by the website's proxy."""
    if not secret_configured():
        return True  # the behaviour before PROXY_SECRET existed
    return carries_secret(request)


class ProxySecretMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Exempt paths are exact (not prefixes), and have their own guard or
        # none needed: the public hazard list, and the retraining job's two
        # endpoints, which check its bearer token (apps/history/job_auth.py)
        if (getattr(settings, 'REQUIRE_PROXY_SECRET', False) and secret_configured()
                and request.path.startswith('/api/') and not carries_secret(request)
                and request.path not in getattr(settings, 'PROXY_SECRET_EXEMPT', ())):
            return JsonResponse(DIRECT_REFUSED, status=403)
        return self.get_response(request)
