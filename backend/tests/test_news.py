"""
The newsfeed: announcements DRRMO, admins and BFP post, edit and delete,
and the public feed that merges them with a post for each hazard alert
that went out. Against a real database; photos go to a temporary folder.
"""
import io
import shutil
import tempfile

from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from PIL import Image
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.accounts.models import Role, User
from apps.admin_dashboard.models import AuditLog
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
