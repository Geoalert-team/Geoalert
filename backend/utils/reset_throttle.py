"""
Rate limits for the forgot-password endpoints, counted in the Django cache.

Each key holds (count, window_end) and is stored for exactly the time left
in its window. Using cache.incr() instead would be wrong on this project's
FileBasedCache: its incr() rewrites the value with the cache's default
TIMEOUT (300 s), so "3 per hour" became "3 per 5 quiet minutes", and every
hit past the limit restarted those 5 minutes, which let someone keep an
account over its limit for good. A fixed window can't be extended.

A cache outage never blocks a reset: someone locked out of their account
should not also be locked out of getting back in because the cache is down.
"""

import time

from django.core.cache import cache

PREFIX = 'pwreset:'


def _read(k, now):
    """(count, window_end) for a live window, or None."""
    value = cache.get(k)
    if isinstance(value, tuple) and len(value) == 2 and now < value[1]:
        return value
    return None  # missing, expired, or left over from an older format


def allow(key, limit, window):
    """Count one hit for `key`; False once more than `limit` fall within its `window` seconds."""
    k = PREFIX + key
    try:
        now = time.time()
        count, end = _read(k, now) or (0, now + window)
        count += 1
        cache.set(k, (count, end), max(1, int(end - now) + 1))
    except Exception:
        return True
    return count <= limit


def blocked(key, limit):
    """True when `key` already has `limit` or more hits in its window, without counting one."""
    try:
        live = _read(PREFIX + key, time.time())
    except Exception:
        return False
    return bool(live) and live[0] >= limit
