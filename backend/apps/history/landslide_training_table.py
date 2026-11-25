"""
The landslide model's training table: slides from the open inventories (NASA
COOLR points, Mangkhut scars) and "no" points sampled around them, each with
the clues of apps/history/landslide_features.py and the UP NOAH class.

Distances between points are in local metres around an event's mean latitude.
The written table has no coordinates; it is a database derived from ODbL data
(OpenStreetMap roads, UP NOAH) and carries that notice on its first line.
"""
import csv
import io
import json
import math
import os
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree

from apps.hazards import susceptibility as sus
from apps.history.fire_features import points_inside
from apps.history.landslide_features import FEATURE_COLUMNS, TERRAIN_COLUMNS, TRAINING_FILE, TRAINING_META

TABLE_COLUMNS = ('event', 'fold', 'region', 'label', *FEATURE_COLUMNS, 'noah_class')
TEXT_COLUMNS = ('event', 'fold', 'region')
NOTICE = 'This table is a database derived from ODbL data and is shared under the ODbL.'

SEED = 0
NO_PER_SLIDE = 3
NO_RADIUS_M = 2000  # the mapped area is taken as ground within 2 km of a slide of the event
NO_GAP_M = 60       # a "no" point is at least this far from every slide of the event
STEEP_DEG = 10      # Talisay's road density is measured on ground this steep or steeper
ROAD_SHARE = 0.1    # an event keeps its road distances at this share of Talisay's density or more

M_PER_DEG_LAT = 110_574          # local metres north per degree (as landslide_features.road_points)
M_PER_DEG_LON_EQUATOR = 111_320  # local metres east per degree at the equator; city_grid's degree too
_BATCH = 4096       # candidate "no" points drawn at a time (fixed, so a seed always gives the same points)


def sample_no_points(slides_xy: np.ndarray, per_slide: int = NO_PER_SLIDE, radius_m: float = NO_RADIUS_M,
                     min_gap_m: float = NO_GAP_M, seed: int = SEED, exclude=None) -> np.ndarray:
    """
    `per_slide` points per slide (x, y metres), uniform over the union of the
    `radius_m` discs around the slides and at least `min_gap_m` from every slide.
    Rejection sampling: a candidate drawn in a random slide's disc is kept with
    chance 1 / (number of discs covering it), so overlapping discs are not
    sampled more densely. `exclude(xy) -> bool array`, when given, rejects the
    candidates it marks (inside a mapped slide's outline).
    """
    slides_xy = np.asarray(slides_xy, float).reshape(-1, 2)
    need = per_slide * len(slides_xy)
    if need == 0:
        return np.zeros((0, 2))
    rng = np.random.default_rng(seed)
    tree = cKDTree(slides_xy)
    kept, count = [], 0
    while count < need:
        centre = slides_xy[rng.integers(len(slides_xy), size=_BATCH)]
        r = radius_m * np.sqrt(rng.random(_BATCH))
        a = 2 * np.pi * rng.random(_BATCH)
        p = centre + np.c_[r * np.cos(a), r * np.sin(a)]
        u = rng.random(_BATCH)
        gap = tree.query(p)[0]
        covering = np.maximum(tree.query_ball_point(p, radius_m, return_length=True), 1)  # discs covering p
        keep = (gap >= min_gap_m) & (u < 1.0 / covering)
        if exclude is not None and keep.any():
            keep[keep] = ~np.asarray(exclude(p[keep]), bool)
        kept.append(p[keep])
        count += int(keep.sum())
    return np.concatenate(kept)[:need]


def _local_frame(points_ll: np.ndarray) -> tuple[float, float, float]:
    """(lon0, lat0, metres per degree of longitude) around the points' mean position."""
    lon0, lat0 = (float(v) for v in np.asarray(points_ll, float).reshape(-1, 2).mean(axis=0))
    return lon0, lat0, M_PER_DEG_LON_EQUATOR * math.cos(math.radians(lat0))


def _areas(geom) -> list:
    """The polygons with area in a geometry, collections flattened; lines and points have none."""
    if geom.geom_type == 'Polygon':
        return [geom] if not geom.empty and geom.area > 0 else []
    if geom.geom_type in ('MultiPolygon', 'GeometryCollection'):
        return [p for part in geom for p in _areas(part)]
    return []  # a (Multi)LineString or (Multi)Point: an outline that collapsed


def repair_outlines(polygons) -> tuple[list, int, int]:
    """
    (outlines, repaired, dropped): each mapped slide outline made valid. A
    self-crossing outline (59 of Mangkhut's 1,100) goes through GEOS make_valid,
    which keeps every lobe (buffer(0) can drop one), and only its areas are kept;
    an outline with no area left (it collapsed to a line or a point) is dropped.
    A valid outline is returned as it was.
    """
    from django.contrib.gis.geos import MultiPolygon

    out, repaired, dropped = [], 0, 0
    for geom in polygons:
        fixed = geom.make_valid()  # a copy of a valid geometry; unlike .valid, it prints no GEOS notice
        if fixed.wkb == geom.wkb:
            out.append(geom)
            continue
        polys = _areas(fixed)
        if not polys:
            dropped += 1
            continue
        repaired += 1
        out.append(polys[0] if len(polys) == 1 else MultiPolygon(*polys, srid=geom.srid))
    return out, repaired, dropped


def event_no_points(slides_ll: np.ndarray, seed: int = SEED, polygons=None) -> np.ndarray:
    """
    An event's "no" points as (lon, lat), sampled in local metres around its
    slides' mean latitude. `polygons` (GEOS, any SRID): the event's mapped slide
    outlines; no "no" point falls inside one, since "no" is ground with no mapped slide.
    """
    slides_ll = np.asarray(slides_ll, float).reshape(-1, 2)
    if not len(slides_ll):
        return np.zeros((0, 2))
    lon0, lat0, kx = _local_frame(slides_ll)

    def to_ll(xy):
        return np.c_[lon0 + xy[:, 0] / kx, lat0 + xy[:, 1] / M_PER_DEG_LAT]

    exclude = None
    if polygons:
        from django.contrib.gis.geos import GeometryCollection, Point

        parts = [p if p.srid in (None, 4326) else p.transform(4326, clone=True) for p in polygons]
        parts, _, _ = repair_outlines(parts)  # a self-crossing outline would make the union fail
        mapped = GeometryCollection(*parts, srid=4326).unary_union.prepared  # overlapping outlines merged

        def exclude(xy):
            return np.array([mapped.intersects(Point(float(x), float(y), srid=4326)) for x, y in to_ll(xy)], bool)

    xy = np.c_[(slides_ll[:, 0] - lon0) * kx, (slides_ll[:, 1] - lat0) * M_PER_DEG_LAT]
    return to_ll(sample_no_points(xy, seed=seed, exclude=exclude))


def _cell_centre_ll(grid, col: float, row: float) -> tuple[float, float]:
    lon, lat = sus.px_to_lnglat(grid.px0 + col, grid.py0 + row, grid.zoom)
    return float(lon), float(lat)


def scar_point(polygon, dem_grid, dem: np.ndarray) -> tuple[float, float]:
    """
    (lon, lat) of the centre of the polygon's highest DEM cell: the scar, where
    the slide started. A cell belongs to the polygon when its centre is inside;
    a polygon too small to hold a cell centre is the cell its centroid falls in.
    `polygon` is a GEOS Polygon or MultiPolygon in any SRID (Mangkhut's is UTM 51N).
    """
    geom = polygon if polygon.srid in (None, 4326) else polygon.transform(4326, clone=True)
    parts = [geom] if geom.geom_type == 'Polygon' else list(geom)
    rings = [[np.array([dem_grid.to_cell(x, y) for x, y in ring.coords]) for ring in part] for part in parts]
    outline = np.concatenate([part[0] for part in rings])
    c0, r0 = np.maximum(np.floor(outline.min(axis=0)).astype(int), 0)
    c1 = min(int(np.ceil(outline[:, 0].max())), dem_grid.width)
    r1 = min(int(np.ceil(outline[:, 1].max())), dem_grid.height)
    cols, rows = np.meshgrid(np.arange(c0, c1), np.arange(r0, r1))
    centres = np.c_[cols.ravel() + 0.5, rows.ravel() + 0.5]
    inside = points_inside(rings, centres) if len(centres) else np.zeros(0, bool)
    if inside.any():
        cells = centres[inside]
    else:
        x, y = dem_grid.to_cell(*geom.centroid.coords)
        cells = np.array([[min(max(math.floor(x), 0), dem_grid.width - 1) + 0.5,
                           min(max(math.floor(y), 0), dem_grid.height - 1) + 0.5]])
    heights = dem[cells[:, 1].astype(int), cells[:, 0].astype(int)]
    col, row = cells[int(np.argmax(heights))]
    return _cell_centre_ll(dem_grid, col, row)


def tiles_for(points_ll: np.ndarray, inner_km: float = 8, pad_km: float = 2) -> list[dict]:
    """
    A regular lattice of `inner_km` squares from the points' south-west corner;
    each square holding a point becomes a tile, padded by `pad_km` (as
    `city_grid` pads). Every point is in exactly one tile's `index`. Boxes are
    (south, west, north, east).
    """
    pts = np.asarray(points_ll, float).reshape(-1, 2)
    if not len(pts):
        return []
    _, lat0, kx = _local_frame(pts)
    dlat = inner_km * 1000 / M_PER_DEG_LON_EQUATOR  # city_grid's degree, so tiles are padded as Talisay's grid is
    dlng = inner_km * 1000 / kx
    west0, south0 = pts.min(axis=0)
    col = np.floor((pts[:, 0] - west0) / dlng).astype(int)
    row = np.floor((pts[:, 1] - south0) / dlat).astype(int)
    pad_lat = pad_km * 1000 / M_PER_DEG_LON_EQUATOR
    tiles = []
    for r, c in sorted(set(zip(row.tolist(), col.tolist()))):
        south, west = south0 + r * dlat, west0 + c * dlng
        north, east = south + dlat, west + dlng
        pad_lng = pad_lat / math.cos(math.radians((south + north) / 2))
        tiles.append({
            'bbox_inner': (south, west, north, east),
            'bbox_outer': (south - pad_lat, west - pad_lng, north + pad_lat, east + pad_lng),
            'index': np.flatnonzero((row == r) & (col == c)),
        })
    return tiles


def sampling_area(grid, slides_ll: np.ndarray, bbox_inner: tuple, dem: np.ndarray,
                  radius_m: float = NO_RADIUS_M) -> np.ndarray:
    """
    The tile's share of its event's sampling area: land cells (height > 0; the
    sea is not ground) within `radius_m` of a slide (any of the event's slides
    on the grid, so those in the tile's pad count too) whose centre lies in the
    tile's inner square, so no two tiles count the same cell.
    """
    slides = [tuple(p) for p in np.asarray(slides_ll, float).reshape(-1, 2)]
    near = sus.distance_to(sus.count_points(grid, slides) > 0, grid.res) <= radius_m
    n = sus.TILE * 2 ** grid.zoom
    lons = (grid.px0 + np.arange(grid.width) + 0.5) / n * 360.0 - 180.0
    lats = np.degrees(np.arctan(np.sinh(np.pi * (1 - 2 * (grid.py0 + np.arange(grid.height) + 0.5) / n))))
    south, west, north, east = bbox_inner
    inner = ((lats >= south) & (lats < north))[:, None] & ((lons >= west) & (lons < east))[None, :]
    return near & inner & (np.asarray(dem) > 0)


def road_check(densities: dict, talisay_density: float) -> dict:
    """{event: keeps its road distances}: its road density is at least ROAD_SHARE of Talisay's steep-ground density."""
    return {key: float(d) >= ROAD_SHARE * float(talisay_density) for key, d in densities.items()}


# --- The table file ----------------------------------------------------------

def _cell(value, column: str) -> str:
    if column in TEXT_COLUMNS:
        return str(value)
    if column == 'label':
        return str(int(value))
    value = float(value)
    return '' if math.isnan(value) else f'{value:.6g}'


def _plain(o):
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, np.floating):
        return float(o)
    if isinstance(o, np.bool_):
        return bool(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    raise TypeError(f'{type(o).__name__} is not JSON serializable')


def write_table(rows: list[dict], meta: dict, path=TRAINING_FILE, meta_path=TRAINING_META) -> None:
    """
    The table (the ODbL notice, then TABLE_COLUMNS only, so no coordinate is
    ever written) and its meta, each written to a .tmp beside it and swapped in.
    Refuses a row with a missing terrain clue: one would grey every Talisay point.
    """
    for i, row in enumerate(rows):
        bad = [c for c in TERRAIN_COLUMNS if not math.isfinite(float(row[c]))]
        if bad:
            raise ValueError(f"Row {i} ({row['event']}) has no {', '.join(bad)}; drop it before writing the table.")
    buffer = io.StringIO()
    buffer.write(f'# {NOTICE}\n')
    writer = csv.writer(buffer, lineterminator='\n')
    writer.writerow(TABLE_COLUMNS)
    writer.writerows([_cell(row[c], c) for c in TABLE_COLUMNS] for row in rows)
    texts = {Path(path): buffer.getvalue(),
             Path(meta_path): json.dumps(meta, indent=1, sort_keys=True, default=_plain) + '\n'}
    temps = {target: target.with_name(target.name + '.tmp') for target in texts}
    try:
        for target, text in texts.items():
            target.parent.mkdir(parents=True, exist_ok=True)
            temps[target].write_text(text, encoding='utf-8', newline='\n')
        for target, tmp in temps.items():
            os.replace(tmp, target)
    finally:
        for tmp in temps.values():
            tmp.unlink(missing_ok=True)


def read_table(path=TRAINING_FILE, meta_path=TRAINING_META) -> tuple[dict, dict]:
    """({column: array} for TABLE_COLUMNS, meta): text columns as str, label as int, the rest float (NaN where empty)."""
    with open(path, newline='', encoding='utf-8') as f:
        notice = f.readline()
        if NOTICE not in notice:
            raise ValueError(f'{path} does not start with the ODbL notice; it is not a training table.')
        records = list(csv.DictReader(f))
    table = {}
    for c in TABLE_COLUMNS:
        values = [r[c] for r in records]
        if c in TEXT_COLUMNS:
            table[c] = np.array(values, dtype=str)
        elif c == 'label':
            table[c] = np.array([int(v) for v in values], dtype=int)
        else:
            table[c] = np.array([float(v) if v != '' else np.nan for v in values], dtype=float)
    meta = json.loads(Path(meta_path).read_text(encoding='utf-8'))
    return table, meta
