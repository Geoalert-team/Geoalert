"""
Per-purok features for the fire risk model (plan Task B1): the feature math on
small hand-made inputs, the feature file, the build command, and the guard
that keeps fire records out of every input (spec section 7).
"""
import ast
import csv
import math
import tempfile
from pathlib import Path
from unittest import mock

import numpy as np
from django.contrib.gis.geos import MultiPolygon
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase

from apps.barangays.models import Barangay, Purok
from apps.history import fire_features as ff
from tests.fire_setup import LAT, LNG, M, box

HISTORY = Path(ff.__file__).parent
GUARDED = (HISTORY / 'fire_features.py', HISTORY / 'fire_sources.py',
           HISTORY / 'management' / 'commands' / 'build_fire_features.py')
FORBIDDEN = ('apps.history.models', 'HistoricalRecord', 'apps.history.forecast', 'apps.history.bfp')


def grid(n, spacing, x0=0.0, y0=0.0):
    """n x n points `spacing` metres apart."""
    return np.array([(x0 + i * spacing, y0 + j * spacing) for i in range(n) for j in range(n)], float)


class BuildingFeatureTests(SimpleTestCase):
    def test_building_features_on_a_grid(self):
        centres = grid(3, 8.0)
        f = ff.building_features(centres, np.full(9, 40.0), np.ones(9, bool), 1.0)
        self.assertEqual(f['buildings_in_area'], 9)
        self.assertEqual(f['building_density_per_ha'], 9)
        self.assertAlmostEqual(f['median_gap_to_nearest_building_m'], 8.0)
        self.assertEqual(f['share_crowded_10m'], 1.0)  # a corner has 2 neighbours at 8 m; the diagonal is 11.3 m
        self.assertEqual(f['median_footprint_m2'], 40.0)

    def test_only_inside_buildings_are_described(self):
        centres = np.vstack([grid(3, 8.0), [[500.0, 500.0]]])
        inside = np.array([True] * 9 + [False])
        f = ff.building_features(centres, np.array([40.0] * 9 + [900.0]), inside, 2.0)
        self.assertEqual(f['buildings_in_area'], 9)
        self.assertEqual(f['building_density_per_ha'], 4.5)
        self.assertEqual(f['median_footprint_m2'], 40.0)

    def test_empty_area_measures_from_its_point(self):
        centres = np.array([[30.0, 40.0], [100.0, 100.0]])
        f = ff.building_features(centres, np.array([50.0, 60.0]), np.zeros(2, bool), 0.5, origin_m=np.array([0.0, 0.0]))
        self.assertEqual((f['buildings_in_area'], f['building_density_per_ha']), (0, 0))
        self.assertEqual((f['median_footprint_m2'], f['share_crowded_10m']), (0, 0))
        self.assertAlmostEqual(f['median_gap_to_nearest_building_m'], 50.0)  # point to the nearest building
        self.assertTrue(all(math.isfinite(v) for v in f.values()))


class RoadFeatureTests(SimpleTestCase):
    def test_segment_points_every_10_m(self):
        pts = ff.segment_points([np.array([[0.0, 0.0], [100.0, 0.0]])])
        self.assertEqual(len(pts), 10)  # each point stands for 10 m of road
        self.assertAlmostEqual(pts[1][0] - pts[0][0], 10.0)

    def test_road_features(self):
        road = ff.segment_points([np.array([[0.0, 0.0], [100.0, 0.0]])])
        main = ff.segment_points([np.array([[0.0, 50.0], [50.0, 50.0]])])
        f = ff.road_features(road, main, np.ones(len(road), bool), np.ones(len(main), bool),
                             np.array([[10.0, 20.0], [20.0, 30.0], [30.0, 40.0]]), 2.0)
        self.assertEqual(f['road_density_m_per_ha'], 50.0)  # 100 m of road over 2 ha
        self.assertEqual(f['main_road_m'], 50.0)
        self.assertAlmostEqual(f['median_building_to_road_m'], 30.0)

    def test_station_distance_follows_roads(self):
        roads = [np.array([[0.0, 0.0], [100.0, 0.0]]), np.array([[100.0, 0.0], [100.0, 100.0]])]
        d = ff.station_distances(roads, np.array([[100.0, 100.0]]), np.array([[0.0, 0.0]]))
        self.assertAlmostEqual(d[0], 200.0, places=3)  # along the road, not the straight 141 m

    def test_station_distance_skips_roads_cut_off_from_every_station(self):
        roads = [np.array([[0.0, 0.0], [100.0, 0.0]]), np.array([[0.0, 5.0], [-300.0, 5.0]])]
        d = ff.station_distances(roads, np.array([[100.0, 0.0]]), np.array([[-1.0, 5.0]]))
        self.assertTrue(math.isfinite(d[0]))  # joins the road that reaches a station
        self.assertAlmostEqual(d[0], 100.0 + math.hypot(1.0, 5.0), places=3)


class LandAndShapeTests(SimpleTestCase):
    def test_landcover_shares(self):
        s = ff.landcover_shares(np.array([50, 50, 30, 10]))
        self.assertEqual(s, {'share_built_up': 0.5, 'share_grass_shrub_bare': 0.25, 'share_tree_cover': 0.25})

    def test_landcover_ignores_no_data(self):
        s = ff.landcover_shares(np.array([0, 0, 50, 80]))
        self.assertEqual(s['share_built_up'], 0.5)

    def test_points_inside_respects_holes(self):
        outer = [(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)]
        hole = [(4, 4), (6, 4), (6, 6), (4, 6), (4, 4)]
        pts = np.array([[1, 1], [5, 5], [11, 5], [9, 9]], float)
        self.assertEqual(ff.points_inside([[outer, hole]], pts).tolist(), [True, False, False, True])

    def test_area_ha_subtracts_holes(self):
        outer = [(0, 0), (100, 0), (100, 100), (0, 100), (0, 0)]
        hole = [(40, 40), (60, 40), (60, 60), (40, 60), (40, 40)]
        self.assertAlmostEqual(ff.area_ha([[outer, hole]]), 0.96)


class FeatureFileTests(SimpleTestCase):
    def table(self):
        row = {c: 1.5 for c in ff.FEATURE_COLUMNS}
        row.update(purok_id=7, barangay_id=3, barangay='Biasong', name='Purok Mahayahay', confidence='medium',
                   from_fire_log=True)
        other = dict(row, purok_id=8, name='Sitio, with a comma', from_fire_log=False, buildings_in_area=0.0)
        return ff.FeatureTable(rows=[row, other], outlines_version='abc123', built_at='2026-11-23T10:00:00+08:00',
                               sources={'buildings': {'name': 'Microsoft', 'licence': 'ODbL'}})

    def test_feature_file_round_trip(self):
        with tempfile.TemporaryDirectory() as d:
            csv_path, meta_path = Path(d) / 'f.csv', Path(d) / 'f.meta.json'
            ff.write_features(self.table(), csv_path, meta_path)
            back = ff.read_features(csv_path, meta_path)
            with open(csv_path, encoding='utf-8', newline='') as fh:
                header = next(csv.reader(fh))
        self.assertEqual(back.rows, self.table().rows)
        self.assertEqual(back.outlines_version, 'abc123')
        self.assertEqual(back.sources, self.table().sources)
        self.assertEqual(header, list(ff.ID_COLUMNS) + list(ff.FEATURE_COLUMNS))

    def test_columns_are_the_allowlist(self):
        self.assertEqual(ff.FEATURE_COLUMNS, (
            'buildings_in_area', 'building_density_per_ha', 'median_footprint_m2',
            'median_gap_to_nearest_building_m', 'share_crowded_10m', 'road_density_m_per_ha', 'main_road_m',
            'median_building_to_road_m', 'road_distance_to_fire_station_m', 'share_built_up',
            'share_grass_shrub_bare', 'share_tree_cover', 'population', 'distance_to_coast_m',
            'distance_to_river_m'))
        self.assertEqual(ff.LOG_COLUMNS, ('buildings_in_area', 'building_density_per_ha', 'population'))
        self.assertFalse(set(ff.ID_COLUMNS) & set(ff.FEATURE_COLUMNS))

    def test_fire_log_names(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'points.csv'
            path.write_text('barangay,name,sources\nBiasong,Purok A,fire log; Overture\n'
                            'Biasong,Purok B,Google Maps\nTangke,Purok C,Fire Log research\n', encoding='utf-8')
            self.assertEqual(ff.fire_log_names(path), {('Biasong', 'Purok A'), ('Tangke', 'Purok C')})


class NoCountingGuardTests(SimpleTestCase):
    def imported_names(self, path):
        tree = ast.parse(path.read_text(encoding='utf-8'))
        names = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names += [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                names.append(node.module or '')
                names += [f'{node.module}.{a.name}' for a in node.names] + [a.name for a in node.names]
        return names

    def test_no_fire_records_in_features(self):
        for path in GUARDED:
            for name in self.imported_names(path):
                for bad in FORBIDDEN:
                    self.assertFalse(name == bad or name.startswith(bad), f'{path.name} imports {name}')

    def test_guard_catches_a_forbidden_import(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'bad.py'
            path.write_text('from apps.history.models import HistoricalRecord\nfrom apps.history import bfp_import\n')
            names = self.imported_names(path)
        self.assertIn('HistoricalRecord', names)
        self.assertTrue(any(n.startswith('apps.history.bfp') for n in names))


def tiled_geotiff(path, values, west, north, d):
    """A tiled, deflated GeoTIFF of `values` with its corner at (west, north) and d-degree pixels."""
    import tifffile
    tags = [(33550, 'd', 3, (d, d, 0.0)), (33922, 'd', 6, (0.0, 0.0, 0.0, west, north, 0.0)),
            (34735, 'H', 8, (1, 1, 0, 1, 1025, 0, 1, 1))]  # GeoKey directory: raster type = pixel is area
    tifffile.imwrite(path, values, tile=(16, 16), compression='zlib', extratags=tags)


class RasterWindowTests(SimpleTestCase):
    """fire_sources reads only the tiles over the city, from a range-read URL or a saved file."""
    values = np.arange(48 * 64, dtype=np.float32).reshape(48, 64)
    bbox = (9.9 - 30 * 0.01, 120.0 + 20 * 0.01, 9.9 - 10 * 0.01, 120.0 + 40 * 0.01)  # rows 10-30, cols 20-40

    def check(self, values, transform):
        west, north, dx, dy = transform
        r0, c0 = round((9.9 - north) / dy), round((west - 120.0) / dx)
        self.assertTrue(np.array_equal(values, self.values[r0:r0 + values.shape[0], c0:c0 + values.shape[1]]))
        self.assertLessEqual(r0, 10)
        self.assertGreaterEqual(r0 + values.shape[0], 30)
        self.assertLessEqual(c0, 20)
        self.assertGreaterEqual(c0 + values.shape[1], 40)

    def test_window_from_a_saved_file(self):
        from apps.history import fire_sources
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'pop.tif'
            tiled_geotiff(path, self.values, 120.0, 9.9, 0.01)
            self.check(*fire_sources.read_local_window(path, self.bbox))

    def test_window_by_range_reads(self):
        from apps.history import fire_sources
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'cover.tif'
            tiled_geotiff(path, self.values, 120.0, 9.9, 0.01)
            data = path.read_bytes()
        self.check(*fire_sources.read_window(lambda url, start, n: data[start:start + n], 'mem://cover', self.bbox))


def metres_to_lnglat(x, y):
    """Fixture metres from (LNG, LAT) as fire_setup.box draws them."""
    return LNG + x * M / math.cos(math.radians(LAT)), LAT + y * M


class BuildCommandTests(TestCase):
    def setUp(self):
        self.brgy = Barangay.objects.create(name='Home', municipality='Talisay',
                                            boundary=MultiPolygon(box(-500, -500, 500, 500), srid=4326))
        self.busy = Purok.objects.create(barangay=self.brgy, name='Purok Busy', kind='purok', source='estimated',
                                         confidence='high', boundary=MultiPolygon(box(-100, -100, 100, 100), srid=4326))
        self.empty = Purok.objects.create(barangay=self.brgy, name='Purok Empty', kind='purok', source='estimated',
                                          confidence='low', boundary=MultiPolygon(box(200, 200, 400, 400), srid=4326))

    def sources(self):
        centres = np.array([metres_to_lnglat(x, y) for x, y in grid(3, 8.0, -8, -8)])
        road = [list(metres_to_lnglat(x, 0)) for x in (-300, 300)]
        osm = {'roads': [road], 'main_roads': [road], 'fire_stations': [list(metres_to_lnglat(300, 0))],
               'coastline': [[list(metres_to_lnglat(-300, -450)), list(metres_to_lnglat(300, -450))]],
               'waterways': [{'kind': 'river', 'name': '', 'coords': [list(metres_to_lnglat(450, -300)),
                                                                     list(metres_to_lnglat(450, 300))]}]}
        west, north = metres_to_lnglat(-500, 500)
        east, south = metres_to_lnglat(500, -500)
        classes = np.full((100, 100), 50, np.uint8)
        land = (classes, (west, north, (east - west) / 100, (north - south) / 100))
        people = (np.full((10, 10), 20.0, np.float32), (west, north, (east - west) / 10, (north - south) / 10))
        return {
            'footprints': mock.patch.object(ff_sources(), 'footprints', return_value=(centres, np.full(9, 40.0))),
            'osm': mock.patch.object(ff_sources(), 'osm', return_value=osm),
            'worldcover': mock.patch.object(ff_sources(), 'worldcover', return_value=land),
            'worldpop': mock.patch.object(ff_sources(), 'worldpop', return_value=people),
        }

    def run_command(self, d, patches):
        for p in patches.values():
            p.start()
        try:
            call_command('build_fire_features', output_dir=d, cache_dir=d, stdout=mock.MagicMock())
        finally:
            for p in patches.values():
                p.stop()
        return ff.read_features(Path(d) / ff.FEATURES_FILE.name, Path(d) / ff.FEATURES_META.name)

    def test_command_writes_one_row_per_purok(self):
        with tempfile.TemporaryDirectory() as d:
            table = self.run_command(d, self.sources())
        self.assertEqual(table.outlines_version, Purok.outlines_version())
        rows = {r['purok_id']: r for r in table.rows}
        self.assertEqual(set(rows), {self.busy.id, self.empty.id})
        busy, empty = rows[self.busy.id], rows[self.empty.id]
        self.assertEqual(busy['buildings_in_area'], 9)
        self.assertEqual(empty['buildings_in_area'], 0)
        self.assertEqual(empty['confidence'], 'low')
        self.assertAlmostEqual(busy['share_built_up'], 1.0)
        self.assertGreater(busy['population'], 0)
        for row in table.rows:
            self.assertTrue(all(math.isfinite(row[c]) for c in ff.FEATURE_COLUMNS), row)
        self.assertIn('buildings', table.sources)

    def test_population_dropped_when_unavailable(self):
        patches = self.sources()
        patches['worldpop'] = mock.patch.object(ff_sources(), 'worldpop', return_value=None)
        with tempfile.TemporaryDirectory() as d:
            table = self.run_command(d, patches)
        self.assertEqual(table.dropped, ('population',))
        self.assertTrue(all(math.isnan(r['population']) for r in table.rows))
        self.assertFalse(table.sources['population']['used'])


def ff_sources():
    from apps.history import fire_sources
    return fire_sources
