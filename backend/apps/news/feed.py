"""
The public newsfeed: announcements, and a post for each hazard alert that
went out, newest first (spec: docs/superpowers/specs/2026-11-04-newsfeed-design.md §2).

Alert posts are read from the hazard zones each time, not stored, so a post
always shows its zone as it is now: Resolved once it is over, gone if it is
withdrawn. A zone with no HazardAlert never went public (an Extreme alert
still held for a second officer), so it has no post.
"""
from datetime import timedelta

from django.db.models import Min

from apps.hazards.models import HazardZone
from apps.news.models import Announcement
from apps.news.permissions import can_manage
from apps.reports.serializers import photo_url

# An edit within this long of posting isn't shown as "edited"
EDIT_GRACE = timedelta(minutes=1)
LIVE = ('Active', 'Resolving')


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


def _alert_post(zone):
    puroks = []
    for report in zone.incidentreport_set.all():
        for purok in report.puroks.all():
            if purok.name not in puroks:
                puroks.append(purok.name)
    active = zone.status in LIVE
    return {
        'kind': 'alert',
        'id': str(zone.id),
        'hazard_type': zone.hazard_type.name if zone.hazard_type else None,
        'severity': zone.severity,
        'published_at': zone.first_alert.isoformat(),
        'barangay': zone.barangay.name if zone.barangay else None,
        'puroks': puroks,
        'status': 'active' if active else 'resolved',
        'map_link': f'/map?zone={zone.id}' if active else None,
    }


def alert_posts(before, limit):
    """The newest `limit` zones that went out before `before` (None for now), as (time, post) pairs."""
    zones = (HazardZone.objects.filter(is_sample=False).exclude(status='Retracted')
             .annotate(first_alert=Min('hazardalert__created_at'))
             .filter(first_alert__isnull=False))
    if before is not None:
        zones = zones.filter(first_alert__lt=before)
    zones = (zones.select_related('hazard_type', 'barangay')
             .prefetch_related('incidentreport_set__puroks')
             .order_by('-first_alert')[:limit])
    return [(z.first_alert, _alert_post(z)) for z in zones]


def build_feed(user, request, before, limit):
    """(posts, next_before): one page, newest first, and where the next page starts (None at the end)."""
    announcements = Announcement.objects.all()
    if before is not None:
        announcements = announcements.filter(created_at__lt=before)
    announcements = [(a.created_at, announcement_post(a, user, request))
                     for a in announcements.order_by('-created_at')[:limit]]
    alerts = alert_posts(before, limit)

    # Merged by the times themselves, not their text
    merged = sorted(announcements + alerts, key=lambda pair: pair[0], reverse=True)
    page = merged[:limit]
    more = len(announcements) == limit or len(alerts) == limit or len(merged) > limit
    return [post for _, post in page], (page[-1][1]['published_at'] if more and page else None)
