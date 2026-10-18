"""
F1 session limits: sign out after 30 minutes idle, or 12 hours in total.

A login used to last two weeks, so an officer's session on a shared office
computer stayed open for anyone who sat down after them.

"Idle" means nobody did anything. The notification bell and the approval
card poll every 30 seconds on their own; those requests carry the
X-GeoAlert-Background header and don't count as activity, or a tab left
open would never time out.

Activity is written to the session at most once a minute, so ordinary use
doesn't turn every request into a database write.
"""

import time

from django.contrib.auth import SESSION_KEY, logout
from django.http import JsonResponse

from utils.audit import log_event

# Defaults. A System Administrator can change both from the configuration
# panel (utils/system_settings.py); limits() reads the current values.
IDLE_LIMIT = 30 * 60        # seconds without activity
TOTAL_LIMIT = 12 * 60 * 60  # seconds since signing in
TOUCH_EVERY = 60            # seconds between activity writes

BACKGROUND_HEADER = 'HTTP_X_GEOALERT_BACKGROUND'

# Tells the frontend a session just ended, on responses that still
# succeed: the public map keeps working signed out, but the app should
# know the officer is no longer signed in.
EXPIRED_HEADER = 'X-GeoAlert-Session-Expired'


def start_session_clock(request, now=None):
    """Call right after login(): both limits count from here."""
    now = now or time.time()
    request.session['login_at'] = now
    request.session['last_activity'] = now


def limits():
    """(idle seconds, total seconds) as currently configured."""
    from utils.system_settings import get_setting
    return get_setting('session.idle_minutes') * 60, get_setting('session.total_hours') * 3600


def expired_reason(session, now, idle_limit=None, total_limit=None):
    if idle_limit is None or total_limit is None:
        idle_limit, total_limit = limits()
    login_at = session.get('login_at')
    last = session.get('last_activity')
    if login_at is not None and now - login_at > total_limit:
        return 'total'
    if last is not None and now - last > idle_limit:
        return 'idle'
    return None


def message(reason):
    idle_limit, total_limit = limits()
    if reason == 'idle':
        return (f'You were signed out after {idle_limit // 60} minutes without activity. '
                'Sign in again to continue.')
    hours = total_limit // 3600
    return (f'You were signed out because {hours} hour{"" if hours == 1 else "s"} have passed '
            'since you signed in. Sign in again to continue.')


class SessionLimitMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        session = getattr(request, 'session', None)
        # Only signed-in API requests. Checking the session key rather than
        # request.user avoids loading the user for anonymous map visitors.
        if session is None or not request.path.startswith('/api/') or SESSION_KEY not in session:
            return self.get_response(request)

        now = time.time()
        if 'login_at' not in session:
            # Signed in before these limits existed: start the clock now
            start_session_clock(request, now)

        reason = expired_reason(session, now)
        if reason:
            log_event(request, 'SESSION_EXPIRED', 'app_user', request.user.id,
                      f'{request.user.email}: {reason} limit reached')
            logout(request)
            # Carry on signed out. Public endpoints (the map, sign-in) still
            # answer; ones that need a login get the reason instead of a
            # bare "credentials were not provided".
            response = self.get_response(request)
            if response.status_code in (401, 403):
                return JsonResponse({'error': message(reason), 'code': 'session_expired'}, status=401)
            response[EXPIRED_HEADER] = reason
            return response

        background = request.META.get(BACKGROUND_HEADER) == '1'
        if not background and now - session.get('last_activity', 0) >= TOUCH_EVERY:
            session['last_activity'] = now

        return self.get_response(request)
