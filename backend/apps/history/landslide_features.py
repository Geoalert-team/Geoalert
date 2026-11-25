"""Terrain, land-cover and road clues for the landslide susceptibility model.

The same functions compute the clues in the Philippine typhoon training tiles
and in Talisay City, so a model learned on one is read on the other with the
same meaning. It reads nothing but heights, roads and land cover.
"""
import csv
import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from scipy import ndimage
from scipy.spatial import cKDTree

from apps.hazards.susceptibility import (
    STREAM_AREA_KM2, Grid, distance_to, draw_lines, fill_depressions, flow_accumulation,
)
from apps.history.fire_features import to_metres
from apps.history.flood_features import DATA_DIR, sample_grid

TERRAIN_COLUMNS = ('slope_deg', 'relief_m', 'profile_curv', 'plan_curv', 'hand_m', 'twi', 'dist_stream_m')
LANDCOVER_CLASSES = {2: 'lc_trees', 11: 'lc_rangeland', 5: 'lc_crops', 7: 'lc_built', 8: 'lc_bare'}
FEATURE_COLUMNS = TERRAIN_COLUMNS + ('dist_road_m',) + tuple(LANDCOVER_CLASSES.values())
CLIP_COLUMNS = ('dist_road_m',) + tuple(LANDCOVER_CLASSES.values())
LOG_COLUMNS = ('dist_stream_m', 'dist_road_m')

TRAINING_FILE = DATA_DIR / 'landslide_training.csv'
TRAINING_META = DATA_DIR / 'landslide_training.meta.json'
FEATURES_FILE = DATA_DIR / 'landslide_purok_features.csv'
FEATURES_META = DATA_DIR / 'landslide_purok_features.meta.json'
POINTS_FILE = 'landslide_points.npz'  # in the cache directory
GRIDS_FILE = 'landslide_feature_grids.npz'  # in the cache directory: Talisay's clue grids
MODEL_FILE = DATA_DIR / 'landslide_purok_model.json'
REPORT_FILE = DATA_DIR / 'landslide_purok_report.json'

AREA_COLUMNS = ('purok_id', 'barangay_id', 'barangay', 'name', 'confidence',
                'points', 'buildings', 'road_points', 'noah_p90')
GRID_COLUMNS = FEATURE_COLUMNS + ('noah_class',)
BUILDING, ROAD = 0, 1
DEDUPE_M = 1.0

RELIEF_WINDOW_M = 150
MIN_TAN_SLOPE = 0.001
FLAT_GRADIENT_SQ = 1e-12


def curvatures(smooth: np.ndarray, res: float) -> tuple[np.ndarray, np.ndarray]:
    """Zevenbergen-Thorne profile and plan curvature (1/m) of a smoothed DEM; 0 where the ground is flat."""
    z = np.pad(np.asarray(smooth, np.float64), 1, mode='edge')
    h, w = smooth.shape
    z0 = z[1:1 + h, 1:1 + w]
    zn, zs = z[0:h, 1:1 + w], z[2:2 + h, 1:1 + w]
    zw, ze = z[1:1 + h, 0:w], z[1:1 + h, 2:2 + w]
    znw, zne = z[0:h, 0:w], z[0:h, 2:2 + w]
    zsw, zse = z[2:2 + h, 0:w], z[2:2 + h, 2:2 + w]
    d = ((zw + ze) / 2 - z0) / res ** 2
    e = ((zn + zs) / 2 - z0) / res ** 2
    f = (-znw + zne + zsw - zse) / (4 * res ** 2)
    g = (-zw + ze) / (2 * res)
    hh = (zn - zs) / (2 * res)
    gg = g * g + hh * hh
    flat = gg < FLAT_GRADIENT_SQ
    denom = np.where(flat, 1.0, gg)
    profile = np.where(flat, 0.0, -2 * (d * g * g + e * hh * hh + f * g * hh) / denom)
    plan = np.where(flat, 0.0, 2 * (d * hh * hh + e * g * g - f * g * hh) / denom)
    return profile.astype(np.float32), plan.astype(np.float32)


def terrain_grids(dem: np.ndarray, res: float) -> dict[str, np.ndarray]:
    """The seven terrain clues for every cell of a DEM with `res` metres per cell."""
    land = dem > 0
    smooth = ndimage.gaussian_filter(dem, sigma=1.0)
    gy, gx = np.gradient(smooth, res)
    tan_slope = np.hypot(gx, gy)
    win = max(3, int(round(RELIEF_WINDOW_M / res)) | 1)
    relief = ndimage.maximum_filter(smooth, size=win) - ndimage.minimum_filter(smooth, size=win)
    profile, plan = curvatures(smooth, res)

    filled = fill_depressions(smooth)
    area = flow_accumulation(filled, res)
    channels = (area >= STREAM_AREA_KM2 * 1e6) & land
    if channels.any():
        _, (ri, ci) = ndimage.distance_transform_edt(~channels, return_indices=True)
        hand = np.clip(filled - filled[ri, ci], 0, None)
    else:
        hand = filled - filled.min()
    twi = np.log((area / res) / np.maximum(tan_slope, MIN_TAN_SLOPE))

    out = {
        'slope_deg': np.degrees(np.arctan(tan_slope)),
        'relief_m': relief,
        'profile_curv': profile,
        'plan_curv': plan,
        'hand_m': hand,
        'twi': twi,
        'dist_stream_m': distance_to(channels, res),
    }
    return {name: out[name].astype(np.float32) for name in TERRAIN_COLUMNS}


def road_distance(grid: Grid, roads: list) -> np.ndarray:
    """Metres from each cell to the nearest road line (roads: lists of (lng, lat) points)."""
    return distance_to(draw_lines(grid, roads, width=1), grid.res)


def landcover_shares(classes: np.ndarray, res_m: float, radius_m: float = 50) -> dict[str, np.ndarray]:
    """For each land-cover group, its share of the cells within `radius_m` (all classes count in the denominator)."""
    r = max(1, int(round(radius_m / res_m)))
    yy, xx = np.mgrid[-r:r + 1, -r:r + 1]
    footprint = (yy ** 2 + xx ** 2 <= r ** 2).astype(np.float32)
    cover = ndimage.convolve(np.ones(classes.shape, np.float32), footprint, mode='constant')
    shares = {}
    for code, name in LANDCOVER_CLASSES.items():
        hits = ndimage.convolve((classes == code).astype(np.float32), footprint, mode='constant')
        shares[name] = (hits / cover).astype(np.float32)
    return shares


def sample(grid: Grid, grids: dict, points_ll: np.ndarray) -> dict[str, np.ndarray]:
    """Each clue grid read under every (lng, lat) point."""
    return {name: sample_grid(grid, values, points_ll) for name, values in grids.items()}


# --- Talisay scoring points --------------------------------------------------

def road_points(lines: list, step_m: float = 20) -> np.ndarray:
    """(lon, lat) every `step_m` metres along each line, starting at its first vertex; points within 1 m of an earlier one are dropped."""
    out = []
    for line in lines:
        if len(line) < 2:
            continue
        arr = np.asarray(line, float)
        local = arr * [111_320 * np.cos(np.radians(arr[:, 1].mean())), 110_574]  # metres at this line's latitude
        seg = np.hypot(*np.diff(local, axis=0).T)
        along = np.concatenate([[0.0], np.cumsum(seg)])
        total = along[-1]
        if total <= 0:
            continue
        at = np.arange(int(np.floor(total / step_m + 1e-6)) + 1) * step_m
        out.append(np.c_[np.interp(at, along, arr[:, 0]), np.interp(at, along, arr[:, 1])])
    if not out:
        return np.zeros((0, 2))
    pts = np.concatenate(out)
    drop = np.zeros(len(pts), bool)
    for i, j in sorted(cKDTree(to_metres(pts)).query_pairs(DEDUPE_M)):
        if not drop[i]:
            drop[j] = True
    return pts[~drop]


def scoring_points(buildings_ll: np.ndarray, roads: list, city) -> tuple[np.ndarray, np.ndarray]:
    """
    Building centres and road points inside the city, as ((n, 2) lon/lat, kind) with
    kind 0 for a building and 1 for a road point. `city` is (grid, mask): the grid and
    a boolean array that is True on the city's cells.
    """
    grid, mask = city
    buildings = np.asarray(buildings_ll, float).reshape(-1, 2)
    on_roads = road_points(roads)
    pts = np.concatenate([buildings, on_roads])
    kind = np.r_[np.full(len(buildings), BUILDING), np.full(len(on_roads), ROAD)]
    cells = np.array([grid.to_cell(lng, lat) for lng, lat in pts]).reshape(-1, 2)
    cols = np.floor(cells[:, 0]).astype(int)
    rows = np.floor(cells[:, 1]).astype(int)
    inside = (cols >= 0) & (cols < grid.width) & (rows >= 0) & (rows < grid.height)
    inside[inside] = mask[rows[inside], cols[inside]]
    return pts[inside], kind[inside].astype(np.uint8)


def write_grids(bbox, zoom: int, grids: dict, cache_dir) -> Path:
    """Save Talisay's clue grids (GRID_COLUMNS) with the padded (south, west, north, east) and zoom they sit on."""
    path = Path(cache_dir) / GRIDS_FILE
    np.savez_compressed(path, bbox=np.asarray(bbox, float), zoom=np.asarray(zoom),
                        **{k: np.asarray(grids[k]) for k in GRID_COLUMNS})
    return path


def on_grid(grid: Grid, points_ll: np.ndarray) -> np.ndarray:
    """True for each (lon, lat) point in one of the grid's cells (sample_grid reads an edge cell for any other)."""
    pts = np.asarray(points_ll, float).reshape(-1, 2)
    cells = np.array([grid.to_cell(lng, lat) for lng, lat in pts], float).reshape(-1, 2)
    return ((cells[:, 0] >= 0) & (cells[:, 0] < grid.width) & (cells[:, 1] >= 0) & (cells[:, 1] < grid.height))


def features_at(points_ll: np.ndarray, cache_dir) -> dict[str, np.ndarray]:
    """
    Every FEATURE_COLUMNS value and the NOAH class at any (lon, lat) points in
    Talisay, from the saved grids. A point off the grids (a misplaced map
    point, say) has no clue there: NaN in every column, never the nearest edge
    cell's values, so the missing-terrain rule (R20) drops it. When every
    point is on the grids the values are read exactly as before.
    """
    with np.load(Path(cache_dir) / GRIDS_FILE, allow_pickle=False) as z:
        grid = Grid(*(float(v) for v in z['bbox']), int(z['zoom']))
        grids = {k: z[k] for k in GRID_COLUMNS}
    pts = np.asarray(points_ll, float).reshape(-1, 2)
    out = sample(grid, grids, pts)
    off = ~on_grid(grid, pts)
    if off.any():
        out = {k: np.where(off, np.nan, np.asarray(v, float)) for k, v in out.items()}
    return out


@dataclass
class LandslideFeatures:
    points: dict       # lon, lat, kind, noah_class and every FEATURE_COLUMNS array (the cache npz only)
    membership: tuple  # (point index array, purok id array)
    areas: list        # AREA_COLUMNS rows
    meta: dict = field(default_factory=dict)


def write_features(features: LandslideFeatures, csv_path=FEATURES_FILE, meta_path=FEATURES_META, cache_dir=None):
    """The per-area table (no coordinates) and meta; with cache_dir also the points and membership npz."""
    csv_path, meta_path = Path(csv_path), Path(meta_path)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=AREA_COLUMNS)
        writer.writeheader()
        writer.writerows({k: row[k] for k in AREA_COLUMNS} for row in features.areas)
    meta_path.write_text(json.dumps(features.meta, indent=1, sort_keys=True), encoding='utf-8')
    if cache_dir is not None:
        np.savez_compressed(Path(cache_dir) / POINTS_FILE, member_point=features.membership[0],
                            member_purok=features.membership[1],
                            **{k: np.asarray(v) for k, v in features.points.items()})


def read_features(csv_path=FEATURES_FILE, meta_path=FEATURES_META, cache_dir=None) -> LandslideFeatures:
    with open(csv_path, newline='', encoding='utf-8') as f:
        areas = [{'purok_id': int(r['purok_id']), 'barangay_id': int(r['barangay_id']), 'barangay': r['barangay'],
                  'name': r['name'], 'confidence': r['confidence'], 'points': int(r['points']),
                  'buildings': int(r['buildings']), 'road_points': int(r['road_points']),
                  'noah_p90': float(r['noah_p90'])} for r in csv.DictReader(f)]
    meta = json.loads(Path(meta_path).read_text(encoding='utf-8'))
    points, member = {}, (np.zeros(0, int), np.zeros(0, int))
    if cache_dir is not None:
        with np.load(Path(cache_dir) / POINTS_FILE, allow_pickle=False) as z:
            member = (z['member_point'], z['member_purok'])
            points = {k: z[k] for k in z.files if not k.startswith('member_')}
    return LandslideFeatures(points=points, membership=member, areas=areas, meta=meta)
