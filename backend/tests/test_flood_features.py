"""
Static inputs for the flood susceptibility model (plan Task 2): the NOAH depth
grid, the NOAH consistency check, height and distance above the river, sink
depth, built-up share, and the guard that keeps flood observations out of
every input (spec section 7).
"""
from pathlib import Path

import numpy as np
from django.test import SimpleTestCase

from apps.hazards.susceptibility import Grid
from apps.history import flood_features
from apps.history.flood_features import (built_share_at, depression_depth, noah_class_grid, noah_consistent,
                                         river_relative)


def square(x0, y0, x1, y1):
    """One polygon (a list of rings) of a lng/lat box."""
    return [[(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]]


class NoahGridTests(SimpleTestCase):
    def setUp(self):
        self.grid = Grid(10.245, 123.825, 10.265, 123.845, 14)
        self.sq_a = square(123.831, 10.251, 123.835, 10.255)
        self.sq_b = square(123.833, 10.253, 123.837, 10.257)

    def cell(self, lng, lat):
        x, y = self.grid.to_cell(lng, lat)
        return int(y), int(x)

    def test_noah_class_grid_keeps_the_highest_class(self):
        g = noah_class_grid(self.grid, {1: [self.sq_a], 3: [self.sq_b]})
        self.assertEqual(g[self.cell(123.834, 10.254)], 3)  # in both
        self.assertEqual(g[self.cell(123.8315, 10.2515)], 1)  # in A only
        self.assertEqual(g[self.cell(123.843, 10.263)], 0)  # in neither

    def test_a_hole_in_a_higher_class_keeps_the_lower_class_under_it(self):
        ring = [(123.829, 10.249), (123.839, 10.249), (123.839, 10.259), (123.829, 10.259), (123.829, 10.249)]
        hole = [(123.832, 10.252), (123.836, 10.252), (123.836, 10.256), (123.832, 10.256), (123.832, 10.252)]
        g = noah_class_grid(self.grid, {1: [self.sq_a], 2: [[ring, hole]]})
        self.assertEqual(g[self.cell(123.8335, 10.2535)], 1)  # inside the class 2 hole, inside class 1
        self.assertEqual(g[self.cell(123.8295, 10.2495)], 2)


class NoahConsistencyTests(SimpleTestCase):
    def test_noah_consistency(self):
        self.assertEqual(noah_consistent({5: 1.0, 25: 1.0, 100: 0.5}), {5: True, 25: True, 100: False})
        self.assertEqual(noah_consistent({5: 1.03, 25: 1.0, 100: 1.2}), {5: False, 25: True, 100: True})
        self.assertEqual(noah_consistent({25: 1.0}), {25: True})


class TerrainFeatureTests(SimpleTestCase):
    def test_river_relative_and_depression(self):
        dem = np.array([[3., 2., 1.], [3., 2., 1.]])
        river = np.zeros_like(dem, bool)
        river[:, 2] = True
        h, d = river_relative(dem, river, res=10.0)
        np.testing.assert_allclose(h[0], [2., 1., 0.])
        np.testing.assert_allclose(d[0], [20., 10., 0.])
        pit = np.array([[5., 5., 5.], [5., 1., 5.], [5., 5., 5.]])
        self.assertAlmostEqual(float(depression_depth(pit)[1, 1]), 4.0, places=2)
        self.assertAlmostEqual(float(depression_depth(pit)[0, 0]), 0.0, places=3)

    def test_ground_below_the_river_reads_zero_not_negative(self):
        h, _ = river_relative(np.array([[0.5, 1.0]]), np.array([[False, True]]), res=10.0)
        self.assertEqual(float(h[0, 0]), 0.0)

    def test_built_share_within_the_radius(self):
        classes = np.full((41, 41), 10, np.uint8)  # tree cover
        classes[:, 20:] = 50  # built-up on the east half
        dx = 10 / flood_features.KX  # 10 m pixels
        dy = 10 / flood_features.KY
        transform = (123.0, 10.0, dx, dy)
        lng_mid, lat_mid = 123.0 + 20.5 * dx, 10.0 - 20.5 * dy
        shares = built_share_at(classes, transform, np.array([[lng_mid, lat_mid], [123.0 + 2 * dx, lat_mid],
                                                              [123.0 + 39 * dx, lat_mid]]), radius_m=100)
        self.assertAlmostEqual(float(shares[0]), 0.5, delta=0.1)
        self.assertEqual(float(shares[1]), 0.0)
        self.assertEqual(float(shares[2]), 1.0)


class FeaturesAtTests(SimpleTestCase):
    def test_features_at_any_point_from_the_saved_grids(self):
        import tempfile
        cache = Path(tempfile.mkdtemp())
        bbox = (10.245, 123.825, 10.265, 123.845)  # south, west, north, east
        grid = Grid(*bbox, 14)
        noah25 = np.zeros(grid.shape, np.uint8)
        x, y = grid.to_cell(123.834, 10.254)
        noah25[int(y), int(x)] = 3
        grids = {name: np.zeros(grid.shape, np.float32) for name in
                 ('noah5_class', 'rel_height_river_m', 'dist_river_m', 'depression_m')}
        grids['noah25_class'] = noah25
        grids['dist_river_m'][:] = 42.0
        flood_features.write_grids(bbox, 14, grids, cache)
        builtup = (np.full((5, 5), 50, np.uint8), (123.82, 10.27, 0.01, 0.01))
        got = flood_features.features_at(np.array([[123.834, 10.254], [123.826, 10.246]]), cache, landcover=builtup)
        self.assertEqual(got['noah25_class'].tolist(), [3, 0])
        self.assertEqual(got['dist_river_m'].tolist(), [42.0, 42.0])
        self.assertEqual(got['built_share'].tolist(), [1.0, 1.0])
        self.assertEqual(set(got), set(flood_features.FEATURE_COLUMNS))


class GuardTests(SimpleTestCase):
    def test_feature_module_reads_no_flood_records(self):
        for path in (Path(flood_features.__file__),
                     Path(flood_features.__file__).parent / 'management' / 'commands' / 'build_flood_features.py'):
            src = path.read_text(encoding='utf-8')
            for name in ('HistoricalRecord', 'flood_labels', 'purok_levels', 'forecast'):
                self.assertNotIn(name, src, f'{path.name} mentions {name}')

    def test_the_model_inputs_are_the_allowlist(self):
        self.assertEqual(flood_features.FEATURE_COLUMNS,
                         ('noah25_class', 'noah5_class', 'rel_height_river_m', 'dist_river_m', 'depression_m',
                          'built_share'))
