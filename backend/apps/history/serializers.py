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
            'archived_at', 'is_sample'
        ]


# Off the public map, as in apps/history/area.py: the BFP's address, the
# damage, the injured and dead by sex, and the zone whose barangay reports
# (names, photos) only DRRMO can open. The totals stay public.
STAFF_ONLY_FIELDS = (
    'location_text', 'damage_cost', 'hazard_zone',
    'injured_ff_male', 'injured_ff_female', 'injured_civ_male', 'injured_civ_female',
    'fatal_ff_male', 'fatal_ff_female', 'fatal_civ_male', 'fatal_civ_female',
)


class HistoricalRecordDetailSerializer(HistoricalRecordSerializer):
    """
    One record in full, for the history page's details window: the list's
    fields plus where exactly (the puroks and the BFP log's location) and
    the fire log's columns G-W. Kept out of the list, which stays light.
    """
    puroks = serializers.SlugRelatedField(many=True, read_only=True, slug_field='name')

    class Meta(HistoricalRecordSerializer.Meta):
        fields = HistoricalRecordSerializer.Meta.fields + [
            'location_text', 'puroks',
            # BFP fire log G-W: property type, injured and fatalities by
            # firefighter / civilian and male / female, damage, structures, alarm
            'property_category', 'property_subcategory',
            'injured_ff_male', 'injured_ff_female', 'injured_civ_male', 'injured_civ_female',
            'fatal_ff_male', 'fatal_ff_female', 'fatal_civ_male', 'fatal_civ_female',
            'damage_cost', 'structures_affected', 'alarm_level',
        ]


class HistoricalRecordCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model  = HistoricalRecord
        fields = [
            'barangay', 'hazard_type', 'hazard_zone',
            'severity_level', 'description', 'occurred_at',
            'total_casualties', 'total_displaced'
        ]