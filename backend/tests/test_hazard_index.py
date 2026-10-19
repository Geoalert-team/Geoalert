import io
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import numpy as np
import tifffile
from django.test import SimpleTestCase
from PIL import Image

from apps.hazards import susceptibility as susc

STEP = 1 / 64  # synthetic tiles: 1 degree in 64 x 64 pixels


def make_cog(data, lat_top, lng_left, step, tile=16):
    """A tiled, deflate + floating-point-predictor GeoTIFF like Copernicus GLO-30 (PixelIsPoint)."""
    buf = io.BytesIO()
    tifffile.imwrite(
        buf, data.astype(np.float32), tile=(tile, tile), compression='zlib', predictor=3,
        photometric='minisblack',
        extratags=[
            (33550, 'd', 3, (step, step, 0.0), True),
            (33922, 'd', 6, (0, 0, 0, lng_left, lat_top, 0), True),
            (34735, 'H', 16, (1, 1, 0, 3, 1024, 0, 1, 2, 1025, 0, 1, 2, 2048, 0, 1, 4326), True),
        ],
    )
    return buf.getvalue()


def planar_tile():
    """data[r, c] = 100 + r + 0.5 c, so bilinear sampling is exact."""
    r, c = np.mgrid[0:64, 0:64]
    return (100 + r + 0.5 * c).astype(np.float32)


class FakeFetch:
    """Serves byte ranges of in-memory tiles by name; None for a tile that does not exist."""

    def __init__(self, tiles):
        self.tiles, self.calls = tiles, []

    def __call__(self, url, start, length):
        self.calls.append((url, start, length))
        for name, blob in self.tiles.items():
            if name in url:
                return blob[start:start + length]
        return None


class FakeSession:
    def __init__(self, status, body=b''):
        self.status, self.body, self.headers = status, body, []

    def get(self, url, headers=None, timeout=None):
        self.headers.append(headers)
        return SimpleNamespace(status_code=self.status, content=self.body)


def quiet(*_):
    pass


def packed(path):
    """(R * 256 + G, B) of an RGB PNG written by the hazard index build."""
    img = Image.open(path)
    rgb = np.asarray(img).astype(int)
    return img.mode, rgb[..., 0] * 256 + rgb[..., 1], rgb[..., 2]


class RasterOutputTests(SimpleTestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_terrain_png_marks_sea_and_waterway(self):
        hand = np.array([[1.0, 2.5], [0.0, 3.0]], np.float32)
        city = np.array([[True, True], [True, False]])
        sea = np.array([[False, True], [False, False]])
        path = self.dir / 'terrain.png'
        susc.write_terrain_png(path, hand, city, sea)
        mode, value, blue = packed(path)
        self.assertEqual(mode, 'RGB')
        self.assertEqual(value.tolist(), [[100, 250], [0, 300]])
        self.assertEqual(blue.tolist(), [[255, 200], [255, 0]])

    def test_elevation_png_is_decimetres_clipped_at_zero(self):
        dem = np.array([[12.34, -3.0], [669.4, 0.0]], np.float32)
        path = self.dir / 'elevation.png'
        susc.write_elevation_png(path, dem, np.ones((2, 2), bool))
        mode, value, blue = packed(path)
        self.assertEqual(mode, 'RGB')
        self.assertEqual(value.tolist(), [[123, 0], [6694, 0]])
        self.assertEqual(blue.tolist(), [[255, 255], [255, 255]])

    def test_metas_carry_the_notice(self):
        grid = susc.Grid(10.30, 123.80, 10.31, 123.81, 14)
        elevation = susc.elevation_meta(grid)
        self.assertEqual(elevation['file'], 'elevation.png')
        self.assertEqual(set(elevation), {'file', 'bounds', 'encoding', 'source'})
        self.assertIn(susc.COPERNICUS_NOTICE, elevation['source'])
        self.assertIn(susc.COPERNICUS_NOTICE, susc.terrain_meta(grid)['source'])
        self.assertIn('200', susc.terrain_meta(grid)['encoding'])


class CopernicusReaderTests(SimpleTestCase):
    N10_E123 = 'Copernicus_DSM_COG_10_N10_00_E123_00_DEM'

    def setUp(self):
        self.grid = susc.Grid(10.30, 123.80, 10.32, 123.82, 14)
        g = self.grid
        expected = np.zeros(g.shape, np.float64)
        for r in range(g.height):
            for c in range(g.width):
                lng, lat = susc.px_to_lnglat(g.px0 + c + 0.5, g.py0 + r + 0.5, g.zoom)
                expected[r, c] = 100 + (11 - lat) * 64 + 0.5 * (lng - 123) * 64
        self.expected = expected

    def fake(self, data=None):
        data = planar_tile() if data is None else data
        return FakeFetch({self.N10_E123: make_cog(data, 11.0, 123.0, STEP)})

    def test_tile_names(self):
        self.assertEqual(susc.copernicus_tile_name(10, 123), 'Copernicus_DSM_COG_10_N10_00_E123_00_DEM')
        self.assertEqual(susc.copernicus_tile_name(-1, -75), 'Copernicus_DSM_COG_10_S01_00_W075_00_DEM')

    def test_reads_only_needed_blocks_and_places_values(self):
        fake = self.fake()
        dem = susc.fetch_copernicus(self.grid, fake, quiet)
        self.assertEqual(dem.shape, self.grid.shape)
        np.testing.assert_allclose(dem, self.expected, atol=1e-3)
        self.assertEqual(fake.calls[0][0], susc.COPERNICUS_URL.format(name=self.N10_E123))
        block_reads = [c for c in fake.calls if c[1] != 0]
        self.assertTrue(0 < len(block_reads) < 16)  # 64 x 64 tile in 16 blocks; the grid needs only a few

    def test_missing_tile_reads_as_zero(self):
        dem = susc.fetch_copernicus(self.grid, FakeFetch({}), quiet)
        self.assertEqual(dem.shape, self.grid.shape)
        self.assertFalse(dem.any())

    def test_voids_read_as_zero(self):
        data = np.full((64, 64), -32767.0, np.float32)
        data[0, 0] = np.nan
        dem = susc.fetch_copernicus(self.grid, self.fake(data), quiet)
        self.assertGreaterEqual(dem.min(), 0)

    def test_small_first_header_read_still_parses(self):
        dem = susc.fetch_copernicus(self.grid, self.fake(), quiet, header_bytes=64)
        np.testing.assert_allclose(dem, self.expected, atol=1e-3)

    def test_range_fetcher(self):
        ok = FakeSession(status=206, body=b'x' * 10)
        self.assertEqual(susc.http_range_fetcher(ok)('u', 10, 10), b'x' * 10)
        self.assertEqual(ok.headers[-1]['Range'], 'bytes=10-19')
        self.assertIsNone(susc.http_range_fetcher(FakeSession(status=404))('u', 0, 1))
        bad = FakeSession(status=500)
        with self.assertRaises(RuntimeError):
            susc.http_range_fetcher(bad, retries=3, backoff_s=0)('u', 0, 1)
        self.assertEqual(len(bad.headers), 3)

    def test_range_fetcher_treats_refused_access_as_a_failure(self):
        # The bucket answers 404 for a tile that does not exist; 403 means access was refused
        refused = FakeSession(status=403)
        with self.assertRaises(RuntimeError):
            susc.http_range_fetcher(refused, retries=3, backoff_s=0)('u', 0, 1)
        self.assertEqual(len(refused.headers), 3)


class BuildTests(SimpleTestCase):
    """build() on a tiny city: a 0 m strip of sea to the west, one river, ground rising east."""

    EXTENT = (123.800, 10.300, 123.810, 10.310)  # west, south, east, north
    CITY = [(1, [[(123.803, 10.300), (123.810, 10.300), (123.810, 10.310), (123.803, 10.310), (123.803, 10.300)]])]

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.out = Path(self._tmp.name)
        height, width = susc.Grid(10.300, 123.800, 10.310, 123.810, 14).shape
        self.dem = np.tile(np.maximum(0, np.linspace(-2, 20, width)), (height, 1)).astype(np.float32)
        self.osm = {
            'waterways': [{'kind': 'river', 'name': 'Test River', 'coords': [(123.807, 10.300), (123.807, 10.310)]}],
            'coastline': [], 'roads': [], 'main_roads': [], 'landuse': [], 'buildings': [], 'fire_stations': [],
        }

    def tearDown(self):
        self._tmp.cleanup()

    def build(self, **kwargs):
        susc.build(self.CITY, {1: 'Test'}, self.EXTENT, self.out, pad_m=0,
                   dem=self.dem, osm=self.osm, log=quiet, **kwargs)
        return json.loads((self.out / 'index.json').read_text())

    def test_build_writes_elevation_and_notice(self):
        index = self.build()
        self.assertTrue((self.out / 'elevation.png').exists())
        self.assertEqual(index['elevation']['file'], 'elevation.png')
        self.assertIn(susc.COPERNICUS_NOTICE, index['sources'][0])
        self.assertIn(susc.COPERNICUS_LIABILITY, index['sources'])
        blue = np.asarray(Image.open(self.out / 'terrain.png'))[..., 2]
        self.assertTrue((blue == 200).any())  # city ground measured against the sea
        self.assertTrue((blue == 255).any())  # city ground measured against the river

    def test_terrain_only_keeps_layers_and_adds_elevation(self):
        (self.out / 'index.json').write_text(json.dumps({'layers': {'flood': 'flood.png'}}))
        index = self.build(terrain_only=True)
        self.assertEqual(index['layers'], {'flood': 'flood.png'})
        self.assertTrue({'terrain', 'elevation'} <= index.keys())
        self.assertTrue((self.out / 'elevation.png').exists())

    def test_ground_measured_against_the_coastline_counts_as_sea(self):
        # OpenStreetMap's coastline is drawn on land at the shore, so it, not the
        # open sea, is often the nearest drainage for coastal ground
        self.osm['coastline'] = [[(123.804, 10.300), (123.804, 10.310)]]
        self.build()
        x, y = susc.Grid(10.300, 123.800, 10.310, 123.810, 14).to_cell(123.8045, 10.305)
        blue = np.asarray(Image.open(self.out / 'terrain.png'))[..., 2]
        self.assertEqual(blue[int(y), int(x)], susc.TERRAIN_B_SEA)

    def test_build_refuses_a_city_with_no_height_and_writes_nothing(self):
        self.dem[:] = 0
        with self.assertRaises(RuntimeError):
            self.build()
        self.assertEqual(list(self.out.iterdir()), [])

    def test_a_flat_download_is_never_cached(self):
        cache = self.out / 'cache'
        flat = np.zeros_like(self.dem)
        with mock.patch.object(susc, 'fetch_copernicus', return_value=flat), self.assertRaises(RuntimeError):
            susc.build(self.CITY, {1: 'Test'}, self.EXTENT, self.out / 'index', pad_m=0,
                       osm=self.osm, log=quiet, cache_dir=cache)
        self.assertEqual(list(cache.glob('dem_*.npy')), [])
        self.assertFalse((self.out / 'index').exists())
