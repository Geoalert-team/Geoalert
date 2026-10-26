"""
The create serializer hands fire reports to prepare_report and saves their
puroks. These pin the wiring without a database: the purok lookup, the city
outline and the clock are stand-ins.
"""
from datetime import datetime, timedelta
from unittest import mock
from zoneinfo import ZoneInfo

from django.contrib.gis.geos import Polygon
from django.http import QueryDict
from django.test import SimpleTestCase
from rest_framework import serializers

from apps.reports.serializers import IncidentReportCreateSerializer


def square(x0, y0, x1, y1):
    return Polygon(((x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)), srid=4326)


class Fake:
    def __init__(self, **kw):
        self.__dict__.update(kw)


NOW = datetime(2026, 10, 25, 14, 0, tzinfo=ZoneInfo('Asia/Manila'))
CITY = square(123.77, 10.22, 123.88, 10.35)
BRGY = Fake(id=19, name='San Roque', boundary=square(123.85, 10.25, 123.86, 10.26))
SAMBAG = Fake(id=3, barangay_id=19, boundary=square(123.85, 10.25, 123.855, 10.255))
AGOHO = Fake(id=6, barangay_id=19, boundary=square(123.855, 10.255, 123.86, 10.26))


def attrs(hazard='Fire', **kw):
    a = {'hazard_type': Fake(name=hazard), 'barangay': BRGY, 'description': 'Smoke from a house',
         'started_at': NOW - timedelta(hours=1), 'puroks': [SAMBAG, AGOHO]}
    a.update(kw)
    return a


class ValidateWiringTests(SimpleTestCase):
    def validate(self, data):
        with mock.patch('apps.reports.serializers.Purok') as purok, \
                mock.patch('apps.hazards.geometry.city_outline', return_value=CITY), \
                mock.patch('django.utils.timezone.now', return_value=NOW):
            purok.objects.filter.return_value.exists.return_value = True
            return IncidentReportCreateSerializer().validate(data)

    def test_multipart_sends_every_purok(self):
        field = IncidentReportCreateSerializer().fields['puroks']
        self.assertEqual(field.get_value(QueryDict('puroks=3&puroks=6')), ['3', '6'])

    def test_a_fire_report_ignores_the_client_pin_and_takes_its_first_purok(self):
        # A pin far outside the city would fail the city check; for a fire it is dropped
        out = self.validate(attrs(latitude=0.0, longitude=0.0))
        self.assertTrue(SAMBAG.boundary.contains(out['location']))
        self.assertNotIn('latitude', out)

    def test_a_fire_report_without_puroks_is_refused_under_puroks(self):
        with self.assertRaises(serializers.ValidationError) as caught:
            self.validate(attrs(puroks=[]))
        self.assertEqual(list(caught.exception.detail), ['puroks'])
        self.assertEqual(str(caught.exception.detail['puroks']), 'Choose the purok or sitio where the fire is.')

    def test_a_flood_keeps_its_pin_and_no_fire_fields(self):
        out = self.validate(attrs('Flood', latitude=10.251, longitude=123.851))
        self.assertAlmostEqual(out['location'].x, 123.851)
        self.assertNotIn('puroks', out)
        self.assertNotIn('started_at', out)


class CreateWiringTests(SimpleTestCase):
    def test_create_links_the_puroks_after_saving(self):
        report = mock.Mock()
        with mock.patch('rest_framework.serializers.ModelSerializer.create', return_value=report) as create:
            out = IncidentReportCreateSerializer().create({'description': 'x', 'photos': [], 'puroks': [SAMBAG, AGOHO]})
        self.assertIs(out, report)
        self.assertNotIn('puroks', create.call_args.args[0])  # not a model field: set after the save
        report.puroks.set.assert_called_once_with([SAMBAG, AGOHO])
