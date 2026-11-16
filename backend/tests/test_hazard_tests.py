import math
from datetime import date, timedelta
from unittest import mock

import numpy as np
from django.test import SimpleTestCase

from apps.history import hazard_tests, two_part
from apps.history.hazard_data import STUDY_END, STUDY_START, Record
from apps.history.hazard_models import CannotEvaluate, benchmark_probs
from apps.history.landslide_catalogue import CatalogueRecord, era_end
from apps.history.rain import RainFile
from apps.history.storms import StormDays
from apps.history.hazard_tests import (
    BASELINES, BUFFER_DAYS, BarangayRate, Block, Climatology, LeakageError, LogisticContender, PagasaBands,
    Persistence, RainOnly, ReturnLevel, SevenDayP95, TwoPartContender, assign_blocks, baselines,
    build_hazard_data, cluster_bootstrap, event_clusters, loso_blocks, out_of_fold, train_mask, yearly_folds)
from tests.hazard_fixtures import toy_event_records, toy_inputs

FLOOD_DAYS = [date(2022, 7, 1), date(2025, 8, 12), date(2025, 8, 18), date(2025, 10, 7), date(2025, 11, 4)]
NAMES = {1: 'Manipis', 2: 'Lagtang', 3: 'Tapul'}


def study_days():
    return [STUDY_START + timedelta(days=i) for i in range((STUDY_END - STUDY_START).days + 1)]


def exposure_rows(values):
    return {b: {'buildings': 1000.0, 'noah25_mh': e, 'noah100_mh': e, 'hand_lt2_buildings': e, 'exposure': e}
            for b, e in values.items()}


def rain_file(rain):
    first = min(min(s) for s in rain.values())
    last = max(max(s) for s in rain.values())
    return RainFile(rain, {b: (10.5, 123.75) for b in rain}, first, last)


def toy_flood(n=3, seed=0):
    """build_hazard_data on toy_inputs: storms flag every event day and every 40th day."""
    terrain, rain, pos = toy_inputs(n_barangays=n, seed=seed)
    stormy = {d for _, d in pos} | {STUDY_START + timedelta(days=i) for i in range(0, 1826, 40)}
    storms = StormDays({d: ('S1', 'TOY', 100.0) for d in stormy}, date(2020, 12, 1), STUDY_END)
    exposure = exposure_rows({b: 300.0 / b for b in terrain})
    return build_hazard_data('Flood', terrain, rain_file(rain), storms, exposure,
                             toy_event_records('Flood', pos), set())


def toy_landslide(n=3, seed=1, far_latest=None):
    """build_hazard_data on toy_inputs from 2007 with a small fake catalogue (2008-2017). `far_latest`: the day
    of a record about 111 km away that is the whole catalogue's latest; near() never keeps it, but it sets the
    catalogue era's end."""
    terrain, rain, pos = toy_inputs(n_barangays=n, start=date(2007, 1, 1), seed=seed)
    heavy = sorted({d for _, d in pos if 2008 <= d.year <= 2016})
    catalogue = []
    for i, d in enumerate(heavy[::3]):
        place = 'Landslide in Manipis, Talisay City' if i % 2 == 0 else 'Landslide near Cebu City'
        catalogue.append(CatalogueRecord(f'c{i}', d, 10.25, 123.85, 'exact', place, place))
    catalogue.append(CatalogueRecord('c-last', date(2017, 3, 9), 10.25, 123.85, 'exact', 'Slide', 'Slide'))
    whole = catalogue + ([CatalogueRecord('c-far', far_latest, 11.25, 123.85, 'exact', 'Far', 'Far')]
                         if far_latest else [])
    return build_hazard_data('Landslide', terrain, rain_file(rain), None, None,
                             toy_event_records('Landslide', pos), set(), catalogue=catalogue, names=NAMES,
                             catalogue_end=era_end(whole)), catalogue


def custom_data(hazard, wet=None, events=(), steep=None, n=3, storm_days=(), storms_end=STUDY_END,
                exposure=None, excluded=()):
    """Every barangay reads one series: 0 mm except `wet`. `events` are (barangay or None, day) records."""
    first = date(2020, 12, 1)
    series = {first + timedelta(days=i): 0.0 for i in range((STUDY_END - first).days + 1)}
    series.update(wet or {})
    rain = {b: dict(series) for b in range(1, n + 1)}
    terrain, _, _ = toy_inputs(n_barangays=n, start=date(2024, 1, 1), end=date(2024, 1, 20))
    for b, s in (steep or {}).items():
        terrain[b]['slope_gt18'] = s
    storms = StormDays({d: ('S1', 'TOY', 100.0) for d in storm_days}, first, storms_end)
    if exposure is None:
        exposure = exposure_rows({b: 100.0 * (n + 1 - b) for b in terrain})
    records = [Record(f'ev-{i}', hazard, b, d, 'TOY', False) for i, (b, d) in enumerate(events)]
    return build_hazard_data(hazard, terrain, rain_file(rain), storms if hazard == 'Flood' else None,
                             exposure if hazard == 'Flood' else None, records, set(excluded))


def city_dates(data):
    return data.city_day.astype(object)


class BlockTests(SimpleTestCase):
    def test_flood_clusters_merge_days_under_14_apart(self):
        days = [date(2022, 7, 1), date(2025, 8, 12), date(2025, 8, 18), date(2025, 10, 7), date(2025, 11, 4)]
        self.assertEqual(len(event_clusters(days)), 4)
        self.assertEqual(event_clusters(days)[1], [date(2025, 8, 12), date(2025, 8, 18)])
        # exactly 14 days apart is not "less than 14": two clusters; 13 days apart merge
        self.assertEqual(len(event_clusters([date(2023, 3, 1), date(2023, 3, 15)])), 2)
        self.assertEqual(len(event_clusters([date(2023, 3, 1), date(2023, 3, 14)])), 1)
        # chained: each step under 14 days, so one cluster though the ends are 24 days apart
        self.assertEqual(len(event_clusters([date(2023, 3, 1), date(2023, 3, 13), date(2023, 3, 25)])), 1)

    def test_blocks_cover_every_day_once(self):
        days = study_days()
        events = FLOOD_DAYS + [date(2023, 3, 1), date(2023, 3, 15)]       # blocks of the last two would touch
        blocks = loso_blocks(days, events)
        event_blocks = [b for b in blocks if b.kind == 'event']
        self.assertEqual(len(event_blocks), 6)
        owner = assign_blocks(np.array(days, dtype='datetime64[D]'), blocks)
        self.assertTrue((owner >= 0).all())
        for d, i in zip(days, owner):
            in_event = [b for b in event_blocks if b.start <= d <= b.end]
            self.assertLessEqual(len(in_event), 1, d)
            if in_event:
                self.assertIs(blocks[i], in_event[0])
            else:
                months = [b for b in blocks if b.kind == 'month' and b.start <= d <= b.end]
                self.assertEqual(months, [blocks[i]], d)
                self.assertEqual(blocks[i].label, f'{d.year}-{d.month:02d}')
        self.assertEqual(sum(1 for b in blocks if b.kind == 'month'), 60)   # every month keeps some days
        touching = [b for b in event_blocks if b.label.startswith('2023-03')]
        self.assertEqual(touching[0].end, date(2023, 3, 8))
        self.assertEqual(touching[1].start, date(2023, 3, 9))             # clipped, not shared

    def test_event_block_is_padded_seven_days(self):
        blocks = loso_blocks(study_days(), FLOOD_DAYS)
        aug = [b for b in blocks if b.kind == 'event' and b.start.month == 8]
        self.assertEqual(aug, [Block('2025-08-12..2025-08-18', 'event', date(2025, 8, 5), date(2025, 8, 25))])
        single = [b for b in blocks if b.kind == 'event' and b.start.year == 2022]
        self.assertEqual(single, [Block('2022-07-01', 'event', date(2022, 6, 24), date(2022, 7, 8))])
        # what is left of August is its month block: Aug 1-4 and Aug 26-31
        month = next(b for b in blocks if b.label == '2025-08')
        self.assertEqual((month.start, month.end), (date(2025, 8, 1), date(2025, 8, 31)))
        aug_days = np.array([date(2025, 8, d) for d in range(1, 32)], dtype='datetime64[D]')
        owner = assign_blocks(aug_days, blocks)
        self.assertEqual([blocks[i].kind for i in owner], ['month'] * 4 + ['event'] * 21 + ['month'] * 6)

    def test_training_never_touches_the_buffer(self):
        days = np.array(study_days(), dtype='datetime64[D]')
        blocks = loso_blocks(study_days(), FLOOD_DAYS)
        owner = assign_blocks(days, blocks)
        for i, block in enumerate(blocks):
            train = train_mask(days, block)
            held = days[owner == i]
            self.assertTrue(len(held))
            gaps = np.abs(days[train][:, None] - held[None, :]).astype(int)
            self.assertGreater(gaps.min(), BUFFER_DAYS, block.label)
            self.assertFalse(train[owner == i].any())
        block = Block('2023-06', 'month', date(2023, 6, 1), date(2023, 6, 30))
        mask = dict(zip(days.astype(object), train_mask(days, block)))
        self.assertFalse(mask[date(2023, 5, 18)])     # 14 days before: buffer
        self.assertTrue(mask[date(2023, 5, 17)])      # 15 days before: training
        self.assertFalse(mask[date(2023, 7, 14)])
        self.assertTrue(mask[date(2023, 7, 15)])


class _Recorder:
    """A contender that records each fit and predicts the number of training days, so rows show their block."""
    name = 'recorder'

    def __init__(self):
        self.fits = []

    def fit(self, data, train):
        self.fits.append(train.copy())
        return int(train.sum())

    def predict(self, fitted, data, days):
        return np.full(int(np.isin(data.rows.day, days).sum()), float(fitted))


class OutOfFoldTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.flood = toy_flood()

    def test_out_of_fold_gives_every_row_one_chance_and_raises_on_leakage(self):
        data = self.flood
        blocks = hazard_tests.blocks_for(data)
        rec = _Recorder()
        p = out_of_fold(rec, data, blocks)
        self.assertEqual(p.shape, data.rows.y.shape)
        self.assertFalse(np.isnan(p).any())
        owner = assign_blocks(data.city_day, blocks)
        used = [i for i in range(len(blocks)) if (owner == i).any()]
        self.assertEqual(len(rec.fits), len(used))                  # one fit per block that holds days
        row_owner = assign_blocks(data.rows.day, blocks)
        for i in used:
            expected = train_mask(data.city_day, blocks[i]).sum()
            np.testing.assert_array_equal(p[row_owner == i], expected)
        with mock.patch.object(hazard_tests, 'train_mask', lambda days, block: np.ones(len(days), bool)):
            with self.assertRaises(LeakageError):
                out_of_fold(_Recorder(), data, blocks)

    def test_buffer_check_measures_from_the_held_out_days_too(self):
        days = np.array(study_days(), dtype='datetime64[D]')
        block = Block('2023-06', 'month', date(2023, 6, 1), date(2023, 6, 30))
        train = train_mask(days, block)
        hazard_tests._check_buffer(days, train, block, days[(days >= np.datetime64('2023-06-01'))
                                                             & (days <= np.datetime64('2023-06-30'))])
        # a block whose dates do not cover its held-out days: 2023-08-10 is held, and training resumes on
        # 2023-07-15, so 2023-07-27 is the first training day within 14 days of a held-out day
        wrong = np.array(['2023-06-15', '2023-08-10'], dtype='datetime64[D]')
        with self.assertRaisesRegex(LeakageError, '2023-07-27'):
            hazard_tests._check_buffer(days, train, block, wrong)

    def test_every_flood_model_gives_every_row_a_chance(self):
        data = self.flood
        blocks = hazard_tests.blocks_for(data)
        models = [TwoPartContender('Flood'), LogisticContender('Flood')] + baselines('Flood')
        self.assertEqual([m.name for m in models[2:]], list(BASELINES['Flood']))
        for model in models:
            p = out_of_fold(model, data, blocks)
            self.assertEqual(len(p), len(data.rows.y), model.name)
            self.assertTrue(np.isfinite(p).all(), model.name)
            self.assertTrue(((p >= 0) & (p <= 1)).all(), model.name)

    def test_yearly_folds_train_on_the_years_before(self):
        folds = yearly_folds(LogisticContender('Flood'), self.flood)
        self.assertEqual([f['test_year'] for f in folds], [2023, 2024, 2025])
        self.assertEqual([tuple(f['train_years']) for f in folds], [(2021, 2022), (2021, 2022, 2023),
                                                                    (2021, 2022, 2023, 2024)])
        years = self.flood.rows.years
        for f in folds:
            np.testing.assert_array_equal(f['rows'], years == f['test_year'])
            self.assertEqual(len(f['p']), int(f['rows'].sum()))
            self.assertGreater(f['train_event_days'], 0)
            self.assertGreater(f['test_event_days'], 0)

    def test_two_part_contender_refits_lambda_from_training_events_only(self):
        data = self.flood
        blocks = [b for b in hazard_tests.blocks_for(data) if b.kind == 'event']
        everything = np.ones(len(data.city_day), bool)
        lam_all = TwoPartContender('Flood').fit(data, everything).lam
        changed = 0
        for block in blocks:
            train = train_mask(data.city_day, block)
            hits = data.rows.y[np.isin(data.rows.day, data.city_day[train])].sum()
            _, lam = two_part.flood_shares(data.place, hits / data.city_y[train].sum())
            with mock.patch.object(hazard_tests, 'fit_when', wraps=two_part.fit_when) as spy:
                fitted = TwoPartContender('Flood').fit(data, train)
            self.assertAlmostEqual(fitted.lam, lam, places=12)
            self.assertEqual(len(spy.call_args.args[1]), int(train.sum()))   # "when" sees training days only
            self.assertEqual(fitted.when.features, ('log1p_r3', 'storm72'))
            changed += not math.isclose(fitted.lam, lam_all)
        self.assertGreater(changed, 0)
        rain_only = RainOnly().fit(data, everything)
        self.assertEqual(rain_only.when.features, ('log1p_r3',))
        self.assertEqual(rain_only.shares, TwoPartContender('Flood').fit(data, everything).shares)

    def test_flood_k_counts_an_event_day_that_names_no_barangay(self):
        days = [date(2021, 8, 1), date(2022, 8, 1), date(2023, 8, 1), date(2024, 8, 1)]
        wet = {d: 60.0 for d in days} | {date(2021, 3, 3): 45.0, date(2023, 2, 2): 50.0}
        data = custom_data('Flood', wet=wet, storm_days=days + [date(2022, 4, 4), date(2024, 9, 9)],
                           events=[(1, days[0]), (2, days[1]), (3, days[2]), (None, days[3])])
        fitted = TwoPartContender('Flood').fit(data, np.ones(len(data.city_day), bool))
        # 3 barangay-day hits on 4 event days: k = 3/4, the unnamed day counting with 0 hits
        _, lam = two_part.flood_shares(data.place, 3 / 4)
        self.assertAlmostEqual(fitted.lam, lam, places=12)
        self.assertAlmostEqual(sum(fitted.shares.values()), 3 / 4, places=9)
        self.assertAlmostEqual(Climatology().fit(data, np.ones(len(data.city_day), bool))['k'], 3 / 4)


class LandslideTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.data, cls.catalogue = toy_landslide()

    def test_catalogue_era_rows(self):
        data = self.data
        self.assertEqual(data.extra_day[0], np.datetime64('2007-01-01'))
        self.assertEqual(data.extra_day[-1], np.datetime64('2017-03-31'))     # end of the last record's month
        self.assertEqual(int(data.extra_y.sum()), len({r.day for r in self.catalogue}))
        named = [r.day for i, r in enumerate(self.catalogue[:-1]) if i % 2 == 0]
        self.assertEqual(data.extra_named, [(d, {1}) for d in sorted(named)])
        self.assertEqual(data.extra_X.shape, (len(data.extra_day), 2))
        self.assertTrue((data.city_day >= np.datetime64('2021-01-01')).all())

    def test_catalogue_era_ends_with_the_whole_catalogue_not_the_last_nearby_record(self):
        # spec 1.4: the era runs to the end of the month of the catalogue's latest record, here one far from
        # Talisay, so the quiet days after the last nearby record (2017-03-09) are catalogue days with no event
        data, catalogue = toy_landslide(far_latest=date(2017, 9, 28))
        self.assertEqual(data.extra_day[0], np.datetime64('2007-01-01'))
        self.assertEqual(data.extra_day[-1], np.datetime64('2017-09-30'))
        after = data.extra_day > np.datetime64('2017-03-09')
        self.assertEqual(int(after.sum()), (date(2017, 9, 30) - date(2017, 3, 9)).days)
        self.assertEqual(int(data.extra_y[after].sum()), 0)
        self.assertEqual(int(data.extra_y.sum()), len({r.day for r in catalogue}))     # the far record is no event
        # a catalogue without its era's end is refused rather than ended at the last nearby record
        terrain, rain, pos = toy_inputs(n_barangays=3, start=date(2007, 1, 1), seed=1)
        with self.assertRaisesRegex(ValueError, "catalogue era's end"):
            build_hazard_data('Landslide', terrain, rain_file(rain), None, None, toy_event_records('Landslide', pos),
                              set(), catalogue=catalogue, names=NAMES)

    def test_landslide_catalogue_rows_are_always_in_training(self):
        data = self.data
        n_extra = len(data.extra_y)
        block = next(b for b in hazard_tests.blocks_for(data) if b.kind == 'event')
        for train in (train_mask(data.city_day, block), data.city_day.astype('datetime64[Y]').astype(int) < 52):
            with mock.patch.object(hazard_tests, 'fit_when', wraps=two_part.fit_when) as when_spy, \
                    mock.patch.object(hazard_tests, 'landslide_shares', wraps=two_part.landslide_shares) as where_spy:
                fitted = TwoPartContender('Landslide').fit(data, train)
            X, y = when_spy.call_args.args
            era = when_spy.call_args.kwargs['era']
            self.assertEqual(len(y), int(train.sum()) + n_extra)
            self.assertEqual(int((era == 'catalogue').sum()), n_extra)
            np.testing.assert_array_equal(y[era == 'catalogue'], data.extra_y)
            self.assertEqual(set(fitted.when.intercepts), {'geoalert', 'catalogue'})
            events = where_spy.call_args.args[1]
            kept = set(data.city_day[train].astype(object))
            expected = [s for d, s in data.named_events if d in kept] + [s for _, s in data.extra_named]
            self.assertEqual(sorted(map(sorted, events)), sorted(map(sorted, expected)))
            # k: GeoAlert hits on all GeoAlert training event days plus catalogue named hits, over both day counts
            geo_hits = data.rows.y[np.isin(data.rows.day, data.city_day[train])].sum()
            cat_hits = sum(len(s) for _, s in data.extra_named)
            k = (geo_hits + cat_hits) / (data.city_y[train].sum() + len(data.extra_named))
            self.assertAlmostEqual(where_spy.call_args.args[2], k, places=12)
            # the baselines never use the catalogue: GeoAlert hits over GeoAlert event days only
            self.assertAlmostEqual(Climatology().fit(data, train)['k'], geo_hits / data.city_y[train].sum())
        # the current model never sees the catalogue era
        self.assertTrue((data.rows.day >= np.datetime64('2021-01-01')).all())
        folds = yearly_folds(TwoPartContender('Landslide'), data)
        self.assertEqual(len(folds), 3)

    def test_every_landslide_model_gives_every_row_a_chance(self):
        data = self.data
        blocks = hazard_tests.blocks_for(data)
        models = [TwoPartContender('Landslide'), LogisticContender('Landslide')] + baselines('Landslide')
        self.assertEqual([m.name for m in models[2:]], list(BASELINES['Landslide']))
        for model in models:
            p = out_of_fold(model, data, blocks)
            self.assertTrue(np.isfinite(p).all(), model.name)
            self.assertTrue(((p >= 0) & (p <= 1)).all(), model.name)


class BuildDataTests(SimpleTestCase):
    def test_flood_when_counts_records_without_a_barangay(self):
        d1, d2, d3, d4 = date(2022, 3, 1), date(2023, 4, 2), date(2024, 5, 3), date(2024, 6, 4)
        data = custom_data('Flood', wet={d1: 40.0, date(2022, 2, 28): 10.0}, storm_days=[d1],
                           events=[(1, d1), (2, d1), (None, d2), (3, d3), (1, d4)], excluded={'ev-4'},
                           storms_end=date(2025, 12, 20))
        days = city_dates(data)
        self.assertEqual(days[0], STUDY_START)
        self.assertEqual(days[-1], date(2025, 12, 20))                     # storm coverage ends here
        self.assertEqual(set(np.unique(data.rows.day)), set(data.city_day))
        self.assertEqual(len(data.rows.y), 3 * len(data.city_day))
        hit = dict(zip(days, data.city_y))
        self.assertEqual([hit[d] for d in (d1, d2, d3, d4)], [1, 1, 1, 0])  # d4's record is excluded
        self.assertEqual(int(data.city_y.sum()), 3)
        self.assertEqual(int(data.rows.y.sum()), 3)                        # (1, d1), (2, d1), (3, d3)
        self.assertEqual(data.named_events, [(d1, {1, 2}), (d3, {3})])
        i = list(days).index(d1)
        np.testing.assert_allclose(data.city_X[i], [math.log1p(50.0), 1.0])
        self.assertEqual(data.place, {1: 300.0, 2: 200.0, 3: 100.0})
        self.assertIsNone(data.extra_day)
        self.assertEqual([r.source_ref for r in data.records], ['ev-0', 'ev-1', 'ev-2', 'ev-3'])

    def test_flood_refuses_a_barangay_without_exposure(self):
        with self.assertRaisesRegex(ValueError, 'exposure'):
            custom_data('Flood', events=[(1, date(2022, 3, 1))], exposure=exposure_rows({1: 5.0, 2: 6.0}))

    def test_landslide_place_is_the_steep_share(self):
        data = custom_data('Landslide', events=[(1, date(2022, 3, 1))], steep={1: 0.6, 2: 0.3, 3: 0.05})
        self.assertEqual(data.place, {1: 0.6, 2: 0.3, 3: 0.05})
        self.assertIsNone(data.extra_day)
        self.assertEqual(data.extra_named, [])


class BaselineTests(SimpleTestCase):
    def test_pagasa_bands_use_the_half_and_one_smoothing(self):
        d1, d2, d3, d4 = date(2021, 3, 10), date(2022, 5, 10), date(2023, 6, 10), date(2025, 6, 15)
        d5 = date(2024, 2, 2)
        data = custom_data('Flood', wet={d1: 60.0, d2: 50.0, d3: 99.9, d4: 75.0, d5: 100.0},
                           events=[(1, d1)])
        block = Block('2025-06', 'month', date(2025, 6, 1), date(2025, 6, 30))
        train = train_mask(data.city_day, block)
        fitted = PagasaBands().fit(data, train)
        n_low = int(train.sum()) - 4
        # bands [0, 50), [50, 100), [100, 200), [200, inf): 50 mm is in the second, 100 mm in the third
        np.testing.assert_allclose(fitted['chances'], [0.5 / (n_low + 1), 1.5 / 4, 0.5 / 2, 0.5 / 1])
        p = PagasaBands().predict(fitted, data, np.array([d4], dtype='datetime64[D]'))
        np.testing.assert_allclose(p, [1.5 / 4 * 1.0 / 3] * 3)    # k = 1 barangay per event day, 3 barangays

    def test_climatology_persistence_and_rate(self):
        e1, e2, e3 = date(2022, 3, 1), date(2022, 3, 2), date(2023, 5, 1)
        data = custom_data('Flood', events=[(1, e1), (2, e2), (1, e3), (None, date(2023, 9, 9))])
        block = Block('2025-06', 'month', date(2025, 6, 1), date(2025, 6, 30))
        train = train_mask(data.city_day, block)
        n = int(train.sum())
        clim = Climatology().fit(data, train)
        self.assertAlmostEqual(clim['k'], 3 / 4)            # 3 hits on 4 event days (one names no barangay)
        june = np.array([date(2025, 6, 3)], dtype='datetime64[D]')
        # the training barangay-day event rate: 3 hits in 3 x n barangay-days
        np.testing.assert_allclose(Climatology().predict(clim, data, june), [1 / n] * 3)
        pers = Persistence().fit(data, train)
        # (events + 0.5) / (days + 1): other days, then days after an event day (03-02 event, 03-03, 05-02, 09-10)
        np.testing.assert_allclose(pers['chances'], [3.5 / (n - 4 + 1), 1.5 / 5])
        after = np.array([e2], dtype='datetime64[D]')
        np.testing.assert_allclose(Persistence().predict(pers, data, after), [1.5 / 5 * (3 / 4) / 3] * 3)
        rate = BarangayRate().fit(data, train)
        rows = data.rows
        test = np.isin(rows.day, june)
        np.testing.assert_allclose(BarangayRate().predict(rate, data, june),
                                   benchmark_probs(rows.subset(np.isin(rows.day, data.city_day[train])),
                                                   rows.subset(test)))

    def test_persistence_never_gives_exactly_zero(self):
        # no event day follows another, so a plain rate after an event day would be 0
        events = [(1, date(2022, 3, 1)), (2, date(2023, 5, 1)), (1, date(2024, 7, 1))]
        data = custom_data('Flood', events=events)
        train = np.ones(len(data.city_day), bool)
        pers = Persistence().fit(data, train)
        self.assertAlmostEqual(pers['chances'][1], 0.5 / 4)            # 3 days after an event day, 0 events
        p = Persistence().predict(pers, data, data.city_day)
        self.assertTrue((p > 0).all())

    def test_climatology_and_rate_refuse_training_without_an_event(self):
        june = Block('2025-06', 'month', date(2025, 6, 1), date(2025, 6, 30))
        for events in ([(1, date(2025, 6, 10))],                        # the only event is held out
                       [(1, date(2025, 6, 10)), (None, date(2022, 3, 1))]):   # training: an unnamed event only
            data = custom_data('Flood', events=events)
            train = train_mask(data.city_day, june)
            for model in (Climatology(), BarangayRate()):
                with self.assertRaises(CannotEvaluate, msg=(model.name, events)):
                    model.fit(data, train)

    def test_landslide_rule_on_flood_data_is_refused_before_fitting(self):
        data = custom_data('Flood', events=[(1, date(2022, 3, 1))])
        one_year = data.city_day < np.datetime64('2022-01-01')         # one complete year: _fit_city would refuse
        for rule in (ReturnLevel(), SevenDayP95()):
            with self.assertRaisesRegex(ValueError, 'landslide rule'):
                rule.fit(data, one_year)

    def test_steep_gate_includes_exactly_0_10(self):
        wet = {date(y, 7, 1): 80.0 + y - 2021 for y in range(2021, 2026)}
        data = custom_data('Landslide', wet=wet, events=[(1, date(2022, 7, 1))],
                           steep={1: 0.6, 2: 0.10, 3: 0.0999})
        train = np.ones(len(data.city_day), bool)
        for rule in (ReturnLevel(), SevenDayP95()):
            fitted = rule.fit(data, train)
            self.assertEqual(fitted['factor'], {1: 0.5, 2: 0.5, 3: 0.0}, rule.name)

    def test_rules_spread_evenly_over_the_steep_gate(self):
        first = date(2020, 12, 1)
        wet = {first + timedelta(days=i): float((i * 7) % 11) for i in range((STUDY_END - first).days + 1)}
        wet.update({date(y, 7, 1) + timedelta(days=i): 30.0 + 20 * i + (y - 2021)
                    for y in range(2021, 2026) for i in range(4)})
        data = custom_data('Landslide', wet=wet, events=[(1, date(2022, 7, 4)), (2, date(2024, 7, 3))],
                           steep={1: 0.6, 2: 0.3, 3: 0.05})
        block = Block('2025-07', 'month', date(2025, 7, 1), date(2025, 7, 31))
        train = train_mask(data.city_day, block)
        july = np.array([date(2025, 6, 20) + timedelta(days=i) for i in range(21)], dtype='datetime64[D]')
        r7 = data.window('r7')
        for rule in (ReturnLevel(), SevenDayP95()):
            fitted = rule.fit(data, train)
            p = rule.predict(fitted, data, july)
            ids = data.rows.barangay_id[np.isin(data.rows.day, july)]
            self.assertTrue((p[ids == 3] == 0).all(), rule.name)
            np.testing.assert_allclose(p[ids == 1], p[ids == 2])
            self.assertTrue((p[ids == 1] > 0).all())
            # each gated barangay gets (class chance) x k / (number gated), k = 1 barangay per event day
            allowed = [min(1.0, c * 1.0 / 2) for c in fitted['chances']]
            for v in p[ids == 1]:
                self.assertTrue(any(math.isclose(v, a, rel_tol=1e-12) for a in allowed), (rule.name, v))
            self.assertGreater(len(set(np.round(p[ids == 1], 12))), 1, rule.name)    # more than one class seen
        fitted = SevenDayP95().fit(data, train)
        self.assertAlmostEqual(fitted['p95'], float(np.percentile(r7[train], 95)))

    def test_return_level_uses_gumbel_moments_on_training_years(self):
        wet = {date(2021, 7, 1): 80.0, date(2022, 7, 1): 120.0, date(2023, 7, 1): 60.0,
               date(2023, 2, 1): 200.0, date(2024, 7, 1): 100.0, date(2025, 7, 1): 90.0}
        data = custom_data('Landslide', wet=wet, events=[(1, date(2022, 7, 1))])
        block = Block('2023-07', 'month', date(2023, 7, 1), date(2023, 7, 31))
        fitted = ReturnLevel().fit(data, train_mask(data.city_day, block))
        self.assertEqual(fitted['years'], [2021, 2022, 2024, 2025])          # 2023 is not a complete training year
        maxima = np.array([80.0, 120.0, 100.0, 90.0])
        beta = maxima.std(ddof=1) * math.sqrt(6) / math.pi
        mu = maxima.mean() - 0.5772 * beta
        t2 = mu - beta * math.log(-math.log(0.5))
        self.assertAlmostEqual(fitted['t2'], t2, places=9)
        # class >= T2: 2022-07-01 (event), 2023-02-01, 2024-07-01 -> 1.5 / 4
        self.assertAlmostEqual(fitted['chances'][2], 1.5 / 4)
        self.assertAlmostEqual(fitted['chances'][1], 0.5 / 3)            # 2021 (80), 2025 (90)


class BootstrapTests(SimpleTestCase):
    def test_bootstrap_keeps_a_day_together_and_is_seeded(self):
        days = [date(2025, 1, 1) + timedelta(days=i) for i in range(31)]
        row_day = np.repeat(np.array(days, dtype='datetime64[D]'), 3)
        rng = np.random.default_rng(5)
        losses = {'a': rng.random(len(row_day)), 'b': rng.random(len(row_day))}
        # one event block and one month block: every replicate holds every day whole, so no spread at all
        one_each = [Block('e', 'event', date(2025, 1, 10), date(2025, 1, 14)),
                    Block('2025-01', 'month', date(2025, 1, 1), date(2025, 1, 31))]
        out = cluster_bootstrap(row_day, one_each, losses, reps=200, seed=0)
        for name in losses:
            low, high = out['intervals'][name]
            self.assertAlmostEqual(low, losses[name].mean(), places=12)
            self.assertAlmostEqual(high, losses[name].mean(), places=12)
        # event blocks and month blocks are drawn separately, each keeping its count
        blocks = [Block('e', 'event', date(2025, 1, 1), date(2025, 1, 2))] + [
            Block(f'm{i}', 'month', date(2025, 1, 3 + 2 * i), date(2025, 1, 4 + 2 * i)) for i in range(3)]
        rd = np.repeat(np.array(days[:8], dtype='datetime64[D]'), 2)
        flag = {'m': (rd <= np.datetime64('2025-01-02')).astype(float)}
        low, high = cluster_bootstrap(rd, blocks, flag, reps=200, seed=3)['intervals']['m']
        self.assertAlmostEqual(low, 0.25)
        self.assertAlmostEqual(high, 0.25)
        # seeded: the same seed gives the same answer, another seed another one
        many = loso_blocks(days, [date(2025, 1, 5), date(2025, 1, 20)]) + loso_blocks(
            [date(2025, 2, 1) + timedelta(days=i) for i in range(59)], [])
        all_days = days + [date(2025, 2, 1) + timedelta(days=i) for i in range(59)]
        rd = np.repeat(np.array(all_days, dtype='datetime64[D]'), 2)
        ls = {'a': rng.random(len(rd)), 'b': rng.random(len(rd)), 'c': rng.random(len(rd))}
        first = cluster_bootstrap(rd, many, ls, reps=300, seed=0)
        self.assertEqual(first, cluster_bootstrap(rd, many, ls, reps=300, seed=0))
        self.assertNotEqual(first['intervals'], cluster_bootstrap(rd, many, ls, reps=300, seed=1)['intervals'])
        self.assertEqual(set(first['differences']), {(x, y) for x in ls for y in ls if x != y})
        mean, low, high = first['differences'][('a', 'b')]
        self.assertAlmostEqual(mean, ls['a'].mean() - ls['b'].mean())
        self.assertLess(low, high)
        with self.assertRaises(ValueError):
            cluster_bootstrap(np.array(['2026-01-01'], dtype='datetime64[D]'), many, {'a': np.zeros(1)})
        with self.assertRaises(ValueError):
            cluster_bootstrap(rd, many, {'a': np.zeros(3)})
