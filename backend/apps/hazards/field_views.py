"""
Endpoints that help an officer draw a zone from evidence rather than a
guess: past zones to start from, and spots checked on the ground while a
zone is live.
"""

from django.contrib.gis.geos import MultiPolygon, Point, Polygon
from django.db import connection
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.hazards.alerts import notify, type_name
from apps.hazards.models import HazardZone, ZoneFieldMark
from utils.audit import log_event
from utils.permissions import IsBarangayPersonnel, IsDRRMOOfficer

# A template should be easy to drag: past this many corners it is simplified.
MAX_TEMPLATE_CORNERS = 40

# A field mark further than this from the zone belongs to a different event
MARK_MAX_DISTANCE_M = 1000


def zone_corners(zone):
    """
    The zone's outline as [[lat, lng], ...] for the map, without the
    closing repeat. Prefers the outline as drawn; falls back to the largest
    part of the saved shape. Simplified until it is easy to drag.
    """
    shape = zone.outline
    if shape is None and zone.geometry is not None:
        parts = list(zone.geometry) if isinstance(zone.geometry, MultiPolygon) else [zone.geometry]
        shape = max(parts, key=lambda p: p.area) if parts else None
    if shape is None:
        return []
    shape = Polygon(shape.exterior_ring, srid=shape.srid or 4326)
    tolerance = 0.00003  # about 3 m
    while len(shape.exterior_ring) - 1 > MAX_TEMPLATE_CORNERS and tolerance < 0.01:
        simpler = shape.simplify(tolerance, preserve_topology=True)
        if isinstance(simpler, Polygon) and not simpler.empty:
            shape = simpler
        tolerance *= 2
    coords = list(shape.exterior_ring.coords)[:-1]
    return [[round(lat, 6), round(lng, 6)] for lng, lat in coords]


def read_point(data):
    """A WGS84 Point from latitude/longitude (or lat/lng), or None."""
    try:
        lat = float(data.get('latitude', data.get('lat')))
        lng = float(data.get('longitude', data.get('lng')))
    except (TypeError, ValueError):
        return None
    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        return None
    return Point(lng, lat, srid=4326)


class PastZonesNearView(APIView):
    """
    GET /api/hazards/past-zones/?type=Flood&lat=10.24&lng=123.84&radius=600

    Resolved or archived zones of one hazard type near a spot, nearest
    first, each with its outline ready to load as a starting shape. Floods
    come back to the same low streets, so last year's outline is often a
    better start than a blank map. DRRMO only.
    """
    permission_classes = [IsAuthenticated, IsDRRMOOfficer]
    LIMIT = 6

    def get(self, request):
        point = read_point(request.query_params)
        hazard = (request.query_params.get('type') or '').strip()
        if point is None or not hazard:
            return Response({'error': 'Give type, lat and lng.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            radius = min(max(float(request.query_params.get('radius', 600)), 50), 3000)
        except ValueError:
            radius = 600

        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT z.hzzn_id,
                       ST_Distance(z.hzzn_polygon::geography,
                                   ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography)
                FROM hazard_zone z
                JOIN hazard_type t ON t.hztp_id = z.hzzn_hztp_id
                WHERE lower(t.hztp_name) = lower(%s)
                  AND z.hzzn_status IN ('Resolved', 'Archived')
                  AND ST_DWithin(z.hzzn_polygon::geography,
                                 ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography, %s)
                ORDER BY 2
                LIMIT %s
                """,
                [point.x, point.y, hazard, point.x, point.y, radius, self.LIMIT],
            )
            found = cursor.fetchall()

        distances = {row[0]: row[1] for row in found}
        zones = HazardZone.objects.filter(id__in=distances).select_related('barangay', 'hazard_type')
        results = []
        for z in sorted(zones, key=lambda z: distances[z.id]):
            corners = zone_corners(z)
            if len(corners) < 3:
                continue
            results.append({
                'id': str(z.id),
                'type': type_name(z),
                'severity': z.severity,
                'barangay': z.barangay.name if z.barangay else None,
                'activated_at': z.activated_at,
                'resolved_at': z.resolved_at,
                'distance_m': round(distances[z.id]),
                'is_sample': z.is_sample,
                'corners': corners,
            })
        return Response({'results': results, 'radius_m': radius})


def mark_row(mark):
    return {
        'id': str(mark.id),
        'kind': mark.kind,
        'lat': round(mark.location.y, 6),
        'lng': round(mark.location.x, 6),
        'note': mark.note,
        'by': mark.created_by.full_name if mark.created_by else None,
        'created_at': mark.created_at,
        'inside_zone': mark.inside_zone,
        'disagrees': mark.disagrees,
    }


class ZoneFieldMarksView(APIView):
    """
    GET  /api/hazards/<id>/marks/   spots checked on the ground for a zone
    POST /api/hazards/<id>/marks/   {kind: Affected|Clear, latitude, longitude, note}

    Barangay staff and officers. A mark that disagrees with the outline
    ("affected" outside it, "clear" inside it) notifies the officer who
    published the zone, who can reshape it. Marks never move the zone.
    """
    permission_classes = [IsAuthenticated, IsBarangayPersonnel]

    def get(self, request, pk):
        zone = HazardZone.objects.filter(pk=pk).first()
        if zone is None:
            return Response({'error': 'Hazard zone not found.'}, status=status.HTTP_404_NOT_FOUND)
        rows = [mark_row(m) for m in zone.field_marks.select_related('created_by', 'zone')]
        return Response({
            'results': rows,
            'disagreeing': sum(1 for r in rows if r['disagrees']),
        })

    def post(self, request, pk):
        zone = HazardZone.objects.filter(pk=pk).select_related('published_by', 'hazard_type', 'barangay').first()
        if zone is None:
            return Response({'error': 'Hazard zone not found.'}, status=status.HTTP_404_NOT_FOUND)
        if zone.status != 'Active':
            return Response({'error': 'Only a live zone can be marked.'}, status=status.HTTP_400_BAD_REQUEST)

        kind = request.data.get('kind')
        if kind not in dict(ZoneFieldMark.KIND_CHOICES):
            return Response({'error': 'kind must be Affected or Clear.'}, status=status.HTTP_400_BAD_REQUEST)
        point = read_point(request.data)
        if point is None:
            return Response({'error': 'Give latitude and longitude.'}, status=status.HTTP_400_BAD_REQUEST)

        with connection.cursor() as cursor:
            cursor.execute(
                'SELECT ST_DWithin(hzzn_polygon::geography, ST_GeomFromEWKB(%s)::geography, %s) '
                'FROM hazard_zone WHERE hzzn_id = %s',
                [bytes(point.ewkb), MARK_MAX_DISTANCE_M, str(zone.pk)],
            )
            near = cursor.fetchone()[0]
        if not near:
            return Response({'error': 'That spot is more than 1 km from this zone.'},
                            status=status.HTTP_400_BAD_REQUEST)

        mark = ZoneFieldMark.objects.create(
            zone=zone, kind=kind, location=point,
            note=(request.data.get('note') or '').strip()[:300],
            created_by=request.user,
        )
        row = mark_row(mark)

        if mark.disagrees and zone.published_by and zone.published_by_id != request.user.id:
            where = 'outside' if kind == 'Affected' else 'inside'
            label = 'Affected here' if kind == 'Affected' else 'Clear here'
            place = f' in {zone.barangay.name}' if zone.barangay else ''
            notify(
                [zone.published_by],
                f'Field check on your {type_name(zone)} zone{place}: "{label}" {where} the outline, '
                f'from {request.user.full_name}. Open the zone and reshape it if the edge is wrong.',
                zone,
            )
        log_event(
            request, 'MARK_HAZARD_ZONE', 'hazard_zone', zone.id,
            f'{kind} mark at {row["lat"]}, {row["lng"]}'
            + (' (disagrees with the outline).' if row['disagrees'] else '.'),
        )
        return Response(row, status=status.HTTP_201_CREATED)
