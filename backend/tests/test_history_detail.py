"""
GET /api/history/<id>/: one record in full, for the history page's details
window. Beside what the list sends, it carries the BFP fire log's columns
G-W, the exact location and the puroks. The list stays light. No database.
"""
from unittest import mock

from django.test import SimpleTestCase
from rest_framework.test import APIRequestFactory

from apps.history.serializers import HistoricalRecordDetailSerializer, HistoricalRecordSerializer
from apps.history.views import HistoricalRecordDetailView

BFP = [
    'property_category', 'property_subcategory',
    'injured_ff_male', 'injured_ff_female', 'injured_civ_male', 'injured_civ_female',
    'fatal_ff_male', 'fatal_ff_female', 'fatal_civ_male', 'fatal_civ_female',
    'damage_cost', 'structures_affected', 'alarm_level',
]


class HistoryDetailTests(SimpleTestCase):
    def test_the_detail_carries_the_bfp_columns_and_where(self):
        fields = HistoricalRecordDetailSerializer.Meta.fields
        for name in [*BFP, 'location_text', 'puroks', 'hazard_zone']:
            self.assertIn(name, fields)

    def test_the_list_stays_light(self):
        for name in BFP:
            self.assertNotIn(name, HistoricalRecordSerializer.Meta.fields)

    def test_the_view_answers_with_the_detail_serializer(self):
        request = APIRequestFactory().get('/api/history/x/')
        with mock.patch('apps.history.views.HistoricalRecord') as model, \
                mock.patch('apps.history.views.HistoricalRecordDetailSerializer') as serializer:
            record = model.objects.select_related.return_value.prefetch_related.return_value.get.return_value
            serializer.return_value.data = {'id': 'x'}
            response = HistoricalRecordDetailView.as_view()(request, pk='x')
        self.assertEqual(response.status_code, 200)
        serializer.assert_called_once_with(record)
