from rest_framework import serializers
from rest_framework_gis.serializers import GeoFeatureModelSerializer
from apps.hazards.hazards_models import HazardType, HazardZone, HazardAlert
from apps.accounts.accounts_serializers import UserSerializer


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
    class Meta:
        model  = HazardZone
        fields = [
            'barangay', 'hazard_type', 'severity',
            'geometry', 'description'
        ]


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