from django.test import SimpleTestCase

from utils.session_limits import IDLE_LIMIT, TOTAL_LIMIT, expired_reason

NOW = 1_000_000.0


class ExpiredReasonTests(SimpleTestCase):
    def test_active_session_is_fine(self):
        self.assertIsNone(expired_reason({'login_at': NOW - 3600, 'last_activity': NOW - 60}, NOW, IDLE_LIMIT, TOTAL_LIMIT))

    def test_idle_too_long(self):
        self.assertEqual(expired_reason({'login_at': NOW - 3600, 'last_activity': NOW - IDLE_LIMIT - 1}, NOW, IDLE_LIMIT, TOTAL_LIMIT), 'idle')

    def test_signed_in_too_long_even_if_active(self):
        self.assertEqual(expired_reason({'login_at': NOW - TOTAL_LIMIT - 1, 'last_activity': NOW}, NOW, IDLE_LIMIT, TOTAL_LIMIT), 'total')

    def test_session_from_before_the_limits(self):
        self.assertIsNone(expired_reason({}, NOW, IDLE_LIMIT, TOTAL_LIMIT))
