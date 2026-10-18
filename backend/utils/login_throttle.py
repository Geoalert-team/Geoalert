"""
F1 per-address login throttle.

The lockout counts wrong passwords per account, so someone trying one
common password against every account never tripped it: each account saw
only one failure. This counts failures per network address instead, across
all accounts: 20 failed sign-ins (wrong passwords, unknown emails, wrong
2FA codes) from one address within 15 minutes refuses sign-ins from that
address for 15 minutes.

20 is well above what a shared office network produces from typos, so
City Hall staff on one address don't lock each other out.
"""

from django.conf import settings
from django.core.cache import cache

MAX_FAILS = 20
WINDOW = 15 * 60   # seconds the failures are counted over
BLOCK = 15 * 60    # seconds the address is refused for

BLOCKED = {
    'error': 'Too many failed sign-ins from this network. Try again in 15 minutes.',
    'code': 'ip_throttled',
}


def throttle_ip(request):
    """
    The address to count against.

    X-Forwarded-For is whatever the client chose to send, so trusting it
    would let an attacker pick a new "address" per try. Only behind a
    reverse proxy (settings.BEHIND_PROXY) is the last entry trusted: that
    is the one the proxy itself added. Otherwise REMOTE_ADDR, which the
    client can't choose.
    """
    if getattr(settings, 'BEHIND_PROXY', False):
        forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
        if forwarded:
            return forwarded.split(',')[-1].strip()
    return request.META.get('REMOTE_ADDR') or 'unknown'


def _keys(request):
    ip = throttle_ip(request)
    return f'geoalert:ip-fails:{ip}', f'geoalert:ip-block:{ip}'


def is_blocked(request):
    try:
        return bool(cache.get(_keys(request)[1]))
    except Exception:
        return False  # a cache outage must not stop anyone signing in


def record_failure(request):
    """Count one failed sign-in. Returns True when this one starts a block."""
    fails_key, block_key = _keys(request)
    try:
        # add() only starts the window on the first failure, so the window
        # isn't pushed back by every new failure.
        cache.add(fails_key, 0, WINDOW)
        try:
            fails = cache.incr(fails_key)
        except ValueError:  # expired between add() and incr()
            cache.set(fails_key, 1, WINDOW)
            fails = 1
        if fails >= MAX_FAILS:
            cache.set(block_key, True, BLOCK)
            cache.delete(fails_key)
            return True
    except Exception:
        pass
    return False
