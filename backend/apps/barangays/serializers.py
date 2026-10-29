from django.contrib.gis.geos import MultiPolygon
from rest_framework_gis.fields import GeometryField
from rest_framework_gis.serializers import GeoFeatureModelSerializer
from rest_framework import serializers
from apps.barangays.models import Barangay, Purok


def sitio_leftovers(puroks):
    """
    {sitio id: the part of its outline none of its puroks cover}, for the
    sitios drawn around puroks (Purok.parent names them). A sitio's own past
    hazards colour only this part, so a purok inside it with none of its own
    isn't painted in the sitio's colour. A sitio its puroks cover entirely
    is left out.
    """
    kids = {}
    for p in puroks:
        if p.parent:
            kids.setdefault((p.barangay_id, p.parent), []).extend(p.boundary)
    leftovers = {}
    for p in puroks:
        inside = kids.get((p.barangay_id, p.name))
        if not inside:
            continue
        rest = p.boundary.difference(MultiPolygon(inside, srid=p.boundary.srid).unary_union)
        if not rest.empty and rest.area > 0:
            leftovers[p.id] = rest
    return leftovers


class BarangayGeoSerializer(GeoFeatureModelSerializer):
    """
    Returns barangay boundaries as GeoJSON.
    Used by Leaflet.js to draw barangay outlines on the map.
    """
    class Meta:
        model     = Barangay
        geo_field = 'boundary'
        fields    = ['id', 'name', 'municipality', 'province', 'region']


class BarangaySerializer(serializers.ModelSerializer):
    class Meta:
        model  = Barangay
        fields = ['id', 'name', 'municipality', 'province', 'region']


class PurokGeoSerializer(GeoFeatureModelSerializer):
    """
    Purok outlines as GeoJSON for the map's purok layer. label_point is a
    point inside the shape (not its centre, which can fall outside an odd
    shape), where the map puts the purok's name. members is how many puroks
    a sitio holds (context['members'], from Purok.member_counts()); 0 for an
    ordinary purok. leftover is a sitio's own part outside its puroks
    (context['leftovers'], from sitio_leftovers()), which is what its past
    hazards fill; null for an ordinary purok.
    """
    # 6 decimals is about 0.1 m, and halves the download for the whole city
    boundary      = GeometryField(precision=6)
    barangay_name = serializers.CharField(source='barangay.name', read_only=True)
    label_point   = serializers.SerializerMethodField()
    members       = serializers.SerializerMethodField()
    leftover      = serializers.SerializerMethodField()

    class Meta:
        model     = Purok
        geo_field = 'boundary'
        fields    = ['id', 'name', 'kind', 'parent', 'barangay', 'barangay_name',
                     'source', 'confidence', 'label_point', 'members', 'leftover']

    def get_leftover(self, obj):
        rest = self.context.get('leftovers', {}).get(obj.id)
        return GeometryField(precision=6).to_representation(rest) if rest is not None else None

    def get_label_point(self, obj):
        p = obj.boundary.point_on_surface
        return [round(p.x, 6), round(p.y, 6)]

    def get_members(self, obj):
        return self.context.get('members', {}).get((obj.barangay_id, obj.name), 0)
