"""
A sitio drawn around its puroks fills only its own part with its past
hazards, so a purok inside it with none of its own isn't painted in the
sitio's colour.
"""
from django.contrib.gis.geos import MultiPolygon, Polygon
from django.test import SimpleTestCase

from apps.barangays.serializers import sitio_leftovers


def box(x0, y0, x1, y1):
    return MultiPolygon(Polygon(((x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0))), srid=4326)


class FakePurok:
    def __init__(self, id, name, boundary, parent='', barangay_id=1):
        self.id, self.name, self.boundary, self.parent, self.barangay_id = id, name, boundary, parent, barangay_id


class SitioLeftoverTests(SimpleTestCase):
    def test_the_leftover_is_the_sitio_without_its_puroks(self):
        laray = FakePurok(1, 'Sitio Laray', box(0, 0, 4, 1))
        sambag = FakePurok(2, 'Purok Sambag', box(0, 0, 1, 1), parent='Sitio Laray')
        avocado = FakePurok(3, 'Purok Avocado', box(1, 0, 2, 1), parent='Sitio Laray')
        leftovers = sitio_leftovers([laray, sambag, avocado])
        self.assertEqual(list(leftovers), [laray.id])
        self.assertAlmostEqual(leftovers[laray.id].area, 2.0)
        self.assertTrue(leftovers[laray.id].equals(box(2, 0, 4, 1)))

    def test_an_ordinary_purok_has_none(self):
        self.assertEqual(sitio_leftovers([FakePurok(1, 'Purok Siba', box(0, 0, 1, 1))]), {})

    def test_a_sitio_its_puroks_cover_has_none(self):
        tunga = FakePurok(1, 'Sitio Tunga', box(0, 0, 1, 1))
        mamsa = FakePurok(2, 'Purok Mamsa', box(0, 0, 1, 1), parent='Sitio Tunga')
        self.assertEqual(sitio_leftovers([tunga, mamsa]), {})

    def test_a_namesake_in_another_barangay_is_not_its_purok(self):
        kimba = FakePurok(1, 'Kimba', box(0, 0, 2, 1), barangay_id=1)
        elsewhere = FakePurok(2, 'Purok Kalapati', box(0, 0, 1, 1), parent='Kimba', barangay_id=2)
        self.assertEqual(sitio_leftovers([kimba, elsewhere]), {})
