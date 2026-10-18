from django.core.cache import cache
from django.test import RequestFactory, SimpleTestCase, override_settings

from utils import map_version

LOCMEM = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache', 'LOCATION': 'map-version-tests'}}


@override_settings(CACHES=LOCMEM)
class MapVersionTests(SimpleTestCase):
    def setUp(self):
        cache.clear()
        self.rf = RequestFactory()

    def test_same_version_same_tag(self):
        req = self.rf.get('/api/hazards/')
        self.assertEqual(map_version.etag_for(req), map_version.etag_for(req))

    def test_change_gives_a_new_tag(self):
        req = self.rf.get('/api/hazards/')
        before = map_version.etag_for(req)
        map_version._bump_now()
        self.assertNotEqual(before, map_version.etag_for(req))

    def test_query_is_part_of_the_tag(self):
        a = map_version.etag_for(self.rf.get('/api/hazards/'))
        b = map_version.etag_for(self.rf.get('/api/hazards/', {'bbox': '1,2,3,4'}))
        self.assertNotEqual(a, b)

    def test_if_none_match(self):
        tag = map_version.etag_for(self.rf.get('/api/hazards/'))
        self.assertTrue(map_version.is_fresh(self.rf.get('/', HTTP_IF_NONE_MATCH=tag), tag))
        self.assertTrue(map_version.is_fresh(self.rf.get('/', HTTP_IF_NONE_MATCH=f'"x", W/{tag}'), tag))
        self.assertFalse(map_version.is_fresh(self.rf.get('/', HTTP_IF_NONE_MATCH='"other"'), tag))
        self.assertFalse(map_version.is_fresh(self.rf.get('/'), tag))
