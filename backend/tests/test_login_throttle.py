from django.core.cache import cache
from django.test import RequestFactory, SimpleTestCase, override_settings

from utils import login_throttle
from utils.login_throttle import MAX_FAILS, is_blocked, record_failure, throttle_ip

LOCMEM = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache', 'LOCATION': 'throttle-tests'}}


@override_settings(CACHES=LOCMEM)
class LoginThrottleTests(SimpleTestCase):
    def setUp(self):
        cache.clear()
        self.rf = RequestFactory()

    def request(self, ip='203.0.113.5', forwarded=None):
        extra = {'REMOTE_ADDR': ip}
        if forwarded:
            extra['HTTP_X_FORWARDED_FOR'] = forwarded
        return self.rf.post('/api/auth/login/', **extra)

    def test_blocks_after_max_failures(self):
        req = self.request()
        started = [record_failure(req) for _ in range(MAX_FAILS)]
        self.assertEqual(started.count(True), 1)
        self.assertTrue(started[-1])
        self.assertTrue(is_blocked(req))

    def test_one_short_is_not_blocked(self):
        req = self.request()
        for _ in range(MAX_FAILS - 1):
            record_failure(req)
        self.assertFalse(is_blocked(req))

    def test_other_address_unaffected(self):
        for _ in range(MAX_FAILS):
            record_failure(self.request('203.0.113.5'))
        self.assertFalse(is_blocked(self.request('203.0.113.6')))

    @override_settings(BEHIND_PROXY=False)
    def test_forwarded_header_ignored_without_proxy(self):
        # A client choosing its own X-Forwarded-For must not get a fresh count
        self.assertEqual(throttle_ip(self.request('203.0.113.5', forwarded='1.2.3.4')), '203.0.113.5')

    @override_settings(BEHIND_PROXY=True)
    def test_behind_proxy_uses_the_entry_the_proxy_added(self):
        req = self.request('10.0.0.2', forwarded='1.2.3.4, 198.51.100.20')
        self.assertEqual(throttle_ip(req), '198.51.100.20')

    def test_cache_outage_never_blocks(self):
        class Broken:
            def __getattr__(self, name):
                raise RuntimeError('cache down')
        real = login_throttle.cache
        login_throttle.cache = Broken()
        try:
            self.assertFalse(record_failure(self.request()))
            self.assertFalse(is_blocked(self.request()))
        finally:
            login_throttle.cache = real
