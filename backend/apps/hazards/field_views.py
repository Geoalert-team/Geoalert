"""
Spots checked on the ground while a zone is live: barangay personnel mark
where it is affected or clear, so DRRMO can see the zone's real extent.
"""

from django.contrib.gis.geos import Point
from django.db import connection
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.hazards.alerts import notify, type_name
from apps.hazards.models import HazardZone, ZoneFieldMark
from utils.audit import log_event
from utils.permissions import IsBarangayPersonnel


# A field mark further than this from the zone belongs to a different event
MARK_MAX_DISTANCE_M = 1000


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


def can_remove(mark, viewer):
    """
    Whoever left the mark, or the officer who published the zone. Worked
    out here and sent with each row so the rule lives in one place: the
    client shows a Remove button from this, and DELETE enforces the same
    thing. A display name is not an identity, so the client could not
    decide this for itself anyway.
    """
    if viewer is None or not getattr(viewer, 'is_authenticated', False):
        return False
    if mark.zone.status != 'Active':
        return False
    return (
        (mark.created_by_id is not None and mark.created_by_id == viewer.id)
        or mark.zone.published_by_id == viewer.id
    )


def mark_row(mark, viewer=None):
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
        'can_remove': can_remove(mark, viewer),
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
        rows = [mark_row(m, request.user)
                for m in zone.field_marks.select_related('created_by', 'zone')]
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
        row = mark_row(mark, request.user)

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


def marks_summary(zone, viewer, extra=None):
    """The same shape GET returns, so a client can reuse one reducer."""
    rows = [mark_row(m, viewer) for m in zone.field_marks.select_related('created_by', 'zone')]
    body = {'results': rows, 'disagreeing': sum(1 for r in rows if r['disagrees'])}
    body.update(extra or {})
    return body


class ZoneFieldMarkDetailView(APIView):
    """
    DELETE /api/hazards/<id>/marks/<mark_id>/   take back a mark

    Dropping a pin on a phone in the field is the easiest thing here to get
    wrong, and a stray mark is not cosmetic: a mark that disagrees with the
    outline notifies the officer who published the zone and nudges them to
    reshape a live hazard. A wrong one has to be removable.

    Deleted rather than withdrawn, unlike a hazard zone. A zone is kept
    after retraction because people were alerted and that has to stay on
    record; a field mark notifies one officer and broadcasts nothing, so
    there is no warning to preserve.

    Who may: whoever left it, or the officer who published the zone, since
    they are the one acting on it. Not anyone else — a mark is evidence,
    and several people contribute marks to the same zone. Only while the
    zone is live, which is the same condition as leaving one.
    """
    permission_classes = [IsAuthenticated, IsBarangayPersonnel]

    def delete(self, request, pk, mark_id):
        mark = (
            ZoneFieldMark.objects
            .select_related('zone', 'zone__published_by', 'zone__hazard_type',
                            'zone__barangay', 'created_by')
            .filter(pk=mark_id, zone_id=pk)
            .first()
        )
        if mark is None:
            return Response({'error': 'Field mark not found on this zone.'},
                            status=status.HTTP_404_NOT_FOUND)

        zone = mark.zone
        if zone.status != 'Active':
            return Response(
                {'error': 'This zone is no longer live, so its marks are part of the record.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        own = mark.created_by_id is not None and mark.created_by_id == request.user.id
        published_this = zone.published_by_id == request.user.id
        if not (own or published_this):
            return Response(
                {'error': 'Only the person who left this mark, or the officer who '
                          'published the zone, can remove it.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Read before deleting: `disagrees` is worked out from the zone's
        # geometry and the mark's own location.
        disagreed = mark.disagrees
        kind = mark.kind
        lat = round(mark.location.y, 6)
        lng = round(mark.location.x, 6)
        left_by = mark.created_by.full_name if mark.created_by else 'someone since removed'
        mark.delete()

        # The officer was told about this disagreement and would otherwise
        # open the zone looking for something that is no longer there.
        if disagreed and zone.published_by and zone.published_by_id != request.user.id:
            label = 'Affected here' if kind == 'Affected' else 'Clear here'
            place = f' in {zone.barangay.name}' if zone.barangay else ''
            notify(
                [zone.published_by],
                f'A "{label}" field check on your {type_name(zone)} zone{place} was '
                f'taken back by {request.user.full_name}. The outline may no longer '
                f'need changing there.',
                zone,
            )

        log_event(
            request, 'UNMARK_HAZARD_ZONE', 'hazard_zone', zone.id,
            f'Removed a {kind} mark at {lat}, {lng} left by {left_by}'
            + (' (it disagreed with the outline).' if disagreed else '.'),
        )
        return Response(marks_summary(zone, request.user, {'removed': str(mark_id)}))
