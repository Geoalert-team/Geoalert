"""
Deciding a fire report: where its pins go, the fire's shape for working out
who to alert, which active fires are close enough to attach to, and whether
it can still be decided. A fire's level is the highest fire model level
among its puroks, Moderate with the reason when any has none; other types
keep their puroks' history (purok_levels).
"""
import math
from datetime import datetime, timezone

from django.contrib.gis.geos import Point, Polygon
from django.test import SimpleTestCase

from apps.reports.decide import NO_MODEL_LEVEL, decision_error, fire_geometry, fire_level, is_nearby, report_pins


def square(x0, y0, x1, y1):
    return Polygon(((x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)), srid=4326)


class Fake:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class Puroks:
    def __init__(self, items):
        self.items = items

    def all(self):
        return self.items


A = Point(123.85, 10.25, srid=4326)
B = Point(123.86, 10.25, srid=4326)  # about 1.1 km east of A


class FireDecisionTests(SimpleTestCase):
    def test_pins_are_the_puroks_centres(self):
        sambag = Fake(boundary=square(123.85, 10.25, 123.855, 10.255))
        pins = report_pins(Fake(puroks=Puroks([sambag]), location=Point(1, 1, srid=4326)))
        self.assertEqual(len(pins), 1)
        self.assertTrue(sambag.boundary.contains(pins[0]))

    def test_pins_fall_back_to_the_report_location(self):
        self.assertEqual(report_pins(Fake(puroks=Puroks([]), location=A)), [A])
        self.assertEqual(report_pins(Fake(puroks=Puroks([]), location=None)), [])

    def test_fire_geometry_is_a_25_m_circle_per_pin(self):
        shape = fire_geometry([A, B])
        self.assertEqual(len(shape), 2)
        self.assertEqual(shape.srid, 4326)
        area = shape.transform(32651, clone=True).area
        self.assertAlmostEqual(area / (2 * math.pi * 25 ** 2), 1, delta=0.05)

    def test_nearby_is_within_500_m(self):
        shape = fire_geometry([A])
        self.assertTrue(is_nearby(shape, [Point(123.8536, 10.25, srid=4326)]))   # ~390 m
        self.assertFalse(is_nearby(shape, [Point(123.8565, 10.25, srid=4326)]))  # ~710 m

    def test_a_decided_report_cannot_be_decided_again(self):
        officer = Fake(full_name='Ana Cruz')
        at = datetime(2026, 10, 26, 0, 20, tzinfo=timezone.utc)  # 08:20 Manila
        fire = Fake(name='Fire')
        self.assertIsNone(decision_error(Fake(hazard_type=fire, status='Pending', hazard_zone_id=None)))
        # Validated under the old flow, never put on the map: can still be approved
        self.assertIsNone(decision_error(Fake(hazard_type=fire, status='Validated', hazard_zone_id=None)))
        self.assertEqual(
            decision_error(Fake(hazard_type=fire, status='Validated', hazard_zone_id='z',
                                reviewed_by=officer, reviewed_at=at)),
            'Already decided by Ana Cruz at 08:20.')
        self.assertEqual(
            decision_error(Fake(hazard_type=fire, status='Rejected', hazard_zone_id=None,
                                reviewed_by=officer, reviewed_at=at)),
            'Already decided by Ana Cruz at 08:20.')
        # Floods and landslides are pushed the same way as fires
        self.assertIsNone(decision_error(Fake(hazard_type=Fake(name='Flood'), status='Pending', hazard_zone_id=None)))


class FireLevelTests(SimpleTestCase):
    def test_highest_model_level(self):
        self.assertEqual(fire_level(['Green', 'Red', 'Orange']), ('Red', None))
        self.assertEqual(fire_level(['Green']), ('Green', None))

    def test_a_purok_without_a_level_gives_moderate_with_the_reason(self):
        self.assertEqual(fire_level(['Red', None]), ('Orange', NO_MODEL_LEVEL))
        self.assertEqual(fire_level([]), ('Orange', NO_MODEL_LEVEL))
        self.assertEqual(NO_MODEL_LEVEL, 'The fire model has no level for these puroks right now, so the level is Moderate.')
