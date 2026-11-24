"""
F7 Analytics dashboard: how the system has been used over a window of
months, for DRRMO officers and administrators.

Where the Hazard Summary and Response Status reports answer "what
happened", this answers "how are we responding": zones published, alerts
issued and how quickly barangays read them, incident reports and how fast
they are reviewed, all month by month. Every figure is counted straight
from the database; nothing is estimated.
"""

from datetime import date
from statistics import median

from django.db.models import Count, Min
from django.db.models.functions import TruncMonth
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.hazards.models import HazardAlert, HazardZone
from apps.history.area import barangay_records
from apps.history.models import HistoricalRecord
from apps.notifications.models import Notification
from apps.reports.filters import (
    MANILA, FilterError, ReportFilters, criteria_text, day_end, day_start, parse_report_filters,
)
from apps.reports.models import IncidentReport
from utils.audit import log_event
from utils.permissions import IsDRRMOOfficer

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


def months_between(start, end):
    """The first day of every month from start's to end's, oldest first."""
    out = []
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        out.append(date(y, m, 1))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


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


def barangay_activity(zone_rows, incident_rows):
    """
    One row per barangay with both counts, from two {'barangay__name', 'count'}
    lists. A barangay in only one list gets 0 for the other, so the table
    never implies a count it was not given. Most zones first, then most
    incident reports, then by name.
    """
    rows = {}
    for key, source in (('zones', zone_rows), ('incidents', incident_rows)):
        for r in source:
            name = r['barangay__name'] or 'Unspecified'
            row = rows.setdefault(name, {'barangay': name, 'zones': 0, 'incidents': 0})
            row[key] += r['count']
    return sorted(rows.values(), key=lambda r: (-r['zones'], -r['incidents'], r['barangay']))


def first_record():
    """The day GeoAlert's own records begin (first zone, alert or incident report), or None."""
    firsts = [
        HazardZone.objects.aggregate(t=Min('activated_at'))['t'],
        HazardAlert.objects.aggregate(t=Min('created_at'))['t'],
        IncidentReport.objects.aggregate(t=Min('submitted_at'))['t'],
    ]
    firsts = [t for t in firsts if t]
    return timezone.localtime(min(firsts), MANILA).date() if firsts else None


class AnalyticsView(APIView):
    """
    GET /api/reports/analytics/?months=12

    months: 3, 6, 12 or 24 (default 12), counted back from this month.
    date_from, date_to: calendar days (Manila); either one replaces months.
                 With no date_from the range starts at first_record.
    hazard_type: a hazard type id; every figure then counts that type only.
    barangay:    a barangay id; zones, alerts (by their zone), incident
                 reports and recorded events (with the History page's
                 barangay rule) of that barangay only.
    "Active zones now" follows hazard_type and barangay, never the dates.
    A filter value that can't be used is a 400 with a sentence.
    """
    permission_classes = [IsAuthenticated, IsDRRMOOfficer]

    def get(self, request):
        try:
            f = parse_report_filters(request.query_params)
        except FilterError as exc:
            return Response({'error': str(exc)}, status=400)

        today = timezone.localdate()
        began = first_record()
        until = None
        if f.date_from or f.date_to:
            end = f.date_to or today
            start = min(f.date_from or began or today.replace(day=1), end)
            starts = months_between(start, end)
            months = len(starts)
            until = day_end(end)
        else:
            try:
                months = int(request.query_params.get('months', DEFAULT_WINDOW))
            except ValueError:
                months = DEFAULT_WINDOW
            if months not in WINDOWS:
                months = DEFAULT_WINDOW
            starts = month_starts(today, months)
            start, end = starts[0], today
        since = day_start(start)

        now = timezone.now()
        zones_all = HazardZone.objects.all()
        zones = zones_all.filter(activated_at__gte=since)
        alerts = HazardAlert.objects.filter(created_at__gte=since)
        incidents = IncidentReport.objects.filter(submitted_at__gte=since)
        events = HistoricalRecord.objects.filter(occurred_at__gte=since)
        if until:
            zones = zones.filter(activated_at__lte=until)
            alerts = alerts.filter(created_at__lte=until)
            incidents = incidents.filter(submitted_at__lte=until)
            events = events.filter(occurred_at__lte=until)

        htype = f.hazard_type
        if htype:
            zones_all = zones_all.filter(hazard_type=htype)
            zones = zones.filter(hazard_type=htype)
            alerts = alerts.filter(hazard_zone__hazard_type=htype)
            incidents = incidents.filter(hazard_type=htype)
            events = events.filter(hazard_type=htype)
        if f.barangay:
            zones_all = zones_all.filter(barangay=f.barangay)
            zones = zones.filter(barangay=f.barangay)
            alerts = alerts.filter(hazard_zone__barangay=f.barangay)
            incidents = incidents.filter(barangay=f.barangay)
            events = events.filter(id__in=barangay_records(f.barangay))
        published = zones.exclude(status='Retracted')
        notices = Notification.objects.filter(hazard_alert__in=alerts)

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
            'hazard_type': {'id': htype.id, 'name': htype.name} if htype else None,
            'barangay': {'id': f.barangay.id, 'name': f.barangay.name} if f.barangay else None,
            # The same shape as the other report answers, which exports read their criteria from
            'filters': {
                'hazard_type': {'id': htype.id, 'name': htype.name} if htype else None,
                'barangay': {'id': f.barangay.id, 'name': f.barangay.name} if f.barangay else None,
            },
            'range': {'from': start.isoformat(), 'to': end.isoformat()},
            'first_record': began.isoformat() if began else None,
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
            # Every zone of the period by where it stands now; withdrawn ones included, as their own count
            'zones_by_status': {'Active': 0, 'Resolved': 0, 'Archived': 0, 'Retracted': 0} | {
                r['status']: r['n'] for r in zones.values('status').annotate(n=Count('pk')).order_by()},
            'zones_by_type': list(published.values('hazard_type__name').annotate(count=Count('pk')).order_by('-count')),
            'zones_by_severity': list(published.values('severity').annotate(count=Count('pk')).order_by('-count')),
            # Every barangay with any activity, both counts in one row, so a
            # barangay's zones and its reports can be read side by side
            'barangays': barangay_activity(
                published.values('barangay__name').annotate(count=Count('pk')).order_by(),
                incidents.values('barangay__name').annotate(count=Count('pk')).order_by(),
            ),
        }

        if until:
            what = criteria_text(ReportFilters(start, end, htype, f.barangay))
        else:
            what = (f'last {months} month(s){f", {htype.name}" if htype else ""}'
                    f'{f", {f.barangay.name}" if f.barangay else ""}.')
        log_event(request, 'GENERATE_REPORT', 'hazard_zone', '', f'Analytics — {what}')
        return Response(data)
