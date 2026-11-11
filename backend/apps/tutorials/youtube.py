"""
Reading YouTube links, and asking YouTube about a video.

Staff paste links in every shape YouTube hands out (the address bar, the
Share button, a Shorts link, an embed code). Only the 11-character video ID
is kept: the page builds the player, thumbnail and "Watch on YouTube" links
from it, so a pasted link's tracking parameters (?si=, &list=, &t=) never
reach the database.

lookup() is called only by the form's "is this link real" check
(GET /api/tutorials/youtube-check/), never when a video is saved: the form
has already checked it, and a slow or unreachable YouTube must not stop
staff from saving.
"""
import re
from urllib.parse import parse_qs, urlsplit

import requests

OEMBED_URL = 'https://www.youtube.com/oembed'
TIMEOUT = 5  # seconds

_ID = re.compile(r'[A-Za-z0-9_-]{11}')
_YOUTUBE_HOSTS = {'youtube.com', 'youtube-nocookie.com'}
_PATH_ID_PREFIXES = ('/shorts/', '/embed/')


def _video_id(candidate):
    return candidate if candidate and _ID.fullmatch(candidate) else None


def parse_youtube_id(text):
    """
    The video ID in a YouTube link, or None.

    Accepts watch?v= links (www., m. or neither, with any other parameters),
    youtu.be/<id>, /shorts/<id>, /embed/<id> on youtube.com or
    youtube-nocookie.com, and a bare ID. Links to channels, playlists and
    other sites give None.
    """
    text = (text or '').strip()
    if not text:
        return None
    if _ID.fullmatch(text):
        return text
    if '://' not in text:
        text = 'https://' + text
    try:
        parts = urlsplit(text)
        host = (parts.hostname or '').lower()
    except ValueError:
        return None
    for prefix in ('www.', 'm.'):
        if host.startswith(prefix):
            host = host[len(prefix):]
            break

    path = parts.path
    if host == 'youtu.be':
        return _video_id(path.strip('/').split('/')[0])
    if host not in _YOUTUBE_HOSTS:
        return None
    if path.rstrip('/') == '/watch':
        return _video_id((parse_qs(parts.query).get('v') or [''])[0])
    for prefix in _PATH_ID_PREFIXES:
        if path.startswith(prefix):
            return _video_id(path[len(prefix):].split('/')[0])
    return None


def lookup(youtube_id):
    """
    What YouTube says about a video, through its public oEmbed endpoint (no
    API key):

      {'status': 'ok', 'title': '...'}   it exists and can be embedded
      {'status': 'not_found'}            deleted, private, or not embeddable
      {'status': 'unchecked'}            YouTube didn't answer
    """
    try:
        response = requests.get(
            OEMBED_URL,
            params={'url': f'https://www.youtube.com/watch?v={youtube_id}', 'format': 'json'},
            timeout=TIMEOUT,
        )
        if response.status_code == 200:
            return {'status': 'ok', 'title': str(response.json().get('title') or '').strip()}
    except (requests.RequestException, ValueError):
        return {'status': 'unchecked'}
    if response.status_code in (400, 401, 403, 404):
        return {'status': 'not_found'}
    return {'status': 'unchecked'}
