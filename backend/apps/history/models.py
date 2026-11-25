import uuid
from django.contrib.gis.db.models import PointField
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
    # A flood or landslide as the flood and landslide log has it (columns
    # H-M; G is the hazard type). Blank or null means not known, never zero.
    hazard_subcategory   = models.CharField(max_length=60, blank=True, default='', db_column='hstr_hazard_subcategory')
    cause                = models.CharField(max_length=200, blank=True, default='', db_column='hstr_cause')
    injured              = models.IntegerField(null=True, blank=True, db_column='hstr_injured')
    fatalities           = models.IntegerField(null=True, blank=True, db_column='hstr_fatalities')
    families_affected    = models.IntegerField(null=True, blank=True, db_column='hstr_families_affected')
    persons_affected     = models.IntegerField(null=True, blank=True, db_column='hstr_persons_affected')
    # The address as the BFP typed it. Staff only: never on the public map.
    location_text        = models.TextField(blank=True, default='', db_column='hstr_location_text')
    # import_bfp_fires' key, so a re-import adds only new rows; null for
    # records made in the app.
    source_ref           = models.CharField(max_length=40, null=True, blank=True, unique=True, db_column='hstr_source_ref')
    # Where it happened, only when the source names the spot: the map pin
    # of the purok or sitio it names, or a landmark it names. Null when the
    # source names only a barangay, whose outline is then all that is known.
    # Written by place_history_records. Staff only, like location_text.
    LOCATION_PRECISIONS = [
        ('place',    'Named purok or sitio'),
        ('landmark', 'Named landmark'),
    ]
    location             = PointField(srid=4326, null=True, blank=True, db_column='hstr_location')
    location_precision   = models.CharField(max_length=20, blank=True, default='', choices=LOCATION_PRECISIONS,
                                            db_column='hstr_location_precision')
    location_basis       = models.CharField(max_length=300, blank=True, default='', db_column='hstr_location_basis')
    # Where the event was read: the flood and landslide log's column P (a
    # news story or report, with its date). Blank for fires and app records.
    source               = models.CharField(max_length=300, blank=True, default='', db_column='hstr_source')

    class Meta:
        db_table = 'historical_record'
        ordering = ['-occurred_at']

    def __str__(self):
        return f'{self.hazard_type} — {self.barangay} — {self.occurred_at}'


# What a prediction log row may hold (checked by the database)
LOG_HAZARDS = ['Fire', 'Flood', 'Landslide']
LOG_KINDS = ['day', 'month']
LOG_LEVELS = ['Low', 'Moderate', 'High']


class HazardPredictionLog(models.Model):
    """
    A chance the app showed, kept so it can be scored against what happened
    (spec 3.4; written by apps/history/prediction_log.py). Rows are only ever
    added: a trigger (migration 0008) refuses any UPDATE or DELETE.

    `day`: flood's or landslide's chance for one rain day. `month`: a hazard's
    chance for the month as the forecast page shows it, with its level.
    """
    id              = models.BigAutoField(primary_key=True, db_column='hzpl_id')
    hazard          = models.TextField(db_column='hzpl_hazard')
    barangay        = models.ForeignKey(Barangay, on_delete=models.PROTECT, db_column='hzpl_brgy_id')
    kind            = models.TextField(db_column='hzpl_kind')
    # the day, or the month's first day
    period_start    = models.DateField(db_column='hzpl_period_start')
    # the Asia/Manila date the row was written
    issued_on       = models.DateField(db_column='hzpl_issued_on')
    # flood and landslide: '<model in use>@<report sha1, 12 characters>'; fire: '<model>@<records tag sha1, 12>'
    model_version   = models.TextField(db_column='hzpl_model_version')
    probability     = models.FloatField(db_column='hzpl_probability')
    # fire only
    expected_events = models.FloatField(null=True, db_column='hzpl_expected_events')
    # on month rows; null on day rows (levels are monthly)
    level           = models.TextField(null=True, db_column='hzpl_level')
    # day rows: the rain sums used, the rain source, the storm flag and name, outside_training;
    # month rows: method, in_training, the scenario years
    inputs          = models.JSONField(db_column='hzpl_inputs')
    created_at      = models.DateTimeField(auto_now_add=True, db_column='hzpl_created_at')

    class Meta:
        db_table = 'hazard_prediction_log'
        constraints = [
            models.UniqueConstraint(fields=['hazard', 'barangay', 'kind', 'period_start', 'issued_on', 'model_version'],
                                    name='hazard_prediction_log_unique'),
            models.CheckConstraint(check=models.Q(hazard__in=LOG_HAZARDS), name='hazard_prediction_log_hazard'),
            models.CheckConstraint(check=models.Q(kind__in=LOG_KINDS), name='hazard_prediction_log_kind'),
            models.CheckConstraint(check=models.Q(level__isnull=True) | models.Q(level__in=LOG_LEVELS),
                                   name='hazard_prediction_log_level'),
            models.CheckConstraint(check=models.Q(probability__gte=0) & models.Q(probability__lte=1),
                                   name='hazard_prediction_log_probability'),
        ]
        indexes = [models.Index(fields=['hazard', 'period_start'])]

    def __str__(self):
        return f'{self.hazard} {self.kind} {self.period_start} — {self.barangay_id} — {self.probability}'


FIRE_LOG_LEVELS = ['Red', 'Orange', 'Green']


class FirePurokPredictionLog(models.Model):
    """
    A purok's fire chance and level for a month as the map showed it, kept so
    the fire model can be scored on fires that came after (spec 8.3; written
    by apps/history/prediction_log.py, one snapshot per Manila day). Rows are
    only ever added: a trigger (migration 0010) refuses any UPDATE or DELETE.

    The purok is kept as a plain id and its name, not a foreign key: a purok
    reload deletes and recreates rows, and must never touch the log.
    """
    id            = models.BigAutoField(primary_key=True, db_column='fppl_id')
    purok_id      = models.BigIntegerField(db_column='fppl_prk_id')
    purok_name    = models.TextField(db_column='fppl_prk_name')
    barangay      = models.ForeignKey(Barangay, on_delete=models.PROTECT, db_column='fppl_brgy_id')
    # the month's first day
    period_start  = models.DateField(db_column='fppl_period_start')
    # the Asia/Manila date the row was written
    issued_on     = models.DateField(db_column='fppl_issued_on')
    # '<model family>@<sha1 of features, fires and settings, 12 characters>' (train_fire_model)
    model_version = models.TextField(db_column='fppl_model_version')
    probability   = models.FloatField(db_column='fppl_probability')
    level         = models.TextField(db_column='fppl_level')
    limited_data  = models.BooleanField(db_column='fppl_limited_data')
    created_at    = models.DateTimeField(auto_now_add=True, db_column='fppl_created_at')

    class Meta:
        db_table = 'fire_purok_prediction_log'
        constraints = [
            models.UniqueConstraint(fields=['purok_id', 'period_start', 'issued_on', 'model_version'],
                                    name='fire_purok_prediction_log_unique'),
            models.CheckConstraint(check=models.Q(probability__gte=0) & models.Q(probability__lte=1),
                                   name='fire_purok_prediction_log_probability'),
            models.CheckConstraint(check=models.Q(level__in=FIRE_LOG_LEVELS), name='fire_purok_prediction_log_level'),
        ]
        indexes = [models.Index(fields=['period_start', 'issued_on'])]

    def __str__(self):
        return f'{self.purok_name} {self.period_start} — {self.probability} {self.level}'


FLOOD_LOG_SOURCES = ['model', 'noah', 'geoalert']  # 'geoalert': an own-data fit (migration 0012)


class FloodPurokSusceptibilityLog(models.Model):
    """
    A purok's flood susceptibility class as a published flood model version
    gave it, kept so the model can be checked against floods that came after
    (spec 8.3; written by apps/history/prediction_log.py once per version).
    Rows are only ever added: a trigger (migration 0011) refuses any UPDATE or
    DELETE. The purok is a plain id and its name, never a foreign key, so a
    purok reload never touches the log.
    """
    id                  = models.BigAutoField(primary_key=True, db_column='fpsl_id')
    purok_id            = models.BigIntegerField(db_column='fpsl_prk_id')
    purok_name          = models.TextField(db_column='fpsl_prk_name')
    barangay            = models.ForeignKey(Barangay, on_delete=models.PROTECT, db_column='fpsl_brgy_id')
    # '<model or noah_fallback>@<sha1 of features, labels and settings, 12 characters>' (train_flood_model)
    model_version       = models.TextField(db_column='fpsl_model_version')
    source              = models.TextField(db_column='fpsl_source')
    # null when the purok is not assessed
    level               = models.TextField(null=True, db_column='fpsl_level')
    score               = models.FloatField(null=True, db_column='fpsl_score')
    uncertain           = models.BooleanField(db_column='fpsl_uncertain')
    not_assessed_reason = models.TextField(default='', blank=True, db_column='fpsl_not_assessed_reason')
    outlines_version    = models.TextField(db_column='fpsl_outlines_version')
    # the Asia/Manila date the version was first logged
    published_on        = models.DateField(db_column='fpsl_published_on')
    created_at          = models.DateTimeField(auto_now_add=True, db_column='fpsl_created_at')

    class Meta:
        db_table = 'flood_purok_susceptibility_log'
        constraints = [
            models.UniqueConstraint(fields=['purok_id', 'model_version'], name='flood_purok_susceptibility_log_unique'),
            models.CheckConstraint(check=models.Q(level__isnull=True) | models.Q(level__in=FIRE_LOG_LEVELS),
                                   name='flood_purok_susceptibility_log_level'),
            models.CheckConstraint(check=models.Q(source__in=FLOOD_LOG_SOURCES),
                                   name='flood_purok_susceptibility_log_source'),
        ]
        indexes = [models.Index(fields=['model_version'])]

    def __str__(self):
        return f'{self.purok_name} {self.model_version} — {self.level or "not assessed"}'


class LandslidePurokSusceptibilityLog(models.Model):
    """
    A purok's landslide susceptibility class as a published landslide model
    version gave it, kept so the model can be checked against landslides that
    came after (written by apps/history/prediction_log.py once per version).
    Rows are only ever added: a trigger (migration 0013) refuses any UPDATE or
    DELETE. The purok is a plain id and its name, never a foreign key, so a
    purok reload never touches the log.
    """
    id                  = models.BigAutoField(primary_key=True, db_column='lpsl_id')
    purok_id            = models.BigIntegerField(db_column='lpsl_purok_id')
    purok_name          = models.TextField(db_column='lpsl_purok_name')
    barangay            = models.ForeignKey(Barangay, on_delete=models.PROTECT, db_column='lpsl_brgy_id')
    model_version       = models.TextField(db_column='lpsl_model_version')
    source              = models.TextField(db_column='lpsl_source')
    # null when the purok is not assessed
    level               = models.TextField(null=True, db_column='lpsl_level')
    score               = models.FloatField(null=True, db_column='lpsl_score')
    uncertain           = models.BooleanField(db_column='lpsl_uncertain')
    not_assessed_reason = models.TextField(default='', blank=True, db_column='lpsl_not_assessed_reason')
    outlines_version    = models.TextField(db_column='lpsl_outlines_version')
    # the Asia/Manila date the version was first logged
    published_on        = models.DateField(db_column='lpsl_published_on')
    created_at          = models.DateTimeField(auto_now_add=True, db_column='lpsl_created_at')

    class Meta:
        db_table = 'landslide_purok_susceptibility_log'
        constraints = [
            models.UniqueConstraint(fields=['purok_id', 'model_version'],
                                    name='landslide_purok_susceptibility_log_unique'),
            models.CheckConstraint(check=models.Q(level__isnull=True) | models.Q(level__in=FIRE_LOG_LEVELS),
                                   name='landslide_purok_susceptibility_log_level'),
            models.CheckConstraint(check=models.Q(source__in=FLOOD_LOG_SOURCES),
                                   name='landslide_purok_susceptibility_log_source'),
        ]
        indexes = [models.Index(fields=['model_version'], name='lpsl_model_version_idx')]

    def __str__(self):
        return f'{self.purok_name} {self.model_version} — {self.level or "not assessed"}'


MODEL_FIT_HAZARDS = ['fire', 'flood', 'landslide']  # landslide since history 0014
MODEL_FIT_RESULTS = ['switched', 'kept', 'not_tried', 'skipped', 'failed']


class ModelFit(models.Model):
    """
    One automatic retraining attempt (the GitHub Actions job posts each one;
    apps/history/model_fits.py stores it). A fit goes live only on a pass:
    at most one live row per hazard, enforced below. Fits that did not go
    live are kept with their model so an admin can undo to an earlier one.
    """
    HAZARDS = tuple((h, h) for h in MODEL_FIT_HAZARDS)
    RESULTS = tuple((r, r) for r in MODEL_FIT_RESULTS)

    id               = models.BigAutoField(primary_key=True, db_column='mfit_id')
    hazard           = models.TextField(choices=HAZARDS, db_column='mfit_hazard')
    result           = models.TextField(choices=RESULTS, db_column='mfit_result')
    reason           = models.TextField(db_column='mfit_reason')
    version          = models.TextField(blank=True, default='', db_column='mfit_version')
    outlines_version = models.TextField(blank=True, default='', db_column='mfit_outlines_version')
    built_at         = models.DateTimeField(null=True, db_column='mfit_built_at')
    model            = models.JSONField(null=True, db_column='mfit_model')
    report           = models.JSONField(null=True, db_column='mfit_report')
    is_live          = models.BooleanField(default=False, db_column='mfit_is_live')
    created_at       = models.DateTimeField(auto_now_add=True, db_column='mfit_created_at')

    class Meta:
        db_table = 'model_fit'
        ordering = ['-created_at', '-id']
        constraints = [
            models.CheckConstraint(check=models.Q(hazard__in=MODEL_FIT_HAZARDS), name='model_fit_hazard'),
            models.CheckConstraint(check=models.Q(result__in=MODEL_FIT_RESULTS), name='model_fit_result'),
            models.UniqueConstraint(fields=['hazard'], condition=models.Q(is_live=True),
                                    name='model_fit_one_live_per_hazard'),
        ]

    def __str__(self):
        return f'{self.hazard} {self.result} {self.version or "-"}'
