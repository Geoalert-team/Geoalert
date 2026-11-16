"""
Flood and landslide on the forecast: the deployed model (the saved fit the
report names, scored with NumPy, never refitted), its cache and lock, and the
rows, levels and chart it puts on a seasonal_forecast result. Toy files in a
temp folder stand in for apps/history/data/.
"""
import copy
import hashlib
import json
import math
import shutil
import tempfile
import threading
import time
from collections import Counter
from datetime import date, datetime, timedelta
from math import prod
from pathlib import Path
from unittest import mock

import numpy as np
import requests
from django.contrib.gis.geos import MultiPolygon
from django.core.cache import cache
from django.test import SimpleTestCase, TestCase
from sklearn.linear_model import LogisticRegression

from apps.barangays.models import Barangay
from apps.hazards.models import HazardType
from apps.history import hazard_data, hazard_forecast, hazard_models, model_forecast, prediction_log, storms, two_part
from apps.history.forecast import empty_profile, seasonal_forecast
from apps.history.hazard_data import MANILA, RAIN_FEATURES, TERRAIN_FEATURES, rain_windows, write_terrain
from apps.history.hazard_models import REPORT_OLD
from apps.history.hazard_scenarios import period_chance, period_dates, scenario_dates
from apps.history.models import HistoricalRecord
from apps.history.rain import ARCHIVE_FIRST_DAY, read_rain_csv, write_rain_csv
from apps.history.two_part import NO_EXPOSURE, TwoPartFit, when_row
from tests.fire_setup import box
from tests.hazard_fixtures import (
    TOY_STORM_THROUGH, toy_inputs, toy_report_v1, toy_report_v2, toy_source_ref, write_toy_files, write_toy_storms)

TODAY = date(2026, 11, 12)
YEARS = [2021, 2022, 2023, 2024, 2025]        # the toy rain file's complete years
MODELLED = ('Flood', 'Landslide')
REPORT_MISSING = 'The model report is missing; run manage.py test_hazard_models.'
NO_TERRAIN = 'No terrain figures for this barangay yet.'
STORMS_MISSING = 'The storm days (storm_days.csv) are missing; run manage.py fetch_storms.'
REAL_LIVE_STORM_DAYS = storms.live_storm_days       # setUp swaps in one that adds nothing; one test uses the real one
STORM_FILES = ('storm_days.csv', 'storm_days.meta.json')


def sigmoid(z):
    return 1.0 / (1.0 + math.exp(-z))


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
        # NASA POWER is never called from the tests: the live rain is down unless a test says otherwise. Nor is
        # IBTrACS: the live storm days add nothing to the file's, and the daily refresh does nothing. The
        # warm-up's prediction log step is a stand-in (tests/test_prediction_log.py tests it).
        self.live = mock.Mock(return_value=None)
        self.live_storms = mock.Mock(side_effect=lambda base, today, get=None: base)
        self.refresh = mock.Mock(return_value=True)
        self.log = mock.Mock(return_value=True)
        for patcher in (mock.patch.object(hazard_data, 'DATA_DIR', self.tmp),
                        mock.patch.object(hazard_models, 'REPORT_PATH', self.report_path),
                        mock.patch.object(hazard_forecast, 'recent_rain', self.live),
                        mock.patch.object(storms, 'live_storm_days', self.live_storms),
                        mock.patch.object(storms, 'refresh_recent', self.refresh),
                        mock.patch.object(prediction_log, 'log_once_today', self.log)):
            patcher.start()
            self.addCleanup(patcher.stop)

    def barangay(self, name, slot):
        return Barangay.objects.create(name=name, municipality='Talisay',
                                       boundary=MultiPolygon(box(1000 * slot, 0, 1000 * slot + 900, 900), srid=4326))

    def report(self):
        return json.loads(self.report_path.read_text(encoding='utf-8'))

    def write_report(self, report):
        self.report_path.write_text(json.dumps(report), encoding='utf-8')

    def storm_days(self):
        return storms.read_storm_days(*(self.tmp / name for name in STORM_FILES))

    def rain_through(self, last, mm=3.0):
        """Carry the toy rain file on to `last` with `mm` a day."""
        rf = read_rain_csv(self.tmp / 'rain_daily.csv')
        days = [rf.last_day + timedelta(days=i) for i in range(1, (last - rf.last_day).days + 1)]
        write_rain_csv(self.tmp / 'rain_daily.csv', {b: {**series, **{d: mm for d in days}}
                                                     for b, series in rf.rain.items()}, rf.cells)

    def november_2026(self):
        """The rain file to 4 November 2026, the storm file to 5 November and the live rain 5-10 November."""
        self.rain_through(date(2026, 11, 4))
        write_toy_storms(self.tmp, min(self.rain[self.ids[0]]), date(2026, 11, 5), sorted({d for _, d in self.pos}))
        self.live.return_value = {b: {date(2026, 11, d): 3.0 for d in range(5, 11)} for b in self.ids}
        return period_dates(11, None, 2026)

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
                self.assertEqual(row['model'], 'two_part')          # the toy report's model in use
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
        # with the live rain of 1-10 January, those days use the rain that fell and the rest each scenario's;
        # the saved fit scores them as it scores the file's days: the city's "when" chance times the share
        recent = {bid: {date(2026, 1, d): 4.0 * d for d in range(1, 11)} for bid in self.ids}
        self.live.return_value = recent
        result, _ = self.forecast(1, year=2026, today=today)
        city = {**dep.rain.rain[min(self.ids)], **recent[min(self.ids)]}
        X = np.array([when_row('Flood', city, self.storm_days(), date(2026, 1, d)) for d in range(1, 11)])
        fit = TwoPartFit.from_json(dep.fit)
        kept = prod(1 - p for p in fit.when.chance(X) * fit.shares[b])
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

    def test_old_report_makes_rows_unavailable_with_report_old(self):
        v2 = self.report()
        old = {
            'the version 1 report': lambda: toy_report_v1(self.report_path),
            'version 1': lambda: self.write_report({**v2, 'version': 1}),
            'no version': lambda: self.write_report({k: v for k, v in v2.items() if k != 'version'}),
        }
        for label, write in old.items():
            with self.subTest(report=label):
                write()
                with self.assertLogs('apps.history.hazard_forecast', level='WARNING'):
                    result, scen = self.forecast(7)
                for hazard in MODELLED:
                    rows = self.rows(result, hazard)
                    self.assertEqual(sorted(r['barangay_id'] for r in rows), sorted(self.ids))
                    for row in rows:
                        self.assert_unavailable(row, REPORT_OLD)
                    self.assertIsNone(scen[hazard]['deployed'])
                self.assertEqual(result['unavailable_hazards'], ['Flood', 'Landslide'])
                with self.assertLogs('apps.history.hazard_forecast', level='WARNING'):
                    self.assertFalse(hazard_forecast.warm_in_background())
        # a version 2 fit whose inputs are not the ones this code builds is old too: never scored out of line
        swapped = copy.deepcopy(v2)
        when = swapped['hazards']['Flood']['fits']['two_part']['when']
        when['features'] = when['features'][::-1]
        self.write_report(swapped)
        with self.assertLogs('apps.history.hazard_forecast', level='WARNING'):
            result, _ = self.forecast(7)
        for row in self.rows(result, 'Flood'):
            self.assert_unavailable(row, REPORT_OLD)
        self.assertTrue(all(r['method'] == 'model' for r in self.rows(result, 'Landslide')))

    def test_barangay_without_exposure_is_unavailable_not_zero(self):
        # the report's fits have no share for the third barangay (it was not in the exposure file)
        without = self.ids[2]
        toy_report_v2(self.report_path, shares={self.ids[0]: 0.6, self.ids[1]: 0.3})
        result, scen = self.forecast(7)
        row = self.row(result, 'Flood', without)
        self.assertEqual((row['method'], row['reason']), ('unavailable', NO_EXPOSURE))
        self.assert_unavailable(row, NO_EXPOSURE)
        self.assert_unavailable(self.row(result, 'Landslide', without), NO_TERRAIN)
        for hazard, reason in (('Flood', NO_EXPOSURE), ('Landslide', NO_TERRAIN)):
            dep = scen[hazard]['deployed']
            self.assertEqual(dep.reasons, {without: reason})
            self.assertNotIn(without, dep.daily)                    # no chance at all, not a chance of 0
            self.assertEqual(set(scen[hazard]['chances']), set(self.ids[:2]))
            for b in self.ids[:2]:
                self.assertEqual(self.row(result, hazard, b)['method'], 'model')
        self.assertEqual(result['unavailable_hazards'], ['Flood', 'Landslide'])
        self.assertEqual(result['model_hazards'], ['Flood', 'Landslide'])

    def test_a_failed_build_releases_the_lock_and_gives_unavailable_rows(self):
        key = hazard_forecast.cache_key('Flood')
        lock = key.replace('hazard-model:', 'hazard-model-lock:')
        with mock.patch.object(hazard_forecast, 'score_two_part', side_effect=RuntimeError('scoring failed')):
            with self.assertRaisesMessage(RuntimeError, 'scoring failed'):
                hazard_forecast.deployed('Flood')
            self.assertFalse(cache.has_key(lock))
            self.assertIsNone(cache.get(key))
            with self.assertLogs('apps.history.hazard_forecast', level='ERROR'):
                result, _ = self.forecast(7, hazards=['Flood'])
        for row in self.rows(result, 'Flood'):
            self.assert_unavailable(row, 'The flood model could not run right now.')
        self.assertFalse(cache.has_key(lock))

    # ---- the storm days ----

    def test_recent_days_without_storm_coverage_get_no_flood_chance(self):
        november = self.november_2026()
        # the real live storm days with IBTrACS unreachable: the storm days stop where the file does, and
        # nothing raises
        with mock.patch.object(storms, 'live_storm_days', REAL_LIVE_STORM_DAYS), \
                mock.patch.object(storms, 'get', side_effect=requests.ConnectionError('IBTrACS is down')) as ncei, \
                self.assertLogs('apps.history.storms', level='WARNING'):
            result, scen = self.forecast(11, year=2026)
            dep = scen['Flood']['deployed']
            recorded = hazard_forecast._recorded_chances(dep, november, TODAY)
        ncei.assert_called()                                 # the active-storms file was asked for
        self.assertEqual(dep.storms.last_day, date(2026, 11, 5))
        for b in self.ids:
            self.assertEqual(max(dep.daily[b]), date(2026, 11, 4))          # the rain file's last day
            # the live rain reaches 10 November, the storm days 5 November: the recorded days stop there
            self.assertEqual(sorted(recorded[b]), [date(2026, 11, d) for d in range(1, 6)])
        # the month's rows still come from the model, by replaying past years
        for row in self.rows(result, 'Flood'):
            self.assertEqual(row['method'], 'model')
            self.assertEqual(row['probability'],
                             round(self.chance(dep, row['barangay_id'], 11, None, 2026).probability, 3))
            self.assertIn('recorded_rain_probability', row)
        # once the live storm days reach yesterday (the active file read, the recent copy fresh), they count too
        self.live_storms.side_effect = lambda base, today, get=None: storms.StormDays(
            base.days, base.first_day, today - timedelta(days=1))
        recorded = hazard_forecast._recorded_chances(dep, november, TODAY)
        self.live_storms.assert_called_with(dep.storms, TODAY)
        for b in self.ids:
            self.assertEqual(max(recorded[b]), date(2026, 11, 10))           # the live rain's last day

    def test_landslide_ignores_storm_coverage(self):
        november = self.november_2026()
        result, scen = self.forecast(11, year=2026, hazards=['Landslide'])
        dep = scen['Landslide']['deployed']
        self.assertIsNone(dep.storms)
        recorded = hazard_forecast._recorded_chances(dep, november, TODAY)
        for b in self.ids:
            # every day of live rain is recorded, past the storm days' 5 November
            self.assertEqual(sorted(recorded[b]), [date(2026, 11, d) for d in range(1, 11)])
        self.live_storms.assert_not_called()
        self.assertTrue(all(r['method'] == 'model' for r in self.rows(result, 'Landslide')))
        # without the storm days, flood says what to run and landslide is served as before
        slide = hazard_forecast.cache_key('Landslide')
        for name in STORM_FILES:
            (self.tmp / name).unlink()
        self.assertEqual(hazard_forecast.cache_key('Landslide'), slide)
        with self.assertLogs('apps.history.hazard_forecast', level='WARNING'):
            result, _ = self.forecast(11, year=2026)
        for row in self.rows(result, 'Flood'):
            self.assert_unavailable(row, STORMS_MISSING)
        self.assertTrue(all(r['method'] == 'model' for r in self.rows(result, 'Landslide')))
        self.assertEqual(result['model_hazards'], ['Landslide'])

    def test_flood_logistic_regression_needs_no_storm_data(self):
        # the model in use reads no storm flag: the storm file and IBTrACS failing leave flood served as before
        toy_report_v2(self.report_path, in_use='logistic_regression')
        november = self.november_2026()
        flood = hazard_forecast.cache_key('Flood')
        for name in STORM_FILES:
            (self.tmp / name).unlink()
        self.assertEqual(hazard_forecast.cache_key('Flood'), flood)          # the storm files are not its inputs
        self.live_storms.side_effect = requests.ConnectionError('IBTrACS is down')
        with mock.patch.object(storms, 'get', side_effect=AssertionError('IBTrACS asked for')):
            result, scen = self.forecast(11, year=2026)
            dep = scen['Flood']['deployed']
            recorded = hazard_forecast._recorded_chances(dep, november, TODAY)
        self.assertEqual(dep.name, 'logistic_regression')
        self.assertIsNone(dep.storms)
        self.live_storms.assert_not_called()
        self.assertEqual(result['model_hazards'], list(MODELLED))
        self.assertTrue(all(r['method'] == 'model' for r in self.rows(result, 'Flood')))
        for b in self.ids:
            # every day of live rain is recorded: no storm coverage limits the logistic regression
            self.assertEqual(sorted(recorded[b]), [date(2026, 11, d) for d in range(1, 11)])

    # ---- the deployed model, its cache and its lock ----

    def test_build_scores_without_fitting(self):
        def no_fit(*args, **kwargs):
            raise AssertionError('the forecast refitted a model')

        def by_hand(fit, hazard, b, rain, d):
            """The saved logistic regression worked by hand: log the rain sums, scale, then the logistic."""
            w = rain_windows(rain, d)
            x = [w[k] for k in RAIN_FEATURES] + [self.terrain[b][k] for k in TERRAIN_FEATURES[hazard]]
            x = [math.log1p(v) if i < len(RAIN_FEATURES) else v for i, v in enumerate(x)]
            z = [(v - m) / s for v, m, s in zip(x, fit['mean'], fit['scale'])]
            return sigmoid(fit['intercept'] + sum(c * v for c, v in zip(fit['coef'], z)))

        rf = read_rain_csv(self.tmp / 'rain_daily.csv')
        recent = {b: {date(2026, 1, d): 6.0 * d for d in range(1, 11)} for b in self.ids}
        for in_use in ('two_part', 'logistic_regression'):
            with self.subTest(in_use=in_use):
                report = toy_report_v2(self.report_path, in_use=in_use)
                sha1 = hashlib.sha1(self.report_path.read_bytes()).hexdigest()
                with mock.patch.object(LogisticRegression, 'fit', no_fit), \
                        mock.patch.object(two_part, 'fit_when', no_fit):
                    result, scen = self.forecast(7)
                for hazard in MODELLED:
                    dep = scen[hazard]['deployed']
                    fit = report['hazards'][hazard]['fits'][in_use]
                    self.assertEqual((dep.name, dep.version, dep.fit), (in_use, f'{in_use}@{sha1[:12]}', fit))
                    self.assertTrue(all(r['model'] == in_use for r in self.rows(result, hazard)))
                    for b in self.ids:
                        # every rain-file day with a whole 14-day window has a chance
                        self.assertEqual((min(dep.daily[b]), max(dep.daily[b]), len(dep.daily[b])),
                                         (date(2021, 1, 1), rf.last_day, (rf.last_day - date(2021, 1, 1)).days + 1))
                    if in_use == 'logistic_regression':
                        b = self.ids[1]
                        self.assertAlmostEqual(dep.daily[b][date(2024, 7, 9)],
                                               by_hand(fit, hazard, b, self.rain[b], date(2024, 7, 9)), places=12)
                        # a day after the rain file, from its windows of file and live rain
                        self.live.return_value = recent
                        late = hazard_forecast._recorded_chances(dep, period_dates(1, None, 2026), date(2026, 1, 20))
                        self.assertEqual(sorted(late[b]), [date(2026, 1, d) for d in range(1, 11)])
                        self.assertAlmostEqual(late[b][date(2026, 1, 3)], by_hand(
                            fit, hazard, b, {**self.rain[b], **recent[b]}, date(2026, 1, 3)), places=12)

    def test_two_part_daily_chance_is_q_times_share(self):
        report = self.report()
        storm_days = self.storm_days()
        city = self.rain[min(self.ids)]              # every barangay reads the one city rain cell
        storm_day = min(d for _, d in self.pos)      # the toy storm days are the toy event days
        for hazard in MODELLED:
            dep = hazard_forecast.deployed(hazard)
            fit = report['hazards'][hazard]['fits']['two_part']
            when = fit['when']
            for d in (storm_day, storm_day + timedelta(days=5), date(2025, 12, 31)):
                x = when_row(hazard, city, storm_days if hazard == 'Flood' else None, d)
                # the forecast uses the GeoAlert-era intercept (landslide's catalogue one is kept for the record)
                q = sigmoid(when['intercepts']['geoalert'] + sum(c * v for c, v in zip(when['coef'], x)))
                for b in self.ids:
                    self.assertAlmostEqual(dep.daily[b][d], q * fit['shares'][str(b)], places=12)
        # flood's first day above was worked with the storm flag on, its second with it off
        self.assertEqual([storm_days.flag(storm_day), storm_days.flag(storm_day + timedelta(days=5))], [1, 0])

    def test_scenario_years_start_in_2007_with_rain_from_2006(self):
        _, toy_rain, _ = toy_inputs(n_barangays=len(self.ids), start=date(2006, 12, 31))
        rain = {self.ids[t - 1]: series for t, series in toy_rain.items()}
        self.assertEqual(min(rain[self.ids[0]]), ARCHIVE_FIRST_DAY)
        write_rain_csv(self.tmp / 'rain_daily.csv', rain, read_rain_csv(self.tmp / 'rain_daily.csv').cells)
        write_toy_storms(self.tmp, ARCHIVE_FIRST_DAY, TOY_STORM_THROUGH)
        years = list(range(2007, 2026))                  # 19 years, not the study's 5
        result, scen = self.forecast(7)
        for hazard in MODELLED:
            dep = scen[hazard]['deployed']
            self.assertEqual(dep.complete_years, years)
            self.assertEqual(sorted(scen[hazard]['dates_by_s']), years)
            for b in self.ids:
                self.assertIn(date(2007, 1, 1), dep.daily[b])         # flood's storm flag reaches back too
                row = self.row(result, hazard, b)
                self.assertEqual((row['method'], row['rain_years']), ('model', years))

    def test_new_records_never_change_the_saved_fit(self):
        keys = {h: hazard_forecast.cache_key(h) for h in MODELLED}
        _, scen = self.forecast(7)
        before = scen['Flood']['chances']
        # an approved report after the study, and a late entry inside it: the saved fit changes only when
        # test_hazard_models runs again (the accuracy card says it is stale)
        for source_ref, day in (('approved-report-2026', date(2026, 3, 1)), ('late-entry-2024', date(2024, 3, 1))):
            HistoricalRecord.objects.create(barangay=self.barangays[2], hazard_type=self.kinds['Flood'],
                                            severity_level='Orange', source_ref=source_ref, occurred_at=at(day),
                                            hazard_subcategory='TOY')
        self.assertEqual({h: hazard_forecast.cache_key(h) for h in MODELLED}, keys)
        with mock.patch.object(hazard_forecast, '_build', wraps=hazard_forecast._build) as build:
            _, scen = self.forecast(7)
        build.assert_not_called()                            # served from the cache
        self.assertEqual(scen['Flood']['chances'], before)

    def test_cache_key_covers_the_report_the_data_files_and_the_hazard(self):
        keys = {h: hazard_forecast.cache_key(h) for h in MODELLED}
        self.assertTrue(keys['Flood'].startswith('hazard-model:'))
        self.assertNotEqual(keys['Landslide'], keys['Flood'])
        for name in ('hazard_model_report.json', 'rain_daily.csv', 'barangay_terrain.csv'):
            path = self.tmp / name
            original = path.read_bytes()
            path.write_bytes(original + b'\n')
            for hazard in MODELLED:
                self.assertNotEqual(hazard_forecast.cache_key(hazard), keys[hazard], name)
            path.write_bytes(original)
            self.assertEqual({h: hazard_forecast.cache_key(h) for h in MODELLED}, keys, name)
        # the exclusions are read only when the models are tested, so they no longer matter here
        (self.tmp / 'hazard_model_exclusions.csv').write_text('source_ref,reason\r\ntoy-x,left out\r\n')
        self.assertEqual({h: hazard_forecast.cache_key(h) for h in MODELLED}, keys)

    def test_cache_key_changes_with_the_storm_file(self):
        flood, slide = hazard_forecast.cache_key('Flood'), hazard_forecast.cache_key('Landslide')
        for name in STORM_FILES:       # hashed together, as test_hazard_models hashes them for the report
            path = self.tmp / name
            original = path.read_bytes()
            path.write_bytes(original + b'\n')
            self.assertNotEqual(hazard_forecast.cache_key('Flood'), flood, name)
            self.assertEqual(hazard_forecast.cache_key('Landslide'), slide, name)    # landslide never reads them
            path.write_bytes(original)
            self.assertEqual(hazard_forecast.cache_key('Flood'), flood, name)
        # a refetch that adds a storm day is a new key, so the cached chances are not served from the old days
        write_toy_storms(self.tmp, min(self.rain[self.ids[0]]), TOY_STORM_THROUGH, [date(2024, 7, 9)])
        self.assertNotEqual(hazard_forecast.cache_key('Flood'), flood)
        for name in STORM_FILES:
            with self.subTest(missing=name):
                write_toy_storms(self.tmp, min(self.rain[self.ids[0]]), TOY_STORM_THROUGH)
                (self.tmp / name).unlink()
                with self.assertRaisesMessage(hazard_forecast.Unavailable, STORMS_MISSING):
                    hazard_forecast.cache_key('Flood')
                self.assertEqual(hazard_forecast.cache_key('Landslide'), slide)

    def test_a_request_that_finds_the_lock_held_waits_then_gives_up(self):
        key = hazard_forecast.cache_key('Flood')
        lock = key.replace('hazard-model:', 'hazard-model-lock:')
        cache.set(lock, 1, 300)                              # another request is building
        clock, slept = [0.0], []

        def sleep(seconds):
            slept.append(seconds)
            clock[0] += seconds

        with mock.patch.object(hazard_forecast, '_sleep', sleep), \
                mock.patch.object(hazard_forecast, '_monotonic', lambda: clock[0]), \
                mock.patch.object(hazard_forecast, '_build') as build:
            with self.assertRaisesMessage(hazard_forecast.Unavailable,
                                          'The model is being prepared; try again in a minute.'):
                hazard_forecast.deployed('Flood')
        build.assert_not_called()
        self.assertEqual(set(slept), {0.5})
        self.assertEqual(sum(slept), 60)
        self.assertEqual(cache.get(lock), 1)                 # the other request's lock is left alone

    def test_only_one_build_when_two_requests_find_the_cache_empty(self):
        real_build = hazard_forecast._build
        calls, errors, got = [], [], []
        start = threading.Barrier(2)

        def slow_build(hazard, inputs):
            calls.append(hazard)
            time.sleep(0.5)
            return real_build(hazard, inputs)

        def request():
            try:
                start.wait(10)
                for hazard in MODELLED:
                    got.append(hazard_forecast.deployed(hazard).hazard)
            except Exception as exc:          # surfaced by the assertion below
                errors.append(exc)

        # the build reads only files (the live storm days are swapped out), never this test's database rows
        with mock.patch.object(hazard_forecast, '_build', side_effect=slow_build):
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

    def test_warm_refreshes_storms_first(self):
        order = []
        self.refresh.side_effect = lambda: order.append('storms') or True
        self.log.side_effect = lambda today: order.append('log')
        with mock.patch.object(hazard_forecast, 'deployed', side_effect=order.append), \
                mock.patch.object(hazard_forecast.connections, 'close_all') as closed:
            hazard_forecast._warm()
        self.assertEqual(order, ['storms', 'Flood', 'Landslide', 'log'])          # the prediction log comes last
        closed.assert_called_once_with()
        # a refresh that fails is logged and the models are warmed all the same, from the storm days there are
        for failure in ({'return_value': False}, {'side_effect': RuntimeError('IBTrACS is down')}):
            with self.subTest(failure=failure):
                self.refresh.reset_mock(side_effect=True, return_value=True)
                self.refresh.configure_mock(**failure)
                with mock.patch.object(hazard_forecast, 'deployed') as built, \
                        mock.patch.object(hazard_forecast.connections, 'close_all'), \
                        self.assertLogs('apps.history.hazard_forecast', level='WARNING'):
                    hazard_forecast._warm()
                self.refresh.assert_called_once_with()
                self.assertEqual([c.args[0] for c in built.call_args_list], ['Flood', 'Landslide'])
        # a missing storm file stops flood only: landslide is still warmed
        self.refresh.reset_mock(side_effect=True, return_value=True)
        self.refresh.return_value = True
        (self.tmp / 'storm_days.csv').unlink()
        with mock.patch.object(hazard_forecast, 'deployed') as built, \
                mock.patch.object(hazard_forecast.connections, 'close_all'), \
                self.assertLogs('apps.history.hazard_forecast', level='WARNING'):
            self.assertTrue(hazard_forecast.warm_in_background())
            for t in threading.enumerate():
                if t.name == hazard_forecast.WARM_THREAD_NAME:
                    t.join(10)
        self.assertIn('Landslide', [c.args[0] for c in built.call_args_list])

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
