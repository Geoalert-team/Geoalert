import uuid
from django.contrib.gis.db import models
from apps.accounts.models import User
from apps.barangays.models import Barangay


class HazardType(models.Model):
    id         = models.BigAutoField(primary_key=True, db_column='hztp_id')
    name       = models.CharField(max_length=50, unique=True, db_column='hztp_name')
    logo_class = models.CharField(max_length=50, blank=True, db_column='hztp_icon_class')
    is_active  = models.BooleanField(default=True, db_column='hztp_is_active')
    created_at = models.DateTimeField(auto_now_add=True, db_column='hztp_created_at')

    class Meta:
        db_table = 'hazard_type'

    def __str__(self):
        return self.name


class HazardZone(models.Model):
    SEVERITY_CHOICES = [
        ('Red',    'Extreme'),
        ('Orange', 'Moderate'),
        ('Green',  'Low'),
    ]
    STATUS_CHOICES = [
        ('Active',   'Active'),
        ('Resolved', 'Resolved'),
        ('Archived', 'Archived'),
    ]

    VERIFICATION_CHOICES = [
        ('Pending',   'Awaiting barangay confirmation'),
        ('Confirmed', 'Confirmed by barangay'),
        ('Disputed',  'Disputed by barangay'),
    ]

    id           = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, db_column='hzzn_id')
    barangay     = models.ForeignKey(Barangay, on_delete=models.SET_NULL, null=True, db_column='hzzn_brgy_id')
    published_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, db_column='hzzn_published_by')
    hazard_type  = models.ForeignKey(HazardType, on_delete=models.SET_NULL, null=True, db_column='hzzn_hztp_id')
    severity     = models.CharField(max_length=20, choices=SEVERITY_CHOICES, db_column='hzzn_severity')
    status       = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Active', db_column='hzzn_status')
    geometry     = models.MultiPolygonField(srid=4326, db_column='hzzn_polygon')
    description  = models.TextField(blank=True, db_column='hzzn_desc')
    activated_at = models.DateTimeField(auto_now_add=True, db_column='hzzn_activated_at')
    resolved_at  = models.DateTimeField(null=True, blank=True, db_column='hzzn_resolved_at')

    verification_status = models.CharField(
        max_length=20, choices=VERIFICATION_CHOICES, default='Pending',
        db_column='hzzn_verification_status',
    )
    verified_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='verified_hazard_zones',  # published_by already uses the default name
        db_column='hzzn_verified_by',
    )
    verified_at       = models.DateTimeField(null=True, blank=True, db_column='hzzn_verified_at')
    verification_note = models.TextField(blank=True, default='', db_column='hzzn_verification_note')

    class Meta:
        db_table = 'hazard_zone'

    def __str__(self):
        return f'{self.hazard_type} - {self.severity} - {self.status}'

    def reset_verification(self):
        """Call when severity or shape changes: the old confirmation no longer applies."""
        self.verification_status = 'Pending'
        self.verified_by         = None
        self.verified_at         = None
        self.verification_note   = ''


class HazardAlert(models.Model):
    id          = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, db_column='hzal_id')
    hazard_zone = models.ForeignKey(HazardZone, on_delete=models.CASCADE, db_column='hzal_hzzn_id')
    issued_by   = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, db_column='hzal_published_by')
    hazard_type = models.ForeignKey(HazardType, on_delete=models.SET_NULL, null=True, db_column='hzal_hztp_id')
    severity    = models.CharField(max_length=20, db_column='hzal_severity')
    notes       = models.TextField(blank=True, db_column='hzal_notes')
    created_at  = models.DateTimeField(auto_now_add=True, db_column='hzal_created_at')

    class Meta:
        db_table = 'hazard_alert'

    def __str__(self):
        return f'Alert - {self.hazard_type} - {self.severity}'
