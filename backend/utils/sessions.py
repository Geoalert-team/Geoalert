"""
Django's session middleware, except that a request whose session another
request deleted while it ran answers normally instead of failing.

Two requests can share one session: the app's start-up and a page's own
request, the notification bell in another tab. If one of them ends the
session (a logout, an expired session signed out by session_limits, the dev
server's fresh-tab sign-out), the other then tries to save the session it
loaded, and Django answers that with a bare 400 "SessionInterrupted". The
reset-password page showed it as "Some of the details were not accepted".
The session is gone on purpose, so the other request just doesn't save it:
its answer stands, and its next request arrives signed out.
"""
from django.contrib.sessions.exceptions import SessionInterrupted
from django.contrib.sessions.middleware import SessionMiddleware as DjangoSessionMiddleware


class SessionMiddleware(DjangoSessionMiddleware):
    def process_response(self, request, response):
        try:
            return super().process_response(request, response)
        except SessionInterrupted:
            return response
