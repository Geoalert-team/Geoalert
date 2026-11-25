"""Landslide model sources: land cover, NOAH landslide classes, roads, DEM. No network."""
import json
import shutil
import tempfile
import zipfile
from datetime import date
from pathlib import Path
from unittest import mock

import numpy as np
from django.test import SimpleTestCase

from apps.hazards import susceptibility as sus
from apps.history import landslide_sources as ls
from apps.history.landslide_inventories import EVENT_NOAH


def failing_fetch(*args, **kwargs):
    raise OSError('blob cannot be range-read')


def quiet(*_):
    pass


class OverpassAnswer:
    """A fake HTTP answer: `payload` is what .json() gives, or an exception it raises (a body that is not JSON)."""

    def __init__(self, payload, status_code=200):
        self.payload, self.status_code = payload, status_code

    def json(self):
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload


class OverpassSession:
    """Gives its answers in turn; an exception in the list is raised by post (a timeout, a dropped connection)."""

    def __init__(self, answers):
        self.answers = list(answers)

    def post(self, url, data=None, timeout=None):
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer if isinstance(answer, OverpassAnswer) else OverpassAnswer(answer)


class LandslideSourcesTests(SimpleTestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.grid = sus.Grid(10.25, 123.85, 10.30, 123.90, 14)

    def _square(self, r0, c0, r1, c1):
        """One polygon (a list of rings) covering cells r0..r1-1 by c0..c1-1."""
        a = sus.px_to_lnglat(self.grid.px0 + c0, self.grid.py0 + r0, 14)
        b = sus.px_to_lnglat(self.grid.px0 + c1, self.grid.py0 + r1, 14)
        return [[(a[0], a[1]), (b[0], a[1]), (b[0], b[1]), (a[0], b[1]), (a[0], a[1])]]

    def test_utm_tiles_and_years(self):
        self.assertEqual(ls.utm_tile(123.85, 10.25), '51P')
        self.assertEqual(ls.utm_tile(120.9, 17.5), '51Q')
        self.assertEqual(ls.utm_tile(124.2, 6.9), '51N')
        self.assertEqual(ls.landcover_year_for(date(2018, 9, 14)), 2017)
        self.assertEqual(ls.landcover_year_for(date(2017, 5, 1)), 2017)
        self.assertEqual(ls.landcover_year_for(date(2023, 7, 26)), 2022)

    def test_noah_grid_keeps_the_highest_class(self):
        a = self._square(10, 10, 30, 30)
        b = self._square(20, 20, 40, 40)
        g = ls.noah_landslide_grid_from({1: [a], 3: [b]}, self.grid)
        self.assertEqual(g.dtype, np.uint8)
        self.assertEqual(g[25, 25], 3)   # overlap: the higher class wins
        self.assertEqual(g[15, 15], 1)
        self.assertEqual(g[35, 35], 3)
        self.assertEqual(g[2, 2], 0)     # outside every polygon

    def test_noah_grid_high_class_wins_whatever_the_order(self):
        a = self._square(10, 10, 30, 30)
        b = self._square(20, 20, 40, 40)
        g = ls.noah_landslide_grid_from({3: [b], 2: [a]}, self.grid)
        self.assertEqual(g[25, 25], 3)
        self.assertEqual(g[12, 12], 2)

    def test_noah_reader_rejects_unsafe_zip_member(self):
        path = self.tmp / 'Evil.zip'
        with zipfile.ZipFile(path, 'w') as z:
            z.writestr('../escape.shp', b'x')
        with self.assertRaisesRegex(RuntimeError, 'unsafe'):
            ls.noah_landslide_polygons(path, (123.85, 10.25, 123.90, 10.30))

    def test_noah_provinces(self):
        self.assertTrue({'Cebu', 'Benguet', 'Abra', 'SouthernLeyte'} <= set(ls.NOAH_LANDSLIDE))
        with self.assertRaises(ValueError):
            ls.noah_landslide_grid(self.grid, ('Atlantis',), self.tmp)

    def test_every_noah_province_is_pinned_and_fetched_verified(self):
        used = {p for provinces in EVENT_NOAH.values() for p in provinces} | {'Cebu'}  # the events' and Talisay's
        self.assertEqual(set(ls.NOAH_LANDSLIDE), used)
        self.assertEqual(len(ls.NOAH_LANDSLIDE), 13)  # R26 added Apayao, Kalinga, MountainProvince, SultanKudarat
        for province, sha in ls.NOAH_LANDSLIDE.items():
            self.assertRegex(sha, r'^[0-9a-f]{64}$', province)
        with mock.patch.object(ls.downloads, 'fetch_verified', return_value=self.tmp / 'x.zip') as fv:
            ls.fetch_noah_landslide('Cebu', self.tmp)
        url, sha, dest = fv.call_args[0]
        self.assertTrue(url.endswith('/Landslide/LandslideHazards/Cebu.zip'))
        self.assertEqual(sha, ls.NOAH_LANDSLIDE['Cebu'])
        self.assertEqual(dest, self.tmp / 'noah_landslide_Cebu.zip')

    def test_noah_grid_merges_provinces_from_the_reader(self):
        """With the zip fetch and the reader stubbed, the grid is painted from the merged polygons."""
        province = next(iter(ls.NOAH_LANDSLIDE))
        zip_path = self.tmp / f'{province}.zip'
        zip_path.write_bytes(b'placeholder')
        polys = {2: [self._square(5, 5, 15, 15)]}
        with mock.patch.object(ls, 'fetch_noah_landslide', return_value=zip_path), \
                mock.patch.object(ls, 'noah_landslide_polygons', return_value=polys):
            g = ls.noah_landslide_grid(self.grid, (province,), self.tmp)
        self.assertEqual(g[10, 10], 2)
        self.assertEqual(g[30, 30], 0)

    def test_unreadable_landcover_is_none_not_an_error(self):
        self.assertIsNone(ls.landcover_classes(self.grid, 2022, self.tmp, log=quiet, fetch=failing_fetch))
        self.assertEqual(list(self.tmp.glob('lulc_*')), [])  # a failure is never cached

    def test_landcover_samples_cell_centres_and_caches(self):
        seen = []

        def fetch(url, xs, ys):
            seen.append((url, len(xs)))
            return np.full(len(xs), 2, np.uint8)

        out = ls.landcover_classes(self.grid, 2022, self.tmp, log=quiet, fetch=fetch)
        self.assertEqual(out.shape, self.grid.shape)
        self.assertTrue((out == 2).all())
        self.assertIn('lc2022/51P_20220101-20230101.tif', seen[0][0])
        self.assertEqual(sum(n for _, n in seen), out.size)
        again = ls.landcover_classes(self.grid, 2022, self.tmp, log=quiet, fetch=failing_fetch)  # cached
        self.assertTrue((again == 2).all())

    def test_landcover_utm_coordinates_are_plausible(self):
        got = {}

        def fetch(url, xs, ys):
            got['x'], got['y'] = xs.copy(), ys.copy()
            return np.zeros(len(xs), np.uint8)

        ls.landcover_classes(self.grid, 2022, self.tmp, log=quiet, fetch=fetch)
        # Talisay in UTM 51N: easting about 5e5, northing about 1.13e6
        self.assertTrue(((got['x'] > 3.5e5) & (got['x'] < 6.5e5)).all())
        self.assertTrue(((got['y'] > 1.1e6) & (got['y'] < 1.16e6)).all())

    def test_road_density(self):
        # one 1 km east-west road across a 1 km x 1 km mask
        r0, c0 = 30, 30
        n = int(round(1000 / self.grid.res))
        mask = np.zeros(self.grid.shape, bool)
        mask[r0:r0 + n, c0:c0 + n] = True
        west = sus.px_to_lnglat(self.grid.px0 + c0, self.grid.py0 + r0 + n / 2, 14)
        east = sus.px_to_lnglat(self.grid.px0 + c0 + n, self.grid.py0 + r0 + n / 2, 14)
        road = [west, east]
        self.assertAlmostEqual(ls.road_density_km_per_km2(self.grid, [road], mask), 1.0, delta=0.1)
        self.assertEqual(ls.road_density_km_per_km2(self.grid, [], mask), 0.0)
        self.assertEqual(ls.road_density_km_per_km2(self.grid, [road], np.zeros(self.grid.shape, bool)), 0.0)

    def test_roads_query_is_roads_only_and_cached(self):
        elements = [
            {'type': 'way', 'tags': {'highway': 'residential'},
             'geometry': [{'lon': 123.85, 'lat': 10.25}, {'lon': 123.86, 'lat': 10.26}]},
            {'type': 'way', 'tags': {'highway': 'footway'},
             'geometry': [{'lon': 123.85, 'lat': 10.25}, {'lon': 123.86, 'lat': 10.26}]},
            {'type': 'way', 'tags': {'highway': 'primary'}, 'geometry': [{'lon': 123.85, 'lat': 10.25}]},
        ]
        bbox = (10.25, 123.85, 10.30, 123.90)
        with mock.patch.object(ls, 'overpass_elements', return_value=elements) as op:
            lines = ls.roads(bbox, self.tmp, log=quiet)
            query = op.call_args[0][0]
        self.assertEqual(len(lines), 1)
        self.assertIn('highway', query)
        for other in ('waterway', 'building', 'landuse', 'coastline'):
            self.assertNotIn(other, query)
        self.assertEqual(len(list(self.tmp.glob('osm_roads_*.json'))), 1)
        with mock.patch.object(ls, 'overpass_elements', side_effect=AssertionError('network')):
            self.assertEqual(ls.roads(bbox, self.tmp, log=quiet), lines)

    def test_an_overpass_answer_with_an_error_remark_is_retried_and_never_cached(self):
        way = {'type': 'way', 'tags': {'highway': 'residential'},
               'geometry': [{'lon': 123.85, 'lat': 10.25}, {'lon': 123.86, 'lat': 10.26}]}
        timed_out = {'remark': 'runtime error: Query timed out in "query" at line 1 after 240 seconds.',
                     'elements': [way]}  # partial: Overpass stopped part way
        whole = {'elements': [way, way]}
        bbox = (10.25, 123.85, 10.30, 123.90)
        with mock.patch.object(ls.time, 'sleep'):
            with mock.patch.object(sus, 'make_session',
                                   return_value=OverpassSession([timed_out] * 2 * len(sus.OVERPASS_URLS))):
                with self.assertRaises(RuntimeError):
                    ls.roads(bbox, self.tmp, log=quiet)
            self.assertFalse(list(self.tmp.glob('osm_roads_*.json')))  # nothing cached: a rerun asks again
            with mock.patch.object(sus, 'make_session', return_value=OverpassSession([timed_out, whole])):
                self.assertEqual(len(ls.roads(bbox, self.tmp, log=quiet)), 2)  # retried; the whole answer is kept
        self.assertEqual(len(list(self.tmp.glob('osm_roads_*.json'))), 1)

    def test_only_a_whole_overpass_answer_can_say_a_tile_has_no_road(self):
        """
        A failed download never becomes "no road" (a NaN road distance): every failure
        is retried on each server, then raises, and nothing is cached. Only a 200 whose
        JSON object holds an "elements" list and no error remark is an answer.
        """
        import requests

        attempts = 2 * len(sus.OVERPASS_URLS)
        failures = {
            'busy (502)': OverpassAnswer('<html>502</html>', status_code=502),
            'timed out': requests.Timeout('Read timed out.'),
            'connection dropped': requests.ConnectionError('Connection aborted.'),
            'a body that is not JSON': OverpassAnswer(ValueError('Expecting value: line 1 column 1')),
            'a JSON object with no elements': {},
            'an error object': {'error': 'rate limited'},
            'a JSON list': [],
            'elements that are not a list': {'elements': None},
        }
        bbox = (10.25, 123.85, 10.30, 123.90)
        with mock.patch.object(ls.time, 'sleep'):
            for i, (name, failure) in enumerate(failures.items()):
                with self.subTest(name):
                    cache = self.tmp / f'case{i}'
                    with mock.patch.object(sus, 'make_session', return_value=OverpassSession([failure] * attempts)):
                        with self.assertRaisesRegex(RuntimeError, 'OpenStreetMap download failed'):
                            ls.roads(bbox, cache, log=quiet)
                    self.assertFalse(list(cache.glob('osm_roads_*.json')))  # never cached as "no road"
            empty = {'version': 0.6, 'generator': 'Overpass API', 'osm3s': {}, 'elements': []}
            with mock.patch.object(sus, 'make_session', return_value=OverpassSession([{}, empty])):
                self.assertEqual(ls.roads(bbox, self.tmp, log=quiet), [])  # a whole answer with no way: no road
        self.assertEqual([p.read_text() for p in self.tmp.glob('osm_roads_*.json')], ['[]'])

    def test_dem_for_uses_the_saved_file(self):
        tag = f'z{self.grid.zoom}_{self.grid.px0}_{self.grid.py0}_{self.grid.width}x{self.grid.height}'
        np.save(self.tmp / f'dem_cop30_{tag}.npy', np.full(self.grid.shape, 7, np.float32))
        with mock.patch.object(sus, 'fetch_copernicus', side_effect=AssertionError('network')):
            out = ls.dem_for(self.grid, self.tmp, log=quiet)
        self.assertTrue((out == 7).all())

    def test_dem_for_flat_download_is_refused_and_not_cached(self):
        with mock.patch.object(sus, 'fetch_copernicus', return_value=np.zeros(self.grid.shape, np.float32)):
            with self.assertRaisesRegex(RuntimeError, 'No ground above sea level'):
                ls.dem_for(self.grid, self.tmp, log=quiet)
        self.assertEqual(list(self.tmp.glob('dem_cop30_*')), [])

    def test_dem_for_downloads_once_and_caches(self):
        good = np.full(self.grid.shape, 50, np.float32)
        with mock.patch.object(sus, 'fetch_copernicus', return_value=good) as fc:
            ls.dem_for(self.grid, self.tmp, log=quiet)
            ls.dem_for(self.grid, self.tmp, log=quiet)
        self.assertEqual(fc.call_count, 1)
        self.assertEqual(len(list(self.tmp.glob('dem_cop30_*.npy'))), 1)

    def test_dem_for_turns_missing_heights_into_sea_level_before_caching(self):
        dem = np.full(self.grid.shape, 50, np.float32)
        dem[:5, :5] = np.nan
        dem[10, 10] = np.inf
        with mock.patch.object(sus, 'fetch_copernicus', return_value=dem):
            out = ls.dem_for(self.grid, self.tmp, log=quiet)
        self.assertTrue(np.isfinite(out).all())
        self.assertEqual(out[0, 0], 0)
        self.assertEqual(out[10, 10], 0)
        saved = np.load(next(self.tmp.glob('dem_cop30_*.npy')))
        self.assertTrue(np.isfinite(saved).all())

    def test_dem_for_all_missing_heights_is_refused(self):
        with mock.patch.object(sus, 'fetch_copernicus', return_value=np.full(self.grid.shape, np.nan, np.float32)):
            with self.assertRaisesRegex(RuntimeError, 'No ground above sea level'):
                ls.dem_for(self.grid, self.tmp, log=quiet)

    def _noah_zip(self, name='Test.zip', field='HAZ'):
        """A real shapefile (UTM 51N, written by hand) with HAZ 3, HAZ 0 and HAZ 2, zipped."""
        import struct
        cx, cy = 5.0e5, 1.13e6  # Talisay area in UTM 51N
        shapes = [
            (3, [(cx, cy), (cx, cy + 2000), (cx + 2000, cy + 2000), (cx + 2000, cy), (cx, cy)]),  # clockwise
            (0, [(cx + 5000, cy), (cx + 5000, cy + 1000), (cx + 6000, cy + 1000), (cx + 5000, cy)]),
            (2, [(cx + 3000, cy), (cx + 3000, cy + 1000), (cx + 4000, cy + 1000), (cx + 3000, cy)]),
        ]
        records, index, offset = b'', b'', 50
        for i, (_, pts) in enumerate(shapes, 1):
            xs, ys = [p[0] for p in pts], [p[1] for p in pts]
            body = struct.pack('<i4d2i', 5, min(xs), min(ys), max(xs), max(ys), 1, len(pts)) + struct.pack('<i', 0)
            body += b''.join(struct.pack('<2d', *p) for p in pts)
            records += struct.pack('>2i', i, len(body) // 2) + body
            index += struct.pack('>2i', offset, len(body) // 2)
            offset += 4 + len(body) // 2
        allx = [p[0] for _, pts in shapes for p in pts]
        ally = [p[1] for _, pts in shapes for p in pts]

        def header(words):
            return (struct.pack('>7i', 9994, 0, 0, 0, 0, 0, words) +
                    struct.pack('<2i8d', 1000, 5, min(allx), min(ally), max(allx), max(ally), 0, 0, 0, 0))

        shp = header(offset) + records
        shx = header(50 + 4 * len(shapes)) + index
        # header: version, date, records, header length, record length; one class field (numeric, 3 wide)
        dbf = struct.pack('<4BIHH20x', 3, 126, 11, 26, len(shapes), 65, 4)
        dbf += field.encode().ljust(11, b'\0') + b'N' + b'\0' * 4 + struct.pack('<BB', 3, 0) + b'\0' * 14 + b'\r'
        for haz, _ in shapes:
            dbf += b' ' + str(haz).rjust(3).encode()
        dbf += b'\x1a'
        prj = (b'PROJCS["WGS 84 / UTM zone 51N",GEOGCS["WGS 84",DATUM["WGS_1984",SPHEROID["WGS 84",6378137,298.257223563]],'
               b'PRIMEM["Greenwich",0],UNIT["degree",0.0174532925199433]],PROJECTION["Transverse_Mercator"],'
               b'PARAMETER["latitude_of_origin",0],PARAMETER["central_meridian",123],PARAMETER["scale_factor",0.9996],'
               b'PARAMETER["false_easting",500000],PARAMETER["false_northing",0],UNIT["metre",1]]')
        path = self.tmp / name
        with zipfile.ZipFile(path, 'w') as z:
            for ext, data in (('shp', shp), ('shx', shx), ('dbf', dbf), ('prj', prj)):
                z.writestr(f'hz.{ext}', data)
        return path

    def test_noah_reader_reads_classes_reprojects_and_clips(self):
        from django.contrib.gis.gdal import CoordTransform, OGRGeometry, SpatialReference
        path = self._noah_zip()
        pt = OGRGeometry('POINT (500500 1130500)', srs=32651)
        pt.transform(CoordTransform(SpatialReference(32651), SpatialReference(4326)))
        lng, lat = pt.x, pt.y
        full = (lng - 0.5, lat - 0.5, lng + 0.5, lat + 0.5)
        got = ls.noah_landslide_polygons(path, full)
        self.assertEqual(sorted(got), [2, 3])  # the HAZ 0 shape is skipped
        # a box around the first polygon's corner only keeps that corner of it
        small = (lng - 0.0045, lat - 0.0045, lng + 0.0045, lat + 0.0045)
        ring = ls.noah_landslide_polygons(path, small)[3][0][0]
        self.assertTrue(all(small[0] - 1e-9 <= x <= small[2] + 1e-9 and small[1] - 1e-9 <= y <= small[3] + 1e-9
                            for x, y in ring))
        # the extracted folder is complete and a second read reuses it
        self.assertTrue((self.tmp / 'Test' / '.complete').exists())
        self.assertEqual(sorted(ls.noah_landslide_polygons(path, full)), [2, 3])

    def test_noah_reader_repairs_a_shape_that_will_not_clip(self):
        from django.contrib.gis.geos import GEOSGeometry
        from django.contrib.gis.geos.error import GEOSException
        real = GEOSGeometry.intersection
        calls = []

        def flaky(this, other):
            calls.append(1)
            if len(calls) == 1:
                raise GEOSException('TopologyException')
            return real(this, other)

        path = self._noah_zip()
        with mock.patch.object(GEOSGeometry, 'intersection', flaky):
            got = ls.noah_landslide_polygons(path, (122.0, 9.0, 125.0, 12.0))
        self.assertEqual(sorted(got), [2, 3])
        self.assertGreater(len(calls), 2)  # the failed clip was repaired and retried

    # Final review B5: the shapes the reader skips are counted in the command's log, not printed past it
    def test_skipped_noah_shapes_are_counted_in_the_log(self):
        from django.contrib.gis.geos import GEOSGeometry
        from django.contrib.gis.geos.error import GEOSException

        def never(this, other):
            raise GEOSException('TopologyException')

        path = self._noah_zip()
        lines = []
        with mock.patch.object(GEOSGeometry, 'intersection', never), mock.patch('builtins.print') as printed:
            got = ls.noah_landslide_polygons(path, (122.0, 9.0, 125.0, 12.0), log=lines.append)
        self.assertEqual(got, {})
        self.assertEqual(lines, ['  NOAH Test: skipped 2 unusable shapes'])  # HAZ 3 and HAZ 2; HAZ 0 is no class
        printed.assert_not_called()
        lines.clear()
        with mock.patch.object(ls, 'fetch_noah_landslide', return_value=path), \
                mock.patch.object(GEOSGeometry, 'intersection', never), mock.patch('builtins.print') as printed:
            ls.noah_landslide_grid(self.grid, ('Cebu',), self.tmp, log=lines.append)  # hands its log down
        self.assertEqual(lines, ['  NOAH Test: skipped 2 unusable shapes'])
        printed.assert_not_called()

    def test_noah_reader_accepts_the_lh_field_name_of_the_real_files(self):
        path = self._noah_zip('Real.zip', field='LH')
        self.assertEqual(sorted(ls.noah_landslide_polygons(path, (122.0, 9.0, 125.0, 12.0))), [2, 3])

    def test_noah_reader_without_a_class_field_says_so(self):
        path = self._noah_zip('Odd.zip', field='ZONE')
        with self.assertRaisesRegex(RuntimeError, 'class fields'):
            ls.noah_landslide_polygons(path, (122.0, 9.0, 125.0, 12.0))

    def test_noah_reader_redoes_an_interrupted_extraction(self):
        path = self._noah_zip()
        half = self.tmp / 'Test'
        half.mkdir()
        (half / 'hz.shp').write_bytes(b'truncated')  # a leftover without its .dbf and no marker
        got = ls.noah_landslide_polygons(path, (122.0, 9.0, 125.0, 12.0))
        self.assertIn(3, got)

    def test_dem_for_scrubs_a_saved_file_written_by_load_inputs(self):
        tag = f'z{self.grid.zoom}_{self.grid.px0}_{self.grid.py0}_{self.grid.width}x{self.grid.height}'
        raw = np.full(self.grid.shape, 7, np.float32)
        raw[0, 0] = np.nan
        np.save(self.tmp / f'dem_cop30_{tag}.npy', raw)
        out = ls.dem_for(self.grid, self.tmp, log=quiet)
        self.assertTrue(np.isfinite(out).all())
        self.assertEqual(out[0, 0], 0)


class Killed(BaseException):
    """A run stopped part way through a write (no `except Exception` catches it)."""


def killed_mid_write(file, *args, **kwargs):
    """numpy.save / savez_compressed stopped after a few bytes, whatever it was handed (a path or a file)."""
    if hasattr(file, 'write'):
        file.write(b'PK\x03\x04 cut short')
    else:
        Path(file).write_bytes(b'PK\x03\x04 cut short')
    raise Killed


class SavedFileTests(SimpleTestCase):
    """
    Final review B2: a run killed part way through writing a cache file left it
    cut short, and every rerun then died on it (BadZipFile, ValueError,
    JSONDecodeError, EOFError) without naming it. Each file is now written
    whole or not at all, and one that cannot be read is named, deleted and
    built again.
    """

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.grid = sus.Grid(10.25, 123.85, 10.30, 123.90, 14)
        self.tag = f'z{self.grid.zoom}_{self.grid.px0}_{self.grid.py0}_{self.grid.width}x{self.grid.height}'
        self.bbox = (10.25, 123.85, 10.30, 123.90)
        self.way = {'type': 'way', 'tags': {'highway': 'residential'},
                    'geometry': [{'lon': 123.86, 'lat': 10.26}, {'lon': 123.87, 'lat': 10.27}]}

    @staticmethod
    def cut_short(path):
        data = path.read_bytes()
        path.write_bytes(data[:len(data) // 2])

    def names(self):
        return sorted(p.name for p in self.tmp.iterdir())

    def test_a_write_stopped_part_way_leaves_the_old_file_or_none(self):
        target = self.tmp / 'x.npy'

        def stopped(f):
            f.write(b'\x93NUMPY cut')
            raise Killed

        with self.assertRaises(Killed):
            ls.save_atomically(target, stopped)
        self.assertEqual(self.names(), [])  # neither the file nor its temporary one
        ls.save_atomically(target, lambda f: np.save(f, np.arange(3)))
        before = target.read_bytes()
        with self.assertRaises(Killed):
            ls.save_atomically(target, stopped)
        self.assertEqual((self.names(), target.read_bytes()), (['x.npy'], before))
        np.testing.assert_array_equal(np.load(target), np.arange(3))

    def test_a_cut_short_saved_dem_is_named_deleted_and_fetched_again(self):
        with mock.patch.object(sus, 'fetch_copernicus', return_value=np.full(self.grid.shape, 50, np.float32)):
            ls.dem_for(self.grid, self.tmp, log=quiet)
        saved = self.tmp / f'dem_cop30_{self.tag}.npy'
        self.cut_short(saved)
        lines = []
        with mock.patch.object(sus, 'fetch_copernicus', return_value=np.full(self.grid.shape, 60, np.float32)) as fc:
            out = ls.dem_for(self.grid, self.tmp, log=lines.append)
        self.assertEqual(fc.call_count, 1)
        self.assertTrue((out == 60).all())
        self.assertTrue(any(saved.name in line for line in lines), lines)
        self.assertTrue((np.load(saved) == 60).all())  # saved whole again
        self.assertEqual(self.names(), [saved.name])

    def test_a_dem_write_stopped_part_way_leaves_no_file(self):
        with mock.patch.object(sus, 'fetch_copernicus', return_value=np.full(self.grid.shape, 50, np.float32)), \
                mock.patch('numpy.save', killed_mid_write), self.assertRaises(Killed):
            ls.dem_for(self.grid, self.tmp, log=quiet)
        self.assertEqual(self.names(), [])

    def test_a_cut_short_saved_land_cover_is_named_deleted_and_read_again(self):
        ls.landcover_classes(self.grid, 2022, self.tmp, log=quiet, fetch=lambda url, xs, ys: np.full(len(xs), 2, np.uint8))
        saved = self.tmp / f'lulc_2022_{self.tag}.npz'
        self.cut_short(saved)
        lines = []
        out = ls.landcover_classes(self.grid, 2022, self.tmp, log=lines.append,
                                   fetch=lambda url, xs, ys: np.full(len(xs), 5, np.uint8))
        self.assertTrue((out == 5).all())
        self.assertTrue(any(saved.name in line for line in lines), lines)
        with np.load(saved) as z:
            self.assertTrue((z['classes'] == 5).all())
        self.assertEqual(self.names(), [saved.name])

    def test_a_land_cover_write_stopped_part_way_leaves_no_file(self):
        with mock.patch('numpy.savez_compressed', killed_mid_write), self.assertRaises(Killed):
            ls.landcover_classes(self.grid, 2022, self.tmp, log=quiet,
                                 fetch=lambda url, xs, ys: np.full(len(xs), 2, np.uint8))
        self.assertEqual(self.names(), [])

    def test_cut_short_saved_roads_are_named_deleted_and_downloaded_again(self):
        with mock.patch.object(ls, 'overpass_elements', return_value=[self.way]):
            first = ls.roads(self.bbox, self.tmp, log=quiet)
        saved = next(self.tmp.glob('osm_roads_*.json'))
        self.cut_short(saved)
        lines = []
        with mock.patch.object(ls, 'overpass_elements', return_value=[self.way, self.way]) as op:
            again = ls.roads(self.bbox, self.tmp, log=lines.append)
        op.assert_called_once()
        self.assertEqual(again, first * 2)
        self.assertTrue(any(saved.name in line for line in lines), lines)
        with mock.patch.object(ls, 'overpass_elements', side_effect=AssertionError('network')):
            self.assertEqual(ls.roads(self.bbox, self.tmp, log=quiet), again)  # saved whole again
        self.assertEqual(self.names(), [saved.name])

    def test_roads_are_saved_through_the_whole_or_nothing_writer(self):
        real = ls.save_atomically
        with mock.patch.object(ls, 'overpass_elements', return_value=[self.way]), \
                mock.patch.object(ls, 'save_atomically', side_effect=real) as saved:
            ls.roads(self.bbox, self.tmp, log=quiet)
        self.assertEqual([c.args[0].name for c in saved.call_args_list],
                         [p.name for p in self.tmp.glob('osm_roads_*.json')])
        self.assertEqual(json.loads(next(self.tmp.glob('osm_roads_*.json')).read_text()),
                         [[[123.86, 10.26], [123.87, 10.27]]])


class FakeBand:
    def __init__(self, value):
        self.value = value

    def data(self, offset, size):
        return np.full(size[0] * size[1], self.value, np.uint8)


class FakeRaster:
    """A one-class land cover blob over Talisay's corner of UTM 51N (easting 300-700 km, northing 800-1,200 km)."""
    origin = (3e5, 1.2e6)
    scale = (10.0, -10.0)
    width = height = 40_000

    def __init__(self, path):
        self.bands = [FakeBand(7)]


class LandcoverRetryTests(SimpleTestCase):
    """
    Ruling R54: GDAL remembers a failed /vsicurl/ lookup for the rest of the
    process, so one network blip during a build made every later tile's blob
    "not exist" and lose its land cover. A failed read now clears that memory
    and is tried again, unless the server says the blob is not there (a year
    not yet published), which ends at once so the newest-year probe stays fast.
    """

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.grid = sus.Grid(10.25, 123.85, 10.30, 123.90, 14)
        self.opened, self.waits, self.lines = [], [], []

    def read(self, failures, exists, year=2022):
        from django.contrib.gis.gdal import GDALException

        def open_raster(path):
            self.opened.append(path)
            if len(self.opened) <= failures:
                raise GDALException(f'Could not open the datasource at "{path}"')
            return FakeRaster(path)

        with mock.patch('django.contrib.gis.gdal.GDALRaster', side_effect=open_raster), \
                mock.patch.object(ls, '_blob_exists', return_value=exists, create=True), \
                mock.patch.object(ls, '_clear_gdal_cache', create=True) as cleared, \
                mock.patch.object(ls.time, 'sleep', side_effect=self.waits.append):
            out = ls.landcover_classes(self.grid, year, self.tmp, log=self.lines.append)
        return out, cleared

    def test_a_network_blip_does_not_cost_the_tile_its_land_cover(self):
        out, cleared = self.read(failures=1, exists=True)
        self.assertIsNotNone(out)
        self.assertTrue((out == 7).all())
        self.assertEqual(len(self.opened), 2)
        cleared.assert_called_once()
        self.assertEqual(self.waits, [15])
        self.assertTrue(any('trying again in 15 s' in line for line in self.lines), self.lines)
        self.assertEqual(len(list(self.tmp.glob('lulc_*.npz'))), 1)

    def test_a_blob_the_server_says_is_not_there_is_not_tried_again(self):
        out, cleared = self.read(failures=99, exists=False, year=2025)
        self.assertIsNone(out)
        self.assertEqual(len(self.opened), 1)
        cleared.assert_not_called()
        self.assertEqual(self.waits, [])

    def test_a_read_that_keeps_failing_gives_up_after_four_reads(self):
        out, cleared = self.read(failures=99, exists=None)  # the server cannot be asked either
        self.assertIsNone(out)
        self.assertEqual(len(self.opened), 4)
        self.assertEqual(cleared.call_count, 3)
        self.assertEqual(self.waits, [15, 30, 60])
        self.assertEqual(list(self.tmp.glob('lulc_*')), [])  # a failure is never cached

    def test_a_fetch_handed_in_is_not_tried_again(self):
        calls = []

        def fetch(url, xs, ys):
            calls.append(url)
            raise OSError('blob cannot be range-read')

        with mock.patch.object(ls.time, 'sleep', side_effect=AssertionError('no wait')):
            self.assertIsNone(ls.landcover_classes(self.grid, 2022, self.tmp, log=quiet, fetch=fetch))
        self.assertEqual(len(calls), 1)

    def test_whether_the_blob_is_there_comes_from_its_status(self):
        import requests

        for code, there in ((200, True), (404, False), (503, None)):
            with mock.patch.object(ls.requests, 'head', return_value=mock.Mock(status_code=code)):
                self.assertIs(ls._blob_exists('https://example.invalid/x.tif'), there, code)
        with mock.patch.object(ls.requests, 'head', side_effect=requests.ConnectionError('could not resolve host')):
            self.assertIsNone(ls._blob_exists('https://example.invalid/x.tif'))

    def test_the_gdal_cache_clears_and_a_gdal_without_the_call_is_no_error(self):
        ls._clear_gdal_cache()  # the real call (GDAL 3.10 has VSICurlClearCache)
        with mock.patch('django.contrib.gis.gdal.libgdal.lgdal', new=object()):
            ls._clear_gdal_cache()
