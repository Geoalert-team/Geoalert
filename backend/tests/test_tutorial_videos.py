"""
Tutorial videos (docs/superpowers/specs/2026-11-11-tutorial-videos-design.md):
the YouTube link reader, the two tables, and the /api/tutorials/ endpoints.
Against a real database; uploads go to a temporary folder; YouTube is mocked.
"""
import shutil
import tempfile
import time
import uuid
from unittest.mock import Mock, patch

import requests
from django.core.cache import cache
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.test import SimpleTestCase, TestCase, override_settings
from rest_framework import serializers as drf_serializers
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.accounts.models import Role, User
from apps.admin_dashboard.models import AuditLog
from apps.tutorials.models import TutorialVideo, VideoCategory, tutorial_video_path
from apps.tutorials.serializers import MAX_VIDEO_BYTES, validate_mp4
from apps.tutorials.views import (
    CategoryDetailView, CategoryListView, VideoDetailView, VideoListView, YouTubeCheckView,
)
from apps.tutorials.youtube import OEMBED_URL, lookup, parse_youtube_id

ID = '2v8vlXgGXwE'
ACCEPTED = [
    ID, f'https://www.youtube.com/watch?v={ID}', f'https://youtube.com/watch?v={ID}&t=42s',
    f'https://m.youtube.com/watch?v={ID}&list=PL123', f'https://www.youtube.com/watch?feature=share&v={ID}',
    f'https://youtu.be/{ID}', f'https://youtu.be/{ID}?si=abc', f'https://www.youtube.com/shorts/{ID}',
    f'https://www.youtube.com/embed/{ID}', f'https://www.youtube-nocookie.com/embed/{ID}',
    f'  www.youtube.com/watch?v={ID}  ', f'http://youtube.com/watch?v={ID}',
    f'HTTPS://WWW.YOUTUBE.COM/watch?v={ID}',
]
REFUSED = [
    None, '', '   ', 'https://vimeo.com/123456789', 'https://www.youtube.com/@TalisayDRRMO',
    'https://www.youtube.com/playlist?list=PL123', 'https://www.youtube.com/watch?v=short',
    'https://youtu.be/2v8vlXgGXw!', f'https://notyoutube.com/watch?v={ID}',
    f'https://youtube.com.evil.example/watch?v={ID}', ID + 'X',
]


class YouTubeLinkTests(SimpleTestCase):
    def test_every_accepted_link_form_gives_the_id(self):
        for text in ACCEPTED:
            with self.subTest(text=text):
                self.assertEqual(parse_youtube_id(text), ID)

    def test_other_links_give_none(self):
        for text in REFUSED:
            with self.subTest(text=text):
                self.assertIsNone(parse_youtube_id(text))


def answer(status, json=None, error=None):
    response = Mock(status_code=status)
    response.json.side_effect = error or (lambda: json)
    return response


class LookupTests(SimpleTestCase):
    @patch('apps.tutorials.youtube.requests.get')
    def test_a_found_video_gives_its_title(self, get):
        get.return_value = answer(200, {'title': '  How to treat a fracture '})
        self.assertEqual(lookup(ID), {'status': 'ok', 'title': 'How to treat a fracture'})
        get.assert_called_once_with(
            OEMBED_URL, params={'url': f'https://www.youtube.com/watch?v={ID}', 'format': 'json'}, timeout=5)

    @patch('apps.tutorials.youtube.requests.get')
    def test_deleted_private_or_unembeddable_is_not_found(self, get):
        for status in (400, 401, 403, 404):
            get.return_value = answer(status)
            self.assertEqual(lookup(ID), {'status': 'not_found'})

    @patch('apps.tutorials.youtube.requests.get')
    def test_no_answer_is_unchecked(self, get):
        for outcome in (answer(500), answer(429), answer(200, error=ValueError('not json')),
                        requests.Timeout(), requests.ConnectionError()):
            get.side_effect = outcome if isinstance(outcome, Exception) else None
            get.return_value = None if isinstance(outcome, Exception) else outcome
            self.assertEqual(lookup(ID), {'status': 'unchecked'})


SEED_IDS = ['gn6xt1ca8A0', 'ea1RJUOiNfQ', 'GmqXqwSV3bo', 'NxO5LvgqZe0', '2v8vlXgGXwE',
            'fKzdiuseEIw', 'PwfBGkBXkFA', '4e7evinsfm0', 'Uqy2IUhYkVA', '0jps5SZlTdo']


class TutorialModelTests(TestCase):
    def test_the_ten_first_aid_videos_are_seeded_in_order(self):
        first_aid = VideoCategory.objects.get(name='First Aid')
        videos = list(first_aid.videos.order_by('created_at'))
        self.assertEqual([v.youtube_id for v in videos], SEED_IDS)
        self.assertEqual(videos[0].title, 'How to use your first aid kit')
        self.assertTrue(all(v.source_type == 'youtube' and not v.file and v.description == '' for v in videos))

    def test_category_names_are_unique_ignoring_case(self):
        with transaction.atomic(), self.assertRaises(IntegrityError):
            VideoCategory.objects.create(name='first aid')

    def test_a_category_with_videos_cannot_be_deleted(self):
        with self.assertRaises(ProtectedError):
            VideoCategory.objects.get(name='First Aid').delete()

    def test_a_video_has_exactly_one_source(self):
        drills = VideoCategory.objects.create(name='Drills')
        for fields in ({'source_type': 'youtube', 'youtube_id': ''},
                       {'source_type': 'upload', 'youtube_id': ''},
                       {'source_type': 'upload', 'youtube_id': 'gn6xt1ca8A0', 'file': 'tutorials/x.mp4'},
                       {'source_type': 'youtube', 'youtube_id': 'gn6xt1ca8A0', 'file': 'tutorials/x.mp4'}):
            with self.subTest(fields=fields), transaction.atomic(), self.assertRaises(IntegrityError):
                TutorialVideo.objects.create(category=drills, title='T', **fields)

    def test_an_upload_is_named_after_the_video(self):
        video = TutorialVideo(title='T')
        self.assertRegex(tutorial_video_path(video, 'My Drill.final.MP4'),
                         rf'^tutorials/\d{{4}}/\d{{2}}/{video.id}\.mp4$')


MEDIA = tempfile.mkdtemp(prefix='geoalert-tutorials-')
LOCAL_FILES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
}
MP4_HEAD = b'\x00\x00\x00\x18ftypmp42'
# The public lists are cached: each test gets its own empty cache, never the
# file cache the dev server keeps its sessions in
LOCMEM = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache', 'LOCATION': 'tutorial-tests'}}


def mp4(name='drill.mp4', data=MP4_HEAD + b'\x00' * 64):
    return SimpleUploadedFile(name, data, content_type='application/octet-stream')


class Mp4CheckTests(SimpleTestCase):
    def refused(self, file):
        with self.assertRaises(drf_serializers.ValidationError) as caught:
            validate_mp4(file)
        return str(caught.exception.detail[0])

    def test_exactly_50_mb_passes_and_one_byte_more_does_not(self):
        self.assertEqual(MAX_VIDEO_BYTES, 52_428_800)
        validate_mp4(mp4(data=MP4_HEAD + b'\x00' * (MAX_VIDEO_BYTES - len(MP4_HEAD))))
        self.assertEqual(self.refused(mp4(data=MP4_HEAD + b'\x00' * (MAX_VIDEO_BYTES - len(MP4_HEAD) + 1))),
                         'That video is 50.0 MB. Please use one under 50 MB, or put it on YouTube.')

    def test_only_real_mp4s_pass(self):
        for file in (mp4('tiny.mp4', b'abc'), mp4('notes.mp4', b'just some text, not a video'),
                     mp4('drill.mov'), mp4('drill')):
            with self.subTest(name=file.name):
                self.assertEqual(self.refused(file), "That file isn't an MP4 video.")

    def test_an_upper_case_name_passes_and_is_stored_as_video(self):
        file = validate_mp4(mp4('FLOOD.MP4'))
        self.assertEqual(file.content_type, 'video/mp4')


@override_settings(MEDIA_ROOT=MEDIA, STORAGES=LOCAL_FILES, CACHES=LOCMEM)
class TutorialApiTestCase(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def setUp(self):
        cache.clear()

        def user(name, role):
            return User.objects.create_user(email=f'{name}@test.ph', password='x', full_name=name.title(),
                                            role=Role.objects.get_or_create(name=role)[0])
        self.officer = user('officer', 'DRRMO_Officer')
        self.admin = user('admin', 'System_Admin')
        self.bfp = user('fireofficer', 'BFP_Personnel')
        self.reporter = user('reporter', 'Barangay_Personnel')
        self.drills = VideoCategory.objects.create(name='Drills')
        self.factory = APIRequestFactory()

    def call(self, view, method, path, user=None, data=None, **kwargs):
        make = getattr(self.factory, method)
        if method == 'get':
            request = make(path, data)          # data becomes the query string
        elif method == 'delete':
            request = make(path)
        else:
            request = make(path, data or {}, format='multipart')
        if user:
            force_authenticate(request, user=user)
        return view.as_view()(request, **kwargs)

    def add(self, user=None, **data):
        data = {'category': str(self.drills.id), 'title': 'Flood drill', **data}
        return self.call(VideoListView, 'post', '/api/tutorials/', user or self.officer, data)

    def edit(self, video, user=None, **data):
        return self.call(VideoDetailView, 'patch', f'/api/tutorials/{video.pk}/', user or self.officer, data,
                         pk=video.pk)

    def remove(self, video, user=None):
        return self.call(VideoDetailView, 'delete', f'/api/tutorials/{video.pk}/', user or self.officer,
                         pk=video.pk)


class VideoApiTests(TutorialApiTestCase):
    def test_anyone_can_read_the_list_in_category_order(self):
        TutorialVideo.objects.create(category=self.drills, title='Drill', source_type='youtube',
                                     youtube_id='aaaaaaaaaaa')
        response = self.call(VideoListView, 'get', '/api/tutorials/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data[0]['category']['name'], 'Drills')   # D before F
        self.assertEqual(len(response.data), 11)
        first_aid = response.data[1]
        self.assertEqual((first_aid['youtube_id'], first_aid['file_url']), ('gn6xt1ca8A0', None))

    def test_only_drrmo_and_admins_can_write(self):
        video = TutorialVideo.objects.get(youtube_id='gn6xt1ca8A0')
        for user in (self.bfp, self.reporter):
            self.assertEqual(self.add(user, source_type='youtube', youtube_url=ID).status_code, 403)
            self.assertEqual(self.edit(video, user, title='X').status_code, 403)
            self.assertEqual(self.remove(video, user).status_code, 403)
        anonymous = self.call(VideoListView, 'post', '/api/tutorials/', None, {'title': 'X'})
        self.assertIn(anonymous.status_code, (401, 403))
        self.assertEqual(self.add(self.admin, source_type='youtube', youtube_url='https://youtu.be/bbbbbbbbbbb')
                         .status_code, 201)

    def test_a_youtube_video_keeps_only_the_id(self):
        response = self.add(source_type='youtube', youtube_url=f'https://youtu.be/{ID}?t=5', description='Step by step')
        self.assertEqual(response.status_code, 201, response.data)
        video = TutorialVideo.objects.get(pk=response.data['id'])
        self.assertEqual((video.youtube_id, video.file.name, video.created_by), (ID, '', self.officer))
        self.assertEqual(response.data['category'], {'id': str(self.drills.id), 'name': 'Drills'})
        self.assertTrue(AuditLog.objects.filter(action='ADD_VIDEO', details='"Flood drill"').exists())

    def test_bad_or_missing_youtube_links_are_refused(self):
        bad = self.add(source_type='youtube', youtube_url='https://vimeo.com/1')
        self.assertEqual(str(bad.data['youtube_url'][0]), "That isn't a YouTube video link.")
        missing = self.add(source_type='youtube')
        self.assertEqual(str(missing.data['youtube_url'][0]), 'Paste the YouTube link for this video.')

    def test_an_mp4_is_stored_with_its_size(self):
        response = self.add(source_type='upload', file=mp4('Flood Drill.MP4'))
        self.assertEqual(response.status_code, 201, response.data)
        video = TutorialVideo.objects.get(pk=response.data['id'])
        self.assertRegex(video.file.name, rf'^tutorials/\d{{4}}/\d{{2}}/{video.id}\.mp4$')
        self.assertEqual((video.file_size, video.youtube_id), (len(MP4_HEAD) + 64, ''))
        self.assertTrue(response.data['file_url'].startswith('http://testserver/'))
        self.assertIsNone(response.data['youtube_id'])
        missing = self.add(source_type='upload')
        self.assertEqual(str(missing.data['file'][0]), 'Choose the MP4 file for this video.')

    def test_title_category_and_description_are_checked(self):
        for data, field in (({'title': '   '}, 'title'), ({'title': 'x' * 121}, 'title'),
                            ({'description': 'x' * 501}, 'description'), ({'category': 'not-a-uuid'}, 'category')):
            response = self.add(source_type='youtube', youtube_url=ID, **data)
            self.assertEqual(response.status_code, 400)
            self.assertIn(field, response.data)

    def test_an_edit_switches_between_youtube_and_mp4_and_cleans_up_the_file(self):
        video = TutorialVideo.objects.get(pk=self.add(source_type='youtube', youtube_url=ID).data['id'])
        self.assertEqual(str(self.edit(video, source_type='upload').data['file'][0]),
                         'Choose the MP4 file for this video.')
        self.assertEqual(self.edit(video, source_type='upload', file=mp4()).status_code, 200)
        video.refresh_from_db()
        first_file = video.file.name
        self.assertEqual((video.source_type, video.youtube_id), ('upload', ''))
        self.assertEqual(self.edit(video, file=mp4('second.mp4')).status_code, 200)   # replace the file
        video.refresh_from_db()
        self.assertFalse(default_storage.exists(first_file))
        second_file = video.file.name
        self.assertEqual(self.edit(video, source_type='youtube', youtube_url=ID).status_code, 200)
        video.refresh_from_db()
        self.assertEqual((video.source_type, video.youtube_id, video.file.name, video.file_size),
                         ('youtube', ID, '', None))
        self.assertFalse(default_storage.exists(second_file))
        self.assertEqual(AuditLog.objects.filter(action='EDIT_VIDEO').count(), 3)

    def test_editing_the_title_keeps_the_file(self):
        video = TutorialVideo.objects.get(pk=self.add(source_type='upload', file=mp4()).data['id'])
        self.assertEqual(self.edit(video, title='Renamed').status_code, 200)
        video.refresh_from_db()
        self.assertTrue(default_storage.exists(video.file.name))

    def test_deleting_a_video_deletes_its_file(self):
        video = TutorialVideo.objects.get(pk=self.add(source_type='upload', file=mp4()).data['id'])
        name = video.file.name
        self.assertEqual(self.remove(video).status_code, 204)
        self.assertFalse(TutorialVideo.objects.filter(pk=video.pk).exists())
        self.assertFalse(default_storage.exists(name))
        self.assertTrue(AuditLog.objects.filter(action='DELETE_VIDEO', details='"Flood drill"').exists())

    def test_an_unknown_video_is_404(self):
        missing = TutorialVideo(pk=uuid.uuid4())
        self.assertEqual(self.edit(missing, title='X').status_code, 404)
        self.assertEqual(self.remove(missing).status_code, 404)


class CategoryApiTests(TutorialApiTestCase):
    def create(self, name, user=None):
        return self.call(CategoryListView, 'post', '/api/tutorials/categories/', user or self.officer, {'name': name})

    def rename(self, category, name, user=None):
        return self.call(CategoryDetailView, 'patch', f'/api/tutorials/categories/{category.pk}/',
                         user or self.officer, {'name': name}, pk=category.pk)

    def drop(self, category, user=None):
        return self.call(CategoryDetailView, 'delete', f'/api/tutorials/categories/{category.pk}/',
                         user or self.officer, pk=category.pk)

    def test_anyone_can_list_categories_a_to_z_with_counts(self):
        response = self.call(CategoryListView, 'get', '/api/tutorials/categories/')
        self.assertEqual([(c['name'], c['description'], c['video_count']) for c in response.data],
                         [('Drills', '', 0), ('First Aid', '', 10)])

    def test_a_description_is_saved_trimmed_and_listed(self):
        response = self.call(CategoryListView, 'post', '/api/tutorials/categories/', self.officer,
                             {'name': 'Typhoon Response', 'description': '  Before, during and after '})
        self.assertEqual((response.status_code, response.data['description']), (201, 'Before, during and after'))
        self.assertEqual(self.create('Earthquake Drills').data['description'], '')   # name only still works
        too_long = self.call(CategoryListView, 'post', '/api/tutorials/categories/', self.officer,
                             {'name': 'Long', 'description': 'x' * 301})
        self.assertEqual(too_long.status_code, 400)
        self.assertIn('description', too_long.data)
        edited = self.call(CategoryDetailView, 'patch', f'/api/tutorials/categories/{self.drills.pk}/', self.officer,
                           {'description': 'What each purok leader does'}, pk=self.drills.pk)
        self.assertEqual((edited.status_code, edited.data['name'], edited.data['description']),
                         (200, 'Drills', 'What each purok leader does'))
        self.assertTrue(AuditLog.objects.filter(action='RENAME_VIDEO_CATEGORY', details='"Drills" (description)').exists())
        listed = {c['name']: c['description'] for c in self.call(CategoryListView, 'get', '/api/tutorials/categories/').data}
        self.assertEqual(listed['Typhoon Response'], 'Before, during and after')

    def test_creating_trims_and_refuses_a_name_in_use(self):
        response = self.create('  Typhoon Response ')
        self.assertEqual((response.status_code, response.data['name']), (201, 'Typhoon Response'))
        self.assertTrue(AuditLog.objects.filter(action='ADD_VIDEO_CATEGORY', details='"Typhoon Response"').exists())
        taken = self.create('first aid')
        self.assertEqual(str(taken.data['name'][0]), 'There is already a category called First Aid.')
        for name in ('   ', 'x' * 61):
            self.assertEqual(self.create(name).status_code, 400)

    def test_renaming_checks_other_names_but_not_its_own(self):
        self.assertEqual(self.rename(self.drills, 'DRILLS').status_code, 200)
        self.assertTrue(AuditLog.objects.filter(action='RENAME_VIDEO_CATEGORY', details='"Drills" → "DRILLS"').exists())
        self.assertEqual(self.rename(self.drills, 'First aid').status_code, 400)

    def test_a_category_is_deleted_with_its_videos_and_files(self):
        upload = TutorialVideo.objects.get(pk=self.add(source_type='upload', file=mp4()).data['id'])
        self.add(source_type='youtube', youtube_url='https://youtu.be/bbbbbbbbbbb')
        name = upload.file.name
        self.assertTrue(default_storage.exists(name))
        with self.captureOnCommitCallbacks(execute=True):   # files go once the delete commits
            response = self.drop(self.drills)
        self.assertEqual(response.status_code, 204)
        self.assertFalse(VideoCategory.objects.filter(pk=self.drills.pk).exists())
        self.assertFalse(TutorialVideo.objects.filter(category_id=self.drills.pk).exists())
        self.assertFalse(default_storage.exists(name))
        self.assertTrue(AuditLog.objects.filter(action='DELETE_VIDEO_CATEGORY', details='"Drills" and 2 videos').exists())
        self.assertEqual(VideoCategory.objects.get(name='First Aid').videos.count(), 10)   # others untouched

    def test_an_unknown_category_is_404(self):
        self.assertEqual(self.drop(VideoCategory(pk=uuid.uuid4())).status_code, 404)

    def test_only_drrmo_and_admins_change_categories(self):
        for user in (self.bfp, self.reporter):
            self.assertEqual(self.create('New', user).status_code, 403)
            self.assertEqual(self.rename(self.drills, 'New', user).status_code, 403)
            self.assertEqual(self.drop(self.drills, user).status_code, 403)


class CachedListTests(TutorialApiTestCase):
    """
    The two public lists come from the cache while nothing changes, so a surge
    of residents before a typhoon doesn't queue on Supabase's 15 pooler
    connections.
    """
    def videos(self, **request_extra):
        return VideoListView.as_view()(self.factory.get('/api/tutorials/', **request_extra))

    def categories(self):
        return CategoryListView.as_view()(self.factory.get('/api/tutorials/categories/'))

    def test_a_repeat_read_makes_no_query(self):
        first_videos, first_categories = self.videos().data, self.categories().data
        with self.assertNumQueries(0):
            videos, categories = self.videos(), self.categories()
        self.assertEqual((videos.status_code, categories.status_code), (200, 200))
        self.assertEqual(len(videos.data), 10)
        self.assertEqual(videos.data, first_videos)
        self.assertEqual([(c['name'], c['video_count']) for c in categories.data],
                         [('Drills', 0), ('First Aid', 10)])
        self.assertEqual(categories.data, first_categories)

    def titles(self, category):
        return [v['title'] for v in self.videos().data if v['category']['name'] == category]

    def counts(self):
        return {c['name']: c['video_count'] for c in self.categories().data}

    def changed(self, write):
        # The lists are refreshed once the change commits, as on the live site
        with self.captureOnCommitCallbacks(execute=True):
            response = write()
        self.assertLess(response.status_code, 300, response.data)

    def test_every_change_shows_on_the_next_read(self):
        self.titles('Drills'), self.counts()   # both lists are now cached
        seeded = TutorialVideo.objects.get(youtube_id='gn6xt1ca8A0')

        self.changed(lambda: self.add(source_type='youtube', youtube_url=ID))
        self.assertEqual(self.titles('Drills'), ['Flood drill'])
        self.assertEqual(self.counts(), {'Drills': 1, 'First Aid': 10})

        self.changed(lambda: self.edit(seeded, title='Using your first aid kit'))
        self.assertEqual(self.titles('First Aid')[0], 'Using your first aid kit')

        self.changed(lambda: self.remove(seeded))
        self.assertNotIn('Using your first aid kit', self.titles('First Aid'))
        self.assertEqual(self.counts(), {'Drills': 1, 'First Aid': 9})

        self.changed(lambda: self.call(CategoryListView, 'post', '/api/tutorials/categories/', self.officer,
                                       {'name': 'Typhoon Response'}))
        self.assertEqual(self.counts(), {'Drills': 1, 'First Aid': 9, 'Typhoon Response': 0})

        # A video carries its category's name, so a rename refreshes the video list too
        self.changed(lambda: self.call(CategoryDetailView, 'patch', f'/api/tutorials/categories/{self.drills.pk}/',
                                       self.officer, {'name': 'Earthquake Drills'}, pk=self.drills.pk))
        self.assertEqual(self.titles('Earthquake Drills'), ['Flood drill'])

        self.changed(lambda: self.call(CategoryDetailView, 'delete', f'/api/tutorials/categories/{self.drills.pk}/',
                                       self.officer, pk=self.drills.pk))
        self.assertEqual(self.titles('Earthquake Drills'), [])
        self.assertEqual(self.counts(), {'First Aid': 9, 'Typhoon Response': 0})

    def test_a_change_this_server_never_hears_of_shows_within_a_minute(self):
        self.titles('First Aid')   # cached
        # A teammate's laptop shares the database but not this cache: update() sends no signal
        TutorialVideo.objects.filter(youtube_id='gn6xt1ca8A0').update(title='Changed on a laptop')
        self.assertNotIn('Changed on a laptop', self.titles('First Aid'))
        with patch('django.core.cache.backends.locmem.time.time', return_value=time.time() + 61):
            self.assertIn('Changed on a laptop', self.titles('First Aid'))

    def test_an_mp4_link_is_made_for_each_request(self):
        # On Supabase the link is signed for an hour, so a cached link would go dead
        self.changed(lambda: self.add(source_type='upload', file=mp4()))
        plain = [v['file_url'] for v in self.videos().data if v['file_url']]
        secure = [v['file_url'] for v in self.videos(secure=True).data if v['file_url']]   # from the cache
        self.assertRegex(plain[0], r'^http://testserver/media/tutorials/')
        self.assertRegex(secure[0], r'^https://testserver/media/tutorials/')

    def test_a_broken_cache_still_answers_from_the_database(self):
        broken = Mock(**{f'{name}.side_effect': OSError('No space left on device') for name in ('get', 'set', 'add')})
        with patch('apps.tutorials.list_cache.cache', broken):
            self.assertEqual(len(self.titles('First Aid')), 10)
            self.assertEqual(self.counts(), {'Drills': 0, 'First Aid': 10})
            self.changed(lambda: self.add(source_type='youtube', youtube_url=ID))   # a save still succeeds
            self.assertEqual(self.titles('Drills'), ['Flood drill'])


class YouTubeCheckTests(TutorialApiTestCase):
    def check(self, url, user=None):
        return self.call(YouTubeCheckView, 'get', '/api/tutorials/youtube-check/', user or self.officer, {'url': url})

    @patch('apps.tutorials.views.lookup', return_value={'status': 'ok', 'title': 'How to treat a fracture'})
    def test_a_saved_video_is_reported_as_a_duplicate(self, _lookup):
        response = self.check(f'https://youtu.be/{ID}')
        self.assertEqual(response.data, {'youtube_id': ID, 'status': 'ok',
                                         'title': 'How to treat a fracture', 'duplicate': 'First Aid'})

    @patch('apps.tutorials.views.lookup', return_value={'status': 'not_found'})
    def test_a_missing_video_has_no_title(self, _lookup):
        response = self.check('https://youtu.be/zzzzzzzzzzz')
        self.assertEqual(response.data, {'youtube_id': 'zzzzzzzzzzz', 'status': 'not_found',
                                         'title': None, 'duplicate': None})

    def test_a_bad_link_is_400_and_staff_only(self):
        response = self.check('https://vimeo.com/1')
        self.assertEqual((response.status_code, str(response.data['url'])),
                         (400, "That isn't a YouTube video link."))
        self.assertEqual(self.check(f'https://youtu.be/{ID}', self.bfp).status_code, 403)
