import json

from rest_framework import serializers
from rest_framework_gis.serializers import GeoFeatureModelSerializer
from rest_framework_gis.fields import GeometryField
from django.contrib.gis.geos import MultiPolygon, Polygon
from apps.barangays.models import Barangay
from apps.hazards.geometry import (
    CORDON_MAX_M, CORDON_MIN_M, city_outline, clip_to_city, cordon_ring, main_barangay, with_cordon,
)
from apps.hazards.models import HazardType, HazardZone, HazardAlert, HazardVerification
from apps.accounts.serializers import UserSerializer


class HazardTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model  = HazardType
        fields = ['id', 'name', 'logo_class', 'is_active']


class HazardVerificationSerializer(serializers.ModelSerializer):
    """One barangay's answer about a zone."""
    barangay_name = serializers.CharField(source='barangay.name', read_only=True, default=None)
    answered_by_name = serializers.CharField(source='answered_by.full_name', read_only=True, default=None)

    class Meta:
        model = HazardVerification
        fields = ['barangay', 'barangay_name', 'status', 'note', 'answered_by_name', 'answered_at']


class HazardZoneGeoSerializer(GeoFeatureModelSerializer):
    """
    Returns hazard zones as proper GeoJSON FeatureCollection.
    This is what Leaflet.js consumes directly.
    """
    hazard_type_name = serializers.CharField(
        source='hazard_type.name', read_only=True, default=None
    )
    barangay_name = serializers.CharField(
        source='barangay.name', read_only=True, default=None
    )
    verified_by_name = serializers.CharField(
        source='verified_by.full_name', read_only=True, default=None
    )
    approved_by_name = serializers.CharField(
        source='approved_by.full_name', read_only=True, default=None
    )
    verifications = HazardVerificationSerializer(many=True, read_only=True)
    reviewed_by_name = serializers.CharField(
        source='reviewed_by.full_name', read_only=True, default=None
    )
    # As drawn, before cutting at the city boundary: what reshaping starts from
    outline = GeometryField(read_only=True)
    # With ?bbox=: 'whole' when the zone lies entirely inside the box
    # (ST_Within), 'partial' when it crosses the edge. Null without a bbox.
    in_view = serializers.SerializerMethodField()
    # The area the zone reaches with its cordon, as GeoJSON, or null when it
    # has none. The same shape the alert was routed on, so the ring the map
    # draws is exactly the area whose barangays were told.
    cordon = serializers.SerializerMethodField()
    # The same cordon without the hazard inside it, for drawing: the map
    # hatches this ring so it never looks like a hazard level of its own.
    cordon_ring = serializers.SerializerMethodField()

    def _reach(self, obj):
        """The zone grown by its cordon, buffered once per zone per response."""
        if not obj.cordon_m or obj.geometry is None:
            return None
        memo = self.context.setdefault('reach', {})
        if obj.pk not in memo:
            city = self.context.get('city')
            if city is None and 'city' not in self.context:
                # Looked up once per response, not once per zone
                city = self.context['city'] = city_outline()
            try:
                memo[obj.pk] = with_cordon(obj.geometry, obj.cordon_m, city)
            except Exception:
                memo[obj.pk] = None
        return memo[obj.pk]

    def get_cordon(self, obj):
        reach = self._reach(obj)
        return json.loads(reach.geojson) if reach is not None else None

    def get_cordon_ring(self, obj):
        ring = cordon_ring(obj.geometry, self._reach(obj))
        return json.loads(ring.geojson) if ring is not None else None

    def get_in_view(self, obj):
        within = self.context.get('within_ids')
        if within is None:
            return None
        return 'whole' if obj.id in within else 'partial'

    class Meta:
        model       = HazardZone
        geo_field   = 'geometry'
        fields = [
            'id', 'barangay', 'barangay_name', 'hazard_type_name',
            'severity', 'status', 'description',
            'activated_at', 'resolved_at',
            'is_sample',
            # Ground confirmation, so the map can show whether anyone in the
            # barangay has actually been out to look.
            'verification_status', 'verification_note',
            'verified_at', 'verified_by_name',
            # Second approval for Extreme alerts
            'approved_by_name', 'approved_at', 'auto_released',
            # Each barangay's own answer, and DRRMO's answer to a dispute
            'verifications', 'review_note', 'reviewed_at', 'reviewed_by_name',
            'outline',
            # A raise to Extreme waiting for a second officer
            'pending_severity', 'pending_at',
            'in_view',
            # Safety cordon: its width, the area it reaches, and that area
            # less the hazard
            'cordon_m', 'cordon', 'cordon_ring',
        ]


class HazardZoneSerializer(serializers.ModelSerializer):
    hazard_type = HazardTypeSerializer(read_only=True)
    barangay_name = serializers.CharField(
        source='barangay.name', read_only=True, default=None
    )
    verified_by_name = serializers.CharField(
        source='verified_by.full_name', read_only=True, default=None
    )
    retracted_by_name = serializers.CharField(
        source='retracted_by.full_name', read_only=True, default=None
    )
    published_by_name = serializers.CharField(
        source='published_by.full_name', read_only=True, default=None
    )
    approved_by_name = serializers.CharField(
        source='approved_by.full_name', read_only=True, default=None
    )
    verifications = HazardVerificationSerializer(many=True, read_only=True)
    reviewed_by_name = serializers.CharField(
        source='reviewed_by.full_name', read_only=True, default=None
    )

    class Meta:
        model  = HazardZone
        fields = [
            'id', 'barangay', 'barangay_name', 'published_by', 'hazard_type',
            'severity', 'status', 'description',
            'activated_at', 'resolved_at',
            'is_sample',
            'verification_status', 'verification_note',
            'verified_at', 'verified_by_name',
            # Withdrawal, so the DRRMO list can say who withdrew it and why
            'retracted_at', 'retracted_by_name', 'retraction_reason',
            'published_by_name',
            # Second approval for Extreme alerts
            'approved_by_name', 'approved_at', 'auto_released',
            # Each barangay's own answer, and DRRMO's answer to a dispute
            'verifications', 'review_note', 'reviewed_at', 'reviewed_by_name',
            # A raise to Extreme waiting for a second officer
            'pending_severity', 'pending_at',
            'cordon_m',
        ]


def clean_zone_geometry(value):
    """
    A hazard zone geometry from the map, made safe to save.

    Returns (clipped, outline): the MultiPolygon to store, repaired and cut
    at the city boundary, and the outline as drawn (a Polygon, or None when
    the client sent something else), kept so the zone can be reshaped later.
    Raises ValidationError with a sentence the officer can act on.
    """
    if value.geom_type not in ('Polygon', 'MultiPolygon'):
        raise serializers.ValidationError(
            f'A hazard zone must be an area, not a {value.geom_type}.'
        )

    # GeoJSON is WGS84 by definition, but a geometry that arrives without
    # an SRID is rejected by PostGIS when the column declares 4326.
    if not getattr(value, 'srid', None):
        value.srid = 4326
    outline = value.clone() if isinstance(value, Polygon) else None

    # HazardZone.geometry is a MultiPolygonField. GeoDjango will not
    # coerce a Polygon into one — it raises outright — so a client that
    # sends the simpler single-polygon GeoJSON (the map's publish form,
    # an API client, a seeder) gets wrapped here instead of failing.
    if isinstance(value, Polygon):
        value = MultiPolygon(value, srid=value.srid)

    # Zones are outlined by hand, so repair a self-crossing outline and
    # cut off whatever spills past the city. See apps/hazards/geometry.py.
    try:
        return clip_to_city(value, city_outline()), outline
    except ValueError as exc:  # also catches OutsideCity
        raise serializers.ValidationError(str(exc))


class HazardZoneCreateSerializer(serializers.ModelSerializer):
    """
    Body for POST /api/hazards/create/ — the map's publish form.
    Plain fields plus a GeoJSON geometry, e.g.

        {"hazard_type": 1, "barangay": 7, "severity": "Orange",
         "description": "...",
         "geometry": {"type": "Polygon", "coordinates": [[[lng, lat], ...]]},
         "cordon_m": 30}

    cordon_m is optional: a safety ring that many meters wide around the
    drawn area. The geometry stays the hazard itself; see HazardZone.cordon_m.
    """

    # Declared explicitly on purpose. A plain ModelSerializer can only build
    # a field for a GIS geometry column when rest_framework_gis is listed in
    # INSTALLED_APPS, because its AppConfig.ready() is what registers the
    # mapping. Naming the field here makes writes work either way, instead of
    # raising while the serializer's fields are being built — which surfaces
    # as a 500 rather than a validation error.
    geometry = GeometryField()
    cordon_m = serializers.IntegerField(
        required=False, allow_null=True,
        min_value=CORDON_MIN_M, max_value=CORDON_MAX_M,
        error_messages={
            'min_value': f'A cordon is at least {CORDON_MIN_M} m wide. Leave it off for none.',
            'max_value': f'A cordon is at most {CORDON_MAX_M} m wide. Draw a larger zone instead.',
        },
    )

    class Meta:
        model  = HazardZone
        fields = [
            'barangay', 'hazard_type', 'severity',
            'geometry', 'description', 'cordon_m',
        ]

    def validate_geometry(self, value):
        clipped, outline = clean_zone_geometry(value)
        self._outline = outline
        return clipped

    def validate(self, attrs):
        # The zone belongs to the barangay holding most of it. The map only
        # previews this; deciding it here means a zone spanning two barangays
        # is filed under the one it mostly covers, not wherever the officer
        # happened to tap first.
        geom = attrs.get('geometry')
        if geom is not None:
            touched = Barangay.objects.filter(boundary__intersects=geom)
            home = main_barangay(geom, touched)
            if home is not None:
                attrs['barangay'] = home
            attrs['outline'] = getattr(self, '_outline', None)
        return attrs


class HazardAlertSerializer(serializers.ModelSerializer):
    class Meta:
        model  = HazardAlert
        fields = [
            'id', 'hazard_zone', 'issued_by',
            'hazard_type', 'severity', 'notes', 'created_at'
        ]