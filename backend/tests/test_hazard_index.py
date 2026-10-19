import tempfile
from pathlib import Path

import numpy as np
from django.test import SimpleTestCase
from PIL import Image

from apps.hazards import susceptibility as susc


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
