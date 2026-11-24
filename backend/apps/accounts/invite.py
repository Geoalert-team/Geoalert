"""
Account invites: a new staff account has no password until its owner
chooses one from a link emailed to the account's address.

Nobody else ever knows the password, and opening the link proves the email
address is right. An account still waiting is "pending": its password is
unusable (Django's '!' + random string), so it can't sign in, and that alone
marks it, no extra column.

The link's token works like the reset link's (signed with the account's
current password hash, email and the time it was made), with two
differences: its own salt, so a reset token is never an invite token or the
other way round, and a longer life (ACCOUNT_INVITE_TIMEOUT, 3 days), since
new staff may not read their email the same day. It stops working once the
password is set, when an admin sends a new invite (that replaces the
unusable hash) or gives a temporary password, and when the email changes.
"""

from django.conf import settings
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.utils.crypto import constant_time_compare
from django.utils.http import base36_to_int

from apps.accounts import emails
from apps.accounts.password_reset import uid_for

BAD_LINK = 'This invite link has expired or was already used.'
DONE_REPLY = 'Your password is set. Log in with your email and new password.'
SUBJECT = 'Set up your GeoAlert Talisay account'

BODY = """Hello {name},

A GeoAlert Talisay staff account has been created for you as {role}.

Your username is this email address: {email}
{employee_id_line}
To choose your password and start using the account, open this link within {days}:

{link}

The link works once. If it has expired, ask your system administrator to send a new one.

If you weren't expecting this email, you can ignore it.
"""


class InviteTokenGenerator(PasswordResetTokenGenerator):
    key_salt = 'geoalert.accounts.invite.InviteTokenGenerator'

    def check_token(self, user, token):
        """Django's own check, but against ACCOUNT_INVITE_TIMEOUT rather than PASSWORD_RESET_TIMEOUT."""
        if not (user and isinstance(token, str) and token):
            return False
        try:
            ts_b36, _ = token.split('-')
            ts = base36_to_int(ts_b36)
        except ValueError:
            return False
        for secret in [self.secret, *self.secret_fallbacks]:
            if constant_time_compare(self._make_token_with_timestamp(user, ts, secret), token):
                break
        else:
            return False
        return (self._num_seconds(self._now()) - ts) <= settings.ACCOUNT_INVITE_TIMEOUT


invite_token_generator = InviteTokenGenerator()


def is_pending(user):
    """Still waiting for its owner to choose a password."""
    return not user.has_usable_password()


def lifetime_text():
    """'3 days', '1 day', or hours for a timeout that isn't whole days."""
    seconds = settings.ACCOUNT_INVITE_TIMEOUT
    days, rest = divmod(seconds, 24 * 3600)
    if days and not rest:
        return f'{days} day{"s" if days != 1 else ""}'
    hours = max(1, seconds // 3600)
    return f'{hours} hour{"s" if hours != 1 else ""}'


def invite_link(user):
    token = invite_token_generator.make_token(user)
    return f'{settings.FRONTEND_URL.rstrip("/")}/set-password/{uid_for(user)}/{token}'


def _role(user):
    return user.role.get_name_display() if user.role_id else 'staff'


def invite_email(user, link):
    """(subject, body) of the invite email's plain-text version."""
    return SUBJECT, BODY.format(
        name=user.full_name or user.email,
        role=_role(user),
        email=user.email,
        employee_id_line=f'Employee ID: {user.employee_id}\n' if user.employee_id else '',
        days=lifetime_text(),
        link=link,
    )


def invite_context(user, link):
    """What the designed HTML version (templates/accounts/email/invite.html) shows."""
    days = lifetime_text()
    return {
        'heading': 'Set up your account',
        'preheader': f'Choose your password to start using GeoAlert Talisay. The link works for {days}.',
        'name': user.full_name or user.email,
        'role': _role(user),
        'email': user.email,
        'employee_id': user.employee_id or '',
        'link': link,
        'button': 'Set your password',
        'expiry': f'This link works once and expires in {days}.',
    }


def send_invite_email(user):
    """Send the invite for the account as it is now; a sending failure is raised for the caller."""
    link = invite_link(user)
    subject, body = invite_email(user, link)
    emails.send(user.email, subject, body, 'accounts/email/invite.html', invite_context(user, link))
