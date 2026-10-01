from rest_framework_gis.serializers import GeoFeatureModelSerializer
from rest_framework import serializers
from apps.barangays.barangays_models import Barangay


class BarangayGeoSerializer(GeoFeatureModelSerializer):
    """
    Returns barangay boundaries as GeoJSON.
    Used by Leaflet.js to draw barangay outlines on the map.
    """
    class Meta:
        model     = Barangay
        geo_field = 'boundary'
        fields    = ['id', 'name', 'municipality']


class BarangaySerializer(serializers.ModelSerializer):
    class Meta:
        model  = Barangay
        fields = ['id', 'name', 'municipality']