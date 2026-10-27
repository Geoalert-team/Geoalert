from django.shortcuts import render

# Create your views here.
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from rest_framework import status

from apps.barangays.models import Barangay, Purok
from apps.hazards.models import HazardZone
from apps.barangays.serializers import BarangayGeoSerializer, BarangaySerializer, PurokGeoSerializer


class BarangayListView(APIView):
    """
    GET /api/barangays/
    Returns all barangay boundaries as GeoJSON.
    Public access — used by Leaflet.js map.
    """
    permission_classes = [AllowAny]

    def get(self, request):
        barangays = Barangay.objects.all()
        serializer = BarangayGeoSerializer(barangays, many=True)
        return Response(serializer.data)


class PurokListView(APIView):
    """
    GET /api/barangays/puroks/
    Every purok outline as GeoJSON, for the map's purok layer. Most are
    estimates until the Barangay Hall's official lines are loaded; `source`
    says which. Public, like the barangay outlines.
    """
    permission_classes = [AllowAny]

    def get(self, request):
        puroks = Purok.objects.select_related('barangay').order_by('barangay__name', 'name')
        return Response(PurokGeoSerializer(puroks, many=True).data)


class BarangayDetailView(APIView):
    """
    GET /api/barangays/<id>/
    Returns a single barangay with its boundary.
    """
    permission_classes = [AllowAny]

    def get(self, request, pk):
        try:
            barangay = Barangay.objects.get(pk=pk)
        except Barangay.DoesNotExist:
            return Response(
                {'error': 'Barangay not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        return Response(BarangayGeoSerializer(barangay).data)


class BarangayHazardsView(APIView):
    """
    GET /api/barangays/<id>/hazards/
    The active hazard zones that affect one barangay, split in two:

        {"barangay": 7,
         "inside":   ["<zone id>", ...],   ST_Within: entirely inside it
         "crossing": ["<zone id>", ...]}   ST_Intersects, not within: crosses its border

    The map used to list a hazard under a barangay only when the hazard's
    pin fell inside it, so a zone reaching in from next door was missed.
    This asks PostGIS instead. "Inside" means the barangay's own problem;
    "crossing" means it shares the hazard with a neighbour, which matters
    for who coordinates the response. Public, like the map.
    """
    permission_classes = [AllowAny]

    def get(self, request, pk):
        barangay = Barangay.objects.filter(pk=pk).only('id', 'boundary').first()
        if barangay is None:
            return Response({'error': 'Barangay not found'}, status=status.HTTP_404_NOT_FOUND)
        if barangay.boundary is None:
            return Response({'barangay': barangay.id, 'inside': [], 'crossing': []})

        active = HazardZone.objects.filter(status='Active')
        inside = list(active.filter(geometry__within=barangay.boundary).values_list('id', flat=True))
        crossing = list(
            active.filter(geometry__intersects=barangay.boundary)
            .exclude(id__in=inside)
            .values_list('id', flat=True)
        )

        return Response({
            'barangay': barangay.id,
            'inside': [str(z) for z in inside],
            'crossing': [str(z) for z in crossing],
        })
