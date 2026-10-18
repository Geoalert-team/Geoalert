import os
import uuid
from django.contrib.gis.db.models import PointField
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone
from apps.accounts.models import User
from apps.barangays.models import Barangay
from apps.hazards.models import HazardType, HazardZone
from apps.history.models import HistoricalRecord


def report_photo_path(instance, filename):
    """
    Where an uploaded photo is stored — a key in the Supabase bucket, or a
    path under MEDIA_ROOT when storage falls back to local disk.

    The uploader's own filename is dropped and the photo row's id used
    instead. A name typed on a phone can carry anything — path separators, a
    second extension, characters the filesystem will not take — and keeping
    it buys nothing, since the report already says what the photo is of.

    Named after the photo rather than the report, because a report can carry
    several and they would otherwise collide.
    """
    ext = os.path.splitext(filename)[1].lower()[:10]
    return f'incident_reports/{timezone.now():%Y/%m}/{instance.id}{ext}'


class IncidentReport(models.Model):

    STATUS_CHOICES = [
        ('Pending',   'Pending'),
        ('Validated', 'Validated'),
        ('Rejected',  'Rejected'),
    ]

    id           = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, db_column='incr_id')
    submitted_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='submitted_reports', db_column='incr_submitted_by')
    barangay     = models.ForeignKey(Barangay, on_delete=models.SET_NULL, null=True, db_column='incr_brgy_id')
    hazard_type  = models.ForeignKey(HazardType, on_delete=models.SET_NULL, null=True, db_column='incr_hztp_id')
    description  = models.TextField(db_column='incr_desc')
    status       = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Pending', db_column='incr_status')
    review_note  = models.TextField(blank=True, db_column='incr_review_note')
    reviewed_by  = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='reviewed_reports', db_column='incr_reviewed_by')
    created_at   = models.DateTimeField(auto_now_add=True, db_column='incr_created_at')
    reviewed_at  = models.DateTimeField(null=True, blank=True, db_column='incr_reviewed_at')

    reporter_name     = models.CharField(max_length=150, blank=True, default='', db_column='incr_reporter_name')
    agency            = models.CharField(max_length=150, blank=True, default='', db_column='incr_agency')
    position          = models.CharField(max_length=100, blank=True, default='', db_column='incr_position')
    severity_estimate = models.CharField(max_length=20,  blank=True, default='', db_column='incr_severity_estimate')
    submitted_at      = models.DateTimeField(default=timezone.now, db_column='incr_submitted_at')
    validated_at      = models.DateTimeField(null=True, blank=True, db_column='incr_validated_at')
    validated_by      = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='validated_reports', db_column='incr_validated_by')
    hazard_zone       = models.ForeignKey(HazardZone, on_delete=models.SET_NULL, null=True, blank=True, db_column='incr_hzzn_id')
    historical_record = models.ForeignKey(HistoricalRecord, on_delete=models.SET_NULL, null=True, blank=True, db_column='incr_hstr_id')

    # Where the reporter saw it, tapped on a map. Optional: a report from a
    # barangay hall about a whole sitio has no single spot. When several
    # reports of one event carry a pin, DRRMO can draw the zone around them
    # instead of guessing where the edge is.
    location = PointField(srid=4326, null=True, blank=True, db_column='incr_location')

    casualties_dead    = models.IntegerField(null=True, blank=True, default=0, validators=[MinValueValidator(0)], db_column='incr_casualties_dead')
    casualties_injured = models.IntegerField(null=True, blank=True, default=0, validators=[MinValueValidator(0)], db_column='incr_casualties_injured')
    casualties_missing = models.IntegerField(null=True, blank=True, default=0, validators=[MinValueValidator(0)], db_column='incr_casualties_missing')
    displaced          = models.IntegerField(null=True, blank=True, default=0, validators=[MinValueValidator(0)], db_column='incr_displaced')

    class Meta:
        db_table = 'incident_report'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.hazard_type} — {self.barangay} — {self.status}'


class ReportPhoto(models.Model):
    """
    A photo attached to an incident report, one row per picture.

    A report usually needs more than one: a wide shot showing how far the
    water reaches, and a close one showing how deep it is at the door. A
    picture settles in a second what a description argues about, and gives
    the DRRMO something to check a report against before validating it.

    The file itself is never in this table. `image` holds the key in the
    Supabase bucket (or the path under MEDIA_ROOT when storage falls back to
    local disk), and Django builds a URL from it on the way out — signed and
    short-lived for Supabase. Storing the key rather than a finished URL is
    what lets the same row work under either backend, and stops a signed URL
    being written to the database on the day it was generated and served
    stale forever after.
    """
    id = models.UUIDField(
        primary_key=True, default=uuid.uuid4, editable=False, db_column='inrp_id',
    )
    report = models.ForeignKey(
        IncidentReport, on_delete=models.CASCADE,
        related_name='photos', db_column='inrp_incr_id',
    )
    # 200 rather than Django's default 100: a stored key is about 65
    # characters today, and the headroom costs nothing on a varchar.
    image = models.ImageField(upload_to=report_photo_path, max_length=200, db_column='inrp_url')
    uploaded_at = models.DateTimeField(auto_now_add=True, db_column='inrp_uploaded_at')

    class Meta:
        db_table = 'incident_report_photo'
        ordering = ['uploaded_at']

    def __str__(self):
        return f'Photo for {self.report_id}'
