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
    Returns historical hazard records with search filters.
    Public access — no login required.

    Filters:
      ?barangay=1
      ?hazard_type=1
      ?severity=Red
      ?date_from=2026-01-01&date_to=2026-12-31
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

        severity = request.query_params.get('severity')
        if severity:
            records = records.filter(severity_level=severity)

        date_from = request.query_params.get('date_from')
        if date_from:
            records = records.filter(occurred_at__gte=date_from)

        date_to = request.query_params.get('date_to')
        if date_to:
            records = records.filter(occurred_at__lte=date_to)

        serializer = HistoricalRecordSerializer(records, many=True)
        return Response(serializer.data)


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