"""
The tutorial videos API (docs/superpowers/specs/2026-11-11-tutorial-videos-design.md).

  GET    /api/tutorials/                   every video, by category: public
  POST   /api/tutorials/                   add one video: DRRMO officers and admins
  PATCH  /api/tutorials/<id>/              edit it: the same people
  DELETE /api/tutorials/<id>/              delete it, with its file: the same people
  GET    /api/tutorials/categories/        the categories A to Z, with video counts: public
  POST   /api/tutorials/categories/        add one: DRRMO officers and admins
  PATCH  /api/tutorials/categories/<id>/   rename it
  DELETE /api/tutorials/categories/<id>/   delete it with all its videos and their files
  GET    /api/tutorials/youtube-check/     ?url=: the form's "is this link real" check

One video per POST, so the page's batch form can show each upload's progress
and retry a failed one without resending the others.
"""
from django.core.files.storage import default_storage
from django.db import IntegrityError, transaction
from django.db.models import Count
from django.db.models.functions import Lower
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.tutorials.list_cache import rows
from apps.tutorials.models import TutorialVideo, VideoCategory
from apps.tutorials.serializers import (
    BAD_LINK, TutorialVideoSerializer, TutorialVideoWriteSerializer, VideoCategorySerializer, name_taken,
)
from apps.tutorials.youtube import lookup, parse_youtube_id
from utils.audit import log_event
from utils.permissions import IsDRRMOOfficer

STAFF = [IsAuthenticated, IsDRRMOOfficer]


class PublicReadStaffWrite:
    """Anyone reads; only DRRMO officers and admins change anything."""
    def get_permissions(self):
        if self.request.method == 'GET':
            return [AllowAny()]
        return [permission() for permission in STAFF]


def video_data(video, request):
    return TutorialVideoSerializer(video, context={'request': request}).data


class VideoListView(PublicReadStaffWrite, APIView):
    def get(self, request):
        # The rows are cached, never this response: each request signs its own MP4 links
        videos = rows('videos', lambda: list(TutorialVideo.objects.select_related('category')))
        return Response(TutorialVideoSerializer(videos, many=True, context={'request': request}).data)

    def post(self, request):
        serializer = TutorialVideoWriteSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        video = serializer.save(created_by=request.user)
        log_event(request, 'ADD_VIDEO', 'tutorial_video', video.id, f'"{video.title}"')
        return Response(video_data(video, request), status=status.HTTP_201_CREATED)


class VideoDetailView(APIView):
    permission_classes = STAFF

    @staticmethod
    def _video(pk):
        """(video, None), or (None, a 404 response)."""
        video = TutorialVideo.objects.select_related('category').filter(pk=pk).first()
        if video is None:
            return None, Response({'error': 'Video not found.'}, status=status.HTTP_404_NOT_FOUND)
        return video, None

    def patch(self, request, pk):
        video, error = self._video(pk)
        if error:
            return error
        serializer = TutorialVideoWriteSerializer(video, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        video = serializer.save()
        log_event(request, 'EDIT_VIDEO', 'tutorial_video', video.id, f'"{video.title}"')
        return Response(video_data(video, request))

    def delete(self, request, pk):
        video, error = self._video(pk)
        if error:
            return error
        title, video_id = video.title, video.id
        if video.file:
            video.file.delete(save=False)
        video.delete()
        log_event(request, 'DELETE_VIDEO', 'tutorial_video', video_id, f'"{title}"')
        return Response(status=status.HTTP_204_NO_CONTENT)


def categories():
    return VideoCategory.objects.annotate(video_count=Count('videos')).order_by(Lower('name'))


def delete_files(names):
    """Best effort: a file already gone, or storage briefly unreachable, mustn't fail the delete."""
    for name in names:
        try:
            default_storage.delete(name)
        except Exception:  # storage backends raise their own error types
            pass


def category_data(pk):
    return VideoCategorySerializer(categories().get(pk=pk)).data


def save_category(serializer):
    """
    (category, None), or (None, a 400 response) when two people took the same
    name at the same moment: the check in the serializer passed for both, the
    database's unique constraint stopped the second.
    """
    try:
        with transaction.atomic():
            return serializer.save(), None
    except IntegrityError:
        name = serializer.validated_data['name']
        existing = VideoCategory.objects.filter(name__iexact=name).first()
        return None, Response({'name': [name_taken(existing.name if existing else name)]},
                              status=status.HTTP_400_BAD_REQUEST)


class CategoryListView(PublicReadStaffWrite, APIView):
    def get(self, request):
        return Response(VideoCategorySerializer(rows('categories', lambda: list(categories())), many=True).data)

    def post(self, request):
        serializer = VideoCategorySerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        category, error = save_category(serializer)
        if error:
            return error
        log_event(request, 'ADD_VIDEO_CATEGORY', 'video_category', category.id, f'"{category.name}"')
        return Response(category_data(category.pk), status=status.HTTP_201_CREATED)


class CategoryDetailView(APIView):
    permission_classes = STAFF

    @staticmethod
    def _category(pk):
        category = VideoCategory.objects.filter(pk=pk).first()
        if category is None:
            return None, Response({'error': 'Category not found.'}, status=status.HTTP_404_NOT_FOUND)
        return category, None

    def patch(self, request, pk):
        category, error = self._category(pk)
        if error:
            return error
        old = category.name
        serializer = VideoCategorySerializer(category, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        category, error = save_category(serializer)
        if error:
            return error
        change = f'"{old}" → "{category.name}"' if old != category.name else f'"{category.name}" (description)'
        log_event(request, 'RENAME_VIDEO_CATEGORY', 'video_category', category.id, change)
        return Response(category_data(category.pk))

    def delete(self, request, pk):
        """
        Deletes the category with all its videos, as the page's warning says. The rows go in
        one transaction; the uploaded files are deleted only once it commits, so a failed
        delete never loses a file whose video is still there.
        """
        category, error = self._category(pk)
        if error:
            return error
        name, category_id = category.name, category.id
        with transaction.atomic():
            videos = list(category.videos.all())
            files = [v.file.name for v in videos if v.file]
            category.videos.all().delete()
            category.delete()
            transaction.on_commit(lambda: delete_files(files))
        log_event(request, 'DELETE_VIDEO_CATEGORY', 'video_category', category_id,
                  f'"{name}" and {len(videos)} videos')
        return Response(status=status.HTTP_204_NO_CONTENT)


class YouTubeCheckView(APIView):
    """
    What the batch form shows beside a pasted link: whether YouTube knows the
    video (and its title, to fill in), and whether it is already on the page.
    """
    permission_classes = STAFF

    def get(self, request):
        youtube_id = parse_youtube_id(request.query_params.get('url', ''))
        if not youtube_id:
            return Response({'url': BAD_LINK}, status=status.HTTP_400_BAD_REQUEST)
        result = lookup(youtube_id)
        saved = TutorialVideo.objects.select_related('category').filter(youtube_id=youtube_id).first()
        return Response({
            'youtube_id': youtube_id,
            'status': result['status'],
            'title': result.get('title') if result['status'] == 'ok' else None,
            'duplicate': saved.category.name if saved else None,
        })
