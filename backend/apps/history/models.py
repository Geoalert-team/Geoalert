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

    id                = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    barangay          = models.ForeignKey(Barangay, on_delete=models.SET_NULL, null=True)
    hazard_type       = models.ForeignKey(HazardType, on_delete=models.SET_NULL, null=True)
    hazard_zone       = models.ForeignKey(HazardZone, on_delete=models.SET_NULL, null=True, blank=True)
    severity_level    = models.CharField(max_length=20, choices=SEVERITY_CHOICES)
    description       = models.TextField(blank=True)
    occurred_at       = models.DateTimeField()
    total_casualties  = models.IntegerField(null=True, blank=True)
    total_displaced   = models.IntegerField(null=True, blank=True)
    archived_at       = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'historical_record'
        ordering = ['-occurred_at']

    def __str__(self):
        return f'{self.hazard_type} — {self.barangay} — {self.occurred_at}'