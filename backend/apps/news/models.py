import os
import uuid

from django.db import models
from django.utils import timezone

from apps.accounts.models import User


def news_photo_path(instance, filename):
    """
    Where an announcement's photo is stored: a key in the Supabase bucket, or
    a path under MEDIA_ROOT on local disk, as report photos are. The uploader's
    filename is dropped for the post's id (see report_photo_path).
    """
    ext = os.path.splitext(filename)[1].lower()[:10]
    return f'news/{timezone.now():%Y/%m}/{instance.id}{ext}'


class Announcement(models.Model):
    """
    A post DRRMO, an admin or BFP wrote for the public newsfeed. The feed's
    other posts, one per hazard alert that went out, are read from the hazard
    zones and not stored (apps/news/feed.py).
    """
    SOURCES = [('DRRMO', 'DRRMO'), ('BFP', 'BFP')]

    id         = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, db_column='anno_id')
    title      = models.CharField(max_length=150, db_column='anno_title')
    body       = models.TextField(db_column='anno_body')
    photo      = models.ImageField(upload_to=news_photo_path, max_length=200, blank=True, db_column='anno_photo')
    # The office it is from, set when posted: kept on the row so a post keeps
    # its office if the author's role later changes. The public never sees
    # the author's name.
    source     = models.CharField(max_length=10, choices=SOURCES, db_column='anno_source')
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name='announcements', db_column='anno_created_by')
    created_at = models.DateTimeField(auto_now_add=True, db_column='anno_created_at')
    updated_at = models.DateTimeField(auto_now=True, db_column='anno_updated_at')

    class Meta:
        db_table = 'announcement'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.source}: {self.title}'
