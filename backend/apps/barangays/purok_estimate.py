"""
Estimated purok outlines, until the Barangay Hall sends official ones.

No purok or sitio boundaries are published for Talisay, so the map draws
estimates (design: docs/superpowers/specs/2026-10-23-purok-boundaries-design.md).
A barangay is split into as many areas as it has puroks. Each purok whose
place was found (data/puroks/purok_points.csv) starts there, from its whole
outline if Wikimapia or OSM has one; puroks nobody could place start at the
centres of the house clusters left over and stay unnamed. Every area grows
across the hazard map's grid. Growing is cheap through houses and small
streets and expensive across main roads, creeks and ridges, so the borders
between areas settle on them, as real purok borders tend to. Each area stops
once it holds its share of the barangay's houses, so dense puroks come out
small and upland ones large; the empty ground left over then goes to the
nearest area, so the whole barangay is split.

Everything here is plain functions on arrays and GEOS shapes, so it tests
without the database or any download.
"""
import heapq
import json
import math
import re
from ctypes import POINTER, c_uint

import numpy as np
from scipy import ndimage
from django.contrib.gis.geos import GEOSGeometry, LineString, MultiLineString, MultiPolygon, Polygon
from django.contrib.gis.geos.libgeos import GEOM_PTR
from django.contrib.gis.geos.prototypes.geom import GeomOutput

# Starting values, to be tuned against the first official barangay that
# arrives (load_puroks prints how far the estimates were from it).
EMPTY_FACTOR = 2.0           # crossing ground with no house nearby costs this much more
HOUSE_NEAR_M = 50            # "near a house" for the line above
MAIN_ROAD_PENALTY_M = 150    # crossing a main road: like walking this much further
WATER_PENALTY_M = 200        # crossing a river, creek or drain
CLIMB_M_PER_M = 10           # each metre climbed: like walking this much further
CAP_FACTOR = 1.5             # a purok reaches at most this many times its typical radius
MIN_PIECE_HA = 0.1           # smaller leftover pieces are dropped
HOUSEHOLDS_PER_PUROK = 175   # median of the city's 2010 profiles (2015 households)
LOOSE_REACH_M = 500          # a name placed only roughly may start this far from its point

ROMAN = {'i': '1', 'ii': '2', 'iii': '3', 'iv': '4', 'v': '5',
         'vi': '6', 'vii': '7', 'viii': '8', 'ix': '9', 'x': '10'}

NEIGHBORS = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]
METERS_PER_DEGREE = 111_320


def norm_name(name):
    """
    A key for matching the same place across sources: 'Purok Ilang-Ilang' and
    'ilang ilang' match, so do Kamunggay and Kamungay. 'Zone 3' keeps its word,
    since a zone and a purok with the same number are different places.
    """
    words = re.findall(r'[a-z0-9]+', name.lower())
    while words and words[0] in ('purok', 'sitio', 'so', 'prk'):
        words = words[1:]
    words = [ROMAN.get(w, w) for w in words]
    return re.sub(r'([a-z])\1+', r'\1', ''.join(words))


def purok_count(official, households, names):
    """
    (N, basis): how many puroks the barangay has. The official sitio count
    where the city's profile gives one, otherwise households / 175; never
    fewer than the names actually found, since each of those is a real place.
    """
    if official:
        base, basis = official, 'official'
    else:
        base, basis = max(1, round(households / HOUSEHOLDS_PER_PUROK)), 'households'
    if names > base:
        return names, 'names'
    return base, basis


def _snap(blocked, r, c):
    """
    The free cell nearest (r, c): a point drawn on the barangay line, inside
    another name's outline or on another point still gets a start of its own.
    """
    if not blocked[r, c]:
        return r, c
    if blocked.all():
        return None
    _, (ri, ci) = ndimage.distance_transform_edt(blocked, return_indices=True)
    return int(ri[r, c]), int(ci[r, c])


def _move_cost(step, barrier, dem, r, c, nr, nc):
    """Metres it costs to step from cell (r, c) to its neighbour (nr, nc)."""
    cost = step[nr, nc] * (math.sqrt(2) if nr != r and nc != c else 1.0)
    if barrier is not None:
        cost += max(0.0, barrier[nr, nc] - barrier[r, c])
    if dem is not None:
        cost += CLIMB_M_PER_M * max(0.0, dem[nr, nc] - dem[r, c])
    return cost


def grow(inside, step, houses, seeds, quotas, caps, barrier=None, dem=None, preset=None):
    """
    Grow every seed at once across the grid (multi-source Dijkstra); each cell
    goes to the seed that reaches it most cheaply.

    inside   bool array: the barangay
    step     metres it costs to cross each cell (diagonals x sqrt 2)
    houses   houses in each cell
    seeds    [(row, col)]
    quotas   houses each seed may hold before it stops
    caps     furthest each seed may reach, in cells, as the crow flies
    barrier  metres added on stepping onto a cell with a higher barrier than
             the one left: crossing a road or creek costs once, following it doesn't
    dem      ground height in metres; climbing costs CLIMB_M_PER_M per metre
    preset   int array: cells a seed holds from the start (its outline drawn on
             Wikimapia or OSM), -1 elsewhere. They count towards its share, it
             grows outward from all of them, and no other seed enters them.

    Returns an int array: the seed index owning each cell, -1 for nobody.
    """
    h, w = inside.shape
    owner = np.full((h, w), -1, dtype=np.int32)
    claimed = [0.0] * len(seeds)
    heap = []
    if preset is not None:
        fixed = inside & (preset >= 0)
        owner[fixed] = preset[fixed]
        for i in range(len(seeds)):
            claimed[i] = float(houses[owner == i].sum())
        heap += [(0.0, int(owner[r, c]), int(r), int(c)) for r, c in zip(*np.nonzero(fixed))]
    # Where a seed can't start: outside, someone's outline, another seed's start
    taken = ~inside | (owner >= 0)
    origin = []
    for i, (r, c) in enumerate(seeds):
        r, c = min(max(int(r), 0), h - 1), min(max(int(c), 0), w - 1)
        if owner[r, c] == i:  # inside its own outline, which already started it
            origin.append((r, c))
            continue
        snapped = _snap(taken, r, c)
        if snapped is None:
            origin.append(None)
            continue
        r, c = snapped
        origin.append((r, c))
        taken[r, c] = True
        heap.append((0.0, i, r, c))
    heapq.heapify(heap)

    while heap:
        d, i, r, c = heapq.heappop(heap)
        if owner[r, c] == -1:
            r0, c0 = origin[i]
            if claimed[i] >= quotas[i] or math.hypot(r - r0, c - c0) > caps[i]:
                continue
            owner[r, c] = i
            claimed[i] += houses[r, c]
        elif owner[r, c] != i or d > 0:
            continue  # someone else's, or reached again: only an outline cell starts from here
        for dr, dc in NEIGHBORS:
            nr, nc = r + dr, c + dc
            if not (0 <= nr < h and 0 <= nc < w) or not inside[nr, nc] or owner[nr, nc] != -1:
                continue
            heapq.heappush(heap, (d + _move_cost(step, barrier, dem, r, c, nr, nc), i, nr, nc))
    return owner


def seed_points(cells, weights, k, iterations=25):
    """
    k starting points for a barangay's puroks: the centres of its k house
    clusters (weighted k-means, farthest-point start so it's repeatable),
    each moved onto the nearest given cell so a purok starts where people live.
    cells are (row, col); weights are the houses in each.
    """
    pts = np.asarray(cells, dtype=np.float64)
    w = np.asarray(weights, dtype=np.float64)
    k = min(k, len(pts))
    if k == 0:
        return []
    mean = (pts * w[:, None]).sum(0) / w.sum()
    chosen = [int(np.argmin(((pts - mean) ** 2).sum(1)))]
    nearest = ((pts - pts[chosen[0]]) ** 2).sum(1)
    while len(chosen) < k:
        nxt = int(np.argmax(nearest))
        chosen.append(nxt)
        nearest = np.minimum(nearest, ((pts - pts[nxt]) ** 2).sum(1))
    centers = pts[chosen].copy()
    for _ in range(iterations):
        label = np.argmin(((pts[:, None, :] - centers[None, :, :]) ** 2).sum(2), axis=1)
        moved = centers.copy()
        for j in range(k):
            m = label == j
            if m.any():
                moved[j] = (pts[m] * w[m, None]).sum(0) / w[m].sum()
        if np.allclose(moved, centers):
            break
        centers = moved
    seeds, used = [], set()
    for c in centers:
        order = np.argsort(((pts - c) ** 2).sum(1), kind='stable')
        pick = next(int(i) for i in order if int(i) not in used)
        used.add(pick)
        seeds.append((int(pts[pick][0]), int(pts[pick][1])))
    return seeds


def fill_gaps(owner, inside, step, barrier=None, dem=None):
    """
    Give every cell of the barangay that no purok claimed (empty ground past
    the house shares) to the purok that reaches it most cheaply, with the same
    crossing costs as grow(), so the barangay ends up fully split and the
    borders through empty ground still follow creeks and ridges.
    """
    h, w = owner.shape
    out = owner.copy()
    open_cell = inside & (owner == -1)
    best = np.full((h, w), np.inf)
    heap = []
    for r, c in zip(*np.nonzero(owner >= 0)):
        best[r, c] = 0.0
        heap.append((0.0, int(owner[r, c]), int(r), int(c)))
    heapq.heapify(heap)
    while heap:
        d, o, r, c = heapq.heappop(heap)
        if d > best[r, c]:
            continue
        if out[r, c] == -1:
            out[r, c] = o
        for dr, dc in NEIGHBORS:
            nr, nc = r + dr, c + dc
            if not (0 <= nr < h and 0 <= nc < w) or not open_cell[nr, nc]:
                continue
            cost = _move_cost(step, barrier, dem, r, c, nr, nc)
            if d + cost < best[nr, nc]:
                best[nr, nc] = d + cost
                heapq.heappush(heap, (d + cost, o, nr, nc))
    return out


def area_points(rows):
    """
    (names that get an area of their own, how many puroks the names stand for).

    rows are one barangay's researched names (purok_points.csv); a name needs
    a lat/lng to get an area. A sitio whose purok was placed gives way to it,
    and the purok's label carries the sitio's name instead ("Purok Sambag ·
    Sitio Laray"). The count is every name that is nobody's parent, placed or
    not, since each is a purok on the ground.
    """
    placed = [r for r in rows if str(r.get('lat') or '').strip() and str(r.get('lng') or '').strip()]
    has_placed_child = {r['parent'] for r in placed if r.get('parent')}
    parents = {r['parent'] for r in rows if r.get('parent')}
    points = [r for r in placed if r['name'] not in has_placed_child]
    return points, sum(1 for r in rows if r['name'] not in parents)


def split_named(inside, houses, step, n, seeds, preset=None, barrier=None, dem=None, loose=None, loose_reach=math.inf):
    """
    Split one barangay into n areas. The first ones grow from where researched
    names were found (seeds, in order; preset holds the outlines drawn for
    them). The puroks nobody placed still need room, so the rest start at the
    centres of the house clusters no name sits in. Each area grows to its
    share of the houses, then the empty ground left over goes to the nearest
    area. Returns the area index of every cell, -1 outside the barangay:
    0 .. len(seeds) - 1 are the names, the rest unnamed.

    loose marks names whose point is only roughly right: outage notices put
    every name they list somewhere along one road, often on top of each
    other. Those start at the free house cluster nearest their point instead
    (within loose_reach cells), so names listed together end up side by side
    rather than squeezed into slivers.
    """
    n = max(n, len(seeds))
    loose = loose or [False] * len(seeds)
    rows, cols = np.nonzero(inside & (houses > 0))
    if len(rows) >= n:
        weights = houses[rows, cols]
    else:  # hardly any houses known: spread the starts over the whole barangay
        rows, cols = np.nonzero(inside)
        weights = np.ones(len(rows))
    centres = seed_points(list(zip(rows.tolist(), cols.tolist())), weights.tolist(), n)

    def dist(a, b):
        return math.hypot(a[0] - b[0], a[1] - b[1])

    def take_nearest(point):
        if centres:
            centres.pop(min(range(len(centres)), key=lambda j: dist(centres[j], point)))

    # Each name found exactly stands for the house cluster nearest it
    for seed, rough in zip(seeds, loose):
        if not rough:
            take_nearest(seed)
    # Rough ones move onto a free cluster, closest pairs first
    starts = list(seeds)
    pairs = sorted((dist(seeds[i], c), i, c) for i in range(len(seeds)) if loose[i] for c in centres)
    moved = set()
    for d, i, c in pairs:
        if d <= loose_reach and i not in moved and c in centres:
            starts[i] = c
            centres.remove(c)
            moved.add(i)
    for i in range(len(seeds)):
        if loose[i] and i not in moved:  # no free cluster near: keep its point
            take_nearest(seeds[i])
    # The clusters left over start the unnamed areas
    seeds = starts + centres
    k = len(seeds)
    total = float(houses[inside].sum())
    quota = total / n if total > 0 else math.inf
    cap = CAP_FACTOR * math.sqrt(inside.sum() / n / math.pi)
    owner = grow(inside, step, houses, seeds, [quota] * k, [cap] * k, barrier=barrier, dem=dem, preset=preset)
    owner = fill_gaps(owner, inside, step, barrier=barrier, dem=dem)
    # A detached piece (an islet, or ground cut off by the grid) that no area
    # could walk to goes to the nearest area as the crow flies
    missing = inside & (owner < 0)
    if missing.any() and (owner >= 0).any():
        _, (ri, ci) = ndimage.distance_transform_edt(owner < 0, return_indices=True)
        owner[missing] = owner[ri[missing], ci[missing]]
    return owner


def tidy(owner, inside, min_cells, passes=2):
    """
    Clean up what growing leaves behind. A creek is expensive to step onto,
    so whichever area reaches it first can keep a 1-cell strip of it inside
    its neighbour, or a few cells cut off on the far side. A majority filter
    hands lone strips to the area around them, then any cut-off bit smaller
    than min_cells joins the area it sits in.
    """
    out = owner.copy()
    labels = [int(v) for v in np.unique(out[inside]) if v >= 0]
    if len(labels) < 2:
        return out
    kernel = np.ones((3, 3))
    kernel[1, 1] = 0
    for _ in range(passes):
        counts = np.stack([ndimage.convolve((out == v).astype(np.int16), kernel, mode='constant') for v in labels])
        best = np.asarray(labels)[counts.argmax(0)]
        flip = inside & (counts.max(0) >= 5) & (best != out)
        out[flip] = best[flip]

    for v in labels:
        parts, n = ndimage.label((out == v) & inside, structure=np.ones((3, 3)))
        if n < 2:
            continue
        sizes = ndimage.sum(np.ones_like(parts), parts, index=range(1, n + 1))
        keep = int(np.argmax(sizes)) + 1
        for p in range(1, n + 1):
            if p == keep or sizes[p - 1] >= min_cells:
                continue
            piece = parts == p
            ring = ndimage.binary_dilation(piece, structure=np.ones((3, 3))) & ~piece & inside
            around = out[ring]
            around = around[(around >= 0) & (around != v)]
            if around.size:
                out[piece] = np.bincount(around).argmax()
    return out


def extend(owner, cells=2):
    """
    Push each area a few cells past the barangay edge. The grid only roughly
    follows the barangay line, so the outlines are drawn a little too big and
    then cut along the real line, which makes their outer edge match it exactly.
    """
    if not (owner >= 0).any():
        return owner.copy()
    dist, (ri, ci) = ndimage.distance_transform_edt(owner < 0, return_indices=True)
    out = owner.copy()
    near = (owner < 0) & (dist <= cells)
    out[near] = owner[ri[near], ci[near]]
    return out


def building_centres(lines, bbox):
    """
    Centres of the building footprints in a Microsoft Global ML Building
    Footprints file (one GeoJSON feature per line) that fall in
    bbox = (south, west, north, east).
    """
    south, west, north, east = bbox
    out = []
    for line in lines:
        ring = json.loads(line)['geometry']['coordinates'][0]
        pts = ring[:-1] if ring[0] == ring[-1] else ring
        x = sum(p[0] for p in pts) / len(pts)
        y = sum(p[1] for p in pts) / len(pts)
        if west <= x <= east and south <= y <= north:
            out.append((x, y))
    return out


# GEOS can rebuild areas from a set of lines (polygonize); Django doesn't
# wrap that call, but its GEOS library has it.
_polygonize = GeomOutput('GEOSPolygonize', argtypes=[POINTER(GEOM_PTR), c_uint])


def _chaikin(coords, closed, iterations):
    """Round off corners by cutting each one; an open line keeps its two ends."""
    pts = coords[:-1] if closed else coords
    for _ in range(iterations):
        out = [] if closed else [pts[0]]
        pairs = zip(pts, pts[1:] + pts[:1]) if closed else zip(pts, pts[1:])
        for (x0, y0), (x1, y1) in pairs:
            out += [(0.75 * x0 + 0.25 * x1, 0.75 * y0 + 0.25 * y1), (0.25 * x0 + 0.75 * x1, 0.25 * y0 + 0.75 * y1)]
        if not closed:
            out.append(pts[-1])
        pts = out
    return pts + pts[:1] if closed else pts


def outline_areas(labels, smooth=2, simplify=0.75):
    """
    Outlines for every labelled area of a grid (label -1 is nobody), in cell
    units: x = column, y = row. {label: Polygon or MultiPolygon}.

    Neighbouring areas must share their border exactly, or the map shows
    doubled lines. So the borders are drawn once: every cell edge where the
    label changes is merged into border lines, each line is straightened and
    rounded off once, and the areas are rebuilt from those lines.
    """
    padded = np.pad(labels, 1, constant_values=-1)
    segments = []
    rows, cols = np.nonzero(padded[:, :-1] != padded[:, 1:])
    segments += [((c, r - 1), (c, r)) for r, c in zip(rows.tolist(), cols.tolist())]
    rows, cols = np.nonzero(padded[:-1, :] != padded[1:, :])
    segments += [((c - 1, r), (c, r)) for r, c in zip(rows.tolist(), cols.tolist())]
    if not segments:
        return {}
    merged = MultiLineString(*[LineString(a, b) for a, b in segments]).unary_union.merged
    lines = list(merged) if merged.geom_type == 'MultiLineString' else [merged]

    smoothed = []
    for line in lines:
        # Straighten the grid's stair-steps first, then round off the corners left
        coords = list(line.simplify(simplify, preserve_topology=True).coords)
        closed = coords[0] == coords[-1]
        if closed and len(coords) < 4:
            continue
        # ...and drop the points rounding left in straight rows (they only add download size)
        smoothed.append(LineString(_chaikin(coords, closed, smooth)).simplify(0.1, preserve_topology=True))
    noded = MultiLineString(*smoothed).unary_union
    parts = list(noded) if noded.geom_type == 'MultiLineString' else [noded]
    faces = GEOSGeometry(_polygonize((GEOM_PTR * len(parts))(*[p.ptr for p in parts]), len(parts)))

    by_label = {}
    for face in faces:
        p = face.point_on_surface
        label = int(padded[int(math.floor(p.y)) + 1, int(math.floor(p.x)) + 1])
        if label >= 0:
            by_label.setdefault(label, []).append(face)
    return {label: (fs[0] if len(fs) == 1 else MultiPolygon(*fs).unary_union) for label, fs in by_label.items()}


def to_map(geom, to_lnglat):
    """A cell-unit shape in map coordinates: to_lnglat(col, row) -> (lng, lat)."""
    polys = [geom] if geom.geom_type == 'Polygon' else list(geom)
    out = []
    for poly in polys:
        rings = [[to_lnglat(x, y) for x, y in ring.coords] for ring in poly]
        out.append(Polygon(*rings))
    return MultiPolygon(*out, srid=4326)


def polygons(geom):
    """The polygons in a shape, whatever kind it is (cutting can leave lines and points too)."""
    if geom.geom_type == 'Polygon':
        return [geom]
    if geom.geom_type in ('MultiPolygon', 'GeometryCollection'):
        return [p for g in geom for p in polygons(g)]
    return []


def area_m2(geom):
    """Area of a lng/lat shape in square metres, close enough at Talisay's size."""
    lat = geom.centroid.y
    return geom.area * METERS_PER_DEGREE * METERS_PER_DEGREE * math.cos(math.radians(lat))
