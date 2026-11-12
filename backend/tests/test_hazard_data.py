import tempfile
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np

from django.contrib.gis.geos import MultiPolygon
from django.test import SimpleTestCase, TestCase

from apps.barangays.models import Barangay
from apps.hazards.models import HazardType
from apps.history.hazard_data import (
    RAIN_FEATURES, STUDY_END, STUDY_START, TERRAIN_COLUMNS, TERRAIN_FEATURES, Record, build_dataset, load_exclusions,
    load_records, positives, rain_windows, read_terrain, records_signature, terrain_shares, write_terrain)
from apps.history.models import HistoricalRecord
from tests.fire_setup import box
from tests.hazard_fixtures import toy_inputs


def rec(ref, barangay, day, sample=False):
    return Record(source_ref=ref, hazard='Flood', barangay_id=barangay, day=day, subtype='', is_sample=sample)


class RainWindowTests(SimpleTestCase):
    def test_windows_are_inclusive_sums_ending_on_the_day(self):
        daily = {date(2024, 1, i): float(i) for i in range(1, 21)}
        w = rain_windows(daily, date(2024, 1, 14))
        self.assertEqual(w, {'r0': 14, 'r1': 13, 'r3': 39, 'r7': 77, 'r14': 105})

    def test_a_missing_day_makes_the_row_missing(self):
        daily = {date(2024, 1, i): 1.0 for i in range(1, 21)}
        daily[date(2024, 1, 9)] = None
        self.assertIsNone(rain_windows(daily, date(2024, 1, 14)))
        self.assertIsNone(rain_windows(daily, date(2024, 1, 5)))   # window reaches before the data


class PositiveTests(SimpleTestCase):
    def test_rules(self):
        recs = [rec('a', 1, date(2021, 6, 12)), rec('b', 1, date(2021, 6, 12)),      # same barangay-day: one row
                rec('c', None, date(2021, 6, 12)), rec('d', 2, date(2022, 7, 8)),    # no barangay; excluded ref
                rec('e', 2, date(2026, 1, 3)), rec('f', 2, date(2023, 6, 26), sample=True)]
        got = positives(recs, {1, 2}, STUDY_START, STUDY_END, excluded={'d'})
        self.assertEqual(got, {(1, date(2021, 6, 12))})

    def test_exclusions_file_lists_the_four_jul_2022_records(self):
        self.assertEqual(set(load_exclusions()), {
            'flood-landslide:d2d9fa7d9b088324', 'flood-landslide:ba57920aece010af',
            'flood-landslide:a0c6189d03dfc448', 'flood-landslide:aaa56259189e9d34'})


class RecordDayTests(TestCase):
    def test_day_is_manila_local(self):
        flood = HazardType.objects.create(name='Flood', logo_class='x')
        brgy = Barangay.objects.create(name='B', municipality='Talisay',
                                       boundary=MultiPolygon(box(-500, -500, 500, 500), srid=4326))
        HistoricalRecord.objects.create(
            barangay=brgy, hazard_type=flood, severity_level='Green',
            occurred_at=datetime(2022, 7, 7, 16, 0, tzinfo=timezone.utc), source_ref='x:1')
        got = load_records('Flood')
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0].day, date(2022, 7, 8))
        self.assertEqual(got[0].barangay_id, brgy.id)


class TerrainTests(SimpleTestCase):
    def test_terrain_shares_on_a_toy_grid(self):
        labels = np.array([[1, 1, 2, 2], [1, 1, 2, 0]])
        f = {k: np.zeros((2, 4)) for k in ('hand', 'elevation', 'dist_water', 'dist_coast',
                                           'building_density', 'slope', 'relief', 'dist_road')}
        f['hand'][:] = [[1, 3, 6, 1], [1, 1, 9, 0]]
        f['slope'][:] = [[20, 35, 0, 19], [0, 0, 40, 90]]
        f['building_density'][:] = [[4, 0, 10, 0], [0, 0, 20, 99]]
        rows = terrain_shares(labels, f, [1, 2])
        self.assertEqual(rows[1]['hand_lt2'], 0.75)         # 3 of 4 cells
        self.assertAlmostEqual(rows[2]['hand_lt2'], 1 / 3)  # label-0 cell ignored
        self.assertEqual(rows[1]['slope_gt18'], 0.5)
        self.assertEqual(rows[1]['slope_gt30'], 0.25)
        self.assertEqual(rows[2]['built_density'], 10.0)    # mean of 10, 0, 20
        self.assertEqual(rows[1]['cells'], 4)

    def test_terrain_csv_round_trip(self):
        feats = TERRAIN_FEATURES['Flood'] + TERRAIN_FEATURES['Landslide']
        rows = {7: {'cells': 123, **{k: (i + 1) / 7 for i, k in enumerate(feats)}},
                9: {'cells': 5, **{k: 0.0 for k in feats}}}
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 't.csv'
            write_terrain(path, rows, {7: 'Alpha', 9: 'Beta'})
            self.assertEqual(read_terrain(path), rows)


class DatasetTests(SimpleTestCase):
    def test_rows_features_and_targets(self):
        terrain, rain, pos = toy_inputs(n_barangays=2, start=date(2024, 1, 1), end=date(2024, 1, 10))
        ds, dropped = build_dataset('Flood', terrain, rain, pos, date(2024, 1, 1), date(2024, 1, 10))
        self.assertEqual(ds.features, RAIN_FEATURES + TERRAIN_FEATURES['Flood'])
        self.assertEqual(ds.X.shape, (20, 11))
        self.assertEqual(ds.X.dtype, np.float64)
        self.assertEqual(len(ds.y) + dropped, 20)
        self.assertEqual(dropped, 0)
        self.assertEqual(int(ds.y.sum()), len({p for p in pos if date(2024, 1, 1) <= p[1] <= date(2024, 1, 10)}))
        self.assertEqual(ds.barangay_id.tolist(), [1] * 10 + [2] * 10)
        self.assertEqual(ds.day.dtype, np.dtype('datetime64[D]'))
        self.assertEqual(ds.day[0], np.datetime64('2024-01-01'))
        self.assertEqual(ds.day[9], np.datetime64('2024-01-10'))
        row = ds.X[0]
        w = rain_windows(rain[1], date(2024, 1, 1))
        self.assertEqual(list(row[:5]), [w[k] for k in RAIN_FEATURES])
        self.assertEqual(list(row[5:]), [terrain[1][k] for k in TERRAIN_FEATURES['Flood']])
        for (b, d) in pos:
            if date(2024, 1, 1) <= d <= date(2024, 1, 10):
                i = (b - 1) * 10 + (d - date(2024, 1, 1)).days
                self.assertEqual(int(ds.y[i]), 1)

    def test_barangay_missing_from_terrain_or_rain_is_left_out(self):
        terrain, rain, pos = toy_inputs(n_barangays=3, start=date(2024, 1, 1), end=date(2024, 1, 5))
        del terrain[2]
        del rain[3]
        ds, dropped = build_dataset('Landslide', terrain, rain, pos, date(2024, 1, 1), date(2024, 1, 5))
        self.assertEqual(set(ds.barangay_id.tolist()), {1})
        self.assertEqual(len(ds.y), 5)
        self.assertEqual(dropped, 0)
        self.assertEqual(ds.features, RAIN_FEATURES + TERRAIN_FEATURES['Landslide'])

    def test_rows_with_missing_rain_are_dropped_and_counted(self):
        terrain, rain, pos = toy_inputs(n_barangays=1, start=date(2024, 1, 1), end=date(2024, 1, 10))
        rain[1][date(2024, 1, 6)] = None
        ds, dropped = build_dataset('Flood', terrain, rain, pos, date(2024, 1, 1), date(2024, 1, 10))
        # day 1/6 is in the window of 1/6 .. 1/19, so 1/6..1/10 lose their row; 1/1..1/5 keep theirs
        self.assertEqual(dropped, 5)
        self.assertEqual(len(ds.y), 5)

    def test_subset_and_years(self):
        terrain, rain, pos = toy_inputs(n_barangays=2, start=date(2021, 12, 29), end=date(2022, 1, 3))
        ds, _ = build_dataset('Flood', terrain, rain, pos, date(2021, 12, 29), date(2022, 1, 3))
        self.assertEqual(ds.years.tolist(), [2021] * 3 + [2022] * 3 + [2021] * 3 + [2022] * 3)
        sub = ds.subset(ds.years == 2022)
        self.assertEqual(len(sub.y), 6)
        self.assertEqual(sub.features, ds.features)
        self.assertEqual(sub.X.shape, (6, 11))
        self.assertEqual(len(ds.y), 12)


class ToyInputsTests(SimpleTestCase):
    def test_deterministic_and_positives_on_heavy_days_every_year(self):
        a = toy_inputs()
        b = toy_inputs()
        self.assertEqual(a[2], b[2])
        self.assertEqual(a[1], b[1])
        terrain, rain, pos = a
        self.assertEqual(set(terrain), {1, 2, 3})
        self.assertIn(date(2020, 12, 19), rain[1])
        self.assertIn(date(2025, 12, 31), rain[1])
        self.assertEqual({p[1].year for p in pos}, {2021, 2022, 2023, 2024, 2025})
        for bid, day in pos:
            self.assertGreaterEqual(rain[bid][day], 50)
        for col in TERRAIN_COLUMNS:
            self.assertEqual(len({terrain[b][col] for b in terrain}), 3, col)
        self.assertIn('cells', terrain[1])
        self.assertEqual(len({terrain[b]['cells'] for b in terrain}), 3)
        self.assertGreater(terrain[1]['hand_lt2'], terrain[3]['hand_lt2'])
        ds, dropped = build_dataset('Flood', terrain, rain, pos, STUDY_START, STUDY_END)
        self.assertEqual(dropped, 0)
        self.assertEqual(len(ds.y), 3 * 1826)


class SignatureTests(SimpleTestCase):
    def base(self):
        return [rec('a', 1, date(2022, 6, 1)), rec('b', None, date(2023, 6, 1)),
                rec('s', 2, date(2023, 7, 1), sample=True)]

    def test_signature_changes_with_study_records_only(self):
        recs = self.base()
        sig = records_signature(recs, STUDY_START, STUDY_END)
        self.assertEqual(len(sig), 40)
        self.assertEqual(sig, records_signature(list(reversed(recs)), STUDY_START, STUDY_END))
        self.assertEqual(sig, records_signature(recs + [rec('z', 3, date(2022, 1, 1), sample=True)],
                                                STUDY_START, STUDY_END))
        self.assertNotEqual(sig, records_signature(recs + [rec('c', 1, date(2024, 1, 1))], STUDY_START, STUDY_END))
        self.assertNotEqual(sig, records_signature(recs[1:], STUDY_START, STUDY_END))
        self.assertNotEqual(sig, records_signature([rec('a', 2, date(2022, 6, 1))] + recs[1:],
                                                   STUDY_START, STUDY_END))
        self.assertNotEqual(sig, records_signature([rec('a', 1, date(2022, 6, 2))] + recs[1:],
                                                   STUDY_START, STUDY_END))
        self.assertNotEqual(sig, records_signature([rec('b', 4, date(2023, 6, 1))] + recs[:1],
                                                   STUDY_START, STUDY_END))

    def test_signature_ignores_records_after_study_end(self):
        recs = self.base()
        sig = records_signature(recs, STUDY_START, STUDY_END)
        self.assertEqual(sig, records_signature(recs + [rec('new', 1, date(2026, 2, 1))], STUDY_START, STUDY_END))
        self.assertEqual(sig, records_signature(recs + [rec('old', 1, date(2020, 12, 31))], STUDY_START, STUDY_END))
