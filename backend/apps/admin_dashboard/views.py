from datetime import timedelta

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.pagination import PageNumberPagination
from rest_framework import status
from django.db.models import Count, Q
from django.utils import timezone

from apps.accounts.models import User
from apps.hazards.models import HazardZone, HazardAlert
from apps.notifications.models import Notification
from apps.guidance.models import GuidanceContent
from apps.admin_dashboard.models import AuditLog
from apps.accounts.models import User, Role
from apps.admin_dashboard.serializers import (
    UserListSerializer,
    UserCreateSerializer,
    UserUpdateSerializer,
    AuditLogSerializer,
    RolesSerializer,
    generate_temp_password,
)
from utils.permissions import IsSystemAdmin, IsDRRMOOfficer
from utils.health import system_health


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


# Fields compared before/after an edit so the audit log says what changed
TRACKED_USER_FIELDS = [
    'first_name', 'middle_initial', 'last_name', 'suffix', 'email', 'phone',
    'employee_id', 'position', 'role_id', 'assigned_barangay_id', 'is_active',
]


class DashboardMetricsView(APIView):
    """
    GET /api/admin-dashboard/metrics/
    Returns dashboard overview: total users, active hazards,
    recent alerts, system status. System Admin only.
    """
    permission_classes = [IsAuthenticated, IsSystemAdmin]

    def get(self, request):
        health = system_health()

        total_users     = User.objects.count()
        active_users    = User.objects.filter(is_active=True).count()
        active_hazards  = HazardZone.objects.filter(status='Active').count()
        published_guidance = GuidanceContent.objects.filter(is_published=True).count()
        recent_logs     = AuditLog.objects.select_related('user')[:6]
        users_by_role   = {
            row['role__name'] or 'Unassigned': row['count']
            for row in User.objects.values('role__name').annotate(count=Count('id'))
        }

        return Response({
            'total_users':          total_users,
            'active_users':         active_users,
            'inactive_users':       total_users - active_users,
            'users_by_role':        users_by_role,
            'active_hazards':       active_hazards,
            'published_guidance':   published_guidance,
            'recent_activity':      AuditLogSerializer(recent_logs, many=True).data,
            # Was the literal string 'Operational', which nothing could ever
            # change. Now the result of real checks — see utils/health.py.
            'system_status':        health['status'],
            'system_health':        health,
        })


class UserListCreateView(APIView):
    """
    GET  /api/admin-dashboard/users/ â†’ List all users
    POST /api/admin-dashboard/users/ â†’ Create new user
    System Admin only.
    """
    permission_classes = [IsAuthenticated, IsSystemAdmin]

    def get(self, request):
        users = User.objects.select_related('role', 'assigned_barangay').order_by('-created_at')

        search = request.query_params.get('search')
        if search:
            users = users.filter(
                Q(full_name__icontains=search) | Q(email__icontains=search) |
                Q(position__icontains=search) | Q(employee_id__icontains=search) |
                Q(assigned_barangay__name__icontains=search)
            )

        role = request.query_params.get('role')
        if role:
            users = users.filter(role__name=role)

        return Response(UserListSerializer(users, many=True).data)

    def post(self, request):
        serializer = UserCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        user = serializer.save()

        log_action(
            request.user, 'CREATE_USER', 'user', user.id,
            f'Created user {user.email} ({user.full_name}) as {user.role.get_name_display()}',
            request
        )

        return Response({
            'message': 'User created successfully',
            'user': UserListSerializer(user).data,
            'temporary_password': user._temp_password,
        }, status=status.HTTP_201_CREATED)


class UserDetailView(APIView):
    """
    PUT    /api/admin-dashboard/users/<id>/ â†’ Edit user
    DELETE /api/admin-dashboard/users/<id>/ â†’ Deactivate user
    System Admin only.
    """
    permission_classes = [IsAuthenticated, IsSystemAdmin]

    def put(self, request, pk):
        try:
            user = User.objects.get(pk=pk)
        except User.DoesNotExist:
            return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)

        if str(request.user.id) == str(pk) and request.data.get('is_active') is False:
            return Response(
                {'error': 'You cannot deactivate your own account.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        serializer = UserUpdateSerializer(user, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        before = {f: getattr(user, f) for f in TRACKED_USER_FIELDS}
        user = serializer.save()
        changed = [f for f in TRACKED_USER_FIELDS if getattr(user, f) != before[f]]

        if changed == ['is_active']:
            action = 'ACTIVATE_USER' if user.is_active else 'DEACTIVATE_USER'
            verb = 'Activated' if user.is_active else 'Deactivated'
            details = f'{verb} user {user.email}'
        else:
            action = 'EDIT_USER'
            labels = ', '.join(f.replace('_id', '').replace('_', ' ') for f in changed)
            details = f'Updated user {user.email}' + (f' ({labels})' if labels else '')

        log_action(request.user, action, 'user', user.id, details, request)

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

        temp_password = generate_temp_password()
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
    page_size = 10


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
        logs = AuditLog.objects.select_related('user')

        date_from = request.query_params.get('date_from')
        if date_from:
            logs = logs.filter(created_at__date__gte=date_from)

        date_to = request.query_params.get('date_to')
        if date_to:
            logs = logs.filter(created_at__date__lte=date_to)

        action = request.query_params.get('action')
        if action:
            logs = logs.filter(action__iexact=action)

        paginator = AuditLogPagination()
        page = paginator.paginate_queryset(logs, request)
        serializer = AuditLogSerializer(page, many=True)

        return paginator.get_paginated_response(serializer.data)


class AlertMonitorView(APIView):
    """
    GET /api/admin-dashboard/alerts/
    Notification and alert monitoring (WBS 3.8.5).

    Publishing a hazard fans an alert out to every account in the affected
    barangays. Nothing until now showed whether that actually landed, so a
    hazard alert that reached nobody looked exactly like one that reached
    everybody. This reports, per alert, how many accounts it was sent to and
    how many of those have opened it.

    Open to DRRMO Officers as well as System Admins: the officer who issued
    an alert is the one who needs to know it went nowhere.

    Filters:
      ?days=7        window in days, 1-90, default 7
      ?severity=Red  Red | Orange | Green
      ?page=1        20 alerts per page

    The summary describes the whole window, not the page being shown.
    """
    permission_classes = [IsAuthenticated, IsDRRMOOfficer]
    PAGE_SIZE = 20

    def get(self, request):
        try:
            days = min(max(int(request.query_params.get('days', 7)), 1), 90)
        except (TypeError, ValueError):
            days = 7
        since = timezone.now() - timedelta(days=days)

        severity = request.query_params.get('severity')

        base = HazardAlert.objects.filter(created_at__gte=since)
        if severity:
            base = base.filter(severity__iexact=severity)

        # --- Summary across the window -------------------------------------
        notifications = Notification.objects.filter(hazard_alert__created_at__gte=since)
        if severity:
            notifications = notifications.filter(hazard_alert__severity__iexact=severity)

        sent = notifications.count()
        read = notifications.filter(is_read=True).count()
        reached = notifications.values('recipient_id').distinct().count()

        # The number worth watching: alerts that went out to nobody at all,
        # which usually means no account is assigned to that barangay.
        silent = base.annotate(n=Count('notifications')).filter(n=0).count()

        by_severity = list(
            base.values('severity').annotate(count=Count('id')).order_by('-count')
        )

        # --- One page of alerts --------------------------------------------
        alerts = (
            base
            .select_related('hazard_type', 'issued_by', 'hazard_zone', 'hazard_zone__barangay')
            .annotate(
                recipient_count=Count('notifications', distinct=True),
                read_count=Count(
                    'notifications',
                    filter=Q(notifications__is_read=True),
                    distinct=True,
                ),
            )
            .order_by('-created_at')
        )

        total = base.count()
        try:
            page = max(int(request.query_params.get('page', 1)), 1)
        except (TypeError, ValueError):
            page = 1
        start = (page - 1) * self.PAGE_SIZE

        results = []
        for alert in alerts[start:start + self.PAGE_SIZE]:
            zone = alert.hazard_zone
            recipients = alert.recipient_count
            results.append({
                'id':           str(alert.id),
                'hazard_type':  alert.hazard_type.name if alert.hazard_type else None,
                'severity':     alert.severity,
                'barangay':     zone.barangay.name if zone and zone.barangay else None,
                'issued_by':    alert.issued_by.full_name if alert.issued_by else None,
                'created_at':   alert.created_at,
                'notes':        alert.notes,
                'zone_id':      str(zone.id) if zone else None,
                'zone_status':  zone.status if zone else None,
                'is_sample':    bool(zone.is_sample) if zone else False,
                'recipients':   recipients,
                'read':         alert.read_count,
                'unread':       recipients - alert.read_count,
                # None rather than 0 when nobody was notified: "no one has
                # read it" and "it was never sent" are different failures.
                'read_rate':    round(alert.read_count / recipients * 100, 1) if recipients else None,
            })

        return Response({
            'window_days': days,
            'summary': {
                'alerts_issued':        total,
                'notifications_sent':   sent,
                'notifications_read':   read,
                'notifications_unread': sent - read,
                'read_rate':            round(read / sent * 100, 1) if sent else None,
                'accounts_reached':     reached,
                'alerts_with_no_recipients': silent,
            },
            'by_severity': by_severity,
            'count':       total,
            'page':        page,
            'page_size':   self.PAGE_SIZE,
            'results':     results,
        })


class SystemHealthView(APIView):
    """
    GET /api/admin-dashboard/health/

    What the dashboard's status indicator is actually reading. Returns

        {"status": "Operational" | "Degraded" | "Down",
         "failing": ["Alert routing"],
         "checks": [{"key", "label", "state", "detail"}, ...]}

    Separate from the metrics endpoint so the indicator keeps working when
    the metrics queries fail, and so the checks can be read on their own.

    Answers 200 even when checks fail — the body carries the bad news.
    A non-200 from this endpoint means something below the checks is wrong
    (the server is not running, or the database is so unavailable that the
    request could not even be authenticated), and the dashboard shows that
    as Down rather than hiding it.
    """
    permission_classes = [IsAuthenticated, IsSystemAdmin]

    def get(self, request):
        return Response(system_health())


class RolesListView(APIView):
    """
    GET /api/admin-dashboard/roles/
    Returns all roles, for populating the role dropdown on user creation.
    System Admin only.
    """
    permission_classes = [IsAuthenticated, IsSystemAdmin]

    def get(self, request):
        roles = Role.objects.all().order_by('id')
        return Response(RolesSerializer(roles, many=True).data)