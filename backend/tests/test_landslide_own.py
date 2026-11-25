"""
The landslide January job's own data (plan Task 10): the floor at and around
30 spots in 3 barangays, and own_rows, GeoAlert's located landslides as
slides with three "no" points each (the outside table's rule), every row in
the Talisay fold with weight 10, clues read where each point lies. No
database.
"""
import math

import numpy as np
from django.test import SimpleTestCase

from apps.history import landslide_run
from apps.history.landslide_features import FEATURE_COLUMNS, TERRAIN_COLUMNS
from apps.history.landslide_own import OWN_FOLD, OWN_WEIGHT, floor, own_rows
from apps.history.landslide_training_table import TABLE_COLUMNS

BASE_LON, BASE_LAT = 123.8412345, 10.2678901  # Talisay's uplands
CLUES = FEATURE_COLUMNS + ('noah_class',)


def spots(n, barangays=3, season_2026=0):
    """
    n located landslide spots over `barangays` barangays: the last
    `season_2026` in the 2026 wet season (held back on 6 January 2027), the
    rest before June 2026.
    """
    out = []
    for i in range(n):
        held = i >= n - season_2026
        when = f'2026-{6 + i % 7:02d}-20T14:00:00+08:00' if held else f'2025-{1 + i % 12:02d}-08T09:30:00+08:00'
        out.append({'id': f'r:{"h" if held else "t"}{i}', 'when': when,
                    'lon': BASE_LON + (i % 9) * 2.1e-3, 'lat': BASE_LAT + (i // 9) * 1.7e-3,
                    'purok_id': 300 + i, 'barangay': f'Barangay {i % barangays}'})
    return out


def clues_at(points):
    """Every model input and the NOAH class at each point: plain numbers that depend on where it is."""
    pts = np.asarray(points, float).reshape(-1, 2)
    base = (pts[:, 0] - BASE_LON) * 1e3 + (pts[:, 1] - BASE_LAT) * 1e3
    return {c: base + k for k, c in enumerate(CLUES)}


def everywhere(points):
    """on_ground for points that are all on ground."""
    return np.ones(len(points), bool)


def local_metres(points, lat0):
    pts = np.asarray(points, float).reshape(-1, 2)
    return np.c_[pts[:, 0] * 111_320 * math.cos(math.radians(lat0)), pts[:, 1] * 110_574]


class FloorTests(SimpleTestCase):
    def spots(self, n, barangays):
        return spots(n, barangays=barangays)

    def test_floor_at_and_around_30_spots_and_3_barangays(self):
        self.assertFalse(floor(self.spots(29, barangays=3))['enough'])
        self.assertFalse(floor(self.spots(30, barangays=2))['enough'])
        self.assertTrue(floor(self.spots(30, barangays=3))['enough'])
        self.assertEqual(floor(self.spots(31, barangays=4)), {'n': 31, 'barangays': 4, 'enough': True})


class OwnRowsTests(SimpleTestCase):
    def setUp(self):
        self.seen = []

        def features_at(points):
            self.seen.append(np.asarray(points, float).copy())
            return clues_at(points)

        self.features_at = features_at
        self.spots = spots(12, barangays=3)
        self.rows = own_rows(self.spots, features_at, on_ground=everywhere)

    def test_spots_are_slides_with_three_no_points_each(self):
        label = self.rows['label']
        self.assertEqual(int(label.sum()), 12)
        self.assertEqual(int((label == 0).sum()), 36)
        self.assertEqual(len(self.seen), 1)  # the clues read once, for every point
        self.assertEqual(len(self.seen[0]), 48)
        np.testing.assert_allclose(self.seen[0][:12], [[s['lon'], s['lat']] for s in self.spots])

    def test_the_talisay_fold_with_weight_ten_on_every_row(self):
        self.assertEqual((OWN_FOLD, OWN_WEIGHT), (landslide_run.OWN_FOLD, landslide_run.OWN_WEIGHT))
        for c in ('event', 'fold', 'region'):
            self.assertEqual(set(self.rows[c].tolist()), {'talisay'}, c)
        np.testing.assert_array_equal(self.rows['weight'], np.full(48, 10.0))  # "no" points too: the 1-to-3 balance

    def test_clues_come_from_features_at(self):
        expected = clues_at(self.seen[0])
        for c in CLUES:
            np.testing.assert_allclose(self.rows[c], expected[c], err_msg=c)

    def test_no_points_within_2_km_of_a_spot_and_60_m_from_every_spot(self):
        pts = self.seen[0]
        lat0 = float(pts[:12, 1].mean())
        slides, no = local_metres(pts[:12], lat0), local_metres(pts[12:], lat0)
        gaps = np.hypot(no[:, None, 0] - slides[None, :, 0], no[:, None, 1] - slides[None, :, 1]).min(axis=1)
        self.assertGreaterEqual(gaps.min(), 60 - 1)   # 1 m for the degree conversion
        self.assertLessEqual(gaps.max(), 2000 + 1)

    def test_the_same_seed_gives_the_same_rows_and_another_seed_other_no_points(self):
        first = self.seen[0]
        again = own_rows(self.spots, self.features_at, on_ground=everywhere)
        for c in self.rows:
            np.testing.assert_array_equal(again[c], self.rows[c], err_msg=c)
        np.testing.assert_array_equal(self.seen[1], first)
        own_rows(self.spots, self.features_at, seed=1, on_ground=everywhere)
        other = self.seen[2]
        np.testing.assert_array_equal(other[:12], first[:12])  # the same slides
        self.assertFalse(np.allclose(other[12:], first[12:]))  # other "no" points

    def test_a_table_run_reads_and_no_coordinate(self):
        self.assertTrue(set(TABLE_COLUMNS) <= set(self.rows), set(TABLE_COLUMNS) - set(self.rows))
        self.assertFalse({'lon', 'lat', 'id', 'when', 'purok_id', 'barangay'} & set(self.rows))
        self.assertEqual({len(v) for v in self.rows.values()}, {48})

    def test_a_point_at_sea_or_with_a_missing_terrain_clue_is_dropped(self):
        # As the outside table (rulings R20, R21): the sea is not ground, and a missing terrain clue would grey the map
        def features_at(points):
            values = clues_at(points)
            values['twi'][1] = np.nan          # a slide with a missing terrain clue
            values['lc_trees'][2] = np.nan     # land cover is not a terrain clue: kept
            return values

        def on_ground(points):
            ground = np.ones(len(points), bool)
            ground[[0, 20]] = False            # a slide and a "no" point at sea
            return ground

        rows = own_rows(self.spots, features_at, on_ground=on_ground)
        self.assertEqual(int(rows['label'].sum()), 10)
        # Review m1: the two dropped slides take no share of the "no" points, which are drawn again around the 10
        # kept (30) and read again, so this mock's drops hit the new ones too: index 0 and 20 at sea, 1 missing twi
        self.assertEqual(int((rows['label'] == 0).sum()), 27)
        for c in TERRAIN_COLUMNS:
            self.assertTrue(np.isfinite(rows[c]).all(), c)
        self.assertEqual(int(np.isnan(rows['lc_trees']).sum()), 2)  # index 2 in each read: a slide and a "no" point

    def test_no_spots_give_an_empty_table(self):
        rows = own_rows([], clues_at, on_ground=everywhere)
        self.assertTrue(set(TABLE_COLUMNS) <= set(rows))
        self.assertEqual({len(v) for v in rows.values()}, {0})

    # Final review M10.4: the ground check is never left out by accident
    def test_the_ground_check_is_a_required_keyword(self):
        with self.assertRaises(TypeError):
            own_rows(self.spots, clues_at)
        with self.assertRaises(TypeError):
            own_rows(self.spots, clues_at, 0, everywhere)

    # Final review B1: a spot off Talisay's clue grids (a misplaced map point) has no clues, so neither it nor its
    # "no" points are trained on
    def test_a_point_with_no_clues_is_dropped_with_its_no_points(self):
        far = [{**self.spots[0], 'lon': BASE_LON + 0.78}]  # 85 km east, its "no" points around it

        def off_the_grids(points):
            values = clues_at(points)
            off = np.asarray(points, float)[:, 0] > BASE_LON + 0.5
            for c in CLUES:
                values[c] = np.where(off, np.nan, values[c])
            return values

        rows = own_rows(self.spots + far, off_the_grids, on_ground=everywhere)
        self.assertEqual(int(rows['label'].sum()), 12)
        self.assertEqual(int((rows['label'] == 0).sum()), 36)  # review m1: three for each kept spot
        self.assertTrue(np.isfinite(rows['slope_deg']).all())
        alone = own_rows(far, off_the_grids, on_ground=everywhere)
        self.assertEqual({len(v) for v in alone.values()}, {0})

    # Final review m1: a spot that is dropped (off the clue grids, or at sea) takes no share of the other spots'
    # "no" points either: the rows are exactly those the other spots give without it
    def test_a_dropped_spot_leaves_the_other_spots_rows_as_they_were(self):
        far = [{**self.spots[0], 'lon': BASE_LON + 0.78}]

        def off_the_grids(points):
            values = clues_at(points)
            off = np.asarray(points, float)[:, 0] > BASE_LON + 0.5
            return {c: np.where(off, np.nan, v) for c, v in values.items()}

        def ground_but_far(points):
            return np.asarray(points, float)[:, 0] <= BASE_LON + 0.5

        without = own_rows(self.spots, clues_at, on_ground=everywhere)
        for name, features_at, on_ground in (('off the grids', off_the_grids, everywhere),
                                             ('at sea', clues_at, ground_but_far)):
            with_far = own_rows(self.spots + far, features_at, on_ground=on_ground)
            self.assertEqual(set(with_far), set(without), name)
            for c in without:
                np.testing.assert_array_equal(with_far[c], without[c], err_msg=f'{name}: {c}')
