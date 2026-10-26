"""
Resolving a fire against a real database: Fire out sends the all-clear and
takes it off the map; closing it with the BFP figures files one history
record that counts once in each of its puroks. Closing a fire still on the
map does both in one step. Floods keep the one-step resolve.
"""
from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.hazards.fire_close_views import FiguresDueView, FireCloseView, FireOutView
from apps.hazards.models import HazardZone
from apps.hazards.views import HazardZoneDetailView
from apps.history.models import HistoricalRecord
from apps.notifications.models import Notification
from tests.fire_setup import FireSetupMixin

OK = {'alarm_level': '1ST ALARM', 'property_category': 'RESIDENTIAL',
      'property_subcategory': 'SINGLE AND TWO FAMILY DWELLING'}


class FireCloseViewTests(FireSetupMixin, TestCase):
    def fire_zone(self, *puroks, **kw):
        """A fire made from one report per purok given (the first purok places the zone)."""
        zone = self.zone(puroks[0], **kw)
        for i, purok in enumerate(puroks):
            report = self.report(purok, hazard_zone=zone, status='Validated')
            report.started_at = timezone.now() - timedelta(minutes=30 + i)
            report.save(update_fields=['started_at'])
        return zone

    def call(self, view, method, zone=None, body=None):
        factory = APIRequestFactory()
        request = getattr(factory, method)('/', body or {}, format='json') if method != 'get' else factory.get('/')
        force_authenticate(request, user=self.officer)
        return view.as_view()(request, **({'pk': zone.pk} if zone else {}))

    def post(self, zone, action, body):
        return self.call({'fire-out': FireOutView, 'close': FireCloseView}[action], 'post', zone, body)

    def test_fire_out_takes_it_off_the_map(self):
        zone = self.fire_zone(self.near)
        self.assertEqual(self.post(zone, 'fire-out', {}).status_code, 200)
        zone.refresh_from_db()
        self.assertEqual((zone.status, zone.fire_out_by_id), ('Resolving', self.officer.id))
        self.assertFalse(HazardZone.objects.filter(status='Active').exists())
        self.assertTrue(Notification.objects.filter(recipient=self.reporter, content__contains='is out').exists())

    def test_only_an_active_fire_can_be_put_out(self):
        zone = self.fire_zone(self.near, status='Resolving')
        self.assertEqual(self.post(zone, 'fire-out', {}).data['error'], 'Only an active fire can be put out.')

    def test_close_files_one_record_counting_each_purok_once(self):
        zone = self.fire_zone(self.near, self.far, self.near, status='Resolving')
        response = self.post(zone, 'close', {**OK, 'injured_civ_male': 1, 'damage_cost': '5000'})
        self.assertEqual(response.status_code, 201)
        record = HistoricalRecord.objects.get(pk=response.data['record_id'])
        self.assertEqual(sorted(p.name for p in record.puroks.all()), ['Purok Far', 'Purok Near'])
        self.assertEqual((record.alarm_level, record.injured_civ_male, record.damage_cost),
                         ('1ST ALARM', 1, Decimal('5000')))
        self.assertEqual(record.occurred_at, min(r.started_at for r in zone.incidentreport_set.all()))
        self.assertIn('PUROK NEAR', record.location_text)
        zone.refresh_from_db()
        self.assertEqual(zone.status, 'Resolved')

    def test_closing_a_live_fire_puts_it_out_and_files_it_in_one_step(self):
        zone = self.fire_zone(self.near, self.far)
        response = self.post(zone, 'close', {**OK, 'fatal_civ_female': 2, 'structures_affected': 3})
        self.assertEqual(response.status_code, 201)
        zone.refresh_from_db()
        self.assertEqual((zone.status, zone.fire_out_by_id), ('Resolved', self.officer.id))
        self.assertIsNotNone(zone.fire_out_at)
        record = HistoricalRecord.objects.get(hazard_zone=zone)
        self.assertEqual((record.fatal_civ_female, record.structures_affected, record.total_casualties), (2, 3, 2))
        self.assertTrue(Notification.objects.filter(recipient=self.reporter, content__contains='filed in history').exists())

    def test_bad_figures_leave_a_live_fire_on_the_map(self):
        zone = self.fire_zone(self.near)
        self.assertEqual(self.post(zone, 'close', {**OK, 'property_subcategory': 'GRASS'}).status_code, 400)
        zone.refresh_from_db()
        self.assertEqual(zone.status, 'Active')
        self.assertFalse(Notification.objects.filter(content__contains='ALL CLEAR').exists())

    def test_closing_twice_files_one_record(self):
        zone = self.fire_zone(self.near, status='Resolving')
        self.post(zone, 'close', OK)
        self.assertEqual(self.post(zone, 'close', OK).status_code, 409)
        self.assertEqual(HistoricalRecord.objects.filter(hazard_zone=zone).count(), 1)

    def test_close_refuses_bad_figures(self):
        zone = self.fire_zone(self.near, status='Resolving')
        self.assertEqual(self.post(zone, 'close', {**OK, 'alarm_level': ''}).status_code, 400)
        self.assertFalse(HistoricalRecord.objects.exists())

    def test_generic_resolve_refuses_fires_not_floods(self):
        fire = self.fire_zone(self.near)
        flood = self.zone(self.near, hazard_type=self.flood)
        self.assertEqual(self.call(HazardZoneDetailView, 'patch', fire, {'status': 'Resolved'}).status_code, 400)
        self.assertEqual(self.call(HazardZoneDetailView, 'patch', flood, {'status': 'Resolved'}).status_code, 200)

    def test_figures_due_lists_fires_that_are_out(self):
        self.fire_zone(self.near)
        out = self.fire_zone(self.far, status='Resolving')
        self.assertEqual([z['id'] for z in self.call(FiguresDueView, 'get').data], [str(out.id)])
