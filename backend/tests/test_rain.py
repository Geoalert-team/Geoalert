import tempfile
from datetime import date, timedelta
from pathlib import Path

import requests
from django.contrib.gis.geos import MultiPolygon
from django.core.cache import cache
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase

from apps.barangays.models import Barangay
from apps.history.rain import (
    POWER_URL, RainFile, city_cell, complete_years, download_archive, read_rain_csv, recent_rain,
    representative_points, write_rain_csv)
from tests.fire_setup import box


def days(a, b):
    return [a + timedelta(days=i) for i in range((b - a).days + 1)]


def ymd(text):
    return date(int(text[:4]), int(text[4:6]), int(text[6:]))


class FakeGet:
    """Records calls and answers like NASA POWER's daily point API: one point, values keyed YYYYMMDD, -999 missing."""

    def __init__(self, value=lambda lat, lon, day: 1.0, fail=None):
        self.calls, self.value, self.fail = [], value, fail

    def __call__(self, url, params):
        self.calls.append((url, dict(params)))
        if self.fail:
            self.fail(url, params, len(self.calls))
        lat, lon = float(params['latitude']), float(params['longitude'])
        series = {}
        for d in days(ymd(params['start']), ymd(params['end'])):
            v = self.value(lat, lon, d)
            series[d.strftime('%Y%m%d')] = -999.0 if v is None else v
        return {'type': 'Feature', 'geometry': {'type': 'Point', 'coordinates': [lon, lat, 25.0]},
                'properties': {'parameter': {'PRECTOTCORR': series}},
                'header': {'fill_value': -999.0, 'sources': ['MERRA2', 'GEOSIT']}}


# Two Talisay-like points: the city's average point is in the cell centred on 10.5 N, 123.75 E
TALISAY = {1: (10.242, 123.84), 2: (10.30, 123.80), 3: (10.36, 123.77)}


def http_error(code):
    resp = requests.Response()
    resp.status_code = code
    return requests.HTTPError(f'{code}', response=resp)


class CityCellTests(SimpleTestCase):
    def test_the_cell_is_the_power_grid_point_nearest_the_citys_average_point(self):
        # POWER's native grid (MERRA-2) has points every 0.5 degrees of latitude and 0.625 of longitude
        self.assertEqual(city_cell(TALISAY), (10.5, 123.75))
        self.assertEqual(city_cell({1: (10.1, 123.6)}), (10.0, 123.75))
        self.assertEqual(city_cell({1: (-7.3, -60.4)}), (-7.5, -60.625))


class DownloadTests(SimpleTestCase):
    def run_dl(self, points, start, end, get, **kw):
        sleeps, logs = [], []
        out = download_archive(points, start, end, get=get, sleep=sleeps.append, log=logs.append, **kw)
        return out, sleeps, logs

    def test_one_request_per_year_newest_first_for_the_city_cell(self):
        get = FakeGet()
        (rain, cells), sleeps, logs = self.run_dl(TALISAY, date(2016, 12, 18), date(2018, 1, 3), get)
        spans = [(c[1]['start'], c[1]['end']) for c in get.calls]
        self.assertEqual(spans, [('20180101', '20180103'), ('20170101', '20171231'), ('20161218', '20161231')])
        self.assertEqual({c[0] for c in get.calls}, {POWER_URL})
        self.assertEqual({(c[1]['latitude'], c[1]['longitude']) for c in get.calls}, {(10.5, 123.75)})
        self.assertEqual(sleeps, [1, 1])                      # a short pause between requests, none after the last
        self.assertTrue(any('3 barangays -> 1 NASA POWER grid cell (10.5, 123.75)' in str(m) for m in logs))

    def test_requests_ask_for_corrected_rain_in_local_solar_days(self):
        get = FakeGet()
        self.run_dl(TALISAY, date(2020, 12, 18), date(2020, 12, 19), get)
        params = get.calls[0][1]
        self.assertEqual({k: params[k] for k in ('parameters', 'community', 'time-standard', 'format')},
                         {'parameters': 'PRECTOTCORR', 'community': 'AG', 'time-standard': 'LST', 'format': 'JSON'})

    def test_every_barangay_gets_the_city_cells_series(self):
        get = FakeGet(value=lambda lat, lon, d: lat * 10 + d.day)
        (rain, cells), _, _ = self.run_dl(TALISAY, date(2020, 12, 18), date(2020, 12, 20), get)
        self.assertEqual(cells, {1: (10.5, 123.75), 2: (10.5, 123.75), 3: (10.5, 123.75)})
        self.assertEqual(rain[1], {date(2020, 12, 18): 123.0, date(2020, 12, 19): 124.0, date(2020, 12, 20): 125.0})
        self.assertEqual(rain[1], rain[2])
        self.assertEqual(rain[2], rain[3])
        self.assertIsNot(rain[1], rain[2])                    # each barangay its own copy

    def test_download_drops_years_with_no_values_and_logs_the_first_day(self):
        get = FakeGet(value=lambda lat, lon, d: 2.0 if d >= date(2020, 12, 18) else None)
        (rain, _), _, logs = self.run_dl(TALISAY, date(2016, 12, 18), date(2021, 1, 2), get)
        self.assertEqual(min(rain[1]), date(2020, 12, 18))
        self.assertEqual(max(rain[1]), date(2021, 1, 2))
        self.assertTrue(any('2020-12-18' in str(m) for m in logs))

    def test_missing_days_stay_as_none_inside_and_the_edges_are_trimmed(self):
        # POWER's last few days are -999 until they are processed: the file ends at the last day with rain
        def value(lat, lon, d):
            if d < date(2020, 12, 18) or d > date(2020, 12, 29):
                return None
            return None if d == date(2020, 12, 25) else 3.0
        (rain, _), _, _ = self.run_dl(TALISAY, date(2020, 12, 16), date(2020, 12, 31), FakeGet(value=value))
        self.assertEqual(min(rain[1]), date(2020, 12, 18))
        self.assertEqual(max(rain[1]), date(2020, 12, 29))
        self.assertIsNone(rain[1][date(2020, 12, 25)])

    def test_download_fails_when_the_archive_starts_after_2020_12_18(self):
        get = FakeGet(value=lambda lat, lon, d: 1.0 if d >= date(2021, 3, 1) else None)
        with self.assertRaises(CommandError):
            self.run_dl(TALISAY, date(2020, 12, 18), date(2021, 6, 1), get)

    def test_download_fails_when_there_is_no_data_at_all(self):
        with self.assertRaises(CommandError):
            self.run_dl(TALISAY, date(2020, 12, 18), date(2021, 1, 5), FakeGet(value=lambda *a: None))

    def test_retries_then_succeeds(self):
        def fail(url, params, n):
            if n <= 2:
                raise requests.Timeout('slow')
        get = FakeGet(fail=fail)
        stats = {}
        (rain, _), sleeps, _ = self.run_dl(TALISAY, date(2020, 12, 18), date(2020, 12, 19), get, stats=stats)
        self.assertEqual(sleeps, [30, 60])
        self.assertEqual(len(get.calls), 3)
        self.assertEqual(stats['retries'], 2)
        self.assertEqual(len(rain[1]), 2)

    def test_http_429_and_5xx_are_retried_but_other_4xx_is_not(self):
        for code, expected_calls in ((429, 3), (503, 3), (422, 1)):
            def fail(url, params, n, code=code):
                raise http_error(code)
            get = FakeGet(fail=fail)
            with self.assertRaises(CommandError):
                self.run_dl(TALISAY, date(2020, 12, 18), date(2020, 12, 19), get)
            self.assertEqual(len(get.calls), expected_calls, code)

    def test_a_failed_old_year_is_logged_and_skipped(self):
        def fail(url, params, n):
            if params['start'].startswith('2017'):
                raise requests.ConnectionError('down')
        get = FakeGet(fail=fail, value=lambda lat, lon, d: 1.0 if d >= date(2020, 12, 18) else None)
        stats = {}
        (rain, _), sleeps, logs = self.run_dl(TALISAY, date(2016, 12, 18), date(2021, 1, 2), get, stats=stats)
        self.assertEqual(min(rain[1]), date(2020, 12, 18))
        self.assertEqual(stats['retries'], 2)
        self.assertEqual(stats['failed'], ['2017-01-01..2017-12-31'])
        self.assertTrue(any('2017-01-01' in str(m) for m in logs))
        self.assertEqual([s for s in sleeps if s in (30, 60)], [30, 60])

    def test_a_failed_span_from_2020_12_18_on_raises(self):
        def fail(url, params, n):
            if params['start'] == '20210101':
                raise requests.Timeout('slow')
        with self.assertRaises(CommandError) as cm:
            self.run_dl(TALISAY, date(2020, 12, 18), date(2021, 1, 2), FakeGet(fail=fail))
        self.assertIn('2021-01-01', str(cm.exception))
        self.assertIn('slow', str(cm.exception))


class MalformedReplyTests(SimpleTestCase):
    BAD = {
        'error reply': lambda params: {'messages': ['Request failed'], 'errors': ['bad request']},
        'no rain parameter': lambda params: {'properties': {'parameter': {}}},
        'a day that is not a date': lambda params: {'properties': {'parameter': {'PRECTOTCORR': {'2021XX01': 1.0}}}},
        'a value that is not a number': lambda params: {'properties': {'parameter': {'PRECTOTCORR': {'20210101': 'x'}}}},
    }

    def test_old_span_with_a_malformed_reply_is_logged_skipped_and_not_retried(self):
        for name, bad in self.BAD.items():
            stats, calls, logs = {}, [], []
            fake = FakeGet(value=lambda lat, lon, d: 1.0 if d >= date(2020, 12, 18) else None)

            def get(url, params, bad=bad):
                calls.append(params['start'])
                return bad(params) if params['start'].startswith('2017') else fake(url, params)
            rain, _ = download_archive(TALISAY, date(2016, 12, 18), date(2020, 12, 19), get=get,
                                       sleep=lambda s: None, log=logs.append, stats=stats)
            self.assertEqual(calls.count('20170101'), 1, name)
            self.assertEqual(stats['retries'], 0, name)
            self.assertEqual(len(stats['failed']), 1, name)
            self.assertEqual(min(rain[1]), date(2020, 12, 18), name)
            self.assertTrue(any('2017-01-01' in str(m) for m in logs), name)

    def test_recent_span_with_a_malformed_reply_raises_with_the_detail(self):
        for name, bad in self.BAD.items():
            with self.assertRaises(CommandError, msg=name) as cm:
                download_archive(TALISAY, date(2020, 12, 18), date(2020, 12, 20), get=lambda url, params: bad(params),
                                 sleep=lambda s: None, log=lambda m: None)
            self.assertIn('2020-12-18', str(cm.exception), name)

    def test_recent_rain_malformed_reply_returns_none_and_is_cached_as_failure(self):
        cache.clear()
        calls = []

        def get(url, params):
            calls.append(1)
            return {'messages': ['x'], 'errors': ['y']}
        args = ({1: (10.5, 123.75)}, date(2026, 11, 7), date(2026, 11, 12))
        with self.assertLogs('apps.history.rain', 'WARNING') as logs:
            self.assertIsNone(recent_rain(*args, get=get))
            self.assertIsNone(recent_rain(*args, get=get))
        self.assertEqual(len(calls), 1)
        self.assertEqual(len(logs.records), 1)


class SourceParamsTests(SimpleTestCase):
    def test_archive_and_live_requests_ask_the_same_source_the_same_way(self):
        cache.clear()
        get = FakeGet()
        download_archive(TALISAY, date(2020, 12, 18), date(2021, 1, 3), get=get, sleep=lambda s: None,
                         log=lambda m: None)
        recent_rain({1: (10.5, 123.75)}, date(2026, 11, 7), date(2026, 11, 12), get=get)
        self.assertEqual(len(get.calls), 3)                   # 2020 and 2021, then the live call
        for url, params in get.calls:
            self.assertEqual(url, POWER_URL)
            self.assertEqual({k: params[k] for k in ('parameters', 'community', 'time-standard', 'format')},
                             {'parameters': 'PRECTOTCORR', 'community': 'AG', 'time-standard': 'LST', 'format': 'JSON'})


class RainFileTests(SimpleTestCase):
    def test_csv_round_trip_is_exact_and_sorted(self):
        rain = {2: {date(2021, 1, 2): 0.1 + 0.2, date(2021, 1, 1): None}, 1: {date(2021, 1, 1): 5.0}}
        cells = {1: (10.5, 122.5), 2: (10.6, 122.6)}
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'rain_daily.csv'
            write_rain_csv(path, rain, cells)
            lines = path.read_text().splitlines()
            self.assertEqual(lines[0], 'barangay_id,cell_lat,cell_lon,date,mm')
            self.assertEqual(lines[1].split(',')[0], '1')
            self.assertEqual(lines[2], '2,10.6,122.6,2021-01-01,')
            rf = read_rain_csv(path)
        self.assertEqual(rf.rain, rain)
        self.assertEqual(rf.cells, cells)
        self.assertEqual((rf.first_day, rf.last_day), (date(2021, 1, 1), date(2021, 1, 2)))

    def test_missing_file_raises_file_not_found(self):
        with self.assertRaises(FileNotFoundError):
            read_rain_csv(Path(tempfile.gettempdir()) / 'nope-rain-daily.csv')

    def test_complete_years_need_every_day_and_13_days_before(self):
        every = days(date(2020, 12, 19), date(2022, 12, 31))
        rain = {1: {d: 1.0 for d in every}, 2: {d: 1.0 for d in every}}
        rf = RainFile(rain, {}, every[0], every[-1])
        self.assertEqual(complete_years(rf), [2021, 2022])
        del rain[2][date(2020, 12, 19)]
        self.assertEqual(complete_years(rf), [2022])
        rain[2][date(2020, 12, 19)] = 1.0
        rain[1][date(2022, 6, 1)] = None
        self.assertEqual(complete_years(rf), [2021])


class RecentRainTests(SimpleTestCase):
    today = date(2026, 11, 12)

    def setUp(self):
        cache.clear()

    def test_recent_rain_asks_once_per_cell_for_the_days_after_the_file_up_to_yesterday(self):
        cells = {1: (10.5, 123.75), 2: (10.5, 123.75), 3: (10.0, 123.75)}
        get = FakeGet(value=lambda lat, lon, d: lat * 10)
        after = self.today - timedelta(days=10)
        got = recent_rain(cells, after, self.today, get=get)
        self.assertEqual([(c[1]['latitude'], c[1]['longitude'], c[1]['start'], c[1]['end']) for c in get.calls],
                         [(10.0, 123.75, '20261103', '20261111'), (10.5, 123.75, '20261103', '20261111')])
        self.assertEqual(set(got[1]), set(days(after + timedelta(days=1), self.today - timedelta(days=1))))
        self.assertEqual(got[1], got[2])
        self.assertAlmostEqual(got[1][self.today - timedelta(days=1)], 105.0)
        self.assertAlmostEqual(got[3][self.today - timedelta(days=1)], 100.0)

    def test_recent_rain_drops_days_power_has_not_filled_yet(self):
        get = FakeGet(value=lambda lat, lon, d: None if d >= self.today - timedelta(days=2) else 1.0)
        got = recent_rain({1: (10.5, 123.75)}, self.today - timedelta(days=6), self.today, get=get)
        self.assertEqual(sorted(got[1]), days(self.today - timedelta(days=5), self.today - timedelta(days=3)))

    def test_nothing_to_fetch_when_the_file_is_current(self):
        get = FakeGet()
        got = recent_rain({1: (10.5, 123.75), 2: (10.5, 123.75)}, self.today - timedelta(days=1), self.today, get=get)
        self.assertEqual(got, {1: {}, 2: {}})
        self.assertEqual(get.calls, [])

    def test_recent_rain_success_is_cached(self):
        get = FakeGet()
        args = ({1: (10.5, 123.75)}, self.today - timedelta(days=5), self.today)
        first = recent_rain(*args, get=get)
        second = recent_rain(*args, get=get)
        self.assertEqual(first, second)
        self.assertEqual(len(get.calls), 1)

    def test_recent_rain_failure_is_cached_15_minutes(self):
        def boom(url, params):
            boom.calls += 1
            raise requests.Timeout('x')
        boom.calls = 0
        args = ({1: (10.5, 123.75)}, self.today - timedelta(days=5), self.today)
        with self.assertLogs('apps.history.rain', 'WARNING') as logs:
            self.assertIsNone(recent_rain(*args, get=boom))
            self.assertIsNone(recent_rain(*args, get=boom))
            self.assertEqual(boom.calls, 1)
            cache.clear()
            self.assertIsNone(recent_rain(*args, get=boom))
            self.assertEqual(boom.calls, 2)
        # a warning, with the error, for each call that failed; none for the cached failure
        self.assertEqual([(r.levelname, r.getMessage()) for r in logs.records],
                         [('WARNING', 'Live rain from NASA POWER failed; not asked again for 15 minutes.')] * 2)
        self.assertTrue(all(isinstance(r.exc_info[1], requests.Timeout) for r in logs.records))


class RepresentativePointsTests(TestCase):
    def test_points_are_lat_lon_of_point_on_surface_and_skip_no_boundary(self):
        poly = box(-500, -500, 500, 500)
        a = Barangay.objects.create(name='A', municipality='Talisay', boundary=MultiPolygon(poly, srid=4326))
        Barangay.objects.create(name='B', municipality='Talisay')
        got = representative_points()
        self.assertEqual(list(got), [a.id])
        lat, lon = got[a.id]
        self.assertAlmostEqual(lat, poly.point_on_surface.y)
        self.assertAlmostEqual(lon, poly.point_on_surface.x)
