"""
Past hazards per purok and per area, for the map's purok colours, its
barangay panel and the History page's Purok filter. Real database: the
counting goes through historical_record_purok.
"""
from datetime import timedelta

from django.contrib.gis.geos import MultiPolygon
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.barangays.models import Purok
from apps.history.models import HistoricalRecord
from apps.history.purok_levels import purok_counts
from apps.history.views import AreaHistoryView, HistoricalRecordListView, PurokLevelsView
from tests.fire_setup import FireSetupMixin, box


def get(view, **params):
    return view.as_view()(APIRequestFactory().get('/', params))


class PurokCountTests(FireSetupMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.history(self.near, 3)
        self.history(self.far, 1)
        flood = HistoricalRecord.objects.create(barangay=self.home, hazard_type=self.flood, severity_level='Green',
                                                occurred_at=timezone.now() - timedelta(days=10))
        flood.puroks.add(self.near)
        untyped = HistoricalRecord.objects.create(barangay=self.home, hazard_type=None, severity_level='Green',
                                                  occurred_at=timezone.now())
        untyped.puroks.add(self.near)
        old = HistoricalRecord.objects.create(barangay=self.home, hazard_type=self.fire, severity_level='Green',
                                              occurred_at=timezone.now() - timedelta(days=365 * 6))
        old.puroks.add(self.near)

    def test_counts_per_purok_and_type_in_the_period(self):
        since = timezone.now() - timedelta(days=365 * 5)
        self.assertEqual(purok_counts(since), {(self.near.id, 'Fire'): 3, (self.near.id, 'Flood'): 1,
                                               (self.far.id, 'Fire'): 1})
        self.assertEqual(purok_counts(since, ['Flood']), {(self.near.id, 'Flood'): 1})
        self.assertEqual(purok_counts(None)[(self.near.id, 'Fire')], 4)

    def test_the_endpoint_gives_levels_and_leaves_out_zeros(self):
        data = get(PurokLevelsView, types='Fire').data
        self.assertEqual(data['thresholds'], {'years': 5, 'moderate': 3, 'extreme': 5})
        self.assertCountEqual(data['results'], [
            {'purok': self.near.id, 'type': 'Fire', 'count': 3, 'level': 'Orange'},
            {'purok': self.far.id, 'type': 'Fire', 'count': 1, 'level': 'Green'},
        ])
        self.assertEqual(get(PurokLevelsView, types='Volcano').data['results'], [])
        self.assertEqual(len(get(PurokLevelsView).data['results']), 3)


class RecordMixin(FireSetupMixin):
    def record(self, barangay, *puroks, hazard=None, **kw):
        fields = {'occurred_at': timezone.now() - timedelta(days=20), **kw}
        r = HistoricalRecord.objects.create(barangay=barangay, hazard_type=hazard or self.fire, severity_level='Green',
                                            **fields)
        r.puroks.set(puroks)
        return r


class AreaHistoryTests(RecordMixin, TestCase):
    def area(self, user=None, **params):
        request = APIRequestFactory().get('/', params)
        if user:
            force_authenticate(request, user=user)
        return AreaHistoryView.as_view()(request)

    def test_barangay_view_lists_puroks_unplaced_and_events(self):
        self.history(self.near, 3)
        self.record(self.home)                                   # no purok
        self.record(self.home, self.near, hazard=self.flood)     # another type
        data = self.area(barangay=self.home.id, types='Fire').data
        self.assertEqual((data['count'], data['unplaced'], data['level'], data['purok']), (4, 1, 'Orange', None))
        self.assertEqual(data['puroks'], [{'id': self.near.id, 'name': 'Purok Near', 'parent': '',
                                           'count': 3, 'level': 'Orange'}])
        self.assertEqual(len(data['events']), 4)
        self.assertNotIn('location_text', data['events'][0])

    def test_types_are_counted_on_their_own(self):
        self.history(self.near, 2)
        self.record(self.home, self.near, hazard=self.flood)
        self.record(self.home, self.near, hazard=self.flood)
        data = self.area(barangay=self.home.id, types='Fire,Flood').data
        self.assertEqual((data['count'], data['puroks'][0]['level']), (4, 'Green'))

    def test_purok_view_and_none_view(self):
        self.history(self.near, 2)
        self.record(self.home)
        purok = self.area(barangay=self.home.id, purok=self.near.id).data
        self.assertEqual((purok['count'], purok['level'], purok['puroks'], purok['unplaced']), (2, 'Green', [], 0))
        self.assertEqual(purok['purok'], {'id': self.near.id, 'name': 'Purok Near', 'parent': ''})
        none = self.area(barangay=self.home.id, purok='none').data
        self.assertEqual((none['count'], none['level'], none['purok']['name']), (1, None, 'Purok not recorded'))

    def test_a_record_in_two_puroks_counts_once_for_the_barangay(self):
        other = Purok.objects.create(barangay=self.home, name='Purok Other', kind='purok', source='estimated',
                                     boundary=MultiPolygon(box(200, 200, 300, 300), srid=4326))
        self.record(self.home, self.near, other)
        data = self.area(barangay=self.home.id).data
        self.assertEqual(data['count'], 1)
        self.assertEqual(sorted(p['count'] for p in data['puroks']), [1, 1])

    def test_a_record_linked_across_a_border_shows_in_both_barangays(self):
        self.record(self.home, self.far)
        self.assertEqual(self.area(barangay=self.home.id).data['count'], 1)
        self.assertEqual(self.area(barangay=self.next.id).data['count'], 1)
        self.assertEqual(self.area(barangay=self.next.id).data['puroks'][0]['count'], 1)

    def test_period_all_reaches_past_the_period(self):
        self.record(self.home, self.near, occurred_at=timezone.now() - timedelta(days=365 * 7))
        self.assertEqual(self.area(barangay=self.home.id).data['count'], 0)
        self.assertEqual(self.area(barangay=self.home.id, period='all').data['count'], 1)

    def test_staff_see_where_and_damage(self):
        self.record(self.home, self.near, location_text='SAMBAG, BRGY HOME', damage_cost='1500.00')
        event = self.area(self.officer, barangay=self.home.id).data['events'][0]
        self.assertEqual((event['location_text'], event['damage_cost']), ('SAMBAG, BRGY HOME', '1500.00'))

    def test_bad_purok_is_a_400(self):
        self.assertEqual(self.area(barangay=self.home.id, purok='abc').data,
                         {'error': 'purok must be an id or "none".'})
        response = self.area(barangay=self.home.id, purok=self.far.id)
        self.assertEqual((response.status_code, response.data['error']), (400, 'That purok is not in Barangay Home.'))
        self.assertEqual(self.area(barangay='x').status_code, 400)
        self.assertEqual(self.area(barangay=99999).status_code, 404)


class HistoryListPurokTests(RecordMixin, TestCase):
    def listed(self, **params):
        return get(HistoricalRecordListView, **params)

    def test_barangay_rule_counts_each_record_once(self):
        other = Purok.objects.create(barangay=self.home, name='Purok Other', kind='purok', source='estimated',
                                     boundary=MultiPolygon(box(200, 200, 300, 300), srid=4326))
        self.record(self.home, self.near, other)
        self.record(self.next, self.near)        # filed next door, linked to a Home purok
        self.assertEqual(len(self.listed(barangay=self.home.id).data), 2)
        page = self.listed(barangay=self.home.id, limit=5).data
        self.assertEqual((page['count'], page['type_counts']), (2, [{'name': 'Fire', 'count': 2}]))

    def test_purok_filter(self):
        self.history(self.near, 2)
        self.record(self.home)
        self.assertEqual(len(self.listed(barangay=self.home.id, purok=self.near.id).data), 2)
        self.assertEqual(len(self.listed(barangay=self.home.id, purok='none').data), 1)

    def test_purok_filter_needs_a_barangay_and_an_id(self):
        self.assertEqual(self.listed(purok='none').data, {'error': 'purok needs a barangay.'})
        self.assertEqual(self.listed(barangay=self.home.id, purok='abc').status_code, 400)
