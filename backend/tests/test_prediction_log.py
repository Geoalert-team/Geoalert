"""
The prediction log (spec 3.4-3.5): the insert-only table of the chances the
app shows, its writer (day rows for flood and landslide, month rows for every
hazard), the once-a-day run from the warm-up, the summary test_hazard_models
writes as `logged`, and the forecast view's result extracted as
views.forecast_result. Toy files in a temp folder stand in for
apps/history/data/; no test reaches NASA POWER or IBTrACS.
"""
import shutil
import tempfile
from datetime import date, datetime, timedelta
from io import StringIO
from pathlib import Path
from unittest import mock

from django.contrib.gis.geos import MultiPolygon
from django.core.cache import cache
from django.core.management import CommandError, call_command
from django.db import DatabaseError, IntegrityError, ProgrammingError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIRequestFactory

from apps.barangays.models import Barangay
from apps.hazards.models import HazardType
from apps.history import hazard_data, hazard_forecast, hazard_models, model_forecast, prediction_log, storms
from apps.history.forecast import MAX_YEARS
from apps.history.hazard_data import MANILA, Record, rain_windows
from apps.history.hazard_verdict import poisson_interval
from apps.history.models import HazardPredictionLog, HistoricalRecord
from apps.history.rain import read_rain_csv, write_rain_csv
from apps.history.views import ForecastAccuracyView, HistoricalForecastView, forecast_result
from tests.fire_setup import box
from tests.hazard_fixtures import toy_report_v2, write_toy_files, write_toy_storms

TODAY = date(2026, 11, 12)
FILE_LAST_DAY = date(2026, 10, 31)          # the rain file's last day; the live feed has the days after it
LIVE_LAST_DAY = TODAY - timedelta(days=1)
ALL = ['Fire', 'Flood', 'Landslide']
MODELLED = ('Flood', 'Landslide')
RAIN_SOURCE = 'NASA POWER PRECTOTCORR'
FIRE_VERSION = 'current@0123456789ab'
TOO_FEW = 'Too few {} records to train and test its model.'
TABLE = HazardPredictionLog._meta.db_table


def at(day):
    return datetime(day.year, day.month, day.day, 12, tzinfo=MANILA)


def days_between(first, last):
    return [first + timedelta(days=i) for i in range((last - first).days + 1)]


class Pinned(datetime):
    """datetime with now() at noon on TODAY, the day the toy data is good for (the warm-up reads datetime.now)."""
    @classmethod
    def now(cls, tz=None):
        return at(TODAY)


def make_row(**fields):
    barangay = Barangay.objects.create(name='Frozen', municipality='Talisay')
    return HazardPredictionLog.objects.create(**{
        'hazard': 'Flood', 'barangay': barangay, 'kind': 'day', 'period_start': date(2026, 11, 1),
        'issued_on': date(2026, 11, 2), 'model_version': 'two_part@0123456789ab', 'probability': 0.2,
        'inputs': {'rain_source': RAIN_SOURCE}, **fields})


@override_settings(HAZARD_LOG_WRITER=True)       # this machine writes the log, as the deployed server does
class PredictionLogTests(TestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.barangays = [Barangay.objects.create(
            name=f'Toy {i}', municipality='Talisay',
            boundary=MultiPolygon(box(1000 * i, 0, 1000 * i + 900, 900), srid=4326)) for i in range(3)]
        self.ids = [b.id for b in self.barangays]
        self.terrain, self.rain, self.pos = write_toy_files(self.tmp, self.ids)
        self.report_path = self.tmp / 'hazard_model_report.json'
        fire = HazardType.objects.create(name='Fire', logo_class='fire')
        for b, d in [(self.ids[0], date(y, 7, 15)) for y in range(2022, 2026)] + [(self.ids[1], date(2024, 7, 14))]:
            HistoricalRecord.objects.create(barangay_id=b, hazard_type=fire, severity_level='Orange', occurred_at=at(d))
        self.fire_table = None
        # NASA POWER and IBTrACS are never called: the live rain is down until a test sets it, the live storm days
        # add nothing to the file's, and the daily storm refresh does nothing.
        self.live = mock.Mock(return_value=None)
        for patcher in (mock.patch.object(hazard_data, 'DATA_DIR', self.tmp),
                        mock.patch.object(hazard_models, 'REPORT_PATH', self.report_path),
                        mock.patch.object(hazard_forecast, 'recent_rain', self.live),
                        mock.patch.object(storms, 'live_storm_days', lambda base, today, get=None: base),
                        mock.patch.object(storms, 'refresh_recent', mock.Mock(return_value=True))):
            patcher.start()
            self.addCleanup(patcher.stop)

    def november(self, storm_days=(), heavy=None):
        """
        The rain file carried on to FILE_LAST_DAY (3 mm a day), the live rain
        from 1 November to the day before TODAY (3 mm a day, or `heavy`
        {day: mm}), and the storm days covering all of it with a storm on each
        toy event day and on `storm_days`.
        """
        rf = read_rain_csv(self.tmp / 'rain_daily.csv')
        added = days_between(rf.last_day + timedelta(days=1), FILE_LAST_DAY)
        write_rain_csv(self.tmp / 'rain_daily.csv', {b: {**series, **{d: 3.0 for d in added}}
                                                     for b, series in rf.rain.items()}, rf.cells)
        write_toy_storms(self.tmp, rf.first_day, date(2026, 12, 31), sorted({d for _, d in self.pos} | set(storm_days)))
        self.live_rain(LIVE_LAST_DAY, heavy)

    def live_rain(self, last, heavy=None):
        late = days_between(FILE_LAST_DAY + timedelta(days=1), last)
        self.live.return_value = {b: {d: (heavy or {}).get(d, 3.0) for d in late} for b in self.ids}

    def fire_model(self):
        """Fire's model in use, as model_forecast._fitted gives it: a fixed table (self.fire_table) and a version."""
        def fitted(hazard, events, until, today):
            where = model_forecast.places()
            if hazard != 'Fire':
                return {'places': where, 'report': {'status': 'too_few_records'}, 'table': None,
                        'in_training': False, 'reason': TOO_FEW.format(hazard.lower()), 'version': 'current@x',
                        'candidate': None}
            order = sorted(p['id'] for p in where)
            self.fire_table = {pid: [0.05 + 0.03 * order.index(pid) + 0.01 * m for m in range(12)] for pid in order}
            return {'places': where, 'report': {'status': 'in_use'}, 'table': self.fire_table, 'in_training': False,
                    'reason': None, 'version': FIRE_VERSION, 'candidate': None}
        return mock.patch.object(model_forecast, '_fitted', side_effect=fitted)

    @staticmethod
    def shown(month, year, today=TODAY, included=ALL):
        return forecast_result(month=month, day=None, year=year, included=list(included), barangay=None,
                               years=MAX_YEARS, exclude_samples=False, now=at(today))

    @staticmethod
    def get(**params):
        return HistoricalForecastView.as_view()(APIRequestFactory().get('/', params))

    @staticmethod
    def fire_accuracy():
        response = ForecastAccuracyView.as_view()(APIRequestFactory().get('/'))
        (fire,) = [e for e in response.data['hazards'] if e['hazard'] == 'Fire']
        return response, fire

    # ---- what is written ----

    def test_rerun_adds_no_rows(self):
        self.november()
        with self.fire_model():
            days, months = prediction_log.write_day_rows(TODAY), prediction_log.write_month_rows(TODAY)
            self.assertEqual(days, 30 * 2 * len(self.ids))          # 30 days, flood and landslide, each barangay
            self.assertEqual(months, 3 * len(self.ids))             # this month, every hazard, each barangay
            self.assertEqual(HazardPredictionLog.objects.count(), days + months)
            # the same day again: nothing new
            self.assertEqual((prediction_log.write_day_rows(TODAY), prediction_log.write_month_rows(TODAY)), (0, 0))
            # the next day, with no new rain day: no day row, and one new month snapshot
            tomorrow = TODAY + timedelta(days=1)
            self.assertEqual(prediction_log.write_day_rows(tomorrow), 0)
            self.assertEqual(prediction_log.write_month_rows(tomorrow), 3 * len(self.ids))
            total = HazardPredictionLog.objects.count()
            # the warm-up's run: at most once a Manila day, by a cache marker
            later = TODAY + timedelta(days=2)
            self.assertTrue(prediction_log.log_once_today(later))
            self.assertTrue(cache.get(f'hazard-log-done:{later.isoformat()}'))
            self.assertEqual(HazardPredictionLog.objects.count(), total + 3 * len(self.ids))
            with mock.patch.object(prediction_log, 'write_day_rows') as day, \
                    mock.patch.object(prediction_log, 'write_month_rows') as month:
                self.assertFalse(prediction_log.log_once_today(later))
            day.assert_not_called()
            month.assert_not_called()
        # the daily command runs both writers for today's Manila date and says what they added
        out = StringIO()
        with mock.patch.object(prediction_log, 'write_day_rows', return_value=60) as day, \
                mock.patch.object(prediction_log, 'write_month_rows', return_value=9) as month:
            call_command('log_hazard_predictions', stdout=out)
        day.assert_called_once_with(timezone.localdate())
        month.assert_called_once_with(timezone.localdate())
        self.assertIn('60 new day rows and 9 new month rows', out.getvalue())

    def test_day_rows_never_reach_back_more_than_30_days(self):
        self.november()
        self.assertEqual(prediction_log.BACKFILL_DAYS, 30)
        prediction_log.write_day_rows(TODAY)
        for hazard in MODELLED:
            for b in self.ids:
                logged = HazardPredictionLog.objects.filter(hazard=hazard, barangay_id=b, kind='day')
                self.assertEqual(sorted(logged.values_list('period_start', flat=True)),
                                 days_between(TODAY - timedelta(days=30), LIVE_LAST_DAY))
                self.assertEqual(set(logged.values_list('issued_on', flat=True)), {TODAY})
                self.assertTrue(all(r.level is None and r.expected_events is None for r in logged))
        # three days on: only the days after the last one logged for this model version
        later = TODAY + timedelta(days=3)
        self.live_rain(later - timedelta(days=1))
        prediction_log.write_day_rows(later)
        new = HazardPredictionLog.objects.filter(kind='day', issued_on=later)
        self.assertEqual(sorted(set(new.values_list('period_start', flat=True))),
                         days_between(TODAY, later - timedelta(days=1)))
        # after a long gap, still no further back than 30 days
        gap = TODAY + timedelta(days=40)
        self.live_rain(gap - timedelta(days=1))
        prediction_log.write_day_rows(gap)
        new = HazardPredictionLog.objects.filter(kind='day', issued_on=gap)
        self.assertEqual(sorted(set(new.values_list('period_start', flat=True))),
                         days_between(gap - timedelta(days=30), gap - timedelta(days=1)))

    def test_day_rows_carry_rain_storm_and_outside_training(self):
        storm_day, heavy_day = date(2026, 11, 8), date(2026, 11, 9)
        self.november(storm_days=[storm_day], heavy={heavy_day: 300.0})
        prediction_log.write_day_rows(TODAY)

        def logged(hazard, b, day):
            return HazardPredictionLog.objects.get(hazard=hazard, barangay_id=b, kind='day', period_start=day)

        flood, slide = hazard_forecast.deployed('Flood'), hazard_forecast.deployed('Landslide')
        recorded = {h: hazard_forecast._recorded_chances(dep, [storm_day, heavy_day], TODAY)
                    for h, dep in (('Flood', flood), ('Landslide', slide))}
        # the two-part model reads the city's rain (the lowest barangay's), its r3 and, for landslide, r14
        lowest = min(self.ids)
        city = {**read_rain_csv(self.tmp / 'rain_daily.csv').rain[lowest], **self.live.return_value[lowest]}
        for b in self.ids:
            row = logged('Flood', b, storm_day)
            self.assertEqual(row.model_version, flood.version)
            # a double read back from the database keeps 15 significant figures
            self.assertAlmostEqual(row.probability, recorded['Flood'][b][storm_day], places=15)
            self.assertEqual(row.inputs, {'rain_mm': {'r3': rain_windows(city, storm_day)['r3']},
                                          'rain_source': RAIN_SOURCE, 'storm72': 1, 'storm': 'TOY',
                                          'outside_training': False})
            # 306 mm in three days: log1p(r3) above the fit's training maximum (5.5)
            row = logged('Flood', b, heavy_day)
            self.assertEqual(row.inputs, {'rain_mm': {'r3': rain_windows(city, heavy_day)['r3']},
                                          'rain_source': RAIN_SOURCE, 'storm72': 0, 'storm': None,
                                          'outside_training': True})
            row = logged('Landslide', b, heavy_day)
            self.assertAlmostEqual(row.probability, recorded['Landslide'][b][heavy_day], places=15)
            windows = rain_windows(city, heavy_day)
            self.assertEqual(row.inputs, {'rain_mm': {'r3': windows['r3'], 'r14': windows['r14']},
                                          'rain_source': RAIN_SOURCE, 'outside_training': True})
            # a day from the rain file itself, scored when the model was built
            row = logged('Flood', b, date(2026, 10, 20))
            self.assertAlmostEqual(row.probability, flood.daily[b][date(2026, 10, 20)], places=15)
            self.assertFalse(row.inputs['outside_training'])

        # the pooled logistic regression reads each barangay's own rain sums and its terrain, and no storm flag,
        # so its flood rows carry no storm keys (as landslide's never do): the log holds what the model read
        toy_report_v2(self.report_path, in_use='logistic_regression')
        prediction_log.write_day_rows(TODAY)                   # a new model version is logged from 30 days back
        lr = hazard_forecast.deployed('Flood')
        self.assertTrue(lr.version.startswith('logistic_regression@'))
        b = self.ids[1]
        own = {**read_rain_csv(self.tmp / 'rain_daily.csv').rain[b], **self.live.return_value[b]}
        row = HazardPredictionLog.objects.get(hazard='Flood', barangay_id=b, kind='day', period_start=heavy_day,
                                              model_version=lr.version)
        self.assertEqual(row.inputs, {'rain_mm': rain_windows(own, heavy_day), 'rain_source': RAIN_SOURCE,
                                      'outside_training': True})                           # r0 above 150 mm
        row = HazardPredictionLog.objects.get(hazard='Flood', barangay_id=b, kind='day',
                                              period_start=date(2026, 10, 20), model_version=lr.version)
        self.assertFalse(row.inputs['outside_training'])

    def test_month_rows_match_what_the_forecast_shows(self):
        self.november()
        with self.fire_model():
            added = prediction_log.write_month_rows(TODAY)
            shown = self.shown(11, 2026)
        logged = {(r.hazard, r.barangay_id): r for r in HazardPredictionLog.objects.filter(kind='month')}
        self.assertEqual(added, len(logged))
        modelled = [r for r in shown['results'] if r.get('method') == 'model']
        self.assertEqual(sorted((r['hazard_type'], r['barangay_id']) for r in modelled), sorted(logged))
        self.assertEqual(len(logged), 3 * len(self.ids))
        versions = {'Fire': FIRE_VERSION, **{h: hazard_forecast.deployed(h).version for h in MODELLED}}
        for row in modelled:
            r = logged[(row['hazard_type'], row['barangay_id'])]
            self.assertEqual((r.probability, r.level), (row['probability'], row['level']))
            self.assertEqual((r.period_start, r.issued_on), (date(2026, 11, 1), TODAY))
            self.assertEqual(r.model_version, versions[row['hazard_type']])
            if row['hazard_type'] == 'Fire':
                # the events fire's table expects in the month the row came from
                self.assertAlmostEqual(r.expected_events, self.fire_table[row['barangay_id']][10], places=12)
                self.assertEqual(r.inputs, {'method': 'model', 'in_training': False})
            else:
                self.assertIsNone(r.expected_events)
                self.assertEqual(r.inputs, {'method': 'model', 'in_training': False,
                                            'scenario_years': row['rain_years']})

    def test_unavailable_rows_are_not_logged(self):
        self.november()
        # no share for the third barangay: its flood and landslide rows are unavailable; fire has too few records
        toy_report_v2(self.report_path, shares={self.ids[0]: 0.6, self.ids[1]: 0.3})
        added = prediction_log.write_day_rows(TODAY) + prediction_log.write_month_rows(TODAY)
        self.assertEqual(added, HazardPredictionLog.objects.count())
        self.assertEqual(set(HazardPredictionLog.objects.values_list('barangay_id', flat=True)), set(self.ids[:2]))
        self.assertFalse(HazardPredictionLog.objects.filter(hazard='Fire').exists())
        shown = self.shown(11, 2026)
        for row in shown['results']:
            if row['hazard_type'] == 'Fire' or row['barangay_id'] == self.ids[2]:
                self.assertEqual(row['method'], 'unavailable')
        self.assertIn('Fire', shown['unavailable_hazards'])

    def test_missing_table_logs_a_warning_and_returns_false(self):
        self.november()
        missing = ProgrammingError('relation "hazard_prediction_log" does not exist')
        with mock.patch.object(prediction_log, 'write_day_rows', side_effect=missing), \
                mock.patch.object(prediction_log, 'write_month_rows') as month, \
                self.assertLogs('apps.history.prediction_log', level='WARNING') as logs:
            self.assertFalse(prediction_log.log_once_today(TODAY))
        self.assertEqual(len(logs.records), 1)                       # one warning, not one per row
        month.assert_not_called()
        self.assertIsNone(cache.get(f'hazard-log-done:{TODAY.isoformat()}'))     # tried again on the next warm-up
        # the daily command stops with the reason instead
        with mock.patch.object(prediction_log, 'write_day_rows', side_effect=missing), \
                self.assertRaisesMessage(CommandError, 'Has migration history 0008 been applied?'):
            call_command('log_hazard_predictions', stdout=StringIO())
        # the warm-up it ends carries on, and the forecast is still served; the date is pinned to TODAY, the
        # day the toy data is good for, for both the warm-up (datetime.now) and the view (timezone.localtime)
        real_localtime = timezone.localtime
        with self.fire_model(), \
                mock.patch.object(hazard_forecast, 'datetime', Pinned), \
                mock.patch.object(timezone, 'localtime',
                                  side_effect=lambda *a, **k: real_localtime(*a, **k) if a or k else at(TODAY)), \
                mock.patch.object(prediction_log, 'write_day_rows', side_effect=missing) as day, \
                mock.patch.object(hazard_forecast.connections, 'close_all'), \
                self.assertLogs('apps.history.prediction_log', level='WARNING') as logs:
            hazard_forecast._warm()
            response = self.get(month=11)
        day.assert_called_once_with(TODAY)
        self.assertEqual(len(logs.records), 1)
        self.assertIn('is migration history 0008 applied?', logs.output[0])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['model_hazards'], ALL)

    def test_other_database_errors_are_not_blamed_on_the_migration(self):
        refused = IntegrityError('new row violates check constraint "level_ok"')
        with mock.patch.object(prediction_log, 'write_day_rows', side_effect=refused), \
                self.assertLogs('apps.history.prediction_log', level='WARNING') as logs:
            self.assertFalse(prediction_log.log_once_today(TODAY))
        self.assertIn('level_ok', logs.output[0])
        self.assertNotIn('0008', logs.output[0])
        with mock.patch.object(prediction_log, 'write_day_rows', side_effect=refused), \
                self.assertRaises(CommandError) as raised:
            call_command('log_hazard_predictions', stdout=StringIO())
        self.assertIn('level_ok', str(raised.exception))
        self.assertNotIn('0008', str(raised.exception))

    @override_settings(HAZARD_LOG_WRITER=False)
    def test_a_machine_that_is_not_the_writer_logs_nothing(self):
        # a teammate's runserver against the shared database: the warm-up still builds and serves every model
        self.november()
        with self.fire_model(), mock.patch.object(hazard_forecast, 'datetime', Pinned), \
                mock.patch.object(hazard_forecast.connections, 'close_all'):
            hazard_forecast._warm()
        self.assertEqual(HazardPredictionLog.objects.count(), 0)
        for hazard in MODELLED:
            self.assertIsNotNone(cache.get(hazard_forecast.cache_key(hazard)))
        self.assertIsNone(cache.get(f'hazard-log-done:{TODAY.isoformat()}'))
        self.assertFalse(prediction_log.log_once_today(TODAY))
        # the daily command refuses, naming the setting to turn on, and writes nothing either
        with self.assertRaises(CommandError) as raised:
            call_command('log_hazard_predictions', stdout=StringIO())
        self.assertIn('Prediction logging is off on this machine', str(raised.exception))
        self.assertIn('HAZARD_LOG_WRITER=true', str(raised.exception))
        self.assertEqual(HazardPredictionLog.objects.count(), 0)

    # ---- scoring the log ----

    def test_logged_summary_scores_new_events(self):
        b0, b1, b2 = self.ids
        self.assertIsNone(prediction_log.logged_summary('Flood', []))           # nothing logged yet

        def log(hazard, b, day, p, issued, version='two_part@aaaaaaaaaaaa', kind='day', expected=None):
            HazardPredictionLog.objects.create(hazard=hazard, barangay_id=b, kind=kind, period_start=day,
                                               issued_on=issued, model_version=version, probability=p,
                                               expected_events=expected, level='Low' if kind == 'month' else None,
                                               inputs={})

        first, second = date(2026, 11, 1), date(2026, 11, 2)
        for b, p1, p2 in ((b0, 0.1, 0.4), (b1, 0.05, 0.2)):
            log('Flood', b, first, p1, first + timedelta(days=1))
            log('Flood', b, second, p2, second + timedelta(days=1))
        # the same day again under a later model version: the chance given at the time counts
        log('Flood', b0, second, 0.9, second + timedelta(days=5), version='two_part@bbbbbbbbbbbb')
        log('Landslide', b0, second, 0.7, second + timedelta(days=1))           # never counts for flood
        records = [Record('new', 'Flood', b0, second, 'TOY', False),
                   Record('none-logged', 'Flood', b2, second, 'TOY', False),     # its barangay has no chance
                   Record('sample', 'Flood', b1, second, 'TOY', True),           # a sample is never an event
                   Record('city', 'Flood', None, second, 'TOY', False),          # no barangay to score
                   Record('old', 'Flood', b0, date(2025, 8, 1), 'TOY', False)]   # before logging began
        self.assertEqual(prediction_log.logged_summary('Flood', records), {
            'first': '2026-11-01', 'last': '2026-11-02', 'rows': 4, 'events': 1, 'expected': 0.75,
            'events_interval': [round(x, 4) for x in poisson_interval(1)],
            'new_events': [
                {'day': '2026-11-02', 'barangay_id': b0, 'barangay': 'Toy 0', 'chance': 0.4, 'chance_before': 0.1,
                 'model_version': 'two_part@aaaaaaaaaaaa'},
                {'day': '2026-11-02', 'barangay_id': b2, 'barangay': 'Toy 2', 'chance': None, 'chance_before': None,
                 'model_version': None}]})

        # fire from its month rows: the first snapshot of each month, and the events its table expected
        log('Fire', b0, first, 0.2, first, version=FIRE_VERSION, kind='month', expected=0.22)
        log('Fire', b0, first, 0.5, first + timedelta(days=3), version=FIRE_VERSION, kind='month', expected=0.69)
        log('Fire', b1, first, 0.1, first, version=FIRE_VERSION, kind='month', expected=0.11)
        fires = [Record('', 'Fire', b0, date(2026, 11, d), '', False) for d in (5, 20)]
        # November is still in progress on 15 November: its rows are not scored yet
        self.assertIsNone(prediction_log.logged_summary('Fire', fires, today=date(2026, 11, 15)))
        # a month that has ended is scored
        self.assertEqual(prediction_log.logged_summary('Fire', fires, today=date(2026, 12, 3)), {
            'first': '2026-11-01', 'last': '2026-11-01', 'rows': 2, 'events': 2, 'expected': 0.33,
            'events_interval': [round(x, 4) for x in poisson_interval(2)],
            'new_events': [{'day': d, 'barangay_id': b0, 'barangay': 'Toy 0', 'chance': 0.2,
                            'model_version': FIRE_VERSION} for d in ('2026-11-05', '2026-11-20')]})
        # with December also logged, December in progress (20 December) is left out; once it ends it is counted
        december = date(2026, 12, 1)
        log('Fire', b0, december, 0.3, december, version=FIRE_VERSION, kind='month', expected=0.4)
        self.assertEqual(prediction_log.logged_summary('Fire', fires, today=date(2026, 12, 20))['rows'], 2)
        self.assertEqual(prediction_log.logged_summary('Fire', fires, today=date(2026, 12, 20))['expected'], 0.33)
        self.assertEqual(prediction_log.logged_summary('Fire', fires, today=date(2027, 1, 3))['rows'], 3)

    # ---- fire's accuracy entry ----

    def test_fire_accuracy_entry_carries_its_logged_block(self):
        with self.fire_model():
            response, fire = self.fire_accuracy()
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(fire['logged'])                                       # nothing logged yet
        b0, b1 = self.ids[:2]
        july = date(2025, 7, 1)
        for b, p, expected in ((b0, 0.3, 0.35), (b1, 0.1, 0.1)):
            HazardPredictionLog.objects.create(
                hazard='Fire', barangay_id=b, kind='month', period_start=july, issued_on=july,
                model_version=FIRE_VERSION, probability=p, expected_events=expected, level='Low',
                inputs={'method': 'model', 'in_training': False})
        with self.fire_model():
            response, fire = self.fire_accuracy()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(fire), {'hazard', 'status', 'candidate', 'logged'})   # the entry as before, plus logged
        # the July 2025 fire in the first barangay, against the events its row expected
        self.assertEqual(fire['logged'], {
            'first': '2025-07-01', 'last': '2025-07-01', 'rows': 2, 'events': 1, 'expected': 0.45,
            'events_interval': [round(x, 4) for x in poisson_interval(1)],
            'new_events': [{'day': '2025-07-15', 'barangay_id': b0, 'barangay': 'Toy 0', 'chance': 0.3,
                            'model_version': FIRE_VERSION}]})

    def test_fire_accuracy_answers_without_the_log_table(self):
        # the shared database has no hazard_prediction_log until migration 0008: the query is refused for real
        with connection.cursor() as cursor:
            cursor.execute('ALTER TABLE hazard_prediction_log RENAME TO hazard_prediction_log_away')
        with self.fire_model(), self.assertLogs('apps.history.prediction_log', level='WARNING') as logs:
            response, fire = self.fire_accuracy()
        self.assertEqual(response.status_code, 200)
        self.assertIn('hazard_prediction_log', logs.output[0])
        self.assertIsNone(fire['logged'])
        self.assertEqual((fire['status'], fire['candidate']), ('in_use', None))
        # the refused query went back to its savepoint: the transaction it ran in still works
        self.assertEqual(Barangay.objects.count(), len(self.ids))

    # ---- the forecast view ----

    def test_forecast_view_unchanged_after_extraction(self):
        self.november()
        now = at(TODAY)
        real_localtime = timezone.localtime
        b = self.ids[1]
        cases = [
            ({'month': '7'}, dict(month=7, day=None, year=None, included=ALL, barangay=None, years=MAX_YEARS,
                                  exclude_samples=False)),
            ({'date': '2026-11-05', 'hazards': 'flood,Fire', 'barangay': str(b), 'years': '3',
              'exclude_samples': 'true'},
             dict(month=11, day=5, year=2026, included=['Fire', 'Flood'], barangay=b, years=3, exclude_samples=True)),
            ({'month': '11', 'year': '2026', 'hazard_type_name': 'landslide'},
             dict(month=11, day=None, year=2026, included=['Landslide'], barangay=None, years=MAX_YEARS,
                  exclude_samples=False)),
            ({}, dict(month=12, day=None, year=None, included=ALL, barangay=None, years=MAX_YEARS,
                      exclude_samples=False)),                                   # next month by default
        ]
        with self.fire_model(), mock.patch.object(
                timezone, 'localtime', side_effect=lambda *a, **k: real_localtime(*a, **k) if a or k else now):
            for params, kwargs in cases:
                with self.subTest(params=params):
                    response = self.get(**params)
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response['Cache-Control'], 'public, max-age=600')
                    self.assertEqual(response.data, forecast_result(**kwargs, now=now))
            # the request's own mistakes are still 400s, before anything is built
            for params in ({'month': '13'}, {'date': 'soon'}, {'hazards': 'Quake'}, {'barangay': 'x'}):
                with self.subTest(params=params):
                    self.assertEqual(self.get(**params).status_code, 400)


class FrozenTableTests(TransactionTestCase):
    """The trigger and the migration need real transactions; the table is emptied by TRUNCATE, which the row
    trigger never sees."""

    def test_update_and_delete_are_refused(self):
        row = make_row()
        with self.assertRaises(DatabaseError):
            with transaction.atomic():
                HazardPredictionLog.objects.filter(pk=row.pk).update(probability=0.5)
        with self.assertRaises(DatabaseError):
            with transaction.atomic():
                HazardPredictionLog.objects.filter(pk=row.pk).delete()
        row.refresh_from_db()
        self.assertEqual(row.probability, 0.2)
        # a row that breaks the table's rules is refused too
        for fields in ({'hazard': 'Earthquake'}, {'kind': 'week'}, {'level': 'Severe'}, {'probability': 1.5},
                       {'probability': -0.1}):
            with self.subTest(fields=fields):
                with self.assertRaises(DatabaseError):
                    with transaction.atomic():
                        HazardPredictionLog.objects.create(**{
                            'hazard': 'Flood', 'barangay': row.barangay, 'kind': 'day',
                            'period_start': date(2026, 11, 3), 'issued_on': date(2026, 11, 4),
                            'model_version': 'two_part@0123456789ab', 'probability': 0.2, 'inputs': {}, **fields})
        # the barangay a row names cannot be deleted from under it
        with self.assertRaises(DatabaseError):
            with transaction.atomic():
                Barangay.objects.filter(pk=row.barangay_id).delete()

    def test_the_table_has_prefixed_columns_its_unique_key_and_index(self):
        with connection.cursor() as cursor:
            columns = [c.name for c in connection.introspection.get_table_description(cursor, TABLE)]
            constraints = connection.introspection.get_constraints(cursor, TABLE)
        self.assertEqual(sorted(columns), sorted(f.column for f in HazardPredictionLog._meta.concrete_fields))
        self.assertTrue(all(c.startswith('hzpl_') for c in columns), columns)
        self.assertEqual(constraints['hazard_prediction_log_unique']['columns'],
                         ['hzpl_hazard', 'hzpl_brgy_id', 'hzpl_kind', 'hzpl_period_start', 'hzpl_issued_on',
                          'hzpl_model_version'])
        (index,) = HazardPredictionLog._meta.indexes
        self.assertEqual(constraints[index.name]['columns'], ['hzpl_hazard', 'hzpl_period_start'])
        self.assertEqual(constraints[index.name]['index'], True)

    def test_migration_is_reversible(self):
        def trigger_parts():
            with connection.cursor() as cursor:
                cursor.execute("SELECT count(*) FROM pg_proc WHERE proname = 'hazard_prediction_log_frozen'")
                functions = cursor.fetchone()[0]
                cursor.execute("SELECT count(*) FROM pg_trigger WHERE tgname = 'hazard_prediction_log_frozen'")
                return functions, cursor.fetchone()[0]

        executor = MigrationExecutor(connection)
        try:
            executor.migrate([('history', '0007_source')])
            self.assertNotIn(TABLE, connection.introspection.table_names())
            self.assertEqual(trigger_parts(), (0, 0))
            # before the migration, the summary says nothing is logged rather than failing test_hazard_models
            with self.assertLogs('apps.history.prediction_log', level='WARNING'):
                self.assertIsNone(prediction_log.logged_summary('Flood', []))
        finally:
            executor.loader.build_graph()
            executor.migrate([('history', '0008_hazard_prediction_log')])
        self.assertIn(TABLE, connection.introspection.table_names())
        self.assertEqual(trigger_parts(), (1, 1))
        row = make_row()
        with self.assertRaises(DatabaseError):
            with transaction.atomic():
                HazardPredictionLog.objects.filter(pk=row.pk).delete()
