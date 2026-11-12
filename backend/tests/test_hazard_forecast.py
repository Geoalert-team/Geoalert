"""
Flood and landslide on the forecast: the deployed rain-and-terrain model, its
cache and lock, and the rows, levels and chart it puts on a seasonal_forecast
result. Toy files in a temp folder stand in for apps/history/data/.
"""
import shutil
import tempfile
import threading
import time
from collections import Counter
from datetime import date, datetime
from math import prod
from pathlib import Path
from unittest import mock

import numpy as np
from django.contrib.gis.geos import MultiPolygon
from django.core.cache import cache
from django.test import SimpleTestCase, TestCase

from apps.barangays.models import Barangay
from apps.hazards.models import HazardType
from apps.history import hazard_data, hazard_forecast, hazard_models, model_forecast
from apps.history.forecast import empty_profile, seasonal_forecast
from apps.history.hazard_data import MANILA, RAIN_FEATURES, TERRAIN_FEATURES, rain_windows, write_terrain
from apps.history.hazard_scenarios import period_chance, period_dates, scenario_dates
from apps.history.models import HistoricalRecord
from tests.fire_setup import box
from tests.hazard_fixtures import toy_event_records, toy_source_ref, write_toy_files

TODAY = date(2026, 11, 12)
YEARS = [2021, 2022, 2023, 2024, 2025]        # the toy rain file's complete years
MODELLED = ('Flood', 'Landslide')
FAST = {'random_forest': {'n_estimators': 10, 'min_samples_leaf': 5}, 'xgboost': {'n_estimators': 10}}
REPORT_MISSING = 'The model report is missing; run manage.py test_hazard_models.'


def at(day):
    return datetime(day.year, day.month, day.day, 12, tzinfo=MANILA)


class RoundedTests(SimpleTestCase):
    def test_a_positive_value_that_would_round_to_zero_keeps_two_significant_figures(self):
        rounded = hazard_forecast._rounded
        self.assertEqual(rounded(0.0234, 3), 0.023)
        self.assertEqual(rounded(0.00041234, 3), 0.00041)
        self.assertEqual(rounded(0.0000357, 3), 3.6e-05)
        self.assertEqual(rounded(0.004, 2), 0.004)                  # 2 significant figures, not 0.0
        self.assertEqual(rounded(0.0123, 2), 0.01)
        self.assertIsInstance(rounded(0.00041234, 3), float)
        # an exact 0 stays 0, and no figure stays no figure
        self.assertEqual(rounded(0.0, 3), 0.0)
        self.assertEqual(rounded(0, 2), 0)
        self.assertIsNone(rounded(None, 3))
        # at or above the rounding step, exactly what round() gives
        for x, digits in ((0.0005, 3), (0.000500001, 3), (0.001, 3), (0.4567, 3), (0.9995, 3), (1.0, 3),
                          (0.005, 2), (0.0123, 2), (1.005, 2), (2.675, 2), (31.0, 2)):
            with self.subTest(x=x, digits=digits):
                self.assertNotEqual(round(x, digits), 0)
                self.assertEqual(rounded(x, digits), round(x, digits))


class HazardForecastTests(TestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.barangays = [self.barangay(f'Toy {i}', i) for i in range(3)]
        self.ids = [b.id for b in self.barangays]
        self.names = {b.id: b.name for b in self.barangays}
        self.terrain, self.rain, self.pos = write_toy_files(self.tmp, self.ids)
        self.kinds = {n: HazardType.objects.create(name=n, logo_class=n.lower()) for n in ('Fire', *MODELLED)}
        for hazard in MODELLED:
            HistoricalRecord.objects.bulk_create(
                [HistoricalRecord(barangay_id=b, hazard_type=self.kinds[hazard], severity_level='Green',
                                  source_ref=toy_source_ref(hazard, b, d), occurred_at=at(d),
                                  hazard_subcategory='TOY')
                 for b, d in sorted(self.pos)])
        self.report_path = self.tmp / 'hazard_model_report.json'
        # NASA POWER is never called from the tests: the live rain is down unless a test says otherwise
        self.live = mock.Mock(return_value=None)
        for patcher in (mock.patch.object(hazard_data, 'DATA_DIR', self.tmp),
                        mock.patch.object(hazard_models, 'REPORT_PATH', self.report_path),
                        mock.patch.object(hazard_forecast, 'recent_rain', self.live)):
            patcher.start()
            self.addCleanup(patcher.stop)

    def barangay(self, name, slot):
        return Barangay.objects.create(name=name, municipality='Talisay',
                                       boundary=MultiPolygon(box(1000 * slot, 0, 1000 * slot + 900, 900), srid=4326))

    def events(self):
        """What the history counts: the toy floods, one city-wide flood with no barangay, and one fire."""
        out = [{'barangay_id': b, 'barangay': self.names[b], 'hazard': 'Flood', 'severity': 'Green',
                'is_sample': False, 'when': at(d)} for b, d in sorted(self.pos)]
        out.append({'barangay_id': self.ids[0], 'barangay': self.names[self.ids[0]], 'hazard': 'Flood',
                    'severity': 'Orange', 'is_sample': False, 'when': at(date(2023, 7, 9))})
        out.append({'barangay_id': None, 'barangay': None, 'hazard': 'Flood', 'severity': 'Red',
                    'is_sample': False, 'when': at(date(2024, 7, 20))})
        out.append({'barangay_id': self.ids[0], 'barangay': self.names[self.ids[0]], 'hazard': 'Fire',
                    'severity': 'Orange', 'is_sample': False, 'when': at(date(2024, 7, 5))})
        return out

    def counting(self, month, day=None, year=None, barangay=None, today=TODAY):
        """The result as the view builds it before the models: the rows' history from counting, an empty chart."""
        now = at(today)
        result = seasonal_forecast(self.events(), month, now, day=day, year=year)
        result['profile'] = empty_profile()
        result['model_hazards'] = []
        result['profile_method'] = 'unavailable'
        return result

    def forecast(self, month, day=None, year=None, hazards=MODELLED, barangay=None, today=TODAY):
        result = self.counting(month, day, year, barangay, today)
        scen = hazard_forecast.use_hazard_models(
            result, month=month, day=day, year=year, hazards=list(hazards), barangay=barangay,
            places=model_forecast.places(), today=today)
        return result, scen

    @staticmethod
    def rows(result, hazard):
        return [r for r in result['results'] if r['hazard_type'] == hazard]

    def row(self, result, hazard, barangay_id):
        (found,) = [r for r in self.rows(result, hazard) if r['barangay_id'] == barangay_id]
        return found

    @staticmethod
    def chance(dep, barangay_id, month, day=None, year=None):
        return period_chance(dep.daily[barangay_id].get, scenario_dates(month, day, year, dep.complete_years))

    def assert_unavailable(self, row, reason):
        self.assertEqual((row['method'], row['probability'], row['expected_events'], row['level']),
                         ('unavailable', None, None, 'None'))
        self.assertEqual(row['reason'], reason)
        for key in ('model', 'range', 'rain_years', 'recorded_rain_probability', 'in_training'):
            self.assertNotIn(key, row)

    # ---- rows ----

    def test_every_barangay_gets_a_row_per_modelled_hazard(self):
        before = self.counting(7)
        self.assertTrue(any(r['barangay_id'] is None for r in self.rows(before, 'Flood')))   # the city-wide flood
        fire_before = self.rows(before, 'Fire')
        result, scen = self.forecast(7, hazards=('Fire', 'Flood', 'Landslide'))
        self.assertEqual(set(scen), set(MODELLED))
        for hazard in MODELLED:
            rows = self.rows(result, hazard)
            # one row per barangay with a boundary; the counting row with no barangay is gone
            self.assertEqual(sorted(r['barangay_id'] for r in rows), sorted(self.ids))
            self.assertTrue(all(r['method'] == 'model' for r in rows))
            self.assertIsInstance(scen[hazard]['deployed'], hazard_forecast.Deployed)
            self.assertEqual(set(scen[hazard]['chances']), set(self.ids))
        self.assertEqual(result['model_hazards'], ['Flood', 'Landslide'])
        self.assertEqual(result.get('unavailable_hazards', []), [])
        self.assertEqual(self.rows(result, 'Fire'), fire_before)            # fire is left as it was
        self.assertEqual({r['barangay_id'] for r in result['by_barangay']}, set(self.ids))
        ranked = [(r['level'], r['probability']) for r in result['results']]
        order = ['None', 'Low', 'Moderate', 'High']
        self.assertEqual(ranked, sorted(ranked, key=lambda lp: (-order.index(lp[0]), -lp[1])))

    def test_rows_carry_the_model_its_chance_range_and_rain_years(self):
        before = {r['barangay_id']: r for r in self.rows(self.counting(7), 'Flood')}
        self.assertIn(self.ids[0], before)
        result, scen = self.forecast(7)
        for hazard in MODELLED:
            dep = scen[hazard]['deployed']
            self.assertEqual(scen[hazard]['dates_by_s'], scenario_dates(7, None, None, YEARS))
            for b in self.ids:
                row, pc = self.row(result, hazard, b), self.chance(dep, b, 7)
                self.assertEqual(row['model'], 'logistic_regression')
                self.assertEqual(row['probability'], round(pc.probability, 3))
                self.assertEqual(row['expected_events'], round(pc.expected, 2))
                # rounded to 3 decimals, but a positive end under 0.0005 keeps 2 significant figures, never 0
                sent = hazard_forecast._rounded
                self.assertEqual(row['range'], [sent(pc.low, 3), sent(pc.high, 3)])
                self.assertEqual(row['range'][0] > 0, pc.low > 0)
                self.assertEqual(row['rain_years'], YEARS)
                self.assertEqual(row['level'], model_forecast.level_for(pc.probability))
                self.assertEqual(scen[hazard]['chances'][b], pc)
                self.assertNotIn('recorded_rain_probability', row)
                self.assertNotIn('in_training', row)
                self.assertNotIn('reason', row)
        # the history stays as forecast.py made it, beside the chance and never part of it
        for b, old in before.items():
            if b is None:
                continue                                   # the city-wide flood: no barangay, so no row
            row = self.row(result, 'Flood', b)
            for key in ('years_hit', 'years_considered', 'events', 'last_occurred', 'typical_severity', 'limited'):
                self.assertEqual(row[key], old[key], key)
        made = self.row(result, 'Landslide', self.ids[1])                  # no landslide was counted in July
        self.assertEqual((made['years_hit'], made['events'], made['last_occurred']), (0, 0, None))

    def test_level_comes_from_the_months_chance_in_the_week_view(self):
        dep = hazard_forecast.deployed('Flood')
        b = self.ids[0]
        week, month = self.chance(dep, b, 7, 15, 2025), self.chance(dep, b, 7, None, 2025)
        self.assertGreater(month.probability, week.probability)
        cut = (week.probability + month.probability) / 2      # Moderate for the month, Low for the week alone
        with mock.patch.object(model_forecast, 'MODERATE_CHANCE', cut), \
                mock.patch.object(model_forecast, 'HIGH_CHANCE', 2.0):
            result, scen = self.forecast(7, day=15, year=2025)
        row = self.row(result, 'Flood', b)
        self.assertEqual(row['probability'], round(week.probability, 3))      # the number is the week's
        self.assertEqual(row['level'], 'Moderate')                             # the level is the month's
        self.assertEqual(row['rain_years'], [2021, 2022, 2023, 2024])         # only the years before 2025
        self.assertEqual(scen['Flood']['dates_by_s'], scenario_dates(7, 15, 2025, YEARS))
        self.assertEqual(scen['Flood']['month_dates_by_s'], scenario_dates(7, None, 2025, YEARS))

    def test_recorded_rain_probability_only_when_the_period_has_recorded_days(self):
        dep = hazard_forecast.deployed('Flood')
        b = self.ids[0]
        # June 2024 lies wholly in the rain file: every day recorded, no scenario needed
        result, _ = self.forecast(6, year=2024)
        whole = 1 - prod(1 - dep.daily[b][d] for d in period_dates(6, None, 2024))
        self.assertEqual(self.row(result, 'Flood', b)['recorded_rain_probability'], round(whole, 3))
        self.live.assert_not_called()                       # nothing after the file: no live call
        # the plain month view has no year, so nothing recorded
        result, _ = self.forecast(6)
        self.assertFalse(any('recorded_rain_probability' in r for r in self.rows(result, 'Flood')))
        # January 2026 is after the file: with NASA POWER down it has no recorded day
        today = date(2026, 1, 20)
        result, _ = self.forecast(1, year=2026, today=today)
        self.assertFalse(any('recorded_rain_probability' in r for r in self.rows(result, 'Flood')))
        self.live.assert_called_with(dep.rain.cells, after=date(2025, 12, 31), today=today)
        self.assertTrue(all(r['method'] == 'model' for r in self.rows(result, 'Flood')))
        # with the live rain of 1-10 January, those days use the rain that fell and the rest each scenario's
        recent = {bid: {date(2026, 1, d): 4.0 * d for d in range(1, 11)} for bid in self.ids}
        self.live.return_value = recent
        result, _ = self.forecast(1, year=2026, today=today)
        series = {**dep.rain.rain[b], **recent[b]}
        X = np.array([[w[k] for k in RAIN_FEATURES] + [self.terrain[b][k] for k in TERRAIN_FEATURES['Flood']]
                      for w in (rain_windows(series, date(2026, 1, d)) for d in range(1, 11))])
        kept = prod(1 - p for p in hazard_models.predict(dep.model, X))
        mixed = [1 - kept * prod(1 - dep.daily[b][date(s, 1, d)] for d in range(11, 32)) for s in YEARS]
        row = self.row(result, 'Flood', b)
        self.assertEqual(row['recorded_rain_probability'], round(sum(mixed) / len(mixed), 3))
        pc = self.chance(dep, b, 1, None, 2026)
        self.assertEqual(row['probability'], round(pc.probability, 3))        # the chance itself is unchanged
        # a period that has not started has no recorded day either
        result, _ = self.forecast(3, year=2026, today=today)
        self.assertFalse(any('recorded_rain_probability' in r for r in self.rows(result, 'Flood')))

    def test_in_training_marks_periods_inside_the_study(self):
        for kwargs, inside in (({'year': 2023}, True), ({'day': 30, 'year': 2025}, True),
                               ({'year': 2026}, False), ({}, False)):
            month = 12 if kwargs.get('day') else 6
            result, _ = self.forecast(month, **kwargs)
            for hazard in MODELLED:
                rows = self.rows(result, hazard)
                self.assertTrue(all(r['method'] == 'model' for r in rows), kwargs)
                if inside:
                    self.assertTrue(all(r['in_training'] is True for r in rows), kwargs)
                else:
                    self.assertFalse(any('in_training' in r for r in rows), kwargs)

    # ---- when the model cannot run ----

    def test_missing_report_gives_unavailable_rows_not_counting(self):
        counted = self.row(self.counting(7), 'Flood', self.ids[0])
        self.assertGreater(counted['probability'], 0)
        self.report_path.unlink()
        with self.assertLogs('apps.history.hazard_forecast', level='WARNING'):
            result, scen = self.forecast(7, hazards=['Flood'])
        rows = self.rows(result, 'Flood')
        self.assertEqual(sorted(r['barangay_id'] for r in rows), sorted(self.ids))
        for row in rows:
            self.assert_unavailable(row, REPORT_MISSING)
        self.assertEqual(result['unavailable_hazards'], ['Flood'])
        self.assertEqual(result['model_hazards'], [])
        self.assertEqual(scen, {'Flood': {'deployed': None, 'chances': {}, 'dates_by_s': {},
                                          'month_dates_by_s': {}}})
        # no counting profile either
        self.assertEqual(result['profile_method'], 'unavailable')
        self.assertTrue(all(e['probability'] is None and e['expected_events'] is None and e['level'] == 'None'
                            for e in result['profile']))
        # the rows without a figure rank last and stay out of the per-barangay summary
        self.assertEqual(result['results'][0]['hazard_type'], 'Fire')
        self.assertEqual([r['top_hazard'] for r in result['by_barangay']], ['Fire'])

    def test_barangay_without_terrain_is_unavailable_alone(self):
        no_rain = self.barangay('Terrain but no rain', 3)          # a terrain row, no rain series
        no_terrain = self.barangay('A boundary added later', 4)    # neither
        terrain = {**self.terrain, no_rain.id: dict(self.terrain[self.ids[0]])}
        write_terrain(self.tmp / 'barangay_terrain.csv', terrain, {})
        result, scen = self.forecast(7)
        for hazard in MODELLED:
            self.assert_unavailable(self.row(result, hazard, no_terrain.id),
                                    'No terrain figures for this barangay yet.')
            self.assert_unavailable(self.row(result, hazard, no_rain.id), 'No rain series for this barangay yet.')
            for b in self.ids:
                self.assertEqual(self.row(result, hazard, b)['method'], 'model')
            self.assertEqual(set(scen[hazard]['chances']), set(self.ids))
            self.assertEqual(scen[hazard]['deployed'].reasons, {no_rain.id: 'No rain series for this barangay yet.'})
        self.assertEqual(result['model_hazards'], ['Flood', 'Landslide'])
        self.assertEqual(result['unavailable_hazards'], ['Flood', 'Landslide'])
        # its own chart has no figure, never a counting one
        result, _ = self.forecast(7, hazards=['Flood'], barangay=no_terrain.id)
        self.assertEqual(result['profile_method'], 'unavailable')
        self.assertTrue(all(e['probability'] is None for e in result['profile']))

    def test_no_rain_year_before_period_is_unavailable(self):
        result, scen = self.forecast(1, year=2021)
        for hazard in MODELLED:
            rows = self.rows(result, hazard)
            self.assertEqual(sorted(r['barangay_id'] for r in rows), sorted(self.ids))
            for row in rows:
                self.assert_unavailable(row, 'no rain years before this period')
            self.assertIsInstance(scen[hazard]['deployed'], hazard_forecast.Deployed)
            self.assertEqual((scen[hazard]['chances'], scen[hazard]['dates_by_s']), ({}, {}))
        self.assertEqual(result['unavailable_hazards'], ['Flood', 'Landslide'])
        self.assertEqual(result['model_hazards'], [])

    def test_a_failed_fit_releases_the_lock_and_gives_unavailable_rows(self):
        key = hazard_forecast.cache_key('Flood')
        lock = key.replace('hazard-model:', 'hazard-model-lock:')
        with mock.patch.object(hazard_models, 'make_pipeline', side_effect=RuntimeError('fit failed')):
            with self.assertRaisesMessage(RuntimeError, 'fit failed'):
                hazard_forecast.deployed('Flood')
            self.assertFalse(cache.has_key(lock))
            self.assertIsNone(cache.get(key))
            with self.assertLogs('apps.history.hazard_forecast', level='ERROR'):
                result, _ = self.forecast(7, hazards=['Flood'])
        for row in self.rows(result, 'Flood'):
            self.assert_unavailable(row, 'The flood model could not run right now.')
        self.assertFalse(cache.has_key(lock))

    # ---- the deployed model, its cache and its lock ----

    def test_platt_only_when_the_report_says_every_fold_was_calibrated(self):
        real_fit = hazard_models.fit_candidate
        fitted = []

        def spy(name, hazard, train):
            fitted.append((name, hazard, sorted(set(train.years.tolist()))))
            fitted.append(real_fit(name, hazard, train))
            return fitted[-1]

        with mock.patch.dict(hazard_models.SPEED_OVERRIDES, FAST), \
                mock.patch.object(hazard_models, 'fit_candidate', side_effect=spy):
            write_toy_files(self.tmp, self.ids, winner='random_forest')
            plain = hazard_forecast.deployed('Landslide')
            self.assertEqual(fitted, [])                     # a plain fit: fit_candidate would add Platt
            self.assertEqual((plain.model.name, plain.model.platt), ('random_forest', None))
            write_toy_files(self.tmp, self.ids, winner='random_forest', calibrated=True)
            calibrated = hazard_forecast.deployed('Landslide')
        self.assertEqual(fitted[0], ('random_forest', 'Landslide', YEARS))    # the whole study period
        self.assertEqual(calibrated.model.platt, fitted[1].platt)

    def test_record_after_study_end_keeps_fit(self):
        key = hazard_forecast.cache_key('Flood')
        _, scen = self.forecast(7)
        before = scen['Flood']['chances']
        HistoricalRecord.objects.create(barangay=self.barangays[2], hazard_type=self.kinds['Flood'],
                                        severity_level='Orange', source_ref='approved-report-2026',
                                        occurred_at=at(date(2026, 3, 1)), hazard_subcategory='TOY')
        self.assertEqual(hazard_forecast.cache_key('Flood'), key)
        with mock.patch.object(hazard_models, 'make_pipeline', wraps=hazard_models.make_pipeline) as fit:
            _, scen = self.forecast(7)
        fit.assert_not_called()                              # served from the cache, not refitted
        self.assertEqual(scen['Flood']['chances'], before)
        # a record inside the study is a different record set
        HistoricalRecord.objects.create(barangay=self.barangays[2], hazard_type=self.kinds['Flood'],
                                        severity_level='Orange', source_ref='late-entry-2024',
                                        occurred_at=at(date(2024, 3, 1)), hazard_subcategory='TOY')
        self.assertNotEqual(hazard_forecast.cache_key('Flood'), key)

    def test_cache_key_covers_the_report_the_data_files_and_the_hazard(self):
        key = hazard_forecast.cache_key('Flood')
        self.assertTrue(key.startswith('hazard-model:'))
        self.assertNotEqual(hazard_forecast.cache_key('Landslide'), key)
        for name in ('hazard_model_report.json', 'rain_daily.csv', 'barangay_terrain.csv',
                     'hazard_model_exclusions.csv'):
            path = self.tmp / name
            original = path.read_bytes()
            path.write_bytes(original + b'\n')
            self.assertNotEqual(hazard_forecast.cache_key('Flood'), key, name)
            path.write_bytes(original)
            self.assertEqual(hazard_forecast.cache_key('Flood'), key, name)

    def test_a_request_that_finds_the_lock_held_waits_then_gives_up(self):
        key = hazard_forecast.cache_key('Flood')
        lock = key.replace('hazard-model:', 'hazard-model-lock:')
        cache.set(lock, 1, 300)                              # another request is fitting
        clock, slept = [0.0], []

        def sleep(seconds):
            slept.append(seconds)
            clock[0] += seconds

        with mock.patch.object(hazard_forecast, '_sleep', sleep), \
                mock.patch.object(hazard_forecast, '_monotonic', lambda: clock[0]), \
                mock.patch.object(hazard_models, 'make_pipeline') as fit:
            with self.assertRaisesMessage(hazard_forecast.Unavailable,
                                          'The model is being prepared; try again in a minute.'):
                hazard_forecast.deployed('Flood')
        fit.assert_not_called()
        self.assertEqual(set(slept), {0.5})
        self.assertEqual(sum(slept), 60)
        self.assertEqual(cache.get(lock), 1)                 # the other request's lock is left alone

    def test_only_one_fit_when_two_requests_find_the_cache_empty(self):
        write_toy_files(self.tmp, self.ids, calibrated=True)     # so the deployed fit goes through fit_candidate
        records = {h: toy_event_records(h, self.pos) for h in MODELLED}
        real_fit = hazard_models.fit_candidate
        calls, errors, got = [], [], []
        start = threading.Barrier(2)

        def slow_fit(name, hazard, train):
            calls.append(hazard)
            time.sleep(0.5)
            return real_fit(name, hazard, train)

        def request():
            try:
                start.wait(10)
                for hazard in MODELLED:
                    got.append(hazard_forecast.deployed(hazard).hazard)
            except Exception as exc:          # surfaced by the assertion below
                errors.append(exc)

        # threads cannot see this test's transaction, so they must not read the records from the database
        with mock.patch.object(hazard_forecast, 'load_records', side_effect=lambda h: records[h]), \
                mock.patch.object(hazard_forecast, 'records_signature', return_value='toy-records'), \
                mock.patch.object(hazard_models, 'fit_candidate', side_effect=slow_fit):
            threads = [threading.Thread(target=request) for _ in range(2)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(60)
        self.assertEqual(errors, [])
        self.assertEqual(sorted(calls), ['Flood', 'Landslide'])
        self.assertEqual(Counter(got), {'Flood': 2, 'Landslide': 2})

    def test_warm_in_background_starts_only_when_cold(self):
        def warm(**deployed_kwargs):
            with mock.patch.object(hazard_forecast, 'deployed', **deployed_kwargs) as built, \
                    mock.patch.object(hazard_forecast.connections, 'close_all') as closed:
                started = hazard_forecast.warm_in_background()
                for t in threading.enumerate():
                    if t.name == hazard_forecast.WARM_THREAD_NAME:
                        t.join(10)
            return started, [c.args[0] for c in built.call_args_list], closed.call_count

        self.assertEqual(warm(), (True, ['Flood', 'Landslide'], 1))                 # cold
        flood, slide = hazard_forecast.cache_key('Flood'), hazard_forecast.cache_key('Landslide')
        cache.set(flood, 'ready', 60)
        self.assertEqual(warm(), (True, ['Flood', 'Landslide'], 1))                 # one still cold
        cache.set(slide, 'ready', 60)
        self.assertEqual(warm(), (False, [], 0))                                    # warm
        cache.delete(slide)
        cache.set(slide.replace('hazard-model:', 'hazard-model-lock:'), 1, 60)
        self.assertEqual(warm(), (False, [], 0))                                    # a fit is already running
        cache.clear()
        with self.assertLogs('apps.history.hazard_forecast', level='ERROR'):        # each failure is logged
            self.assertEqual(warm(side_effect=RuntimeError('fit failed')), (True, ['Flood', 'Landslide'], 1))
        self.report_path.unlink()
        with self.assertLogs('apps.history.hazard_forecast', level='WARNING'):      # no key without a report
            self.assertEqual(warm(), (False, [], 0))

    # ---- the 12-month chart ----

    def test_single_hazard_profile_is_the_models_month_by_month(self):
        b = self.ids[0]
        result, scen = self.forecast(7, hazards=['Flood'], barangay=b)
        dep = scen['Flood']['deployed']
        self.assertEqual(result['profile_method'], 'model')
        for entry in result['profile']:
            pc = self.chance(dep, b, entry['month'])
            level = model_forecast.level_for(pc.probability)
            self.assertEqual((entry['probability'], entry['expected_events'], entry['level']),
                             (round(pc.probability, 3), round(pc.expected, 2), level))
        # the city: the mean of each barangay's chance
        result, _ = self.forecast(7, hazards=['Flood'])
        for entry in result['profile']:
            mean = sum(self.chance(dep, i, entry['month']).probability for i in self.ids) / len(self.ids)
            self.assertEqual(entry['probability'], round(mean, 3))
            self.assertEqual(entry['level'], model_forecast.level_for(mean))
        # a year reads only the rain years before it
        result, _ = self.forecast(7, year=2024, hazards=['Flood'], barangay=b)
        self.assertEqual(result['profile'][0]['probability'], round(self.chance(dep, b, 1, None, 2024).probability, 3))
        # several hazards: the chart is left for the combined chance
        result, _ = self.forecast(7, barangay=b)
        self.assertEqual(result['profile_method'], 'unavailable')
        self.assertEqual(result['profile'], empty_profile())
