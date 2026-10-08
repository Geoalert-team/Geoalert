from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework import status
from django.contrib.gis.geos import Polygon
from django.db.models import Count
from django.utils import timezone

from apps.notifications.models import Notification
from apps.accounts.models import User
from apps.history.models import HistoricalRecord

from apps.hazards.models import HazardType, HazardZone, HazardAlert
from apps.hazards.serializers import (
    HazardZoneGeoSerializer,
    HazardZoneSerializer,
    HazardZoneCreateSerializer,
    HazardZoneVerifySerializer,
    HazardTypeSerializer,
)
from utils.permissions import IsDRRMOOfficer, IsBarangayPersonnel


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


class HazardZoneListView(APIView):
    """
    GET /api/hazards/
    Returns all active hazard zones as GeoJSON FeatureCollection.
    Supports optional bbox filter: ?bbox=xmin,ymin,xmax,ymax
    Public access — no login required.
    """
    permission_classes = [AllowAny]

    def get(self, request):
        zones = (
            HazardZone.objects
            .filter(status='Active')
            .select_related('hazard_type', 'barangay', 'verified_by')
        )

        barangay = request.query_params.get('barangay')
        if barangay:
            zones = zones.filter(barangay_id=barangay)

        # Viewport bounding box filter for map pan/zoom
        bbox = request.query_params.get('bbox')
        if bbox:
            try:
                xmin, ymin, xmax, ymax = [float(x) for x in bbox.split(',')]
                bbox_polygon = Polygon.from_bbox((xmin, ymin, xmax, ymax))
                bbox_polygon.srid = 4326
                zones = zones.filter(geometry__intersects=bbox_polygon)
            except (ValueError, Exception):
                pass  # ignore malformed bbox

        serializer = HazardZoneGeoSerializer(zones, many=True)
        return Response(serializer.data)


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

        zone = serializer.save(published_by=request.user)

        # Create alert record
        alert = HazardAlert.objects.create(
            hazard_zone = zone,
            issued_by   = request.user,
            hazard_type = zone.hazard_type,
            severity    = zone.severity,
            notes       = zone.description,
        )

        # Notify every active user except whoever just published this alert
        affected_users = User.objects.filter(is_active=True).exclude(id=request.user.id)
        Notification.objects.bulk_create([
            Notification(
                hazard_alert=alert,
                recipient=u,
                content=f'{zone.hazard_type.name} alert ({zone.severity}) published for {zone.barangay.name if zone.barangay else "Talisay City"}.'
            )
            for u in affected_users
        ])

        return Response(
            HazardZoneSerializer(zone).data,
            status=status.HTTP_201_CREATED
        )


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

        valid_statuses = [c[0] for c in HazardZone.STATUS_CHOICES]
        if new_status not in valid_statuses:
            return Response(
                {'error': f'status must be one of {valid_statuses}.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        zone.severity    = new_severity
        zone.status      = new_status
        zone.description = request.data.get('description', zone.description)

        # A severity change makes any earlier ground confirmation stale
        if zone.severity != old_severity:
            zone.reset_verification()

        is_resolving = (
            zone.status in ('Resolved', 'Archived')
            and not was_already_resolved
        )

        if is_resolving and not zone.resolved_at:
            zone.resolved_at = timezone.now()

        zone.save()

        # Archive to historical records on the transition into Resolved,
        # not on every PATCH that happens to carry status='Resolved'.
        if is_resolving and not HistoricalRecord.objects.filter(hazard_zone=zone).exists():
            HistoricalRecord.objects.create(
                barangay         = zone.barangay,
                hazard_type      = zone.hazard_type,
                hazard_zone      = zone,
                severity_level   = zone.severity,
                description      = request.data.get('summary') or zone.description or '',
                occurred_at      = zone.activated_at or zone.resolved_at or timezone.now(),
                total_casualties = _as_count(request.data.get('total_casualties')),
                total_displaced  = _as_count(request.data.get('total_displaced')),
            )

        return Response(HazardZoneSerializer(zone).data)


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

        # Filter by bbox if specified
        bbox = request.query_params.get('bbox')
        if bbox:
            try:
                xmin, ymin, xmax, ymax = [float(x) for x in bbox.split(',')]
                bbox_polygon = Polygon.from_bbox((xmin, ymin, xmax, ymax))
                bbox_polygon.srid = 4326
                zones = zones.filter(geometry__intersects=bbox_polygon)
            except (ValueError, Exception):
                pass

        serializer = HazardZoneGeoSerializer(zones, many=True)
        return Response({
            'type': 'FeatureCollection',
            'count': zones.count(),
            'features': serializer.data['features']
        })


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


class HazardZoneVerifyView(APIView):
    """
    POST /api/hazards/<id>/verify/
    Barangay personnel confirm or dispute conditions on the ground.
    Body: { "verification_status": "Confirmed" | "Disputed",
            "verification_note": "..." }   (note required when Disputed)
    """
    permission_classes = [IsAuthenticated, IsBarangayPersonnel]

    def post(self, request, pk):
        try:
            zone = (
                HazardZone.objects
                .select_related('hazard_type', 'barangay')
                .get(pk=pk, status='Active')
            )
        except HazardZone.DoesNotExist:
            return Response(
                {'error': 'This hazard zone is no longer active.'},
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = HazardZoneVerifySerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        if serializer.validated_data['verification_status'] == 'Pending':
            zone.reset_verification()
        else:
            zone.verification_status = serializer.validated_data['verification_status']
            zone.verification_note   = serializer.validated_data['verification_note']
            zone.verified_by         = request.user
            zone.verified_at         = timezone.now()
        zone.save(update_fields=[
            'verification_status', 'verification_note',
            'verified_by', 'verified_at',
        ])

        return Response(HazardZoneGeoSerializer(zone).data)