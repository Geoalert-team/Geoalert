"""The Rain watch forecast job: fetch GFS rain for 4 points and post it to GeoAlert.

Standalone (no Django). Run by .github/workflows/rain-forecast.yml every 6 hours.

    python tools/rain_forecast/fetch.py              # fetch and post
    python tools/rain_forecast/fetch.py --dry-run    # fetch, print the plan, post nothing
    python tools/rain_forecast/fetch.py --compare 2026111500
                                                     # NOMADS against dynamical.org, one cycle

Needs RAIN_WATCH_API_URL and RAIN_WATCH_INGEST_TOKEN in the environment (not for --compare).
"""
import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import gfs  # noqa: E402

JOB_VERSION = 'rain-forecast-1'
UTC = timezone.utc
FULL_HOURS = 96
GAP_HOURS = 6
MAX_GAP_RUNS = 12
POST_TRIES = 3


def _iso(dt):
    return dt.astimezone(UTC).strftime('%Y-%m-%dT%H:%M:%SZ')


def _parse(text):
    dt = datetime.fromisoformat(str(text).replace('Z', '+00:00'))
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def plan_runs(now, held, newest):
    """[(cycle, hours)]: the newest in full if needed, then up to 12 missing runs of 6 hours."""
    if newest is None:
        return []
    held_hours = {}
    for r in held:
        init = _parse(r['init_time'])
        held_hours[init] = max(held_hours.get(init, 0), int(r.get('hours', 0)))
    plan = []
    if held_hours.get(newest, 0) < 72:
        plan.append((newest, FULL_HOURS))
    cycle = newest - timedelta(hours=6)
    floor = now - timedelta(hours=72)
    gaps = 0
    while cycle > floor and gaps < MAX_GAP_RUNS:
        if cycle not in held_hours:
            plan.append((cycle, GAP_HOURS))
            gaps += 1
        cycle -= timedelta(hours=6)
    return plan


def payload(source, init, series, version):
    return {
        'source': source,
        'init_time': _iso(init),
        'job_version': version,
        'points': [
            {
                'lat': lat,
                'lon': lon,
                'first_hour_start': _iso(init),
                'mm_per_hour': [round(float(v), 4) for v in series[(lat, lon)]],
            }
            for lat, lon in gfs.GRID
        ],
    }


def _default_get(url, headers=None):
    import requests
    h = {'User-Agent': gfs.USER_AGENT}
    h.update(headers or {})
    r = requests.get(url, headers=h, timeout=60)
    r.raise_for_status()
    return r.content


def _default_post(url, body, headers):
    import requests
    r = requests.post(url, json=body, headers=headers, timeout=60)
    r.raise_for_status()
    return r.status_code


def _post_with_retries(post, url, body, headers, sleep):
    for attempt in range(1, POST_TRIES + 1):
        try:
            post(url, body, headers)
            return True
        except Exception as exc:  # noqa: BLE001 - any failure counts as a failed try
            print(f'  post failed (try {attempt}/{POST_TRIES}): {exc}', file=sys.stderr)
            if attempt < POST_TRIES:
                sleep(5 * 3 ** (attempt - 1))
    return False


def _held_runs(api, headers, get):
    try:
        data = json.loads(get(f'{api}/api/rain-watch/forecast-runs/status/', headers=headers))
        return list(data.get('runs', []))
    except Exception as exc:  # noqa: BLE001
        print(f'could not read the held runs ({exc}); treating none as held', file=sys.stderr)
        return []


def _compare(arg, get, decode, pause):
    cycle = datetime.strptime(arg, '%Y%m%d%H').replace(tzinfo=UTC)
    nomads = gfs.fetch_nomads(cycle, FULL_HOURS, get=get, decode=decode, pause=pause)
    init, dyn = gfs.fetch_dynamical(FULL_HOURS, cycle)
    print(f'NOMADS {_iso(cycle)} vs dynamical {_iso(init)}')
    if init != cycle:
        print('dynamical.org does not have this cycle; the comparison is not valid')
        return 1
    worst = 0.0
    for p in gfs.GRID:
        diffs = []
        for d in range(FULL_HOURS // 24):
            a = sum(nomads[p][d * 24:(d + 1) * 24])
            b = sum(dyn[p][d * 24:(d + 1) * 24])
            diffs.append(abs(a - b))
        worst = max(worst, max(diffs))
        print(f'  {p}: daily |diff| mm ' + ', '.join(f'{x:.3f}' for x in diffs))
    print(f'worst daily difference: {worst:.3f} mm ({"OK" if worst <= 0.1 else "TOO BIG"})')
    return 0 if worst <= 0.1 else 1


def main(argv=None, env=os.environ, get=None, post=None, exists=None, decode=None,
         now=None, sleep=time.sleep, pause=1.0, dynamical=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--compare', metavar='YYYYMMDDHH')
    args = parser.parse_args(argv)
    get = get or _default_get
    dynamical = dynamical or gfs.fetch_dynamical
    post = post or _default_post
    now = now or datetime.now(UTC)

    if args.compare:
        return _compare(args.compare, get, decode, pause)

    api = (env.get('RAIN_WATCH_API_URL') or '').rstrip('/')
    token = env.get('RAIN_WATCH_INGEST_TOKEN') or ''
    if not args.dry_run and not (api and token):
        print('RAIN_WATCH_API_URL and RAIN_WATCH_INGEST_TOKEN must be set', file=sys.stderr)
        return 2
    headers = {'Authorization': f'Bearer {token}'}
    held = _held_runs(api, headers, get) if api and token else []

    newest = gfs.latest_cycle(now, exists=exists)
    dyn = None
    if newest is None:
        print('NOMADS has no recent complete run; using dynamical.org')
        try:
            dyn = dynamical(FULL_HOURS, now)
            newest = dyn[0]
        except Exception as exc:  # noqa: BLE001
            print(f'dynamical.org failed too: {exc}', file=sys.stderr)
            return 1

    plan = plan_runs(now, held, newest)
    print('plan: ' + (', '.join(f'{_iso(c)} x{h}h' for c, h in plan) or 'nothing to do'))

    newest_ok = True
    for cycle, hours in plan:
        is_newest = cycle == newest
        source, init, series = 'gfs-nomads', cycle, None
        if dyn is not None and dyn[0] == cycle:
            source, series = 'gfs-dynamical', {p: v[:hours] for p, v in dyn[1].items()}
        else:
            try:
                series = gfs.fetch_nomads(cycle, hours, get=get, decode=decode, pause=pause)
            except Exception as exc:  # noqa: BLE001
                print(f'NOMADS failed for {_iso(cycle)}: {exc}', file=sys.stderr)
                if is_newest:
                    try:
                        init, full = dynamical(hours, cycle)
                        source, series = 'gfs-dynamical', full
                    except Exception as exc2:  # noqa: BLE001
                        print(f'dynamical.org failed too: {exc2}', file=sys.stderr)
        if series is None:
            if is_newest:
                newest_ok = False
                break
            continue
        body = payload(source, init, series, JOB_VERSION)
        size = len(json.dumps(body))
        print(f'{source} {_iso(init)} {hours}h: {size} bytes')
        if args.dry_run:
            continue
        ok = _post_with_retries(post, f'{api}/api/rain-watch/forecast-runs/', body, headers, sleep)
        if not ok and is_newest:
            newest_ok = False
            break  # the site is probably down; do not hammer it with the gap runs
    return 0 if newest_ok else 1


if __name__ == '__main__':
    sys.exit(main())
