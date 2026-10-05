from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status

from apps.notifications.models import Notification
from apps.notifications.serializers import NotificationSerializer


class NotificationListView(APIView):
    """
    GET /api/notifications/
    Returns the logged-in user's notifications.
    Supports ?unread=true to filter.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        notes = Notification.objects.filter(recipient=request.user)

        if request.query_params.get('unread') == 'true':
            notes = notes.filter(is_read=False)

        return Response(NotificationSerializer(notes, many=True).data)


class NotificationMarkReadView(APIView):
    """
    PATCH /api/notifications/<id>/read/
    Marks a single notification as read.
    """
    permission_classes = [IsAuthenticated]

    def patch(self, request, pk):
        try:
            note = Notification.objects.get(pk=pk, recipient=request.user)
        except Notification.DoesNotExist:
            return Response({'error': 'Notification not found'}, status=status.HTTP_404_NOT_FOUND)

        note.is_read = True
        note.read_at = timezone.now()
        note.save()
        return Response(NotificationSerializer(note).data)


class NotificationMarkAllReadView(APIView):
    """
    POST /api/notifications/read-all/
    Marks all of the logged-in user's notifications as read.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        updated = Notification.objects.filter(
            recipient=request.user, is_read=False
        ).update(is_read=True, read_at=timezone.now())
        return Response({'marked_read': updated})