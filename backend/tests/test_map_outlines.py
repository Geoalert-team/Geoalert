"""
The map's heaviest data. Outlines are read from the database only when
something draws them, and the purok layer is rebuilt only when it has changed.
"""
import gzip
import json
from datetime import timedelta

from django.conf import settings
from django.contrib.gis.geos import MultiPolygon, Polygon
from django.core.cache import cache
from django.db import connection, transaction
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient

from apps.barangays.models import Barangay, Purok
from apps.hazards.models import HazardType
from apps.history.models import HistoricalRecord

OWN_CACHE = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache', 'LOCATION': 'map-outlines'}}
HOME = 'Outline Test Home'


def square():
    ring = ((123.80, 10.20), (123.81, 10.20), (123.81, 10.21), (123.80, 10.21), (123.80, 10.20))
    return MultiPolygon(Polygon(ring, srid=4326), srid=4326)


def fetched(queries, column):
    """Whether a query brought this geometry column back (filtering on it costs nothing to send)."""
    return any(f'"{column}"::bytea' in q['sql'] for q in queries)


@override_settings(CACHES=OWN_CACHE)
class PurokLayerCacheTests(TestCase):
    URL = '/api/barangays/puroks/'

    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.home = Barangay.objects.create(name=HOME, boundary=square())
        self.purok = Purok.objects.create(barangay=self.home, name='Purok Sambag', kind='purok',
                                          source='estimated', boundary=square())

    def feature(self, response, purok_id=None):
        wanted = purok_id or self.purok.id
        return next(f for f in response.json()['features'] if f['id'] == wanted)

    # A real change commits in its own transaction, which is what gives its
    # rows a new xmin. Inside a test a savepoint stands in for that.
    def committed(self, change):
        with transaction.atomic():
            change()

    def test_the_second_load_reads_no_outlines(self):
        first = self.client.get(self.URL)
        with CaptureQueriesContext(connection) as queries:
            second = self.client.get(self.URL)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.json(), first.json())
        self.assertEqual(len(queries), 1)
        self.assertFalse(fetched(queries, 'prk_boundary'))

    def test_building_it_leaves_out_the_barangay_outlines(self):
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(self.URL)
        self.assertEqual(self.feature(response)['properties']['barangay_name'], HOME)
        self.assertTrue(fetched(queries, 'prk_boundary'))
        self.assertFalse(fetched(queries, 'brgy_boundary'))

    def test_an_edited_purok_shows_at_once(self):
        self.client.get(self.URL)
        self.committed(lambda: Purok.objects.filter(pk=self.purok.pk).update(name='Purok Lubi'))
        self.assertEqual(self.feature(self.client.get(self.URL))['properties']['name'], 'Purok Lubi')

    def test_puroks_added_and_removed_in_bulk_show_at_once(self):
        """load_puroks writes in bulk, which no save signal sees."""
        self.client.get(self.URL)
        self.committed(lambda: Purok.objects.bulk_create([
            Purok(barangay=self.home, name='Purok New', kind='purok', source='official', boundary=square()),
        ]))
        names = [f['properties']['name'] for f in self.client.get(self.URL).json()['features']]
        self.assertIn('Purok New', names)

        self.committed(lambda: Purok.objects.filter(name='Purok New').delete())
        names = [f['properties']['name'] for f in self.client.get(self.URL).json()['features']]
        self.assertNotIn('Purok New', names)

    def test_a_renamed_barangay_shows_at_once(self):
        self.client.get(self.URL)
        self.committed(lambda: Barangay.objects.filter(pk=self.home.pk).update(name='Outline Test Renamed'))
        self.assertEqual(self.feature(self.client.get(self.URL))['properties']['barangay_name'], 'Outline Test Renamed')

    def test_a_browser_with_the_current_copy_downloads_nothing(self):
        etag = self.client.get(self.URL)['ETag']
        again = self.client.get(self.URL, HTTP_IF_NONE_MATCH=etag)
        self.assertEqual(again.status_code, 304)
        self.assertEqual(again.content, b'')
        # Nginx marks the tag as weak when it compresses the answer
        self.assertEqual(self.client.get(self.URL, HTTP_IF_NONE_MATCH=f'W/{etag}').status_code, 304)

    def test_a_compressed_answer_still_gets_the_short_reply_next_time(self):
        gzip_first = ['django.middleware.gzip.GZipMiddleware', *settings.MIDDLEWARE]
        with override_settings(MIDDLEWARE=gzip_first):
            first = self.client.get(self.URL, HTTP_ACCEPT_ENCODING='gzip')
            self.assertEqual(first['Content-Encoding'], 'gzip')
            self.assertIn('Purok Sambag', [f['properties']['name'] for f in json.loads(gzip.decompress(first.content))['features']])
            again = self.client.get(self.URL, HTTP_IF_NONE_MATCH=first['ETag'], HTTP_ACCEPT_ENCODING='gzip')
        self.assertEqual(again.status_code, 304)

    def test_a_browser_with_an_old_copy_gets_the_new_one(self):
        etag = self.client.get(self.URL)['ETag']
        self.committed(lambda: Purok.objects.filter(pk=self.purok.pk).update(name='Purok Lubi'))
        fresh = self.client.get(self.URL, HTTP_IF_NONE_MATCH=etag)
        self.assertEqual(fresh.status_code, 200)
        self.assertNotEqual(fresh['ETag'], etag)
        self.assertEqual(self.feature(fresh)['properties']['name'], 'Purok Lubi')


class HistoryLeavesOutOutlinesTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.home = Barangay.objects.create(name=HOME, boundary=square())
        purok = Purok.objects.create(barangay=self.home, name='Purok Sambag', kind='purok',
                                     source='estimated', boundary=square())
        fire, _ = HazardType.objects.get_or_create(name='Fire', defaults={'logo_class': 'fire-icon'})
        for days in (1, 2):
            record = HistoricalRecord.objects.create(barangay=self.home, hazard_type=fire, severity_level='Green',
                                                     occurred_at=timezone.now() - timedelta(days=days))
            record.puroks.add(purok)

    def test_the_list_never_fetches_a_barangay_outline(self):
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get('/api/history/')
        self.assertEqual({r['barangay_detail']['name'] for r in response.json()}, {HOME})
        self.assertFalse(fetched(queries, 'brgy_boundary'))
        self.assertEqual(len(queries), 1)  # and nothing goes back for it row by row

    def test_a_barangay_panel_never_fetches_a_purok_outline(self):
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get('/api/history/area/', {'barangay': self.home.id, 'period': 'all'})
        self.assertEqual(response.json()['events'][0]['puroks'], ['Purok Sambag'])
        self.assertFalse(fetched(queries, 'prk_boundary'))
