"""
A request whose session another request deleted while it ran (a logout in a
second tab, an expired session ended by a parallel request) answers normally, signed out, instead of Django's bare
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


class StaleCookieTests(TestCase):
    """
    A request still carrying a session that has since been replaced (it left
    the browser before a new sign-in finished) must not clear the cookie: by
    the time its answer lands, the browser's cookie is the new session's.
    """

    def request_with_cookie(self, key):
        request = RequestFactory().get('/api/notifications/')
        request.COOKIES[settings.SESSION_COOKIE_NAME] = key
        return request

    def test_an_answer_for_a_replaced_session_leaves_the_cookie_alone(self):
        store = engine.SessionStore()
        store['_auth_user_id'] = '1'
        store.create()
        key = store.session_key
        engine.SessionStore(session_key=key).delete()  # a new sign-in replaced it

        def view(req):
            req.session.get('_auth_user_id')  # the request looks up who it is
            return HttpResponse('ok')

        response = SessionMiddleware(view)(self.request_with_cookie(key))
        self.assertNotIn(settings.SESSION_COOKIE_NAME, response.cookies)
        self.assertEqual(response['Vary'], 'Cookie')

    def test_signing_out_still_clears_the_cookie(self):
        store = engine.SessionStore()
        store['_auth_user_id'] = '1'
        store.create()

        def view(req):
            req.session.flush()
            return HttpResponse('ok')

        response = SessionMiddleware(view)(self.request_with_cookie(store.session_key))
        self.assertEqual(response.cookies[settings.SESSION_COOKIE_NAME].value, '')
