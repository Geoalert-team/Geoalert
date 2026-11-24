"""
What each purok area is like, for the fire risk model: buildings, roads, the
road distance to a fire station, land cover, population and distance to the
coast and rivers. One row per area in the purok table, written to
data/fire_purok_features.csv by `manage.py build_fire_features`.

Adapted from the City of Pittsburgh Bureau of Fire / Carnegie Mellon Metro21
fire risk model (github.com/CityofPittsburgh/fire_risk_analysis, MIT License,
© 2017 mmadaio). Pittsburgh described each property from city records; Talisay
has no open property records, so each area is described from open map data
instead (spec section 4.2).

No fire record is read here or in fire_sources.py: every input comes from a
non-fire source, so no past fire can drive a prediction. Fire records are only
the yes/no label `fire_occurred`, built in fire_training.py.
tests.test_fire_features fails if t hese modules import a fire-record source.

Distances use an equirectangular projection at 10.27° N, the city's middle;
over Talisay's few kilometres that is within a fraction of a percent.
"""
import csv
import json
import math
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import dijkstra
from scipy.spatial import cKDTree

DATA_DIR = Path(__file__).parent / 'data'
FEATURES_FILE = DATA_DIR / 'fire_purok_features.csv'
FEATURES_META = DATA_DIR / 'fire_purok_features.meta.json'
MODEL_FILE = DATA_DIR / 'fire_purok_model.json'    # written by train_fire_model, read by fire_purok.py
REPORT_FILE = DATA_DIR / 'fire_purok_report.json'  # what the accuracy card shows
CREDIT = ('Adapted from the City of Pittsburgh Bureau of Fire / Carnegie Mellon Metro21 fire risk model '
          '(github.com/CityofPittsburgh/fire_risk_analysis, MIT License, © 2017 mmadaio)')

# The model's inputs, fixed in advance (spec 4.2); each is named for what it measures
FEATURE_COLUMNS = (
    'buildings_in_area', 'building_density_per_ha', 'median_footprint_m2',
    'median_gap_to_nearest_building_m', 'share_crowded_10m', 'road_density_m_per_ha', 'main_road_m',
    'median_building_to_road_m', 'road_distance_to_fire_station_m', 'share_built_up',
    'share_grass_shrub_bare', 'share_tree_cover', 'population', 'distance_to_coast_m',
    'distance_to_river_m',
)
LOG_COLUMNS = ('buildings_in_area', 'building_density_per_ha', 'population')  # used as log(1 + x)
# Which area a row is. from_fire_log (the area was drawn because a fire address
# named it) is for the report's map-leak table only, never an input.
ID_COLUMNS = ('purok_id', 'barangay_id', 'barangay', 'name', 'confidence', 'from_fire_log')
OPTIONAL_COLUMNS = ('population',)  # dropped, and said so, when WorldPop can't be had without an account

LAT0 = 10.27
KX = 111_320 * math.cos(math.radians(LAT0))  # metres per degree of longitude
KY = 110_574                                 # metres per degree of latitude
CROWD_RADIUS_M = 10   # a building with 2 or more others this close counts as crowded
CROWD_NEIGHBOURS = 2
ROAD_STEP_M = 10      # roads are measured as points this far apart
SNAP_M = 0.01         # road vertices closer than this are one junction (1e-7° is about 0.011 m)

# ESA WorldCover classes
BUILT_UP = (50,)
GRASS_SHRUB_BARE = (20, 30, 60)
TREE_COVER = (10,)
NO_DATA = 0


def to_metres(lnglat):
    """(n, 2) longitude/latitude as metres east and north."""
    a = np.asarray(lnglat, float).reshape(-1, 2)
    return np.c_[a[:, 0] * KX, a[:, 1] * KY]


def polygons_to_metres(polygons):
    """A list of polygons, each a list of (lng, lat) rings, in metres."""
    return [[to_metres(ring) for ring in poly] for poly in polygons]


def points_inside(polygons, pts):
    """
    Which of the (n, 2) points fall inside the polygons (each a list of rings,
    the first its outline, the rest holes), by the even-odd rule.
    """
    pts = np.asarray(pts, float).reshape(-1, 2)
    inside = np.zeros(len(pts), bool)
    if not len(pts):
        return inside
    px, py = pts[:, 0], pts[:, 1]
    for poly in polygons:
        for ring in poly:
            r = np.asarray(ring, float)
            x1, y1, x2, y2 = r[:-1, 0], r[:-1, 1], r[1:, 0], r[1:, 1]
            for a, b, c, d in zip(x1, y1, x2, y2):
                if b == d:
                    continue
                crosses = (b > py) != (d > py)
                inside ^= crosses & (px < a + (py - b) * (c - a) / (d - b))
    return inside


def ring_area_m2(ring):
    """Area inside one ring given in metres."""
    r = np.asarray(ring, float)
    return abs(float(np.dot(r[:-1, 0], r[1:, 1]) - np.dot(r[1:, 0], r[:-1, 1]))) / 2


def area_ha(polygons_m):
    """Hectares inside polygons given in metres, holes taken out."""
    return sum(ring_area_m2(p[0]) - sum(ring_area_m2(h) for h in p[1:]) for p in polygons_m) / 1e4


def segment_points(lines, step=ROAD_STEP_M):
    """Points every `step` metres along lines given in metres; each stands for `step` metres of line."""
    out = []
    for line in lines:
        a = np.asarray(line, float)
        for p, q in zip(a[:-1], a[1:]):
            n = max(1, int(np.hypot(*(q - p)) // step))
            out.append(p + (np.arange(n) / n)[:, None] * (q - p))
    return np.vstack(out) if out else np.zeros((0, 2))


def _nearest(targets, origins, tree=None):
    """Distance from each origin to its nearest target (inf when there is none)."""
    origins = np.asarray(origins, float).reshape(-1, 2)
    if not len(targets):
        return np.full(len(origins), np.inf)
    return (tree or cKDTree(targets)).query(origins)[0]


def median_distance(origins, targets, tree=None):
    """Median over the origins of the distance to the nearest target."""
    return float(np.median(_nearest(targets, origins, tree)))


def building_features(centres_m, footprint_m2, inside, area_ha, origin_m=None, tree=None):
    """
    The five building inputs for one area. centres_m are building centres in
    metres (all of them, so a building's nearest neighbour may lie outside),
    inside marks this area's. An area with no building gets zeros, and its gap
    is measured from origin_m (a point in the area) to the nearest building.
    """
    centres_m = np.asarray(centres_m, float).reshape(-1, 2)
    inside = np.asarray(inside, bool)
    n = int(inside.sum())
    tree = tree if tree is not None else (cKDTree(centres_m) if len(centres_m) else None)
    if n == 0:
        gap = median_distance(origin_m, centres_m, tree) if origin_m is not None else float('nan')
        return {'buildings_in_area': 0, 'building_density_per_ha': 0, 'median_footprint_m2': 0,
                'median_gap_to_nearest_building_m': gap, 'share_crowded_10m': 0}
    mine = centres_m[inside]
    gaps = tree.query(mine, k=2)[0][:, 1] if len(centres_m) > 1 else np.full(n, np.inf)
    near = tree.query_ball_point(mine, CROWD_RADIUS_M, return_length=True) - 1
    return {
        'buildings_in_area': n,
        'building_density_per_ha': n / area_ha,
        'median_footprint_m2': float(np.median(np.asarray(footprint_m2, float)[inside])),
        'median_gap_to_nearest_building_m': float(np.median(gaps)),
        'share_crowded_10m': float((near >= CROWD_NEIGHBOURS).mean()),
    }


def road_features(road_pts_m, main_pts_m, inside_road, inside_main, centres_inside_m, area_ha, origin_m=None,
                  road_tree=None):
    """
    The three road inputs for one area, from road points every ROAD_STEP_M
    metres (segment_points): road metres per hectare, metres of main road, and
    the median distance from its buildings (or origin_m when it has none) to a road.
    """
    centres = np.asarray(centres_inside_m, float).reshape(-1, 2)
    origins = centres if len(centres) else origin_m
    to_road = median_distance(origins, road_pts_m, road_tree) if origins is not None else float('nan')
    return {
        'road_density_m_per_ha': ROAD_STEP_M * int(np.sum(inside_road)) / area_ha,
        'main_road_m': float(ROAD_STEP_M * int(np.sum(inside_main))),
        'median_building_to_road_m': to_road,
    }


def station_distances(road_lines_m, stations_m, origins_m):
    """
    Metres by road from each origin to the nearest fire station: straight to
    the nearest road vertex that a station can be reached from, then along the
    road graph (vertices within SNAP_M are one junction), then straight from
    the road to the station.
    """
    keys, coords, edges = {}, [], {}

    def vertex(p):
        k = (round(p[0] / SNAP_M), round(p[1] / SNAP_M))
        if k not in keys:
            keys[k] = len(coords)
            coords.append(p)
        return keys[k]

    def join(i, j, metres):
        # Each edge once, at its shortest: the sparse matrix would add up repeats
        k = (min(i, j), max(i, j))
        edges[k] = min(edges.get(k, math.inf), metres + 1e-9)  # a zero weight would read as no edge

    for line in road_lines_m:
        a = np.asarray(line, float)
        ids = [vertex(p) for p in a]
        for (i, j), p, q in zip(zip(ids[:-1], ids[1:]), a[:-1], a[1:]):
            if i != j:
                join(i, j, float(np.hypot(*(q - p))))
    origins = np.asarray(origins_m, float).reshape(-1, 2)
    stations = np.asarray(stations_m, float).reshape(-1, 2)
    if not coords or not len(stations):
        return np.full(len(origins), np.inf)
    coords = np.asarray(coords)
    n = len(coords)
    # One extra node joined to each station's nearest vertex by the straight walk to it
    leg, at = cKDTree(coords).query(stations)
    for metres, i in zip(leg, at):
        join(int(i), n, float(metres))
    rows, cols = [i for i, _ in edges], [j for _, j in edges]
    graph = coo_matrix((list(edges.values()), (rows, cols)), shape=(n + 1, n + 1)).tocsr()
    dist = dijkstra(graph, directed=False, indices=n)[:n]
    reach = np.isfinite(dist)
    off_road, nearest = cKDTree(coords[reach]).query(origins)
    return off_road + dist[reach][nearest]


def landcover_shares(classes):
    """Shares of built-up, grass/shrub/bare and tree cover among the WorldCover pixels given (no-data left out)."""
    c = np.asarray(classes).ravel()
    c = c[c != NO_DATA]
    if not len(c):
        return {'share_built_up': 0.0, 'share_grass_shrub_bare': 0.0, 'share_tree_cover': 0.0}
    return {
        'share_built_up': float(np.isin(c, BUILT_UP).mean()),
        'share_grass_shrub_bare': float(np.isin(c, GRASS_SHRUB_BARE).mean()),
        'share_tree_cover': float(np.isin(c, TREE_COVER).mean()),
    }


def raster_window(transform, shape, bounds_ll, pad=1):
    """Row and column slices of a north-up raster covering (west, south, east, north), padded."""
    west, north, dx, dy = transform
    x0, y0, x1, y1 = bounds_ll
    r0 = max(int(math.floor((north - y1) / dy)) - pad, 0)
    r1 = min(int(math.ceil((north - y0) / dy)) + pad, shape[0])
    c0 = max(int(math.floor((x0 - west) / dx)) - pad, 0)
    c1 = min(int(math.ceil((x1 - west) / dx)) + pad, shape[1])
    return slice(r0, max(r0, r1)), slice(c0, max(c0, c1))


def pixel_centres(transform, rows, cols, split=1):
    """
    Centres (lng, lat) of the raster pixels in the row and column slices, each
    pixel split into split x split equal parts, row by row.
    """
    west, north, dx, dy = transform
    offs = (np.arange(split) + 0.5) / split
    xs = west + (np.arange(cols.start, cols.stop)[:, None] + offs).ravel() * dx
    ys = north - (np.arange(rows.start, rows.stop)[:, None] + offs).ravel() * dy
    gx, gy = np.meshgrid(xs, ys)
    return np.c_[gx.ravel(), gy.ravel()]


def landcover_in(polygons_m, bounds_ll, point_ll, landcover):
    """Land-cover shares over the WorldCover pixels centred in the area, or the pixel under its point."""
    classes, transform = landcover
    rows, cols = raster_window(transform, classes.shape, bounds_ll)
    window = classes[rows, cols]
    pts = pixel_centres(transform, rows, cols)
    picked = window.ravel()[points_inside(polygons_m, to_metres(pts))]
    if not len(picked):
        west, north, dx, dy = transform
        r = min(max(int((north - point_ll[1]) / dy), 0), classes.shape[0] - 1)
        c = min(max(int((point_ll[0] - west) / dx), 0), classes.shape[1] - 1)
        picked = classes[r:r + 1, c:c + 1].ravel()
    return landcover_shares(picked)


POP_SPLIT = 5  # each population pixel is spread over 5 x 5 points, so small areas get their share


def population_in(polygons_m, bounds_ll, population):
    """People in the area: WorldPop pixels spread evenly over POP_SPLIT² points each, summed inside."""
    values, transform = population
    rows, cols = raster_window(transform, values.shape, bounds_ll)
    window = np.where(values[rows, cols] > 0, values[rows, cols], 0.0)
    spread = np.repeat(np.repeat(window, POP_SPLIT, axis=0), POP_SPLIT, axis=1) / POP_SPLIT ** 2
    pts = pixel_centres(transform, rows, cols, POP_SPLIT)
    return float(spread.ravel()[points_inside(polygons_m, to_metres(pts))].sum())


def fire_log_names(points_csv):
    """
    (barangay, name) of the researched places whose sources include the BFP
    fire log: areas drawn because a fire address named them. For the report's
    map-leak table only (spec 6.5).
    """
    with open(points_csv, encoding='utf-8', newline='') as fh:
        return {(r['barangay'], r['name']) for r in csv.DictReader(fh)
                if 'fire log' in (r.get('sources') or '').lower()}


def _bounds(polygons_ll):
    rings = np.vstack([np.asarray(ring, float) for poly in polygons_ll for ring in poly])
    return rings[:, 0].min(), rings[:, 1].min(), rings[:, 0].max(), rings[:, 1].max()


def area_rows(areas, inputs, log=lambda msg: None):
    """
    One feature row per area.

    areas   dicts with the ID_COLUMNS, `polygons` (lng/lat rings as
            Purok.boundary.coords gives them) and `point` (lng, lat inside it)
    inputs  'buildings': (centres lng/lat (n, 2), footprint m² (n,));
            'osm': the cached OpenStreetMap dict (roads, main_roads,
            fire_stations, coastline, waterways);
            'landcover': (WorldCover classes, (west, north, dx, dy));
            'population': (WorldPop people per pixel, transform) or None
    """
    centres_ll, footprints = inputs['buildings']
    centres_ll = np.asarray(centres_ll, float).reshape(-1, 2)
    centres = to_metres(centres_ll)
    osm = inputs['osm']
    roads_m = [to_metres(line) for line in osm['roads']]
    road_pts = segment_points(roads_m)
    main_pts = segment_points([to_metres(line) for line in osm['main_roads']])
    road_ll, main_ll = road_pts / [KX, KY], main_pts / [KX, KY]
    coast = segment_points([to_metres(line) for line in osm['coastline']])
    rivers = segment_points([to_metres(w['coords']) for w in osm['waterways']])
    trees = {'buildings': cKDTree(centres) if len(centres) else None,
             'roads': cKDTree(road_pts) if len(road_pts) else None,
             'coast': cKDTree(coast) if len(coast) else None,
             'rivers': cKDTree(rivers) if len(rivers) else None}
    points = to_metres([a['point'] for a in areas])
    log(f'  Road distances to {len(osm["fire_stations"])} fire stations...')
    to_station = station_distances(roads_m, to_metres(osm['fire_stations']), np.vstack([centres, points]))
    building_to_station, point_to_station = to_station[:len(centres)], to_station[len(centres):]

    rows = []
    for i, area in enumerate(areas):
        polys = polygons_to_metres(area['polygons'])
        x0, y0, x1, y1 = _bounds(area['polygons'])
        ha = area_ha(polys)

        def near(pts_ll, pad_deg=0.0):
            return ((pts_ll[:, 0] >= x0 - pad_deg) & (pts_ll[:, 0] <= x1 + pad_deg)
                    & (pts_ll[:, 1] >= y0 - pad_deg) & (pts_ll[:, 1] <= y1 + pad_deg))

        inside = np.zeros(len(centres), bool)
        box = np.flatnonzero(near(centres_ll))
        inside[box[points_inside(polys, centres[box])]] = True
        origins = centres[inside] if inside.any() else points[i:i + 1]

        row = {c: area[c] for c in ID_COLUMNS}
        row.update(building_features(centres, footprints, inside, ha, origin_m=points[i], tree=trees['buildings']))
        in_road = np.zeros(len(road_pts), bool)
        box = np.flatnonzero(near(road_ll))
        in_road[box[points_inside(polys, road_pts[box])]] = True
        in_main = np.zeros(len(main_pts), bool)
        box = np.flatnonzero(near(main_ll))
        in_main[box[points_inside(polys, main_pts[box])]] = True
        row.update(road_features(road_pts, main_pts, in_road, in_main, centres[inside], ha,
                                 origin_m=points[i], road_tree=trees['roads']))
        row['road_distance_to_fire_station_m'] = float(np.median(
            building_to_station[inside] if inside.any() else point_to_station[i:i + 1]))
        row.update(landcover_in(polys, (x0, y0, x1, y1), area['point'], inputs['landcover']))
        population = inputs.get('population')
        row['population'] = (population_in(polys, (x0, y0, x1, y1), population)
                             if population is not None else float('nan'))
        row['distance_to_coast_m'] = median_distance(origins, coast, trees['coast'])
        row['distance_to_river_m'] = median_distance(origins, rivers, trees['rivers'])
        rows.append(row)
        if (i + 1) % 100 == 0:
            log(f'  {i + 1} of {len(areas)} areas')
    return rows


@dataclass
class FeatureTable:
    rows: list
    outlines_version: str
    built_at: str
    sources: dict
    dropped: tuple = field(default=())  # optional inputs left out (OPTIONAL_COLUMNS), with the reason in sources


def write_features(table, csv_path=FEATURES_FILE, meta_path=FEATURES_META):
    """The feature rows as CSV (a dropped input is left blank) and what built them as JSON beside it."""
    csv_path, meta_path = Path(csv_path), Path(meta_path)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    columns = list(ID_COLUMNS) + list(FEATURE_COLUMNS)
    with open(csv_path, 'w', encoding='utf-8', newline='') as fh:
        writer = csv.DictWriter(fh, fieldnames=columns, lineterminator='\n')
        writer.writeheader()
        for row in table.rows:
            out = {c: row[c] for c in columns}
            out['from_fire_log'] = 'yes' if row['from_fire_log'] else 'no'
            for c in FEATURE_COLUMNS:
                v = row[c]
                out[c] = '' if v is None or (isinstance(v, float) and math.isnan(v)) else repr(float(v))
            writer.writerow(out)
    meta = {'outlines_version': table.outlines_version, 'built_at': table.built_at, 'sources': table.sources,
            'dropped': list(table.dropped), 'columns': list(FEATURE_COLUMNS)}
    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


def read_features(csv_path=FEATURES_FILE, meta_path=FEATURES_META):
    """The FeatureTable write_features saved; a blank input reads as NaN."""
    meta = json.loads(Path(meta_path).read_text(encoding='utf-8'))
    rows = []
    with open(csv_path, encoding='utf-8', newline='') as fh:
        for r in csv.DictReader(fh):
            row = {'purok_id': int(r['purok_id']), 'barangay_id': int(r['barangay_id']), 'barangay': r['barangay'],
                   'name': r['name'], 'confidence': r['confidence'], 'from_fire_log': r['from_fire_log'] == 'yes'}
            row.update({c: float(r[c]) if r[c] != '' else float('nan') for c in FEATURE_COLUMNS})
            rows.append(row)
    return FeatureTable(rows=rows, outlines_version=meta['outlines_version'], built_at=meta['built_at'],
                        sources=meta['sources'], dropped=tuple(meta.get('dropped', ())))
