"""
Stage 2: a cordon is metadata on one zone, grown from the drawn hazard
when needed. These run without a database, so the buffer takes the planar
fallback; the PostGIS path gives the same shape measured on the spheroid.
"""
import math

from django.contrib.gis.geos import MultiPolygon, Polygon
from django.test import SimpleTestCase

from apps.hazards.geometry import CORDON_MAX_M, CORDON_MIN_M, with_cordon
from apps.hazards.serializers import HazardZoneCreateSerializer

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
