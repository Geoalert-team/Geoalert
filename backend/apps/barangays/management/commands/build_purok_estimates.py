import csv
import gzip
import io
import json
from pathlib import Path

import numpy as np
from django.conf import settings
from django.contrib.gis.geos import MultiPolygon
from django.core.management.base import BaseCommand, CommandError
from scipy import ndimage

from apps.barangays import purok_estimate as pe
from apps.barangays.aliases import canonical
from apps.barangays.models import Barangay
from apps.hazards import susceptibility as sus

OUT_FILE = Path(__file__).resolve().parents[2] / 'data' / 'puroks' / 'talisay_puroks_estimated.geojson'

# Microsoft Global ML Building Footprints (ODbL): one file per zoom-9 tile;
# 132330002 covers all of Talisay
BUILDINGS_INDEX = 'https://minedbuildings.z5.web.core.windows.net/global-buildings/dataset-links.csv'
BUILDINGS_TILE = '132330002'

# How many puroks to split each barangay into. Official sitio counts from the
# City of Talisay Barangay Profiles (2010); elsewhere households (PSA 2015
# census) / 175, the median households per sitio in those profiles.
OFFICIAL_SITIOS = {'Cansojong': 26, 'Tabunoc': 22, 'Lawaan II': 14, 'Pooc': 12, 'Camp IV': 9,
                   'Jaclupan': 9, 'Maghaway': 6, 'Cadulawan': 5}
HOUSEHOLDS_2015 = {
    'Biasong': 1509, 'Bulacao': 2949, 'Cadulawan': 1095, 'Camp IV': 687, 'Cansojong': 3921, 'Dumlog': 4245,
    'Jaclupan': 1921, 'Lagtang': 3071, 'Lawaan I': 2052, 'Lawaan II': 1301, 'Lawaan III': 2598, 'Linao': 2199,
    'Maghaway': 1632, 'Manipis': 521, 'Mohon': 2372, 'Poblacion': 2027, 'Pooc': 2322, 'San Isidro': 3647,
    'San Roque': 4183, 'Tabunoc': 3454, 'Tangke': 3187, 'Tapul': 346,
}
OFFICIAL = {canonical(k): v for k, v in OFFICIAL_SITIOS.items()}
HOUSEHOLDS = {canonical(k): v for k, v in HOUSEHOLDS_2015.items()}


class Command(BaseCommand):
    help = ('Split every barangay into estimated purok areas along roads, creeks and ridges, sized by '
            'where its houses are, and write them as GeoJSON for load_puroks. Stand-in until the '
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
        except Exception as exc:  # network problems are the usual cause
            raise CommandError(f'Download failed: {exc}') from exc
        log(f'  {len(buildings)} buildings')

        step, barrier, houses = self.costs(grid, dem, osm, buildings, log)
        labels = sus.draw_polygons(grid, [(i + 1, [list(r.coords) for r in poly])
                                          for i, b in enumerate(barangays) for poly in b.boundary])
        features = []
        for i, b in enumerate(barangays):
            if b in wanted:
                features += self.split_one(b, labels == i + 1, grid, step, barrier, houses, dem, log)

        out = Path(options['out'])
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({'type': 'FeatureCollection', 'features': features}), encoding='utf-8')
        self.stdout.write(self.style.SUCCESS(f'Wrote {len(features)} estimated purok areas to {out}'))

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

    def split_one(self, barangay, mask, grid, step, barrier, houses, dem, log):
        rows, cols = np.nonzero(mask)
        if not len(rows):
            log(f'  {barangay.name}: too small for the grid, skipped')
            return []
        r0, r1 = max(rows.min() - 4, 0), min(rows.max() + 5, grid.height)
        c0, c1 = max(cols.min() - 4, 0), min(cols.max() + 5, grid.width)
        win = (slice(r0, r1), slice(c0, c1))
        inside = mask[win]

        official = OFFICIAL.get(canonical(barangay.name))
        n, basis = pe.purok_count(official, HOUSEHOLDS.get(canonical(barangay.name), 0), 0)
        owner = pe.split(inside, houses[win], step[win], n, barrier=barrier[win], dem=dem[win].astype(np.float64))
        # Cut-off bits smaller than a tenth of a typical area (or 0.1 ha) join their surroundings
        min_cells = max(pe.MIN_PIECE_HA * 10_000 / grid.res ** 2, inside.sum() / n / 10)
        owner = pe.tidy(owner, inside, min_cells=min_cells)
        shapes = pe.outline_areas(pe.extend(owner))

        def to_lnglat(x, y):
            return sus.px_to_lnglat(grid.px0 + c0 + x, grid.py0 + r0 + y, grid.zoom)

        areas = []
        for label, shape in shapes.items():
            geom = pe.to_map(shape, to_lnglat).intersection(barangay.boundary)
            pieces = [g for g in (geom if geom.geom_type in ('MultiPolygon', 'GeometryCollection') else [geom])
                      if g.geom_type == 'Polygon' and pe.area_m2(g) >= pe.MIN_PIECE_HA * 10_000]
            if pieces:
                areas.append(MultiPolygon(*pieces, srid=4326))
        # Number the areas north to south, then west to east, so the names stay put between builds
        areas.sort(key=lambda g: (-round(g.point_on_surface.y, 3), g.point_on_surface.x))
        log(f'  {barangay.name}: {len(areas)} areas (target {n}, from {basis}), '
            f'{int(houses[win][inside].sum())} buildings')
        return [{'type': 'Feature', 'geometry': json.loads(g.json), 'properties': {
            'barangay': barangay.name, 'name': f'Area {k}', 'kind': 'purok', 'source': 'estimated'}}
            for k, g in enumerate(areas, 1)]
