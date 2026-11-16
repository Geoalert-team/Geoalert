import io
import tempfile
from contextlib import redirect_stdout
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from django.contrib.gis.geos import MultiPolygon
from django.core.cache import cache
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase

from apps.barangays.models import Barangay
from apps.history import storms
from apps.history.storms import (
    StormDays, TrackPoint, covered_through, flag_days, haversine_km, live_storm_days, merge,
    parse_ibtracs, read_storm_days, refresh_recent, write_storm_days)
from tests.fire_setup import box

UTC = timezone.utc
CENTRE = (10.2447, 123.8494)
HEADER = 'SID,SEASON,NUMBER,BASIN,SUBBASIN,NAME,ISO_TIME,NATURE,LAT,LON,WMO_WIND,WMO_PRES'
UNITS = ' ,Year, ,Basin,Subbasin, ,,,degrees_north,degrees_east,kts,mb'
KM_PER_DEG = 6371.0088 * 3.141592653589793 / 180


def utc(text):
    return datetime.strptime(text, '%Y-%m-%d %H:%M:%S').replace(tzinfo=UTC)


def point(text, name='NONAME', sid='S1', lat=CENTRE[0], lon=CENTRE[1]):
    return TrackPoint(sid, name, utc(text), lat, lon)


def row(time, lat, lon, name='KIKO', sid='2025300N10130'):
    return f'{sid},2025,1,WP,MM,{name},{time},TS,{lat},{lon},35,990'


def csv_lines(*rows):
    return [HEADER, UNITS, *rows]


def lm(text='Thu, 12 Nov 2026 10:06:46 GMT'):
    return datetime(2026, 11, 12, 10, 6, 46, tzinfo=UTC)


class FlagDaysTests(SimpleTestCase):
    def test_a_point_late_on_a_manila_day_flags_that_day_and_the_next_two(self):
        p = point('2025-11-04 15:59:00')                 # UTC = 23:59 Manila on 4 Nov
        self.assertEqual(sorted(flag_days([p], CENTRE)), [date(2025, 11, 4), date(2025, 11, 5), date(2025, 11, 6)])

    def test_a_point_at_manila_midnight_belongs_to_the_day_before(self):
        p = point('2025-11-04 16:00:00')                 # 00:00 Manila on 5 Nov = end of 4 Nov
        self.assertEqual(sorted(flag_days([p], CENTRE)), [date(2025, 11, 4), date(2025, 11, 5), date(2025, 11, 6)])

    def test_closest_distance_and_name_are_kept_per_day(self):
        far = point('2025-11-04 02:00:00', name='FAR', sid='A', lat=CENTRE[0] + 2.0)
        near = point('2025-11-04 06:00:00', name='NEAR', sid='B', lat=CENTRE[0] + 1.0)
        got = flag_days([far, near], CENTRE)
        sid, name, km = got[date(2025, 11, 4)]
        self.assertEqual((sid, name), ('B', 'NEAR'))
        self.assertAlmostEqual(km, KM_PER_DEG, delta=1.0)


class ParseTests(SimpleTestCase):
    def test_points_beyond_300_km_are_dropped(self):
        d = 1.0 / KM_PER_DEG
        lines = csv_lines(row('2025-11-04 06:00:00', CENTRE[0] + 299 * d, CENTRE[1], sid='IN'),
                          row('2025-11-04 06:00:00', CENTRE[0] + 301 * d, CENTRE[1], sid='OUT'))
        got = parse_ibtracs(lines, CENTRE, date(2025, 1, 1))
        self.assertEqual([p.sid for p in got], ['IN'])

    def test_units_row_is_skipped_and_since_is_respected(self):
        lines = csv_lines(row('2025-10-20 18:00:00', ' 10.3', ' 123.9', sid='OLD'),
                          row('2025-11-01 00:00:00', ' 10.3', ' 123.9', sid='NEW'))
        got = parse_ibtracs(lines, CENTRE, date(2025, 11, 1))
        self.assertEqual([p.sid for p in got], ['NEW'])
        self.assertEqual(got[0].time, utc('2025-11-01 00:00:00'))
        self.assertEqual(got[0].lat, 10.3)

    def test_a_point_just_before_since_still_flags_the_first_days(self):
        since = date(2006, 12, 18)
        lines = csv_lines(row('2006-12-17 20:00:00', 10.3, 123.9, sid='A'),
                          row('2006-12-16 23:00:00', 10.3, 123.9, sid='B'))
        pts = parse_ibtracs(lines, CENTRE, since)
        self.assertEqual([p.sid for p in pts], ['A', 'B'])
        a = storms.build(pts[:1], CENTRE, since, lm())
        self.assertEqual(sorted(a.days), [date(2006, 12, 18), date(2006, 12, 19), date(2006, 12, 20)])
        b = storms.build(pts[1:], CENTRE, since, lm())
        self.assertEqual(sorted(b.days), [date(2006, 12, 18), date(2006, 12, 19)])   # 12-17 is before since
        self.assertIsNone(b.flag(date(2006, 12, 17)))
        self.assertEqual(b.first_day, since)

    def test_lines_are_text_even_when_requests_cannot_infer_an_encoding(self):
        class Resp:
            encoding = None

            def iter_lines(self, decode_unicode=False):
                return iter([b'a,b'] if self.encoding is None else ['a,b'])
        self.assertEqual(list(storms.decoded_lines(Resp())), ['a,b'])

    def test_blank_coordinates_are_skipped(self):
        lines = csv_lines(row('2025-11-01 00:00:00', ' ', ' '))
        self.assertEqual(parse_ibtracs(lines, CENTRE, date(2025, 1, 1)), [])

    def test_a_download_gives_up_quickly_on_a_slow_server(self):
        # a forecast request can be waiting on the live download (under the build lock): 5 s to connect, then
        # at most 20 s between reads, never two minutes
        resp = mock.Mock(headers={'Last-Modified': 'Thu, 12 Nov 2026 10:06:46 GMT'})
        with mock.patch.object(storms.requests, 'get', return_value=resp) as fetch:
            _, modified = storms.get(storms.ACTIVE_URL)
        self.assertEqual(fetch.call_args.kwargs['timeout'], (5, 20))
        self.assertTrue(fetch.call_args.kwargs['stream'])
        self.assertEqual(modified, lm())


class HelpersTests(SimpleTestCase):
    def test_haversine_one_degree_of_latitude(self):
        self.assertAlmostEqual(haversine_km(10, 123, 11, 123), KM_PER_DEG, places=3)

    def test_covered_through_is_the_manila_day_before_the_file_time(self):
        self.assertEqual(covered_through(datetime(2026, 11, 12, 10, 6, 46, tzinfo=UTC)), date(2026, 11, 11))

    def test_covered_through_uses_the_manila_date(self):
        # 20:00 UTC on 12 Nov is already 13 Nov in Manila
        self.assertEqual(covered_through(datetime(2026, 11, 12, 20, 0, 0, tzinfo=UTC)), date(2026, 11, 12))

    def test_flag_is_none_outside_coverage(self):
        sd = StormDays({date(2025, 11, 5): ('S', 'N', 10.0)}, date(2025, 11, 1), date(2025, 11, 10))
        self.assertEqual(sd.flag(date(2025, 11, 5)), 1)
        self.assertEqual(sd.flag(date(2025, 11, 6)), 0)
        self.assertIsNone(sd.flag(date(2025, 10, 31)))
        self.assertIsNone(sd.flag(date(2025, 11, 11)))
        self.assertEqual(sd.name(date(2025, 11, 5)), 'N')
        self.assertIsNone(sd.name(date(2025, 11, 6)))

    def test_merge_unions_days_keeps_the_closer_and_widens_coverage(self):
        a = StormDays({date(2025, 11, 5): ('A', 'A', 50.0)}, date(2025, 1, 1), date(2025, 11, 10))
        b = StormDays({date(2025, 11, 5): ('B', 'B', 20.0), date(2025, 11, 12): ('B', 'B', 9.0)},
                      date(2025, 6, 1), date(2025, 11, 13))
        m = merge(a, b)
        self.assertEqual(m.days[date(2025, 11, 5)], ('B', 'B', 20.0))
        self.assertIn(date(2025, 11, 12), m.days)
        self.assertEqual((m.first_day, m.last_day), (date(2025, 1, 1), date(2025, 11, 13)))

    def test_merge_of_touching_inputs_is_continuous(self):
        a = StormDays({}, date(2025, 1, 1), date(2025, 6, 30))
        b = StormDays({date(2025, 7, 2): ('B', 'B', 5.0)}, date(2025, 7, 1), date(2025, 7, 10))
        m = merge(a, b)
        self.assertEqual((m.first_day, m.last_day), (date(2025, 1, 1), date(2025, 7, 10)))
        self.assertEqual(m.flag(date(2025, 7, 1)), 0)
        self.assertEqual(m.flag(date(2025, 7, 2)), 1)

    def test_merge_of_gapped_inputs_does_not_claim_the_gap(self):
        a = StormDays({}, date(2025, 1, 1), date(2025, 6, 30))
        b = StormDays({date(2025, 7, 5): ('B', 'B', 5.0)}, date(2025, 7, 2), date(2025, 7, 10))
        with self.assertLogs('apps.history.storms', level='WARNING'):
            m = merge(b, a)
        self.assertEqual((m.first_day, m.last_day), (date(2025, 1, 1), date(2025, 6, 30)))
        self.assertIsNone(m.flag(date(2025, 7, 1)))
        self.assertIsNone(m.flag(date(2025, 7, 5)))

    def test_write_and_read_round_trip(self):
        sd = StormDays({date(2025, 11, 5): ('S1', 'KIKO, JR', 123.456), date(2025, 11, 6): ('S1', 'KIKO, JR', 99.0)},
                       date(2006, 12, 18), date(2026, 11, 11))
        with tempfile.TemporaryDirectory() as tmp:
            p, m = Path(tmp) / 's.csv', Path(tmp) / 's.meta.json'
            write_storm_days(sd, 'unit test', datetime(2026, 11, 12, 10, 0, tzinfo=UTC), CENTRE, p, m)
            got = read_storm_days(p, m)
            self.assertEqual(got, sd)
            with self.assertRaises(FileNotFoundError):
                read_storm_days(Path(tmp) / 'none.csv', Path(tmp) / 'none.json')


def fake_get(recent=None, active=None, calls=None):
    """Answers by file name like the real get(url): (lines, Last-Modified)."""
    def get(url):
        if calls is not None:
            calls.append(url)
        want = active if 'ACTIVE' in url else recent
        if isinstance(want, Exception):
            raise want
        return want
    return get


BASE = StormDays({}, date(2006, 12, 18), date(2026, 11, 1))
TODAY = date(2026, 11, 13)


class LiveTests(SimpleTestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        p = mock.patch.object(storms, 'talisay_centre', return_value=CENTRE)
        p.start()
        self.addCleanup(p.stop)
        self.now = datetime(2026, 11, 13, 1, 0, tzinfo=UTC)     # 09:00 Manila on 13 Nov

    def files(self):
        recent = (csv_lines(row('2026-11-09 00:00:00', 10.3, 123.9, sid='R')), lm())
        active = (csv_lines(row('2026-11-12 00:00:00', 10.3, 123.9, sid='A')), lm())
        return recent, active

    def test_live_coverage_reaches_yesterday_only_with_a_fresh_recent_copy_and_the_active_file(self):
        recent, active = self.files()
        get = fake_get(recent, active)
        self.assertTrue(refresh_recent(get=get, now=self.now))
        live = live_storm_days(BASE, TODAY, get=get)
        self.assertEqual(live.last_day, date(2026, 11, 12))
        self.assertEqual(live.flag(date(2026, 11, 12)), 1)
        self.assertEqual(live.flag(date(2026, 11, 10)), 1)
        self.assertEqual(live.name(date(2026, 11, 12)), 'KIKO')
        self.assertIsNone(live.flag(date(2026, 11, 13)))

    def test_a_stale_recent_copy_limits_coverage_even_with_the_active_file(self):
        recent, active = self.files()
        old = (recent[0], datetime(2026, 11, 3, 10, 0, tzinfo=UTC))      # covered through 2 Nov: 11 days back
        get = fake_get(old, active)
        refresh_recent(get=get, now=self.now)
        live = live_storm_days(BASE, TODAY, get=get)
        self.assertEqual(live.last_day, date(2026, 11, 11))   # furthest available: the active file's own day

    def test_live_coverage_falls_back_when_the_active_file_fails(self):
        recent, _ = self.files()
        get = fake_get(recent, OSError('down'))
        refresh_recent(get=get, now=self.now)
        live = live_storm_days(BASE, TODAY, get=get)
        self.assertEqual(live.last_day, covered_through(lm()))        # the recent copy's last day
        self.assertNotEqual(live.last_day, TODAY - timedelta(days=1))

    def test_refresh_recent_runs_once_a_day_and_never_raises(self):
        recent, active = self.files()
        calls = []
        get = fake_get(recent, active, calls)
        self.assertTrue(refresh_recent(get=get, now=self.now))
        self.assertTrue(refresh_recent(get=get, now=self.now))
        self.assertEqual(len(calls), 1)
        cache.clear()
        boom = fake_get(RuntimeError('no network'), active)
        with self.assertLogs('apps.history.storms', level='WARNING'):
            self.assertFalse(refresh_recent(get=boom, now=self.now))


class CommandTests(TestCase):
    def setUp(self):
        cache.clear()
        for name, x in (('A', 0), ('B', 1000)):
            Barangay.objects.create(name=name, municipality='Talisay',
                                    boundary=MultiPolygon(box(x, 0, x + 1000, 1000), srid=4326))

    def test_command_writes_the_files_with_a_fake_download(self):
        calls = []

        def get(url):
            calls.append(url)
            if 'last3years' in url:
                return csv_lines(row('2025-11-04 06:00:00', 10.3, 123.9, sid='L3')), lm()
            return csv_lines(row('2012-11-04 06:00:00', 10.3, 123.9, sid='WP1'),
                             row('2012-11-04 06:00:00', 40.0, 123.9, sid='FAR')), lm()

        with tempfile.TemporaryDirectory() as tmp:
            sf, mf = Path(tmp) / 'storm_days.csv', Path(tmp) / 'storm_days.meta.json'
            with mock.patch.object(storms, 'STORM_FILE', sf), mock.patch.object(storms, 'META_FILE', mf), \
                    mock.patch.object(storms, 'get', get), redirect_stdout(io.StringIO()):
                call_command('fetch_storms')
            sd = read_storm_days(sf, mf)
            self.assertEqual(len(calls), 2)
            self.assertEqual(sd.flag(date(2012, 11, 4)), 1)
            self.assertEqual(sd.flag(date(2025, 11, 5)), 1)
            self.assertEqual(sd.flag(date(2012, 11, 20)), 0)
            self.assertEqual(sd.first_day, date(2006, 12, 18))
            self.assertEqual(sd.last_day, date(2026, 11, 11))
            self.assertEqual(sd.name(date(2012, 11, 4)), 'KIKO')

            calls.clear()
            with mock.patch.object(storms, 'STORM_FILE', sf), mock.patch.object(storms, 'META_FILE', mf), \
                    mock.patch.object(storms, 'get', get), redirect_stdout(io.StringIO()):
                call_command('fetch_storms', '--recent')
            self.assertEqual(len(calls), 1)
            self.assertEqual(read_storm_days(sf, mf).flag(date(2012, 11, 4)), 1)
