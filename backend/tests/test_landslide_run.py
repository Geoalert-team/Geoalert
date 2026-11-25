"""
The landslide model's training run and its command (plan Task 7): the order
that keeps Talisay's test data unseen until the training set, the choice and
the cut-offs are in the report; the NOAH fallback when a gate fails; every
area with a level or a reason; no coordinate in the written files; the own
(January job) mode's tags and its Talisay fold; and the command's files,
prints and catalogue reader. A small synthetic table and city; no database.
"""
import csv
import json
import re
import shutil
import tempfile
from io import StringIO
from pathlib import Path
from unittest import mock

import numpy as np
from django.contrib.gis.geos import Polygon
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase

from apps.history import landslide_run
from apps.history.landslide_features import (
    CLIP_COLUMNS, FEATURE_COLUMNS, LANDCOVER_CLASSES, TERRAIN_COLUMNS, LandslideFeatures, write_features,
)
from apps.history.landslide_run import CODE_FILES, MODES, code_digest, columns_for, run
from apps.history.landslide_training import NO_POINTS, PH_FOLDS, UNLIKE, prepare_talisay
from apps.history.landslide_training_table import TABLE_COLUMNS, write_table
from apps.history.management.commands import train_landslide_model as tlm
from tests.test_landslide_training import block, ground, stack, valley_floor

BASE_LON, BASE_LAT = 123.8312, 10.2437
PER = 20                              # scoring points per purok
SLIDES = 8                            # slides per typhoon fold
STEEP = (101, 102, 103)               # steep hillside puroks: the model should flag them
FLAT = (104, 105, 106, 107, 108)      # flat, built-up lowland: Green, not grey
CLIFF = 109                           # ground steeper than any training slope: not assessed (unlike)
EMPTY = 110                           # no building or road point
PLANTED = 0                           # point 0 (purok 101): out of range on slope, in an assessed, flagged purok
PUROKS = STEEP + FLAT + (CLIFF, EMPTY)
MANIPIS, LAWAAN = 1, 2
QUIET = {'log': lambda msg: None}


def training_table(seed: int = 0, world: bool = False) -> tuple[dict, dict]:
    """
    The four Philippine typhoon folds (valley floors among the "no" points),
    with `world` one world event too, as read_table gives them. Small (under
    200 rows, one Adam batch), so the neural network fits quickly; the world
    event only where rule 1 is under test, since its test fits 40 networks.
    """
    rng = np.random.default_rng(seed)
    blocks = [block(rng, f, 'ph', SLIDES, valley_floors=True) for f in PH_FOLDS]
    if world:
        extra = block(rng, 'world', 'world', 6)
        extra['event'] = np.full(len(extra['label']), 'rwanda_2023-05-03', dtype=object)
        blocks.append(extra)
    t = stack(*blocks)
    table = {c: np.asarray(t[c], dtype=str) if c in ('event', 'fold', 'region') else np.asarray(t[c], float)
             for c in TABLE_COLUMNS}
    table['label'] = np.asarray(t['label'], int)
    table['dist_road_m'][table['event'] == 'paeng'] = np.nan  # Paeng failed the road check
    events = []
    for key in list(PH_FOLDS) + (['rwanda_2023-05-03'] if world else []):
        rows = table['event'] == key
        events.append({'key': key, 'fold': str(table['fold'][rows][0]), 'region': str(table['region'][rows][0]),
                       'slides': int(table['label'][rows].sum()), 'no_points': int((table['label'][rows] == 0).sum()),
                       'landcover_year': 2021, 'road_kept': key != 'paeng', 'dropped_missing_terrain': 0,
                       'dropped_at_sea_level': 0})
    meta = {'built_at': '2026-11-25T01:00:00+08:00', 'seed': 0, 'landcover_ok': True,
            'talisay_steep_road_density': 1.5,
            'road_check': {'talisay_steep_road_density': 1.5, 'steep_deg': 10, 'share': 0.1, 'threshold': 0.15,
                           'events': {e['key']: (0.05 if e['key'] == 'paeng' else 0.9) for e in events}},
            'events': events, 'rows': int(len(table['label']))}
    return table, meta


def talisay(seed: int = 1, steep_lowland: bool = False) -> LandslideFeatures:
    """
    Ten purok areas in two barangays: steep hillsides, flat built-up lowland, a
    cliff and an empty area. One hillside point (PLANTED) is steeper than any
    training slope, so it is out of range in a purok that is still assessed.
    With `steep_lowland` the lowland puroks are hillsides too, so Red and Orange
    would hold most of the city.
    """
    rng = np.random.default_rng(seed)
    parts, owner = [], []
    for pid in PUROKS:
        if pid == EMPTY:
            continue
        if pid in FLAT and not steep_lowland:
            pts = valley_floor(rng, PER)
            pts.update(slope_deg=rng.uniform(0.5, 2, PER), relief_m=rng.uniform(2, 10, PER),
                       hand_m=rng.uniform(0.5, 5, PER), lc_built=rng.uniform(0.9, 1.0, PER),
                       dist_road_m=rng.uniform(0, 3, PER))  # homes in built-up ground, road points on their road
            noah = 0.0
        else:
            pts = ground(rng, PER, 36, 3)
            if pid == CLIFF:
                pts['slope_deg'] = np.full(PER, 85.0)
            if pid == STEEP[0]:
                pts['slope_deg'][PLANTED] = 85.0
            noah = 3.0 if pid in STEEP or pid == CLIFF else 0.0
        pts['noah_class'] = np.full(PER, noah)
        parts.append(pts)
        owner += [pid] * PER
    n = len(owner)
    points = {c: np.concatenate([p[c] for p in parts]) for c in FEATURE_COLUMNS + ('noah_class',)}
    points.update(lon=BASE_LON + rng.uniform(0, 0.02, n), lat=BASE_LAT + rng.uniform(0, 0.02, n),
                  kind=(np.arange(n) % 2).astype(np.uint8))
    membership = (np.arange(n), np.asarray(owner, int))
    areas = []
    for pid in PUROKS:
        count = 0 if pid == EMPTY else PER
        hill = pid in STEEP or pid == CLIFF
        areas.append({'purok_id': pid, 'barangay_id': MANIPIS if hill else LAWAAN,
                      'barangay': 'Manipis' if hill else 'Lawaan III', 'name': f'Purok {pid}',
                      'confidence': 'low' if pid == 108 else 'medium', 'points': count, 'buildings': count // 2,
                      'road_points': count - count // 2, 'noah_p90': 1.0 if hill else 0.0})
    meta = {'outlines_version': 'v1', 'built_at': '2026-11-25T02:00:00+08:00', 'points': n, 'landcover_year': 2023,
            'landcover_ok': True}
    return LandslideFeatures(points=points, membership=membership, areas=areas, meta=meta)


def own_rows(seed: int = 3) -> dict:
    """GeoAlert's own located slides and their "no" points: the Talisay fold (weight left to the default, 10)."""
    rows = block(np.random.default_rng(seed), 'talisay', 'ph', SLIDES, valley_floors=True)
    rows['region'] = np.full(len(rows['label']), 'talisay', dtype=object)
    return {c: rows[c] for c in TABLE_COLUMNS}


TESTS_OK = {'test_puroks': [101, 102], 'catalogue_purok_ids': [103, None],
            'barangay_records': [{'barangay_id': MANIPIS, 'barangay': 'Manipis', 'records': 7}]}
TESTS_IN_GREEN = {**TESTS_OK, 'test_puroks': [104, 105]}


class LandslideRunTests(SimpleTestCase):
    """The plan's tests, as written."""

    def setUp(self):
        self.table, self.table_meta = training_table()
        self.features = talisay()
        self.tests_ok, self.tests_in_green = TESTS_OK, TESTS_IN_GREEN

    def test_tests_load_only_after_the_training_set_choice_and_cutoffs(self):
        seen = {}; report = {}
        def load_tests():
            seen.update({k: k in report for k in ('training_set', 'choice', 'cutoffs')}); return self.tests_ok
        run(self.table, self.table_meta, self.features, load_tests, report=report, reps=50, stability_reps=5, **QUIET)
        self.assertEqual(seen, {'training_set': True, 'choice': True, 'cutoffs': True})

    def test_a_failed_gate_ships_the_noah_fallback(self):  # test puroks placed where the model says Green
        model, report = run(self.table, self.table_meta, self.features, lambda: self.tests_in_green, reps=50, stability_reps=5, **QUIET)
        self.assertEqual(model['source'], 'noah'); self.assertTrue(model['version'].startswith('noah_fallback@'))
        self.assertFalse(report['acceptance']['adopted']); self.assertTrue(report['acceptance']['reasons'])

    def test_every_area_has_a_level_or_a_reason(self):
        model, _ = run(self.table, self.table_meta, self.features, lambda: self.tests_ok, reps=50, stability_reps=5, **QUIET)
        for a in model['areas'].values():
            self.assertTrue((a['level'] in ('Red', 'Orange', 'Green')) != bool(a['not_assessed_reason']))

    def test_no_coordinates_in_the_written_files(self):
        model, report = run(self.table, self.table_meta, self.features, lambda: self.tests_ok, reps=50, stability_reps=5, **QUIET)
        text = json.dumps([model, report])
        for lon, lat in zip(self.features.points['lon'][:50], self.features.points['lat'][:50]):
            self.assertNotIn(f'{lat:.4f}', text); self.assertNotIn(f'{lon:.4f}', text)

    def test_no_test_puroks_fails_gate_two(self):
        _, report = run(self.table, self.table_meta, self.features, lambda: {**self.tests_ok, 'test_puroks': []}, reps=50, stability_reps=5, **QUIET)
        self.assertFalse(report['acceptance']['gates']['talisay_test'])


class LandslideRunDetailTests(SimpleTestCase):
    """
    What the files hold, from one adopted run (with a world event, so rule 1
    runs), one fallback run and one own-mode run.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.table, cls.table_meta = training_table(world=True)
        cls.ph_table, cls.ph_meta = training_table()
        cls.features = talisay()
        cls.before_tests = []

        def load_tests():  # a snapshot of the report at each call
            cls.before_tests.append({k: json.loads(json.dumps(v)) for k, v in cls.partial.items()})
            return TESTS_OK

        cls.partial = {}
        cls.model, cls.report = run(cls.table, cls.table_meta, cls.features, load_tests, report=cls.partial,
                                    fingerprint='synthetic', reps=50, stability_reps=5, **QUIET)
        cls.fb_model, cls.fb_report = run(cls.ph_table, cls.ph_meta, cls.features, lambda: TESTS_IN_GREEN,
                                          fingerprint='synthetic', reps=50, stability_reps=5, **QUIET)
        cls.own_tests = {'test_puroks': [101, 102, 101, 102, 104], 'season': 2026}  # one entry per held-back spot
        core = landslide_run.lt
        with mock.patch.object(core, 'out_of_fold', wraps=core.out_of_fold) as cls.oof_spy, \
                mock.patch.object(core, 'point_cutoffs', wraps=core.point_cutoffs) as cls.cutoff_spy, \
                mock.patch.object(core, 'stability', wraps=core.stability) as cls.stability_spy:
            cls.own_model, cls.own_report = run(cls.ph_table, cls.ph_meta, cls.features, lambda: cls.own_tests,
                                                fingerprint='synthetic', reps=50, stability_reps=5, mode='own',
                                                own_rows=own_rows(), **QUIET)

    def test_a_model_that_passes_every_gate_is_adopted(self):
        model, report = self.model, self.report
        self.assertEqual(model['source'], 'model', report['acceptance'])
        self.assertEqual(report['acceptance']['gates'], {'better_than_noah': True, 'talisay_test': True,
                                                         'not_everything_flagged': True, 'tests_seen_last': True})
        self.assertEqual(report['acceptance']['reasons'], [])
        self.assertRegex(model['version'], r'^(neural_network|logistic_regression|xgboost)@[0-9a-f]{12}$')
        self.assertEqual(model['version'].split('@')[0], model['chosen'])
        levels = {pid: a['level'] for pid, a in model['areas'].items()}
        self.assertTrue(all(levels[p] in ('Red', 'Orange') for p in STEEP), levels)
        self.assertIn('Red', [levels[p] for p in STEEP])
        self.assertTrue(all(levels[p] == 'Green' for p in FLAT), levels)  # flat built-up ground: Green, not grey
        self.assertEqual(model['areas'][CLIFF]['not_assessed_reason'], UNLIKE)
        self.assertEqual(model['areas'][EMPTY]['not_assessed_reason'], NO_POINTS)
        self.assertTrue(model['areas'][108]['estimated_outline'])
        self.assertFalse(model['areas'][101]['estimated_outline'])
        self.assertEqual(report['stability'], {'refits': 5, 'uncertain_puroks': sum(
            a['uncertain'] for a in model['areas'].values())})

    def test_gate_three_counts_only_the_in_range_points_of_assessed_puroks(self):
        # Ruling R27: the share is over the unique in-range scoring points of assessed puroks
        model, report = self.model, self.report
        world = self.table['fold'] == 'world'
        train = self.table if model['training_set'] == 'ph+world' else {k: v[~world] for k, v in self.table.items()}
        _, valid = prepare_talisay(self.features.points, train, FEATURE_COLUMNS)
        self.assertEqual(int(valid.sum()), report['in_range']['in_range'])  # the same mask run() used
        self.assertFalse(valid[PLANTED])
        self.assertIn(model['areas'][STEEP[0]]['level'], ('Red', 'Orange'))  # assessed and flagged
        idx, pids = self.features.membership
        levels = {pid: a['level'] for pid, a in model['areas'].items() if a['level']}
        assessed = np.isin(pids, list(levels))
        flagged = np.isin(pids, [p for p, lv in levels.items() if lv in ('Red', 'Orange')])

        def share(keep):
            return np.unique(idx[flagged & keep]).size / np.unique(idx[assessed & keep]).size

        in_range, every_point = share(valid[idx]), share(np.ones(len(idx), bool))
        self.assertNotAlmostEqual(in_range, every_point, places=4)  # the two readings differ here
        self.assertEqual(report['classes']['flagged_point_share'], round(in_range, 4))
        self.assertEqual(report['acceptance']['details']['not_everything_flagged'],
                         f'{in_range:.0%} of the in-range scoring points of assessed puroks in Red or Orange')

    def test_the_report_before_the_tests_held_the_training_set_choice_cutoffs_and_in_range(self):
        self.assertEqual(len(self.before_tests), 1)  # the test data are loaded once, never earlier
        before = self.before_tests[0]
        for key in ('training_set', 'choice', 'cutoffs', 'in_range', 'candidates'):
            self.assertIn(key, before)
        self.assertEqual(before['cutoffs'], self.report['cutoffs'])
        self.assertNotIn('talisay_test', before)
        self.assertNotIn('acceptance', before)

    def test_the_model_file_has_every_key_the_site_reads(self):
        model = self.model
        self.assertEqual(set(model) >= {'version', 'source', 'chosen', 'training_set', 'built_at', 'outlines_version',
                                        'cutoffs', 'clip_ranges', 'inputs', 'areas'}, True, sorted(model))
        self.assertIn(model['training_set'], ('ph', 'ph+world'))
        self.assertEqual(model['outlines_version'], 'v1')
        self.assertRegex(model['built_at'], r'^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\+08:00$')
        self.assertEqual(set(model['cutoffs']), {'red', 'orange', 'red_recall', 'orange_recall', 'target_reached'})
        self.assertEqual(set(model['clip_ranges']), set(CLIP_COLUMNS))
        for lo, hi in model['clip_ranges'].values():
            self.assertLessEqual(lo, hi)
        self.assertIs(model['inputs']['landcover_ok'], True)
        self.assertEqual(model['inputs']['columns'], list(FEATURE_COLUMNS))
        self.assertEqual(set(model['areas']), set(PUROKS))
        for pid, a in model['areas'].items():
            self.assertEqual(set(a), {'barangay_id', 'level', 'score', 'uncertain', 'not_assessed_reason',
                                      'estimated_outline', 'points'}, pid)
            self.assertIs(type(a['points']), int)
            self.assertIs(type(a['uncertain']), bool)
        self.assertEqual(model['areas'][101]['points'], PER)
        self.assertEqual(model['areas'][101]['barangay_id'], MANIPIS)

    def test_the_report_has_every_key_the_card_reads(self):
        report = self.report
        for key in ('version', 'source', 'training_set', 'candidates', 'choice', 'acceptance', 'cutoffs',
                    'talisay_test', 'in_range', 'road_check', 'classes', 'limits', 'credits'):
            self.assertIn(key, report)
        self.assertEqual((report['version'], report['source']), (self.model['version'], 'model'))
        ts = report['training_set']
        self.assertEqual(set(ts['world']) >= {'joined', 'gain', 'lo', 'hi'}, True)
        events = {e['event']: e for e in ts['events']}
        self.assertEqual(set(events), set(PH_FOLDS) | {'rwanda_2023-05-03'})
        self.assertEqual((events['egay']['fold'], events['egay']['region'], events['egay']['slides']),
                         ('egay', 'ph', SLIDES))
        self.assertEqual(events['rwanda_2023-05-03']['fold'], 'world')
        names = [c['name'] for c in report['candidates']]
        self.assertEqual(names, ['neural_network', 'logistic_regression', 'xgboost', 'noah_only'])
        for c in report['candidates']:
            self.assertLessEqual(c['lo'], c['auc']); self.assertLessEqual(c['auc'], c['hi'])
            self.assertEqual([f['fold'] for f in c['folds']], list(PH_FOLDS))
        self.assertEqual(report['choice']['chosen'], self.model['chosen'])
        self.assertTrue(report['choice']['verdict'])
        self.assertEqual(set(report['acceptance']['details']), set(report['acceptance']['gates']))
        tt = report['talisay_test']
        self.assertEqual([(p['name'], p['level']) for p in tt['puroks']],
                         [(f'Purok {p}', self.model['areas'][p]['level']) for p in (101, 102)])
        self.assertEqual([c['level'] for c in tt['catalogue']], [self.model['areas'][103]['level'], None])
        check = {b['barangay']: b for b in tt['barangay_check']['barangays']}
        self.assertEqual((check['Manipis']['records'], check['Manipis']['points']), (7, 4 * PER))
        self.assertIn('rest', tt['barangay_check'])
        self.assertEqual(report['road_check']['threshold'], 0.15)
        kept = int(np.isfinite(self.table['dist_road_m']).sum()) if self.model['training_set'] == 'ph+world' else \
            int(np.isfinite(self.table['dist_road_m'][self.table['fold'] != 'world']).sum())
        self.assertEqual(report['road_check']['rows_with_road'], kept)
        self.assertEqual(report['road_check']['events_without_road'], ['paeng'])
        classes = report['classes']
        self.assertEqual(sum(v['puroks'] for v in classes['levels'].values()), len(STEEP) + len(FLAT))
        self.assertEqual(classes['not_assessed'], {UNLIKE: 1, NO_POINTS: 1})
        self.assertTrue(any('Vershel et al. (2025)' in c for c in report['credits']))
        self.assertTrue(any('Microsoft building footprints (ODbL)' == c for c in report['credits']))
        text = json.dumps(report).lower()
        for word in ('likely', 'risk now', 'expected'):
            self.assertNotIn(word, text)

    def test_the_in_range_block_counts_points_and_clipped_values(self):
        block_ = self.report['in_range']
        n = len(self.features.membership[0])
        self.assertEqual(block_['points'], n)
        self.assertGreaterEqual(block_['in_range'], 4 * PER)  # the flat lowland is in range, the cliff is not
        self.assertLessEqual(block_['in_range'], n - PER)
        self.assertAlmostEqual(block_['share'], block_['in_range'] / n, places=4)
        self.assertEqual(set(block_['clipped']), set(CLIP_COLUMNS))
        self.assertGreaterEqual(block_['clipped']['lc_built'], len(FLAT) * PER)  # built-up homes clipped, not dropped
        self.assertGreaterEqual(block_['clipped']['dist_road_m'], 1)
        self.assertEqual(set(block_['outside_by_column']), set(TERRAIN_COLUMNS))
        self.assertGreaterEqual(block_['outside_by_column']['slope_deg']['above'], PER)  # the cliff, at least
        self.assertEqual(block_['unlike_puroks'], 1)

    def test_the_fallback_ships_noah_classes_without_uncertain_marks(self):
        model, report = self.fb_model, self.fb_report
        self.assertEqual(report['acceptance']['gates']['talisay_test'], False)
        self.assertEqual(report['acceptance']['reasons'],
                         ['Only 0 of the 2 Talisay puroks with a located landslide were Red or Orange (2 needed).'])
        self.assertEqual(model['cutoffs'], report['fallback']['cutoffs'])
        self.assertNotEqual(report['fallback']['cutoffs'], report['cutoffs'])
        for pid, a in model['areas'].items():
            self.assertFalse(a['uncertain'])
            if pid == EMPTY:
                self.assertEqual(a['not_assessed_reason'], NO_POINTS)
            else:  # NOAH covers the province: every purok with points is assessed
                self.assertIn(a['level'], ('Red', 'Orange', 'Green'), pid)
        self.assertEqual(model['areas'][101]['level'], 'Red')     # NOAH class 3 under the hillsides
        self.assertEqual(model['areas'][104]['level'], 'Green')   # NOAH class 0 on the lowland
        self.assertIsNone(report['stability'])
        for p in report['talisay_test']['puroks']:  # the rejected model's level, and the level that ships
            self.assertEqual(p['published_level'], model['areas'][p['purok_id']]['level'])
        # The fallback's share reads every scoring point (each has a NOAH class): the cliff is Red here although
        # every one of its points is out of the model's range, so the in-range reading would give another share
        self.assertEqual(model['areas'][CLIFF]['level'], 'Red')
        idx, pids = self.features.membership
        levels = {pid: a['level'] for pid, a in model['areas'].items() if a['level']}
        flagged = np.unique(idx[np.isin(pids, [p for p, lv in levels.items() if lv in ('Red', 'Orange')])]).size
        share = round(flagged / np.unique(idx[np.isin(pids, list(levels))]).size, 4)
        self.assertEqual((report['fallback']['flagged_share'], report['classes']['flagged_point_share']),
                         (share, share))

    def test_own_mode_tags_the_report_and_adds_the_talisay_fold(self):
        model, report = self.own_model, self.own_report
        self.assertEqual(model['source'], 'geoalert')
        self.assertEqual(report['source'], 'geoalert')
        self.assertEqual(report['own_spots'], SLIDES)
        self.assertEqual(report['season'], 2026)
        held = report['temporal_test']['held_back']
        self.assertEqual([h['purok_id'] for h in held], [101, 102, 101, 102, 104])
        self.assertEqual([h['level'] for h in held], [model['areas'][p]['level'] for p in (101, 102, 101, 102, 104)])
        # Ruling R30: gate 2 counts held-back spots (n = spots; a spot hits when its purok is Red or Orange). Here
        # that is 4 of 5 (4 needed): a pass; counted by purok it would be 2 of 3 (3 needed): a fail. The bars
        # differ too (4 against 3), so neither the count nor the bar can read puroks unseen
        self.assertIn(model['areas'][101]['level'], ('Red', 'Orange'))
        self.assertIn(model['areas'][102]['level'], ('Red', 'Orange'))
        self.assertEqual(model['areas'][104]['level'], 'Green')
        self.assertEqual(report['acceptance']['details']['talisay_test'], '4 of 5 in Red or Orange (4 needed)')
        self.assertIs(report['acceptance']['gates']['talisay_test'], True)
        for c in report['candidates']:
            self.assertEqual([f['fold'] for f in c['folds']], list(PH_FOLDS) + ['talisay'])
        events = {e['event']: e for e in report['training_set']['events']}
        self.assertEqual((events['talisay']['fold'], events['talisay']['slides'], events['talisay']['weight']),
                         ('talisay', SLIDES, 10))
        self.assertEqual(events['egay']['weight'], 1)
        self.assertFalse(model['version'].startswith('noah_fallback@'))
        self.assertNotEqual(model['version'], self.model['version'])

    def test_own_rows_weigh_ten_in_the_fits_and_the_cutoff_walk(self):
        # AUC and its bootstrap take no weight at all (choose, auc_gain); the fits and the walk do
        self.assertEqual(len(self.oof_spy.call_args_list), 3)
        for call in self.oof_spy.call_args_list:
            name, table, columns, folds_scored, w = call.args
            self.assertEqual(folds_scored, PH_FOLDS + ('talisay',))
            mine = table['fold'] == 'talisay'
            self.assertEqual(int(mine.sum()), 4 * SLIDES)  # each own slide and its three "no" points
            self.assertTrue((w[mine] == 10).all() and (w[~mine] == 1).all(), name)
        (scores, y, w), _ = self.cutoff_spy.call_args
        np.testing.assert_array_equal(w, self.oof_spy.call_args.args[4])
        self.assertEqual(self.stability_spy.call_args.args[3].tolist(), w.tolist())

    def test_the_files_are_plain_json_with_no_coordinate(self):
        for model, report in ((self.model, self.report), (self.fb_model, self.fb_report),
                              (self.own_model, self.own_report)):
            text = json.dumps([model, report], allow_nan=False)  # plain types only: no numpy number, no NaN
            for lon, lat in zip(self.features.points['lon'], self.features.points['lat']):
                self.assertNotIn(f'{lat:.4f}', text); self.assertNotIn(f'{lon:.4f}', text)


class FallbackGateTests(SimpleTestCase):
    """Gates 1 and 3 failing on their own each ship the NOAH fallback (gate 2's path is tested above)."""

    def ship(self, table, meta, features):
        return run(table, meta, features, lambda: TESTS_OK, fingerprint='synthetic', reps=50, stability_reps=5,
                   **QUIET)

    def test_a_model_no_better_than_noah_ships_noah(self):
        table, meta = training_table()
        ph = table['fold'] != 'world'
        table['noah_class'][ph] = np.where(table['label'][ph] == 1, 3.0, 0.0)  # NOAH's map ranks every slide first
        model, report = self.ship(table, meta, talisay())
        gates = report['acceptance']['gates']
        self.assertEqual((gates['better_than_noah'], gates['talisay_test'], gates['not_everything_flagged']),
                         (False, True, True))
        self.assertEqual(len(report['acceptance']['reasons']), 1)
        self.assertRegex(report['acceptance']['reasons'][0],
                         r"^It did not clearly beat UP NOAH's landslide map on the held-out Philippine typhoons: "
                         r'the lower end of its AUC gain was -?\d\.\d{3}, not above zero\.$')
        self.assertEqual(model['source'], 'noah'); self.assertTrue(model['version'].startswith('noah_fallback@'))
        self.assertIsNone(report['stability'])

    def test_a_map_flagging_most_of_the_city_ships_noah(self):
        table, meta = training_table()
        model, report = self.ship(table, meta, talisay(steep_lowland=True))
        gates = report['acceptance']['gates']
        self.assertEqual((gates['better_than_noah'], gates['talisay_test'], gates['not_everything_flagged']),
                         (True, True, False))
        self.assertEqual(len(report['acceptance']['reasons']), 1)
        self.assertRegex(report['acceptance']['reasons'][0],
                         r"^Red and Orange would cover \d+% of the in-range scoring points of Talisay's assessed "
                         r'puroks, more than half\.$')
        self.assertEqual(model['source'], 'noah'); self.assertTrue(model['version'].startswith('noah_fallback@'))
        self.assertEqual(model['areas'][104]['level'], 'Green')  # NOAH class 0 there: the fallback is not the model


class HelperTests(SimpleTestCase):
    def test_modes_code_files_and_digest(self):
        self.assertEqual(MODES, ('outside', 'own'))
        self.assertEqual(CODE_FILES, ('landslide_training.py', 'landslide_run.py', 'landslide_features.py',
                                      'flood_rules.py', 'flood_training.py', 'landslide_training_table.py',
                                      'landslide_own.py', 'mlp_fit.py'))
        self.assertRegex(code_digest(), r'^[0-9a-f]{40}$')

    # Ruling R57: a table built from the Philippine typhoons only says why the world test did not run
    def test_the_world_verdict_says_when_the_world_events_were_left_out_of_the_build(self):
        none = {'joined': False, 'gain': None, 'lo': None, 'hi': None}
        left_out = landslide_run._world_verdict(none, False, {'world_left_out': ['rwanda_2023-05-03']})
        self.assertEqual(left_out, 'The world events were left out of this build (it was built from the Philippine '
                                   'typhoons only), so the world test did not run.')
        self.assertEqual(landslide_run._world_verdict(none, False, {}), 'No world events are in the training table.')
        self.assertEqual(landslide_run._world_verdict(none, False, {'world_left_out': []}),
                         'No world events are in the training table.')
        table, meta = training_table()
        _, report = run(table, {**meta, 'world_left_out': ['rwanda_2023-05-03']}, talisay(), lambda: TESTS_OK,
                        reps=50, stability_reps=5, **QUIET)
        self.assertEqual(report['training_set']['world']['verdict'], left_out)
        self.assertEqual(report['training_set']['chosen'], 'ph')

    # Final review B5: the cut-off walk, auc_gain, in_range and the "no" sampling live in these files; a change to
    # any of them can give other classes, so it must give another model version
    def test_a_change_to_the_shared_rules_or_the_no_sampling_changes_the_digest(self):
        real = Path.read_bytes
        before = code_digest()
        for name in ('flood_rules.py', 'flood_training.py', 'landslide_training_table.py', 'landslide_own.py'):
            def edited(path, name=name):
                return real(path) + (b'\n# changed\n' if path.name == name else b'')

            with self.subTest(name), mock.patch.object(Path, 'read_bytes', edited):
                self.assertNotEqual(code_digest(), before)

    # Final review B3: a passed deadline stops the run in its first refit loop, before any test data is read
    def test_a_passed_deadline_stops_the_run_before_the_tests(self):
        from apps.history import landslide_training as lt

        table, meta = training_table(world=True)
        tests = mock.Mock(return_value=TESTS_OK)
        with self.assertRaisesMessage(lt.PastDeadline, 'the run passed its 330-minute limit'):
            run(table, meta, talisay(), tests, reps=20, stability_reps=2, deadline=lt.Deadline(at=0.0, minutes=330),
                **QUIET)
        tests.assert_not_called()

    def test_the_deadline_reaches_every_refit_loop(self):
        from apps.history import landslide_training as lt

        table, meta = training_table(world=True)
        far = lt.Deadline(at=lt.time.monotonic() + 3600, minutes=330)
        with mock.patch.object(lt, 'world_test', wraps=lt.world_test) as world, \
                mock.patch.object(lt, 'out_of_fold', wraps=lt.out_of_fold) as oof, \
                mock.patch.object(lt, 'stability', wraps=lt.stability) as refits:
            model, _ = run(table, meta, talisay(), lambda: TESTS_OK, reps=50, stability_reps=2, deadline=far, **QUIET)
        self.assertEqual(model['source'], 'model')  # adopted, so the stability refits ran
        self.assertIs(world.call_args.kwargs['deadline'], far)
        self.assertEqual({c.kwargs['deadline'] is far for c in oof.call_args_list}, {True})
        self.assertIs(refits.call_args.kwargs['deadline'], far)

    def test_land_cover_is_dropped_unless_both_sides_read_it(self):
        no_lc = tuple(c for c in FEATURE_COLUMNS if c not in LANDCOVER_CLASSES.values())
        self.assertEqual(columns_for({'landcover_ok': True}, {'landcover_ok': True}), FEATURE_COLUMNS)
        self.assertEqual(columns_for({'landcover_ok': False}, {'landcover_ok': True}), no_lc)
        self.assertEqual(columns_for({'landcover_ok': True}, {'landcover_ok': False}), no_lc)
        self.assertEqual(columns_for({}, {'landcover_ok': True}), no_lc)

    def test_an_unknown_mode_or_own_mode_without_rows_is_refused(self):
        table, meta = training_table()
        with self.assertRaises(ValueError):
            run(table, meta, talisay(), lambda: TESTS_OK, mode='survey', **QUIET)
        with self.assertRaises(ValueError):
            run(table, meta, talisay(), lambda: TESTS_OK, mode='own', **QUIET)


CATALOGUE_HEADER = ['source_name', 'event_id', 'event_date', 'location_accuracy', 'country_name', 'longitude',
                    'latitude']


def write_catalogue(path: Path, rows: list):
    with open(path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(CATALOGUE_HEADER)
        for i, (accuracy, lon, lat) in enumerate(rows):
            writer.writerow(['x', i, '08/01/2008 12:00:00 AM', accuracy, 'Philippines', lon, lat])


def city_polygon():
    city = Polygon.from_bbox((BASE_LON - 0.01, BASE_LAT - 0.01, BASE_LON + 0.03, BASE_LAT + 0.03))
    city.srid = 4326
    return city


class CatalogueTests(SimpleTestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def test_only_exact_and_1km_points_inside_the_city_reach_a_purok(self):
        path = self.tmp / tlm.CATALOGUE_FILE
        write_catalogue(path, [('exact', BASE_LON + 0.001, BASE_LAT + 0.001), ('1km', BASE_LON + 0.002, BASE_LAT),
                               ('5km', BASE_LON, BASE_LAT), ('unknown', BASE_LON, BASE_LAT),
                               ('exact', BASE_LON + 1, BASE_LAT), ('exact', '', '')])
        points = tlm.read_catalogue(path)
        self.assertEqual(len(points), 3)  # the far exact point is read, then left outside the city
        placed = []
        ids = tlm.catalogue_puroks(points, city_polygon(), place=lambda p: placed.append((p.x, p.y)) or 101)
        self.assertEqual(ids, [101, 101])
        self.assertEqual(len(placed), 2)


class CommandTests(SimpleTestCase):
    """The command on files written by the real writers; the database reads are stubbed (no query can run here)."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.cache, self.out = self.tmp / 'cache', self.tmp / 'out'
        self.cache.mkdir()
        self.out.mkdir()

    def write_inputs(self):
        table, meta = training_table()
        rows = [{c: table[c][i] for c in TABLE_COLUMNS} for i in range(len(table['label']))]
        write_table(rows, meta, self.out / 'landslide_training.csv', self.out / 'landslide_training.meta.json')
        features = talisay()
        write_features(features, self.out / 'landslide_purok_features.csv',
                       self.out / 'landslide_purok_features.meta.json', cache_dir=self.cache)
        write_catalogue(self.cache / tlm.CATALOGUE_FILE, [('exact', BASE_LON + 0.001, BASE_LAT + 0.001)])

    def call(self, *args):
        out = StringIO()
        call_command('train_landslide_model', '--cache-dir', str(self.cache), '--output-dir', str(self.out), *args,
                     stdout=out)
        return out.getvalue()

    def test_a_missing_catalogue_stops_before_any_training(self):
        self.write_inputs()
        (self.cache / tlm.CATALOGUE_FILE).unlink()
        with mock.patch.object(tlm, 'run') as fake_run, self.assertRaises(CommandError) as caught:
            self.call()
        self.assertIn(tlm.CATALOGUE_FILE, str(caught.exception))
        fake_run.assert_not_called()

    def test_a_missing_table_names_the_command_to_run(self):
        with self.assertRaises(CommandError) as caught:
            self.call()
        self.assertIn('build_landslide_training', str(caught.exception))

    def test_a_changed_purok_map_stops_the_run(self):
        self.write_inputs()
        with mock.patch.object(tlm.Purok, 'outlines_version', return_value='v2'), \
                mock.patch.object(tlm, 'run') as fake_run, self.assertRaises(CommandError):
            self.call()
        fake_run.assert_not_called()

    def test_writes_both_files_and_prints_the_in_range_block_and_one_verdict(self):
        self.write_inputs()
        order = []

        def test_puroks():
            order.append('located_test_puroks')
            return [101, 102]

        with mock.patch.object(tlm.Purok, 'outlines_version', return_value='v1'), \
                mock.patch.object(tlm, 'close_old_connections',
                                  side_effect=lambda: order.append('close_old_connections')) as close, \
                mock.patch.object(tlm, 'located_test_puroks', side_effect=test_puroks), \
                mock.patch.object(tlm, 'landslide_barangays', return_value=TESTS_OK['barangay_records']), \
                mock.patch.object(tlm, 'city_outline', return_value=city_polygon()), \
                mock.patch.object(tlm, 'smallest_purok', return_value=103):
            printed = self.call('--reps', '30', '--stability-reps', '2')
        model = json.loads((self.out / 'landslide_purok_model.json').read_text(encoding='utf-8'))
        report = json.loads((self.out / 'landslide_purok_report.json').read_text(encoding='utf-8'))
        self.assertEqual(sorted(p.name for p in self.out.iterdir() if p.suffix == '.tmp'), [])
        self.assertEqual(model['version'], report['version'])
        self.assertEqual(set(model['inputs']['files']), {'landslide_training.csv', 'landslide_training.meta.json',
                                                         'landslide_purok_features.csv',
                                                         'landslide_purok_features.meta.json',
                                                         'landslide_points.npz'})
        for digest in model['inputs']['files'].values():
            self.assertRegex(digest, r'^[0-9a-f]{40}$')
        self.assertEqual([c['level'] for c in report['talisay_test']['catalogue']], [model['areas']['103']['level']])
        self.assertEqual(len(re.findall(r'^Verdict:', printed, flags=re.M)), 1, printed)
        self.assertRegex(printed, r'In range: \d+ of \d+ Talisay scoring points')
        self.assertIn('Clipped to the training range:', printed)
        self.assertNotIn(self.tmp.name, json.dumps([model, report]))  # the temp folder's name: no separators
        self.assertEqual(close.call_count, 1)
        self.assertEqual(order[0], 'close_old_connections')  # R29: before the first test-data query

    def test_a_value_json_cannot_carry_stops_before_any_file_is_written(self):
        self.write_inputs()
        bad = ({'version': 'x@0', 'source': 'model', 'inputs': {}, 'cutoffs': {'red': float('nan')}, 'areas': {}},
               {'version': 'x@0'})
        with mock.patch.object(tlm.Purok, 'outlines_version', return_value='v1'), \
                mock.patch.object(tlm, 'run', return_value=bad), self.assertRaises(CommandError) as caught:
            self.call()
        self.assertIn('nothing was written', str(caught.exception))
        self.assertFalse((self.out / 'landslide_purok_model.json').exists())
        self.assertFalse((self.out / 'landslide_purok_report.json').exists())

    # Final review B5: hours of fitting never end in a bare traceback on a bad value
    def test_a_bad_value_in_the_run_is_a_command_error_that_names_it(self):
        self.write_inputs()
        with mock.patch.object(tlm.Purok, 'outlines_version', return_value='v1'), \
                mock.patch.object(tlm, 'run', side_effect=ValueError('Input X contains NaN.')), \
                self.assertRaises(CommandError) as caught:
            self.call()
        self.assertIn('Input X contains NaN.', str(caught.exception))
        self.assertIn('nothing was written', str(caught.exception))
        self.assertFalse((self.out / 'landslide_purok_model.json').exists())

    def test_the_writer_has_no_string_fallback(self):
        self.assertEqual(tlm._plain(np.int64(3)), 3)
        self.assertIs(type(tlm._plain(np.float32(0.5))), float)
        with self.assertRaises(TypeError):
            tlm._plain(object())
