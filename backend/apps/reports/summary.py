"""
Reports & Analytics' Summary: GET /api/reports/summary/.

What GeoAlert holds, and the archive's events and their impact for the
filters, in the order disaster loss reporting uses (Sendai Framework:
deaths, injured, affected people, damage; NDRRMC/DROMIC: families and
persons affected per barangay). Each impact figure says how many of the
selected records carry it, because the archive leaves many blank: a sum over
the records that have the figure is not a total for the period.

Fires come from the BFP log (injured and dead split by firefighter/civilian
and sex, damage cost, structures); floods and landslides from the DRRMO
events sheet (injured, dead, families and persons affected).
"""
from functools import reduce
from operator import or_

from django.db.models import Case, Count, F, IntegerField, Max, Min, Q, Sum, Value, When
from django.db.models.functions import Coalesce
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.barangays.models import Barangay, Purok
from apps.hazards.models import HazardAlert, HazardZone
from apps.history.models import HistoricalRecord
from apps.notifications.models import Notification
from apps.reports.filters import FilterError, criteria_text, filter_records, parse_report_filters
from apps.reports.models import IncidentReport
from apps.reports.trends import SEVERITIES, UNSPECIFIED, hazard_order, manila_date
from utils.audit import log_event
from utils.permissions import IsDRRMOOfficer

FIRE_CELLS = ('ff_male', 'ff_female', 'civ_male', 'civ_female')
METRICS = {
    'deaths': ('fatalities',) + tuple(f'fatal_{c}' for c in FIRE_CELLS),
    'injured': ('injured',) + tuple(f'injured_{c}' for c in FIRE_CELLS),
    'families_affected': ('families_affected',),
    'persons_affected': ('persons_affected',),
    'structures_affected': ('structures_affected',),
    'damage_cost': ('damage_cost',),
}
FLOOD_LANDSLIDE = ('Flood', 'Landslide')
TOP = 10


def _recorded(fields):
    return reduce(or_, [Q(**{f'{f}__isnull': False}) for f in fields])


def _split():
    """Everyone a record lists as dead or injured, field by field (blank cells as 0)."""
    fields = METRICS['deaths'] + METRICS['injured']
    return reduce(lambda a, b: a + b, [Coalesce(F(f), Value(0)) for f in fields])


def impact_annotations():
    """Sums of every impact field and, per figure, how many records carry it."""
    ann = {'events': Count('pk')}
    for name, fields in METRICS.items():
        for f in fields:
            ann[f's_{f}'] = Sum(f)
        ann[f'r_{name}'] = Count('pk', filter=_recorded(fields))
    # The BFP log's column T counts everyone hurt or killed even where the split
    # cells are blank or fewer; that remainder is its own figure, never guessed
    # into deaths or injuries
    more = Q(total_casualties__gt=_split())
    ann['s_unsplit'] = Sum(Case(When(more, then=F('total_casualties') - _split()), default=Value(0),
                                output_field=IntegerField()))
    ann['r_unsplit_casualties'] = Count('pk', filter=more)
    return ann


def impact_values(row):
    """{figure: value or None}: None when no record carries the figure (not recorded is not zero)."""
    out = {}
    for name, fields in METRICS.items():
        if not row[f'r_{name}']:
            out[name] = None
            continue
        total = sum(row[f's_{f}'] or 0 for f in fields)
        out[name] = round(float(total), 2) if name == 'damage_cost' else int(total)
    out['unsplit_casualties'] = int(row['s_unsplit'] or 0) if row['r_unsplit_casualties'] else None
    return out


def _counts(queryset, field):
    rows = (queryset.exclude(**{field: ''}).values(field).annotate(count=Count('pk'))
            .order_by('-count', field)[:TOP])
    return [{'label': r[field], 'count': r['count']} for r in rows]


def _first(value):
    return manila_date(value).isoformat() if value else None


class SummaryView(APIView):
    """
    GET /api/reports/summary/?date_from=&date_to=&hazard_type=&barangay=

    The shared filters (apps.reports.filters). Holdings are not filtered:
    they say what the system has. Logged as the Hazard Summary report.
    """
    permission_classes = [IsAuthenticated, IsDRRMOOfficer]

    def get(self, request):
        try:
            f = parse_report_filters(request.query_params)
        except FilterError as exc:
            return Response({'error': str(exc)}, status=400)

        records = filter_records(HistoricalRecord.objects.all(), f)
        totals = records.aggregate(**impact_annotations())
        events = totals['events']
        values = impact_values(totals)
        impact = {name: {'value': values[name], 'recorded_on': totals[f'r_{name}'], 'of': events}
                  for name in (*METRICS, 'unsplit_casualties')}
        first = records.aggregate(first=Min('occurred_at'))['first']

        data = {
            'range': {'from': (f.date_from.isoformat() if f.date_from else _first(first)),
                      'to': (f.date_to or timezone.localdate()).isoformat(), 'all_records': f.date_from is None},
            'filters': {
                'hazard_type': {'id': f.hazard_type.id, 'name': f.hazard_type.name} if f.hazard_type else None,
                'barangay': {'id': f.barangay.id, 'name': f.barangay.name} if f.barangay else None,
            },
            'generated_at': timezone.now(),
            'generated_by': request.user.full_name,
            'holdings': self.holdings(),
            'events': events,
            'impact': impact,
            'displaced': None,  # never recorded in the archive
            'by_hazard': self.by_hazard(records),
            'by_barangay': self.by_barangay(records),
            'by_purok': self.by_purok(records, f),
            'severity': self.severity(records),
            'fire': self.fire(records, f),
            'flood_landslide': self.flood_landslide(records, f),
            'completeness': self.completeness(records, events),
        }
        log_event(request, 'GENERATE_REPORT', 'historical_record', '',
                  f'Hazard Summary — {events} record(s). {criteria_text(f)}')
        return Response(data)

    @staticmethod
    def holdings():
        archive = {r['hazard_type__name'] or UNSPECIFIED: r for r in
                   HistoricalRecord.objects.values('hazard_type__name')
                   .annotate(records=Count('pk'), first=Min('occurred_at'), last=Max('occurred_at')).order_by()}
        zones = HazardZone.objects.aggregate(count=Count('pk'), first=Min('activated_at'))
        alerts = HazardAlert.objects.aggregate(count=Count('pk'), first=Min('created_at'))
        reports = IncidentReport.objects.aggregate(count=Count('pk'), first=Min('submitted_at'))
        return {
            'archive': [{'hazard': h, 'records': archive[h]['records'], 'first': _first(archive[h]['first']),
                         'last': _first(archive[h]['last'])} for h in hazard_order(archive)],
            'zones': {'count': zones['count'], 'first': _first(zones['first'])},
            'alerts': {'count': alerts['count'], 'first': _first(alerts['first'])},
            'notices': {'count': Notification.objects.filter(hazard_alert__isnull=False).count()},
            'incident_reports': {'count': reports['count'], 'first': _first(reports['first'])},
            'barangays': Barangay.objects.count(),
            'puroks': Purok.objects.count(),
        }

    @staticmethod
    def by_hazard(records):
        rows = {r['hazard_type__name'] or UNSPECIFIED: r for r in
                records.values('hazard_type__name').annotate(**impact_annotations()).order_by()}
        return [{'hazard': h, 'events': rows[h]['events'], **impact_values(rows[h])} for h in hazard_order(rows)]

    @staticmethod
    def by_barangay(records):
        rows = [{'id': r['barangay_id'], 'name': r['barangay__name'] or UNSPECIFIED, 'events': r['events'],
                 **impact_values(r)}
                for r in records.values('barangay_id', 'barangay__name').annotate(**impact_annotations()).order_by()]
        # Ranked by events; records filed under no barangay last
        return sorted(rows, key=lambda r: (r['id'] is None, -r['events'], r['name']))

    @staticmethod
    def by_purok(records, f):
        if not f.barangay:
            return []
        puroks = (Purok.objects.filter(barangay=f.barangay)
                  .annotate(events=Count('history', filter=Q(history__in=records.values('pk'))))
                  .filter(events__gt=0).order_by('-events', 'name'))
        return [{'id': p.id, 'name': p.name, 'events': p.events} for p in puroks]

    @staticmethod
    def severity(records):
        counts = {r['severity_level']: r['n'] for r in records.values('severity_level').annotate(n=Count('pk')).order_by()}
        return [{'severity': s, 'count': counts.get(s, 0)} for s in SEVERITIES]

    @staticmethod
    def fire(records, f):
        if f.hazard_type and f.hazard_type.name != 'Fire':
            return None
        fires = records.filter(hazard_type__name='Fire')
        if not fires.exists():
            return None
        return {'property_category': _counts(fires, 'property_category'), 'alarm_level': _counts(fires, 'alarm_level')}

    @staticmethod
    def flood_landslide(records, f):
        if f.hazard_type and f.hazard_type.name not in FLOOD_LANDSLIDE:
            return None
        rows = records.filter(hazard_type__name__in=FLOOD_LANDSLIDE)
        if not rows.exists():
            return None
        return {'subcategory': _counts(rows, 'hazard_subcategory'), 'cause': _counts(rows, 'cause')}

    @staticmethod
    def completeness(records, events):
        fires = records.filter(hazard_type__name='Fire')
        others = records.filter(hazard_type__name__in=FLOOD_LANDSLIDE)
        rows = [
            ('barangay', 'Filed under a barangay', records.filter(barangay__isnull=False).count(), events),
            ('purok', 'Linked to a purok', records.filter(puroks__isnull=False).distinct().count(), events),
            ('location', 'Placed on the map', records.filter(location__isnull=False).count(), events),
            ('casualties', 'Deaths or injuries recorded',
             records.filter(_recorded(METRICS['deaths'] + METRICS['injured'] + ('total_casualties',))).count(), events),
        ]
        n_fires, n_others = fires.count(), others.count()
        if n_fires:
            rows.append(('damage', 'Damage cost recorded (fires)', fires.filter(damage_cost__isnull=False).count(), n_fires))
        if n_others:
            rows.append(('families', 'Families affected recorded (floods and landslides)',
                         others.filter(families_affected__isnull=False).count(), n_others))
        return [{'key': k, 'label': label, 'count': c, 'of': of} for k, label, c, of in rows]
