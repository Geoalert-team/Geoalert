from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.pagination import PageNumberPagination
from rest_framework import status
from django.utils import timezone

from apps.accounts.models import User
from apps.hazards.models import HazardZone
from apps.guidance.models import GuidanceContent
from apps.admin_dashboard.models import AuditLog
from apps.admin_dashboard.serializers import (
    UserListSerializer,
    UserCreateSerializer,
    UserUpdateSerializer,
    AuditLogSerializer,
)
from utils.permissions import IsSystemAdmin


def log_action(user, action, target_table='', target_id='', details='', request=None):
    """Helper to create an audit log entry."""
    ip = None
    if request:
        ip = request.META.get('REMOTE_ADDR')
    AuditLog.objects.create(
        user=user,
        action=action,
        target_table=target_table,
        target_id=str(target_id),
        details=details,
        ip_address=ip,
    )


class DashboardMetricsView(APIView):
    """
    GET /api/admin-dashboard/metrics/
    Returns dashboard overview: total users, active hazards,
    recent alerts, system status. System Admin only.
    """
    permission_classes = [IsAuthenticated, IsSystemAdmin]

    def get(self, request):
        total_users     = User.objects.count()
        active_users    = User.objects.filter(is_active=True).count()
        active_hazards  = HazardZone.objects.filter(status='Active').count()
        published_guidance = GuidanceContent.objects.filter(is_published=True).count()
        recent_logs     = AuditLog.objects.all()[:5]

        return Response({
            'total_users':          total_users,
            'active_users':         active_users,
            'active_hazards':       active_hazards,
            'published_guidance':   published_guidance,
            'recent_activity':      AuditLogSerializer(recent_logs, many=True).data,
            'system_status':        'Operational',
        })


class UserListCreateView(APIView):
    """
    GET  /api/admin-dashboard/users/ → List all users
    POST /api/admin-dashboard/users/ → Create new user
    System Admin only.
    """
    permission_classes = [IsAuthenticated, IsSystemAdmin]

    def get(self, request):
        users = User.objects.all().order_by('-created_at')

        search = request.query_params.get('search')
        if search:
            users = users.filter(full_name__icontains=search)

        role = request.query_params.get('role')
        if role:
            users = users.filter(role__name=role)

        return Response(UserListSerializer(users, many=True).data)

    def post(self, request):
        serializer = UserCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        if User.objects.filter(email=serializer.validated_data['email']).exists():
            return Response(
                {'error': 'A user with this email already exists. Please use a different email address.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        user = serializer.save()

        log_action(
            request.user, 'CREATE_USER', 'user', user.id,
            f'Created user {user.email} with role {user.role.name}',
            request
        )

        return Response({
            'message': 'User created successfully',
            'user': UserListSerializer(user).data,
            'temporary_password': user._temp_password,
        }, status=status.HTTP_201_CREATED)


class UserDetailView(APIView):
    """
    PUT    /api/admin-dashboard/users/<id>/ → Edit user
    DELETE /api/admin-dashboard/users/<id>/ → Deactivate user
    System Admin only.
    """
    permission_classes = [IsAuthenticated, IsSystemAdmin]

    def put(self, request, pk):
        try:
            user = User.objects.get(pk=pk)
        except User.DoesNotExist:
            return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)

        serializer = UserUpdateSerializer(user, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        user = serializer.save()

        log_action(
            request.user, 'EDIT_USER', 'user', user.id,
            f'Updated user {user.email}', request
        )

        return Response(UserListSerializer(user).data)

    def delete(self, request, pk):
        if str(request.user.id) == str(pk):
            return Response(
                {'error': 'You cannot delete your own account. Please contact another administrator.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            user = User.objects.get(pk=pk)
        except User.DoesNotExist:
            return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)

        user.is_active = False
        user.save()

        log_action(
            request.user, 'DEACTIVATE_USER', 'user', user.id,
            f'Deactivated user {user.email}', request
        )

        return Response({'message': 'User deactivated successfully'})


class ResetPasswordView(APIView):
    """
    POST /api/admin-dashboard/users/<id>/reset-password/
    Generates a temporary password. System Admin only.
    """
    permission_classes = [IsAuthenticated, IsSystemAdmin]

    def post(self, request, pk):
        try:
            user = User.objects.get(pk=pk)
        except User.DoesNotExist:
            return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)

        import secrets
        import string
        temp_password = ''.join(
            secrets.choice(string.ascii_letters + string.digits + '!@#')
            for _ in range(12)
        )
        user.set_password(temp_password)
        user.failed_login_count = 0
        user.locked_until = None
        user.save()

        log_action(
            request.user, 'RESET_PASSWORD', 'user', user.id,
            f'Reset password for {user.email}', request
        )

        return Response({
            'message': 'Password reset successfully',
            'temporary_password': temp_password,
        })


class AuditLogPagination(PageNumberPagination):
    page_size = 25


class AuditLogListView(APIView):
    """
    GET /api/admin-dashboard/logs/
    Returns paginated audit logs with filters.
    System Admin only.

    Filters:
      ?date_from=2026-01-01&date_to=2026-12-31
      ?action=LOGIN
    """
    permission_classes = [IsAuthenticated, IsSystemAdmin]

    def get(self, request):
        logs = AuditLog.objects.all()

        date_from = request.query_params.get('date_from')
        if date_from:
            logs = logs.filter(created_at__gte=date_from)

        date_to = request.query_params.get('date_to')
        if date_to:
            logs = logs.filter(created_at__lte=date_to)

        action = request.query_params.get('action')
        if action:
            logs = logs.filter(action__icontains=action)

        paginator = AuditLogPagination()
        page = paginator.paginate_queryset(logs, request)
        serializer = AuditLogSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)