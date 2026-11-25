"""
Clue functions for the landslide susceptibility model (plan Task 2): terrain,
curvature, road distance and land-cover shares, computed by one set of
functions for the training tiles and for Talisay.
"""
import ast
import json
import shutil
import tempfile
from pathlib import Path

import numpy as np
from django.test import SimpleTestCase
from scipy import ndimage

from apps.hazards.susceptibility import Grid
from apps.history import landslide_features
from apps.history.landslide_features import (FEATURE_COLUMNS, GRID_COLUMNS, GRIDS_FILE, LANDCOVER_CLASSES,
                                             POINTS_FILE, TERRAIN_COLUMNS, LandslideFeatures, curvatures, features_at,
                                             landcover_shares, read_features, road_distance, road_points, sample,
                                             scoring_points, terrain_grids, write_features, write_grids)


def imported_modules(src: str, package: str) -> set:
    """Every module the source imports, and module.name for each `from module import name`; relative ones resolved."""
    imported = set()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = package.split('.')[:len(package.split('.')) - (node.level - 1)]
                module = '.'.join(base + ([node.module] if node.module else []))
            else:
                module = node.module
            imported.add(module)
            imported.update(f'{module}.{a.name}' for a in node.names)
    return imported


class ClueTests(SimpleTestCase):
    def setUp(self):
        rows, cols = np.mgrid[0:80, 0:80].astype(float)
        # A V-shaped valley, its floor at column 40, draining south (row 79)
        self.valley_dem = 50 + 3 * np.abs(cols - 40) + 1.0 * (79 - rows)
        self.axis_cell = (70, 40)
        self.ridge_cell = (70, 2)

    def test_a_plane_has_its_slope_and_no_curvature(self):
        y, x = np.mgrid[0:60, 0:60].astype(float)
        dem = 100 + 0.5 * x * 10  # 0.5 m per m east, res 10 m
        g = terrain_grids(dem, res=10.0)
        self.assertAlmostEqual(float(np.median(g['slope_deg'])), np.degrees(np.arctan(0.5)), places=1)
        prof, plan = curvatures(ndimage.gaussian_filter(dem, 1.0), 10.0)
        self.assertLess(float(np.abs(prof[10:-10, 10:-10]).max()), 1e-6)
        self.assertLess(float(np.abs(plan[10:-10, 10:-10]).max()), 1e-6)

    def test_a_hollow_has_concave_plan_curvature_and_wetter_twi(self):
        g = terrain_grids(self.valley_dem, res=10.0)  # V-shaped valley draining south
        self.assertGreater(g['twi'][self.axis_cell], g['twi'][self.ridge_cell])
        self.assertLess(g['hand_m'][self.axis_cell], g['hand_m'][self.ridge_cell])
        self.assertEqual(float(g['hand_m'][self.axis_cell]), 0.0)
        self.assertEqual(float(g['dist_stream_m'][self.axis_cell]), 0.0)
        self.assertGreater(g['dist_stream_m'][self.ridge_cell], 100)
        # The mid slope of a V-shaped valley is a plane; its floor bends the ground across the line of fall
        self.assertGreater(g['plan_curv'][70, 41], 0.0)

    def test_a_dome_has_positive_profile_curvature(self):
        rows, cols = np.mgrid[0:41, 0:41].astype(float)
        dome = 200 - 0.01 * ((rows - 20) ** 2 + (cols - 20) ** 2) * 10
        prof, _ = curvatures(dome, 10.0)
        self.assertGreater(float(prof[20, 25]), 0.0)  # this formula: convex is positive
        self.assertEqual(float(prof[20, 20]), 0.0)  # flat summit: no gradient

    def test_the_same_clues_for_a_training_window_and_the_city_grid(self):
        a = terrain_grids(self.valley_dem, 9.4)
        b = terrain_grids(self.valley_dem.copy(), 9.4)
        self.assertEqual(tuple(a), TERRAIN_COLUMNS)
        for c in TERRAIN_COLUMNS:
            self.assertEqual(a[c].dtype, np.float32)
            np.testing.assert_array_equal(a[c], b[c])

    def test_landcover_shares(self):
        cls = np.full((21, 21), 2)
        cls[:, 11:] = 7
        s = landcover_shares(cls, res_m=10.0, radius_m=50)
        self.assertAlmostEqual(float(s['lc_built'][10, 10]), 5 / 11, places=1)
        self.assertEqual(set(s), set(LANDCOVER_CLASSES.values()))
        total = sum(s[n] for n in ('lc_trees', 'lc_built'))
        np.testing.assert_allclose(total, 1.0, atol=1e-5)

    def test_other_classes_count_only_in_the_denominator(self):
        cls = np.full((21, 21), 1)  # water: not one of the five groups
        cls[:, 11:] = 7
        s = landcover_shares(cls, res_m=10.0, radius_m=50)
        self.assertAlmostEqual(float(s['lc_built'][10, 10]), 5 / 11, places=1)
        self.assertEqual(float(s['lc_trees'][10, 10]), 0.0)

    def test_road_distance_in_metres(self):
        grid = Grid(10.245, 123.825, 10.265, 123.845, 14)
        road = [(123.835, 10.245), (123.835, 10.265)]
        d = road_distance(grid, [road])
        self.assertEqual(d.shape, grid.shape)
        col, row = grid.to_cell(123.835, 10.255)
        self.assertLess(float(d[int(row), int(col)]), 2 * grid.res)
        self.assertAlmostEqual(float(d[int(row), int(col) + 5]), 5 * grid.res, delta=grid.res)

    def test_sample_reads_the_grid_under_each_point(self):
        grid = Grid(10.245, 123.825, 10.265, 123.845, 14)
        values = np.arange(grid.height * grid.width, dtype=np.float32).reshape(grid.shape)
        out = sample(grid, {'a': values}, np.array([[123.835, 10.255]]))
        col, row = grid.to_cell(123.835, 10.255)
        self.assertEqual(float(out['a'][0]), float(values[int(row), int(col)]))

    def test_feature_columns_are_the_thirteen_inputs(self):
        self.assertEqual(len(FEATURE_COLUMNS), 13)
        self.assertEqual(FEATURE_COLUMNS[:7], TERRAIN_COLUMNS)

    def test_feature_module_reads_no_landslide_records(self):
        src = Path(landslide_features.__file__).read_text(encoding='utf-8')
        for name in ('HistoricalRecord', 'landslide_inventories', 'purok_levels', 'forecast'):
            self.assertNotIn(name, src)

    # Spec 7, final review B5: no feature builder reaches GeoAlert's records, the history loaders, forecast.py or
    # purok_levels (the training builder reads the outside inventories, so landslide_inventories is allowed there)
    def test_no_feature_builder_reads_history(self):
        here = Path(landslide_features.__file__).parent
        commands = here / 'management' / 'commands'
        builders = (here / 'landslide_features.py', here / 'landslide_sources.py', here / 'landslide_training_table.py',
                    commands / 'build_landslide_features.py', commands / 'build_landslide_training.py')
        history_modules = {'apps.history.models', 'apps.history.area', 'apps.history.places',
                           'apps.history.importing', 'apps.history.flood_landslide', 'apps.history.flood_labels',
                           'apps.history.forecast', 'apps.history.forecast_rows', 'apps.history.purok_levels',
                           'apps.hazards.models', 'apps.reports.models'}
        backend = here.parents[1]
        for path in builders:
            src = path.read_text(encoding='utf-8')
            for name in ('HistoricalRecord', 'ZoneFieldMark', 'purok_levels', 'forecast', 'flood_labels'):
                self.assertNotIn(name, src, f'{path.name} mentions {name}')
            package = '.'.join(path.relative_to(backend).with_suffix('').parts[:-1])
            imported = imported_modules(src, package)
            self.assertFalse(imported & history_modules, f'{path.name} imports {sorted(imported & history_modules)}')

    # Final review m2: a relative import (`from . import places`) is resolved against the file's package, so the
    # guard sees it too (landslide_sources already imports `from . import downloads`)
    def test_the_import_guard_sees_relative_imports(self):
        self.assertIn('apps.history.places', imported_modules('from . import places', 'apps.history'))
        self.assertIn('apps.history.models', imported_modules('from ..models import X', 'apps.history.sub'))
        self.assertIn('apps.history.forecast_rows',
                      imported_modules('from ...forecast_rows import f', 'apps.history.management.commands'))
        self.assertIn('apps.history.downloads', imported_modules('from . import downloads', 'apps.history'))
        self.assertEqual(imported_modules('import numpy as np; from apps.hazards import susceptibility', 'x'),
                         {'numpy', 'apps.hazards', 'apps.hazards.susceptibility'})


class ScoringPointTests(SimpleTestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.grid = Grid(10.245, 123.825, 10.265, 123.845, 14)
        self.mask = np.zeros(self.grid.shape, bool)
        c0, r0 = self.grid.to_cell(123.832, 10.262)
        c1, r1 = self.grid.to_cell(123.838, 10.248)
        self.mask[int(r0):int(r1), int(c0):int(c1)] = True  # the city: a box in the middle
        self.city = (self.grid, self.mask)
        # three buildings inside the box, two outside it
        self.buildings_ll = np.array([[123.834, 10.255], [123.835, 10.256], [123.836, 10.257],
                                      [123.826, 10.255], [123.844, 10.264]])
        self.buildings_inside = 3
        # a road running east across the whole grid, half of it inside the box
        self.road_line = [(123.826, 10.255), (123.844, 10.255)]

    def _features(self):
        pts, kind = scoring_points(self.buildings_ll, [self.road_line], self.city)
        n = len(pts)
        points = {'lon': pts[:, 0], 'lat': pts[:, 1], 'kind': kind,
                  'noah_class': (np.arange(n) % 4).astype(np.uint8)}
        for i, name in enumerate(FEATURE_COLUMNS):
            points[name] = np.full(n, float(i), np.float32)
        member = (np.arange(n), np.where(np.arange(n) % 2 == 0, 7, 9))
        areas = []
        for pid in (7, 9, 11):
            idx = member[0][member[1] == pid]
            areas.append({'purok_id': pid, 'barangay_id': 1, 'barangay': 'Bulacao', 'name': f'Purok {pid}',
                          'confidence': 'official', 'points': len(idx), 'buildings': int((kind[idx] == 0).sum()),
                          'road_points': int((kind[idx] == 1).sum()),
                          'noah_p90': float(np.percentile(points['noah_class'][idx] / 3, 90)) if len(idx) else 0.0})
        meta = {'outlines_version': 'v1', 'landcover_year': 2023, 'landcover_ok': True,
                'talisay_steep_road_density': 1.5, 'points': n}
        return LandslideFeatures(points=points, membership=member, areas=areas, meta=meta)

    def test_road_points_every_20_m(self):
        line = [(123.85, 10.25), (123.85 + 100 / (111320 * np.cos(np.radians(10.25))), 10.25)]  # 100 m east
        self.assertEqual(len(road_points([line], step_m=20)), 6)

    def test_road_points_include_the_start_and_drop_duplicates(self):
        a = [(123.85, 10.25), (123.8505, 10.25)]
        b = [(123.8505, 10.25), (123.851, 10.25)]  # starts where a ends
        pts = road_points([a, b], step_m=20)
        np.testing.assert_allclose(pts[0], a[0])
        self.assertEqual(len(pts), len({(round(x, 6), round(y, 6)) for x, y in pts}))
        gaps = np.hypot(*np.diff(pts[:, :2] * [111320 * np.cos(np.radians(10.25)), 110574], axis=0).T)
        self.assertGreater(float(gaps.min()), 1.0)

    def test_road_points_skip_empty_lines(self):
        self.assertEqual(road_points([], step_m=20).shape, (0, 2))

    def test_scoring_points_are_inside_the_city_and_tagged(self):
        pts, kind = scoring_points(self.buildings_ll, [self.road_line], self.city)
        self.assertTrue(set(kind.tolist()) <= {0, 1})
        self.assertEqual(int((kind == 0).sum()), self.buildings_inside)
        self.assertGreater(int((kind == 1).sum()), 0)
        self.assertEqual(pts.shape, (len(kind), 2))
        self.assertTrue(((pts[:, 0] > 123.8315) & (pts[:, 0] < 123.8385)).all())  # nothing outside the box

    def test_features_csv_has_no_coordinates(self):
        write_features(self._features(), self.tmp / 'f.csv', self.tmp / 'f.json', cache_dir=self.tmp)
        text = (self.tmp / 'f.csv').read_text(encoding='utf-8')
        self.assertEqual(text.splitlines()[0],
                         'purok_id,barangay_id,barangay,name,confidence,points,buildings,road_points,noah_p90')
        self.assertNotIn('lat', text.splitlines()[0])
        self.assertNotIn('lon', text.splitlines()[0])
        self.assertNotIn('lat', (self.tmp / 'f.json').read_text(encoding='utf-8'))

    def test_features_round_trip_with_the_points_file(self):
        f = self._features()
        write_features(f, self.tmp / 'f.csv', self.tmp / 'f.json', cache_dir=self.tmp)
        self.assertTrue((self.tmp / POINTS_FILE).exists())
        back = read_features(self.tmp / 'f.csv', self.tmp / 'f.json', cache_dir=self.tmp)
        self.assertEqual(back.areas, f.areas)
        self.assertEqual(back.meta, f.meta)
        np.testing.assert_array_equal(back.membership[1], f.membership[1])
        for name in ('lon', 'lat', 'kind', 'noah_class') + FEATURE_COLUMNS:
            np.testing.assert_array_equal(back.points[name], f.points[name])

    def test_read_without_a_cache_dir_has_no_points(self):
        write_features(self._features(), self.tmp / 'f.csv', self.tmp / 'f.json')
        back = read_features(self.tmp / 'f.csv', self.tmp / 'f.json')
        self.assertEqual(back.points, {})
        self.assertEqual(len(back.areas), 3)

    def test_features_at_reads_every_clue_and_the_noah_class(self):
        grids = {name: np.full(self.grid.shape, float(i), np.float32) for i, name in enumerate(FEATURE_COLUMNS)}
        grids['slope_deg'][:, :] = np.arange(self.grid.width, dtype=np.float32)[None, :]  # varies by column
        grids['noah_class'] = np.full(self.grid.shape, 2, np.uint8)
        bbox = (10.245, 123.825, 10.265, 123.845)
        write_grids(bbox, self.grid.zoom, grids, self.tmp)
        self.assertTrue((self.tmp / GRIDS_FILE).exists())
        pts = np.array([[123.835, 10.255], [123.84, 10.25]])
        out = features_at(pts, self.tmp)
        self.assertEqual(set(out), set(FEATURE_COLUMNS) | {'noah_class'})
        self.assertEqual(float(out['dist_road_m'][0]), float(FEATURE_COLUMNS.index('dist_road_m')))
        self.assertEqual(out['noah_class'].tolist(), [2, 2])
        col0, _ = self.grid.to_cell(*pts[0])
        col1, _ = self.grid.to_cell(*pts[1])
        self.assertEqual(out['slope_deg'].tolist(), [float(int(col0)), float(int(col1))])
        self.assertNotEqual(out['slope_deg'][0], out['slope_deg'][1])

    # Final review B1: a point off the saved grids has no clue (NaN), never the edge cell's
    def test_features_at_a_point_off_the_saved_grids_is_missing_not_the_edge_cells(self):
        grids = {name: np.full(self.grid.shape, float(i), np.float32) for i, name in enumerate(FEATURE_COLUMNS)}
        grids['slope_deg'][:, :] = np.arange(self.grid.width, dtype=np.float32)[None, :]
        grids['noah_class'] = np.full(self.grid.shape, 2, np.uint8)
        write_grids((10.245, 123.825, 10.265, 123.845), self.grid.zoom, grids, self.tmp)
        inside = np.array([[123.835, 10.255], [123.84, 10.25]])
        far = np.array([[123.835 + 0.78, 10.255], [123.835, 10.255 - 0.5], [123.80, 10.255]])  # 85 km east, south, west
        out = features_at(np.r_[inside, far], self.tmp)
        for name in GRID_COLUMNS:
            self.assertTrue(np.isnan(out[name][2:]).all(), name)
        # The points on the grids read exactly what they read before (the scoring points are all on them)
        before = sample(self.grid, grids, inside)
        for name in GRID_COLUMNS:
            np.testing.assert_array_equal(out[name][:2], before[name], err_msg=name)


class AreaRowTests(SimpleTestCase):
    def test_area_rows_count_points_by_kind_and_take_the_noah_p90(self):
        from types import SimpleNamespace

        from apps.history.management.commands.build_landslide_features import Command

        puroks = [SimpleNamespace(id=1, barangay_id=5, barangay=SimpleNamespace(name='Bulacao'), name='Purok 1',
                                  confidence='official'),
                  SimpleNamespace(id=2, barangay_id=5, barangay=SimpleNamespace(name='Bulacao'), name='Purok 2',
                                  confidence='official')]
        kind = np.array([0, 0, 1, 1])
        noah = np.array([0, 3, 3, 3], np.uint8)
        rows = Command.area_rows(puroks, (np.array([0, 1, 2]), np.array([1, 1, 1])), kind, noah)
        self.assertEqual((rows[0]['points'], rows[0]['buildings'], rows[0]['road_points']), (3, 2, 1))
        self.assertAlmostEqual(rows[0]['noah_p90'], 1.0)
        self.assertEqual((rows[1]['points'], rows[1]['noah_p90']), (0, 0.0))
