from rest_framework import serializers
from apps.guidance.models import GuidanceContent
from apps.hazards.serializers import HazardTypeSerializer


class GuidanceContentSerializer(serializers.ModelSerializer):
    hazard_type_detail = HazardTypeSerializer(
        source='hazard_type', read_only=True
    )

    class Meta:
        model  = GuidanceContent
        fields = [
            'id', 'hazard_type', 'hazard_type_detail',
            'title', 'body', 'timeline_phase',
            'is_published', 'created_at', 'updated_at'
        ]


class GuidanceContentCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model  = GuidanceContent
        fields = [
            'hazard_type', 'title', 'body',
            'timeline_phase', 'is_published'
        ]