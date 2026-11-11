"""
Django's session middleware, with two changes for requests that overlap.

Two requests can share one session: the app's start-up and a page's own
request, the notification bell in another tab. If one of them ends the
session (a logout, an expired session signed out by session_limits), the other
then tries to save the session it loaded, and Django answers that with a bare
400 "SessionInterrupted". The reset-password page showed it as "Some of the
details were not accepted". The session is gone on purpose, so the other
request just doesn't save it: its answer stands, and its next request arrives
signed out.

A request can also leave the browser just before a sign-in replaces its
session and answer just after. Django clears the cookie of any request whose
session no longer exists, and by then the browser's cookie is the new
session's, so the person was signed out moments after signing in, with no
logout anywhere to show for it. Only a request that ended the session itself
clears the cookie now.
"""
from django.conf import settings
from django.contrib.sessions.exceptions import SessionInterrupted
from django.contrib.sessions.middleware import SessionMiddleware as DjangoSessionMiddleware
from django.utils.cache import patch_vary_headers


def _cookie_is_out_of_date(request):
    """Sent a session that doesn't exist, and didn't end it here (flush() marks the session modified)."""
    session = getattr(request, 'session', None)
    return (session is not None and settings.SESSION_COOKIE_NAME in request.COOKIES
            and session.is_empty() and not session.modified)


class SessionMiddleware(DjangoSessionMiddleware):
    def process_response(self, request, response):
        if _cookie_is_out_of_date(request):
            patch_vary_headers(response, ('Cookie',))
            return response
        try:
            return super().process_response(request, response)
        except SessionInterrupted:
            return response
