import json
import os
import sys
import unittest
from unittest import mock
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np  # noqa: E402

import fetch  # noqa: E402
import gfs  # noqa: E402

UTC = timezone.utc


def run(init, hours, source='gfs-nomads'):
    return {'source': source, 'init_time': init.strftime('%Y-%m-%dT%H:%M:%SZ'), 'hours': hours}


class PerHourTests(unittest.TestCase):
    def test_per_hour_from_avg(self):
        rain = [1, 2, 3, 0, 0, 6, 4]
        avgs = [1, 1.5, 2, 1.5, 1.2, 2, 4]
        got = gfs.per_hour_from_avg([a / 3600.0 for a in avgs])
        for g, w in zip(got, rain):
            self.assertAlmostEqual(g, w, places=6)

    def test_constant_stays_constant(self):
        got = gfs.per_hour_from_avg([2.0 / 3600.0] * 13)
        for g in got:
            self.assertAlmostEqual(g, 2.0, places=6)


class PerHourFromAccTests(unittest.TestCase):
    def test_per_hour_from_acc(self):
        # hourly rain 1,2,3,0,0,6 then 4,1: accumulations reset after hour 6
        got = gfs.per_hour_from_acc([1, 3, 6, 6, 6, 12, 4, 5])
        self.assertEqual(got, [1, 2, 3, 0, 0, 6, 4, 1])

    def test_negative_noise_is_clamped(self):
        self.assertEqual(gfs.per_hour_from_acc([1.0, 0.9]), [1.0, 0.0])


class UrlTests(unittest.TestCase):
    def test_nomads_url(self):
        url = gfs.nomads_url(datetime(2026, 11, 18, 6, tzinfo=UTC), 24)
        self.assertIn('dir=%2Fgfs.20261118%2F06%2Fatmos', url)
        self.assertIn('file=gfs.t06z.pgrb2.0p25.f024', url)
        self.assertIn('var_APCP=on&lev_surface=on&subregion=&toplat=10.5&leftlon=123.75'
                      '&rightlon=124&bottomlat=10.25', url)

    def test_latest_cycle(self):
        now = datetime(2026, 11, 18, 10, 17, tzinfo=UTC)
        c = gfs.latest_cycle(now, exists=lambda u: True)
        self.assertEqual(c, datetime(2026, 11, 18, 6, tzinfo=UTC))
        c = gfs.latest_cycle(now, exists=lambda u: 'gfs.t06z' not in u)
        self.assertEqual(c, datetime(2026, 11, 18, 0, tzinfo=UTC))
        self.assertIsNone(gfs.latest_cycle(now, exists=lambda u: False))
        # too early for the 06z run: now - 3 h = 05:30
        c = gfs.latest_cycle(datetime(2026, 11, 18, 8, 30, tzinfo=UTC), exists=lambda u: True)
        self.assertEqual(c, datetime(2026, 11, 18, 0, tzinfo=UTC))


class FetchNomadsTests(unittest.TestCase):
    def test_fetch_nomads_uses_decode_per_hour(self):
        urls = []

        def get(url):
            urls.append(url)
            return url.encode()

        def decode(data):
            # 1 mm of rain every hour: APCP accumulates from the 6-h boundary (0-1, 0-2 ... 6-7)
            hour = int(data.decode().split('.f')[1][:3])
            return {p: float((hour - 1) % 6 + 1) for p in gfs.GRID}

        out = gfs.fetch_nomads(datetime(2026, 11, 18, 0, tzinfo=UTC), 8, get=get, decode=decode,
                               pause=0)
        self.assertEqual(len(urls), 8)
        self.assertIn('f008', urls[-1])
        self.assertEqual(set(out), set(gfs.GRID))
        for series in out.values():
            self.assertEqual(len(series), 8)
            for v in series:
                self.assertAlmostEqual(v, 1.0, places=6)

    def test_missing_hour_raises(self):
        def get(url):
            if 'f003' in url:
                raise OSError('404')
            return b''

        with self.assertRaises(RuntimeError):
            gfs.fetch_nomads(datetime(2026, 11, 18, 0, tzinfo=UTC), 4, get=get,
                             decode=lambda b: {p: 0.0 for p in gfs.GRID}, pause=0)


class _Arr:
    def __init__(self, values):
        self.values = values


class FakeBox:
    """A stand-in for the one dataarray fetch_dynamical slices (dims init, lead, lat, lon)."""

    def __init__(self, data, lats, lons):
        self.data, self.lats, self.lons = data, lats, lons

    def sel(self, latitude, longitude):
        la = (self.lats <= latitude.start) & (self.lats >= latitude.stop)
        lo = (self.lons >= longitude.start) & (self.lons <= longitude.stop)
        return FakeBox(self.data[:, :, la][:, :, :, lo], self.lats[la], self.lons[lo])

    def isel(self, init_time):
        return FakeBox(self.data[init_time], self.lats, self.lons)

    def transpose(self, *dims):
        return self

    @property
    def values(self):
        return self.data


def fake_dataset(rate=1.0 / 3600.0, bad=None):
    inits = np.array(['2026-11-18T00:00', '2026-11-18T06:00'], dtype='datetime64[ns]')
    leads = np.arange(0, 7).astype('timedelta64[h]').astype('timedelta64[ns]')
    lats = np.array([10.5, 10.25, 10.0])
    lons = np.array([123.5, 123.75, 124.0, 124.25])
    data = np.full((2, 7, 3, 4), rate)
    data[0] *= 2.0  # the older run rains twice as hard
    if bad is not None:
        data[1, 3, 1, 1] = bad
    return {
        'init_time': _Arr(inits), 'lead_time': _Arr(leads),
        'latitude': _Arr(lats), 'longitude': _Arr(lons),
        'precipitation_surface': FakeBox(data, lats, lons),
    }


class FetchDynamicalTests(unittest.TestCase):
    def test_newest_run_before_limit(self):
        init, out = gfs.fetch_dynamical(
            6, datetime(2026, 11, 18, 9, tzinfo=UTC), opener=lambda: fake_dataset())
        self.assertEqual(init, datetime(2026, 11, 18, 6, tzinfo=UTC))
        self.assertEqual(set(out), set(gfs.GRID))
        for series in out.values():
            self.assertEqual(len(series), 6)
            for v in series:
                self.assertAlmostEqual(v, 1.0, places=6)

    def test_earlier_run_chosen_when_limit_is_earlier(self):
        init, out = gfs.fetch_dynamical(
            3, datetime(2026, 11, 18, 5, tzinfo=UTC), opener=lambda: fake_dataset())
        self.assertEqual(init, datetime(2026, 11, 18, 0, tzinfo=UTC))
        self.assertAlmostEqual(out[gfs.GRID[0]][0], 2.0, places=6)

    def test_no_run_raises(self):
        with self.assertRaises(RuntimeError):
            gfs.fetch_dynamical(3, datetime(2026, 11, 17, tzinfo=UTC), opener=lambda: fake_dataset())

    def test_bad_value_raises(self):
        for bad in (float('nan'), 9999.0):
            with self.assertRaises(RuntimeError):
                gfs.fetch_dynamical(6, datetime(2026, 11, 18, 9, tzinfo=UTC),
                                    opener=lambda: fake_dataset(bad=bad))


class ValidationTests(unittest.TestCase):
    def _fetch(self, value, hours=4):
        return gfs.fetch_nomads(
            datetime(2026, 11, 18, 0, tzinfo=UTC), hours,
            get=lambda url: url.encode(),
            decode=lambda d: {p: (value if b'f003' in d else 0.0) for p in gfs.GRID}, pause=0)

    def test_nan_raises_naming_the_hour(self):
        with self.assertRaisesRegex(RuntimeError, 'hour 3'):
            self._fetch(float('nan'))

    def test_missing_value_sentinel_raises(self):
        with self.assertRaisesRegex(RuntimeError, 'hour 3'):
            self._fetch(9999.0)

    def test_sane_value_passes(self):
        out = self._fetch(40.0)
        self.assertAlmostEqual(out[gfs.GRID[0]][2], 40.0, places=6)

    def test_hourly_jump_over_500_raises(self):
        with self.assertRaises(RuntimeError):
            gfs.fetch_nomads(datetime(2026, 11, 18, 0, tzinfo=UTC), 2, get=lambda u: u.encode(),
                             decode=lambda d: {p: (0.0 if b'f001' in d else 600.0) for p in gfs.GRID},
                             pause=0)


class ExistsTests(unittest.TestCase):
    def _resp(self, status, body):
        r = mock.Mock()
        r.status_code, r.content = status, body
        return r

    def test_html_error_page_is_not_a_file(self):
        with mock.patch('requests.get', return_value=self._resp(200, b'<html>not present</html>')):
            self.assertFalse(gfs._default_exists('u'))

    def test_grib_body_is_a_file(self):
        with mock.patch('requests.get', return_value=self._resp(200, b'GRIB\x00')):
            self.assertTrue(gfs._default_exists('u'))

    def test_404_is_not_a_file(self):
        with mock.patch('requests.get', return_value=self._resp(404, b'GRIB')):
            self.assertFalse(gfs._default_exists('u'))


class PlanTests(unittest.TestCase):
    now = datetime(2026, 11, 18, 10, 17, tzinfo=UTC)
    newest = datetime(2026, 11, 18, 6, tzinfo=UTC)

    def test_nothing_held(self):
        plan = fetch.plan_runs(self.now, [], self.newest)
        self.assertEqual(plan[0], (self.newest, 96))
        rest = plan[1:]
        self.assertEqual(len(rest), 11)  # 00z today back to 12z on the 15th (window is 72 h)
        self.assertLessEqual(len(rest), 12)
        self.assertTrue(all(h == 6 for _, h in rest))
        self.assertEqual(rest[0][0], self.newest - timedelta(hours=6))
        self.assertTrue(all(c > self.now - timedelta(hours=72) for c, _ in rest))
        self.assertTrue(all(c < self.newest for c, _ in rest))

    def test_newest_held_full(self):
        plan = fetch.plan_runs(self.now, [run(self.newest, 96)], self.newest)
        self.assertTrue(all(h == 6 for _, h in plan))
        self.assertNotIn(self.newest, [c for c, _ in plan])

    def test_newest_held_short_is_fetched_again(self):
        plan = fetch.plan_runs(self.now, [run(self.newest, 6)], self.newest)
        self.assertEqual(plan[0], (self.newest, 96))

    def test_held_older_runs_skipped(self):
        older = self.newest - timedelta(hours=12)
        plan = fetch.plan_runs(self.now, [run(older, 6)], self.newest)
        self.assertNotIn(older, [c for c, _ in plan])

    def test_no_newest(self):
        self.assertEqual(fetch.plan_runs(self.now, [], None), [])


class PayloadTests(unittest.TestCase):
    def test_payload_shape(self):
        init = datetime(2026, 11, 18, 6, tzinfo=UTC)
        series = {p: [0.5] * 6 for p in gfs.GRID}
        body = fetch.payload('gfs-nomads', init, series, 'v1')
        self.assertEqual(body['source'], 'gfs-nomads')
        self.assertEqual(body['init_time'], '2026-11-18T06:00:00Z')
        self.assertEqual(body['job_version'], 'v1')
        self.assertEqual(len(body['points']), 4)
        for pt in body['points']:
            self.assertEqual(pt['first_hour_start'], '2026-11-18T06:00:00Z')
            self.assertEqual(len(pt['mm_per_hour']), 6)
        self.assertEqual({(p['lat'], p['lon']) for p in body['points']}, set(gfs.GRID))
        json.dumps(body)


ENV = {'RAIN_WATCH_API_URL': 'https://example.test', 'RAIN_WATCH_INGEST_TOKEN': 'tok'}
NOW = datetime(2026, 11, 18, 10, 17, tzinfo=UTC)


def fake_get(held=()):
    def get(url, headers=None):
        if 'forecast-runs/status' in url:
            return json.dumps({'runs': list(held)}).encode()
        return b'grib'
    return get


def fake_decode(_data):
    return {p: 1.0 / 3600.0 for p in gfs.GRID}


def call_main(argv, post, env=ENV, held=()):
    return fetch.main(argv, env=env, get=fake_get(held), post=post, exists=lambda u: True,
                      decode=fake_decode, now=NOW, sleep=lambda s: None, pause=0)


class MainTests(unittest.TestCase):
    def test_main_dry_run_posts_nothing(self):
        posts = []
        rc = call_main(['--dry-run'], lambda *a, **k: posts.append(a))
        self.assertEqual(rc, 0)
        self.assertEqual(posts, [])

    def test_main_posts_with_bearer_header(self):
        calls = []

        def post(url, body, headers):
            calls.append((url, body, headers))
            return 201

        rc = call_main([], post)
        self.assertEqual(rc, 0)
        self.assertEqual(calls[0][0], 'https://example.test/api/rain-watch/forecast-runs/')
        self.assertEqual(calls[0][2]['Authorization'], 'Bearer tok')
        self.assertEqual(len(calls[0][1]['points'][0]['mm_per_hour']), 96)
        self.assertEqual(len(calls), 12)

    def test_main_skips_held_runs(self):
        calls = []
        held = [run(datetime(2026, 11, 18, 6, tzinfo=UTC), 96)]
        rc = call_main([], lambda u, b, h: calls.append(b) or 200, held=held)
        self.assertEqual(rc, 0)
        self.assertEqual(len(calls), 11)

    def test_main_retries_then_fails(self):
        attempts = []

        def post(url, body, headers):
            attempts.append(1)
            raise OSError('down')

        rc = call_main([], post)
        self.assertEqual(rc, 1)
        self.assertEqual(len(attempts), 3)

    def test_failing_gap_run_does_not_fail_the_job(self):
        held = [run(datetime(2026, 11, 18, 6, tzinfo=UTC), 96)]
        calls = []

        def get(url, headers=None):
            if 'forecast-runs/status' in url:
                return json.dumps({'runs': held}).encode()
            if 'gfs.20261117' in url and '%2F12%2F' in url:
                raise OSError('NOMADS miss')
            return b'grib'

        def post(url, body, headers):
            calls.append(body['init_time'])
            return 201

        dyn_calls = []

        def dyn(*a):
            dyn_calls.append(a)
            raise OSError('down')

        rc = fetch.main([], env=ENV, get=get, post=post, exists=lambda u: True, decode=fake_decode,
                        now=NOW, sleep=lambda s: None, pause=0, dynamical=dyn)
        self.assertEqual(rc, 0)
        self.assertEqual(dyn_calls, [])  # no dynamical fallback for a gap cycle
        self.assertEqual(len(calls), 10)  # 11 gap runs, one missing
        self.assertNotIn('2026-11-17T12:00:00Z', calls)

    def test_gap_run_post_failure_continues(self):
        held = [run(datetime(2026, 11, 18, 6, tzinfo=UTC), 96)]
        attempts = []

        def post(url, body, headers):
            attempts.append(body['init_time'])
            if body['init_time'] == '2026-11-18T00:00:00Z':
                raise OSError('down')
            return 201

        rc = call_main([], post, held=held)
        self.assertEqual(rc, 0)
        self.assertEqual(len(attempts), 3 + 10)

    def _nomads_06z_down_get(self):
        def get(url, headers=None):
            if 'forecast-runs/status' in url:
                return b'{"runs": []}'
            if 'gfs.20261118' in url and '%2F06%2F' in url:
                raise OSError('NOMADS miss')
            return b'grib'
        return get

    def test_nomads_fails_falls_back_to_dynamical(self):
        posts = []
        series = {p: [0.1] * 96 for p in gfs.GRID}
        rc = fetch.main([], env=ENV, get=self._nomads_06z_down_get(),
                        post=lambda u, b, h: posts.append(b) or 201,
                        exists=lambda u: True, decode=fake_decode, now=NOW, sleep=lambda s: None,
                        pause=0, dynamical=lambda hours, before: (before, series))
        self.assertEqual(rc, 0)
        self.assertEqual(posts[0]['source'], 'gfs-dynamical')
        self.assertEqual(posts[0]['init_time'], '2026-11-18T06:00:00Z')
        self.assertTrue(all(p['source'] == 'gfs-nomads' for p in posts[1:]))

    def test_both_sources_fail_exits_1(self):
        posts = []

        def dyn(hours, before):
            raise RuntimeError('archive down')

        rc = fetch.main([], env=ENV, get=self._nomads_06z_down_get(),
                        post=lambda u, b, h: posts.append(b) or 201,
                        exists=lambda u: True, decode=fake_decode, now=NOW, sleep=lambda s: None,
                        pause=0, dynamical=dyn)
        self.assertEqual(rc, 1)
        self.assertEqual(posts, [])

    def test_no_nomads_cycle_uses_dynamical_newest(self):
        posts = []
        series = {p: [0.1] * 96 for p in gfs.GRID}
        dyn_init = datetime(2026, 11, 18, 0, tzinfo=UTC)
        rc = fetch.main([], env=ENV, get=fake_get(), post=lambda u, b, h: posts.append(b) or 201,
                        exists=lambda u: False, decode=fake_decode, now=NOW,
                        sleep=lambda s: None, pause=0, dynamical=lambda h, b: (dyn_init, series))
        self.assertEqual(rc, 0)
        self.assertEqual(posts[0]['source'], 'gfs-dynamical')
        self.assertEqual(posts[0]['init_time'], '2026-11-18T00:00:00Z')
        self.assertEqual(len(posts[0]['points'][0]['mm_per_hour']), 96)

    def test_no_nomads_cycle_and_dynamical_fails(self):
        def dyn(h, b):
            raise RuntimeError('down')

        rc = fetch.main([], env=ENV, get=fake_get(), post=lambda *a: 201, exists=lambda u: False,
                        decode=fake_decode, now=NOW, sleep=lambda s: None, pause=0, dynamical=dyn)
        self.assertEqual(rc, 1)

    def test_main_missing_env_fails(self):
        rc = call_main([], lambda *a: 201, env={})
        self.assertNotEqual(rc, 0)


if __name__ == '__main__':
    unittest.main()
