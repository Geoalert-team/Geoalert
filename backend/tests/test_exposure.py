import csv
import gzip
import io
import json
import tempfile
from pathlib import Path

import numpy as np
from django.test import SimpleTestCase

from apps.barangays.purok_estimate import BUILDINGS_INDEX, BUILDINGS_TILE
from apps.history import exposure
from apps.hazards.susceptibility import Grid
from apps.history.exposure import (EXPOSURE_COLUMNS, city_buildings, exposure_rows, noah_class_grid,
                                   noah_polygons, read_exposure, write_exposure)


class FakeResp:
    def __init__(self, content=b'', text=''):
        self.content, self.text = content, text

    def raise_for_status(self):
        pass


def building_line(x, y):
    d = 0.0001
    ring = [[x - d, y - d], [x + d, y - d], [x + d, y + d], [x - d, y + d], [x - d, y - d]]
    return json.dumps({'type': 'Feature', 'geometry': {'type': 'Polygon', 'coordinates': [ring]}})


class ExposureTests(SimpleTestCase):
    def test_exposure_counts_buildings_inside_each_layer(self):
        labels = np.array([[1, 1], [2, 2]]); counts = np.array([[3., 1.], [2., 0.]])
        noah25 = np.array([[2, 0], [3, 3]]); noah100 = np.array([[2, 2], [1, 3]]); hand = np.array([[1., 5.], [1., 1.]])
        rows = exposure_rows(labels, counts, noah25, noah100, hand, [1, 2])
        self.assertEqual(rows[1], {'buildings': 4, 'noah25_mh': 3, 'noah100_mh': 4, 'hand_lt2_buildings': 3,
                                   'exposure': (3 + 4 + 3) / 3})
        self.assertEqual(rows[2]['noah100_mh'], 0)        # Var 1 is Low, not Medium/High

    def test_noah_polygons_reads_var_and_clips_to_the_box(self):
        def square(x0, x1):
            return [[[x0, 0.0], [x1, 0.0], [x1, 1.0], [x0, 1.0], [x0, 0.0]]]
        gj = {'type': 'FeatureCollection', 'features': [
            {'type': 'Feature', 'properties': {'Var': 2},
             'geometry': {'type': 'MultiPolygon', 'coordinates': [square(0.0, 1.0)]}},
            {'type': 'Feature', 'properties': {'Var': 3},
             'geometry': {'type': 'MultiPolygon', 'coordinates': [square(1.5, 3.0)]}},
        ]}
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'noah.geojson'
            p.write_text(json.dumps(gj))
            # bbox = (south, west, north, east); the Var 3 square is half outside
            out = noah_polygons(str(p), (0.0, 0.0, 1.0, 2.0))
        self.assertEqual(sorted(v for v, _ in out), [2, 3])
        by_var = {v: rings for v, rings in out}
        xs = [x for x, _ in by_var[3][0]]
        self.assertAlmostEqual(min(xs), 1.5)
        self.assertAlmostEqual(max(xs), 2.0)
        self.assertAlmostEqual(max(x for x, _ in by_var[2][0]), 1.0)

    def test_round_trip_and_column_order(self):
        rows = {7: dict(buildings=10., noah25_mh=1., noah100_mh=2., hand_lt2_buildings=3., exposure=2.),
                3: dict(buildings=0., noah25_mh=0., noah100_mh=0., hand_lt2_buildings=0., exposure=0.)}
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'e.csv'
            write_exposure(p, rows, {7: 'Bulacao', 3: 'Zone 1'})
            header = next(csv.reader(open(p, encoding='utf-8')))
            self.assertEqual(header, ['barangay_id', 'barangay', *EXPOSURE_COLUMNS])
            self.assertEqual(read_exposure(p), {3: rows[3], 7: rows[7]})

    def test_buildings_never_overwrite_the_purok_cache(self):
        index = f'Location,QuadKey,Url\nPhilippines,{BUILDINGS_TILE},http://tile/x.gz\n'
        tile = gzip.compress((building_line(123.85, 10.25) + '\n' + building_line(124.9, 10.25) + '\n').encode())
        calls = []

        def get(url, **kw):
            calls.append(url)
            return FakeResp(text=index) if url == BUILDINGS_INDEX else FakeResp(content=tile)
        with tempfile.TemporaryDirectory() as d:
            cache = Path(d)
            purok = cache / f'ms_buildings_{BUILDINGS_TILE}.json'
            purok.write_bytes(b'[[1.0, 2.0]]')
            pts = city_buildings(cache, (10.2, 123.8, 10.3, 123.9), False, lambda m: None, get=get)
            self.assertEqual(len(pts), 1)
            self.assertEqual(purok.read_bytes(), b'[[1.0, 2.0]]')
            self.assertTrue((cache / f'ms_buildings_city_{BUILDINGS_TILE}.json').exists())
            n = len(calls)
            self.assertEqual(city_buildings(cache, (10.2, 123.8, 10.3, 123.9), False, lambda m: None, get=get), pts)
            self.assertEqual(len(calls), n)               # second run used the saved copy

    def test_download_noah_saves_once(self):
        calls = []

        def get(url, **kw):
            calls.append(url)
            return FakeResp(content=b'zip')
        with tempfile.TemporaryDirectory() as d:
            p = exposure.download_noah(Path(d), 25, False, lambda m: None, get=get)
            self.assertEqual(p.read_bytes(), b'zip')
            exposure.download_noah(Path(d), 25, False, lambda m: None, get=get)
        self.assertEqual(calls, [exposure.NOAH_URLS[25]])

    def test_class_grid_hole_only_removes_its_own_class(self):
        grid = Grid(10.0, 123.0, 10.01, 123.01, 14)
        w, s, e, n = 123.0, 10.0, 123.01, 10.01
        sq = lambda f: [(w + (e - w) * f[0], s + (n - s) * f[1]), (w + (e - w) * f[2], s + (n - s) * f[1]),
                        (w + (e - w) * f[2], s + (n - s) * f[3]), (w + (e - w) * f[0], s + (n - s) * f[3]),
                        (w + (e - w) * f[0], s + (n - s) * f[1])]
        high = (3, [sq((0.1, 0.1, 0.9, 0.9)), sq((0.4, 0.4, 0.6, 0.6))])      # square with a hole
        island = (2, [sq((0.4, 0.4, 0.6, 0.6))])                              # Medium in the hole
        for polys in ([high, island], [island, high]):
            out = noah_class_grid(grid, polys)
            cx, cy = (int(round(v)) for v in grid.to_cell((w + e) / 2, (s + n) / 2))
            rx, ry = (int(round(v)) for v in grid.to_cell(w + (e - w) * 0.2, s + (n - s) * 0.5))
            self.assertEqual(out[cy, cx], 2)
            self.assertEqual(out[ry, rx], 3)
            self.assertEqual(out[0, 0], 0)

    def test_noah_polygon_outside_the_box_gives_nothing(self):
        gj = {'type': 'FeatureCollection', 'features': [
            {'type': 'Feature', 'properties': {'Var': 3},
             'geometry': {'type': 'MultiPolygon', 'coordinates': [[[[5, 5], [6, 5], [6, 6], [5, 6], [5, 5]]]]}}]}
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'far.geojson'
            p.write_text(json.dumps(gj))
            self.assertEqual(noah_polygons(str(p), (0.0, 0.0, 1.0, 1.0)), [])

    def test_missing_tile_in_index_is_a_clear_error(self):
        get = lambda url, **kw: FakeResp(text='Location,QuadKey,Url\nPhilippines,999,http://x\n')
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(RuntimeError, BUILDINGS_TILE):
                city_buildings(Path(d), (0, 0, 1, 1), False, lambda m: None, get=get)
