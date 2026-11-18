"""
PAGASA's public CAP 1.2 alert feed (Atom, CC BY 4.0): fetch new alerts, store them,
and work out whether each is active in Talisay and what minimum colour it implies.
"""
import logging
import threading
import xml.etree.ElementTree as ET
from datetime import datetime, timezone as dt_tz

from django.contrib.gis.geos import Point, Polygon
from django.db import IntegrityError, close_old_connections, connection, transaction

from apps.rainwatch import assess
from apps.rainwatch.models import PagasaAlert
from apps.rainwatch.rules import YELLOW

logger = logging.getLogger(__name__)

FEED_URL = 'https://publicalert.pagasa.dost.gov.ph/feeds/'
TALISAY = (10.2835, 123.8212)  # lat, lon
CEBU_PSGC = '072200000'
MAX_SPAN = 3.0  # degrees: a polygon wider or taller than about a province says nothing about Cebu
CHECK_KEY = 'geoalert:pagasa-feed-check'
CHECK_EVERY = 3600
TIMEOUT = 20
USER_AGENT = 'GeoAlert-Talisay/1.0 (PAGASA alerts)'
THREAD_NAME = 'pagasa-feed-check'

ATOM = '{http://www.w3.org/2005/Atom}'
CAP = '{urn:oasis:names:tc:emergency:cap:1.2}'
SEVERITY_RANK = {'Moderate': 1, 'Severe': 2, 'Extreme': 3}


def _http_get(url):
    import requests
    response = requests.get(url, timeout=TIMEOUT, headers={'User-Agent': USER_AGENT})
    response.raise_for_status()
    return response.content  # bytes: requests would guess ISO-8859-1 for text/* without a charset


def _decode(text):
    if isinstance(text, str):
        return text
    try:
        return text.decode('utf-8')
    except UnicodeDecodeError:
        return text.decode('latin-1')


def _root(text):
    try:
        return ET.fromstring(text.encode('utf-8') if isinstance(text, str) else text)
    except ET.ParseError as exc:
        raise ValueError(f'not valid XML: {exc}') from exc


def parse_feed(text):
    """(CAP identifier, CAP URL) for each Atom entry."""
    root = _root(text)
    if root.tag != f'{ATOM}feed':
        raise ValueError('not an Atom feed')
    entries = []
    for entry in root.findall(f'{ATOM}entry'):
        ident = (entry.findtext(f'{ATOM}id') or '').strip()
        if ident.startswith('urn:uuid:'):
            ident = ident[len('urn:uuid:'):]
        url = ''
        for link in entry.findall(f'{ATOM}link'):
            if link.get('type') == 'application/cap+xml' and link.get('href'):
                url = link.get('href')
                break
        if ident and url:
            entries.append((ident, url))
    return entries


def _time(value, required=False, name=''):
    value = (value or '').strip()
    if not value:
        if required:
            raise ValueError(f'missing <{name}>')
        return None
    try:
        when = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f'bad <{name}>: {value!r}') from exc
    if when.tzinfo is None:
        when = when.replace(tzinfo=dt_tz.utc)
    return when.astimezone(dt_tz.utc)


def _polygon(text):
    points = []
    for pair in text.split():
        lat, lon = pair.split(',')
        points.append((float(lat), float(lon)))
    return points


def parse_cap(text, url):
    """A CAP 1.2 alert as a dict shaped like PagasaAlert, plus polygons and geocodes."""
    root = _root(text)
    if root.tag != f'{CAP}alert':
        raise ValueError('not a CAP 1.2 alert')

    def top(tag):
        return (root.findtext(f'{CAP}{tag}') or '').strip()

    identifier = top('identifier')
    if not identifier:
        raise ValueError('missing <identifier>')
    info = root.find(f'{CAP}info')
    if info is None:
        raise ValueError('missing <info>')

    def inf(tag):
        return (info.findtext(f'{CAP}{tag}') or '').strip()

    sent = _time(top('sent'), True, 'sent')
    expires = _time(inf('expires'), True, 'expires')
    polygons, geocodes, names = [], [], []
    try:
        for area in info.findall(f'{CAP}area'):
            name = (area.findtext(f'{CAP}areaDesc') or '').strip()
            if name:
                names.append(name)
            polygons += [_polygon(p.text or '') for p in area.findall(f'{CAP}polygon')]
            geocodes += [(g.findtext(f'{CAP}value') or '').strip() for g in area.findall(f'{CAP}geocode')]
    except ValueError as exc:
        raise ValueError(f'bad <polygon>: {exc}') from exc
    return {
        'identifier': identifier,
        'sent': sent,
        'msg_type': top('msgType'),
        'references': top('references'),
        'event': inf('event'),
        'category': inf('category'),
        'response_type': inf('responseType'),
        'urgency': inf('urgency'),
        'severity': inf('severity'),
        'certainty': inf('certainty'),
        'effective': _time(inf('effective')),
        'expires': expires,
        'headline': inf('headline'),
        'description': inf('description'),
        'area_desc': '; '.join(names),
        'cap_url': url,
        'raw_xml': _decode(text),
        'polygons': polygons,
        'geocodes': geocodes,
    }


def _province_sized(ring):
    """The ring's bounding box spans at most MAX_SPAN degrees of latitude and of longitude."""
    lats, lons = [lat for lat, _ in ring], [lon for _, lon in ring]
    return max(lats) - min(lats) <= MAX_SPAN and max(lons) - min(lons) <= MAX_SPAN


def covers_talisay(cap):
    """Whether an alert is about Talisay. An alert counts only if it names Cebu or its area is about
    province-sized (user ruling 2026-11-18): PAGASA draws Tropical Cyclone Alerts over the whole Philippine
    Area of Responsibility, which holds the city point without saying anything about Cebu.

    - a province-sized `<area>` polygon (bounding box at most 3.0 degrees each way) holds the city point, or
    - a geocode is Cebu's PSGC code, or
    - with no province-sized polygon at all, `areaDesc` names Cebu.
    """
    here = Point(TALISAY[1], TALISAY[0])
    rings = [ring for ring in cap.get('polygons') or [] if ring and _province_sized(ring)]
    for ring in rings:
        try:
            if Polygon([(lon, lat) for lat, lon in ring]).contains(here):
                return True
        except Exception:  # a degenerate ring cannot hold the point
            continue
    if CEBU_PSGC in (cap.get('geocodes') or []):
        return True
    return not rings and 'cebu' in (cap.get('area_desc') or '').lower()


def _kind(alert):
    """Which row of spec 6.5's mapping table the event name falls in: 'flood', 'rain' or None."""
    event = (alert.event or '').lower()
    if 'flood' in event:
        return 'flood'
    if 'tropical cyclone' in event or 'rainfall' in event:
        return 'rain'
    return None


def is_mapped(alert):
    """The event type has a floor mapping (whatever this alert's severity); staff review the others."""
    return _kind(alert) is not None


def floor_for(alert):
    """The least colour per hazard this alert implies: {'Flood': level, 'Landslide': level}."""
    kind = _kind(alert)
    sev = SEVERITY_RANK.get(alert.severity, 0)
    if kind == 'flood':
        return {'Flood': max(YELLOW, sev)}
    if kind == 'rain':
        return {'Flood': sev, 'Landslide': sev} if sev > 0 else {}
    return {}


def referenced_identifiers(alerts):
    """Identifiers that some alert in `alerts` replaces or cancels."""
    found = set()
    for alert in alerts:
        for entry in (alert.references or '').split():
            parts = entry.split(',')
            if len(parts) >= 2 and parts[1]:
                found.add(parts[1])
    return found


def is_active(alert, now, newer_references):
    start = alert.effective or alert.sent
    if not alert.covers_talisay or start is None or alert.expires is None:
        return False
    if not (start <= now < alert.expires):
        return False
    if alert.msg_type == 'Cancel' or alert.response_type == 'AllClear' or alert.urgency == 'Past':
        return False
    return alert.identifier not in newer_references


def check_feed(get=None, now=None):
    """Store each feed entry not yet held. Returns how many were stored."""
    get = get or _http_get
    try:
        entries = parse_feed(get(FEED_URL))
    except Exception as exc:
        logger.warning('PAGASA feed could not be read: %s', exc)
        return 0
    known = set(PagasaAlert.objects.filter(identifier__in=[i for i, _ in entries])
                .values_list('identifier', flat=True))
    stored = 0
    for ident, url in entries:
        if ident in known:
            continue
        try:
            cap = parse_cap(get(url), url)
            cap['covers_talisay'] = covers_talisay(cap)
            fields = {k: v for k, v in cap.items() if k not in ('polygons', 'geocodes')}
            try:
                with transaction.atomic():
                    _, created = PagasaAlert.objects.get_or_create(
                        identifier=fields.pop('identifier'), defaults=fields)
            except IntegrityError:
                created = False
            stored += 1 if created else 0
        except Exception as exc:
            logger.warning('Skipped PAGASA alert %s: %s', ident, exc)
    if stored:
        assess.bump()
    return stored


def _run():
    try:
        check_feed()
    except Exception:
        logger.exception('The PAGASA feed check failed.')
    finally:
        close_old_connections()
        connection.close()


def check_in_background():
    """Start the feed check in a daemon thread unless one is still running."""
    if any(t.name == THREAD_NAME and t.is_alive() for t in threading.enumerate()):
        return False
    threading.Thread(target=_run, name=THREAD_NAME, daemon=True).start()
    return True
