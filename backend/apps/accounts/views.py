import base64
import io
import threading
import time

import pyotp
import qrcode
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.utils.crypto import constant_time_compare
from django.views.decorators.csrf import ensure_csrf_cookie
from django.http import JsonResponse
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.authentication import SessionAuthentication
from rest_framework import status
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt


from datetime import timedelta


from django.contrib.auth.tokens import default_token_generator
from django.db import connection

from apps.accounts import invite
from apps.accounts.models import User
from apps.accounts.password_reset import (
    ATTEMPTS_REPLY, BAD_LINK, DONE_REPLY, GENERIC_REPLY, LIMIT_REPLY, SAME_PASSWORD,
    find_active_user, send_reset_email, user_from_uid,
)
from apps.accounts.serializers import LoginSerializer, UserSerializer, TwoFactorCodeSerializer
from utils import login_throttle, reset_throttle
from utils.audit import log_event
from utils.security_cache import SecurityCacheProxy
from utils.session_limits import start_session_clock
from utils.system_settings import get_setting

# Unknown-email lockouts and 2FA counts live in the security cache, which the
# public map can't fill up and flush (utils/security_cache.py)
cache = SecurityCacheProxy()

# F1 lockout: this many wrong passwords locks the account for a while. A
# System Administrator sets both from the configuration panel
# (utils/system_settings.py).


def max_failed_logins():
    return get_setting('auth.max_failed_logins')


def lock_minutes():
    return get_setting('auth.lock_minutes')


def locked_response():
    return {'error': f'Account locked. Try again in {lock_minutes()} minutes.'}

# Wrong 2FA codes allowed in one login attempt before it is cancelled.
MAX_2FA_TRIES = 5

INVALID = {'error': 'Invalid email or password'}

_dummy_hash = None


def _spend_a_password_check(password):
    """
    Take as long as checking a real password does.

    A login for an email with no account used to answer at once, while a
    real account took the time of a bcrypt check, so response time alone
    told an attacker which emails exist.
    """
    global _dummy_hash
    if _dummy_hash is None:
        _dummy_hash = make_password('not-a-real-password')
    check_password(password, _dummy_hash)


def _unknown_email_locked(email):
    """
    Lock unknown emails exactly like real ones.

    Only real accounts could ever answer "Account locked", so trying an
    address five times revealed whether it had an account. Unknown
    addresses now count failures too (in the cache, there is no row) and
    lock the same way.
    """
    key = f'geoalert:login-fail:{email.strip().lower()}'
    try:
        fails = cache.get(key, 0)
        if fails >= max_failed_logins():
            return True
        cache.set(key, fails + 1, lock_minutes() * 60)
    except Exception:
        pass  # a cache outage must not stop anyone signing in
    return False

def _count_ip_failure(request, email):
    if login_throttle.record_failure(request):
        log_event(
            request, 'IP_THROTTLED', 'app_user', '',
            f'{login_throttle.MAX_FAILS} failed sign-ins from this address in '
            f'{login_throttle.WINDOW // 60} minutes (last tried {email}); '
            f'refused for {login_throttle.BLOCK // 60} minutes',
        )


def _code_step(secret, code, now=None):
    """
    The 30-second step whose code this is, or None for a wrong code. The
    current step and one either side are accepted, as totp.verify(valid_window=1)
    did, so a phone clock a little off still works.
    """
    totp = pyotp.TOTP(secret)
    base = int((time.time() if now is None else now) // totp.interval)
    for step in (base, base - 1, base + 1):
        if constant_time_compare(totp.generate_otp(step), code):
            return step
    return None


def _claim_step(user, step):
    """
    Use up this account's code for `step`. False when it, or a later one, was
    already used to sign in: a code someone saw over a shoulder, or caught on
    its way, mustn't sign in a second time while it is still valid.
    """
    key = f'geoalert:2fa-step:{user.id}'
    try:
        last = cache.get(key)
        if last is not None and step <= last:
            return False
        cache.set(key, step, 5 * 60)
    except Exception:
        pass  # a cache outage must not stop anyone signing in
    return True


def _count_2fa_failure(user):
    """
    One more wrong code for this account, whichever sign-in attempt it came
    from. Returns the total in the current lockout window, or None when the
    cache can't be reached.

    The five-try limit used to be per attempt, so opening many attempts gave
    four free guesses each without ever counting as a failed sign-in.
    """
    key = f'geoalert:2fa-fails:{user.id}'
    try:
        now = time.time()
        value = cache.get(key)
        live = isinstance(value, tuple) and len(value) == 2 and now < value[1]
        count, end = value if live else (0, now + lock_minutes() * 60)
        count += 1
        cache.set(key, (count, end), max(1, int(end - now) + 1))
        return count
    except Exception:
        return None


def _end_pending(request):
    request.session.pop('pending_2fa_user_id', None)
    request.session.pop('pending_2fa_tries', None)


@ensure_csrf_cookie
def csrf_view(request):
    return JsonResponse({'message': 'CSRF cookie set'})


class CsrfExemptSessionAuthentication(SessionAuthentication):
    """Session auth that skips DRF's own CSRF check — used on endpoints
    that already handle CSRF elsewhere (e.g. via csrf_exempt) but still
    need to know who the logged-in user is."""
    def enforce_csrf(self, request):
        return


@method_decorator(csrf_exempt, name='dispatch')
class LoginView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = [] 
    
    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        email    = serializer.validated_data['email']
        password = serializer.validated_data['password']

        # One password tried against every account never trips the
        # per-account lockout; the per-address count does.
        if login_throttle.is_blocked(request):
            log_event(request, 'LOGIN_BLOCKED_IP', 'app_user', '', f'{email}: address throttled')
            return Response(login_throttle.BLOCKED, status=status.HTTP_429_TOO_MANY_REQUESTS)

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            _spend_a_password_check(password)
            _count_ip_failure(request, email)
            if _unknown_email_locked(email):
                log_event(request, 'LOGIN_BLOCKED_LOCKED', 'app_user', '', f'{email} (no such account)')
                return Response(locked_response(), status=status.HTTP_423_LOCKED)
            log_event(request, 'LOGIN_FAILED', 'app_user', '', f'{email} (no such account)')
            return Response(INVALID, status=status.HTTP_401_UNAUTHORIZED)

        # A lock that has run out starts the count again, instead of
        # re-locking on the very next mistake.
        if user.locked_until and not user.is_locked():
            user.failed_login_count = 0
            user.locked_until = None
            user.save(update_fields=['failed_login_count', 'locked_until'])

        if user.is_locked():
            log_event(request, 'LOGIN_BLOCKED_LOCKED', 'app_user', user.id, user.email, user=user)
            return Response(locked_response(), status=status.HTTP_423_LOCKED)

        # Authenticate
        auth_user = authenticate(request, username=email, password=password)

        if auth_user is None:
            # An account still waiting for its invite has no password, and
            # Django answers that without hashing anything; take a real
            # check's time so the reply's speed doesn't single it out.
            if invite.is_pending(user):
                _spend_a_password_check(password)
            _count_ip_failure(request, email)
            user.failed_login_count += 1
            locked_now = user.failed_login_count >= max_failed_logins()
            if locked_now:
                user.locked_until = timezone.now() + timedelta(minutes=lock_minutes())
            user.save(update_fields=['failed_login_count', 'locked_until'])
            log_event(
                request, 'ACCOUNT_LOCKED' if locked_now else 'LOGIN_FAILED', 'app_user', user.id,
                f'{user.email}: wrong password ({user.failed_login_count} in a row)'
                + (f'; locked for {lock_minutes()} minutes' if locked_now else ''),
                user=user,
            )
            return Response(INVALID, status=status.HTTP_401_UNAUTHORIZED)

        # Password is correct. Without 2FA that is a full sign-in: reset the
        # lockout tracking. With 2FA it is only half of one, so the count
        # stays until the code is right too; clearing it here let rounds of
        # wrong codes go on for ever, each new password check wiping the last.
        # `auth_user`, not the earlier `user`, since authenticate() may have
        # rehashed the password in the DB and `user` was loaded before that.
        if not auth_user.two_factor_enabled:
            auth_user.failed_login_count = 0
            auth_user.locked_until = None
            auth_user.save(update_fields=['failed_login_count', 'locked_until'])

        # If 2FA is on, stop here — don't start a logged-in session yet.
        # Stash which user passed the password step in this (still
        # anonymous) session, and ask the frontend for the 6-digit code next.
        if auth_user.two_factor_enabled:
            request.session['pending_2fa_user_id'] = str(auth_user.id)
            request.session['pending_2fa_tries'] = 0
            return Response({'require_2fa': True}, status=status.HTTP_200_OK)

        # No 2FA — log in now, same as before.
        auth_user.last_login = timezone.now()
        auth_user.save(update_fields=['last_login'])
        login(request, auth_user)
        start_session_clock(request)
        log_event(request, 'LOGIN_SUCCESS', 'app_user', auth_user.id, auth_user.email, user=auth_user)

        return Response({
            'message': 'Login successful',
            'user': UserSerializer(auth_user).data,
            'role': auth_user.role.name if auth_user.role else None,
        }, status=status.HTTP_200_OK)


@method_decorator(csrf_exempt, name='dispatch')
class TwoFactorVerifyView(APIView):
    """
    POST /api/auth/2fa/verify/
    Step 2 of login, only reached when LoginView returned require_2fa: true.
    Checks the 6-digit code against the pending user from the session,
    then completes the login the same way LoginView normally would.
    """
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        if login_throttle.is_blocked(request):
            return Response(login_throttle.BLOCKED, status=status.HTTP_429_TOO_MANY_REQUESTS)
        pending_id = request.session.get('pending_2fa_user_id')
        if not pending_id:
            return Response(
                {'error': 'No login in progress. Please log in again.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        serializer = TwoFactorCodeSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            user = User.objects.get(id=pending_id, two_factor_enabled=True)
        except User.DoesNotExist:
            request.session.pop('pending_2fa_user_id', None)
            return Response(
                {'error': 'No login in progress. Please log in again.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # The password was checked a moment ago, but the account may have been
        # locked since (by wrong codes in another attempt) or deactivated. An
        # attempt already past the password step used to go on regardless, so
        # a correct code signed in to a locked account.
        if not user.is_active:
            _end_pending(request)
            return Response({'error': 'No login in progress. Please log in again.'},
                            status=status.HTTP_400_BAD_REQUEST)
        if user.is_locked():
            _end_pending(request)
            log_event(request, 'LOGIN_BLOCKED_LOCKED', 'app_user', user.id, f'{user.email} (2FA step)', user=user)
            return Response(locked_response(), status=status.HTTP_423_LOCKED)

        step = _code_step(user.two_factor_secret, serializer.validated_data['code'])
        replayed = step is not None and not _claim_step(user, step)
        if step is None or replayed:
            _count_ip_failure(request, user.email)
            # Six digits is only a million codes, and each accepts the ones
            # either side of it. Without a limit the code step could be
            # guessed through by script once the password was known.
            tries = request.session.get('pending_2fa_tries', 0) + 1
            # Every MAX_2FA_TRIES wrong codes for the account, however many
            # attempts they are spread over, count as one failed sign-in, so
            # guessing ends in the usual lockout rather than going on for ever.
            wrong = _count_2fa_failure(user)
            locked_now = False
            if (wrong is not None and wrong % MAX_2FA_TRIES == 0) or (wrong is None and tries >= MAX_2FA_TRIES):
                user.failed_login_count += 1
                locked_now = user.failed_login_count >= max_failed_logins()
                if locked_now:
                    user.locked_until = timezone.now() + timedelta(minutes=lock_minutes())
                user.save(update_fields=['failed_login_count', 'locked_until'])
                log_event(
                    request, 'ACCOUNT_LOCKED' if locked_now else 'TWO_FACTOR_TOO_MANY', 'app_user', user.id,
                    f'{user.email}: {MAX_2FA_TRIES} wrong 2FA codes'
                    + (f'; locked for {lock_minutes()} minutes' if locked_now else ''),
                    user=user,
                )
            if tries >= MAX_2FA_TRIES:
                _end_pending(request)
                return Response(
                    {'error': 'Too many wrong codes. Sign in again with your password.'},
                    status=status.HTTP_429_TOO_MANY_REQUESTS,
                )
            if locked_now:
                _end_pending(request)
                return Response(locked_response(), status=status.HTTP_423_LOCKED)
            request.session['pending_2fa_tries'] = tries
            log_event(request, 'TWO_FACTOR_FAILED', 'app_user', user.id,
                      f'{user.email}: ' + ('2FA code already used' if replayed else 'wrong 2FA code')
                      + f' ({tries} of {MAX_2FA_TRIES})', user=user)
            return Response(
                {'error': 'That code was already used. Wait for the next one.' if replayed else 'Incorrect code',
                 'tries_left': MAX_2FA_TRIES - tries},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        _end_pending(request)
        try:
            cache.delete(f'geoalert:2fa-fails:{user.id}')
        except Exception:
            pass
        user.last_login = timezone.now()
        # Password and code both right: now the failed sign-ins are cleared
        user.failed_login_count = 0
        user.locked_until = None
        user.save(update_fields=['last_login', 'failed_login_count', 'locked_until'])
        login(request, user)
        start_session_clock(request)
        log_event(request, 'LOGIN_SUCCESS', 'app_user', user.id, f'{user.email} (with 2FA)', user=user)

        return Response({
            'message': 'Login successful',
            'user': UserSerializer(user).data,
            'role': user.role.name if user.role else None,
        }, status=status.HTTP_200_OK)


# The signed-in account views below check the CSRF token like the rest of the
# API (the app sends it with every POST). They used to skip it, so another site
# could submit a form to them in a signed-in officer's browser.

class TwoFactorSetupView(APIView):
    """
    POST /api/auth/2fa/setup/
    Starts enabling 2FA for the logged-in user: generates a new secret
    (not active yet) and returns a QR code to scan plus the secret for
    manual entry. Must be followed by a correct code to 2fa/confirm/.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        # Starting setup again while 2FA is on used to replace the working
        # secret straight away. Abandon that setup and the authenticator app
        # no longer matched, so the officer could not sign in at all.
        if request.user.two_factor_enabled:
            return Response(
                {'error': 'Two-factor authentication is already on. Turn it off first to set it up again.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        secret = pyotp.random_base32()
        request.user.two_factor_secret = secret
        request.user.save(update_fields=['two_factor_secret'])
        log_event(request, 'TWO_FACTOR_SETUP_STARTED', 'app_user', request.user.id, request.user.email)

        uri = pyotp.totp.TOTP(secret).provisioning_uri(
            name=request.user.email,
            issuer_name='GeoAlert',
        )

        img = qrcode.make(uri)
        buf = io.BytesIO()
        img.save(buf, format='PNG')
        qr_base64 = base64.b64encode(buf.getvalue()).decode()

        return Response({
            'secret': secret,
            'qr_code': f'data:image/png;base64,{qr_base64}',
        })


class TwoFactorConfirmView(APIView):
    """
    POST /api/auth/2fa/confirm/
    Finishes enabling 2FA: checks a code against the secret from
    2fa/setup/, and if correct, turns 2FA on for this account.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = TwoFactorCodeSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        if not request.user.two_factor_secret:
            return Response(
                {'error': 'Start setup first.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        totp = pyotp.TOTP(request.user.two_factor_secret)
        if not totp.verify(serializer.validated_data['code'], valid_window=1):
            return Response({'error': 'Incorrect code'}, status=status.HTTP_401_UNAUTHORIZED)

        request.user.two_factor_enabled = True
        request.user.save(update_fields=['two_factor_enabled'])
        log_event(request, 'TWO_FACTOR_ENABLED', 'app_user', request.user.id, request.user.email)

        return Response({
            'message': 'Two-factor authentication enabled',
            'user': UserSerializer(request.user).data,
        })


class TwoFactorDisableView(APIView):
    """
    POST /api/auth/2fa/disable/
    Turns 2FA off, after confirming the user can still produce a
    correct code (not just that they're logged in).
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = TwoFactorCodeSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        if not request.user.two_factor_enabled or not request.user.two_factor_secret:
            return Response(
                {'error': 'Two-factor authentication is not enabled.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        totp = pyotp.TOTP(request.user.two_factor_secret)
        if not totp.verify(serializer.validated_data['code'], valid_window=1):
            return Response({'error': 'Incorrect code'}, status=status.HTTP_401_UNAUTHORIZED)

        request.user.two_factor_enabled = False
        request.user.two_factor_secret = None
        request.user.save(update_fields=['two_factor_enabled', 'two_factor_secret'])
        log_event(request, 'TWO_FACTOR_DISABLED', 'app_user', request.user.id, request.user.email)

        return Response({
            'message': 'Two-factor authentication disabled',
            'user': UserSerializer(request.user).data,
        })


class ChangePasswordView(APIView):
    """
    POST /api/auth/change-password/
    Body: { current_password, new_password }
    Any logged-in user (Admin, DRRMO, Barangay) can change their own password.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        current_password = request.data.get('current_password', '')
        new_password     = request.data.get('new_password', '')

        if not current_password or not new_password:
            return Response(
                {'error': 'Both current_password and new_password are required.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if not request.user.check_password(current_password):
            log_event(request, 'PASSWORD_CHANGE_FAILED', 'app_user', request.user.id,
                      f'{request.user.email}: wrong current password')
            return Response(
                {'error': 'Current password is incorrect.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        # The rules in AUTH_PASSWORD_VALIDATORS: length, not too common, not
        # all digits, not too close to the account's name or email. This
        # endpoint only checked the length before.
        if new_password == current_password:
            return Response({'error': 'Choose a password different from your current one.'},
                            status=status.HTTP_400_BAD_REQUEST)
        try:
            validate_password(new_password, user=request.user)
        except ValidationError as exc:
            return Response({'error': ' '.join(exc.messages)}, status=status.HTTP_400_BAD_REQUEST)
        was_temporary = request.user.must_change_password
        request.user.set_password(new_password)
        request.user.must_change_password = False
        request.user.save()
        # Re-login so the session stays valid after the password hash changes
        login(request, request.user)
        start_session_clock(request)
        log_event(request, 'PASSWORD_CHANGED', 'app_user', request.user.id,
                  request.user.email + (' (replaced a temporary password)' if was_temporary else ''))

        return Response({'message': 'Password changed successfully.',
                         'user': UserSerializer(request.user).data})


# Still without the CSRF check: the app treats a refused logout as already
# signed out, so a stale token would leave the session open on the server.
# The worst another site can do with it is sign someone out.
@method_decorator(csrf_exempt, name='dispatch')
class LogoutView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [CsrfExemptSessionAuthentication]

    def post(self, request):
        log_event(request, 'LOGOUT', 'app_user', request.user.id, request.user.email)
        logout(request)
        return Response({'message': 'Logged out successfully'})


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(UserSerializer(request.user).data)

# ---------- Forgot password ----------
# Rate limits (see utils/reset_throttle.py). Failed checks and failed
# confirms share one counter per address, so a token can't be guessed
# through either endpoint.
REQUESTS_PER_ADDRESS = (10, 15 * 60)
EMAILS_PER_ADDRESS_TYPED = (3, 60 * 60)
FAILURES_PER_ADDRESS = (20, 15 * 60)


def run_in_background(job):
    """Run `job` on a daemon thread, so the HTTP reply doesn't wait for it."""
    threading.Thread(target=job, daemon=True).start()


def _link_user(request, tokens=default_token_generator):
    """The account a reset (or invite) link is for, if its uid and token are both good."""
    user = user_from_uid(request.data.get('uid'))
    token = request.data.get('token')
    ok = bool(user and isinstance(token, str) and tokens.check_token(user, token))
    return user, ok


def _failures_key(request):
    return f'fail:{login_throttle.throttle_ip(request)}'


def _too_many_failures(request):
    return reset_throttle.blocked(_failures_key(request), FAILURES_PER_ADDRESS[0])


def _count_failure(request):
    reset_throttle.allow(_failures_key(request), *FAILURES_PER_ADDRESS)


def _too_many_attempts():
    return Response({'error': ATTEMPTS_REPLY}, status=status.HTTP_429_TOO_MANY_REQUESTS)


@method_decorator(csrf_exempt, name='dispatch')
class PasswordResetRequestView(APIView):
    """
    POST /api/auth/password-reset/   Body: { email }
    Emails a one-time, 1-hour reset link to the active account with that
    email. Nothing about the answer depends on whether there is one: the
    same reply, the same per-email count and lookup either way, and the slow
    part (sending and logging) happens after the reply has gone, so not
    even the response time tells.
    """
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        ip = login_throttle.throttle_ip(request)
        if not reset_throttle.allow(f'ip:{ip}', *REQUESTS_PER_ADDRESS):
            return Response({'error': LIMIT_REPLY}, status=status.HTTP_429_TOO_MANY_REQUESTS)

        generic = Response({'message': GENERIC_REPLY})
        email = request.data.get('email')
        email = email.strip() if isinstance(email, str) else ''
        if not email:
            return generic
        # Counted by the address typed, known or not, so both paths do the
        # same work before the reply
        if not reset_throttle.allow(f'email:{email.lower()}', *EMAILS_PER_ADDRESS_TYPED):
            return generic

        user = find_active_user(email)
        # Unknown and deactivated accounts get the same answer, unlogged, so
        # the audit log can't be filled with made-up addresses
        if user is not None:
            run_in_background(lambda: self.send(request, user))
        return generic

    @staticmethod
    def send(request, user):
        try:
            try:
                send_reset_email(user)
            except Exception as exc:  # SMTP down, wrong app password, timed out, ...
                log_event(request, 'PASSWORD_RESET_EMAIL_FAILED', 'app_user', user.id,
                          f'{user.email}: {type(exc).__name__}', user=user)
            else:
                log_event(request, 'PASSWORD_RESET_REQUESTED', 'app_user', user.id, user.email, user=user)
        finally:
            # This thread opened its own database connection; the team's
            # pooler allows only a handful, so give it back now
            connection.close()


@method_decorator(csrf_exempt, name='dispatch')
class PasswordResetCheckView(APIView):
    """
    POST /api/auth/password-reset/check/   Body: { uid, token }
    Whether a reset link still works, so the page can say so before the
    person types a new password.
    """
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        if _too_many_failures(request):
            return _too_many_attempts()
        _, ok = _link_user(request)
        if not ok:
            _count_failure(request)
        return Response({'valid': ok})


@method_decorator(csrf_exempt, name='dispatch')
class PasswordResetConfirmView(APIView):
    """
    POST /api/auth/password-reset/confirm/   Body: { uid, token, new_password }
    Sets the new password under the same rules as change-password,
    including not reusing the current one (so an admin-set temporary
    password can't be kept). Also clears the admin-set-password flag and any
    lockout. Changing the hash ends the account's other sessions and makes
    this link unusable. Nobody is signed in: they sign in normally next, 2FA
    included.
    """
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        if _too_many_failures(request):
            return _too_many_attempts()

        user, ok = _link_user(request)
        if not ok:
            _count_failure(request)  # only bad links count: that is what guessing looks like
            if user is not None:
                log_event(request, 'PASSWORD_RESET_FAILED', 'app_user', user.id,
                          f'{user.email}: expired or already used link', user=user)
            return Response({'error': BAD_LINK}, status=status.HTTP_400_BAD_REQUEST)

        new_password = request.data.get('new_password')
        new_password = new_password if isinstance(new_password, str) else ''
        try:
            validate_password(new_password, user=user)
        except ValidationError as exc:
            log_event(request, 'PASSWORD_RESET_FAILED', 'app_user', user.id,
                      f'{user.email}: new password rejected', user=user)
            return Response({'error': ' '.join(exc.messages)}, status=status.HTTP_400_BAD_REQUEST)
        # hashers.check_password, not user.check_password: on a match the
        # latter may re-hash and save, which would change the hash and kill
        # this very link
        if check_password(new_password, user.password):
            log_event(request, 'PASSWORD_RESET_FAILED', 'app_user', user.id,
                      f'{user.email}: new password same as current', user=user)
            return Response({'error': SAME_PASSWORD}, status=status.HTTP_400_BAD_REQUEST)

        user.set_password(new_password)
        user.must_change_password = False
        user.failed_login_count = 0
        user.locked_until = None
        user.save()
        log_event(request, 'PASSWORD_RESET_DONE', 'app_user', user.id, user.email, user=user)
        return Response({'message': DONE_REPLY})


# ---------- Account invites ----------
# A new account's owner chooses its first password from an emailed link
# (apps/accounts/invite.py). Failed checks and accepts count toward the same
# per-address limit as the reset link, so guessing through either is slowed alike.

@method_decorator(csrf_exempt, name='dispatch')
class InviteCheckView(APIView):
    """
    POST /api/auth/invite/check/   Body: { uid, token }
    Whether an invite link still works, so the page can say so before the
    person types a password.
    """
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        if _too_many_failures(request):
            return _too_many_attempts()
        _, ok = _link_user(request, invite.invite_token_generator)
        if not ok:
            _count_failure(request)
        return Response({'valid': ok})


@method_decorator(csrf_exempt, name='dispatch')
class InviteAcceptView(APIView):
    """
    POST /api/auth/invite/accept/   Body: { uid, token, new_password }
    Sets the account's first password under the same rules as
    change-password. Setting it makes the link unusable and ends the
    "pending" state. Nobody is signed in: they log in next, like after a reset.
    """
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        if _too_many_failures(request):
            return _too_many_attempts()

        user, ok = _link_user(request, invite.invite_token_generator)
        if not ok:
            _count_failure(request)
            if user is not None:
                log_event(request, 'INVITE_ACCEPT_FAILED', 'app_user', user.id,
                          f'{user.email}: expired or already used invite link', user=user)
            return Response({'error': invite.BAD_LINK}, status=status.HTTP_400_BAD_REQUEST)

        new_password = request.data.get('new_password')
        new_password = new_password if isinstance(new_password, str) else ''
        try:
            validate_password(new_password, user=user)
        except ValidationError as exc:
            log_event(request, 'INVITE_ACCEPT_FAILED', 'app_user', user.id,
                      f'{user.email}: new password rejected', user=user)
            return Response({'error': ' '.join(exc.messages)}, status=status.HTTP_400_BAD_REQUEST)

        user.set_password(new_password)
        user.must_change_password = False
        user.failed_login_count = 0
        user.locked_until = None
        user.save()
        log_event(request, 'INVITE_ACCEPTED', 'app_user', user.id, user.email, user=user)
        return Response({'message': invite.DONE_REPLY})
