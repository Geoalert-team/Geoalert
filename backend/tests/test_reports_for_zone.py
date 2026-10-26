"""
GET /api/reports/incidents/?hazard_zone=<id>: the barangay reports a zone
was published from (or joined), for the resolve form to show DRRMO what the
barangay sent. No database: the queryset and the user are stand-ins.
"""
import uuid
from unittest import mock

from django.test import SimpleTestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.reports.views import IncidentReportListCreateView


class FakeRole:
    name = 'DRRMO_Officer'


class FakeUser:
    is_authenticated = True
    is_active = True
    role = FakeRole()


def get(params):
    request = APIRequestFactory().get('/api/reports/incidents/', params)
    force_authenticate(request, user=FakeUser())
    with mock.patch('apps.reports.views.IncidentReport') as model, \
            mock.patch('apps.reports.views.IncidentReportSerializer') as serializer:
        reports = model.objects.all.return_value.select_related.return_value.prefetch_related.return_value
        reports.filter.return_value = reports
        serializer.return_value.data = []
        response = IncidentReportListCreateView.as_view()(request)
    return response, reports


class ReportsForZoneTests(SimpleTestCase):
    def test_narrows_to_the_zones_reports(self):
        zone = uuid.uuid4()
        response, reports = get({'hazard_zone': str(zone)})
        self.assertEqual(response.status_code, 200)
        reports.filter.assert_called_once_with(hazard_zone_id=zone)

    def test_a_malformed_id_is_refused_rather_than_ignored(self):
        response, reports = get({'hazard_zone': 'not-a-zone'})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data['hazard_zone'], 'Not a hazard zone id.')

    def test_without_it_nothing_is_narrowed(self):
        response, reports = get({})
        self.assertEqual(response.status_code, 200)
        reports.filter.assert_not_called()
