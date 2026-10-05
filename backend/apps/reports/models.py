import uuid
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone
from apps.accounts.models import User
from apps.barangays.models import Barangay
from apps.hazards.models import HazardType, HazardZone
from apps.history.models import HistoricalRecord


class IncidentReport(models.Model):

    STATUS_CHOICES = [
        ('Pending',   'Pending'),
        ('Validated', 'Validated'),
        ('Rejected',  'Rejected'),
    ]

    id           = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    submitted_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='submitted_reports')
    barangay     = models.ForeignKey(Barangay, on_delete=models.SET_NULL, null=True)
    hazard_type  = models.ForeignKey(HazardType, on_delete=models.SET_NULL, null=True)
    description  = models.TextField()
    status       = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Pending')
    review_note  = models.TextField(blank=True)
    reviewed_by  = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='reviewed_reports')
    created_at   = models.DateTimeField(auto_now_add=True)
    reviewed_at  = models.DateTimeField(null=True, blank=True)

    # --- Columns that already exist in the shared Supabase table ---
    reporter_name     = models.CharField(max_length=150, blank=True, default='')
    agency            = models.CharField(max_length=150, blank=True, default='')
    position          = models.CharField(max_length=150, blank=True, default='')
    severity_estimate = models.CharField(max_length=50,  blank=True, default='')
    submitted_at      = models.DateTimeField(default=timezone.now)   # NOT NULL in the DB, no DB default
    validated_at      = models.DateTimeField(null=True, blank=True)
    validated_by      = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='validated_reports')
    hazard_zone       = models.ForeignKey(HazardZone, on_delete=models.SET_NULL, null=True, blank=True)
    historical_record = models.ForeignKey(HistoricalRecord, on_delete=models.SET_NULL, null=True, blank=True)

    # --- Casualties & injured ---
    casualties_dead    = models.IntegerField(null=True, blank=True, default=0, validators=[MinValueValidator(0)])
    casualties_injured = models.IntegerField(null=True, blank=True, default=0, validators=[MinValueValidator(0)])
    casualties_missing = models.IntegerField(null=True, blank=True, default=0, validators=[MinValueValidator(0)])
    displaced          = models.IntegerField(null=True, blank=True, default=0, validators=[MinValueValidator(0)])

    class Meta:
        db_table = 'incident_report'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.hazard_type} — {self.barangay} — {self.status}'
    
    