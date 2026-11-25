"""
Landslide model sources: Esri land cover, UP NOAH landslide classes, OSM roads
and the Copernicus DEM, each downloaded for a grid and cached.

Sources: Esri / Impact Observatory 10 m annual land cover (CC BY 4.0); UP NOAH
landslide hazard maps (ODbL, via the bettergovph mirror); (c) OpenStreetMap
contributors (ODbL); Copernicus GLO-30 DEM.
"""
import hashlib
import io
import json
import math
import os
import shutil
import tempfile
import time
import zipfile
import zlib
from datetime import date
from pathlib import Path

import numpy as np
import requests
from scipy import ndimage

from apps.hazards import susceptibility as sus

from . import downloads

LANDCOVER_URL = ('https://lulctimeseries.blob.core.windows.net/lulctimeseriesv003/'
                 'lc{year}/{tile}_{year}0101-{next_year}0101.tif')
LANDCOVER_FIRST_YEAR = 2017
BAND_LETTERS = 'CDEFGHJKLMNPQRSTUVWX'  # UTM latitude bands, 8 degrees each from 80 S
LATTICE_STEP = 16                      # cells between exactly transformed points

NOAH_URL = ('https://huggingface.co/datasets/bettergovph/project-noah-hazard-maps/resolve/main/'
            'Landslide/LandslideHazards/{province}.zip')
# province -> SHA-256 of its zip (Hugging Face's LFS oid for the file, which is the
# SHA-256 of its bytes; checked by downloading Southern Leyte and hashing it).
NOAH_LANDSLIDE = {
    'Abra': 'c4ad06980595b2c4c48959c0638900f6a9ee01622a6387b8399e40457cca7f1a',
    'IlocosNorte': '9586ab5d6f09a3baa2cbb4a8a779fe489e7c354944df018cd50a59dd77c75e0b',
    'IlocosSur': 'dcee730a67d6f2f5b8df81c785e94fb98c4b86eacbf45ffd10b8775e2c922255',
    'Benguet': 'b16c42aa06d7639afdea76182135e5f7f2a5d758f3ed4f8b005d18084df440db',
    'Maguindanao': 'b92f05bc418b3f4d88951e8fd0c1fbf1693a57da21f15e8bc057625d9174ebac',
    'Cotabato': '8b483f085782ec01eeebdf91220b8eda8c49d3b818f97fd9bcd64a7c08f09842',
    'Leyte': 'b6a2a3225e6048a4bc4e7b5a308cc9a9f6d1c0aec54a448c52f8dfcb69745603',
    'SouthernLeyte': 'e7d364e82e46f04590f2e7203e1f4ba63176348b1a2f7f401b3117988c3c899e',
    'Cebu': '7147cebbb278281c74645a088417f314e3e048c0f1b68a1f8570558691018eb9',
    # R26, pinned the same way from the tree API's lfs oid on 2026-11-25:
    'Apayao': '87276559db2604c84a3c555782b80538774cf67d66cd3ffecaaabf600ca54b0a',
    'Kalinga': '03da06e5c421af62775af9c031c8c136d75e5d8cb64ae4f444d94159475731d0',
    'MountainProvince': 'ebad91a26e998ec04a2ad0b5f9fd79bf3c7b891444585148fb54f000a83bcce6',
    'SultanKudarat': '6a6f83604f1c660d00050e82daf7a1d376af9e0129f36e9751256bc2d18b0647',
}
NOAH_FIELDS = ('HAZ', 'LH')  # the class column: Southern Leyte's file calls it LH (1 low, 2 medium, 3 high)

# What reading a saved file raises when a stopped run left it cut short or broken (final review B2)
UNREADABLE = (EOFError, KeyError, ValueError, zipfile.BadZipFile, zlib.error)


# --- Saved files -------------------------------------------------------------

def save_atomically(path, write) -> Path:
    """
    Save `path` whole or not at all: `write(file)` writes into a temporary file
    (binary) in the same folder, which then takes the real name in one step
    (os.replace). A run stopped part way leaves at most a stray temporary file,
    never a cut-short file under the real name that every rerun would fail on.
    """
    path = Path(path)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f'.{path.name}.', suffix='.part')
    try:
        with os.fdopen(fd, 'wb') as f:
            write(f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return path


def read_saved(path, read, log=print):
    """
    read(the file's bytes), or None when the saved file is missing or cannot be
    read (UNREADABLE: cut short by a stopped run, say). A broken file is named in
    the log and deleted, so the caller builds it again.
    """
    path = Path(path)
    if not path.exists():
        return None
    try:
        return read(path.read_bytes())
    except UNREADABLE as exc:
        log(f'  {path.name} could not be read ({type(exc).__name__}: {exc}); deleting it to build it again')
        path.unlink(missing_ok=True)
        return None


def npz_arrays(data: bytes) -> dict:
    """Every array of a saved .npz, read from its bytes (nothing stays open, so a broken file can be deleted)."""
    with np.load(io.BytesIO(data), allow_pickle=False) as z:
        return {k: z[k] for k in z.files}


# --- Land cover --------------------------------------------------------------

def utm_tile(lon: float, lat: float) -> str:
    """The Esri land cover tile name (UTM zone and latitude band), e.g. '51P'."""
    zone = int((lon + 180) // 6) % 60 + 1
    band = BAND_LETTERS[min(max(int((lat + 80) // 8), 0), len(BAND_LETTERS) - 1)]
    return f'{zone}{band}'


def landcover_year_for(event_date: date) -> int:
    """The year before the event (the map of the ground as it was), at least 2017."""
    return max(event_date.year - 1, LANDCOVER_FIRST_YEAR)


def _tag(grid) -> str:
    return f'z{grid.zoom}_{grid.px0}_{grid.py0}_{grid.width}x{grid.height}'


def _cell_centres(grid):
    """(lons, lats) of every cell centre, as (height, width) arrays."""
    n = sus.TILE * 2 ** grid.zoom
    xs = grid.px0 + np.arange(grid.width) + 0.5
    ys = grid.py0 + np.arange(grid.height) + 0.5
    lons = xs / n * 360.0 - 180.0
    lats = np.degrees(np.arctan(np.sinh(np.pi * (1 - 2 * ys / n))))
    return np.broadcast_to(lons[None, :], grid.shape), np.broadcast_to(lats[:, None], grid.shape)


def _utm_xy(lons, lats, tile: str):
    """UTM (easting, northing) of cell centres in the tile's zone: exact on a lattice, bilinear between."""
    from django.contrib.gis.gdal import CoordTransform, OGRGeometry, SpatialReference

    zone = int(tile[:-1])
    north = BAND_LETTERS.index(tile[-1]) >= BAND_LETTERS.index('N')
    transform = CoordTransform(SpatialReference(4326), SpatialReference((32600 if north else 32700) + zone))
    h, w = lons.shape
    rows = np.unique(np.append(np.arange(0, h, LATTICE_STEP), h - 1))
    cols = np.unique(np.append(np.arange(0, w, LATTICE_STEP), w - 1))
    ex = np.zeros((len(rows), len(cols)))
    ny = np.zeros_like(ex)
    for i, r in enumerate(rows):
        for j, c in enumerate(cols):
            pt = OGRGeometry(f'POINT ({float(lons[r, c])!r} {float(lats[r, c])!r})', srs=4326)
            pt.transform(transform)
            ex[i, j], ny[i, j] = pt.x, pt.y
    ri = np.interp(np.arange(h), rows, np.arange(len(rows)))
    ci = np.interp(np.arange(w), cols, np.arange(len(cols)))
    rr, cc = np.meshgrid(ri, ci, indexing='ij')
    return (ndimage.map_coordinates(ex, [rr, cc], order=1), ndimage.map_coordinates(ny, [rr, cc], order=1))


LANDCOVER_TRIES = 4    # reads of one blob before its cells go without land cover (ruling R54)
LANDCOVER_WAIT_S = 15  # seconds before the second read, doubling after each failure


def _clear_gdal_cache():
    """
    Forget what GDAL's /vsicurl/ has cached. After one failed lookup (a network
    blip) GDAL says the blob "does not exist" for the rest of the process, so
    every later tile of a build would lose its land cover.
    """
    try:
        from django.contrib.gis.gdal.libgdal import lgdal

        clear = lgdal.VSICurlClearCache
        clear.restype, clear.argtypes = None, []
        clear()
    except Exception:  # no GDAL, or one without the call: nothing cached to clear
        pass


def _blob_exists(url):
    """True when the blob answers 200, False on 404 (a year or tile not published), None when it cannot be asked."""
    try:
        r = requests.head(url, timeout=30)
    except requests.RequestException:
        return None
    return {200: True, 404: False}.get(r.status_code)


def _gdal_fetch(url, xs, ys, log=print, wait=None):
    """
    _gdal_read, tried again after a failure (ruling R54): GDAL's cache is cleared
    and the read retried after 15, 30 and 60 s, unless the server says the blob
    is not there (that ends at once, so probing for the newest year stays fast).
    The last failure is raised.
    """
    wait = wait or time.sleep
    for attempt in range(1, LANDCOVER_TRIES + 1):
        try:
            return _gdal_read(url, xs, ys)
        except Exception as exc:
            if attempt == LANDCOVER_TRIES or _blob_exists(url) is False:
                raise
            delay = LANDCOVER_WAIT_S * 2 ** (attempt - 1)
            log(f'  Land cover read failed ({type(exc).__name__}: {exc}); trying again in {delay} s')
            _clear_gdal_cache()
            wait(delay)


def _gdal_read(url, xs, ys):
    """Class at each UTM (x, y) of one tile, by range-reading the blob through GDAL's /vsicurl/."""
    from django.contrib.gis.gdal import GDALRaster

    raster = GDALRaster('/vsicurl/' + url)
    ox, oy = raster.origin
    dx, dy = raster.scale
    cols = np.floor((xs - ox) / dx).astype(int)
    rows = np.floor((ys - oy) / dy).astype(int)
    inside = (cols >= 0) & (cols < raster.width) & (rows >= 0) & (rows < raster.height)
    out = np.zeros(len(xs), np.uint8)
    if not inside.any():
        return out
    c0, c1 = cols[inside].min(), cols[inside].max() + 1
    r0, r1 = rows[inside].min(), rows[inside].max() + 1
    window = np.asarray(raster.bands[0].data(offset=(int(c0), int(r0)), size=(int(c1 - c0), int(r1 - r0))))
    window = window.reshape(int(r1 - r0), int(c1 - c0))
    out[inside] = window[rows[inside] - r0, cols[inside] - c0]
    return out


def landcover_classes(grid, year: int, cache_dir, log=print, fetch=None):
    """
    The Esri land cover class (1-11, 0 = no data) at each grid cell centre, nearest
    neighbour, or None when the blob cannot be range-read (the model then drops
    land cover). `fetch(url, xs, ys)` -> uint8 classes at UTM coordinates; the
    default range-reads the tile through GDAL, trying again after a failure (R54).
    """
    cache = Path(cache_dir)
    cache.mkdir(parents=True, exist_ok=True)
    saved = cache / f'lulc_{year}_{_tag(grid)}.npz'
    classes = read_saved(saved, lambda data: npz_arrays(data)['classes'], log)
    if classes is not None:
        log('  Using saved land cover')
        return classes
    fetch = fetch or (lambda url, xs, ys: _gdal_fetch(url, xs, ys, log=log))
    lons, lats = _cell_centres(grid)
    zones = (np.floor((lons + 180) // 6).astype(int) % 60 + 1)
    bands = np.clip(((lats + 80) // 8).astype(int), 0, len(BAND_LETTERS) - 1)
    tile_ids = zones * 100 + bands
    out = np.zeros(grid.shape, np.uint8)
    try:
        for tid in np.unique(tile_ids):
            sel = tile_ids == tid
            tile = f'{tid // 100}{BAND_LETTERS[tid % 100]}'
            url = LANDCOVER_URL.format(year=year, next_year=year + 1, tile=tile)
            ex, ny = _utm_xy(lons, lats, tile)
            values = fetch(url, ex[sel], ny[sel])
            if values is None:
                raise RuntimeError(f'{url} could not be read')
            out[sel] = values
            log(f'  Land cover {year}: tile {tile}, {int(sel.sum())} cells')
    except Exception as exc:  # unreachable blob, 404, no GDAL: the model drops land cover
        log(f'  Land cover unavailable ({type(exc).__name__}: {exc}); the model will not use it')
        return None
    save_atomically(saved, lambda f: np.savez_compressed(f, classes=out))
    return out


# --- NOAH landslide classes --------------------------------------------------

def fetch_noah_landslide(province: str, cache_dir, log=print) -> Path:
    """The province's NOAH landslide zip, downloaded when missing and checked against its pinned SHA-256."""
    if province not in NOAH_LANDSLIDE:
        raise ValueError(f'No NOAH landslide map is listed for {province}')
    dest = Path(cache_dir) / f'noah_landslide_{province}.zip'
    url = NOAH_URL.format(province=province)
    return downloads.fetch_verified(url, NOAH_LANDSLIDE[province], dest)


def noah_landslide_polygons(path: Path, bbox_ll, log=print) -> dict:
    """
    {HAZ class: [polygon (list of rings)]} of one NOAH zip, clipped to bbox_ll = (west, south, east, north);
    the shapes GEOS cannot use are skipped and counted in the log.
    """
    from django.contrib.gis.gdal import CoordTransform, DataSource, SpatialReference
    from django.contrib.gis.geos import GEOSGeometry, Polygon

    path = Path(path)
    folder = path.parent / path.stem
    with zipfile.ZipFile(path) as z:
        root = folder.resolve()
        for member in z.namelist():
            if not (root / member).resolve().is_relative_to(root):
                raise RuntimeError(f'{path} has an unsafe member name: {member}')
        if not (folder / '.complete').exists():  # extract whole, then mark: an interrupted run is redone
            shutil.rmtree(folder, ignore_errors=True)
            z.extractall(folder)
            (folder / '.complete').write_text('ok')
    shapes = sorted(folder.rglob('*.shp'))
    if not shapes:
        raise RuntimeError(f'{path} holds no shapefile')
    box = Polygon.from_bbox(bbox_ll)
    box.srid = 4326
    wgs84 = SpatialReference(4326)
    out = {}
    skipped = 0
    for shape in shapes:
        layer = DataSource(str(shape))[0]
        srs = layer.srs
        field = next((f for f in NOAH_FIELDS if f in layer.fields), None)
        if field is None:
            raise RuntimeError(f'{shape} has none of the class fields {NOAH_FIELDS}; it has {layer.fields}')
        convert = CoordTransform(srs, wgs84) if srs is not None and srs.srid not in (None, 4326) else None
        for feature in layer:
            cls = int(feature.get(field))
            if cls not in (1, 2, 3):
                continue
            geom = feature.geom
            if convert is not None:
                geom = geom.clone()
                geom.transform(convert)
            try:
                poly = GEOSGeometry(geom.wkb, srid=4326)
                try:
                    clipped = poly.intersection(box)
                except Exception:  # an invalid (self-touching) shape: repair it and clip again
                    poly = poly.make_valid() if hasattr(poly, 'make_valid') else poly.buffer(0)
                    clipped = poly.intersection(box)
            except Exception:  # a geometry GEOS cannot repair: skip it, and say how many
                skipped += 1
                continue
            polys = [clipped] if clipped.geom_type == 'Polygon' else [g for g in clipped if g.geom_type == 'Polygon']
            out.setdefault(cls, []).extend([list(ring.coords) for ring in p] for p in polys if not p.empty)
    if skipped:
        log(f'  NOAH {path.stem}: skipped {skipped} unusable shapes')
    return out


def noah_landslide_grid_from(polygons_by_class: dict, grid) -> np.ndarray:
    """uint8 grid of the highest NOAH class at each cell (0 outside every polygon)."""
    out = np.zeros(grid.shape, np.uint8)
    for cls in sorted(polygons_by_class):  # ascending, so a higher class paints over a lower one
        painted = sus.draw_polygons(grid, [(1, rings) for rings in polygons_by_class[cls]]) > 0
        out[painted] = np.uint8(cls)
    return out


def noah_landslide_grid(grid, provinces: tuple, cache_dir, log=print) -> np.ndarray:
    """The highest NOAH landslide class (HAZ 1-3) at each cell over the given provinces' maps, 0 outside."""
    (south, west), (north, east) = grid.bounds()
    merged = {}
    for province in provinces:
        path = fetch_noah_landslide(province, cache_dir, log)
        for cls, polys in noah_landslide_polygons(path, (west, south, east, north), log).items():
            merged.setdefault(cls, []).extend(polys)
    return noah_landslide_grid_from(merged, grid)


# --- Roads -------------------------------------------------------------------

def roads(bbox: tuple, cache_dir, log=print) -> list:
    """OSM `highway` lines (lists of (lon, lat)) of the ROAD_TYPES set inside bbox = (south, west, north, east)."""
    cache = Path(cache_dir)
    cache.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(','.join(f'{v:.5f}' for v in bbox).encode()).hexdigest()[:16]
    saved = cache / f'osm_roads_{digest}.json'
    kept = read_saved(saved, lambda data: json.loads(data.decode('utf-8')), log)
    if kept is not None:
        log('  Using saved roads')
        return [[tuple(p) for p in line] for line in kept]
    types = '|'.join(sorted(sus.ROAD_TYPES))
    log('  Downloading roads from OpenStreetMap...')
    elements = overpass_elements(
        f'[out:json][timeout:240];way["highway"~"^({types})$"]({sus._bbox(*bbox)});out geom;',
        sus.make_session(), log)
    lines = []
    for el in elements:
        if el.get('type') != 'way' or el.get('tags', {}).get('highway') not in sus.ROAD_TYPES:
            continue
        line = sus._line(el.get('geometry'))
        if len(line) >= 2:
            lines.append(line)
    save_atomically(saved, lambda f: f.write(json.dumps(lines).encode('utf-8')))  # ASCII, as write_text gave it
    return lines


def overpass_elements(query: str, session, log=print) -> list:
    """
    The query's elements, trying each Overpass server twice as susceptibility.overpass
    does. Only a 200 whose JSON object holds an "elements" list and no error remark is
    an answer, so an empty list always means the server found nothing. Anything else
    counts as failed and is retried: a body that is not that object (a proxy's error
    page or object), or a "remark" reporting an error (a timeout, out of memory), whose
    elements may be partial. If no server answers cleanly this raises, so nothing
    partial is ever cached.
    """
    last_error = None
    for url in sus.OVERPASS_URLS:
        for _ in range(2):
            try:
                r = session.post(url, data={'data': query}, timeout=300)
                if r.status_code == 200:
                    answer = r.json()
                    if not isinstance(answer, dict) or not isinstance(answer.get('elements'), list):
                        last_error = f'{url} answered without an elements list'
                    else:
                        remark = str(answer.get('remark') or '')
                        if not any(word in remark.lower() for word in ('error', 'timed out')):
                            return answer['elements']
                        last_error = f'{url} answered with the remark "{remark}"'
                else:
                    last_error = f'{url} answered {r.status_code}'
            except (requests.RequestException, ValueError) as exc:
                last_error = f'{url}: {exc}'
            log(f'  Overpass busy ({last_error}), retrying...')
            time.sleep(10)
    raise RuntimeError(f'OpenStreetMap download failed: {last_error}')


def road_density_km_per_km2(grid, roads: list, mask: np.ndarray) -> float:
    """Kilometres of road per square kilometre over the cells where mask is True."""
    mask = np.asarray(mask, bool)
    area_km2 = mask.sum() * grid.res ** 2 / 1e6
    if area_km2 <= 0 or not roads:
        return 0.0
    step = 0.5  # cells between samples along a line
    length_m = 0.0
    for line in roads:
        pts = np.array([grid.to_cell(lng, lat) for lng, lat in line])
        for a, b in zip(pts[:-1], pts[1:]):
            n = max(int(math.ceil(np.hypot(*(b - a)) / step)), 1)
            t = (np.arange(n) + 0.5) / n
            xy = a[None, :] + t[:, None] * (b - a)[None, :]
            cols = np.floor(xy[:, 0]).astype(int)
            rows = np.floor(xy[:, 1]).astype(int)
            ok = (cols >= 0) & (cols < grid.width) & (rows >= 0) & (rows < grid.height)
            hits = mask[rows[ok], cols[ok]].sum()
            length_m += hits * (np.hypot(*(b - a)) / n) * grid.res
    return float(length_m / 1000 / area_km2)


# --- DEM ---------------------------------------------------------------------

def dem_for(grid, cache_dir, log=print) -> np.ndarray:
    """Copernicus GLO-30 heights on the grid, cached as dem_cop30_{tag}.npy; missing heights become 0; never caches a flat result."""
    cache = Path(cache_dir)
    cache.mkdir(parents=True, exist_ok=True)
    dem_file = cache / f'dem_cop30_{_tag(grid)}.npy'
    dem = read_saved(dem_file, lambda data: np.load(io.BytesIO(data)), log)
    if dem is not None:
        log('  Using saved elevation data')  # load_inputs writes this name too, unscrubbed
        return np.where(np.isfinite(dem), dem, 0).astype(dem.dtype)
    log('  Downloading Copernicus GLO-30 elevation...')
    dem = sus.fetch_copernicus(grid, sus.http_range_fetcher(sus.make_session()), log)
    dem = np.where(np.isfinite(dem), dem, 0).astype(dem.dtype)  # a missing height is sea level
    if not (dem > 0).any():
        raise RuntimeError(sus.NO_HEIGHT)
    save_atomically(dem_file, lambda f: np.save(f, dem))
    return dem
