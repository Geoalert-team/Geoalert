"""
The two public lists, videos and categories, kept in the cache.

Before a typhoon many residents open the What To Do page at once, and each
visit asked Supabase for both lists: two queries, each borrowing one of the
pooler's 15 connections. Now the rows are kept in the cache (the file cache
in settings, shared by every gunicorn worker), so a visit while the rows are
fresh makes no query at all.

Every save or delete of a video or a category moves a version number once
its transaction commits (wired in apps.py), and the rows are kept under the
version, so a change shows on the very next read. Moving it after the commit
means a read can't store the old rows under the new version. Both lists
share one version: a video row carries its category's name, so a rename
changes the video list too.

The rows also expire after 60 seconds, for changes this server never hears
of: a teammate's laptop uses the same database but its own cache, and an
edit made straight in the database sends no signal.

Only rows are kept, never finished responses. An MP4's link is signed for an
hour, so the view builds it from the row on every request.

A broken cache (a full disk, say) never fails a request: the lists are read
from the database as before, and a save still succeeds.
"""
import uuid

from django.core.cache import cache
from django.db import transaction

KEEP = 60  # seconds
VERSION_KEY = 'geoalert:tutorials:version'


def _version():
    version = cache.get(VERSION_KEY)
    if version is None:
        cache.add(VERSION_KEY, uuid.uuid4().hex, None)
        version = cache.get(VERSION_KEY)
    return version


def _bump_now():
    try:
        cache.set(VERSION_KEY, uuid.uuid4().hex, None)
    except Exception:
        pass  # the rows still expire within KEEP seconds


def bump(**_signal_kwargs):
    """Mark both lists as changed once the current transaction commits."""
    transaction.on_commit(_bump_now)


def rows(name, build):
    """The rows `build` reads from the database, read at most once per version and minute."""
    try:
        key = f'geoalert:tutorials:{name}:{_version()}'
        found = cache.get(key)
    except Exception:
        return build()  # no cache: read every time, as before
    if found is None:
        found = build()
        try:
            cache.set(key, found, KEEP)
        except Exception:
            pass
    return found
