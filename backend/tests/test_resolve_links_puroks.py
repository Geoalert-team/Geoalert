"""
Resolving a flood or landslide files its history record under every purok
its area overlaps, so it colours those puroks. Sharing only a border doesn't
count. One made from reports counts in the puroks the reports named.
"""
import math
from unittest import mock

from django.contrib.gis.geos import MultiPolygon, Point
from django.db import DatabaseError
from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.barangays.models import Purok
from apps.hazards import views as hazard_views
from apps.hazards.views import HazardZoneDetailView
from apps.history.models import HistoricalRecord
from apps.reports.decide import fire_geometry
from tests.fire_setup import LAT, LNG, M, FireSetupMixin, box


class ResolveLinksPuroksTests(FireSetupMixin, TestCase):
    def resolve(self, zone):
        request = APIRequestFactory().patch('/', {'status': 'Resolved'}, format='json')
        force_authenticate(request, user=self.officer)
        return HazardZoneDetailView.as_view()(request, pk=zone.pk)

    def test_a_flood_counts_in_the_puroks_it_overlaps_not_one_it_touches(self):
        inside = self.zone(self.near, hazard_type=self.flood,
                           geometry=MultiPolygon(box(-50, -50, 50, 50), srid=4326))
        touching = self.zone(self.near, hazard_type=self.flood,
                             geometry=MultiPolygon(box(100, -50, 200, 50), srid=4326))
        self.assertEqual(self.resolve(inside).status_code, 200)
        self.assertEqual(self.resolve(touching).status_code, 200)
        self.assertEqual(list(HistoricalRecord.objects.get(hazard_zone=inside).puroks.all()), [self.near])
        self.assertEqual(list(HistoricalRecord.objects.get(hazard_zone=touching).puroks.all()), [])

    def test_a_flood_never_counts_in_a_sitio_around_its_puroks(self):
        sitio = Purok.objects.create(barangay=self.home, name='Sitio Around', kind='sitio', source='estimated',
                                     boundary=MultiPolygon(box(-300, -300, 300, 300), srid=4326))
        self.near.parent = 'Sitio Around'
        self.near.save(update_fields=['parent'])
        zone = self.zone(self.near, hazard_type=self.flood, geometry=MultiPolygon(box(-50, -50, 50, 50), srid=4326))
        self.assertEqual(self.resolve(zone).status_code, 200)
        self.assertEqual(list(HistoricalRecord.objects.get(hazard_zone=zone).puroks.all()), [self.near])
        self.assertEqual(Purok.member_counts(), {(self.home.id, 'Sitio Around'): 1})
        self.assertTrue(Purok.objects.filter(pk=sitio.pk).exists())

    def test_a_flood_made_from_reports_counts_in_the_puroks_they_named(self):
        # Its pin circle near the edge of Purok Near spills into the purok beside it
        beside = Purok.objects.create(barangay=self.home, name='Purok Beside', kind='purok', source='estimated',
                                      boundary=MultiPolygon(box(100, -100, 300, 100), srid=4326))
        edge = Point(LNG + 90 * M / math.cos(math.radians(LAT)), LAT, srid=4326)
        flood = self.zone(self.near, hazard_type=self.flood, geometry=fire_geometry([edge]))
        self.assertTrue(flood.geometry.intersects(beside.boundary))
        self.report(self.near, hazard=self.flood, hazard_zone=flood, status='Validated')
        self.assertEqual(self.resolve(flood).status_code, 200)
        self.assertEqual(list(HistoricalRecord.objects.get(hazard_zone=flood).puroks.all()), [self.near])

    def test_a_purok_lookup_error_never_stops_the_all_clear(self):
        flood = self.zone(self.near, hazard_type=self.flood,
                          geometry=MultiPolygon(box(-50, -50, 50, 50), srid=4326))
        with mock.patch.object(hazard_views, 'overlapping_puroks', side_effect=DatabaseError('bad shape')), \
                mock.patch.object(hazard_views, 'all_clear', wraps=hazard_views.all_clear) as all_clear:
            self.assertEqual(self.resolve(flood).status_code, 200)
        all_clear.assert_called_once()
        self.assertEqual(list(HistoricalRecord.objects.get(hazard_zone=flood).puroks.all()), [])
