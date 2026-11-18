"""Token check for the scheduled job's endpoints. No session, no CSRF: a bearer token only."""
import hmac

from django.conf import settings
from rest_framework.permissions import BasePermission


def bearer_token(request):
    header = request.META.get('HTTP_AUTHORIZATION', '')
    scheme, _, token = header.partition(' ')
    if scheme.lower() != 'bearer':
        return ''
    return token.strip()


class IngestTokenPermission(BasePermission):
    def has_permission(self, request, view):
        expected = settings.RAIN_WATCH_INGEST_TOKEN
        if not expected:  # not configured: reject everything, even an empty token
            return False
        given = bearer_token(request)
        return hmac.compare_digest(given.encode(), expected.encode())
