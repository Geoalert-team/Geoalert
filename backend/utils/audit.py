"""
Shared audit logging.

Lived as a private helper inside apps/hazards/views.py until reports needed
the same thing. One copy, so every logged action lands in AuditLog with the
same shape and the Logs tab can render them all the same way.
"""

import logging

from django.db import transaction

from apps.admin_dashboard.models import AuditLog
from utils.login_throttle import throttle_ip

logger = logging.getLogger('geoalert.audit')

# The audit_log columns' lengths (apps/admin_dashboard/models.py)
SHORT = 100


def client_ip(request):
    """The visitor's address, by the same rule as the login throttle, so a forged header can't reach the log."""
    ip = throttle_ip(request)
    return None if ip == 'unknown' else ip


def _write(**fields):
    # A savepoint, so a refused row can't abort a transaction the caller is in
    with transaction.atomic():
        AuditLog.objects.create(**fields)


def log_event(request, action, table='', target_id='', details='', user=None):
    """
    Write one audit row.

    An audit failure must never take down the action being audited:
    publishing a hazard alert matters more than recording that it happened.
    But it mustn't vanish either. A header that wasn't an address once made
    every row fail silently (security audit GA-01), so a refused row is tried
    again without the address and said in the server log, and only a second
    failure is given up on, loudly.
    """
    try:
        # Sign-in events happen before (or after) the request has a user,
        # so those callers name the account themselves.
        if user is None and getattr(request, 'user', None) is not None and request.user.is_authenticated:
            user = request.user
    except Exception:
        user = None
    fields = {
        'user': user,
        'action': str(action)[:SHORT],
        'target_table': str(table)[:SHORT],
        'target_id': str(target_id)[:SHORT],
        'details': str(details),
    }
    try:
        ip = client_ip(request)
    except Exception:
        ip = None
    try:
        _write(**fields, ip_address=ip)
        return
    except Exception:
        logger.exception('Audit row refused (%s); retrying without the address', fields['action'])
    try:
        _write(**fields, ip_address=None)
    except Exception:
        logger.exception('Audit row lost: %s %s %s', fields['action'], fields['target_table'], fields['target_id'])
