"""
Resolving a fire: put out, then closed with the BFP figures.

POST /api/hazards/<id>/fire-out/   the fire is out: all-clear, off the map
POST /api/hazards/<id>/close/      the BFP figures: one history record. On a
                                   fire still Active it is put out first, in
                                   the same transaction (the resolve form's
                                   one step); on one already out it only closes
GET  /api/hazards/figures-due/     fires out and still waiting for figures

A fire is one row of the BFP fire log. The report gave its columns A-F
(when and where); closing gives the rest (G onward: property type,
casualties, damage, structures, alarm level). The record counts once in
every purok its reports named, which is what the purok colours count.
Floods and landslides keep the one-step resolve in HazardZoneDetailView.
"""
from django.db import transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.hazards.alerts import all_clear, notify, touch, type_name
from apps.hazards.models import HazardZone
from apps.hazards.serializers import HazardZoneSerializer
from apps.history.bfp import ALARM_LEVELS, PROPERTY_TYPES, close_fields, exact_location
from apps.history.models import HistoricalRecord
from apps.reports.decide import zone_puroks
from utils.audit import log_event
from utils.permissions import IsDRRMOOfficer


def _is_fire(zone):
    return (zone.hazard_type.name if zone.hazard_type else '').lower() == 'fire'


def _locked_fire(pk):
    return (HazardZone.objects.select_for_update(of=('self',))
            .select_related('hazard_type', 'barangay').filter(pk=pk).first())


def _put_out(zone, user, note, reporter_text):
    """
    Take an Active fire off the map: Resolving, the all-clear to everyone who
    got its alert, and a word to whoever reported it. Call inside the
    transaction holding the zone's lock. Returns (told, where).
    """
    zone.status = 'Resolving'
    zone.fire_out_at = timezone.now()
    zone.fire_out_by = user
    touch(zone)  # the daily reminder now asks for the BFP figures
    zone.save(update_fields=['status', 'fire_out_at', 'fire_out_by', 'next_nudge_at'])

    told, where = all_clear(zone, user, note)
    reporters = {r.submitted_by for r in zone.incidentreport_set.select_related('submitted_by')
                 if r.submitted_by and r.submitted_by.is_active}
    notify(reporters, reporter_text.format(where=where), zone)
    return told, where


class FireOutView(APIView):
    permission_classes = [IsAuthenticated, IsDRRMOOfficer]

    def post(self, request, pk):
        note = (request.data.get('note') or '').strip()
        with transaction.atomic():
            zone = _locked_fire(pk)
            if zone is None:
                return Response({'error': 'Hazard zone not found'}, status=status.HTTP_404_NOT_FOUND)
            if not _is_fire(zone) or zone.status != 'Active':
                return Response({'error': 'Only an active fire can be put out.'}, status=status.HTTP_409_CONFLICT)
            told, where = _put_out(zone, request.user, note,
                                   'The fire you reported at {where} is out. DRRMO will record the BFP figures.')

        log_event(request, 'FIRE_OUT', 'hazard_zone', zone.id,
                  f'{type_name(zone)} for {where} is out. All-clear sent to {len(told)} account(s).')
        return Response(HazardZoneSerializer(zone).data)


class FireCloseView(APIView):
    permission_classes = [IsAuthenticated, IsDRRMOOfficer]

    def post(self, request, pk):
        fields, errors = close_fields(request.data)
        with transaction.atomic():
            zone = _locked_fire(pk)
            if zone is None:
                return Response({'error': 'Hazard zone not found'}, status=status.HTTP_404_NOT_FOUND)
            if not _is_fire(zone) or zone.status not in ('Active', 'Resolving'):
                return Response({'error': 'Only a live fire, or one that is out, can be closed.'},
                                status=status.HTTP_409_CONFLICT)
            if errors:
                return Response(errors, status=status.HTTP_400_BAD_REQUEST)

            summary = fields.pop('summary')
            # Still on the map: put it out first, so the all-clear goes with the record
            put_out = None
            if zone.status == 'Active':
                put_out = _put_out(zone, request.user, summary,
                                   'The fire you reported at {where} is out and has been filed in history.')

            puroks = zone_puroks(zone)
            started = [r.started_at for r in zone.incidentreport_set.all() if r.started_at]
            record = HistoricalRecord.objects.create(
                hazard_zone=zone,
                hazard_type=zone.hazard_type,
                barangay=zone.barangay,
                severity_level=zone.severity,
                occurred_at=min(started) if started else zone.activated_at,
                description=summary or (f'BFP: {fields["property_category"]} – '
                                        f'{fields["property_subcategory"]}, {fields["alarm_level"]}'),
                location_text=exact_location([p.name for p in puroks], zone.barangay.name if zone.barangay else None),
                total_displaced=None,  # not in the BFP log
                is_sample=zone.is_sample,
                **fields,
            )
            record.puroks.set(puroks)

            zone.status = 'Resolved'
            zone.resolved_at = timezone.now()
            zone.save(update_fields=['status', 'resolved_at'])

        if put_out:
            told, where = put_out
            log_event(request, 'FIRE_OUT', 'hazard_zone', zone.id,
                      f'{type_name(zone)} for {where} is out. All-clear sent to {len(told)} account(s).')
        log_event(request, 'CLOSE_FIRE', 'hazard_zone', zone.id,
                  f'Fire closed with {fields["alarm_level"]}; history record {record.id} '
                  f'for {len(puroks)} purok(s).')
        return Response({'zone': HazardZoneSerializer(zone).data, 'record_id': str(record.id)},
                        status=status.HTTP_201_CREATED)


class FiguresDueView(APIView):
    """Fires that are out and still waiting for their BFP figures, longest-waiting first."""
    permission_classes = [IsAuthenticated, IsDRRMOOfficer]

    def get(self, request):
        zones = (HazardZone.objects.filter(status='Resolving', hazard_type__name__iexact='fire')
                 .select_related('barangay', 'hazard_type').order_by('fire_out_at'))
        out = []
        for zone in zones:
            started = [r.started_at for r in zone.incidentreport_set.all() if r.started_at]
            out.append({
                **HazardZoneSerializer(zone).data,
                'barangay_name': zone.barangay.name if zone.barangay else None,
                'puroks': [p.name for p in zone_puroks(zone)],
                'started_at': min(started) if started else zone.activated_at,
            })
        return Response(out)


class BfpOptionsView(APIView):
    """The close form's lists: property types by category, and alarm levels."""
    permission_classes = [IsAuthenticated, IsDRRMOOfficer]

    def get(self, request):
        return Response({'property_types': PROPERTY_TYPES, 'alarm_levels': ALARM_LEVELS})
