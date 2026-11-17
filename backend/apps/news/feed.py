"""
The public newsfeed: the announcements DRRMO and BFP post, newest first
(spec: docs/design/specs/2026-11-04-newsfeed-design.md §2). Hazard alerts are
not posted here: they reach people through the map and the notification bell.
"""
from datetime import timedelta

from apps.news.models import Announcement
from apps.news.permissions import can_manage
from apps.reports.serializers import photo_url

# An edit within this long of posting isn't shown as "edited"
EDIT_GRACE = timedelta(minutes=1)


def announcement_post(post, user, request=None):
    edited = post.updated_at - post.created_at > EDIT_GRACE
    return {
        'kind': 'announcement',
        'id': str(post.id),
        'title': post.title,
        'body': post.body,
        'photo_url': photo_url(post.photo, request) if post.photo else None,
        'source': post.source,
        'published_at': post.created_at.isoformat(),
        'edited_at': post.updated_at.isoformat() if edited else None,
        'can_edit': can_manage(user, post),
    }


def build_feed(user, request, before, limit):
    """(posts, next_before): one page, newest first, and where the next page starts (None at the end)."""
    announcements = Announcement.objects.all()
    if before is not None:
        announcements = announcements.filter(created_at__lt=before)
    page = list(announcements.order_by('-created_at')[:limit])
    posts = [announcement_post(a, user, request) for a in page]
    return posts, (posts[-1]['published_at'] if len(page) == limit else None)
