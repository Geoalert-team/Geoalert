from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from django.db import transaction
from django.db.models import Count

from apps.hazards.models import HazardZone, HazardAlert
from apps.history.models import HistoricalRecord
from utils.permissions import IsDRRMOOfficer
from utils.audit import log_event
from utils.sampling import include_samples, without_samples

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
        # Seeded sample events are excluded unless asked for: a report is
        # read as an official figure, and Faker incidents are not one.
        records = without_samples(HistoricalRecord.objects.all(), request)

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

        criteria = (
            f"date_from={date_from or '-'} date_to={date_to or '-'} "
            f"barangay={barangay or 'all'} hazard_type={hazard_type or 'all'}"
        )

        if not records.exists():
            log_event(
                request, 'GENERATE_REPORT', 'historical_record', '',
                f'Hazard Summary — no data. {criteria}',
            )
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

        log_event(
            request, 'GENERATE_REPORT', 'historical_record', '',
            f'Hazard Summary — {records.count()} record(s). {criteria}',
        )

        return Response({
            'report_type':            'Hazard Summary Report',
            'includes_samples':       include_samples(request),
            'generated_by':           request.user.full_name,
            'generated_at':           timezone.now(),
            'total_occurrences':      records.count(),
            'breakdown_by_type':      breakdown_by_type,
            'severity_distribution':  severity_distribution,
            'affected_barangays':     affected_barangays,
            'total_casualties':       total_casualties,
            'total_displaced':        total_displaced,
        })


class ReportPrintedView(APIView):
    """
    POST /api/reports/printed/

        {"report": "hazard-summary" | "response-status" | "analytics",
         "criteria": "date_from=... barangay=...",
         "via": "print" | "csv" | "pdf"}

    F7: generating a report is logged by the report endpoints themselves.
    Printing, saving as PDF and downloading as CSV happen in the browser,
    where the server can't see them, so the page reports each one here
    first. That way the audit log shows which reports left the system, in
    what form, by whom and with what filters.
    """
    permission_classes = [IsAuthenticated, IsDRRMOOfficer]
    REPORTS = {
        'hazard-summary': 'Hazard Summary',
        'response-status': 'Response Status',
        'analytics': 'Analytics',
    }
    VIA = {'print': ('PRINT_REPORT', 'printed'),
           'pdf': ('EXPORT_REPORT', 'saved as PDF'),
           'csv': ('EXPORT_REPORT', 'downloaded as CSV')}

    def post(self, request):
        kind = request.data.get('report')
        if kind not in self.REPORTS:
            return Response({'error': f'report must be one of {list(self.REPORTS)}.'},
                            status=status.HTTP_400_BAD_REQUEST)
        via = request.data.get('via') or 'print'
        if via not in self.VIA:
            return Response({'error': f'via must be one of {list(self.VIA)}.'},
                            status=status.HTTP_400_BAD_REQUEST)
        action, verb = self.VIA[via]
        criteria = str(request.data.get('criteria') or '')[:300]
        log_event(
            request, action, 'historical_record' if kind == 'hazard-summary' else 'hazard_zone', '',
            f'{self.REPORTS[kind]} {verb}. {criteria}'.strip(),
        )
        return Response({'logged': True})


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
        zones = without_samples(HazardZone.objects.all(), request)
        # HazardAlert has no flag of its own; a sample alert is one raised
        # over a sample zone.
        alerts = without_samples(
            HazardAlert.objects.all(), request, 'hazard_zone__is_sample',
        )

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

        criteria = (
            f"date_from={date_from or '-'} date_to={date_to or '-'} "
            f"barangay={barangay or 'all'}"
        )

        active_count    = zones.filter(status='Active').count()
        resolved_count  = zones.filter(status='Resolved').count()
        archived_count  = zones.filter(status='Archived').count()
        retracted_count = zones.filter(status='Retracted').count()

        # Zones withdrawn as published in error are not hazard events — they
        # never happened — so they are reported as their own figure rather
        # than counted in the total. The alert total below still counts the
        # alerts they issued, because those alerts really did go out.
        events = zones.exclude(status='Retracted')

        if zones.count() == 0:
            log_event(
                request, 'GENERATE_REPORT', 'hazard_zone', '',
                f'Response Status — no data. {criteria}',
            )
            return Response(
                {'error': 'Insufficient data available for selected criteria. Please expand the date range or modify filters.'},
                status=status.HTTP_200_OK
            )

        alerts_by_severity = list(
            alerts.values('severity')
            .annotate(count=Count('id'))
            .order_by('-count')
        )

        log_event(
            request, 'GENERATE_REPORT', 'hazard_zone', '',
            f'Response Status — {zones.count()} zone(s). {criteria}',
        )

        return Response({
            'report_type':          'Response Status Report',
            'includes_samples':     include_samples(request),
            'generated_by':         request.user.full_name,
            'generated_at':         timezone.now(),
            'active_hazards':       active_count,
            'resolved_hazards':     resolved_count,
            'archived_hazards':     archived_count,
            'retracted_hazards':    retracted_count,
            'total_hazard_events':  events.count(),
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
        # Fetched up front, or listing N reports costs N extra queries each
        # for their photos, puroks, barangay, type and people
        reports = (
            IncidentReport.objects.all()
            .select_related('barangay', 'hazard_type', 'submitted_by', 'reviewed_by')
            .prefetch_related('photos', 'puroks')
        )

        role = request.user.role.name if request.user.role else None
        if role == 'Barangay_Personnel':
            reports = reports.filter(submitted_by=request.user)

        status_filter = request.query_params.get('status')
        if status_filter:
            reports = reports.filter(status=status_filter)

        # For drawing a zone around reported spots: only pinned, not
        # rejected, of one hazard type, from the last few hours.
        params = request.query_params
        if (params.get('located') or '').lower() in ('1', 'true', 'yes'):
            reports = reports.filter(location__isnull=False).exclude(status='Rejected')
        hazard_name = (params.get('hazard_type_name') or '').strip()
        if hazard_name:
            reports = reports.filter(hazard_type__name__iexact=hazard_name)
        try:
            since_hours = float(params.get('since_hours')) if params.get('since_hours') else None
        except ValueError:
            since_hours = None
        if since_hours:
            from datetime import timedelta
            from django.utils import timezone
            reports = reports.filter(submitted_at__gte=timezone.now() - timedelta(hours=min(since_hours, 24 * 14)))

        # context carries the request so photo URLs come back absolute
        return Response(
            IncidentReportSerializer(reports, many=True, context={'request': request}).data
        )

    def post(self, request):
        # request.data covers both JSON and multipart/form-data, so a report
        # with photos and one without arrive through the same path. DRF's
        # MultiPartParser is on by default; nothing here needs to know which
        # was used.
        serializer = IncidentReportCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        # One transaction around the report and its photos. An upload that
        # fails halfway would otherwise leave a report claiming pictures it
        # does not have, which is worse than a submission that plainly
        # failed and can be retried.
        with transaction.atomic():
            report = serializer.save(submitted_by=request.user)

        return Response(
            IncidentReportSerializer(report, context={'request': request}).data,
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

        # A fire report has one way to be decided, which also puts it on the
        # map: POST .../decide/ (apps/reports/decide_views.py)
        if report.hazard_type and report.hazard_type.name.lower() == 'fire':
            return Response({'error': 'Fire reports are approved or rejected with the fire decision.'},
                            status=status.HTTP_400_BAD_REQUEST)

        serializer = IncidentReportReviewSerializer(report, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        report = serializer.save(
            reviewed_by=request.user,
            reviewed_at=timezone.now()
        )
        return Response(IncidentReportSerializer(report, context={'request': request}).data)