"""
A barangay's hazard list has to agree with who was alerted: both test the
zone's own area. The safety cordon used to grow it for both; it was removed
(2026-10-27), and zones published before then still hold a width in
cordon_m that nothing may read.
"""
import math

from django.contrib.gis.geos import MultiPolygon, Polygon
from django.test import TestCase
from rest_framework.test import APIRequestFactory

from apps.barangays.models import Barangay
from apps.barangays.views import BarangayHazardsView
from apps.hazards.alerts import affected_barangays
from apps.hazards.models import HazardType, HazardZone
from apps.hazards.serializers import HazardZoneCreateSerializer, HazardZoneGeoSerializer, HazardZoneSerializer

LAT, LNG = 10.74, 122.97
M = 1 / 111_320


def box(x0, y0, x1, y1):
    """A rectangle given in meters from (LNG, LAT)."""
    sx = M / math.cos(math.radians(LAT))
    pts = ((x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0))
    return Polygon([(LNG + x * sx, LAT + y * M) for x, y in pts], srid=4326)


class BarangayListingTests(TestCase):
    """
    The block runs to x=50. The neighbour starts at x=75, so there is a
    25 m gap that an old 30 m cordon used to cross.
    """

    def setUp(self):
        self.home = Barangay.objects.create(
            name='Blockside', municipality='Talisay',
            boundary=MultiPolygon(box(-250, -250, 75, 250), srid=4326),
        )
        self.neighbour = Barangay.objects.create(
            name='Across the alley', municipality='Talisay',
            boundary=MultiPolygon(box(75, -250, 300, 250), srid=4326),
        )
        self.fire = HazardType.objects.create(
            name='Fire', logo_class='fire', is_active=True,
        )
        self.block = box(-50, -50, 50, 50)

    def zone(self, cordon_m=None):
        return HazardZone.objects.create(
            hazard_type=self.fire, barangay=self.home,
            severity='Orange', status='Active',
            geometry=MultiPolygon(self.block.clone(), srid=4326),
            outline=self.block.clone(), cordon_m=cordon_m,
            description='block fire',
        )

    def listing(self, barangay):
        request = APIRequestFactory().get(f'/api/barangays/{barangay.id}/hazards/')
        return BarangayHazardsView.as_view()(request, pk=barangay.id).data

    def alerted(self, zone):
        return {b.name for b in affected_barangays(zone)}

    def test_the_neighbour_is_left_out_of_both(self):
        zone = self.zone()
        listed = self.listing(self.neighbour)
        self.assertNotIn('Across the alley', self.alerted(zone))
        self.assertNotIn(str(zone.id), listed['inside'] + listed['crossing'])

    def test_it_is_listed_inside_at_home(self):
        zone = self.zone()
        home = self.listing(self.home)
        self.assertIn(str(zone.id), home['inside'])
        self.assertNotIn(str(zone.id), home['crossing'])

    def test_an_old_cordon_width_is_ignored(self):
        for cordon_m in (10, 30, 100):
            with self.subTest(cordon_m=cordon_m):
                zone = self.zone(cordon_m)
                listed = self.listing(self.neighbour)
                self.assertEqual(self.alerted(zone), {'Blockside'})
                self.assertNotIn(str(zone.id), listed['inside'] + listed['crossing'])
                zone.delete()

    def test_a_withdrawn_zone_drops_out(self):
        zone = self.zone()
        self.assertIn(str(zone.id), self.listing(self.home)['inside'])
        zone.status = 'Retracted'
        zone.save(update_fields=['status'])
        listed = self.listing(self.home)
        self.assertNotIn(str(zone.id), listed['inside'] + listed['crossing'])


class NoCordonFieldsTests(TestCase):
    def test_the_map_and_the_dashboard_send_no_cordon(self):
        for serializer in (HazardZoneGeoSerializer, HazardZoneSerializer):
            for name in ('cordon_m', 'cordon', 'cordon_ring'):
                self.assertNotIn(name, serializer.Meta.fields)

    def test_publishing_takes_no_cordon(self):
        self.assertNotIn('cordon_m', HazardZoneCreateSerializer().fields)
