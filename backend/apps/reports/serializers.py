from rest_framework import serializers
from apps.reports.models import IncidentReport
from apps.hazards.serializers import HazardTypeSerializer
from apps.barangays.serializers import BarangaySerializer

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
            'status',
            'review_note',
            'reviewed_by',
            'reviewed_by_name',
            'created_at',
            'reviewed_at',
        ]

class IncidentReportCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = IncidentReport
        fields = [
            'barangay',
            'hazard_type',
            'description',
        ]

class IncidentReportReviewSerializer(serializers.ModelSerializer):
    class Meta:
        model  = IncidentReport
        fields = ['status', 'review_note']
