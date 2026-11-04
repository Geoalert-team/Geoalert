"""
The newsfeed's API (docs/superpowers/specs/2026-11-04-newsfeed-design.md).

  GET    /api/news/        the public feed
  POST   /api/news/        post an announcement: DRRMO, admins and BFP
  PATCH  /api/news/<id>/   edit it: its BFP author, or any DRRMO officer or admin
  DELETE /api/news/<id>/   delete it, with its photo: the same people
"""
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.news.models import Announcement
from apps.news.permissions import can_manage, source_for
from apps.news.serializers import AnnouncementWriteSerializer
from utils.audit import log_event
from utils.permissions import IsBFPPersonnel


class NewsListView(APIView):
    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsAuthenticated(), IsBFPPersonnel()]
        return [AllowAny()]

    def post(self, request):
        serializer = AnnouncementWriteSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        post = serializer.save(source=source_for(request.user), created_by=request.user)
        log_event(request, 'POST_NEWS', 'announcement', post.id, f'"{post.title}"')
        return Response({'id': str(post.id)}, status=status.HTTP_201_CREATED)


class NewsDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def _managed(self, request, pk):
        """(post, None) when this person may change it, else (None, an error response)."""
        post = Announcement.objects.filter(pk=pk).first()
        if post is None:
            return None, Response({'error': 'Announcement not found.'}, status=status.HTTP_404_NOT_FOUND)
        if not can_manage(request.user, post):
            return None, Response({'error': 'You can only change your own announcements.'},
                                  status=status.HTTP_403_FORBIDDEN)
        return post, None

    def patch(self, request, pk):
        post, error = self._managed(request, pk)
        if error:
            return error
        serializer = AnnouncementWriteSerializer(post, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        post = serializer.save()
        log_event(request, 'EDIT_NEWS', 'announcement', post.id, f'"{post.title}"')
        return Response({'id': str(post.id)})

    def delete(self, request, pk):
        post, error = self._managed(request, pk)
        if error:
            return error
        title, post_id = post.title, post.id
        if post.photo:
            post.photo.delete(save=False)
        post.delete()
        log_event(request, 'DELETE_NEWS', 'announcement', post_id, f'"{title}"')
        return Response(status=status.HTTP_204_NO_CONTENT)
