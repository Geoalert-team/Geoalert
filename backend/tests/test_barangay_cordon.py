"""
A barangay's hazard list has to agree with who was alerted.

affected_barangays() grows a zone by its cordon before asking which
barangays it touches, so a fire across the boundary notifies the
neighbour's personnel. BarangayHazardsView tested the drawn block alone,
so those same personnel opened their panel and found nothing — an alert
for a hazard the app said did not exist.

Uses the database, so the cordon takes the PostGIS spheroid path rather
than the planar fallback in test_cordon.py.
"""
import math

from django.contrib.gis.geos import MultiPolygon, Polygon
from django.test import TestCase
from rest_framework.test import APIRequestFactory

from apps.barangays.models import Barangay
from apps.barangays.views import BarangayHazardsView
from apps.hazards.alerts import affected_barangays
from apps.hazards.models import HazardType, HazardZone

LAT, LNG = 10.74, 122.97
M = 1 / 111_320


def box(x0, y0, x1, y1):
    """A rectangle given in meters from (LNG, LAT)."""
    sx = M / math.cos(math.radians(LAT))
    pts = ((x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0))
    return Polygon([(LNG + x * sx, LAT + y * M) for x, y in pts], srid=4326)


class BarangayCordonListingTests(TestCase):
    """
    The block runs to x=50. The neighbour starts at x=75, so there is a
    25 m gap: the smallest cordon (10 m) stops short of it and a 30 m one
    crosses into it.
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

    def zone(self, cordon_m):
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

    def test_no_cordon_leaves_the_neighbour_out_of_both(self):
        zone = self.zone(None)
        listed = self.listing(self.neighbour)
        self.assertNotIn('Across the alley', self.alerted(zone))
        self.assertNotIn(str(zone.id), listed['inside'] + listed['crossing'])

    def test_no_cordon_still_lists_it_at_home(self):
        zone = self.zone(None)
        self.assertIn(str(zone.id), self.listing(self.home)['inside'])

    def test_cordon_reaching_over_shows_in_the_neighbours_list(self):
        zone = self.zone(30)
        self.assertIn('Across the alley', self.alerted(zone))
        self.assertIn(str(zone.id), self.listing(self.neighbour)['crossing'])

    def test_reaching_in_by_cordon_is_crossing_never_inside(self):
        zone = self.zone(30)
        self.assertNotIn(str(zone.id), self.listing(self.neighbour)['inside'])

    def test_the_block_is_still_inside_its_own_barangay(self):
        zone = self.zone(30)
        home = self.listing(self.home)
        self.assertIn(str(zone.id), home['inside'])
        # Matched by the indexed query, so the cordon pass must not add it again
        self.assertNotIn(str(zone.id), home['crossing'])

    def test_a_cordon_that_stops_short_changes_nothing(self):
        zone = self.zone(10)
        listed = self.listing(self.neighbour)
        self.assertNotIn('Across the alley', self.alerted(zone))
        self.assertNotIn(str(zone.id), listed['inside'] + listed['crossing'])

    def test_listing_agrees_with_alerting_at_every_width(self):
        for cordon_m in (None, 10, 30, 100):
            with self.subTest(cordon_m=cordon_m):
                zone = self.zone(cordon_m)
                reached = 'Across the alley' in self.alerted(zone)
                listed = self.listing(self.neighbour)
                shown = str(zone.id) in listed['inside'] + listed['crossing']
                self.assertEqual(reached, shown)
                zone.delete()

    def test_a_withdrawn_zone_drops_out(self):
        zone = self.zone(30)
        self.assertIn(str(zone.id), self.listing(self.neighbour)['crossing'])
        zone.status = 'Retracted'
        zone.save(update_fields=['status'])
        listed = self.listing(self.neighbour)
        self.assertNotIn(str(zone.id), listed['inside'] + listed['crossing'])
