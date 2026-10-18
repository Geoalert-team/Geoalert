"""
Seasonal hazard likelihood from the historical record. Rule-based
statistics only: no AI, no machine learning, nothing that learns.

For a month (say November), a barangay and a hazard type, it looks at the
same month in each past year the record covers and asks two things:

  * In how many of those Novembers did at least one event happen?
  * How many events were there on average?

Recent years count more than old ones. A year's weight halves every
HALF_LIFE_YEARS, the same half-life the map's history shading uses, so a
barangay that flooded every November until a drainage project three years
ago slowly stops showing as likely. That is the only adjustment; there is
no fitting and no hidden parameter.

Likelihood levels, from the weighted share of years with an event:

    High      at least HIGH_SHARE of years, or EXPECTED_HIGH or more events
              expected in the month
    Moderate  at least MODERATE_SHARE of years
    Low       it has happened in that month before, but rarely

Too little history makes a share meaningless (one year out of one is
"100%"), so a result based on fewer than MIN_YEARS years is marked
`limited`, and the page says so instead of hiding it.
"""

from collections import Counter, defaultdict
from datetime import datetime

HALF_LIFE_YEARS = 3.0
MAX_YEARS = 10
MIN_YEARS = 3
HIGH_SHARE = 0.6
MODERATE_SHARE = 0.3
EXPECTED_HIGH = 2.0

LEVELS = ['None', 'Low', 'Moderate', 'High']
SEVERITY_RANK = {'Green': 1, 'Orange': 2, 'Red': 3}
MONTH_NAMES = ['January', 'February', 'March', 'April', 'May', 'June', 'July',
               'August', 'September', 'October', 'November', 'December']


def years_for_month(month, now, first_event, max_years=MAX_YEARS):
    """
    The past years whose `month` is fully in the record, newest first.

    A year counts only once that month has ended (this year's November is
    not evidence before December) and only if the record had started by
    then, so the months before the first record are not read as "nothing
    happened".
    """
    if first_event is None:
        return []
    first_month = (first_event.year, first_event.month)
    years = []
    for year in range(now.year, first_event.year - 1, -1):
        if (year, month) >= (now.year, now.month):
            continue  # not over yet
        if (year, month) < first_month:
            continue  # before the record started
        years.append(year)
        if len(years) >= max_years:
            break
    return years


def year_weights(years):
    """{year: weight}, the newest year weighing 1 and older years less."""
    if not years:
        return {}
    newest = max(years)
    return {y: 0.5 ** ((newest - y) / HALF_LIFE_YEARS) for y in years}


def level_for(share, expected):
    if share <= 0:
        return 'None'
    if share >= HIGH_SHARE or expected >= EXPECTED_HIGH:
        return 'High'
    if share >= MODERATE_SHARE:
        return 'Moderate'
    return 'Low'


def likelihood(counts_by_year, weights):
    """
    counts_by_year: {year: number of events in the month that year}
    weights:        {year: weight} for every year considered
    Returns (share of years with an event, expected events, years hit).
    """
    total = sum(weights.values())
    if not total:
        return 0.0, 0.0, 0
    share = sum(w for y, w in weights.items() if counts_by_year.get(y, 0) > 0) / total
    expected = sum(w * counts_by_year.get(y, 0) for y, w in weights.items()) / total
    hit = sum(1 for y in weights if counts_by_year.get(y, 0) > 0)
    return share, expected, hit


def _typical_severity(severities):
    """The most common severity; on a tie, the worse one."""
    if not severities:
        return None
    counts = Counter(severities)
    return max(counts, key=lambda s: (counts[s], SEVERITY_RANK.get(s, 0)))


def seasonal_forecast(events, month, now, max_years=MAX_YEARS):
    """
    events: iterable of dicts with
        barangay_id, barangay, hazard, when (local datetime), severity
    month:  1-12
    now:    local datetime

    Returns a dict ready to serve: the years considered and one row per
    barangay and hazard type that has ever been hit in that month.
    """
    events = [e for e in events if e.get('when') is not None]
    first = min((e['when'] for e in events), default=None)
    years = years_for_month(month, now, first, max_years)
    weights = year_weights(years)
    in_window = set(years)

    grouped = defaultdict(lambda: {'counts': Counter(), 'severities': [], 'last': None})
    for e in events:
        when = e['when']
        if when.month != month or when.year not in in_window:
            continue
        key = (e.get('barangay_id'), e.get('barangay'), e.get('hazard'))
        g = grouped[key]
        g['counts'][when.year] += 1
        g['severities'].append(e.get('severity'))
        if g['last'] is None or when > g['last']:
            g['last'] = when

    rows = []
    for (barangay_id, barangay, hazard), g in grouped.items():
        share, expected, hit = likelihood(g['counts'], weights)
        rows.append({
            'barangay_id': barangay_id,
            'barangay': barangay or 'Unknown barangay',
            'hazard_type': hazard or 'Unknown',
            'probability': round(share, 3),
            'expected_events': round(expected, 2),
            'years_hit': hit,
            'years_considered': len(years),
            'level': level_for(share, expected),
            'limited': len(years) < MIN_YEARS,
            'typical_severity': _typical_severity(g['severities']),
            'events': sum(g['counts'].values()),
            'last_occurred': g['last'],
        })
    rows.sort(key=lambda r: (-LEVELS.index(r['level']), -r['probability'], -r['expected_events'], r['barangay']))

    return {
        'month': month,
        'month_name': MONTH_NAMES[month - 1],
        'years': sorted(years),
        'limited': len(years) < MIN_YEARS,
        'results': rows,
        'by_barangay': summarize_by_barangay(rows),
    }


def summarize_by_barangay(rows):
    """One row per barangay: its highest level and the hazard behind it."""
    best = {}
    for r in rows:
        key = r['barangay_id']
        current = best.get(key)
        rank = (LEVELS.index(r['level']), r['probability'], r['expected_events'])
        if current is None or rank > current[0]:
            best[key] = (rank, r)
    out = []
    for _, r in best.values():
        hazards = sorted(
            {x['hazard_type'] for x in rows if x['barangay_id'] == r['barangay_id'] and x['level'] != 'None'}
        )
        out.append({
            'barangay_id': r['barangay_id'],
            'barangay': r['barangay'],
            'level': r['level'],
            'top_hazard': r['hazard_type'],
            'probability': r['probability'],
            'hazards': hazards,
        })
    out.sort(key=lambda r: (-LEVELS.index(r['level']), -r['probability'], r['barangay']))
    return out


def seasonal_profile(events, now, barangay_id=None, hazard=None, max_years=MAX_YEARS):
    """
    The likelihood for each month of the year, January first, for one
    barangay (or the whole city when barangay_id is None) and one hazard
    type (or all of them). For the "when is the risky season here" chart.
    """
    picked = [
        e for e in events
        if e.get('when') is not None
        and (barangay_id is None or e.get('barangay_id') == barangay_id)
        and (hazard is None or (e.get('hazard') or '').lower() == hazard.lower())
    ]
    first_all = min((e['when'] for e in events if e.get('when')), default=None)
    months = []
    for m in range(1, 13):
        years = years_for_month(m, now, first_all, max_years)
        weights = year_weights(years)
        counts = Counter(e['when'].year for e in picked if e['when'].month == m and e['when'].year in weights)
        share, expected, hit = likelihood(counts, weights)
        months.append({
            'month': m,
            'month_name': MONTH_NAMES[m - 1],
            'probability': round(share, 3),
            'expected_events': round(expected, 2),
            'years_hit': hit,
            'years_considered': len(years),
            'level': level_for(share, expected),
        })
    return months


def as_local(dt, tz):
    """An aware datetime in the local zone, so months follow Manila's calendar."""
    if dt is None:
        return None
    if isinstance(dt, datetime) and dt.tzinfo is not None:
        return dt.astimezone(tz)
    return dt
