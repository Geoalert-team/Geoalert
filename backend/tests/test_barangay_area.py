"""
Every barangay carries the region, province and city the BFP fire log files
a fire under (its columns C-E), and the API sends them wherever it sends the
barangay: the report form reads them from the barangay list, and a report's
barangay_details carries them. No database: the barangay is never saved.
"""
from django.test import SimpleTestCase

from apps.barangays.models import Barangay
from apps.barangays.serializers import BarangayGeoSerializer, BarangaySerializer
from apps.reports.serializers import IncidentReportSerializer


class BarangayAreaTests(SimpleTestCase):
    def test_a_new_barangay_is_in_talisay_city_cebu_region_vii(self):
        b = Barangay(name='Jaclupan')
        self.assertEqual(
            (b.region, b.province, b.municipality),
            ('Region VII (Central Visayas)', 'Cebu', 'Talisay City'),
        )

    def test_the_report_carries_them_with_its_barangay(self):
        data = BarangaySerializer(Barangay(id=7, name='Jaclupan')).data
        self.assertEqual(data['region'], 'Region VII (Central Visayas)')
        self.assertEqual(data['province'], 'Cebu')
        self.assertEqual(data['municipality'], 'Talisay City')
        self.assertIsInstance(IncidentReportSerializer().fields['barangay_details'], BarangaySerializer)

    def test_the_barangay_list_sends_them_to_the_form(self):
        for field in ('municipality', 'province', 'region'):
            self.assertIn(field, BarangayGeoSerializer.Meta.fields)
