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


@override_settings(CACHES=LOCMEM)
class CachedBodyTests(SimpleTestCase):
    """The map GeoJSON is built once per version, not once per open map."""

    def setUp(self):
        cache.clear()
        self.rf = RequestFactory()
        self.builds = 0

    def build(self):
        self.builds += 1
        return {'type': 'FeatureCollection', 'features': [], 'build': self.builds}

    def test_same_tag_builds_once(self):
        tag = map_version.etag_for(self.rf.get('/api/hazards/'))
        first = map_version.cached_body(tag, self.build)
        second = map_version.cached_body(tag, self.build)
        self.assertEqual(self.builds, 1)
        self.assertEqual(first, second)

    def test_a_change_builds_again(self):
        req = self.rf.get('/api/hazards/')
        map_version.cached_body(map_version.etag_for(req), self.build)
        map_version._bump_now()
        body = map_version.cached_body(map_version.etag_for(req), self.build)
        self.assertEqual(self.builds, 2)
        self.assertEqual(body['build'], 2)

    def test_each_query_has_its_own_copy(self):
        a = map_version.etag_for(self.rf.get('/api/hazards/'))
        b = map_version.etag_for(self.rf.get('/api/hazards/', {'bbox': '1,2,3,4'}))
        map_version.cached_body(a, self.build)
        map_version.cached_body(b, self.build)
        self.assertEqual(self.builds, 2)

    def test_broken_cache_still_answers(self):
        from unittest import mock

        with mock.patch.object(map_version.cache, 'get', side_effect=RuntimeError('down')), \
                mock.patch.object(map_version.cache, 'set', side_effect=RuntimeError('down')):
            body = map_version.cached_body('"tag"', self.build)
        self.assertEqual(body['build'], 1)
