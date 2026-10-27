"""Seasonal likelihood: rule-based counts of past months, recent years weighted more."""
from datetime import date, datetime, timezone

from django.test import SimpleTestCase

from apps.history.forecast import (
    drop_samples, level_for, likelihood, period_window, seasonal_forecast, seasonal_profile, year_weights,
    years_for_month, years_for_period,
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


class DropSamplesTests(SimpleTestCase):
    events = [{'barangay': 'A', 'is_sample': True}, {'barangay': 'B', 'is_sample': False}]

    def test_keeps_everything_unless_asked(self):
        self.assertEqual(drop_samples(self.events, False), self.events)

    def test_drops_sample_rows_when_asked(self):
        self.assertEqual(drop_samples(self.events, True), [{'barangay': 'B', 'is_sample': False}])


class PeriodWindowTests(SimpleTestCase):
    def test_a_month_runs_to_the_first_of_the_next(self):
        self.assertEqual(period_window(2025, 11), (date(2025, 11, 1), date(2025, 12, 1)))
        self.assertEqual(period_window(2025, 12), (date(2025, 12, 1), date(2026, 1, 1)))

    def test_a_date_is_the_week_around_it(self):
        self.assertEqual(period_window(2025, 11, 15), (date(2025, 11, 12), date(2025, 11, 19)))
        # Across the new year, and 29 February in a year without one
        self.assertEqual(period_window(2025, 12, 30), (date(2025, 12, 27), date(2026, 1, 3)))
        self.assertEqual(period_window(2025, 2, 29), (date(2025, 2, 25), date(2025, 3, 4)))

    def test_a_date_week_counts_once_it_is_over(self):
        first = datetime(2022, 1, 1, tzinfo=TZ)
        # NOW is 19 Oct 2026: the week of 15 Oct ended on the 18th, the week of 17 Oct hasn't
        self.assertIn(2026, years_for_period(10, 15, NOW.date(), first))
        self.assertNotIn(2026, years_for_period(10, 17, NOW.date(), first))


class PeriodForecastTests(SimpleTestCase):
    def events(self):
        return [
            ev(2021, 1, barangay=9),                                  # starts the record
            ev(2021, 11), ev(2022, 11), ev(2023, 11),                 # B1 every November to 2023
            ev(2024, 11, barangay=2), ev(2024, 11, barangay=2),       # 2024: B2, never hit before
        ]

    def test_a_month_and_year_reads_only_the_years_before_it(self):
        out = seasonal_forecast(self.events(), 11, NOW, year=2024)
        self.assertEqual(out['years'], [2021, 2022, 2023])
        b1 = next(r for r in out['results'] if r['barangay'] == 'B1')
        self.assertEqual((b1['level'], b1['years_hit'], b1['actual']), ('High', 3, 0))

    def test_a_past_month_and_year_shows_what_happened(self):
        out = seasonal_forecast(self.events(), 11, NOW, year=2024)
        self.assertEqual(out['outcome'], {'complete': True, 'events': 2})
        # B2 wasn't expected, but it happened: it is listed with what happened
        b2 = next(r for r in out['results'] if r['barangay'] == 'B2')
        self.assertEqual((b2['level'], b2['actual']), ('None', 2))

    def test_a_future_month_and_year_is_the_plain_month(self):
        plain = seasonal_forecast(self.events(), 11, NOW)
        future = seasonal_forecast(self.events(), 11, NOW, year=2027)
        self.assertEqual(future['years'], plain['years'])
        self.assertEqual([(r['barangay'], r['level']) for r in future['results']],
                         [(r['barangay'], r['level']) for r in plain['results']])
        self.assertIsNone(future['outcome'])
        self.assertNotIn('actual', future['results'][0])

    def test_an_exact_date_counts_the_week_around_it(self):
        events = [ev(2021, 1, barangay=9),
                  {**ev(2022, 11), 'when': datetime(2022, 11, 14, tzinfo=TZ)},   # in the week of the 15th
                  {**ev(2023, 11), 'when': datetime(2023, 11, 25, tzinfo=TZ)}]   # same month, not that week
        out = seasonal_forecast(events, 11, NOW, day=15, year=2027)
        b1 = next(r for r in out['results'] if r['barangay'] == 'B1')
        self.assertEqual((b1['years_hit'], b1['years_considered']), (1, 5))
        self.assertEqual(out['window'], {'start': date(2027, 11, 12), 'end': date(2027, 11, 18)})

    def test_the_profile_for_a_year_reads_only_the_years_before_it(self):
        before = seasonal_profile(self.events(), NOW, barangay_id=2, hazard='Flood', year=2024)
        after = seasonal_profile(self.events(), NOW, barangay_id=2, hazard='Flood')
        self.assertEqual(before[10]['level'], 'None')   # B2 had never flooded before 2024
        self.assertNotEqual(after[10]['level'], 'None')


class ForecastViewParamTests(SimpleTestCase):
    def get(self, **params):
        from rest_framework.test import APIRequestFactory
        from apps.history.views import HistoricalForecastView
        return HistoricalForecastView.as_view()(APIRequestFactory().get('/', params))

    def test_bad_periods_are_refused_before_reading_anything(self):
        for params, word in [({'date': '2026-13-01'}, 'date'), ({'date': 'soon'}, 'date'),
                             ({'month': '11', 'year': 'next'}, 'year'), ({'month': '11', 'year': '1800'}, 'year')]:
            with self.subTest(params=params):
                response = self.get(**params)
                self.assertEqual(response.status_code, 400)
                self.assertIn(word, response.data['error'])
