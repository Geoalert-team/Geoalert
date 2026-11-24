"""
Downloads for the fire risk model's features (fire_features.py), each saved
in the cache folder after the first run so a rerun reads them from disk.

  Microsoft Global ML Building Footprints   ODbL       footprints()
  ESA WorldCover 2021 v200, 10 m            CC BY 4.0  worldcover()
  WorldPop constrained population, 100 m    CC BY 4.0  worldpop()  (None when no free download works)
  OpenStreetMap roads, stations, water      ODbL       osm()  (saved by build_purok_estimates)

All are free and need no account. Part of the fire model adapted from the City
of Pittsburgh Bureau of Fire / Carnegie Mellon Metro21 fire risk model
(github.com/CityofPittsburgh/fire_risk_analysis, MIT License, © 2017 mmadaio).
No fire record is read here.
"""
import csv
import gzip
import io
import json
import math
from pathlib import Path

import numpy as np
import requests

from apps.barangays.purok_estimate import BUILDINGS_INDEX, BUILDINGS_TILE
from apps.hazards import susceptibility as sus
from apps.history import fire_features as ff

FOOTPRINTS_FILE = f'ms_footprints_{BUILDINGS_TILE}.json'
WORLDCOVER_URL = ('https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/'
                  'ESA_WorldCover_10m_2021_v200_{tile}_Map.tif')
WORLDCOVER_FILE = 'worldcover_2021_v200_window.npz'
# Newest first. Each is a direct download with no sign-in (checked 2026-11-23).
WORLDPOP_URLS = (
    ('WorldPop 2025 constrained 100 m (Global2 R2025A v1)',
     'https://data.worldpop.org/GIS/Population/Global_2015_2030/R2025A/2025/PHL/v1/100m/constrained/'
     'phl_pop_2025_CN_100m_R2025A_v1.tif'),
    ('WorldPop 2020 constrained 100 m (BSGM)',
     'https://data.worldpop.org/GIS/Population/Global_2000_2020_Constrained/2020/BSGM/PHL/'
     'phl_ppp_2020_constrained.tif'),
)
WORLDPOP_FILE = 'worldpop_window.npz'
HEADER_BYTES = 1 << 16


def _covers(saved_bbox, bbox):
    """Whether a saved (south, west, north, east) holds the one asked for."""
    s, w, n, e = saved_bbox
    south, west, north, east = bbox
    return s <= south and w <= west and n >= north and e >= east


def footprints(cache_dir, bbox, refresh=False, log=print):
    """
    Building centres (lng, lat) and footprint areas (m²) in bbox = (south, west,
    north, east), from Microsoft's footprints for tile BUILDINGS_TILE. The
    centre is the mean of the outline's corners, as building_centres takes it.
    """
    path = Path(cache_dir) / FOOTPRINTS_FILE
    if path.exists() and not refresh:
        saved = json.loads(path.read_text())
        if _covers(saved['bbox'], bbox):
            log('  Using saved building footprints')
            return np.asarray(saved['centres'], float).reshape(-1, 2), np.asarray(saved['area_m2'], float)
    session = sus.make_session()
    log('  Downloading Microsoft building footprints (about 31 MB)...')
    index = session.get(BUILDINGS_INDEX, timeout=120)
    index.raise_for_status()
    url = next(r['Url'] for r in csv.DictReader(io.StringIO(index.text))
               if r['Location'] == 'Philippines' and r['QuadKey'] == BUILDINGS_TILE)
    resp = session.get(url, timeout=600)
    resp.raise_for_status()
    with gzip.open(io.BytesIO(resp.content), 'rt', encoding='utf-8') as fh:
        centres, areas = outlines_in(fh, bbox)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({'bbox': list(bbox), 'centres': centres, 'area_m2': areas}))
    return np.asarray(centres, float).reshape(-1, 2), np.asarray(areas, float)


def outlines_in(lines, bbox):
    """([centre (lng, lat)], [area m²]) of the footprint features (one GeoJSON feature per line) centred in bbox."""
    south, west, north, east = bbox
    centres, areas = [], []
    for line in lines:
        ring = json.loads(line)['geometry']['coordinates'][0]
        pts = ring[:-1] if ring[0] == ring[-1] else ring
        x = sum(p[0] for p in pts) / len(pts)
        y = sum(p[1] for p in pts) / len(pts)
        if west <= x <= east and south <= y <= north:
            closed = list(pts) + [pts[0]]
            centres.append([x, y])
            areas.append(round(ff.ring_area_m2(ff.to_metres(closed)), 2))
    return centres, areas


def read_window(fetch, url, bbox):
    """
    (values, (west, north, dx, dy)) of a tiled, north-up Cloud-Optimized
    GeoTIFF over bbox = (south, west, north, east), reading only its header
    and the tiles that cover the box.
    """
    opened = sus._open_cog(fetch, url, HEADER_BYTES)
    if opened is None:
        raise RuntimeError(f'{url} was not found')
    tf, page, (lng_tie, lat_tie, dx, dy, _) = opened
    try:
        return _tiles(page, (lng_tie, lat_tie, dx, dy), fetch, url, bbox)
    finally:
        tf.close()


def read_local_window(path, bbox):
    """read_window for a saved GeoTIFF, whose index may sit anywhere in the file (WorldPop's is at the end)."""
    import tifffile

    with tifffile.TiffFile(path) as tf:
        page = tf.pages[0]
        dx, dy = page.tags['ModelPixelScaleTag'].value[:2]
        tie = page.tags['ModelTiepointTag'].value
        return _tiles(page, (tie[3], tie[4], dx, dy), _file_fetcher(path), str(path), bbox)


def _tiles(page, transform, fetch, url, bbox):
    lng_tie, lat_tie, dx, dy = transform
    south, west, north, east = bbox
    transform = (lng_tie, lat_tie, dx, dy)
    rows, cols = ff.raster_window(transform, (page.imagelength, page.imagewidth), (west, south, east, north), pad=2)
    if rows.start >= rows.stop or cols.start >= cols.stop:
        raise RuntimeError(f'{url} does not cover {bbox}')
    th, tw = page.tilelength, page.tilewidth
    across = -(-page.imagewidth // tw)
    out = np.zeros((rows.stop - rows.start, cols.stop - cols.start), page.dtype)
    for tr in range(rows.start // th, (rows.stop - 1) // th + 1):
        for tc in range(cols.start // tw, (cols.stop - 1) // tw + 1):
            i = tr * across + tc
            raw = fetch(url, page.dataoffsets[i], page.databytecounts[i])
            if raw is None:
                raise RuntimeError(f'{url}: block {i} is missing')
            data, _, shape = page.decode(raw, i)
            block = np.asarray(data).reshape(shape[-3], shape[-2])
            br, bc = tr * th, tc * tw
            ra, rb = max(rows.start, br), min(rows.stop, br + th)
            ca, cb = max(cols.start, bc), min(cols.stop, bc + tw)
            out[ra - rows.start:rb - rows.start, ca - cols.start:cb - cols.start] = \
                block[ra - br:rb - br, ca - bc:cb - bc]
    return out, (lng_tie + cols.start * dx, lat_tie - rows.start * dy, dx, dy)


def _save_window(path, values, transform, bbox, label):
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(path, values=values, transform=np.asarray(transform, float),
                        bbox=np.asarray(bbox, float), label=np.asarray(label))


def _saved_window(path, bbox):
    """(values, transform, label) saved by _save_window when it covers bbox, else None."""
    if not path.exists():
        return None
    saved = np.load(path)
    if not _covers(saved['bbox'], bbox):
        return None
    return saved['values'], tuple(float(x) for x in saved['transform']), str(saved['label'])


def worldcover_tile(lat, lng):
    """The 3° WorldCover tile name holding (lat, lng), e.g. N09E123."""
    lat0, lng0 = 3 * math.floor(lat / 3), 3 * math.floor(lng / 3)
    return f'{"N" if lat0 >= 0 else "S"}{abs(lat0):02d}{"E" if lng0 >= 0 else "W"}{abs(lng0):03d}'


def worldcover(cache_dir, bbox, refresh=False, log=print):
    """ESA WorldCover 2021 classes over bbox and their (west, north, dx, dy); only the tiles needed are read."""
    path = Path(cache_dir) / WORLDCOVER_FILE
    saved = None if refresh else _saved_window(path, bbox)
    if saved:
        log('  Using saved WorldCover land cover')
        return saved[0], saved[1]
    south, west, north, east = bbox
    tile = worldcover_tile(south, west)
    if tile != worldcover_tile(north, east):
        raise RuntimeError('The area spans more than one WorldCover tile; only one is read.')
    url = WORLDCOVER_URL.format(tile=tile)
    log(f'  Downloading ESA WorldCover 2021 ({tile}, only the blocks over the city)...')
    values, transform = read_window(sus.http_range_fetcher(sus.make_session()), url, bbox)
    _save_window(path, values, transform, bbox, url)
    return values, transform


def _file_fetcher(path):
    def fetch(_url, start, length):
        with open(path, 'rb') as fh:
            fh.seek(start)
            return fh.read(length)
    return fetch


def worldpop(cache_dir, bbox, refresh=False, log=print):
    """
    WorldPop people per 100 m pixel over bbox and its transform, from the
    newest release that downloads without an account, or None (logged) when
    none does. Its server sends whole files, so the country file is saved once.
    """
    cache = Path(cache_dir)
    path = cache / WORLDPOP_FILE
    saved = None if refresh else _saved_window(path, bbox)
    if saved:
        log(f'  Using saved {saved[2]}')
        return saved[0], saved[1]
    session = sus.make_session()
    for label, url in WORLDPOP_URLS:
        local = cache / 'worldpop' / url.rsplit('/', 1)[1]
        try:
            if refresh or not local.exists():
                log(f'  Downloading {label} for the Philippines...')
                local.parent.mkdir(parents=True, exist_ok=True)
                with session.get(url, stream=True, timeout=600) as resp:
                    resp.raise_for_status()
                    part = local.with_suffix('.part')
                    with open(part, 'wb') as fh:
                        for chunk in resp.iter_content(1 << 20):
                            fh.write(chunk)
                    part.replace(local)
            values, transform = read_local_window(local, bbox)
        except (requests.RequestException, RuntimeError, OSError, ValueError, KeyError, IndexError) as exc:
            log(f'  {label}: not available ({exc})')
            continue
        values = np.where(values > 0, values, 0).astype(np.float32)  # -99999 is no data
        _save_window(path, values, transform, bbox, label)
        return values, transform
    log('  No WorldPop download works without an account; population is left out.')
    return None


def worldpop_label(cache_dir):
    """Which WorldPop release the saved window came from, or None."""
    path = Path(cache_dir) / WORLDPOP_FILE
    return str(np.load(path)['label']) if path.exists() else None


def osm(cache_dir):
    """The OpenStreetMap roads, main roads, fire stations, coastline and waterways build_purok_estimates saved."""
    found = sorted(Path(cache_dir).glob('osm_z14_*.json'))
    if not found:
        raise RuntimeError(f'No saved OpenStreetMap data in {cache_dir}; run build_purok_estimates first.')
    return json.loads(found[-1].read_text())
