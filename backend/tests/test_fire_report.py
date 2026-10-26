"""
What a report must say: when it started and which puroks it is in - the
BFP fire log's columns A-F, asked of floods and landslides too. The reporter
picks the puroks. A fire's location is set from them, never from a pin the
client sends; a flood or landslide keeps its own pin when it has one.
Everything else is DRRMO's, entered when closing.
"""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from django.contrib.gis.geos import Point, Polygon
from django.test import SimpleTestCase

from apps.reports.fire_report import prepare_report


def square(x0, y0, x1, y1):
    return Polygon(((x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)), srid=4326)


class FakeBarangay:
    def __init__(self, id, name, boundary=None):
        self.id, self.name, self.boundary = id, name, boundary


class FakePurok:
    def __init__(self, id, barangay_id, boundary):
        self.id, self.barangay_id, self.boundary = id, barangay_id, boundary


class FakeType:
    def __init__(self, name):
        self.name = name


BRGY = FakeBarangay(19, 'San Roque', square(123.85, 10.25, 123.86, 10.26))
SAMBAG = FakePurok(3, 19, square(123.85, 10.25, 123.855, 10.255))
AGOHO = FakePurok(6, 19, square(123.855, 10.255, 123.86, 10.26))
FIRE, FLOOD, LANDSLIDE = FakeType('Fire'), FakeType('Flood'), FakeType('Landslide')
NOW = datetime(2026, 10, 25, 14, 0, tzinfo=ZoneInfo('Asia/Manila'))


def yes(barangay):
    return True


def no(barangay):
    return False


def ok(**kw):
    attrs = {'hazard_type': FIRE, 'barangay': BRGY, 'started_at': NOW - timedelta(hours=1),
             'puroks': [SAMBAG], 'location': None, 'description': 'Smoke from a house'}
    attrs.update(kw)
    return attrs


class PrepareReportTests(SimpleTestCase):
    def test_a_complete_fire_report_gets_its_location_from_the_first_purok(self):
        attrs, errors = prepare_report(ok(puroks=[SAMBAG, AGOHO], location=Point(1, 1, srid=4326)), NOW, yes)
        self.assertEqual(errors, {})
        self.assertTrue(SAMBAG.boundary.contains(attrs['location']))  # the client's pin is ignored

    def test_start_time_is_required_and_not_in_the_future(self):
        self.assertEqual(prepare_report(ok(started_at=None), NOW, yes)[1],
                         {'started_at': 'Say when the fire started.'})
        self.assertEqual(prepare_report(ok(started_at=NOW + timedelta(minutes=10)), NOW, yes)[1],
                         {'started_at': "The start time can't be in the future."})
        # A phone clock a little fast is not the future
        self.assertEqual(prepare_report(ok(started_at=NOW + timedelta(minutes=2)), NOW, yes)[1], {})

    def test_a_fire_report_needs_a_purok(self):
        self.assertEqual(prepare_report(ok(puroks=[]), NOW, yes)[1],
                         {'puroks': 'Choose the purok or sitio where the fire is.'})

    def test_puroks_must_be_in_the_barangay_and_at_most_ten(self):
        self.assertEqual(prepare_report(ok(puroks=[FakePurok(7, 8, SAMBAG.boundary)]), NOW, yes)[1],
                         {'puroks': 'That purok is not in Barangay San Roque.'})
        many = [FakePurok(i, 19, SAMBAG.boundary) for i in range(11)]
        self.assertEqual(prepare_report(ok(puroks=many), NOW, yes)[1], {'puroks': 'Choose at most 10 puroks.'})

    def test_duplicate_puroks_count_once(self):
        attrs, errors = prepare_report(ok(puroks=[SAMBAG, AGOHO, SAMBAG]), NOW, yes)
        self.assertEqual(errors, {})
        self.assertEqual([p.id for p in attrs['puroks']], [3, 6])

    def test_no_puroks_in_the_barangay_uses_its_centre(self):
        attrs, errors = prepare_report(ok(puroks=[]), NOW, no)
        self.assertEqual(errors, {})
        self.assertTrue(BRGY.boundary.contains(attrs['location']))

    def test_a_fire_report_needs_a_barangay(self):
        self.assertEqual(prepare_report(ok(barangay=None), NOW, yes)[1],
                         {'barangay': 'Choose the barangay where this is happening.'})

    def test_a_flood_or_landslide_needs_a_start_time_and_purok_too(self):
        self.assertEqual(prepare_report(ok(hazard_type=FLOOD, started_at=None, puroks=[]), NOW, yes)[1], {
            'started_at': 'Say when the flood started.',
            'puroks': 'Choose the purok or sitio where the flood is.',
        })
        self.assertEqual(prepare_report(ok(hazard_type=LANDSLIDE, started_at=NOW + timedelta(hours=1)), NOW, yes)[1],
                         {'started_at': "The start time can't be in the future."})

    def test_a_flood_keeps_its_own_pin_and_its_puroks(self):
        attrs, errors = prepare_report(
            ok(hazard_type=FLOOD, puroks=[AGOHO, AGOHO], location=Point(123.851, 10.251, srid=4326)), NOW, yes)
        self.assertEqual(errors, {})
        self.assertEqual(attrs['location'].x, 123.851)
        self.assertEqual(attrs['puroks'], [AGOHO])
        self.assertEqual(attrs['started_at'], NOW - timedelta(hours=1))

    def test_a_landslide_without_a_pin_is_placed_at_its_first_purok(self):
        attrs, errors = prepare_report(ok(hazard_type=LANDSLIDE, puroks=[AGOHO, SAMBAG]), NOW, yes)
        self.assertEqual(errors, {})
        self.assertTrue(AGOHO.boundary.contains(attrs['location']))

    def test_no_hazard_type_keeps_no_when_or_where(self):
        attrs, errors = prepare_report(ok(hazard_type=None), NOW, yes)
        self.assertEqual(errors, {})
        self.assertNotIn('started_at', attrs)
        self.assertNotIn('puroks', attrs)
