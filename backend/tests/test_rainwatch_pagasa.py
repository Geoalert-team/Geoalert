"""Rain watch Task 5: the PAGASA CAP feed reader, the floor rules and the hourly start."""
from datetime import datetime, timedelta, timezone as dt_tz
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from django.contrib.gis.geos import Point, Polygon
from django.core.cache import cache
from django.test import TestCase, override_settings

from apps.history.exposure import read_exposure
from apps.history.hazard_data import read_terrain
from apps.rainwatch import assess, pagasa
from apps.rainwatch.models import PagasaAlert
from apps.rainwatch.rules import BALANCED, ORANGE, RED, YELLOW

FIX = Path(__file__).parent / 'fixtures' / 'pagasa'
FEED = (FIX / 'feed.xml').read_text(encoding='utf-8')
GFA = (FIX / 'gfa_south_cotabato.cap').read_text(encoding='utf-8')
TC = (FIX / 'tc_alert_samuel.cap').read_text(encoding='utf-8')
SQUARE = [(10.0, 123.5), (10.5, 123.5), (10.5, 124.0), (10.0, 124.0), (10.0, 123.5)]
GFA_ID = 'bd7f6925-22e0-459a-83ce-c499ac546cf7'
TC_ID = 'a3f06dfd-42e2-4720-8071-f3173e8715e5'
TC_SEVERE = TC.replace('<severity>Minor</severity>', '<severity>Severe</severity>')
TC_WITH_CEBU_CODE = TC_SEVERE.replace(
    '</polygon></area>', '</polygon><geocode><valueName>SAME</valueName><value>072200000</value></geocode></area>')
TC_NAMING_CEBU = TC_SEVERE.replace('<areaDesc>Philippine Area of Responsibility</areaDesc>', '<areaDesc>Cebu</areaDesc>')
IN_SAMUEL = datetime(2026, 11, 9, 6, tzinfo=dt_tz.utc)  # 14:00 in Manila, while the Samuel alert runs


def box(south, west, north, east):
    return [(south, west), (north, west), (north, east), (south, east), (south, west)]


def alert(**kw):
    base = dict(identifier='x', event='', severity='', msg_type='Alert', response_type='Prepare',
                urgency='Expected', references='', covers_talisay=True, sent=None, effective=None,
                expires=None)
    base.update(kw)
    return SimpleNamespace(**base)


class ParseTests(TestCase):
    def test_parse_feed_fixture(self):
        entries = pagasa.parse_feed(FEED)
        self.assertEqual(len(entries), 15)
        self.assertEqual(entries[0][0], GFA_ID)
        self.assertTrue(entries[0][1].endswith('.cap'))

    def test_parse_gfa_fixture(self):
        cap = pagasa.parse_cap(GFA, 'http://x/a.cap')
        self.assertEqual(cap['event'], 'General Flood Advisory (Final)')
        self.assertEqual(cap['severity'], 'Minor')
        self.assertEqual(cap['response_type'], 'AllClear')
        self.assertFalse(pagasa.covers_talisay(cap))

    def test_parse_tc_fixture(self):
        cap = pagasa.parse_cap(TC, 'http://x/b.cap')
        self.assertEqual(cap['event'], 'Tropical Cyclone Alert')
        self.assertEqual(cap['severity'], 'Minor')
        self.assertIsNotNone(cap['expires'])

    def test_covers_by_polygon_geocode_and_name(self):
        self.assertTrue(pagasa.covers_talisay({'polygons': [SQUARE], 'geocodes': [], 'area_desc': ''}))
        self.assertTrue(pagasa.covers_talisay({'polygons': [], 'geocodes': ['072200000'], 'area_desc': ''}))
        self.assertTrue(pagasa.covers_talisay({'polygons': [], 'geocodes': [], 'area_desc': 'Cebu'}))
        self.assertFalse(pagasa.covers_talisay({'polygons': [], 'geocodes': [], 'area_desc': 'Bohol'}))

    def test_only_a_province_sized_polygon_counts(self):
        # User ruling 2026-11-18: an alert counts only if it names Cebu or its area is about province-sized.
        # A polygon counts when its bounding box spans at most 3.0 degrees of latitude and of longitude.
        here = Point(pagasa.TALISAY[1], pagasa.TALISAY[0])
        cap = pagasa.parse_cap(TC_SEVERE, 'u')
        par = cap['polygons'][0]
        self.assertTrue(Polygon([(lon, lat) for lat, lon in par]).contains(here))  # PAGASA's PAR polygon holds it
        self.assertFalse(pagasa.covers_talisay(cap))
        # The same alert with Cebu's geocode, or naming Cebu, counts
        self.assertTrue(pagasa.covers_talisay(pagasa.parse_cap(TC_WITH_CEBU_CODE, 'u')))
        self.assertTrue(pagasa.covers_talisay(pagasa.parse_cap(TC_NAMING_CEBU, 'u')))
        # At the edge: 3.0 degrees each way counts, a little more either way does not
        def covers(*polygons, area_desc=''):
            return pagasa.covers_talisay({'polygons': list(polygons), 'geocodes': [], 'area_desc': area_desc})

        self.assertTrue(covers(box(9.0, 122.5, 12.0, 125.5)))
        self.assertFalse(covers(box(9.0, 122.5, 12.01, 125.5)))
        self.assertFalse(covers(box(9.0, 122.5, 12.0, 125.51)))
        # A small polygon elsewhere still outweighs the name, as before
        self.assertFalse(covers(box(6.0, 124.0, 7.0, 125.0), area_desc='Cebu'))
        # A big polygon and a small one holding the city: the small one counts
        self.assertTrue(covers(par, SQUARE))

    def test_broken_cap_raises_value_error(self):
        with self.assertRaises(ValueError):
            pagasa.parse_cap('<html>502</html>', 'u')
        with self.assertRaises(ValueError):
            pagasa.parse_cap('<html', 'u')


class RuleTests(TestCase):
    def test_floor_mapping(self):
        self.assertEqual(pagasa.floor_for(alert(event='General Flood Advisory', severity='Minor')), {'Flood': YELLOW})
        self.assertEqual(pagasa.floor_for(alert(event='General Flood Advisory', severity='Severe')), {'Flood': ORANGE})
        self.assertEqual(pagasa.floor_for(alert(event='Tropical Cyclone Alert', severity='Severe')),
                         {'Flood': ORANGE, 'Landslide': ORANGE})
        self.assertEqual(pagasa.floor_for(alert(event='Tropical Cyclone Alert', severity='Extreme')),
                         {'Flood': RED, 'Landslide': RED})
        self.assertEqual(pagasa.floor_for(alert(event='Tropical Cyclone Alert', severity='Minor')), {})
        self.assertEqual(pagasa.floor_for(alert(event='Thunderstorm Advisory', severity='Severe')), {})
        self.assertEqual(pagasa.floor_for(alert(event='Heavy Rainfall Warning', severity='Moderate')),
                         {'Flood': YELLOW, 'Landslide': YELLOW})

    def test_mapped_event_types(self):
        # Spec 6.5's table: "Flood", "Tropical Cyclone" or "Rainfall" in the event name, whatever the severity
        for event in ('General Flood Advisory', 'General Flood Advisory (Final)', 'Tropical Cyclone Alert',
                      'Heavy Rainfall Warning'):
            self.assertTrue(pagasa.is_mapped(alert(event=event, severity='Minor')), event)
        for event in ('Thunderstorm Advisory', 'Earthquake Information', ''):
            self.assertFalse(pagasa.is_mapped(alert(event=event, severity='Extreme')), event)

    def test_active_rules(self):
        now = datetime(2026, 11, 18, 12, tzinfo=dt_tz.utc)
        ok = dict(sent=now - timedelta(hours=1), expires=now + timedelta(hours=1))
        self.assertTrue(pagasa.is_active(alert(**ok), now, set()))
        self.assertFalse(pagasa.is_active(
            alert(sent=now - timedelta(hours=3), expires=now - timedelta(hours=1)), now, set()))
        self.assertFalse(pagasa.is_active(alert(**ok, msg_type='Cancel'), now, set()))
        self.assertFalse(pagasa.is_active(alert(**ok, response_type='AllClear'), now, set()))
        self.assertFalse(pagasa.is_active(alert(**ok, urgency='Past'), now, set()))
        self.assertFalse(pagasa.is_active(alert(**ok, covers_talisay=False), now, set()))
        self.assertFalse(pagasa.is_active(alert(**ok, identifier='old'), now, {'old'}))
        self.assertFalse(pagasa.is_active(
            alert(sent=now + timedelta(hours=1), expires=now + timedelta(hours=2)), now, set()))

    def test_referenced_identifiers(self):
        a = alert(references='PAGASA-DOST,aaa,2026-11-13T17:09:19+08:00 PAGASA-DOST,bbb,2026-11-13T17:09:19+08:00')
        self.assertEqual(pagasa.referenced_identifiers([a, alert(references='')]), {'aaa', 'bbb'})


class CheckFeedTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_check_feed_stores_new_and_skips_known(self):
        entries = pagasa.parse_feed(FEED)
        caps = {url: GFA.replace(GFA_ID, ident) for ident, url in entries}

        def get(url):
            return FEED if url == pagasa.FEED_URL else caps[url]

        with mock.patch('apps.rainwatch.assess.bump') as bump:
            self.assertEqual(pagasa.check_feed(get=get), 15)
            self.assertEqual(PagasaAlert.objects.count(), 15)
            self.assertEqual(pagasa.check_feed(get=get), 0)
            self.assertEqual(bump.call_count, 1)
        row = PagasaAlert.objects.get(identifier=entries[0][0])
        self.assertFalse(row.covers_talisay)
        self.assertEqual(row.msg_type, 'Update')
        self.assertTrue(row.raw_xml)

    def test_malformed_entries_are_skipped(self):
        entries = pagasa.parse_feed(FEED)[:3]
        no_expires = GFA.replace('<expires>2026-11-14T17:17:01+08:00</expires>', '')
        caps = {entries[0][1]: '<html>502</html>',
                entries[1][1]: no_expires.replace(GFA_ID, entries[1][0]),
                entries[2][1]: GFA.replace(GFA_ID, entries[2][0])}

        def get(url):
            if url == pagasa.FEED_URL:
                return FEED
            if url not in caps:
                raise OSError('down')
            return caps[url]

        with self.assertLogs('apps.rainwatch.pagasa', level='WARNING'):
            self.assertEqual(pagasa.check_feed(get=get), 1)
        self.assertEqual(PagasaAlert.objects.get().identifier, entries[2][0])
        with self.assertLogs('apps.rainwatch.pagasa', level='WARNING'):
            self.assertEqual(pagasa.check_feed(get=lambda url: '<html>502</html>'), 0)

    def test_a_country_wide_alert_is_stored_as_not_for_talisay(self):
        url = 'https://publicalert.pagasa.dost.gov.ph/output/tc/samuel.cap'
        for cap, covers in ((TC_SEVERE, False), (TC_WITH_CEBU_CODE, True), (TC_NAMING_CEBU, True)):
            PagasaAlert.objects.all().delete()
            with mock.patch('apps.rainwatch.pagasa.parse_feed', return_value=[(TC_ID, url)]), \
                    mock.patch('apps.rainwatch.assess.bump'):
                self.assertEqual(pagasa.check_feed(get=lambda u, cap=cap: cap), 1)
            row = PagasaAlert.objects.get()
            self.assertEqual((row.severity, row.covers_talisay), ('Severe', covers))

            r = assess.build(IN_SAMUEL, BALANCED, [], {'mm_14_days': None, 'wet': None}, [row], [],
                             read_exposure(), read_terrain(), {1: 'Biasong', 4: 'Camp IV'})
            entry = r['pagasa_alerts'][0]
            self.assertEqual((entry['covers_talisay'], entry['mapped'], entry['active'], entry['applied']),
                             (covers, True, covers, covers))
            biasong = r['days'][0]['barangays'][0]['flood']
            if covers:
                self.assertEqual([f['level'] for f in r['floors']], ['Orange', 'Orange'])
                self.assertEqual(biasong['level'], 'Orange')
            else:  # no floor: the forecast part alone (no runs here)
                self.assertEqual(r['floors'], [])
                self.assertEqual(biasong, {'level': 'unknown', 'reasons': ['Forecast out of date']})

    def test_utf8_bytes_keep_curly_quotes(self):
        entries = pagasa.parse_feed(FEED)[:1]
        cap = GFA.replace(GFA_ID, entries[0][0]).replace(
            '<headline>General Flood Advisory (Final)</headline>',
            '<headline>“Samuel” advisory</headline>')
        self.assertIn('“', cap)
        data = cap.encode('utf-8')
        get = lambda url: FEED.encode('utf-8') if url == pagasa.FEED_URL else data
        self.assertEqual(pagasa.check_feed(get=get), 1)
        row = PagasaAlert.objects.get()
        self.assertEqual(row.headline, '“Samuel” advisory')
        self.assertIn('“', row.raw_xml)


class HookTests(TestCase):
    def setUp(self):
        cache.clear()
        warm = mock.patch('apps.history.hazard_forecast.warm_in_background')
        warm.start()
        self.addCleanup(warm.stop)

    def _get(self):
        return self.client.get('/api/hazards/')

    @override_settings(PAGASA_FEED_WRITER=True)
    def test_hazard_list_survives_a_failing_check(self):
        with mock.patch('apps.rainwatch.pagasa.check_in_background', side_effect=RuntimeError('boom')), \
                self.assertLogs('apps.hazards.views', 'ERROR') as logs:
            self.assertEqual(self._get().status_code, 200)
        logged = [(r.getMessage(), str(r.exc_info[1])) for r in logs.records if r.exc_info]
        self.assertIn(('Could not start the PAGASA feed check.', 'boom'), logged)

    @override_settings(PAGASA_FEED_WRITER=True)
    def test_hook_runs_at_most_hourly(self):
        with mock.patch('apps.rainwatch.pagasa.check_in_background') as start:
            self._get()
            self._get()
            self.assertEqual(start.call_count, 1)

    @override_settings(PAGASA_FEED_WRITER=False)
    def test_hook_off_when_not_the_writer(self):
        with mock.patch('apps.rainwatch.pagasa.check_in_background') as start:
            self._get()
            self.assertEqual(start.call_count, 0)
