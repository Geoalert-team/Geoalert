"""
Settings a System Administrator can change from the dashboard (F8 System
configuration panel), stored in the ERD's system_config table.

Each setting has a default, an allowed range and a unit. Code reads them
with get_setting(key); a value nobody has changed, a value outside its
range, or a database that cannot be reached all fall back to the default,
so a configuration problem can never lock everyone out or stop alerts.

Values are cached for CACHE_SECONDS, so a change takes effect within a
minute without a restart and without a query on every request.
"""

from django.core.cache import cache

CACHE_SECONDS = 60
_CACHE_KEY = 'geoalert:system-settings'

# key: (default, minimum, maximum, unit, label, help)
SETTINGS = {
    'auth.max_failed_logins': (
        5, 3, 10, 'attempts', 'Wrong passwords before lockout',
        'An account is locked after this many wrong passwords in a row.',
    ),
    'auth.lock_minutes': (
        15, 5, 120, 'minutes', 'Lockout length',
        'How long a locked account stays locked.',
    ),
    'session.idle_minutes': (
        30, 5, 240, 'minutes', 'Sign out after inactivity',
        'Staff are signed out after this long without using the system.',
    ),
    'session.total_hours': (
        12, 1, 24, 'hours', 'Longest session',
        'Staff must sign in again after this long, even when active.',
    ),
    'alerts.approval_minutes': (
        10, 2, 60, 'minutes', 'Extreme alert approval window',
        'An Extreme alert waits this long for a second officer, then goes out on its own.',
    ),
    'alerts.remind_after_minutes': (
        15, 5, 120, 'minutes', 'Unread Extreme alert reminder',
        'Barangays that have not opened an Extreme alert after this long are reminded.',
    ),
}


def default(key):
    return SETTINGS[key][0]


def validate(key, value):
    """The value as an int within range, or raise ValueError with a message."""
    if key not in SETTINGS:
        raise ValueError(f'Unknown setting: {key}')
    dflt, lo, hi, unit, label, _ = SETTINGS[key]
    try:
        number = int(value)
        if str(number) != str(value).strip() and float(value) != number:
            raise ValueError
    except (TypeError, ValueError):
        raise ValueError(f'{label} must be a whole number.')
    if not lo <= number <= hi:
        raise ValueError(f'{label} must be between {lo} and {hi} {unit}.')
    return number


def _load():
    """{key: value} of stored settings, from the cache or the database."""
    try:
        stored = cache.get(_CACHE_KEY)
    except Exception:
        stored = None
    if stored is not None:
        return stored
    try:
        from apps.admin_dashboard.models import SystemConfig
        stored = dict(SystemConfig.objects.filter(key__in=SETTINGS).values_list('key', 'value'))
    except Exception:
        return {}  # no database (tests, outage): defaults
    try:
        cache.set(_CACHE_KEY, stored, CACHE_SECONDS)
    except Exception:
        pass
    return stored


def get_setting(key):
    """The current value of a setting, or its default when unset or invalid."""
    raw = _load().get(key)
    if raw in (None, ''):
        return default(key)
    try:
        return validate(key, raw)
    except ValueError:
        return default(key)


def all_settings():
    """Every setting with its current value and limits, for the admin panel."""
    stored = _load()
    out = []
    for key, (dflt, lo, hi, unit, label, help_text) in SETTINGS.items():
        out.append({
            'key': key,
            'value': get_setting(key),
            'default': dflt,
            'min': lo,
            'max': hi,
            'unit': unit,
            'label': label,
            'help': help_text,
            'is_default': stored.get(key) in (None, ''),
        })
    return out


def forget_cache():
    try:
        cache.delete(_CACHE_KEY)
    except Exception:
        pass
