"""
Where sign-in throttles, unknown-email lockouts, password-reset limits and
used 2FA codes are counted.

A cache of their own ('security' in settings.CACHES). The default cache also
holds the public map's answers, and anyone can fill it by asking for the map
with a different query string each time. A full file cache deletes a random
third of its entries, so blocked addresses and lockouts used to disappear with
them (security audit GA-07). Nothing public writes to this one.

Falls back to the default cache where no 'security' cache is configured, as
in tests that swap CACHES for an in-memory one.
"""
from django.core.cache import caches
from django.core.cache.backends.base import InvalidCacheBackendError


def security_cache():
    try:
        return caches['security']
    except InvalidCacheBackendError:
        return caches['default']


class SecurityCacheProxy:
    """
    Stands in for a module's `cache`: every use looks up security_cache()
    again, so settings swapped by a test apply, and a test can still replace
    the module attribute or patch a method on it.
    """
    def __getattr__(self, name):
        return getattr(security_cache(), name)
