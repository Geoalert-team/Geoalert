import uuid
from django.db import models
from apps.accounts.models import User
from apps.hazards.models import HazardAlert


class Notification(models.Model):
    id           = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, db_column='notf_id')
    hazard_alert = models.ForeignKey(HazardAlert, on_delete=models.CASCADE, null=True, blank=True, related_name='notifications', db_column='notf_hzal_id')
    recipient    = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications', db_column='notf_recipient_id')
    content      = models.TextField(db_column='notf_content')
    is_read      = models.BooleanField(default=False, db_column='notf_is_read')
    sent_at      = models.DateTimeField(auto_now_add=True, db_column='notf_sent_at')
    read_at      = models.DateTimeField(null=True, blank=True, db_column='notf_read_at')

    class Meta:
        db_table = 'notification'
        ordering = ['-sent_at']

    def __str__(self):
        return f'{self.recipient} — {"read" if self.is_read else "unread"} — {self.sent_at:%Y-%m-%d %H:%M}'
