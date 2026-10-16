import random
from collections import Counter
from datetime import datetime, timezone

from django.test import SimpleTestCase
from faker import Faker

from apps.hazards import fake_data

# A 4 x 4 grid over part of Talisay; row 0 is the north edge
BOUNDS = [[10.24, 123.82], [10.26, 123.84]]
CLASSES = bytes([
    0, 1, 1, 0,
    1, 2, 3, 1,
    1, 4, 5, 1,
    0, 1, 1, 0,
])
NOW = datetime(2026, 10, 10, 12, tzinfo=timezone.utc)


def make_spots(seed=1):
    rnd = random.Random(seed)
    grid = fake_data.SusceptibilityGrid(CLASSES, 4, 4, BOUNDS)
    return {h: fake_data.Spots(grid, rnd, fake_data.MIN_CLASS[h]) for h in fake_data.HAZARDS}, rnd


def make_fake(seed=1):
    fake = Faker('fil_PH')
    fake.seed_instance(seed)
    return fake


class SusceptibilityGridTests(SimpleTestCase):
    def test_pixel_and_lnglat_agree(self):
        grid = fake_data.SusceptibilityGrid(CLASSES, 4, 4, BOUNDS)
        lng, lat = grid.to_lnglat(2.5, 2.5)  # centre of the class-5 cell
        self.assertEqual(grid.class_at(lng, lat), 5)
        self.assertEqual(grid.class_at(123.0, 10.0), 0)  # outside the raster


class SpotsTests(SimpleTestCase):
    def test_draws_only_susceptible_cells_and_favors_the_highest(self):
        spots, _ = make_spots()
        drawn = Counter(spots['Flood'].draw()[2] for _ in range(2000))
        self.assertEqual(set(drawn), {3, 4, 5})
        self.assertGreater(drawn[5], drawn[4])
        self.assertGreater(drawn[4], drawn[3])

    def test_fire_also_uses_low_ground(self):
        spots, _ = make_spots()
        drawn = {spots['Fire'].draw()[2] for _ in range(500)}
        self.assertIn(2, drawn)
        self.assertNotIn(1, drawn)

    def test_raises_when_nothing_is_susceptible(self):
        grid = fake_data.SusceptibilityGrid(bytes([1, 1, 1, 1]), 2, 2, BOUNDS)
        with self.assertRaises(ValueError):
            fake_data.Spots(grid, random.Random(1), 3)


class HistoricalEventsTests(SimpleTestCase):
    def test_events_are_in_the_past_and_resolve_after_they_occur(self):
        spots, rnd = make_spots()
        events = fake_data.historical_events(spots, 3, NOW, make_fake(), rnd)
        self.assertTrue(events)
        for e in events:
            self.assertLessEqual(e['occurred_at'], NOW)
            self.assertLessEqual(e['occurred_at'], e['resolved_at'])
            self.assertLessEqual(e['resolved_at'], NOW)
            self.assertGreaterEqual(e['occurred_at'].year, NOW.year - 2)
            self.assertIn(e['severity'], fake_data.SEVERITIES)

    def test_seasons_follow_talisay(self):
        spots, rnd = make_spots()
        events = fake_data.historical_events(spots, 30, NOW, make_fake(), rnd)
        months = {h: Counter(e['occurred_at'].month for e in events if e['hazard'] == h) for h in fake_data.HAZARDS}
        # Floods peak in the typhoon months, fires in the dry season
        self.assertGreater(sum(months['Flood'][m] for m in (9, 10, 11)), 3 * sum(months['Flood'][m] for m in (2, 3, 4)))
        self.assertGreater(sum(months['Fire'][m] for m in (3, 4, 5)), 2 * sum(months['Fire'][m] for m in (7, 8, 9)))

    def test_same_seed_gives_same_data(self):
        def run():
            spots, rnd = make_spots(7)
            return [(e['hazard'], e['severity'], e['lng'], e['description'])
                    for e in fake_data.historical_events(spots, 2, NOW, make_fake(7), rnd)]
        self.assertEqual(run(), run())


class ActiveEventsTests(SimpleTestCase):
    def test_active_events_are_recent(self):
        spots, rnd = make_spots()
        events = fake_data.active_events(spots, 20, NOW, make_fake(), rnd)
        self.assertEqual(len(events), 20)
        for e in events:
            self.assertLess((NOW - e['occurred_at']).days, 7)


class PastEventNearTests(SimpleTestCase):
    def test_lands_nearby_on_prone_ground_and_in_the_past(self):
        spots, rnd = make_spots()
        grid = spots['Flood'].grid
        lng, lat = grid.to_lnglat(2.5, 2.5)  # the class-5 cell
        for _ in range(30):
            e = fake_data.past_event_near('Flood', lng, lat, grid, 5, NOW, make_fake(), rnd, spread_m=300)
            self.assertEqual(e['hazard'], 'Flood')
            self.assertLess(abs(e['lat'] - lat) * 111320, 301)
            self.assertGreaterEqual(grid.class_at(e['lng'], e['lat']), fake_data.MIN_CLASS['Flood'])
            self.assertLessEqual((NOW - e['occurred_at']).days, 5 * 366)
            self.assertGreaterEqual((NOW - e['occurred_at']).days, 14)
            self.assertLessEqual(e['occurred_at'], e['resolved_at'])


class ImpactTests(SimpleTestCase):
    def sizes(self, hazard, severity, n=300):
        rnd = random.Random(3)
        return [fake_data.impact(hazard, severity, rnd) for _ in range(n)]

    def test_fires_are_small_and_floods_are_wide(self):
        for severity in fake_data.SEVERITIES:
            fires = self.sizes('Fire', severity)
            floods = self.sizes('Flood', severity)
            self.assertLessEqual(max(f['radius_m'] for f in fires), 120)
            self.assertLess(sorted(f['radius_m'] for f in fires)[150], sorted(f['radius_m'] for f in floods)[150])

    def test_fire_zone_matches_the_houses_burned(self):
        for f in self.sizes('Fire', 'Red'):
            houses = f['details']['houses']
            burned = (houses * fake_data.GROUND_PER_HOUSE_M2 / 3.1416) ** 0.5
            self.assertGreaterEqual(f['radius_m'], round(burned))
            self.assertLessEqual(f['radius_m'], round(burned) + 30)
            if f['displaced'] is not None:
                self.assertGreaterEqual(f['displaced'], houses * 4)  # at least one household per house

    def test_minor_events_displace_nobody(self):
        for hazard in fake_data.HAZARDS:
            for f in self.sizes(hazard, 'Green', 50):
                self.assertIn(f['displaced'], (0, None))
                self.assertIn(f['casualties'], (0, None))

    def test_descriptions_fill_every_placeholder(self):
        rnd = random.Random(5)
        fake = make_fake(5)
        for hazard in fake_data.HAZARDS:
            for severity in fake_data.SEVERITIES:
                for _ in range(20):
                    text = fake_data.describe(hazard, severity, fake_data.impact(hazard, severity, rnd)['details'], fake)
                    self.assertNotIn('{', text)


class CircleRingTests(SimpleTestCase):
    def test_ring_is_closed_and_about_the_right_size(self):
        ring = fake_data.circle_ring(123.83, 10.25, 300)
        self.assertEqual(ring[0], ring[-1])
        self.assertAlmostEqual((ring[0][0] - 123.83) * 111320 * 0.984, 300, delta=5)
