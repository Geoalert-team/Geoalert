from rest_framework import serializers
from apps.history.models import HistoricalRecord
from apps.hazards.serializers import HazardTypeSerializer
from apps.barangays.serializers import BarangaySerializer


class HistoricalRecordSerializer(serializers.ModelSerializer):
    hazard_type_detail = HazardTypeSerializer(source='hazard_type', read_only=True)
    barangay_detail     = BarangaySerializer(source='barangay', read_only=True)

    class Meta:
        model  = HistoricalRecord
        fields = [
            'id', 'barangay', 'barangay_detail',
            'hazard_type', 'hazard_type_detail',
            'hazard_zone', 'severity_level', 'description',
            'occurred_at', 'total_casualties', 'total_displaced',
            'archived_at'
        ]


class HistoricalRecordCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model  = HistoricalRecord
        fields = [
            'barangay', 'hazard_type', 'hazard_zone',
            'severity_level', 'description', 'occurred_at',
            'total_casualties', 'total_displaced'
        ]