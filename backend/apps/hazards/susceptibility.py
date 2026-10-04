import heapq
import io
import json
import math
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import requests
from PIL import Image, ImageDraw
from scipy import ndimage

TERRAIN_URL = 'https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png'
OVERPASS_URLS = [
    'https://overpass-api.de/api/interpreter',
    'https://overpass.private.coffee/api/interpreter',
    'https://maps.mail.ru/osm/tools/overpass/api/interpreter',
    'https://overpass.kumi.systems/api/interpreter',
]
USER_AGENT = 'GeoAlert-Talisay/1.0 (hazard susceptibility build)'
TILE = 256
EARTH_CIRCUMFERENCE = 40075016.686  # meters

# Five output classes, lowest first (same colors as the frontend legend)
CLASSES = [
    {'key': 'very-low', 'label': 'Very low', 'color': '#a8a8a8'},
    {'key': 'low', 'label': 'Low', 'color': '#ffb100'},
    {'key': 'medium', 'label': 'Medium', 'color': '#8fe800'},
    {'key': 'high', 'label': 'High', 'color': '#1f3cff'},
    {'key': 'very-high', 'label': 'Very high', 'color': '#ff0000'},
]

# Factor, 4 thresholds between scores 1..5, direction, weight.
# 'up' means larger values score higher; 'down' means smaller values score higher.
FACTORS = {
    'flood': [
        ('elevation', [5, 10, 20, 50], 'down', 0.25),           # m above sea level
        ('hand', [2, 5, 10, 20], 'down', 0.25),                 # m above nearest drainage or sea
        ('dist_water', [100, 200, 400, 800], 'down', 0.20),     # m to river / stream / canal / drain
        ('slope', [1, 3, 8, 15], 'down', 0.15),                 # degrees
        ('dist_coast', [200, 500, 1000, 2000], 'down', 0.15),   # m to the sea
    ],
    'landslide': [
        ('slope', [5, 10, 18, 30], 'up', 0.45),                 # degrees
        ('relief', [5, 15, 30, 60], 'up', 0.15),                # m of local relief within ~150 m
        ('elevation', [20, 60, 150, 300], 'up', 0.10),          # m above sea level
        ('dist_water', [50, 150, 300, 500], 'down', 0.15),      # stream undercutting
        ('dist_road', [50, 100, 200, 400], 'down', 0.15),       # road cuts
    ],
    'fire': [
        ('building_density', [2, 8, 20, 40], 'up', 0.40),       # buildings per hectare
        ('urban_landuse', [1.5, 2.5, 3.5, 4.5], 'up', 0.15),    # 1 none, 3 residential, 4 commercial, 5 industrial
        ('dist_fire_station', [1000, 2000, 3500, 5000], 'up', 0.20),  # m, farther = slower response
        ('dist_main_road', [100, 250, 500, 800], 'up', 0.15),   # m to a primary/secondary/tertiary road
        ('dist_road', [25, 50, 100, 200], 'up', 0.10),          # m to any road a fire truck can use
    ],
}
SCORE_BREAKS = [1.8, 2.6, 3.4, 4.2]  # equal intervals on the 1-5 weighted score

STREAM_AREA_KM2 = 0.25    # upstream area that starts a DEM-derived channel
FLAT_SLOPE_DEG = 3        # landslides: flatter than this is always very low
FIRE_STATION_SEARCH_M = 6000  # look for stations this far outside the city

ROAD_TYPES = {
    'motorway', 'trunk', 'primary', 'secondary', 'tertiary', 'unclassified',
    'residential', 'service', 'living_street',
    'motorway_link', 'trunk_link', 'primary_link', 'secondary_link', 'tertiary_link',
}
MAIN_ROAD_TYPES = {
    'trunk', 'primary', 'secondary', 'tertiary',
    'trunk_link', 'primary_link', 'secondary_link', 'tertiary_link',
}
LANDUSE_SCORE = {'residential': 3, 'commercial': 4, 'retail': 4, 'industrial': 5}
WATERWAY_TYPES = {'river', 'stream', 'canal', 'drain', 'ditch'}
DRAWN_WATERWAYS = {'river', 'stream', 'canal'}  # shown on the map

NEIGHBORS = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]


# ---------------------------------------------------------------------------
# Web Mercator grid (one cell = one terrain-tile pixel at the chosen zoom)
# ---------------------------------------------------------------------------

def lnglat_to_px(lng, lat, zoom):
    n = TILE * 2 ** zoom
    x = (lng + 180.0) / 360.0 * n
    s = math.sin(math.radians(lat))
    y = (0.5 - math.log((1 + s) / (1 - s)) / (4 * math.pi)) * n
    return x, y


def px_to_lnglat(x, y, zoom):
    n = TILE * 2 ** zoom
    lng = x / n * 360.0 - 180.0
    lat = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / n))))
    return lng, lat


class Grid:
    def __init__(self, south, west, north, east, zoom):
        self.zoom = zoom
        x0, y1 = lnglat_to_px(west, south, zoom)
        x1, y0 = lnglat_to_px(east, north, zoom)
        self.px0 = int(math.floor(x0))
        self.py0 = int(math.floor(y0))
        self.width = int(math.ceil(x1)) - self.px0
        self.height = int(math.ceil(y1)) - self.py0
        lat_mid = (south + north) / 2
        self.res = EARTH_CIRCUMFERENCE * math.cos(math.radians(lat_mid)) / (TILE * 2 ** zoom)

    @property
    def shape(self):
        return (self.height, self.width)

    def to_cell(self, lng, lat):
        x, y = lnglat_to_px(lng, lat, self.zoom)
        return x - self.px0, y - self.py0

    def bounds(self):
        """[[south, west], [north, east]] of the cell edges, for Leaflet."""
        west, north = px_to_lnglat(self.px0, self.py0, self.zoom)
        east, south = px_to_lnglat(self.px0 + self.width, self.py0 + self.height, self.zoom)
        return [[south, west], [north, east]]


# ---------------------------------------------------------------------------
# Downloads
# ---------------------------------------------------------------------------

def make_session():
    s = requests.Session()
    s.headers['User-Agent'] = USER_AGENT
    return s


def fetch_dem(grid, session, log):
    tx0, ty0 = grid.px0 // TILE, grid.py0 // TILE
    tx1 = (grid.px0 + grid.width - 1) // TILE
    ty1 = (grid.py0 + grid.height - 1) // TILE
    mosaic = np.zeros(((ty1 - ty0 + 1) * TILE, (tx1 - tx0 + 1) * TILE), np.float32)
    total = (tx1 - tx0 + 1) * (ty1 - ty0 + 1)
    log(f'  Downloading {total} elevation tiles (zoom {grid.zoom})...')
    for tx in range(tx0, tx1 + 1):
        for ty in range(ty0, ty1 + 1):
            url = TERRAIN_URL.format(z=grid.zoom, x=tx, y=ty)
            r = session.get(url, timeout=60)
            r.raise_for_status()
            rgb = np.asarray(Image.open(io.BytesIO(r.content)).convert('RGB'), np.float32)
            elev = rgb[..., 0] * 256 + rgb[..., 1] + rgb[..., 2] / 256 - 32768
            oy, ox = (ty - ty0) * TILE, (tx - tx0) * TILE
            mosaic[oy:oy + TILE, ox:ox + TILE] = elev
    ox, oy = grid.px0 - tx0 * TILE, grid.py0 - ty0 * TILE
    return mosaic[oy:oy + grid.height, ox:ox + grid.width].copy()


def overpass(query, session, log):
    last_error = None
    for url in OVERPASS_URLS:
        for _ in range(2):
            try:
                r = session.post(url, data={'data': query}, timeout=300)
                if r.status_code == 200:
                    return r.json().get('elements', [])
                last_error = f'{url} answered {r.status_code}'
            except (requests.RequestException, ValueError) as exc:
                last_error = f'{url}: {exc}'
            log(f'  Overpass busy ({last_error}), retrying...')
            time.sleep(10)
    raise RuntimeError(f'OpenStreetMap download failed: {last_error}')


def _bbox(south, west, north, east):
    return f'{south},{west},{north},{east}'


def _line(geometry):
    return [(p['lon'], p['lat']) for p in geometry or [] if p]


def fetch_osm(south, west, north, east, session, log):
    bbox = _bbox(south, west, north, east)
    log('  Downloading rivers, coastline, roads and land use from OpenStreetMap...')
    elements = overpass(f"""
[out:json][timeout:240];
(
  way["waterway"]({bbox});
  way["natural"="coastline"]({bbox});
  way["highway"]({bbox});
  way["landuse"~"^(residential|commercial|retail|industrial)$"]({bbox});
  relation["landuse"~"^(residential|commercial|retail|industrial)$"]({bbox});
);
out geom;
""", session, log)

    osm = {'waterways': [], 'coastline': [], 'roads': [], 'main_roads': [], 'landuse': [],
           'buildings': [], 'fire_stations': []}
    for el in elements:
        tags = el.get('tags', {})
        if el['type'] == 'way':
            line = _line(el.get('geometry'))
            if len(line) < 2:
                continue
            if tags.get('waterway') in WATERWAY_TYPES:
                osm['waterways'].append({'kind': tags['waterway'], 'name': tags.get('name', ''), 'coords': line})
            elif tags.get('natural') == 'coastline':
                osm['coastline'].append(line)
            elif tags.get('highway') in ROAD_TYPES:
                osm['roads'].append(line)
                if tags['highway'] in MAIN_ROAD_TYPES:
                    osm['main_roads'].append(line)
            elif tags.get('landuse') in LANDUSE_SCORE and len(line) >= 3:
                osm['landuse'].append((LANDUSE_SCORE[tags['landuse']], [line]))
        elif el['type'] == 'relation' and tags.get('landuse') in LANDUSE_SCORE:
            for m in el.get('members', []):
                line = _line(m.get('geometry'))
                if m.get('role') == 'outer' and len(line) >= 3:
                    osm['landuse'].append((LANDUSE_SCORE[tags['landuse']], [line]))

    log('  Downloading buildings from OpenStreetMap...')
    for el in overpass(f'[out:json][timeout:240];way["building"]({bbox});out center;', session, log):
        c = el.get('center')
        if c:
            osm['buildings'].append((c['lon'], c['lat']))

    osm['fire_stations'] = fetch_fire_stations(south, west, north, east, session, log)
    return osm


def fetch_fire_stations(south, west, north, east, session, log):
    """Stations outside the city still respond to it. Optional: if every server is
    busy, the build carries on and treats response distance as average."""
    log('  Downloading fire stations from OpenStreetMap...')
    dlat = FIRE_STATION_SEARCH_M / 111320
    dlng = dlat / math.cos(math.radians((south + north) / 2))
    wide = _bbox(south - dlat, west - dlng, north + dlat, east + dlng)
    try:
        stations = overpass(f'[out:json][timeout:120];nwr["amenity"="fire_station"]({wide});out center;', session, log)
    except RuntimeError as exc:
        log(f'  Warning: skipped fire stations ({exc}).')
        stations = []
    points = []
    for el in stations:
        if el['type'] == 'node':
            points.append((el['lon'], el['lat']))
        elif el.get('center'):
            points.append((el['center']['lon'], el['center']['lat']))
    return points


# ---------------------------------------------------------------------------
# Rasterizing
# ---------------------------------------------------------------------------

def draw_lines(grid, lines, width=1):
    img = Image.new('1', (grid.width, grid.height), 0)
    d = ImageDraw.Draw(img)
    for coords in lines:
        pts = [grid.to_cell(lng, lat) for lng, lat in coords]
        if len(pts) >= 2:
            d.line(pts, fill=1, width=width)
    return np.array(img, dtype=bool)


def draw_polygons(grid, polygons):
    """polygons: list of (value, [outer_ring, hole, ...]); later values paint over earlier ones."""
    img = Image.new('I', (grid.width, grid.height), 0)
    d = ImageDraw.Draw(img)
    for value, rings in polygons:
        outer = [grid.to_cell(lng, lat) for lng, lat in rings[0]]
        if len(outer) >= 3:
            d.polygon(outer, fill=int(value))
        for hole in rings[1:]:
            pts = [grid.to_cell(lng, lat) for lng, lat in hole]
            if len(pts) >= 3:
                d.polygon(pts, fill=0)
    return np.array(img, dtype=np.int32)


def count_points(grid, points):
    counts = np.zeros(grid.shape, np.float32)
    if not points:
        return counts
    cells = np.array([grid.to_cell(lng, lat) for lng, lat in points])
    cols = np.floor(cells[:, 0]).astype(int)
    rows = np.floor(cells[:, 1]).astype(int)
    ok = (cols >= 0) & (cols < grid.width) & (rows >= 0) & (rows < grid.height)
    np.add.at(counts, (rows[ok], cols[ok]), 1)
    return counts


def distance_to(mask, res):
    if not mask.any():
        return np.full(mask.shape, 1e7, np.float32)
    return (ndimage.distance_transform_edt(~mask) * res).astype(np.float32)


def distance_to_points(grid, points):
    """Meters to the nearest point; points may lie outside the grid."""
    if not points:
        return np.full(grid.shape, 3000, np.float32)  # unknown: treat as average response distance
    rows = np.arange(grid.height, dtype=np.float32)[:, None] + 0.5
    cols = np.arange(grid.width, dtype=np.float32)[None, :] + 0.5
    best = np.full(grid.shape, np.inf, np.float32)
    for lng, lat in points:
        c, r = grid.to_cell(lng, lat)
        best = np.minimum(best, np.hypot(cols - c, rows - r))
    return best * grid.res


# ---------------------------------------------------------------------------
# Terrain and hydrology
# ---------------------------------------------------------------------------

def fill_depressions(dem, eps=1e-4):
    """Priority-flood (Barnes et al. 2014) with a tiny gradient so flats still drain."""
    h, w = dem.shape
    filled = dem.astype(np.float64).ravel().tolist()
    closed = bytearray(h * w)
    heap = []
    for r in range(h):
        for c in (0, w - 1):
            i = r * w + c
            if not closed[i]:
                closed[i] = 1
                heap.append((filled[i], i))
    for c in range(w):
        for r in (0, h - 1):
            i = r * w + c
            if not closed[i]:
                closed[i] = 1
                heap.append((filled[i], i))
    heapq.heapify(heap)
    push, pop = heapq.heappush, heapq.heappop
    while heap:
        z, i = pop(heap)
        r, c = divmod(i, w)
        for dr, dc in NEIGHBORS:
            nr, nc = r + dr, c + dc
            if 0 <= nr < h and 0 <= nc < w:
                j = nr * w + nc
                if not closed[j]:
                    closed[j] = 1
                    if filled[j] <= z:
                        filled[j] = z + eps
                    push(heap, (filled[j], j))
    return np.array(filled, np.float64).reshape(h, w)


def flow_accumulation(filled, res):
    """D8 upstream area in square meters."""
    h, w = filled.shape
    padded = np.pad(filled, 1, constant_values=np.inf)
    best = np.zeros_like(filled)
    receiver = np.full(h * w, -1, np.int64)
    rows = np.arange(h)[:, None]
    cols = np.arange(w)[None, :]
    for dr, dc in NEIGHBORS:
        nb = padded[1 + dr:1 + dr + h, 1 + dc:1 + dc + w]
        drop = (filled - nb) / (res * math.hypot(dr, dc))
        better = drop > best
        best = np.where(better, drop, best)
        target = ((rows + dr) * w + (cols + dc)).ravel()
        receiver = np.where(better.ravel(), target, receiver)
    order = np.argsort(-filled.ravel(), kind='stable').tolist()
    recv = receiver.tolist()
    acc = [1.0] * (h * w)
    for i in order:
        j = recv[i]
        if j >= 0:
            acc[j] += acc[i]
    return np.array(acc).reshape(h, w) * res * res


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------

def reclass(values, breaks, direction):
    score = np.digitize(values, breaks).astype(np.float32) + 1  # 1..5, larger values score higher
    return score if direction == 'up' else 6 - score


def classify(factors, hazard):
    score = np.zeros(next(iter(factors.values())).shape, np.float32)
    for name, breaks, direction, weight in FACTORS[hazard]:
        score += weight * reclass(factors[name], breaks, direction)
    return (np.digitize(score, SCORE_BREAKS) + 1).astype(np.uint8)  # 1..5


def compute_factors(grid, dem, osm, city_mask, log):
    res = grid.res
    land = dem > 0

    log('  Terrain: slope and local relief...')
    smooth = ndimage.gaussian_filter(dem, sigma=1.0)
    gy, gx = np.gradient(smooth, res)
    slope = np.degrees(np.arctan(np.hypot(gx, gy))).astype(np.float32)
    win = max(3, int(round(150 / res)) | 1)
    relief = (ndimage.maximum_filter(smooth, size=win) - ndimage.minimum_filter(smooth, size=win)).astype(np.float32)

    log('  Hydrology: filling depressions and tracing drainage (can take a minute)...')
    filled = fill_depressions(smooth)
    area = flow_accumulation(filled, res)
    dem_streams = (area >= STREAM_AREA_KM2 * 1e6) & land

    water_lines = draw_lines(grid, [w['coords'] for w in osm['waterways']], width=1)
    sea = (~land) & (~city_mask)
    coast = sea | draw_lines(grid, osm['coastline'], width=1)
    drainage = water_lines | dem_streams | coast

    _, (ri, ci) = ndimage.distance_transform_edt(~drainage, return_indices=True)
    hand = np.clip(filled - filled[ri, ci], 0, None).astype(np.float32)

    log('  Roads, buildings, land use and fire stations...')
    roads = draw_lines(grid, osm['roads'], width=1)
    main_roads = draw_lines(grid, osm['main_roads'], width=2)
    counts = count_points(grid, osm['buildings'])
    win_b = max(3, int(round(200 / res)) | 1)
    density = ndimage.uniform_filter(counts, size=win_b) * 1e4 / (res * res)  # buildings per hectare
    landuse = draw_polygons(grid, sorted(osm['landuse'], key=lambda p: p[0])).astype(np.float32)
    landuse[landuse == 0] = 1
    station_dist = distance_to_points(grid, osm['fire_stations'])

    return {
        'elevation': np.clip(dem, 0, None),
        'slope': slope,
        'relief': relief,
        'hand': hand,
        'dist_water': distance_to(water_lines | dem_streams, res),
        'dist_coast': distance_to(coast, res),
        'dist_road': distance_to(roads, res),
        'dist_main_road': distance_to(main_roads, res),
        'building_density': density.astype(np.float32),
        'urban_landuse': landuse,
        'dist_fire_station': station_dist,
    }


def build_layers(factors, city_mask):
    layers = {hazard: classify(factors, hazard) for hazard in FACTORS}
    # Flat ground does not slide; empty land has little to burn
    layers['landslide'][factors['slope'] < FLAT_SLOPE_DEG] = 1
    empty = (factors['building_density'] < 0.5) & (factors['urban_landuse'] <= 1)
    layers['fire'][empty] = 1
    layers['all'] = np.maximum.reduce([layers['flood'], layers['landslide'], layers['fire']])
    for arr in layers.values():
        arr[~city_mask] = 0
    return layers


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def _rgb(hex_color):
    n = int(hex_color[1:], 16)
    return (n >> 16) & 255, (n >> 8) & 255, n & 255


def write_png(path, classes):
    lut = np.zeros((6, 4), np.uint8)
    for i, c in enumerate(CLASSES, start=1):
        lut[i] = (*_rgb(c['color']), 255)
    Image.fromarray(lut[classes], 'RGBA').save(path, optimize=True)


def barangay_stats(labels, layers, names):
    stats = {}
    for bid, name in names.items():
        inside = labels == bid
        total = int(inside.sum())
        if not total:
            continue
        entry = {'name': name}
        for hazard in ('flood', 'landslide', 'fire'):
            counts = np.bincount(layers[hazard][inside], minlength=6)[1:6]
            entry[hazard] = [round(100 * int(n) / total, 1) for n in counts]
        stats[str(bid)] = entry
    return stats


def rivers_geojson(osm):
    features = []
    for w in osm['waterways']:
        if w['kind'] not in DRAWN_WATERWAYS:
            continue
        features.append({
            'type': 'Feature',
            'properties': {'kind': w['kind'], 'name': w['name']},
            'geometry': {'type': 'LineString', 'coordinates': [[round(x, 6), round(y, 6)] for x, y in w['coords']]},
        })
    return {'type': 'FeatureCollection', 'features': features}


def build(barangay_polygons, barangay_names, extent, out_dir, zoom=14, pad_m=500, log=print,
          dem=None, osm=None, cache_dir=None, refresh=False):
    """
    barangay_polygons  list of (barangay_id, [outer_ring, hole, ...]) with (lng, lat) coords
    barangay_names     {barangay_id: name}
    extent             (west, south, east, north) of all barangays
    dem, osm           optional pre-loaded data (used by tests); downloaded when None
    cache_dir          keeps downloads here so a rerun skips them (refresh=True downloads again)
    """
    west, south, east, north = extent
    dlat = pad_m / 111320
    dlng = dlat / math.cos(math.radians((south + north) / 2))
    south, west, north, east = south - dlat, west - dlng, north + dlat, east + dlng
    grid = Grid(south, west, north, east, zoom)
    log(f'Grid: {grid.width} x {grid.height} cells, {grid.res:.1f} m each')

    session = make_session()
    cache = Path(cache_dir) if cache_dir else None
    if cache:
        cache.mkdir(parents=True, exist_ok=True)
    tag = f'z{zoom}_{grid.px0}_{grid.py0}_{grid.width}x{grid.height}'

    if dem is None:
        dem_file = cache / f'dem_{tag}.npy' if cache else None
        if dem_file and dem_file.exists() and not refresh:
            log('  Using saved elevation data')
            dem = np.load(dem_file)
        else:
            dem = fetch_dem(grid, session, log)
            if dem_file:
                np.save(dem_file, dem)
    if osm is None:
        osm_file = cache / f'osm_{tag}.json' if cache else None
        if osm_file and osm_file.exists() and not refresh:
            log('  Using saved OpenStreetMap data')
            osm = json.loads(osm_file.read_text())
            if not osm['fire_stations']:  # skipped last time; try once more
                osm['fire_stations'] = fetch_fire_stations(south, west, north, east, session, log)
                osm_file.write_text(json.dumps(osm))
        else:
            osm = fetch_osm(south, west, north, east, session, log)
            if osm_file:
                osm_file.write_text(json.dumps(osm))
    log(f"  OSM: {len(osm['waterways'])} waterways, {len(osm['roads'])} roads, "
        f"{len(osm['buildings'])} buildings, {len(osm['landuse'])} land-use areas, "
        f"{len(osm['fire_stations'])} fire stations")
    if len(osm['buildings']) < 1000:
        log('  Warning: few buildings are mapped in OpenStreetMap here, so the fire layer leans on land use and roads.')
    if not osm['fire_stations']:
        log('  Warning: no fire stations found; response distance is treated as average everywhere.')

    labels = draw_polygons(grid, barangay_polygons)
    city_mask = labels > 0

    factors = compute_factors(grid, dem, osm, city_mask, log)
    layers = build_layers(factors, city_mask)

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    files = {}
    for name, arr in layers.items():
        write_png(out_dir / f'{name}.png', arr)
        files[name] = f'{name}.png'
    (out_dir / 'rivers.geojson').write_text(json.dumps(rivers_geojson(osm), separators=(',', ':')))

    index = {
        'generated': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'bounds': grid.bounds(),
        'cellSizeM': round(grid.res, 1),
        'classes': CLASSES,
        'layers': files,
        'rivers': 'rivers.geojson',
        'method': 'Weighted overlay of reclassified factors, five equal-interval classes',
        'factors': {h: [{'factor': f, 'breaks': b, 'direction': d, 'weight': w} for f, b, d, w in fs]
                    for h, fs in FACTORS.items()},
        'sources': [
            'Elevation: AWS Terrain Tiles (SRTM, ~30 m)',
            'Rivers, coastline, roads, buildings, land use, fire stations: (c) OpenStreetMap contributors',
        ],
        'osmCounts': {k: len(v) for k, v in osm.items()},
        'barangays': barangay_stats(labels, layers, barangay_names),
    }
    (out_dir / 'index.json').write_text(json.dumps(index, indent=1))
    log(f'Wrote {len(files)} layers to {out_dir}')
    return index