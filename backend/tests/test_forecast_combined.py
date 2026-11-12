"""
The forecast API across hazards: the hazards filter, the combined chance
("All hazards"), by_barangay and the 12-month chart that follow it, the HTTP
caching header, the accuracy endpoint's flood and landslide entries, and the
warm-up the hazard list ping starts. Toy files in a temp folder stand in for
apps/history/data/; fire keeps its own model, read and never changed.
"""
import builtins
import copy
import json
import math
import shutil
import sys
import tempfile
from calendar import monthrange
from datetime import date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import requests
from django.contrib.gis.geos import MultiPolygon
from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIRequestFactory

from apps.barangays.models import Barangay
from apps.hazards import views as hazard_views
from apps.hazards.models import HazardType
from apps.history import hazard_data, hazard_forecast, hazard_models, model_forecast, rain
from apps.history.forecast import seasonal_forecast
from apps.history.hazard_data import MANILA
from apps.history.hazard_scenarios import any_chance, pair_chance, period_chance, scenario_dates
from apps.history.models import HistoricalRecord
from apps.history.views import ForecastAccuracyView, HistoricalForecastView, _forecast_events
from tests.fire_setup import box
from tests.hazard_fixtures import toy_source_ref, write_toy_files

TODAY = date(2026, 11, 12)
YEARS = [2021, 2022, 2023, 2024, 2025]        # the toy rain file's complete years
ALL = ['Fire', 'Flood', 'Landslide']
MODELLED = ('Flood', 'Landslide')
PUBLIC = 'public, max-age=600'
BOTH = 'Use hazards or hazard_type_name, not both.'
MODELS_DOWN = 'The flood and landslide models are unavailable right now.'
NOTE = 'Built from the three tested models; not tested on its own.'
REPORT_DOWN = 'The flood and landslide test report could not be loaded right now.'
LIBRARIES_BROKEN = 'The model libraries (scikit-learn and xgboost) could not be loaded.'
LIBRARIES_MISSING = 'The model libraries (scikit-learn and xgboost) are not installed.'
LIBRARIES_LOG = 'The flood and landslide model libraries could not be loaded.'
BY_BARANGAY_KEYS = {'barangay_id', 'barangay', 'level', 'top_hazard', 'probability', 'hazards'}
TOO_FEW = 'Too few fire records to train and test its model.'


def at(day):
    return datetime(day.year, day.month, day.day, 12, tzinfo=MANILA)


def rows(data, hazard):
    return [r for r in data['results'] if r['hazard_type'] == hazard]


class CombinedForecastTests(TestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.barangays = [self.barangay(f'Toy {i}', i) for i in range(3)]
        self.ids = [b.id for b in self.barangays]
        self.terrain, self.rain, self.pos = write_toy_files(self.tmp, self.ids)
        self.kinds = {n: HazardType.objects.create(name=n, logo_class=n.lower()) for n in ALL}
        for hazard in MODELLED:
            HistoricalRecord.objects.bulk_create(
                [HistoricalRecord(barangay_id=b, hazard_type=self.kinds[hazard], severity_level='Green',
                                  source_ref=toy_source_ref(hazard, b, d), occurred_at=at(d),
                                  hazard_subcategory='TOY')
                 for b, d in sorted(self.pos)])
        # fires: the first barangay every mid-July since 2022, the second once; the third never
        fires = [(self.ids[0], date(y, 7, 15)) for y in range(2022, 2026)] + [(self.ids[1], date(2024, 7, 14))]
        for b, d in fires:
            HistoricalRecord.objects.create(barangay_id=b, hazard_type=self.kinds['Fire'], severity_level='Orange',
                                            occurred_at=at(d))
        self.report_path = self.tmp / 'hazard_model_report.json'
        self.fire_table = None
        # NASA POWER is never called from the tests: the live rain is down unless a test says otherwise
        for patcher in (mock.patch.object(hazard_data, 'DATA_DIR', self.tmp),
                        mock.patch.object(hazard_models, 'REPORT_PATH', self.report_path),
                        mock.patch.object(hazard_forecast, 'recent_rain', mock.Mock(return_value=None))):
            patcher.start()
            self.addCleanup(patcher.stop)

    def barangay(self, name, slot):
        return Barangay.objects.create(name=name, municipality='Talisay',
                                       boundary=MultiPolygon(box(1000 * slot, 0, 1000 * slot + 900, 900), srid=4326))

    @staticmethod
    def get(view=HistoricalForecastView, **params):
        return view.as_view()(APIRequestFactory().get('/', params))

    def fire_model(self):
        """
        Fire's model in use, as model_forecast._fitted gives it once the model
        passed its test: a fixed table for every place, kept in self.fire_table.
        The other hazards' Poisson models do not pass.
        """
        def fitted(hazard, events, until, today):
            where = model_forecast.places()
            if hazard != 'Fire':
                return {'places': where, 'report': {'status': 'too_few_records'}, 'table': None,
                        'in_training': False, 'reason': TOO_FEW}
            order = sorted(p['id'] for p in where)
            self.fire_table = {pid: [0.05 + 0.03 * order.index(pid) + 0.01 * m for m in range(12)] for pid in order}
            return {'places': where, 'report': {'status': 'in_use'}, 'table': self.fire_table,
                    'in_training': False, 'reason': None}
        return mock.patch.object(model_forecast, '_fitted', side_effect=fitted)

    def expected(self, b, hazards, month=7, year=None):
        """The combined month chance by the rule (spec 3.2), from fire's table and the deployed models."""
        dates = scenario_dates(month, None, year, YEARS)
        parts = []
        if 'Fire' in hazards:
            parts.append(model_forecast.chance(self.fire_table[b][month - 1]))
        gets = [hazard_forecast.deployed(h).daily[b].get for h in MODELLED if h in hazards]
        if len(gets) == 2:
            parts.append(pair_chance(gets[0], gets[1], dates).probability)
        elif gets:
            parts.append(period_chance(gets[0], dates).probability)
        return any_chance(parts)

    def edit_report(self, **entries):
        """Change the toy report's hazard entries: {hazard: fields to set}, or None to remove the entry."""
        report = json.loads(self.report_path.read_text(encoding='utf-8'))
        for hazard, fields in entries.items():
            if fields is None:
                del report['hazards'][hazard]
            else:
                report['hazards'][hazard].update(fields)
        self.report_path.write_text(json.dumps(report), encoding='utf-8')

    # ---- the combined chance ----

    def test_combined_chance_matches_the_rule_for_one_barangay(self):
        b, name = 7, 'One'
        places = [{'id': b, 'name': name, 'area_km2': 1.0, 'puroks': 1}]

        def row(hazard, probability, expected, level, **extra):
            return {'barangay_id': b, 'barangay': name, 'hazard_type': hazard, 'probability': probability,
                    'expected_events': expected, 'level': level, **extra}

        def scen(daily, dates, month_dates):
            return {h: {'deployed': hazard_forecast.Deployed(h, None, daily, {}, [2021, 2022], None, {}),
                        'chances': {b: period_chance(daily[b].get, dates)},
                        'dates_by_s': dates, 'month_dates_by_s': month_dates}
                    for h in MODELLED}

        # Task 7's storms: flood and landslide each 0.5 on one day of 2021, nothing in 2022
        dates = {2021: [date(2021, 8, 1)], 2022: [date(2022, 8, 1)]}
        daily = {b: {date(2021, 8, 1): 0.5, date(2022, 8, 1): 0.0}}
        result = {'month': 8, 'day': None, 'year': None, 'profile': None, 'by_barangay': [],
                  'results': [row('Fire', 0.2, 0.22, 'Low', method='model'),
                              row('Flood', 0.25, 0.25, 'High', method='model'),
                              row('Landslide', 0.25, 0.25, 'High', method='model')]}
        fire_table = {b: [-math.log(0.8)] * 12}                          # a chance of 0.2 every month
        hazard_forecast.combine(result, scen(daily, dates, dates), fire_table, ALL, 8, None, None, None, places,
                                TODAY)
        (combined,) = result['combined']
        # 1 - (1 - 0.2)(1 - 0.375): the pair inside each storm, not 1 - 0.8 * 0.75 * 0.75 = 0.55
        self.assertEqual(combined['probability'], 0.5)
        self.assertEqual(combined, {
            'barangay_id': b, 'barangay': name, 'probability': 0.5, 'expected_events': 0.72, 'level': 'High',
            'top_hazard': 'Flood', 'missing': [],
            'hazards': [{'hazard_type': 'Fire', 'probability': 0.2, 'level': 'Low'},
                        {'hazard_type': 'Flood', 'probability': 0.25, 'level': 'High'},
                        {'hazard_type': 'Landslide', 'probability': 0.25, 'level': 'High'}]})
        self.assertEqual(result['hazards_included'], ALL)
        self.assertEqual(result['by_barangay'], [{'barangay_id': b, 'barangay': name, 'level': 'High',
                                                  'top_hazard': 'Flood', 'probability': 0.5,
                                                  'hazards': ['Fire', 'Flood', 'Landslide']}])

        # a fire row with no model behind it (a counting share) never enters the chance: only models count
        result = {'month': 8, 'day': None, 'year': None, 'profile': None, 'by_barangay': [],
                  'results': [row('Fire', 0.2, 0.22, 'Low'),
                              row('Flood', 0.25, 0.25, 'High', method='model'),
                              row('Landslide', 0.25, 0.25, 'High', method='model')]}
        hazard_forecast.combine(result, scen(daily, dates, dates), None, ALL, 8, None, None, None, places, TODAY)
        (combined,) = result['combined']
        self.assertEqual((combined['probability'], combined['missing']), (0.375, ['Fire']))

        # the week view with fire's table: the figure is the week's, the level the month's
        rate = 0.3
        week = {2021: [date(2021, 8, 1)], 2022: [date(2022, 8, 1)]}
        month = {2021: [date(2021, 8, 1), date(2021, 8, 2)], 2022: [date(2022, 8, 1), date(2022, 8, 2)]}
        daily = {b: {date(2021, 8, 1): 0.1, date(2022, 8, 1): 0.0, date(2021, 8, 2): 0.3, date(2022, 8, 2): 0.3}}
        before = (copy.deepcopy(week), copy.deepcopy(month))
        given = scen(daily, week, month)
        share = 7 / monthrange(2025, 8)[1]
        result = {'month': 8, 'day': 15, 'year': 2025, 'profile': None, 'by_barangay': [],
                  'results': [row('Fire', round(model_forecast.chance(rate * share), 3), round(rate * share, 2),
                                  'High', method='model'),
                              row('Flood', 0.05, 0.05, 'Moderate', method='model'),
                              row('Landslide', 0.05, 0.05, 'Moderate', method='model')]}
        hazard_forecast.combine(result, given, {b: [rate] * 12}, ALL, 8, 15, 2025, None, places, TODAY)
        (combined,) = result['combined']
        f = l = daily[b].get
        in_week = any_chance([model_forecast.chance(rate * share), pair_chance(f, l, week).probability])
        in_month = any_chance([model_forecast.chance(rate), pair_chance(f, l, month).probability])
        self.assertEqual(combined['probability'], round(in_week, 3))
        self.assertEqual(model_forecast.level_for(in_week), 'Moderate')
        self.assertEqual(combined['level'], model_forecast.level_for(in_month))
        self.assertEqual(combined['level'], 'High')
        flood_week = given['Flood']['chances'][b]
        self.assertEqual(combined['expected_events'], round(rate * share + 2 * flood_week.expected, 2))
        self.assertEqual((week, month), before)              # Task 9's scenario dates are read, never changed

    def test_hazards_param_limits_rows_and_the_combined_chance(self):
        with self.fire_model():
            data = self.get(month=7, hazards='Fire,Flood').data
        self.assertEqual(data['hazards_included'], ['Fire', 'Flood'])
        self.assertEqual({r['hazard_type'] for r in data['results']}, {'Fire', 'Flood'})
        self.assertNotIn('Landslide', data['model_hazards'])
        self.assertEqual(sorted(c['barangay_id'] for c in data['combined']), sorted(self.ids))
        for c in data['combined']:
            self.assertEqual([h['hazard_type'] for h in c['hazards']], ['Fire', 'Flood'])
            self.assertEqual(c['missing'], [])
            p = self.expected(c['barangay_id'], ['Fire', 'Flood'])
            self.assertEqual(c['probability'], round(p, 3))
            self.assertEqual(c['level'], model_forecast.level_for(p))
        # the basis counts only the hazards asked for
        floods = len(self.pos)
        self.assertEqual(data['basis']['records'], floods + 5)

    def test_hazards_param_ignores_case_spaces_and_duplicates(self):
        parse = hazard_forecast.parse_hazards
        self.assertEqual(parse({'hazards': 'fire, Flood,flood'}, ALL), ['Fire', 'Flood'])
        self.assertEqual(parse({'hazards': ' LANDSLIDE ,fire,'}, ALL), ['Fire', 'Landslide'])
        self.assertEqual(parse({'hazard_type_name': 'flood'}, ALL), ['Flood'])
        self.assertEqual(parse({}, ALL), ALL)                          # neither: every hazard
        self.assertEqual(parse({'hazards': ''}, ALL), ALL)             # an empty list: every hazard
        data = self.get(month=7, hazards='fire, Flood,flood').data
        self.assertEqual(data['hazards_included'], ['Fire', 'Flood'])
        self.assertEqual(self.get(month=7, hazard_type_name='landslide').data['hazards_included'], ['Landslide'])
        self.assertEqual(self.get(month=7).data['hazards_included'], ALL)

    def test_both_parameters_is_a_400(self):
        with self.assertRaisesMessage(ValueError, BOTH):
            hazard_forecast.parse_hazards({'hazards': 'Fire', 'hazard_type_name': 'Flood'}, ALL)
        response = self.get(month=7, hazards='Fire', hazard_type_name='Flood')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data, {'error': BOTH})

    def test_unknown_hazard_is_a_400_listing_the_valid_names(self):
        for params in ({'hazards': 'Fire,Earthquake'}, {'hazard_type_name': 'Earthquake'}):
            with self.subTest(params=params):
                with self.assertRaises(ValueError):
                    hazard_forecast.parse_hazards(params, ALL)
                response = self.get(month=7, **params)
                self.assertEqual(response.status_code, 400)
                for word in ('Earthquake', 'Fire', 'Flood', 'Landslide'):
                    self.assertIn(word, response.data['error'])

    def test_by_barangay_keeps_its_shape_and_follows_combined(self):
        for model in (True, False):
            with self.subTest(fire_model=model):
                cache.clear()
                if model:
                    with self.fire_model():
                        data = self.get(month=7).data
                else:
                    data = self.get(month=7).data                 # too few fires: fire unavailable, never counting
                combined = [c for c in data['combined'] if c['probability'] is not None]
                self.assertEqual(len(data['by_barangay']), len(combined))
                for summary, c in zip(data['by_barangay'], combined):
                    self.assertEqual(set(summary), BY_BARANGAY_KEYS)
                    self.assertEqual({k: summary[k] for k in ('barangay_id', 'barangay', 'level', 'top_hazard',
                                                              'probability')},
                                     {k: c[k] for k in ('barangay_id', 'barangay', 'level', 'top_hazard',
                                                        'probability')})
                    # still a sorted list of names, as before
                    self.assertEqual(summary['hazards'], sorted(h['hazard_type'] for h in c['hazards']
                                                                if h['level'] != 'None'))
                    self.assertTrue(all(isinstance(h, str) for h in summary['hazards']))
                    # the chance of any of them, at least each one's own
                    self.assertTrue(all(c['probability'] >= h['probability']
                                        for h in c['hazards'] if h['probability'] is not None))
                ranked = [(['None', 'Low', 'Moderate', 'High'].index(c['level']), c['probability'], c['barangay'])
                          for c in combined]
                self.assertEqual(ranked, sorted(ranked, key=lambda r: (-r[0], -r[1], r[2])))
                if model:
                    self.assertEqual(len(combined), 3)
                else:
                    third = next(c for c in data['combined'] if c['barangay_id'] == self.ids[2])
                    self.assertEqual(third['missing'], ['Fire'])
                    summary = next(s for s in data['by_barangay'] if s['barangay_id'] == self.ids[2])
                    self.assertEqual(summary['hazards'], ['Flood', 'Landslide'])

    def test_unavailable_hazard_is_named_in_missing(self):
        with self.fire_model():
            self.report_path.unlink()
            with self.assertLogs('apps.history.hazard_forecast', level='WARNING'):
                data = self.get(month=7).data
            self.assertEqual(data['unavailable_hazards'], ['Flood', 'Landslide'])
            fire = {r['barangay_id']: r for r in rows(data, 'Fire')}
            for c in data['combined']:
                self.assertEqual(c['missing'], ['Flood', 'Landslide'])
                self.assertEqual(c['probability'], fire[c['barangay_id']]['probability'])
                self.assertEqual(c['top_hazard'], 'Fire')
                self.assertEqual(c['hazards'][1:], [{'hazard_type': 'Flood', 'probability': None, 'level': 'None'},
                                                    {'hazard_type': 'Landslide', 'probability': None,
                                                     'level': 'None'}])

            # a barangay with a boundary but no terrain or rain yet: only its row lists them
            write_toy_files(self.tmp, self.ids)
            later = self.barangay('A boundary added later', 4)
            cache.clear()
            data = self.get(month=7).data
        combined = {c['barangay_id']: c for c in data['combined']}
        self.assertEqual(combined[later.id]['missing'], ['Flood', 'Landslide'])
        fire = next(r for r in rows(data, 'Fire') if r['barangay_id'] == later.id)
        self.assertEqual(combined[later.id]['probability'], fire['probability'])
        for b in self.ids:
            self.assertEqual(combined[b]['missing'], [])

    def test_a_failing_model_step_never_takes_the_forecast_down(self):
        b = self.ids[0]
        # flood and landslide fail as a whole: unavailable rows and chart, never counting
        with mock.patch.object(hazard_forecast, 'use_hazard_models', side_effect=RuntimeError('boom')), \
                self.assertLogs('apps.history.views', level='ERROR'):
            response = self.get(month=7, hazards='Flood', barangay=b)
        self.assertEqual(response.status_code, 200)
        data = response.data
        flood = rows(data, 'Flood')
        self.assertEqual(sorted(r['barangay_id'] for r in flood), sorted(self.ids))
        for r in flood:
            self.assertEqual((r['method'], r['probability'], r['level'], r['reason']),
                             ('unavailable', None, 'None', MODELS_DOWN))
        self.assertEqual(data['unavailable_hazards'], ['Flood'])
        self.assertEqual(data['profile_method'], 'unavailable')
        self.assertTrue(all(e['probability'] is None for e in data['profile']))
        self.assertTrue(all(c['missing'] == ['Flood'] and c['probability'] is None for c in data['combined']))
        # with fire too, the combined chance and the chart come from fire alone
        with self.fire_model(), \
                mock.patch.object(hazard_forecast, 'use_hazard_models', side_effect=RuntimeError('boom')), \
                self.assertLogs('apps.history.views', level='ERROR'):
            data = self.get(month=7, barangay=b).data
        self.assertEqual(data['unavailable_hazards'], ['Flood', 'Landslide'])
        for c in data['combined']:
            self.assertEqual(c['missing'], ['Flood', 'Landslide'])
            self.assertEqual(c['probability'], round(self.expected(c['barangay_id'], ['Fire']), 3))
        self.assertEqual(data['profile_method'], 'model')
        self.assertEqual([e['probability'] for e in data['profile']],
                         [round(model_forecast.chance(rate), 3) for rate in self.fire_table[b]])
        # the combined chance fails: every hazard's rows stand, `combined` is empty and the chart has no figure
        with mock.patch.object(hazard_forecast, 'combine', side_effect=RuntimeError('boom')), \
                self.assertLogs('apps.history.views', level='ERROR'):
            response = self.get(month=7)
        self.assertEqual(response.status_code, 200)
        data = response.data
        self.assertEqual(data['combined'], [])
        self.assertEqual(data['hazards_included'], ALL)
        self.assertTrue(all(r['method'] == 'model' for h in MODELLED for r in rows(data, h)))
        self.assertEqual(data['profile_method'], 'unavailable')

    def test_a_tiny_positive_chance_is_never_sent_as_zero(self):
        """
        Every barangay-day's chance is tiny, so each period's chance is under
        0.0005, which round(x, 3) sends as 0. It keeps 2 significant figures
        instead: on the rows and their range, the rain so far, the combined
        chance and both charts.
        """
        first, last = date(2021, 1, 1), date(2025, 12, 15)          # the rain file ends mid-December 2025
        days = [first + timedelta(days=i) for i in range((last - first).days + 1)]
        daily = {b: {d: 4e-6 if d.year == 2021 else 8e-6 for d in days} for b in self.ids}
        rf = rain.RainFile({b: {} for b in self.ids}, {}, first, last)
        model = SimpleNamespace(name='logistic_regression')
        deps = {h: hazard_forecast.Deployed(h, model, daily, {}, YEARS, rf, {}) for h in MODELLED}

        def sig2(x):
            return float(f'{x:.2g}')

        with mock.patch.object(hazard_forecast, 'deployed', side_effect=deps.get):
            data = self.get(month=7, hazards='Flood,Landslide').data
            whole = self.get(month=6, year=2024, hazards='Flood').data      # every day of June 2024 recorded
            part = self.get(month=12, year=2025, hazards='Flood').data      # recorded to 15 December
        dates = scenario_dates(7, None, None, YEARS)
        for hazard in MODELLED:
            found = rows(data, hazard)
            self.assertEqual(len(found), len(self.ids))
            for r in found:
                pc = period_chance(daily[r['barangay_id']].get, dates)
                self.assertEqual(round(pc.probability, 3), 0.0)             # what was sent before
                self.assertEqual(r['probability'], sig2(pc.probability))
                self.assertEqual(r['expected_events'], sig2(pc.expected))
                self.assertEqual(r['range'], [sig2(pc.low), sig2(pc.high)])
                self.assertGreater(r['range'][0], 0)
                self.assertLess(r['range'][0], r['range'][1])
        self.assertEqual(len(data['combined']), len(self.ids))
        for c in data['combined']:
            b = c['barangay_id']
            pair = pair_chance(daily[b].get, daily[b].get, dates).probability
            self.assertLess(pair, 0.0005)
            self.assertEqual(c['probability'], sig2(any_chance([pair])))
            self.assertGreater(c['expected_events'], 0)
            self.assertTrue(all(h['probability'] > 0 for h in c['hazards']))
        # the combined chart, then flood's own chart and its rain so far
        self.assertTrue(all(e['probability'] > 0 and e['expected_events'] > 0 for e in data['profile']))
        for single in (whole, part):
            found = rows(single, 'Flood')
            self.assertEqual(len(found), len(self.ids))
            self.assertTrue(all(0 < r['recorded_rain_probability'] < 0.0005 for r in found))
            self.assertEqual(len(single['profile']), 12)
            self.assertTrue(all(e['probability'] > 0 and e['expected_events'] > 0 for e in single['profile']))

    # ---- the 12-month chart ----

    def test_profile_is_combined_for_several_and_single_for_one(self):
        b = self.ids[0]
        with self.fire_model():
            data = self.get(month=7, barangay=b).data
            self.assertEqual(data['profile_method'], 'model')
            for entry in data['profile']:
                p = self.expected(b, ALL, month=entry['month'])
                self.assertEqual((entry['probability'], entry['level']),
                                 (round(p, 3), model_forecast.level_for(p)), entry['month'])
            # the city: the mean over the barangays
            data = self.get(month=7).data
            for entry in data['profile']:
                mean = sum(self.expected(i, ALL, month=entry['month']) for i in self.ids) / len(self.ids)
                self.assertEqual(entry['probability'], round(mean, 3), entry['month'])
            # a subset uses the same rule with only those hazards
            data = self.get(month=7, hazards='Fire,Landslide', barangay=b).data
            for entry in data['profile']:
                p = self.expected(b, ['Fire', 'Landslide'], month=entry['month'])
                self.assertEqual(entry['probability'], round(p, 3), entry['month'])
            # one hazard: its own chart, fire's from its model
            data = self.get(month=7, hazards='Fire', barangay=b).data
            self.assertEqual(data['profile_method'], 'model')
            self.assertEqual([e['probability'] for e in data['profile']],
                             [round(model_forecast.chance(rate), 3) for rate in self.fire_table[b]])
        # flood alone: Task 9's chart
        data = self.get(month=7, hazards='Flood', barangay=b).data
        dep = hazard_forecast.deployed('Flood')
        self.assertEqual(data['profile_method'], 'model')
        for entry in data['profile']:
            pc = period_chance(dep.daily[b].get, scenario_dates(entry['month'], None, None, YEARS))
            self.assertEqual(entry['probability'], round(pc.probability, 3), entry['month'])

    # ---- headers, live rain, accuracy, fire, warm-up ----

    def test_both_endpoints_send_cache_control(self):
        for url, params in (('/api/history/forecast/', {'month': 7}), ('/api/history/forecast/accuracy/', {})):
            with self.subTest(url=url):
                response = self.client.get(url, params)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response['Cache-Control'], PUBLIC)
        # an error is never cached for everyone
        response = self.get(month=7, hazards='Fire', hazard_type_name='Fire')
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.has_header('Cache-Control'))
        with mock.patch.object(model_forecast, 'accuracy_reports', side_effect=RuntimeError('down')), \
                self.assertLogs('apps.history.views', level='ERROR'):
            response = self.get(ForecastAccuracyView)
        self.assertEqual(response.status_code, 503)
        self.assertFalse(response.has_header('Cache-Control'))

    def test_fire_accuracy_stands_when_the_flood_and_landslide_report_cannot_load(self):
        want = self.get(ForecastAccuracyView).data['hazards'][0]          # fire's entry with nothing failing
        self.assertEqual(want['hazard'], 'Fire')
        down = [{'hazard': h, 'kind': 'rain_terrain', 'status': 'unavailable', 'reason': REPORT_DOWN}
                for h in MODELLED]
        failures = {
            # a missing library: importing hazard_models raises ImportError
            'import': lambda: mock.patch.dict(sys.modules, {'apps.history.hazard_models': None}),
            # a report or a library that fails once loaded
            'entries': lambda: mock.patch.object(hazard_models, 'accuracy_entries',
                                                 side_effect=ValueError('bad report')),
        }
        for name, failure in failures.items():
            with self.subTest(failure=name):
                with failure(), self.assertLogs('apps.history.views', level='ERROR'):
                    response = self.get(ForecastAccuracyView)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response['Cache-Control'], PUBLIC)
                self.assertEqual(response.data, {'hazards': [want, *down], 'combined_note': NOTE})

    def test_a_model_library_that_fails_to_load_makes_the_models_unavailable(self):
        real_import = builtins.__import__

        def failing(error):
            def fake(name, globals=None, locals=None, fromlist=(), level=0):
                if name == 'apps.history' and 'hazard_models' in (fromlist or ()):
                    raise error
                return real_import(name, globals, locals, fromlist, level)
            return fake

        # a broken xgboost load raises XGBoostError (a ValueError) or OSError, not ImportError; it is
        # logged with its traceback, since its callers log only the one-line reason
        for error, message in ((ValueError('xgboost could not load its library'), LIBRARIES_BROKEN),
                               (OSError('libxgboost.dll not found'), LIBRARIES_BROKEN)):
            with self.subTest(error=type(error).__name__):
                with mock.patch('builtins.__import__', failing(error)), \
                        self.assertLogs('apps.history.hazard_forecast', 'ERROR') as logs, \
                        self.assertRaisesMessage(hazard_forecast.Unavailable, message) as caught:
                    hazard_forecast._models()
                self.assertIs(caught.exception.__cause__, error)
                (record,) = logs.records
                self.assertEqual(record.getMessage(), LIBRARIES_LOG)
                self.assertIs(record.exc_info[1], error)
        # a library that is not installed keeps its own message, with nothing logged here
        error = ImportError('No module named xgboost')
        with mock.patch('builtins.__import__', failing(error)), \
                self.assertNoLogs('apps.history.hazard_forecast', 'ERROR'), \
                self.assertRaisesMessage(hazard_forecast.Unavailable, LIBRARIES_MISSING) as caught:
            hazard_forecast._models()
        self.assertIs(caught.exception.__cause__, error)

    def test_forecast_answers_when_live_rain_fails(self):
        on = timezone.localdate() - timedelta(days=10)       # a week after the rain file, already over
        with mock.patch.object(hazard_forecast, 'recent_rain', rain.recent_rain), \
                mock.patch.object(rain, 'get', side_effect=requests.ConnectionError('NASA POWER is down')) as live, \
                self.assertLogs('apps.history.rain', level='WARNING'):          # the operator is told
            response = self.get(date=on.isoformat())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Cache-Control'], PUBLIC)
        live.assert_called_once()                            # tried once; the failure is cached for both hazards
        data = response.data
        for hazard in MODELLED:
            self.assertTrue(all(r['method'] == 'model' for r in rows(data, hazard)))
        self.assertFalse(any('recorded_rain_probability' in r for r in data['results']))
        self.assertEqual(len(data['combined']), len(self.ids))

    def test_accuracy_status_in_use_not_better_unavailable_and_stale(self):
        def entries():
            body = self.get(ForecastAccuracyView).data
            self.assertEqual(body['combined_note'], NOTE)
            return body['hazards']

        self.edit_report(Flood={'beats_benchmark': True}, Landslide={'beats_benchmark': False})
        hazards = entries()
        # fire's test as it is; flood's and landslide's counting tests replaced by their rain-and-terrain reports
        self.assertEqual([(h['hazard'], h.get('kind')) for h in hazards],
                         [('Fire', None), ('Flood', 'rain_terrain'), ('Landslide', 'rain_terrain')])
        self.assertEqual(hazards[0]['status'], 'too_few_records')
        flood, slide = hazards[1], hazards[2]
        self.assertEqual((flood['status'], flood['stale']), ('in_use', False))
        self.assertEqual((slide['status'], slide['stale']), ('in_use_not_better', False))
        self.assertEqual(flood['winner'], 'logistic_regression')
        self.assertEqual(flood['study'], {'start': '2021-01-01', 'end': '2025-12-31'})
        self.assertEqual(flood['tested_at'], '2026-11-12T00:00:00+08:00')
        # an approved report dated after the study period changes nothing
        HistoricalRecord.objects.create(barangay=self.barangays[2], hazard_type=self.kinds['Flood'],
                                        severity_level='Orange', source_ref='approved-report-2026',
                                        occurred_at=at(date(2026, 3, 1)), hazard_subcategory='TOY')
        self.assertEqual([h.get('stale') for h in entries()[1:]], [False, False])
        # a record added inside it does: the card asks for the test to be run again
        HistoricalRecord.objects.create(barangay=self.barangays[2], hazard_type=self.kinds['Flood'],
                                        severity_level='Orange', source_ref='late-entry-2024',
                                        occurred_at=at(date(2024, 3, 1)), hazard_subcategory='TOY')
        self.assertEqual([h.get('stale') for h in entries()[1:]], [True, False])
        # no entry for a hazard, then no report at all
        self.edit_report(Landslide=None)
        slide = entries()[2]
        self.assertEqual(set(slide), {'hazard', 'kind', 'status', 'reason'})
        self.assertEqual((slide['hazard'], slide['kind'], slide['status']),
                         ('Landslide', 'rain_terrain', 'unavailable'))
        self.report_path.unlink()
        for entry in entries()[1:]:
            self.assertEqual((entry['kind'], entry['status']), ('rain_terrain', 'unavailable'))
            self.assertIn('test_hazard_models', entry['reason'])

    def test_fire_rows_come_from_fires_own_model_or_are_unavailable(self):
        def fire(found):
            return sorted((r for r in found if r['hazard_type'] == 'Fire'), key=lambda r: r['barangay_id'])

        def alone(names, month, day=None, year=None):
            """Fire's rows from the counting and fire's model alone, over the same records."""
            now = timezone.localtime()
            events = [e for e in _forecast_events() if e['hazard'] in names]
            result = seasonal_forecast(events, month, now, day=day, year=year)
            result['profile'] = []                           # the chart plays no part in the rows
            model_forecast.use_models(result, events, month, day=day, hazard=None, barangay=None,
                                      today=now.date())
            return fire(result['results'])

        periods = [({'month': 7}, (7,)), ({'month': 7, 'year': 2025}, (7, None, 2025)),
                   ({'date': '2025-07-15'}, (7, 15, 2025))]
        # every hazard is the view's old default; hazard_type_name=Fire its old single-hazard request
        asked = [({}, ALL), ({'hazards': 'Fire,Flood'}, ['Fire', 'Flood']), ({'hazard_type_name': 'Fire'}, ['Fire'])]
        for model in (False, True):
            for params, period in periods:
                for hazards, names in asked:
                    with self.subTest(fire_model=model, params=params, hazards=hazards):
                        if model:
                            with self.fire_model():
                                got = fire(self.get(**params, **hazards).data['results'])
                                want = alone(names, *period)
                            self.assertEqual(got, want)
                            self.assertTrue(all(r['method'] == 'model' for r in got))
                        else:
                            # five fires are too few to train and test: unavailable, never the counting
                            got = fire(self.get(**params, **hazards).data['results'])
                            self.assertEqual({(r['method'], r['probability'], r['level'], r['reason']) for r in got},
                                             {('unavailable', None, 'None', TOO_FEW)})
                            self.assertEqual(len(got), len(self.ids))
                        self.assertTrue(got)

    def test_hazard_list_ping_warms_the_models(self):
        with mock.patch.object(hazard_forecast, 'warm_in_background') as warm:
            response = self.client.get('/api/hazards/')
        self.assertEqual(response.status_code, 200)
        warm.assert_called_once_with()
        # a warm-up problem never breaks the hazard list the uptime ping relies on
        cache.delete(hazard_views.WARM_CHECK_KEY)            # a minute later
        with mock.patch.object(hazard_forecast, 'warm_in_background', side_effect=RuntimeError('no warm-up')), \
                self.assertLogs('apps.hazards.views', level='ERROR'):
            response = self.client.get('/api/hazards/')
        self.assertEqual(response.status_code, 200)

    def test_hazard_list_asks_about_the_warm_up_once_a_minute(self):
        with mock.patch.object(hazard_forecast, 'warm_in_background') as warm:
            for _ in range(2):                               # the map polling inside the window
                self.assertEqual(self.client.get('/api/hazards/').status_code, 200)
            warm.assert_called_once_with()
            cache.delete(hazard_views.WARM_CHECK_KEY)        # the window is over
            self.assertEqual(self.client.get('/api/hazards/').status_code, 200)
            self.assertEqual(warm.call_count, 2)
        # a cache that fails never stops the warm-up: it is checked anyway, with a warning
        failing = mock.Mock(**{'add.side_effect': RuntimeError('cache down')})
        with mock.patch.object(hazard_views, 'cache', failing), \
                mock.patch.object(hazard_forecast, 'warm_in_background') as warm, \
                self.assertLogs('apps.hazards.views', level='WARNING'):
            self.assertEqual(self.client.get('/api/hazards/').status_code, 200)
        warm.assert_called_once_with()
        failing.add.assert_called_once_with('geoalert:hazard-model-warm-check', 1, timeout=60)
