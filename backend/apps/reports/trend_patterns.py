"""
Trend Analysis' key changes and places, from the archive of past hazard events.

GET /api/reports/trends/patterns/  per hazard: the yearly counts over complete
    years, whether they show a steady rise or fall (apps.reports.stats), the
    latest year against the earlier ones, this year so far, a sentence built
    only from those numbers, and months that stood out from the same month in
    other years.
GET /api/reports/trends/places/    every barangay: events, events per km², the
    yearly counts and how often the barangay had events.

A year counts as complete when the whole of it is inside the range and it has
ended. Years with no records inside a hazard's span are 0 in the series and
named in the sentence as possible gaps in the archive.
"""
from datetime import date, timedelta

from django.contrib.gis.db.models.functions import Area, Transform
from django.db.models import Count, Max, Min
from django.db.models.functions import ExtractMonth, ExtractYear
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.barangays.models import Barangay
from apps.history.models import HistoricalRecord
from apps.reports.filters import MANILA, FilterError, ReportFilters, criteria_text, filter_records, parse_report_filters
from apps.reports.stats import (
    MIN_TREND_YEARS, change_vs_earlier, mann_kendall, recurrence, sens_slope, trend_verdict, unusual,
)
from apps.reports.trends import MONTHS, UNSPECIFIED, hazard_order, manila_date
from utils.audit import log_event
from utils.permissions import IsDRRMOOfficer

UTM_51N = 32651  # metres, for barangay areas around Talisay City
MAX_UNUSUAL = 12


def _filters_json(f):
    return {
        'hazard_type': {'id': f.hazard_type.id, 'name': f.hazard_type.name} if f.hazard_type else None,
        'barangay': {'id': f.barangay.id, 'name': f.barangay.name} if f.barangay else None,
    }


def scope(f, barangay=True):
    """(records, first day, last day) for the filters; with no start date the range opens on the first record's year."""
    end = f.date_to or timezone.localdate()
    records = filter_records(HistoricalRecord.objects.all(),
                             ReportFilters(f.date_from, end, f.hazard_type, f.barangay if barangay else None))
    if f.date_from:
        start = f.date_from
    else:
        first = records.aggregate(first=Min('occurred_at'))['first']
        start = date(manila_date(first).year, 1, 1) if first else date(end.year, 1, 1)
    return records, min(start, end), end


def complete_years(start, end):
    """Calendar years wholly inside [start, end] that have ended."""
    today = timezone.localdate()
    first = start.year if start == date(start.year, 1, 1) else start.year + 1
    last = end.year if end >= date(end.year, 12, 31) else end.year - 1
    return list(range(first, min(last, today.year - 1) + 1))


def _years_words(years):
    return f'{years[0]}' if len(years) == 1 else f'{years[0]}–{years[-1]}'


def describe(hazard, series, verdict, slope, p, change, so_far, tested=None, quiet_since=None):
    """
    One paragraph from the numbers alone; a direction only when the test allows
    one. `series` is every complete year shown; `tested` the years the test and
    the change used (up to the last record).
    """
    parts = []
    tested = series if tested is None else tested
    years = [y for y, _ in series]
    counts = [c for _, c in series]
    if not series:
        parts.append(f'{hazard}: no complete year on record in this range yet.')
    else:
        listed = ', '.join(str(c) for c in counts)
        parts.append(f'{hazard}: {listed} event{"s" if counts != [1] else ""} a year in {_years_words(years)}.')
        n = len(tested)
        gaps = [str(y) for y, c in tested if c == 0]
        if verdict == 'too_few_years':
            parts.append(f'{n} complete year{"s are" if n != 1 else " is"} too few to call a trend '
                         f'(at least {MIN_TREND_YEARS} are needed).')
        elif verdict == 'gaps':
            parts.append('Some years have no records, which may be gaps in the archive, so no rise or fall is named.')
        elif verdict == 'no_clear_trend':
            parts.append(f'No clear rise or fall over these {n} years (Mann–Kendall p = {p:.2f}).')
        else:
            word = 'rising' if verdict == 'increasing' else 'falling'
            parts.append(f'A {word} trend of about {abs(slope):.1f} event{"s" if abs(slope) != 1 else ""} a year '
                         f'(Mann–Kendall p = {p:.3f}).')
        if change['pct'] is not None and n > 1:
            side = 'above' if change['pct'] >= 0 else 'below'
            parts.append(f'{tested[-1][0]} had {change["latest"]}, {abs(change["pct"])}% {side} the average of the '
                         f'years before ({change["earlier_mean"]:g}).')
        if gaps:
            parts.append(f'Years with no records ({", ".join(gaps)}) may be gaps in the archive rather than quiet years.')
        if quiet_since:
            parts.append(f'No records since {quiet_since}: the years after it may be a gap in the archive.')
    if so_far:
        parts.append(f'{so_far["year"]} so far: {so_far["count"]} (to {so_far["through"]}).')
    return ' '.join(parts)


class _Base(APIView):
    permission_classes = [IsAuthenticated, IsDRRMOOfficer]
    label = ''

    def get(self, request):
        try:
            f = parse_report_filters(request.query_params)
        except FilterError as exc:
            return Response({'error': str(exc)}, status=400)
        data = self.answer(request, f)
        data.update({'filters': _filters_json(f), 'generated_at': timezone.now(),
                     'generated_by': request.user.full_name})
        log_event(request, 'GENERATE_REPORT', 'historical_record', '', f'{self.label} — {criteria_text(f)}')
        return Response(data)


class PatternsView(_Base):
    label = 'Trend patterns'

    def answer(self, request, f):
        records, start, end = scope(f)
        years = complete_years(start, end)
        by_hazard_year = {}
        for r in (records.annotate(y=ExtractYear('occurred_at', tzinfo=MANILA))
                  .values('hazard_type__name', 'y').annotate(n=Count('pk')).order_by()):
            by_hazard_year[(r['hazard_type__name'] or UNSPECIFIED, r['y'])] = r['n']
        cells = {}
        for r in (records.annotate(y=ExtractYear('occurred_at', tzinfo=MANILA), m=ExtractMonth('occurred_at', tzinfo=MANILA))
                  .values('hazard_type__name', 'y', 'm').annotate(n=Count('pk')).order_by()):
            cells[(r['hazard_type__name'] or UNSPECIFIED, r['y'], r['m'])] = r['n']
        firsts = {r['hazard_type__name'] or UNSPECIFIED: manila_date(r['first']) for r in
                  records.values('hazard_type__name').annotate(first=Min('occurred_at')).order_by()}
        lasts = {r['hazard_type__name'] or UNSPECIFIED: manila_date(r['last']) for r in
                 records.values('hazard_type__name').annotate(last=Max('occurred_at')).order_by()}

        hazards, unusual_months = [], []
        today = timezone.localdate()
        for name in hazard_order(firsts):
            first = firsts[name]
            span = [y for y in years if y >= first.year]
            series = [(y, by_hazard_year.get((name, y), 0)) for y in span]
            # Years after the last record may be a gap in the archive, not a fall:
            # they are shown, but the test and the change stop at the last record
            tested = [(y, c) for y, c in series if y <= lasts[name].year]
            quiet_since = lasts[name].year if len(tested) < len(series) else None
            counts = [c for _, c in tested]
            test = mann_kendall(counts)
            verdict = trend_verdict(counts)
            # A year with no records inside the series may be a gap too; a direction
            # it could have produced is not named
            if verdict in ('increasing', 'decreasing', 'no_clear_trend') and 0 in counts:
                verdict = 'gaps'
            slope = round(sens_slope(counts), 2)
            change = change_vs_earlier(counts)
            so_far = None
            if end.year not in span and end.year >= first.year:
                so_far = {'year': end.year, 'count': by_hazard_year.get((name, end.year), 0),
                          'through': end.isoformat()}
            hazards.append({
                'hazard': name, 'first': first.isoformat(), 'last': lasts[name].isoformat(),
                'years': [{'year': y, 'count': c} for y, c in series], 'complete_years': len(series),
                'verdict': verdict, 'slope': slope, 'p': test['p'], 'change': change, 'so_far': so_far,
                'quiet_since': quiet_since,
                'sentence': describe(name, series, verdict, slope, test['p'], change, so_far, tested, quiet_since),
            })
            unusual_months.extend(self.unusual_months(name, first, start, end, today, cells))

        unusual_months.sort(key=lambda m: m['count'] - m['baseline_mean'], reverse=True)
        return {'range': {'from': start.isoformat(), 'to': end.isoformat(), 'all_records': f.date_from is None,
                          'complete_years': years},
                'hazards': hazards, 'unusual_months': unusual_months[:MAX_UNUSUAL]}

    @staticmethod
    def unusual_months(name, first, start, end, today, cells):
        """Months above the same month in at least 3 other years, from the hazard's first record month on."""
        opens = max(start, date(first.year, first.month, 1))

        def complete(y, m):
            """The month lies inside the range, on or after the hazard's first record, and has ended."""
            nxt = date(y + (m == 12), m % 12 + 1, 1)
            return date(y, m, 1) >= opens and nxt - timedelta(days=1) <= end and nxt <= today
        out = []
        for y in range(first.year, end.year + 1):
            for m in range(1, 13):
                if not complete(y, m):
                    continue
                count = cells.get((name, y, m), 0)
                baseline = [cells.get((name, other, m), 0) for other in range(first.year, end.year + 1)
                            if other != y and complete(other, m)]
                if unusual(count, baseline):
                    out.append({'hazard': name, 'year': y, 'month': m, 'label': f'{MONTHS[m - 1]} {y}',
                                'count': count, 'baseline_mean': round(sum(baseline) / len(baseline), 2),
                                'baseline_min': min(baseline), 'baseline_max': max(baseline),
                                'baseline_years': len(baseline)})
        return out


class PlacesView(_Base):
    label = 'Trend places'

    def answer(self, request, f):
        records, start, end = scope(f, barangay=False)
        years = list(range(start.year, end.year + 1))
        whole = set(complete_years(start, end))
        counts = {}
        for r in (records.annotate(y=ExtractYear('occurred_at', tzinfo=MANILA))
                  .values('barangay_id', 'y').annotate(n=Count('pk')).order_by()):
            counts[(r['barangay_id'], r['y'])] = r['n']

        rows = []
        for b in Barangay.objects.annotate(area=Area(Transform('boundary', UTM_51N))).order_by('name'):
            per_year = [counts.get((b.id, y), 0) for y in years]
            complete_counts = [c for y, c in zip(years, per_year) if y in whole]
            total = sum(per_year)
            area = round(b.area.sq_km, 3) if b.area is not None else None
            rows.append({
                'id': b.id, 'name': b.name, 'area_km2': area, 'total': total,
                'per_km2': round(total / area, 2) if area else None,
                'years': per_year,
                'years_with_events': sum(1 for c in complete_counts if c),
                'recurrence': recurrence(complete_counts),
                'change': change_vs_earlier(complete_counts),
            })
        rows.sort(key=lambda r: (-r['total'], r['name']))
        unspecified = sum(n for (bid, _), n in counts.items() if bid is None)
        return {
            'range': {'from': start.isoformat(), 'to': end.isoformat(), 'all_records': f.date_from is None},
            'years': [{'year': y, 'complete': y in whole} for y in years],
            'barangays': rows,
            'unspecified': {'total': unspecified},
            'selected': f.barangay.id if f.barangay else None,
        }
