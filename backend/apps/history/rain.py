"""
Daily rain per barangay from NASA POWER (https://power.larc.nasa.gov): the archive for training and the
same service for the rain so far, so both always share one source.

POWER's corrected daily rain (PRECTOTCORR) comes from NASA's MERRA-2 and GEOS-IT models on a grid of
0.5 by 0.625 degrees (about 55 by 69 km), in local solar days, a few days behind today. POWER data have no
restrictions on use (CC BY 4.0, commercial use included); credit the POWER Project wherever they are
shown. No account or key is needed.

Talisay is far smaller than one cell and a cell edge (10.25 N) runs through it, so every barangay reads
the one cell that holds the city's average point (city_cell); terrain, not rain, sets barangays apart.
"""
import csv
import hashlib
import logging
import time
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import requests
from django.core.cache import cache
from django.core.management.base import CommandError

from apps.history.hazard_data import DATA_DIR

logger = logging.getLogger(__name__)

POWER_URL = 'https://power.larc.nasa.gov/api/temporal/daily/point'
POWER_PARAMS = {'parameters': 'PRECTOTCORR', 'community': 'AG', 'time-standard': 'LST', 'format': 'JSON'}
USER_AGENT = 'GeoAlert-Talisay/1.0 (hazard model rain)'
LAT_STEP, LON_STEP = 0.5, 0.625         # POWER's native grid (MERRA-2)
FILL = -999.0                           # POWER's value for a day it has not filled
ARCHIVE_FIRST_DAY = date(2016, 12, 18)  # the file starts here; POWER itself reaches back to 1981
CSV_FIRST_DAY_LIMIT = date(2020, 12, 18)  # the file must reach back at least this far
ATTEMPTS = 3
RETRY_WAITS = (30, 60)
PAUSE = 1                               # seconds between archive requests, to be polite
LIVE_TTL, LIVE_FAIL_TTL = 3 * 3600, 15 * 60
_FAILED = 'hazard-rain-recent-failed'  # cache.get returns None on a miss, so a failure needs its own marker
CSV_HEADER = ['barangay_id', 'cell_lat', 'cell_lon', 'date', 'mm']


def get(url, params):
    resp = requests.get(url, params=params, timeout=60, headers={'User-Agent': USER_AGENT})
    resp.raise_for_status()
    return resp.json()


def representative_points():
    from apps.barangays.models import Barangay
    out = {}
    for b in Barangay.objects.exclude(boundary__isnull=True).order_by('id'):
        p = b.boundary.point_on_surface
        out[b.id] = (p.y, p.x)
    return out


def city_cell(points):
    """The POWER grid point nearest the average of `points` ({id: (lat, lon)}), as (lat, lon)."""
    lat = sum(p[0] for p in points.values()) / len(points)
    lon = sum(p[1] for p in points.values()) / len(points)
    return round(round(lat / LAT_STEP) * LAT_STEP, 4), round(round(lon / LON_STEP) * LON_STEP, 4)


def _retryable(exc):
    if isinstance(exc, (requests.Timeout, requests.ConnectionError)):
        return True
    if isinstance(exc, requests.HTTPError) and exc.response is not None:
        code = exc.response.status_code
        return code == 429 or code >= 500
    return False


def _fetch(getter, url, params, sleep, stats):
    for attempt in range(ATTEMPTS):
        try:
            return getter(url, params)
        except requests.RequestException as exc:
            if not _retryable(exc) or attempt == ATTEMPTS - 1:
                raise
            stats['retries'] += 1
            sleep(RETRY_WAITS[attempt])


def _params(cell, a, b):
    return {**POWER_PARAMS, 'latitude': cell[0], 'longitude': cell[1],
            'start': a.strftime('%Y%m%d'), 'end': b.strftime('%Y%m%d')}


def _parse(payload):
    """A POWER reply as {date: mm or None}; its fill value (-999) is None. ValueError if malformed."""
    try:
        series = payload['properties']['parameter']['PRECTOTCORR']
        fill = float((payload.get('header') or {}).get('fill_value', FILL))
        out = {}
        for key, value in series.items():
            if len(key) != 8 or not key.isdigit():
                raise ValueError(f'day {key!r} is not YYYYMMDD')
            mm = float(value)
            out[date(int(key[:4]), int(key[4:6]), int(key[6:]))] = None if mm in (fill, FILL) else mm
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise ValueError(f'malformed NASA POWER reply ({exc!r}): {str(payload)[:200]}') from exc
    if not out:
        raise ValueError(f'NASA POWER reply with no days: {str(payload)[:200]}')
    return out


def _span_text(a, b):
    return f'{a.isoformat()}..{b.isoformat()}'


def download_archive(points, start, end, get=None, sleep=time.sleep, log=print, stats=None):
    """Daily rain for every barangay from `start` to `end`, and the grid cell each one reads.

    `points` maps barangay id to (lat, lon). One series is downloaded, for the city's cell (city_cell), a
    year per request, newest first, and copied to every barangay. A year before CSV_FIRST_DAY_LIMIT that
    fails is logged and left out; a later one stops the download. `stats`, if given, receives 'retries'
    and 'failed'.
    """
    getter = get or globals()['get']
    stats = stats if stats is not None else {}
    stats['retries'], stats['failed'] = 0, []
    ids = sorted(points)
    cell = city_cell(points)
    log(f'{len(ids)} barangays -> 1 NASA POWER grid cell {cell}')
    plan = [(max(start, date(year, 1, 1)), min(end, date(year, 12, 31)))
            for year in range(end.year, start.year - 1, -1)]
    log(f'NASA POWER plan: {len(plan)} requests, newest year first.')

    series = {}
    for n, (a, b) in enumerate(plan):
        try:
            got = _parse(_fetch(getter, POWER_URL, _params(cell, a, b), sleep, stats))
        except (requests.RequestException, ValueError) as exc:
            if b >= CSV_FIRST_DAY_LIMIT:
                raise CommandError(f'NASA POWER failed for {_span_text(a, b)}: {exc}') from exc
            stats['failed'].append(_span_text(a, b))
            log(f'NASA POWER failed for {_span_text(a, b)}, no values for it: {exc}')
            got = {}
        series.update({d: mm for d, mm in got.items() if a <= d <= b})
        if n < len(plan) - 1:
            sleep(PAUSE)

    valued = {d for d, mm in series.items() if mm is not None}
    if not valued:
        raise CommandError('NASA POWER returned no rain values at all.')
    first, last = min(valued), max(valued)
    years = {d.year for d in valued}
    kept = sorted(d for d in series if first <= d <= last and d.year in years)
    log(f'First day with rain values: {first.isoformat()}.')
    if first > CSV_FIRST_DAY_LIMIT:
        raise CommandError(f'The rain archive starts on {first.isoformat()}, after {CSV_FIRST_DAY_LIMIT.isoformat()}.')
    return {bid: {d: series[d] for d in kept} for bid in ids}, {bid: cell for bid in ids}


@dataclass
class RainFile:
    rain: dict
    cells: dict
    first_day: date | None
    last_day: date | None


def write_rain_csv(path, rain, cells):
    with open(path, 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(CSV_HEADER)
        for bid in sorted(rain):
            lat, lon = cells[bid]
            for d in sorted(rain[bid]):
                mm = rain[bid][d]
                w.writerow([bid, repr(float(lat)), repr(float(lon)), d.isoformat(), '' if mm is None else repr(float(mm))])


def read_rain_csv(path=DATA_DIR / 'rain_daily.csv'):
    rain, cells, every = {}, {}, set()
    with open(path, newline='') as f:  # FileNotFoundError when the file is missing
        for row in csv.DictReader(f):
            bid, d = int(row['barangay_id']), date.fromisoformat(row['date'])
            cells[bid] = (float(row['cell_lat']), float(row['cell_lon']))
            rain.setdefault(bid, {})[d] = float(row['mm']) if row['mm'] != '' else None
            every.add(d)
    return RainFile(rain, cells, min(every, default=None), max(every, default=None))


def complete_years(rf):
    """Years where every barangay has rain on every day of the year and the 13 days before it."""
    if not rf.rain or rf.first_day is None:
        return []
    out = []
    for year in range(rf.first_day.year, rf.last_day.year + 1):
        needed = [date(year - 1, 12, 31) - timedelta(days=i) for i in range(13)]
        d = date(year, 1, 1)
        while d.year == year:
            needed.append(d)
            d += timedelta(days=1)
        if all(series.get(day) is not None for series in rf.rain.values() for day in needed):
            out.append(year)
    return out


def recent_rain(cells, after, today, get=None):
    """
    Rain on days strictly between `after` and `today`, from NASA POWER, one request per cell; days POWER
    has not filled yet are left out. None when POWER cannot be reached.
    """
    gap = (today - after).days
    if gap <= 1 or not cells:
        return {b: {} for b in cells}
    key = 'hazard-rain-recent:' + hashlib.sha1(
        repr((sorted(cells.items()), after.isoformat(), today.isoformat())).encode()).hexdigest()
    hit = cache.get(key)
    if hit is not None:
        return None if hit == _FAILED else hit
    getter = get or globals()['get']
    first, last = after + timedelta(days=1), today - timedelta(days=1)
    try:
        series = {}
        for cell in sorted(set(cells.values())):
            got = _parse(getter(POWER_URL, _params(cell, first, last)))
            series[cell] = {d: mm for d, mm in got.items() if after < d < today and mm is not None}
        out = {b: dict(series[c]) for b, c in cells.items()}
    except Exception:
        logger.warning('Live rain from NASA POWER failed; not asked again for %d minutes.', LIVE_FAIL_TTL // 60,
                       exc_info=True)
        cache.set(key, _FAILED, LIVE_FAIL_TTL)
        return None
    cache.set(key, out, LIVE_TTL)
    return out
