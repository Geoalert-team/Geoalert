import json
import logging

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework import status
from django.contrib.gis.geos import Polygon
from django.db import DatabaseError, connection, transaction
from django.db.models import Count, Q
from django.utils import timezone

from apps.notifications.models import Notification
from apps.accounts.models import User
from apps.barangays.models import Barangay
from apps.history.models import HistoricalRecord

from apps.hazards.geometry import main_barangay, overlap_shares, overlapping_puroks
from apps.reports.decide import zone_puroks
from apps.hazards.models import HazardType, HazardZone, HazardAlert, HazardVerification
from apps.hazards.serializers import (
    clean_zone_geometry,
    HazardZoneGeoSerializer,
    HazardZoneSerializer,
    HazardZoneCreateSerializer,
    HazardTypeSerializer,
)
from rest_framework_gis.fields import GeometryField
from rest_framework.exceptions import ValidationError as DRFValidationError
from utils.permissions import IsDRRMOOfficer, IsBarangayPersonnel
from utils.audit import log_event
from utils import map_version

from apps.hazards.alerts import (
    affected_barangays,
    all_clear,
    alert_recipients,
    approval_window,
    apply_raise,
    approval_due_at,
    approvers_for,
    issue_alert,
    needs_second_approval,
    notify,
    release_overdue_quietly,
    request_raise,
    touch,
    type_name,
    where_text,
)

logger = logging.getLogger(__name__)

# An active zone of the same hazard type already covering this share of a
# new drawing is most likely the same event: the officer is asked to update
# that zone instead, and has to say so to publish anyway.
DUPLICATE_SHARE = 0.5


def find_duplicates(geometry, hazard_type):
    """
    Active (or held) zones of the same hazard type that overlap a new
    drawing, most-overlapping first, each with the share of the new drawing
    it already covers (0-1).
    """
    zones = list(
        HazardZone.objects
        .filter(
            status__in=['Active', 'Awaiting_Approval'],
            hazard_type=hazard_type,
            geometry__intersects=geometry,
        )
        .select_related('hazard_type', 'barangay', 'published_by')
    )
    shares = overlap_shares(geometry, [z.id for z in zones])
    found = [
        {
            'id': str(z.id),
            'type': type_name(z),
            'severity': z.severity,
            'status': z.status,
            'barangay': z.barangay.name if z.barangay else None,
            'activated_at': z.activated_at,
            'published_by': z.published_by.full_name if z.published_by else None,
            'overlap': round(shares.get(z.id, 0), 3),
            'major': shares.get(z.id, 0) >= DUPLICATE_SHARE,
        }
        for z in zones
    ]
    found.sort(key=lambda d: d['overlap'], reverse=True)
    return found


def _as_count(value):
    """
    Turn whatever the frontend sent for a casualty/displaced count into
    either a non-negative int or None ("not recorded").

    '' / None / 'n/a' / '-3' all become None rather than 0, because
    'zero casualties' and 'nobody counted yet' are different facts and
    the report totals should not treat a blank field as a confirmed zero.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


def link_report(request, zone):
    """
    Published from a validated incident report ("Publish hazard here" on the
    dashboard): record which zone came of it, so the report shows it was
    acted on and the same report isn't published twice.
    """
    report_id = request.data.get('incident_report')
    if not report_id:
        return
    from apps.reports.models import IncidentReport
    try:
        IncidentReport.objects.filter(
            id=report_id, status='Validated', hazard_zone__isnull=True,
        ).update(hazard_zone=zone)
    except Exception:
        pass  # a bad report id must not stop the alert going out


def parse_bbox(value):
    """
    ?bbox=xmin,ymin,xmax,ymax (longitude, latitude, WGS84) as a Polygon.
    Raises ValueError with a sentence the caller can show.
    """
    try:
        xmin, ymin, xmax, ymax = [float(x) for x in value.split(',')]
    except ValueError:
        raise ValueError('bbox must be four numbers: xmin,ymin,xmax,ymax (longitude, latitude).')
    if xmin >= xmax or ymin >= ymax:
        raise ValueError('bbox must have xmin below xmax and ymin below ymax.')
    if not (-180 <= xmin <= 180 and -180 <= xmax <= 180 and -90 <= ymin <= 90 and -90 <= ymax <= 90):
        raise ValueError('bbox must be longitude and latitude in degrees.')
    box = Polygon.from_bbox((xmin, ymin, xmax, ymax))
    box.srid = 4326
    return box


def filter_by_bbox(zones, request):
    """
    F3.3: hazard zone query by bounding box, with ST_Within and ST_Intersects.

    ?bbox=xmin,ymin,xmax,ymax           every zone at least partly in the box
                                        (ST_Intersects), each marked by
                                        ST_Within as wholly or partly in view
    ?bbox=...&within=true               only zones entirely inside the box
                                        (ST_Within)

    The default keeps zones that are only partly on screen: a map that
    dropped a flood zone because its edge ran off the side would hide a
    hazard the user is looking at. ST_Within is what tells the two apart,
    and the strict form is there for anything that wants only zones it can
    see in full, such as a printed map of one area.

    Returns (zones, within_ids, error_response). within_ids is None when no
    bbox was given; error_response is set when the bbox is malformed, which
    used to be ignored silently and return every zone.
    """
    value = request.query_params.get('bbox')
    if not value:
        return zones, None, None
    try:
        box = parse_bbox(value)
    except ValueError as exc:
        return zones, None, Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    within_ids = set(zones.filter(geometry__within=box).values_list('id', flat=True))   # ST_Within
    if (request.query_params.get('within') or '').lower() in ('1', 'true', 'yes'):
        return zones.filter(id__in=within_ids), within_ids, None
    return zones.filter(geometry__intersects=box), within_ids, None                     # ST_Intersects


class HazardZoneListView(APIView):
    """
    GET /api/hazards/
    Returns all active hazard zones as GeoJSON FeatureCollection.
    Supports optional bbox filter: ?bbox=xmin,ymin,xmax,ymax, and
    &within=true for only zones entirely inside it. See filter_by_bbox.
    Public access — no login required.
    """
    permission_classes = [AllowAny]

    def get(self, request):
        # The public map is the busiest caller, so it is one of the places
        # an unanswered Extreme alert gets sent once its window is up.
        release_overdue_quietly()

        # Nothing changed since this browser last asked: no queries at all
        etag = map_version.etag_for(request)
        if map_version.is_fresh(request, etag):
            return map_version.tag(Response(status=status.HTTP_304_NOT_MODIFIED), etag)

        zones = (
            HazardZone.objects
            .filter(status='Active')
            .select_related('hazard_type', 'barangay', 'verified_by', 'approved_by', 'reviewed_by')
            .prefetch_related('verifications__barangay', 'verifications__answered_by',
                              'incidentreport_set__puroks')  # a report-made fire's pins
        )

        barangay = request.query_params.get('barangay')
        if barangay:
            zones = zones.filter(barangay_id=barangay)

        # Viewport bounding box filter for map pan/zoom
        zones, within_ids, error = filter_by_bbox(zones, request)
        if error:
            return error

        # The first map to refresh after a change builds this; the rest share it
        def build():
            return dict(HazardZoneGeoSerializer(zones, many=True, context={'within_ids': within_ids}).data)

        return map_version.tag(Response(map_version.cached_body(etag, build)), etag)


class HazardZoneCreateView(APIView):
    """
    POST /api/hazards/create/
    Publish a new hazard zone. DRRMO Officer only.
    """
    permission_classes = [IsAuthenticated, IsDRRMOOfficer]

    def post(self, request):
        serializer = HazardZoneCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                serializer.errors,
                status=status.HTTP_400_BAD_REQUEST
            )

        # Optional override for when the GIS data can't name the affected
        # barangays and the officer picks them by hand.
        manual_ids = request.data.get('affected_barangays') or None
        severity = serializer.validated_data['severity']

        # Most of this area already has a live zone for the same hazard:
        # likely a second alert for one event. The officer saw this in the
        # preview and must confirm it is a separate event.
        major = [
            d for d in find_duplicates(serializer.validated_data['geometry'],
                                       serializer.validated_data.get('hazard_type'))
            if d['major']
        ]
        confirmed_duplicate = str(request.data.get('confirm_duplicate', '')).lower() in ('1', 'true', 'yes')
        if major and not confirmed_duplicate:
            top = major[0]
            return Response(
                {
                    'error': f'An active {top["type"]} zone already covers {round(top["overlap"] * 100)}% '
                             f'of this area. Update that zone instead, or confirm this is a separate event.',
                    'code': 'duplicate_zone',
                    'duplicates': major,
                },
                status=status.HTTP_409_CONFLICT,
            )
        duplicate_note = (
            ' Published despite overlapping active zone(s): '
            + ', '.join(f'{d["id"]} ({round(d["overlap"] * 100)}%)' for d in major) + '.'
        ) if major else ''

        # Extreme alerts wait for a second officer. If there is nobody else
        # who could approve, waiting would only delay the warning, so it
        # goes straight out.
        hold = needs_second_approval(severity) and approvers_for(request.user).exists()

        if hold:
            with transaction.atomic():
                zone = serializer.save(published_by=request.user, status='Awaiting_Approval')
                link_report(request, zone)
                barangays = affected_barangays(zone, manual_ids)
                where = where_text(barangays)
                due = approval_due_at(zone)
                notify(
                    approvers_for(request.user),
                    f'Approval needed: Extreme {type_name(zone)} alert for {where}, '
                    f'published by {request.user.full_name}. It goes out automatically at '
                    f'{timezone.localtime(due):%I:%M %p} if no officer answers.',
                    zone,
                )
            log_event(
                request, 'HOLD_HAZARD_ALERT', 'hazard_zone', zone.id,
                f'{type_name(zone)} / Red for {where} held for a second approval.{duplicate_note}',
            )
            payload = HazardZoneSerializer(zone).data
            payload['approval'] = {
                'required': True,
                'due_at': due,
                'affected_barangays': [b.name for b in barangays],
            }
            return Response(payload, status=status.HTTP_201_CREATED)

        # One transaction: a hazard that is half-published - saved but with
        # nobody notified - is worse than one that failed outright.
        with transaction.atomic():
            zone = serializer.save(published_by=request.user)
            link_report(request, zone)
            if needs_second_approval(severity):
                # Extreme, but no second officer exists to approve it
                zone.auto_released = True
                zone.save(update_fields=['auto_released'])
            alert, barangays, recipients = issue_alert(zone, request.user, manual_ids)
            names = [b.name for b in barangays] or ['Talisay City']
            where = ', '.join(names)

        log_event(
            request,
            action='PUBLISH_HAZARD_ALERT',
            table='hazard_alert',
            target_id=alert.id,
            details=(
                f'{type_name(zone)} / {zone.severity} published for {where}. '
                f'{len(recipients)} recipient(s) notified. '
                f'Zone {zone.id}. '
                f'Barangays identified {"manually" if manual_ids else "from zone geometry"}.'
                f'{duplicate_note}'
            ),
        )

        payload = HazardZoneSerializer(zone).data
        # Feedback for the officer, and what F8's alert monitoring reads back
        payload['alert'] = {
            'id': str(alert.id),
            'affected_barangays': names,
            'recipients_notified': len(recipients),
            # True when no mapped boundary matched, so the UI can offer manual selection
            'barangays_uncertain': not barangays,
        }

        return Response(payload, status=status.HTTP_201_CREATED)


class HazardZoneDetailView(APIView):
    """
    GET   /api/hazards/<id>/  → Get single hazard zone
    PATCH /api/hazards/<id>/  → Update severity, description, or resolve the hazard

    Resolving (status='Resolved') also writes a HistoricalRecord so the
    event shows up in History and in the hazard summary report. Optional
    body fields used only when resolving:
        total_casualties  int or ''   → '' means "not recorded"
        total_displaced   int or ''
        summary           text        → stored as the record's description,
                                        leaving the live zone's own
                                        description untouched
    """
    permission_classes = [IsAuthenticated, IsDRRMOOfficer]

    def get(self, request, pk):
        try:
            zone = HazardZone.objects.get(pk=pk)
        except HazardZone.DoesNotExist:
            return Response(
                {'error': 'Hazard zone not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        return Response(HazardZoneGeoSerializer(zone).data)

    def patch(self, request, pk):
        try:
            zone = (
                HazardZone.objects
                .select_related('hazard_type', 'barangay')
                .get(pk=pk)
            )
        except HazardZone.DoesNotExist:
            return Response(
                {'error': 'Hazard zone not found'},
                status=status.HTTP_404_NOT_FOUND
            )

        # A withdrawn alert is final. Re-opening or resolving one would turn
        # a mistake that was publicly corrected back into a live hazard, or
        # file it as an incident that never happened.
        if zone.status == 'Retracted':
            return Response(
                {'error': 'This hazard was withdrawn and can no longer be changed. '
                          'Publish a new zone if the hazard is real.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if zone.status == 'Awaiting_Approval':
            return Response(
                {'error': 'This Extreme alert is still waiting for a second approval. '
                          'Approve it or withdraw it first.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Remember where the zone stood BEFORE this request touched it, so a
        # repeated PATCH on an already-resolved zone can't archive it twice.
        was_already_resolved = zone.status in ('Resolved', 'Archived')
        old_severity = zone.severity

        new_severity = request.data.get('severity', zone.severity)
        new_status   = request.data.get('status',   zone.status)

        valid_severities = [c[0] for c in HazardZone.SEVERITY_CHOICES]
        if new_severity not in valid_severities:
            return Response(
                {'error': f'severity must be one of {valid_severities}.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Retracting is not a status edit: it needs a written reason and it
        # notifies everyone who got the original alert. Sending it through
        # here would skip both, so it has an endpoint of its own.
        if new_status == 'Retracted':
            return Response(
                {'error': 'Use POST /api/hazards/<id>/retract/ to withdraw a hazard '
                          'published in error. A reason is required.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # A fire is closed with its BFP figures (POST /api/hazards/<id>/close/),
        # which fill the fire log's columns G onward. Resolving it here would
        # file a history record without them.
        is_fire = (zone.hazard_type.name if zone.hazard_type else '').lower() == 'fire'
        if is_fire and new_status in ('Resolved', 'Archived') and not was_already_resolved:
            return Response(
                {'error': 'Fire zones are closed with their BFP figures.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        valid_statuses = [
            c[0] for c in HazardZone.STATUS_CHOICES if c[0] != 'Retracted'
        ]
        if new_status not in valid_statuses:
            return Response(
                {'error': f'status must be one of {valid_statuses}.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Reshaping: the officer redrew the outline of a live zone. Same
        # cleanup as publishing (repair, cut at the city boundary).
        reshaped = 'geometry' in request.data
        if reshaped:
            if zone.status != 'Active':
                return Response(
                    {'error': 'Only an active hazard zone can be reshaped.'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            try:
                drawn = GeometryField().to_internal_value(request.data['geometry'])
                clipped, outline = clean_zone_geometry(drawn)
            except DRFValidationError as exc:
                detail = exc.detail[0] if isinstance(exc.detail, list) else exc.detail
                return Response({'error': str(detail)}, status=status.HTTP_400_BAD_REQUEST)
            before = {b.id for b in affected_barangays(zone)}
            zone.geometry = clipped
            zone.outline = outline
            home = main_barangay(clipped, Barangay.objects.filter(boundary__intersects=clipped))
            if home is not None:
                zone.barangay = home

        # Raising a live zone to Extreme needs a second officer, the same as
        # publishing an Extreme one; otherwise Edit was a way around the
        # approval. The zone stays live at its current severity meanwhile.
        raising = (
            zone.status == 'Active' and new_status == 'Active'
            and new_severity == 'Red' and old_severity != 'Red'
        )
        hold_raise = raising and approvers_for(request.user).exists()
        if hold_raise:
            new_severity = old_severity
        if new_status != 'Active' or (new_severity != 'Red' and 'severity' in request.data):
            # Resolved, or an officer chose a lower severity: any held raise is moot
            zone.pending_severity = ''
            zone.pending_by = None
            zone.pending_at = None

        zone.severity    = new_severity
        zone.status      = new_status
        zone.description = request.data.get('description', zone.description)
        touch(zone)  # an officer looked at it: no "still active?" reminder for 24 h

        # A severity or shape change makes every earlier ground answer stale:
        # the barangays confirmed a different hazard.
        if zone.severity != old_severity or reshaped:
            zone.reset_verification()

        is_resolving = (
            zone.status in ('Resolved', 'Archived')
            and not was_already_resolved
        )

        if is_resolving and not zone.resolved_at:
            zone.resolved_at = timezone.now()

        zone.save()

        if hold_raise:
            request_raise(zone, request.user)
            zone.save(update_fields=['pending_severity', 'pending_by', 'pending_at'])
            log_event(
                request, 'HOLD_HAZARD_RAISE', 'hazard_zone', zone.id,
                f'{type_name(zone)} raise from {old_severity} to Red held for a second approval.',
            )
        elif raising:
            # No other officer exists to approve: raise it now, and send the
            # Extreme alert, which a severity change never used to do.
            zone.auto_released = True
            zone.save(update_fields=['auto_released'])
            with transaction.atomic():
                alert, barangays, recipients = issue_alert(zone, request.user, suffix=' Raised to Extreme.')
            log_event(
                request, 'RAISE_HAZARD_ALERT', 'hazard_alert', alert.id,
                f'{type_name(zone)} raised to Red with no second officer available. '
                f'{len(recipients)} recipient(s) notified. Zone {zone.id}.',
            )

        if reshaped:
            after = affected_barangays(zone)
            added = [b for b in after if b.id not in before]
            # Barangays the zone now reaches never got the original alert
            if added:
                notify(
                    User.objects
                    .filter(is_active=True, assigned_barangay__in=added)
                    .exclude(id=request.user.id),
                    f'{type_name(zone)} alert ({zone.severity}) now covers {where_text(added)}: '
                    f'DRRMO enlarged the hazard zone. Tap to see it and what to do.',
                    zone,
                )
            log_event(
                request, 'RESHAPE_HAZARD', 'hazard_zone', zone.id,
                f'{type_name(zone)} / {zone.severity} reshaped. Now covers {where_text(after)}'
                + (f'; newly added and notified: {where_text(added)}.' if added else '.')
                + ' Barangay answers reset.',
            )

        # Archive to historical records on the transition into Resolved,
        # not on every PATCH that happens to carry status='Resolved'.
        if is_resolving and not HistoricalRecord.objects.filter(hazard_zone=zone).exists():
            record = HistoricalRecord.objects.create(
                barangay         = zone.barangay,
                hazard_type      = zone.hazard_type,
                hazard_zone      = zone,
                severity_level   = zone.severity,
                description      = request.data.get('summary') or zone.description or '',
                occurred_at      = zone.activated_at or zone.resolved_at or timezone.now(),
                total_casualties = _as_count(request.data.get('total_casualties')),
                total_displaced  = _as_count(request.data.get('total_displaced')),
                is_sample        = zone.is_sample,
            )
            # It counts once in every purok its reports named, or for a zone
            # drawn on the map every purok its area overlaps, which is what
            # colours those puroks on the map (fires are closed elsewhere).
            # A shape PostGIS can't compare costs the links, never the
            # all-clear below: a retry couldn't send it, the zone is resolved.
            if zone.geometry:
                try:
                    with transaction.atomic():
                        record.puroks.set(zone_puroks(zone) or overlapping_puroks(zone.geometry))
                except DatabaseError:
                    logger.warning('Resolved zone %s: its puroks could not be worked out', zone.id, exc_info=True)

        if is_resolving:
            told, where = all_clear(zone, request.user, request.data.get('summary') or '')
            log_event(
                request, 'RESOLVE_HAZARD', 'hazard_zone', zone.id,
                f'{type_name(zone)} / {zone.severity} for {where} resolved. '
                f'All-clear sent to {len(told)} account(s).',
            )

        payload = HazardZoneSerializer(zone).data
        if hold_raise:
            payload['approval'] = {'required': True, 'due_at': approval_due_at(zone)}
        return Response(payload)


class HazardZoneRetractView(APIView):
    """
    POST /api/hazards/<id>/retract/

        {"reason": "why it was withdrawn"}

    Withdraws a hazard zone that was published in error. DRRMO Officer only,
    and only while the zone is still Active.

    Three things a mis-publish is NOT:

      * It is not a resolution. Resolving writes a HistoricalRecord, which
        then counts in the hazard summary report and the trend analysis.
        Filing a zone nobody meant to publish would invent an incident that
        never happened in Talisay City.

      * It is not a delete. HazardAlert cascades from the zone and
        Notification cascades from the alert, so deleting the row would wipe
        out the record that an alert went to residents' accounts. The alert
        happened; that cannot be unsaid, only corrected.

      * It is not silent. Residents and barangay personnel acted on the
        alert. Everyone the original alert reached is told it was withdrawn,
        so nobody keeps responding to a hazard the map no longer shows.

    What it does: takes the zone off the public map (every map endpoint
    filters to status='Active'), records who withdrew it, when and why,
    notifies the original recipients, and writes an audit entry. There is no
    time limit — a wrong alert should be withdrawable the moment it is
    noticed — but every withdrawal is permanent and on the record.
    """
    permission_classes = [IsAuthenticated, IsDRRMOOfficer]

    # Enough to rule out "." or "x" without pretending a longer string is a
    # better reason. The audit entry is the real control.
    MIN_REASON = 5

    def post(self, request, pk):
        try:
            zone = (
                HazardZone.objects
                .select_related('hazard_type', 'barangay')
                .get(pk=pk)
            )
        except HazardZone.DoesNotExist:
            return Response(
                {'error': 'Hazard zone not found'},
                status=status.HTTP_404_NOT_FOUND
            )

        if zone.status == 'Retracted':
            return Response(
                {'error': 'This hazard has already been withdrawn.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        if zone.status not in ('Active', 'Awaiting_Approval'):
            return Response(
                {'error': 'This hazard has already been resolved and archived as a '
                          'historical record, so it can no longer be withdrawn.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        was_awaiting = zone.status == 'Awaiting_Approval'

        reason = (request.data.get('reason') or '').strip()
        if len(reason) < self.MIN_REASON:
            return Response(
                {'error': 'Please say why this hazard is being withdrawn. '
                          'The reason is kept on the record and sent to everyone '
                          'who received the original alert.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        type_name = zone.hazard_type.name if zone.hazard_type else 'Hazard'
        where = ', '.join(b.name for b in affected_barangays(zone)) or 'Talisay City'

        # Exactly the accounts the original alert reached — not everyone who
        # could be notified today, which may be a different set by now.
        recipients = list(
            User.objects
            .filter(notifications__hazard_alert__hazard_zone=zone)
            .distinct()
        )

        with transaction.atomic():
            zone.status            = 'Retracted'
            zone.retracted_by      = request.user
            zone.retracted_at      = timezone.now()
            zone.retraction_reason = reason
            zone.save(update_fields=[
                'status', 'retracted_by', 'retracted_at', 'retraction_reason',
            ])

            # hazard_alert is left null on purpose. These rows belong to the
            # withdrawal, not to the alert, and attaching them to the alert
            # would inflate its "sent to N accounts" figure in F8's alert
            # monitoring — making a corrected mistake look like wider reach.
            Notification.objects.bulk_create([
                Notification(
                    hazard_alert=None,
                    hazard_zone=zone,
                    recipient=u,
                    content=f'WITHDRAWN: the {type_name} alert for {where} was '
                            f'published in error and has been withdrawn by DRRMO. '
                            f'Reason: {reason}',
                )
                for u in recipients
            ])

            # An Extreme alert stopped before it went out: nobody else was
            # told about it, but the officer who published it should know.
            if was_awaiting and zone.published_by and zone.published_by != request.user:
                notify(
                    [zone.published_by],
                    f'{request.user.full_name} did not approve your Extreme {type_name} alert '
                    f'for {where}, so it was not sent. Reason: {reason}',
                    zone,
                )

        log_event(
            request, 'RETRACT_HAZARD', 'hazard_zone', zone.id,
            f'{type_name} / {zone.severity} for {where} withdrawn as published in error. '
            f'{len(recipients)} recipient(s) told. Reason: {reason}',
        )

        payload = HazardZoneSerializer(zone).data
        payload['retraction'] = {
            'reason': reason,
            'recipients_notified': len(recipients),
            'affected_barangays': where,
        }
        return Response(payload)


class HazardZoneRetractedListView(APIView):
    """
    GET /api/hazards/retracted/
    Hazard zones withdrawn as published in error, newest first.
    DRRMO Officer / System Admin only.

    Withdrawn zones are gone from the public map and out of the reports, so
    without this list they would be invisible — and a system where any
    inconvenient hazard can be made to have never existed is not auditable.
    Supports ?limit=<n> (default 20, max 100).
    """
    permission_classes = [IsAuthenticated, IsDRRMOOfficer]

    def get(self, request):
        zones = (
            HazardZone.objects
            .filter(status='Retracted')
            .select_related('hazard_type', 'barangay', 'retracted_by')
            .order_by('-retracted_at')
        )
        total = zones.count()

        try:
            limit = min(max(int(request.query_params.get('limit', 20)), 1), 100)
        except (TypeError, ValueError):
            limit = 20

        return Response({
            'count':   total,
            'results': HazardZoneSerializer(zones[:limit], many=True).data,
        })


class HazardZoneVerifyView(APIView):
    """
    POST /api/hazards/<id>/verify/
    Ground confirmation.

        {"status": "Confirmed" | "Disputed", "note": "optional, what they saw"}

    A hazard zone is published from the DRRMO office, often off a forecast or
    a phoned-in report. This is the people standing in it saying whether it
    matches what they can see — which is why only Barangay Personnel may
    answer, and only for a zone that touches their own barangay. An officer
    confirming the zone they published themselves would mean nothing, so
    DRRMO and admins can read the answer but not give one.

    A zone that is no longer Active cannot be confirmed: there is nothing
    left on the ground to look at.
    """
    permission_classes = [IsAuthenticated, IsBarangayPersonnel]

    ALLOWED = ('Confirmed', 'Disputed')

    def post(self, request, pk):
        try:
            zone = (
                HazardZone.objects
                .select_related('hazard_type', 'barangay', 'verified_by')
                .get(pk=pk)
            )
        except HazardZone.DoesNotExist:
            return Response(
                {'error': 'Hazard zone not found'},
                status=status.HTTP_404_NOT_FOUND
            )

        new_status = request.data.get('status')
        if new_status not in self.ALLOWED:
            return Response(
                {'error': f'status must be one of {list(self.ALLOWED)}.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if zone.status != 'Active':
            return Response(
                {'error': 'This hazard is already closed, so it can no longer be confirmed.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        role = getattr(getattr(request.user, 'role', None), 'name', '')
        if role != 'Barangay_Personnel':
            return Response(
                {'error': 'Only barangay personnel can confirm a hazard on the ground.'},
                status=status.HTTP_403_FORBIDDEN
            )

        assigned = getattr(request.user, 'assigned_barangay_id', None)
        if assigned is None:
            return Response(
                {'error': 'Your account has no barangay assigned, so there is nothing for you to confirm.'},
                status=status.HTTP_403_FORBIDDEN
            )
        if assigned not in {b.id for b in affected_barangays(zone)}:
            return Response(
                {'error': 'You can only confirm hazards in your own barangay.'},
                status=status.HTTP_403_FORBIDDEN
            )

        note = (request.data.get('note') or '').strip()
        with transaction.atomic():
            previous = (
                HazardVerification.objects
                .filter(hazard_zone=zone, barangay_id=assigned)
                .values_list('status', flat=True)
                .first()
            )
            answer, _ = HazardVerification.objects.update_or_create(
                hazard_zone=zone,
                barangay_id=assigned,
                defaults={
                    'status': new_status,
                    'note': note,
                    'answered_by': request.user,
                    'answered_at': timezone.now(),
                },
            )
            newly_disputed = new_status == 'Disputed' and previous != 'Disputed'
            if newly_disputed:
                # A review answered the earlier disputes, not this one
                zone.clear_review()
            zone.refresh_verification_summary()
            zone.save(update_fields=[
                'verification_status', 'verified_by', 'verified_at', 'verification_note',
                'review_note', 'reviewed_by', 'reviewed_at',
            ])

            if newly_disputed:
                # Tell the officer who published it, or every officer when
                # that account is gone, so a wrong alert is looked at now
                # rather than whenever someone happens to open it.
                publisher = zone.published_by if zone.published_by and zone.published_by.is_active else None
                officers = (
                    [publisher] if publisher
                    else User.objects.filter(is_active=True, role__name__in=['DRRMO_Officer', 'System_Admin'])
                )
                notify(
                    officers,
                    f'Disputed: {answer.barangay.name} personnel say the {type_name(zone)} alert '
                    f'is not there as published'
                    + (f': "{note}".' if note else '.')
                    + ' Review it, withdraw it, or reshape it.',
                    zone,
                )

        log_event(
            request, 'VERIFY_HAZARD', 'hazard_zone', zone.id,
            f'{new_status} for {answer.barangay.name} by {request.user.email}',
        )

        return Response(HazardZoneSerializer(zone).data)


class HazardZoneForBarangayView(APIView):
    """
    GET /api/hazards/for-barangay/
    Active hazard zones touching the signed-in user's barangay, newest first,
    so the barangay dashboard can push what needs an answer rather than
    making personnel hunt for it on the map.

    ?pending=true returns only the ones nobody has answered yet.

    Barangay Personnel see their own barangay. DRRMO and admins have no
    single barangay of their own, so they get an empty list here and use the
    map instead.
    """
    permission_classes = [IsAuthenticated, IsBarangayPersonnel]

    def get(self, request):
        assigned = getattr(request.user, 'assigned_barangay_id', None)
        if assigned is None:
            return Response({'barangay': None, 'count': 0, 'results': []})

        zones = (
            HazardZone.objects
            .filter(status='Active')
            .select_related('hazard_type', 'barangay', 'verified_by')
            .order_by('-activated_at')
        )

        # The barangay recorded on a zone is only where the officer tapped;
        # a 1 km zone can cross three of them. Match on the geometry, the same
        # way the alert decides who to notify, so what the dashboard shows and
        # what the alert went out to agree.
        boundary = (
            Barangay.objects
            .filter(id=assigned)
            .values_list('boundary', flat=True)
            .first()
        )
        if boundary is None:
            zones = zones.filter(barangay_id=assigned)
        else:
            try:
                zones = zones.filter(Q(geometry__intersects=boundary) | Q(barangay_id=assigned))
                zones.exists()  # force the query now, so a bad boundary is caught here
            except Exception:
                # Malformed boundary: fall back to the barangay recorded on the
                # zone rather than showing nothing at all.
                zones = (
                    HazardZone.objects
                    .filter(status='Active', barangay_id=assigned)
                    .select_related('hazard_type', 'barangay', 'verified_by')
                    .order_by('-activated_at')
                )

        if (request.query_params.get('pending') or '').strip().lower() in ('1', 'true', 'yes'):
            zones = zones.exclude(verifications__barangay_id=assigned)

        return Response({
            'barangay': assigned,
            'count': zones.count(),
            'results': HazardZoneSerializer(zones, many=True).data,
        })


class HazardZoneResolvedListView(APIView):
    """
    GET /api/hazards/resolved/
    Hazard zones that have been resolved, newest first — the live map only
    ever returns Active ones, so the dashboard needs its own endpoint to
    count and list these. DRRMO Officer / System Admin only.
    Supports ?limit=<n> (default 20, max 100).
    """
    permission_classes = [IsAuthenticated, IsDRRMOOfficer]

    def get(self, request):
        zones = (
            HazardZone.objects
            .filter(status__in=['Resolved', 'Archived'])
            .select_related('hazard_type', 'barangay')
            .order_by('-resolved_at')
        )
        total = zones.count()

        try:
            limit = min(max(int(request.query_params.get('limit', 20)), 1), 100)
        except (TypeError, ValueError):
            limit = 20

        return Response({
            'count':   total,
            'results': HazardZoneSerializer(zones[:limit], many=True).data,
        })


class HazardTypeListView(APIView):
    """
    GET /api/hazards/types/
    Returns all active hazard types. Public access.
    """
    permission_classes = [AllowAny]

    def get(self, request):
        types = HazardType.objects.filter(is_active=True)
        return Response(HazardTypeSerializer(types, many=True).data)


class HazardUnifiedView(APIView):
    """
    GET /api/hazards/unified/
    Returns all active hazard zones grouped by hazard type.
    Supports layer toggle: ?types=Flood,Fire
    Public access — no login required.
    Used by Leaflet.js unified display with layer control.
    """
    permission_classes = [AllowAny]

    def get(self, request):
        etag = map_version.etag_for(request)
        if map_version.is_fresh(request, etag):
            return map_version.tag(Response(status=status.HTTP_304_NOT_MODIFIED), etag)

        zones = HazardZone.objects.filter(
            status='Active'
        ).select_related('hazard_type', 'barangay')

        # Filter by hazard types if specified
        # Example: ?types=Flood,Fire
        types_param = request.query_params.get('types')
        if types_param:
            type_names = [t.strip() for t in types_param.split(',')]
            zones = zones.filter(hazard_type__name__in=type_names)

        # Filter by severity if specified
        # Example: ?severity=Red
        severity = request.query_params.get('severity')
        if severity:
            zones = zones.filter(severity=severity)

        # Filter by bbox if specified (same rules as /api/hazards/)
        zones, within_ids, error = filter_by_bbox(zones, request)
        if error:
            return error

        def build():
            serializer = HazardZoneGeoSerializer(zones, many=True, context={'within_ids': within_ids})
            return {
                'type': 'FeatureCollection',
                'count': zones.count(),
                'features': serializer.data['features'],
            }

        return map_version.tag(Response(map_version.cached_body(etag, build)), etag)


class HazardLayerListView(APIView):
    """
    GET /api/hazards/layers/
    Returns available hazard layers with counts.
    Used by Leaflet.js layer control panel.
    Public access.
    """
    permission_classes = [AllowAny]

    def get(self, request):
        layers = []
        hazard_types = HazardType.objects.filter(is_active=True)

        for ht in hazard_types:
            # One grouped query per type instead of four separate counts
            by_severity = dict(
                HazardZone.objects
                .filter(hazard_type=ht, status='Active')
                .values_list('severity')
                .annotate(total=Count('id'))
            )

            severity_counts = {
                'Red':    by_severity.get('Red', 0),
                'Orange': by_severity.get('Orange', 0),
                'Green':  by_severity.get('Green', 0),
            }

            layers.append({
                'id': ht.id,
                'name': ht.name,
                'logo_class': ht.logo_class,
                'active_count': sum(severity_counts.values()),
                'severity_counts': severity_counts,
                'color_legend': {
                    'Red': 'Extreme Risk',
                    'Orange': 'Moderate Risk',
                    'Green': 'Low Risk'
                }
            })

        return Response({
            'Layers': layers,
            'Total_active_hazards': HazardZone.objects.filter(status='Active').count(),
        })

class HazardZonePreviewView(APIView):
    """
    POST /api/hazards/preview/
    Same body as /api/hazards/create/. Saves nothing and notifies nobody.

    What the officer sees before an alert goes out: the shape as it will be
    saved (clipped to the city), the barangays it reaches, how many accounts
    will be notified, whether it needs a second approval, and any active zone
    of the same hazard type it overlaps, which is usually a double publish.
    """
    permission_classes = [IsAuthenticated, IsDRRMOOfficer]

    def post(self, request):
        serializer = HazardZoneCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        geometry = data['geometry']
        manual_ids = request.data.get('affected_barangays') or None
        barangays = affected_barangays(geometry, manual_ids)
        recipients = alert_recipients(request.user, barangays).count()

        duplicates = find_duplicates(geometry, data.get('hazard_type'))

        # Measured by PostGIS on the spheroid rather than by reprojecting
        # here: GDAL needs PROJ's data files, which aren't set up on every
        # developer machine, and the database already has them.
        def measure(shape):
            try:
                with connection.cursor() as cursor:
                    cursor.execute('SELECT ST_Area(ST_GeomFromEWKB(%s)::geography)', [bytes(shape.ewkb)])
                    return cursor.fetchone()[0]
            except Exception:
                return None

        area = measure(geometry)

        needs_approval = (
            needs_second_approval(data['severity'])
            and approvers_for(request.user).exists()
        )
        home = data.get('barangay')

        return Response({
            'geometry': json.loads(geometry.geojson),
            'area_m2': round(area) if area is not None else None,
            'barangay': {'id': home.id, 'name': home.name} if home else None,
            'affected_barangays': [b.name for b in barangays],
            'recipients': recipients,
            'needs_approval': needs_approval,
            'approval_minutes': int(approval_window().total_seconds() // 60),
            'duplicates': duplicates,
            # True when one of them covers DUPLICATE_SHARE or more of this
            # drawing: publishing then needs confirm_duplicate.
            'major_duplicate': any(d['major'] for d in duplicates),
            'duplicate_share': DUPLICATE_SHARE,
        })


class HazardZoneReceiptsView(APIView):
    """
    GET /api/hazards/<id>/receipts/

    Who received this zone's latest alert and who has opened it, by
    barangay. The admin alert monitor already counts this for every alert;
    this puts it on the zone itself, so the officer looking at a hazard can
    see that Poblacion's personnel have read it and Cansojong's haven't,
    and phone them.
    """
    permission_classes = [IsAuthenticated, IsDRRMOOfficer]

    def get(self, request, pk):
        alert = (
            HazardAlert.objects.filter(hazard_zone_id=pk)
            .order_by('-created_at').first()
        )
        if alert is None:
            if not HazardZone.objects.filter(pk=pk).exists():
                return Response({'error': 'Hazard zone not found'}, status=status.HTTP_404_NOT_FOUND)
            return Response({'alert': None, 'sent': 0, 'opened': 0, 'groups': []})

        rows = (
            Notification.objects.filter(hazard_alert=alert)
            .select_related('recipient__assigned_barangay', 'recipient__role')
            .order_by('recipient__full_name')
        )
        groups = {}
        for n in rows:
            u = n.recipient
            role = u.role.name if u.role else ''
            if role == 'Barangay_Personnel':
                name = u.assigned_barangay.name if u.assigned_barangay else 'No barangay set'
            else:
                name = 'DRRMO and administrators'
            g = groups.setdefault(name, {'name': name, 'sent': 0, 'opened': 0, 'unread': []})
            g['sent'] += 1
            if n.is_read:
                g['opened'] += 1
            else:
                g['unread'].append(u.full_name)

        ordered = sorted(groups.values(), key=lambda g: (g['name'] == 'DRRMO and administrators', g['name']))
        return Response({
            'alert': {'id': str(alert.id), 'severity': alert.severity, 'created_at': alert.created_at},
            'sent': sum(g['sent'] for g in ordered),
            'opened': sum(g['opened'] for g in ordered),
            'groups': ordered,
        })


class HazardZoneAwaitingListView(APIView):
    """
    GET /api/hazards/awaiting/
    Extreme alerts waiting for a second officer, oldest first, with when each
    goes out on its own. DRRMO Officer / System Admin only.
    """
    permission_classes = [IsAuthenticated, IsDRRMOOfficer]

    def get(self, request):
        release_overdue_quietly()
        zones = (
            HazardZone.objects
            .filter(Q(status='Awaiting_Approval') | Q(status='Active', pending_severity='Red'))
            .select_related('hazard_type', 'barangay', 'published_by', 'pending_by')
            .order_by('activated_at')
        )
        results = []
        for zone in zones:
            raise_ = zone.status == 'Active'
            asked_by = zone.pending_by if raise_ else zone.published_by
            row = HazardZoneSerializer(zone).data
            # 'new': an Extreme alert not sent yet. 'raise': a live zone an
            # officer asked to raise to Extreme.
            row['kind'] = 'raise' if raise_ else 'new'
            row['requested_by_name'] = asked_by.full_name if asked_by else None
            row['requested_at'] = zone.pending_at if raise_ else zone.activated_at
            row['approval_due_at'] = approval_due_at(zone)
            row['affected_barangays'] = [b.name for b in affected_barangays(zone)]
            row['can_approve'] = (asked_by.id if asked_by else None) != request.user.id
            results.append(row)
        return Response({'count': len(results), 'results': results})


class HazardZoneApproveView(APIView):
    """
    POST /api/hazards/<id>/approve/
    The second officer's approval for an Extreme alert. Sends it.

    Not the officer who published it: approving your own alert is the check
    this exists to add. To stop an alert instead, withdraw it with a reason
    through /retract/, which tells the publisher why.
    """
    permission_classes = [IsAuthenticated, IsDRRMOOfficer]

    def post(self, request, pk):
        with transaction.atomic():
            zone = (
                HazardZone.objects
                .select_for_update(of=('self',))
                .select_related('hazard_type', 'barangay', 'published_by', 'pending_by')
                .filter(pk=pk)
                .first()
            )
            if zone is None:
                return Response({'error': 'Hazard zone not found'}, status=status.HTTP_404_NOT_FOUND)

            # A live zone waiting to be raised to Extreme
            if zone.status == 'Active' and zone.pending_severity == 'Red':
                if zone.pending_by_id == request.user.id:
                    return Response(
                        {'error': 'You asked for this raise, so another officer has to approve it.'},
                        status=status.HTTP_403_FORBIDDEN,
                    )
                alert, barangays, recipients = apply_raise(zone, approver=request.user)
                log_event(
                    request, 'APPROVE_HAZARD_RAISE', 'hazard_alert', alert.id,
                    f'{type_name(zone)} raised to Red for {where_text(barangays)} and sent. '
                    f'{len(recipients)} recipient(s) notified. Zone {zone.id}.',
                )
                payload = HazardZoneSerializer(zone).data
                payload['alert'] = {
                    'id': str(alert.id),
                    'affected_barangays': [b.name for b in barangays],
                    'recipients_notified': len(recipients),
                }
                return Response(payload)

            if zone.status != 'Awaiting_Approval':
                message = {
                    'Active': 'This alert has already gone out'
                              + (' on its own after the approval window.' if zone.auto_released else '.'),
                    'Retracted': 'This alert was withdrawn, so it can no longer be approved.',
                }.get(zone.status, 'This alert is not waiting for approval.')
                return Response({'error': message}, status=status.HTTP_400_BAD_REQUEST)

            if zone.published_by_id == request.user.id:
                return Response(
                    {'error': 'You published this alert, so another officer has to approve it.'},
                    status=status.HTTP_403_FORBIDDEN,
                )

            zone.status = 'Active'
            zone.approved_by = request.user
            zone.approved_at = timezone.now()
            zone.save(update_fields=['status', 'approved_by', 'approved_at'])

            alert, barangays, recipients = issue_alert(zone, issued_by=zone.published_by or request.user)
            where = where_text(barangays)
            if zone.published_by:
                notify(
                    [zone.published_by],
                    f'{request.user.full_name} approved your Extreme {type_name(zone)} alert '
                    f'for {where}. It has been sent.',
                    zone,
                )

        log_event(
            request, 'APPROVE_HAZARD_ALERT', 'hazard_alert', alert.id,
            f'{type_name(zone)} / Red for {where} approved and sent. '
            f'{len(recipients)} recipient(s) notified. Zone {zone.id}.',
        )

        payload = HazardZoneSerializer(zone).data
        payload['alert'] = {
            'id': str(alert.id),
            'affected_barangays': [b.name for b in barangays],
            'recipients_notified': len(recipients),
        }
        return Response(payload)


class HazardZoneReviewView(APIView):
    """
    POST /api/hazards/<id>/review/

        {"note": "Checked with the barangay captain; the creek is still rising upstream."}

    DRRMO's answer to a dispute: the zone was looked at and stays as it is.
    The alternatives are withdrawing it or reshaping it, which have their
    own endpoints. The note shows on the public map next to the dispute, and
    the personnel who disputed it are told. A new dispute clears the review.
    """
    permission_classes = [IsAuthenticated, IsDRRMOOfficer]
    MIN_NOTE = 5

    def post(self, request, pk):
        zone = (
            HazardZone.objects
            .select_related('hazard_type', 'barangay')
            .filter(pk=pk)
            .first()
        )
        if zone is None:
            return Response({'error': 'Hazard zone not found'}, status=status.HTTP_404_NOT_FOUND)
        if zone.status != 'Active':
            return Response({'error': 'Only an active hazard zone can be reviewed.'},
                            status=status.HTTP_400_BAD_REQUEST)
        if zone.verification_status != 'Disputed':
            return Response({'error': 'No barangay has disputed this hazard, so there is nothing to review.'},
                            status=status.HTTP_400_BAD_REQUEST)

        note = (request.data.get('note') or '').strip()
        if len(note) < self.MIN_NOTE:
            return Response({'error': 'Say what was checked and why the zone stays. '
                                      'The note is shown with the dispute on the public map.'},
                            status=status.HTTP_400_BAD_REQUEST)

        disputers = [
            v.answered_by for v in
            zone.verifications.filter(status='Disputed').select_related('answered_by')
            if v.answered_by and v.answered_by.is_active
        ]
        with transaction.atomic():
            zone.review_note = note
            zone.reviewed_by = request.user
            zone.reviewed_at = timezone.now()
            zone.save(update_fields=['review_note', 'reviewed_by', 'reviewed_at'])
            notify(
                disputers,
                f'DRRMO reviewed your dispute about the {type_name(zone)} alert and is keeping it: "{note}"',
                zone,
            )

        log_event(
            request, 'REVIEW_HAZARD_DISPUTE', 'hazard_zone', zone.id,
            f'Dispute reviewed, zone kept. {len(disputers)} disputer(s) told. Note: {note}',
        )
        return Response(HazardZoneSerializer(zone).data)


class HazardZoneRefuseRaiseView(APIView):
    """
    POST /api/hazards/<id>/raise/refuse/

        {"reason": "Water is going down; Moderate still fits."}

    Don't raise a live zone to Extreme after all. The zone stays live at its
    current severity, and the officer who asked is told why. The one who
    asked may also withdraw their own request this way.
    """
    permission_classes = [IsAuthenticated, IsDRRMOOfficer]
    MIN_REASON = 5

    def post(self, request, pk):
        with transaction.atomic():
            zone = (
                HazardZone.objects
                .select_for_update(of=('self',))
                .select_related('hazard_type', 'barangay', 'pending_by')
                .filter(pk=pk)
                .first()
            )
            if zone is None:
                return Response({'error': 'Hazard zone not found'}, status=status.HTTP_404_NOT_FOUND)
            if zone.status != 'Active' or zone.pending_severity != 'Red':
                return Response({'error': 'This hazard is not waiting to be raised to Extreme.'},
                                status=status.HTTP_400_BAD_REQUEST)
            reason = (request.data.get('reason') or '').strip()
            if len(reason) < self.MIN_REASON:
                return Response({'error': 'Say why it should not be raised. The officer who asked is told.'},
                                status=status.HTTP_400_BAD_REQUEST)

            asked_by = zone.pending_by
            zone.pending_severity = ''
            zone.pending_by = None
            zone.pending_at = None
            zone.save(update_fields=['pending_severity', 'pending_by', 'pending_at'])
            if asked_by and asked_by != request.user:
                notify(
                    [asked_by],
                    f'{request.user.full_name} did not approve raising the {type_name(zone)} alert to Extreme. '
                    f'It stays {zone.get_severity_display()}. Reason: {reason}',
                    zone,
                )

        log_event(
            request, 'REFUSE_HAZARD_RAISE', 'hazard_zone', zone.id,
            f'{type_name(zone)} raise to Red not approved; stays {zone.severity}. Reason: {reason}',
        )
        return Response(HazardZoneSerializer(zone).data)
