"""
BFP personnel, against a real database: they get fire alerts city-wide and
no others, close fires with the BFP figures, see a fire record's figures and
export the fire history, read every fire report (and hear of each new one),
and can do nothing DRRMO does with floods, publishing or withdrawing.
"""
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.accounts.models import Role, User
from apps.hazards.alerts import alert_recipients, issue_alert, tell_bfp_of_report
from apps.hazards.fire_close_views import BfpOptionsView, FireCloseView
from apps.hazards.models import HazardZone
from apps.hazards.views import HazardZoneDetailView, HazardZoneRetractView
from apps.history.models import HistoricalRecord
from apps.history.views import HistoricalRecordDetailView, HistoryExportView
from apps.notifications.models import Notification
from apps.notifications.serializers import NotificationSerializer
from apps.reports.views import IncidentReportListCreateView
from tests.fire_setup import FireSetupMixin

OK = {'alarm_level': '1ST ALARM', 'property_category': 'RESIDENTIAL',
      'property_subcategory': 'SINGLE AND TWO FAMILY DWELLING'}


class BfpRoleTests(FireSetupMixin, TestCase):
    def setUp(self):
        super().setUp()
        role, _ = Role.objects.get_or_create(name='BFP_Personnel')
        self.bfp = User.objects.create_user(email='bfp@test.ph', password='x', full_name='Fire Officer', role=role)

    def call(self, view, method, body=None, user=None, params=None, **kwargs):
        factory = APIRequestFactory()
        if method == 'get':
            request = factory.get('/', params or {})
        else:
            request = getattr(factory, method)('/', body or {}, format='json')
        force_authenticate(request, user=user or self.bfp)
        return view.as_view()(request, **kwargs)

    def fire_zone(self, **kw):
        zone = self.zone(self.near, **kw)
        self.report(self.near, hazard_zone=zone, status='Validated')
        return zone

    # ---------- Alerts ----------

    def test_a_fire_alerts_bfp_and_a_flood_does_not(self):
        self.assertIn(self.bfp, alert_recipients(self.officer, [self.home], self.fire))
        self.assertNotIn(self.bfp, alert_recipients(self.officer, [self.home], self.flood))
        self.assertNotIn(self.bfp, alert_recipients(self.officer, [self.home]))

    def test_a_published_fire_reaches_bfp_wherever_it_is(self):
        zone = self.zone(self.far)
        issue_alert(zone, issued_by=self.officer)
        self.assertTrue(Notification.objects.filter(recipient=self.bfp, hazard_alert__hazard_zone=zone).exists())

    # ---------- Closing a fire ----------

    def test_bfp_closes_a_fire_with_the_figures(self):
        zone = self.fire_zone()
        issue_alert(zone, issued_by=self.officer)  # so the barangay hears the all-clear
        response = self.call(FireCloseView, 'post', OK, pk=zone.pk)
        self.assertEqual(response.status_code, 201)
        zone.refresh_from_db()
        self.assertEqual(zone.status, 'Resolved')
        self.assertEqual(HistoricalRecord.objects.get(pk=response.data['record_id']).alarm_level, '1ST ALARM')
        self.assertTrue(Notification.objects.filter(recipient=self.reporter,
                                                    content__contains='resolved by the BFP').exists())

    def test_bfp_gets_the_close_forms_lists(self):
        self.assertEqual(self.call(BfpOptionsView, 'get').status_code, 200)

    def test_bfp_cannot_close_a_flood_or_withdraw_a_fire(self):
        flood = self.zone(self.near, hazard_type=self.flood)
        self.assertEqual(self.call(HazardZoneDetailView, 'patch', {'status': 'Resolved'}, pk=flood.pk).status_code, 403)
        fire = self.fire_zone()
        self.assertEqual(self.call(HazardZoneRetractView, 'post', {'reason': 'Not a fire after all'},
                                   pk=fire.pk).status_code, 403)
        self.assertEqual(HazardZone.objects.get(pk=fire.pk).status, 'Active')

    # ---------- History ----------

    def record(self, hazard, **kw):
        return HistoricalRecord.objects.create(barangay=self.home, hazard_type=hazard, severity_level='Green',
                                               occurred_at=timezone.now() - timedelta(days=1), **kw)

    def test_bfp_sees_a_fires_figures_and_not_a_floods(self):
        fire = self.record(self.fire, location_text='12 RIZAL ST', damage_cost=5000)
        flood = self.record(self.flood, location_text='RIVERSIDE')
        self.assertEqual(self.call(HistoricalRecordDetailView, 'get', pk=fire.pk).data['location_text'], '12 RIZAL ST')
        self.assertNotIn('location_text', self.call(HistoricalRecordDetailView, 'get', pk=flood.pk).data)

    def test_bfp_exports_fires_only_whatever_it_asks_for(self):
        self.record(self.fire, location_text='THE FIRE')
        self.record(self.flood, location_text='THE FLOOD')
        for params in ({'file': 'csv'}, {'file': 'csv', 'types': 'Flood'}):
            response = self.call(HistoryExportView, 'get', params=params)
            self.assertEqual(response.status_code, 200)
            body = response.content.decode('utf-8-sig')
            self.assertIn('THE FIRE', body)
            self.assertNotIn('THE FLOOD', body)

    # ---------- Reports ----------

    def test_bfp_reads_every_fire_report_and_no_flood_report(self):
        fire = self.fire_zone()
        waiting = self.report(self.near)  # not on the map yet
        flood = self.zone(self.near, hazard_type=self.flood)
        self.report(self.near, hazard=self.flood, hazard_zone=flood, status='Validated')
        response = self.call(IncidentReportListCreateView, 'get')
        self.assertEqual(response.status_code, 200)
        self.assertEqual({r['id'] for r in response.data},
                         {str(r.id) for r in fire.incidentreport_set.all()} | {str(waiting.id)})

    def test_a_new_fire_report_is_told_to_bfp(self):
        tell_bfp_of_report(self.report(self.near))
        notice = Notification.objects.get(recipient=self.bfp)
        self.assertEqual(notice.content, 'New fire report from Barangay Home (Purok Near). '
                                         'DRRMO is reviewing it; the report is on your dashboard.')
        self.assertFalse(Notification.objects.exclude(recipient=self.bfp).exists())
        self.assertEqual(NotificationSerializer(notice).data['link'], '/app/dashboard')

    def test_bfp_cannot_submit_a_report(self):
        response = self.call(IncidentReportListCreateView, 'post', {'description': 'Smoke'})
        self.assertEqual(response.status_code, 403)
