from django.contrib.postgres.fields import ArrayField
from django.db import models
from django.utils import timezone

from apps.accounts.models import User


class InsertOnly(models.Model):
    """Rows are added and never changed: a second save() of a stored row is refused."""

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if self.pk is not None and not self._state.adding:
            raise ValueError(f'{type(self).__name__} rows are insert-only')
        super().save(*args, **kwargs)


class RainForecastRun(InsertOnly):
    """One forecast run (GFS) posted by the scheduled job. Kept forever.

    The one change ever made: a run first stored short (a gap-fill run) is upgraded when the same run
    arrives longer; the ingest view replaces its series, hours, job_version and received_at with update().
    """

    SOURCES = [('gfs-nomads', 'gfs-nomads'), ('gfs-dynamical', 'gfs-dynamical')]

    source = models.CharField(max_length=20, choices=SOURCES)
    init_time = models.DateTimeField()
    received_at = models.DateTimeField(auto_now_add=True)
    job_version = models.CharField(max_length=40, blank=True)
    hours = models.PositiveSmallIntegerField()

    class Meta:
        db_table = 'rain_forecast_run'
        constraints = [models.UniqueConstraint(fields=['source', 'init_time'], name='rain_forecast_run_unique')]


class RainForecastSeries(InsertOnly):
    """Hourly rain (mm) at one grid point of one run. Four rows per run."""

    run = models.ForeignKey(RainForecastRun, on_delete=models.PROTECT, related_name='series')
    lat = models.DecimalField(max_digits=5, decimal_places=2)
    lon = models.DecimalField(max_digits=6, decimal_places=2)
    first_hour_start = models.DateTimeField()
    mm_per_hour = ArrayField(models.FloatField())

    class Meta:
        db_table = 'rain_forecast_series'
        constraints = [models.UniqueConstraint(fields=['run', 'lat', 'lon'], name='rain_forecast_series_unique')]


class PagasaAlert(models.Model):
    """One PAGASA CAP alert, kept for the record."""

    identifier = models.CharField(max_length=200, unique=True)
    sent = models.DateTimeField(null=True, blank=True)
    msg_type = models.CharField(max_length=20, blank=True)
    references = models.TextField(blank=True)
    event = models.CharField(max_length=200, blank=True)
    category = models.CharField(max_length=50, blank=True)
    response_type = models.CharField(max_length=50, blank=True)
    urgency = models.CharField(max_length=50, blank=True)
    severity = models.CharField(max_length=50, blank=True)
    certainty = models.CharField(max_length=50, blank=True)
    effective = models.DateTimeField(null=True, blank=True)
    expires = models.DateTimeField(null=True, blank=True)
    headline = models.TextField(blank=True)
    description = models.TextField(blank=True)
    area_desc = models.TextField(blank=True)
    covers_talisay = models.BooleanField(default=False)
    cap_url = models.URLField(max_length=500, blank=True)
    raw_xml = models.TextField(blank=True)
    fetched_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'pagasa_alert'

    def __str__(self):
        return f'{self.event} ({self.identifier})'


class RainWatchOverride(models.Model):
    """A colour DRRMO sets by hand. Rows are only added; cancelling fills in the two cancel fields."""

    HAZARDS = [('Flood', 'Flood'), ('Landslide', 'Landslide'), ('Both', 'Both')]
    LEVELS = [('Yellow', 'Yellow'), ('Orange', 'Orange'), ('Red', 'Red')]

    hazard = models.CharField(max_length=10, choices=HAZARDS)
    level = models.CharField(max_length=10, choices=LEVELS)
    starts_at = models.DateTimeField(default=timezone.now)
    ends_at = models.DateTimeField()
    note = models.CharField(max_length=300)
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True, related_name='+')

    class Meta:
        db_table = 'rain_watch_override'

    def __str__(self):
        return f'{self.hazard} {self.level} until {self.ends_at:%Y-%m-%d %H:%M}'


def _cutoffs():
    return ArrayField(models.FloatField(), size=3)


class RainWatchRules(InsertOnly):
    """The colour cut-offs. Insert-only: the newest row is in force, so changes keep their history."""

    flood_dry = _cutoffs()
    flood_wet = _cutoffs()
    slide_dry = _cutoffs()
    slide_wet = _cutoffs()
    wet_14day_mm = models.FloatField()
    flood_exposure_min = models.FloatField()
    steep_share_min = models.FloatField()
    stale_hours = models.PositiveSmallIntegerField()
    note = models.CharField(max_length=300, blank=True)
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'rain_watch_rules'

    @classmethod
    def current(cls):
        return cls.objects.order_by('-created_at', '-id').first()

    def as_rules(self):
        from apps.rainwatch.rules import Rules

        return Rules(
            flood_dry=tuple(float(v) for v in self.flood_dry),
            flood_wet=tuple(float(v) for v in self.flood_wet),
            slide_dry=tuple(float(v) for v in self.slide_dry),
            slide_wet=tuple(float(v) for v in self.slide_wet),
            wet_14day_mm=float(self.wet_14day_mm),
            flood_exposure_min=float(self.flood_exposure_min),
            steep_share_min=float(self.steep_share_min),
            stale_hours=int(self.stale_hours),
        )

    def __str__(self):
        return f'Rules {self.created_at:%Y-%m-%d}: {self.note}'
