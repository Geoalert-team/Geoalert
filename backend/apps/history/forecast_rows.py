"""
The forecast's barangay rows: one per barangay with a boundary for each
hazard the forecast covers, with the history columns forecast.py gives them
and the figures the hazard's model gives (or "unavailable" with a reason).

Shared by views.forecast_result and the fire model's serving code, so both
make rows the same way. Since 2026-11-22 fire is the only hazard with a
prediction model (docs/design/specs/2026-11-22-fire-purok-model-design.md).
"""
from apps.history import forecast


def places():
    """Every barangay the map draws, as {'id', 'name'}: one with no boundary is not a place on the map."""
    from apps.barangays.models import Barangay

    return [{'id': pid, 'name': name}
            for pid, name in Barangay.objects.exclude(boundary__isnull=True).values_list('id', 'name')]


def _rank_key(row):
    """forecast.rank_rows' order, worst first, with a missing figure ranked lowest instead of failing."""
    def down(value):
        return float('inf') if value is None else -value
    return (-forecast.LEVELS.index(row['level']), down(row.get('probability')), down(row.get('expected_events')),
            row['barangay'])


def rerank(result):
    """Sort the rows worst first and rebuild the barangay summary from the rows that have figures."""
    result['results'].sort(key=_rank_key)
    result['by_barangay'] = forecast.summarize_by_barangay(
        [r for r in result['results'] if r.get('probability') is not None and r.get('expected_events') is not None])


def _listed(result, key, hazard):
    names = result.setdefault(key, [])
    if hazard not in names:
        names.append(hazard)


def hazard_rows(result, hazard, where):
    """
    {barangay id: row} for this hazard, one per place in `where`. A missing
    row is made with empty history; a row for a barangay that is not a place
    is removed (it has no outline, so no figure). Its events still count in
    `outcome`.
    """
    ids = {p['id'] for p in where}
    rows, kept = {}, []
    for r in result['results']:
        if r['hazard_type'] == hazard:
            if r['barangay_id'] not in ids or r['barangay_id'] in rows:
                continue
            rows[r['barangay_id']] = r
        kept.append(r)
    result['results'][:] = kept
    for place in where:
        if place['id'] in rows:
            continue
        row = {'barangay_id': place['id'], 'barangay': place['name'], 'hazard_type': hazard, 'years_hit': 0,
               'years_considered': len(result['years']), 'limited': result['limited'], 'typical_severity': None,
               'events': 0, 'last_occurred': None}
        if result.get('outcome') is not None:
            row['actual'] = 0
        result['results'].append(row)
        rows[place['id']] = row
    return rows


def set_unavailable(row, reason):
    """No figure on this row, with the reason the page shows."""
    for key in ('model', 'range', 'in_training'):
        row.pop(key, None)
    row.update(method='unavailable', probability=None, expected_events=None, level='None', reason=reason)


def mark_unavailable(result, hazard, where, reason):
    """Every place's row of this hazard unavailable with `reason`, and the hazard in `unavailable_hazards`."""
    for row in hazard_rows(result, hazard, where).values():
        set_unavailable(row, reason)
    _listed(result, 'unavailable_hazards', hazard)
    rerank(result)


def mark_profile_unavailable(result):
    """No figure in the 12-month chart, rather than a counting one."""
    if result.get('profile') is None:
        return
    for entry in result['profile']:
        entry.update(probability=None, expected_events=None, level='None')
    result['profile_method'] = 'unavailable'
