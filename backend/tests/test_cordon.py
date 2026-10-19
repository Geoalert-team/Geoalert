"""
Stage 2: a cordon is metadata on one zone, grown from the drawn hazard
when needed. These run without a database, so the buffer takes the planar
fallback; the PostGIS path gives the same shape measured on the spheroid.
"""
import math

from django.contrib.gis.geos import MultiPolygon, Polygon
from django.test import SimpleTestCase

from apps.hazards.geometry import CORDON_MAX_M, CORDON_MIN_M, cordon_ring, with_cordon
from apps.hazards.models import HazardZone
from apps.hazards.serializers import HazardZoneCreateSerializer, HazardZoneGeoSerializer

# Talisay's latitude, so a meter is about what it is on the real map
LAT, LNG = 10.74, 122.97
M = 1 / 111_320  # one meter of latitude, in degrees


def box(x0, y0, x1, y1):
    """A rectangle given in meters from (LNG, LAT)."""
    sx = M / math.cos(math.radians(LAT))
    pts = ((x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0))
    return Polygon([(LNG + x * sx, LAT + y * M) for x, y in pts], srid=4326)


CITY = MultiPolygon(box(-1000, -1000, 1000, 1000), srid=4326)
BLOCK = MultiPolygon(box(0, 0, 40, 40), srid=4326)


class WithCordonTests(SimpleTestCase):
    def test_no_cordon_returns_the_block_itself(self):
        self.assertIs(with_cordon(BLOCK, None, CITY), BLOCK)
        self.assertIs(with_cordon(BLOCK, 0, CITY), BLOCK)

    def test_cordon_surrounds_the_block(self):
        out = with_cordon(BLOCK, 30, CITY)
        self.assertIsInstance(out, MultiPolygon)
        self.assertTrue(out.covers(BLOCK))
        # 40 m square grown by 30 m: roughly (40 + 60)^2 less rounded corners
        self.assertGreater(out.area / BLOCK.area, 4)
        self.assertLess(out.area / BLOCK.area, 6.5)

    def test_reaches_a_barangay_the_block_does_not(self):
        neighbour = box(55, 0, 200, 40)          # starts 15 m past the block
        self.assertFalse(BLOCK.intersects(neighbour))
        self.assertTrue(with_cordon(BLOCK, 30, CITY).intersects(neighbour))
        self.assertFalse(with_cordon(BLOCK, 10, CITY).intersects(neighbour))

    def test_cordon_is_cut_at_the_city_boundary(self):
        edge_city = MultiPolygon(box(-1000, -1000, 50, 1000), srid=4326)
        out = with_cordon(BLOCK, 30, edge_city)
        self.assertTrue(edge_city.covers(out))
        self.assertTrue(out.covers(BLOCK))

    def test_keeps_srid(self):
        self.assertEqual(with_cordon(BLOCK, 20, CITY).srid, 4326)


class CordonRingTests(SimpleTestCase):
    """
    The ring is the cordon without the hazard in it, so the map can hatch
    the ring alone and leave the hazard's own shading uncovered.
    """

    def test_ring_does_not_cover_the_block(self):
        ring = cordon_ring(BLOCK, with_cordon(BLOCK, 30, CITY))
        self.assertIsInstance(ring, MultiPolygon)
        self.assertLess(ring.intersection(BLOCK).area, BLOCK.area * 1e-6)

    def test_ring_and_block_make_the_whole_cordon(self):
        reach = with_cordon(BLOCK, 30, CITY)
        ring = cordon_ring(BLOCK, reach)
        self.assertAlmostEqual((ring.area + BLOCK.area) / reach.area, 1, places=6)

    def test_ring_stays_inside_the_city(self):
        edge_city = MultiPolygon(box(-1000, -1000, 50, 1000), srid=4326)
        ring = cordon_ring(BLOCK, with_cordon(BLOCK, 30, edge_city))
        self.assertTrue(edge_city.buffer(1e-9).covers(ring))

    def test_no_cordon_no_ring(self):
        self.assertIsNone(cordon_ring(BLOCK, with_cordon(BLOCK, None, CITY)))
        self.assertIsNone(cordon_ring(BLOCK, None))
        self.assertIsNone(cordon_ring(None, None))

    def test_keeps_srid(self):
        self.assertEqual(cordon_ring(BLOCK, with_cordon(BLOCK, 20, CITY)).srid, 4326)


class CordonSerializerTests(SimpleTestCase):
    def zone(self, cordon_m):
        return HazardZone(geometry=BLOCK, cordon_m=cordon_m, severity='Red', status='Active')

    def test_zone_with_a_cordon_sends_both_shapes(self):
        s = HazardZoneGeoSerializer(context={'city': CITY})
        zone = self.zone(30)
        cordon = s.get_cordon(zone)
        ring = s.get_cordon_ring(zone)
        self.assertEqual(cordon['type'], 'MultiPolygon')
        self.assertEqual(ring['type'], 'MultiPolygon')
        # The ring is the routed cordon with a hole where the block is
        self.assertGreater(len(ring['coordinates'][0]), 1)

    def test_zone_without_a_cordon_sends_neither(self):
        s = HazardZoneGeoSerializer(context={'city': CITY})
        zone = self.zone(None)
        self.assertIsNone(s.get_cordon(zone))
        self.assertIsNone(s.get_cordon_ring(zone))


class CordonPayloadTests(SimpleTestCase):
    def errors(self, cordon):
        """Runs only the cordon field: the geometry step needs the database."""
        return HazardZoneCreateSerializer().fields['cordon_m'].run_validation(cordon)

    def test_range_is_accepted(self):
        self.assertEqual(self.errors(CORDON_MIN_M), CORDON_MIN_M)
        self.assertEqual(self.errors(CORDON_MAX_M), CORDON_MAX_M)

    def test_out_of_range_is_refused(self):
        from rest_framework.exceptions import ValidationError
        for bad in (CORDON_MIN_M - 1, CORDON_MAX_M + 1, -5):
            with self.assertRaises(ValidationError):
                self.errors(bad)

    def test_cordon_is_optional(self):
        field = HazardZoneCreateSerializer().fields['cordon_m']
        self.assertFalse(field.required)
        self.assertIsNone(field.run_validation(None))
