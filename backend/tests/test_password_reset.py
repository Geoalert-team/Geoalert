"""Forgot password: rate limits, the reset link and email, and the three endpoints.

SimpleTestCase only: the database is the team's shared server, so lookups,
saves and audit writes are patched out.
"""
from unittest import mock

from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.core.cache import cache
from django.test import SimpleTestCase, override_settings
from django.utils.http import urlsafe_base64_encode

from apps.accounts import password_reset
from apps.accounts.models import User
from utils import reset_throttle

LOCMEM = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}}


@override_settings(CACHES=LOCMEM)
class AllowTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    def test_allows_up_to_the_limit_then_refuses(self):
        self.assertEqual([reset_throttle.allow('k', 3, 60) for _ in range(4)], [True, True, True, False])

    def test_keys_are_counted_separately(self):
        for _ in range(3):
            reset_throttle.allow('a', 3, 60)
        self.assertTrue(reset_throttle.allow('b', 3, 60))

    def test_a_cache_fault_never_blocks_a_reset(self):
        with mock.patch.object(reset_throttle.cache, 'get', side_effect=RuntimeError):
            self.assertTrue(reset_throttle.allow('k', 1, 60))
        with mock.patch.object(reset_throttle.cache, 'get', side_effect=RuntimeError):
            self.assertFalse(reset_throttle.blocked('k', 1))

    def test_blocked_looks_without_counting(self):
        reset_throttle.allow('k', 2, 60)
        self.assertFalse(reset_throttle.blocked('k', 2))
        self.assertFalse(reset_throttle.blocked('k', 2))  # still one hit
        reset_throttle.allow('k', 2, 60)
        self.assertTrue(reset_throttle.blocked('k', 2))


@override_settings(FRONTEND_URL='https://geoalert.example/')
class ResetLinkTests(SimpleTestCase):
    def setUp(self):
        self.user = User(email='juan@example.com', full_name='Juan Dela Cruz')
        self.user.set_password('Old-pass-2026')

    def test_link_points_at_the_reset_page_and_its_token_verifies(self):
        link = password_reset.reset_link(self.user)
        prefix = f'https://geoalert.example/reset-password/{password_reset.uid_for(self.user)}/'
        self.assertTrue(link.startswith(prefix), link)
        self.assertTrue(default_token_generator.check_token(self.user, link[len(prefix):]))

    def test_a_token_stops_working_once_the_password_changes(self):
        token = password_reset.reset_link(self.user).rsplit('/', 1)[1]
        self.user.set_password('New-pass-2026')
        self.assertFalse(default_token_generator.check_token(self.user, token))

    def test_the_email_names_the_person_the_link_and_the_hour(self):
        subject, body = password_reset.reset_email(self.user, 'https://x/reset-password/u/t')
        self.assertEqual(subject, 'Reset your GeoAlert password')
        self.assertIn('Hello Juan Dela Cruz,', body)
        self.assertIn('https://x/reset-password/u/t', body)
        self.assertIn('within 1 hour', body)
        self.assertIn("If you didn't ask for this, ignore this email; your password stays the same.", body)


class UidTests(SimpleTestCase):
    def test_garbage_uids_are_none_without_a_query(self):
        with mock.patch.object(User.objects, 'filter') as q:
            for bad in (None, '', 'abc', '!!!', 123, urlsafe_base64_encode(b'not-a-uuid')):
                self.assertIsNone(password_reset.user_from_uid(bad), bad)
            q.assert_not_called()

    def test_reset_timeout_is_one_hour(self):
        self.assertEqual(settings.PASSWORD_RESET_TIMEOUT, 3600)

    def test_lookup_by_email_is_case_insensitive_and_active_only(self):
        with mock.patch.object(User.objects, 'filter') as q:
            password_reset.find_active_user('Juan@Example.com')
        q.assert_called_once_with(email__iexact='Juan@Example.com', is_active=True)


# ---------- The three endpoints ----------
from smtplib import SMTPException  # noqa: E402

from django.utils import timezone  # noqa: E402
from rest_framework.test import APIRequestFactory  # noqa: E402

from apps.accounts import views  # noqa: E402

factory = APIRequestFactory()
V = 'apps.accounts.views.'


def post(view, path, body):
    return view.as_view()(factory.post(path, body, format='json'))


def a_user(**extra):
    user = User(email='juan@example.com', full_name='Juan Dela Cruz', is_active=True, **extra)
    user.set_password('Old-pass-2026')
    return user


def actions(log):
    return [c.args[1] for c in log.call_args_list]


@override_settings(CACHES=LOCMEM)
# The email is sent on a background thread; run that job inline here so the
# assertions don't race it (RequestTimingTests checks the ordering itself)
@mock.patch(V + 'run_in_background', new=lambda job: job())
@mock.patch(V + 'connection', new=mock.MagicMock())
@mock.patch(V + 'log_event')
@mock.patch(V + 'send_reset_email')
@mock.patch(V + 'find_active_user')
class RequestViewTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    def ask(self, body):
        return post(views.PasswordResetRequestView, '/api/auth/password-reset/', body)

    def test_unknown_email_gets_the_generic_reply_and_no_email(self, find, send, log):
        find.return_value = None
        res = self.ask({'email': 'nobody@example.com'})
        self.assertEqual((res.status_code, res.data['message']), (200, password_reset.GENERIC_REPLY))
        send.assert_not_called()
        log.assert_not_called()

    def test_known_email_gets_the_same_reply_and_an_email(self, find, send, log):
        user = a_user()
        find.return_value = user
        res = self.ask({'email': 'juan@example.com'})
        self.assertEqual((res.status_code, res.data['message']), (200, password_reset.GENERIC_REPLY))
        send.assert_called_once_with(user)
        self.assertEqual(actions(log), ['PASSWORD_RESET_REQUESTED'])

    def test_the_email_is_trimmed_before_the_lookup(self, find, send, log):
        find.return_value = None
        self.ask({'email': ' Juan@Example.com '})
        find.assert_called_once_with('Juan@Example.com')

    def test_missing_or_odd_email_values_never_fail(self, find, send, log):
        for body in ({}, {'email': ''}, {'email': '   '}, {'email': 123}, {'email': ['a']}):
            res = self.ask(body)
            self.assertEqual((res.status_code, res.data['message']), (200, password_reset.GENERIC_REPLY), body)
        find.assert_not_called()

    def test_a_failed_send_still_answers_generically_and_is_logged(self, find, send, log):
        find.return_value = a_user()
        send.side_effect = SMTPException('auth failed')
        res = self.ask({'email': 'juan@example.com'})
        self.assertEqual((res.status_code, res.data['message']), (200, password_reset.GENERIC_REPLY))
        self.assertEqual(actions(log), ['PASSWORD_RESET_EMAIL_FAILED'])

    def test_three_emails_per_account_per_hour(self, find, send, log):
        find.return_value = a_user()
        replies = [self.ask({'email': 'juan@example.com'}).data['message'] for _ in range(4)]
        self.assertEqual(send.call_count, 3)
        self.assertEqual(set(replies), {password_reset.GENERIC_REPLY})

    def test_ten_requests_per_address_then_429(self, find, send, log):
        find.return_value = None
        codes = [self.ask({'email': f'n{i}@example.com'}).status_code for i in range(11)]
        self.assertEqual(codes[:10], [200] * 10)
        res = self.ask({'email': 'n@example.com'})
        self.assertEqual((codes[10], res.data['error']), (429, password_reset.LIMIT_REPLY))


@override_settings(CACHES=LOCMEM)
@mock.patch(V + 'user_from_uid')
class CheckViewTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    def check(self, token):
        return post(views.PasswordResetCheckView, '/api/auth/password-reset/check/', {'uid': 'u', 'token': token})

    def test_a_good_link_is_valid(self, from_uid):
        user = a_user()
        from_uid.return_value = user
        res = self.check(default_token_generator.make_token(user))
        self.assertEqual((res.status_code, res.data), (200, {'valid': True}))

    def test_bad_or_odd_links_are_invalid(self, from_uid):
        user = a_user()
        for found, token in ((None, 'x'), (user, 'wrong'), (user, 123), (user, None)):
            from_uid.return_value = found
            res = self.check(token)
            self.assertEqual((res.status_code, res.data), (200, {'valid': False}), token)


@override_settings(CACHES=LOCMEM)
@mock.patch.object(User, 'save')
@mock.patch(V + 'log_event')
@mock.patch(V + 'user_from_uid')
class ConfirmViewTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    def confirm(self, token, password='Fresh-Harbor-2026'):
        return post(views.PasswordResetConfirmView, '/api/auth/password-reset/confirm/',
                    {'uid': 'u', 'token': token, 'new_password': password})

    def test_a_bad_link_is_refused(self, from_uid, log, save):
        from_uid.return_value = a_user()
        res = self.confirm('wrong')
        self.assertEqual((res.status_code, res.data['error']), (400, password_reset.BAD_LINK))
        self.assertEqual(actions(log), ['PASSWORD_RESET_FAILED'])
        save.assert_not_called()

    def test_an_unknown_account_is_refused_like_a_bad_link(self, from_uid, log, save):
        from_uid.return_value = None
        res = self.confirm('anything')
        self.assertEqual((res.status_code, res.data['error']), (400, password_reset.BAD_LINK))
        log.assert_not_called()

    def test_a_weak_password_is_refused_with_the_rules(self, from_uid, log, save):
        user = a_user()
        from_uid.return_value = user
        res = self.confirm(default_token_generator.make_token(user), password='12345678')
        self.assertEqual(res.status_code, 400)
        self.assertIn('entirely numeric', res.data['error'])
        save.assert_not_called()

    def test_success_sets_the_password_and_clears_flags_and_lockout(self, from_uid, log, save):
        user = a_user(must_change_password=True, failed_login_count=5, locked_until=timezone.now())
        from_uid.return_value = user
        res = self.confirm(default_token_generator.make_token(user))
        self.assertEqual((res.status_code, res.data['message']), (200, password_reset.DONE_REPLY))
        self.assertTrue(user.check_password('Fresh-Harbor-2026'))
        self.assertEqual((user.must_change_password, user.failed_login_count, user.locked_until), (False, 0, None))
        save.assert_called_once()
        self.assertEqual(actions(log), ['PASSWORD_RESET_DONE'])

    def test_twenty_failures_per_address_then_429(self, from_uid, log, save):
        from_uid.return_value = a_user()
        codes = [self.confirm('wrong').status_code for _ in range(21)]
        self.assertEqual((codes[:20], codes[20]), ([400] * 20, 429))


@override_settings(CACHES=LOCMEM)
@mock.patch(V + 'user_from_uid')
class CheckSharesTheLimitTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    def test_failed_checks_count_toward_the_same_limit_as_confirm(self, from_uid):
        from_uid.return_value = a_user()
        for _ in range(20):
            post(views.PasswordResetCheckView, '/api/auth/password-reset/check/', {'uid': 'u', 'token': 'wrong'})
        res = post(views.PasswordResetCheckView, '/api/auth/password-reset/check/', {'uid': 'u', 'token': 'wrong'})
        self.assertEqual((res.status_code, res.data['error']), (429, password_reset.ATTEMPTS_REPLY))



# ---------- Fixes from the final review ----------
import tempfile  # noqa: E402
import time  # noqa: E402


class ThrottleWindowOnTheRealCacheTests(SimpleTestCase):
    """The project runs FileBasedCache with TIMEOUT 300; LocMem hid that incr() reset it."""

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.cfg = override_settings(CACHES={'default': {
            'BACKEND': 'django.core.cache.backends.filebased.FileBasedCache', 'LOCATION': self.dir, 'TIMEOUT': 300}})
        self.cfg.enable()
        cache.clear()

    def tearDown(self):
        self.cfg.disable()

    def test_the_window_outlives_the_cache_default_timeout(self):
        t0 = time.time()
        with mock.patch('time.time', return_value=t0):
            for _ in range(3):
                reset_throttle.allow('k', 3, 3600)
        with mock.patch('time.time', return_value=t0 + 400):
            self.assertTrue(reset_throttle.blocked('k', 3))
            self.assertFalse(reset_throttle.allow('k', 3, 3600))

    def test_hits_past_the_limit_do_not_extend_the_window(self):
        t0 = time.time()
        with mock.patch('time.time', return_value=t0):
            for _ in range(3):
                reset_throttle.allow('k', 3, 3600)
        with mock.patch('time.time', return_value=t0 + 3000):
            self.assertFalse(reset_throttle.allow('k', 3, 3600))
        with mock.patch('time.time', return_value=t0 + 3601):
            self.assertTrue(reset_throttle.allow('k', 3, 3600))


@override_settings(CACHES=LOCMEM)
@mock.patch(V + 'log_event')
@mock.patch(V + 'send_reset_email')
@mock.patch(V + 'find_active_user')
class RequestTimingTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    def test_the_reply_goes_out_before_the_email_is_sent(self, find, send, log):
        find.return_value = a_user()
        jobs = []
        with mock.patch(V + 'run_in_background', side_effect=jobs.append), mock.patch(V + 'connection') as conn:
            res = post(views.PasswordResetRequestView, '/api/auth/password-reset/', {'email': 'juan@example.com'})
            self.assertEqual((res.status_code, res.data['message']), (200, password_reset.GENERIC_REPLY))
            send.assert_not_called()          # nothing slow happened before the reply
            log.assert_not_called()
            self.assertEqual(len(jobs), 1)
            jobs[0]()                         # the background job sends, logs, then frees its connection
        send.assert_called_once()
        self.assertEqual(actions(log), ['PASSWORD_RESET_REQUESTED'])
        conn.close.assert_called_once()

    def test_unknown_emails_count_against_the_same_per_email_limit(self, find, send, log):
        find.return_value = None
        for _ in range(3):
            post(views.PasswordResetRequestView, '/api/auth/password-reset/', {'email': 'Nobody@Example.com'})
        post(views.PasswordResetRequestView, '/api/auth/password-reset/', {'email': 'nobody@example.com'})
        self.assertEqual(find.call_count, 3)  # the 4th never reached the database


@override_settings(CACHES=LOCMEM)
@mock.patch.object(User, 'save')
@mock.patch(V + 'log_event')
@mock.patch(V + 'user_from_uid')
class ConfirmFixTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    def confirm(self, user, password):
        return post(views.PasswordResetConfirmView, '/api/auth/password-reset/confirm/',
                    {'uid': 'u', 'token': default_token_generator.make_token(user), 'new_password': password})

    def test_the_current_password_is_refused_like_change_password_does(self, from_uid, log, save):
        user = a_user(must_change_password=True)   # 'Old-pass-2026' is the admin-set password
        from_uid.return_value = user
        res = self.confirm(user, 'Old-pass-2026')
        self.assertEqual((res.status_code, res.data['error']),
                         (400, 'Choose a password different from your current one.'))
        self.assertTrue(user.must_change_password)
        save.assert_not_called()

    def test_rejected_passwords_do_not_count_toward_the_guessing_limit(self, from_uid, log, save):
        user = a_user()
        from_uid.return_value = user
        for _ in range(25):
            self.assertEqual(self.confirm(user, '12345678').status_code, 400)
        self.assertEqual(self.confirm(user, 'Fresh-Harbor-2026').status_code, 200)

    def test_too_many_failed_attempts_say_so_in_their_own_words(self, from_uid, log, save):
        from_uid.return_value = a_user()
        body = {'uid': 'u', 'token': 'bad', 'new_password': 'x'}
        for _ in range(20):
            post(views.PasswordResetConfirmView, '/api/auth/password-reset/confirm/', body)
        res = post(views.PasswordResetConfirmView, '/api/auth/password-reset/confirm/', body)
        self.assertEqual((res.status_code, res.data['error']),
                         (429, 'Too many attempts. Try again in a little while.'))


class EmailTimeoutTests(SimpleTestCase):
    def test_sending_gives_up_after_a_bounded_time(self):
        self.assertEqual(settings.EMAIL_TIMEOUT, 10)
