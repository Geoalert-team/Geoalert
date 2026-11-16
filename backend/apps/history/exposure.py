"""Fixed flood exposure per barangay: buildings in UP NOAH Medium/High flood hazard and on low ground."""
import csv
import gzip
import io
import json
from pathlib import Path

import numpy as np

from apps.barangays.purok_estimate import BUILDINGS_INDEX, BUILDINGS_TILE, building_centres
from apps.history.hazard_data import DATA_DIR

NOAH_URLS = {
    25: 'https://huggingface.co/datasets/bettergovph/project-noah-hazard-maps/resolve/main/Flood/25yr/Cebu.zip',
    100: 'https://huggingface.co/datasets/bettergovph/project-noah-hazard-maps/resolve/main/Flood/100yr/Cebu.zip',
}
NOAH_LAYERS = {25: 'Cebu/PH072200000_FH_25yr.shp', 100: 'Cebu/PH072200000_FH_100yr.shp'}
EXPOSURE_FILE = DATA_DIR / 'barangay_exposure.csv'
EXPOSURE_COLUMNS = ('buildings', 'noah25_mh', 'noah100_mh', 'hand_lt2_buildings', 'exposure')
MEDIUM = 2      # NOAH Var: 1 Low, 2 Medium, 3 High
HAND_LIMIT_M = 2.0


def _default_get(url, **kw):
    from apps.hazards import susceptibility
    return susceptibility.make_session().get(url, **kw)


def download_noah(cache_dir: Path, period: int, refresh: bool, log, get=None) -> Path:
    """The NOAH flood hazard zip for one return period, saved in cache_dir after the first download."""
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    saved = cache_dir / f'noah_cebu_{period}yr.zip'
    if saved.exists() and not refresh:
        log(f'  Using saved NOAH {period}-year flood map')
        return saved
    log(f'  Downloading NOAH {period}-year flood map...')
    resp = (get or _default_get)(NOAH_URLS[period], timeout=600)
    resp.raise_for_status()
    tmp = saved.with_suffix('.part')
    tmp.write_bytes(resp.content)
    tmp.replace(saved)
    return saved


def noah_polygons(path: str, bbox) -> list[tuple[int, list]]:
    """(Var, [outer_ring, hole, ...]) per polygon, clipped to bbox = (south, west, north, east), lng/lat."""
    from django.contrib.gis.gdal import DataSource, OGRGeometry
    south, west, north, east = bbox
    box = OGRGeometry.from_bbox((west, south, east, north))
    out = []
    layer = DataSource(path)[0]
    layer.spatial_filter = (west, south, east, north)
    for feature in layer:
        var = int(feature.get('Var'))
        geom = feature.geom
        clipped = geom.intersection(box)
        if clipped.empty:
            continue
        parts = clipped if clipped.geom_type in ('MultiPolygon', 'GeometryCollection') else [clipped]
        for part in parts:
            if part.geom_type == 'Polygon':
                out.append((var, [[(p[0], p[1]) for p in ring.tuple] for ring in part]))
    return out


def noah_class_grid(grid, polygons) -> np.ndarray:
    """Highest NOAH class per cell (0 where none); a hole removes only its own class."""
    from apps.hazards import susceptibility
    out = np.zeros(grid.shape, np.int32)
    for v in (1, 2, 3):
        mask = susceptibility.draw_polygons(grid, [(1, rings) for var, rings in polygons if var == v]) > 0
        out = np.maximum(out, v * mask.astype(np.int32))
    return out


def city_buildings(cache_dir: Path, bbox, refresh: bool, log, get=None) -> list[tuple[float, float]]:
    """Building centres inside bbox; its own cache file, apart from the purok build's."""
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    saved = cache_dir / f'ms_buildings_city_{BUILDINGS_TILE}.json'
    if saved.exists() and not refresh:
        log('  Using saved city building footprints')
        return [tuple(p) for p in json.loads(saved.read_text())]
    get = get or _default_get
    log('  Downloading Microsoft building footprints (about 31 MB)...')
    index = get(BUILDINGS_INDEX, timeout=120)
    index.raise_for_status()
    url = next((r['Url'] for r in csv.DictReader(io.StringIO(index.text))
                if r['Location'] == 'Philippines' and r['QuadKey'] == BUILDINGS_TILE), None)
    if url is None:
        raise RuntimeError(f'Building footprint tile {BUILDINGS_TILE} is not in the Microsoft index')
    resp = get(url, timeout=600)
    resp.raise_for_status()
    with gzip.open(io.BytesIO(resp.content), 'rt', encoding='utf-8') as fh:
        centres = building_centres(fh, bbox)
    saved.write_text(json.dumps(centres))
    return centres


def exposure_rows(labels, counts, noah25, noah100, hand, barangay_ids) -> dict[int, dict[str, float]]:
    """Buildings per barangay in NOAH Medium/High (25 and 100 year) and on ground under 2 m above drainage."""
    low = np.nan_to_num(np.asarray(hand, float), nan=np.inf) < HAND_LIMIT_M
    layers = {
        'buildings': np.ones(np.shape(counts), bool),
        'noah25_mh': np.asarray(noah25) >= MEDIUM,
        'noah100_mh': np.asarray(noah100) >= MEDIUM,
        'hand_lt2_buildings': low,
    }
    rows = {}
    for bid in barangay_ids:
        inside = np.asarray(labels) == bid
        r = {k: float(np.asarray(counts, float)[inside & m].sum()) for k, m in layers.items()}
        r['exposure'] = (r['noah25_mh'] + r['noah100_mh'] + r['hand_lt2_buildings']) / 3
        rows[bid] = r
    return rows


def write_exposure(path, rows, names):
    with open(path, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['barangay_id', 'barangay', *EXPOSURE_COLUMNS])
        for bid in sorted(rows):
            w.writerow([bid, names.get(bid, ''), *(repr(float(rows[bid][k])) for k in EXPOSURE_COLUMNS)])


def read_exposure(path=EXPOSURE_FILE) -> dict[int, dict[str, float]]:
    with open(path, newline='', encoding='utf-8') as f:
        return {int(row['barangay_id']): {k: float(row[k]) for k in EXPOSURE_COLUMNS}
                for row in csv.DictReader(f)}
