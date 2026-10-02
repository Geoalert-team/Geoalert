import base64
import io

import pyotp
import qrcode
from django.contrib.auth import authenticate, login, logout
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
            return Response(
                {'error': 'Invalid email or password'},
                status=status.HTTP_401_UNAUTHORIZED
            )

        # Check lockout
        if user.is_locked():
            return Response(
                {'error': 'Account locked. Try again in 15 minutes.'},
                status=status.HTTP_423_LOCKED
            )

        # Authenticate
        auth_user = authenticate(request, username=email, password=password)

        if auth_user is None:
            user.failed_login_count += 1
            if user.failed_login_count >= 5:
                user.locked_until = timezone.now() + timedelta(minutes=15)
            user.save()
            return Response(
                {'error': 'Invalid email or password'},
                status=status.HTTP_401_UNAUTHORIZED
            )

        # Password is correct — reset lockout tracking either way.
        # `auth_user`, not the earlier `user`, since authenticate() may have
        # rehashed the password in the DB and `user` was loaded before that.
        auth_user.failed_login_count = 0
        auth_user.locked_until = None
        auth_user.save()

        # If 2FA is on, stop here — don't start a logged-in session yet.
        # Stash which user passed the password step in this (still
        # anonymous) session, and ask the frontend for the 6-digit code next.
        if auth_user.two_factor_enabled:
            request.session['pending_2fa_user_id'] = str(auth_user.id)
            return Response({'require_2fa': True}, status=status.HTTP_200_OK)

        # No 2FA — log in now, same as before.
        auth_user.last_login = timezone.now()
        auth_user.save()
        login(request, auth_user)

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
            return Response({'error': 'Incorrect code'}, status=status.HTTP_401_UNAUTHORIZED)

        request.session.pop('pending_2fa_user_id', None)
        user.last_login = timezone.now()
        user.save()
        login(request, user)

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
        secret = pyotp.random_base32()
        request.user.two_factor_secret = secret
        request.user.save()

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
        request.user.save()

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
        request.user.save()

        return Response({
            'message': 'Two-factor authentication disabled',
            'user': UserSerializer(request.user).data,
        })


@method_decorator(csrf_exempt, name='dispatch')
class LogoutView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [CsrfExemptSessionAuthentication]

    def post(self, request):
        logout(request)
        return Response({'message': 'Logged out successfully'})


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(UserSerializer(request.user).data)