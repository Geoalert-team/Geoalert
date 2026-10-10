import uuid
from django.db import models
from apps.barangays.models import Barangay
from apps.hazards.models import HazardType, HazardZone


class HistoricalRecord(models.Model):

    SEVERITY_CHOICES = [
        ('Red',    'Extreme'),
        ('Orange', 'Moderate'),
        ('Green',  'Low'),
    ]

    id                = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, db_column='hstr_id')
    barangay          = models.ForeignKey(Barangay, on_delete=models.SET_NULL, null=True, db_column='hstr_brgy_id')
    hazard_type       = models.ForeignKey(HazardType, on_delete=models.SET_NULL, null=True, db_column='hstr_hztp_id')
    hazard_zone       = models.ForeignKey(HazardZone, on_delete=models.SET_NULL, null=True, blank=True, db_column='hstr_hzzn_id')
    severity_level    = models.CharField(max_length=20, choices=SEVERITY_CHOICES, db_column='hstr_severity')
    description       = models.TextField(blank=True, db_column='hstr_desc')
    occurred_at       = models.DateTimeField(db_column='hstr_occurred_at')
    total_casualties  = models.IntegerField(null=True, blank=True, db_column='hstr_total_casualties')
    total_displaced   = models.IntegerField(null=True, blank=True, db_column='hstr_total_displaced')
    archived_at       = models.DateTimeField(auto_now_add=True, db_column='hstr_archived_at')
    is_sample         = models.BooleanField(default=False, db_column='hstr_is_sample')

    class Meta:
        db_table = 'historical_record'
        ordering = ['-occurred_at']

    def __str__(self):
        return f'{self.hazard_type} — {self.barangay} — {self.occurred_at}'
