from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework import status
from django.contrib.gis.geos import Polygon

from apps.hazards.models import HazardType, HazardZone, HazardAlert
from apps.hazards.serializers import (
    HazardZoneGeoSerializer,
    HazardZoneSerializer,
    HazardZoneCreateSerializer,
    HazardTypeSerializer,
)
from utils.permissions import IsDRRMOOfficer


class HazardZoneListView(APIView):
    """
    GET /api/hazards/
    Returns all active hazard zones as GeoJSON FeatureCollection.
    Supports optional bbox filter: ?bbox=xmin,ymin,xmax,ymax
    Public access — no login required.
    """
    permission_classes = [AllowAny]

    def get(self, request):
        zones = HazardZone.objects.filter(status='Active')

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
        HazardAlert.objects.create(
            hazard_zone = zone,
            issued_by   = request.user,
            hazard_type = zone.hazard_type,
            severity    = zone.severity,
            notes       = zone.description,
        )

        return Response(
            HazardZoneSerializer(zone).data,
            status=status.HTTP_201_CREATED
        )


class HazardZoneDetailView(APIView):
    """
    GET  /api/hazards/<id>/  → Get single hazard zone
    PATCH /api/hazards/<id>/ → Update severity or resolve hazard
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
            zone = HazardZone.objects.get(pk=pk)
        except HazardZone.DoesNotExist:
            return Response(
                {'error': 'Hazard zone not found'},
                status=status.HTTP_404_NOT_FOUND
            )

        zone.severity    = request.data.get('severity',    zone.severity)
        zone.status      = request.data.get('status',      zone.status)
        zone.description = request.data.get('description', zone.description)
        zone.save()

        # Auto-archive to historical records when resolved
        if zone.status == 'Resolved':
            from apps.history.models import HistoricalRecord
            from django.utils import timezone
            zone.resolved_at = timezone.now()
            zone.save()

        return Response(HazardZoneSerializer(zone).data)


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
                xmin, ymin, xmax, ymax = [
                    float(x) for x in bbox.split(',')
                ]
                from django.contrib.gis.geos import Polygon
                bbox_polygon = Polygon.from_bbox(
                    (xmin, ymin, xmax, ymax)
                )
                bbox_polygon.srid = 4326
                zones = zones.filter(
                    geometry__intersects=bbox_polygon
                )
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
        from apps.hazards.models import HazardType
        from django.db.models import Count

        layers = []
        hazard_types = HazardType.objects.filter(is_active=True)

        for ht in hazard_types:
            active_count = HazardZone.objects.filter(
                hazard_type=ht,
                status='Active'
            ).count()

            severity_counts = {
                'Red':    HazardZone.objects.filter(hazard_type=ht, status='Active', severity='Red').count(),
                'Orange': HazardZone.objects.filter(hazard_type=ht, status='Active', severity='Orange').count(),
                'Green':  HazardZone.objects.filter(hazard_type=ht, status='Active', severity='Green').count(),
            }

            layers.append({
                'id': ht.id,
                'name': ht.name,
                'logo_class': ht.logo_class,
                'active_count': active_count,
                'severity_counts': severity_counts,
                'color_legend': {
                    'Red': 'Extreme Risk',
                    'Orange': 'Moderate Risk',
                    'Green': 'Low Risk'
                }
            })

        return Response({
            'Layers': layers,
            'Total_active_hazards':  HazardZone.objects.filter(status='Active').count(),
        })

