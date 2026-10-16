import uuid
from django.db import models
from apps.accounts.models import User


class AuditLog(models.Model):
    id             = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, db_column='audl_id')
    user           = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, db_column='audl_user_id')
    action         = models.CharField(max_length=100, db_column='audl_action')
    target_table   = models.CharField(max_length=100, blank=True, db_column='audl_target_table')
    target_id      = models.CharField(max_length=100, blank=True, db_column='audl_target_id')
    details        = models.TextField(blank=True, db_column='audl_detail')
    ip_address     = models.GenericIPAddressField(null=True, blank=True, db_column='audl_ip_address')
    created_at     = models.DateTimeField(auto_now_add=True, db_column='audl_created_at')

    class Meta:
        db_table = 'audit_log'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.action} by {self.user} at {self.created_at}'
