import uuid
from django.db import models
from apps.accounts.models import User
from apps.hazards.models import HazardType


class GuidanceContent(models.Model):

    PHASE_CHOICES = [
        ('Before', 'Before'),
        ('During', 'During'),
        ('After',  'After'),
    ]

    id             = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    hazard_type    = models.ForeignKey(HazardType, on_delete=models.CASCADE)
    created_by     = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    title          = models.CharField(max_length=200)
    body           = models.TextField()
    timeline_phase = models.CharField(max_length=10, choices=PHASE_CHOICES)
    is_published   = models.BooleanField(default=True)
    created_at     = models.DateTimeField(auto_now_add=True)
    updated_at     = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'guidance_content'
        ordering = ['hazard_type', 'timeline_phase']

    def __str__(self):
        return f'{self.hazard_type.name} — {self.timeline_phase} — {self.title}'