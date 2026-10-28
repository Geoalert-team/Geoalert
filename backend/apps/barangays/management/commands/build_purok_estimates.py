import csv
import gzip
import io
import json
from pathlib import Path

import numpy as np
from django.conf import settings
from django.contrib.gis.geos import GEOSGeometry, MultiPolygon
from django.core.management.base import BaseCommand, CommandError
from scipy import ndimage

from apps.barangays import purok_estimate as pe
from apps.barangays.aliases import canonical
from apps.barangays.models import Barangay
from apps.hazards import susceptibility as sus

DATA_DIR = Path(__file__).resolve().parents[2] / 'data' / 'puroks'
OUT_FILE = DATA_DIR / 'talisay_puroks_estimated.geojson'
# Where each researched purok/sitio name was found (hand-editable; SOURCES.md)
POINTS_FILE = DATA_DIR / 'purok_points.csv'
# Outlines drawn for some of them on Wikimapia and OpenStreetMap
OUTLINES_FILE = DATA_DIR / 'community_outlines.geojson'
# How many puroks each barangay has: official sitio counts from the City of
# Talisay Barangay Profiles (2010); elsewhere households (PSA 2015 census) / 175,
# the median households per sitio in those profiles
COUNTS_FILE = DATA_DIR / 'barangay_counts.csv'
# Written beside the outlines: the area each landmark stands in and each street mostly runs through,
# for linking fire addresses (apps/history/bfp_link.load_link_index)
PLACES_NAME = 'place_areas.csv'

# Microsoft Global ML Building Footprints (ODbL): one file per zoom-9 tile;
# 132330002 covers all of Talisay
BUILDINGS_INDEX = 'https://minedbuildings.z5.web.core.windows.net/global-buildings/dataset-links.csv'
BUILDINGS_TILE = '132330002'


def read_research(points_file=POINTS_FILE, outlines_file=OUTLINES_FILE, counts_file=COUNTS_FILE):
    """
    ({barangay: [name rows]}, {(barangay, name): outline}, {barangay: (official count, households)}),
    keyed by canonical barangay name.
    """
    points = {}
    with open(points_file, encoding='utf-8', newline='') as fh:
        for row in csv.DictReader(fh):
            points.setdefault(canonical(row['barangay']), []).append(row)
    outlines = {}
    for f in json.loads(Path(outlines_file).read_text(encoding='utf-8'))['features']:
        p = f['properties']
        outlines[(canonical(p['barangay']), p['name'])] = GEOSGeometry(json.dumps(f['geometry']), srid=4326)
    counts = {}
    with open(counts_file, encoding='utf-8', newline='') as fh:
        for row in csv.DictReader(fh):
            counts[canonical(row['barangay'])] = (int(row['official_sitios']) if row['official_sitios'] else None,
                                                  int(row['households_2015'] or 0))
    return points, outlines, counts


class Command(BaseCommand):
    help = ('Split every barangay into estimated purok areas along roads, creeks and ridges, sized by '
            'where its houses are, and write them as GeoJSON for load_puroks. Puroks whose place was '
            'found (data/puroks/purok_points.csv) grow from there and carry their names; the rest are '
            'named after a landmark there ("Near Tapul Elementary School"). Stand-in until the '
            "Barangay Hall's official purok lines arrive.")

    def add_arguments(self, parser):
        parser.add_argument('--out', default=str(OUT_FILE), help='GeoJSON to write.')
        parser.add_argument('--barangay', help='Only this barangay (for checking one).')
        parser.add_argument('--refresh', action='store_true',
                            help='Download elevation, OpenStreetMap and building data again.')

    def handle(self, *args, **options):
        barangays = list(Barangay.objects.exclude(boundary__isnull=True).order_by('name'))
        if not barangays:
            raise CommandError('No barangay boundaries to split. Load the barangays first.')
        wanted = [b for b in barangays
                  if not options['barangay'] or canonical(b.name) == canonical(options['barangay'])]
        if not wanted:
            raise CommandError(f'No barangay called "{options["barangay"]}".')
        log = self.stdout.write

        # The whole city's grid even for one barangay: the same grid as the
        # hazard map, so the downloads it saved are reused
        west, south, east, north = (min(b.boundary.extent[0] for b in barangays),
                                    min(b.boundary.extent[1] for b in barangays),
                                    max(b.boundary.extent[2] for b in barangays),
                                    max(b.boundary.extent[3] for b in barangays))
        grid, bbox = sus.city_grid((west, south, east, north))
        log(f'Grid: {grid.width} x {grid.height} cells, {grid.res:.1f} m each')
        cache = Path(settings.BASE_DIR) / '.hazard_cache'
        try:
            dem, osm = sus.load_inputs(grid, bbox, log, cache_dir=cache, refresh=options['refresh'])
            buildings = self.buildings(cache, bbox, options['refresh'], log)
            landmarks = self.landmarks(cache, bbox, options['refresh'], log)
        except Exception as exc:  # network problems are the usual cause
            raise CommandError(f'Download failed: {exc}') from exc
        log(f'  {len(buildings)} buildings; {len(landmarks[0])} landmarks, {len(landmarks[1])} named streets and rivers')

        try:
            research = read_research()
        except FileNotFoundError as exc:
            raise CommandError(f'Research file missing: {exc.filename}') from exc

        step, barrier, houses = self.costs(grid, dem, osm, buildings, log)
        labels = sus.draw_polygons(grid, [(i + 1, [list(r.coords) for r in poly])
                                          for i, b in enumerate(barangays) for poly in b.boundary])
        features, places = [], []
        for i, b in enumerate(barangays):
            if b in wanted:
                found, rows = self.split_one(b, labels == i + 1, grid, step, barrier, houses, dem, research,
                                             landmarks, log)
                features += found
                places += [{'barangay': b.name, **r} for r in rows]

        out = Path(options['out'])
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({'type': 'FeatureCollection', 'features': features}), encoding='utf-8')
        self.stdout.write(self.style.SUCCESS(f'Wrote {len(features)} estimated purok areas to {out}'))
        self.write_places(out.parent / PLACES_NAME, places, {canonical(b.name) for b in wanted})

    def write_places(self, path, rows, rebuilt):
        """place_areas.csv beside the outlines: rows for the barangays not rebuilt this time are kept."""
        kept = []
        if path.exists():
            with open(path, encoding='utf-8', newline='') as fh:
                kept = [r for r in csv.DictReader(fh) if canonical(r['barangay']) not in rebuilt]
        with open(path, 'w', encoding='utf-8', newline='') as fh:
            writer = csv.DictWriter(fh, fieldnames=['barangay', 'place', 'kind', 'area', 'share'], lineterminator='\n')
            writer.writeheader()
            writer.writerows(sorted(kept + rows, key=lambda r: (r['barangay'], r['kind'], r['place'])))
        self.stdout.write(f'Wrote {len(rows)} landmark and street places to {path}')

    def buildings(self, cache, bbox, refresh, log):
        """Building centres from Microsoft's footprints, saved after the first download."""
        cache.mkdir(parents=True, exist_ok=True)
        saved = cache / f'ms_buildings_{BUILDINGS_TILE}.json'
        if saved.exists() and not refresh:
            log('  Using saved building footprints')
            return [tuple(p) for p in json.loads(saved.read_text())]
        session = sus.make_session()
        log('  Downloading Microsoft building footprints (about 31 MB)...')
        index = session.get(BUILDINGS_INDEX, timeout=120)
        index.raise_for_status()
        url = next(r['Url'] for r in csv.DictReader(io.StringIO(index.text))
                   if r['Location'] == 'Philippines' and r['QuadKey'] == BUILDINGS_TILE)
        resp = session.get(url, timeout=600)
        resp.raise_for_status()
        with gzip.open(io.BytesIO(resp.content), 'rt', encoding='utf-8') as fh:
            centres = pe.building_centres(fh, bbox)
        saved.write_text(json.dumps(centres))
        return centres

    def landmarks(self, cache, bbox, refresh, log):
        """Named landmarks, streets and rivers, for naming the areas no purok was found for."""
        # v2 also holds the bridges and malls fire addresses name (pe.LINK_PLACES)
        saved = cache / 'osm_landmarks_v2.json'
        if saved.exists() and not refresh:
            log('  Using saved landmarks')
            elements = json.loads(saved.read_text(encoding='utf-8'))
        else:
            log('  Downloading landmarks and street names from OpenStreetMap...')
            elements = sus.overpass(pe.landmark_query(*bbox), sus.make_session(), log)
            saved.write_text(json.dumps(elements), encoding='utf-8')
        return pe.landmarks_from_osm(elements)

    def costs(self, grid, dem, osm, buildings, log):
        """What crossing each cell costs, and what crossing into it adds (roads, creeks)."""
        res = grid.res
        houses = sus.count_points(grid, buildings)
        near_house = sus.distance_to(houses > 0, res) <= pe.HOUSE_NEAR_M
        streets = sus.draw_lines(grid, osm['roads'], width=1)
        step = np.where(near_house | streets, res, res * pe.EMPTY_FACTOR)

        log('  Tracing creeks from the elevation data (can take a minute)...')
        smooth = ndimage.gaussian_filter(dem, sigma=1.0)
        area = sus.flow_accumulation(sus.fill_depressions(smooth), res)
        water = sus.draw_lines(grid, [w['coords'] for w in osm['waterways']], width=1)
        water |= (area >= sus.STREAM_AREA_KM2 * 1e6) & (dem > 0)
        main_roads = sus.draw_lines(grid, osm['main_roads'], width=2)
        barrier = np.maximum(main_roads * pe.MAIN_ROAD_PENALTY_M, water * pe.WATER_PENALTY_M).astype(np.float64)
        return step, barrier, houses

    def split_one(self, barangay, mask, grid, step, barrier, houses, dem, research, landmarks, log):
        rows, cols = np.nonzero(mask)
        if not len(rows):
            log(f'  {barangay.name}: too small for the grid, skipped')
            return [], []
        r0, r1 = max(rows.min() - 4, 0), min(rows.max() + 5, grid.height)
        c0, c1 = max(cols.min() - 4, 0), min(cols.max() + 5, grid.width)
        win = (slice(r0, r1), slice(c0, c1))
        inside = mask[win]

        points, outlines, counts = research
        key = canonical(barangay.name)
        names = self.pulled_inside(points.get(key, []), key, outlines)
        top, leaves = pe.name_tree(names)
        official, households = counts.get(key, (None, 0))
        n, basis = pe.purok_count(official, households, leaves)
        placed = sum(1 for r in names if r['lat'] and r['lng'])
        n = max(n, placed)

        def to_cell(row):
            col, r = grid.to_cell(float(row['lng']), float(row['lat']))
            return int(r) - r0, int(col) - c0

        # Names with an outline on Wikimapia or OSM start from all of it
        drawn = {}

        def preset_for(row):
            if (key, row['name']) not in outlines:
                return None
            if row['name'] not in drawn:
                rings = [(1, [list(ring.coords) for ring in poly]) for poly in pe.polygons(outlines[(key, row['name'])])]
                drawn[row['name']] = sus.draw_polygons(grid, rings)[win] == 1
            return drawn[row['name']]

        # Cut-off bits smaller than a tenth of a typical area (or 0.1 ha) join their surroundings
        min_cells = max(pe.MIN_PIECE_HA * 10_000 / grid.res ** 2, inside.sum() / n / 10)
        # Names placed only from outage notices are roughly right: they may start at a nearby house cluster
        named, unnamed_cells = pe.split_nested(inside, houses[win], step[win], n, top, to_cell, preset_for,
                                               barrier=barrier[win], dem=dem[win].astype(np.float64),
                                               loose_reach=pe.LOOSE_REACH_M / grid.res, min_cells=min_cells)
        # One grid to draw from: each cell goes to the deepest name holding it, so a sitio's
        # own label is the part of it none of its puroks cover
        labels = np.full(inside.shape, -1, np.int32)
        for i, (_, cells, _) in enumerate(named):
            labels[cells] = i
        for j, cells in enumerate(unnamed_cells):
            labels[cells] = len(named) + j
        shapes = pe.outline_areas(pe.extend(labels))

        def to_lnglat(x, y):
            return sus.px_to_lnglat(grid.px0 + c0 + x, grid.py0 + r0 + y, grid.zoom)

        own = {}
        for label, shape in shapes.items():
            geom = pe.to_map(shape, to_lnglat).intersection(barangay.boundary)
            pieces = [g for g in pe.polygons(geom) if pe.area_m2(g) >= pe.MIN_PIECE_HA * 10_000]
            if pieces:
                own[label] = MultiPolygon(*pieces, srid=4326)
        index_of = {id(row): i for i, (row, _, _) in enumerate(named)}

        def whole(node):
            """A name's area with all of its puroks': a sitio's outline goes around them."""
            parts = [own[index_of[id(node.row)]]] if index_of[id(node.row)] in own else []
            parts += [g for g in (whole(c) for c in node.children) if g is not None]
            if not parts:
                return None
            union = parts[0]
            for part in parts[1:]:
                union = union.union(part)
            return MultiPolygon(*pe.polygons(union), srid=4326)

        found = []  # (row, area, members), sitios before their puroks

        def collect(node):
            area = whole(node) if node.children else own.get(index_of[id(node.row)])
            if area is not None:
                found.append((node.row, area, len(node.children)))
            for child in node.children:
                collect(child)
        for node in top:
            collect(node)
        unnamed = [own[len(named) + j] for j in range(len(unnamed_cells)) if len(named) + j in own]
        # North to south, then west to east, so a landmark shared by two goes the same way every build
        unnamed.sort(key=lambda g: (-round(g.point_on_surface.y, 3), g.point_on_surface.x))
        described = pe.area_names(unnamed, *landmarks, taken={r['name'] for r, _, _ in found})

        lost = [r['name'] for r, _, _ in named if r['name'] not in {f['name'] for f, _, _ in found}]
        sitios = sum(1 for _, _, members in found if members)
        log(f'  {barangay.name}: {len(found)} named ({sitios} sitios) + {len(unnamed)} unnamed areas '
            f'(target {n}, from {basis}); {len(names) - placed} names still to place')
        if lost:
            log(f'      no area left for {", ".join(lost)}')

        def feature(geom, **props):
            return {'type': 'Feature', 'geometry': json.loads(geom.json),
                    'properties': {'barangay': barangay.name, 'source': 'estimated', **props}}

        places = pe.place_areas([(r['name'], g) for r, g, members in found if not members] +
                                list(zip(described, unnamed)),
                                [(r['name'], g) for r, g, members in found if members], *landmarks)
        return ([feature(g, name=r['name'], kind=r['kind'], parent=r['parent'], confidence=r['confidence'],
                         members=members) for r, g, members in found] +
                [feature(g, name=name, kind='purok', parent='', confidence='', members=0)
                 for name, g in zip(described, unnamed)]), places

    @staticmethod
    def pulled_inside(names, key, outlines):
        """The names, with each one placed only roughly moved inside its sitio's drawn outline."""
        out = []
        for row in names:
            outline = outlines.get((key, row.get('parent') or ''))
            if outline is not None and row['confidence'] == 'low' and row['lat'] and row['lng']:
                lng, lat = pe.pull_inside(float(row['lng']), float(row['lat']), outline)
                row = {**row, 'lng': f'{lng:.6f}', 'lat': f'{lat:.6f}'}
            out.append(row)
        return out
