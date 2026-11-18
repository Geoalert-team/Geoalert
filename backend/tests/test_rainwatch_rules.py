from django.test import SimpleTestCase, TestCase

from apps.history.exposure import read_exposure
from apps.history.hazard_data import read_terrain
from apps.rainwatch.models import RainWatchRules
from apps.rainwatch.rules import (
    BALANCED, GREEN, LEVEL_NAMES, ORANGE, RED, YELLOW, band, combine, flood_exposed_ids, flood_level,
    one_step_lower, slide_level, steep_ids,
)


class RulesTests(SimpleTestCase):
    def test_level_names(self):
        self.assertEqual(LEVEL_NAMES, ('Green', 'Yellow', 'Orange', 'Red'))
        self.assertEqual((GREEN, YELLOW, ORANGE, RED), (0, 1, 2, 3))

    def test_band(self):
        self.assertEqual(band(0, (30, 60, 120)), GREEN)
        self.assertEqual(band(120, (30, 60, 120)), RED)

    def test_tino_day_is_red(self):
        self.assertEqual(flood_level(192.5, False, BALANCED), RED)

    def test_limited_barangay_one_step_lower(self):
        self.assertEqual(one_step_lower(flood_level(192.5, False, BALANCED)), ORANGE)

    def test_wet_ground_lowers_flood_cutoffs(self):
        self.assertEqual(flood_level(23, True, BALANCED), YELLOW)
        self.assertEqual(flood_level(23, False, BALANCED), GREEN)

    def test_cutoff_is_inclusive(self):
        self.assertEqual(flood_level(30, False, BALANCED), YELLOW)

    def test_landslide_pileups(self):
        self.assertEqual(slide_level(55.5, False, BALANCED), YELLOW)
        self.assertEqual(slide_level(48.7, True, BALANCED), ORANGE)
        self.assertEqual(slide_level(226.4, False, BALANCED), RED)
        self.assertEqual(slide_level(31.1, False, BALANCED), GREEN)

    def test_one_step_lower_floors_at_green(self):
        self.assertEqual(one_step_lower(GREEN), GREEN)
        self.assertEqual(one_step_lower(RED), ORANGE)

    def test_limits_from_repo_files(self):
        self.assertEqual(flood_exposed_ids(read_exposure(), BALANCED), {1, 2, 5, 6, 8, 10, 11, 12, 16, 17, 18, 19, 20, 21})
        self.assertEqual(steep_ids(read_terrain(), BALANCED), {4, 7, 8, 13, 14, 22, 23})

    def test_combine(self):
        self.assertEqual(combine(YELLOW, [ORANGE]), ORANGE)
        self.assertEqual(combine(RED, [YELLOW]), RED)
        self.assertIsNone(combine(None, []))
        self.assertEqual(combine(None, [YELLOW]), YELLOW)


class RulesRowTests(TestCase):
    def test_model_row_converts(self):
        self.assertEqual(RainWatchRules.current().as_rules(), BALANCED)
