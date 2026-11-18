"""Rain watch levels (assess.build and friends) and GET /api/rain-watch/."""
import csv
import dataclasses
import json
import threading
import time as _time
from datetime import date, datetime, time, timedelta, timezone as dt_tz
from unittest import mock

from django.core.cache import cache
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import Role, User
from apps.barangays.models import Barangay
from apps.history.exposure import EXPOSURE_FILE, read_exposure
from apps.history.hazard_data import MANILA, read_terrain
from apps.history.rain import RainFile
from apps.rainwatch import assess
from apps.rainwatch.models import PagasaAlert, RainForecastRun, RainForecastSeries, RainWatchOverride
from apps.rainwatch.rules import BALANCED
from apps.rainwatch.series import GRID

URL = '/api/rain-watch/'
RUNS_URL = '/api/rain-watch/forecast-runs/'
NOW = datetime(2026, 11, 18, 4, tzinfo=dt_tz.utc)  # 12:00 in Manila on 18 Nov
TODAY = date(2026, 11, 18)
H = timedelta(hours=1)
FULL_INIT = datetime(2026, 11, 15, 12, tzinfo=dt_tz.utc)  # 124 hours from here reach the end of the Day after
FULL_HOURS = 124

DRY = {'mm_14_days': 80.0, 'wet': False}
WET = {'mm_14_days': 170.0, 'wet': True}
UNKNOWN = {'mm_14_days': None, 'wet': None}

LIMITED = 'Fewer homes in flood-prone ground: one step lower'
STALE = 'Forecast out of date'

EXPOSURE = read_exposure()
TERRAIN = read_terrain()
with open(EXPOSURE_FILE, newline='', encoding='utf-8') as _f:
    NAMES = {int(r['barangay_id']): r['barangay'] for r in csv.DictReader(_f)}

# Southern grid points get 5/8 of the rain and northern ones 15/8: the upland point then reads exactly
# the day's mm, and the city about 79% of it.
SOUTH, NORTH = 0.625, 1.875


def iso(dt):
    return dt.astimezone(dt_tz.utc).isoformat().replace('+00:00', 'Z')


def stored_run(init, hours, daily, received=None, source='gfs-nomads', tilt=False):
    """A stored run spreading daily(Manila date) mm evenly over each day's hours."""
    values = [daily((init + k * H).astimezone(MANILA).date()) / 24 for k in range(hours)]
    series = {p: [v * ((SOUTH if p[0] == 10.25 else NORTH) if tilt else 1.0) for v in values] for p in GRID}
    return assess.StoredRun(source, init, series, received_at=received or NOW - H, hours=hours)


def on(mm_by_day, other=0.0):
    return lambda d: mm_by_day.get(d, other)


def flat(mm):
    return lambda d: mm


def build(runs=(), wet=DRY, alerts=(), overrides=(), barangays=None, rules=BALANCED, now=NOW):
    return assess.build(now, rules, list(runs), wet, list(alerts), list(overrides), EXPOSURE, TERRAIN,
                        barangays or NAMES)


def part(result, key, bid, hazard='flood'):
    day = next(d for d in result['days'] if d['key'] == key)
    return next(b for b in day['barangays'] if b['id'] == bid)[hazard]


def all_levels(result):
    return {p['level'] for d in result['days'] for b in d['barangays']
            for p in (b['flood'], b['landslide']) if p is not None}


def alert(**over):
    data = dict(identifier='tc-1', sent=NOW - H, effective=NOW - H, expires=NOW + 6 * H, msg_type='Alert',
                references='', event='Tropical Cyclone Alert', category='Met', response_type='Prepare',
                urgency='Expected', severity='Severe', certainty='Likely', headline='TC alert for Cebu',
                area_desc='Cebu', covers_talisay=True)
    data.update(over)
    return PagasaAlert(**data)


def override(**over):
    data = dict(id=7, hazard='Flood', level='Red', starts_at=NOW - H, ends_at=NOW + 30 * H, note='HRW #3',
                created_by=User(email='dora@example.com', full_name='Dora Officer'))
    data.update(over)
    return RainWatchOverride(**data)


class BuildTests(SimpleTestCase):
    def test_tino_like_run(self):
        r = build([stored_run(FULL_INIT, FULL_HOURS, on({TODAY + timedelta(days=1): 192.0}), tilt=True)])
        # Upland (192) is worse than the city (about 152): the flood reads the worse one
        self.assertEqual(part(r, 'tomorrow', 2), {'level': 'Red', 'reasons': ['Forecast 192 mm']})
        camp = part(r, 'tomorrow', 4)
        self.assertEqual(camp['level'], 'Orange')
        self.assertEqual(camp['reasons'], ['Forecast 192 mm', LIMITED])
        self.assertEqual(part(r, 'tomorrow', 4, 'landslide'), {'level': 'Red', 'reasons': ['192 mm over 3 days']})
        self.assertIsNone(part(r, 'tomorrow', 1, 'landslide'))
        self.assertEqual(part(r, 'today', 2), {'level': 'Green', 'reasons': ['Forecast 0 mm']})
        self.assertEqual(part(r, 'today', 4, 'landslide'), {'level': 'Green', 'reasons': ['0 mm over 3 days']})
        # The Day after: that day plus the 2 before still hold the 192 mm
        self.assertEqual(part(r, 'day_after', 4, 'landslide')['level'], 'Red')
        self.assertEqual(part(r, 'day_after', 2)['level'], 'Green')

        self.assertEqual(set(r), {'updated_at', 'run_init', 'source', 'stale', 'stale_hours', 'wet_ground', 'days',
                                  'floors', 'pagasa_alerts', 'overrides'})
        self.assertFalse(r['stale'])
        self.assertEqual(r['stale_hours'], 12)  # the rules in use (Balanced), for both audiences
        self.assertEqual(assess.public_view(r)['stale_hours'], 12)
        self.assertEqual(build(rules=dataclasses.replace(BALANCED, stale_hours=6))['stale_hours'], 6)
        self.assertEqual(r['updated_at'], '2026-11-18T03:00:00Z')
        self.assertEqual(r['run_init'], '2026-11-15T12:00:00Z')
        self.assertEqual(r['source'], 'gfs-nomads')
        self.assertEqual(r['wet_ground'], DRY)
        self.assertEqual([(d['key'], d['date'], d['less_certain']) for d in r['days']],
                         [('today', '2026-11-18', False), ('tomorrow', '2026-11-19', False),
                          ('day_after', '2026-11-20', True)])
        self.assertEqual(len(r['days'][0]['barangays']), 22)
        self.assertEqual(set(r['days'][0]['barangays'][0]), {'id', 'name', 'flood', 'landslide'})
        self.assertEqual((r['floors'], r['pagasa_alerts'], r['overrides']), ([], [], []))
        json.dumps(r)  # plain JSON, ready to cache and send

    def test_wet_ground_reason(self):
        runs = [stored_run(FULL_INIT, FULL_HOURS, flat(23.0))]
        self.assertEqual(part(build(runs, wet=WET), 'tomorrow', 2),
                         {'level': 'Yellow', 'reasons': ['Forecast 23 mm; ground already wet']})
        self.assertEqual(part(build(runs, wet=DRY), 'tomorrow', 2), {'level': 'Green', 'reasons': ['Forecast 23 mm']})

    def test_wetness_unknown_uses_dry_cutoffs(self):
        runs = [stored_run(FULL_INIT, FULL_HOURS, flat(23.0))]
        r = build(runs, wet=UNKNOWN)
        self.assertEqual(r['wet_ground'], UNKNOWN)
        self.assertEqual(part(r, 'tomorrow', 2),
                         {'level': 'Green', 'reasons': ['Forecast 23 mm', 'Ground wetness unknown']})
        public = assess.public_view(r)
        self.assertEqual(part(public, 'tomorrow', 2), {'level': 'none', 'reasons': []})
        self.assertNotIn('Ground wetness unknown', json.dumps(public))

        # Staff only, even on a colour the public sees
        r = build(runs, wet=UNKNOWN, overrides=[override(level='Orange')])
        self.assertEqual(part(r, 'tomorrow', 2)['reasons'],
                         ['Forecast 23 mm', 'Ground wetness unknown', 'Raised by DRRMO: HRW #3'])
        public = assess.public_view(r)
        self.assertEqual(part(public, 'tomorrow', 2),
                         {'level': 'Orange', 'reasons': ['Forecast 23 mm', 'Raised by DRRMO: HRW #3']})
        self.assertNotIn('Ground wetness unknown', json.dumps(public))

    def test_pagasa_floor_raises_only(self):
        dry = [stored_run(FULL_INIT, FULL_HOURS, flat(0.0))]
        r = build(dry, alerts=[alert()])
        self.assertEqual(part(r, 'today', 2),
                         {'level': 'Orange', 'reasons': ['Forecast 0 mm', 'Raised to Orange: PAGASA Tropical Cyclone Alert']})
        # Never lowered (user ruling 2026-11-18): Orange in the limited barangays too, with no limited reason
        self.assertEqual(part(r, 'today', 4),
                         {'level': 'Orange', 'reasons': ['Forecast 0 mm', 'Raised to Orange: PAGASA Tropical Cyclone Alert']})
        self.assertEqual(part(r, 'today', 4, 'landslide'),
                         {'level': 'Orange',
                          'reasons': ['0 mm over 3 days', 'Raised to Orange: PAGASA Tropical Cyclone Alert']})
        self.assertIsNone(part(r, 'today', 2, 'landslide'))
        # It ends before tomorrow starts (16:00 UTC)
        self.assertEqual(part(r, 'tomorrow', 2), {'level': 'Green', 'reasons': ['Forecast 0 mm']})
        until = iso(NOW + 6 * H)
        self.assertEqual(r['floors'], [
            {'source': 'PAGASA', 'hazard': 'Flood', 'level': 'Orange', 'until': until, 'text': 'TC alert for Cebu'},
            {'source': 'PAGASA', 'hazard': 'Landslide', 'level': 'Orange', 'until': until, 'text': 'TC alert for Cebu'},
        ])
        self.assertEqual(r['pagasa_alerts'], [{
            'identifier': 'tc-1', 'event': 'Tropical Cyclone Alert', 'severity': 'Severe', 'sent': iso(NOW - H),
            'expires': until, 'headline': 'TC alert for Cebu', 'covers_talisay': True, 'mapped': True,
            'applied': True, 'active': True}])

        # Never lowers a Red forecast, and says nothing about a floor that did not raise
        red = build([stored_run(FULL_INIT, FULL_HOURS, flat(192.0))], alerts=[alert()])
        self.assertEqual(part(red, 'today', 2), {'level': 'Red', 'reasons': ['Forecast 192 mm']})

        # Not in Talisay, Minor, a replaced one, or a kind with no mapping: nothing raised
        others = [
            alert(identifier='far', covers_talisay=False),
            alert(identifier='minor', severity='Minor'),
            alert(identifier='old'),
            alert(identifier='update', msg_type='Cancel', references='PAGASA,old,2026-11-18T03:00:00+00:00'),
            alert(identifier='quake', event='Earthquake Information'),
        ]
        r = build(dry, alerts=others)
        self.assertEqual(part(r, 'today', 2), {'level': 'Green', 'reasons': ['Forecast 0 mm']})
        self.assertEqual(r['floors'], [])
        flags = {a['identifier']: (a['active'], a['applied']) for a in r['pagasa_alerts']}
        self.assertEqual(flags, {'far': (False, False), 'minor': (True, False), 'old': (False, False),
                                 'update': (False, False), 'quake': (True, False)})
        # Staff see why one was not applied: not for Talisay, or a kind with no mapping (whatever its severity)
        reasons = {a['identifier']: (a['covers_talisay'], a['mapped']) for a in r['pagasa_alerts']}
        self.assertEqual(reasons, {'far': (False, True), 'minor': (True, True), 'old': (True, True),
                                   'update': (True, True), 'quake': (True, False)})
        mapped = build(dry, alerts=[alert(identifier=e, event=e, severity='Minor') for e in (
            'General Flood Advisory', 'Heavy Rainfall Warning', 'Thunderstorm Advisory')])['pagasa_alerts']
        self.assertEqual({a['identifier']: a['mapped'] for a in mapped},
                         {'General Flood Advisory': True, 'Heavy Rainfall Warning': True, 'Thunderstorm Advisory': False})
        self.assertTrue(all(type(a['covers_talisay']) is bool and type(a['mapped']) is bool for a in mapped))

    def test_pagasa_flood_floor_is_never_lowered(self):
        # User ruling 2026-11-18 ("Never lower PAGASA"): a PAGASA flood floor is at its full level in all 22
        # barangays. DRRMO floors and the forecast keep the one-step limit.
        dry = [stored_run(FULL_INIT, FULL_HOURS, flat(0.0))]
        red = alert(identifier='gfa', event='General Flood Advisory', severity='Extreme', headline='GFA Cebu')
        raised = 'Raised to Red: PAGASA General Flood Advisory'
        r = build(dry, alerts=[red])
        for bid in (2, 4, 15):  # Bulacao (full level), Camp IV and Mohon (limited)
            self.assertEqual(part(r, 'today', bid), {'level': 'Red', 'reasons': ['Forecast 0 mm', raised]})
        self.assertEqual(part(r, 'today', 4, 'landslide'), {'level': 'Green', 'reasons': ['0 mm over 3 days']})

        # The same colour set by DRRMO is one step lower there, as before
        drrmo = override(level='Red')
        r = build(dry, overrides=[drrmo])
        self.assertEqual(part(r, 'today', 4),
                         {'level': 'Orange', 'reasons': ['Forecast 0 mm', LIMITED, 'Raised by DRRMO: HRW #3']})
        self.assertEqual(part(r, 'today', 2), {'level': 'Red', 'reasons': ['Forecast 0 mm', 'Raised by DRRMO: HRW #3']})
        # Both at once: PAGASA's Red sets the level, and nothing was lowered
        r = build(dry, alerts=[red], overrides=[drrmo])
        self.assertEqual(part(r, 'today', 4), {'level': 'Red', 'reasons': ['Forecast 0 mm', raised]})

        # A forecast lowered by the limit, under a PAGASA floor that sets the level: no limited reason
        severe = alert(identifier='gfa', event='General Flood Advisory', severity='Severe')
        r = build([stored_run(FULL_INIT, FULL_HOURS, flat(70.0))], alerts=[severe])  # Orange, Yellow where limited
        self.assertEqual(part(r, 'today', 4),
                         {'level': 'Orange', 'reasons': ['Forecast 70 mm', 'Raised to Orange: PAGASA General Flood Advisory']})
        self.assertEqual(part(r, 'today', 2), {'level': 'Orange', 'reasons': ['Forecast 70 mm']})
        # ... while a lowered forecast that still sets the level keeps it
        r = build([stored_run(FULL_INIT, FULL_HOURS, flat(130.0))], alerts=[severe])  # Red, Orange where limited
        self.assertEqual(part(r, 'today', 4), {'level': 'Orange', 'reasons': ['Forecast 130 mm', LIMITED]})

        # A PAGASA landslide floor still applies only in the 7 steep barangays; the flood floor keeps the
        # map at PAGASA's level in the others
        r = build(dry, alerts=[alert(severity='Extreme')])  # Tropical Cyclone Alert: both hazards Red
        self.assertEqual(part(r, 'today', 4, 'landslide')['level'], 'Red')
        self.assertIsNone(part(r, 'today', 15, 'landslide'))
        self.assertEqual(part(r, 'today', 15)['level'], 'Red')

    def test_unknown_forecast_under_a_yellow_floor(self):
        # With no forecast, a hidden (Yellow) floor must not make the riskiest places look calmest on the
        # public map: the part stays 'unknown' with the forecast's own reason, never 'none'.
        moderate = alert(severity='Moderate')  # Tropical Cyclone Alert, Moderate: Yellow for both hazards
        raised = 'Raised to Yellow: PAGASA Tropical Cyclone Alert'
        old = stored_run(FULL_INIT, FULL_HOURS, flat(0.0), received=NOW - 13 * H)
        for runs in ([], [old]):  # no runs yet, and a stale forecast
            r = build(runs, alerts=[moderate])
            self.assertTrue(r['stale'])
            for bid in (1, 2, 4):  # Biasong, Bulacao, and Camp IV (limited; PAGASA is not lowered)
                self.assertEqual(part(r, 'today', bid), {'level': 'Yellow', 'reasons': [STALE, raised]})
            self.assertEqual(part(r, 'today', 4, 'landslide'), {'level': 'Yellow', 'reasons': [STALE, raised]})
            public = assess.public_view(r)
            for bid in (1, 2, 4, 15):
                self.assertEqual(part(public, 'today', bid), {'level': 'unknown', 'reasons': [STALE]})
            self.assertEqual(part(public, 'today', 4, 'landslide'), {'level': 'unknown', 'reasons': [STALE]})
            self.assertEqual(part(public, 'tomorrow', 1), {'level': 'unknown', 'reasons': [STALE]})  # no floor
            self.assertNotIn('Yellow', json.dumps(public))
            # The marker never reaches the JSON
            self.assertEqual(set(part(r, 'today', 1)), {'level', 'reasons'})
            self.assertEqual(json.loads(json.dumps(r)), r)

        # An Orange floor over a stale forecast is unchanged; where the limit makes a DRRMO floor Yellow,
        # the public sees 'unknown' again
        r = build([old], overrides=[override(level='Orange')])
        public = assess.public_view(r)
        self.assertEqual(part(public, 'today', 2), {'level': 'Orange', 'reasons': [STALE, 'Raised by DRRMO: HRW #3']})
        self.assertEqual(part(r, 'today', 4), {'level': 'Yellow', 'reasons': [STALE, LIMITED, 'Raised by DRRMO: HRW #3']})
        self.assertEqual(part(public, 'today', 4), {'level': 'unknown', 'reasons': [STALE]})

        # A fresh forecast that does not reach the Day after: only that day is 'unknown'; the known days
        # under the same Yellow floor are hidden as before
        fresh = stored_run(FULL_INIT, 96, flat(40.0), received=NOW - 2 * H)  # ends 4 h before the Day after
        r = build([fresh], alerts=[alert(severity='Moderate', expires=NOW + 60 * H)])
        self.assertFalse(r['stale'])
        public = assess.public_view(r)
        self.assertEqual(part(r, 'day_after', 1), {'level': 'Yellow', 'reasons': [STALE + ' (partial)', raised]})
        self.assertEqual(part(public, 'day_after', 1), {'level': 'unknown', 'reasons': [STALE + ' (partial)']})
        self.assertEqual(part(public, 'today', 1), {'level': 'none', 'reasons': []})
        self.assertEqual(part(public, 'tomorrow', 1), {'level': 'none', 'reasons': []})

    def test_override_floor_and_reason(self):
        dry = [stored_run(FULL_INIT, FULL_HOURS, flat(0.0))]
        r = build(dry, overrides=[override()])
        self.assertEqual(part(r, 'today', 2), {'level': 'Red', 'reasons': ['Forecast 0 mm', 'Raised by DRRMO: HRW #3']})
        self.assertEqual(part(r, 'tomorrow', 4),
                         {'level': 'Orange', 'reasons': ['Forecast 0 mm', LIMITED, 'Raised by DRRMO: HRW #3']})
        self.assertEqual(part(r, 'day_after', 2)['level'], 'Green')  # it ends 6 h before the Day after
        self.assertEqual(part(r, 'today', 4, 'landslide')['level'], 'Green')  # Flood only
        self.assertEqual(r['floors'], [
            {'source': 'DRRMO', 'hazard': 'Flood', 'level': 'Red', 'until': iso(NOW + 30 * H), 'text': 'HRW #3'}])
        self.assertEqual(r['overrides'], [{
            'id': 7, 'hazard': 'Flood', 'level': 'Red', 'starts_at': iso(NOW - H), 'ends_at': iso(NOW + 30 * H),
            'note': 'HRW #3', 'created_by_name': 'Dora Officer', 'cancelled_at': None}])

        # 'Both' covers landslide too; a cancelled override does nothing
        r = build(dry, overrides=[override(hazard='Both', level='Orange'),
                                  override(id=8, cancelled_at=NOW - H / 6)])
        self.assertEqual(part(r, 'today', 2)['level'], 'Orange')
        self.assertEqual(part(r, 'today', 4, 'landslide'),
                         {'level': 'Orange', 'reasons': ['0 mm over 3 days', 'Raised by DRRMO: HRW #3']})
        self.assertEqual([o['id'] for o in r['overrides']], [7])
        self.assertEqual([(f['hazard'], f['level']) for f in r['floors']], [('Flood', 'Orange'), ('Landslide', 'Orange')])

    def test_stale_hides_forecast_keeps_floors(self):
        old = stored_run(FULL_INIT, FULL_HOURS, flat(192.0), received=NOW - 13 * H)
        r = build([old], overrides=[override(level='Orange')])
        self.assertTrue(r['stale'])
        self.assertEqual(r['updated_at'], iso(NOW - 13 * H))
        self.assertEqual(part(r, 'tomorrow', 2), {'level': 'Orange', 'reasons': [STALE, 'Raised by DRRMO: HRW #3']})
        self.assertEqual(part(r, 'tomorrow', 4),
                         {'level': 'Yellow', 'reasons': [STALE, LIMITED, 'Raised by DRRMO: HRW #3']})
        self.assertEqual(part(r, 'day_after', 2), {'level': 'unknown', 'reasons': [STALE]})
        self.assertEqual(part(r, 'tomorrow', 4, 'landslide'), {'level': 'unknown', 'reasons': [STALE]})

        # A newer short gap-fill run does not make it fresh
        gap = stored_run(datetime(2026, 11, 18, 0, tzinfo=dt_tz.utc), 6, flat(0.0), received=NOW - H)
        self.assertTrue(build([old, gap])['stale'])
        # 12 hours exactly is still fresh
        self.assertFalse(build([stored_run(FULL_INIT, FULL_HOURS, flat(0.0), received=NOW - 12 * H)])['stale'])

    def test_no_runs_yet(self):
        r = build([])
        self.assertTrue(r['stale'])
        self.assertIsNone(r['updated_at'])
        self.assertIsNone(r['run_init'])
        self.assertIsNone(r['source'])
        self.assertEqual(all_levels(r), {'unknown'})
        self.assertIsNone(part(r, 'today', 1, 'landslide'))
        self.assertEqual(part(r, 'today', 2), {'level': 'unknown', 'reasons': [STALE]})
        self.assertEqual(r['floors'], [])
        self.assertEqual(all_levels(assess.public_view(r)), {'unknown'})

    def test_newest_run_too_short_for_day_after(self):
        # An old full run ending at 12:00 UTC on 19 Nov, 4 h before the Day after starts, then only
        # 6-hour gap-fill runs. (Its received time is recent so that staleness is not what is tested.)
        full = stored_run(FULL_INIT, 96, flat(40.0), received=NOW - 2 * H)
        gaps = [stored_run(datetime(2026, 11, 16, tzinfo=dt_tz.utc) + 6 * i * H, 6, flat(40.0),
                           received=NOW - H, source='gfs-dynamical') for i in range(9)]
        r = build([full] + gaps)
        self.assertFalse(r['stale'])
        self.assertEqual(part(r, 'today', 2), {'level': 'Yellow', 'reasons': ['Forecast 40 mm']})
        self.assertEqual(part(r, 'today', 4, 'landslide'), {'level': 'Red', 'reasons': ['120 mm over 3 days']})
        self.assertEqual(part(r, 'tomorrow', 2), {'level': 'Yellow', 'reasons': ['Forecast 33 mm (partial)']})
        self.assertEqual(part(r, 'day_after', 2), {'level': 'unknown', 'reasons': ['Forecast out of date (partial)']})
        self.assertEqual(part(r, 'day_after', 4, 'landslide'),
                         {'level': 'unknown', 'reasons': ['Forecast out of date (partial)']})

    def test_barangay_missing_from_csv(self):
        names = {**NAMES, 99: 'Bagong Barangay'}
        r = build([stored_run(FULL_INIT, FULL_HOURS, on({TODAY + timedelta(days=1): 192.0}))], barangays=names)
        self.assertEqual(part(r, 'tomorrow', 99), {'level': 'Orange', 'reasons': ['Forecast 192 mm', LIMITED]})
        self.assertIsNone(part(r, 'tomorrow', 99, 'landslide'))
        self.assertEqual(part(r, 'tomorrow', 99, 'flood'), part(r, 'tomorrow', 4, 'flood'))

    def test_public_view_shape(self):
        r = build([stored_run(FULL_INIT, FULL_HOURS, on({TODAY + timedelta(days=1): 192.0}, other=35.0))],
                  alerts=[alert(event='General Flood Advisory', severity='Moderate')],
                  overrides=[override(level='Orange', hazard='Landslide')])
        self.assertIn('Yellow', all_levels(r))
        self.assertIn('Green', all_levels(r))
        public = assess.public_view(r)
        self.assertNotIn('pagasa_alerts', public)
        self.assertNotIn('overrides', public)
        self.assertEqual([(f['source'], f['level']) for f in public['floors']], [('DRRMO', 'Orange')])
        self.assertEqual(all_levels(public), {'none', 'Orange', 'Red'})
        text = json.dumps(public)
        self.assertNotIn('Yellow', text)
        self.assertNotIn('Green', text)
        self.assertEqual(part(public, 'tomorrow', 2), part(r, 'tomorrow', 2))  # Red kept with its reasons
        # The staff answer is left as it was
        self.assertIn('pagasa_alerts', r)
        self.assertIn('Yellow', all_levels(r))


def toy_file(days):
    rain = {1: dict(days), 2: dict(days)}
    return RainFile(rain, {1: (10.5, 123.75), 2: (10.5, 123.75)}, min(days), max(days))


FILE_DAYS = {date(2026, 10, 25) + timedelta(days=i): 10.0 for i in range(19)}  # 25 Oct to 12 Nov
RECENT = {b: {date(2026, 11, 13): 20.0, date(2026, 11, 14): 20.0, date(2026, 11, 15): 20.0} for b in (1, 2)}


class WetGroundTests(SimpleTestCase):
    def test_wet_ground_from_file_and_recent(self):
        # 2 to 15 Nov: 11 file days of 10 mm and 3 recent days of 20 mm
        self.assertEqual(assess.wet_ground(TODAY, BALANCED, rain_file=toy_file(FILE_DAYS), recent=RECENT),
                         {'mm_14_days': 170.0, 'wet': True})
        # Nothing recent: 30 Oct to 12 Nov
        self.assertEqual(assess.wet_ground(TODAY, BALANCED, rain_file=toy_file(FILE_DAYS), recent={1: {}, 2: {}}),
                         {'mm_14_days': 140.0, 'wet': False})
        # A gap on 8 Nov leaves no 14 days in a row within the 20 before today
        gap = {**FILE_DAYS, date(2026, 11, 8): None}
        self.assertEqual(assess.wet_ground(TODAY, BALANCED, rain_file=toy_file(gap), recent=RECENT), UNKNOWN)
        # Values that stop too long ago
        old = {d: mm for d, mm in FILE_DAYS.items() if d <= date(2026, 11, 9)}
        self.assertEqual(assess.wet_ground(TODAY, BALANCED, rain_file=toy_file(old), recent={1: {}, 2: {}}), UNKNOWN)

    def test_recent_rain_asked_after_the_file(self):
        rf = toy_file(FILE_DAYS)
        with mock.patch('apps.rainwatch.assess.recent_rain', return_value=RECENT) as fake:
            self.assertEqual(assess.wet_ground(TODAY, BALANCED, rain_file=rf)['mm_14_days'], 170.0)
        fake.assert_called_once_with(rf.cells, after=date(2026, 11, 12), today=TODAY)
        with mock.patch('apps.rainwatch.assess.recent_rain', return_value=None):  # NASA POWER down
            self.assertEqual(assess.wet_ground(TODAY, BALANCED, rain_file=rf), {'mm_14_days': 140.0, 'wet': False})
        with mock.patch('apps.rainwatch.assess.read_rain_csv', side_effect=FileNotFoundError), \
                self.assertLogs('apps.rainwatch.assess', 'WARNING'):
            self.assertEqual(assess.wet_ground(TODAY, BALANCED, recent={}), UNKNOWN)


class CacheVersionTests(SimpleTestCase):
    def test_version_never_expires(self):
        # Django's incr() re-sets the key with the default timeout (300 s); the version must outlive it,
        # or it falls back to 0, 1, 2 ... and can meet a result still cached under the same number.
        cache.delete(assess.VERSION_KEY)
        assess.bump()
        assess.bump()
        with mock.patch('time.time', return_value=_time.time() + 3600):
            self.assertEqual(cache.get(assess.VERSION_KEY), 2)

    def test_bump_logs_and_swallows_a_cache_failure(self):
        broken = mock.Mock()
        broken.incr.side_effect = ConnectionError('cache down')
        broken.set.side_effect = ConnectionError('cache down')
        with mock.patch('apps.rainwatch.assess.cache', broken), \
                self.assertLogs('apps.rainwatch.assess', 'WARNING') as logs:
            assess.bump()  # no exception
        self.assertIn('cache down', logs.output[0])


def wait_for_wet_thread():
    for t in threading.enumerate():
        if t.name == assess.WET_THREAD:
            t.join(30)


def run_wet_job_now(today, rules):
    """For the endpoint tests: the background wet-ground work in its own thread, waited for."""
    thread = threading.Thread(target=assess._refresh_wet, args=(today, rules))
    thread.start()
    thread.join(30)


class WetGroundCacheTests(SimpleTestCase):
    """A request never works out wet ground (spec anti-goal 1): it reads the cache, and a miss starts the
    work once in a background thread."""

    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)

    def test_a_miss_answers_at_once_and_starts_one_computation(self):
        with mock.patch('apps.rainwatch.assess._start_wet_thread') as start, \
                mock.patch('apps.rainwatch.assess.wet_ground') as compute:
            self.assertEqual(assess._wet_cached(TODAY, BALANCED), UNKNOWN)
            start.assert_called_once_with(TODAY, BALANCED)
            # A second miss while the first computation runs (on any worker sharing the cache) starts none
            self.assertEqual(assess._wet_cached(TODAY, BALANCED), UNKNOWN)
            self.assertEqual(start.call_count, 1)
        compute.assert_not_called()

    def test_no_second_thread_in_the_same_process(self):
        release = threading.Event()
        busy = threading.Thread(target=release.wait, name=assess.WET_THREAD, daemon=True)
        busy.start()
        try:
            with mock.patch('apps.rainwatch.assess._start_wet_thread') as start:
                self.assertFalse(assess.refresh_wet_in_background(TODAY, BALANCED))
            start.assert_not_called()
        finally:
            release.set()
            busy.join(5)

    def test_the_thread_stores_the_value_and_bumps(self):
        with mock.patch('apps.rainwatch.assess.wet_ground', return_value=WET) as compute:
            self.assertEqual(assess._wet_cached(TODAY, BALANCED), UNKNOWN)
            wait_for_wet_thread()
        compute.assert_called_once_with(TODAY, BALANCED)
        self.assertEqual(cache.get(assess.VERSION_KEY), 1)  # cached answers dropped
        with mock.patch('apps.rainwatch.assess._start_wet_thread') as start:
            self.assertEqual(assess._wet_cached(TODAY, BALANCED), WET)
            # After the day's value expires (1 h), the last good one fills in while it is worked out again
            with mock.patch('time.time', return_value=_time.time() + 3601):
                self.assertEqual(assess._wet_cached(TODAY, BALANCED), WET)
        start.assert_called_once_with(TODAY, BALANCED)

    def test_an_unknown_value_is_kept_15_minutes_and_is_not_a_last_good_one(self):
        with mock.patch('apps.rainwatch.assess.wet_ground', return_value=dict(UNKNOWN)):
            self.assertTrue(assess.refresh_wet_in_background(TODAY, BALANCED))
            wait_for_wet_thread()
        with mock.patch('apps.rainwatch.assess._start_wet_thread') as start:
            self.assertEqual(assess._wet_cached(TODAY, BALANCED), UNKNOWN)
            start.assert_not_called()
            with mock.patch('time.time', return_value=_time.time() + 15 * 60 + 1):
                self.assertEqual(assess._wet_cached(TODAY, BALANCED), UNKNOWN)
            start.assert_called_once_with(TODAY, BALANCED)

    def test_last_good_value_at_most_2_days_old(self):
        with mock.patch('apps.rainwatch.assess.wet_ground', return_value=WET):
            self.assertTrue(assess.refresh_wet_in_background(TODAY - timedelta(days=2), BALANCED))
            wait_for_wet_thread()
        with mock.patch('apps.rainwatch.assess._start_wet_thread') as start:
            self.assertEqual(assess._wet_cached(TODAY, BALANCED), WET)  # worked out 2 days ago: used
            start.assert_called_once_with(TODAY, BALANCED)
            self.assertEqual(assess._wet_cached(TODAY + timedelta(days=1), BALANCED), UNKNOWN)  # 3 days: ignored
        # Another wet-ground cut-off is another value
        self.assertEqual(assess._last_good(cache.get(assess._wet_last_key(dataclasses.replace(
            BALANCED, wet_14day_mm=100.0))), TODAY), None)

    def test_a_day_value_that_is_unknown_falls_back_to_the_last_good_one(self):
        with mock.patch('apps.rainwatch.assess.wet_ground', return_value=WET):
            assess.refresh_wet_in_background(TODAY - timedelta(days=1), BALANCED)
            wait_for_wet_thread()
        with mock.patch('apps.rainwatch.assess.wet_ground', return_value=dict(UNKNOWN)):
            assess.refresh_wet_in_background(TODAY, BALANCED)  # NASA POWER down today
            wait_for_wet_thread()
        with mock.patch('apps.rainwatch.assess._start_wet_thread') as start:
            self.assertEqual(assess._wet_cached(TODAY, BALANCED), WET)
        start.assert_not_called()  # the unknown value still holds the 15-minute retry

    def test_a_failure_in_the_thread_is_logged_and_leaves_the_request_alone(self):
        with mock.patch('apps.rainwatch.assess.wet_ground', side_effect=RuntimeError('POWER exploded')), \
                self.assertLogs('apps.rainwatch.assess', 'ERROR') as logs:
            self.assertEqual(assess._wet_cached(TODAY, BALANCED), UNKNOWN)
            wait_for_wet_thread()
        self.assertIn('ground wetness', logs.output[0])
        self.assertEqual(str(logs.records[0].exc_info[1]), 'POWER exploded')
        self.assertIsNone(cache.get(assess.VERSION_KEY))  # nothing stored, nothing bumped
        with mock.patch('apps.rainwatch.assess._start_wet_thread') as start:
            self.assertEqual(assess._wet_cached(TODAY, BALANCED), UNKNOWN)
        start.assert_not_called()  # retried once the lock runs out (10 minutes), not on every request

    def test_a_failing_cache_gives_unknown(self):
        broken = mock.Mock()
        broken.get.side_effect = ConnectionError('cache down')
        with mock.patch('apps.rainwatch.assess.cache', broken), \
                mock.patch('apps.rainwatch.assess._start_wet_thread') as start, \
                self.assertLogs('apps.rainwatch.assess', 'WARNING'):
            self.assertEqual(assess._wet_cached(TODAY, BALANCED), UNKNOWN)
        start.assert_not_called()


def make_user(role_name, email):
    role, _ = Role.objects.get_or_create(name=role_name)
    return User.objects.create_user(email=email, password='pw-12345-xyz', role=role, full_name=f'{role_name} Person')


def run_body(init, mm_per_hour, n=96, source='gfs-nomads'):
    return {'source': source, 'init_time': iso(init), 'job_version': 'test',
            'points': [{'lat': lat, 'lon': lon, 'first_hour_start': iso(init), 'mm_per_hour': [mm_per_hour] * n}
                       for lat, lon in GRID]}


def last_cycle(now):
    return now.replace(hour=now.hour // 6 * 6, minute=0, second=0, microsecond=0)


def store_run(init, mm_per_hour, n=96, source='gfs-nomads'):
    run = RainForecastRun.objects.create(source=source, init_time=init, job_version='test', hours=n)
    RainForecastSeries.objects.bulk_create([
        RainForecastSeries(run=run, lat=lat, lon=lon, first_hour_start=init, mm_per_hour=[mm_per_hour] * n)
        for lat, lon in GRID])
    return run


@override_settings(RAIN_WATCH_INGEST_TOKEN='s3cret')
class RainWatchEndpointTests(TestCase):
    def setUp(self):
        cache.clear()
        for bid in (1, 2, 4, 7):
            Barangay.objects.create(id=bid, name=NAMES[bid])
        self.today = timezone.now().astimezone(MANILA).date()
        days = {self.today - timedelta(days=k): 5.0 for k in range(3, 21)}  # NASA POWER 3 days behind, 5 mm a day
        self.fakes = {}
        for name, value in (('read_rain_csv', toy_file(days)), ('recent_rain', {})):
            patcher = mock.patch(f'apps.rainwatch.assess.{name}', return_value=value)
            self.fakes[name] = patcher.start()
            self.addCleanup(patcher.stop)
        # The background wet-ground work runs in a thread that is waited for, so the tests are deterministic.
        # The day's value is worked out up front, as the first visitors of the day would have started it.
        patcher = mock.patch('apps.rainwatch.assess._start_wet_thread', side_effect=run_wet_job_now)
        self.start_wet = patcher.start()
        self.addCleanup(patcher.stop)
        run_wet_job_now(self.today, BALANCED)
        self.fakes['read_rain_csv'].reset_mock()
        self.anon = APIClient()

    def client_for(self, user):
        c = APIClient()
        c.force_authenticate(user)
        return c

    def post_run(self, mm_per_hour, init=None, n=96):
        init = init or last_cycle(timezone.now())
        response = APIClient().post(RUNS_URL, run_body(init, mm_per_hour, n), format='json',
                                    HTTP_AUTHORIZATION='Bearer s3cret')
        self.assertEqual(response.status_code, 201, response.content)

    def test_no_runs_yet(self):
        response = self.anon.get(URL)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['stale'])
        self.assertIsNone(data['updated_at'])
        self.assertEqual(all_levels(data), {'unknown'})
        self.assertEqual([b['id'] for b in data['days'][0]['barangays']], [1, 2, 4, 7])  # by name
        self.assertEqual(data['wet_ground'], {'mm_14_days': 70.0, 'wet': False})
        self.assertEqual(data['stale_hours'], 12)  # from the rules row in force
        self.fakes['read_rain_csv'].assert_not_called()  # a cached value: nothing worked out

    def test_wet_ground_is_never_worked_out_in_the_request(self):
        cache.clear()  # a restart, say: no value for the day, no last good one
        self.start_wet.side_effect = None
        first = self.anon.get(URL)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json()['wet_ground'], UNKNOWN)
        self.start_wet.assert_called_once_with(self.today, BALANCED)
        self.fakes['read_rain_csv'].assert_not_called()
        self.assertEqual(self.anon.get(URL).json(), first.json())  # still cached; nothing new started
        self.assertEqual(self.start_wet.call_count, 1)

        run_wet_job_now(self.today, BALANCED)  # the thread it started: stores the value and bumps
        after = self.anon.get(URL).json()
        self.assertEqual(after['wet_ground'], {'mm_14_days': 70.0, 'wet': False})
        self.assertEqual(self.start_wet.call_count, 1)

    def test_a_failing_wet_ground_thread_leaves_the_page_alone(self):
        cache.clear()
        with mock.patch('apps.rainwatch.assess.wet_ground', side_effect=RuntimeError('boom')), \
                self.assertLogs('apps.rainwatch.assess', 'ERROR'):
            response = self.anon.get(URL)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['wet_ground'], UNKNOWN)

    def test_a_failing_cache_still_answers(self):
        broken = mock.Mock(wraps=cache)
        broken.get.side_effect = ConnectionError('cache down')
        with mock.patch('apps.rainwatch.assess.cache', broken), \
                self.assertLogs('apps.rainwatch.assess', 'WARNING') as logs:
            response = self.anon.get(URL)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['stale'])
        self.assertEqual(all_levels(data), {'unknown'})
        self.assertEqual(data['wet_ground'], UNKNOWN)
        self.assertTrue(any('cache down' in line for line in logs.output))

        # Only the write fails: the answer is still worked out and sent, just not kept
        broken = mock.Mock(wraps=cache)
        broken.set_many.side_effect = OSError('disk full')
        with mock.patch('apps.rainwatch.assess.cache', broken), \
                self.assertLogs('apps.rainwatch.assess', 'WARNING'):
            response = self.client_for(make_user('DRRMO_Officer', 'drrmo@example.com')).get(URL)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['wet_ground'], {'mm_14_days': 70.0, 'wet': False})
        version = cache.get(assess.VERSION_KEY, 0)
        self.assertIsNone(cache.get(assess.result_key(version, True)))

    def test_public_view_hides_yellow_and_green(self):
        self.post_run(35 / 24)  # 35 mm a day: Yellow on dry or wet ground
        drrmo = make_user('DRRMO_Officer', 'drrmo@example.com')
        admin = make_user('System_Admin', 'admin@example.com')
        brgy = make_user('Barangay_Personnel', 'brgy@example.com')
        RainWatchOverride.objects.create(hazard='Flood', level='Yellow', ends_at=timezone.now() + 6 * H,
                                         note='Watch the river', created_by=drrmo)
        anon = self.anon.get(URL)
        self.assertEqual(anon.status_code, 200)
        text = anon.content.decode()
        self.assertNotIn('Yellow', text)
        self.assertNotIn('Green', text)
        public = anon.json()
        self.assertFalse(public['stale'])
        self.assertNotIn('pagasa_alerts', public)
        self.assertNotIn('overrides', public)
        self.assertEqual(public['floors'], [])
        self.assertEqual(part(public, 'tomorrow', 2), {'level': 'none', 'reasons': []})

        for user in (drrmo, admin):
            staff = self.client_for(user).get(URL).json()
            self.assertEqual(part(staff, 'tomorrow', 2), {'level': 'Yellow', 'reasons': ['Forecast 35 mm']})
            self.assertEqual([o['note'] for o in staff['overrides']], ['Watch the river'])
            self.assertEqual(staff['overrides'][0]['created_by_name'], 'DRRMO_Officer Person')
            self.assertEqual([f['level'] for f in staff['floors']], ['Yellow'])
            self.assertEqual(staff['pagasa_alerts'], [])

        self.assertEqual(self.client_for(brgy).get(URL).json(), public)

    def test_cache_cleared_by_new_run(self):
        first = self.anon.get(URL).json()
        self.assertIsNone(first['updated_at'])
        store_run(last_cycle(timezone.now()) - 6 * H, 1.0)  # stored without telling the cache
        self.assertEqual(self.anon.get(URL).json(), first)
        self.post_run(1.0)
        after = self.anon.get(URL).json()
        self.assertNotEqual(after, first)
        self.assertIsNotNone(after['updated_at'])
        self.assertFalse(after['stale'])

    def test_rain_watch_caches_per_audience(self):
        now = timezone.now()
        staff = assess.rain_watch(now, staff=True)
        version = cache.get(assess.VERSION_KEY, 0)
        self.assertEqual(cache.get(f'rainwatch:result:{version}:staff'), staff)
        self.assertEqual(cache.get(f'rainwatch:result:{version}:public'), assess.public_view(staff))
        self.assertEqual(assess.rain_watch(now), assess.public_view(staff))

    def test_is_stale_latest_runs_and_age_of_an_old_run(self):
        now = timezone.now()
        rules = BALANCED
        self.assertTrue(assess.is_stale(now, rules))
        with mock.patch('django.utils.timezone.now', return_value=now - 13 * H):
            store_run(last_cycle(now - 13 * H) - 6 * H, 1.0)
        self.assertTrue(assess.is_stale(now, rules))
        store_run(last_cycle(now), 1.0, n=6, source='gfs-dynamical')  # a fresh gap-fill run does not count
        self.assertTrue(assess.is_stale(now, rules))
        fresh = store_run(last_cycle(now) - 6 * H, 1.0, n=72)
        self.assertFalse(assess.is_stale(now, rules))

        with mock.patch('django.utils.timezone.now', return_value=now - 5 * 24 * H):
            store_run(last_cycle(now - 5 * 24 * H) - 6 * H, 1.0)  # outside the 4 days
        runs = assess.latest_runs(now)
        self.assertEqual(len(runs), 3)
        newest = next(r for r in runs if r.hours == 72)
        self.assertEqual(newest.received_at, fresh.received_at)
        self.assertEqual(newest.hours, 72)
        self.assertEqual(set(newest.series), set(GRID))
        self.assertEqual(newest.series[(10.25, 124.0)], [1.0] * 72)

    def test_old_run_still_gives_its_age(self):
        now = timezone.now()
        with mock.patch('django.utils.timezone.now', return_value=now - 5 * 24 * H):
            old = store_run(last_cycle(now - 5 * 24 * H) - 6 * H, 1.0)
        data = assess.rain_watch(now, staff=True)
        self.assertTrue(data['stale'])
        self.assertEqual(data['updated_at'], iso(old.received_at))
        self.assertEqual(all_levels(data), {'unknown'})

    def test_active_pagasa_alert_from_the_database(self):
        now = timezone.now()
        PagasaAlert.objects.create(identifier='tc-db', sent=now - H, effective=now - H, expires=now + 3 * H,
                                   msg_type='Alert', event='Tropical Cyclone Alert', severity='Extreme',
                                   urgency='Immediate', response_type='Evacuate', headline='Signal 4',
                                   covers_talisay=True)
        data = assess.rain_watch(now, staff=True)
        self.assertEqual(part(data, 'today', 2)['level'], 'Red')
        self.assertEqual(part(data, 'today', 2)['reasons'], [STALE, 'Raised to Red: PAGASA Tropical Cyclone Alert'])
        self.assertEqual([(a['identifier'], a['applied']) for a in data['pagasa_alerts']], [('tc-db', True)])
