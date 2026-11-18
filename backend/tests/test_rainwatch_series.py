from datetime import date, datetime, timedelta, timezone

from django.test import SimpleTestCase

from apps.rainwatch.series import (
    CITY, GRID, SOURCE_PREFERENCE, UPLAND, RunData, at_point, manila_day_total, place_hours, stitched,
)

INIT = datetime(2026, 11, 17, 18, tzinfo=timezone.utc)  # 02:00 PHT on 18 Nov


def flat(mm, n):
    return {p: [mm] * n for p in GRID}


class SeriesTests(SimpleTestCase):
    def test_bilinear_corners_and_city(self):
        v = {(10.25, 123.75): 0, (10.25, 124.0): 100, (10.5, 123.75): 0, (10.5, 124.0): 100}
        self.assertAlmostEqual(at_point(v, CITY), 28.48, places=2)
        v2 = {(10.25, 123.75): 0, (10.25, 124.0): 0, (10.5, 123.75): 100, (10.5, 124.0): 100}
        self.assertAlmostEqual(at_point(v2, CITY), 13.4, places=2)
        self.assertEqual(at_point(v, (10.25, 124.0)), 100)

    def test_day_missing_first_two_hours_is_partial(self):
        h = place_hours(stitched([RunData('gfs-nomads', INIT, flat(1.0, 96))]), CITY)
        self.assertEqual(manila_day_total(h, date(2026, 11, 18)), (22.0, False))
        self.assertEqual(manila_day_total(h, date(2026, 11, 19)), (24.0, True))

    def test_older_run_fills_earlier_hours(self):
        older = RunData('gfs-nomads', INIT - timedelta(hours=6), flat(2.0, 6))
        h = place_hours(stitched([older, RunData('gfs-nomads', INIT, flat(1.0, 96))]), CITY)
        self.assertEqual(manila_day_total(h, date(2026, 11, 18)), (26.0, True))

    def test_newest_run_wins_and_nomads_wins_ties(self):
        a = RunData('gfs-dynamical', INIT, flat(5.0, 6))
        b = RunData('gfs-nomads', INIT, flat(1.0, 6))
        self.assertEqual(stitched([a, b])[INIT][(10.25, 123.75)], 1.0)
        self.assertEqual(stitched([b, a])[INIT][(10.25, 123.75)], 1.0)

    def test_newer_run_beats_preferred_source(self):
        old = RunData('gfs-nomads', INIT, flat(1.0, 6))
        new = RunData('gfs-dynamical', INIT + timedelta(hours=6), flat(7.0, 6))
        self.assertEqual(stitched([old, new])[INIT + timedelta(hours=6)][(10.5, 124.0)], 7.0)
        self.assertEqual(stitched([old, new])[INIT][(10.5, 124.0)], 1.0)

    def test_place_hours_needs_all_four_points(self):
        s = {p: [1.0, 1.0] for p in GRID}
        s[GRID[0]] = [1.0]
        h = place_hours(stitched([RunData('gfs-nomads', INIT, s)]), UPLAND)
        self.assertEqual(list(h), [INIT])

    def test_constants(self):
        self.assertEqual(len(GRID), 4)
        self.assertEqual(SOURCE_PREFERENCE, {'gfs-nomads': 1, 'gfs-dynamical': 0})
