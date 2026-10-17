import os
import uuid
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone
from apps.accounts.models import User
from apps.barangays.models import Barangay
from apps.hazards.models import HazardType, HazardZone
from apps.history.models import HistoricalRecord


def report_photo_path(instance, filename):
    """
    Where an uploaded photo is stored, under MEDIA_ROOT.

    The uploader's own filename is dropped and the report's id used instead.
    A name typed on a phone can carry anything — path separators, a second
    extension, characters the filesystem will not take — and keeping it buys
    nothing, since the report already says what the photo is of.
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

    # One optional photo of what the reporter is looking at. A picture of
    # knee-deep water on the national road settles in a second what a
    # description argues about, and gives DRRMO something to check a report
    # against before validating it.
    photo = models.ImageField(
        upload_to=report_photo_path, null=True, blank=True, db_column='incr_photo',
    )

    reporter_name     = models.CharField(max_length=150, blank=True, default='', db_column='incr_reporter_name')
    agency            = models.CharField(max_length=150, blank=True, default='', db_column='incr_agency')
    position          = models.CharField(max_length=100, blank=True, default='', db_column='incr_position')
    severity_estimate = models.CharField(max_length=20,  blank=True, default='', db_column='incr_severity_estimate')
    submitted_at      = models.DateTimeField(default=timezone.now, db_column='incr_submitted_at')
    validated_at      = models.DateTimeField(null=True, blank=True, db_column='incr_validated_at')
    validated_by      = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='validated_reports', db_column='incr_validated_by')
    hazard_zone       = models.ForeignKey(HazardZone, on_delete=models.SET_NULL, null=True, blank=True, db_column='incr_hzzn_id')
    historical_record = models.ForeignKey(HistoricalRecord, on_delete=models.SET_NULL, null=True, blank=True, db_column='incr_hstr_id')

    casualties_dead    = models.IntegerField(null=True, blank=True, default=0, validators=[MinValueValidator(0)], db_column='incr_casualties_dead')
    casualties_injured = models.IntegerField(null=True, blank=True, default=0, validators=[MinValueValidator(0)], db_column='incr_casualties_injured')
    casualties_missing = models.IntegerField(null=True, blank=True, default=0, validators=[MinValueValidator(0)], db_column='incr_casualties_missing')
    displaced          = models.IntegerField(null=True, blank=True, default=0, validators=[MinValueValidator(0)], db_column='incr_displaced')

    class Meta:
        db_table = 'incident_report'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.hazard_type} — {self.barangay} — {self.status}'
