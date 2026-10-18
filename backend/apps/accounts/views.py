import base64
import io

import pyotp
import qrcode
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth.password_validation import validate_password
from django.core.cache import cache
from django.core.exceptions import ValidationError
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


from apps.accounts.models import User
from apps.accounts.serializers import LoginSerializer, UserSerializer, TwoFactorCodeSerializer
from utils.audit import log_event
from utils.session_limits import start_session_clock

# F1 lockout: this many wrong passwords locks the account for LOCK_MINUTES.
MAX_FAILED_LOGINS = 5
LOCK_MINUTES = 15
# Wrong 2FA codes allowed in one login attempt before it is cancelled.
MAX_2FA_TRIES = 5

INVALID = {'error': 'Invalid email or password'}
LOCKED = {'error': f'Account locked. Try again in {LOCK_MINUTES} minutes.'}

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
        if fails >= MAX_FAILED_LOGINS:
            return True
        cache.set(key, fails + 1, LOCK_MINUTES * 60)
    except Exception:
        pass  # a cache outage must not stop anyone signing in
    return False

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

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            _spend_a_password_check(password)
            if _unknown_email_locked(email):
                log_event(request, 'LOGIN_BLOCKED_LOCKED', 'app_user', '', f'{email} (no such account)')
                return Response(LOCKED, status=status.HTTP_423_LOCKED)
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
            return Response(LOCKED, status=status.HTTP_423_LOCKED)

        # Authenticate
        auth_user = authenticate(request, username=email, password=password)

        if auth_user is None:
            user.failed_login_count += 1
            locked_now = user.failed_login_count >= MAX_FAILED_LOGINS
            if locked_now:
                user.locked_until = timezone.now() + timedelta(minutes=LOCK_MINUTES)
            user.save(update_fields=['failed_login_count', 'locked_until'])
            log_event(
                request, 'ACCOUNT_LOCKED' if locked_now else 'LOGIN_FAILED', 'app_user', user.id,
                f'{user.email}: wrong password ({user.failed_login_count} in a row)'
                + (f'; locked for {LOCK_MINUTES} minutes' if locked_now else ''),
                user=user,
            )
            return Response(INVALID, status=status.HTTP_401_UNAUTHORIZED)

        # Password is correct — reset lockout tracking either way.
        # `auth_user`, not the earlier `user`, since authenticate() may have
        # rehashed the password in the DB and `user` was loaded before that.
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

        totp = pyotp.TOTP(user.two_factor_secret)
        if not totp.verify(serializer.validated_data['code'], valid_window=1):
            # Six digits is only a million codes, and each accepts the ones
            # either side of it. Without a limit the code step could be
            # guessed through by script once the password was known.
            tries = request.session.get('pending_2fa_tries', 0) + 1
            if tries >= MAX_2FA_TRIES:
                request.session.pop('pending_2fa_user_id', None)
                request.session.pop('pending_2fa_tries', None)
                # Counts as a failed sign-in, so repeating this ends in the
                # usual lockout rather than an endless stream of guesses.
                user.failed_login_count += 1
                locked_now = user.failed_login_count >= MAX_FAILED_LOGINS
                if locked_now:
                    user.locked_until = timezone.now() + timedelta(minutes=LOCK_MINUTES)
                user.save(update_fields=['failed_login_count', 'locked_until'])
                log_event(
                    request, 'ACCOUNT_LOCKED' if locked_now else 'TWO_FACTOR_TOO_MANY', 'app_user', user.id,
                    f'{user.email}: {MAX_2FA_TRIES} wrong 2FA codes; login attempt cancelled'
                    + (f'; locked for {LOCK_MINUTES} minutes' if locked_now else ''),
                    user=user,
                )
                return Response(
                    {'error': 'Too many wrong codes. Sign in again with your password.'},
                    status=status.HTTP_429_TOO_MANY_REQUESTS,
                )
            request.session['pending_2fa_tries'] = tries
            log_event(request, 'TWO_FACTOR_FAILED', 'app_user', user.id,
                      f'{user.email}: wrong 2FA code ({tries} of {MAX_2FA_TRIES})', user=user)
            return Response(
                {'error': 'Incorrect code', 'tries_left': MAX_2FA_TRIES - tries},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        request.session.pop('pending_2fa_user_id', None)
        request.session.pop('pending_2fa_tries', None)
        user.last_login = timezone.now()
        user.save(update_fields=['last_login'])
        login(request, user)
        start_session_clock(request)
        log_event(request, 'LOGIN_SUCCESS', 'app_user', user.id, f'{user.email} (with 2FA)', user=user)

        return Response({
            'message': 'Login successful',
            'user': UserSerializer(user).data,
            'role': user.role.name if user.role else None,
        }, status=status.HTTP_200_OK)


@method_decorator(csrf_exempt, name='dispatch')
class TwoFactorSetupView(APIView):
    """
    POST /api/auth/2fa/setup/
    Starts enabling 2FA for the logged-in user: generates a new secret
    (not active yet) and returns a QR code to scan plus the secret for
    manual entry. Must be followed by a correct code to 2fa/confirm/.
    """
    permission_classes = [IsAuthenticated]
    authentication_classes = [CsrfExemptSessionAuthentication]

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


@method_decorator(csrf_exempt, name='dispatch')
class TwoFactorConfirmView(APIView):
    """
    POST /api/auth/2fa/confirm/
    Finishes enabling 2FA: checks a code against the secret from
    2fa/setup/, and if correct, turns 2FA on for this account.
    """
    permission_classes = [IsAuthenticated]
    authentication_classes = [CsrfExemptSessionAuthentication]

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


@method_decorator(csrf_exempt, name='dispatch')
class TwoFactorDisableView(APIView):
    """
    POST /api/auth/2fa/disable/
    Turns 2FA off, after confirming the user can still produce a
    correct code (not just that they're logged in).
    """
    permission_classes = [IsAuthenticated]
    authentication_classes = [CsrfExemptSessionAuthentication]

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


@method_decorator(csrf_exempt, name='dispatch')
class ChangePasswordView(APIView):
    """
    POST /api/auth/change-password/
    Body: { current_password, new_password }
    Any logged-in user (Admin, DRRMO, Barangay) can change their own password.
    """
    permission_classes = [IsAuthenticated]
    authentication_classes = [CsrfExemptSessionAuthentication]

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
        try:
            validate_password(new_password, user=request.user)
        except ValidationError as exc:
            return Response({'error': ' '.join(exc.messages)}, status=status.HTTP_400_BAD_REQUEST)
        request.user.set_password(new_password)
        request.user.save()
        # Re-login so the session stays valid after the password hash changes
        login(request, request.user)
        start_session_clock(request)
        log_event(request, 'PASSWORD_CHANGED', 'app_user', request.user.id, request.user.email)

        return Response({'message': 'Password changed successfully.'})


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