import uuid
from django.db import models
from apps.accounts.models import User


class AuditLog(models.Model):
    id             = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user           = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    action         = models.CharField(max_length=100)
    target_table   = models.CharField(max_length=100, blank=True)
    target_id      = models.CharField(max_length=100, blank=True)
    details        = models.TextField(blank=True)
    ip_address     = models.GenericIPAddressField(null=True, blank=True)
    created_at     = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'audit_log'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.action} by {self.user} at {self.created_at}'