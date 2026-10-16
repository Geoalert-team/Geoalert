from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status

from apps.notifications.models import Notification
from apps.notifications.serializers import NotificationSerializer

DEFAULT_LIMIT = 30
MAX_LIMIT = 100


class NotificationListView(APIView):
    """
    GET /api/notifications/
    Returns the logged-in user's notifications, newest first.

    Query params:
        ?unread=true     only unread ones
        ?limit=<n>       how many to return (default 30, max 100)

    Response:
        {
          "unread_count": 4,     total unread, NOT capped by limit
          "count": 12,           how many rows this response carries
          "results": [ ... ]
        }

    The envelope matters: a notification is created for every active user on
    every hazard publish, so this list grows without bound while the navbar
    bell polls it on a timer. The bell needs an accurate unread badge but
    only ever renders the most recent handful, so the count is computed in
    the database and the rows are sliced.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        notes = (
            Notification.objects
            .filter(recipient=request.user)
            .select_related(
                'hazard_alert',
                'hazard_alert__hazard_type',
                'hazard_alert__hazard_zone',
                'hazard_alert__hazard_zone__barangay',
            )
        )

        # Counted before any unread filter or slice, so the badge stays right
        unread_count = notes.filter(is_read=False).count()

        if request.query_params.get('unread') == 'true':
            notes = notes.filter(is_read=False)

        try:
            limit = int(request.query_params.get('limit', DEFAULT_LIMIT))
        except (TypeError, ValueError):
            limit = DEFAULT_LIMIT
        limit = min(max(limit, 1), MAX_LIMIT)

        rows = list(notes[:limit])

        return Response({
            'unread_count': unread_count,
            'count':        len(rows),
            'results':      NotificationSerializer(rows, many=True).data,
        })


class NotificationMarkReadView(APIView):
    """
    PATCH /api/notifications/<id>/read/
    Marks a single notification as read. Scoped to the requesting user, so
    one account can't touch another's notifications.
    """
    permission_classes = [IsAuthenticated]

    def patch(self, request, pk):
        try:
            note = Notification.objects.get(pk=pk, recipient=request.user)
        except Notification.DoesNotExist:
            return Response({'error': 'Notification not found'},
                            status=status.HTTP_404_NOT_FOUND)

        # Don't overwrite the original read_at if this fires twice
        if not note.is_read:
            note.is_read = True
            note.read_at = timezone.now()
            note.save(update_fields=['is_read', 'read_at'])

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