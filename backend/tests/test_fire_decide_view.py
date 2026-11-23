"""
The fire decision against a real database: approving puts the fire on the
map at its puroks' fire model level for this month (Moderate, with the
reason, when the model has none), Extreme waits for a second officer, a
report is decided once, and attaching never alerts early and never restarts
a waiting raise. Floods and landslides are pushed the same way, at their own
type's history level. A zone's map pins come from its reports, whatever its
type.
"""
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.hazards.models import HazardZone
from apps.hazards.serializers import HazardZoneGeoSerializer
from apps.history.models import HistoricalRecord
from apps.notifications.models import Notification
from apps.reports.decide_views import IncidentReportDecideView
from apps.reports.views import IncidentReportReviewView
from tests.fire_model_file import model_files
from tests.fire_setup import FireSetupMixin

NO_MODEL_LEVEL = 'The fire model has no level for these puroks right now, so the level is Moderate.'


class FireDecideViewTests(FireSetupMixin, TestCase):
    def decide(self, report, body=None, user=None):
        factory = APIRequestFactory()
        request = factory.post('/', body, format='json') if body is not None else factory.get('/')
        force_authenticate(request, user=user or self.officer)
        return IncidentReportDecideView.as_view()(request, pk=report.pk)

    # the reviewer's findings

    def test_pins_come_from_reports_whatever_the_type(self):
        flood_zone = self.zone(self.near, hazard_type=self.flood)
        self.report(self.near, hazard=self.flood, hazard_zone=flood_zone, status='Validated')
        pins = HazardZoneGeoSerializer(flood_zone).data['properties']['pins']
        self.assertEqual([(p['purok_id'], p['purok_name']) for p in pins], [(self.near.id, 'Purok Near')])
        # Drawn on the map with no report: the map places it itself
        drawn = self.zone(self.near, hazard_type=self.flood)
        self.assertEqual(HazardZoneGeoSerializer(drawn).data['properties']['pins'], [])

    def test_a_flood_is_pushed_at_its_flood_history_level(self):
        self.history(self.near, 5)  # Extreme for fires: a flood doesn't count them
        for i in range(3):
            past = HistoricalRecord.objects.create(barangay=self.home, hazard_type=self.flood, severity_level='Green',
                                                   occurred_at=timezone.now() - timedelta(days=40 * (i + 1)))
            past.puroks.add(self.near)
        report = self.report(self.near, hazard=self.flood)
        check = self.decide(report).data
        self.assertEqual((check['error'], check['level']), (None, 'Orange'))
        # The quick check says who it reaches before anything is sent
        self.assertEqual((check['affected_barangays'], check['recipients']), (['Home'], 2))
        response = self.decide(report, {'action': 'approve'})
        self.assertEqual(response.status_code, 201)
        zone = HazardZone.objects.get(pk=response.data['zone']['id'])
        self.assertEqual((zone.hazard_type, zone.severity, zone.status), (self.flood, 'Orange', 'Active'))
        report.refresh_from_db()
        self.assertEqual((report.status, report.hazard_zone_id), ('Validated', zone.id))

    def test_attach_to_a_held_fire_alerts_no_one_until_it_is_approved(self):
        held = self.zone(self.near, severity='Red', status='Awaiting_Approval')
        response = self.decide(self.report(self.far), {'action': 'attach', 'zone': str(held.id)})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Notification.objects.filter(recipient=self.neighbour).exists())

    def test_attach_keeps_a_waiting_raise_on_its_clock(self):
        asked_at = timezone.now() - timedelta(minutes=4)
        waiting = self.zone(self.near, pending_severity='Red', pending_by=self.officer, pending_at=asked_at)
        with model_files({self.near: 0.01, self.far: 0.08}):  # far is Red: would ask for the raise again
            self.decide(self.report(self.far), {'action': 'attach', 'zone': str(waiting.id)}, user=self.second)
        waiting.refresh_from_db()
        self.assertEqual((waiting.pending_at, waiting.pending_by_id), (asked_at, self.officer.id))

    # the decision as the spec lists it

    def test_approve_uses_the_model_level_and_ignores_a_sent_one(self):
        self.history(self.near, 5)  # Extreme by its history, which no longer sets a fire's level
        with model_files({self.near: 0.03, self.far: 0.004}):
            response = self.decide(self.report(self.near), {'action': 'approve', 'severity': 'Green'})
        self.assertEqual(response.status_code, 201)
        zone = HazardZone.objects.get(pk=response.data['zone']['id'])
        self.assertEqual((zone.severity, zone.status), ('Orange', 'Active'))
        self.assertTrue(Notification.objects.filter(recipient=self.reporter, hazard_alert__hazard_zone=zone).exists())

    def test_extreme_waits_for_a_second_officer(self):
        with model_files({self.near: 0.08, self.far: 0.004}):
            response = self.decide(self.report(self.near), {'action': 'approve'})
        self.assertTrue(response.data['held'])
        self.assertEqual(HazardZone.objects.get(pk=response.data['zone']['id']).status, 'Awaiting_Approval')

    def test_decide_uses_model_level(self):
        with model_files({self.near: 0.08, self.far: 0.004}):
            check = self.decide(self.report(self.near, self.far)).data
        self.assertEqual((check['level'], check['level_basis'], check['level_reason']), ('Red', 'model', None))
        self.assertEqual({p['id'] for p in check['puroks']}, {self.near.id, self.far.id})  # their history, as before

    def test_decide_falls_back_to_orange(self):
        with model_files({self.far: 0.004}):  # near is not in the model
            check = self.decide(self.report(self.near, self.far)).data
            response = self.decide(self.report(self.near), {'action': 'approve'})
        self.assertEqual((check['level'], check['level_reason']), ('Orange', NO_MODEL_LEVEL))
        self.assertEqual(HazardZone.objects.get(pk=response.data['zone']['id']).severity, 'Orange')

    def test_decide_falls_back_to_orange_before_training(self):
        self.history(self.near, 5)
        with model_files(None):
            check = self.decide(self.report(self.near)).data
        self.assertEqual((check['level'], check['level_reason']), ('Orange', NO_MODEL_LEVEL))

    def test_flood_report_still_uses_history(self):
        past = HistoricalRecord.objects.create(barangay=self.home, hazard_type=self.flood, severity_level='Green',
                                               occurred_at=timezone.now() - timedelta(days=40))
        past.puroks.add(self.near)
        with model_files({self.near: 0.08}):  # a fire level never sets a flood's
            check = self.decide(self.report(self.near, hazard=self.flood)).data
        self.assertEqual((check['level'], check['level_basis'], check['level_reason']), ('Green', 'history', None))

    def test_a_report_is_decided_once(self):
        report = self.report(self.near)
        self.assertEqual(self.decide(report, {'action': 'approve'}).status_code, 201)
        again = self.decide(report, {'action': 'approve'}, user=self.second)
        self.assertEqual(again.status_code, 409)
        self.assertIn('Already decided by Officer', again.data['error'])
        self.assertEqual(HazardZone.objects.count(), 1)

    def test_reject_needs_a_note(self):
        report = self.report(self.near)
        self.assertEqual(self.decide(report, {'action': 'reject'}).status_code, 400)
        self.assertEqual(self.decide(report, {'action': 'reject', 'note': 'Duplicate'}).status_code, 200)
        report.refresh_from_db()
        self.assertEqual(report.status, 'Rejected')

    def test_attach_to_a_closed_fire_is_refused(self):
        closed = self.zone(self.near, status='Resolved')
        response = self.decide(self.report(self.near), {'action': 'attach', 'zone': str(closed.id)})
        self.assertEqual((response.status_code, response.data['error']), (409, 'That fire is no longer active.'))

    def test_the_old_review_refuses_fire_reports(self):
        request = APIRequestFactory().patch('/', {'status': 'Validated'}, format='json')
        force_authenticate(request, user=self.officer)
        response = IncidentReportReviewView.as_view()(request, pk=self.report(self.near).pk)
        self.assertEqual(response.status_code, 400)
