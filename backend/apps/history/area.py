"""
The past hazards of one barangay, or of one purok in it, for the map's
barangay panel and the History page's Purok filter.

A barangay's history is the records filed under it plus the records linked
to one of its puroks, each once: a BFP fire can be filed under one barangay
and placed in a purok across the border. Records filed under the barangay
with no purok are its "Purok not recorded" ones; they colour no purok.

Levels follow apps/history/purok_levels.py: each hazard type is counted on
its own, and a purok over several types takes the highest of its levels.
"""
from django.db.models import Q

from apps.history.models import HistoricalRecord
from apps.history.purok_levels import RANK, level_for, purok_counts, thresholds

NOT_RECORDED = {'id': 'none', 'name': 'Purok not recorded', 'parent': ''}


def barangay_records(barangay):
    """Ids of the records filed under this barangay or linked to one of its puroks (for id__in)."""
    return HistoricalRecord.objects.filter(Q(barangay=barangay) | Q(puroks__barangay=barangay)).values('id')


def _top(levels):
    """The highest of these levels, or None when there is none (no history is no level)."""
    known = [lv for lv in levels if lv in RANK]
    return max(known, key=RANK.get) if known else None


def _event(record, staff):
    event = {
        'id': str(record.id),
        'date': record.occurred_at,
        'type': record.hazard_type.name if record.hazard_type else None,
        'property_category': record.property_category,
        'property_subcategory': record.property_subcategory,
        'alarm_level': record.alarm_level,
        'structures_affected': record.structures_affected,
        'puroks': [p.name for p in record.puroks.all()],
    }
    if staff:
        # The BFP's address and the damage stay off the public map
        event['location_text'] = record.location_text
        event['damage_cost'] = None if record.damage_cost is None else str(record.damage_cost)
    return event


def area_history(barangay, purok, types, since, staff):
    """
    The history of a barangay (purok None), one of its puroks (a Purok), or
    its records with no purok ('none'), since `since` (all time for None),
    for these hazard type names (every type when empty).
    """
    t = thresholds()
    if purok is None:
        records = HistoricalRecord.objects.filter(id__in=barangay_records(barangay))
    elif purok == 'none':
        records = HistoricalRecord.objects.filter(barangay=barangay, puroks__isnull=True)
    else:
        records = HistoricalRecord.objects.filter(puroks=purok)
    if since is not None:
        records = records.filter(occurred_at__gte=since)
    if types:
        records = records.filter(hazard_type__name__in=types)
    records = records.select_related('hazard_type').prefetch_related('puroks').order_by('-occurred_at', 'id')
    events = [_event(r, staff) for r in records]
    result = {'count': len(events), 'thresholds': t, 'events': events, 'puroks': [], 'unplaced': 0}

    if purok == 'none':
        result.update(purok=NOT_RECORDED, level=None)
        return result

    # Each purok's counts by type; a purok with several types takes its highest level
    counts = purok_counts(since, types)

    def level_of(pid):
        return _top(level_for(n, t) for (p, _), n in counts.items() if p == pid)

    if purok is not None:
        result.update(purok={'id': purok.id, 'name': purok.name, 'parent': purok.parent}, level=level_of(purok.id))
        return result

    rows = []
    for pid, name, parent in barangay.puroks.values_list('id', 'name', 'parent'):
        # Its level is the highest of its types' levels, not the level of its
        # total count: by_type says which type set it
        by_type = {kind: {'count': c, 'level': level_for(c, t)} for (p, kind), c in counts.items() if p == pid}
        n = sum(v['count'] for v in by_type.values())
        if n:
            rows.append({'id': pid, 'name': name, 'parent': parent, 'count': n, 'level': level_of(pid),
                         'by_type': by_type})
    rows.sort(key=lambda r: (-r['count'], r['name']))
    result.update(purok=None, puroks=rows, level=_top(r['level'] for r in rows),
                  unplaced=sum(1 for e in events if not e['puroks']))
    return result
