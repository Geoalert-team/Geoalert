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
    """Vercel's usual /api/:path* doesn't match an address ending in a slash, and every API address ends in one."""

    def config(self):
        return json.loads((Path(__file__).resolve().parents[2] / 'frontend' / 'vercel.json').read_text(encoding='utf-8'))

    def test_the_api_rule_keeps_the_final_slash(self):
        rule = self.config()['rewrites'][0]
        self.assertEqual(rule['source'], '/api/(.*)')
        self.assertTrue(rule['destination'].endswith('.onrender.com/api/$1'))

    def test_every_other_address_is_a_page_of_the_app(self):
        self.assertEqual(self.config()['rewrites'][-1], {'source': '/(.*)', 'destination': '/index.html'})

    def test_vercel_never_keeps_a_copy_of_an_api_answer(self):
        headers = self.config()['headers'][0]
        self.assertEqual(headers['source'], '/api/(.*)')
        self.assertIn({'key': 'x-vercel-enable-rewrite-caching', 'value': '0'}, headers['headers'])


class AdminAuditAddressTests(TestCase):
    @override_settings(BEHIND_PROXY=True)
    def test_admin_actions_log_the_visitor_not_the_proxy(self):
        request = RequestFactory().get('/', REMOTE_ADDR='127.0.0.1', HTTP_X_FORWARDED_FOR='203.0.113.9')
        log_action(None, 'TEST', request=request)
        self.assertEqual(AuditLog.objects.get(action='TEST').ip_address, '203.0.113.9')
