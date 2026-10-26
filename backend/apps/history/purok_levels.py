"""
A purok's hazard level from how often it has been hit.

Few past events in the period is green (Low), more is orange (Moderate), many
is red (Extreme); none is no level. The period and the two thresholds are
System Admin settings. Each hazard type is counted on its own, and a past
event counts once in every purok it touched (HistoricalRecord.puroks).

The values are the existing severity codes, so nothing downstream changes
vocabulary. This is the one place the rule lives.
"""
from datetime import timedelta

from utils.system_settings import default, get_setting

RANK = {'Green': 1, 'Orange': 2, 'Red': 3}
LABEL = {'Green': 'Low', 'Orange': 'Moderate', 'Red': 'Extreme'}


def thresholds():
    """{'years', 'moderate', 'extreme'}; all defaults when the settings contradict each other."""
    t = {'years': get_setting('history.period_years'),
         'moderate': get_setting('history.moderate_at'),
         'extreme': get_setting('history.extreme_at')}
    if t['extreme'] <= t['moderate']:
        t = {'years': default('history.period_years'),
             'moderate': default('history.moderate_at'),
             'extreme': default('history.extreme_at')}
    return t


def level_for(count, t):
    """The level for this many past events, or None for none."""
    if count <= 0:
        return None
    if count < t['moderate']:
        return 'Green'
    if count < t['extreme']:
        return 'Orange'
    return 'Red'


def highest(levels):
    """The highest of these levels; Low when there is none (an area with no history starts at Low)."""
    known = [lv for lv in levels if lv in RANK]
    return max(known, key=RANK.get) if known else 'Green'


def purok_levels(purok_ids, hazard_type, now):
    """{purok id: {'count', 'level'}} for these puroks, counting this hazard type in the period."""
    from django.db.models import Count
    from apps.history.models import HistoricalRecord

    t = thresholds()
    since = now - timedelta(days=365 * t['years'])
    counts = dict(
        HistoricalRecord.objects
        .filter(hazard_type=hazard_type, occurred_at__gte=since, puroks__in=purok_ids)
        .values_list('puroks')
        .annotate(n=Count('id', distinct=True))
    )
    return {pid: {'count': counts.get(pid, 0), 'level': level_for(counts.get(pid, 0), t)} for pid in purok_ids}
