"""
The landslide model's training table (plan Task 4): "no" points around each
event's slides, Mangkhut scars placed at their highest cell, the tile lattice,
the road check and the committed table (no coordinates, ODbL notice).
No network, no database.
"""
import io
import math
import shutil
import tempfile
from pathlib import Path
from unittest import mock

import numpy as np
from django.contrib.gis.geos import MultiPolygon, Polygon
from django.core.management import CommandError, call_command
from django.test import SimpleTestCase

from apps.hazards import susceptibility as sus
from apps.history import landslide_features as lf
from apps.history.fire_features import points_inside
from apps.history.landslide_features import FEATURE_COLUMNS, TERRAIN_COLUMNS
from apps.history.landslide_training_table import (NOTICE, TABLE_COLUMNS, event_no_points, read_table,
                                                   repair_outlines, road_check, sample_no_points, sampling_area,
                                                   scar_point, tiles_for, write_table)
from apps.history.management.commands import build_landslide_training
from tests.test_landslide_sources import Killed, killed_mid_write


def metres_between(lon1, lat1, lon2, lat2):
    """Great-circle metres (haversine), independent of the module's local projection."""
    p1, p2 = np.radians(lat1), np.radians(lat2)
    a = np.sin((p2 - p1) / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(np.radians(lon2 - lon1) / 2) ** 2
    return 2 * 6_371_008.8 * np.arcsin(np.sqrt(a))


class NoPointTests(SimpleTestCase):
    def test_no_points_keep_their_distances_and_count(self):
        slides = np.array([[0., 0.], [5000., 0.]])
        nop = sample_no_points(slides, per_slide=3, seed=0)
        self.assertEqual(len(nop), 6)
        d = np.min(np.hypot(*(nop[:, None, :] - slides[None]).transpose(2, 0, 1)), axis=1)
        self.assertTrue(((d >= 60) & (d <= 2000)).all())
        np.testing.assert_array_equal(nop, sample_no_points(slides, per_slide=3, seed=0))

    def test_no_points_never_fall_within_60_m_of_a_slide(self):  # many points, so a missing gap check would show
        slides = np.array([[0., 0.], [5000., 0.]])
        nop = sample_no_points(slides, per_slide=5000, seed=1)
        d = np.min(np.hypot(*(nop[:, None, :] - slides[None]).transpose(2, 0, 1)), axis=1)
        self.assertGreaterEqual(d.min(), 60)

    def test_no_points_are_uniform_over_overlapping_discs(self):  # 100 slides on one spot + 1 alone: about half each side
        slides = np.r_[np.zeros((100, 2)), [[10000., 0.]]]
        nop = sample_no_points(slides, per_slide=3, seed=0)
        near_lone = (np.hypot(nop[:, 0] - 10000, nop[:, 1]) < 2000).mean()
        self.assertGreater(near_lone, 0.35); self.assertLess(near_lone, 0.65)

    def test_event_no_points_are_measured_in_true_metres_east_and_north(self):
        # 50 slides 10 km apart at 45 N, where a degree of longitude is only 0.71 of a degree of latitude
        slides = np.c_[10.0 + np.arange(50) * 10_000 / (111_320 * math.cos(math.radians(45))), np.full(50, 45.0)]
        nop = event_no_points(slides, seed=0)
        self.assertEqual(len(nop), 150)
        np.testing.assert_array_equal(nop, event_no_points(slides, seed=0))
        d = metres_between(nop[:, None, 0], nop[:, None, 1], slides[None, :, 0], slides[None, :, 1])
        nearest = d.argmin(axis=1)
        self.assertTrue(((d.min(axis=1) >= 59) & (d.min(axis=1) <= 2005)).all())
        east = metres_between(nop[:, 0], 45.0, slides[nearest, 0], 45.0)
        north = metres_between(slides[nearest, 0], nop[:, 1], slides[nearest, 0], 45.0)
        self.assertGreater(east.max(), 1700); self.assertGreater(north.max(), 1700)


    def test_no_points_stay_off_every_mapped_slide_outline(self):  # R25: "no" is ground with no mapped slide
        kx = 111_320 * math.cos(math.radians(16.4))
        slides = np.c_[120.60 + np.arange(40) * 100 / kx, np.full(40, 16.40)]  # 40 scars 100 m apart
        west, east = slides[0, 0] - 300 / kx, slides[-1, 0] + 300 / kx
        south, north = 16.40 - 300 / 110_574, 16.40 + 300 / 110_574
        outline = Polygon([(west, south), (east, south), (east, north), (west, north), (west, south)], srid=4326)
        utm = outline.transform(32651, clone=True)  # Mangkhut's outlines come in UTM 51N
        nop = event_no_points(slides, seed=0, polygons=[utm])
        self.assertEqual(len(nop), 120)
        lon, lat = nop.T
        self.assertFalse(((lon > west) & (lon < east) & (lat > south) & (lat < north)).any())
        unfiltered = event_no_points(slides, seed=0)
        self.assertTrue(((unfiltered[:, 0] > west) & (unfiltered[:, 0] < east)
                         & (unfiltered[:, 1] > south) & (unfiltered[:, 1] < north)).any())  # the outline matters here

    def test_a_self_crossing_outline_is_repaired_not_fatal(self):  # 59 Mangkhut outlines cross themselves
        kx = 111_320 * math.cos(math.radians(16.4))
        slides = np.c_[120.60 + np.arange(40) * 100 / kx, np.full(40, 16.40)]
        west, east = slides[0, 0] - 300 / kx, slides[-1, 0] + 300 / kx
        south, north = 16.40 - 300 / 110_574, 16.40 + 300 / 110_574
        ring = [(west, south), (east, north), (east, south), (west, north), (west, south)]  # a bow-tie
        bow = Polygon(ring, srid=4326).transform(32651, clone=True)
        x, dx, dy = west + 500 / kx, 50 / kx, 50 / 110_574  # a second outline, in the western lobe: merging the two
        small = Polygon([(x - dx, 16.40 - dy), (x + dx, 16.40 - dy), (x + dx, 16.40 + dy), (x - dx, 16.40 + dy),
                         (x - dx, 16.40 - dy)], srid=4326).transform(32651, clone=True)  # fails on an unrepaired bow-tie
        nop = event_no_points(slides, seed=0, polygons=[bow, small])
        self.assertEqual(len(nop), 120)
        self.assertFalse(points_inside([[np.array(ring)]], nop).any())  # in neither lobe

    def test_repair_keeps_every_lobe_and_counts(self):
        bow = Polygon([(0, 0), (2, 2), (2, 0), (0, 2), (0, 0)], srid=4326)
        square = Polygon([(5, 5), (6, 5), (6, 6), (5, 6), (5, 5)], srid=4326)
        flat = Polygon([(7, 7), (8, 8), (9, 9), (7, 7)], srid=4326)  # no area at all
        outlines, repaired, dropped = repair_outlines([bow, square, flat])
        self.assertEqual((len(outlines), repaired, dropped), (2, 1, 1))
        self.assertEqual(outlines[0].geom_type, 'MultiPolygon')
        self.assertAlmostEqual(outlines[0].area, 2.0)  # both triangles kept (buffer(0) would keep one)
        self.assertEqual(outlines[1].wkb, square.wkb)    # a valid outline is left as it was
        self.assertTrue(all(o.srid == 4326 for o in outlines))

    def test_an_outline_that_collapses_to_a_line_or_a_point_is_dropped_not_fatal(self):
        there_and_back = Polygon([(0, 0), (1, 0), (0, 0), (1, 0), (0, 0)], srid=4326)  # make_valid: a LineString
        one_spot = Polygon([(1, 1), (1, 1), (1, 1), (1, 1)], srid=4326)                  # make_valid: a Point
        spiked = Polygon([(0, 0), (2, 2), (2, 0), (3, 0), (2, 0), (0, 2), (0, 0)], srid=4326)  # areas and a line
        outlines, repaired, dropped = repair_outlines([there_and_back, one_spot, spiked])
        self.assertEqual((len(outlines), repaired, dropped), (1, 1, 2))
        self.assertEqual(outlines[0].geom_type, 'MultiPolygon')
        self.assertAlmostEqual(outlines[0].area, 2.0)  # both lobes; the spike has no area


class ScarPointTests(SimpleTestCase):
    def setUp(self):
        self.grid = sus.Grid(10.25, 123.85, 10.27, 123.87, 14)
        rows, cols = np.mgrid[0:self.grid.height, 0:self.grid.width].astype(np.float32)
        self.slope_dem = 200 + 2.0 * cols - 3.0 * rows  # rises to the east and to the north (row 0)
        self.square_on_slope = self._square(10.2, 10.2, 19.8, 19.8)  # covers the centres of cells 10..19
        self.top_cell_centre_ll = self._ll(19.5, 10.5)               # its north-east cell, row 10, col 19

    def _ll(self, col, row):
        return sus.px_to_lnglat(self.grid.px0 + col, self.grid.py0 + row, self.grid.zoom)

    def _square(self, c0, r0, c1, r1):
        ring = [self._ll(c0, r0), self._ll(c1, r0), self._ll(c1, r1), self._ll(c0, r1), self._ll(c0, r0)]
        return Polygon(ring, srid=4326)

    def test_scar_point_is_the_highest_cell(self):
        self.assertEqual(scar_point(self.square_on_slope, self.grid, self.slope_dem), self.top_cell_centre_ll)

    def test_scar_point_reads_a_projected_polygon(self):  # the Mangkhut polygons come in UTM 51N
        utm = self.square_on_slope.transform(32651, clone=True)
        lon, lat = scar_point(utm, self.grid, self.slope_dem)
        self.assertAlmostEqual(lon, self.top_cell_centre_ll[0], places=9)
        self.assertAlmostEqual(lat, self.top_cell_centre_ll[1], places=9)

    def test_a_scar_smaller_than_a_cell_and_a_multipolygon(self):
        tiny = self._square(40.3, 30.3, 40.6, 30.6)  # no cell centre inside: the cell holding it
        self.assertEqual(scar_point(tiny, self.grid, self.slope_dem), self._ll(40.5, 30.5))
        two = MultiPolygon(self._square(50.2, 50.2, 52.8, 52.8), self._square(60.2, 40.2, 62.8, 42.8), srid=4326)
        self.assertEqual(scar_point(two, self.grid, self.slope_dem), self._ll(62.5, 40.5))  # the second part is higher

    def test_scar_point_of_a_repaired_self_crossing_outline(self):
        rows, cols = np.mgrid[0:self.grid.height, 0:self.grid.width].astype(np.float32)
        east_rising = 200 + 5.0 * cols - 0.1 * rows
        corners = [(10.2, 10.2), (30.9, 30.9), (30.9, 10.2), (10.2, 30.9), (10.2, 10.2)]  # lobes meet at 20.55
        bow = Polygon([self._ll(c, r) for c, r in corners], srid=4326)
        (fixed,), repaired, _ = repair_outlines([bow])
        self.assertEqual(repaired, 1)
        # the higher (eastern) lobe's top cell in column 30: row 10's centre is above its edge, row 11's inside
        self.assertEqual(scar_point(fixed, self.grid, east_rising), self._ll(30.5, 11.5))


class TileTests(SimpleTestCase):
    def setUp(self):
        rng = np.random.default_rng(1)
        self.points_ll = np.c_[rng.uniform(120.5, 120.85, 400), rng.uniform(17.3, 17.55, 400)]

    def test_every_point_in_one_tile_inner_square(self):
        t = tiles_for(self.points_ll)
        self.assertEqual(sorted(np.concatenate([x['index'] for x in t]).tolist()), list(range(len(self.points_ll))))
        for tile in t:
            south, west, north, east = tile['bbox_inner']
            lon, lat = self.points_ll[tile['index']].T
            eps = 1e-9
            self.assertTrue(((lon >= west - eps) & (lon <= east + eps) & (lat >= south - eps) & (lat <= north + eps)).all())

    def test_tiles_are_8_km_squares_with_a_2_km_pad(self):
        for tile in tiles_for(self.points_ll):
            south, west, north, east = tile['bbox_inner']
            o_south, o_west, o_north, o_east = tile['bbox_outer']
            kx = 111_320 * math.cos(math.radians((south + north) / 2))
            self.assertAlmostEqual((north - south) * 111_320, 8000, delta=1)
            self.assertAlmostEqual((east - west) * kx, 8000, delta=40)  # one cos for the event's mean latitude
            self.assertAlmostEqual((o_north - north) * 111_320, 2000, delta=1)
            self.assertAlmostEqual((south - o_south) * 111_320, 2000, delta=1)
            self.assertAlmostEqual((west - o_west) * kx, 2000, delta=1)
            self.assertAlmostEqual((o_east - east) * kx, 2000, delta=1)


class RoadCheckTests(SimpleTestCase):
    def test_an_event_keeps_roads_at_a_tenth_of_talisays_steep_density_or_more(self):
        self.assertEqual(road_check({'a': 0.5, 'b': 0.0999, 'c': 0.1}, 1.0), {'a': True, 'b': False, 'c': True})

    def test_the_sampling_area_is_near_a_slide_and_inside_the_inner_square(self):
        grid = sus.Grid(17.40, 120.60, 17.42, 120.62, 14)
        slide = sus.px_to_lnglat(grid.px0 + 100.5, grid.py0 + 100.5, 14)
        inner = (17.40, 120.60, 17.42, slide[0] + 0.001)  # the inner square ends about 106 m east of the slide
        cells = int(round(200 / grid.res))
        dem = np.full(grid.shape, 50.0, np.float32)
        dem[:, :100 - cells // 2] = 0.0                    # sea from about 100 m west of the slide
        mask = sampling_area(grid, np.array([slide]), inner, dem, radius_m=300)
        self.assertTrue(mask[100, 100])
        self.assertTrue(mask[100 - cells, 100])            # 200 m north: near, inside, land
        self.assertFalse(mask[100, 100 + cells])           # 200 m east: near, but past the inner square
        self.assertFalse(mask[100 + 2 * cells, 100])       # 400 m south: too far
        self.assertFalse(mask[100, 100 - cells])           # 200 m west: near and inside, but sea is not ground
        self.assertFalse(mask[dem <= 0].any())


class TableTests(SimpleTestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.rows = []
        for i, (event, fold, region, label) in enumerate([
                ('egay', 'egay', 'ph', 1), ('egay', 'egay', 'ph', 0), ('paeng', 'paeng', 'ph', 1),
                ('malawi_20230313', 'world', 'world', 1), ('malawi_20230313', 'world', 'world', 0)]):
            row = {'event': event, 'fold': fold, 'region': region, 'label': label,
                   'lon': 120.98321 + i, 'lat': 17.12345 + i}  # the command's points carry these; the table must not
            row.update({c: 1.5 + i + j / 10 for j, c in enumerate(FEATURE_COLUMNS)})
            row['noah_class'] = float(i % 4) if region == 'ph' else float('nan')
            self.rows.append(row)
        self.rows[1]['dist_road_m'] = float('nan')  # an event whose roads were dropped by the road check
        self.meta = {'seed': 0, 'landcover_ok': True, 'talisay_steep_road_density': 4.25,
                     'events': [{'key': 'egay', 'fold': 'egay', 'region': 'ph', 'slides': 1, 'no_points': 1,
                                 'landcover_year': 2022, 'road_kept': True}]}

    def test_training_table_has_no_coordinates(self):
        write_table(self.rows, self.meta, self.tmp / 't.csv', self.tmp / 't.json')
        text = (self.tmp / 't.csv').read_text(encoding='utf-8')
        head = text.splitlines()[1]
        self.assertEqual(head.split(','), list(TABLE_COLUMNS))  # line 0 is the ODbL notice
        self.assertNotIn('lat', head); self.assertNotIn('lon', head)
        self.assertIn(NOTICE, text.splitlines()[0])
        self.assertTrue(all(len(line.split(',')) == len(TABLE_COLUMNS) for line in text.splitlines()[2:]))
        meta_text = (self.tmp / 't.json').read_text(encoding='utf-8')
        for row in self.rows:  # two decimals: a prefix of any way the value could be written
            for value in (f"{row['lon']:.2f}", f"{row['lat']:.2f}"):
                self.assertNotIn(value, text); self.assertNotIn(value, meta_text)

    def test_read_table_gives_back_the_rows_and_meta(self):
        write_table(self.rows, self.meta, self.tmp / 't.csv', self.tmp / 't.json')
        table, meta = read_table(self.tmp / 't.csv', self.tmp / 't.json')
        self.assertEqual(meta, self.meta)
        self.assertEqual(set(table), set(TABLE_COLUMNS))
        self.assertEqual(table['event'].tolist(), [r['event'] for r in self.rows])
        self.assertEqual(table['fold'].tolist(), [r['fold'] for r in self.rows])
        self.assertEqual(table['label'].tolist(), [1, 0, 1, 1, 0])
        self.assertEqual(table['label'].dtype.kind, 'i')
        for c in FEATURE_COLUMNS + ('noah_class',):
            np.testing.assert_allclose(table[c], [r[c] for r in self.rows], rtol=1e-5, equal_nan=True)
        self.assertTrue(np.isnan(table['dist_road_m'][1]))
        self.assertTrue(np.isnan(table['noah_class'][3:]).all())

    def test_write_table_refuses_missing_terrain(self):  # one NaN terrain value would grey every Talisay point
        write_table(self.rows, self.meta, self.tmp / 't.csv', self.tmp / 't.json')
        before = (self.tmp / 't.csv').read_bytes()
        for column in TERRAIN_COLUMNS:
            bad = [dict(r) for r in self.rows]
            bad[2][column] = float('nan')
            with self.assertRaises(ValueError):
                write_table(bad, self.meta, self.tmp / 't.csv', self.tmp / 't.json')
        self.assertEqual((self.tmp / 't.csv').read_bytes(), before)  # the old table is left as it was
        self.assertEqual(sorted(p.name for p in self.tmp.iterdir()), ['t.csv', 't.json'])


AGATON = [(124.850, 10.750), (124.853, 10.750), (124.850, 10.753)]
FAR_AGATON = (125.250, 10.750)  # about 44 km east: its own tiles, with no road and no NOAH cover in the fakes
RWANDA = [(29.500, -1.900), (29.504, -1.900)]


def west_of(grid):
    return sus.px_to_lnglat(grid.px0, grid.py0, grid.zoom)[0]


class CommandTests(SimpleTestCase):
    """The command end to end on fake sources: no network, no database (zoom 12 keeps the tiles small)."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.cache, self.out = self.tmp / 'cache', self.tmp / 'out'
        self.grid_now = None
        coolr = [{'ev_date': '2022/04/10', 'ctry_name': 'Philippines', 'longitude': lon, 'latitude': lat}
                 for lon, lat in AGATON]
        coolr += [{'ev_date': '2023/05/03', 'ctry_name': 'Rwanda', 'longitude': lon, 'latitude': lat}
                  for lon, lat in RWANDA]
        self.coolr = coolr
        self.landcover_off = lambda grid: False  # which tiles' land cover cannot be read
        scar = Polygon([(251000, 1817000), (251030, 1817000), (251030, 1817030), (251000, 1817030), (251000, 1817000)],
                       srid=32651)
        real_terrain = lf.terrain_grids

        def dem_for(grid, cache, log=print):  # sea (height 0) under Agaton's second slide
            self.grid_now = grid
            rows, cols = np.mgrid[0:grid.height, 0:grid.width].astype(np.float32)
            dem = 500 - 0.5 * rows + 0.2 * cols
            c, r = (int(v) for v in grid.to_cell(*AGATON[1]))
            if 0 <= r < grid.height and 0 <= c < grid.width:
                dem[r, c] = 0.0
            return dem

        def terrain_with_a_hole(dem, res):  # a missing terrain value under Rwanda's first slide
            grids = real_terrain(dem, res)
            c, r = (int(v) for v in self.grid_now.to_cell(*RWANDA[0]))
            if 0 <= r < dem.shape[0] and 0 <= c < dem.shape[1]:
                grids['hand_m'][r, c] = np.nan
            return grids

        def roads(bbox, cache, log=print):  # roads in the Philippines west of 125 E only
            south, west, north, east = bbox
            return [[(west, south), (east, north)]] if 100 < west < 125.0 else []

        def landcover(grid, year, cache, log=print, fetch=None):
            return None if self.landcover_off(grid) else np.full(grid.shape, 2, np.uint8)

        def noah(grid, provinces, cache, log=print):  # class 2, but 0 east of 125 E (outside the listed provinces)
            return np.full(grid.shape, 0 if west_of(grid) > 125.0 else 2, np.uint8)

        for target, fake in [
                ('apps.history.landslide_inventories.read_coolr', lambda cache: coolr),
                ('apps.history.landslide_inventories.read_mangkhut', lambda cache: [scar]),
                ('apps.history.landslide_sources.dem_for', dem_for),
                ('apps.history.landslide_sources.roads', roads),
                ('apps.history.landslide_sources.landcover_classes', landcover),
                ('apps.history.landslide_sources.noah_landslide_grid', noah),
                ('apps.history.landslide_features.terrain_grids', terrain_with_a_hole)]:
            patcher = mock.patch(target, fake)
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = mock.patch.object(build_landslide_training, 'ZOOM', 12)
        patcher.start()
        self.addCleanup(patcher.stop)

    def run_command(self, *args):
        out = io.StringIO()
        call_command('build_landslide_training', '--cache-dir', str(self.cache), *args, stdout=out)
        return out.getvalue()

    def test_a_full_run_applies_the_road_check_and_drops_missing_terrain_and_sea(self):
        with mock.patch.object(build_landslide_training.Command, 'talisay_steep_density', return_value=0.1):
            printed = self.run_command('--output-dir', str(self.out))
        table, meta = read_table(self.out / 'landslide_training.csv', self.out / 'landslide_training.meta.json')
        events = table['event']
        self.assertEqual([e['key'] for e in meta['events']], ['mangkhut', 'agaton', 'rwanda_20230503'])
        self.assertEqual(int((events == 'agaton').sum()), 11)           # 3 slides, 9 "no" points, less the one at sea
        self.assertEqual(int((events == 'mangkhut').sum()), 4)          # 1 scar, 3 "no" points
        self.assertEqual(int((events == 'rwanda_20230503').sum()), 7)   # 8, less the one with no terrain
        by_key = {e['key']: e for e in meta['events']}
        self.assertEqual(by_key['rwanda_20230503']['dropped_missing_terrain'], 1)
        self.assertEqual((by_key['agaton']['dropped_at_sea_level'], by_key['agaton']['slides']), (1, 2))
        self.assertEqual(by_key['rwanda_20230503']['dropped_at_sea_level'], 0)
        self.assertIn('agaton: 2 slides, 9 no points, roads kept', printed)
        self.assertIn('0 dropped for a missing terrain clue; 1 dropped at sea level', printed)
        self.assertEqual((by_key['agaton']['road_kept'], by_key['rwanda_20230503']['road_kept']), (True, False))
        self.assertTrue(np.isfinite(table['dist_road_m'][events == 'agaton']).all())
        self.assertTrue(np.isnan(table['dist_road_m'][events == 'rwanda_20230503']).all())
        self.assertTrue((table['noah_class'][table['region'] == 'ph'] == 2).all())
        self.assertTrue(np.isnan(table['noah_class'][table['region'] == 'world']).all())
        self.assertEqual(table['fold'][events == 'rwanda_20230503'][0], 'world')
        self.assertEqual((meta['talisay_steep_road_density'], meta['landcover_ok'], meta['seed']), (0.1, True, 0))
        self.assertEqual(meta['road_check']['threshold'], 0.01)
        self.assertIn('rwanda_20230503: 1 slides, 6 no points, roads dropped', printed)
        self.assertNotIn(f'{AGATON[0][0]:.2f}', (self.out / 'landslide_training.csv').read_text(encoding='utf-8'))
        self.assertTrue(list(self.cache.glob('landslide_tile_agaton_*.npz')))  # a rerun resumes from these

    def add_far_agaton_slide(self):
        self.coolr.append({'ev_date': '2022/04/10', 'ctry_name': 'Philippines',
                           'longitude': FAR_AGATON[0], 'latitude': FAR_AGATON[1]})

    def test_a_tile_without_roads_or_noah_cover_is_counted_not_faked(self):  # I4.1, I4.4
        self.add_far_agaton_slide()
        with mock.patch.object(build_landslide_training.Command, 'talisay_steep_density', return_value=0.1):
            printed = self.run_command('--output-dir', str(self.out))
        table, meta = read_table(self.out / 'landslide_training.csv', self.out / 'landslide_training.meta.json')
        by_key = {e['key']: e for e in meta['events']}
        agaton = table['event'] == 'agaton'
        far = agaton & np.isnan(table['dist_road_m'])
        n_far = int(far.sum())  # the far slide and the "no" points around it (uniform over the discs' union)
        self.assertTrue(by_key['agaton']['road_kept'])
        self.assertEqual(int(table['label'][far].sum()), 1); self.assertGreaterEqual(n_far, 2)
        self.assertFalse((table['dist_road_m'] >= 1e6).any())   # never the 10,000 km "no road" placeholder
        np.testing.assert_array_equal(far[agaton], table['noah_class'][agaton] == 0)  # the same far tiles
        self.assertEqual(by_key['agaton']['road_unknown'], n_far)
        self.assertEqual((by_key['agaton']['noah_zero_slides'], by_key['agaton']['noah_zero_no_points']),
                         (1, n_far - 1))
        self.assertIsNone(by_key['rwanda_20230503']['noah_zero_slides'])
        self.assertIn(f'{n_far} on tiles with no road', printed)
        self.assertIn(f'NOAH class 0 at 1 slides and {n_far - 1} no points', printed)

    def test_land_cover_missing_on_some_tiles_stops_before_the_table_is_written(self):  # I4.2
        self.add_far_agaton_slide()
        self.landcover_off = lambda grid: west_of(grid) > 125.0  # the far tiles' reads fail (a timeout, say)
        with self.assertRaisesMessage(CommandError, 'have no land cover') as raised:
            self.run_command('--events', 'agaton', '--output-dir', str(self.out))
        # building without land cover needs the saved land cover gone too: each tile's is cached apart
        self.assertIn('landslide_tile_*.npz', str(raised.exception))
        self.assertIn('lulc_*.npz', str(raised.exception))
        self.assertFalse((self.out / 'landslide_training.csv').exists())
        self.assertTrue(list(self.cache.glob('landslide_tile_agaton_*.npz')))  # the tiles that read it are kept
        self.landcover_off = lambda grid: False
        printed = self.run_command('--events', 'agaton', '--output-dir', str(self.out))  # the rerun resumes
        self.assertIn('Using saved tile', printed)
        self.assertIn('Land cover read for every tile.', printed)
        self.assertTrue(read_table(self.out / 'landslide_training.csv', self.out / 'landslide_training.meta.json')[1]
                        ['landcover_ok'])

    def test_a_self_crossing_mangkhut_outline_is_repaired_and_counted(self):
        bow = Polygon([(251000, 1817000), (251040, 1817040), (251040, 1817000), (251000, 1817040), (251000, 1817000)],
                      srid=32651)
        flat = Polygon([(251500, 1817500), (251540, 1817540), (251500, 1817500), (251540, 1817540), (251500, 1817500)],
                       srid=32651)  # there and back: no area at all
        with mock.patch('apps.history.landslide_inventories.read_mangkhut', lambda cache: [bow, flat]):
            printed = self.run_command('--events', 'mangkhut', '--output-dir', str(self.out))
        table, meta = read_table(self.out / 'landslide_training.csv', self.out / 'landslide_training.meta.json')
        # repaired before the scar points too: the outline with no area gives no slide
        self.assertEqual((int(table['label'].sum()), int((table['label'] == 0).sum())), (1, 3))
        self.assertEqual((meta['events'][0]['outlines_repaired'], meta['events'][0]['outlines_dropped']), (1, 1))
        self.assertIn('mangkhut: 1 scar outlines (1 repaired, 1 with no area dropped)', printed)

    def test_land_cover_missing_everywhere_builds_the_table_without_it(self):
        self.landcover_off = lambda grid: True
        printed = self.run_command('--events', 'agaton', '--output-dir', str(self.out))
        table, meta = read_table(self.out / 'landslide_training.csv', self.out / 'landslide_training.meta.json')
        self.assertFalse(meta['landcover_ok'])
        for name in lf.LANDCOVER_CLASSES.values():
            self.assertTrue(np.isnan(table[name]).all())
        self.assertIn('could not be read', printed)

    def test_a_trial_needs_an_output_folder_and_skips_the_road_check(self):
        with self.assertRaises(CommandError):
            self.run_command('--events', 'agaton')
        with mock.patch.object(build_landslide_training.Command, 'talisay_steep_density') as talisay:
            self.run_command('--events', 'agaton', '--output-dir', str(self.out))
        talisay.assert_not_called()
        table, meta = read_table(self.out / 'landslide_training.csv', self.out / 'landslide_training.meta.json')
        self.assertEqual(set(table['event'].tolist()), {'agaton'})
        self.assertIsNone(meta['events'][0]['road_kept'])
        self.assertIn('skipped', meta['road_check'])
        self.assertTrue(np.isfinite(table['dist_road_m']).all())
        again = self.run_command('--events', 'agaton', '--output-dir', str(self.out))  # resumes from the saved tiles
        self.assertIn('Using saved tile', again); self.assertNotIn('Terrain clues', again)
        for path in self.cache.glob('landslide_tile_agaton_*.npz'):  # a tile saved by an older version of the command
            with np.load(path) as z:
                old = {k: z[k] for k in z.files if k != 'version'}
            np.savez_compressed(path, **old)
        stale = self.run_command('--events', 'agaton', '--output-dir', str(self.out))
        self.assertNotIn('Using saved tile', stale); self.assertIn('Terrain clues', stale)
        with mock.patch.dict(build_landslide_training.inv.EVENT_NOAH, {'agaton': ('Leyte',)}):  # its NOAH list changed
            relisted = self.run_command('--events', 'agaton', '--output-dir', str(self.out))
        self.assertNotIn('Using saved tile', relisted); self.assertIn('Terrain clues', relisted)
        self.assertEqual(read_table(self.out / 'landslide_training.csv', self.out / 'landslide_training.meta.json')[0]
                         ['slope_deg'].tolist(), table['slope_deg'].tolist())

    # Ruling R57 (the user's choice, 2026-11-25, to finish sooner): a real run over the Philippine typhoons only.
    # The road check still runs; the world events are named as left out, and none of their tiles is built
    def test_a_philippines_only_run_keeps_the_road_check_and_names_the_world_events_left_out(self):
        with mock.patch.object(build_landslide_training.Command, 'talisay_steep_density', return_value=0.1) as talisay:
            printed = self.run_command('--philippines-only', '--output-dir', str(self.out))
        talisay.assert_called_once()
        table, meta = read_table(self.out / 'landslide_training.csv', self.out / 'landslide_training.meta.json')
        self.assertEqual([e['key'] for e in meta['events']], ['mangkhut', 'agaton'])
        self.assertEqual(set(table['region'].tolist()), {'ph'})
        self.assertEqual(meta['world_left_out'], ['rwanda_20230503'])
        self.assertEqual(meta['road_check']['threshold'], 0.01)
        self.assertEqual({e['key']: e['road_kept'] for e in meta['events']}, {'mangkhut': True, 'agaton': True})
        self.assertEqual(list(self.cache.glob('landslide_tile_rwanda_*')), [])
        self.assertIn('Philippine typhoons only', printed)
        self.assertIn('rwanda_20230503', printed)
        with self.assertRaises(CommandError):  # a trial already picks its events
            self.run_command('--philippines-only', '--events', 'agaton', '--output-dir', str(self.out))

    def test_a_full_run_leaves_no_world_event_out(self):
        with mock.patch.object(build_landslide_training.Command, 'talisay_steep_density', return_value=0.1):
            self.run_command('--output-dir', str(self.out))
        _, meta = read_table(self.out / 'landslide_training.csv', self.out / 'landslide_training.meta.json')
        self.assertEqual(meta['world_left_out'], [])
        self.assertFalse(meta['saved_tiles_only'])
        self.assertEqual({(e['tiles_left_out'], e['points_left_out']) for e in meta['events']}, {(0, 0)})

    # Ruling R59 (the user's choice, 2026-11-25: minutes, not hours): only tiles already saved are used; a tile not
    # saved is not built, and its points are left out and counted, not reported as dropped for a missing clue
    def test_saved_tiles_only_leaves_unsaved_tiles_out_and_builds_none(self):
        with mock.patch.object(build_landslide_training.Command, 'talisay_steep_density', return_value=0.1):
            self.run_command('--philippines-only', '--output-dir', str(self.out))
        full, _ = read_table(self.out / 'landslide_training.csv', self.out / 'landslide_training.meta.json')
        gone = sorted(self.cache.glob('landslide_tile_agaton_*.npz'))[0]
        gone.unlink()
        with mock.patch.object(build_landslide_training.Command, 'talisay_steep_density', return_value=0.1):
            printed = self.run_command('--philippines-only', '--saved-tiles-only', '--output-dir', str(self.out))
        table, meta = read_table(self.out / 'landslide_training.csv', self.out / 'landslide_training.meta.json')
        by_key = {e['key']: e for e in meta['events']}
        self.assertTrue(meta['saved_tiles_only'])
        self.assertEqual(by_key['agaton']['tiles_left_out'], 1)
        self.assertGreater(by_key['agaton']['points_left_out'], 0)
        self.assertEqual(by_key['agaton']['dropped_missing_terrain'], 0)
        self.assertEqual((by_key['mangkhut']['tiles_left_out'], by_key['mangkhut']['points_left_out']), (0, 0))
        self.assertEqual(int((table['event'] == 'mangkhut').sum()), int((full['event'] == 'mangkhut').sum()))
        self.assertLess(int((table['event'] == 'agaton').sum()), int((full['event'] == 'agaton').sum()))
        self.assertFalse(gone.exists())  # not built again
        self.assertIn('left out (--saved-tiles-only)', printed)
        self.assertNotIn('Terrain clues', printed)

    # Final review B2: a tile a killed run left cut short stopped every rerun (BadZipFile, naming no file)
    def test_a_cut_short_saved_tile_is_named_deleted_and_built_again(self):
        self.add_far_agaton_slide()  # two tiles: one is broken, the other reused
        self.run_command('--events', 'agaton', '--output-dir', str(self.out))
        table = read_table(self.out / 'landslide_training.csv', self.out / 'landslide_training.meta.json')[0]
        tiles = sorted(self.cache.glob('landslide_tile_agaton_*.npz'))
        self.assertGreaterEqual(len(tiles), 2)
        broken = tiles[0]
        data = broken.read_bytes()
        broken.write_bytes(data[:len(data) // 2])
        again = self.run_command('--events', 'agaton', '--output-dir', str(self.out))
        self.assertIn(broken.name, again)
        self.assertEqual(again.count('Terrain clues'), 1)  # only the broken tile is built again
        self.assertEqual(again.count('Using saved tile'), len(tiles) - 1)
        with np.load(broken) as z:
            self.assertEqual(int(z['version']), build_landslide_training.TILE_VERSION)  # saved whole again
        rebuilt = read_table(self.out / 'landslide_training.csv', self.out / 'landslide_training.meta.json')[0]
        self.assertEqual(rebuilt['slope_deg'].tolist(), table['slope_deg'].tolist())

    def test_a_tile_write_stopped_part_way_leaves_no_tile(self):
        with mock.patch('numpy.savez_compressed', killed_mid_write), self.assertRaises(Killed):
            self.run_command('--events', 'agaton', '--output-dir', str(self.out))
        self.assertEqual([p.name for p in self.cache.iterdir() if 'landslide_tile_' in p.name], [])
