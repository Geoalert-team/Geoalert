from rest_framework import serializers
from rest_framework_gis.serializers import GeoFeatureModelSerializer
from rest_framework_gis.fields import GeometryField
from django.contrib.gis.geos import MultiPolygon, Polygon
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

    class Meta:
        model       = HazardZone
        geo_field   = 'geometry'
        fields = [
            'id', 'barangay', 'barangay_name', 'hazard_type_name',
            'severity', 'status', 'description',
            'activated_at', 'resolved_at',
            'verification_status', 'verified_by_name',
            'verified_at', 'verification_note',
        ]


class HazardZoneSerializer(serializers.ModelSerializer):
    hazard_type = HazardTypeSerializer(read_only=True)
    barangay_name = serializers.CharField(
        source='barangay.name', read_only=True, default=None
    )
    verified_by_name = serializers.CharField(
        source='verified_by.full_name', read_only=True, default=None
    )

    class Meta:
        model  = HazardZone
        fields = [
            'id', 'barangay', 'barangay_name', 'published_by', 'hazard_type',
            'severity', 'status', 'description',
            'activated_at', 'resolved_at',
            'verification_status', 'verified_by_name',
            'verified_at', 'verification_note',
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
        return value


class HazardZoneVerifySerializer(serializers.Serializer):
    """
    Body for POST /api/hazards/<id>/verify/
    Barangay personnel report what they see on the ground.
    """
    verification_status = serializers.ChoiceField(choices=['Pending', 'Confirmed', 'Disputed'])
    verification_note   = serializers.CharField(
        required=False, allow_blank=True, max_length=1000
    )

    def validate(self, data):
        note = (data.get('verification_note') or '').strip()
        if data['verification_status'] == 'Disputed' and not note:
            raise serializers.ValidationError({
                'verification_note': 'Describe the conditions you saw so the DRRMO can update the map.'
            })
        data['verification_note'] = note
        return data


class HazardAlertSerializer(serializers.ModelSerializer):
    class Meta:
        model  = HazardAlert
        fields = [
            'id', 'hazard_zone', 'issued_by',
            'hazard_type', 'severity', 'notes', 'created_at'
        ]