"""
Shared audit logging.

Lived as a private helper inside apps/hazards/views.py until reports needed
the same thing. One copy, so every logged action lands in AuditLog with the
same shape and the Logs tab can render them all the same way.
"""

from apps.admin_dashboard.models import AuditLog


def client_ip(request):
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


def log_event(request, action, table='', target_id='', details='', user=None):
    """
    Write one audit row.

    Deliberately swallows its own errors: an audit failure must never take
    down the action being audited. Publishing a hazard alert matters more
    than recording that it happened.
    """
    try:
        # Sign-in events happen before (or after) the request has a user,
        # so those callers name the account themselves.
        if user is None and getattr(request, 'user', None) is not None and request.user.is_authenticated:
            user = request.user
        AuditLog.objects.create(
            user=user,
            action=action,
            target_table=table,
            target_id=str(target_id),
            details=details,
            ip_address=client_ip(request),
        )
    except Exception:
        pass