"""GFS rain for the 4 grid points around Talisay: NOMADS first, dynamical.org as the fallback.

No Django. eccodes, dynamical_catalog, icechunk and zarr are imported only inside the functions
that need them, so the tests run with just numpy and requests.
"""
import math
import time
from datetime import datetime, timedelta, timezone

GRID = [(10.25, 123.75), (10.25, 124.0), (10.5, 123.75), (10.5, 124.0)]
NOMADS_BASE = 'https://nomads.ncep.noaa.gov/cgi-bin/filter_gfs_0p25.pl'
USER_AGENT = 'GeoAlert-Talisay/1.0 (rain forecast job)'


def nomads_url(cycle, hour):
    return (
        f'{NOMADS_BASE}?dir=%2Fgfs.{cycle:%Y%m%d}%2F{cycle:%H}%2Fatmos'
        f'&file=gfs.t{cycle:%H}z.pgrb2.0p25.f{hour:03d}'
        '&var_APCP=on&lev_surface=on&subregion=&toplat=10.5&leftlon=123.75'
        '&rightlon=124&bottomlat=10.25'
    )


def per_hour_from_avg(avgs):
    """avgs[f-1] = mean rate (mm/s) from the last 6-h boundary to hour f. Returns mm per hour."""
    out = []
    for f, a in enumerate(avgs, start=1):
        k = (f - 1) % 6 + 1  # hours since the boundary
        prev = avgs[f - 2] if k > 1 else 0.0
        out.append(max(0.0, (k * a - (k - 1) * prev) * 3600.0))
    return out


def per_hour_from_acc(accs):
    """accs[f-1] = rain (mm) accumulated from the last 6-h boundary to hour f. Returns mm per hour.

    GFS APCP files read 0-1, 0-2 ... 0-6, then 6-7 ... 6-12, and so on, so the rain in hour f is
    the accumulation at f minus the one at f-1, except in the first hour after a boundary.
    """
    out = []
    for f, a in enumerate(accs, start=1):
        prev = accs[f - 2] if (f - 1) % 6 else 0.0
        out.append(max(0.0, a - prev))
    return out


def _default_get(url):
    import requests
    r = requests.get(url, timeout=60, headers={'User-Agent': USER_AGENT})
    r.raise_for_status()
    return r.content


def decode_grib(data):
    """GRIB2 bytes -> {(lat, lon): value} for the grid points (eccodes). APCP values are mm."""
    import eccodes
    out = {}
    handle = eccodes.codes_new_from_message(data)
    try:
        lats = eccodes.codes_get_array(handle, 'latitudes')
        lons = eccodes.codes_get_array(handle, 'longitudes')
        vals = eccodes.codes_get_values(handle)
        for la, lo, v in zip(lats, lons, vals):
            out[(round(float(la), 4), round(float(lo), 4))] = float(v)
    finally:
        eccodes.codes_release(handle)
    return out


def fetch_nomads(cycle, hours, get=None, decode=None, pause=1.0):
    get = get or _default_get
    decode = decode or decode_grib
    avgs = {p: [] for p in GRID}  # accumulated mm per hour file
    for hour in range(1, hours + 1):
        if hour > 1 and pause:
            time.sleep(pause)
        try:
            values = decode(get(nomads_url(cycle, hour)))
        except Exception as exc:
            raise RuntimeError(f'NOMADS hour {hour} missing: {exc}') from exc
        for p in GRID:
            if p not in values:
                raise RuntimeError(f'NOMADS hour {hour} has no value for {p}')
            avgs[p].append(_check(values[p], MAX_ACCUM_MM, f'NOMADS hour {hour} at {p}'))
    out = {p: per_hour_from_acc(a) for p, a in avgs.items()}
    for p, series in out.items():
        for hour, v in enumerate(series, start=1):
            _check(v, MAX_HOURLY_MM, f'NOMADS hour {hour} at {p}')
    return out


MAX_HOURLY_MM = 500.0
MAX_ACCUM_MM = 3000.0


def _check(value, limit, what):
    """Reject NaN, missing-value sentinels (e.g. 9999) and absurd rain; raise RuntimeError."""
    if not math.isfinite(value) or value < -1e-6 or value > limit:
        raise RuntimeError(f'{what} has an invalid value: {value}')
    return value


def _open_dynamical():
    import dynamical_catalog
    return dynamical_catalog.open('noaa-gfs-forecast', chunks=None)


def fetch_dynamical(hours, newest_before, opener=None):
    """Newest archived run at or before newest_before: (init_time, {point: mm per hour}).

    opener() returns the dataset (default: the dynamical.org archive); tests pass a fake.
    """
    import numpy as np
    ds = (opener or _open_dynamical)()
    limit = np.datetime64(newest_before.astimezone(timezone.utc).replace(tzinfo=None), 'ns')
    inits = np.asarray(ds['init_time'].values).astype('datetime64[ns]')
    idx = np.flatnonzero(inits <= limit)
    if len(idx) == 0:
        raise RuntimeError('dynamical.org has no run at or before ' + str(newest_before))
    i = idx[np.argmax(inits[idx])]
    lats = np.asarray(ds['latitude'].values, dtype=float)
    lons = np.asarray(ds['longitude'].values, dtype=float)
    leads = np.asarray(ds['lead_time'].values).astype('timedelta64[ns]')
    lat_keep = np.flatnonzero((lats >= 10.25 - 1e-6) & (lats <= 10.5 + 1e-6))
    lon_keep = np.flatnonzero((lons >= 123.75 - 1e-6) & (lons <= 124.0 + 1e-6))
    box = ds['precipitation_surface'].sel(
        latitude=slice(10.5, 10.25), longitude=slice(123.75, 124.0),
    ).isel(init_time=int(i)).transpose('lead_time', 'latitude', 'longitude')
    vals = np.asarray(box.values, dtype=float)  # (lead, lat, lon) of the small box
    lats, lons = lats[lat_keep], lons[lon_keep]
    want = np.arange(1, hours + 1).astype('timedelta64[h]').astype('timedelta64[ns]')
    lead_idx = [int(np.flatnonzero(leads == w)[0]) if (leads == w).any() else None for w in want]
    if None in lead_idx:
        raise RuntimeError('dynamical.org run is missing forecast hours')
    out = {}
    for lat, lon in GRID:
        y = int(np.argmin(np.abs(lats - lat)))
        x = int(np.argmin(np.abs(lons - lon)))
        series = []
        for h, li in enumerate(lead_idx, start=1):
            v = float(vals[li, y, x]) * 3600.0
            series.append(max(0.0, _check(v, MAX_HOURLY_MM, f'dynamical.org hour {h} at {(lat, lon)}')))
        out[(lat, lon)] = series
    init_dt = datetime.fromtimestamp(
        float(inits[i].astype('datetime64[s]').astype('int64')), tz=timezone.utc)
    return init_dt, out


def _default_exists(url):
    import requests
    try:
        r = requests.get(url, timeout=30, headers={'User-Agent': USER_AGENT})
        # NOMADS can answer 200 with an HTML 'file not present' page
        return r.status_code == 200 and r.content[:4] == b'GRIB'
    except requests.RequestException:
        return False


def latest_cycle(now, exists=None):
    """Newest of the last 4 cycles at or before now - 3 h whose f096 file exists, else None."""
    exists = exists or _default_exists
    limit = now - timedelta(hours=3)
    cycle = limit.replace(hour=limit.hour - limit.hour % 6, minute=0, second=0, microsecond=0)
    for i in range(4):
        c = cycle - timedelta(hours=6 * i)
        if exists(nomads_url(c, 96)):
            return c
    return None
