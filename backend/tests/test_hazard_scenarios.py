from datetime import date, timedelta

from django.test import SimpleTestCase

from apps.history import forecast
from apps.history.hazard_scenarios import (
    PeriodChance, any_chance, pair_chance, period_chance, period_dates,
    scenario_dates, shift_dates,
)

COMPLETE = [2021, 2022, 2023, 2024, 2025]


class PeriodDatesTests(SimpleTestCase):
    def test_month_matches_period_window(self):
        start, end = forecast.period_window(2024, 2)
        got = period_dates(2, None, 2024)
        self.assertEqual(got[0], start)
        self.assertEqual(got[-1], end - timedelta(days=1))
        self.assertEqual(len(got), 29)

    def test_date_matches_period_window(self):
        start, end = forecast.period_window(2023, 6, 10)
        got = period_dates(6, 10, 2023)
        self.assertEqual(got, [start + timedelta(days=i) for i in range((end - start).days)])
        self.assertEqual(len(got), 7)

    def test_week_is_the_date_plus_minus_3_days(self):
        got = period_dates(8, 15, 2022)
        self.assertEqual((got[0], got[-1]), (date(2022, 8, 12), date(2022, 8, 18)))


class ShiftDatesTests(SimpleTestCase):
    def test_feb_29_becomes_feb_28_in_a_non_leap_year(self):
        self.assertEqual(shift_dates([date(2024, 2, 29)], 2024, 2023), [date(2023, 2, 28)])

    def test_keeps_year_offset(self):
        got = shift_dates([date(2024, 12, 31), date(2025, 1, 2)], 2024, 2021)
        self.assertEqual(got, [date(2021, 12, 31), date(2022, 1, 2)])


class ScenarioDatesTests(SimpleTestCase):
    def test_scenario_years_are_strictly_before_the_year(self):
        got = scenario_dates(5, 10, 2024, COMPLETE)
        self.assertEqual(list(got), [2021, 2022, 2023])

    def test_month_view_uses_each_scenario_years_own_month(self):
        got = scenario_dates(2, None, None, [2023, 2024])
        self.assertEqual(len(got[2023]), 28)
        self.assertEqual(len(got[2024]), 29)

    def test_week_crossing_new_year_needs_next_year_rain(self):
        got = scenario_dates(12, 30, 2026, complete=COMPLETE)
        self.assertEqual(sorted(got), [2021, 2022, 2023, 2024])
        self.assertEqual(got[2024][-1], date(2025, 1, 2))

    def test_drops_scenario_whose_dates_fall_in_incomplete_year(self):
        got = scenario_dates(12, 30, 2026, complete=[2021, 2022, 2024])
        self.assertEqual(list(got), [2021])

    def test_feb_29_week_is_the_history_window_in_a_common_year(self):
        got = scenario_dates(2, 29, 2024, [2023])
        self.assertEqual(got[2023], [date(2023, 2, 25) + timedelta(days=i) for i in range(7)])
        self.assertEqual(got[2023][-1], date(2023, 3, 3))

    def test_leap_february_into_leap_year_keeps_29_days(self):
        got = scenario_dates(2, None, 2028, [2024])
        self.assertEqual(len(got[2024]), 29)

    def test_leap_february_into_common_year_has_28_distinct_days(self):
        got = scenario_dates(2, None, 2028, [2025])
        self.assertEqual(got[2025], [date(2025, 2, 1) + timedelta(days=i) for i in range(28)])
        self.assertEqual(got[2025][-1], date(2025, 2, 28))

    def test_common_february_into_leap_year_has_no_29th(self):
        got = scenario_dates(2, None, 2027, [2024])
        self.assertEqual(len(got[2024]), 28)
        self.assertNotIn(date(2024, 2, 29), got[2024])

    def test_early_january_week_runs_back_into_previous_year(self):
        got = scenario_dates(1, 2, 2026, [2022, 2023, 2024, 2025])
        self.assertEqual(got[2023], [date(2022, 12, 30) + timedelta(days=i) for i in range(7)])
        self.assertEqual(got[2023][-1], date(2023, 1, 5))
        self.assertNotIn(2022, got)  # its week needs 2021 rain

    def test_early_january_week_dropped_when_previous_year_incomplete(self):
        got = scenario_dates(1, 2, 2026, [2023, 2024, 2025])
        self.assertEqual(list(got), [2024, 2025])

    def test_ordinary_month_with_year(self):
        got = scenario_dates(11, None, 2026, [2024, 2025])
        self.assertEqual(len(got[2024]), 30)
        self.assertEqual((got[2024][0], got[2024][-1]), (date(2024, 11, 1), date(2024, 11, 30)))

    def test_shift_dates_drops_duplicates_in_order(self):
        dates = [date(2024, 2, 28), date(2024, 2, 29), date(2024, 3, 1)]
        self.assertEqual(shift_dates(dates, 2024, 2023), [date(2023, 2, 28), date(2023, 3, 1)])


class PeriodChanceTests(SimpleTestCase):
    def test_period_chance_is_the_mean_of_one_minus_the_product(self):
        dates = {2021: [date(2021, 3, 1), date(2021, 3, 2)], 2022: [date(2022, 3, 1), date(2022, 3, 2)]}
        pc = period_chance(lambda d: 0.1 if d.year == 2021 else 0.0, dates)
        self.assertIsInstance(pc, PeriodChance)
        self.assertAlmostEqual(pc.probability, 0.095)
        self.assertAlmostEqual(pc.expected, 0.1)
        self.assertEqual((pc.low, round(pc.high, 2), pc.years), (0.0, 0.19, [2021, 2022]))

    def test_skips_scenario_with_a_none_day(self):
        dates = {2021: [date(2021, 3, 1), date(2021, 3, 2)], 2022: [date(2022, 3, 1), date(2022, 3, 2)]}
        pc = period_chance(lambda d: None if d == date(2021, 3, 2) else 0.5, dates)
        self.assertEqual(pc.years, [2022])
        self.assertAlmostEqual(pc.probability, 0.75)

    def test_none_when_nothing_is_left(self):
        self.assertIsNone(period_chance(lambda d: None, {2021: [date(2021, 3, 1)]}))
        self.assertIsNone(period_chance(lambda d: 0.1, {}))

    def test_pair_chance_combines_inside_each_scenario(self):
        dates = {2021: [date(2021, 8, 1)], 2022: [date(2022, 8, 1)]}
        f = lambda d: 0.5 if d.year == 2021 else 0.0
        pc = pair_chance(f, f, dates)
        self.assertAlmostEqual(pc.probability, 0.375)  # not 1 - 0.75*0.75 = 0.4375

    def test_pair_chance_expected_is_the_sum_over_hazards(self):
        dates = {2021: [date(2021, 8, 1)], 2022: [date(2022, 8, 1)]}
        f = lambda d: 0.5 if d.year == 2021 else 0.0
        pc = pair_chance(f, f, dates)
        self.assertAlmostEqual(pc.expected, 0.5)  # mean of 1.0 and 0.0
        self.assertEqual((pc.low, pc.high, pc.years), (0.0, 0.75, [2021, 2022]))

    def test_pair_chance_skips_none_from_either_and_returns_none(self):
        dates = {2021: [date(2021, 8, 1)]}
        self.assertIsNone(pair_chance(lambda d: None, lambda d: 0.1, dates))
        self.assertIsNone(pair_chance(lambda d: 0.1, lambda d: None, dates))

    def test_any_chance(self):
        self.assertAlmostEqual(any_chance([0.2, 0.375]), 0.5)
        self.assertEqual(any_chance([]), 0.0)
