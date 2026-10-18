"""
Sending hazard alerts.

Three paths put a hazard zone in front of people: a normal publish, a second
officer approving an Extreme alert, and an Extreme alert going out on its own
when nobody approves it in time. They all go through issue_alert(), so the
recipients and the wording can't drift apart between them.
"""

import logging
from datetime import timedelta

from django.core.cache import cache
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


# An Extreme alert nobody in a barangay has opened after this long is sent
# to them again, once, and the publisher is told who hasn't read it.
REMIND_AFTER = timedelta(minutes=15)

# A zone left Active this long with no officer update: remind the publisher
# to resolve it or bring it up to date, then again every STALE_AFTER.
STALE_AFTER = timedelta(hours=24)

SEVERITY_LABEL = {'Red': 'Extreme', 'Orange': 'Moderate', 'Green': 'Low'}


def touch(zone, now=None):
    """An officer just acted on this zone: restart its 24-hour reminder clock."""
    zone.next_nudge_at = (now or timezone.now()) + STALE_AFTER


def approval_due_at(zone):
    """When a held Extreme alert, or a held raise to Extreme, goes out on its own."""
    if zone.status == 'Active' and zone.pending_severity and zone.pending_at:
        return zone.pending_at + APPROVAL_WINDOW
    return zone.activated_at + APPROVAL_WINDOW if zone.activated_at else None


def request_raise(zone, requested_by, now=None):
    """
    Hold a live zone's raise to Extreme for a second officer. The zone stays
    live at its current severity meanwhile; taking it off the map to wait
    would hide a hazard that is already there.
    """
    zone.pending_severity = 'Red'
    zone.pending_by = requested_by
    zone.pending_at = now or timezone.now()
    barangays = affected_barangays(zone)
    notify(
        approvers_for(requested_by),
        f'Approval needed: raise the {type_name(zone)} alert for {where_text(barangays)} to Extreme, '
        f'asked by {requested_by.full_name}. It is raised automatically at '
        f'{timezone.localtime(zone.pending_at + APPROVAL_WINDOW):%I:%M %p} if no officer answers.',
        zone,
    )


def apply_raise(zone, approver=None, auto=False):
    """
    Make a held raise to Extreme happen and send the Extreme alert. Call
    inside a transaction. approver None with auto=True means the window ran
    out with nobody answering.
    """
    requested_by = zone.pending_by
    zone.severity = 'Red'
    zone.reset_verification()  # the barangays answered for a lower severity
    zone.pending_severity = ''
    zone.pending_by = None
    zone.pending_at = None
    zone.approved_by = approver
    zone.approved_at = timezone.now() if approver else None
    zone.auto_released = auto
    zone.save()
    suffix = ' Raised to Extreme.' + (' Sent without a second approval after 10 minutes.' if auto else '')
    alert, barangays, recipients = issue_alert(zone, issued_by=requested_by or approver, suffix=suffix)
    if requested_by and requested_by != approver:
        notify(
            [requested_by],
            (f'{approver.full_name} approved raising the {type_name(zone)} alert for '
             f'{where_text(barangays)} to Extreme. It has been sent.') if approver else
            (f'The {type_name(zone)} alert for {where_text(barangays)} was raised to Extreme '
             f'without a second approval: no officer answered within 10 minutes.'),
            zone,
        )
    return alert, barangays, recipients


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
    touch(zone)
    HazardZone.objects.filter(pk=zone.pk).update(next_nudge_at=zone.next_nudge_at)
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
    if not HazardZone.objects.filter(
        Q(status='Awaiting_Approval', activated_at__lte=cutoff)
        | Q(status='Active', pending_severity='Red', pending_at__lte=cutoff)
    ).exists():
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

    # Raises to Extreme on live zones that nobody answered
    while True:
        with transaction.atomic():
            zone = (
                HazardZone.objects
                .select_for_update(skip_locked=True, of=('self',))
                .select_related('hazard_type', 'barangay', 'published_by', 'pending_by')
                .filter(status='Active', pending_severity='Red', pending_at__lte=cutoff)
                .order_by('pending_at')
                .first()
            )
            if zone is None:
                break
            alert, barangays, recipients = apply_raise(zone, approver=None, auto=True)
            AuditLog.objects.create(
                user=None,
                action='AUTO_RELEASE_HAZARD_RAISE',
                target_table='hazard_alert',
                target_id=str(alert.id),
                details=f'{type_name(zone)} raised to Red for {where_text(barangays)} without a '
                        f'second approval after the approval window. '
                        f'{len(recipients)} recipient(s) notified. Zone {zone.id}.',
            )
            released += 1
    return released


def remind_unread_extreme(now=None):
    """
    Re-send Extreme alerts that barangay personnel haven't opened after
    REMIND_AFTER, once per alert, and tell the officer who published it
    which barangays haven't read it. Returns how many alerts were followed up.

    Only personnel are reminded: they act on the ground, and DRRMO already
    has the map and the dashboard. Alerts more than a day old are left
    alone, so turning this on doesn't remind people about last week.
    """
    now = now or timezone.now()
    due = HazardAlert.objects.filter(
        severity='Red',
        reminded_at__isnull=True,
        created_at__lte=now - REMIND_AFTER,
        created_at__gte=now - timedelta(days=1),
        hazard_zone__status='Active',
    )
    if not due.exists():
        return 0

    done = 0
    while True:
        with transaction.atomic():
            alert = (
                HazardAlert.objects
                .select_for_update(skip_locked=True, of=('self',))
                .select_related('hazard_zone', 'hazard_zone__hazard_type', 'hazard_zone__published_by')
                .filter(pk__in=due.values('pk'), reminded_at__isnull=True)
                .order_by('created_at')
                .first()
            )
            if alert is None:
                break
            alert.reminded_at = now
            alert.save(update_fields=['reminded_at'])
            zone = alert.hazard_zone
            unread = list(
                Notification.objects
                .filter(hazard_alert=alert, is_read=False, recipient__is_active=True,
                        recipient__role__name='Barangay_Personnel')
                .select_related('recipient__assigned_barangay')
            )
            if unread:
                notify(
                    [n.recipient for n in unread],
                    f'REMINDER: Extreme {type_name(zone)} alert for your barangay. '
                    f'You have not opened it yet. Tap to see the hazard zone and what to do.',
                    zone,
                )
                places = sorted({n.recipient.assigned_barangay.name for n in unread if n.recipient.assigned_barangay})
                if zone.published_by and zone.published_by.is_active:
                    notify(
                        [zone.published_by],
                        f'{len(unread)} barangay personnel have not opened your Extreme {type_name(zone)} alert '
                        f'after 15 minutes ({", ".join(places) or "no barangay set"}). They were reminded.',
                        zone,
                    )
                AuditLog.objects.create(
                    user=None,
                    action='REMIND_UNREAD_ALERT',
                    target_table='hazard_alert',
                    target_id=str(alert.id),
                    details=f'{len(unread)} unread after 15 minutes; reminded. Barangays: {", ".join(places) or "-"}.',
                )
            done += 1
    return done


def all_clear(zone, resolved_by, summary=''):
    """
    Tell everyone who got this zone's alert that it is over.

    Resolving used to tell nobody: residents who were warned about a flood
    never heard that it had passed, unless they happened to open the map.
    Withdrawal already sent a notice; this is the same for a real hazard
    that has ended. Everyone who received any alert for the zone is told
    once, except the officer resolving it.
    """
    recipients = (
        User.objects
        .filter(is_active=True, notifications__hazard_alert__hazard_zone=zone)
        .exclude(id=getattr(resolved_by, 'id', None))
        .distinct()
    )
    where = where_text(affected_barangays(zone))
    note = f' {summary.strip()}' if summary and summary.strip() else ''
    users = list(recipients)
    notify(
        users,
        f'ALL CLEAR: the {type_name(zone)} alert for {where} has been resolved by DRRMO.{note}',
        zone,
    )
    return users, where


def nudge_stale_zones(now=None):
    """
    Remind publishers about zones left Active with no update for 24 hours.
    Returns how many zones were flagged.

    A zone nobody resolves stays on the public map, alarming people about a
    flood that drained yesterday. The publisher is asked to resolve it or
    bring it up to date; if they no longer have an active account, every
    officer is asked instead. Sample zones are left alone.
    """
    now = now or timezone.now()
    due = HazardZone.objects.filter(status='Active', is_sample=False, next_nudge_at__lte=now)
    if not due.exists():
        return 0

    done = 0
    while True:
        with transaction.atomic():
            zone = (
                HazardZone.objects
                .select_for_update(skip_locked=True, of=('self',))
                .select_related('hazard_type', 'published_by')
                .filter(status='Active', is_sample=False, next_nudge_at__lte=now)
                .order_by('next_nudge_at')
                .first()
            )
            if zone is None:
                break
            last_change = zone.next_nudge_at - STALE_AFTER
            idle_hours = max(int((now - last_change).total_seconds() // 3600), 24)
            zone.next_nudge_at = now + STALE_AFTER
            zone.save(update_fields=['next_nudge_at'])

            publisher = zone.published_by if zone.published_by and zone.published_by.is_active else None
            who = [publisher] if publisher else list(approvers_for(None))
            where = where_text(affected_barangays(zone))
            notify(
                who,
                f'Still active? The {type_name(zone)} zone ({SEVERITY_LABEL.get(zone.severity, zone.severity)}) '
                f'for {where} has had no update for {idle_hours} hours. Resolve it if it is over, or change '
                f'its severity or area so the public map stays accurate.',
                zone,
            )
            AuditLog.objects.create(
                user=None,
                action='STALE_ZONE_REMINDER',
                target_table='hazard_zone',
                target_id=str(zone.id),
                details=f'{type_name(zone)} for {where}: no update for {idle_hours} h; '
                        f'reminded {"the publisher" if publisher else f"{len(who)} officer(s)"}.',
            )
            done += 1
    return done


# How often request paths look for overdue alerts. The map and every bell
# poll call in, so without a limit this was a database query on almost
# every request to answer a question that changes once in ten minutes.
RELEASE_CHECK_EVERY = 20  # seconds


def release_overdue_quietly():
    """For request paths: a failure here must never break the map or the bell."""
    try:
        # cache.add only succeeds for the first caller in each window, across
        # every worker sharing the cache. If the cache itself fails, check
        # anyway: a late alert is worse than an extra query.
        try:
            if not cache.add('geoalert:release-check', 1, timeout=RELEASE_CHECK_EVERY):
                return 0
        except Exception:
            logger.warning('Cache unavailable; checking for overdue alerts without a limit')
        released = release_overdue_approvals()
        remind_unread_extreme()
        nudge_stale_zones()
        return released
    except Exception:
        logger.exception('Releasing overdue Extreme alerts failed')
        return 0
