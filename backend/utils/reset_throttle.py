"""
Rate limits for the forgot-password endpoints, counted in the Django cache
like utils/login_throttle.py.

A cache outage never blocks a reset: someone locked out of their account
should not also be locked out of getting back in because the cache is down.
"""

from django.core.cache import cache

PREFIX = 'pwreset:'


def allow(key, limit, window):
    """Count one hit for `key`; False once more than `limit` fall within `window` seconds."""
    k = PREFIX + key
    try:
        cache.add(k, 0, window)
        try:
            hits = cache.incr(k)
        except ValueError:  # expired between add and incr
            cache.set(k, 1, window)
            hits = 1
    except Exception:
        return True
    return hits <= limit


def blocked(key, limit):
    """True when `key` already has `limit` or more hits, without counting one."""
    try:
        return (cache.get(PREFIX + key) or 0) >= limit
    except Exception:
        return False
