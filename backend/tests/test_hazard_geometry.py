from django.contrib.gis.geos import MultiPolygon, Polygon
from django.test import SimpleTestCase

from apps.hazards.geometry import OutsideCity, clip_to_city, main_barangay, repair


def square(x0, y0, x1, y1):
    return Polygon(((x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)), srid=4326)


class FakeBarangay:
    def __init__(self, name, boundary):
        self.name, self.boundary = name, boundary


CITY = MultiPolygon(square(0, 0, 10, 10), srid=4326)


class ClipToCityTests(SimpleTestCase):
    def test_inside_shape_is_unchanged(self):
        out = clip_to_city(square(2, 2, 4, 4), CITY)
        self.assertIsInstance(out, MultiPolygon)
        self.assertAlmostEqual(out.area, 4)

    def test_part_outside_the_city_is_cut_off(self):
        out = clip_to_city(square(8, 8, 12, 12), CITY)
        self.assertAlmostEqual(out.area, 4)  # only the 2x2 inside corner stays
        self.assertTrue(CITY.covers(out))

    def test_shape_entirely_outside_is_refused(self):
        with self.assertRaises(OutsideCity):
            clip_to_city(square(20, 20, 22, 22), CITY)

    def test_no_boundaries_loaded_means_no_clipping(self):
        out = clip_to_city(square(8, 8, 12, 12), None)
        self.assertAlmostEqual(out.area, 16)

    def test_keeps_srid(self):
        self.assertEqual(clip_to_city(square(2, 2, 4, 4), CITY).srid, 4326)


class RepairTests(SimpleTestCase):
    def test_figure_eight_becomes_valid_area(self):
        bowtie = Polygon(((0, 0), (2, 2), (2, 0), (0, 2), (0, 0)), srid=4326)
        self.assertFalse(bowtie.valid)
        fixed = repair(bowtie)
        self.assertTrue(fixed.valid)
        self.assertAlmostEqual(fixed.area, 2)

    def test_flat_outline_is_refused(self):
        line_like = Polygon(((0, 0), (1, 1), (2, 2), (0, 0)), srid=4326)
        with self.assertRaises(ValueError):
            repair(line_like)


class MainBarangayTests(SimpleTestCase):
    def test_picks_the_barangay_holding_most_of_the_zone(self):
        west = FakeBarangay('West', MultiPolygon(square(0, 0, 5, 10)))
        east = FakeBarangay('East', MultiPolygon(square(5, 0, 10, 10)))
        zone = MultiPolygon(square(4, 4, 8, 6))  # 1 unit west, 3 units east
        self.assertIs(main_barangay(zone, [west, east]), east)

    def test_none_when_nothing_overlaps(self):
        west = FakeBarangay('West', MultiPolygon(square(0, 0, 5, 10)))
        self.assertIsNone(main_barangay(MultiPolygon(square(20, 20, 21, 21)), [west]))
