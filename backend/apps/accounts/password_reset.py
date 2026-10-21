"""
Forgot password: the reset link, its email, and the two account lookups.

The link carries Django's default_token_generator token, which is signed
with the account's current password hash and the time it was made. It
stops working after PASSWORD_RESET_TIMEOUT (1 hour), and as soon as the
password changes, so each link works once. No table stores it.

The lookups are the only database access, so the views can be tested with
them patched out.
"""

import uuid

from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode

from apps.accounts.models import User

GENERIC_REPLY = ("If an account with that email exists, we've sent a link to reset its "
                 "password. It works for 1 hour.")
LIMIT_REPLY = 'Too many reset requests. Try again in a little while.'
BAD_LINK = 'This link has expired or was already used.'
DONE_REPLY = 'Password changed. Log in with your new password.'
SUBJECT = 'Reset your GeoAlert password'

BODY = """Hello {name},

Someone asked to reset the password for your GeoAlert account. To choose a new password, open this link within 1 hour:

{link}

If you didn't ask for this, ignore this email; your password stays the same.
"""


def find_active_user(email):
    """The active account with this email, matched without regard to case, or None."""
    return User.objects.filter(email__iexact=email, is_active=True).first()


def user_from_uid(uid):
    """The active account a link's uid names, or None for anything that doesn't decode to one."""
    if not isinstance(uid, str) or not uid:
        return None
    try:
        pk = uuid.UUID(force_str(urlsafe_base64_decode(uid)))
    except (TypeError, ValueError, UnicodeDecodeError):
        return None
    return User.objects.filter(pk=pk, is_active=True).first()


def uid_for(user):
    return urlsafe_base64_encode(force_bytes(user.pk))


def reset_link(user):
    token = default_token_generator.make_token(user)
    return f'{settings.FRONTEND_URL.rstrip("/")}/reset-password/{uid_for(user)}/{token}'


def reset_email(user, link):
    """(subject, body) of the reset email."""
    return SUBJECT, BODY.format(name=user.full_name or user.email, link=link)


def send_reset_email(user):
    """Send the reset email; a sending failure is raised for the caller to log."""
    subject, body = reset_email(user, reset_link(user))
    send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [user.email])
