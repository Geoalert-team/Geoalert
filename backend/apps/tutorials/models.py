import uuid

from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower
from django.utils import timezone

from apps.accounts.models import User


def tutorial_video_path(instance, filename):
    """
    Where an uploaded video is stored: a key in the Supabase bucket, or a path
    under MEDIA_ROOT on local disk, as news photos are. The uploader's file
    name is dropped for the video's id; every upload is an MP4.
    """
    return f'tutorials/{timezone.now():%Y/%m}/{instance.id}.mp4'


class VideoCategory(models.Model):
    """
    A heading the What To Do page groups videos under ("First Aid", "Flood
    Preparedness"). Free text, not tied to a hazard type; unique ignoring case
    so "First aid" and "First Aid" can't both exist.
    """
    id         = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, db_column='vdct_id')
    name        = models.CharField(max_length=60, db_column='vdct_name')
    # Shown under the name in the What To Do page's header; optional
    description = models.CharField(max_length=300, blank=True, default='', db_column='vdct_description')
    created_at  = models.DateTimeField(auto_now_add=True, db_column='vdct_created_at')

    class Meta:
        db_table = 'video_category'
        ordering = [Lower('name')]
        constraints = [
            models.UniqueConstraint(Lower('name'), name='video_category_name_ci_unique'),
        ]

    def __str__(self):
        return self.name


class TutorialVideo(models.Model):
    """
    One tutorial video on the What To Do page: a YouTube video (only its ID is
    kept) or an MP4 that DRRMO uploaded. The check constraint keeps the two
    kinds apart, so a row is never both or neither.
    """
    SOURCES = [('youtube', 'YouTube link'), ('upload', 'MP4 upload')]

    id          = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, db_column='tvid_id')
    # PROTECT: deleting a category goes through the API, which deletes its videos and their
    # files first (apps/tutorials/views.py); a stray ORM delete can't orphan the files
    category    = models.ForeignKey(VideoCategory, on_delete=models.PROTECT, related_name='videos',
                                    db_column='tvid_vdct_id')
    title       = models.CharField(max_length=120, db_column='tvid_title')
    description = models.CharField(max_length=500, blank=True, db_column='tvid_description')
    source_type = models.CharField(max_length=10, choices=SOURCES, db_column='tvid_source_type')
    youtube_id  = models.CharField(max_length=11, blank=True, db_column='tvid_youtube_id')
    file        = models.FileField(upload_to=tutorial_video_path, max_length=200, blank=True, db_column='tvid_file')
    file_size   = models.PositiveIntegerField(null=True, blank=True, db_column='tvid_file_size')
    created_by  = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name='tutorial_videos', db_column='tvid_created_by')
    created_at  = models.DateTimeField(auto_now_add=True, db_column='tvid_created_at')
    updated_at  = models.DateTimeField(auto_now=True, db_column='tvid_updated_at')

    class Meta:
        db_table = 'tutorial_video'
        # Category A to Z, then the order they were added, so a series stays in order
        ordering = [Lower('category__name'), 'created_at']
        constraints = [
            models.CheckConstraint(
                name='tutorial_video_one_source',
                check=(Q(source_type='youtube') & ~Q(youtube_id='') & Q(file=''))
                | (Q(source_type='upload') & Q(youtube_id='') & ~Q(file='')),
            ),
        ]

    def __str__(self):
        return f'{self.category.name}: {self.title}'
