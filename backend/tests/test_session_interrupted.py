"""
A request whose session another request deleted while it ran (a logout in a
second tab, an expired session ended by a parallel request, the dev server's
fresh-tab sign-out) answers normally, signed out, instead of Django's bare
400 "SessionInterrupted": the reset-password page and the app's start-up
showed that 400 as an error.
"""
from importlib import import_module

from django.conf import settings
from django.http import HttpResponse
from django.test import RequestFactory, TestCase

from utils.sessions import SessionMiddleware

engine = import_module(settings.SESSION_ENGINE)


class ConcurrentLogoutTests(TestCase):
    def request_with_session(self):
        store = engine.SessionStore()
        store['last_activity'] = 0
        store.create()
        request = RequestFactory().get('/api/auth/csrf/')
        request.COOKIES[settings.SESSION_COOKIE_NAME] = store.session_key
        return request, store.session_key

    def test_a_session_deleted_mid_request_still_answers(self):
        request, key = self.request_with_session()

        def view(req):
            req.session['last_activity'] = 1             # this request touches its session
            engine.SessionStore(session_key=key).delete()  # meanwhile another request signs out
            return HttpResponse('ok')

        response = SessionMiddleware(view)(request)
        self.assertEqual((response.status_code, response.content), (200, b'ok'))

    def test_a_session_still_saves_normally(self):
        request, key = self.request_with_session()

        def view(req):
            req.session['last_activity'] = 42
            return HttpResponse('ok')

        SessionMiddleware(view)(request)
        self.assertEqual(engine.SessionStore(session_key=key).load()['last_activity'], 42)
