"""Account invites: the token and email, the two public endpoints, login timing, and the admin side.

SimpleTestCase only: the database is the team's shared server, so lookups,
saves and audit writes are patched out.
"""
import re
from datetime import timedelta
from smtplib import SMTPException
from unittest import mock

from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.core.cache import cache
from django.test import SimpleTestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.accounts import emails, invite, password_reset
from apps.accounts import views as auth_views
from apps.accounts.models import Role, User
from apps.admin_dashboard import views as admin_views
from apps.admin_dashboard.serializers import UserCreateSerializer

LOCMEM = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}}
AUTH = 'apps.accounts.views.'
ADMIN = 'apps.admin_dashboard.views.'
factory = APIRequestFactory()
tokens = invite.invite_token_generator


def pending_user(**extra):
    """A new account as the Add a user form leaves it: no password yet."""
    fields = dict(email='juan@example.com', full_name='Juan Dela Cruz', is_active=True,
                  role=Role(id=2, name='DRRMO_Officer'), employee_id='DRRMO-0012')
    fields.update(extra)
    user = User(**fields)
    user.set_unusable_password()
    return user


def admin():
    return User(email='admin@example.com', full_name='Admin', is_active=True, role=Role(id=1, name='System_Admin'))


def actions(log):
    return [c.args[1] for c in log.call_args_list]


def post(view, path, body, user=None, **kwargs):
    request = factory.post(path, body, format='json')
    if user is not None:
        force_authenticate(request, user=user)
    return view.as_view()(request, **kwargs)


# ---------- The token and the email ----------

@override_settings(FRONTEND_URL='https://geoalert.example/')
class InviteLinkTests(SimpleTestCase):
    def setUp(self):
        self.user = pending_user()

    def test_link_points_at_the_set_password_page_and_its_token_verifies(self):
        link = invite.invite_link(self.user)
        prefix = f'https://geoalert.example/set-password/{password_reset.uid_for(self.user)}/'
        self.assertTrue(link.startswith(prefix), link)
        self.assertTrue(tokens.check_token(self.user, link[len(prefix):]))

    def test_invite_and_reset_tokens_are_not_interchangeable(self):
        self.assertFalse(default_token_generator.check_token(self.user, tokens.make_token(self.user)))
        self.assertFalse(tokens.check_token(self.user, default_token_generator.make_token(self.user)))

    def test_it_lasts_three_days_not_one_hour(self):
        self.assertEqual(settings.ACCOUNT_INVITE_TIMEOUT, 3 * 24 * 3600)
        token = tokens.make_token(self.user)
        made = tokens._now()
        with mock.patch.object(tokens, '_now', return_value=made + timedelta(days=2, hours=23)):
            self.assertTrue(tokens.check_token(self.user, token))
        with mock.patch.object(tokens, '_now', return_value=made + timedelta(days=3, seconds=1)):
            self.assertFalse(tokens.check_token(self.user, token))

    def test_it_stops_working_once_a_password_is_set_or_a_new_invite_replaces_it(self):
        token = tokens.make_token(self.user)
        self.user.set_unusable_password()          # what Resend invite does
        self.assertFalse(tokens.check_token(self.user, token))
        token = tokens.make_token(self.user)
        self.user.set_password('Fresh-Harbor-2026')
        self.assertFalse(tokens.check_token(self.user, token))

    def test_it_stops_working_when_the_email_is_corrected(self):
        token = tokens.make_token(self.user)
        self.user.email = 'juan.delacruz@example.com'
        self.assertFalse(tokens.check_token(self.user, token))

    def test_garbage_tokens_are_refused(self):
        for bad in (None, '', 123, 'abc', 'zzzzzzzzzzz-abc', '-', 'a-b-c'):
            self.assertFalse(tokens.check_token(self.user, bad), bad)

    def test_a_new_account_is_pending_until_it_has_a_password(self):
        self.assertTrue(invite.is_pending(self.user))
        self.user.set_password('Fresh-Harbor-2026')
        self.assertFalse(invite.is_pending(self.user))


class InviteEmailTests(SimpleTestCase):
    def test_the_email_names_the_person_role_username_id_link_and_lifetime(self):
        subject, body = invite.invite_email(pending_user(), 'https://x/set-password/u/t')
        self.assertEqual(subject, 'Set up your GeoAlert Talisay account')
        self.assertIn('Hello Juan Dela Cruz,', body)
        self.assertIn('as DRRMO Officer.', body)
        self.assertIn('Your username is this email address: juan@example.com', body)
        self.assertIn('Employee ID: DRRMO-0012', body)
        self.assertIn('https://x/set-password/u/t', body)
        self.assertIn('within 3 days', body)

    def test_no_employee_id_line_without_one(self):
        _, body = invite.invite_email(pending_user(employee_id=None), 'https://x')
        self.assertNotIn('Employee ID', body)

    def test_the_lifetime_reads_naturally(self):
        for seconds, text in ((86400, '1 day'), (7 * 86400, '7 days'), (7200, '2 hours'), (3600, '1 hour')):
            with override_settings(ACCOUNT_INVITE_TIMEOUT=seconds):
                self.assertEqual(invite.lifetime_text(), text)


@override_settings(FRONTEND_URL='https://geoalert.example', DEFAULT_FROM_EMAIL='GeoAlert <noreply@example.com>')
class EmailDesignTests(SimpleTestCase):
    """The designed HTML version sent beside the plain text (Django's test runner keeps mail in mail.outbox)."""

    def setUp(self):
        mail.outbox = []

    def sent(self):
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        (html, kind), = message.alternatives
        self.assertEqual(kind, 'text/html')
        return message, html

    def test_the_invite_has_a_button_the_details_and_an_inline_logo(self):
        user = pending_user()
        invite.send_invite_email(user)
        message, html = self.sent()
        self.assertEqual(message.to, ['juan@example.com'])
        self.assertEqual(message.subject, 'Set up your GeoAlert Talisay account')
        self.assertIn('Hello Juan Dela Cruz,', message.body)           # the plain text is still there
        link = re.search(r'https://geoalert\.example/set-password/\S+', message.body).group(0)
        self.assertTrue(tokens.check_token(user, link.rsplit('/', 1)[1]))
        self.assertIn(f'href="{link}"', html)
        for text in ('Set up your account', 'Set your password', 'DRRMO Officer', 'juan@example.com',
                     'DRRMO-0012', 'expires in 3 days', 'cid:geoalert-logo'):
            self.assertIn(text, html)
        raw = message.message().as_string()
        self.assertIn('multipart/related', raw)
        self.assertIn('Content-ID: <geoalert-logo>', raw)

    def test_names_typed_in_the_admin_form_cannot_add_markup(self):
        invite.send_invite_email(pending_user(full_name='<a href="https://evil.example">Juan</a>'))
        _, html = self.sent()
        self.assertNotIn('evil.example">', html)
        self.assertIn('&lt;a href=', html)

    def test_it_still_sends_without_the_logo_file(self):
        with mock.patch.object(emails, 'LOGO_PATH', emails.LOGO_PATH.with_name('missing.png')):
            invite.send_invite_email(pending_user())
        message, html = self.sent()
        self.assertNotIn('<img', html)
        self.assertNotIn('Content-ID', message.message().as_string())

    def test_the_reset_email_shares_the_design(self):
        user = pending_user()
        user.set_password('Old-pass-2026')
        password_reset.send_reset_email(user)
        message, html = self.sent()
        self.assertEqual(message.subject, 'Reset your GeoAlert password')
        self.assertIn('within 1 hour', message.body)
        for text in ('Reset your password', 'Choose a new password', 'expires in 1 hour',
                     'https://geoalert.example/reset-password/', 'your password stays the same'):
            self.assertIn(text, html)

    def test_the_logo_shipped_with_the_backend_is_small(self):
        self.assertLess(emails.LOGO_PATH.stat().st_size, 40_000)


# ---------- The public endpoints ----------

@override_settings(CACHES=LOCMEM)
@mock.patch(AUTH + 'user_from_uid')
class InviteCheckViewTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    def check(self, token):
        return post(auth_views.InviteCheckView, '/api/auth/invite/check/', {'uid': 'u', 'token': token})

    def test_a_good_link_is_valid(self, from_uid):
        user = pending_user()
        from_uid.return_value = user
        self.assertEqual(self.check(tokens.make_token(user)).data, {'valid': True})

    def test_bad_links_and_reset_tokens_are_invalid(self, from_uid):
        user = pending_user()
        for found, token in ((None, 'x'), (user, 'wrong'), (user, 123),
                             (user, default_token_generator.make_token(user))):
            from_uid.return_value = found
            self.assertEqual(self.check(token).data, {'valid': False}, token)


@override_settings(CACHES=LOCMEM)
@mock.patch.object(User, 'save')
@mock.patch(AUTH + 'log_event')
@mock.patch(AUTH + 'user_from_uid')
class InviteAcceptViewTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    def accept(self, token, password='Fresh-Harbor-2026'):
        return post(auth_views.InviteAcceptView, '/api/auth/invite/accept/',
                    {'uid': 'u', 'token': token, 'new_password': password})

    def test_success_sets_the_password_ends_pending_and_clears_lockout(self, from_uid, log, save):
        user = pending_user(failed_login_count=5, locked_until=timezone.now())
        from_uid.return_value = user
        res = self.accept(tokens.make_token(user))
        self.assertEqual((res.status_code, res.data['message']), (200, invite.DONE_REPLY))
        self.assertTrue(user.check_password('Fresh-Harbor-2026'))
        self.assertFalse(invite.is_pending(user))
        self.assertEqual((user.must_change_password, user.failed_login_count, user.locked_until), (False, 0, None))
        save.assert_called_once()
        self.assertEqual(actions(log), ['INVITE_ACCEPTED'])

    def test_the_link_works_once(self, from_uid, log, save):
        user = pending_user()
        from_uid.return_value = user
        token = tokens.make_token(user)
        self.assertEqual(self.accept(token).status_code, 200)
        res = self.accept(token, 'Another-Harbor-2026')
        self.assertEqual((res.status_code, res.data['error']), (400, invite.BAD_LINK))
        self.assertTrue(user.check_password('Fresh-Harbor-2026'))

    def test_a_bad_link_or_a_reset_token_is_refused(self, from_uid, log, save):
        user = pending_user()
        from_uid.return_value = user
        for token in ('wrong', default_token_generator.make_token(user)):
            res = self.accept(token)
            self.assertEqual((res.status_code, res.data['error']), (400, invite.BAD_LINK))
        self.assertEqual(actions(log), ['INVITE_ACCEPT_FAILED'] * 2)
        save.assert_not_called()

    def test_a_weak_password_is_refused_with_the_rules(self, from_uid, log, save):
        user = pending_user()
        from_uid.return_value = user
        res = self.accept(tokens.make_token(user), password='12345678')
        self.assertEqual(res.status_code, 400)
        self.assertIn('entirely numeric', res.data['error'])
        self.assertTrue(invite.is_pending(user))
        save.assert_not_called()

    def test_failures_share_the_reset_links_limit(self, from_uid, log, save):
        from_uid.return_value = pending_user()
        for _ in range(20):
            self.accept('wrong')
        res = post(auth_views.PasswordResetCheckView, '/api/auth/password-reset/check/', {'uid': 'u', 'token': 'x'})
        self.assertEqual((res.status_code, res.data['error']), (429, password_reset.ATTEMPTS_REPLY))
        self.assertEqual(self.accept('wrong').status_code, 429)


# ---------- Login ----------

@override_settings(CACHES=LOCMEM)
@mock.patch(AUTH + 'lock_minutes', return_value=30)
@mock.patch(AUTH + 'max_failed_logins', return_value=5)
@mock.patch.object(User, 'save')
@mock.patch(AUTH + 'log_event')
@mock.patch(AUTH + '_spend_a_password_check')
class PendingLoginTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    def login(self, user):
        with mock.patch.object(User.objects, 'get', return_value=user):
            return post(auth_views.LoginView, '/api/auth/login/', {'email': user.email, 'password': 'Guess-2026-x'})

    def test_a_pending_account_cannot_sign_in_and_takes_a_real_checks_time(self, spend, log, save, *_):
        res = self.login(pending_user())
        self.assertEqual((res.status_code, res.data), (401, auth_views.INVALID))
        spend.assert_called_once_with('Guess-2026-x')

    def test_an_account_with_a_password_is_not_padded_twice(self, spend, log, save, *_):
        user = pending_user()
        user.set_password('Real-pass-2026')
        self.assertEqual(self.login(user).status_code, 401)
        spend.assert_not_called()


# ---------- Admin: creating, resending, editing ----------

class CreateSerializerTests(SimpleTestCase):
    @mock.patch.object(User, 'save')
    @mock.patch.object(Role.objects, 'get', return_value=Role(id=2, name='DRRMO_Officer'))
    def test_a_new_account_has_no_password_and_nothing_for_the_admin_to_see(self, get_role, save):
        user = UserCreateSerializer().create({
            'email': 'juan@example.com', 'first_name': 'Juan', 'last_name': 'Dela Cruz', 'role_id': 2,
        })
        self.assertTrue(invite.is_pending(user))
        self.assertFalse(user.must_change_password)
        self.assertFalse(hasattr(user, '_temp_password'))
        save.assert_called_once()


@mock.patch(ADMIN + 'log_action')
@mock.patch(ADMIN + 'send_invite_email')
class SendInviteTests(SimpleTestCase):
    def request(self):
        request = mock.Mock()
        request.user = admin()
        return request

    def test_a_sent_invite_is_logged(self, send, log):
        user = pending_user()
        self.assertTrue(admin_views.send_invite(self.request(), user))
        send.assert_called_once_with(user)
        self.assertEqual(actions(log), ['INVITE_SENT'])

    def test_a_failed_send_is_logged_and_reported(self, send, log):
        send.side_effect = SMTPException('auth failed')
        self.assertFalse(admin_views.send_invite(self.request(), pending_user()))
        self.assertEqual(actions(log), ['INVITE_EMAIL_FAILED'])
        self.assertIn('SMTPException', log.call_args.args[4])


@mock.patch(ADMIN + 'log_action')
@mock.patch(ADMIN + 'send_invite_email')
class CreateViewTests(SimpleTestCase):
    def create(self, user):
        serializer = mock.Mock()
        serializer.is_valid.return_value = True
        serializer.save.return_value = user
        with mock.patch(ADMIN + 'UserCreateSerializer', return_value=serializer):
            return post(admin_views.UserListCreateView, '/api/admin-dashboard/users/', {}, user=admin())

    def test_creating_an_account_emails_the_invite_and_returns_no_password(self, send, log):
        user = pending_user()
        res = self.create(user)
        self.assertEqual(res.status_code, 201)
        self.assertNotIn('temporary_password', res.data)
        self.assertTrue(res.data['invite_sent'])
        self.assertTrue(res.data['user']['invite_pending'])
        send.assert_called_once_with(user)
        self.assertEqual(actions(log), ['CREATE_USER', 'INVITE_SENT'])

    def test_the_account_is_still_created_when_the_email_fails(self, send, log):
        send.side_effect = SMTPException('down')
        res = self.create(pending_user())
        self.assertEqual((res.status_code, res.data['invite_sent']), (201, False))
        self.assertEqual(actions(log), ['CREATE_USER', 'INVITE_EMAIL_FAILED'])


@mock.patch.object(User, 'save')
@mock.patch(ADMIN + 'log_action')
@mock.patch(ADMIN + 'send_invite_email')
class ResendInviteViewTests(SimpleTestCase):
    def resend(self, user, as_user=None):
        with mock.patch.object(User.objects, 'get', return_value=user):
            return post(admin_views.ResendInviteView, '/x/', {}, user=as_user or admin(), pk=user.pk)

    def test_a_new_link_replaces_the_old_one(self, send, log, save):
        user = pending_user()
        old = tokens.make_token(user)
        res = self.resend(user)
        self.assertEqual(res.status_code, 200)
        send.assert_called_once_with(user)
        save.assert_called_once_with(update_fields=['password'])
        self.assertTrue(invite.is_pending(user))
        self.assertFalse(tokens.check_token(user, old))

    def test_a_failed_send_keeps_the_last_link_working(self, send, log, save):
        send.side_effect = SMTPException('down')
        res = self.resend(pending_user())
        self.assertEqual(res.status_code, 502)
        self.assertIn('Reset password', res.data['error'])
        save.assert_not_called()

    def test_refused_once_a_password_is_set_or_the_account_is_off(self, send, log, save):
        has_password = pending_user()
        has_password.set_password('Real-pass-2026')
        for user in (has_password, pending_user(is_active=False)):
            self.assertEqual(self.resend(user).status_code, 400)
        send.assert_not_called()
        save.assert_not_called()

    def test_unknown_account_is_404(self, send, log, save):
        with mock.patch.object(User.objects, 'get', side_effect=User.DoesNotExist):
            res = post(admin_views.ResendInviteView, '/x/', {}, user=admin(), pk='00000000-0000-0000-0000-000000000000')
        self.assertEqual(res.status_code, 404)

    def test_admins_only(self, send, log, save):
        officer = User(email='o@example.com', full_name='O', is_active=True, role=Role(id=2, name='DRRMO_Officer'))
        self.assertEqual(self.resend(pending_user(), as_user=officer).status_code, 403)
        send.assert_not_called()


@mock.patch(ADMIN + 'log_action')
@mock.patch(ADMIN + 'send_invite_email')
class EditEmailTests(SimpleTestCase):
    def edit(self, user, new_email):
        serializer = mock.Mock()
        serializer.is_valid.return_value = True

        def save():
            user.email = new_email
            return user
        serializer.save.side_effect = save
        with mock.patch.object(User.objects, 'get', return_value=user), \
                mock.patch(ADMIN + 'UserUpdateSerializer', return_value=serializer):
            request = factory.put('/x/', {'email': new_email}, format='json')
            force_authenticate(request, user=admin())
            return admin_views.UserDetailView.as_view()(request, pk=user.pk)

    def test_correcting_a_pending_accounts_email_sends_the_invite_there(self, send, log):
        user = pending_user(email='juan@exmaple.com')
        res = self.edit(user, 'juan@example.com')
        self.assertEqual((res.status_code, res.data['invite_sent']), (200, True))
        send.assert_called_once_with(user)

    def test_no_invite_for_an_account_that_has_a_password(self, send, log):
        user = pending_user()
        user.set_password('Real-pass-2026')
        res = self.edit(user, 'juan2@example.com')
        self.assertNotIn('invite_sent', res.data)
        send.assert_not_called()

    def test_no_invite_when_the_email_did_not_change(self, send, log):
        res = self.edit(pending_user(), 'juan@example.com')
        self.assertNotIn('invite_sent', res.data)
        send.assert_not_called()
