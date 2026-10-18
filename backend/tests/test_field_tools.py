"""Past-zone templates and field marks: geometry only, no database."""
from types import SimpleNamespace

from django.contrib.gis.geos import MultiPolygon, Point, Polygon
from django.test import SimpleTestCase

from apps.hazards.field_views import MAX_TEMPLATE_CORNERS, read_point, zone_corners
from apps.hazards.models import HazardZone, ZoneFieldMark


def square(x0, y0, x1, y1):
    return Polygon(((x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)), srid=4326)


def circle(cx, cy, r, n):
    import math
    pts = [(cx + r * math.cos(2 * math.pi * i / n), cy + r * math.sin(2 * math.pi * i / n)) for i in range(n)]
    return Polygon(pts + [pts[0]], srid=4326)


class ZoneCornersTests(SimpleTestCase):
    def test_uses_the_outline_as_drawn_in_lat_lng_order(self):
        zone = SimpleNamespace(outline=square(123.80, 10.20, 123.81, 10.21), geometry=None)
        corners = zone_corners(zone)
        self.assertEqual(len(corners), 4)
        self.assertEqual(corners[0], [10.2, 123.8])  # [lat, lng], no closing repeat

    def test_falls_back_to_the_largest_saved_part(self):
        geom = MultiPolygon(square(123.80, 10.20, 123.801, 10.201), square(123.81, 10.21, 123.83, 10.23), srid=4326)
        corners = zone_corners(SimpleNamespace(outline=None, geometry=geom))
        lats = [c[0] for c in corners]
        self.assertAlmostEqual(min(lats), 10.21)

    def test_busy_outlines_are_simplified(self):
        zone = SimpleNamespace(outline=circle(123.82, 10.25, 0.01, 300), geometry=None)
        self.assertLessEqual(len(zone_corners(zone)), MAX_TEMPLATE_CORNERS)
        self.assertGreaterEqual(len(zone_corners(zone)), 3)


class ReadPointTests(SimpleTestCase):
    def test_reads_either_spelling(self):
        self.assertEqual(read_point({'lat': '10.2', 'lng': '123.8'}).coords, (123.8, 10.2))
        self.assertEqual(read_point({'latitude': 10.2, 'longitude': 123.8}).coords, (123.8, 10.2))

    def test_rejects_nonsense(self):
        self.assertIsNone(read_point({'lat': 'x', 'lng': 1}))
        self.assertIsNone(read_point({'lat': 100, 'lng': 1}))
        self.assertIsNone(read_point({}))


class MarkDisagreementTests(SimpleTestCase):
    def setUp(self):
        self.zone = HazardZone(geometry=MultiPolygon(square(123.80, 10.20, 123.81, 10.21), srid=4326))
        self.inside = Point(123.805, 10.205, srid=4326)
        self.outside = Point(123.82, 10.205, srid=4326)

    def mark(self, kind, where):
        return ZoneFieldMark(zone=self.zone, kind=kind, location=where)

    def test_affected_outside_disagrees(self):
        self.assertTrue(self.mark('Affected', self.outside).disagrees)
        self.assertFalse(self.mark('Affected', self.inside).disagrees)

    def test_clear_inside_disagrees(self):
        self.assertTrue(self.mark('Clear', self.inside).disagrees)
        self.assertFalse(self.mark('Clear', self.outside).disagrees)
