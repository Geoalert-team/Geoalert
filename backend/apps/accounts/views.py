from django.contrib.auth import authenticate, login, logout
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework import status
from datetime import timedelta

from apps.accounts.models import User
from apps.accounts.serializers import LoginSerializer, UserSerializer


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

        # Success
        user.failed_login_count = 0
        user.locked_until = None
        user.last_login = timezone.now()
        user.save()

        login(request, auth_user)

        return Response({
            'message': 'Login successful',
            'user': UserSerializer(user).data,
            'role': user.role.name if user.role else None,
        }, status=status.HTTP_200_OK)


@method_decorator(csrf_exempt, name='dispatch')
class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        logout(request)
        return Response({'message': 'Logged out successfully'})


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(UserSerializer(request.user).data)