"""
Resolving a flood or landslide files its history record under every purok
its area overlaps, so it colours those puroks. Sharing only a border doesn't count.
"""
from django.contrib.gis.geos import MultiPolygon
from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.hazards.views import HazardZoneDetailView
from apps.history.models import HistoricalRecord
from tests.fire_setup import FireSetupMixin, box


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
