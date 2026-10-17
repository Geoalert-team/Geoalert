"""
Sending hazard alerts.

Three paths put a hazard zone in front of people: a normal publish, a second
officer approving an Extreme alert, and an Extreme alert going out on its own
when nobody approves it in time. They all go through issue_alert(), so the
recipients and the wording can't drift apart between them.
"""

import logging
from datetime import timedelta

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.accounts.models import User
from apps.admin_dashboard.models import AuditLog
from apps.barangays.models import Barangay
from apps.hazards.models import HazardAlert, HazardZone
from apps.notifications.models import Notification

logger = logging.getLogger(__name__)

# Extreme alerts wait this long for a second officer, then go out anyway.
# Long enough for someone on duty to look; short enough that an empty
# office at 2 AM can't hold back a warning.
APPROVAL_WINDOW = timedelta(minutes=10)

OFFICER_ROLES = ['DRRMO_Officer', 'System_Admin']


def needs_second_approval(severity):
    return severity == 'Red'


def approval_due_at(zone):
    return zone.activated_at + APPROVAL_WINDOW if zone.activated_at else None


def affected_barangays(zone_or_geometry, manual_ids=None):
    """
    Which barangays a hazard zone actually touches.

    F2 calls for the affected barangays to be identified from the zone's
    geometry rather than from the single barangay the officer happened to
    tap: a 1 km zone can cross three of them, and only notifying one leaves
    the rest uninformed.

    manual_ids is the fallback the spec asks for when the GIS data can't
    answer - the officer names the barangays and we use those instead.

    Accepts a saved zone or, for the publish preview, a bare geometry.
    """
    if manual_ids:
        return list(Barangay.objects.filter(id__in=manual_ids))

    zone = zone_or_geometry if isinstance(zone_or_geometry, HazardZone) else None
    geometry = zone.geometry if zone else zone_or_geometry
    try:
        found = list(Barangay.objects.filter(boundary__intersects=geometry))
    except Exception:
        # A malformed boundary shouldn't stop an alert going out
        found = []

    if found:
        return found
    # No boundary data, or the zone sits outside every mapped boundary:
    # fall back to whatever barangay the zone itself records.
    return [zone.barangay] if zone and zone.barangay else []


def alert_recipients(publisher, barangays):
    """
    Who gets told. Barangay personnel assigned to an affected barangay, plus
    DRRMO and admins who need city-wide visibility.

    Anyone with no assigned barangay is included too: until every account has
    one set, excluding them would silently stop their alerts, which is a worse
    failure than one extra notification.
    """
    users = User.objects.filter(is_active=True)
    if publisher is not None:
        users = users.exclude(id=publisher.id)
    return (
        users
        .filter(
            Q(assigned_barangay__in=barangays)
            | Q(assigned_barangay__isnull=True)
            | Q(role__name__in=OFFICER_ROLES)
        )
        .distinct()
    )


def approvers_for(publisher):
    """Officers who could give the second approval: anyone but the publisher."""
    users = User.objects.filter(is_active=True, role__name__in=OFFICER_ROLES)
    if publisher is not None:
        users = users.exclude(id=publisher.id)
    return users


def where_text(barangays):
    return ', '.join(b.name for b in barangays) or 'Talisay City'


def type_name(zone):
    return zone.hazard_type.name if zone.hazard_type else 'Hazard'


def notify(users, content, zone=None):
    """A notice about a zone that is not the alert itself."""
    Notification.objects.bulk_create([
        Notification(hazard_alert=None, hazard_zone=zone, recipient=u, content=content)
        for u in users
    ])


def issue_alert(zone, issued_by, manual_ids=None, suffix=''):
    """
    Send the alert for a zone that has just gone live. Call inside a
    transaction: a hazard that is half-published - live but with nobody
    notified - is worse than one that failed outright.

    Returns (alert, barangays, recipients).
    """
    barangays = affected_barangays(zone, manual_ids)
    alert = HazardAlert.objects.create(
        hazard_zone=zone,
        issued_by=issued_by,
        hazard_type=zone.hazard_type,
        severity=zone.severity,
        notes=zone.description,
    )
    recipients = list(alert_recipients(zone.published_by or issued_by, barangays))
    Notification.objects.bulk_create([
        Notification(
            hazard_alert=alert,
            recipient=u,
            # Carries the hazard type, severity and every affected barangay.
            # The serializer adds the link through to the zone and its
            # safety guidance.
            content=f'{type_name(zone)} alert ({zone.severity}) for {where_text(barangays)}. '
                    f'Tap to see the hazard zone and what to do.{suffix}',
        )
        for u in recipients
    ])
    return alert, barangays, recipients


def release_overdue_approvals(now=None):
    """
    Send every Extreme alert that has waited past APPROVAL_WINDOW without a
    second officer. Returns how many went out.

    There is no task scheduler in this project, so this runs whenever
    something busy asks for hazards or notifications: the public map and
    every signed-in bell poll it. `manage.py release_pending_alerts` runs
    the same thing from cron for a quiet night.

    Each zone is locked with SKIP LOCKED, so two requests releasing at the
    same moment can't send the same alert twice, and an officer approving
    at the last second wins cleanly.
    """
    now = now or timezone.now()
    cutoff = now - APPROVAL_WINDOW
    if not HazardZone.objects.filter(status='Awaiting_Approval', activated_at__lte=cutoff).exists():
        return 0

    released = 0
    while True:
        with transaction.atomic():
            zone = (
                HazardZone.objects
                .select_for_update(skip_locked=True, of=('self',))
                .select_related('hazard_type', 'barangay', 'published_by')
                .filter(status='Awaiting_Approval', activated_at__lte=cutoff)
                .order_by('activated_at')
                .first()
            )
            if zone is None:
                break

            zone.status = 'Active'
            zone.auto_released = True
            zone.save(update_fields=['status', 'auto_released'])

            alert, barangays, recipients = issue_alert(
                zone, issued_by=zone.published_by,
                suffix=' Sent without a second approval after 10 minutes.',
            )
            if zone.published_by:
                notify(
                    [zone.published_by],
                    f'Your Extreme {type_name(zone)} alert for {where_text(barangays)} went out '
                    f'without a second approval: no officer answered within 10 minutes.',
                    zone,
                )
            AuditLog.objects.create(
                user=None,
                action='AUTO_RELEASE_HAZARD_ALERT',
                target_table='hazard_alert',
                target_id=str(alert.id),
                details=f'{type_name(zone)} / Red for {where_text(barangays)} sent without a '
                        f'second approval after the approval window. '
                        f'{len(recipients)} recipient(s) notified. Zone {zone.id}.',
            )
            released += 1
    return released


def release_overdue_quietly():
    """For request paths: a failure here must never break the map or the bell."""
    try:
        return release_overdue_approvals()
    except Exception:
        logger.exception('Releasing overdue Extreme alerts failed')
        return 0
