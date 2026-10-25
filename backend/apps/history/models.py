import uuid
from django.db import models
from apps.barangays.models import Barangay, Purok
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

    # Every purok the event touched. One event counts once in each, however
    # many reports it had. Links go to purok rows, not shapes, so new purok
    # lines need no re-import (load_puroks keeps ids where names match).
    puroks = models.ManyToManyField(Purok, blank=True, related_name='history', db_table='historical_record_purok')

    # A fire as the BFP logs it. Blank or null means not known, never zero.
    alarm_level          = models.CharField(max_length=30, blank=True, default='', db_column='hstr_alarm_level')
    property_category    = models.CharField(max_length=20, blank=True, default='', db_column='hstr_property_category')
    property_subcategory = models.CharField(max_length=40, blank=True, default='', db_column='hstr_property_subcategory')
    damage_cost          = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True, db_column='hstr_damage_cost')
    structures_affected  = models.IntegerField(null=True, blank=True, db_column='hstr_structures_affected')
    injured_ff_male      = models.IntegerField(null=True, blank=True, db_column='hstr_injured_ff_male')
    injured_ff_female    = models.IntegerField(null=True, blank=True, db_column='hstr_injured_ff_female')
    injured_civ_male     = models.IntegerField(null=True, blank=True, db_column='hstr_injured_civ_male')
    injured_civ_female   = models.IntegerField(null=True, blank=True, db_column='hstr_injured_civ_female')
    fatal_ff_male        = models.IntegerField(null=True, blank=True, db_column='hstr_fatal_ff_male')
    fatal_ff_female      = models.IntegerField(null=True, blank=True, db_column='hstr_fatal_ff_female')
    fatal_civ_male       = models.IntegerField(null=True, blank=True, db_column='hstr_fatal_civ_male')
    fatal_civ_female     = models.IntegerField(null=True, blank=True, db_column='hstr_fatal_civ_female')
    # The address as the BFP typed it. Staff only: never on the public map.
    location_text        = models.TextField(blank=True, default='', db_column='hstr_location_text')
    # import_bfp_fires' key, so a re-import adds only new rows; null for
    # records made in the app.
    source_ref           = models.CharField(max_length=40, null=True, blank=True, unique=True, db_column='hstr_source_ref')

    class Meta:
        db_table = 'historical_record'
        ordering = ['-occurred_at']

    def __str__(self):
        return f'{self.hazard_type} — {self.barangay} — {self.occurred_at}'
