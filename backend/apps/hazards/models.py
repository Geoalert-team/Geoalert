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
        # Published in error and withdrawn. Deliberately separate from
        # Resolved: resolving means the hazard happened and is over, and it
        # writes a historical record that then counts in reports and trend
        # analysis. A zone published by mistake never happened, so filing it
        # as history would invent an incident. It is not a delete either —
        # HazardAlert cascades from the zone and Notification cascades from
        # the alert, so deleting the row would erase the evidence that an
        # alert was sent to residents.
        ('Retracted', 'Retracted'),
        # An Extreme alert waiting for a second DRRMO officer. Off the public
        # map and nobody notified yet. Goes Active when approved, or on its
        # own after APPROVAL_WINDOW so an empty office can't hold back a
        # typhoon warning.
        ('Awaiting_Approval', 'Awaiting approval'),
        # A fire that is out: the all-clear has gone and it is off the map,
        # but DRRMO has yet to record the BFP figures (alarm level,
        # casualties, damage) that close it into history.
        ('Resolving', 'Fire out, figures pending'),
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
    # The outline as the officer drew it, before cutting at the city
    # boundary. Reshaping starts from this: the saved geometry can follow
    # the coastline with hundreds of corners nobody could drag.
    outline      = models.PolygonField(srid=4326, null=True, blank=True, db_column='hzzn_outline')
    description  = models.TextField(blank=True, db_column='hzzn_desc')
    # Safety cordon around the hazard, in meters, or null for none. Metadata
    # on this one zone rather than a second zone: one hazard stays one zone,
    # one alert and one retraction. `geometry` is the hazard itself (the
    # burning block); the cordon is derived from it on demand, see
    # apps/hazards/geometry.py with_cordon(). It counts for who is alerted
    # and is drawn one level below the published severity.
    cordon_m     = models.IntegerField(null=True, blank=True, db_column='hzzn_cordon_m')
    activated_at = models.DateTimeField(auto_now_add=True, db_column='hzzn_activated_at')
    resolved_at  = models.DateTimeField(null=True, blank=True, db_column='hzzn_resolved_at')
    # A fire put out (status Resolving): when, and by which officer
    fire_out_at  = models.DateTimeField(null=True, blank=True, db_column='hzzn_fire_out_at')
    fire_out_by  = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                     related_name='fires_put_out', db_column='hzzn_fire_out_by')

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

    # DRRMO's answer to a dispute: "we checked, and it stays". Cleared when
    # a new dispute comes in, so a stale review never covers a fresh one.
    review_note = models.TextField(blank=True, default='', db_column='hzzn_review_note')
    reviewed_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='reviewed_hazard_zones',
        db_column='hzzn_reviewed_by',
    )
    reviewed_at = models.DateTimeField(null=True, blank=True, db_column='hzzn_reviewed_at')

    # Retraction. Set together, only by the retract endpoint, and never
    # cleared: a withdrawn alert stays on the record with who withdrew it,
    # when, and why.
    retracted_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='retracted_hazard_zones',
        db_column='hzzn_retracted_by',
    )
    retracted_at      = models.DateTimeField(null=True, blank=True, db_column='hzzn_retracted_at')
    retraction_reason = models.TextField(blank=True, default='', db_column='hzzn_retraction_reason')

    # Second approval for Extreme alerts. approved_by stays empty when the
    # alert went out on its own after the approval window (auto_released).
    approved_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='approved_hazard_zones',
        db_column='hzzn_approved_by',
    )
    approved_at   = models.DateTimeField(null=True, blank=True, db_column='hzzn_approved_at')
    auto_released = models.BooleanField(default=False, db_column='hzzn_auto_released')

    # Raising a live zone to Extreme waits for a second officer too, the same
    # as publishing an Extreme one. Until then the zone stays live at its
    # current severity and these say what was asked, by whom and when.
    pending_severity = models.CharField(max_length=20, blank=True, default='', db_column='hzzn_pending_severity')
    pending_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='pending_hazard_changes',
        db_column='hzzn_pending_by',
    )
    pending_at = models.DateTimeField(null=True, blank=True, db_column='hzzn_pending_at')

    # Generated by seed_fake_hazards; shown as sample data and removable with --clear
    is_sample = models.BooleanField(default=False, db_column='hzzn_is_sample')

    # When the publisher is next reminded that this zone is still Active.
    # Going live, any officer update and each reminder move it 24 hours on.
    next_nudge_at = models.DateTimeField(null=True, blank=True, db_column='hzzn_next_nudge_at')

    class Meta:
        db_table = 'hazard_zone'
        indexes = [models.Index(fields=['status', 'next_nudge_at'], name='hzzn_nudge_due_idx')]

    def __str__(self):
        return f'{self.hazard_type} - {self.severity} - {self.status}'

    def reset_verification(self):
        """
        Call when severity or shape changes: the old answers were about a
        different hazard, so every barangay is asked again. Deletes the
        per-barangay answers, so only call it on a zone that is being saved.
        """
        self.verification_status = 'Pending'
        self.verified_by         = None
        self.verified_at         = None
        self.verification_note   = ''
        self.clear_review()
        if self.pk:
            self.verifications.all().delete()

    def clear_review(self):
        self.review_note = ''
        self.reviewed_by = None
        self.reviewed_at = None

    def refresh_verification_summary(self):
        """
        Set the zone-level fields from the per-barangay answers, so older
        screens that only read verification_status keep working.

        Any dispute wins: one barangay saying "it isn't there" is what DRRMO
        needs to look at, even if another barangay confirmed its own part.
        The note and name are from the most recent answer with that status.
        """
        answers = list(self.verifications.select_related('answered_by').order_by('-answered_at'))
        disputed = [a for a in answers if a.status == 'Disputed']
        confirmed = [a for a in answers if a.status == 'Confirmed']
        latest = (disputed or confirmed or [None])[0]
        self.verification_status = 'Disputed' if disputed else 'Confirmed' if confirmed else 'Pending'
        self.verified_by = latest.answered_by if latest else None
        self.verified_at = latest.answered_at if latest else None
        self.verification_note = latest.note if latest else ''


class HazardVerification(models.Model):
    """
    One barangay's answer about one hazard zone.

    A zone crossing two barangays used to hold a single answer, so the
    second barangay to answer erased the first. Each barangay now keeps its
    own, and changing an answer replaces only that barangay's row.
    """
    STATUS_CHOICES = [
        ('Confirmed', 'Confirmed by barangay'),
        ('Disputed',  'Disputed by barangay'),
    ]

    id          = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, db_column='hzvf_id')
    hazard_zone = models.ForeignKey(HazardZone, on_delete=models.CASCADE, related_name='verifications', db_column='hzvf_hzzn_id')
    barangay    = models.ForeignKey(Barangay, on_delete=models.CASCADE, related_name='hazard_verifications', db_column='hzvf_brgy_id')
    status      = models.CharField(max_length=20, choices=STATUS_CHOICES, db_column='hzvf_status')
    note        = models.TextField(blank=True, default='', db_column='hzvf_note')
    answered_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='hazard_verifications', db_column='hzvf_answered_by')
    answered_at = models.DateTimeField(db_column='hzvf_answered_at')

    class Meta:
        db_table = 'hazard_verification'
        constraints = [
            models.UniqueConstraint(fields=['hazard_zone', 'barangay'], name='one_answer_per_barangay'),
        ]

    def __str__(self):
        return f'{self.barangay} {self.status} {self.hazard_zone_id}'


class HazardAlert(models.Model):
    id          = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, db_column='hzal_id')
    hazard_zone = models.ForeignKey(HazardZone, on_delete=models.CASCADE, db_column='hzal_hzzn_id')
    issued_by   = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, db_column='hzal_published_by')
    hazard_type = models.ForeignKey(HazardType, on_delete=models.SET_NULL, null=True, db_column='hzal_hztp_id')
    severity    = models.CharField(max_length=20, db_column='hzal_severity')
    notes       = models.TextField(blank=True, db_column='hzal_notes')
    created_at  = models.DateTimeField(auto_now_add=True, db_column='hzal_created_at')
    # When unread Extreme alerts were re-sent to barangay personnel who
    # hadn't opened them. Set once, so nobody is reminded twice.
    reminded_at = models.DateTimeField(null=True, blank=True, db_column='hzal_reminded_at')

    class Meta:
        db_table = 'hazard_alert'

    def __str__(self):
        return f'Alert - {self.hazard_type} - {self.severity}'


class ZoneFieldMark(models.Model):
    """
    A spot on the ground someone checked while a zone is live: "affected
    here" (water, fire, debris) or "clear here". Barangay staff and officers
    drop these on the map; the officer reshaping the zone sees which marks
    fall on the wrong side of the outline.

    A mark is evidence, not an edit: it never moves the zone by itself.
    """
    KIND_CHOICES = [
        ('Affected', 'Affected here'),
        ('Clear', 'Clear here'),
    ]

    id         = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, db_column='hzmk_id')
    zone       = models.ForeignKey(HazardZone, on_delete=models.CASCADE, related_name='field_marks', db_column='hzmk_hzzn_id')
    kind       = models.CharField(max_length=10, choices=KIND_CHOICES, db_column='hzmk_kind')
    location   = models.PointField(srid=4326, db_column='hzmk_location')
    note       = models.CharField(max_length=300, blank=True, default='', db_column='hzmk_note')
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='zone_field_marks', db_column='hzmk_created_by')
    created_at = models.DateTimeField(auto_now_add=True, db_column='hzmk_created_at')

    class Meta:
        db_table = 'hazard_zone_mark'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.kind} mark on {self.zone_id}'

    @property
    def inside_zone(self):
        geom = self.zone.geometry
        return bool(geom and geom.covers(self.location))

    @property
    def disagrees(self):
        """True when the mark says the outline is wrong at this spot."""
        inside = self.inside_zone
        return (self.kind == 'Affected' and not inside) or (self.kind == 'Clear' and inside)
