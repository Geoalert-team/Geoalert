import re
from datetime import date, timedelta

from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from django.db.models import Count, Q
from django.db.models.functions import TruncMonth

from apps.history.flood_landslide import SUBCATEGORIES
from apps.history.models import HistoricalRecord
from apps.history.serializers import STAFF_ONLY_FIELDS, HistoricalRecordDetailSerializer, HistoricalRecordSerializer
from utils.audit import log_event
from utils.permissions import IsDRRMOOfficer
from utils.sampling import TRUTHY


def _filtered(request):
    """
    (records, None) narrowed by ?barangay, ?purok, ?severity, ?date_from and
    ?date_to, or (None, error response). The hazard type is left to the caller.
    """
    records = HistoricalRecord.objects.select_related('hazard_type', 'barangay')

    barangay = request.query_params.get('barangay')
    purok = (request.query_params.get('purok') or '').strip()
    if purok and not barangay:
        return None, Response({'error': 'purok needs a barangay.'}, status=400)
    if purok and purok != 'none':
        try:
            purok = int(purok)
        except ValueError:
            return None, Response({'error': 'purok must be an id or "none".'}, status=400)
    if barangay:
        from apps.history.area import barangay_records
        records = records.filter(id__in=barangay_records(barangay))
    if purok == 'none':
        records = records.filter(barangay_id=barangay, puroks__isnull=True)
    elif purok:
        records = records.filter(puroks__id=purok)

    severity = request.query_params.get('severity')
    if severity:
        records = records.filter(severity_level=severity)

    date_from = request.query_params.get('date_from')
    if date_from:
        records = records.filter(occurred_at__gte=date_from)

    date_to = request.query_params.get('date_to')
    if date_to:
        records = records.filter(occurred_at__lte=date_to)
    return records, None


class HistoricalRecordListView(APIView):
    """
    GET /api/history/
    Returns historical hazard records with search filters, newest first.
    Public access — no login required.

    Filters:
      ?barangay=1      filed under it, or linked to one of its puroks
                       (apps/history/area.py), each record once
      ?purok=12  or  ?purok=none   with ?barangay: one purok's records, or
                       the barangay's records that name no purok
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
        records, error = _filtered(request)
        if error:
            return error

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
    Returns a single historical record. Public access, opened from the
    map's past hazards; DRRMO staff also get STAFF_ONLY_FIELDS.
    """
    permission_classes = [AllowAny]

    def get(self, request, pk):
        from utils.permissions import IsDRRMOOfficer

        try:
            record = (HistoricalRecord.objects
                      .select_related('barangay', 'hazard_type')
                      .prefetch_related('puroks')
                      .get(pk=pk))
        except HistoricalRecord.DoesNotExist:
            return Response(
                {'error': 'Historical record not found'},
                status=404
            )
        # In full: the BFP figures, the puroks and the exact location too
        data = HistoricalRecordDetailSerializer(record).data
        if not IsDRRMOOfficer().has_permission(request, self):
            for name in STAFF_ONLY_FIELDS:
                data.pop(name, None)
        return Response(data)


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

def _type_names(request):
    """?types=Flood,Fire as a list of names; empty means every type."""
    return [t.strip() for t in (request.query_params.get('types') or '').split(',') if t.strip()]


class PurokLevelsView(APIView):
    """
    GET /api/history/purok-levels/?types=Flood,Fire
    Each purok's level from how often it was hit, per hazard type, for the
    map's purok colours. Public access.

      {"thresholds": {"years", "moderate", "extreme"},
       "results": [{"purok": id, "type": "Fire", "count": 3, "level": "Orange"}]}

    Puroks with no past event are left out. Without ?types, every type;
    unknown names match nothing.
    """
    permission_classes = [AllowAny]

    def get(self, request):
        from apps.history.purok_levels import level_for, purok_counts, thresholds

        t = thresholds()
        since = timezone.now() - timedelta(days=365 * t['years'])
        counts = purok_counts(since, _type_names(request))
        results = [
            {'purok': purok, 'type': kind, 'count': n, 'level': level_for(n, t)}
            for (purok, kind), n in sorted(counts.items())
        ]
        return Response({'thresholds': t, 'results': results})


class AreaHistoryView(APIView):
    """
    GET /api/history/area/?barangay=7[&purok=12|none][&types=Fire][&period=all]
    One barangay's past hazards, or one of its puroks', for the map's
    barangay panel and the History page's Purok filter. Public access;
    DRRMO staff also get each event's BFP address and damage.

    In the history period (Settings) unless ?period=all. With no purok:
    the total, each purok with history (count, level), how many records
    name no purok, and the events. With purok=<id>: that purok only; with
    purok=none: the barangay's records that name no purok.
    See apps/history/area.py.
    """
    permission_classes = [AllowAny]

    def get(self, request):
        from apps.barangays.models import Barangay, Purok
        from apps.history.area import area_history
        from apps.history.purok_levels import thresholds
        from utils.permissions import IsDRRMOOfficer

        try:
            barangay = Barangay.objects.get(pk=int(request.query_params.get('barangay', '')))
        except ValueError:
            return Response({'error': 'barangay must be an id.'}, status=400)
        except Barangay.DoesNotExist:
            return Response({'error': 'Barangay not found'}, status=404)

        purok = (request.query_params.get('purok') or '').strip() or None
        if purok is not None and purok != 'none':
            try:
                purok_id = int(purok)
            except ValueError:
                return Response({'error': 'purok must be an id or "none".'}, status=400)
            purok = Purok.objects.filter(pk=purok_id, barangay=barangay).first()
            if purok is None:
                return Response({'error': f'That purok is not in Barangay {barangay.name}.'}, status=400)

        since = None
        if request.query_params.get('period') != 'all':
            since = timezone.now() - timedelta(days=365 * thresholds()['years'])

        staff = IsDRRMOOfficer().has_permission(request, self)
        return Response(area_history(barangay, purok, _type_names(request), since, staff))


class HistoricalForecastView(APIView):
    """
    GET /api/history/forecast/?month=11
    Seasonal likelihood per barangay and hazard type for a month, from the
    historical record. Public: residents see it as a heads-up, not an alert.

    Rule-based statistics only (see apps/history/forecast.py): how often
    that month was hit in past years, recent years counting more.

      ?month=1-12            defaults to next month
      ?year=2024             with month: that month in that year, read from
                             the years before it; once it has started, each
                             row also has `actual`, what happened in it
      ?date=2027-11-15       instead of month: the week around that date
      ?hazard_type_name=Flood
      ?barangay=7            also returns that barangay's 12-month profile
      ?years=10              how many past years to read (1-10)
      ?exclude_samples=true  leave seeded sample records out. Off by default:
                             the public map and the dashboard label sample
                             data instead; Reports › Analytics leaves it out.

    Without ?barangay the profile is for the whole city.
    """
    permission_classes = [AllowAny]

    def get(self, request):
        from apps.history.forecast import (
            MAX_YEARS, as_local, drop_samples, seasonal_forecast, seasonal_profile,
        )

        now = timezone.localtime()
        day = year = None
        if request.query_params.get('date'):
            try:
                on = date.fromisoformat(request.query_params['date'])
            except ValueError:
                return Response({'error': 'date must be a real date, like 2027-11-15.'}, status=400)
            month, day, year = on.month, on.day, on.year
        else:
            try:
                month = int(request.query_params.get('month') or (now.month % 12 + 1))
                if not 1 <= month <= 12:
                    raise ValueError
            except (TypeError, ValueError):
                return Response({'error': 'month must be a number from 1 to 12.'}, status=400)
            if request.query_params.get('year'):
                try:
                    year = int(request.query_params['year'])
                    if not 1900 <= year <= 2100:
                        raise ValueError
                except ValueError:
                    return Response({'error': 'year must be a year from 1900 to 2100.'}, status=400)
        if year is not None and not 1900 <= year <= 2100:
            return Response({'error': 'date must be in a year from 1900 to 2100.'}, status=400)
        try:
            years = min(max(int(request.query_params.get('years', MAX_YEARS)), 1), MAX_YEARS)
        except (TypeError, ValueError):
            years = MAX_YEARS

        hazard = (request.query_params.get('hazard_type_name') or '').strip() or None
        barangay = request.query_params.get('barangay')
        try:
            barangay = int(barangay) if barangay else None
        except ValueError:
            return Response({'error': 'barangay must be an id.'}, status=400)

        records = HistoricalRecord.objects.values(
            'barangay_id', 'barangay__name', 'hazard_type__name',
            'occurred_at', 'severity_level', 'is_sample',
        )
        tz = timezone.get_current_timezone()
        events = [
            {
                'barangay_id': r['barangay_id'],
                'barangay': r['barangay__name'],
                'hazard': r['hazard_type__name'],
                'when': as_local(r['occurred_at'], tz),
                'severity': r['severity_level'],
                'is_sample': r['is_sample'],
            }
            for r in records
        ]
        events = drop_samples(
            events, (request.query_params.get('exclude_samples') or '').strip().lower() in TRUTHY,
        )
        picked = [e for e in events if not hazard or (e['hazard'] or '').lower() == hazard.lower()]

        result = seasonal_forecast(picked, month, now, max_years=years, day=day, year=year)
        result['profile'] = seasonal_profile(events, now, barangay_id=barangay, hazard=hazard, max_years=years,
                                             year=year)
        result['profile_barangay'] = barangay
        result['hazard_type'] = hazard
        result['basis'] = {
            'records': len(picked),
            'sample_records': sum(1 for e in picked if e['is_sample']),
            'method': f'Share of past years with an event in {"the week around this date" if day else "this month"}; '
                      'a year counts half as much every 3 years back. Rule-based, no AI.',
        }
        return Response(result)


class EventOptionsView(APIView):
    """The flood and landslide close form's list: sub categories by hazard type name."""
    permission_classes = [IsAuthenticated, IsDRRMOOfficer]

    def get(self, request):
        return Response({'subcategories': SUBCATEGORIES})


class HistoryExportView(APIView):
    """
    GET /api/history/export/?file=xlsx|csv&types=Fire,Flood
    The records in the BFP fire log's columns A-W (apps/history/export.py),
    newest first. DRRMO staff only: the log has the exact address and the
    damage. Takes the list's barangay, purok and date filters; ?types are
    hazard type names, every type when left out. Sample records stay out
    of a file that leaves the system. Logged, as the report prints are.
    """
    permission_classes = [IsAuthenticated, IsDRRMOOfficer]
    FILES = {
        'xlsx': ('application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 'Excel'),
        'csv': ('text/csv; charset=utf-8', 'CSV'),
    }

    def get(self, request):
        from django.http import HttpResponse
        from apps.history.export import log_row, to_csv, to_xlsx

        kind = request.query_params.get('file') or 'xlsx'
        if kind not in self.FILES:
            return Response({'error': f'file must be one of {list(self.FILES)}.'}, status=400)
        records, error = _filtered(request)
        if error:
            return error
        types = _type_names(request)
        if types:
            match = Q()
            for name in types:
                match |= Q(hazard_type__name__iexact=name)
            records = records.filter(match)
        records = records.filter(is_sample=False).prefetch_related('puroks').order_by('-occurred_at', 'id')

        rows = [log_row(r) for r in records]
        content_type, label = self.FILES[kind]
        body = to_xlsx(rows) if kind == 'xlsx' else to_csv(rows)
        # history-fire-flood-2026-10-29.xlsx
        words = [re.sub(r'[^a-z0-9]+', '', t.lower()) for t in types]
        name = '-'.join(['history', *filter(None, words), timezone.localdate().isoformat()])

        criteria = ' '.join(f'{k}={v}' for k, v in request.query_params.items() if k != 'file' and v)
        log_event(request, 'EXPORT_REPORT', 'historical_record', '',
                  f'History downloaded as {label}: {len(rows)} record(s). {criteria}'[:300].strip())
        response = HttpResponse(body, content_type=content_type)
        response['Content-Disposition'] = f'attachment; filename="{name}.{kind}"'
        return response
