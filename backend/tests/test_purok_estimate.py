"""
Estimated purok outlines: the pieces that turn researched points into areas.

The Barangay Hall hasn't sent official purok boundaries, so the map draws
estimates. Each purok grows from a researched point across a grid; edges
should settle on main roads, creeks and ridges, and each purok should hold
about its share of the barangay's houses. These tests pin that behaviour on
small hand-made grids, without the database.
"""
import json
import math
import tempfile
from pathlib import Path

import numpy as np
from django.contrib.gis.geos import GeometryCollection, LineString, MultiPolygon, Polygon
from django.test import SimpleTestCase

from apps.barangays import purok_estimate as pe


class NormNameTests(SimpleTestCase):
    def test_prefix_case_and_punctuation_are_ignored(self):
        self.assertEqual(pe.norm_name('Purok Ilang-Ilang'), pe.norm_name('ilang ilang'))
        self.assertEqual(pe.norm_name('Sitio Tunga'), pe.norm_name('TUNGA'))

    def test_doubled_letters_match(self):
        self.assertEqual(pe.norm_name('Kamunggay'), pe.norm_name('Kamungay'))

    def test_numbers_stay_distinct(self):
        self.assertNotEqual(pe.norm_name('Purok 4'), pe.norm_name('Purok 7'))

    def test_zone_keeps_its_word(self):
        # "Zone 3" and "Purok 3" are different places
        self.assertNotEqual(pe.norm_name('Zone 3'), pe.norm_name('Purok 3'))


class PurokCountTests(SimpleTestCase):
    def test_official_count_wins(self):
        self.assertEqual(pe.purok_count(official=9, households=687, names=4), (9, 'official'))

    def test_households_when_no_official_count(self):
        self.assertEqual(pe.purok_count(official=None, households=1750, names=3), (10, 'households'))

    def test_never_fewer_than_names_found(self):
        self.assertEqual(pe.purok_count(official=None, households=350, names=8), (8, 'names'))
        self.assertEqual(pe.purok_count(official=14, households=1301, names=17), (17, 'names'))


def grid(h, w, value=1.0):
    return np.full((h, w), value, dtype=np.float64)


class GrowTests(SimpleTestCase):
    def test_border_settles_on_a_creek_between_two_points(self):
        inside = np.ones((5, 21), bool)
        barrier = grid(5, 21, 0)
        barrier[:, 13] = pe.WATER_PENALTY_M  # creek nearer the right point
        houses = grid(5, 21, 1)
        owner = pe.grow(inside, step=grid(5, 21, 9), houses=houses, seeds=[(2, 2), (2, 18)],
                        quotas=[1e9, 1e9], caps=[1e9, 1e9], barrier=barrier)
        # Without the creek the split would be at column 10; with it the left
        # point stops at the creek and the right one owns it
        self.assertTrue((owner[:, :13] == 0).all())
        self.assertTrue((owner[:, 13:] == 1).all())

    def test_a_point_stops_at_its_share_of_houses(self):
        inside = np.ones((1, 30), bool)
        owner = pe.grow(inside, step=grid(1, 30, 9), houses=grid(1, 30, 1), seeds=[(0, 0)],
                        quotas=[10], caps=[1e9])
        self.assertEqual(int((owner == 0).sum()), 10)
        self.assertTrue((owner[0, 10:] == -1).all())

    def test_radius_cap_holds_on_empty_ground(self):
        inside = np.ones((41, 41), bool)
        owner = pe.grow(inside, step=grid(41, 41, 18), houses=grid(41, 41, 0), seeds=[(20, 20)],
                        quotas=[5], caps=[6])
        rows, cols = np.nonzero(owner == 0)
        self.assertLessEqual(np.hypot(rows - 20, cols - 20).max(), 6)

    def test_never_leaves_the_barangay(self):
        inside = np.zeros((3, 10), bool)
        inside[:, :4] = True
        owner = pe.grow(inside, step=grid(3, 10, 9), houses=grid(3, 10, 1), seeds=[(1, 0)],
                        quotas=[1e9], caps=[1e9])
        self.assertTrue((owner[:, 4:] == -1).all())

    def test_climbing_costs_so_a_ridge_holds_the_border(self):
        inside = np.ones((3, 21), bool)
        dem = grid(3, 21, 0)
        dem[:, 12] = 30  # ridge right of the middle
        owner = pe.grow(inside, step=grid(3, 21, 9), houses=grid(3, 21, 1), seeds=[(1, 2), (1, 18)],
                        quotas=[1e9, 1e9], caps=[1e9, 1e9], dem=dem)
        self.assertTrue((owner[:, :12] == 0).all())

    def test_seed_just_outside_the_mask_snaps_inside(self):
        inside = np.zeros((5, 5), bool)
        inside[2:, 2:] = True
        owner = pe.grow(inside, step=grid(5, 5, 9), houses=grid(5, 5, 1), seeds=[(1, 1)],
                        quotas=[1e9], caps=[1e9])
        self.assertTrue((owner[2:, 2:] == 0).all())


class GrowFromOutlineTests(SimpleTestCase):
    """A name with an outline drawn on Wikimapia or OSM starts from that whole outline."""

    def test_the_outline_is_kept_whole_and_grows_outward(self):
        inside = np.ones((10, 30), bool)
        preset = np.full((10, 30), -1, np.int32)
        preset[3:7, 2:6] = 0  # 16 cells
        owner = pe.grow(inside, step=grid(10, 30, 9), houses=grid(10, 30, 1), seeds=[(5, 4), (5, 25)],
                        quotas=[40, 1e9], caps=[1e9, 1e9], preset=preset)
        self.assertTrue((owner[3:7, 2:6] == 0).all())
        self.assertEqual(int((owner == 0).sum()), 40)

    def test_no_other_area_enters_an_outline(self):
        inside = np.ones((5, 20), bool)
        preset = np.full((5, 20), -1, np.int32)
        preset[:, 8:12] = 1  # an outline across the whole strip, already holding its share
        owner = pe.grow(inside, step=grid(5, 20, 9), houses=grid(5, 20, 1), seeds=[(2, 2), (2, 10)],
                        quotas=[1e9, 20], caps=[1e9, 1e9], preset=preset)
        self.assertTrue((owner[:, 8:12] == 1).all())
        self.assertFalse((owner[:, 12:] == 0).any())  # area 0 can't walk through it

    def test_two_points_on_the_same_cell_both_get_an_area(self):
        inside = np.ones((9, 9), bool)
        owner = pe.grow(inside, step=grid(9, 9, 9), houses=grid(9, 9, 1), seeds=[(4, 4), (4, 4)],
                        quotas=[1e9, 1e9], caps=[1e9, 1e9])
        self.assertGreater(int((owner == 0).sum()), 1)
        self.assertGreater(int((owner == 1).sum()), 1)

    def test_a_point_inside_another_names_outline_moves_out_of_it(self):
        inside = np.ones((9, 9), bool)
        preset = np.full((9, 9), -1, np.int32)
        preset[2:7, 2:7] = 0
        owner = pe.grow(inside, step=grid(9, 9, 9), houses=grid(9, 9, 1), seeds=[(4, 4), (4, 4)],
                        quotas=[25, 1e9], caps=[1e9, 1e9], preset=preset)
        self.assertTrue((owner[2:7, 2:7] == 0).all())
        self.assertGreater(int((owner == 1).sum()), 0)


class SeedPointsTests(SimpleTestCase):
    def test_one_seed_in_each_cluster_of_houses(self):
        cells = [(0, 0), (0, 1), (1, 0), (1, 1), (20, 20), (20, 21), (21, 20)]
        seeds = pe.seed_points(cells, [1] * len(cells), 2)
        self.assertEqual(len(seeds), 2)
        near = sorted(min(abs(r - 0) + abs(c - 0), abs(r - 20) + abs(c - 20)) <= 2 for r, c in seeds)
        self.assertEqual(near, [True, True])
        self.assertNotEqual(seeds[0][0] < 10, seeds[1][0] < 10)  # not both in the same cluster

    def test_seeds_sit_on_given_cells(self):
        cells = [(0, 0), (0, 10), (10, 0), (10, 10)]
        for seed in pe.seed_points(cells, [1, 1, 1, 1], 3):
            self.assertIn(seed, cells)

    def test_same_input_same_seeds(self):
        cells = [(r, c) for r in range(0, 30, 3) for c in range(0, 30, 4)]
        weights = [1 + (r * c) % 5 for r, c in cells]
        self.assertEqual(pe.seed_points(cells, weights, 4), pe.seed_points(cells, weights, 4))

    def test_never_more_seeds_than_cells(self):
        self.assertEqual(len(pe.seed_points([(1, 1), (5, 5)], [1, 1], 4)), 2)


class FillGapsTests(SimpleTestCase):
    def test_leftover_ground_goes_to_the_nearest_area(self):
        inside = np.ones((1, 10), bool)
        owner = np.full((1, 10), -1, np.int32)
        owner[0, 0], owner[0, 9] = 0, 1
        filled = pe.fill_gaps(owner, inside, step=grid(1, 10, 9))
        self.assertEqual(filled[0].tolist(), [0, 0, 0, 0, 0, 1, 1, 1, 1, 1])

    def test_a_creek_holds_the_border_here_too(self):
        inside = np.ones((1, 10), bool)
        owner = np.full((1, 10), -1, np.int32)
        owner[0, 0], owner[0, 9] = 0, 1
        barrier = grid(1, 10, 0)
        barrier[0, 2] = pe.WATER_PENALTY_M
        filled = pe.fill_gaps(owner, inside, step=grid(1, 10, 9), barrier=barrier)
        # Without the creek the border is between cells 4 and 5; with it, right after the creek
        self.assertEqual(filled[0].tolist(), [0, 0, 0, 1, 1, 1, 1, 1, 1, 1])

    def test_owned_and_outside_cells_are_left_alone(self):
        inside = np.ones((1, 6), bool)
        inside[0, 5] = False
        owner = np.array([[0, -1, 1, 1, -1, -1]], np.int32)
        filled = pe.fill_gaps(owner, inside, step=grid(1, 6, 9))
        self.assertEqual(filled[0, :4].tolist(), [0, 0, 1, 1])
        self.assertEqual(filled[0, 5], -1)


class OutlineAreasTests(SimpleTestCase):
    def test_neighbours_share_one_border_with_no_gap_or_overlap(self):
        labels = np.full((12, 20), -1, np.int32)
        labels[1:11, 1:10] = 0
        labels[1:11, 10:19] = 1
        shapes = pe.outline_areas(labels)
        a, b = shapes[0], shapes[1]
        self.assertAlmostEqual(a.intersection(b).area, 0, delta=0.01)
        # The border between them is drawn once: nothing left uncovered along it
        middle = Polygon.from_bbox((3, 2, 16, 10))
        self.assertAlmostEqual(middle.difference(a.union(b)).area, 0, delta=0.01)

    def test_a_staircase_border_comes_out_as_a_straight_diagonal(self):
        labels = np.full((22, 22), -1, np.int32)
        for r in range(1, 21):
            labels[r, 1:21] = 0
            labels[r, max(1, r):21] = 1  # diagonal split, a staircase on the grid
        shape = pe.outline_areas(labels)[1]
        ring = shape.coords[0] if shape.geom_type == 'Polygon' else shape[0].coords[0]
        # Border vertices away from the barangay edge should all lie on one
        # diagonal line (x - y the same everywhere), not zig-zag across it;
        # none at all means one straight segment
        diffs = [x - y for x, y in ring if 3 < x < 18 and 3 < y < 18]
        self.assertLess(max(diffs, default=0) - min(diffs, default=0), 0.1)
        self.assertLess(len(ring), 20)  # the 40-step staircase is gone

    def test_a_straight_border_carries_no_extra_points(self):
        # 300 outlines for the whole city; points in a straight row only add download size
        labels = np.full((12, 20), -1, np.int32)
        labels[1:11, 1:10] = 0
        labels[1:11, 10:19] = 1
        ring = pe.outline_areas(labels)[0].coords[0]
        on_border = [(x, y) for x, y in ring if 9 < x < 11 and 3 < y < 8]
        self.assertLessEqual(len(on_border), 1)

    def test_an_area_inside_another_leaves_a_hole(self):
        labels = np.full((14, 14), -1, np.int32)
        labels[1:13, 1:13] = 0
        labels[5:9, 5:9] = 1
        shapes = pe.outline_areas(labels)
        outer = shapes[0] if shapes[0].geom_type == 'Polygon' else shapes[0][0]
        self.assertGreaterEqual(outer.num_interior_rings, 1)
        self.assertAlmostEqual(shapes[0].intersection(shapes[1]).area, 0, delta=0.01)

    def test_outside_cells_make_no_area(self):
        labels = np.full((5, 5), -1, np.int32)
        labels[1:4, 1:4] = 0
        self.assertEqual(set(pe.outline_areas(labels)), {0})


class SplitTests(SimpleTestCase):
    def setUp(self):
        self.inside = np.ones((20, 40), bool)
        self.houses = np.zeros((20, 40))
        self.houses[5:10, 3:8] = 2     # a cluster on the left
        self.houses[10:15, 30:36] = 2  # and one on the right
        self.step = grid(20, 40, 9)

    def test_every_cell_of_the_barangay_gets_an_area(self):
        labels = pe.split_named(self.inside, self.houses, self.step, n=2, seeds=[])
        self.assertTrue((labels[self.inside] >= 0).all())
        self.assertEqual(set(np.unique(labels).tolist()), {0, 1})

    def test_each_house_cluster_lands_in_its_own_area(self):
        labels = pe.split_named(self.inside, self.houses, self.step, n=2, seeds=[])
        left, right = set(labels[5:10, 3:8].ravel().tolist()), set(labels[10:15, 30:36].ravel().tolist())
        self.assertEqual(len(left), 1)
        self.assertEqual(len(right), 1)
        self.assertNotEqual(left, right)

    def test_more_puroks_than_house_cells_still_splits(self):
        houses = np.zeros((20, 40))
        houses[10, 10] = 1
        labels = pe.split_named(self.inside, houses, self.step, n=4, seeds=[])
        self.assertEqual(len(np.unique(labels[self.inside])), 4)

    def test_a_detached_piece_of_the_barangay_is_covered_too(self):
        inside = np.zeros((20, 40), bool)
        inside[:, :15] = True
        inside[:, 30:] = True   # an islet the growth can't walk to
        houses = np.zeros((20, 40))
        houses[5:10, 3:8] = 1
        labels = pe.split_named(inside, houses, self.step, n=1, seeds=[])
        self.assertTrue((labels[inside] == 0).all())
        self.assertTrue((labels[~inside] == -1).all())


class SplitNamedTests(SimpleTestCase):
    """Researched names grow from where they were found; unnamed areas cover the rest."""

    def setUp(self):
        self.inside = np.ones((20, 40), bool)
        self.houses = np.zeros((20, 40))
        self.houses[5:10, 3:8] = 2     # a cluster on the left
        self.houses[10:15, 30:36] = 2  # and one on the right
        self.step = grid(20, 40, 9)

    def test_each_name_keeps_its_index_at_its_point(self):
        labels = pe.split_named(self.inside, self.houses, self.step, n=2, seeds=[(7, 5)])
        self.assertEqual(labels[7, 5], 0)

    def test_the_unnamed_area_starts_where_no_name_was_found(self):
        labels = pe.split_named(self.inside, self.houses, self.step, n=2, seeds=[(7, 5)])
        self.assertTrue((labels[10:15, 30:36] == 1).all())
        self.assertEqual(set(np.unique(labels[self.inside]).tolist()), {0, 1})

    def test_every_cell_of_the_barangay_gets_an_area(self):
        labels = pe.split_named(self.inside, self.houses, self.step, n=4, seeds=[(7, 5), (12, 32)])
        self.assertTrue((labels[self.inside] >= 0).all())
        self.assertEqual(len(np.unique(labels[self.inside])), 4)

    def test_more_names_than_puroks_gives_every_name_an_area(self):
        labels = pe.split_named(self.inside, self.houses, self.step, n=1, seeds=[(7, 5), (12, 32)])
        self.assertEqual(set(np.unique(labels[self.inside]).tolist()), {0, 1})

    def test_approximate_names_spread_over_the_nearest_house_clusters(self):
        houses = np.zeros((20, 60))
        houses[5:10, 3:8] = 2      # left
        houses[5:10, 25:30] = 2    # middle
        houses[5:10, 50:55] = 2    # right
        inside = np.ones((20, 60), bool)
        # Two names an outage notice put on the same spot by the left cluster
        labels = pe.split_named(inside, houses, grid(20, 60, 9), n=3, seeds=[(7, 9), (7, 9)], loose=[True, True])
        self.assertEqual({int(labels[7, 5]), int(labels[7, 27])}, {0, 1})
        self.assertEqual(int(labels[7, 52]), 2)  # the far cluster stays unnamed

    def test_an_approximate_name_far_from_any_free_cluster_keeps_its_point(self):
        labels = pe.split_named(self.inside, self.houses, self.step, n=2, seeds=[(7, 5), (18, 20)],
                                loose=[False, True], loose_reach=3)
        self.assertEqual(int(labels[18, 20]), 1)

    def test_an_outline_stays_with_its_name(self):
        preset = np.full((20, 40), -1, np.int32)
        preset[0:4, 15:25] = 0
        labels = pe.split_named(self.inside, self.houses, self.step, n=3, seeds=[(2, 20)], preset=preset)
        self.assertTrue((labels[0:4, 15:25] == 0).all())


class AreaPointsTests(SimpleTestCase):
    def row(self, name, parent='', placed=True):
        return {'name': name, 'parent': parent, 'lat': '10.25' if placed else '', 'lng': '123.85' if placed else ''}

    def test_a_sitio_whose_purok_is_placed_gives_way_to_it(self):
        rows = [self.row('Sitio Laray'), self.row('Purok Sambag', parent='Sitio Laray')]
        points, _ = pe.area_points(rows)
        self.assertEqual([r['name'] for r in points], ['Purok Sambag'])

    def test_a_sitio_whose_puroks_are_not_placed_keeps_its_area(self):
        rows = [self.row('Sitio Laray'), self.row('Purok Sambag', parent='Sitio Laray', placed=False)]
        points, _ = pe.area_points(rows)
        self.assertEqual([r['name'] for r in points], ['Sitio Laray'])

    def test_names_without_a_point_get_no_area(self):
        points, _ = pe.area_points([self.row('Sitio Tubod', placed=False)])
        self.assertEqual(points, [])

    def test_leaves_count_every_name_that_is_nobodys_parent(self):
        rows = [self.row('Sitio Laray'), self.row('Purok Sambag', parent='Sitio Laray'),
                self.row('Purok Macopa', parent='Sitio Laray', placed=False), self.row('Sitio Ughay')]
        _, leaves = pe.area_points(rows)
        self.assertEqual(leaves, 3)


class TidyTests(SimpleTestCase):
    def test_a_one_cell_strip_along_a_creek_is_absorbed(self):
        owner = np.zeros((9, 20), np.int32)
        owner[:, 12:] = 1
        owner[4, 2:10] = 1  # a creek strip claimed by the wrong side
        tidied = pe.tidy(owner, np.ones((9, 20), bool), min_cells=10)
        self.assertTrue((tidied[:, :12] == 0).all())
        self.assertTrue((tidied[:, 12:] == 1).all())

    def test_a_small_detached_bit_joins_the_area_around_it(self):
        owner = np.zeros((20, 20), np.int32)
        owner[:, 14:] = 1
        owner[3:5, 3:5] = 1  # 4 cells cut off from area 1
        tidied = pe.tidy(owner, np.ones((20, 20), bool), min_cells=10)
        self.assertTrue((tidied[3:5, 3:5] == 0).all())
        self.assertTrue((tidied[:, 14:] == 1).all())

    def test_outside_stays_outside(self):
        owner = np.full((6, 6), -1, np.int32)
        inside = np.zeros((6, 6), bool)
        inside[1:5, 1:5] = True
        owner[inside] = 0
        tidied = pe.tidy(owner, inside, min_cells=3)
        self.assertTrue((tidied[~inside] == -1).all())
        self.assertTrue((tidied[inside] == 0).all())


class ExtendTests(SimpleTestCase):
    def test_areas_reach_a_little_past_the_barangay_edge(self):
        owner = np.full((1, 9), -1, np.int32)
        owner[0, 3:6] = [0, 0, 1]
        out = pe.extend(owner, cells=2)
        self.assertEqual(out[0].tolist(), [-1, 0, 0, 0, 0, 1, 1, 1, -1])


class BuildingCentresTests(SimpleTestCase):
    def test_keeps_footprint_centres_inside_the_box(self):
        lines = [
            '{"type": "Feature", "properties": {}, "geometry": {"type": "Polygon", "coordinates": '
            '[[[123.80, 10.30], [123.81, 10.30], [123.81, 10.31], [123.80, 10.31], [123.80, 10.30]]]}}',
            '{"type": "Feature", "properties": {}, "geometry": {"type": "Polygon", "coordinates": '
            '[[[124.50, 10.30], [124.51, 10.30], [124.51, 10.31], [124.50, 10.30]]]}}',
        ]
        centres = pe.building_centres(lines, (10.2, 123.7, 10.4, 123.9))
        self.assertEqual(len(centres), 1)
        lng, lat = centres[0]
        self.assertAlmostEqual(lng, 123.805, places=4)
        self.assertAlmostEqual(lat, 10.305, places=4)


class ReadResearchTests(SimpleTestCase):
    def test_names_outlines_and_counts_are_keyed_by_barangay_under_any_spelling(self):
        from apps.barangays.aliases import canonical
        from apps.barangays.management.commands.build_purok_estimates import read_research

        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / 'points.csv').write_text(
                'barangay,name,kind,parent,lat,lng,placed_by,confidence,sources,note\n'
                'Tabunok,Purok Kalinaw,purok,,10.2608,123.8418,Overture place,medium,Overture Maps,\n'
                'Camp 4,Sitio Nangka,sitio,,,,,,news,\n', encoding='utf-8')
            (d / 'outlines.geojson').write_text(json.dumps({'type': 'FeatureCollection', 'features': [{
                'type': 'Feature', 'properties': {'barangay': 'Tabunoc', 'name': 'Purok Kalinaw'},
                'geometry': {'type': 'Polygon', 'coordinates': [[[0, 0], [1, 0], [1, 1], [0, 0]]]}}]}),
                encoding='utf-8')
            (d / 'counts.csv').write_text(
                'barangay,official_sitios,official_source,households_2015,households_source\n'
                'Camp IV,9,profile,687,PSA\nTabunoc,,,3454,PSA\n', encoding='utf-8')
            points, outlines, counts = read_research(d / 'points.csv', d / 'outlines.geojson', d / 'counts.csv')
        self.assertEqual(points[canonical('Tabunoc')][0]['name'], 'Purok Kalinaw')
        self.assertEqual(points[canonical('Camp IV')][0]['lat'], '')
        self.assertIn((canonical('Tabunok'), 'Purok Kalinaw'), outlines)
        self.assertEqual(counts[canonical('Camp 4')], (9, 687))
        self.assertEqual(counts[canonical('Tabunoc')], (None, 3454))


class PolygonsTests(SimpleTestCase):
    def test_polygons_come_out_of_any_shape_and_lines_are_dropped(self):
        a, b = Polygon.from_bbox((0, 0, 1, 1)), Polygon.from_bbox((2, 0, 3, 1))
        self.assertEqual(len(pe.polygons(a)), 1)
        self.assertEqual(len(pe.polygons(MultiPolygon(a, b))), 2)
        self.assertEqual(len(pe.polygons(GeometryCollection(a, LineString((0, 0), (1, 1))))), 1)


class AreaTests(SimpleTestCase):
    def test_area_in_square_meters_near_talisay(self):
        # 0.001 degree square at 10.25 N: about 111 m by 109.5 m
        sq = MultiPolygon(Polygon.from_bbox((123.84, 10.25, 123.841, 10.251)), srid=4326)
        self.assertAlmostEqual(pe.area_m2(sq), 111_320 * 111_320 * math.cos(math.radians(10.2505)) * 1e-6,
                               delta=50)
