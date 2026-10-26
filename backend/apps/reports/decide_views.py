"""
GET/POST /api/reports/incidents/<id>/decide/: the DRRMO's decision on a
fire report. Approving it makes it a live fire on the map, a pin at each of
its puroks; attaching joins it to a fire already live nearby; rejecting it
says why. The rules are in apps/reports/decide.py; this does the lookups,
the alerts and the one transaction.
"""
from django.db import transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.hazards.alerts import (
    affected_barangays, approval_due_at, approvers_for, issue_alert, needs_second_approval,
    notify, request_raise, type_name, where_text,
)
from apps.hazards.models import HazardZone
from apps.hazards.serializers import HazardZoneSerializer
from apps.history.purok_levels import RANK, highest, purok_levels, thresholds
from apps.reports.decide import decision_error, fire_geometry, is_nearby, report_pins
from apps.reports.models import IncidentReport
from apps.reports.serializers import IncidentReportSerializer
from apps.accounts.models import User
from utils.audit import log_event
from utils.permissions import IsDRRMOOfficer

LIVE = ('Active', 'Awaiting_Approval')


def _history(report):
    """[{id, name, count, level}] for the report's puroks, and the highest level among them."""
    puroks = list(report.puroks.all())
    levels = purok_levels([p.id for p in puroks], report.hazard_type, timezone.now())
    rows = [{'id': p.id, 'name': p.name, **levels[p.id]} for p in puroks]
    return rows, highest(r['level'] for r in rows)


def _live_fires_near(report, pins):
    # Sample fires (seed_fake_hazards) are never offered: a real report
    # joined to one would vanish with it
    zones = (HazardZone.objects
             .filter(status__in=LIVE, hazard_type=report.hazard_type, is_sample=False)
             .prefetch_related('incidentreport_set__puroks'))
    near = []
    for zone in zones:
        if pins and zone.geometry is not None and is_nearby(zone.geometry, pins):
            linked = list(zone.incidentreport_set.all())
            names = sorted({p.name for r in linked for p in r.puroks.all()})
            near.append({'id': str(zone.id), 'severity': zone.severity, 'status': zone.status,
                         'activated_at': zone.activated_at, 'reports': len(linked), 'puroks': names})
    return near


def _link(report, zone, user, note):
    now = timezone.now()
    report.status = 'Validated'
    report.hazard_zone = zone
    report.reviewed_by = report.validated_by = user
    report.reviewed_at = report.validated_at = now
    report.review_note = note
    report.save(update_fields=['status', 'hazard_zone', 'reviewed_by', 'validated_by',
                               'reviewed_at', 'validated_at', 'review_note'])


class IncidentReportDecideView(APIView):
    permission_classes = [IsAuthenticated, IsDRRMOOfficer]

    def _report(self, pk):
        return (IncidentReport.objects.select_related('hazard_type', 'barangay', 'reviewed_by')
                .prefetch_related('puroks').filter(pk=pk).first())

    def get(self, request, pk):
        report = self._report(pk)
        if report is None:
            return Response({'error': 'Report not found'}, status=status.HTTP_404_NOT_FOUND)
        rows, level = _history(report)
        return Response({
            'error': decision_error(report),
            'puroks': rows,
            'level': level,
            'thresholds': thresholds(),
            'nearby': _live_fires_near(report, report_pins(report)),
        })

    def post(self, request, pk):
        report = self._report(pk)
        if report is None:
            return Response({'error': 'Report not found'}, status=status.HTTP_404_NOT_FOUND)
        action = request.data.get('action')
        note = (request.data.get('note') or '').strip()

        with transaction.atomic():
            # Locked, so two officers deciding at once can't both succeed
            locked = IncidentReport.objects.select_for_update().get(pk=report.pk)
            report.status, report.hazard_zone_id = locked.status, locked.hazard_zone_id
            report.reviewed_by_id, report.reviewed_at = locked.reviewed_by_id, locked.reviewed_at
            error = decision_error(report)
            if error:
                return Response({'error': error}, status=status.HTTP_409_CONFLICT)

            if action == 'reject':
                return self._reject(request, report, note)
            if action == 'approve':
                return self._approve(request, report, note)
            if action == 'attach':
                return self._attach(request, report, note)
        return Response({'error': 'Choose approve, attach or reject.'}, status=status.HTTP_400_BAD_REQUEST)

    def _reject(self, request, report, note):
        if not note:
            return Response({'note': 'Say why the report is rejected.'}, status=status.HTTP_400_BAD_REQUEST)
        report.status = 'Rejected'
        report.review_note = note
        report.reviewed_by = request.user
        report.reviewed_at = timezone.now()
        report.save(update_fields=['status', 'review_note', 'reviewed_by', 'reviewed_at'])
        log_event(request, 'REJECT_FIRE_REPORT', 'incident_report', report.id, f'Fire report rejected: {note}')
        return Response({'report': IncidentReportSerializer(report, context={'request': request}).data})

    def _approve(self, request, report, note):
        # The level is the puroks' fire history; the officer doesn't choose one
        _, level = _history(report)
        pins = report_pins(report)
        if not pins:
            return Response({'error': 'This report has no purok or location to put on the map.'},
                            status=status.HTTP_400_BAD_REQUEST)

        user = request.user
        held = needs_second_approval(level) and approvers_for(user).exists()
        zone = HazardZone.objects.create(
            barangay=report.barangay, hazard_type=report.hazard_type, published_by=user,
            severity=level, geometry=fire_geometry(pins), description=report.description,
            status='Awaiting_Approval' if held else 'Active',
        )
        _link(report, zone, user, note)

        if held:
            barangays = affected_barangays(zone)
            due = approval_due_at(zone)
            notify(
                approvers_for(user),
                f'Approval needed: Extreme {type_name(zone)} alert for {where_text(barangays)}, '
                f'published by {user.full_name}. It goes out automatically at '
                f'{timezone.localtime(due):%I:%M %p} if no officer answers.',
                zone,
            )
            details = f'Fire report approved as Red for {where_text(barangays)}; held for a second approval.'
        else:
            if needs_second_approval(level):
                zone.auto_released = True  # Extreme, but nobody else to approve it
                zone.save(update_fields=['auto_released'])
            alert, barangays, recipients = issue_alert(zone, user)
            details = (f'Fire report approved as {level} for {where_text(barangays)}. '
                       f'{len(recipients)} recipient(s) notified.')
        log_event(request, 'APPROVE_FIRE_REPORT', 'hazard_zone', zone.id, f'{details} Report {report.id}.')
        return Response({
            'report': IncidentReportSerializer(report, context={'request': request}).data,
            'zone': HazardZoneSerializer(zone).data,
            'held': held,
        }, status=status.HTTP_201_CREATED)

    def _attach(self, request, report, note):
        zone = (HazardZone.objects.select_for_update()
                .filter(pk=request.data.get('zone'), status__in=LIVE, hazard_type=report.hazard_type,
                        is_sample=False).first())
        if zone is None:
            return Response({'error': 'That fire is no longer active.'}, status=status.HTTP_409_CONFLICT)
        pins = report_pins(report)
        if not pins:
            return Response({'error': 'This report has no purok or location to put on the map.'},
                            status=status.HTTP_400_BAD_REQUEST)

        user = request.user
        before = {b.id for b in affected_barangays(zone)}
        zone.geometry = fire_geometry(pins).union(zone.geometry)
        if zone.geometry.geom_type != 'MultiPolygon':
            from django.contrib.gis.geos import MultiPolygon
            zone.geometry = MultiPolygon(zone.geometry, srid=4326)
        zone.save(update_fields=['geometry'])
        _link(report, zone, user, note)

        added = [b for b in affected_barangays(zone) if b.id not in before]
        # A fire still waiting for a second officer alerts nobody yet: when
        # it goes out, issue_alert reaches the added barangays with the rest
        if added and zone.status == 'Active':
            notify(
                User.objects.filter(is_active=True, assigned_barangay__in=added).exclude(id=user.id),
                f'{type_name(zone)} alert ({zone.severity}) now covers {where_text(added)}: '
                f'another report joined the fire. Tap to see it and what to do.',
                zone,
            )

        _, history_level = _history(report)
        raised = ''
        # A raise to Red already waiting keeps its request and its clock
        raise_waiting = zone.pending_severity == 'Red' and history_level == 'Red'
        if RANK[history_level] > RANK.get(zone.severity, 0) and not raise_waiting:
            if history_level == 'Red' and approvers_for(user).exists():
                request_raise(zone, user)
                zone.save()
                raised = ' Raise to Red held for a second officer.'
            elif history_level == 'Red':
                # Nobody else to approve: raise now and send the Extreme
                # alert, as the zone PATCH does in the same case
                zone.severity = 'Red'
                zone.reset_verification()
                zone.auto_released = True
                zone.save()
                issue_alert(zone, user, suffix=' Raised to Extreme.')
                raised = ' Raised to Red (no second officer).'
            else:
                zone.severity = history_level
                zone.reset_verification()
                zone.save()
                raised = f' Raised to {history_level}.'

        log_event(request, 'ATTACH_FIRE_REPORT', 'hazard_zone', zone.id,
                  f'Report {report.id} joined the fire'
                  + (f'; newly alerted: {where_text(added)}.' if added else '.') + raised)
        return Response({
            'report': IncidentReportSerializer(report, context={'request': request}).data,
            'zone': HazardZoneSerializer(zone).data,
        })
