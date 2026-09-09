from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework import status

from apps.guidance.models import GuidanceContent
from apps.guidance.serializers import (
    GuidanceContentSerializer,
    GuidanceContentCreateSerializer,
)
from utils.permissions import IsDRRMOOfficer


class GuidanceListView(APIView):
    """
    GET /api/guidance/
    Returns all published guidance articles.
    Supports filters: ?hazard_type=1 ?phase=Before
    Public access — no login required.
    """
    permission_classes = [AllowAny]

    def get(self, request):
        articles = GuidanceContent.objects.filter(is_published=True)

        # Filter by hazard type
        hazard_type = request.query_params.get('hazard_type')
        if hazard_type:
            articles = articles.filter(hazard_type_id=hazard_type)

        # Filter by timeline phase
        phase = request.query_params.get('phase')
        if phase:
            articles = articles.filter(timeline_phase=phase)

        serializer = GuidanceContentSerializer(articles, many=True)
        return Response(serializer.data)

    def post(self, request):
        """
        POST /api/guidance/
        Create a new guidance article. DRRMO Officer only.
        """
        if not request.user.is_authenticated:
            return Response(
                {'error': 'Authentication required'},
                status=status.HTTP_401_UNAUTHORIZED
            )

        if not IsDRRMOOfficer().has_permission(request, self):
            return Response(
                {'error': 'Only DRRMO Officers can create guidance content'},
                status=status.HTTP_403_FORBIDDEN
            )

        serializer = GuidanceContentCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                serializer.errors,
                status=status.HTTP_400_BAD_REQUEST
            )

        article = serializer.save(created_by=request.user)
        return Response(
            GuidanceContentSerializer(article).data,
            status=status.HTTP_201_CREATED
        )


class GuidanceDetailView(APIView):
    """
    GET    /api/guidance/<id>/ → Get single article (public)
    PUT    /api/guidance/<id>/ → Edit article (DRRMO only)
    DELETE /api/guidance/<id>/ → Soft delete (DRRMO only)
    """
    permission_classes = [AllowAny]

    def get_object(self, pk):
        try:
            return GuidanceContent.objects.get(pk=pk, is_published=True)
        except GuidanceContent.DoesNotExist:
            return None

    def get(self, request, pk):
        article = self.get_object(pk)
        if not article:
            return Response(
                {'error': 'Article not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        return Response(GuidanceContentSerializer(article).data)

    def put(self, request, pk):
        if not IsDRRMOOfficer().has_permission(request, self):
            return Response(
                {'error': 'Only DRRMO Officers can edit guidance content'},
                status=status.HTTP_403_FORBIDDEN
            )

        try:
            article = GuidanceContent.objects.get(pk=pk)
        except GuidanceContent.DoesNotExist:
            return Response(
                {'error': 'Article not found'},
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = GuidanceContentCreateSerializer(
            article, data=request.data, partial=True
        )
        if not serializer.is_valid():
            return Response(
                serializer.errors,
                status=status.HTTP_400_BAD_REQUEST
            )

        article = serializer.save()
        return Response(GuidanceContentSerializer(article).data)

    def delete(self, request, pk):
        if not IsDRRMOOfficer().has_permission(request, self):
            return Response(
                {'error': 'Only DRRMO Officers can delete guidance content'},
                status=status.HTTP_403_FORBIDDEN
            )

        try:
            article = GuidanceContent.objects.get(pk=pk)
        except GuidanceContent.DoesNotExist:
            return Response(
                {'error': 'Article not found'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Soft delete — just unpublish, never hard delete
        article.is_published = False
        article.save()
        return Response(
            {'message': 'Article unpublished successfully'},
            status=status.HTTP_200_OK
        )   