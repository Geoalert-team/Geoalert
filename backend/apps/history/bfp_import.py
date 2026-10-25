"""
What manage.py import_bfp_fires writes, decided without the database.

Each fire in the BFP log becomes one HistoricalRecord, linked to its purok
when the address names one, and to its barangay otherwise. Everything that
could not be placed goes into a report, so the purok list can be fixed
(spellings, missing names) and the import re-run: a re-run only adds rows
whose source_ref is new.
"""
import difflib
from collections import Counter

from apps.barangays.purok_estimate import norm_name
from apps.history import bfp
from apps.history.bfp_link import link_address, split_address


def _new_report(read):
    return {'read': read, 'imported': 0, 'skipped_existing': 0, 'linked': 0, 'barangay_only': 0,
            'duplicates': [], 'outside_city': [], 'bad_date': [], 'no_barangay': [],
            'unknown_alarms': Counter(), 'unlinked': {}}


def _as_typed(label, place):
    return f'{label.title()} {place}' if label else place


def _close(place, purok_names):
    by_key = {norm_name(n): n for n in purok_names}
    return [by_key[k] for k in difflib.get_close_matches(norm_name(place), list(by_key), n=3, cutoff=0.75)]


def _note_unlinked(report, row, barangay, purok_names):
    _, candidates = split_address(row['location'], [barangay.name])
    names = report['unlinked'].setdefault(barangay.name, {})
    for label, place in candidates:
        entry = names.setdefault(_as_typed(label, place), {'fires': 0, 'close': _close(place, purok_names)})
        entry['fires'] += 1


def _record(row, when, ref, barangay, purok_name):
    severity, _ = bfp.severity_for_alarm(row['alarm'])
    rec = {
        'occurred_at': when,
        'barangay': barangay,
        'purok_name': purok_name,
        'severity_level': severity,
        'description': f'BFP: {row["category"]} – {row["subcategory"]}, {row["alarm"]}',
        'alarm_level': row['alarm'],
        'property_category': row['category'],
        'property_subcategory': row['subcategory'],
        'damage_cost': row['damage_cost'],
        'structures_affected': row['structures_affected'],
        'total_casualties': bfp.total_casualties(row),
        'total_displaced': None,  # not in the BFP log
        'location_text': row['location'],
        'source_ref': ref,
        'is_sample': False,
    }
    rec.update({k: row[k] for k in bfp.CASUALTY_FIELDS})
    return rec


def plan_import(rows, existing_refs, barangays, puroks_by_barangay, variants):
    """(records to create, report). See the command for how the report is printed."""
    report = _new_report(len(rows))
    records, seen_rows, refs_used = [], set(), Counter()

    for row in rows:
        if not bfp.is_talisay(row):
            report['outside_city'].append(row['row'])
            continue
        when = bfp.parse_when(row['date'], row['time'])
        if when is None:
            report['bad_date'].append(row['row'])
            continue
        # The same row typed twice is one fire, not two
        content = tuple(sorted((k, str(v)) for k, v in row.items() if k != 'row'))
        if content in seen_rows:
            report['duplicates'].append(row['row'])
            continue
        seen_rows.add(content)

        # A different fire logged at the same minute and address gets :2, :3...
        base = bfp.source_ref(when, row['location'])
        refs_used[base] += 1
        ref = base if refs_used[base] == 1 else f'{base}:{refs_used[base]}'
        if ref in existing_refs:
            report['skipped_existing'] += 1
            continue

        if not bfp.severity_for_alarm(row['alarm'])[1]:
            report['unknown_alarms'][row['alarm']] += 1
        barangay, purok_name = link_address(row['location'], barangays, puroks_by_barangay, variants)
        if barangay is None:
            report['no_barangay'].append(row['row'])
        elif purok_name:
            report['linked'] += 1
        else:
            report['barangay_only'] += 1
            _note_unlinked(report, row, barangay, puroks_by_barangay.get(barangay.id, []))
        records.append(_record(row, when, ref, barangay, purok_name))

    report['imported'] = len(records)
    report['unknown_alarms'] = dict(report['unknown_alarms'])
    return records, report
