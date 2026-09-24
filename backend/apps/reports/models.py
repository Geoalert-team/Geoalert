import uuid
from django.db import models
from apps.accounts.models import User
from apps.barangays.models import Barangay
from apps.hazards.models import HazardType


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

    class Meta:
        db_table = 'incident_report'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.hazard_type} — {self.barangay} — {self.status}'