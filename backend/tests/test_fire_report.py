"""
What a fire report must say: when it started, a pin inside the barangay, and
the purok (or the name typed when it is not on the list) - the BFP fire
log's columns A-F. Everything else is DRRMO's, entered when closing.
"""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from django.contrib.gis.geos import Point, Polygon
from django.test import SimpleTestCase

from apps.reports.fire_report import fire_report_errors


def square(x0, y0, x1, y1):
    return Polygon(((x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)), srid=4326)


class FakeBarangay:
    def __init__(self, id, name, boundary=None):
        self.id, self.name, self.boundary = id, name, boundary


class FakePurok:
    def __init__(self, barangay_id):
        self.barangay_id = barangay_id


BRGY = FakeBarangay(19, 'San Roque', square(123.85, 10.25, 123.86, 10.26))
NOW = datetime(2026, 10, 25, 14, 0, tzinfo=ZoneInfo('Asia/Manila'))


def ok(**kw):
    attrs = {'started_at': NOW - timedelta(hours=1), 'location': Point(123.855, 10.255, srid=4326),
             'purok': FakePurok(barangay_id=19), 'purok_other': ''}
    attrs.update(kw)
    return attrs


class FireReportErrorsTests(SimpleTestCase):
    def test_a_complete_fire_report_has_no_errors(self):
        self.assertEqual(fire_report_errors(ok(), BRGY, True, NOW), {})

    def test_start_time_is_required_and_not_in_the_future(self):
        self.assertEqual(fire_report_errors(ok(started_at=None), BRGY, True, NOW),
                         {'started_at': 'Say when the fire started.'})
        self.assertEqual(fire_report_errors(ok(started_at=NOW + timedelta(minutes=10)), BRGY, True, NOW),
                         {'started_at': "The start time can't be in the future."})
        # A phone clock a little fast is not the future
        self.assertEqual(fire_report_errors(ok(started_at=NOW + timedelta(minutes=2)), BRGY, True, NOW), {})

    def test_pin_is_required_and_inside_the_barangay(self):
        self.assertEqual(fire_report_errors(ok(location=None), BRGY, True, NOW),
                         {'location': 'Drop a pin where the fire is.'})
        self.assertEqual(fire_report_errors(ok(location=Point(123.90, 10.255, srid=4326)), BRGY, True, NOW),
                         {'location': 'The pin is outside Barangay San Roque.'})
        # The barangay lines are approximate: about 55 m over is accepted
        self.assertEqual(fire_report_errors(ok(location=Point(123.8605, 10.255, srid=4326)), BRGY, True, NOW), {})

    def test_purok_must_be_in_the_barangay(self):
        self.assertEqual(fire_report_errors(ok(purok=FakePurok(barangay_id=7)), BRGY, True, NOW),
                         {'purok': 'That purok is not in Barangay San Roque.'})

    def test_one_of_purok_or_a_typed_name(self):
        self.assertEqual(fire_report_errors(ok(purok=None), BRGY, True, NOW),
                         {'purok': "Choose the purok or sitio, or pick 'Not on the list' and type its name."})
        self.assertEqual(fire_report_errors(ok(purok_other='Purok Boongon'), BRGY, True, NOW),
                         {'purok': 'Choose a purok from the list or type one, not both.'})
        self.assertEqual(fire_report_errors(ok(purok=None, purok_other='Purok Boongon'), BRGY, True, NOW), {})

    def test_no_puroks_means_no_purok_needed(self):
        self.assertEqual(fire_report_errors(ok(purok=None), BRGY, False, NOW), {})
