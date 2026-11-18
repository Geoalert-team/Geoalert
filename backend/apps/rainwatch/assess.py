"""
Rain watch results: the levels for each barangay, hazard and day (spec 6.3-6.8).

  build()        pure: stored runs + wet ground + PAGASA alerts + DRRMO overrides -> the staff answer
  public_view()  the same answer with Green and Yellow hidden (everyone but DRRMO and admins)
  rain_watch()   loads everything, builds, and caches both answers for 5 minutes

Results are cached per audience; any new run, alert or override calls bump(), which
changes the version the cache keys are built from and so drops every cached result.
A cache that fails is logged and the answer is worked out uncached; it never answers 500.

Wet ground is never worked out inside a request (reading rain_daily.csv and asking NASA POWER take
seconds on Render's small CPU). A request reads the cached value; a miss starts the work in one
background thread (refresh_wet_in_background), which stores the value and calls bump().
"""
import logging
import threading
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone as dt_tz
from typing import NamedTuple, Optional

from django.core.cache import cache
from django.db import close_old_connections, connection
from django.db.models import Q, prefetch_related_objects
from django.utils import timezone

from apps.history.hazard_data import MANILA
from apps.history.rain import read_rain_csv, recent_rain
from apps.rainwatch.rules import (
    BALANCED, GREEN, LEVEL_NAMES, Rules, combine, flood_exposed_ids, flood_level, one_step_lower,
    slide_level, steep_ids,
)
from apps.rainwatch.series import CITY, UPLAND, RunData, manila_day_total, place_hours, stitched

logger = logging.getLogger(__name__)

VERSION_KEY = 'rainwatch:version'
RESULT_TTL = 300
WET_TTL, WET_FAIL_TTL = 3600, 15 * 60  # the day's wet ground: known, unknown
WET_LAST_TTL = 2 * 24 * 3600           # the last known value, kept 2 days ...
WET_LAST_DAYS = 2                      # ... and used when worked out for a Manila day at most 2 days back
WET_LOCK_TTL = 10 * 60                 # one computation at a time; a failed one is tried again after this
WET_THREAD = 'rainwatch-wet-ground'
DAY_KEYS = ('today', 'tomorrow', 'day_after')
FULL_HOURS = 72                      # a run this long counts for freshness; gap-fill runs do not
RUN_WINDOW = timedelta(days=4)
WET_DAYS, WET_LOOKBACK = 14, 20
ALERT_LOOKBACK = timedelta(days=30)  # alerts that may replace or cancel a still-active one
ALERT_RECENT = timedelta(days=1)     # staff list: alerts still running or ended within the last day
ALERT_LIST_MAX = 20
STAFF_ROLES = ('DRRMO_Officer', 'System_Admin')

# Reasons (exact copy)
STALE = 'Forecast out of date'
PARTIAL = ' (partial)'
WET_SUFFIX = '; ground already wet'
WETNESS_UNKNOWN = 'Ground wetness unknown'  # staff only
LIMITED = 'Fewer homes in flood-prone ground: one step lower'


def bump():
    """Drop every cached answer. A cache failure is logged, never raised: the caller has already saved its
    row (a run, an alert, an override), and a 500 then would make an officer submit it twice."""
    try:
        try:
            cache.incr(VERSION_KEY)
            cache.touch(VERSION_KEY, None)  # incr() re-sets the key with the default 300 s timeout
        except ValueError:  # no version stored yet
            cache.set(VERSION_KEY, 1, None)
    except Exception as exc:
        logger.warning('Cache unavailable (%s); cached rain watch answers expire within %d minutes instead.',
                       exc, RESULT_TTL // 60)


def active_overrides(now):
    """DRRMO overrides in force at `now`: not cancelled, starts_at <= now < ends_at."""
    from apps.rainwatch.models import RainWatchOverride
    return list(RainWatchOverride.objects.filter(
        cancelled_at__isnull=True, starts_at__lte=now, ends_at__gt=now).order_by('id'))


@dataclass(frozen=True)
class StoredRun(RunData):
    """A RunData plus what freshness needs: when it arrived and how many hours it holds."""
    received_at: Optional[datetime] = None
    hours: int = 0


# --- wet ground -----------------------------------------------------------------------------------

def wet_ground(today: date, rules: Rules, rain_file=None, recent=None) -> dict:
    """NASA POWER's total over its latest 14 days in a row with values, ending before `today`."""
    unknown = {'mm_14_days': None, 'wet': None}
    rf = rain_file
    if rf is None:
        try:
            rf = read_rain_csv()
        except (OSError, ValueError, KeyError):
            logger.warning('The rain file could not be read; ground wetness unknown.', exc_info=True)
            return unknown
    if not rf.rain:
        return unknown
    bid = min(rf.rain)  # every barangay reads the same cell
    series = dict(rf.rain[bid])
    if recent is None and rf.last_day is not None:
        try:
            recent = recent_rain(rf.cells, after=rf.last_day, today=today)
        except Exception:
            logger.warning('Recent rain from NASA POWER failed; using the rain file only.', exc_info=True)
            recent = None
    if recent:
        series.update(recent.get(bid) if bid in recent else next(iter(recent.values()), {}))
    for back in range(1, WET_LOOKBACK - WET_DAYS + 2):  # the window ends 1 to 7 days before today
        end = today - timedelta(days=back)
        values = [series.get(end - timedelta(days=i)) for i in range(WET_DAYS)]
        if all(v is not None for v in values):
            mm = round(sum(values), 2)
            return {'mm_14_days': mm, 'wet': mm >= rules.wet_14day_mm}
    return unknown


# --- runs and freshness ---------------------------------------------------------------------------

def _stored(row, series=True):
    points = ({(float(s.lat), float(s.lon)): list(s.mm_per_hour) for s in row.series.all()} if series else {})
    return StoredRun(row.source, row.init_time, points, received_at=row.received_at, hours=row.hours)


def latest_runs(now) -> list:
    """Stored runs (StoredRun) with init_time within the last 4 days."""
    from apps.rainwatch.models import RainForecastRun
    rows = (RainForecastRun.objects.filter(init_time__gte=now - RUN_WINDOW)
            .prefetch_related('series').order_by('init_time', 'source'))
    return [_stored(r) for r in rows]


def _newest_full_row():
    from apps.rainwatch.models import RainForecastRun
    return (RainForecastRun.objects.filter(hours__gte=FULL_HOURS)
            .order_by('-init_time', '-received_at').first())


def _newest_full(runs):
    full = [r for r in runs if getattr(r, 'hours', 0) >= FULL_HOURS and getattr(r, 'received_at', None)]
    return max(full, key=lambda r: (r.init_time, r.received_at), default=None)


def _stale(received_at, now, rules) -> bool:
    return received_at is None or now - received_at > timedelta(hours=rules.stale_hours)


def is_stale(now, rules) -> bool:
    """The newest run of 72 hours or more arrived more than stale_hours ago, or there is none."""
    row = _newest_full_row()
    return _stale(row.received_at if row else None, now, rules)


# --- building the answer --------------------------------------------------------------------------

def _iso(dt):
    return None if dt is None else dt.astimezone(dt_tz.utc).isoformat().replace('+00:00', 'Z')


def _day_start(day):
    return datetime.combine(day, time(0), tzinfo=MANILA).astimezone(dt_tz.utc)


class DayRain(NamedTuple):
    mm: float
    complete: bool
    present: bool  # at least one hour


def _day_rain(placed, day):
    total, complete = manila_day_total(placed, day)
    start, end = _day_start(day), _day_start(day + timedelta(days=1))
    return DayRain(total, complete, complete or any(start <= h < end for h in placed))


@dataclass(frozen=True)
class Floor:
    source: str      # 'PAGASA' or 'DRRMO'
    hazard: str      # 'Flood' or 'Landslide'
    level: int
    start: datetime
    end: datetime
    label: str       # the PAGASA event, or the DRRMO note
    text: str

    def reason(self, level):
        if self.source == 'PAGASA':
            return f'Raised to {LEVEL_NAMES[level]}: PAGASA {self.label}'
        return f'Raised by DRRMO: {self.label}'


def _floors(now, alerts, overrides):
    """(floors, staff alert list, staff override list)."""
    from apps.rainwatch import pagasa
    refs = pagasa.referenced_identifiers(alerts)
    floors, listed = [], []
    for a in alerts:
        active = pagasa.is_active(a, now, refs)
        implied = pagasa.floor_for(a) if active else {}
        for hazard, level in implied.items():
            floors.append(Floor('PAGASA', hazard, level, a.effective or a.sent, a.expires, a.event,
                                a.headline or a.event))
        if a.expires is None or a.expires > now - ALERT_RECENT:
            listed.append((a, active, bool(implied)))
    listed.sort(key=lambda x: (x[0].covers_talisay, x[0].sent or x[0].expires or now, x[0].identifier),
                reverse=True)
    staff_alerts = [{
        'identifier': a.identifier, 'event': a.event, 'severity': a.severity, 'sent': _iso(a.sent),
        'expires': _iso(a.expires), 'headline': a.headline, 'covers_talisay': bool(a.covers_talisay),
        'mapped': pagasa.is_mapped(a), 'applied': applied, 'active': active,
    } for a, active, applied in listed[:ALERT_LIST_MAX]]

    in_force = [o for o in overrides
                if o.cancelled_at is None and o.starts_at <= now < o.ends_at]
    for o in in_force:
        hazards = ('Flood', 'Landslide') if o.hazard == 'Both' else (o.hazard,)
        for hazard in hazards:
            floors.append(Floor('DRRMO', hazard, LEVEL_NAMES.index(o.level), o.starts_at, o.ends_at, o.note, o.note))
    staff_overrides = [{
        'id': o.id, 'hazard': o.hazard, 'level': o.level, 'starts_at': _iso(o.starts_at),
        'ends_at': _iso(o.ends_at), 'note': o.note, 'created_by_name': o.created_by.full_name,
        'cancelled_at': _iso(o.cancelled_at),
    } for o in in_force]
    return floors, staff_alerts, staff_overrides


class Part(dict):
    """One hazard's {level, reasons} for one barangay and day: a plain dict to JSON and to ==.

    `forecast_unknown` is the forecast's own reasons when the forecast part was unknown (stale, no runs,
    or a day the runs don't reach), else None. It is an attribute, not a key, so it never reaches the
    JSON; public_view() reads it so a hidden level over an unknown forecast stays 'unknown'.
    """
    forecast_unknown = None


def _part(forecast, reasons, limited, floors):
    """One hazard's Part for one barangay and day: the forecast raised by any floor.

    Where few homes sit in flood-prone ground (`limited`), the forecast and DRRMO floors are one step
    lower. A PAGASA floor never is: an active PAGASA alert shows at its own level everywhere it applies
    (user ruling 2026-11-18, "Never lower PAGASA"). The limited reason shows only when the limit lowered
    whatever set the final level.
    """
    level, out, lowered = forecast, list(reasons), False
    if limited and level is not None and level > GREEN:
        level, lowered = one_step_lower(level), True
    raising = []
    for f in floors:
        applied = one_step_lower(f.level) if limited and f.source != 'PAGASA' else f.level
        if applied > GREEN:  # a floor lowered to Green raises nothing
            raising.append((applied, f))
    final = combine(level, [applied for applied, _ in raising])
    deciding = [(applied, f) for applied, f in raising if applied == final and (level is None or applied > level)]
    if (lowered and level == final) or any(applied < f.level for applied, f in deciding):
        out.append(LIMITED)
    out += [f.reason(applied) for applied, f in deciding]
    part = Part(level='unknown' if final is None else LEVEL_NAMES[final], reasons=list(dict.fromkeys(out)))
    if forecast is None:
        part.forecast_unknown = list(reasons)
    return part


def build(now, rules, runs, wet, alerts, overrides, exposure, terrain, barangays) -> dict:
    """The staff answer (spec 6.7). Pure: everything it reads is passed in.

    `runs` are StoredRun (their received_at and hours set freshness), `barangays` is {id: name}.
    """
    runs = list(runs)
    today = now.astimezone(MANILA).date()
    newest = _newest_full(runs)
    stale = _stale(newest.received_at if newest else None, now, rules)

    hours = stitched(runs)
    city, upland = place_hours(hours, CITY), place_hours(hours, UPLAND)
    span = [today + timedelta(days=i) for i in range(-2, len(DAY_KEYS))]
    city_rain = {d: _day_rain(city, d) for d in span}
    upland_rain = {d: _day_rain(upland, d) for d in span}

    is_wet = bool(wet.get('wet'))
    extra = [WETNESS_UNKNOWN] if wet.get('wet') is None else []

    def forecast(mm_text, days):
        if stale:
            return None, [STALE]
        if not all(d.present for d in days):
            return None, [STALE + PARTIAL]
        text = mm_text + ('' if all(d.complete for d in days) else PARTIAL) + (WET_SUFFIX if is_wet else '')
        return text, extra

    exposed = flood_exposed_ids(exposure, rules)
    steep = steep_ids(terrain, rules)
    floors, staff_alerts, staff_overrides = _floors(now, alerts, overrides)
    order = sorted(barangays.items(), key=lambda item: (item[1], item[0]))

    days = []
    for i, key in enumerate(DAY_KEYS):
        day = today + timedelta(days=i)
        start, end = _day_start(day), _day_start(day + timedelta(days=1))
        # Floors normally have both ends: a PAGASA alert is only active with a start (effective or sent)
        # and `expires`, and a DRRMO override always has starts_at and ends_at. The guard skips one bad
        # row instead of letting it break the endpoint for every visitor.
        today_floors = [f for f in floors if f.start is not None and f.end is not None
                        and f.start < end and f.end > start]

        flood_days = [city_rain[day], upland_rain[day]]
        flood_mm = round(max(city_rain[day].mm, upland_rain[day].mm), 2)
        text, more = forecast(f'Forecast {flood_mm:.0f} mm', flood_days)
        flood = (None, more) if text is None else (flood_level(flood_mm, is_wet, rules), [text] + more)

        slide_days = [upland_rain[day - timedelta(days=k)] for k in (2, 1, 0)]
        slide_mm = round(sum(d.mm for d in slide_days), 2)
        text, more = forecast(f'{slide_mm:.0f} mm over 3 days', slide_days)
        slide = (None, more) if text is None else (slide_level(slide_mm, is_wet, rules), [text] + more)

        flood_floors = [f for f in today_floors if f.hazard == 'Flood']
        slide_floors = [f for f in today_floors if f.hazard == 'Landslide']
        days.append({
            'key': key,
            'date': day.isoformat(),
            'less_certain': key == 'day_after',
            'barangays': [{
                'id': bid,
                'name': name,
                'flood': _part(*flood, bid not in exposed, flood_floors),
                'landslide': _part(*slide, False, slide_floors) if bid in steep else None,
            } for bid, name in order],
        })

    return {
        'updated_at': _iso(newest.received_at) if newest else None,
        'run_init': _iso(newest.init_time) if newest else None,
        'source': newest.source if newest else None,
        'stale': stale,
        'stale_hours': rules.stale_hours,
        'wet_ground': {'mm_14_days': wet.get('mm_14_days'), 'wet': wet.get('wet')},
        'days': days,
        'floors': [{'source': f.source, 'hazard': f.hazard, 'level': LEVEL_NAMES[f.level],
                    'until': _iso(f.end), 'text': f.text} for f in floors],
        'pagasa_alerts': staff_alerts,
        'overrides': staff_overrides,
    }


HIDDEN_LEVELS = ('Green', 'Yellow')


def _public_part(part):
    if part is None:
        return None
    if part['level'] in HIDDEN_LEVELS:
        unknown = getattr(part, 'forecast_unknown', None)
        if unknown is not None:  # no forecast: hiding a Yellow floor must not look calmer than grey
            return {'level': 'unknown', 'reasons': [r for r in unknown if r != WETNESS_UNKNOWN]}
        return {'level': 'none', 'reasons': []}
    return {'level': part['level'], 'reasons': [r for r in part['reasons'] if r != WETNESS_UNKNOWN]}


def public_view(result: dict) -> dict:
    """Everyone but DRRMO and admins: Green and Yellow become 'none' with no reasons, or 'unknown' with
    the forecast's own reason when the forecast part was unknown; no Yellow floors, no staff lists, no
    staff-only reasons. Orange and Red are unchanged."""
    out = {k: v for k, v in result.items() if k not in ('pagasa_alerts', 'overrides', 'days', 'floors')}
    out['days'] = [{**day, 'barangays': [
        {**b, 'flood': _public_part(b['flood']), 'landslide': _public_part(b['landslide'])}
        for b in day['barangays']]} for day in result['days']]
    out['floors'] = [dict(f) for f in result['floors'] if f['level'] != 'Yellow']
    return out


# --- loading and caching --------------------------------------------------------------------------

def _rules():
    from apps.rainwatch.models import RainWatchRules
    row = RainWatchRules.current()
    return row.as_rules() if row is not None else BALANCED


WET_UNKNOWN = {'mm_14_days': None, 'wet': None}


def _wet_key(today, rules):
    return f'rainwatch:wet:{today.isoformat()}:{rules.wet_14day_mm}'


def _wet_last_key(rules):
    return f'rainwatch:wet-last:{rules.wet_14day_mm}'


def _wet_lock_key(today, rules):
    return f'rainwatch:wet-lock:{today.isoformat()}:{rules.wet_14day_mm}'


def _last_good(stored, today):
    """The stored last known value, if it was worked out for a Manila day at most 2 days before today."""
    try:
        day, wet = date.fromisoformat(stored['day']), stored['wet']
    except (TypeError, KeyError, ValueError):
        return None
    return wet if timedelta(0) <= today - day <= timedelta(days=WET_LAST_DAYS) else None


def _wet_cached(today, rules):
    """Wet ground for one request. Read from the cache, never worked out here (spec anti-goal 1).

    The day's value when known; else the last known value when at most 2 days old; else unknown (dry
    cut-offs; staff see 'Ground wetness unknown'). A miss of the day's value starts the work in the
    background; an unknown day's value is kept 15 minutes before it is tried again.
    """
    try:
        hit = cache.get(_wet_key(today, rules))
        if hit is not None and hit.get('wet') is not None:
            return hit
        last = _last_good(cache.get(_wet_last_key(rules)), today)
    except Exception as exc:
        logger.warning('Cache unavailable (%s); ground wetness unknown.', exc)
        return dict(WET_UNKNOWN)
    if hit is None:
        try:
            refresh_wet_in_background(today, rules)
        except Exception:
            logger.exception('Could not start working out the ground wetness.')
    return last or hit or dict(WET_UNKNOWN)


def refresh_wet_in_background(today, rules) -> bool:
    """Start working out the day's wet ground in a daemon thread, unless one is already running here or
    (cache.add on its own lock key) on any worker that shares the cache. True when one was started."""
    if any(t.name == WET_THREAD and t.is_alive() for t in threading.enumerate()):
        return False
    if not cache.add(_wet_lock_key(today, rules), 1, WET_LOCK_TTL):
        return False
    _start_wet_thread(today, rules)
    return True


def _start_wet_thread(today, rules):
    """The one place the thread starts; tests replace it to run the work deterministically."""
    threading.Thread(target=_refresh_wet, args=(today, rules), name=WET_THREAD, daemon=True).start()


def _refresh_wet(today, rules):
    """The background work: store the day's value (1 h, or 15 min when unknown), keep it as the last known
    value when known, then bump() so cached answers pick it up. Every failure is logged and swallowed."""
    try:
        wet = wet_ground(today, rules)
        known = wet['wet'] is not None
        cache.set(_wet_key(today, rules), wet, WET_TTL if known else WET_FAIL_TTL)
        if known:
            cache.set(_wet_last_key(rules), {'day': today.isoformat(), 'wet': wet}, WET_LAST_TTL)
        bump()
    except Exception:
        logger.exception('Working out the ground wetness failed; tried again in %d minutes.', WET_LOCK_TTL // 60)
    finally:
        close_old_connections()
        connection.close()


def _compute(now):
    from apps.barangays.models import Barangay
    from apps.history.exposure import read_exposure
    from apps.history.hazard_data import read_terrain
    from apps.rainwatch.models import PagasaAlert

    rules = _rules()
    runs = latest_runs(now)
    if _newest_full(runs) is None:  # keep the age of an older full run, without its hours
        row = _newest_full_row()
        if row is not None:
            runs.append(_stored(row, series=False))
    alerts = list(PagasaAlert.objects.filter(Q(sent__gte=now - ALERT_LOOKBACK) | Q(expires__gt=now))
                  .defer('raw_xml', 'description').order_by('sent', 'id'))
    overrides = active_overrides(now)
    prefetch_related_objects(overrides, 'created_by')
    barangays = dict(Barangay.objects.values_list('id', 'name'))
    wet = _wet_cached(now.astimezone(MANILA).date(), rules)
    return build(now, rules, runs, wet, alerts, overrides, read_exposure(), read_terrain(), barangays)


def result_key(version, staff):
    return f'rainwatch:result:{version}:{"staff" if staff else "public"}'


def rain_watch(now=None, staff=False) -> dict:
    """The answer for one audience, cached 300 s; a new run, alert or override clears it (bump).
    If the cache fails, the failure is logged and the answer is worked out uncached."""
    now = now or timezone.now()
    try:
        version = cache.get(VERSION_KEY, 0)
        hit = cache.get(result_key(version, staff))
    except Exception as exc:
        logger.warning('Cache unavailable (%s); working out the rain watch uncached.', exc)
        version, hit = None, None
    if hit is not None:
        return hit
    result = _compute(now)
    public = public_view(result)
    if version is not None:
        try:
            cache.set_many({result_key(version, True): result, result_key(version, False): public}, RESULT_TTL)
        except Exception as exc:
            logger.warning('Cache unavailable (%s); the rain watch answer was not kept.', exc)
    return result if staff else public
