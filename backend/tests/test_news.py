"""
The newsfeed: announcements DRRMO, admins and BFP post, edit and delete,
and the public feed that merges them with a post for each hazard alert
that went out. Against a real database; photos go to a temporary folder.
"""
import io
import shutil
import tempfile
from datetime import timedelta

from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from PIL import Image
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.accounts.models import Role, User
from apps.admin_dashboard.models import AuditLog
from apps.hazards.models import HazardAlert
from apps.news.models import Announcement
from apps.news.views import NewsDetailView, NewsListView
from tests.fire_setup import FireSetupMixin

MEDIA = tempfile.mkdtemp(prefix='geoalert-news-')
LOCAL_FILES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
}


def image_file(name='photo.png', fmt='PNG'):
    out = io.BytesIO()
    Image.new('RGB', (1, 1), 'red').save(out, fmt)
    return SimpleUploadedFile(name, out.getvalue(), content_type=f'image/{fmt.lower()}')


@override_settings(MEDIA_ROOT=MEDIA, STORAGES=LOCAL_FILES)
class NewsTestCase(FireSetupMixin, TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def setUp(self):
        super().setUp()
        bfp = Role.objects.get_or_create(name='BFP_Personnel')[0]
        admin = Role.objects.get_or_create(name='System_Admin')[0]
        make = lambda name, role: User.objects.create_user(email=f'{name}@test.ph', password='x',
                                                          full_name=name.title(), role=role)
        self.bfp = make('fireofficer', bfp)
        self.other_bfp = make('otherofficer', bfp)
        self.admin = make('admin', admin)

    def post(self, user, data):
        request = APIRequestFactory().post('/api/news/', data, format='multipart')
        if user:
            force_authenticate(request, user=user)
        return NewsListView.as_view()(request)

    def patch(self, user, pk, data):
        request = APIRequestFactory().patch(f'/api/news/{pk}/', data, format='multipart')
        force_authenticate(request, user=user)
        return NewsDetailView.as_view()(request, pk=pk)

    def delete(self, user, pk):
        request = APIRequestFactory().delete(f'/api/news/{pk}/')
        force_authenticate(request, user=user)
        return NewsDetailView.as_view()(request, pk=pk)

    def announce(self, user, **data):
        response = self.post(user, {'title': 'Typhoon advisory', 'body': 'Stay indoors.', **data})
        self.assertEqual(response.status_code, 201, response.data)
        return Announcement.objects.get(pk=response.data['id'])


class NewsWriteTests(NewsTestCase):
    def test_drrmo_posts_as_drrmo(self):
        post = self.announce(self.officer)
        self.assertEqual((post.source, post.created_by, post.title), ('DRRMO', self.officer, 'Typhoon advisory'))
        self.assertTrue(AuditLog.objects.filter(action='POST_NEWS', user=self.officer).exists())

    def test_bfp_posts_as_bfp_and_admin_as_drrmo(self):
        self.assertEqual(self.announce(self.bfp).source, 'BFP')
        self.assertEqual(self.announce(self.admin).source, 'DRRMO')

    def test_barangay_personnel_and_anonymous_cannot_post(self):
        self.assertEqual(self.post(self.reporter, {'title': 'Hi', 'body': 'There'}).status_code, 403)
        self.assertIn(self.post(None, {'title': 'Hi', 'body': 'There'}).status_code, (401, 403))
        self.assertFalse(Announcement.objects.exists())

    def test_title_and_text_are_required_and_bounded(self):
        for data, field in (({'title': '  ', 'body': 'Text'}, 'title'),
                            ({'title': 'x' * 151, 'body': 'Text'}, 'title'),
                            ({'title': 'Title', 'body': 'x' * 5001}, 'body')):
            response = self.post(self.officer, data)
            self.assertEqual(response.status_code, 400)
            self.assertIn(field, response.data)
        self.assertFalse(Announcement.objects.exists())

    def test_photo_must_be_a_jpeg_png_or_webp_image(self):
        text = SimpleUploadedFile('notes.txt', b'not an image', content_type='text/plain')
        self.assertIn('photo', self.post(self.officer, {'title': 'T', 'body': 'B', 'photo': text}).data)
        gif = image_file('anim.gif', 'GIF')
        response = self.post(self.officer, {'title': 'T', 'body': 'B', 'photo': gif})
        self.assertEqual(response.status_code, 400)
        self.assertIn('photo', response.data)
        post = self.announce(self.officer, photo=image_file())
        self.assertTrue(post.photo.name.startswith('news/'))
        self.assertTrue(post.photo.name.endswith('.png'))

    def test_bfp_edits_own_post_but_not_drrmos(self):
        own = self.announce(self.bfp)
        self.assertEqual(self.patch(self.bfp, own.pk, {'title': 'Fire safety week'}).status_code, 200)
        own.refresh_from_db()
        self.assertEqual(own.title, 'Fire safety week')
        self.assertTrue(AuditLog.objects.filter(action='EDIT_NEWS', user=self.bfp).exists())
        drrmos = self.announce(self.officer)
        self.assertEqual(self.patch(self.bfp, drrmos.pk, {'title': 'Changed'}).status_code, 403)

    def test_drrmo_edits_and_deletes_a_bfp_post(self):
        theirs = self.announce(self.bfp)
        self.assertEqual(self.patch(self.officer, theirs.pk, {'body': 'Corrected.'}).status_code, 200)
        self.assertEqual(self.delete(self.other_bfp, theirs.pk).status_code, 403)
        self.assertEqual(self.delete(self.officer, theirs.pk).status_code, 204)
        self.assertFalse(Announcement.objects.filter(pk=theirs.pk).exists())
        self.assertTrue(AuditLog.objects.filter(action='DELETE_NEWS', user=self.officer).exists())

    def test_an_unknown_post_is_404(self):
        import uuid
        self.assertEqual(self.patch(self.officer, uuid.uuid4(), {'title': 'X'}).status_code, 404)

    def test_editing_the_title_keeps_the_photo(self):
        post = self.announce(self.officer, photo=image_file())
        name = post.photo.name
        self.assertEqual(self.patch(self.officer, post.pk, {'title': 'New'}).status_code, 200)
        post.refresh_from_db()
        self.assertEqual(post.photo.name, name)
        self.assertTrue(default_storage.exists(name))

    def test_removing_or_replacing_a_photo_deletes_its_file(self):
        post = self.announce(self.officer, photo=image_file())
        first = post.photo.name
        self.assertEqual(self.patch(self.officer, post.pk, {'photo': image_file('new.png')}).status_code, 200)
        post.refresh_from_db()
        self.assertNotEqual(post.photo.name, first)
        self.assertFalse(default_storage.exists(first))
        second = post.photo.name
        self.assertEqual(self.patch(self.officer, post.pk, {'remove_photo': 'true'}).status_code, 200)
        post.refresh_from_db()
        self.assertFalse(post.photo)
        self.assertFalse(default_storage.exists(second))

        gone = self.announce(self.officer, photo=image_file())
        name = gone.photo.name
        self.delete(self.officer, gone.pk)
        self.assertFalse(default_storage.exists(name))


class NewsFeedTests(NewsTestCase):
    def feed(self, user=None, **params):
        request = APIRequestFactory().get('/api/news/', params)
        if user:
            force_authenticate(request, user=user)
        return NewsListView.as_view()(request)

    def ago(self, minutes):
        return timezone.now() - timedelta(minutes=minutes)

    def went_out(self, zone, minutes_ago, severity=None):
        alert = HazardAlert.objects.create(hazard_zone=zone, issued_by=self.officer, hazard_type=zone.hazard_type,
                                           severity=severity or zone.severity)
        HazardAlert.objects.filter(pk=alert.pk).update(created_at=self.ago(minutes_ago))
        return HazardAlert.objects.get(pk=alert.pk)

    def posted(self, user, minutes_ago, **data):
        post = self.announce(user, **data)
        Announcement.objects.filter(pk=post.pk).update(created_at=self.ago(minutes_ago),
                                                       updated_at=self.ago(minutes_ago))
        return Announcement.objects.get(pk=post.pk)

    def alerts(self, response):
        return [r for r in response.data['results'] if r['kind'] == 'alert']

    def test_public_newest_first_mixing_both(self):
        old = self.posted(self.officer, 120)
        zone = self.zone(self.near)
        self.went_out(zone, 60)
        new = self.posted(self.bfp, 0)
        results = self.feed().data['results']
        self.assertEqual([(r['kind'], r['id']) for r in results],
                         [('announcement', str(new.id)), ('alert', str(zone.id)), ('announcement', str(old.id))])

    def test_alert_post_shows_the_zone(self):
        zone = self.zone(self.near)
        self.report(self.near, hazard_zone=zone, status='Validated')
        first = self.went_out(zone, 30)
        self.went_out(zone, 10)
        [post] = self.alerts(self.feed())
        self.assertEqual(
            {k: post[k] for k in ('hazard_type', 'severity', 'barangay', 'puroks', 'status', 'map_link')},
            {'hazard_type': 'Fire', 'severity': 'Orange', 'barangay': 'Home', 'puroks': ['Purok Near'],
             'status': 'active', 'map_link': f'/map?zone={zone.id}'})
        self.assertEqual(parse_datetime(post['published_at']), first.created_at)

    def test_a_raised_zone_is_one_post(self):
        zone = self.zone(self.near, severity='Red')
        first = self.went_out(zone, 30, severity='Orange')
        self.went_out(zone, 10, severity='Red')
        posts = self.alerts(self.feed())
        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0]['severity'], 'Red')
        self.assertEqual(parse_datetime(posts[0]['published_at']), first.created_at)

    def test_a_resolved_zone_shows_resolved_without_a_map_link(self):
        zone = self.zone(self.near, status='Resolved')
        self.went_out(zone, 30)
        [post] = self.alerts(self.feed())
        self.assertEqual((post['status'], post['map_link']), ('resolved', None))

    def test_sample_withdrawn_and_held_zones_are_left_out(self):
        self.went_out(self.zone(self.near, is_sample=True), 30)
        self.went_out(self.zone(self.near, status='Retracted'), 20)
        self.zone(self.near, status='Awaiting_Approval', severity='Red')  # held: no alert went out
        self.assertEqual(self.alerts(self.feed()), [])

    def test_paging_with_before(self):
        for minutes in (30, 20, 10):
            self.posted(self.officer, minutes)
        first = self.feed(limit=2).data
        self.assertEqual(len(first['results']), 2)
        self.assertIsNotNone(first['next_before'])
        second = self.feed(limit=2, before=first['next_before']).data
        self.assertEqual(len(second['results']), 1)
        self.assertIsNone(second['next_before'])

    def test_bad_paging_values(self):
        self.assertIn('before', self.feed(before='yesterday').data)
        self.assertEqual(self.feed(before='yesterday').status_code, 400)
        self.assertIn('limit', self.feed(limit='abc').data)
        # Python takes offsets to ±23:59 and PostgreSQL only to ±15:59: such a time is
        # served in UTC, not a 500; a date that overflows in UTC is refused
        for odd in ('2026-11-04T08:00:00+20:00', '2026-11-04T08:00:00-23:00'):
            self.assertEqual(self.feed(before=odd).status_code, 200, odd)
        self.assertIn('before', self.feed(before='0001-01-01T00:30:00+01:00').data)
        Announcement.objects.bulk_create([Announcement(title=f'Post {i}', body='Text', source='DRRMO')
                                          for i in range(31)])
        self.assertEqual(len(self.feed(limit=99).data['results']), 30)

    def test_can_edit_follows_who_is_asking(self):
        bfps = self.posted(self.bfp, 20)
        drrmos = self.posted(self.officer, 10)
        can = lambda user: {r['id']: r['can_edit'] for r in self.feed(user).data['results']}
        self.assertEqual(can(None), {str(bfps.id): False, str(drrmos.id): False})
        self.assertEqual(can(self.bfp), {str(bfps.id): True, str(drrmos.id): False})
        self.assertEqual(can(self.other_bfp), {str(bfps.id): False, str(drrmos.id): False})
        self.assertEqual(can(self.officer), {str(bfps.id): True, str(drrmos.id): True})

    def test_a_post_outlives_its_authors_account(self):
        post = self.posted(self.bfp, 10)
        self.bfp.delete()
        [row] = self.feed(self.officer).data['results']
        self.assertEqual((row['id'], row['source'], row['can_edit']), (str(post.id), 'BFP', True))

    def test_announcement_post_shape(self):
        post = self.posted(self.officer, 5, photo=image_file())
        [row] = self.feed().data['results']
        self.assertEqual({k: row[k] for k in ('kind', 'title', 'body', 'source', 'edited_at')},
                         {'kind': 'announcement', 'title': 'Typhoon advisory', 'body': 'Stay indoors.',
                          'source': 'DRRMO', 'edited_at': None})
        self.assertTrue(row['photo_url'].startswith('http'))
        self.patch(self.officer, post.pk, {'title': 'Typhoon advisory (updated)'})
        [row] = self.feed().data['results']
        self.assertIsNotNone(row['edited_at'])
