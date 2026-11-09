"""Field marks: geometry only, no database."""
from types import SimpleNamespace

from django.contrib.gis.geos import MultiPolygon, Point, Polygon
from django.test import SimpleTestCase

from apps.hazards.models import HazardZone, ZoneFieldMark


def square(x0, y0, x1, y1):
    return Polygon(((x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)), srid=4326)


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
