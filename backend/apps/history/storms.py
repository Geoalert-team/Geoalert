"""
Storm days from IBTrACS (NOAA NCEI), the flood model's "storm flag": was a tropical-cyclone centre within
STORM_RADIUS_KM of Talisay at any time in the STORM_HOURS hours to the end of the day (Asia/Manila)?

Every IBTrACS track point (all storm types, UTC time, no interpolation) within the radius flags its own Manila
day (a point at exactly Manila midnight belongs to the day that is ending) and the next two. Coverage comes
from the file's HTTP Last-Modified time, not from the latest track point, since a quiet season has no recent
points. NumPy and scikit-learn are not needed here.
"""
import csv
import json
import logging
import math
import os
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Iterable

import requests
from django.core.cache import cache

from apps.history.hazard_data import DATA_DIR, MANILA
from apps.history.rain import ARCHIVE_FIRST_DAY, USER_AGENT

logger = logging.getLogger(__name__)

STORM_RADIUS_KM = 300.0
STORM_HOURS = 72
_BASE = 'https://www.ncei.noaa.gov/data/international-best-track-archive-for-climate-stewardship-ibtracs/v04r01/access/csv/'
WP_URL = _BASE + 'ibtracs.WP.list.v04r01.csv'
LAST3_URL = _BASE + 'ibtracs.last3years.list.v04r01.csv'
ACTIVE_URL = _BASE + 'ibtracs.ACTIVE.list.v04r01.csv'
STORM_FILE = DATA_DIR / 'storm_days.csv'
META_FILE = DATA_DIR / 'storm_days.meta.json'
EARTH_KM = 6371.0088
RECENT_KEY, ACTIVE_KEY = 'hazard-storms-recent', 'hazard-storms-active'
_RECENT_DAY_KEY, _RECENT_FAILED, _ACTIVE_FAILED = 'hazard-storms-recent-day', 'hazard-storms-recent-failed', 'hazard-storms-active-failed'
ACTIVE_TTL, FAIL_TTL = 3 * 3600, 15 * 60
FRESH_DAYS = 7
CSV_HEADER = ['date', 'sid', 'name', 'km']


@dataclass(frozen=True)
class TrackPoint:
    sid: str
    name: str
    time: datetime      # aware, UTC
    lat: float
    lon: float


@dataclass
class StormDays:
    days: dict          # date -> (sid, name, closest km)
    first_day: date
    last_day: date

    def flag(self, day):
        """1 on a storm day, 0 on another covered day, None outside [first_day, last_day]."""
        if not self.first_day <= day <= self.last_day:
            return None
        return 1 if day in self.days else 0

    def name(self, day):
        hit = self.days.get(day)
        return hit[1] if hit else None


DOWNLOAD_TIMEOUT = (5, 20)     # seconds to connect, then at most between reads: a request may be waiting on it


def get(url):
    """Download `url`; returns (lines, Last-Modified as an aware datetime). `lines` is read lazily."""
    resp = requests.get(url, stream=True, timeout=DOWNLOAD_TIMEOUT, headers={'User-Agent': USER_AGENT})
    resp.raise_for_status()
    stamp = resp.headers.get('Last-Modified')
    if not stamp:
        resp.close()
        raise ValueError(f'No Last-Modified header on {url}')
    return decoded_lines(resp), parsedate_to_datetime(stamp)


def decoded_lines(resp):
    """The response's lines as text; requests gives bytes when it cannot infer an encoding, so default to UTF-8."""
    resp.encoding = resp.encoding or 'utf-8'
    for line in resp.iter_lines(decode_unicode=True):
        yield line.decode('utf-8', 'replace') if isinstance(line, bytes) else line


def haversine_km(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 2 * EARTH_KM * math.asin(math.sqrt(a))


def talisay_centre():
    """(lat, lon) of the centroid of the union of the barangay boundaries."""
    from django.contrib.gis.db.models.aggregates import Union
    from apps.barangays.models import Barangay
    union = Barangay.objects.exclude(boundary__isnull=True).aggregate(u=Union('boundary'))['u']
    if union is None:
        raise ValueError('No barangay boundaries in the database.')
    c = union.centroid
    return c.y, c.x


def _num(text):
    text = (text or '').strip()
    return float(text) if text else None


def parse_ibtracs(lines: Iterable[str], centre, since: date):
    """Track points within the radius that can flag `since` or later: ISO_TIME (UTC) on or after `since` minus
    STORM_HOURS (a point just before `since` still flags its first days). Line 1 is the header, line 2 the units."""
    earliest = since - timedelta(hours=STORM_HOURS)
    reader = csv.reader(lines)
    header = [h.strip() for h in next(reader, [])]
    col = {h: i for i, h in enumerate(header)}
    for need in ('SID', 'NAME', 'ISO_TIME', 'LAT', 'LON'):
        if need not in col:
            raise ValueError(f'IBTrACS file has no {need} column')
    next(reader, None)  # the units row
    out = []
    for r in reader:
        if len(r) <= max(col['SID'], col['NAME'], col['ISO_TIME'], col['LAT'], col['LON']):
            continue
        try:
            when = datetime.strptime(r[col['ISO_TIME']].strip(), '%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc)
            lat, lon = _num(r[col['LAT']]), _num(r[col['LON']])
        except ValueError:
            continue
        if lat is None or lon is None or when.date() < earliest:
            continue
        if haversine_km(centre[0], centre[1], lat, lon) > STORM_RADIUS_KM:
            continue
        out.append(TrackPoint(r[col['SID']].strip(), r[col['NAME']].strip(), when, lat, lon))
    return out


def flag_days(points, centre):
    """{day: (sid, name, closest km)}: each point flags its Manila day and the next two (72 hours to day's end)."""
    out = {}
    span = STORM_HOURS // 24
    for p in points:
        km = haversine_km(centre[0], centre[1], p.lat, p.lon)
        first = (p.time.astimezone(MANILA) - timedelta(microseconds=1)).date()  # midnight belongs to the day ending
        for i in range(span):
            d = first + timedelta(days=i)
            if d not in out or km < out[d][2]:
                out[d] = (p.sid, p.name, km)
    return out


def covered_through(last_modified: datetime) -> date:
    return last_modified.astimezone(MANILA).date() - timedelta(days=1)


def build(points, centre, since: date, last_modified: datetime) -> StormDays:
    days = {d: v for d, v in flag_days(points, centre).items() if d >= since}
    return StormDays(days, since, covered_through(last_modified))


def write_storm_days(sd: StormDays, source: str, fetched: datetime, centre, path=STORM_FILE, meta_path=META_FILE):
    tmp_csv, tmp_meta = Path(f'{path}.tmp'), Path(f'{meta_path}.tmp')
    with open(tmp_csv, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(CSV_HEADER)
        for d in sorted(sd.days):
            sid, name, km = sd.days[d]
            w.writerow([d.isoformat(), sid, name, repr(float(km))])
    meta = {'source': source, 'fetched': fetched.isoformat(), 'centre': [centre[0], centre[1]],
            'first_day': sd.first_day.isoformat(), 'last_day': sd.last_day.isoformat(),
            'radius_km': STORM_RADIUS_KM, 'hours': STORM_HOURS}
    with open(tmp_meta, 'w', encoding='utf-8') as f:
        json.dump(meta, f, indent=2)
    os.replace(tmp_csv, path)
    os.replace(tmp_meta, meta_path)


def read_storm_days(path=STORM_FILE, meta_path=META_FILE) -> StormDays:
    with open(meta_path, encoding='utf-8') as f:  # FileNotFoundError when missing
        meta = json.load(f)
    days = {}
    with open(path, newline='', encoding='utf-8') as f:
        for r in csv.DictReader(f):
            days[date.fromisoformat(r['date'])] = (r['sid'], r['name'], float(r['km']))
    return StormDays(days, date.fromisoformat(meta['first_day']), date.fromisoformat(meta['last_day']))


def merge(a: StormDays, b: StormDays) -> StormDays:
    """Union of two inputs. Coverage stays continuous: if the later input starts more than a day after the earlier
    one ends, only the earlier input's coverage is kept (gap days must read None, not 0)."""
    a, b = (a, b) if a.first_day <= b.first_day else (b, a)
    if b.first_day > a.last_day + timedelta(days=1):
        logger.warning('Storm days not merged: gap between %s and %s; coverage ends %s.',
                       a.last_day, b.first_day, a.last_day)
        return StormDays(dict(a.days), a.first_day, a.last_day)
    days = dict(a.days)
    for d, v in b.days.items():
        if d not in days or v[2] < days[d][2]:
            days[d] = v
    return StormDays(days, a.first_day, max(a.last_day, b.last_day))


def download(url, centre, since, getter=None):
    """One IBTrACS file as StormDays."""
    lines, modified = (getter or globals()['get'])(url)
    return build(parse_ibtracs(lines, centre, since), centre, since, modified)


def _recent_since(today):
    return date(today.year - 2, 1, 1)


def refresh_recent(get=None, now=None):
    """Keep the last-3-years file in the cache, fetched at most once per Manila day. False on failure; never raises."""
    try:
        now = now or datetime.now(timezone.utc)
        today = now.astimezone(MANILA).date()
        if cache.get(_RECENT_DAY_KEY) == today.isoformat() and cache.get(RECENT_KEY) is not None:
            return True
        if cache.get(_RECENT_FAILED):
            return False
        try:
            sd = download(LAST3_URL, talisay_centre(), _recent_since(today), get)
        except Exception:
            logger.warning('Recent IBTrACS download failed; not asked again for %d minutes.', FAIL_TTL // 60,
                           exc_info=True)
            cache.set(_RECENT_FAILED, 1, FAIL_TTL)
            return False
        cache.set(RECENT_KEY, sd, 2 * 86400)
        cache.set(_RECENT_DAY_KEY, today.isoformat(), 2 * 86400)
        return True
    except Exception:
        logger.warning('Recent IBTrACS refresh failed.', exc_info=True)
        return False


def _active(today, get):
    hit = cache.get(ACTIVE_KEY)
    if hit is not None:
        return hit
    if cache.get(_ACTIVE_FAILED):
        return None
    try:
        sd = download(ACTIVE_URL, talisay_centre(), today - timedelta(days=30), get)
    except Exception:
        logger.warning('Active IBTrACS download failed; not asked again for %d minutes.', FAIL_TTL // 60,
                       exc_info=True)
        cache.set(_ACTIVE_FAILED, 1, FAIL_TTL)
        return None
    cache.set(ACTIVE_KEY, sd, ACTIVE_TTL)
    return sd


def live_storm_days(base: StormDays, today: date, get=None) -> StormDays:
    """base plus the cached recent copy plus the active file. Coverage reaches today - 1 only when the active file
    was read and the recent copy ends within FRESH_DAYS of today; otherwise it is the furthest last_day available."""
    out = base
    recent = cache.get(RECENT_KEY)
    if recent is not None:
        out = merge(out, recent)
    active = _active(today, get)
    if active is not None:
        out = merge(out, active)
        if recent is not None and (today - recent.last_day).days <= FRESH_DAYS and out.last_day >= active.last_day:
            out = StormDays(out.days, out.first_day, today - timedelta(days=1))
    return out
