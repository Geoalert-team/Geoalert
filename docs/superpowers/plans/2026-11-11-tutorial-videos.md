# Tutorial Videos Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** DRRMO officers and admins add, edit and delete tutorial videos (YouTube links and MP4 uploads, mixed in one batch, grouped by category) directly on the public What To Do page, replacing the hardcoded first aid list.

**Architecture:** A new Django app `apps/tutorials` (two tables, a YouTube link reader, a REST API at `/api/tutorials/`) stores videos; MP4s go to the existing storage (Supabase bucket or local disk) exactly as news photos do. On the frontend, the What To Do page's videos section moves into `components/Tutorials/TutorialVideos.jsx`, which plays videos for everyone and, for `canPublish` users, opens an in-place batch form (`AddVideosForm.jsx`) whose row logic lives in a pure module (`videoRows.js`).

**Tech Stack:** Django 4.2 + DRF 3.15, `requests` (already installed), django-storages; React 18 (react-scripts, Jest, `createRoot` + `act` tests), axios.

**Spec:** `docs/superpowers/specs/2026-11-11-tutorial-videos-design.md`

## Global Constraints

- **Never `git commit`** in this repo (the user's standing rule). Every commit step reads "Leave uncommitted".
- **Never run `manage.py migrate`** against the configured database: it is the team's shared Supabase database. Applying the migrations is the go-live step (spec, "Going live"), done only on the user's go-ahead after a backup. Tests build their own test database.
- **Backend tests use their own test database name** so they can't collide with a teammate's run. Once, create `%TEMP%\geoalert-tv\tv_settings.py` containing:
  ```python
  from config.settings.development import *  # noqa: F401,F403
  DATABASES['default']['TEST'] = {'NAME': 'test_geoalert_tutorials'}
  ```
  Then run from `backend/` in PowerShell (save the whole log; don't filter out tracebacks):
  ```powershell
  $env:PYTHONPATH = "$env:TEMP\geoalert-tv;."; $env:DJANGO_SETTINGS_MODULE = 'tv_settings'; .\venv\Scripts\python.exe manage.py test tests.test_tutorial_videos --noinput *> "$env:TEMP\geoalert-tv\test.log"; Get-Content "$env:TEMP\geoalert-tv\test.log" -Tail 40
  ```
  Below, "Run backend: `<label>`" means this command with `tests.test_tutorial_videos` replaced by `tests.test_tutorial_videos.<label>`.
- **Frontend tests**, from `frontend/` in PowerShell: `$env:CI='true'; npm test -- --watchAll=false <pattern>`.
- **CI rules:** `makemigrations --check --dry-run` must report no changes; `CI=true npm run build` fails on any warning (unused imports or variables included).
- **Limits:** MP4 at most `50 * 1024 * 1024` bytes (52,428,800); title at most 120 characters, description at most 500, category name at most 60, all trimmed. YouTube ID matches `[A-Za-z0-9_-]{11}`. oEmbed timeout 5 seconds.
- **Tables and columns:** `video_category` (columns prefixed `vdct_`) and `tutorial_video` (prefixed `tvid_`).
- **Who:** writes use `utils.permissions.IsDRRMOOfficer` (DRRMO_Officer, System_Admin); the page uses `useAuth().canPublish`.
- **Embeds and thumbnails:** player `https://www.youtube-nocookie.com/embed/<id>`; thumbnail `https://i.ytimg.com/vi/<id>/mqdefault.jpg`; "Watch on YouTube" link `https://www.youtube.com/watch?v=<id>`.
- **Text is text:** no `dangerouslySetInnerHTML` anywhere in this feature.
- **Copy** that the spec fixes is quoted in the task that uses it; use it verbatim.
- **Test files that grow across tasks:** when a step says "append", its imports go at the top of the file with the others.

## Review Focus

1. **A messy paste** (blank lines, Windows `\r\n` line endings, spaces around links, the same video twice, a link already in the batch): one row per distinct video, nothing for blank lines. Pinned in Task 5.
2. **File name case and type:** `FLOOD.MP4` is accepted on both sides; a `.mov` or `.jpg` that is dropped becomes a "Not an MP4" row instead of being silently ignored. Pinned in Tasks 3 and 5.
3. **Tiny, truncated or boundary-size files:** a 3-byte `.mp4` gets a 400 "That file isn't an MP4 video.", not a 500; exactly 50 MB is accepted, one byte more is refused. Pinned in Task 3.
4. **An MP4 that keeps failing to play** (a broken file, not an expired link): the section fetches the list again once per video, never in a loop. Pinned in Task 6.
5. **Deleting the video that is playing, or the last video of the chosen category:** the player moves to the first remaining video, and the chips fall back to All. Pinned in Task 9.

---

### Task 1: YouTube link reader (backend)

**Files:**
- Create: `backend/apps/tutorials/__init__.py` (empty), `backend/apps/tutorials/apps.py`, `backend/apps/tutorials/youtube.py`
- Test: `backend/tests/test_tutorial_videos.py` (new; later tasks add to it)

**Interfaces:**
- Produces: `parse_youtube_id(text: str | None) -> str | None`; `lookup(youtube_id: str) -> dict` returning `{'status': 'ok', 'title': str}`, `{'status': 'not_found'}` or `{'status': 'unchecked'}`; `OEMBED_URL = 'https://www.youtube.com/oembed'`. `apps.py`: `TutorialsConfig(name='apps.tutorials', default_auto_field='django.db.models.BigAutoField')`.

- [ ] **Step 1: Write the failing tests**

```python
"""
Tutorial videos (docs/superpowers/specs/2026-11-11-tutorial-videos-design.md):
the YouTube link reader, the two tables, and the /api/tutorials/ endpoints.
Against a real database; uploads go to a temporary folder; YouTube is mocked.
"""
from unittest.mock import Mock, patch

import requests
from django.test import SimpleTestCase

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
```

- [ ] **Step 2: Run them and see them fail**

Run backend: `YouTubeLinkTests` and `LookupTests`. Expected: ImportError (`apps.tutorials.youtube` does not exist).

- [ ] **Step 3: Implement `parse_youtube_id` and `lookup` in `backend/apps/tutorials/youtube.py`**

Use `urllib.parse`. Strip the text; a bare ID that fully matches the ID pattern is returned as is. Otherwise prefix `https://` when there is no `://`, take the host lowercased without its port, and drop one leading `www.` or `m.`. If the host is `youtu.be`, the ID is the first path segment. If the host is exactly `youtube.com` or `youtube-nocookie.com`, the ID is the `v` query value on `/watch`, or the second path segment of `/shorts/<id>` or `/embed/<id>`. Return it only when it fully matches `[A-Za-z0-9_-]{11}`, else `None`. `lookup` calls `requests.get` exactly as the test asserts. 200 → `ok` with the trimmed title; 400, 401, 403 or 404 → `not_found`; any other status, any `requests.RequestException`, or `ValueError` from `.json()` → `unchecked`. Write a module docstring saying why the server never calls YouTube when saving (spec section 3).

- [ ] **Step 4: Run them and see them pass**

Run backend: `YouTubeLinkTests` and `LookupTests`. Expected: OK.

- [ ] **Step 5: Leave uncommitted**

---

### Task 2: The two tables and the seed

**Files:**
- Create: `backend/apps/tutorials/models.py`, `backend/apps/tutorials/migrations/__init__.py`, `backend/apps/tutorials/migrations/0001_initial.py` (generated), `backend/apps/tutorials/migrations/0002_seed_first_aid.py`
- Modify: `backend/config/settings/base.py` (append `'apps.tutorials'` to `LOCAL_APPS`, after `'apps.news'`)
- Test: `backend/tests/test_tutorial_videos.py`

**Interfaces:**
- Produces:
  - `tutorial_video_path(instance, filename) -> str`: `f'tutorials/{timezone.now():%Y/%m}/{instance.id}.mp4'`. The uploader's file name is dropped.
  - `VideoCategory`: `id` UUID (`vdct_id`), `name` (`vdct_name`, max 60), `created_at` (`vdct_created_at`). `Meta`: `db_table='video_category'`, `ordering=[Lower('name')]`, and `UniqueConstraint(Lower('name'), name='video_category_name_ci_unique')`.
  - `TutorialVideo`:
    - `id` UUID (`tvid_id`).
    - `category`: FK to `VideoCategory`, `on_delete=PROTECT`, `related_name='videos'`, column `tvid_vdct_id`.
    - `title` (`tvid_title`, max 120).
    - `description` (`tvid_description`, `CharField` max 500, `blank=True`).
    - `source_type` (`tvid_source_type`, max 10, choices `SOURCES = [('youtube', 'YouTube link'), ('upload', 'MP4 upload')]`).
    - `youtube_id` (`tvid_youtube_id`, max 11, `blank=True`).
    - `file` (`FileField(upload_to=tutorial_video_path, max_length=200, blank=True)`, `tvid_file`).
    - `file_size` (`PositiveIntegerField(null=True, blank=True)`, `tvid_file_size`).
    - `created_by`: FK to `User`, `SET_NULL`, `null=True`, `blank=True`, `related_name='tutorial_videos'`, column `tvid_created_by`.
    - `created_at` (`tvid_created_at`) and `updated_at` (`tvid_updated_at`).
    - `Meta`: `db_table='tutorial_video'`; `ordering=[Lower('category__name'), 'created_at']`; and `CheckConstraint(name='tutorial_video_one_source')`, which allows exactly `(source_type='youtube' AND youtube_id<>'' AND file='') OR (source_type='upload' AND youtube_id='' AND file<>'')`.
  - `SEED` in `0002`: the 10 `(youtube_id, title)` pairs below, in this order.

- [ ] **Step 1: Write the failing tests** (append)

```python
import re

from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.test import TestCase

from apps.tutorials.models import TutorialVideo, VideoCategory, tutorial_video_path

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
```

- [ ] **Step 2: Implement `models.py`** with the fields and constraints in Interfaces. Give each class a docstring that says what it is, as `apps/news/models.py` does. Add `'apps.tutorials'` to `LOCAL_APPS`.

- [ ] **Step 3: Generate the schema migration**

Run from `backend/`: `.\venv\Scripts\python.exe manage.py makemigrations tutorials`
Expected: `Migrations for 'tutorials': apps\tutorials\migrations\0001_initial.py` with both models. (This only reads the database.)

- [ ] **Step 4: Write `0002_seed_first_aid.py`**

Run `.\venv\Scripts\python.exe manage.py makemigrations tutorials --empty --name seed_first_aid`, then add `RunPython(seed_first_aid, remove_first_aid)`. Use `apps.get_model`. `seed_first_aid` creates the category "First Aid", then the videos one by one in this order, so `created_at` keeps the order. Each video gets `source_type='youtube'`, its ID and title, and nothing else:

```python
SEED = [
    ('gn6xt1ca8A0', 'How to use your first aid kit'),
    ('ea1RJUOiNfQ', 'How to do the primary survey'),
    ('GmqXqwSV3bo', 'The recovery position'),
    ('NxO5LvgqZe0', 'How to treat severe bleeding'),
    ('2v8vlXgGXwE', 'How to treat a fracture'),
    ('fKzdiuseEIw', 'How to bandage a hand'),
    ('PwfBGkBXkFA', 'How to make a sling'),
    ('4e7evinsfm0', 'How to treat cuts and grazes'),
    ('Uqy2IUhYkVA', 'What to do if someone has a spinal cord injury'),
    ('0jps5SZlTdo', 'How to bandage a sprain'),
]
```

`remove_first_aid` deletes the "First Aid" videos whose `youtube_id` is in `SEED`, then deletes the category if it has no videos left.

- [ ] **Step 5: Run the tests and the migration check**

Run backend: `TutorialModelTests`. Expected: OK (5 tests).
Run: `.\venv\Scripts\python.exe manage.py makemigrations --check --dry-run`. Expected: `No changes detected`.

- [ ] **Step 6: Leave uncommitted**

---

### Task 3: The videos API

**Files:**
- Create: `backend/apps/tutorials/serializers.py`, `backend/apps/tutorials/views.py`, `backend/apps/tutorials/urls.py`
- Modify: `backend/config/urls.py` (add `path('api/tutorials/', include('apps.tutorials.urls'))` after `api/news/`)
- Test: `backend/tests/test_tutorial_videos.py`

**Interfaces:**
- Consumes: `parse_youtube_id` (Task 1); `TutorialVideo`, `VideoCategory` (Task 2); `apps.reports.serializers.photo_url(fieldfile, request)`; `utils.audit.log_event`; `utils.permissions.IsDRRMOOfficer`.
- Produces:
  - `MAX_VIDEO_BYTES = 50 * 1024 * 1024` in `serializers.py`.
  - `validate_mp4(file) -> file`. It raises `serializers.ValidationError` with the copy below, and on success sets `file.content_type = 'video/mp4'` so storage serves the file as video.
  - `TutorialVideoSerializer` (read): `{id, title, description, category: {id, name}, source_type, youtube_id, file_url, file_size, created_at}`. Ids are strings. `youtube_id` is `None` for uploads. `file_url` comes from `photo_url(obj.file, context['request'])` and is `None` for YouTube videos.
  - `TutorialVideoWriteSerializer`: fields `category` (PK), `title`, `description`, `source_type`, and write-only `youtube_url` (`CharField(required=False)`) and `file` (`FileField(required=False, validators=[validate_mp4])`).
  - Views: `VideoListView` (`GET` `AllowAny`; `POST` `IsAuthenticated` + `IsDRRMOOfficer`) and `VideoDetailView` (`PATCH`, `DELETE`; `IsAuthenticated` + `IsDRRMOOfficer`). A missing id answers 404 `{'error': 'Video not found.'}`. `POST` answers 201 and `PATCH` 200, both with the read shape. `DELETE` answers 204.
  - URL names: `''` → `tutorial-list`, `'<uuid:pk>/'` → `tutorial-detail`.
  - Audit: `log_event(request, 'ADD_VIDEO' | 'EDIT_VIDEO' | 'DELETE_VIDEO', 'tutorial_video', video.id, f'"{title}"')`.
  - Field error copy (verbatim):
    - `youtube_url`: `That isn't a YouTube video link.`
    - `file`, too big: `That video is {size_mb:.1f} MB. Please use one under 50 MB, or put it on YouTube.` (size in MiB)
    - `file`, wrong extension, fewer than 8 bytes, or bytes 4–7 not `ftyp`: `That file isn't an MP4 video.`
    - YouTube chosen but no link sent when creating or switching: `youtube_url`: `Paste the YouTube link for this video.`
    - MP4 chosen but no file sent when creating or switching: `file`: `Choose the MP4 file for this video.`

- [ ] **Step 1: Write the failing tests** (append)

```python
import shutil
import tempfile

from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from rest_framework import serializers as drf_serializers
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.accounts.models import Role, User
from apps.admin_dashboard.models import AuditLog
from apps.tutorials.serializers import MAX_VIDEO_BYTES, validate_mp4
from apps.tutorials.views import VideoDetailView, VideoListView

MEDIA = tempfile.mkdtemp(prefix='geoalert-tutorials-')
LOCAL_FILES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
}
MP4_HEAD = b'\x00\x00\x00\x18ftypmp42'


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


@override_settings(MEDIA_ROOT=MEDIA, STORAGES=LOCAL_FILES)
class TutorialApiTestCase(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def setUp(self):
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
        import uuid
        missing = TutorialVideo(pk=uuid.uuid4())
        self.assertEqual(self.edit(missing, title='X').status_code, 404)
        self.assertEqual(self.remove(missing).status_code, 404)
```

- [ ] **Step 2: Run them and see them fail**

Run backend: `Mp4CheckTests` and `VideoApiTests`. Expected: ImportError (`apps.tutorials.serializers` does not exist).

- [ ] **Step 3: Implement `serializers.py`**

`validate_mp4` checks, in this order: the extension (case-insensitive `.mp4`), then the size against `MAX_VIDEO_BYTES` (size in MiB in the message), then the signature. For the signature, `seek(0)`, read 12 bytes, `seek(0)`; it passes when there are at least 8 bytes and bytes 4–7 are `b'ftyp'`.

`TutorialVideoWriteSerializer.validate(attrs)`:
- The effective source is `attrs.get('source_type')`, else the instance's.
- A `youtube_url` that's sent must parse, or it's the `youtube_url` error. Turn it into `attrs['youtube_id']`.
- When creating, or when `source_type` changes, the new kind needs its media (the two "no link / no file" errors).
- A `youtube_url` sent for an upload, or a `file` sent for a YouTube video, is refused with the same two messages, so the request can't mix kinds.

In `create` and `update`:
- YouTube: set `youtube_id`, clear `file` and `file_size`.
- Upload: set `file`, set `file_size = file.size`, clear `youtube_id`.
- After saving, delete the old stored file whenever its name changed or the file was cleared. This is the `AnnouncementWriteSerializer.update` pattern.

`title` and `description` are `CharField` with `max_length` 120 and 500. `description` has `allow_blank=True, required=False`.

- [ ] **Step 4: Implement `views.py` and `urls.py`**, following `apps/news/views.py`: a module docstring listing the endpoints, permissions per method, and `log_event` after each change. Pass `context={'request': request}` to the read serializer. `GET` returns `TutorialVideo.objects.select_related('category')` in model order, unpaginated. `DELETE` deletes the file (`video.file.delete(save=False)` when there is one), then the row.

- [ ] **Step 5: Run them and see them pass**

Run backend: `Mp4CheckTests`, `VideoApiTests` and `TutorialModelTests`. Expected: OK.

- [ ] **Step 6: Leave uncommitted**

---

### Task 4: Categories and the YouTube check

**Files:**
- Modify: `backend/apps/tutorials/serializers.py`, `backend/apps/tutorials/views.py`, `backend/apps/tutorials/urls.py`
- Test: `backend/tests/test_tutorial_videos.py`

**Interfaces:**
- Consumes: `TutorialApiTestCase` (Task 3); `lookup`, `parse_youtube_id` (Task 1). `views.py` imports them as `from apps.tutorials.youtube import lookup, parse_youtube_id`, so tests patch `apps.tutorials.views.lookup`.
- Produces:
  - `VideoCategorySerializer`: fields `id`, `name` (`CharField(max_length=60)`, trimmed), and read-only `video_count`. `validate_name` refuses a name another category already has, ignoring case: `There is already a category called {existing.name}.` (the existing category's spelling). An `IntegrityError` on save answers 400 with the same message.
  - `CategoryListView`: `GET` (`AllowAny`) returns `[{id, name, video_count}]` A–Z, via `annotate(video_count=Count('videos'))`. `POST` (staff) answers 201.
  - `CategoryDetailView`: `PATCH` renames (200). `DELETE` answers 204, or 409 `{'error': 'This category still has videos. Move or delete them first.'}`. A missing id answers 404 `{'error': 'Category not found.'}`.
  - `YouTubeCheckView`: `GET ?url=` (staff) → `{youtube_id, status, title, duplicate}`. `title` is `None` unless `status == 'ok'`. `duplicate` is the category name of a saved video with that ID, else `None`. A link that doesn't parse answers 400 `{'url': "That isn't a YouTube video link."}`.
  - URL names: `categories/` → `tutorial-category-list`, `categories/<uuid:pk>/` → `tutorial-category-detail`, `youtube-check/` → `tutorial-youtube-check`.
  - Audit (table `video_category`):
    - `ADD_VIDEO_CATEGORY` with `"<name>"`
    - `RENAME_VIDEO_CATEGORY` with `"<old>" → "<new>"`
    - `DELETE_VIDEO_CATEGORY` with `"<name>"`

- [ ] **Step 1: Write the failing tests** (append)

```python
from apps.tutorials.views import CategoryDetailView, CategoryListView, YouTubeCheckView


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
        self.assertEqual([(c['name'], c['video_count']) for c in response.data], [('Drills', 0), ('First Aid', 10)])

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

    def test_only_an_empty_category_can_be_deleted(self):
        first_aid = VideoCategory.objects.get(name='First Aid')
        response = self.drop(first_aid)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data['error'], 'This category still has videos. Move or delete them first.')
        self.assertEqual(self.drop(self.drills).status_code, 204)
        self.assertTrue(AuditLog.objects.filter(action='DELETE_VIDEO_CATEGORY', details='"Drills"').exists())

    def test_only_drrmo_and_admins_change_categories(self):
        for user in (self.bfp, self.reporter):
            self.assertEqual(self.create('New', user).status_code, 403)
            self.assertEqual(self.rename(self.drills, 'New', user).status_code, 403)
            self.assertEqual(self.drop(self.drills, user).status_code, 403)


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
```

- [ ] **Step 2: Run them and see them fail**

Run backend: `CategoryApiTests` and `YouTubeCheckTests`. Expected: ImportError (`CategoryDetailView` not defined).

- [ ] **Step 3: Implement the serializer, the three views and the three URLs** described in Interfaces. Category `DELETE` checks `category.videos.exists()` before deleting, so the 409 is answered without relying on `ProtectedError`.

- [ ] **Step 4: Run the whole backend file**

Run backend: `tests.test_tutorial_videos` (the full module). Expected: OK, every test from Tasks 1–4.

- [ ] **Step 5: Leave uncommitted**

---

### Task 5: Frontend link, file and row helpers, and the API client

**Files:**
- Create: `frontend/src/utils/youtube.js`, `frontend/src/utils/youtube.test.js`, `frontend/src/components/Tutorials/videoRows.js`, `frontend/src/components/Tutorials/videoRows.test.js`, `frontend/src/api/tutorialsApi.js`

**Interfaces:**
- Produces, `utils/youtube.js`:
  - `parseYouTubeId(text) -> string | null`: the backend's rules from Task 1, using `new URL()`.
  - `youtubeThumb(id)`, `youtubeEmbed(id)`, `youtubeWatch(id)`: the three URLs in Global Constraints.
- Produces, `components/Tutorials/videoRows.js`:
  - `MAX_VIDEO_BYTES = 50 * 1024 * 1024`
  - `formatMB(bytes) -> string`, to one decimal (`66270000` → `'63.2'`).
  - `titleFromFileName(name) -> string`: drop the last extension, turn runs of `-` and `_` into one space, collapse spaces, trim, cut to 120 characters.
  - `rowsFromLinks(text, rows) -> Row[]`: the **new** rows only. One per distinct video in the pasted text. Lines are split on `\n` and trimmed of `\r` and spaces; blank lines are skipped. A video already among `rows` (same `youtubeId`) or earlier in the paste is skipped. A line that doesn't parse still makes a row, with `youtubeId: null`, so the staff see it was refused.
  - `rowFromFile(file) -> Row`
  - `rowFromVideo(video) -> Row`, for editing.
  - `rowState(row) -> { key, label, blocking }`
  - **Row shape:** `{ key: string (unique), videoId: string|null, kind: 'youtube'|'upload', categoryId: string|null (null = the batch's category), link: string, youtubeId: string|null, file: File|null, title: string, description: string, check: null|'pending'|'ok'|'not_found'|'unchecked', duplicate: string|null, send: 'idle'|'sending'|'saving'|'done'|'failed', progress: number, error: string }`
  - **`rowState` precedence**, first match wins (`key`: `label`):
    1. `bad_link`: `Not a YouTube link` (blocking): YouTube row, no `youtubeId`
    2. `not_found`: `Video not found or private` (blocking)
    3. `not_mp4`: `Not an MP4` (blocking): upload row with a `file` whose name isn't `.mp4` (any case)
    4. `too_big`: `` `Too big (${formatMB(size)} MB, limit 50 MB)` `` (blocking)
    5. `checking`: `Checking with YouTube…` (blocking): `check === 'pending'`
    6. `no_title`: `Needs a title` (blocking)
    7. `unchecked`: `Couldn't check with YouTube` (not blocking)
    8. `duplicate`: `` `Already in ${duplicate}` `` (not blocking)
    9. `ready`: `Ready` (not blocking)

    An upload row being edited with no new file (`file: null`, `videoId` set) skips 3 and 4.
- Produces, `api/tutorialsApi.js` (`tutorialsApi`):
  - `list()`, `categories()`
  - `create(video, onProgress)`, `update(id, video, onProgress)`, `remove(id)`
  - `createCategory(name)`, `renameCategory(id, name)`, `removeCategory(id)`
  - `checkYouTube(url)`, resolving to the response data.
  - `video` is `{ category, title, description, sourceType, youtubeUrl, file }`. Only defined fields are sent, as multipart with the field names from Task 3 (see `newsApi.form`).
  - `onProgress(percent)` gets 0–100 from axios `onUploadProgress` (`Math.round(loaded * 100 / total)`).

- [ ] **Step 1: Write the failing tests**

`frontend/src/utils/youtube.test.js`: copy `ACCEPTED` and `REFUSED` from Task 1 (with `null` for `None`):

```js
import { parseYouTubeId, youtubeEmbed, youtubeThumb, youtubeWatch } from './youtube';

const ID = '2v8vlXgGXwE';
const ACCEPTED = [/* the 13 strings from Task 1, same order */];
const REFUSED = [/* the 11 values from Task 1, same order */];

test.each(ACCEPTED)('%s gives the id', (text) => expect(parseYouTubeId(text)).toBe(ID));
test.each(REFUSED)('%s gives null', (text) => expect(parseYouTubeId(text)).toBeNull());
test('the three urls', () => {
  expect(youtubeEmbed(ID)).toBe(`https://www.youtube-nocookie.com/embed/${ID}`);
  expect(youtubeThumb(ID)).toBe(`https://i.ytimg.com/vi/${ID}/mqdefault.jpg`);
  expect(youtubeWatch(ID)).toBe(`https://www.youtube.com/watch?v=${ID}`);
});
```

`frontend/src/components/Tutorials/videoRows.test.js`:

```js
import { formatMB, rowFromFile, rowFromVideo, rowState, rowsFromLinks, titleFromFileName } from './videoRows';

const file = (name, size = 1000) => Object.defineProperty(new File(['x'], name), 'size', { value: size });

test('a messy paste makes one row per distinct video', () => {
  const rows = rowsFromLinks('\r\n https://youtu.be/aaaaaaaaaaa \r\n\r\nhttps://www.youtube.com/watch?v=aaaaaaaaaaa\r\nnot a link\nbbbbbbbbbbb\n', []);
  expect(rows.map((r) => r.youtubeId)).toEqual(['aaaaaaaaaaa', null, 'bbbbbbbbbbb']);
  expect(rows[1].link).toBe('not a link');
  expect(rows.every((r) => r.kind === 'youtube' && r.send === 'idle' && r.categoryId === null)).toBe(true);
  expect(new Set(rows.map((r) => r.key)).size).toBe(3);
  expect(rowsFromLinks('https://youtu.be/bbbbbbbbbbb', rows)).toEqual([]);
});

test('titles from file names', () => {
  expect(titleFromFileName('flood-drill_2026.mp4')).toBe('flood drill 2026');
  expect(titleFromFileName('  Evac--Plan__v2.final.MP4')).toBe('Evac Plan v2.final');
  expect(titleFromFileName(`${'a'.repeat(130)}.mp4`)).toHaveLength(120);
});

test('file rows: case, type and size', () => {
  expect(rowState(rowFromFile(file('FLOOD.MP4'))).key).toBe('ready');
  expect(rowFromFile(file('FLOOD.MP4')).title).toBe('FLOOD');
  expect(rowState(rowFromFile(file('drill.mov')))).toEqual({ key: 'not_mp4', label: 'Not an MP4', blocking: true });
  expect(rowState(rowFromFile(file('photo.jpg'))).key).toBe('not_mp4');
  expect(formatMB(66270000)).toBe('63.2');
  expect(rowState(rowFromFile(file('big.mp4', 66270000))).label).toBe('Too big (63.2 MB, limit 50 MB)');
  expect(rowState(rowFromFile(file('edge.mp4', 50 * 1024 * 1024))).key).toBe('ready');
});

test('youtube row states in order', () => {
  const [row] = rowsFromLinks('https://youtu.be/aaaaaaaaaaa', []);
  expect(rowState({ ...row, check: 'pending' })).toEqual({ key: 'checking', label: 'Checking with YouTube…', blocking: true });
  expect(rowState({ ...row, check: 'not_found' }).label).toBe('Video not found or private');
  expect(rowState({ ...row, check: 'ok', title: ' ' }).label).toBe('Needs a title');
  expect(rowState({ ...row, check: 'unchecked', title: 'T' })).toEqual({ key: 'unchecked', label: "Couldn't check with YouTube", blocking: false });
  expect(rowState({ ...row, check: 'ok', title: 'T', duplicate: 'First Aid' })).toEqual({ key: 'duplicate', label: 'Already in First Aid', blocking: false });
  expect(rowState({ ...row, check: 'ok', title: 'T' }).label).toBe('Ready');
  expect(rowState(rowsFromLinks('nope', [])[0]).label).toBe('Not a YouTube link');
});

test('an existing video becomes one editable row', () => {
  const row = rowFromVideo({ id: 'v1', title: 'Drill', description: 'D', category: { id: 'c1', name: 'Drills' },
    source_type: 'upload', youtube_id: null, file_url: 'https://x/v.mp4', file_size: 10 });
  expect(row).toMatchObject({ videoId: 'v1', kind: 'upload', categoryId: 'c1', file: null, title: 'Drill', description: 'D' });
  expect(rowState(row).key).toBe('ready');
});
```

- [ ] **Step 2: Run them and see them fail**

Run frontend: `youtube videoRows`. Expected: "Cannot find module './youtube'" and "'./videoRows'".

- [ ] **Step 3: Implement `utils/youtube.js`, `videoRows.js` and `api/tutorialsApi.js`** to the Interfaces. Row keys come from a module counter (`row-1`, `row-2`, …). `tutorialsApi` uses `client` from `./axiosClient` and the same `MULTIPART` header object as `newsApi`.

- [ ] **Step 4: Run them and see them pass**

Run frontend: `youtube videoRows`. Expected: all pass.

- [ ] **Step 5: Leave uncommitted**

---

### Task 6: The public videos section on What To Do

**Files:**
- Create: `frontend/src/components/Tutorials/VideoPlayer.jsx`, `frontend/src/components/Tutorials/TutorialVideos.jsx`, `frontend/src/components/Tutorials/TutorialVideos.test.js`, `frontend/src/components/Tutorials/css/TutorialVideos.css`
- Modify:
  - `frontend/src/pages/WhatToDo.jsx`:
    - drop `VIDEOS` from the import (line 5);
    - remove the `videoId` state (line 69), `sortedVideos` and `activeVideo` (lines 210–213), and the two `firstVideo` lines in `chooseHazard` (lines 219–220);
    - replace the `VIDEOS` section (from `{/* ============ VIDEOS ============ */}`, line 563, to its closing `</section>`) with `<TutorialVideos />`.
  - `frontend/src/pages/css/WhatToDo.css`: move the `/* ---------- Videos ---------- */` block (`.wt-videos` through the `.wt-playlist-item` rules) and the `.wt-videos` and `.wt-playlist` lines of the `max-width: 1000px` query into `TutorialVideos.css`, with the class names unchanged.
  - `frontend/src/data/safetyGuides.js`: delete the `VIDEOS` export and its comment (lines 173–186).
  - `frontend/src/pages/whatToDoEditing.test.js`: add `jest.mock('../components/Tutorials/TutorialVideos', () => () => null);`.

**Interfaces:**
- Consumes: `tutorialsApi.list` (Task 5); `youtubeEmbed`, `youtubeThumb`, `youtubeWatch` (Task 5); `useAuth` from `../../context/AuthContext`.
- Produces:
  - `VideoPlayer({ video, onError })`. A YouTube video renders the existing iframe markup (`wt-player-frame`, the same `allow` attribute, `allowFullScreen`, `loading="lazy"`, `key` by id). An upload renders `<video controls preload="metadata" src={video.file_url} onError={onError}>`.
  - `TutorialVideos()`, the default export, used by `WhatToDo.jsx`. Its state: `videos`, `loading`, `failed`, `chosen` (`'all'` or a category id), `activeId`, and `reload()`. Task 9 adds the staff tools to this component.
  - Copy:
    - heading `Tutorial videos`
    - sub-line `Short lessons. Watch and share them with your family.`
    - chip `All`
    - while loading: `Loading videos…`
    - on failure: `Couldn't load the videos. Try again.`, with a `Try again` button
    - link: `Watch on YouTube`

- [ ] **Step 1: Write the failing tests**

```js
import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import TutorialVideos from './TutorialVideos';
import { tutorialsApi } from '../../api/tutorialsApi';
import { useAuth } from '../../context/AuthContext';

jest.mock('../../context/AuthContext', () => ({ useAuth: jest.fn() }));
jest.mock('../../api/tutorialsApi', () => ({ tutorialsApi: { list: jest.fn(), remove: jest.fn() } }));

const FIRST_AID = { id: 'c1', name: 'First Aid' };
const DRILLS = { id: 'c2', name: 'Drills' };
const YT = { id: 'v1', title: 'How to treat a fracture', description: 'Keep the limb still', category: FIRST_AID,
  source_type: 'youtube', youtube_id: '2v8vlXgGXwE', file_url: null, file_size: null };
const MP4 = { id: 'v2', title: 'Flood drill', description: '', category: DRILLS,
  source_type: 'upload', youtube_id: null, file_url: 'https://files/v2.mp4', file_size: 31000000 };

beforeAll(() => { global.IS_REACT_ACT_ENVIRONMENT = true; });
beforeEach(() => { jest.clearAllMocks(); useAuth.mockReturnValue({ canPublish: false }); });

async function render() {
  const el = document.createElement('div');
  document.body.appendChild(el);
  await act(async () => { createRoot(el).render(<TutorialVideos />); });
  return el;
}
const click = (b) => act(async () => { b.click(); });
const chip = (el, text) => [...el.querySelectorAll('.tv-chip')].find((b) => b.textContent === text);

test('plays the first video, with its category, title, description and YouTube link', async () => {
  tutorialsApi.list.mockResolvedValue([MP4, YT]);
  const el = await render();
  expect(el.querySelector('h2').textContent).toBe('Tutorial videos');
  expect([...el.querySelectorAll('.tv-chip')].map((b) => b.textContent)).toEqual(['All', 'Drills', 'First Aid']);
  expect(el.querySelector('video').getAttribute('src')).toBe('https://files/v2.mp4');
  expect(el.textContent).not.toMatch('Watch on YouTube');
  await click(el.querySelectorAll('.wt-playlist-item')[1]);
  expect(el.querySelector('iframe').getAttribute('src')).toBe('https://www.youtube-nocookie.com/embed/2v8vlXgGXwE');
  expect(el.querySelector('.wt-player-info').textContent).toMatch('Keep the limb still');
  expect(el.querySelector('.wt-youtube-link').getAttribute('href')).toBe('https://www.youtube.com/watch?v=2v8vlXgGXwE');
});

test('a chip shows its category and plays its first video', async () => {
  tutorialsApi.list.mockResolvedValue([MP4, YT]);
  const el = await render();
  await click(chip(el, 'First Aid'));
  expect(el.querySelectorAll('.wt-playlist-item')).toHaveLength(1);
  expect(el.querySelector('iframe')).not.toBeNull();
});

test('a failed load offers to try again', async () => {
  tutorialsApi.list.mockRejectedValueOnce(new Error('down')).mockResolvedValueOnce([YT]);
  const el = await render();
  expect(el.textContent).toMatch("Couldn't load the videos. Try again.");
  await click([...el.querySelectorAll('button')].find((b) => b.textContent === 'Try again'));
  expect(el.querySelector('iframe')).not.toBeNull();
});

test('residents see nothing when there are no videos', async () => {
  tutorialsApi.list.mockResolvedValue([]);
  const el = await render();
  expect(el.innerHTML).toBe('');
});

test('an MP4 that fails to play fetches fresh links once, not in a loop', async () => {
  tutorialsApi.list.mockResolvedValue([MP4]);
  const el = await render();
  await act(async () => { el.querySelector('video').dispatchEvent(new Event('error')); });
  await act(async () => { el.querySelector('video').dispatchEvent(new Event('error')); });
  expect(tutorialsApi.list).toHaveBeenCalledTimes(2);
});
```

- [ ] **Step 2: Run them and see them fail**

Run frontend: `TutorialVideos`. Expected: "Cannot find module './TutorialVideos'".

- [ ] **Step 3: Implement `VideoPlayer.jsx` and `TutorialVideos.jsx`**, keeping the existing `ph-section` / `ph-container` / `ph-section-head` / `wt-videos` / `wt-player` / `wt-playlist` markup. Chips have class `tv-chip`, with `is-active` and `aria-pressed` on the chosen one. They list categories in the order they first appear in the list (the server sorts by category). Playlist thumbnails:
  - YouTube: `youtubeThumb(id)`.
  - MP4: a play-icon tile `<span className="tv-thumb-mp4" aria-hidden="true">`.

  Each item's small line shows the category name, plus ` · MP4` for uploads. When `activeId` isn't among the shown videos, the first shown video plays. The fetch-once guard is a `useRef(new Set())` of video ids already retried. Import `./css/TutorialVideos.css`.

- [ ] **Step 4: Wire it into `WhatToDo.jsx`** and make the CSS, `safetyGuides.js` and `whatToDoEditing.test.js` changes listed under Files.

- [ ] **Step 5: Run the tests**

Run frontend: `TutorialVideos whatToDoEditing`. Expected: all pass.

- [ ] **Step 6: Leave uncommitted**

---

### Task 7: The category picker

**Files:**
- Create: `frontend/src/components/Tutorials/CategoryPicker.jsx`, `frontend/src/components/Tutorials/CategoryPicker.test.js`
- Modify: `frontend/src/components/Tutorials/css/TutorialVideos.css` (picker styles, `tv-` prefix)

**Interfaces:**
- Consumes: `tutorialsApi.createCategory`, `renameCategory`, `removeCategory` (Task 5).
- Produces: `CategoryPicker({ categories, value, onChange, onChanged })`:
  - `categories` is `[{id, name, video_count}]` in server order. `value` is a category id or `null`.
  - `onChange(id | null)` selects a category.
  - `onChanged()` asks the parent to fetch the categories again after a create, rename or delete.
  - Markup and copy:
    - a `<select aria-label="Category">` whose first option is `Choose a category` (value `''`);
    - `+ New category`, which opens a name input (`aria-label="New category name"`) with `Create` and `Cancel`;
    - `Rename`, shown when `value` is set, which opens an input (`aria-label="Category name"`) with `Save` and `Cancel`;
    - `Delete`, shown only when the chosen category's `video_count === 0`, which asks `window.confirm(`Delete the category "${name}"?`)` first;
    - an API error (`err.message`) shows in `<p role="alert">`.

- [ ] **Step 1: Write the failing tests**

```js
// render(props) mounts <CategoryPicker {...props} /> as in TutorialVideos.test.js;
// type(input, value) is the native-setter helper from components/Guidance/guidanceEditor.test.js.
const CATS = [{ id: 'c2', name: 'Drills', video_count: 0 }, { id: 'c1', name: 'First Aid', video_count: 10 }];

test('lists the categories and selects one', async () => {
  const onChange = jest.fn();
  const el = await render({ categories: CATS, value: null, onChange, onChanged: jest.fn() });
  expect([...el.querySelectorAll('option')].map((o) => o.textContent)).toEqual(['Choose a category', 'Drills', 'First Aid']);
  await change(el.querySelector('select'), 'c1');
  expect(onChange).toHaveBeenCalledWith('c1');
});

test('creates a category and selects it', async () => {
  tutorialsApi.createCategory.mockResolvedValue({ id: 'c3', name: 'Typhoon Response', video_count: 0 });
  const onChange = jest.fn(); const onChanged = jest.fn();
  const el = await render({ categories: CATS, value: null, onChange, onChanged });
  await click(button(el, '+ New category'));
  await type(el.querySelector('[aria-label="New category name"]'), 'Typhoon Response');
  await click(button(el, 'Create'));
  expect(tutorialsApi.createCategory).toHaveBeenCalledWith('Typhoon Response');
  expect(onChange).toHaveBeenCalledWith('c3');
  expect(onChanged).toHaveBeenCalled();
});

test("shows the server's message when a name is taken", async () => {
  tutorialsApi.createCategory.mockRejectedValue(new Error('There is already a category called First Aid.'));
  const el = await render({ categories: CATS, value: null, onChange: jest.fn(), onChanged: jest.fn() });
  await click(button(el, '+ New category'));
  await type(el.querySelector('[aria-label="New category name"]'), 'first aid');
  await click(button(el, 'Create'));
  expect(el.querySelector('[role="alert"]').textContent).toBe('There is already a category called First Aid.');
});

test('renames the chosen category; Delete only when it is empty and confirmed', async () => {
  tutorialsApi.renameCategory.mockResolvedValue({});
  tutorialsApi.removeCategory.mockResolvedValue({});
  const onChange = jest.fn(); const onChanged = jest.fn();
  let el = await render({ categories: CATS, value: 'c1', onChange, onChanged });
  expect(button(el, 'Delete')).toBeUndefined();
  await click(button(el, 'Rename'));
  await type(el.querySelector('[aria-label="Category name"]'), 'First Aid Basics');
  await click(button(el, 'Save'));
  expect(tutorialsApi.renameCategory).toHaveBeenCalledWith('c1', 'First Aid Basics');
  el = await render({ categories: CATS, value: 'c2', onChange, onChanged });
  jest.spyOn(window, 'confirm').mockReturnValueOnce(false).mockReturnValueOnce(true);
  await click(button(el, 'Delete'));
  expect(tutorialsApi.removeCategory).not.toHaveBeenCalled();
  await click(button(el, 'Delete'));
  expect(window.confirm).toHaveBeenLastCalledWith('Delete the category "Drills"?');
  expect(tutorialsApi.removeCategory).toHaveBeenCalledWith('c2');
  expect(onChange).toHaveBeenLastCalledWith(null);
});
```

Define `button(el, text)` (by exact `textContent`), `click`, `type` and `change` (dispatches `change` on the select after setting `value`) at the top of the file.

- [ ] **Step 2: Run them and see them fail**

Run frontend: `CategoryPicker`. Expected: "Cannot find module './CategoryPicker'".

- [ ] **Step 3: Implement `CategoryPicker.jsx`** to the Interfaces. Trim names before sending, and keep `Create` and `Save` disabled while the input is blank or the request is running.

- [ ] **Step 4: Run them and see them pass**

Run frontend: `CategoryPicker`. Expected: all pass.

- [ ] **Step 5: Leave uncommitted**

---

### Task 8: The batch form

**Files:**
- Create: `frontend/src/components/Tutorials/VideoEntryRow.jsx`, `frontend/src/components/Tutorials/AddVideosForm.jsx`, `frontend/src/components/Tutorials/AddVideosForm.test.js`
- Modify: `frontend/src/components/Tutorials/css/TutorialVideos.css` (form styles)

**Interfaces:**
- Consumes:
  - `rowsFromLinks`, `rowFromFile`, `rowFromVideo`, `rowState`, `formatMB` (Task 5);
  - `tutorialsApi.categories`, `create`, `update`, `checkYouTube` (Task 5);
  - `CategoryPicker` (Task 7).
- Produces:
  - `VideoEntryRow({ row, categories, onChange(patch), onRemove(), onRetry() })`. It renders:
    - the thumbnail: YouTube's, or a `<video>` playing `URL.createObjectURL(file)` for a new file, revoked on unmount;
    - `Title` and `About` inputs (`aria-label`s `Title` and `Description`);
    - a category `<select aria-label="Row category">` with a first option `Batch category` (value `''`);
    - the `rowState` label in `.tv-row-state`;
    - a progress bar with text `${progress}%` while `send === 'sending'`, and `Saving…` while `'saving'`;
    - `Done` once `'done'`; on `'failed'`, `row.error` in `role="alert"` and a `Retry` button;
    - a remove button (`aria-label="Remove row"`).
  - `AddVideosForm({ video = null, defaultCategoryId = null, usedBytes, onClose(changed: boolean) })`:
    - **Inputs:** a textarea (`aria-label="YouTube links"`) with an `Add links` button, and a drop zone with `<input type="file" accept="video/mp4,.mp4" multiple aria-label="MP4 files">`. Both are always shown.
    - **Copy under the drop zone:** `` `Up to 50 MB each. Uploaded videos use ${formatMB(usedBytes)} MB of the 1 GB shared with report photos.` ``
    - **YouTube check:** each new YouTube row with an ID starts `check: 'pending'` and calls `checkYouTube(link)`. `ok` fills the title only when it's empty. `ok`/`not_found` set `check` and `duplicate`. A rejection sets `check: 'unchecked'`. In edit mode, a `duplicate` for the video's own current ID is ignored.
    - **Publish button:** `Publish ${n} videos` (`Publish 1 video` for one), where `n` counts rows not `done`. It's disabled while any row is blocking, while a send is running, or while a row has no category (its own or the batch's). With no batch category and a row needing it, show `Pick a category first.`
    - **Publishing:** rows are sent one at a time, in order. `sourceType` is `row.kind`; `youtubeUrl` is `row.link`; `file` is the file; `category` is `row.categoryId ?? batch category`. A row is `sending` from when its request starts (`progress` follows `onProgress`) and `saving` once progress reaches 100. Success sets `done`; a rejection sets `failed` with `error: err.message`. `Retry` resends that row only.
    - **When every row is done:** `` `${n} videos published` `` (`1 video published`), with `Add more videos` (empty rows, same batch category) and `Done`, which calls `onClose(true)`.
    - **Cancel:** calls `onClose(anySaved)`. While a row is `sending`/`saving`, it first asks `` window.confirm(`${n} videos are still uploading. Leave anyway?`) `` (`1 video is still uploading. Leave anyway?`), and a `beforeunload` listener is attached while sending.
    - **Edit mode** (`video` set):
      - the form's `<h3>` reads `Edit video` (else `Add videos`);
      - one row from `rowFromVideo(video)`;
      - a new link or file **replaces** that row's media (keeping its title, description and `videoId`) instead of adding rows. For links, the first non-blank line is used, without `rowsFromLinks`' de-duplication (which would drop the video's own link), and it is checked with `checkYouTube` as usual;
      - the button is `Save`. It calls `update(video.id, …)`, sending `youtubeUrl`/`file` only when the media changed, and `sourceType` only when the kind changed. Then `onClose(true)`.

- [ ] **Step 1: Write the failing tests**

Put this at the top of the file:

```js
// render/click/type/button helpers as in CategoryPicker.test.js
jest.mock('../../api/tutorialsApi', () => ({ tutorialsApi: {
  categories: jest.fn(), create: jest.fn(), update: jest.fn(), checkYouTube: jest.fn(),
  createCategory: jest.fn(), renameCategory: jest.fn(), removeCategory: jest.fn() } }));
const CATS = [{ id: 'c1', name: 'First Aid', video_count: 10 }];
const file = (name, size = 1000) => Object.defineProperty(new File(['x'], name, { type: 'video/mp4' }), 'size', { value: size });
async function pickFiles(el, files) {
  const input = el.querySelector('[aria-label="MP4 files"]');
  Object.defineProperty(input, 'files', { value: files, configurable: true });
  await act(async () => { input.dispatchEvent(new Event('change', { bubbles: true })); });
}
beforeEach(() => {
  jest.clearAllMocks();
  global.URL.createObjectURL = jest.fn(() => 'blob:preview');
  global.URL.revokeObjectURL = jest.fn();
  tutorialsApi.categories.mockResolvedValue(CATS);
  tutorialsApi.checkYouTube.mockImplementation((url) => Promise.resolve(
    { youtube_id: url.slice(-11), status: 'ok', title: `Title ${url.slice(-3)}`, duplicate: null }));
});
const states = (el) => [...el.querySelectorAll('.tv-row-state')].map((s) => s.textContent);
```

Then these tests:

```js
test('links and files go in one batch, titles filled in', async () => {
  const el = await render({ defaultCategoryId: 'c1', usedBytes: 222298112, onClose: jest.fn() });
  expect(el.textContent).toMatch('Uploaded videos use 212.0 MB of the 1 GB shared with report photos.');
  await type(el.querySelector('[aria-label="YouTube links"]'), 'https://youtu.be/aaaaaaaaaaa\nhttps://youtu.be/bbbbbbbbbbb\nhttps://youtu.be/ccccccccccc');
  await click(button(el, 'Add links'));
  await pickFiles(el, [file('flood-drill_2026.mp4'), file('evac.mp4')]);
  const titles = [...el.querySelectorAll('[aria-label="Title"]')].map((i) => i.value);
  expect(titles).toEqual(['Title aaa', 'Title bbb', 'Title ccc', 'flood drill 2026', 'evac']);
  expect(button(el, 'Publish 5 videos').disabled).toBe(false);
});

test('a file over 50 MB is never uploaded and blocks Publish', async () => {
  const el = await render({ defaultCategoryId: 'c1', usedBytes: 0, onClose: jest.fn() });
  await pickFiles(el, [file('big.mp4', 66270000)]);
  expect(states(el)).toEqual(['Too big (63.2 MB, limit 50 MB)']);
  expect(button(el, 'Publish 1 video').disabled).toBe(true);
  expect(tutorialsApi.create).not.toHaveBeenCalled();
});

test('rows are sent one at a time in order; a failed row can be retried alone', async () => {
  let finishFirst;
  tutorialsApi.create
    .mockImplementationOnce((video, onProgress) => new Promise((resolve) => { onProgress(62); finishFirst = resolve; }))
    .mockRejectedValueOnce(new Error("That file isn't an MP4 video."))
    .mockResolvedValueOnce({ id: 'v2' });
  const onClose = jest.fn();
  const el = await render({ defaultCategoryId: 'c1', usedBytes: 0, onClose });
  await pickFiles(el, [file('one.mp4'), file('two.mp4')]);
  await click(button(el, 'Publish 2 videos'));
  expect(el.textContent).toMatch('62%');
  expect(tutorialsApi.create).toHaveBeenCalledTimes(1);
  expect(tutorialsApi.create.mock.calls[0][0]).toMatchObject({ category: 'c1', sourceType: 'upload', title: 'one' });
  await act(async () => { finishFirst({ id: 'v1' }); });
  expect(tutorialsApi.create).toHaveBeenCalledTimes(2);
  expect(el.querySelector('[role="alert"]').textContent).toBe("That file isn't an MP4 video.");
  await click(button(el, 'Retry'));
  expect(tutorialsApi.create).toHaveBeenCalledTimes(3);
  expect(tutorialsApi.create.mock.calls[2][0].title).toBe('two');
  expect(el.textContent).toMatch('2 videos published');
  await click(button(el, 'Add more videos'));
  expect(el.querySelectorAll('[aria-label="Title"]')).toHaveLength(0);
  expect(el.querySelector('select[aria-label="Category"]').value).toBe('c1');
  await click(button(el, 'Done'));
  expect(onClose).toHaveBeenCalledWith(true);
});

test('leaving while uploading asks first', async () => {
  tutorialsApi.create.mockImplementation(() => new Promise(() => {}));
  const onClose = jest.fn();
  const el = await render({ defaultCategoryId: 'c1', usedBytes: 0, onClose });
  await pickFiles(el, [file('one.mp4')]);
  await click(button(el, 'Publish 1 video'));
  jest.spyOn(window, 'confirm').mockReturnValueOnce(false);
  await click(button(el, 'Cancel'));
  expect(window.confirm).toHaveBeenCalledWith('1 video is still uploading. Leave anyway?');
  expect(onClose).not.toHaveBeenCalled();
});

test('editing a YouTube video with a new file switches it to MP4, and is not its own duplicate', async () => {
  tutorialsApi.update.mockResolvedValue({});
  tutorialsApi.checkYouTube.mockResolvedValue({ youtube_id: '2v8vlXgGXwE', status: 'ok', title: 'X', duplicate: 'First Aid' });
  const video = { id: 'v1', title: 'Fracture', description: '', category: { id: 'c1', name: 'First Aid' },
    source_type: 'youtube', youtube_id: '2v8vlXgGXwE', file_url: null, file_size: null };
  const onClose = jest.fn();
  const el = await render({ video, usedBytes: 0, onClose });
  expect(el.querySelector('h3').textContent).toBe('Edit video');
  await type(el.querySelector('[aria-label="YouTube links"]'), 'https://youtu.be/2v8vlXgGXwE');
  await click(button(el, 'Add links'));
  expect(tutorialsApi.checkYouTube).toHaveBeenCalledWith('https://youtu.be/2v8vlXgGXwE');
  expect(states(el)).toEqual(['Ready']);   // not "Already in First Aid": that is this video
  await pickFiles(el, [file('fracture.mp4')]);
  expect(el.querySelectorAll('[aria-label="Title"]')).toHaveLength(1);
  expect(el.querySelector('[aria-label="Title"]').value).toBe('Fracture');
  await click(button(el, 'Save'));
  expect(tutorialsApi.update).toHaveBeenCalledWith('v1', expect.objectContaining({ sourceType: 'upload', title: 'Fracture' }), expect.any(Function));
  expect(onClose).toHaveBeenCalledWith(true);
});
```

- [ ] **Step 2: Run them and see them fail**

Run frontend: `AddVideosForm`. Expected: "Cannot find module './AddVideosForm'".

- [ ] **Step 3: Implement `VideoEntryRow.jsx`**: props in, events out, no API calls.

- [ ] **Step 4: Implement `AddVideosForm.jsx`** to the Interfaces. Rows live in one `useState` array; update a row by `key`. Run the send loop from an async function that reads the latest rows through a ref, so `Retry` and the loop never send a `done` row twice. Fetch the categories on mount and again on the picker's `onChanged`. Drops on the zone (`dragover` `preventDefault`, `drop` → `dataTransfer.files`) go through the same handler as the file input. A dropped `.mov` or `.jpg` still becomes a row (Review Focus 2).

- [ ] **Step 5: Run them and see them pass**

Run frontend: `AddVideosForm videoRows CategoryPicker`. Expected: all pass.

- [ ] **Step 6: Leave uncommitted**

---

### Task 9: Staff tools on the section, and activity log labels

**Files:**
- Modify: `frontend/src/components/Tutorials/TutorialVideos.jsx`, `frontend/src/components/Tutorials/TutorialVideos.test.js`, `frontend/src/components/Tutorials/css/TutorialVideos.css`, `frontend/src/pages/Dashboard/admin/adminShared.jsx` (`ACTION_META`)
- Create: `frontend/src/pages/Dashboard/admin/actionMeta.test.js`

**Interfaces:**
- Consumes: `AddVideosForm` (Task 8); `tutorialsApi.remove` (Task 5); `useAuth().canPublish`.
- Produces: in `TutorialVideos`, `editing` state (`null` | `'new'` | a video id) and `actionError`.
  - **Add videos:** a `wt-edit-btn` beside the heading. It opens `<AddVideosForm defaultCategoryId={chosen === 'all' ? null : chosen} usedBytes={sum of file_size} onClose={…} />` at the top of the section and scrolls to it (`scrollIntoView` when present).
  - **Edit and Delete:** each playlist `<li>` gets `Edit` and `Delete` buttons, siblings of the play button (not inside it). Their `aria-label`s are `` `Edit "${title}"` `` and `` `Delete "${title}"` ``. Edit opens the form with `video`.
  - **While the form is open**, or while the list is loading or failed to load, Add, Edit and Delete are hidden.
  - **`onClose(changed)`** closes the form and calls `reload()` when `changed`.
  - **Delete** asks `` window.confirm(`Delete '${title}'? Residents will stop seeing it.`) ``, adding ` The uploaded file is deleted too.` for uploads. On yes it calls `tutorialsApi.remove(id)` and then `reload()`. A failure puts `err.message` in `<p className="wt-action-error" role="alert">` above the playlist.
  - **After the list changes:** if `activeId` is gone, the first shown video plays. If the chosen category has no videos left, `chosen` goes back to `'all'`.
  - **Staff with no videos** see the section with `No videos yet.` and Add videos.
  - **`ACTION_META` entries:**
    - `ADD_VIDEO`: `Added a video` (`good`, `list`)
    - `EDIT_VIDEO`: `Edited a video` (`info`, `edit`)
    - `DELETE_VIDEO`: `Deleted a video` (`bad`, `x`)
    - `ADD_VIDEO_CATEGORY`: `Added a video category` (`good`, `list`)
    - `RENAME_VIDEO_CATEGORY`: `Renamed a video category` (`info`, `edit`)
    - `DELETE_VIDEO_CATEGORY`: `Deleted a video category` (`bad`, `x`)

- [ ] **Step 1: Write the failing tests** (append to `TutorialVideos.test.js`)

Add this at the top:

```js
// No JSX inside a jest.mock factory: it may only use what it requires itself
jest.mock('./AddVideosForm', () => {
  const React = require('react');
  return function AddVideosFormStub(props) {
    return React.createElement('div', { className: 'form-stub' },
      props.video ? `editing ${props.video.id}` : `adding in ${props.defaultCategoryId}`,
      React.createElement('button', { type: 'button', onClick: () => props.onClose(true) }, 'stub close'));
  };
});
const button = (el, text) => [...el.querySelectorAll('button')].find((b) => b.textContent === text);
```

Then these tests:

```js
test('residents get no tools; staff get Add, Edit and Delete', async () => {
  tutorialsApi.list.mockResolvedValue([MP4, YT]);
  let el = await render();
  expect(button(el, 'Add videos')).toBeUndefined();
  expect(el.querySelector('[aria-label^="Edit"]')).toBeNull();
  useAuth.mockReturnValue({ canPublish: true });
  el = await render();
  expect(button(el, 'Add videos')).toBeDefined();
  expect(el.querySelector('[aria-label="Edit \\"Flood drill\\""]')).not.toBeNull();
  expect(el.querySelector('[aria-label="Delete \\"How to treat a fracture\\""]')).not.toBeNull();
});

test('staff see the section with no videos', async () => {
  useAuth.mockReturnValue({ canPublish: true });
  tutorialsApi.list.mockResolvedValue([]);
  const el = await render();
  expect(el.textContent).toMatch('No videos yet.');
  expect(button(el, 'Add videos')).toBeDefined();
});

test('one form at a time, opened in the chosen category; closing with changes reloads', async () => {
  useAuth.mockReturnValue({ canPublish: true });
  tutorialsApi.list.mockResolvedValue([MP4, YT]);
  const el = await render();
  await click(chip(el, 'First Aid'));
  await click(button(el, 'Add videos'));
  expect(el.querySelector('.form-stub').textContent).toMatch('adding in c1');
  expect(button(el, 'Add videos')).toBeUndefined();
  expect(el.querySelector('[aria-label^="Edit"]')).toBeNull();
  await click(button(el, 'stub close'));
  expect(tutorialsApi.list).toHaveBeenCalledTimes(2);
  await click(el.querySelector('[aria-label="Edit \\"How to treat a fracture\\""]'));
  expect(el.querySelector('.form-stub').textContent).toMatch('editing v1');
});

test('deleting asks first, and the player and chips move on', async () => {
  useAuth.mockReturnValue({ canPublish: true });
  tutorialsApi.list.mockResolvedValueOnce([MP4, YT]).mockResolvedValueOnce([YT]);
  tutorialsApi.remove.mockResolvedValue({});
  const el = await render();
  await click(chip(el, 'Drills'));
  const confirm = jest.spyOn(window, 'confirm').mockReturnValueOnce(false).mockReturnValueOnce(true);
  await click(el.querySelector('[aria-label="Delete \\"Flood drill\\""]'));
  expect(tutorialsApi.remove).not.toHaveBeenCalled();
  await click(el.querySelector('[aria-label="Delete \\"Flood drill\\""]'));
  expect(confirm).toHaveBeenLastCalledWith("Delete 'Flood drill'? Residents will stop seeing it. The uploaded file is deleted too.");
  expect(tutorialsApi.remove).toHaveBeenCalledWith('v2');
  expect(chip(el, 'All').classList.contains('is-active')).toBe(true);
  expect(el.querySelector('iframe').getAttribute('src')).toMatch('2v8vlXgGXwE');
});

test('a failed delete says why', async () => {
  useAuth.mockReturnValue({ canPublish: true });
  tutorialsApi.list.mockResolvedValue([YT]);
  tutorialsApi.remove.mockRejectedValue(new Error("Your account isn't allowed to do this."));
  jest.spyOn(window, 'confirm').mockReturnValue(true);
  const el = await render();
  await click(el.querySelector('[aria-label^="Delete"]'));
  expect(el.querySelector('.wt-action-error').textContent).toBe("Your account isn't allowed to do this.");
});
```

`frontend/src/pages/Dashboard/admin/actionMeta.test.js`:

```js
import { actionMeta } from './adminShared';

test.each([
  ['ADD_VIDEO', 'Added a video'], ['EDIT_VIDEO', 'Edited a video'], ['DELETE_VIDEO', 'Deleted a video'],
  ['ADD_VIDEO_CATEGORY', 'Added a video category'], ['RENAME_VIDEO_CATEGORY', 'Renamed a video category'],
  ['DELETE_VIDEO_CATEGORY', 'Deleted a video category'],
])('%s reads "%s"', (action, label) => expect(actionMeta(action).label).toBe(label));
```

- [ ] **Step 2: Run them and see them fail**

Run frontend: `TutorialVideos actionMeta`. Expected: the new tests fail (no `Add videos` button; labels fall back to "Add video", etc.); Task 6's tests still pass.

- [ ] **Step 3: Implement the staff tools in `TutorialVideos.jsx` and add the six `ACTION_META` entries** after `DELETE_NEWS`.

- [ ] **Step 4: Run them and see them pass**

Run frontend: `TutorialVideos actionMeta whatToDoEditing`. Expected: all pass.

- [ ] **Step 5: Leave uncommitted**

---

### Task 10: Whole-feature check

**Files:** none new.

- [ ] **Step 1: Backend, the whole suite on its own test database**

From `backend/`, run the Global Constraints command with `tests apps` in place of `tests.test_tutorial_videos`. Expected: `OK` at the end of the log. Any failure outside this feature: compare with a run before your changes before calling it unrelated.

- [ ] **Step 2: Migration check**

Run: `.\venv\Scripts\python.exe manage.py makemigrations --check --dry-run`. Expected: `No changes detected`.

- [ ] **Step 3: Frontend, every test and the production build**

From `frontend/`: `$env:CI='true'; npm test -- --watchAll=false`, then `$env:CI='true'; npm run build`. Expected: all tests pass; `Compiled successfully.` with no warnings.

- [ ] **Step 4: Search for leftovers**

Run `git grep -n "VIDEOS" frontend/src` (expected: nothing) and `git grep -n "dangerouslySetInnerHTML" frontend/src/components/Tutorials` (expected: nothing).

- [ ] **Step 5: Report to the user, without migrating**

List the changed files with `git status --short`. Say that the new tables are **not** in the shared database yet. Going live means: back up the database, run `manage.py migrate tutorials`, then run the two checks by hand from the spec:
  - a 50 MB MP4 uploads, plays and can be skipped forward on Supabase;
  - the bucket's own file size limit is at least 50 MB.

Leave all of it uncommitted.
