"""Seasonal likelihood: rule-based counts of past months, recent years weighted more."""
from datetime import datetime, timezone

from django.test import SimpleTestCase

from apps.history.forecast import (
    level_for, likelihood, seasonal_forecast, seasonal_profile, year_weights, years_for_month,
)

TZ = timezone.utc
NOW = datetime(2026, 10, 19, tzinfo=TZ)


def ev(year, month, barangay=1, hazard='Flood', severity='Orange'):
    return {'barangay_id': barangay, 'barangay': f'B{barangay}', 'hazard': hazard,
            'when': datetime(year, month, 10, tzinfo=TZ), 'severity': severity}


class YearsTests(SimpleTestCase):
    def test_month_not_over_yet_is_left_out(self):
        first = datetime(2022, 1, 1, tzinfo=TZ)
        self.assertEqual(years_for_month(11, NOW, first), [2025, 2024, 2023, 2022])
        self.assertEqual(years_for_month(9, NOW, first), [2026, 2025, 2024, 2023, 2022])
        self.assertNotIn(2026, years_for_month(10, NOW, first))  # October is still running

    def test_months_before_the_record_started_are_left_out(self):
        first = datetime(2022, 6, 1, tzinfo=TZ)
        self.assertNotIn(2022, years_for_month(3, NOW, first))
        self.assertIn(2022, years_for_month(7, NOW, first))

    def test_no_history_means_no_years(self):
        self.assertEqual(years_for_month(5, NOW, None), [])

    def test_recent_years_weigh_more(self):
        w = year_weights([2025, 2022])
        self.assertEqual(w[2025], 1)
        self.assertAlmostEqual(w[2022], 0.5)


class LikelihoodTests(SimpleTestCase):
    def test_every_year_hit_is_certain(self):
        w = year_weights([2023, 2024, 2025])
        share, expected, hit = likelihood({2023: 1, 2024: 2, 2025: 1}, w)
        self.assertAlmostEqual(share, 1.0)
        self.assertEqual(hit, 3)
        self.assertGreater(expected, 1)

    def test_recent_hit_counts_more_than_old_one(self):
        w = year_weights([2021, 2025])
        recent, _, _ = likelihood({2025: 1}, w)
        old, _, _ = likelihood({2021: 1}, w)
        self.assertGreater(recent, old)

    def test_levels(self):
        self.assertEqual(level_for(0, 0), 'None')
        self.assertEqual(level_for(0.1, 0.1), 'Low')
        self.assertEqual(level_for(0.4, 0.4), 'Moderate')
        self.assertEqual(level_for(0.7, 0.7), 'High')
        self.assertEqual(level_for(0.2, 2.5), 'High')  # rarely, but many at once


class ForecastTests(SimpleTestCase):
    def events(self):
        return [
            ev(2022, 1, barangay=9),            # starts the record
            ev(2022, 11), ev(2023, 11), ev(2024, 11), ev(2025, 11),   # B1 floods every November
            ev(2023, 11, barangay=2),                                   # B2 once
            ev(2024, 4, barangay=3, hazard='Fire', severity='Red'),     # a different month
        ]

    def test_ranks_the_regular_barangay_first(self):
        out = seasonal_forecast(self.events(), 11, NOW)
        self.assertEqual(out['years'], [2022, 2023, 2024, 2025])
        first = out['results'][0]
        self.assertEqual((first['barangay'], first['level'], first['years_hit']), ('B1', 'High', 4))
        b2 = next(r for r in out['results'] if r['barangay'] == 'B2')
        self.assertEqual(b2['level'], 'Low')

    def test_other_months_do_not_count(self):
        out = seasonal_forecast(self.events(), 11, NOW)
        self.assertFalse(any(r['hazard_type'] == 'Fire' for r in out['results']))
        april = seasonal_forecast(self.events(), 4, NOW)
        self.assertEqual([r['barangay'] for r in april['results']], ['B3'])
        self.assertEqual(april['results'][0]['typical_severity'], 'Red')

    def test_summary_keeps_each_barangays_worst(self):
        out = seasonal_forecast(self.events(), 11, NOW)
        levels = {r['barangay']: r['level'] for r in out['by_barangay']}
        self.assertEqual(levels, {'B1': 'High', 'B2': 'Low'})

    def test_short_history_is_flagged(self):
        out = seasonal_forecast([ev(2025, 3), ev(2025, 11)], 11, NOW)
        self.assertTrue(out['limited'])

    def test_profile_peaks_in_the_flood_month(self):
        months = seasonal_profile(self.events(), NOW, barangay_id=1, hazard='Flood')
        self.assertEqual(len(months), 12)
        self.assertEqual(max(months, key=lambda m: m['probability'])['month'], 11)
        self.assertEqual(months[5]['level'], 'None')
