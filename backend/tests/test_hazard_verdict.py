import json
import math
import warnings
from datetime import date, timedelta
from unittest import mock

import numpy as np
from django.test import SimpleTestCase
from sklearn.metrics import average_precision_score, log_loss, roc_auc_score

from apps.history import hazard_tests, hazard_verdict
from apps.history.firth import FitFailed
from apps.history.hazard_data import STUDY_START, Dataset, rain_windows
from apps.history.hazard_models import CannotEvaluate, _auc
from apps.history.hazard_scoring import score_logistic
from apps.history.hazard_tests import BASELINES, HazardData, LogisticContender
from apps.history.hazard_verdict import (
    _table, breakeven, event_table, evaluate, level_tables, model_scores, outside_test, per_year, poisson_interval,
    verdict, wald_slopes, when_scores, where_scores)
from apps.history.storms import StormDays
from apps.history.two_part import FEATURES, WhenFit, fit_when
from tests.hazard_fixtures import toy_inputs
from tests.test_hazard_tests import custom_data, toy_flood, toy_landslide

NEW, CURRENT = 'two_part', 'logistic_regression'


def sedi_formula(F, H):
    return ((math.log(F) - math.log(H) - math.log(1 - F) + math.log(1 - H))
            / (math.log(F) + math.log(H) + math.log(1 - F) + math.log(1 - H)))


def small_data(days, hits, n=3, unnamed=()):
    """A hand-made HazardData: n barangays on each of `days`; `hits` {day: {barangay, ...}}; `unnamed` event
    days whose records name no barangay."""
    days = sorted(set(days) | set(hits) | set(unnamed))
    ids = list(range(1, n + 1))
    y = np.array([int(b in hits.get(d, ())) for d in days for b in ids])
    rows = Dataset(X=np.zeros((len(y), 1)), y=y, barangay_id=np.array(ids * len(days)),
                   day=np.repeat(np.array(days, dtype='datetime64[D]'), n), features=('r0',))
    return HazardData(
        hazard='Flood', rows=rows, city_day=np.array(days, dtype='datetime64[D]'), city_X=np.zeros((len(days), 2)),
        city_y=np.array([int(d in hits or d in unnamed) for d in days]), extra_day=None, extra_X=None,
        extra_y=None, place={b: 1.0 for b in ids}, named_events=sorted((d, set(s)) for d, s in hits.items()),
        extra_named=[], rain={}, records=[])


def set_chance(data, p, day, values, hit_only=False):
    """p for `day`'s rows (barangays 1..n in order), or for its hit rows only when `hit_only`."""
    on = data.rows.day == np.datetime64(day)
    if hit_only:
        on &= data.rows.y == 1
    p[on] = values
    return p


class TableTests(SimpleTestCase):
    def test_sedi_and_peirce_on_a_known_table(self):
        # hits 3, misses 1, false alarms 10, correct negatives 86: H=0.75, F=10/96
        t = _table(3, 1, 10, 86)
        self.assertAlmostEqual(t['peirce'], 0.75 - 10 / 96)
        self.assertAlmostEqual(t['sedi'], sedi_formula(10 / 96, 0.75))
        self.assertAlmostEqual(t['false_alarms_per_event'], 10 / 4)
        self.assertAlmostEqual(t['pod'], 0.75)
        self.assertAlmostEqual(t['far'], 10 / 13)
        self.assertEqual((t['hits'], t['misses'], t['false_alarms'], t['correct_negatives']), (3, 1, 10, 86))
        # no real event: POD, Peirce, SEDI and false alarms per event are undefined
        quiet = _table(0, 0, 3, 7)
        for key in ('pod', 'peirce', 'sedi', 'false_alarms_per_event'):
            self.assertIsNone(quiet[key], key)
        self.assertAlmostEqual(quiet['far'], 1.0)
        # every event caught (H = 1): SEDI undefined, Peirce defined
        self.assertIsNone(_table(2, 0, 1, 5)['sedi'])
        self.assertAlmostEqual(_table(2, 0, 1, 5)['peirce'], 1 - 1 / 6)
        self.assertIsNone(_table(0, 0, 0, 0)['far'])

    def test_breakeven_is_5_7_and_3_0(self):
        self.assertEqual([round(b['false_alarms_per_event'], 2) for b in breakeven()], [3.0, 5.67])
        self.assertEqual([b['cutoff'] for b in breakeven()], [0.25, 0.15])

    def test_exact_poisson_interval_for_zero_and_five(self):
        low, high = poisson_interval(0)
        self.assertEqual(low, 0.0)
        self.assertAlmostEqual(high, -math.log(0.025), places=9)        # 3.689
        low, high = poisson_interval(5)
        self.assertAlmostEqual(low, 1.6235, places=4)
        self.assertAlmostEqual(high, 11.6683, places=4)

    def test_per_year_counts_barangay_day_events(self):
        days = [date(2023, 5, 1), date(2023, 6, 1), date(2024, 5, 1)]
        data = small_data(days, {date(2023, 5, 1): {1, 2}, date(2023, 6, 1): {3}})
        p = np.linspace(0.01, 0.09, len(data.rows.y))
        out = per_year(data, p)
        self.assertEqual([r['year'] for r in out], [2023, 2024])
        self.assertEqual([r['observed'] for r in out], [3, 0])
        self.assertAlmostEqual(out[0]['expected'], p[:6].sum())
        self.assertAlmostEqual(out[1]['expected'], p[6:].sum())
        self.assertEqual((out[0]['low'], out[0]['high']), poisson_interval(3))
        self.assertEqual((out[1]['low'], out[1]['high']), poisson_interval(0))

    def test_level_tables_count_barangay_months(self):
        jan1, jan2, feb1, feb2 = date(2024, 1, 1), date(2024, 1, 2), date(2024, 2, 1), date(2024, 2, 2)
        data = small_data([jan1, jan2, feb1, feb2], {jan1: {1}}, n=2)
        p = np.zeros(len(data.rows.y))
        set_chance(data, p, jan1, [0.2, 0.1])
        set_chance(data, p, jan2, [0.1, 0.1])
        set_chance(data, p, feb1, [0.3, 0.0])
        # month chances 1 - prod(1 - p): Jan b1 0.28 (event), Jan b2 0.19, Feb b1 0.3, Feb b2 0
        high, moderate = level_tables(data, p)
        self.assertEqual(high['cutoff'], 0.25)
        self.assertEqual((high['hits'], high['misses'], high['false_alarms'], high['correct_negatives']),
                         (1, 0, 1, 2))
        self.assertEqual(moderate['cutoff'], 0.15)
        self.assertEqual((moderate['hits'], moderate['misses'], moderate['false_alarms'],
                          moderate['correct_negatives']), (1, 0, 2, 1))
        self.assertAlmostEqual(high['false_alarms_per_event'], 1.0)
        self.assertAlmostEqual(moderate['false_alarms_per_event'], 2.0)


class ScoreTests(SimpleTestCase):
    def test_model_scores(self):
        rng = np.random.default_rng(0)
        q = rng.uniform(0.01, 0.6, 20000)
        y = (rng.random(len(q)) < q).astype(int)
        p = q ** 2 / (q ** 2 + (1 - q) ** 2)          # logit(p) = 2 logit(q): too extreme, slope 0.5
        clim = np.full(len(y), y.mean())
        s = model_scores(y, p, clim, q)
        self.assertAlmostEqual(s['log_loss'], log_loss(y, p))
        self.assertAlmostEqual(s['brier'], float(np.mean((p - y) ** 2)))
        self.assertAlmostEqual(s['brier_skill_climatology'], 1 - s['brier'] / float(np.mean((clim - y) ** 2)))
        self.assertAlmostEqual(s['brier_skill_rate'], 1 - s['brier'] / float(np.mean((q - y) ** 2)))
        self.assertAlmostEqual(s['roc_auc'], roc_auc_score(y, p))
        self.assertAlmostEqual(s['pr_auc'], average_precision_score(y, p))
        self.assertAlmostEqual(s['no_skill_pr_auc'], y.mean())
        self.assertAlmostEqual(s['calibration_slope'], 0.5, delta=0.05)
        self.assertAlmostEqual(model_scores(y, q, None, None)['calibration_slope'], 1.0, delta=0.08)
        # one class, or a constant chance: rank and calibration scores undefined; no reference, no skill
        one = model_scores(np.zeros(5, int), np.full(5, 0.2), None, None)
        for key in ('roc_auc', 'pr_auc', 'calibration_slope', 'brier_skill_climatology', 'brier_skill_rate'):
            self.assertIsNone(one[key], key)
        self.assertIsNone(model_scores(y, np.full(len(y), 0.3), None, None)['calibration_slope'])
        # an exact zero that meets an event is clipped to 1e-6, so the log score stays finite
        hit = model_scores(np.array([1, 0]), np.array([0.0, 0.0]), None, None)
        self.assertAlmostEqual(hit['log_loss'], -math.log(1e-6) / 2 - math.log(1 - 1e-6) / 2)

    def test_when_scores_use_the_city_chance(self):
        d1, d2, d3, d4 = date(2024, 3, 1), date(2024, 3, 2), date(2024, 3, 3), date(2024, 3, 4)
        data = small_data([d1, d2, d3, d4], {d2: {1}}, unnamed=[d4])
        p = np.zeros(len(data.rows.y))
        set_chance(data, p, d1, [0.1, 0.1, 0.1])
        set_chance(data, p, d2, [0.5, 0.2, 0.0])
        set_chance(data, p, d3, [0.3, 0.0, 0.0])
        set_chance(data, p, d4, [0.05, 0.05, 0.0])
        city = np.array([1 - 0.9 ** 3, 1 - 0.5 * 0.8, 0.3, 1 - 0.95 ** 2])
        np.testing.assert_allclose(hazard_verdict.city_chance(data, p), city)
        out = when_scores(data, p)
        y = [0, 1, 0, 1]                                  # d4's record names no barangay but is an event day
        self.assertAlmostEqual(out['auc'], roc_auc_score(y, city))
        self.assertAlmostEqual(out['log_loss'], log_loss(y, city))
        self.assertEqual((out['days'], out['event_days']), (4, 2))

    def test_lift_ratio(self):
        day, quiet = date(2024, 9, 1), date(2024, 9, 2)
        data = small_data([day, quiet], {day: {1, 3, 7, 10}}, n=22)
        p = np.full(len(data.rows.y), 0.01)
        ranked = np.linspace(0.9, 0.05, 22)               # barangay 1 highest, 22 lowest
        set_chance(data, p, day, ranked)
        out = where_scores(data, p)
        # hits ranked 1, 3, 7 and 10: two of the four in the top 5
        self.assertAlmostEqual(out['lift'], (2 / 4) / (5 / 22))
        hit = np.isin(np.arange(1, 23), [1, 3, 7, 10]).astype(int)
        self.assertAlmostEqual(out['auc'], roc_auc_score(hit, ranked))
        self.assertEqual((out['auc_days'], out['hit_rows']), (1, 4))
        # an even spread ranks no barangay above another: ties share the top 5, so the lift is 1
        even = where_scores(data, np.full(len(data.rows.y), 0.02))
        self.assertAlmostEqual(even['lift'], 1.0)
        self.assertAlmostEqual(even['auc'], 0.5)
        # a day on which every barangay was hit has no AUC but still counts toward the lift
        full = small_data([day], {day: {1, 2, 3}})
        out = where_scores(full, np.array([0.3, 0.2, 0.1]))
        self.assertIsNone(out['auc'])
        self.assertEqual(out['auc_days'], 0)
        self.assertAlmostEqual(out['lift'], 1.0)         # 3 barangays: the top 5 holds them all


class EventTableTests(SimpleTestCase):
    def test_event_table_rows(self):
        d1, d2 = date(2023, 6, 10), date(2024, 7, 3)
        wet = {d1: 120.0, d1 - timedelta(days=1): 30.0, d2: 45.0}
        data = custom_data('Flood', wet=wet, storm_days=[d1],
                           events=[(1, STUDY_START), (1, d1), (2, d1), (None, d2)])
        rows = data.rows
        p = np.full(len(rows.y), 0.001)
        set_chance(data, p, d1, [0.5, 0.3, 0.05])
        set_chance(data, p, d1 - timedelta(days=1), [0.2, 0.1, 0.1])
        table = event_table(data, {NEW: p, CURRENT: np.full(len(rows.y), 0.001)})
        self.assertEqual([e['day'] for e in table], [STUDY_START.isoformat(), d1.isoformat(), d2.isoformat()])
        first, storm, unnamed = table
        self.assertEqual(storm['subtypes'], ['TOY'])
        self.assertEqual(storm['storm'], 'TOY')
        self.assertIsNone(unnamed['storm'])
        self.assertAlmostEqual(storm['rain_1day'], 120.0)     # the day's own rain, not the day before's 30 mm
        self.assertAlmostEqual(storm['rain_3day'], 150.0)
        self.assertEqual(storm['band'], '100-200 mm')
        self.assertEqual(unnamed['band'], 'under 50 mm')
        new = storm['models'][NEW]
        self.assertAlmostEqual(new['hit_chance'], 0.4)
        self.assertAlmostEqual(new['hit_chance_before'], 0.15)
        self.assertAlmostEqual(new['city_chance'], 1 - 0.5 * 0.7 * 0.95)
        # June 2023 month chances: barangay 1 >= 0.5 and 2 >= 0.3 are High, 3 about 0.08 is not
        self.assertEqual(new['high_barangays'], 2)
        self.assertEqual(storm['models'][CURRENT]['high_barangays'], 0)
        self.assertIsNone(unnamed['models'][NEW]['hit_chance'])
        self.assertIsNone(unnamed['models'][NEW]['hit_chance_before'])
        self.assertAlmostEqual(unnamed['models'][NEW]['city_chance'], 1 - 0.999 ** 3)
        self.assertAlmostEqual(first['models'][NEW]['hit_chance'], 0.001)
        self.assertIsNone(first['models'][NEW]['hit_chance_before'])       # the day before is no study day

    def test_storm_is_named_for_flood_only(self):
        d = date(2023, 6, 10)
        data = custom_data('Landslide', wet={d: 120.0}, events=[(1, d)])
        data.storms = StormDays({d: ('S1', 'TOY', 100.0)}, date(2020, 12, 1), date(2025, 12, 31))
        [event] = event_table(data, {NEW: np.full(len(data.rows.y), 0.01)})
        self.assertIsNone(event['storm'])


DAYS = [date(2025, 8, 1), date(2025, 8, 12), date(2025, 8, 18), date(2025, 9, 1), date(2025, 10, 7)]
HITS = {date(2025, 8, 12): {1}, date(2025, 8, 18): {2, 3}, date(2025, 10, 7): {1}}
CROSSES = {(NEW, CURRENT): (-0.001, -0.01, 0.002)}


def levels(high):
    return [{'cutoff': 0.25, 'false_alarms_per_event': high}, {'cutoff': 0.15, 'false_alarms_per_event': 9.0}]


def chances(data, on_hits):
    """0.1 on every row, except the hit rows of the days in `on_hits` ({day: value or [values]})."""
    p = np.full(len(data.rows.y), 0.1)
    for d, v in on_hits.items():
        set_chance(data, p, d, v, hit_only=True)
    return p


class RuleTests(SimpleTestCase):
    def setUp(self):
        self.data = small_data(DAYS, HITS)
        self.cur = chances(self.data, {})

    def test_rule_a_adopts_when_the_interval_is_below_zero(self):
        lost = chances(self.data, {date(2025, 8, 18): 0.05})       # rule (b) fails
        v = verdict(self.data, lost, self.cur, {(NEW, CURRENT): (-0.01, -0.02, -0.001)}, levels(9.0), levels(1.0))
        self.assertEqual((v['adopted'], v['rule'], v['leakage_checked']), (True, 'a', True))
        self.assertIn('lies wholly below zero (-0.02 to -0.001)', v['reasons'][0])
        # real row log-score differences are about 1e-4: three significant figures, never "-0.0000"
        tiny = verdict(self.data, lost, self.cur, {(NEW, CURRENT): (-2.2e-4, -3.456e-4, -1.234e-4)}, levels(9.0),
                       levels(1.0))
        self.assertIn('(-0.000346 to -0.000123)', tiny['reasons'][0])
        # below 1e-4 too: a plain decimal, never e-notation (the real landslide interval, -0.000155 to 8.81e-05)
        tinier = verdict(self.data, lost, self.cur, {(NEW, CURRENT): (-5e-5, -8.81e-5, -2.893e-5)}, levels(9.0),
                         levels(1.0))
        self.assertIn('(-0.0000881 to -0.0000289).', tinier['reasons'][0])
        crossing = verdict(self.data, lost, self.cur, {(NEW, CURRENT): (-2.4e-5, -0.0001553, 8.8146e-5)},
                           levels(9.0), levels(1.0))
        self.assertEqual(crossing['reasons'][0], 'The interval of the log-score difference does not lie wholly below '
                                                 'zero (-0.000155 to 0.0000881).')
        self.assertFalse(any('e-' in reason for reason in tinier['reasons'] + crossing['reasons']))
        touching = verdict(self.data, lost, self.cur, {(NEW, CURRENT): (-0.01, -0.02, 0.0)}, levels(1.0),
                           levels(1.0))
        self.assertEqual((touching['adopted'], touching['rule']), (False, None))
        self.assertIn('does not lie wholly below zero', touching['reasons'][0])

    def test_rule_b_needs_every_event_day_no_worse_and_most_better(self):
        better_two = chances(self.data, {date(2025, 8, 12): 0.2, date(2025, 8, 18): 0.3})   # 10-07 equal
        v = verdict(self.data, better_two, self.cur, CROSSES, levels(2.0), levels(2.5))
        self.assertEqual((v['adopted'], v['rule']), (True, 'b'))
        self.assertTrue(any('better one on 2' in r for r in v['reasons']), v['reasons'])
        better_one = chances(self.data, {date(2025, 8, 12): 0.2})
        v = verdict(self.data, better_one, self.cur, CROSSES, levels(2.0), levels(2.5))
        self.assertEqual((v['adopted'], v['rule']), (False, None))
        self.assertIn('It gave the hit barangays a better log score on only 1 of the 3 event days, not more than '
                      'half.', v['reasons'])
        # the mean log score, not the mean chance: 0.5 and 0.015 average 0.26 but score worse than 0.1 and 0.1
        uneven = chances(self.data, {date(2025, 8, 12): 0.2, date(2025, 8, 18): [0.5, 0.015],
                                     date(2025, 10, 7): 0.2})
        v = verdict(self.data, uneven, self.cur, CROSSES, levels(2.0), levels(2.5))
        self.assertFalse(v['adopted'])
        self.assertIn('It gave a lower chance to the hit barangays on 2025-08-18.', v['reasons'])
        # an event day whose records name no barangay has nothing to compare: left out, and said so
        unnamed = small_data(DAYS, HITS, unnamed=[date(2025, 9, 15)])
        v = verdict(unnamed, chances(unnamed, {date(2025, 8, 12): 0.2, date(2025, 8, 18): 0.3}),
                    chances(unnamed, {}), CROSSES, levels(2.0), levels(2.5))
        self.assertEqual((v['adopted'], v['rule']), (True, 'b'))
        self.assertTrue(any('1 event day' in r and 'no barangay' in r for r in v['reasons']), v['reasons'])
        nothing = small_data(DAYS, {}, unnamed=[date(2025, 9, 15)])
        v = verdict(nothing, chances(nothing, {}), chances(nothing, {}), CROSSES, levels(2.0), levels(2.5))
        self.assertFalse(v['adopted'])
        self.assertTrue(any('No event day' in r for r in v['reasons']), v['reasons'])

    def test_rule_b_refuses_extra_false_alarms_at_high(self):
        better_two = chances(self.data, {date(2025, 8, 12): 0.2, date(2025, 8, 18): 0.3})
        v = verdict(self.data, better_two, self.cur, CROSSES, levels(4.0), levels(2.5))
        self.assertFalse(v['adopted'])
        self.assertIn('It raised more false alarms per real event at High (4.0 against 2.5).', v['reasons'])
        self.assertTrue(verdict(self.data, better_two, self.cur, CROSSES, levels(2.5), levels(2.5))['adopted'])
        undefined = verdict(self.data, better_two, self.cur, CROSSES, levels(None), levels(2.5))
        self.assertFalse(undefined['adopted'])
        self.assertTrue(any('undefined' in r for r in undefined['reasons']), undefined['reasons'])

    def test_rule_b_needs_the_high_row_of_the_level_tables(self):
        better_two = chances(self.data, {date(2025, 8, 12): 0.2, date(2025, 8, 18): 0.3})
        moderate_only = [{'cutoff': 0.15, 'false_alarms_per_event': 1.0}]
        with self.assertRaisesRegex(ValueError, '0.25'):
            verdict(self.data, better_two, self.cur, CROSSES, moderate_only, levels(2.5))

    def test_not_adopted_names_the_day_it_lost(self):
        lost = chances(self.data, {date(2025, 8, 12): 0.2, date(2025, 8, 18): 0.05, date(2025, 10, 7): 0.2})
        v = verdict(self.data, lost, self.cur, CROSSES, levels(1.0), levels(2.5))
        self.assertEqual((v['adopted'], v['rule']), (False, None))
        self.assertIn('2025-08-18', ' '.join(v['reasons']))
        self.assertNotIn('2025-08-12', ' '.join(v['reasons']))


class _Unavailable:
    name = 'never'

    def fit(self, data, train):
        raise CannotEvaluate('This baseline cannot be fitted.')

    def predict(self, fitted, data, days):
        raise AssertionError('not reached')


class EvaluateTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.data = toy_flood()
        with mock.patch.object(hazard_verdict, 'baselines',
                               lambda h: hazard_tests.baselines(h) + [_Unavailable()]):
            cls.result = evaluate(cls.data, reps=20)

    def test_evaluate_on_toy_flood_has_every_field_the_card_reads(self):
        r = self.result
        self.assertEqual(json.loads(json.dumps(r, allow_nan=False)), r)      # strict JSON, nothing lost
        self.assertEqual(set(r), {'tests', 'verdict', 'in_use'})
        self.assertEqual(set(r['tests']), {'loso', 'yearly', 'events', 'outside'})
        loso = r['tests']['loso']
        models = loso['models']
        self.assertEqual(list(models), [NEW, CURRENT, *BASELINES['Flood'], 'never'])
        self.assertEqual(models['never'], {'unavailable': 'This baseline cannot be fitted.'})
        for name in [NEW, CURRENT, *BASELINES['Flood']]:
            m = models[name]
            self.assertLessEqual({'log_loss', 'brier', 'brier_skill_climatology', 'brier_skill_rate', 'pr_auc',
                                  'no_skill_pr_auc', 'roc_auc', 'calibration_slope'}, set(m['scores']), name)
            low, high = m['log_loss_interval']
            self.assertLessEqual(low, high)
            self.assertLessEqual({'auc', 'log_loss'}, set(m['when']), name)
            self.assertLessEqual({'auc', 'lift'}, set(m['where']), name)
            self.assertEqual([t['cutoff'] for t in m['levels']], [0.25, 0.15])
            self.assertEqual([y['year'] for y in m['per_year']], [2021, 2022, 2023, 2024, 2025])
            self.assertEqual(sum(y['observed'] for y in m['per_year']), int(self.data.rows.y.sum()))
        self.assertAlmostEqual(models['climatology']['scores']['brier_skill_climatology'], 0.0)
        self.assertAlmostEqual(models['rate']['scores']['brier_skill_rate'], 0.0)
        expected = {f'{NEW} - {CURRENT}'} | {f'{a} - {b}' for a in (NEW, CURRENT) for b in BASELINES['Flood']}
        self.assertEqual(set(loso['differences']), expected)
        diff = loso['differences'][f'{NEW} - {CURRENT}']
        self.assertAlmostEqual(diff['difference'],
                               models[NEW]['scores']['log_loss'] - models[CURRENT]['scores']['log_loss'])
        self.assertLessEqual(diff['low'], diff['high'])
        self.assertEqual([round(b['false_alarms_per_event'], 2) for b in loso['breakeven']], [3.0, 5.67])
        self.assertEqual(loso['event_days'], int(self.data.city_y.sum()))
        self.assertEqual(set(r['tests']['yearly']), {NEW, CURRENT})
        for folds in r['tests']['yearly'].values():
            self.assertEqual([f['test_year'] for f in folds], [2023, 2024, 2025])
            for f in folds:
                self.assertGreater(f['test_event_days'], 0)
                self.assertIn('log_loss', f['scores'])
        events = r['tests']['events']
        self.assertEqual(len(events), int(self.data.city_y.sum()))
        self.assertEqual(set(events[0]), {'day', 'subtypes', 'storm', 'rain_1day', 'rain_3day', 'band', 'models'})
        self.assertEqual(set(events[0]['models']), {NEW, CURRENT})
        self.assertEqual(set(events[0]['models'][NEW]),
                         {'hit_chance', 'hit_chance_before', 'city_chance', 'high_barangays'})
        self.assertIsNone(r['tests']['outside'])
        v = r['verdict']
        self.assertEqual(set(v), {'adopted', 'rule', 'reasons', 'leakage_checked'})
        self.assertTrue(v['leakage_checked'])
        self.assertTrue(v['reasons'])
        self.assertEqual(r['in_use'], NEW if v['adopted'] else CURRENT)

    def test_a_contender_that_cannot_be_fitted_stops_the_evaluation(self):
        for error in (CannotEvaluate('no event'), FitFailed('no convergence')):
            with mock.patch.object(hazard_verdict.TwoPartContender, 'fit', side_effect=error):
                with self.assertRaises(type(error)):
                    evaluate(self.data, reps=5)


def _numeric_information(design, y, beta, step=1e-5):
    """Minus the Hessian of the Bernoulli log-likelihood, by central differences of its gradient."""
    def grad(b):
        return design.T @ (y - 1 / (1 + np.exp(-(design @ b))))
    cols = []
    for j in range(len(beta)):
        e = np.zeros(len(beta))
        e[j] = step
        cols.append((grad(beta + e) - grad(beta - e)) / (2 * step))
    return -np.column_stack(cols)


class WaldTests(SimpleTestCase):
    def test_a_variance_that_is_not_positive_gives_no_interval_and_no_warning(self):
        x = np.linspace(-2, 2, 50)
        when = WhenFit(('a', 'b'), np.array([0.5, 0.2]), {'geoalert': -1.0})
        for diagonal in ([1.0, 4.0, -1.0], [1.0, 4.0, np.nan]):
            inverse = mock.patch.object(hazard_verdict.np.linalg, 'inv', return_value=np.diag(diagonal))
            with inverse, warnings.catch_warnings():
                warnings.simplefilter('error')
                slopes = wald_slopes(when, np.column_stack([x, 3 * x + 1]), 'geoalert')
            self.assertAlmostEqual(slopes['a']['low'], 0.5 - 1.959964 * 2, places=5)
            self.assertAlmostEqual(slopes['a']['high'], 0.5 + 1.959964 * 2, places=5)
            self.assertEqual(slopes['b'], {'coef': 0.2, 'low': None, 'high': None})


class OutsideTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.data, _ = toy_landslide()
        cls.current = LogisticContender('Landslide').fit(cls.data, np.ones(len(cls.data.city_day), bool))

    def test_outside_test_scores_catalogue_days_by_auc_only(self):
        data, current = self.data, self.current
        out = outside_test(data, current)
        self.assertEqual(set(out), {'current', 'catalogue_to_geoalert', 'geoalert_to_catalogue'})
        self.assertEqual(set(out['current']), {'auc', 'observed', 'expected'})      # no log score
        # independently: each catalogue day's rows from the city rain and the barangays' terrain
        terrain, _, _ = toy_inputs(n_barangays=3, start=date(2007, 1, 1), seed=1)
        names = current['features'][5:]
        city = []
        for d in data.extra_day.astype(object):
            w = rain_windows(data.rain, d)
            X = [[w[k] for k in ('r0', 'r1', 'r3', 'r7', 'r14')] + [terrain[b][f] for f in names] for b in (1, 2, 3)]
            city.append(1 - np.prod(1 - score_logistic(current, np.array(X))))
        city = np.array(city)
        self.assertEqual(out['current']['observed'], int(data.extra_y.sum()))
        self.assertAlmostEqual(out['current']['expected'], city.sum(), places=6)
        self.assertAlmostEqual(out['current']['auc'], _auc(data.extra_y, city))
        # the new "when" model across eras, with each training era's slopes and Wald intervals
        for key, X, y, era, X_test, y_test in (
                ('catalogue_to_geoalert', data.extra_X, data.extra_y, 'catalogue', data.city_X, data.city_y),
                ('geoalert_to_catalogue', data.city_X, data.city_y, 'geoalert', data.extra_X, data.extra_y)):
            self.assertEqual(set(out[key]), {'auc', 'slopes'})
            when = fit_when(X, y, era=np.array([era] * len(y)), features=FEATURES['Landslide'])
            self.assertAlmostEqual(out[key]['auc'], _auc(y_test, when.chance(X_test, era)))
            slopes = out[key]['slopes']
            self.assertEqual(list(slopes), list(FEATURES['Landslide']))
            design = np.column_stack([np.ones(len(y)), X])
            beta = np.r_[when.intercepts[era], when.coef]
            se = np.sqrt(np.diag(np.linalg.inv(_numeric_information(design, y, beta))))[1:]
            for j, f in enumerate(FEATURES['Landslide']):
                self.assertAlmostEqual(slopes[f]['coef'], when.coef[j])
                self.assertAlmostEqual(slopes[f]['low'], when.coef[j] - 1.959964 * se[j], places=4)
                self.assertAlmostEqual(slopes[f]['high'], when.coef[j] + 1.959964 * se[j], places=4)
        self.assertGreater(out['current']['observed'], 0)
        # flood has no outside test; landslide without a catalogue era says why
        self.assertIsNone(outside_test(toy_flood(), {}))
        plain = custom_data('Landslide', events=[(1, date(2022, 3, 1))])
        self.assertIn('unavailable', outside_test(plain, {}))

    def test_evaluate_on_toy_landslide_adds_the_outside_test(self):
        r = evaluate(self.data, reps=10)
        self.assertEqual(json.loads(json.dumps(r, allow_nan=False)), r)
        self.assertEqual(r['tests']['outside'], outside_test(self.data, self.current))
        models = r['tests']['loso']['models']
        self.assertEqual(list(models), [NEW, CURRENT, *BASELINES['Landslide']])
        # the gated landslide rules are scored like every other model (an exact 0 is clipped: ScoreTests)
        for name in ('return_level', 'p95_7day'):
            self.assertTrue(math.isfinite(models[name]['scores']['log_loss']), name)
            self.assertTrue(math.isfinite(models[name]['when']['log_loss']), name)
        self.assertEqual(set(r['tests']['events'][0]['models']), {NEW, CURRENT})
        self.assertIsNone(r['tests']['events'][0]['storm'])                # landslide has no storm flag
