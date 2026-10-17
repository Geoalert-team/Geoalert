from rest_framework import serializers
from rest_framework_gis.serializers import GeoFeatureModelSerializer
from rest_framework_gis.fields import GeometryField
from django.contrib.gis.geos import MultiPolygon, Polygon
from apps.barangays.models import Barangay
from apps.hazards.geometry import city_outline, clip_to_city, main_barangay
from apps.hazards.models import HazardType, HazardZone, HazardAlert
from apps.accounts.serializers import UserSerializer


class HazardTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model  = HazardType
        fields = ['id', 'name', 'logo_class', 'is_active']


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
        ]


class HazardZoneCreateSerializer(serializers.ModelSerializer):
    """
    Body for POST /api/hazards/create/ — the map's publish form.
    Plain fields plus a GeoJSON geometry, e.g.

        {"hazard_type": 1, "barangay": 7, "severity": "Orange",
         "description": "...",
         "geometry": {"type": "Polygon", "coordinates": [[[lng, lat], ...]]}}
    """

    # Declared explicitly on purpose. A plain ModelSerializer can only build
    # a field for a GIS geometry column when rest_framework_gis is listed in
    # INSTALLED_APPS, because its AppConfig.ready() is what registers the
    # mapping. Naming the field here makes writes work either way, instead of
    # raising while the serializer's fields are being built — which surfaces
    # as a 500 rather than a validation error.
    geometry = GeometryField()

    class Meta:
        model  = HazardZone
        fields = [
            'barangay', 'hazard_type', 'severity',
            'geometry', 'description'
        ]

    def validate_geometry(self, value):
        if value.geom_type not in ('Polygon', 'MultiPolygon'):
            raise serializers.ValidationError(
                f'A hazard zone must be an area, not a {value.geom_type}.'
            )

        # HazardZone.geometry is a MultiPolygonField. GeoDjango will not
        # coerce a Polygon into one — it raises outright — so a client that
        # sends the simpler single-polygon GeoJSON (the map's publish form,
        # an API client, a seeder) gets wrapped here instead of failing.
        if isinstance(value, Polygon):
            value = MultiPolygon(value)

        # GeoJSON is WGS84 by definition, but a geometry that arrives without
        # an SRID is rejected by PostGIS when the column declares 4326.
        if not getattr(value, 'srid', None):
            value.srid = 4326

        # Zones are outlined by hand, so repair a self-crossing outline and
        # cut off whatever spills past the city. See apps/hazards/geometry.py.
        try:
            return clip_to_city(value, city_outline())
        except ValueError as exc:  # also catches OutsideCity
            raise serializers.ValidationError(str(exc))

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
        return attrs


class HazardAlertSerializer(serializers.ModelSerializer):
    class Meta:
        model  = HazardAlert
        fields = [
            'id', 'hazard_zone', 'issued_by',
            'hazard_type', 'severity', 'notes', 'created_at'
        ]