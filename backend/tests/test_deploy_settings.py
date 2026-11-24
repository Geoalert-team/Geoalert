"""
Running behind Nginx, which ends HTTPS and passes requests on over plain HTTP.
Django has to be told who to believe, or HTTPS pages redirect for ever and
every visitor looks like 127.0.0.1 in the audit log.
"""
import importlib
import json
import os
import sys
from pathlib import Path
from unittest import mock

from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings

from apps.admin_dashboard.models import AuditLog
from apps.admin_dashboard.views import log_action
from utils.audit import client_ip


class ProductionSettingsTests(SimpleTestCase):
    def production(self, **env):
        import config.settings.base as base
        self.addCleanup(importlib.reload, base)
        with mock.patch.dict(os.environ, {'SECRET_KEY': 'k' * 60, **env}):
            importlib.reload(base)
            sys.modules.pop('config.settings.production', None)  # a reload would keep old names
            return importlib.import_module('config.settings.production')

    def test_behind_a_proxy_https_is_read_from_the_header_it_sets(self):
        settings = self.production(BEHIND_PROXY='True')
        self.assertEqual(settings.SECURE_PROXY_SSL_HEADER, ('HTTP_X_FORWARDED_PROTO', 'https'))

    def test_without_a_proxy_that_header_is_not_believed(self):
        settings = self.production(BEHIND_PROXY='False')
        self.assertFalse(hasattr(settings, 'SECURE_PROXY_SSL_HEADER'))

    def test_trusted_origins_come_from_the_environment(self):
        settings = self.production(CSRF_TRUSTED_ORIGINS='https://geoalert.example,https://www.geoalert.example')
        self.assertEqual(settings.CSRF_TRUSTED_ORIGINS, ['https://geoalert.example', 'https://www.geoalert.example'])

    def test_answers_are_compressed(self):
        self.assertEqual(self.production().MIDDLEWARE[0], 'django.middleware.gzip.GZipMiddleware')

    def test_the_first_forwarded_address_is_believed_only_when_asked(self):
        self.assertFalse(self.production().FORWARDED_FOR_TRUST_FIRST)
        self.assertTrue(self.production(FORWARDED_FOR_TRUST_FIRST='True').FORWARDED_FOR_TRUST_FIRST)

    def test_production_answers_json_only(self):
        renderers = self.production().REST_FRAMEWORK['DEFAULT_RENDERER_CLASSES']
        self.assertEqual(renderers, ['rest_framework.renderers.JSONRenderer'])

    def test_django_admin_is_off_unless_asked_for(self):
        self.assertFalse(self.production().DJANGO_ADMIN_ENABLED)
        self.assertTrue(self.production(DJANGO_ADMIN_ENABLED='True').DJANGO_ADMIN_ENABLED)

    def test_a_server_error_reaches_the_log(self):
        """With DEBUG off, Django's own settings print nothing to the console."""
        self.assertIn('console', self.production().LOGGING['loggers']['django.request']['handlers'])


class ClientAddressTests(SimpleTestCase):
    def request(self, forwarded=None):
        extra = {'HTTP_X_FORWARDED_FOR': forwarded} if forwarded else {}
        return RequestFactory().get('/', REMOTE_ADDR='127.0.0.1', **extra)

    @override_settings(BEHIND_PROXY=True)
    def test_behind_a_proxy_the_entry_it_added_is_the_visitor(self):
        self.assertEqual(client_ip(self.request('6.6.6.6, 203.0.113.9')), '203.0.113.9')

    @override_settings(BEHIND_PROXY=False)
    def test_without_a_proxy_a_forwarded_header_is_ignored(self):
        self.assertEqual(client_ip(self.request('6.6.6.6')), '127.0.0.1')

    @override_settings(BEHIND_PROXY=True, FORWARDED_FOR_TRUST_FIRST=True)
    def test_behind_vercel_and_render_the_first_entry_is_the_visitor(self):
        # Vercel writes the visitor; the proxies after it add their own addresses
        self.assertEqual(client_ip(self.request('203.0.113.9, 76.76.21.21, 10.0.0.1')), '203.0.113.9')

    @override_settings(BEHIND_PROXY=False, FORWARDED_FOR_TRUST_FIRST=True)
    def test_the_first_entry_still_needs_a_proxy_in_front(self):
        self.assertEqual(client_ip(self.request('6.6.6.6')), '127.0.0.1')


class VercelForwardingTests(SimpleTestCase):
    """
    Vercel's usual /api/:path* doesn't match an address ending in a slash, and every API address ends in one.
    The rules are `routes` (not `rewrites`) because only a route can add the proxy secret header (utils/proxy.py).
    """

    def config(self):
        return json.loads((Path(__file__).resolve().parents[2] / 'frontend' / 'vercel.json').read_text(encoding='utf-8'))

    def api_route(self):
        return next(r for r in self.config()['routes'] if r.get('src') == '/api/(.*)')

    def test_the_api_rule_keeps_the_final_slash(self):
        self.assertTrue(self.api_route()['dest'].endswith('.onrender.com/api/$1'))

    def test_every_other_address_is_a_page_of_the_app(self):
        routes = self.config()['routes']
        self.assertEqual(routes[-2], {'handle': 'filesystem'})  # the built files first
        self.assertEqual(routes[-1], {'src': '/(.*)', 'dest': '/index.html'})

    def test_vercel_never_keeps_a_copy_of_an_api_answer(self):
        self.assertEqual(self.api_route()['headers'], {'x-vercel-enable-rewrite-caching': '0'})

    def test_the_api_route_adds_the_proxy_secret(self):
        [transform] = self.api_route()['transforms']
        self.assertEqual(transform['type'], 'request.headers')
        self.assertEqual(transform['op'], 'set')  # replaces any copy a visitor sends
        self.assertEqual(transform['target'], {'key': 'x-geoalert-proxy'})
        self.assertEqual(transform['args'], '$GEOALERT_PROXY_SECRET')
        self.assertEqual(transform['env'], ['GEOALERT_PROXY_SECRET'])

    def test_the_api_route_comes_before_the_app_fallback(self):
        routes = self.config()['routes']
        self.assertLess(routes.index(self.api_route()), routes.index({'handle': 'filesystem'}))

    def test_the_app_pages_cannot_be_framed(self):
        pages = self.config()['routes'][0]
        self.assertEqual(pages['src'], '/((?!api/).*)')
        self.assertTrue(pages['continue'])
        self.assertEqual(pages['headers']['X-Frame-Options'], 'DENY')
        self.assertIn("frame-ancestors 'none'", pages['headers']['Content-Security-Policy'])


class AdminAuditAddressTests(TestCase):
    @override_settings(BEHIND_PROXY=True)
    def test_admin_actions_log_the_visitor_not_the_proxy(self):
        request = RequestFactory().get('/', REMOTE_ADDR='127.0.0.1', HTTP_X_FORWARDED_FOR='203.0.113.9')
        log_action(None, 'TEST', request=request)
        self.assertEqual(AuditLog.objects.get(action='TEST').ip_address, '203.0.113.9')
