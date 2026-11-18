from datetime import datetime, timedelta, timezone as dt_timezone
from unittest import mock

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.rainwatch import assess
from apps.rainwatch.models import RainForecastRun, RainForecastSeries
from apps.rainwatch.rules import BALANCED

URL = '/api/rain-watch/forecast-runs/'
STATUS_URL = '/api/rain-watch/forecast-runs/status/'
GRID = ((10.25, 123.75), (10.25, 124.0), (10.5, 123.75), (10.5, 124.0))
AUTH = {'HTTP_AUTHORIZATION': 'Bearer s3cret'}


def last_cycle(now=None, days_back=0):
    now = now or datetime.now(dt_timezone.utc)
    cycle = now.replace(hour=now.hour // 6 * 6, minute=0, second=0, microsecond=0)
    return cycle - timedelta(days=days_back)


def body(init=None, n=96, **changes):
    init = init or last_cycle()
    data = {
        'source': 'gfs-nomads',
        'init_time': init.isoformat().replace('+00:00', 'Z'),
        'job_version': 'test-1',
        'points': [
            {'lat': lat, 'lon': lon, 'first_hour_start': (init + timedelta(hours=0)).isoformat(),
             'mm_per_hour': [0.5] * n}
            for lat, lon in GRID
        ],
    }
    data.update(changes)
    return data


@override_settings(RAIN_WATCH_INGEST_TOKEN='s3cret')
class IngestTests(TestCase):
    def setUp(self):
        self.client = APIClient(enforce_csrf_checks=True)

    def post(self, data, **extra):
        return self.client.post(URL, data, format='json', **(AUTH if not extra else extra))

    def test_valid_post_creates_run_and_four_series(self):
        response = self.post(body())
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json(), {'created': True})
        run = RainForecastRun.objects.get()
        self.assertEqual(run.hours, 96)
        self.assertEqual(run.job_version, 'test-1')
        self.assertEqual(RainForecastSeries.objects.filter(run=run).count(), 4)

    def test_duplicate_post_is_a_noop(self):
        self.post(body())
        response = self.post(body())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'created': False})
        self.assertEqual(RainForecastRun.objects.count(), 1)
        self.assertEqual(RainForecastSeries.objects.count(), 4)

    def test_missing_or_wrong_token_403(self):
        self.assertEqual(self.client.post(URL, body(), format='json').status_code, 403)
        self.assertEqual(
            self.client.post(URL, body(), format='json', HTTP_AUTHORIZATION='Bearer nope').status_code, 403)
        self.assertEqual(
            self.client.post(URL, body(), format='json', HTTP_AUTHORIZATION='s3cret').status_code, 403)
        self.assertEqual(self.client.get(STATUS_URL).status_code, 403)
        self.assertEqual(RainForecastRun.objects.count(), 0)

    def test_empty_server_token_rejects_everything(self):
        with override_settings(RAIN_WATCH_INGEST_TOKEN=''):
            for header in ('Bearer ', 'Bearer', ''):
                response = self.client.post(URL, body(), format='json', HTTP_AUTHORIZATION=header)
                self.assertEqual(response.status_code, 403, header)
            self.assertEqual(
                self.client.get(STATUS_URL, HTTP_AUTHORIZATION='Bearer ').status_code, 403)
        self.assertEqual(RainForecastRun.objects.count(), 0)

    def test_rejects_bad_bodies(self):
        good = body()

        def with_points(mutator):
            data = body()
            mutator(data['points'])
            return data

        def off_grid(points):
            points[0]['lat'] = 10.3

        def negative(points):
            points[1]['mm_per_hour'][3] = -0.1

        def nan(points):
            points[2]['mm_per_hour'][0] = 'NaN'

        def unequal(points):
            points[3]['mm_per_hour'] = [0.5] * 95

        cases = {
            'three points': with_points(lambda p: p.pop()),
            'duplicate point': with_points(lambda p: p.__setitem__(3, dict(p[0]))),
            'off grid': with_points(off_grid),
            'negative': with_points(negative),
            'nan': with_points(nan),
            'unequal': with_points(unequal),
            '121 values': body(n=121),
            'empty list': body(n=0),
            'init 03:00': body(init=last_cycle().replace(hour=3)),
            'init with minutes': body(init=last_cycle().replace(minute=30)),
            'init 11 days old': body(init=last_cycle(days_back=11)),
            'init in the future': body(init=last_cycle() + timedelta(hours=12)),
            'unknown source': body(source='other'),
            'no points': {k: v for k, v in good.items() if k != 'points'},
        }
        for name, data in cases.items():
            response = self.post(data)
            self.assertEqual(response.status_code, 400, name)
        self.assertEqual(RainForecastRun.objects.count(), 0)

    def test_accepts_120_values_and_near_future_init(self):
        self.assertEqual(self.post(body(n=120)).status_code, 201)

    def test_status_lists_recent_runs_with_hours(self):
        old = last_cycle(days_back=5)
        self.post(body(init=old))
        newer = last_cycle(days_back=1)
        self.post(body(init=newer, n=6, source='gfs-dynamical'))
        newest = last_cycle()
        self.post(body(init=newest, n=96))
        response = self.client.get(STATUS_URL, **AUTH)
        self.assertEqual(response.status_code, 200)
        runs = response.json()['runs']
        self.assertEqual([(r['source'], r['hours']) for r in runs],
                         [('gfs-nomads', 96), ('gfs-dynamical', 6)])
        self.assertEqual(set(runs[0]), {'source', 'init_time', 'hours'})
        self.assertEqual(datetime.fromisoformat(runs[0]['init_time'].replace('Z', '+00:00')), newest)

    def test_post_bumps_cache_version(self):
        cache.delete('rainwatch:version')
        self.post(body())
        first = cache.get('rainwatch:version')
        self.assertIsNotNone(first)
        self.post(body(init=last_cycle(days_back=1)))
        self.assertGreater(cache.get('rainwatch:version'), first)
        second = cache.get('rainwatch:version')
        self.assertEqual(self.post(body(init=last_cycle(days_back=1))).status_code, 200)  # duplicate
        self.assertEqual(cache.get('rainwatch:version'), second)

    def test_a_full_run_upgrades_one_stored_short(self):
        # The job re-fetches a newest run it holds short (fetch.plan_runs); the full one must replace it,
        # or the site stays stale while the job reports success.
        received = timezone.now() - timedelta(hours=13)
        init = last_cycle(received)
        with mock.patch('django.utils.timezone.now', return_value=received):
            self.assertEqual(self.post(body(init=init, n=6, job_version='gap-1')).status_code, 201)
        self.assertTrue(assess.is_stale(timezone.now(), BALANCED))
        version = cache.get(assess.VERSION_KEY, 0)

        full = body(init=init, n=96)
        for p in full['points']:
            p['mm_per_hour'] = [1.5] * 96
        response = self.post(full)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json(), {'created': False, 'upgraded': True})
        run = RainForecastRun.objects.get()
        self.assertEqual((run.hours, run.job_version), (96, 'test-1'))
        self.assertGreater(run.received_at, received + timedelta(hours=12))
        self.assertEqual(RainForecastSeries.objects.count(), 4)
        self.assertEqual([s.mm_per_hour for s in run.series.all()], [[1.5] * 96] * 4)
        self.assertFalse(assess.is_stale(timezone.now(), BALANCED))  # fresh
        self.assertGreater(cache.get(assess.VERSION_KEY), version)  # cached answers dropped

    def test_a_shorter_or_equal_run_changes_nothing(self):
        init = last_cycle()
        self.post(body(init=init, n=96))
        run = RainForecastRun.objects.get()
        version = cache.get(assess.VERSION_KEY)
        for n in (6, 96):
            response = self.post(body(init=init, n=n))
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json(), {'created': False})
        again = RainForecastRun.objects.get()
        self.assertEqual((again.hours, again.received_at), (96, run.received_at))
        self.assertEqual(sorted(len(s.mm_per_hour) for s in again.series.all()), [96] * 4)
        self.assertEqual(cache.get(assess.VERSION_KEY), version)

    def test_a_failing_cache_does_not_fail_a_stored_run(self):
        broken = mock.Mock()
        broken.incr.side_effect = ConnectionError('cache down')
        broken.set.side_effect = ConnectionError('cache down')
        with mock.patch('apps.rainwatch.assess.cache', broken), \
                self.assertLogs('apps.rainwatch.assess', 'WARNING'):
            response = self.post(body())
        self.assertEqual(response.status_code, 201)
        self.assertEqual(RainForecastSeries.objects.count(), 4)
