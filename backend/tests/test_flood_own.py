"""
Flood's own-data mode (automatic retraining plan, Task 4): the floor to try,
the held-back wet season, the folds by barangay, and `run(mode='own')`, which
keeps the live map's level outside the area GeoAlert's records cover, scores
the held-back spots on the map that would ship, and writes no survey credit
and no coordinate. Survey mode is checked against a golden made before the
own mode was added. A small synthetic city, no database.
"""
import copy
import json
import re
import subprocess
import sys
from datetime import date
from pathlib import Path
from unittest import mock

import numpy as np
from django.conf import settings
from django.test import SimpleTestCase

from apps.history import flood_own, flood_run
from apps.history import flood_rules as rules
from apps.history import flood_training as tr
from apps.history.flood_features import FloodFeatures
from apps.history.flood_own import compare, floor, own_folds, season_split, train_own
from apps.history.flood_purok import BASIS_GEOALERT
from apps.history.flood_run import FROM_NOAH_NOTE, LIMITS_OWN, OUTSIDE_OWN, UNLIKE_OWN, run
from tests.test_flood_run import PRONE, block, inputs_for, synthetic_city, tests_at

GOLDEN = Path(__file__).with_name('fixtures') / 'flood_survey_golden.json'
OWN_RULE = ("Convex hull of GeoAlert's located flood spots before the held-back season, buffered 300 m, clipped to "
            'the city')
GATE2_OWN = 'Held-back wet season spots in Red or Orange'
OUTSIDE_OWN_TEXT = "Outside the area GeoAlert's records cover"
# The domain covers the synthetic city's columns 0-2 (puroks 1x0-1x2); columns 3-4 lie outside it
OUTSIDE_LIVE_RED, OUTSIDE_NOT_ASSESSED, OUTSIDE_NO_LIVE, OUTSIDE_BLANK = 104, 109, 103, 113
OUTSIDE_RED = [100 + k for k in range(20) if k % 5 >= 3
               and 100 + k not in (OUTSIDE_NOT_ASSESSED, OUTSIDE_NO_LIVE, OUTSIDE_BLANK)]
UNLIKE_PUROK = 107  # inside the domain; its buildings are made out of range


def brgy(pid):
    return f'Brgy {pid}'


def spot(i, pid, when, lon, lat, inputs=None):
    s = {'id': f'r{i}', 'when': when, 'lon': lon, 'lat': lat, 'purok_id': pid, 'barangay': brgy(pid)}
    if inputs is not None:
        s.update(positive=True, inputs=inputs)
    return s


def own_city(seed=0):
    """
    The synthetic city with one barangay per purok, and GeoAlert's own flood
    spots before the 2026 wet season: the survey's 40 flooded spots (puroks
    100, 101, 110, 111) plus 6 in purok 105, so they are in 5 barangays.
    """
    features, spots, city = synthetic_city(seed)
    buildings = dict(features.buildings)
    buildings['barangay'] = np.array([brgy(p) for p in features.membership[1]])  # membership[0] is 0..n-1 in order
    features = FloodFeatures(buildings=buildings, membership=features.membership, areas=features.areas,
                             meta=features.meta)
    rng = np.random.default_rng(seed + 1)
    train = [spot(i, s['purok_id'], '2025-08-10T14:00:00+08:00', s['lon'], s['lat'], s['inputs'])
             for i, s in enumerate(s for s in spots if s['positive'])]
    x0, y0 = block(5)
    train += [spot(100 + i, 105, '2025-09-01T09:00:00+08:00', round(x0 + 0.0002 + i * 0.0002, 7),
                   round(y0 + 0.0003, 7), inputs_for(0, rng)) for i in range(6)]
    return features, train, city


def held_at(pids):
    out = []
    for i, pid in enumerate(pids):
        x0, y0 = block(pid - 100)
        out.append(spot(500 + i, pid, f'2026-07-{10 + i:02d}T10:00:00+08:00', round(x0 + 0.0007, 7),
                        round(y0 + 0.0007, 7)))
    return out


def live_map():
    """The map in use: every purok Red, except one not assessed, one missing, and one row with neither."""
    live = {100 + k: {'level': 'Red', 'score': 0.9, 'not_assessed_reason': None} for k in range(20)}
    live[OUTSIDE_NOT_ASSESSED] = {'level': None, 'score': None, 'not_assessed_reason': tr.NO_NOAH}
    live[OUTSIDE_BLANK] = {'level': None, 'score': None, 'not_assessed_reason': None}
    del live[OUTSIDE_NO_LIVE]
    return live


class FloodOwnRulesTests(SimpleTestCase):
    def test_floor(self):
        def spots(n, barangays, blank=0):
            return ([{'barangay': f'B{i % barangays}'} for i in range(n - blank)]
                    + [{'barangay': name} for name in ([''] * (blank - blank // 2) + [None] * (blank // 2))])

        self.assertEqual(floor(spots(99, 5)), {'n': 99, 'barangays': 5, 'enough': False})
        self.assertEqual(floor(spots(100, 4)), {'n': 100, 'barangays': 4, 'enough': False})
        self.assertEqual(floor(spots(100, 5)), {'n': 100, 'barangays': 5, 'enough': True})
        # Empty barangay names don't count as barangays
        self.assertEqual(floor(spots(100, 4, blank=6)), {'n': 100, 'barangays': 4, 'enough': False})

    def test_season_split(self):
        whens = {
            'train': ['2026-05-31T23:30:00+08:00', '2025-12-31T10:00:00+08:00'],
            'held': ['2026-06-01T00:10:00+08:00', '2026-05-31T16:10:00+00:00',  # 00:10 on 1 June in Manila
                     '2026-12-31T23:59:00+08:00', '2026-12-31'],
            'neither': ['2027-01-02T08:00:00+08:00', '2026-12-31T16:30:00+00:00'],  # 00:30 on 1 January in Manila
        }
        spots = [{'id': f'{kind}-{i}', 'when': w} for kind, ws in whens.items() for i, w in enumerate(ws)]
        train, held, season = season_split(spots[::-1], date(2027, 1, 5))
        self.assertEqual(season, 2026)
        self.assertEqual(sorted(s['id'] for s in train), ['train-0', 'train-1'])
        self.assertEqual(sorted(s['id'] for s in held), ['held-0', 'held-1', 'held-2', 'held-3'])

    def test_own_folds_are_balanced_and_stable(self):
        counts = {'A': 5, 'B': 4, 'C': 3, 'D': 2, 'E': 1, 'F': 1}
        spots = [{'barangay': name} for name, n in counts.items() for _ in range(n)]
        expected = {'A': 0, 'B': 1, 'C': 2, 'D': 3, 'E': 4, 'F': 4}
        self.assertEqual(own_folds(spots), expected)
        for seed in range(3):
            shuffled = list(spots)
            np.random.default_rng(seed).shuffle(shuffled)
            self.assertEqual(own_folds(shuffled), expected)

    def test_own_folds_with_few_barangays(self):
        spots = [{'barangay': name} for name in ('A', 'A', 'B', 'C', 'C', 'C', '', None)]
        folds = own_folds(spots)
        self.assertEqual(folds, {'C': 0, 'A': 1, 'B': 2})
        self.assertEqual(len(set(folds.values())), 3)

    def test_compare(self):
        self.assertEqual(compare(['Red', 'Green', 'Orange'], ['Green', 'Green', 'Red']), (2, 1))
        self.assertEqual(compare([None, 'Green'], [None, None]), (0, 0))

    def test_spots_digest_ignores_order_and_sees_each_field(self):
        _, train, _ = own_city()
        base = flood_run._spots_digest(train)
        self.assertEqual(flood_run._spots_digest(train[::-1]), base)
        first = train[0]
        for changed in ({**first, 'id': 'other'}, {**first, 'when': '2025-08-11T14:00:00+08:00'},
                        {**first, 'purok_id': 101}, {**first, 'inputs': {**first['inputs'], 'built_share': 0.123}}):
            self.assertNotEqual(flood_run._spots_digest([changed] + train[1:]), base, changed)

    def test_own_acceptance_sentences(self):
        # Controller ruling RA: own mode names the held-back season and GeoAlert's area, never the survey
        self.assertEqual(rules.acceptance(0.01, [], 0.4, own=True),
                         (False, ['No held-back wet season spot was available to test it on.']))
        ok, why = rules.acceptance(0.01, ['Red', None, 'Green', 'Green'], 0.6, own=True)
        self.assertFalse(ok)
        self.assertEqual(why, [
            'Only 1 of the 4 held-back wet season spots fell in a Red or Orange area (3 needed).',
            "Red and Orange would cover 60% of the buildings in the area GeoAlert's records cover, more than half.",
        ])
        self.assertEqual(rules.acceptance(0.01, ['Red', 'Orange', 'Green', 'Red'], 0.4, own=True), (True, []))
        # Gate 1's sentence is the same in both modes
        for gain in (-0.01, float('nan')):
            self.assertEqual(rules.acceptance(gain, ['Red'], 0.4, own=True), rules.acceptance(gain, ['Red'], 0.4))

    def test_survey_acceptance_sentences_unchanged(self):
        ok, why = rules.acceptance(-0.012, ['Red', None, 'Green', 'Green'], 0.6)
        self.assertEqual(why, [
            "It did not clearly beat UP NOAH's map on its own: the lower end of its AUC gain was -0.012, not above "
            'zero.',
            'Only 1 of the 4 GeoAlert Mananga flood points fell in a Red or Orange area (3 needed).',
            "Red and Orange would cover 60% of the floodplain's buildings, more than half.",
        ])
        self.assertEqual(rules.acceptance(0.01, [], 0.4)[1],
                         ['No GeoAlert Mananga flood point was available to test it on.'])


class FloodOwnRunTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.features, cls.train, cls.city = own_city()
        cls.held = held_at([OUTSIDE_LIVE_RED, OUTSIDE_NO_LIVE, 100])
        b_idx, p_ids = cls.features.membership
        unlike = np.zeros(len(cls.features.buildings['lon']), bool)
        unlike[b_idx[p_ids == UNLIKE_PUROK]] = True
        real = tr.in_range
        with mock.patch.object(tr, 'in_range', side_effect=lambda X, X_b: real(X, X_b) & ~unlike):
            cls.model, cls.report = train_own(cls.features, cls.train, cls.held, cls.city, live_map(), season=2026,
                                              fingerprint='synthetic-own', reps=40, stability_reps=4,
                                              log=lambda msg: None, outside_source='noah')

    def test_training_spots_span_five_barangays(self):
        self.assertEqual(len({s['barangay'] for s in self.train}), 5)
        self.assertEqual(self.report['own_spots'], len(self.train))

    def test_outside_puroks_keep_the_live_level(self):
        areas = self.model['areas']
        red = areas[OUTSIDE_LIVE_RED]
        self.assertEqual((red['level'], red['score'], red['not_assessed_reason'], red['note']),
                         ('Red', 0.9, None, FROM_NOAH_NOTE))
        not_assessed = areas[OUTSIDE_NOT_ASSESSED]
        self.assertEqual((not_assessed['level'], not_assessed['score'], not_assessed['not_assessed_reason']),
                         (None, None, tr.NO_NOAH))
        self.assertIsNone(not_assessed.get('note'))
        # No flood model was live there (ruling RB): no level, and the own mode's outside reason
        self.assertEqual(OUTSIDE_OWN, OUTSIDE_OWN_TEXT)
        for pid in (OUTSIDE_NO_LIVE, OUTSIDE_BLANK):  # missing, and a live row with neither a level nor a reason
            a = areas[pid]
            self.assertEqual((a['level'], a['not_assessed_reason']), (None, OUTSIDE_OWN), pid)
            self.assertIsNone(a.get('note'), pid)
        for k in range(20):
            a = areas[100 + k]
            if k % 5 < 3:  # inside the domain the new model's levels stand, never the live map's
                self.assertIsNone(a.get('note'), 100 + k)
                self.assertNotEqual(a['score'], 0.9, 100 + k)
            elif 100 + k in OUTSIDE_RED:
                self.assertEqual((a['level'], a['note']), ('Red', FROM_NOAH_NOTE), 100 + k)
            self.assertTrue((a['level'] in ('Red', 'Orange', 'Green')) != bool(a['not_assessed_reason']), a)

    def test_own_gate_three_names_the_area_geoalert_covers(self):
        gate = self.report['acceptance']['gates'][2]
        share = gate['detail'].split('%')[0]
        self.assertEqual(gate['detail'], f"{share}% of the buildings in the area GeoAlert's records cover")

    def test_a_failed_own_fit_never_names_the_survey(self):
        acceptance = self.report['acceptance']
        self.assertFalse(acceptance['adopted'])
        hits = acceptance['gates'][1]['detail'].split(' of ')[0]
        self.assertIn(f'Only {hits} of the 3 held-back wet season spots fell in a Red or Orange area (3 needed).',
                      acceptance['reasons'])
        text = json.dumps(self.model) + json.dumps(self.report)
        self.assertNotIn('Mananga', text)
        self.assertNotIn('surveyed', text)

    def test_unlike_ground_has_the_own_reason(self):
        self.assertEqual(self.model['areas'][UNLIKE_PUROK]['not_assessed_reason'], UNLIKE_OWN)
        self.assertNotIn(tr.UNLIKE, json.dumps(self.model))

    def test_held_spots_scored_on_the_composed_map(self):
        gate = self.report['acceptance']['gates'][1]
        self.assertEqual(gate['gate'], GATE2_OWN)
        levels = [self.model['areas'][s['purok_id']]['level'] for s in self.held]
        self.assertEqual(levels[:2], ['Red', None])  # outside the domain: the live Red, and no level
        hits = sum(1 for lv in levels if lv in ('Red', 'Orange'))
        self.assertEqual(gate['detail'], f'{hits} of 3')
        test = self.report['temporal_test']
        self.assertEqual(test['season'], 2026)
        self.assertEqual([p['level'] for p in test['held_back']], levels)
        self.assertEqual(test['held_back'][0], {'day': '2026-07-10', 'barangay': brgy(OUTSIDE_LIVE_RED),
                                                'purok_id': OUTSIDE_LIVE_RED, 'level': 'Red'})
        self.assertIsNone(test['eosrs'])  # no Tino map given: nothing to show

    def test_a_failed_fit_still_ships_the_composed_map(self):
        # The spot with no level means at most 2 of the 3 held spots are hits: gate 2 fails (3 needed)
        self.assertFalse(self.report['acceptance']['gates'][1]['passed'])
        self.assertFalse(self.report['acceptance']['adopted'])
        self.assertEqual(self.model['source'], 'geoalert')
        self.assertTrue(self.model['version'].startswith(self.model['chosen'] + '@'))
        self.assertNotIn('fallback', self.report)
        self.assertEqual(self.model['cutoffs'], self.report['cutoffs'])
        self.assertEqual(self.model['areas'][OUTSIDE_LIVE_RED]['level'], 'Red')

    def test_own_report_has_no_survey_or_coordinates(self):
        model, report = self.model, self.report
        self.assertEqual((model['source'], report['source']), ('geoalert', 'geoalert'))
        self.assertEqual(report['basis'], BASIS_GEOALERT)
        self.assertEqual(report['version'], model['version'])
        self.assertNotIn('survey_spots', report)
        self.assertNotIn('mananga_points', report['temporal_test'])
        self.assertNotIn('elsewhere', report['temporal_test'])
        self.assertFalse([c for c in report['credits'] if 'Paringit' in c])
        self.assertEqual(report['limits'], LIMITS_OWN)
        self.assertEqual(model['domain'], {'buffer_m': 300, 'rule': OWN_RULE})
        text = json.dumps(model) + json.dumps(report)
        self.assertNotIn('POLYGON', text)
        for s in self.train + self.held:
            self.assertNotIn(f'{s["lon"]:.4f}', text)
            self.assertNotIn(f'{s["lat"]:.4f}', text)


class NoScikitLearnOnTheWebTests(SimpleTestCase):
    """
    Final review P2: the readiness panel (a public request) imports flood_own;
    scikit-learn (flood_run's) must load only when a model is trained.
    """

    def test_importing_flood_own_leaves_sklearn_out(self):
        code = ('import sys, django; django.setup(); before = "sklearn" in sys.modules; '
                'import apps.history.flood_own; print(before, "sklearn" in sys.modules)')
        done = subprocess.run([sys.executable, '-c', code], cwd=settings.BASE_DIR, capture_output=True, text=True,
                              timeout=300)
        self.assertEqual(done.returncode, 0, done.stderr[-2000:])
        self.assertEqual(done.stdout.split()[-2:], ['False', 'False'])

    def test_flood_own_holds_no_flood_run_reference(self):
        self.assertFalse(hasattr(flood_own, 'run'))
        for name, value in vars(flood_own).items():
            self.assertIsNot(value, flood_run, name)
            self.assertNotEqual(getattr(value, '__module__', None), 'apps.history.flood_run', name)


class FloodOwnPassTests(SimpleTestCase):
    """The held-back season in the low ground by the river: the own fit can pass every check."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.features, cls.train, cls.city = own_city()
        cls.held = held_at([100 + k for k in sorted(PRONE)])
        cls.seen = {}
        real_run = flood_run.run  # train_own imports it when it runs (final review P2)

        def spy(features, spots, city, load_tests, **kwargs):
            report = {}

            def checked():
                cls.seen.update(choice='choice' in report, cutoffs='cutoffs' in report)
                return load_tests()

            return real_run(features, spots, city, checked, report=report, **kwargs)

        common = dict(season=2026, fingerprint='synthetic-own', reps=40, stability_reps=4, log=lambda msg: None)
        with mock.patch.object(flood_run, 'run', spy):
            cls.model, cls.report = train_own(cls.features, cls.train, cls.held, cls.city, live_map(),
                                              outside_source='geoalert', **common)
        cls.no_live_model, cls.no_live_report = train_own(cls.features, cls.train, cls.held, cls.city, {}, **common)

    def test_tests_load_only_after_choice_and_cutoffs(self):
        self.assertEqual(self.seen, {'choice': True, 'cutoffs': True})

    def test_an_own_fit_can_pass_every_check(self):
        acceptance = self.report['acceptance']
        self.assertTrue(acceptance['adopted'], acceptance)
        self.assertEqual([g['passed'] for g in acceptance['gates']], [True] * 4)
        self.assertEqual(acceptance['gates'][1]['detail'], '4 of 4')
        self.assertEqual(self.model['source'], 'geoalert')
        self.assertTrue(self.model['version'].startswith(self.model['chosen'] + '@'))
        self.assertNotIn('fallback', self.report)
        for k in PRONE:
            self.assertIn(self.model['areas'][100 + k]['level'], ('Red', 'Orange'))

    def test_a_geoalert_live_map_keeps_the_note(self):
        # Ruling RC: an own fit's rows outside its domain are UP NOAH's, so the note carries over
        for pid in OUTSIDE_RED:
            self.assertEqual((self.model['areas'][pid]['level'], self.model['areas'][pid]['note']),
                             ('Red', FROM_NOAH_NOTE), pid)

    def test_with_no_live_model_outside_puroks_are_not_assessed(self):
        for k in range(20):
            a = self.no_live_model['areas'][100 + k]
            if k % 5 >= 3:
                self.assertEqual((a['level'], a['not_assessed_reason']), (None, OUTSIDE_OWN), 100 + k)
            self.assertIsNone(a.get('note'), 100 + k)
            if k % 5 < 3:  # inside the domain nothing depends on the live map
                self.assertEqual(a, self.model['areas'][100 + k])

    def test_version_follows_the_live_rows_it_copies(self):
        # The log keeps one row per area and version: other copied rows are other classes, so another version
        self.assertNotEqual(self.no_live_model['version'], self.model['version'])
        self.assertEqual(self.no_live_model['chosen'], self.model['chosen'])


class FloodOwnSourceAndVersionTests(SimpleTestCase):
    """
    Ruling RC: the NOAH note only when the live map's source is 'noah' or 'geoalert'. And the version: the flood
    prediction log is insert-only and keyed by version, so any change that can change the classes needs another.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        features, train, city = own_city()
        held = held_at([100 + k for k in sorted(PRONE)])
        first = train[0]
        one_spot_changed = [{**first, 'inputs': {**first['inputs'], 'depression_m': first['inputs']['depression_m']
                                                 + 0.001}}] + train[1:]
        other_live_rows = {**live_map(), OUTSIDE_LIVE_RED: {'level': 'Orange', 'score': 0.5,
                                                            'not_assessed_reason': None}}
        runs = {'model': (train, live_map(), 'model'), None: (train, live_map(), None),
                'one spot changed': (one_spot_changed, live_map(), 'model'),
                'other live rows': (train, other_live_rows, 'model')}
        cls.fits = {name: train_own(features, spots, held, city, live, season=2026, fingerprint='synthetic-own',
                                    reps=40, stability_reps=4, log=lambda msg: None, outside_source=source)[0]
                    for name, (spots, live, source) in runs.items()}

    def test_no_note_from_a_survey_model_or_an_unknown_source(self):
        for source in ('model', None):
            model = self.fits[source]
            for pid in OUTSIDE_RED:  # the live level is still copied, without claiming it is UP NOAH's
                self.assertEqual(model['areas'][pid]['level'], 'Red', (source, pid))
            self.assertFalse([pid for pid, a in model['areas'].items() if a.get('note')], source)

    def test_version_follows_the_live_source(self):
        self.assertNotEqual(self.fits['model']['version'], self.fits[None]['version'])

    def test_version_follows_the_training_spots(self):
        # Same fingerprint, folds, live rows and source: only the changed spot can tell the two versions apart
        changed, base = self.fits['one spot changed'], self.fits['model']
        self.assertEqual(changed['chosen'], base['chosen'])
        self.assertNotEqual(changed['version'], base['version'])

    def test_version_follows_the_live_rows_alone(self):
        changed, base = self.fits['other live rows'], self.fits['model']
        self.assertEqual(changed['areas'][OUTSIDE_LIVE_RED]['level'], 'Orange')
        self.assertNotEqual(changed['version'], base['version'])


class FloodSurveyModeTests(SimpleTestCase):
    def test_survey_mode_unchanged(self):
        # The golden was made with flood_run.py as it was before the own mode (see the Task 4 report)
        golden = json.loads(GOLDEN.read_text(encoding='utf-8'))
        features, spots, city = synthetic_city()
        n = len(features.buildings['lon'])
        prone = np.isin(features.membership[1], [100 + k for k in PRONE])
        eosrs = np.zeros(n, bool)
        eosrs[features.membership[0][prone]] = True
        records = {'tino': ['Lawaan III'], 'any': ['Lawaan III', 'Biasong']}
        scenarios = {'adopted': ('model', tests_at([0, 1, 10, 11])), 'fallback': ('noah', tests_at([6, 6, 6, 6]))}
        for name, (source, points) in scenarios.items():
            tests = {'geoalert_points': points, 'eosrs_flagged': eosrs, 'barangay_records': records}
            model, report = run(features, spots, city, lambda: tests, log=lambda msg: None, fingerprint='synthetic',
                                reps=40, stability_reps=4, built_at='2026-11-24T00:00:00+08:00')
            self.assertEqual(model['source'], source)
            self.assertIn('survey_spots', report)
            got = json.loads(json.dumps({'areas': model['areas'], 'acceptance': report['acceptance'],
                                         'candidates': report['candidates']}))
            assert_survey_same(self, got, golden[name], name)

    def test_survey_comparison_allows_last_digit_noise_only(self):
        # CI on Linux (2026-11-24): a candidate metric one unit off in its 4th decimal failed the golden,
        # because several sit exactly on a 3-decimal halfway point (0.8465, -0.2175)
        golden = json.loads(GOLDEN.read_text(encoding='utf-8'))['adopted']
        for bump in (0.0001, -0.0001):
            noisy = copy.deepcopy(golden)
            for c in noisy['candidates']:
                for k, v in c.items():
                    if is_number(v):
                        c[k] = round(v + bump, 4)
            for a in noisy['areas'].values():
                if is_number(a.get('score')):
                    a['score'] += bump / 100
            assert_survey_same(self, noisy, golden, f'noise {bump}')
        # A real change still fails: a level, or a metric far off
        changed = copy.deepcopy(golden)
        pid = next(p for p, a in changed['areas'].items() if a.get('level') == 'Orange')
        changed['areas'][pid]['level'] = 'Red'
        with self.assertRaises(AssertionError):
            assert_survey_same(self, changed, golden, 'level changed')
        far = copy.deepcopy(golden)
        far['candidates'][0]['auc'] = far['candidates'][0]['auc'] - 0.05
        with self.assertRaises(AssertionError):
            assert_survey_same(self, far, golden, 'metric far off')

    def test_survey_comparison_range_checks_platform_dependent_fits(self):
        # CI on Linux (2026-11-24): xgboost's Boyce was 0.3234 against the Windows golden's 0.2866, with the
        # same library versions; the shipped map and every other number matched
        golden = json.loads(GOLDEN.read_text(encoding='utf-8'))['adopted']
        moved = copy.deepcopy(golden)
        for c in moved['candidates']:
            if c['name'] in ('xgboost', 'neural_network'):
                c['boyce'] = c['boyce'] + 0.04
                c['auc'] = c['auc'] - 0.02
        assert_survey_same(self, moved, golden, 'platform-dependent fits moved')
        broken = copy.deepcopy(golden)
        next(c for c in broken['candidates'] if c['name'] == 'neural_network')['auc'] = 1.5
        with self.assertRaises(AssertionError):
            assert_survey_same(self, broken, golden, 'AUC out of range')
        missing = copy.deepcopy(golden)
        del next(c for c in missing['candidates'] if c['name'] == 'xgboost')['boyce']
        with self.assertRaises(AssertionError):
            assert_survey_same(self, missing, golden, 'metric missing')


def is_number(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


# The golden was made on Windows and CI runs on Linux, where a fit's last digits can differ. Rounding can't
# absorb that (a value on a halfway point flips either way), so the numbers are compared within these.
SCORE_TOLERANCE = 0.001    # an area's score (0-1)
METRIC_TOLERANCE = 0.005   # a candidate's AUC or Boyce, a mean over the reps (0.0001 = one rank swap in one rep)
# Candidates whose development scores differ between Windows and Linux builds even with the same seeds and
# library versions: xgboost samples rows for each tree, and the network's training carries the platform's
# rounding along (CI 2026-11-24: xgboost's Boyce 0.3234 on Linux, 0.2866 on Windows). Their metrics must be
# present and in range; the others, and the shipped map, are compared.
PLATFORM_DEPENDENT = ('xgboost', 'neural_network')
METRIC_RANGE = {'auc': (0.0, 1.0)}  # every other metric is a Boyce index, -1 to 1


def assert_survey_same(test, got: dict, golden: dict, name: str):
    """
    Survey mode kept what the golden holds: survey_summary exactly, then every number within its tolerance
    (or range, for PLATFORM_DEPENDENT candidates), all mismatches reported together.
    """
    test.assertEqual(survey_summary(got), survey_summary(golden), name)
    problems = []

    def close(a, b, delta, where):
        if not (is_number(a) and is_number(b)):
            if a != b:
                problems.append(f'{where}: {a!r} != {b!r}')
        elif abs(a - b) > delta:
            problems.append(f'{where}: {a} != {b} (off by {abs(a - b):.4f}, allowed {delta})')

    for pid, a in golden['areas'].items():
        close(got['areas'][pid].get('score'), a.get('score'), SCORE_TOLERANCE, f'area {pid} score')
    for g, c in zip(golden['candidates'], got['candidates']):
        for k, v in g.items():
            if k == 'name':
                continue
            where = f"candidate {g['name']} {k}"
            if g['name'] not in PLATFORM_DEPENDENT:
                close(c[k], v, METRIC_TOLERANCE, where)
            elif v is None:
                close(c[k], v, 0, where)
            else:
                low, high = METRIC_RANGE.get(k, (-1.0, 1.0))
                if not (is_number(c[k]) and low <= c[k] <= high):
                    problems.append(f'{where}: {c[k]!r} outside {low} to {high}')
    if problems:
        test.fail(f'{name}: ' + '; '.join(problems))


def survey_summary(result: dict) -> dict:
    """
    What survey mode must keep exactly: levels, reasons, flags, buildings, adoption, gate names and passes, the
    gate wording (its numbers left out), and each candidate's name and metric names. Area scores and candidate
    metrics are left out here and compared within a tolerance by assert_survey_same.
    """
    def without_decimals(text):
        return re.sub(r'-?\d+\.\d+', '#', text)

    acceptance = result['acceptance']
    return {
        'areas': {pid: {k: v for k, v in a.items() if k != 'score'} for pid, a in result['areas'].items()},
        'adopted': acceptance['adopted'],
        'gates': [{'gate': g['gate'], 'passed': g['passed'], 'detail': without_decimals(g['detail'])}
                  for g in acceptance['gates']],
        'reasons': [without_decimals(r) for r in acceptance['reasons']],
        'candidates': [{'name': c['name'], 'metrics': sorted(k for k in c if k != 'name')}
                       for c in result['candidates']],
    }
