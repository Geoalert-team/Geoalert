import math
from datetime import timedelta

from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from django.db.models import Count
from django.db.models.functions import TruncMonth

from apps.history.models import HistoricalRecord
from apps.history.serializers import HistoricalRecordSerializer


class HistoricalRecordListView(APIView):
    """
    GET /api/history/
    Returns historical hazard records with search filters, newest first.
    Public access — no login required.

    Filters:
      ?barangay=1
      ?hazard_type=1   or   ?hazard_type_name=Flood
      ?severity=Red
      ?date_from=2026-01-01&date_to=2026-12-31

    Paging (optional): ?limit=5&offset=10 returns one page as
      {"count": total matching, "results": [...],
       "type_counts": [{"name": "Flood", "count": 12}, ...]}
    where type_counts ignores the hazard type filter, so a client can show
    one chip per type. Without limit the plain list is returned, as before.
    """
    permission_classes = [AllowAny]
    MAX_LIMIT = 50

    def get(self, request):
        records = HistoricalRecord.objects.select_related('hazard_type', 'barangay')

        barangay = request.query_params.get('barangay')
        if barangay:
            records = records.filter(barangay_id=barangay)

        severity = request.query_params.get('severity')
        if severity:
            records = records.filter(severity_level=severity)

        date_from = request.query_params.get('date_from')
        if date_from:
            records = records.filter(occurred_at__gte=date_from)

        date_to = request.query_params.get('date_to')
        if date_to:
            records = records.filter(occurred_at__lte=date_to)

        # Counts per hazard type before narrowing to one type
        all_types = records

        hazard_type = request.query_params.get('hazard_type')
        if hazard_type:
            records = records.filter(hazard_type_id=hazard_type)

        hazard_type_name = request.query_params.get('hazard_type_name')
        if hazard_type_name:
            records = records.filter(hazard_type__name__iexact=hazard_type_name)

        # Ties on the date are broken by id so pages never repeat or skip a record
        records = records.order_by('-occurred_at', 'id')

        if 'limit' not in request.query_params:
            return Response(HistoricalRecordSerializer(records, many=True).data)

        try:
            limit = min(max(int(request.query_params.get('limit')), 1), self.MAX_LIMIT)
            offset = max(int(request.query_params.get('offset', 0)), 0)
        except (TypeError, ValueError):
            return Response({'error': 'limit and offset must be whole numbers.'}, status=400)

        type_counts = [
            {'name': row['hazard_type__name'], 'count': row['count']}
            for row in (
                all_types.exclude(hazard_type__isnull=True)
                .values('hazard_type__name')
                .annotate(count=Count('id'))
                .order_by('-count', 'hazard_type__name')
            )
        ]
        page = records[offset:offset + limit]
        return Response({
            'count': records.count(),
            'results': HistoricalRecordSerializer(page, many=True).data,
            'type_counts': type_counts,
        })


class HistoricalRecordDetailView(APIView):
    """
    GET /api/history/<id>/
    Returns a single historical record. Public access.
    """
    permission_classes = [AllowAny]

    def get(self, request, pk):
        try:
            record = HistoricalRecord.objects.get(pk=pk)
        except HistoricalRecord.DoesNotExist:
            return Response(
                {'error': 'Historical record not found'},
                status=404
            )
        return Response(HistoricalRecordSerializer(record).data)


class HistoricalTrendsView(APIView):
    """
    GET /api/history/trends/
    Returns aggregated trend data for visualization.
    Public access.

    Supports same filters as list view.
    """
    permission_classes = [AllowAny]

    def get(self, request):
        records = HistoricalRecord.objects.all()

        barangay = request.query_params.get('barangay')
        if barangay:
            records = records.filter(barangay_id=barangay)

        hazard_type = request.query_params.get('hazard_type')
        if hazard_type:
            records = records.filter(hazard_type_id=hazard_type)

        date_from = request.query_params.get('date_from')
        if date_from:
            records = records.filter(occurred_at__gte=date_from)

        date_to = request.query_params.get('date_to')
        if date_to:
            records = records.filter(occurred_at__lte=date_to)

        # Frequency by hazard type
        by_type = list(
            records.values('hazard_type__name')
            .annotate(count=Count('id'))
            .order_by('-count')
        )

        # Frequency by barangay
        by_barangay = list(
            records.values('barangay__name')
            .annotate(count=Count('id'))
            .order_by('-count')[:10]
        )

        # Frequency by severity
        by_severity = list(
            records.values('severity_level')
            .annotate(count=Count('id'))
            .order_by('-count')
        )

        # Frequency over time (by month)
        by_month = list(
            records.annotate(month=TruncMonth('occurred_at'))
            .values('month')
            .annotate(count=Count('id'))
            .order_by('month')
        )

        return Response({
            'total_records':  records.count(),
            'by_hazard_type': by_type,
            'by_barangay':    by_barangay,
            'by_severity':    by_severity,
            'by_month':       by_month,
        })

class HistoricalHeatView(APIView):
    """
    GET /api/history/heat/?years=5
    Where past hazards happened, for the heat shading on the public map.
    Public access.

    Each record becomes one spot: the middle of its archived hazard zone and
    that zone's radius, or the middle of its barangay when no zone was kept.
    Records with neither are skipped, since there is nowhere to put them.
    """
    permission_classes = [AllowAny]

    FALLBACK_RADIUS_M = 150  # barangay-only records: a modest patch at its centre

    def get(self, request):
        try:
            years = min(max(int(request.query_params.get('years', 5)), 1), 20)
        except (TypeError, ValueError):
            years = 5
        since = timezone.now() - timedelta(days=365 * years)

        records = (
            HistoricalRecord.objects
            .filter(occurred_at__gte=since)
            .select_related('hazard_type', 'hazard_zone', 'barangay')
        )

        spots = []
        for r in records:
            if r.hazard_zone and r.hazard_zone.geometry:
                geom = r.hazard_zone.geometry
                point = geom.point_on_surface
                xmin, ymin, xmax, ymax = geom.extent
                width = (xmax - xmin) * 111320 * math.cos(math.radians(point.y))
                height = (ymax - ymin) * 111320
                radius = max(10, min(width, height) / 2)
            elif r.barangay and r.barangay.boundary:
                point = r.barangay.boundary.point_on_surface
                radius = self.FALLBACK_RADIUS_M
            else:
                continue
            spots.append({
                'type': r.hazard_type.name if r.hazard_type else None,
                'severity': r.severity_level,
                'lat': round(point.y, 6),
                'lng': round(point.x, 6),
                'radius': round(radius),
                'occurred_at': r.occurred_at,
            })

        return Response({'years': years, 'spots': spots})
