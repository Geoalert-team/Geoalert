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


class SystemConfig(models.Model):
    """
    One setting a System Administrator can change (F8 configuration panel).
    Maps onto the ERD's system_config table. What each key means, its
    default and its allowed range live in utils/system_settings.py.
    """
    id         = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, db_column='sysc_id')
    key        = models.CharField(max_length=100, unique=True, db_column='sysc_key')
    value      = models.TextField(default='', db_column='sysc_value')
    updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, db_column='sysc_updated_by')
    updated_at = models.DateTimeField(auto_now=True, db_column='sysc_updated_at')

    class Meta:
        db_table = 'system_config'
        ordering = ['key']

    def __str__(self):
        return f'{self.key} = {self.value}'
