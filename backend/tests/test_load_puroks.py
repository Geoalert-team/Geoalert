"""
Loading purok outlines: estimates now, the Barangay Hall's official lines later.

Swapping official lines in has to be one command that can't half-apply:
it checks every shape first, replaces only the barangays in the file (so one
barangay's official lines can go in on their own), and reports how far the
estimates were from the official lines so the estimate can be tuned.
"""
from django.contrib.gis.geos import MultiPolygon, Polygon
from django.test import SimpleTestCase

from apps.barangays import purok_load as pl
from apps.barangays.aliases import match_barangay
from apps.barangays.models import Barangay, Purok
from apps.barangays.serializers import PurokGeoSerializer


def square(x0, y0, x1, y1):
    return Polygon(((x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)), srid=4326)


def feature(props, geom=None):
    geom = geom or square(0, 0, 1, 1)
    return {'type': 'Feature', 'properties': props, 'geometry': {
        'type': 'Polygon', 'coordinates': [list(geom.coords[0])]}}


class FakeBarangay:
    def __init__(self, id, name, boundary=None):
        self.id, self.name, self.boundary = id, name, boundary


class ReadFeaturesTests(SimpleTestCase):
    def test_reads_properties_and_defaults_the_source(self):
        rows, problems = pl.read_features({'features': [feature(
            {'barangay': 'Tangke', 'name': 'Sitio Tunga', 'kind': 'sitio', 'parent': '', 'confidence': 'low'})]},
            default_source='estimated')
        self.assertEqual(problems, [])
        self.assertEqual(rows[0]['barangay'], 'Tangke')
        self.assertEqual(rows[0]['source'], 'estimated')
        self.assertEqual(rows[0]['confidence'], 'low')
        self.assertIsInstance(rows[0]['boundary'], MultiPolygon)

    def test_every_problem_is_reported_not_just_the_first(self):
        rows, problems = pl.read_features({'features': [
            feature({'name': 'A', 'kind': 'purok'}),
            feature({'barangay': 'Tangke', 'kind': 'purok'}),
            feature({'barangay': 'Tangke', 'name': 'B', 'kind': 'castle'}),
        ]}, default_source='official')
        self.assertEqual(len(problems), 3)
        self.assertIn('barangay', problems[0])
        self.assertIn('name', problems[1])
        self.assertIn('kind', problems[2])

    def test_official_rows_carry_no_confidence(self):
        rows, _ = pl.read_features({'features': [feature(
            {'barangay': 'Tangke', 'name': 'Tunga', 'kind': 'sitio', 'confidence': 'low'})]},
            default_source='official')
        self.assertEqual(rows[0]['confidence'], '')


class MatchBarangayTests(SimpleTestCase):
    def test_other_spellings_match(self):
        tabunok = FakeBarangay(20, 'Tabunok', square(0, 0, 1, 1))
        camp = FakeBarangay(4, 'Camp IV', square(0, 0, 1, 1))
        self.assertIs(match_barangay('Tabunoc', [tabunok, camp]), tabunok)
        self.assertIs(match_barangay('camp 4', [tabunok, camp]), camp)

    def test_the_row_with_an_outline_wins(self):
        # The shared database has an outline-less "Candulawan" next to the real "Cadulawan"
        empty = FakeBarangay(3, 'Candulawan')
        real = FakeBarangay(23, 'Cadulawan', square(0, 0, 1, 1))
        self.assertIs(match_barangay('Candulawan', [empty, real]), real)

    def test_unknown_name_is_none(self):
        self.assertIsNone(match_barangay('Atlantis', [FakeBarangay(1, 'Biasong')]))


class FitToBarangayTests(SimpleTestCase):
    BRGY = MultiPolygon(square(0, 0, 10, 10), srid=4326)

    def test_small_overhang_is_trimmed(self):
        # 5% of the shape lies past the barangay line: a tracing slip, cut off
        fitted, share = pl.fit_to_barangay(MultiPolygon(square(0, 0, 10.5, 10), srid=4326), self.BRGY)
        self.assertGreater(share, 0.9)
        self.assertAlmostEqual(fitted.area, 100)

    def test_shape_mostly_outside_is_refused(self):
        fitted, share = pl.fit_to_barangay(MultiPolygon(square(5, 0, 15, 10), srid=4326), self.BRGY)
        self.assertIsNone(fitted)
        self.assertAlmostEqual(share, 0.5)


class OverlapTests(SimpleTestCase):
    def test_identical_is_one_and_disjoint_is_zero(self):
        a = MultiPolygon(square(0, 0, 2, 2), srid=4326)
        self.assertAlmostEqual(pl.overlap(a, a), 1.0)
        self.assertAlmostEqual(pl.overlap(a, MultiPolygon(square(5, 5, 6, 6), srid=4326)), 0.0)

    def test_compare_matches_by_name_and_lists_the_rest(self):
        old = {'Tunga': MultiPolygon(square(0, 0, 2, 2), srid=4326), 'Magay': MultiPolygon(square(5, 5, 6, 6))}
        new = {'Sitio Tunga': MultiPolygon(square(1, 0, 3, 2), srid=4326), 'Rattan': MultiPolygon(square(8, 8, 9, 9))}
        report = pl.compare(old, new)
        self.assertEqual(len(report['matched']), 1)
        name, score = report['matched'][0]
        self.assertEqual(name, 'Sitio Tunga')
        self.assertAlmostEqual(score, 2 / 6)
        self.assertEqual(report['only_estimated'], ['Magay'])
        self.assertEqual(report['only_new'], ['Rattan'])


class FakeStore:
    def __init__(self, existing=()):
        self.rows, self.asked, self.applied = list(existing), None, None

    def existing(self, barangay_ids):
        self.asked = set(barangay_ids)
        return [r for r in self.rows if r[1] in self.asked]

    def apply(self, plan):
        self.applied = plan


class ReplaceTests(SimpleTestCase):
    """
    A reload updates puroks in place rather than deleting and recreating
    them, so their ids, and the fire history linked to them, survive.
    """

    def test_matching_puroks_are_updated_new_created_missing_deleted(self):
        tunga, rattan = {'barangay_id': 21, 'name': 'Sitio Tunga'}, {'barangay_id': 21, 'name': 'Rattan'}
        plan = pl.plan_replace([(7, 21, 'Sitio Tunga'), (8, 21, 'Magay')], [tunga, rattan])
        self.assertEqual(plan, {'update': [(7, tunga)], 'create': [rattan], 'delete': [8]})

    def test_a_respelled_purok_keeps_its_id(self):
        row = {'barangay_id': 16, 'name': 'Purok Kamunggay'}
        self.assertEqual(pl.plan_replace([(5, 16, 'Purok Kamungay')], [row])['update'], [(5, row)])

    def test_only_the_barangays_in_the_file_are_touched(self):
        store = FakeStore(existing=[(7, 21, 'Sitio Tunga'), (9, 22, 'Purok 4')])
        pl.replace([{'barangay_id': 21, 'name': 'Sitio Tunga'}], store)
        self.assertEqual(store.asked, {21})
        self.assertEqual(store.applied['delete'], [])


class PurokSerializerTests(SimpleTestCase):
    def test_feature_carries_what_the_map_needs(self):
        brgy = Barangay(id=21, name='Tangke')
        purok = Purok(id=5, barangay=brgy, name='Purok Mamsa', kind='purok', parent='Tunga',
                      boundary=MultiPolygon(square(123.84, 10.25, 123.842, 10.252), srid=4326),
                      source='estimated', confidence='low')
        data = PurokGeoSerializer(purok).data
        props = data['properties']
        self.assertEqual(data['geometry']['type'], 'MultiPolygon')
        self.assertEqual(props['barangay'], 21)
        self.assertEqual(props['barangay_name'], 'Tangke')
        self.assertEqual(props['parent'], 'Tunga')
        self.assertEqual(props['source'], 'estimated')
        self.assertEqual(props['confidence'], 'low')
        lng, lat = props['label_point']
        self.assertTrue(123.84 < lng < 123.842 and 10.25 < lat < 10.252)

    def test_feature_carries_its_member_count(self):
        brgy = Barangay(id=1, name='San Roque')
        shape = MultiPolygon(square(123.85, 10.25, 123.852, 10.252), srid=4326)
        laray = Purok(id=7, barangay=brgy, name='Sitio Laray', kind='sitio', source='estimated', boundary=shape)
        sambag = Purok(id=8, barangay=brgy, name='Purok Sambag', kind='purok', parent='Sitio Laray',
                       source='estimated', boundary=shape)
        context = {'members': {(1, 'Sitio Laray'): 2}}
        self.assertEqual(PurokGeoSerializer(laray, context=context).data['properties']['members'], 2)
        self.assertEqual(PurokGeoSerializer(sambag, context=context).data['properties']['members'], 0)
        self.assertEqual(PurokGeoSerializer(sambag).data['properties']['members'], 0)

    def test_coordinates_are_rounded_to_keep_the_download_small(self):
        # 300 outlines at full precision is over a megabyte; 6 decimals is about 0.1 m
        brgy = Barangay(id=21, name='Tangke')
        purok = Purok(id=5, barangay=brgy, name='Area 1', kind='purok', source='estimated',
                      boundary=MultiPolygon(square(123.8400001234567, 10.25, 123.842, 10.2520007654321), srid=4326))
        ring = PurokGeoSerializer(purok).data['geometry']['coordinates'][0][0]
        for lng, lat in ring:
            self.assertEqual(lng, round(lng, 6))
            self.assertEqual(lat, round(lat, 6))
