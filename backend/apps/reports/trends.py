"""
Trend Analysis' hazard history: GET /api/reports/trends/.

The archive of past hazard events (HistoricalRecord) counted by period, by
calendar month, by severity and by barangay, for the filters on the Reports &
Analytics page. Counted in the database, in Manila time; periods with nothing
in them are present as zeros so a chart never skips a month.
"""
from datetime import date, timedelta

from django.db.models import Count, DateTimeField, Max, Min, Sum
from django.db.models.functions import ExtractIsoWeekDay, ExtractMonth, ExtractYear, Trunc
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.history.models import HistoricalRecord
from apps.reports.filters import (
    MANILA, FilterError, ReportFilters, criteria_text, filter_records, parse_report_filters,
)
from utils.audit import log_event
from utils.permissions import IsDRRMOOfficer

GRANULARITIES = ('day', 'week', 'month', 'quarter', 'year')
STEP_MONTHS = {'month': 1, 'quarter': 3, 'year': 12}
# Day and week bars past these counts are unreadable; the screen offers a longer step
MAX_BUCKETS = {'day': 92, 'week': 105}
MONTHS = ('Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec')
WEEKDAYS = ('Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun')
HAZARD_ORDER = ('Fire', 'Flood', 'Landslide')
SEVERITIES = ('Red', 'Orange', 'Green')
UNSPECIFIED = 'Unspecified'


def months_spanned(start, end):
    """Calendar months from start's to end's, both counted."""
    return (end.year - start.year) * 12 + end.month - start.month + 1


def pick_granularity(start, end):
    """Month up to 24 months, quarter up to 6 years, otherwise year."""
    n = months_spanned(start, end)
    return 'month' if n <= 24 else 'quarter' if n <= 72 else 'year'


def bucket_start(d, granularity):
    if granularity == 'day':
        return d
    if granularity == 'week':
        return d - timedelta(days=d.weekday())  # ISO weeks start on Monday
    if granularity == 'year':
        return date(d.year, 1, 1)
    if granularity == 'quarter':
        return date(d.year, 3 * ((d.month - 1) // 3) + 1, 1)
    return date(d.year, d.month, 1)


def next_bucket(d, granularity):
    """The first day of the period after the one starting on d."""
    if granularity == 'day':
        return d + timedelta(days=1)
    if granularity == 'week':
        return d + timedelta(days=7)
    m = d.month - 1 + STEP_MONTHS[granularity]
    return date(d.year + m // 12, m % 12 + 1, 1)


def bucket_key(d, granularity):
    if granularity == 'day':
        return d.isoformat()
    if granularity == 'week':
        iso = d.isocalendar()
        return f'{iso[0]}-W{iso[1]:02d}'
    if granularity == 'year':
        return str(d.year)
    if granularity == 'quarter':
        return f'{d.year}-Q{(d.month - 1) // 3 + 1}'
    return f'{d.year}-{d.month:02d}'


def bucket_label(d, granularity):
    if granularity == 'day':
        return f'{d.day} {MONTHS[d.month - 1]} {d.year}'
    if granularity == 'week':
        monday = bucket_start(d, 'week')
        return f'Week of {monday.day} {MONTHS[monday.month - 1]} {monday.year}'
    if granularity == 'year':
        return str(d.year)
    if granularity == 'quarter':
        return f'Q{(d.month - 1) // 3 + 1} {d.year}'
    return f'{MONTHS[d.month - 1]} {d.year}'


def bucket_spans(start, end, granularity):
    """(key, label, partial) for every period from start's to end's; partial when it runs past either end."""
    out = []
    d = bucket_start(start, granularity)
    while d <= end:
        following = next_bucket(d, granularity)
        partial = d < start or following - timedelta(days=1) > end
        out.append((bucket_key(d, granularity), bucket_label(d, granularity), partial))
        d = following
    return out


def buckets(start, end, granularity):
    """(key, label) for every period from start's to end's."""
    return [(key, label) for key, label, _ in bucket_spans(start, end, granularity)]


def previous_window(start, end):
    """The same number of days, ending the day before start."""
    prev_end = start - timedelta(days=1)
    return prev_end - timedelta(days=(end - start).days), prev_end


def hazard_order(names):
    """Fire, Flood, Landslide, then others by name, Unspecified last."""
    def key(name):
        if name == UNSPECIFIED:
            return (2, 0, '')
        if name in HAZARD_ORDER:
            return (0, HAZARD_ORDER.index(name), '')
        return (1, 0, name)
    return sorted(names, key=key)


def manila_date(value):
    return timezone.localtime(value, MANILA).date()


def _hazard(name):
    return name or UNSPECIFIED


class TrendsView(APIView):
    """
    GET /api/reports/trends/?date_from=&date_to=&hazard_type=&barangay=&granularity=

    No date_from: the range starts with the earliest matching record. No
    date_to: today. granularity month, quarter or year; chosen from the range
    when left out. Bad values are a 400 with a sentence to show.
    """
    permission_classes = [IsAuthenticated, IsDRRMOOfficer]

    def get(self, request):
        try:
            f = parse_report_filters(request.query_params)
            granularity = request.query_params.get('granularity') or None
            if granularity and granularity not in GRANULARITIES:
                raise FilterError('granularity must be day, week, month, quarter or year.')
        except FilterError as exc:
            return Response({'error': str(exc)}, status=400)
        try:
            return self.answer(request, f, granularity)
        except FilterError as exc:
            return Response({'error': str(exc)}, status=400)

    def answer(self, request, f, granularity):

        end = f.date_to or timezone.localdate()
        everywhere = filter_records(HistoricalRecord.objects.all(),
                                    ReportFilters(None, None, f.hazard_type, f.barangay))
        records = filter_records(HistoricalRecord.objects.all(),
                                 ReportFilters(f.date_from, end, f.hazard_type, f.barangay))
        if f.date_from:
            start = f.date_from
        else:
            first = records.aggregate(first=Min('occurred_at'))['first']
            start = min(manila_date(first), end) if first else end
        granularity = granularity or pick_granularity(start, end)
        if not f.date_from:
            start = bucket_start(start, granularity)

        by_type = {_hazard(r['hazard_type__name']): r['n']
                   for r in records.values('hazard_type__name').annotate(n=Count('pk')).order_by()}
        in_play = set(by_type) | ({f.hazard_type.name} if f.hazard_type else set())
        hazards = hazard_order(in_play)
        events = sum(by_type.values())

        def zeros():
            return {h: 0 for h in hazards}

        # Events over time, one row per period, empty periods included; a period
        # that runs past either end of the range is marked partial
        spans = bucket_spans(start, end, granularity)
        if len(spans) > MAX_BUCKETS.get(granularity, len(spans)):
            raise FilterError('Too many periods: choose a longer step.')
        series = {key: {'period': key, 'label': label, 'partial': partial, 'counts': zeros(), 'total': 0}
                  for key, label, partial in spans}
        per_period = (records.annotate(b=Trunc('occurred_at', granularity, output_field=DateTimeField(),
                                               tzinfo=MANILA))
                      .values('b', 'hazard_type__name').annotate(n=Count('pk')).order_by())
        for r in per_period:
            row = series.get(bucket_key(manila_date(r['b']), granularity))
            if row:
                row['counts'][_hazard(r['hazard_type__name'])] += r['n']
                row['total'] += r['n']

        # When in the year hazards happen
        month_of_year = [{'month': m, 'label': MONTHS[m - 1], 'counts': zeros(), 'total': 0} for m in range(1, 13)]
        per_month = (records.annotate(m=ExtractMonth('occurred_at', tzinfo=MANILA))
                     .values('m', 'hazard_type__name').annotate(n=Count('pk')).order_by())
        for r in per_month:
            row = month_of_year[r['m'] - 1]
            row['counts'][_hazard(r['hazard_type__name'])] += r['n']
            row['total'] += r['n']

        # Severity mix per hazard type
        severity = {h: {s: 0 for s in SEVERITIES} for h in hazards if by_type.get(h)}
        for r in records.values('hazard_type__name', 'severity_level').annotate(n=Count('pk')).order_by():
            counts = severity[_hazard(r['hazard_type__name'])]
            counts[r['severity_level']] = counts.get(r['severity_level'], 0) + r['n']

        # Year by month, for the calendar heatmap
        calendar = {y: [0] * 12 for y in range(start.year, end.year + 1)}
        year_month = (records.annotate(y=ExtractYear('occurred_at', tzinfo=MANILA),
                                       m=ExtractMonth('occurred_at', tzinfo=MANILA))
                      .values('y', 'm').annotate(n=Count('pk')).order_by())
        for r in year_month:
            if r['y'] in calendar:
                calendar[r['y']][r['m'] - 1] += r['n']

        # Average events in each calendar month, per year that month is covered:
        # from the hazard's first record month (or the range start) to today or
        # the range end. A month never covered is null, not "0 a year"
        firsts = {_hazard(r['hazard_type__name']): manila_date(r['first']) for r in
                  records.values('hazard_type__name').annotate(first=Min('occurred_at')).order_by()}
        last_day = min(end, timezone.localdate())
        month_average = []
        for h in hazards:
            if h not in firsts:
                continue
            opens = max(date(start.year, start.month, 1), date(firsts[h].year, firsts[h].month, 1))
            covered = [sum(1 for y in range(opens.year, last_day.year + 1) if opens <= date(y, m, 1) <= last_day)
                       for m in range(1, 13)]
            month_average.append({
                'hazard': h, 'years': max(covered), 'month_years': covered,
                'months': [round(row['counts'][h] / n, 2) if n else None for row, n in zip(month_of_year, covered)],
            })

        weekday = [{'day': d, 'label': WEEKDAYS[d - 1], 'counts': zeros(), 'total': 0} for d in range(1, 8)]
        per_day = (records.annotate(d=ExtractIsoWeekDay('occurred_at', tzinfo=MANILA))
                   .values('d', 'hazard_type__name').annotate(n=Count('pk')).order_by())
        for r in per_day:
            row = weekday[r['d'] - 1]
            row['counts'][_hazard(r['hazard_type__name'])] += r['n']
            row['total'] += r['n']

        by_year = {}
        for r in (records.annotate(y=ExtractYear('occurred_at', tzinfo=MANILA))
                  .values('y', 'severity_level').annotate(n=Count('pk')).order_by('y')):
            counts = by_year.setdefault(r['y'], {s: 0 for s in SEVERITIES})
            counts[r['severity_level']] = counts.get(r['severity_level'], 0) + r['n']

        data = {
            'range': {'from': start.isoformat(), 'to': end.isoformat(), 'granularity': granularity,
                      'all_records': f.date_from is None},
            'filters': {
                'hazard_type': {'id': f.hazard_type.id, 'name': f.hazard_type.name} if f.hazard_type else None,
                'barangay': {'id': f.barangay.id, 'name': f.barangay.name} if f.barangay else None,
            },
            'generated_at': timezone.now(),
            'generated_by': request.user.full_name,
            'totals': {
                'events': events,
                'casualties': records.aggregate(s=Sum('total_casualties'))['s'] or 0,
                'by_type': [{'hazard': h, 'count': by_type[h]} for h in hazards if by_type.get(h)],
                'previous': self.previous(f, start, end),
            },
            'series': list(series.values()),
            'month_of_year': month_of_year,
            'month_average': month_average,
            'calendar': [{'year': y, 'months': m, 'total': sum(m)} for y, m in calendar.items()],
            'weekday': weekday,
            'severity': [{'hazard': h, 'counts': c} for h, c in severity.items()],
            'severity_by_year': [{'year': y, 'counts': c} for y, c in sorted(by_year.items())],
            'barangays': self.barangays(records, f, events, by_type),
            'coverage': self.coverage(everywhere),
        }
        log_event(request, 'GENERATE_REPORT', 'historical_record', '', f'Trend analysis — {criteria_text(f)}')
        return Response(data)

    @staticmethod
    def previous(f, start, end):
        if not f.date_from:
            return None
        p_start, p_end = previous_window(start, end)
        before = filter_records(HistoricalRecord.objects.all(), ReportFilters(p_start, p_end, f.hazard_type, f.barangay))
        by_type = {_hazard(r['hazard_type__name']): r['n']
                   for r in before.values('hazard_type__name').annotate(n=Count('pk')).order_by()}
        places = sorted(({'id': r['barangay_id'], 'name': r['barangay__name'] or UNSPECIFIED, 'total': r['n']}
                         for r in before.values('barangay_id', 'barangay__name').annotate(n=Count('pk')).order_by()),
                        key=lambda r: (r['id'] is None, -r['total'], r['name']))
        # Broken down too, so the two periods can be compared by hazard and by barangay
        return {'from': p_start.isoformat(), 'to': p_end.isoformat(), 'events': sum(by_type.values()),
                'by_type': [{'hazard': h, 'count': by_type[h]} for h in hazard_order(by_type)],
                'barangays': places}

    @staticmethod
    def barangays(records, f, events, by_type):
        """Every barangay with events, most first. Records with no barangay are 'Unspecified'."""
        def share(n):
            return round(n / events, 3) if events else None

        if f.barangay:
            # The barangay rule: also records filed elsewhere but in one of its puroks
            if not events:
                return []
            return [{'id': f.barangay.id, 'name': f.barangay.name, 'total': events,
                     'counts': {h: by_type[h] for h in hazard_order(by_type)}, 'share': share(events)}]

        rows = {}
        for r in records.values('barangay_id', 'barangay__name', 'hazard_type__name').annotate(n=Count('pk')).order_by():
            row = rows.setdefault(r['barangay_id'], {'id': r['barangay_id'], 'name': r['barangay__name'] or UNSPECIFIED,
                                                     'total': 0, 'counts': {}})
            hazard = _hazard(r['hazard_type__name'])
            row['counts'][hazard] = row['counts'].get(hazard, 0) + r['n']
            row['total'] += r['n']
        out = []
        for row in rows.values():
            row['counts'] = {h: row['counts'][h] for h in hazard_order(row['counts'])}
            row['share'] = share(row['total'])
            out.append(row)
        return sorted(out, key=lambda r: (-r['total'], r['id'] is None, r['name']))

    @staticmethod
    def coverage(everywhere):
        """First and last record per hazard type, whatever the dates picked."""
        rows = {_hazard(r['hazard_type__name']): r for r in
                everywhere.values('hazard_type__name')
                .annotate(first=Min('occurred_at'), last=Max('occurred_at'), records=Count('pk')).order_by()}
        return [{'hazard': h, 'first': manila_date(rows[h]['first']).isoformat(),
                 'last': manila_date(rows[h]['last']).isoformat(), 'records': rows[h]['records']}
                for h in hazard_order(rows)]
