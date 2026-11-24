"""
The flood model's training run (plan Task 5): the order that keeps test data
unseen until the choice and cut-offs are fixed, the NOAH fallback when a gate
fails, every area getting a level or a reason, and no raw survey point in the
written files (spec 4.4, 5, 6, 8.1). A small synthetic city, no database.
"""
import json
from unittest import mock

import numpy as np
from django.contrib.gis.geos import Polygon
from django.test import SimpleTestCase

from apps.history import flood_run
from apps.history.flood_features import FloodFeatures
from apps.history.flood_run import run

BASE_LNG, BASE_LAT, STEP = 123.830, 10.250, 0.002  # puroks are 0.002° blocks (~220 m), 5 per row
PRONE = {0, 1, 10, 11}  # where the floods are: low ground by the river


def block(k):
    return BASE_LNG + (k % 5) * STEP, BASE_LAT + (k // 5) * STEP


def inputs_for(k, rng):
    low = k in PRONE
    return {'noah25_class': float(rng.integers(0, 4)), 'noah5_class': 0.0,
            'rel_height_river_m': float(rng.uniform(0, 1) if low else rng.uniform(3, 8)),
            'dist_river_m': float(rng.uniform(10, 60) if low else rng.uniform(200, 600)),
            'depression_m': float(rng.uniform(0, 0.2)), 'built_share': float(rng.uniform(0.3, 0.9))}


def synthetic_city(seed=0):
    rng = np.random.default_rng(seed)
    cols = ('noah25_class', 'noah5_class', 'rel_height_river_m', 'dist_river_m', 'depression_m', 'built_share')
    rows, lon, lat, purok = [], [], [], []
    for k in range(20):
        x0, y0 = block(k)
        for _ in range(30):
            rows.append(inputs_for(k, rng))
            lon.append(x0 + rng.uniform(0, 0.0015))
            lat.append(y0 + rng.uniform(0, 0.0015))
            purok.append(100 + k)
    buildings = {c: np.array([r[c] for r in rows]) for c in cols}
    buildings.update(lon=np.array(lon), lat=np.array(lat), barangay_id=np.array([1 if p < 110 else 2 for p in purok]),
                     barangay=np.array(['Lawaan III' if p < 110 else 'Biasong' for p in purok]),
                     noah25_within_300m=buildings['noah25_class'] > 0)
    member = (np.arange(len(purok)), np.array(purok))
    areas = [{'purok_id': 100 + k, 'barangay_id': 1 if k < 10 else 2, 'barangay': 'Lawaan III' if k < 10 else 'Biasong',
              'name': f'Purok {k}', 'confidence': 'low' if k == 19 else 'high', 'buildings': 30} for k in range(20)]
    meta = {'noah_layers_used': ['noah25_class'], 'outlines_version': 'v1'}
    features = FloodFeatures(buildings=buildings, membership=member, areas=areas, meta=meta)
    spots = []
    for k in sorted(PRONE):
        x0, y0 = block(k)
        for i in range(10):
            spots.append({'lat': round(y0 + 0.0001234 + i * 0.0001111, 7), 'lon': round(x0 + 0.0003456 + i * 0.0000999, 7),
                          'positive': True, 'events': ['Ruby'], 'max_depth': 1.0, 'purok_id': 100 + k,
                          'barangay': 'Lawaan III' if k < 10 else 'Biasong', 'inputs': inputs_for(k, rng)})
    x0, y0 = block(6)
    for i in range(2):
        spots.append({'lat': round(y0 + 0.0005678 + i * 0.0001, 7), 'lon': round(x0 + 0.0004321, 7), 'positive': False,
                      'events': ['Ruby'], 'max_depth': 0.0, 'purok_id': 106, 'barangay': 'Lawaan III',
                      'inputs': inputs_for(6, rng)})
    city = Polygon.from_bbox((123.825, 10.245, 123.845, 10.262))
    city.srid = 4326
    return features, spots, city


def tests_at(puroks):
    pts = []
    for i, k in enumerate(puroks):
        x0, y0 = block(k)
        pts.append({'day': '2025-11-04', 'barangay': 'Lawaan III' if k < 10 else 'Biasong', 'purok_id': 100 + k,
                    'lat': y0 + 0.0007, 'lon': x0 + 0.0007, 'precision': 'place', 'source_ref': f'ref-{i}'})
    return pts


class FloodRunTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.features, cls.spots, cls.city = synthetic_city()
        n = len(cls.features.buildings['lon'])
        prone = np.isin(cls.features.membership[1], [100 + k for k in PRONE])
        cls.eosrs = np.zeros(n, bool)
        cls.eosrs[cls.features.membership[0][prone]] = True
        records = {'tino': ['Lawaan III'], 'any': ['Lawaan III', 'Biasong']}
        cls.tests_ok = {'geoalert_points': tests_at([0, 1, 10, 11]), 'eosrs_flagged': cls.eosrs,
                        'barangay_records': records}
        cls.tests_in_green = {'geoalert_points': tests_at([6, 6, 6, 6]), 'eosrs_flagged': cls.eosrs,
                              'barangay_records': records}

    def go(self, tests, report=None):
        return run(self.features, self.spots, self.city, lambda: tests, log=lambda msg: None, report=report,
                   fingerprint='synthetic', reps=40, stability_reps=4)

    def test_tests_load_only_after_choice_and_cutoffs(self):
        report_so_far, seen = {}, {}

        def load_tests():
            seen['choice'] = 'choice' in report_so_far
            seen['cutoffs'] = 'cutoffs' in report_so_far
            return self.tests_ok

        run(self.features, self.spots, self.city, load_tests, log=lambda msg: None, report=report_so_far,
            fingerprint='synthetic', reps=40, stability_reps=4)
        self.assertEqual(seen, {'choice': True, 'cutoffs': True})

    def test_a_model_that_beats_noah_is_adopted(self):
        model, report = self.go(self.tests_ok)
        self.assertEqual(model['source'], 'model', report['acceptance'])
        self.assertTrue(report['acceptance']['adopted'])
        self.assertFalse(model['version'].startswith('noah_fallback@'))
        for k in PRONE:
            self.assertIn(model['areas'][100 + k]['level'], ('Red', 'Orange'))
        self.assertIn('Red', [model['areas'][100 + k]['level'] for k in PRONE])
        self.assertEqual(model['areas'][106]['level'], 'Green')  # in the floodplain, on high ground

    def test_failed_gate_ships_the_noah_fallback(self):
        model, report = self.go(self.tests_in_green)
        self.assertEqual(model['source'], 'noah')
        self.assertTrue(model['version'].startswith('noah_fallback@'))
        self.assertFalse(report['acceptance']['adopted'])
        self.assertTrue(report['acceptance']['reasons'])

    def test_every_area_has_a_level_or_a_reason(self):
        for tests in (self.tests_ok, self.tests_in_green):
            model, _ = self.go(tests)
            self.assertEqual(set(model['areas']), {100 + k for k in range(20)})
            for a in model['areas'].values():
                self.assertTrue((a['level'] in ('Red', 'Orange', 'Green')) != bool(a['not_assessed_reason']), a)
            self.assertTrue(model['areas'][119]['estimated_outline'])

    def test_no_raw_points_in_the_written_files(self):
        model, report = self.go(self.tests_ok)
        text = json.dumps([model, report])
        for s in self.spots:
            self.assertNotIn(str(s['lat']), text)
            self.assertNotIn(str(s['lon']), text)

    def test_the_model_file_holds_no_domain_outline(self):
        # The domain is the spots' hull buffered 300 m: its arcs are centred on survey spots, so its outline
        # would give them away even when rounded
        model, report = self.go(self.tests_ok)
        self.assertNotIn('area_wkt', model['domain'])
        self.assertNotIn('POLYGON', json.dumps([model, report]))
        self.assertEqual(model['domain']['buffer_m'], 300)

    def test_gate_one_says_why_it_is_judged_on_auc(self):
        _, report = self.go(self.tests_ok)
        self.assertIn('Judged on AUC', report['acceptance']['gates'][0]['detail'])

    def test_no_test_points_fail_gate_two(self):
        model, report = self.go({**self.tests_ok, 'geoalert_points': []})
        gate = report['acceptance']['gates'][1]
        self.assertEqual((gate['passed'], gate['detail']), (False, '0 of 0'))
        self.assertFalse(report['acceptance']['adopted'])
        self.assertEqual(model['source'], 'noah')

    def test_version_changes_with_the_run_settings_and_the_code(self):
        # The log keeps one row per area and version: a rerun that can give other classes needs another version
        def version(reps=40, stability_reps=4):
            return run(self.features, self.spots, self.city, lambda: self.tests_ok, log=lambda msg: None,
                       fingerprint='synthetic', reps=reps, stability_reps=stability_reps)[0]['version'].split('@')[1]

        base = version()
        with mock.patch.object(flood_run, 'code_digest', return_value='other code'):
            other_code = version()
        self.assertEqual(len({base, version(reps=41), version(stability_reps=5), other_code}), 4)
        self.assertEqual(version(), base)

    def test_the_fallback_says_how_much_it_flags(self):
        # The user's ruling (2026-11-24): the NOAH fallback keeps its breadth, and the card says how broad it is
        _, report = self.go(self.tests_in_green)
        levels = report['classes']['levels']
        flagged = sum(levels[k]['buildings'] for k in ('Red', 'Orange') if k in levels)
        share = flagged / sum(v['buildings'] for v in levels.values())
        self.assertAlmostEqual(report['fallback']['flagged_share'], share, places=4)
        self.assertIn(f'It flags about {share:.0%} of the assessed buildings as Red or Orange',
                      report['fallback']['note'])

    def test_mananga_points_carry_the_level_that_ships(self):
        # Under the NOAH fallback the test levels are the rejected model's; the card also needs the map's own
        for tests in (self.tests_ok, self.tests_in_green):
            model, report = self.go(tests)
            points = report['temporal_test']['mananga_points']
            self.assertTrue(points)
            for p in points:
                self.assertEqual(p['published_level'], model['areas'][p['purok_id']]['level'])
