import math
from datetime import timedelta, timezone as dt_timezone

from django.utils import timezone
from rest_framework import serializers

from apps.rainwatch.models import RainForecastRun, RainWatchOverride
from apps.rainwatch.series import GRID

MAX_HOURS = 120
MAX_AGE = timedelta(days=10)
MAX_AHEAD = timedelta(hours=1)


class PointSerializer(serializers.Serializer):
    lat = serializers.FloatField()
    lon = serializers.FloatField()
    first_hour_start = serializers.DateTimeField()
    mm_per_hour = serializers.ListField(
        child=serializers.FloatField(min_value=0), allow_empty=False, max_length=MAX_HOURS)

    def validate_mm_per_hour(self, values):
        if not all(math.isfinite(v) for v in values):
            raise serializers.ValidationError('Values must be finite.')
        return values


class ForecastRunSerializer(serializers.Serializer):
    source = serializers.ChoiceField(choices=[c[0] for c in RainForecastRun.SOURCES])
    init_time = serializers.DateTimeField()
    job_version = serializers.CharField(max_length=40, required=False, allow_blank=True, default='')
    points = PointSerializer(many=True)

    def validate_init_time(self, value):
        value = value.astimezone(dt_timezone.utc)  # the hour check is on UTC, whatever the server zone
        if value.minute or value.second or value.microsecond or value.hour % 6:
            raise serializers.ValidationError('init_time must be on a 00, 06, 12 or 18 UTC hour.')
        now = timezone.now()
        if value > now + MAX_AHEAD:
            raise serializers.ValidationError('init_time is in the future.')
        if value < now - MAX_AGE:
            raise serializers.ValidationError('init_time is older than 10 days.')
        return value

    def validate_points(self, points):
        found = sorted((p['lat'], p['lon']) for p in points)
        if found != sorted(GRID):
            raise serializers.ValidationError('Expected exactly the 4 grid points.')
        if len({len(p['mm_per_hour']) for p in points}) != 1:
            raise serializers.ValidationError('All points need the same number of values.')
        return points


MAX_OVERRIDE = timedelta(hours=72)


class OverrideSerializer(serializers.ModelSerializer):
    """Reads and writes a DRRMO override; the creator and start are set by the server."""
    created_by_name = serializers.CharField(source='created_by.full_name', read_only=True)
    hazard = serializers.ChoiceField(choices=[c[0] for c in RainWatchOverride.HAZARDS])
    level = serializers.ChoiceField(choices=[c[0] for c in RainWatchOverride.LEVELS])
    note = serializers.CharField(max_length=300)  # blank is refused and spaces are trimmed by default

    class Meta:
        model = RainWatchOverride
        fields = ['id', 'hazard', 'level', 'starts_at', 'ends_at', 'note', 'created_by_name', 'cancelled_at']
        read_only_fields = ['id', 'starts_at', 'cancelled_at']

    def validate_ends_at(self, value):
        now = timezone.now()
        if value <= now:
            raise serializers.ValidationError('ends_at must be in the future.')
        if value > now + MAX_OVERRIDE:
            raise serializers.ValidationError('ends_at can be at most 72 hours from now.')
        return value
