"""Daily rain per barangay from Open-Meteo: the archive for training, the live feed for the forecast."""
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

ARCHIVE_URL = 'https://archive-api.open-meteo.com/v1/archive'
LIVE_URL = 'https://api.open-meteo.com/v1/forecast'
USER_AGENT = 'GeoAlert-Talisay/1.0 (hazard model rain)'
ARCHIVE_FIRST_DAY = date(2016, 12, 18)
CSV_FIRST_DAY_LIMIT = date(2020, 12, 18)  # the file must reach back at least this far
CHUNK = 100
ATTEMPTS = 3
RETRY_WAITS = (30, 60)
MIN_WAIT = 13
MINUTE_LIMIT, HOUR_LIMIT = 500, 4500  # Open-Meteo free tier, in weighted calls
LIVE_PAST_DAYS_MAX = 92
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


def request_cost(n_points, n_days):
    """Open-Meteo counts a request over two weeks as several calls, once per location."""
    return n_points * max(1, n_days / 14)


def pace_wait(cost, planned_total):
    """Seconds to wait after a request so the plan stays inside the minute or the hour limit."""
    if planned_total <= HOUR_LIMIT:
        return max(MIN_WAIT, cost * 60 / MINUTE_LIMIT)
    return max(MIN_WAIT, cost * 3600 / HOUR_LIMIT)


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


def _parse(payload, n_points):
    """Validate an Open-Meteo reply: one (cell, days, values) per point sent, in order. ValueError if malformed."""
    entries = [payload] if isinstance(payload, dict) else payload
    if not isinstance(entries, list) or len(entries) != n_points:
        raise ValueError(f'unexpected reply, wanted {n_points} locations: {str(payload)[:200]}')
    out = []
    for entry in entries:
        try:
            daily = entry['daily']
            days, values = daily['time'], daily['precipitation_sum']
            cell = (float(entry['latitude']), float(entry['longitude']))
            parsed = [date.fromisoformat(d) for d in days]
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f'malformed location in reply ({exc!r}): {str(entry)[:200]}') from exc
        if len(days) != len(values):
            raise ValueError('malformed location in reply: time and precipitation_sum differ in length')
        out.append((cell, parsed, values))
    return out


def _span_text(a, b):
    return f'{a.isoformat()}..{b.isoformat()}'


def _params(chunk, points, a, b):
    return {
        'latitude': ','.join(str(points[i][0]) for i in chunk),
        'longitude': ','.join(str(points[i][1]) for i in chunk),
        'start_date': a.isoformat(), 'end_date': b.isoformat(),
        'daily': 'precipitation_sum', 'models': 'ecmwf_ifs', 'timezone': 'Asia/Manila'}


def download_archive(points, start, end, get=None, sleep=time.sleep, log=print, stats=None):
    """Daily rain for every barangay from `start` to `end`, and the grid cell served for each.

    `points` maps barangay id to (lat, lon). One series is downloaded per distinct grid cell and copied to
    every barangay in it. `stats`, if given, receives 'retries' and 'failed'.
    """
    getter = get or globals()['get']
    stats = stats if stats is not None else {}
    stats['retries'], stats['failed'] = 0, []
    ids = sorted(points)

    # Discovery: one day per point, to learn the grid cell Open-Meteo serves for each barangay.
    disc = [(ids[i:i + CHUNK], request_cost(len(ids[i:i + CHUNK]), 1)) for i in range(0, len(ids), CHUNK)]
    cells, disc_pending = {}, []
    for chunk, cost in disc:
        try:
            entries = _parse(_fetch(getter, ARCHIVE_URL, _params(chunk, points, end, end), sleep, stats), len(chunk))
        except (requests.RequestException, ValueError) as exc:
            raise CommandError(f'Open-Meteo failed to name the grid cells for {end.isoformat()}: {exc}') from exc
        for bid, (cell, _days, _values) in zip(chunk, entries):
            cells[bid] = cell
        disc_pending.append(cost)
    groups = {}
    for bid in ids:
        groups.setdefault(cells[bid], []).append(bid)
    reps = sorted(g[0] for g in groups.values())
    log(f'{len(ids)} points -> {len(groups)} grid cells')

    rep_chunks = [reps[i:i + CHUNK] for i in range(0, len(reps), CHUNK)]
    plan = []
    # Newest first: if Open-Meteo's daily cap is hit, it lands on the optional pre-2020 spans.
    for year in range(end.year, start.year - 1, -1):
        a, b = max(start, date(year, 1, 1)), min(end, date(year, 12, 31))
        for chunk in rep_chunks:
            plan.append((a, b, chunk, request_cost(len(chunk), (b - a).days + 1)))
    total = sum(disc_pending) + sum(p[3] for p in plan)
    disc_waits = [pace_wait(c, total) for c in disc_pending]  # also after the last one: archive requests follow
    waits = [pace_wait(p[3], total) for p in plan[:-1]]
    log(f'Open-Meteo plan: {len(disc) + len(plan)} requests, newest first, {total:.0f} weighted calls, '
        f'about {(sum(disc_waits) + sum(waits)) / 60:.0f} minutes of waiting.')
    for w in disc_waits:
        sleep(w)

    rain = {b: {} for b in ids}
    for n, (a, b, chunk, _cost) in enumerate(plan):
        try:
            entries = _parse(_fetch(getter, ARCHIVE_URL, _params(chunk, points, a, b), sleep, stats), len(chunk))
        except (requests.RequestException, ValueError) as exc:
            if b >= CSV_FIRST_DAY_LIMIT:
                raise CommandError(f'Open-Meteo failed for {_span_text(a, b)}: {exc}') from exc
            stats['failed'].append(_span_text(a, b))
            log(f'Open-Meteo failed for {_span_text(a, b)}, no values for it: {exc}')
            entries = []
        for rep, (cell, day_list, values) in zip(chunk, entries):
            if cell != cells[rep]:
                log(f'Warning: barangay {rep} got grid cell {cell} for {_span_text(a, b)}, '
                    f'keeping the first cell {cells[rep]}.')
            for member in groups[cells[rep]]:
                for d, mm in zip(day_list, values):
                    rain[member][d] = mm
        if n < len(waits):
            sleep(waits[n])

    valued = {d for series in rain.values() for d, v in series.items() if v is not None}
    if not valued:
        raise CommandError('Open-Meteo returned no rain values at all.')
    first, last = min(valued), max(valued)
    years = {d.year for d in valued}
    kept = sorted({d for series in rain.values() for d in series
                   if first <= d <= last and d.year in years})
    rain = {bid: {d: series.get(d) for d in kept} for bid, series in rain.items()}
    log(f'First day with rain values: {first.isoformat()}.')
    if first > CSV_FIRST_DAY_LIMIT:
        raise CommandError(f'The rain archive starts on {first.isoformat()}, after {CSV_FIRST_DAY_LIMIT.isoformat()}.')
    return rain, cells


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
    """Rain on days strictly between `after` and `today`, or None when Open-Meteo cannot be reached."""
    gap = (today - after).days
    if gap <= 1 or not cells:
        return {b: {} for b in cells}
    key = 'hazard-rain-recent:' + hashlib.sha1(
        repr((sorted(cells.items()), after.isoformat(), today.isoformat())).encode()).hexdigest()
    hit = cache.get(key)
    if hit is not None:
        return None if hit == _FAILED else hit
    getter = get or globals()['get']
    distinct = sorted(set(cells.values()))
    params = {
        'latitude': ','.join(str(c[0]) for c in distinct), 'longitude': ','.join(str(c[1]) for c in distinct),
        'daily': 'precipitation_sum', 'models': 'ecmwf_ifs', 'timezone': 'Asia/Manila',
        'past_days': min(LIVE_PAST_DAYS_MAX, gap), 'forecast_days': 1}
    try:
        entries = _parse(getter(LIVE_URL, params), len(distinct))
        series = {cell: {day: mm for day, mm in zip(days, values) if after < day < today and mm is not None}
                  for cell, (_, days, values) in zip(distinct, entries)}
        out = {b: dict(series[c]) for b, c in cells.items()}
    except Exception:
        logger.warning('Live rain from Open-Meteo failed; not asked again for %d minutes.', LIVE_FAIL_TTL // 60,
                       exc_info=True)
        cache.set(key, _FAILED, LIVE_FAIL_TTL)
        return None
    cache.set(key, out, LIVE_TTL)
    return out
