"""The seam between the forecast job (tools/rain_forecast/fetch.py) and the rain-watch ingest endpoints.

The job's own payload builder, poster and status reader run against the real endpoints, so a change on
either side that breaks the other fails here. The tool is loaded by file path; nothing goes on the network.
"""
import importlib.util
import sys
from datetime import timedelta
from pathlib import Path

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.rainwatch.models import RainForecastRun

TOOL = Path(__file__).resolve().parents[2] / 'tools' / 'rain_forecast' / 'fetch.py'
API = 'https://geoalert.example'
TOKEN = 's3cret'


def load_fetch():
    """tools/rain_forecast/fetch.py as a module. It puts its folder on sys.path to import gfs; undo that."""
    saved, had_gfs = list(sys.path), 'gfs' in sys.modules
    spec = importlib.util.spec_from_file_location('rain_forecast_fetch', TOOL)
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path[:] = saved
        if not had_gfs:
            sys.modules.pop('gfs', None)  # fetch keeps its own reference
    return module


fetch = load_fetch()


def last_cycle(now):
    return now.replace(hour=now.hour // 6 * 6, minute=0, second=0, microsecond=0)


@override_settings(RAIN_WATCH_INGEST_TOKEN=TOKEN)
class JobContractTests(TestCase):
    def setUp(self):
        cache.clear()
        self.api = APIClient()
        self.headers = {'Authorization': f'Bearer {TOKEN}'}
        self.answers = []

    def _path(self, url):
        self.assertTrue(url.startswith(API), url)
        return url[len(API):]

    # The job's own get(url, headers=...) and post(url, body, headers), served by the test client;
    # like requests' raise_for_status, an error status raises.
    def get(self, url, headers=None):
        response = self.api.get(self._path(url), HTTP_AUTHORIZATION=(headers or {}).get('Authorization', ''))
        if response.status_code >= 400:
            raise RuntimeError(f'{response.status_code}: {response.content!r}')
        return response.content

    def post(self, url, body, headers):
        response = self.api.post(self._path(url), body, format='json', HTTP_AUTHORIZATION=headers['Authorization'])
        if response.status_code >= 400:
            raise RuntimeError(f'{response.status_code}: {response.content!r}')
        self.answers.append((response.status_code, response.json()))
        return response.status_code

    def no_sleep(self, seconds):
        self.fail('a post failed and the job would retry')

    def send(self, init, hours, mm, source='gfs-nomads'):
        """The job's payload for a run of `hours` hours of `mm` mm an hour at each grid point, posted its way."""
        series = {point: [mm] * hours for point in fetch.gfs.GRID}
        body = fetch.payload(source, init, series, fetch.JOB_VERSION)
        return fetch._post_with_retries(self.post, f'{API}/api/rain-watch/forecast-runs/', body, self.headers,
                                        self.no_sleep)

    def held(self):
        return fetch._held_runs(API, self.headers, self.get)

    def test_job_payload_passes_the_ingest_checks(self):
        now = timezone.now()
        init = last_cycle(now)
        self.assertTrue(self.send(init, fetch.FULL_HOURS, 0.25))
        self.assertEqual(self.answers, [(201, {'created': True})])
        run = RainForecastRun.objects.get()
        self.assertEqual((run.source, run.init_time, run.hours, run.job_version),
                         ('gfs-nomads', init, fetch.FULL_HOURS, fetch.JOB_VERSION))
        series = {(float(s.lat), float(s.lon)): s for s in run.series.all()}
        self.assertEqual(set(series), set(fetch.gfs.GRID))
        for s in series.values():
            self.assertEqual((s.first_hour_start, s.mm_per_hour), (init, [0.25] * fetch.FULL_HOURS))

        # A gap-fill run from dynamical.org passes too
        self.assertTrue(self.send(init - timedelta(hours=6), fetch.GAP_HOURS, 0.5, source='gfs-dynamical'))
        self.assertEqual(self.answers[-1], (201, {'created': True}))

        # The status endpoint, read the job's way: both runs held, so neither is planned again
        held = self.held()
        self.assertEqual(sorted((r['source'], fetch._parse(r['init_time']), r['hours']) for r in held),
                         [('gfs-dynamical', init - timedelta(hours=6), fetch.GAP_HOURS),
                          ('gfs-nomads', init, fetch.FULL_HOURS)])
        plan = fetch.plan_runs(now, held, init)
        self.assertNotIn(init, [cycle for cycle, _ in plan])
        self.assertNotIn(init - timedelta(hours=6), [cycle for cycle, _ in plan])
        self.assertTrue(all(hours == fetch.GAP_HOURS for _, hours in plan))

    def test_a_newest_run_held_short_is_fetched_again_and_upgraded(self):
        now = timezone.now()
        init = last_cycle(now)
        self.assertTrue(self.send(init, fetch.GAP_HOURS, 0.25))
        self.assertEqual(fetch.plan_runs(now, self.held(), init)[0], (init, fetch.FULL_HOURS))

        self.assertTrue(self.send(init, fetch.FULL_HOURS, 0.5))
        self.assertEqual(self.answers[-1], (200, {'created': False, 'upgraded': True}))
        run = RainForecastRun.objects.get()
        self.assertEqual(run.hours, fetch.FULL_HOURS)
        self.assertEqual([s.mm_per_hour for s in run.series.all()], [[0.5] * fetch.FULL_HOURS] * 4)
        self.assertNotIn(init, [cycle for cycle, _ in fetch.plan_runs(now, self.held(), init)])
