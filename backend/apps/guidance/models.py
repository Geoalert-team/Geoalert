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

    id             = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, db_column='gdcn_id')
    hazard_type    = models.ForeignKey(HazardType, on_delete=models.CASCADE, db_column='gdcn_hztp_id')
    created_by     = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, db_column='gdcn_created_by')
    title          = models.CharField(max_length=200, db_column='gdcn_title')
    body           = models.TextField(db_column='gdcn_body')
    timeline_phase = models.CharField(max_length=10, choices=PHASE_CHOICES, db_column='gdcn_phase')
    is_published   = models.BooleanField(default=True, db_column='gdcn_is_active')
    created_at     = models.DateTimeField(auto_now_add=True, db_column='gdcn_created_at')
    updated_at     = models.DateTimeField(auto_now=True, db_column='gdcn_updated_at')

    class Meta:
        db_table = 'guidance_content'
        ordering = ['hazard_type', 'timeline_phase']

    def __str__(self):
        return f'{self.hazard_type.name} — {self.timeline_phase} — {self.title}'
