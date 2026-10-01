from rest_framework import serializers
from apps.reports.reports_models import IncidentReport
from apps.hazards.hazards_serializers import HazardTypeSerializer
from apps.barangays.barangays_serializers import BarangaySerializer

class IncidentReportSerializer(serializers.ModelSerializer):
    hazard_type_details = HazardTypeSerializer(source='hazard_type', read_only=True)
    barangay_details = BarangaySerializer(source='barangay', read_only=True)
    submitted_by_name = serializers.CharField(source='submitted_by.full_name', read_only=True)
    reviewed_by_name = serializers.CharField(source='reviewed_by.full_name', read_only=True)

    class Meta:
        model = IncidentReport
        fields = [
            'id',
            'submitted_by',
            'submitted_by_name',
            'barangay',
            'barangay_details',
            'hazard_type',
            'hazard_type_details',
            'description',
            'casualties_dead',
            'casualties_injured',
            'casualties_missing',
            'displaced',
            'reporter_name',
            'agency',
            'position',
            'severity_estimate',
            'status',
            'review_note',
            'reviewed_by',
            'reviewed_by_name',
            'created_at',
            'reviewed_at',
            'validated_at',
        ]

class IncidentReportCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = IncidentReport
        fields = [
            'barangay',
            'hazard_type',
            'description',
            'casualties_dead',
            'casualties_injured',
            'casualties_missing',
            'agency',
            'position',
            'severity_estimate',
        ]
        extra_kwargs = {
            'casualties_dead':    {'min_value': 0, 'required': False},
            'casualties_injured': {'min_value': 0, 'required': False},
            'casualties_missing': {'min_value': 0, 'required': False},
        }

class IncidentReportReviewSerializer(serializers.ModelSerializer):
    class Meta:
        model  = IncidentReport
        fields = ['status', 'review_note']
