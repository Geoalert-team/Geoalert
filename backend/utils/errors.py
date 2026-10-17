"""
Readable errors for the API.

Without this, any unhandled exception on /api/ comes back as Django's HTML
error page (or a bare 500 in production). The frontend can't read either,
so officers saw "Request failed with status code 500" with no idea whether
to retry, wait, or call someone, which is what happened when withdrawing a
hazard hit a database constraint.

Now the client gets a short sentence it can show, plus a reference that
matches the full traceback in the server log.
"""

import logging
import uuid

from django.db import DatabaseError, IntegrityError, InterfaceError, OperationalError
from django.http import JsonResponse

logger = logging.getLogger('geoalert.api')

DB_UNREACHABLE = (
    "Can't reach the database right now. Wait a moment and try again. "
    "Nothing was saved."
)
DB_REJECTED = (
    "The database refused this change, so nothing was saved. "
    "Tell the system admin and quote reference {ref}."
)
DB_OTHER = (
    "The database ran into a problem, so nothing was saved. Try again, "
    "and if it keeps happening tell the system admin and quote reference {ref}."
)
UNEXPECTED = (
    "Something went wrong on the server. Try again, and if it keeps "
    "happening tell the system admin and quote reference {ref}."
)


def describe(exc, ref):
    """(HTTP status, message) for an unhandled exception."""
    if isinstance(exc, (OperationalError, InterfaceError)):
        return 503, DB_UNREACHABLE
    if isinstance(exc, IntegrityError):
        return 500, DB_REJECTED.format(ref=ref)
    if isinstance(exc, DatabaseError):
        return 500, DB_OTHER.format(ref=ref)
    return 500, UNEXPECTED.format(ref=ref)


class ApiErrorMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_exception(self, request, exc):
        if not request.path.startswith('/api/'):
            return None  # admin and other pages keep Django's own handling

        ref = uuid.uuid4().hex[:8]
        code, message = describe(exc, ref)
        logger.exception('API error %s on %s %s', ref, request.method, request.path)
        return JsonResponse({'error': message, 'reference': ref}, status=code)
