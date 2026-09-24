from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from django.db.models import Count

from apps.hazards.models import HazardZone, HazardAlert
from apps.history.models import HistoricalRecord
from utils.permissions import IsDRRMOOfficer

from django.utils import timezone
from apps.reports.models import IncidentReport
from apps.reports.serializers import (
    IncidentReportSerializer,
    IncidentReportCreateSerializer,
    IncidentReportReviewSerializer,
)
from utils.permissions import IsBarangayPersonnel


class HazardSummaryReportView(APIView):
    """
    GET /api/reports/hazard-summary/
    Returns total hazard occurrences, breakdown by type,
    severity distribution, and affected barangays.
    DRRMO Officer / System Admin only.

    Filters:
      ?date_from=2026-01-01&date_to=2026-12-31
      ?barangay=1
      ?hazard_type=1
    """
    permission_classes = [IsAuthenticated, IsDRRMOOfficer]

    def get(self, request):
        records = HistoricalRecord.objects.all()

        date_from = request.query_params.get('date_from')
        if date_from:
            records = records.filter(occurred_at__gte=date_from)

        date_to = request.query_params.get('date_to')
        if date_to:
            records = records.filter(occurred_at__lte=date_to)

        barangay = request.query_params.get('barangay')
        if barangay:
            records = records.filter(barangay_id=barangay)

        hazard_type = request.query_params.get('hazard_type')
        if hazard_type:
            records = records.filter(hazard_type_id=hazard_type)

        if not records.exists():
            return Response(
                {'error': 'Insufficient data available for selected criteria. Please expand the date range or modify filters.'},
                status=status.HTTP_200_OK
            )

        breakdown_by_type = list(
            records.values('hazard_type__name')
            .annotate(count=Count('id'))
            .order_by('-count')
        )

        severity_distribution = list(
            records.values('severity_level')
            .annotate(count=Count('id'))
            .order_by('-count')
        )

        affected_barangays = list(
            records.values('barangay__name')
            .annotate(count=Count('id'))
            .order_by('-count')
        )

        total_casualties = sum(
            r.total_casualties or 0 for r in records
        )
        total_displaced = sum(
            r.total_displaced or 0 for r in records
        )

        return Response({
            'report_type':            'Hazard Summary Report',
            'generated_by':           request.user.full_name,
            'total_occurrences':      records.count(),
            'breakdown_by_type':      breakdown_by_type,
            'severity_distribution':  severity_distribution,
            'affected_barangays':     affected_barangays,
            'total_casualties':       total_casualties,
            'total_displaced':        total_displaced,
        })


class ResponseStatusReportView(APIView):
    """
    GET /api/reports/response-status/
    Returns active hazards, resolved hazards, and alert
    delivery statistics. DRRMO Officer / System Admin only.

    Filters:
      ?date_from=2026-01-01&date_to=2026-12-31
      ?barangay=1
    """
    permission_classes = [IsAuthenticated, IsDRRMOOfficer]

    def get(self, request):
        zones = HazardZone.objects.all()
        alerts = HazardAlert.objects.all()

        date_from = request.query_params.get('date_from')
        if date_from:
            zones = zones.filter(activated_at__gte=date_from)
            alerts = alerts.filter(created_at__gte=date_from)

        date_to = request.query_params.get('date_to')
        if date_to:
            zones = zones.filter(activated_at__lte=date_to)
            alerts = alerts.filter(created_at__lte=date_to)

        barangay = request.query_params.get('barangay')
        if barangay:
            zones = zones.filter(barangay_id=barangay)

        active_count   = zones.filter(status='Active').count()
        resolved_count = zones.filter(status='Resolved').count()
        archived_count = zones.filter(status='Archived').count()

        if zones.count() == 0:
            return Response(
                {'error': 'Insufficient data available for selected criteria. Please expand the date range or modify filters.'},
                status=status.HTTP_200_OK
            )

        alerts_by_severity = list(
            alerts.values('severity')
            .annotate(count=Count('id'))
            .order_by('-count')
        )

        return Response({
            'report_type':          'Response Status Report',
            'generated_by':         request.user.full_name,
            'active_hazards':       active_count,
            'resolved_hazards':     resolved_count,
            'archived_hazards':     archived_count,
            'total_hazard_events':  zones.count(),
            'total_alerts_issued':  alerts.count(),
            'alerts_by_severity':   alerts_by_severity,
            
        })


class IncidentReportListCreateView(APIView):
    """
    GET  /api/reports/incidents/   → List reports
         Barangay Personnel see only their own submissions.
         DRRMO Officer / System Admin see all submissions.
    POST /api/reports/incidents/   → Submit a new report
         Barangay Personnel only.
    """
    permission_classes = [IsAuthenticated, IsBarangayPersonnel]

    def get(self, request):
        reports = IncidentReport.objects.all()

        role = request.user.role.name if request.user.role else None
        if role == 'Barangay_Personnel':
            reports = reports.filter(submitted_by=request.user)

        status_filter = request.query_params.get('status')
        if status_filter:
            reports = reports.filter(status=status_filter)

        return Response(IncidentReportSerializer(reports, many=True).data)

    def post(self, request):
        serializer = IncidentReportCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        report = serializer.save(submitted_by=request.user)
        return Response(
            IncidentReportSerializer(report).data,
            status=status.HTTP_201_CREATED
        )


class IncidentReportReviewView(APIView):
    """
    PATCH /api/reports/incidents/<id>/review/
    DRRMO Officer / System Admin only.
    Body: { "status": "Validated" | "Rejected", "review_note": "..." }
    """
    permission_classes = [IsAuthenticated, IsDRRMOOfficer]

    def patch(self, request, pk):
        try:
            report = IncidentReport.objects.get(pk=pk)
        except IncidentReport.DoesNotExist:
            return Response({'error': 'Report not found'}, status=status.HTTP_404_NOT_FOUND)

        serializer = IncidentReportReviewSerializer(report, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        report = serializer.save(
            reviewed_by=request.user,
            reviewed_at=timezone.now()
        )
        return Response(IncidentReportSerializer(report).data)