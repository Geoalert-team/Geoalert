"""
F3: cheap "has the map changed?" answers for the hazard zone endpoints.

The public map refreshes its zones every 30 seconds. Building that GeoJSON
takes several queries against a pooler that allows 15 connections, and
almost every refresh finds nothing new. So every change to what the map
shows (a zone, a barangay answer, a hazard type, a barangay) moves a
version number kept in the cache, and the zone endpoints send an ETag made
from it. A browser that already has the current version gets 304 Not
Modified without a single database query.

The version is bumped after the transaction commits, so a refresh can't
store the old data under the new version. The ETag also changes every five
minutes on its own, so anything that slips past the signals (a name change
on an account shown in a zone, an edit straight in the database) shows up
within five minutes anyway.
"""

import hashlib
import time
import uuid

from django.core.cache import cache
from django.db import transaction

KEY = 'geoalert:map-version'
REFRESH_EVERY = 5 * 60  # seconds; the ETag changes at least this often


def current():
    try:
        version = cache.get(KEY)
        if version is None:
            cache.add(KEY, uuid.uuid4().hex, None)
            version = cache.get(KEY)
        return version or 'none'
    except Exception:
        # No cache: a fresh tag every time, so nothing is ever wrongly 304'd
        return uuid.uuid4().hex


def _bump_now():
    try:
        cache.set(KEY, uuid.uuid4().hex, None)
    except Exception:
        pass


def bump(**_signal_kwargs):
    """Mark the map as changed once the current transaction commits."""
    transaction.on_commit(_bump_now)


def etag_for(request):
    bucket = int(time.time() // REFRESH_EVERY)
    raw = f'{current()}|{bucket}|{request.get_full_path()}'
    return '"' + hashlib.sha1(raw.encode()).hexdigest()[:24] + '"'


def is_fresh(request, etag):
    """True when the browser already holds this exact version."""
    sent = request.META.get('HTTP_IF_NONE_MATCH', '')
    return etag in [t.strip().removeprefix('W/') for t in sent.split(',') if t.strip()]


def tag(response, etag):
    response['ETag'] = etag
    # Keep a copy, but check with us every time before using it
    response['Cache-Control'] = 'no-cache'
    return response
