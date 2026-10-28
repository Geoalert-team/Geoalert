"""
Estimated purok outlines, until the Barangay Hall sends official ones.

No purok or sitio boundaries are published for Talisay, so the map draws
estimates (design: docs/superpowers/specs/2026-10-23-purok-boundaries-design.md).
A barangay is split into as many areas as it has puroks. Each purok whose
place was found (data/puroks/purok_points.csv) starts there, from its whole
outline if Wikimapia or OSM has one; puroks nobody could place start at the
centres of the house clusters left over and are named after a landmark
there ("Near Tapul Elementary School") until their name is found. Every area grows
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
import unicodedata
from collections import namedtuple
from ctypes import POINTER, c_uint

import numpy as np
from scipy import ndimage
from django.contrib.gis.geos import GEOSGeometry, LineString, MultiLineString, MultiPolygon, Point, Polygon
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
    Accents go too: the BFP types "Tres Aliños" where other sources have
    "Tres Alinos".
    """
    plain = ''.join(c for c in unicodedata.normalize('NFKD', name) if not unicodedata.combining(c))
    words = re.findall(r'[a-z0-9]+', plain.lower())
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


Node = namedtuple('Node', 'row children')


def _placed(row):
    return bool(str(row.get('lat') or '').strip() and str(row.get('lng') or '').strip())


def name_tree(rows):
    """
    (top-level names as Nodes, how many puroks the names stand for).

    rows are one barangay's researched names (purok_points.csv); a name needs
    a lat/lng to get an area. A placed name sits under its parent when the
    parent is placed too ("Purok Sambag, Sitio Laray"): on the ground a sitio
    holds its puroks. Under an unplaced parent it stands alone, its label
    still naming the sitio. The count is every name that is nobody's parent,
    placed or not, since each is a purok on the ground.
    """
    placed = [r for r in rows if _placed(r)]
    nodes = {r['name']: Node(r, []) for r in placed}
    top = []
    for r in placed:
        parent = nodes.get(r.get('parent') or '')
        if parent is not None and parent.row is not r:
            parent.children.append(nodes[r['name']])
        else:
            top.append(nodes[r['name']])
    # A loop of parents (a typo in the research) would hide its names: they stand alone instead
    reached = set()

    def walk(node):
        if id(node) not in reached:
            reached.add(id(node))
            for child in node.children:
                walk(child)
    for node in top:
        walk(node)
    for r in placed:
        if id(nodes[r['name']]) not in reached:
            top.append(nodes[r['name']])
            walk(nodes[r['name']])
    parents = {r['parent'] for r in rows if r.get('parent')}
    return top, sum(1 for r in rows if r['name'] not in parents)


def pull_inside(lng, lat, outline):
    """
    The point if outline holds it; otherwise the nearest point about 5 m
    inside the outline. A purok placed only roughly (outage notices) whose
    sitio has a drawn outline belongs in the outline.
    """
    point = Point(lng, lat, srid=4326)
    if outline.contains(point):
        return lng, lat
    inner = outline.buffer(-0.00005)
    target = inner if not inner.empty and inner.area > 0 else outline
    edge = target.boundary
    try:
        near = edge.interpolate(edge.project(point))
    except Exception:  # GEOS can't project onto this edge: any point inside will do
        near = target.point_on_surface
    return near.x, near.y


def _subtree(node):
    yield node.row
    for child in node.children:
        yield from _subtree(child)


def _split_level(mask, houses, step, n, groups, to_cell, preset_for, barrier, dem, loose_reach, min_cells):
    """
    One split_named over every name in groups (a list of row lists), each name
    its own seed, then each seed handed to its group. Returns (labels, number
    of unnamed areas): 0 .. len(groups) - 1 the groups, then the unnamed.
    """
    rows = [(row, g) for g, members in enumerate(groups) for row in members]
    preset = None
    for i, (row, _) in enumerate(rows):
        cells = preset_for(row)
        if cells is not None:
            if preset is None:
                preset = np.full(mask.shape, -1, np.int32)
            preset[cells & mask] = i  # parents come first, so a purok's own outline wins inside its sitio's
    owner = split_named(mask, houses, step, n, [to_cell(r) for r, _ in rows], preset=preset, barrier=barrier,
                        dem=dem, loose=[r.get('confidence') == 'low' for r, _ in rows], loose_reach=loose_reach)
    labels = np.full(owner.shape, -1, np.int32)
    lookup = np.asarray([g for _, g in rows] + list(range(len(groups), len(groups) + n)), np.int32)
    labels[owner >= 0] = lookup[owner[owner >= 0]]
    labels[~mask] = -1
    return tidy(labels, mask, min_cells=min_cells), max(n - len(rows), 0)


def split_nested(inside, houses, step, n, top, to_cell, preset_for, barrier=None, dem=None,
                 loose_reach=math.inf, min_cells=0):
    """
    Split one barangay as it is on the ground: sitios first, then each sitio
    among its puroks. (named, unnamed): named is [(row, mask, members)] for
    every placed name, parents before their puroks, members how many puroks
    it holds; a sitio's mask is its whole territory. unnamed are the masks of
    the areas no name was found for.

    The first split takes every placed name as a seed with one share each, so
    a sitio grows from its own point and its puroks' points together, sized
    for all of them. Inside a sitio its puroks and its own point (its
    leftover) split the territory again, sized by the houses there.

    to_cell(row) gives a name's cell, preset_for(row) the cells of its drawn
    outline (or None).
    """
    named = []
    level, extra = _split_level(inside, houses, step, max(n, sum(1 for t in top for _ in _subtree(t))),
                                [list(_subtree(t)) for t in top], to_cell, preset_for, barrier, dem,
                                loose_reach, min_cells)

    def emit(node, territory):
        named.append((node.row, territory, len(node.children)))
        if not node.children or not territory.any():
            return
        # The sitio's own point has no outline here: its outline already shaped the territory
        groups = [[node.row]] + [list(_subtree(c)) for c in node.children]
        sub, _ = _split_level(territory, houses, step, sum(len(g) for g in groups), groups, to_cell,
                              lambda row: None if row is node.row else preset_for(row), barrier, dem,
                              loose_reach, min_cells)
        for c, child in enumerate(node.children, start=1):
            emit(child, sub == c)

    for t, node in enumerate(top):
        emit(node, level == t)
    unnamed = [m for m in (level == len(top) + j for j in range(extra)) if m.any()]
    return named, unnamed


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
    # A rough name still on top of others (a notice listing many names along one road) would be
    # hemmed in to a sliver: it starts at the house in reach farthest from every other start instead
    crowd = math.sqrt(inside.sum() / n / math.pi)  # a typical area's radius
    houses_at = np.argwhere(inside & (houses > 0))
    for i in range(len(seeds)):
        if not loose[i] or i in moved or not len(houses_at):
            continue
        others = np.asarray([s for j, s in enumerate(starts) if j != i] + centres, dtype=np.float64)
        if not len(others):
            continue

        def room(cells):
            return np.sqrt(((cells[:, None, :] - others[None, :, :]) ** 2).sum(2)).min(1)

        here = room(np.asarray([starts[i]], dtype=np.float64))[0]
        if here >= crowd:
            continue
        near = houses_at[np.hypot(houses_at[:, 0] - seeds[i][0], houses_at[:, 1] - seeds[i][1]) <= loose_reach]
        if len(near):
            space = room(near.astype(np.float64))
            if space.max() > here:
                starts[i] = tuple(int(v) for v in near[int(np.argmax(space))])
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


def _face_label(face, padded, samples=400):
    """
    The label most of a rebuilt area's cells carry (padded as in
    outline_areas). Smoothing moves a border by up to a cell or two, so a
    single point near the edge can sit on the neighbour's side and hand it the
    whole area; counting cells (every few, on big areas) settles it.
    """
    x0, y0, x1, y1 = face.extent
    rows = range(math.floor(y0), math.ceil(y1))
    cols = range(math.floor(x0), math.ceil(x1))
    stride = max(1, int(math.sqrt(len(rows) * len(cols) / samples)))
    votes = {}
    for r in rows[::stride]:
        for c in cols[::stride]:
            if face.prepared.contains(Point(c + 0.5, r + 0.5)):
                v = int(padded[r + 1, c + 1])
                votes[v] = votes.get(v, 0) + 1
    if votes:
        return max(votes, key=votes.get)
    p = face.point_on_surface  # a sliver no cell centre falls in
    return int(padded[int(math.floor(p.y)) + 1, int(math.floor(p.x)) + 1])


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
        label = _face_label(face, padded)
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


# What people give directions by, best first, and the OSM tags that make each
LANDMARKS = [
    ('school', 'amenity', ('school', 'kindergarten', 'college', 'university')),
    ('chapel', 'amenity', ('place_of_worship',)),
    ('hall', 'amenity', ('townhall', 'community_centre', 'fire_station', 'police')),
    ('health', 'amenity', ('hospital', 'clinic', 'health_post')),
    ('market', 'amenity', ('marketplace',)),
    ('court', 'leisure', ('pitch', 'sports_hall', 'sports_centre', 'park', 'playground')),
    ('cemetery', 'landuse', ('cemetery',)),
]
# Also asked for, only to place fire addresses that name them ("Mananga Bridge II", "South Town Centre");
# they don't name areas, since a bridge or a mall isn't how a purok is told apart
LINK_PLACES = [
    ('bridge', 'bridge', ('yes',)),
    ('mall', 'shop', ('mall', 'department_store', 'supermarket')),
]
BARANGAY_HALL = re.compile(r'barangay hall|bulwagang|bahay pamahalaan', re.IGNORECASE)
STREET_TYPES = ('trunk', 'primary', 'secondary', 'tertiary', 'unclassified', 'residential', 'living_street')
RIVER_TYPES = ('river', 'stream', 'canal')
# Names that say what a thing is but not which one
GENERIC_NAMES = {'basketball court', 'covered court', 'court', 'chapel', 'church', 'school', 'park',
                 'playground', 'gym', 'cemetery', 'barangay hall', 'health center', 'day care center'}
MIN_STREET_M = 50  # an area must hold this much of a street to be named along it
STREET_SHARE = 0.75  # a fire on a street links to an area only when the area holds this much of the street
# "Along Purok Siba Street" would read as the purok's own name
NAMES_A_PUROK = re.compile(r'\b(purok|sitio|zone)\b', re.IGNORECASE)
MAX_NAME = 100  # Purok.name's length
COMPASS = ['east', 'northeast', 'north', 'northwest', 'west', 'southwest', 'south', 'southeast']


def landmark_query(south, west, north, east):
    """The Overpass query whose answer landmarks_from_osm reads."""
    bbox = f'{south},{west},{north},{east}'
    places = ''.join(f'  nwr["name"]["{key}"~"^({"|".join(values)})$"]({bbox});\n'
                     for _, key, values in LANDMARKS + LINK_PLACES)
    return (f'[out:json][timeout:240];\n(\n{places});\nout tags center;\n(\n'
            f'  way["name"]["highway"~"^({"|".join(STREET_TYPES)})$"]({bbox});\n'
            f'  way["name"]["waterway"~"^({"|".join(RIVER_TYPES)})$"]({bbox});\n);\nout tags geom;\n')


def landmarks_from_osm(elements):
    """
    (points, lines) from an Overpass answer: points are (name, kind, lng, lat)
    for the schools, chapels, halls and such in LANDMARKS; lines are
    (name, LineString) for named streets and rivers.
    """
    kinds = {(key, value): kind for kind, key, values in LANDMARKS + LINK_PLACES for value in values}
    points, lines = [], []
    for el in elements:
        tags = el.get('tags', {})
        # "Santo Niño Preparatory School of Mohon, Talisay City, Inc." is known by its first part
        name = tags.get('name', '').split(',')[0].strip()
        kind = next((kinds[(k, v)] for k, v in tags.items() if (k, v) in kinds), None)
        if kind == 'bridge' and 'bridge' not in name.lower():
            kind = None  # a bridge carrying a road's name is just that road
        if not name or name.lower() in GENERIC_NAMES:
            continue
        if kind:
            at = el if 'lat' in el else el.get('center')
            if at:
                points.append((name, kind, at['lon'], at['lat']))
        elif tags.get('highway') in STREET_TYPES or tags.get('waterway') in RIVER_TYPES:
            coords = [(p['lon'], p['lat']) for p in el.get('geometry') or [] if p]
            if len(coords) >= 2:
                lines.append((name, LineString(coords, srid=4326)))
    return points, lines


def _offset_m(lng0, lat0, lng1, lat1):
    """(east, north) metres from the first point to the second."""
    return ((lng1 - lng0) * METERS_PER_DEGREE * math.cos(math.radians(lat0)),
            (lat1 - lat0) * METERS_PER_DEGREE)


def _how_far(metres):
    rounded = max(100, round(metres, -2))
    return f'{rounded:.0f} m' if rounded < 1000 else f'{metres / 1000:.1f} km'


def area_names(areas, points, lines, taken=()):
    """
    A name for each area no researched purok was found for, from what is on
    the ground there, so a reporter can still tell them apart. A landmark
    inside it, best kind first ("Near Tapul Elementary School"); else the
    street or river it holds most of ("Along Burgos Street"), each going to
    the area holding most of it; else how far and which way it lies from the
    nearest landmark ("800 m west of Camp 4 Barangay Hall"). They describe
    where the area is; they don't claim to be the purok's name.

    areas   lng/lat shapes, in the order to name them
    points  (name, kind, lng, lat) from landmarks_from_osm
    lines   (name, LineString) from landmarks_from_osm
    taken   names already used in the barangay
    """
    rank = {kind: i for i, (kind, _, _) in enumerate(LANDMARKS)}
    points = [p for p in points if p[1] in rank]
    used = set(taken)
    names = [None] * len(areas)

    def free(name):
        return name not in used and len(name) <= MAX_NAME

    def claim(i, name):
        names[i] = name
        used.add(name)

    for i, area in enumerate(areas):
        inside = sorted((rank[kind], name) for name, kind, lng, lat in points
                        if area.prepared.contains(Point(lng, lat, srid=area.srid)))
        unused = [f'Near {name}' for _, name in inside if free(f'Near {name}')]
        if unused:
            claim(i, unused[0])

    held = {}
    for i, area in enumerate(areas):
        if names[i] is None:
            for name, line in lines:
                if not NAMES_A_PUROK.search(name) and area.prepared.intersects(line):
                    held[(i, name)] = held.get((i, name), 0.0) + area.intersection(line).length * METERS_PER_DEGREE
    for metres, i, name in sorted(((m, i, n) for (i, n), m in held.items()), reverse=True):
        if metres >= MIN_STREET_M and names[i] is None and free(f'Along {name}'):
            claim(i, f'Along {name}')

    for i, area in enumerate(areas):
        if names[i] is not None:
            continue
        p = area.point_on_surface
        for metres, name, lng, lat in sorted((math.hypot(*_offset_m(lng, lat, p.x, p.y)), name, lng, lat)
                                             for name, _, lng, lat in points):
            east, north = _offset_m(lng, lat, p.x, p.y)
            label = f'{_how_far(metres)} {COMPASS[round(math.degrees(math.atan2(north, east)) / 45) % 8]} of {name}'
            if free(label):
                claim(i, label)
                break

    # Nothing known anywhere near: numbered, as before
    k = 0
    for i in range(len(areas)):
        if names[i] is None:
            k += 1
            while f'Unnamed area {k}' in used:
                k += 1
            claim(i, f'Unnamed area {k}')
    return names


def place_areas(leaves, containers, points, lines):
    """
    Where a fire address that names a landmark or a street lies, for
    linking it: [{'place', 'kind', 'area', 'share'}].

    leaves      [(name, shape)]: the areas that hold no others
    containers  [(name, shape)]: sitios drawn around their puroks
    points      (name, kind, lng, lat) from landmarks_from_osm
    lines       (name, LineString) from landmarks_from_osm

    A landmark goes to the leaf it stands in, or the sitio when it stands in
    a sitio's own part. A barangay hall is also "Barangay Hall", as fire
    addresses write it. A name two landmarks share says nothing, so it gets
    no row. A street goes to the leaf holding the most of its length in the
    barangay, or to a sitio when no leaf holds STREET_SHARE but a sitio does;
    share says how much. Streets named after a purok are left out.
    """
    shapes = leaves + containers
    if not shapes:
        return []
    cover = shapes[0][1]
    for _, shape in shapes[1:]:
        cover = cover.union(shape)

    def where(lng, lat):
        p = Point(lng, lat, srid=4326)
        return next((name for name, shape in shapes if shape.contains(p)), None)

    found = {}
    for name, kind, lng, lat in points:
        if not cover.prepared.contains(Point(lng, lat, srid=4326)):
            continue
        area = where(lng, lat)
        found.setdefault(name, []).append(area)
        if kind == 'hall' and BARANGAY_HALL.search(name):
            found.setdefault('Barangay Hall', []).append(area)
    rows = [{'place': place, 'kind': 'landmark', 'area': areas[0], 'share': 1.0}
            for place, areas in found.items() if len(areas) == 1 and areas[0]]

    streets = {}
    for name, line in lines:
        if not NAMES_A_PUROK.search(name) and cover.prepared.intersects(line):
            streets.setdefault(name, []).append(line)
    for name, pieces in streets.items():
        total = sum(cover.intersection(p).length for p in pieces)
        if not total:
            continue

        def best(group):
            held = [(sum(shape.intersection(p).length for p in pieces) / total, area) for area, shape in group]
            return max(held, default=(0.0, None))

        share, area = best(leaves)
        if share < STREET_SHARE and containers:
            outer = best(containers)
            if outer[0] >= STREET_SHARE:
                share, area = outer
        if area:
            rows.append({'place': name, 'kind': 'street', 'area': area, 'share': round(share, 3)})
    return rows
