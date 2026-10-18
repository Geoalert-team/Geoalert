"""
F7 Analytics dashboard: how the system has been used over a window of
months, for DRRMO officers and administrators.

Where the Hazard Summary and Response Status reports answer "what
happened", this answers "how are we responding": zones published, alerts
issued and how quickly barangays read them, incident reports and how fast
they are reviewed, all month by month. Every figure is counted straight
from the database; nothing is estimated.
"""

from datetime import date, datetime, time
from statistics import median

from django.db.models import Count
from django.db.models.functions import TruncMonth
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.hazards.models import HazardAlert, HazardZone
from apps.history.models import HistoricalRecord
from apps.notifications.models import Notification
from apps.reports.models import IncidentReport
from utils.audit import log_event
from utils.permissions import IsDRRMOOfficer
from utils.sampling import include_samples, without_samples

WINDOWS = (3, 6, 12, 24)
DEFAULT_WINDOW = 12


def month_starts(today, months):
    """The first day of each of the last `months` months, oldest first."""
    y, m = today.year, today.month
    out = []
    for _ in range(months):
        out.append(date(y, m, 1))
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return out[::-1]


def monthly_counts(queryset, field):
    """{'YYYY-MM': count} of rows per month of a date field."""
    rows = (queryset.annotate(_m=TruncMonth(field)).values('_m')
            .annotate(n=Count('pk')).order_by())
    return {r['_m'].strftime('%Y-%m'): r['n'] for r in rows if r['_m']}


def median_minutes(pairs):
    """Median minutes between (start, end) pairs, or None when there are none."""
    gaps = [(end - start).total_seconds() / 60 for start, end in pairs if start and end and end >= start]
    return round(median(gaps), 1) if gaps else None


def share(part, whole):
    return round(part / whole, 3) if whole else None


class AnalyticsView(APIView):
    """
    GET /api/reports/analytics/?months=12

    months: 3, 6, 12 or 24 (default 12), counted back from this month.
    include_samples=true counts seeded test rows too.
    """
    permission_classes = [IsAuthenticated, IsDRRMOOfficer]

    def get(self, request):
        try:
            months = int(request.query_params.get('months', DEFAULT_WINDOW))
        except ValueError:
            months = DEFAULT_WINDOW
        if months not in WINDOWS:
            months = DEFAULT_WINDOW

        now = timezone.now()
        starts = month_starts(timezone.localdate(), months)
        since = timezone.make_aware(datetime.combine(starts[0], time.min))

        zones_all = without_samples(HazardZone.objects.all(), request)
        zones = zones_all.filter(activated_at__gte=since)
        published = zones.exclude(status='Retracted')
        alerts = without_samples(HazardAlert.objects.filter(created_at__gte=since), request,
                                 'hazard_zone__is_sample')
        notices = Notification.objects.filter(hazard_alert__in=alerts)
        incidents = IncidentReport.objects.filter(submitted_at__gte=since)
        events = without_samples(HistoricalRecord.objects.filter(occurred_at__gte=since), request)

        # Month by month, every month present even when nothing happened
        series = {
            'zones': monthly_counts(published, 'activated_at'),
            'alerts': monthly_counts(alerts, 'created_at'),
            'incidents': monthly_counts(incidents, 'submitted_at'),
            'events': monthly_counts(events, 'occurred_at'),
        }
        monthly = [
            {'month': s.strftime('%Y-%m'), **{k: v.get(s.strftime('%Y-%m'), 0) for k, v in series.items()}}
            for s in starts
        ]

        # Alerts reaching people: of the notices sent for these alerts, how
        # many were opened, and how long that took
        sent = notices.count()
        read = notices.filter(is_read=True).count()
        read_pairs = list(notices.filter(read_at__isnull=False).values_list('sent_at', 'read_at'))

        # Incident reports: how many were reviewed, and how fast
        by_status = {r['status']: r['n'] for r in incidents.values('status').annotate(n=Count('pk')).order_by()}
        review_pairs = list(incidents.filter(reviewed_at__isnull=False).values_list('submitted_at', 'reviewed_at'))
        reviewed = by_status.get('Validated', 0) + by_status.get('Rejected', 0)

        # Zones: how long a resolved zone stayed active
        resolve_pairs = list(published.filter(resolved_at__isnull=False).values_list('activated_at', 'resolved_at'))

        data = {
            'months': months,
            'since': starts[0].isoformat(),
            'generated_at': now,
            'generated_by': request.user.full_name,
            'includes_samples': include_samples(request),
            'kpis': {
                'active_zones_now': zones_all.filter(status='Active').count(),
                'zones_published': published.count(),
                'zones_retracted': zones.filter(status='Retracted').count(),
                'alerts_issued': alerts.count(),
                'extreme_alerts': alerts.filter(severity='Red').count(),
                'notices_sent': sent,
                'notices_read': read,
                'read_rate': share(read, sent),
                'median_minutes_to_read': median_minutes(read_pairs),
                'incidents_submitted': incidents.count(),
                'incidents_pending': by_status.get('Pending', 0),
                'incidents_validated': by_status.get('Validated', 0),
                'incidents_rejected': by_status.get('Rejected', 0),
                'review_rate': share(reviewed, incidents.count()),
                'median_minutes_to_review': median_minutes(review_pairs),
                'median_minutes_zone_active': median_minutes(resolve_pairs),
                'recorded_events': events.count(),
            },
            'monthly': monthly,
            'zones_by_type': list(published.values('hazard_type__name').annotate(count=Count('pk')).order_by('-count')),
            'zones_by_severity': list(published.values('severity').annotate(count=Count('pk')).order_by('-count')),
            'zones_by_barangay': list(published.values('barangay__name').annotate(count=Count('pk')).order_by('-count')[:10]),
            'incidents_by_barangay': list(incidents.values('barangay__name').annotate(count=Count('pk')).order_by('-count')[:10]),
        }

        log_event(request, 'GENERATE_REPORT', 'hazard_zone', '',
                  f'Analytics — last {months} month(s).{" Samples included." if data["includes_samples"] else ""}')
        return Response(data)
