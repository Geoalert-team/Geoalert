"""
Permission for the automatic retraining job's two endpoints: the bearer token
in settings.MODEL_JOB_TOKEN. An empty token refuses everything.
"""
import hmac

from django.conf import settings
from rest_framework.permissions import BasePermission


class ModelJobTokenPermission(BasePermission):
    def has_permission(self, request, view):
        token = getattr(settings, 'MODEL_JOB_TOKEN', '') or ''
        header = request.META.get('HTTP_AUTHORIZATION', '')
        scheme, _, sent = header.partition(' ')
        if not token or scheme.lower() != 'bearer' or not sent.strip():
            return False
        return hmac.compare_digest(sent.strip().encode(), token.encode())
