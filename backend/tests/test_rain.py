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
    RainFile, complete_years, download_archive, pace_wait, read_rain_csv, recent_rain, representative_points,
    write_rain_csv)
from tests.fire_setup import box


def days(a, b):
    return [a + timedelta(days=i) for i in range((b - a).days + 1)]


class FakeGet:
    """Records calls and answers like Open-Meteo: a list for many points, an object for one."""

    def __init__(self, value=lambda lat, lon, day: 1.0, cell=lambda lat, lon: (lat, lon), fail=None):
        self.calls, self.value, self.cell, self.fail = [], value, cell, fail

    def __call__(self, url, params):
        self.calls.append((url, dict(params)))
        if self.fail:
            self.fail(url, params, len(self.calls))
        lats = [float(x) for x in str(params['latitude']).split(',')]
        lons = [float(x) for x in str(params['longitude']).split(',')]
        if 'start_date' in params:
            span = days(date.fromisoformat(params['start_date']), date.fromisoformat(params['end_date']))
        else:
            today = date(2026, 11, 12)
            span = days(today - timedelta(days=params['past_days']), today)
        out = []
        for lat, lon in zip(lats, lons):
            clat, clon = self.cell(lat, lon)
            out.append({'latitude': clat, 'longitude': clon, 'daily': {
                'time': [d.isoformat() for d in span],
                'precipitation_sum': [self.value(lat, lon, d) for d in span]}})
        return out if len(out) > 1 else out[0]


def pts(n):
    return {i + 1: (10.0 + i * 0.01, 122.0 + i * 0.01) for i in range(n)}


def http_error(code):
    resp = requests.Response()
    resp.status_code = code
    return requests.HTTPError(f'{code}', response=resp)


class DownloadTests(SimpleTestCase):
    def run_dl(self, points, start, end, get, **kw):
        sleeps, logs = [], []
        out = download_archive(points, start, end, get=get, sleep=sleeps.append, log=logs.append, **kw)
        return out, sleeps, logs

    def test_download_sends_at_most_100_points_and_waits_13_s(self):
        get = FakeGet(value=lambda lat, lon, d: 1.0 if d >= date(2020, 12, 18) else None)
        (rain, cells), sleeps, _ = self.run_dl(pts(150), date(2020, 12, 18), date(2021, 1, 4), get)
        sizes = [len(str(c[1]['latitude']).split(',')) for c in get.calls]
        self.assertEqual(sizes, [100, 50, 100, 50, 100, 50])  # discovery, then 2021, then 2020
        self.assertEqual(sleeps, [13] * 5)
        self.assertEqual(len(rain), 150)
        self.assertEqual(rain[150][date(2021, 1, 4)], 1.0)

    def test_requests_run_newest_year_first_ending_with_the_2016_12_18_span(self):
        get = FakeGet()
        self.run_dl(pts(2), date(2016, 12, 18), date(2018, 1, 3), get)
        spans = [(c[1]['start_date'], c[1]['end_date']) for c in get.calls[1:]]  # [0] is discovery
        self.assertEqual(spans, [('2018-01-01', '2018-01-03'), ('2017-01-01', '2017-12-31'),
                                 ('2016-12-18', '2016-12-31')])

    def test_download_drops_years_with_no_values_and_logs_the_first_day(self):
        get = FakeGet(value=lambda lat, lon, d: 2.0 if d >= date(2020, 12, 18) else None)
        (rain, _), _, logs = self.run_dl(pts(2), date(2016, 12, 18), date(2021, 1, 2), get)
        self.assertEqual(min(rain[1]), date(2020, 12, 18))
        self.assertEqual(max(rain[1]), date(2021, 1, 2))
        self.assertTrue(any('2020-12-18' in str(m) for m in logs))

    def test_interior_gaps_stay_as_none_and_edges_are_trimmed(self):
        def value(lat, lon, d):
            if d < date(2020, 12, 18) or d > date(2020, 12, 29):
                return None
            return None if d == date(2020, 12, 25) else 3.0
        get = FakeGet(value=value)
        (rain, _), _, _ = self.run_dl(pts(1), date(2020, 12, 16), date(2020, 12, 31), get)
        self.assertEqual(min(rain[1]), date(2020, 12, 18))
        self.assertEqual(max(rain[1]), date(2020, 12, 29))
        self.assertIsNone(rain[1][date(2020, 12, 25)])

    def test_download_fails_when_the_archive_starts_after_2020_12_18(self):
        get = FakeGet(value=lambda lat, lon, d: 1.0 if d >= date(2021, 3, 1) else None)
        with self.assertRaises(CommandError):
            self.run_dl(pts(2), date(2020, 12, 18), date(2021, 6, 1), get)

    def test_download_fails_when_there_is_no_data_at_all(self):
        with self.assertRaises(CommandError):
            self.run_dl(pts(2), date(2020, 12, 18), date(2021, 1, 5), FakeGet(value=lambda *a: None))

    def test_cells_are_the_grid_points_open_meteo_served(self):
        get = FakeGet(cell=lambda lat, lon: (round(lat, 1) + 0.05, round(lon, 1) + 0.05))
        (_, cells), _, _ = self.run_dl(pts(3), date(2020, 12, 18), date(2020, 12, 20), get)
        self.assertEqual(cells[2], (10.05, 122.05))
        self.assertNotEqual(cells[2], pts(3)[2])

    def test_single_point_object_response_is_accepted(self):
        get = FakeGet()
        (rain, cells), _, _ = self.run_dl(pts(1), date(2020, 12, 18), date(2020, 12, 19), get)
        self.assertEqual(rain[1], {date(2020, 12, 18): 1.0, date(2020, 12, 19): 1.0})
        self.assertEqual(cells[1], pts(1)[1])

    def test_entries_map_to_barangays_by_position(self):
        get = FakeGet(value=lambda lat, lon, d: lat, cell=lambda lat, lon: (lat + 5, lon + 5))
        (rain, _), _, _ = self.run_dl(pts(3), date(2020, 12, 18), date(2020, 12, 18), get)
        self.assertEqual([rain[i][date(2020, 12, 18)] for i in (1, 2, 3)], [10.0, 10.01, 10.02])

    def test_a_different_cell_in_a_later_span_warns_and_keeps_the_first(self):
        calls = []

        def cell(lat, lon):
            calls.append(1)
            return (lat, lon) if len(calls) == 1 else (lat + 1, lon + 1)
        get = FakeGet(cell=cell)
        (_, cells), _, logs = self.run_dl(pts(1), date(2020, 12, 18), date(2021, 1, 2), get)
        self.assertEqual(cells[1], pts(1)[1])
        self.assertTrue(any('cell' in str(m).lower() for m in logs))

    def test_full_year_plan_uses_the_hourly_pace(self):
        get = FakeGet()
        _, sleeps, logs = self.run_dl(pts(22), date(2016, 12, 18), date(2025, 12, 31), get)
        self.assertEqual(len(sleeps), len(get.calls) - 1)
        self.assertAlmostEqual(sleeps[0], 22 * 3600 / 4500)  # after discovery
        self.assertAlmostEqual(sleeps[1], 22 * (365 / 14) * 3600 / 4500)
        self.assertAlmostEqual(sleeps[-1], 22 * (365 / 14) * 3600 / 4500)
        self.assertNotEqual(sleeps[1], 13)
        self.assertEqual(get.calls[0][1]['start_date'], '2025-12-31')  # discovery
        self.assertEqual(get.calls[1][1]['start_date'], '2025-01-01')
        self.assertEqual(get.calls[-1][1]['start_date'], '2016-12-18')
        self.assertTrue(logs)

    def test_pace_wait_formula(self):
        self.assertEqual(pace_wait(10, 100), 13)
        self.assertAlmostEqual(pace_wait(500, 4500), 60)
        self.assertAlmostEqual(pace_wait(450, 4501), 360)

    def test_retries_then_succeeds(self):
        def fail(url, params, n):
            if n <= 2:
                raise requests.Timeout('slow')
        get = FakeGet(fail=fail)
        stats = {}
        (rain, _), sleeps, _ = self.run_dl(pts(1), date(2020, 12, 18), date(2020, 12, 19), get, stats=stats)
        self.assertEqual(sleeps, [30, 60, 13])  # two retries on discovery, then the pace wait
        self.assertEqual(len(get.calls), 4)
        self.assertEqual(stats['retries'], 2)
        self.assertEqual(len(rain[1]), 2)

    def test_http_429_and_5xx_are_retried_but_other_4xx_is_not(self):
        for code, expected_calls in ((429, 3), (503, 3), (404, 1)):
            def fail(url, params, n, code=code):
                raise http_error(code)
            get = FakeGet(fail=fail)
            with self.assertRaises(CommandError):
                self.run_dl(pts(1), date(2020, 12, 18), date(2020, 12, 19), get)
            self.assertEqual(len(get.calls), expected_calls, code)

    def test_a_failed_old_year_is_logged_and_skipped(self):
        def fail(url, params, n):
            if params['start_date'].startswith('2017'):
                raise requests.ConnectionError('down')
        get = FakeGet(fail=fail, value=lambda lat, lon, d: 1.0 if d >= date(2020, 12, 18) else None)
        stats = {}
        (rain, _), sleeps, logs = self.run_dl(pts(1), date(2016, 12, 18), date(2021, 1, 2), get, stats=stats)
        self.assertEqual(min(rain[1]), date(2020, 12, 18))
        self.assertEqual(stats['retries'], 2)
        self.assertEqual(len(stats['failed']), 1)
        self.assertTrue(any('2017-01-01' in str(m) for m in logs))
        retry_sleeps = [s for s in sleeps if s in (30, 60)]
        self.assertEqual(retry_sleeps, [30, 60])

    def test_a_failed_span_from_2020_12_18_on_raises(self):
        def fail(url, params, n):
            if params['start_date'] == '2021-01-01':
                raise requests.Timeout('slow')
        get = FakeGet(fail=fail)
        with self.assertRaises(CommandError) as cm:
            self.run_dl(pts(1), date(2020, 12, 18), date(2021, 1, 2), get)
        self.assertIn('2021-01-01', str(cm.exception))
        self.assertIn('slow', str(cm.exception))


class MalformedReplyTests(SimpleTestCase):
    BAD = {
        'error object': lambda params: {'error': True, 'reason': 'Too many requests'},
        'wrong length': lambda params: [
            {'latitude': 1, 'longitude': 1, 'daily': {'time': [], 'precipitation_sum': []}}] * 5,
        'missing daily': lambda params: [{'latitude': 1, 'longitude': 1}] * len(str(params['latitude']).split(',')),
    }

    def test_old_span_with_a_malformed_reply_is_logged_skipped_and_not_retried(self):
        for name, bad in self.BAD.items():
            stats, calls, logs = {}, [], []
            fake = FakeGet(value=lambda lat, lon, d: 1.0 if d >= date(2020, 12, 18) else None)

            def get(url, params, bad=bad):
                calls.append(params['start_date'])
                return bad(params) if params['start_date'].startswith('2017') else fake(url, params)
            rain, _ = download_archive(pts(2), date(2016, 12, 18), date(2020, 12, 19), get=get,
                                       sleep=lambda s: None, log=logs.append, stats=stats)
            self.assertEqual(calls.count('2017-01-01'), 1, name)
            self.assertEqual(stats['retries'], 0, name)
            self.assertEqual(len(stats['failed']), 1, name)
            self.assertEqual(min(rain[1]), date(2020, 12, 18), name)
            self.assertTrue(any('2017-01-01' in str(m) for m in logs), name)

    def test_recent_span_with_a_malformed_reply_raises_with_the_detail(self):
        for name, bad in self.BAD.items():
            calls, fake = [], FakeGet()

            def get(url, params, bad=bad):
                if params['start_date'] == params['end_date']:
                    return fake(url, params)  # discovery
                calls.append(1)
                return bad(params)
            with self.assertRaises(CommandError, msg=name) as cm:
                download_archive(pts(2), date(2020, 12, 18), date(2020, 12, 20), get=get,
                                 sleep=lambda s: None, log=lambda m: None)
            self.assertIn('2020-12-18', str(cm.exception), name)
            self.assertEqual(len(calls), 1, name)

    def test_a_malformed_or_failed_discovery_raises_before_any_archive_request(self):
        for name, bad in self.BAD.items():
            calls = []

            def get(url, params, bad=bad):
                calls.append(params['start_date'])
                return bad(params)
            with self.assertRaises(CommandError, msg=name):
                download_archive(pts(2), date(2016, 12, 18), date(2020, 12, 20), get=get,
                                 sleep=lambda s: None, log=lambda m: None)
            self.assertEqual(calls, ['2020-12-20'], name)

        def timeout(url, params):
            calls.append(params['start_date'])
            raise requests.Timeout('slow')
        calls = []
        with self.assertRaises(CommandError):
            download_archive(pts(2), date(2016, 12, 18), date(2020, 12, 20), get=timeout,
                             sleep=lambda s: None, log=lambda m: None)
        self.assertEqual(calls, ['2020-12-20'] * 3)

    def test_recent_rain_malformed_reply_returns_none_and_is_cached_as_failure(self):
        cache.clear()
        calls = []

        def get(url, params):
            calls.append(1)
            return {'error': True, 'reason': 'x'}
        args = ({1: (10.0, 122.0)}, date(2026, 11, 7), date(2026, 11, 12))
        with self.assertLogs('apps.history.rain', 'WARNING') as logs:
            self.assertIsNone(recent_rain(*args, get=get))
            self.assertIsNone(recent_rain(*args, get=get))
        self.assertEqual(len(calls), 1)
        self.assertEqual(len(logs.records), 1)


class SourceParamsTests(SimpleTestCase):
    def test_archive_and_live_requests_use_the_same_model_variable_and_timezone(self):
        cache.clear()
        get = FakeGet()
        download_archive(pts(150), date(2020, 12, 18), date(2021, 1, 3), get=get, sleep=lambda s: None,
                         log=lambda m: None)
        recent_rain({1: (10.0, 122.0)}, date(2026, 11, 7), date(2026, 11, 12), get=get)
        self.assertEqual(len(get.calls), 7)  # 2 discovery, 2 spans x 2 chunks, 1 live
        for _, params in get.calls:
            self.assertEqual(params['models'], 'ecmwf_ifs')
            self.assertEqual(params['daily'], 'precipitation_sum')
            self.assertEqual(params['timezone'], 'Asia/Manila')


class GridCellTests(SimpleTestCase):
    @staticmethod
    def coarse(lat, lon):
        return (round(lat, 1), round(lon, 1)) 

    def test_one_series_is_downloaded_per_distinct_cell_and_copied_to_the_group(self):
        points = {1: (10.01, 122.01), 2: (10.02, 122.02), 3: (10.03, 122.03), 4: (10.21, 122.21),
                  5: (10.22, 122.22)}
        get = FakeGet(value=lambda lat, lon, d: round(lat, 1) * 100 + d.day, cell=self.coarse)
        logs = []
        rain, cells = download_archive(points, date(2020, 12, 18), date(2021, 1, 3), get=get,
                                       sleep=lambda s: None, log=logs.append)
        first = get.calls[0][1]
        self.assertEqual(first['start_date'], first['end_date'])  # discovery: one day
        self.assertEqual(first['start_date'], '2021-01-03')
        self.assertEqual(len(first['latitude'].split(',')), 5)
        for _, params in get.calls[1:]:
            self.assertEqual(len(params['latitude'].split(',')), 2)
        self.assertEqual(len(get.calls), 3)
        # the representative's own point is sent, lowest id of the group
        self.assertEqual(get.calls[1][1]['latitude'], '10.01,10.21')
        self.assertEqual(rain[1], rain[2])
        self.assertEqual(rain[2], rain[3])
        self.assertEqual(rain[4], rain[5])
        self.assertNotEqual(rain[1], rain[4])
        self.assertEqual({cells[i] for i in (1, 2, 3)}, {(10.0, 122.0)})
        self.assertEqual({cells[i] for i in (4, 5)}, {(10.2, 122.2)})
        self.assertTrue(any('5 points -> 2 grid cells' in str(m) for m in logs))

    def test_the_discovery_cell_is_kept_when_a_span_serves_another(self):
        points = {1: (10.01, 122.01), 2: (10.02, 122.02)}

        def cell(lat, lon):
            return (1.0, 2.0) if len(seen) == 0 else (9.0, 9.0)
        seen = []
        inner = FakeGet(cell=cell)

        def get(url, params):
            out = inner(url, params)
            seen.append(1)
            return out
        logs = []
        rain, cells = download_archive(points, date(2020, 12, 18), date(2020, 12, 20), get=get,
                                       sleep=lambda s: None, log=logs.append)
        self.assertEqual(cells, {1: (1.0, 2.0), 2: (1.0, 2.0)})
        self.assertTrue(any('Warning' in str(m) for m in logs))


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

    def test_recent_rain_asks_once_per_cell_for_days_after_the_file(self):
        cells = {1: (10.1, 122.1), 2: (10.1, 122.1), 3: (10.2, 122.2)}
        get = FakeGet(value=lambda lat, lon, d: lat * 10)
        after = self.today - timedelta(days=10)
        got = recent_rain(cells, after, self.today, get=get)
        self.assertEqual(len(get.calls), 1)
        url, params = get.calls[0]
        self.assertEqual(url, 'https://api.open-meteo.com/v1/forecast')
        self.assertEqual(len(str(params['latitude']).split(',')), 2)
        self.assertEqual(params['past_days'], 10)
        self.assertEqual(params['forecast_days'], 1)
        self.assertEqual(params['models'], 'ecmwf_ifs')
        self.assertEqual(params['daily'], 'precipitation_sum')
        self.assertEqual(params['timezone'], 'Asia/Manila')
        self.assertEqual(set(got[1]), set(days(after + timedelta(days=1), self.today - timedelta(days=1))))
        self.assertEqual(got[1], got[2])
        self.assertAlmostEqual(got[1][self.today - timedelta(days=1)], 101.0)
        self.assertAlmostEqual(got[3][self.today - timedelta(days=1)], 102.0)

    def test_recent_rain_drops_null_days(self):
        get = FakeGet(value=lambda lat, lon, d: None if d == self.today - timedelta(days=2) else 1.0)
        got = recent_rain({1: (10.0, 122.0)}, self.today - timedelta(days=4), self.today, get=get)
        self.assertNotIn(self.today - timedelta(days=2), got[1])
        self.assertEqual(len(got[1]), 2)

    def test_recent_rain_caps_past_days_at_92(self):
        get = FakeGet()
        recent_rain({1: (10.0, 122.0)}, self.today - timedelta(days=400), self.today, get=get)
        self.assertEqual(get.calls[0][1]['past_days'], 92)

    def test_nothing_to_fetch_when_the_file_is_current(self):
        get = FakeGet()
        got = recent_rain({1: (10.0, 122.0), 2: (10.1, 122.1)}, self.today - timedelta(days=1), self.today, get=get)
        self.assertEqual(got, {1: {}, 2: {}})
        self.assertEqual(get.calls, [])

    def test_recent_rain_success_is_cached(self):
        get = FakeGet()
        args = ({1: (10.0, 122.0)}, self.today - timedelta(days=5), self.today)
        first = recent_rain(*args, get=get)
        second = recent_rain(*args, get=get)
        self.assertEqual(first, second)
        self.assertEqual(len(get.calls), 1)

    def test_recent_rain_failure_is_cached_15_minutes(self):
        def boom(url, params):
            boom.calls += 1
            raise requests.Timeout('x')
        boom.calls = 0
        args = ({1: (10.0, 122.0)}, self.today - timedelta(days=5), self.today)
        with self.assertLogs('apps.history.rain', 'WARNING') as logs:
            self.assertIsNone(recent_rain(*args, get=boom))
            self.assertIsNone(recent_rain(*args, get=boom))
            self.assertEqual(boom.calls, 1)
            cache.clear()
            self.assertIsNone(recent_rain(*args, get=boom))
            self.assertEqual(boom.calls, 2)
        # a warning, with the error, for each call that failed; none for the cached failure
        self.assertEqual([(r.levelname, r.getMessage()) for r in logs.records],
                         [('WARNING', 'Live rain from Open-Meteo failed; not asked again for 15 minutes.')] * 2)
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
