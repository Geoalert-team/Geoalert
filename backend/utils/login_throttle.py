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

Counted in the security cache (utils/security_cache.py), which the public
map can't fill up and flush.
"""

import ipaddress
import time

from django.conf import settings

from utils.proxy import from_trusted_proxy
from utils.security_cache import SecurityCacheProxy

MAX_FAILS = 20
WINDOW = 15 * 60   # seconds the failures are counted over
BLOCK = 15 * 60    # seconds the address is refused for

BLOCKED = {
    'error': 'Too many failed sign-ins from this network. Try again in 15 minutes.',
    'code': 'ip_throttled',
}

cache = SecurityCacheProxy()


def valid_ip(value):
    """The address in `value` written the standard way, or None when it isn't one."""
    value = (value or '').strip()
    if not value:
        return None
    try:
        return str(ipaddress.ip_address(value))
    except ValueError:
        pass
    # Some proxies add the port: "203.0.113.5:4711", "[2001:db8::1]:443"
    if value.startswith('[') and ']' in value:
        value = value[1:value.index(']')]
    else:
        host, sep, port = value.rpartition(':')
        if not (sep and port.isdigit() and '.' in host):
            return None
        value = host
    try:
        return str(ipaddress.ip_address(value))
    except ValueError:
        return None


def throttle_ip(request):
    """
    The address to count against.

    X-Forwarded-For is whatever the client chose to send, so trusting it
    would let an attacker pick a new "address" per try. Only behind a
    reverse proxy (settings.BEHIND_PROXY) is the last entry trusted: that
    is the one the proxy itself added. With Vercel in front of that proxy
    (settings.FORWARDED_FOR_TRUST_FIRST) it is the first entry, which Vercel
    overwrites with the visitor's address, but only on requests that came
    through Vercel (utils/proxy.py): one sent straight to Render wrote that
    entry itself. Otherwise REMOTE_ADDR, which the client can't choose.

    Never anything but a real address (or 'unknown'): a made-up entry would
    be a fresh count per try, and the audit log's address column refuses
    anything else.
    """
    remote = valid_ip(request.META.get('REMOTE_ADDR')) or 'unknown'
    if not getattr(settings, 'BEHIND_PROXY', False):
        return remote
    entries = [e.strip() for e in (request.META.get('HTTP_X_FORWARDED_FOR') or '').split(',') if e.strip()]
    if not entries:
        return remote
    first = getattr(settings, 'FORWARDED_FOR_TRUST_FIRST', False) and from_trusted_proxy(request)
    return valid_ip(entries[0] if first else entries[-1]) or remote


def _keys(request):
    ip = throttle_ip(request)
    return f'geoalert:ip-fails:{ip}', f'geoalert:ip-block:{ip}'


def is_blocked(request):
    try:
        return bool(cache.get(_keys(request)[1]))
    except Exception:
        return False  # a cache outage must not stop anyone signing in


def record_failure(request):
    """
    Count one failed sign-in. Returns True when this one starts a block.

    Each count is stored with the end of its window and kept for exactly the
    time left in it (as utils/reset_throttle.py does). cache.incr() would be
    wrong on a file cache: it rewrites the value with the cache's default
    300-second timeout, so "20 in 15 minutes" became "20 with no 5-minute gap".
    """
    fails_key, block_key = _keys(request)
    try:
        now = time.time()
        value = cache.get(fails_key)
        live = isinstance(value, tuple) and len(value) == 2 and now < value[1]
        count, end = value if live else (0, now + WINDOW)
        count += 1
        if count >= MAX_FAILS:
            cache.set(block_key, True, BLOCK)
            cache.delete(fails_key)
            return True
        cache.set(fails_key, (count, end), max(1, int(end - now) + 1))
    except Exception:
        pass
    return False
