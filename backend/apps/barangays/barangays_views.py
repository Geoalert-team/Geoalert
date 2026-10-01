from django.shortcuts import render

# Create your views here.
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from rest_framework import status

from apps.barangays.barangays_models import Barangay
from apps.barangays.barangays_serializers import BarangayGeoSerializer, BarangaySerializer


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