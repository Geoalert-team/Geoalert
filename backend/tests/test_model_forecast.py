"""
The trained model behind the likelihood: what it learns from, what it must
never read, the test that decides whether it is used, and how its figures
land on the forecast.
"""
import functools
import hashlib
import itertools
import json
import math
import random
import shutil
import tempfile
import threading
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from django.contrib.gis.geos import MultiPolygon
from django.core.cache import cache
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone as dj_timezone
from rest_framework.test import APIRequestFactory

from apps.barangays.models import Barangay
from apps.history import fire_candidate, hazard_data, hazard_forecast, hazard_models, prediction_log, storms
from apps.history import model_forecast as mf
from apps.history.exposure import write_exposure
from apps.history.forecast import empty_profile, seasonal_forecast
from apps.history.models import HistoricalRecord
from apps.history.views import ForecastAccuracyView, HistoricalForecastView, _forecast_events
from tests.fire_setup import FireSetupMixin, box

TZ = timezone.utc
TODAY = date(2026, 11, 5)
NOW = datetime(2026, 11, 5, tzinfo=TZ)
PLACES = [
    {'id': 1, 'name': 'Busy', 'area_km2': 1.0, 'puroks': 20},
    {'id': 2, 'name': 'Quiet', 'area_km2': 2.0, 'puroks': 10},
    {'id': 3, 'name': 'Never', 'area_km2': 3.0, 'puroks': 5},
]
MONTHS = [(y, m) for y in range(2023, 2027) for m in range(1, 13) if (y, m) <= (2026, 9)]


def ev(year, month, barangay=1, hazard='Fire', sample=False):
    name = next((p['name'] for p in PLACES if p['id'] == barangay), None)
    return {'barangay_id': barangay, 'barangay': name, 'hazard': hazard, 'severity': 'Orange', 'is_sample': sample,
            'when': datetime(year, month, 10, tzinfo=TZ)}


def steady():
    """Busy burns 3 times a month and 8 times every March; Quiet once every March; Never not at all."""
    events = []
    for y, m in MONTHS:
        events += [ev(y, m) for _ in range(8 if m == 3 else 3)]
        if m == 3:
            events.append(ev(y, m, barangay=2))
    return events


def write_buildings(path, counts):
    """An exposure file holding only building counts, the one column fire reads."""
    zero = dict(noah25_mh=0.0, noah100_mh=0.0, hand_lt2_buildings=0.0, exposure=0.0)
    write_exposure(path, {b: dict(buildings=float(n), **zero) for b, n in counts.items()}, {})


def private_data_dir(test):
    """Point the data folder at an empty temp one: fire never reads the real building counts in a test."""
    test.tmp = Path(tempfile.mkdtemp())
    test.addCleanup(shutil.rmtree, test.tmp, ignore_errors=True)
    patcher = mock.patch.object(hazard_data, 'DATA_DIR', test.tmp)
    patcher.start()
    test.addCleanup(patcher.stop)


def scattered(sample=False):
    """Fires falling at random across ten barangays, as they really do: no place or month is certain."""
    rng = random.Random(5)
    places = [{'id': i, 'name': f'B{i}', 'area_km2': 1.0 + i / 4, 'puroks': 8 + i} for i in range(1, 11)]
    events = []
    for y, m in MONTHS:
        for p in places:
            for _ in range(sum(rng.random() < 0.06 + p['id'] / 100 for _ in range(5))):
                events.append({'barangay_id': p['id'], 'barangay': p['name'], 'hazard': 'Fire', 'severity': 'Orange',
                               'is_sample': sample, 'when': datetime(y, m, 10, tzinfo=TZ)})
    return events, places


class RatesTests(SimpleTestCase):
    def test_the_busy_barangay_and_the_busy_month_rate_highest(self):
        table = mf.rates_table(steady(), PLACES, today=TODAY)
        self.assertGreater(table[1][2], table[1][7])   # Busy, March over August
        self.assertGreater(table[1][2], table[2][2])   # March, Busy over Quiet

    def test_a_barangay_with_no_events_still_gets_a_rate(self):
        table = mf.rates_table(steady(), PLACES, today=TODAY)
        self.assertGreater(table[3][2], 0)
        self.assertEqual(len(table[3]), 12)

    def test_events_after_the_cutoff_change_nothing(self):
        before = [e for e in steady() if e['when'].year < 2026]
        cut = date(2026, 1, 1)
        self.assertEqual(mf.rates_table(steady(), PLACES, until=cut, today=TODAY),
                         mf.rates_table(before, PLACES, until=cut, today=TODAY))

    def test_months_past_the_last_record_are_not_read_as_quiet(self):
        # The log stops in September. October on is unknown, not fire-free.
        self.assertEqual(mf.rates_table(steady(), PLACES, today=TODAY),
                         mf.rates_table(steady(), PLACES, today=date(2030, 1, 1)))

    def test_the_month_still_running_is_left_out(self):
        record = steady() + [ev(2026, 10)]
        self.assertEqual(mf.rates_table(record + [ev(2026, 11)] * 6, PLACES, today=TODAY),
                         mf.rates_table(record, PLACES, today=TODAY))

    def test_events_in_no_known_barangay_are_left_out(self):
        record = steady()
        stray = [ev(2024, 5, barangay=None), ev(2024, 5, barangay=99)]
        self.assertEqual(mf.rates_table(record + stray, PLACES, today=TODAY),
                         mf.rates_table(record, PLACES, today=TODAY))

    def test_too_few_events_means_no_model(self):
        self.assertIsNone(mf.rates_table(steady()[:40], PLACES, today=TODAY))
        self.assertIsNone(mf.rates_table([], PLACES, today=TODAY))


class ChanceTests(SimpleTestCase):
    def test_chance_of_at_least_one_event(self):
        self.assertEqual(mf.chance(0), 0)
        self.assertAlmostEqual(mf.chance(math.log(2)), 0.5)

    def test_levels_at_each_boundary(self):
        self.assertEqual([mf.level_for(c) for c in (0.0, 0.149, 0.15, 0.249, 0.25, 0.9)],
                         ['Low', 'Low', 'Moderate', 'Moderate', 'High', 'High'])


class EvaluateTests(SimpleTestCase):
    def test_it_tests_on_the_last_nine_months_of_the_record(self):
        out = mf.evaluate(steady(), PLACES, TODAY)
        # Busy 41 a year and Quiet 1 for three years; then eight months of 3, one March of 8, and Quiet's March
        self.assertEqual(out['train'], {'start': '2023-01', 'end': '2025-12', 'events': 126})
        self.assertEqual(out['test'], {'start': '2026-01', 'end': '2026-09', 'events': 33})

    def test_a_model_worse_than_counting_stays_in_use_and_says_so(self):
        # A pattern this regular is exactly what counting gets right; the model is used anyway, never counting
        self.assertEqual(mf.evaluate(steady(), PLACES, TODAY)['status'], 'in_use_not_better')

    def test_a_model_better_than_counting_is_used(self):
        events, places = scattered()
        out = mf.evaluate(events, places, TODAY)
        self.assertEqual(out['status'], 'in_use')
        self.assertLess(out['model']['brier'], out['counting']['brier'])

    def test_too_few_records_is_said_so(self):
        out = mf.evaluate(steady()[:40], PLACES, TODAY)
        self.assertEqual(out['status'], 'too_few_records')
        self.assertNotIn('model', out)

    def test_the_level_check_covers_every_tested_barangay_month(self):
        events, places = scattered()
        out = mf.evaluate(events, places, TODAY)
        self.assertEqual(sum(row['rows'] for row in out['levels']), len(places) * 9)
        self.assertEqual(sum(row['events'] for row in out['levels']), out['test']['events'])

    def test_it_must_beat_counting_on_both_measures(self):
        good, bad = {'deviance': 1, 'brier': 1}, {'deviance': 2, 'brier': 2}
        self.assertTrue(mf.beats(good, bad))
        self.assertFalse(mf.beats(bad, good))
        self.assertFalse(mf.beats({'deviance': 1, 'brier': 2}, {'deviance': 2, 'brier': 1}))
        self.assertFalse(mf.beats({'deviance': 2, 'brier': 1}, {'deviance': 1, 'brier': 2}))


class ApplyTests(SimpleTestCase):
    TABLE = {1: [0.5] * 12, 2: [0.2] * 12, 3: [0.05] * 12}

    def forecast(self, *extra, **kw):
        return seasonal_forecast([ev(2023, 1), ev(2024, 3), ev(2025, 3), ev(2025, 3, barangay=2), *extra], 3, NOW, **kw)

    def row(self, result, name, hazard='Fire'):
        return next(r for r in result['results'] if r['barangay'] == name and r['hazard_type'] == hazard)

    def test_a_row_takes_the_models_chance_and_level_and_keeps_its_history(self):
        result = self.forecast()
        mf.apply_table(result, 'Fire', self.TABLE, PLACES, month=3)
        busy = self.row(result, 'Busy')
        self.assertEqual((busy['probability'], busy['expected_events'], busy['level'], busy['method']),
                         (0.393, 0.5, 'High', 'model'))
        self.assertEqual(busy['years_hit'], 2)

    def test_a_barangay_counting_never_listed_gets_a_row(self):
        result = self.forecast()
        mf.apply_table(result, 'Fire', self.TABLE, PLACES, month=3)
        never = self.row(result, 'Never')
        self.assertEqual((never['level'], never['years_hit'], never['events'], never['method']),
                         ('Low', 0, 0, 'model'))
        self.assertEqual(never['years_considered'], len(result['years']))

    def test_other_hazards_keep_their_counting(self):
        result = self.forecast(ev(2025, 3, hazard='Flood'))
        before = dict(self.row(result, 'Busy', 'Flood'))
        mf.apply_table(result, 'Fire', self.TABLE, PLACES, month=3)
        self.assertEqual(self.row(result, 'Busy', 'Flood'), before)

    def test_rows_stay_worst_first_and_the_summary_follows(self):
        result = self.forecast()
        mf.apply_table(result, 'Fire', {1: [0.01] * 12, 2: [0.5] * 12, 3: [0.2] * 12}, PLACES, month=3)
        self.assertEqual([r['barangay'] for r in result['results']], ['Quiet', 'Never', 'Busy'])
        self.assertEqual(result['by_barangay'][0]['barangay'], 'Quiet')
        self.assertEqual(result['by_barangay'][0]['level'], 'High')

    def test_a_date_gives_the_weeks_chance_and_the_months_level(self):
        result = self.forecast(day=15, year=2027)
        mf.apply_table(result, 'Fire', self.TABLE, PLACES, month=3, day=15)
        busy = self.row(result, 'Busy')
        # 0.5 a month over March's 31 days, for 7 days: 0.1129 expected, 1 - e^-0.1129 = 0.107
        self.assertEqual((busy['probability'], busy['expected_events']), (0.107, 0.11))
        self.assertEqual(busy['level'], 'High')

    def test_a_period_that_started_keeps_what_happened(self):
        result = self.forecast(ev(2026, 3, barangay=2), year=2026)
        mf.apply_table(result, 'Fire', self.TABLE, PLACES, month=3)
        self.assertEqual((self.row(result, 'Quiet')['actual'], self.row(result, 'Never')['actual']), (1, 0))

    def test_the_year_chart_follows_the_model(self):
        result = {'profile': empty_profile()}
        mf.apply_profile(result, {1: [0.5] * 12, 2: [0.1] * 12}, barangay_id=1)
        self.assertEqual((result['profile'][2]['probability'], result['profile'][2]['level']), (0.393, 'High'))
        self.assertEqual(result['profile_method'], 'model')

    def test_the_city_chart_is_the_average_barangay(self):
        result = {'profile': empty_profile()}
        mf.apply_profile(result, {1: [0.5] * 12, 2: [0.1] * 12}, barangay_id=None)
        # (0.5 + 0.1) / 2 = 0.3 expected, 1 - e^-0.3 = 0.259
        self.assertEqual(result['profile'][2]['probability'], 0.259)

    def test_a_barangay_the_model_does_not_know_has_no_chart(self):
        result = {'profile': empty_profile()}
        mf.apply_profile(result, {1: [0.5] * 12}, barangay_id=77)
        self.assertEqual(result['profile'], empty_profile())
        self.assertEqual(result['profile_method'], 'unavailable')

    def test_the_empty_chart_has_twelve_months_and_no_figures(self):
        months = empty_profile()
        self.assertEqual([(m['month'], m['month_name']) for m in months][::11], [(1, 'January'), (12, 'December')])
        self.assertTrue(all(m == {'month': m['month'], 'month_name': m['month_name'], 'probability': None,
                                  'expected_events': None, 'level': 'None'} for m in months))


LOCAL_CACHE = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache', 'LOCATION': 'model-forecast'}}


@override_settings(CACHES=LOCAL_CACHE)
class UseModelsTests(SimpleTestCase):
    def setUp(self):
        cache.clear()
        private_data_dir(self)

    def use(self, events, places, month=3, year=None, hazard='Fire'):
        result = seasonal_forecast(events, month, NOW, year=year)
        result['profile'] = empty_profile()
        with mock.patch.object(mf, 'places', return_value=places), mock.patch.object(mf, 'neighbours', return_value={}):
            self.unavailable = mf.use_models(result, events, month, hazard=hazard, today=TODAY)
        return result

    def test_cache_key_changes_with_the_exposure_file(self):
        events = steady()[:40]
        path = self.tmp / 'barangay_exposure.csv'
        with mock.patch.object(mf, 'places', return_value=PLACES) as where, \
                mock.patch.object(mf, 'neighbours', return_value={}):
            def builds():
                mf._fitted('Fire', events, None, TODAY)
                return where.call_count

            self.assertEqual(builds(), 1)
            self.assertEqual(builds(), 1)               # from the cache
            write_buildings(path, {1: 10, 2: 20, 3: 30})
            self.assertEqual(builds(), 2)               # the building counts arrived
            self.assertEqual(builds(), 2)
            write_buildings(path, {1: 10, 2: 20, 3: 31})
            self.assertEqual(builds(), 3)               # and changed
            path.unlink()
            self.assertEqual(builds(), 3)               # gone again: the first fit, still cached, is the right one

    def test_version_changes_with_the_exposure_file_alone(self):
        # the prediction log keys rows on the version, so new building counts with the same records must not
        # reuse the old one
        events = steady()[:40]
        path = self.tmp / 'barangay_exposure.csv'
        with mock.patch.object(mf, 'places', return_value=PLACES), mock.patch.object(mf, 'neighbours', return_value={}):
            def version():
                return mf._fitted('Fire', events, None, TODAY)['version']

            no_file = version()
            write_buildings(path, {1: 10, 2: 20, 3: 30})
            first = version()
            write_buildings(path, {1: 10, 2: 20, 3: 31})
            second = version()
            self.assertEqual(len({no_file, first, second}), 3)
            self.assertTrue(all(v.startswith('current@') and len(v) == len('current@') + 12
                                for v in (no_file, first, second)))
            self.assertEqual(version(), second)         # the same records and counts: the same version
            path.unlink()
            self.assertEqual(version(), no_file)

    def test_every_period_shares_one_comparison(self):
        # a past month and a period not yet started: one comparison and one test, two tables
        events, places = scattered()
        with mock.patch.object(mf, 'places', return_value=places), \
                mock.patch.object(mf, 'neighbours', return_value={}), \
                mock.patch.object(fire_candidate, 'compare', wraps=fire_candidate.compare) as compared, \
                mock.patch.object(mf, 'evaluate', wraps=mf.evaluate) as tested:
            default = mf._fitted('Fire', events, None, TODAY)
            past = mf._fitted('Fire', events, date(2026, 3, 1), TODAY)
        self.assertEqual((compared.call_count, tested.call_count), (1, 1))
        self.assertEqual((past['version'], past['candidate'], past['report']),
                         (default['version'], default['candidate'], default['report']))
        self.assertNotEqual(past['table'], default['table'])

    def test_concurrent_cold_requests_compare_once(self):
        events, places = scattered()
        waiting = threading.Event()
        real_compare = fire_candidate.compare

        def slow_compare(*args):
            waiting.wait(10)                # until the other request is waiting for this one
            return real_compare(*args)

        def poll(seconds):
            waiting.set()
            time.sleep(0.01)

        versions, errors = [], []

        def request():
            try:
                versions.append(mf._fitted('Fire', events, None, TODAY)['version'])
            except Exception as exc:        # reported below, not lost in the thread
                errors.append(exc)

        with mock.patch.object(mf, 'places', return_value=places), \
                mock.patch.object(mf, 'neighbours', return_value={}), \
                mock.patch.object(fire_candidate, 'compare', side_effect=slow_compare) as compared, \
                mock.patch.object(mf, '_sleep', side_effect=poll):
            threads = [threading.Thread(target=request) for _ in range(2)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(60)
        self.assertEqual(errors, [])
        self.assertEqual(compared.call_count, 1)
        self.assertEqual(len(versions), 2)
        self.assertEqual(len(set(versions)), 1)

    def test_a_request_that_waits_too_long_is_told_the_model_is_being_prepared(self):
        events, places = scattered()
        tag = mf._record_tag('Fire', events, TODAY)
        cache.set(mf.CHOICE_LOCK + hashlib.sha1(tag.encode('utf-8')).hexdigest(), 1, 60)     # another is building
        clock = itertools.count(0, mf.WAIT_SECONDS)
        with mock.patch.object(mf, '_monotonic', side_effect=lambda: next(clock)), mock.patch.object(mf, '_sleep'):
            result = self.use(events, places)
        self.assertEqual(self.unavailable, {'Fire': 'The fire model is being prepared; try again in a minute.'})
        self.assertEqual(result['model_hazards'], [])

    def test_a_building_file_that_cannot_be_read_leaves_todays_model_in_use(self):
        path = self.tmp / 'barangay_exposure.csv'
        header = 'barangay_id,barangay,buildings,noah25_mh,noah100_mh,hand_lt2_buildings,exposure\n'
        for name, body in (('a short row', '1,Busy,10\n'), ('an endless count', '1,Busy,inf,0,0,0,0\n')):
            with self.subTest(name):
                path.write_text(header + body, encoding='utf-8')
                with mock.patch.object(mf, 'places', return_value=PLACES), \
                        mock.patch.object(mf, 'neighbours', return_value={}), \
                        self.assertLogs('apps.history.model_forecast', level='WARNING'):
                    fitted = mf._fitted('Fire', steady(), None, TODAY)
                self.assertIsNotNone(fitted['table'])
                self.assertEqual(fitted['candidate']['in_use'], 'current')
                self.assertEqual(fitted['candidate']['verdict']['reasons'], [fire_candidate.NO_BUILDINGS])
                self.assertTrue(fitted['version'].startswith('current@'))

    def test_the_all_types_chart_follows_the_model(self):
        events, places = scattered()
        everything = self.use(events, places, hazard=None)
        self.assertEqual(everything['profile_method'], 'model')
        self.assertEqual(everything['profile'], self.use(events, places)['profile'])

    def test_the_all_types_chart_adds_the_hazards_together(self):
        events, places = scattered()
        fire_alone = self.use(events, places)['profile'][2]['probability']
        both = self.use(events + [{**e, 'hazard': 'Flood'} for e in events], places, hazard=None)
        self.assertEqual(both['model_hazards'], ['Fire', 'Flood'])
        # Two hazards just as likely: the chance neither happens is the one chance squared
        self.assertAlmostEqual(both['profile'][2]['probability'], 1 - (1 - fire_alone) ** 2, delta=0.002)

    def test_the_all_types_chart_never_leaves_a_hazard_out(self):
        events, places = scattered()
        flood = [{**e, 'hazard': 'Flood'} for e in events[:5]]
        result = self.use(events + flood, places, hazard=None)
        self.assertEqual(result['model_hazards'], ['Fire'])
        self.assertNotEqual(result.get('profile_method'), 'model')

    def test_a_hazard_that_passed_uses_the_model(self):
        events, places = scattered()
        result = self.use(events, places)
        self.assertTrue(all(r['method'] == 'model' for r in result['results']))
        self.assertEqual(len(result['results']), len(places))
        self.assertEqual(result['model_hazards'], ['Fire'])

    def test_a_model_that_did_not_beat_counting_is_still_used(self):
        result = self.use(steady(), PLACES)
        self.assertTrue(all(r['method'] == 'model' for r in result['results']))
        self.assertEqual(result['model_hazards'], ['Fire'])
        self.assertEqual(self.unavailable, {})

    def test_too_few_records_gives_no_figures_and_says_why(self):
        result = self.use(steady()[:40], PLACES)
        self.assertFalse(any('method' in r for r in result['results']))
        self.assertEqual(result['model_hazards'], [])
        self.assertEqual(self.unavailable, {'Fire': 'Too few fire records to train and test its model.'})

    def test_sample_records_never_train_the_model(self):
        events, places = scattered(sample=True)
        result = self.use(events, places)
        self.assertEqual(result['model_hazards'], [])

    def test_a_past_period_is_estimated_only_from_what_came_before_it(self):
        events, places = scattered()
        future_free = [e for e in events if e['when'] < datetime(2026, 3, 1, tzinfo=TZ)]
        with_later = self.use(events, places, year=2026)
        self.assertEqual({r['barangay_id']: r['probability'] for r in with_later['results']},
                         {r['barangay_id']: r['probability'] for r in self.use(future_free, places, year=2026)['results']})
        # trained on what came before, so not "in training"
        self.assertFalse(any('in_training' in r for r in with_later['results']))

    def test_a_past_period_with_too_few_earlier_records_uses_the_whole_record(self):
        events, places = scattered()
        # June 2023: five months of fires came before it, far fewer than MIN_TRAIN_EVENTS
        early = self.use(events, places, month=6, year=2023)
        whole = self.use(events, places, month=6)
        self.assertEqual(early['model_hazards'], ['Fire'])
        self.assertTrue(all(r['method'] == 'model' and r['in_training'] is True for r in early['results']))
        self.assertEqual({r['barangay_id']: r['probability'] for r in early['results']},
                         {r['barangay_id']: r['probability'] for r in whole['results']})
        self.assertEqual(early['profile_method'], 'model')

    def test_a_period_before_the_record_began_has_no_figures(self):
        events, places = scattered()
        result = self.use(events, places, month=6, year=2022)
        self.assertEqual(result['model_hazards'], [])
        self.assertFalse(any('method' in r for r in result['results']))
        self.assertEqual(self.unavailable, {'Fire': 'Fire records start in January 2023.'})


class PlacesTests(FireSetupMixin, TestCase):
    def test_a_barangay_with_no_boundary_is_not_a_place(self):
        Barangay.objects.create(name='Empty duplicate', municipality='Talisay')
        rows = {p['name']: p for p in mf.places()}
        self.assertEqual(set(rows), {'Home', 'Next door'})
        self.assertAlmostEqual(rows['Home']['area_km2'], 1.0, delta=0.02)
        self.assertEqual(rows['Home']['puroks'], 1)

    def test_barangays_that_share_a_border_are_neighbours(self):
        # Home and Next door share the edge at 500 m; across the road is 0.5 m from Next door, across the river
        # 2.5 m from the road; a barangay with no boundary is not a place
        road = Barangay.objects.create(name='Across the road', municipality='Talisay',
                                       boundary=MultiPolygon(box(1500.5, -500, 2500, 500), srid=4326))
        river = Barangay.objects.create(name='Across the river', municipality='Talisay',
                                        boundary=MultiPolygon(box(2502.5, -500, 3500, 500), srid=4326))
        Barangay.objects.create(name='Empty duplicate', municipality='Talisay')
        self.assertEqual(mf.neighbours(), {self.home.id: {self.next.id}, self.next.id: {self.home.id, road.id},
                                           road.id: {self.next.id}, river.id: set()})


@override_settings(CACHES=LOCAL_CACHE)
class ForecastViewTests(FireSetupMixin, TestCase):
    def setUp(self):
        super().setUp()
        cache.clear()
        # flood and landslide have no test report here: never the real one in apps/history/data/
        patcher = mock.patch.object(hazard_models, 'REPORT_PATH',
                                    Path(__file__).with_name('no_hazard_model_report.json'))
        patcher.start()
        self.addCleanup(patcher.stop)
        private_data_dir(self)

    def get(self, view=HistoricalForecastView, **params):
        return view.as_view()(APIRequestFactory().get('/', params))

    def fires(self):
        """Every month of 2023-01 to 2026-09: three fires in Home, one in Next door. Enough to train and test."""
        months = [(y, m) for y in range(2023, 2027) for m in range(1, 13) if (y, m) <= (2026, 9)]
        HistoricalRecord.objects.bulk_create(
            [HistoricalRecord(barangay=b, hazard_type=self.fire, severity_level='Orange',
                              occurred_at=datetime(y, m, 10 + i, 12, tzinfo=TZ))
             for y, m in months for b, n in ((self.home, 3), (self.next, 1)) for i in range(n)])

    def assert_fire_unavailable(self, data, reason):
        fire = [r for r in data['results'] if r['hazard_type'] == 'Fire']
        self.assertEqual(len(fire), 2)
        for row in fire:
            self.assertEqual((row['method'], row['probability'], row['level'], row['reason']),
                             ('unavailable', None, 'None', reason))
        self.assertIn('Fire', data['unavailable_hazards'])
        self.assertNotIn('Fire', data['model_hazards'])
        self.assertEqual(data['profile_method'], 'unavailable')
        self.assertTrue(all(c['missing'] == ['Fire'] and c['probability'] is None for c in data['combined']))

    def test_the_model_breaking_makes_fire_unavailable_never_counting(self):
        self.history(self.near, 2)
        with mock.patch('apps.history.model_forecast.use_models', side_effect=RuntimeError('no model')):
            with self.assertLogs('apps.history.views', level='ERROR'):
                response = self.get(month=dj_timezone.localtime().month, hazard_type_name='Fire')
        self.assertEqual(response.status_code, 200)
        self.assert_fire_unavailable(response.data, 'The fire model could not run right now.')

    def test_too_few_fires_makes_fire_unavailable_never_counting(self):
        self.history(self.near, 2)
        response = self.get(month=dj_timezone.localtime().month, hazard_type_name='Fire')
        self.assertEqual(response.status_code, 200)
        self.assert_fire_unavailable(response.data, 'Too few fire records to train and test its model.')

    def test_a_past_period_without_enough_earlier_fires_uses_the_whole_record_model(self):
        self.fires()
        data = self.get(month=6, year=2023, hazards='Fire').data
        fire = {r['barangay_id']: r for r in data['results']}
        self.assertEqual(len(fire), 2)
        self.assertTrue(all(r['method'] == 'model' and r['in_training'] is True for r in fire.values()))
        self.assertEqual(data['profile_method'], 'model')
        # the All hazards figure is fire's model chance, not a counting share
        for c in data['combined']:
            self.assertEqual(c['missing'], [])
            self.assertEqual((c['probability'], c['level']),
                             (fire[c['barangay_id']]['probability'], fire[c['barangay_id']]['level']))
        self.assertGreater(fire[self.home.id]['probability'], fire[self.next.id]['probability'])

    def test_the_chart_and_the_basis_carry_no_counting(self):
        self.fires()
        for params in ({'hazards': 'Fire'}, {}):
            with self.subTest(params=params):
                data = self.get(**params).data
                self.assertEqual(data['profile_method'], 'model')
                for entry in data['profile']:
                    self.assertNotIn('years_hit', entry)
                    self.assertNotIn('years_considered', entry)
                    self.assertIsNotNone(entry['probability'])
                self.assertNotIn('Share of past years', data['basis']['method'])
                self.assertIn('trained model', data['basis']['method'])

    def test_a_barangay_the_fire_model_does_not_know_has_no_chart(self):
        self.fires()
        unknown = Barangay.objects.create(name='No boundary', municipality='Talisay')
        data = self.get(hazards='Fire', barangay=unknown.id).data
        self.assertEqual(data['profile_method'], 'unavailable')
        self.assertTrue(all(m['probability'] is None and 'years_hit' not in m for m in data['profile']))

    def test_a_period_before_the_fire_records_began_is_unavailable(self):
        self.fires()
        data = self.get(month=6, year=2022, hazards='Fire').data
        self.assert_fire_unavailable(data, 'Fire records start in January 2023.')

    def test_accuracy_says_when_there_are_too_few_records(self):
        self.history(self.near, 3)
        entries = self.get(ForecastAccuracyView).data['hazards']
        # fire's own test first, then flood's and landslide's rain-and-terrain entries (no report here)
        self.assertEqual([(h['hazard'], h.get('kind'), h['status']) for h in entries],
                         [('Fire', None, 'too_few_records'), ('Flood', 'rain_terrain', 'unavailable'),
                          ('Landslide', 'rain_terrain', 'unavailable')])
        hazards = [h for h in entries if h.get('kind') != 'rain_terrain']
        self.assertEqual([(h['hazard'], h['status']) for h in hazards], [('Fire', 'too_few_records')])

    def test_fitted_uses_the_winner_and_reports_the_candidate(self):
        self.fires()
        buildings = {self.home.id: 400, self.next.id: 100}
        write_buildings(self.tmp / 'barangay_exposure.csv', buildings)
        fires = mf._real_by_hazard(_forecast_events())['Fire']
        where = mf.places()
        last = max(e['when'] for e in fires)
        # the version hashes what the models learn from, whatever the period: the records, the month they are
        # read in, then the building counts' sha1
        counts = hashlib.sha1((self.tmp / 'barangay_exposure.csv').read_bytes()).hexdigest()
        tag = f'Fire|{len(fires)}|{last.isoformat()}|2026-11|{counts}'
        records = hashlib.sha1(tag.encode('utf-8')).hexdigest()[:12]
        table_fns = {'pooled_exposure': functools.partial(fire_candidate.exposure_rates_table, buildings=buildings),
                     'current': mf.rates_table}
        scores = {'log_score', 'deviance', 'brier', 'auc', 'top_share', 'coverage80', 'pit'}
        for adopted, name in ((True, 'pooled_exposure'), (False, 'current')):
            with self.subTest(in_use=name):
                cache.clear()
                rule = {'adopted': adopted, 'reasons': ['By the rule.']}
                with mock.patch.object(fire_candidate, 'verdict', return_value=rule) as judged:
                    fitted = mf._fitted('Fire', fires, None, TODAY)
                candidate = fitted['candidate']
                self.assertEqual((candidate['in_use'], candidate['verdict']), (name, rule))
                self.assertEqual(fitted['version'], f'{name}@{records}')
                # the rule judged the paired log-score differences on the main window
                self.assertAlmostEqual(judged.call_args.args[0]['mean'], candidate['difference']['mean'], places=4)
                # the table and the test against counting come from the model in use
                self.assertEqual(fitted['table'], table_fns[name](fires, where, today=TODAY))
                self.assertEqual(fitted['report'], mf.evaluate(fires, where, TODAY, table_fn=table_fns[name]))
                # both models one month ahead on the last nine months, the difference, and the two checks
                self.assertEqual(set(candidate), {'in_use', 'verdict', 'window', 'models', 'difference', 'secondary',
                                                  'dispersion', 'dispersion_flag', 'morans_i'})
                self.assertEqual(candidate['window'], {'start': '2026-01', 'end': '2026-09'})
                for model in ('current', 'pooled_exposure'):
                    self.assertEqual(set(candidate['models'][model]), scores)
                    self.assertEqual(sum(candidate['models'][model]['pit']), 2 * 9)
                difference = candidate['difference']
                self.assertLessEqual(difference['low'], difference['mean'])
                self.assertLessEqual(difference['mean'], difference['high'])
                self.assertEqual(set(difference['dm']), {'statistic', 'p'})
                # from the first month with 100 fires before it (25 months of 4) to the last full month
                self.assertEqual(candidate['secondary']['window'], {'start': '2025-02', 'end': '2026-09'})
                self.assertIsInstance(candidate['dispersion'], float)
                self.assertEqual(candidate['dispersion_flag'], candidate['dispersion'] > fire_candidate.DISPERSION_FLAG)
                # two neighbours: one's leftover error is the other's opposite
                self.assertAlmostEqual(candidate['morans_i']['i'], -1.0, places=9)
                # the accuracy card carries the block, read from the same cached fit, as strict JSON
                json.dumps(candidate, allow_nan=False)
                entry = mf.accuracy_reports(_forecast_events(), TODAY)[0]
                self.assertEqual((entry['hazard'], entry['status'], entry['candidate']),
                                 ('Fire', fitted['report']['status'], candidate))

    def test_warm_fills_the_fire_cache_too(self):
        self.fires()
        order = []
        real_warm_fire = mf.warm_fire

        def warm_fire(today):
            order.append('Fire')
            real_warm_fire(today)

        # no network: the flood and landslide builds, the storm refresh and the prediction log are stand-ins
        with mock.patch.object(hazard_forecast, 'deployed', side_effect=order.append), \
                mock.patch.object(storms, 'refresh_recent', return_value=True), \
                mock.patch.object(mf, 'warm_fire', side_effect=warm_fire), \
                mock.patch.object(prediction_log, 'log_once_today'), \
                mock.patch.object(hazard_forecast.connections, 'close_all'):
            hazard_forecast._warm()
        self.assertEqual(order, ['Flood', 'Landslide', 'Fire'])
        # the forecast's own request for fire is now a cache hit: nothing is fitted again
        fires = mf._real_by_hazard(_forecast_events())['Fire']
        with mock.patch.object(mf, 'places', side_effect=AssertionError('fitted again')):
            fitted = mf._fitted('Fire', fires, None, dj_timezone.localdate())
        self.assertEqual(fitted['candidate']['in_use'], 'current')          # no building counts here
        self.assertEqual(fitted['candidate']['verdict']['reasons'], [fire_candidate.NO_BUILDINGS])
        # a period that has started reuses the warmed comparison: only its own table is fitted
        with mock.patch.object(mf, 'places', side_effect=AssertionError('compared again')), \
                mock.patch.object(fire_candidate, 'compare', side_effect=AssertionError('compared again')):
            past = mf._fitted('Fire', fires, date(2026, 3, 1), dj_timezone.localdate())
        self.assertEqual((past['version'], past['candidate']), (fitted['version'], fitted['candidate']))
        self.assertIsNotNone(past['table'])
        # a fire warm-up that fails is logged and stops nothing
        with mock.patch.object(hazard_forecast, 'deployed') as built, \
                mock.patch.object(storms, 'refresh_recent', return_value=True), \
                mock.patch.object(mf, 'warm_fire', side_effect=RuntimeError('no fit')), \
                mock.patch.object(prediction_log, 'log_once_today'), \
                mock.patch.object(hazard_forecast.connections, 'close_all') as closed, \
                self.assertLogs('apps.history.hazard_forecast', level='ERROR'):
            hazard_forecast._warm()
        self.assertEqual([c.args[0] for c in built.call_args_list], ['Flood', 'Landslide'])
        closed.assert_called_once_with()

    def test_accuracy_never_counts_sample_records(self):
        HistoricalRecord.objects.create(barangay=self.home, hazard_type=self.flood, severity_level='Green',
                                        occurred_at=dj_timezone.now() - timedelta(days=30), is_sample=True)
        entries = self.get(ForecastAccuracyView).data['hazards']
        # no counting test for anything: only flood's and landslide's rain-and-terrain entries (no report here)
        self.assertEqual([(h['hazard'], h['kind'], h['status']) for h in entries],
                         [('Flood', 'rain_terrain', 'unavailable'), ('Landslide', 'rain_terrain', 'unavailable')])
        self.assertEqual([h for h in entries if h.get('kind') != 'rain_terrain'], [])
