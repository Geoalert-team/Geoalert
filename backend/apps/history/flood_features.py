"""
Static ground inputs for the flood susceptibility model (spec 3.2), measured
at every building in Talisay and kept per purok area. Run by
`manage.py build_flood_features` on a developer machine.

Inputs (FEATURE_COLUMNS, the only columns a model may read):
  noah25_class        UP NOAH 25-year flood depth class at the building:
                      0 none, 1 low (< 0.5 m), 2 medium (0.5-1.5 m), 3 high
  noah5_class         the same for the 5-year map, used only when that map
                      passes the consistency check (meta 'noah_layers_used')
  rel_height_river_m  height above the nearest point of a mapped river
  dist_river_m        metres to that river (the model reads log(1 + m))
  depression_m        how deep the ground sits in a sink that holds water
  built_share         ESA WorldCover built-up share within 100 m

`noah25_within_300m` is not an input: it only decides where the NOAH-based
fallback classes can be given (spec 5.3).

This module reads static maps and the purok table only. It never reads a
flood report, a survey point or any history, so no observation of a flood
can become an input.

Sources: UP NOAH flood hazard maps (ODbL, via the bettergovph mirror);
Copernicus GLO-30 DEM; OpenStreetMap rivers (ODbL); ESA WorldCover 2021
(CC BY 4.0); Microsoft building footprints (ODbL).
"""
import csv
import json
import math
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage, signal

from apps.history.downloads import fetch_verified
from apps.history.fire_features import KX, KY, points_inside, to_metres  # noqa: F401  (KX/KY used by tests)

DATA_DIR = Path(__file__).parent / 'data'
FEATURES_FILE = DATA_DIR / 'flood_purok_features.csv'
FEATURES_META = DATA_DIR / 'flood_purok_features.meta.json'
BUILDINGS_FILE = 'flood_building_features.npz'  # in the cache folder: too big to keep with the code
GRIDS_FILE = 'flood_feature_grids.npz'          # the input grids, so inputs can be read anywhere (cache folder)
MODEL_FILE = DATA_DIR / 'flood_purok_model.json'    # written by train_flood_model, read by flood_purok.py
REPORT_FILE = DATA_DIR / 'flood_purok_report.json'  # what the accuracy card shows

FEATURE_COLUMNS = ('noah25_class', 'noah5_class', 'rel_height_river_m', 'dist_river_m', 'depression_m',
                   'built_share')
AUX_COLUMNS = ('noah25_within_300m',)
AREA_COLUMNS = ('purok_id', 'barangay_id', 'barangay', 'name', 'confidence', 'buildings')

NOAH_BASE = 'https://huggingface.co/datasets/bettergovph/project-noah-hazard-maps/resolve/main/Flood/{p}yr/Cebu.zip'
NOAH = {
    5: ('d41f470285a91cddcd56af867012f492632805fc6000617ebc3640a65d275fac', 'noah_cebu_5yr.zip'),
    25: ('bb630ac3bd360ad0686d7945ea7c389986e3d97f7d76cf5109645e46941c1ffe', 'noah_cebu_25yr.zip'),
    100: ('52c7b3e0a6db23439499d1f5ce281774e60e1dbb5fc845ea7ace374f7b66f9af', 'noah_cebu_100yr.zip'),
}
NOAH_SHAPE = 'Cebu/PH072200000_FH_{p}yr.shp'
NOAH_SLACK = 0.02       # 2% of the flooded city area (spec 3.3)
NOAH_NEAR_M = 300       # fallback coverage: within 300 m of a NOAH 25-year polygon (spec 5.3)
BUILT_UP = 50           # ESA WorldCover class
BUILT_RADIUS_M = 100


# --- NOAH -----------------------------------------------------------------

def noah_class_grid(grid, polygons_by_class: dict) -> np.ndarray:
    """
    The highest NOAH class over each grid cell. Each class is drawn on its own
    (holes cut only that class), so a hole in one class never erases another.
    polygons_by_class: {class: [polygon, ...]}, a polygon a list of (lng, lat) rings, outline first.
    """
    out = np.zeros(grid.shape, np.uint8)
    for cls in sorted(polygons_by_class):
        img = Image.new('1', (grid.width, grid.height), 0)
        draw = ImageDraw.Draw(img)
        for poly in polygons_by_class[cls]:
            outer = [grid.to_cell(lng, lat) for lng, lat in poly[0]]
            if len(outer) >= 3:
                draw.polygon(outer, fill=1)
            for hole in poly[1:]:
                pts = [grid.to_cell(lng, lat) for lng, lat in hole]
                if len(pts) >= 3:
                    draw.polygon(pts, fill=0)
        mask = np.array(img, dtype=bool)
        out[mask] = np.maximum(out[mask], cls)
    return out


def noah_consistent(areas: dict, slack: float = NOAH_SLACK) -> dict:
    """
    Which NOAH layers agree with the 25-year one: rarer rain floods at least as
    much ground, so the 5-year area may not exceed the 25-year by more than
    `slack`, nor the 100-year fall short of it by more. areas: {years: flooded m²}.
    """
    a25 = areas[25]
    out = {}
    for years, area in areas.items():
        if years == 25:
            out[years] = True
        elif years < 25:
            out[years] = area <= a25 * (1 + slack)
        else:
            out[years] = area >= a25 * (1 - slack)
    return out


def noah_polygons(path: Path, years: int, bbox_ll) -> dict:
    """{class: [polygon rings]} of one NOAH zip, clipped to bbox_ll = (west, south, east, north)."""
    from django.contrib.gis.gdal import DataSource
    from django.contrib.gis.geos import GEOSGeometry, Polygon

    folder = path.parent / path.stem
    shape = folder / NOAH_SHAPE.format(p=years)
    if not shape.exists():
        with zipfile.ZipFile(path) as z:
            root = folder.resolve()
            for member in z.namelist():
                if not (root / member).resolve().is_relative_to(root):
                    raise RuntimeError(f'{path} has an unsafe member name: {member}')
            z.extractall(folder)
    box = Polygon.from_bbox(bbox_ll)
    box.srid = 4326
    out = {}
    for feature in DataSource(str(shape))[0]:
        cls = int(feature.get('Var'))
        clipped = GEOSGeometry(feature.geom.wkt, srid=4326).intersection(box)
        polys = [clipped] if clipped.geom_type == 'Polygon' else [g for g in clipped if g.geom_type == 'Polygon']
        out.setdefault(cls, []).extend([list(ring.coords) for ring in p] for p in polys if not p.empty)
    return out


def fetch_noah(cache_dir: Path, years: int) -> Path:
    sha, name = NOAH[years]
    return fetch_verified(NOAH_BASE.format(p=years), sha, Path(cache_dir) / name)


# --- Terrain ----------------------------------------------------------------

def river_relative(dem: np.ndarray, river_mask: np.ndarray, res: float):
    """(height above the nearest river cell, floored at 0; metres to it) for every cell."""
    if not river_mask.any():
        return np.clip(dem, 0, None).astype(np.float32), np.full(dem.shape, 1e7, np.float32)
    dist, (ri, ci) = ndimage.distance_transform_edt(~river_mask, return_indices=True)
    height = np.clip(dem - dem[ri, ci], 0, None)
    return height.astype(np.float32), (dist * res).astype(np.float32)


def depression_depth(dem: np.ndarray) -> np.ndarray:
    """How far each cell sits below the level water would fill its sink to (0 where it drains)."""
    from apps.hazards.susceptibility import fill_depressions

    return np.clip(fill_depressions(dem) - dem, 0, None).astype(np.float32)


def built_share_at(classes: np.ndarray, transform, points_ll: np.ndarray, radius_m: float = BUILT_RADIUS_M):
    """
    The share of WorldCover built-up pixels within radius_m of each point, on a
    north-up raster with transform (west, north, dx, dy) in degrees.
    """
    west, north, dx, dy = transform
    rx, ry = radius_m / (dx * KX), radius_m / (dy * KY)
    nx, ny = int(math.ceil(rx)), int(math.ceil(ry))
    yy, xx = np.mgrid[-ny:ny + 1, -nx:nx + 1]
    disk = ((xx / rx) ** 2 + (yy / ry) ** 2 <= 1).astype(float)
    built = (classes == BUILT_UP).astype(float)
    valid = (classes > 0).astype(float)
    num = signal.fftconvolve(built, disk, mode='same')
    den = signal.fftconvolve(valid, disk, mode='same')
    share = np.where(den > 0.5, num / np.maximum(den, 1e-9), 0.0)
    pts = np.asarray(points_ll, float).reshape(-1, 2)
    rows = np.clip(((north - pts[:, 1]) / dy).astype(int), 0, classes.shape[0] - 1)
    cols = np.clip(((pts[:, 0] - west) / dx).astype(int), 0, classes.shape[1] - 1)
    return np.clip(np.round(share[rows, cols], 6), 0, 1).astype(np.float32)


def sample_grid(grid, values: np.ndarray, points_ll: np.ndarray) -> np.ndarray:
    """The grid value under each (lng, lat) point (the nearest edge cell when a point is just outside)."""
    from apps.hazards.susceptibility import lnglat_to_px

    pts = np.asarray(points_ll, float).reshape(-1, 2)
    cols = np.empty(len(pts), int)
    rows = np.empty(len(pts), int)
    for i, (lng, lat) in enumerate(pts):
        x, y = lnglat_to_px(lng, lat, grid.zoom)
        cols[i], rows[i] = int(x - grid.px0), int(y - grid.py0)
    return values[np.clip(rows, 0, grid.height - 1), np.clip(cols, 0, grid.width - 1)]


# --- Areas and buildings ----------------------------------------------------

def membership(areas: list, buildings_ll: np.ndarray):
    """(building index, purok id) pairs: every area each building centre falls in (sitios overlap their puroks)."""
    pts_m = to_metres(buildings_ll)
    b_idx, p_ids = [], []
    for area in areas:
        polys = [[np.asarray(r, float) for r in poly] for poly in area['polygons']]
        flat = np.concatenate([r for poly in polys for r in poly])
        x0, y0 = flat.min(0)
        x1, y1 = flat.max(0)
        near = np.flatnonzero((buildings_ll[:, 0] >= x0) & (buildings_ll[:, 0] <= x1)
                              & (buildings_ll[:, 1] >= y0) & (buildings_ll[:, 1] <= y1))
        if not len(near):
            continue
        inside = points_inside([[to_metres(r) for r in poly] for poly in polys], pts_m[near])
        b_idx.extend(near[inside].tolist())
        p_ids.extend([area['purok_id']] * int(inside.sum()))
    return np.asarray(b_idx, int), np.asarray(p_ids, int)


GRID_COLUMNS = ('noah25_class', 'noah5_class', 'rel_height_river_m', 'dist_river_m', 'depression_m')


def write_grids(bbox, zoom: int, grids: dict, cache_dir) -> Path:
    """
    Save the input grids (GRID_COLUMNS) and the grid they sit on (the padded
    (south, west, north, east) and zoom), so training can read the same inputs
    at places that are not buildings.
    """
    path = Path(cache_dir) / GRIDS_FILE
    np.savez_compressed(path, bbox=np.asarray(bbox, float), zoom=np.asarray(zoom),
                        **{k: np.asarray(grids[k]) for k in GRID_COLUMNS})
    return path


def features_at(points_ll: np.ndarray, cache_dir, landcover=None) -> dict:
    """
    FEATURE_COLUMNS at any (lng, lat) points, read from the saved grids and
    WorldCover (`landcover` = (classes, transform), else the cached window).
    """
    from apps.hazards.susceptibility import Grid
    from apps.history import fire_sources

    with np.load(Path(cache_dir) / GRIDS_FILE, allow_pickle=False) as z:
        bbox = tuple(float(v) for v in z['bbox'])
        grid = Grid(*bbox, int(z['zoom']))
        grids = {k: z[k] for k in GRID_COLUMNS}
    pts = np.asarray(points_ll, float).reshape(-1, 2)
    out = {k: sample_grid(grid, grids[k], pts) for k in GRID_COLUMNS}
    if landcover is None:
        landcover = fire_sources.worldcover(cache_dir, bbox, log=lambda msg: None)
    out['built_share'] = built_share_at(landcover[0], landcover[1], pts)
    return out


@dataclass
class FloodFeatures:
    buildings: dict                    # lon, lat, barangay_id, barangay, FEATURE_COLUMNS, AUX_COLUMNS
    membership: tuple                  # (building index array, purok id array)
    areas: list                        # AREA_COLUMNS rows
    meta: dict = field(default_factory=dict)


def write_features(features: FloodFeatures, csv_path=FEATURES_FILE, meta_path=FEATURES_META, cache_dir=None):
    csv_path, meta_path = Path(csv_path), Path(meta_path)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=AREA_COLUMNS)
        writer.writeheader()
        writer.writerows({k: row[k] for k in AREA_COLUMNS} for row in features.areas)
    meta_path.write_text(json.dumps(features.meta, indent=1, sort_keys=True), encoding='utf-8')
    if cache_dir is not None:
        b = features.buildings
        np.savez_compressed(Path(cache_dir) / BUILDINGS_FILE, member_building=features.membership[0],
                            member_purok=features.membership[1],
                            **{k: np.asarray(v) for k, v in b.items()})


def read_features(csv_path=FEATURES_FILE, meta_path=FEATURES_META, cache_dir=None) -> FloodFeatures:
    with open(csv_path, newline='', encoding='utf-8') as f:
        areas = [{'purok_id': int(r['purok_id']), 'barangay_id': int(r['barangay_id']), 'barangay': r['barangay'],
                  'name': r['name'], 'confidence': r['confidence'], 'buildings': int(r['buildings'])}
                 for r in csv.DictReader(f)]
    meta = json.loads(Path(meta_path).read_text(encoding='utf-8'))
    buildings, member = {}, (np.zeros(0, int), np.zeros(0, int))
    if cache_dir is not None:
        with np.load(Path(cache_dir) / BUILDINGS_FILE, allow_pickle=False) as z:
            member = (z['member_building'], z['member_purok'])
            buildings = {k: z[k] for k in z.files if not k.startswith('member_')}
    return FloodFeatures(buildings=buildings, membership=member, areas=areas, meta=meta)
