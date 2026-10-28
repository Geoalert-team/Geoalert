"""
The flood and landslide log: reading it (manage.py import_flood_landslide)
and closing a flood or landslide in the app as one row of it (close_fields).

The workbook is laid out like the BFP fire log. The Flood and Landslide sheets
hold one event per row below three header rows: when (A-B), where (C-F), the
hazard type and sub category (G-H), the cause (I), injured, fatalities,
families and persons affected (J-M) and what happened (N). The By Barangay
sheet splits the same events one row per barangay (or purok) below one header
row, and an event naming no barangay is not in it.

Each (event, barangay) becomes one history record, so the map's barangay
panel, the History filter and the forecast, which all read a record's one
barangay, see every barangay an event hit. An event in no barangay is one
record without one. A purok is linked where the sheet names one that is on
that barangay's purok list; otherwise the record is filed under the barangay
and the place goes in the report, as the BFP import does.

Plain functions so they test without the database; the command does the
lookups and the one transaction.
"""
import hashlib
import re
from datetime import datetime

from apps.barangays.aliases import canonical, match_barangay
from apps.history import bfp
from apps.history.bfp_import import _close
from apps.history.bfp_link import find_purok, split_address

REF_PREFIX = 'flood-landslide:'
HAZARDS = {'FLOOD': 'Flood', 'LANDSLIDE': 'Landslide'}
EVENT_SHEETS = ('Flood', 'Landslide')
SPLIT_SHEET = 'By Barangay'

# Column letter -> key, from A
EVENT_COLUMNS = ('date', 'time', 'region', 'province', 'city', 'location', 'hazard', 'subcategory', 'cause',
                 'injured', 'fatalities', 'families', 'persons', 'impact', 'remarks', 'source')
SPLIT_COLUMNS = ('date', 'hazard', 'region', 'province', 'city', 'barangay', 'place', 'event', 'families',
                 'remarks', 'source')
COUNTS = ('injured', 'fatalities', 'families', 'persons')

# Rows the log keeps as warnings, not events: nothing flooded or slid
WARNING_ONLY = {'RIVER LEVEL RISING', 'GROUND CRACK (SLOPE INSTABILITY)'}

# Sub categories (column H) as the log has them, for events. The one list the
# close form, the server's check and the import share; edit it here.
SUBCATEGORIES = {
    'Flood': ['RIVER OVERFLOW', 'RIVER SWELLING', 'FLASH FLOOD', 'UPLAND FLASH FLOOD', 'FLASH FLOOD (ROAD)',
              'ROAD FLOODING', 'COASTAL WAVES'],
    'Landslide': ['LANDSLIDE', 'ROAD LANDSLIDE', 'ROAD LANDSLIDE / ROCKFALL', 'SLOPE FAILURE / ROCKFALL',
                  'REPEATED ROCKSLIDES', 'LANDSLIDE / MUDFLOW', 'GROUND CRACK (SLOPE INSTABILITY)'],
}
CAUSE_MAX = 200
# Close form key -> HistoricalRecord field, for the counts J-M
CLOSE_COUNTS = ('injured', 'fatalities', 'families_affected', 'persons_affected')


def _text(value):
    return '' if value is None else ' '.join(str(value).split())


def _count(value):
    if value is None or str(value).strip() == '':
        return None
    try:
        return int(float(str(value).replace(',', '')))
    except ValueError:
        return None


def _rows(ws, columns, first_row):
    for number, cells in enumerate(ws.iter_rows(min_row=first_row, values_only=True), start=first_row):
        cells = tuple(cells) + (None,) * (len(columns) - len(cells))
        if all(c is None or str(c).strip() == '' for c in cells):
            continue
        yield number, dict(zip(columns, cells))


def read_workbook(path):
    """(events, splits). Raises ValueError when a sheet is missing."""
    import openpyxl

    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        missing = [s for s in (*EVENT_SHEETS, SPLIT_SHEET) if s not in wb.sheetnames]
        if missing:
            raise ValueError(f'No sheet named {", ".join(missing)}.')
        events = []
        for sheet in EVENT_SHEETS:
            for number, row in _rows(wb[sheet], EVENT_COLUMNS, 4):
                event = {'sheet': sheet, 'row': number, 'date': row['date'], 'time': row['time']}
                for key in ('city', 'location', 'hazard', 'subcategory', 'cause', 'impact', 'remarks', 'source'):
                    event[key] = _text(row[key])
                event['hazard'] = event['hazard'].upper()
                event.update({key: _count(row[key]) for key in COUNTS})
                events.append(event)
        splits = []
        for number, row in _rows(wb[SPLIT_SHEET], SPLIT_COLUMNS, 2):
            splits.append({'row': number, 'date': row['date'], 'hazard': _text(row['hazard']).upper(),
                           'barangay': _text(row['barangay']), 'place': _text(row['place']) or None,
                           'families': _count(row['families'])})
        return events, splits
    finally:
        wb.close()


def is_warning(event):
    sub = event['subcategory'].upper()
    return 'NO CONFIRMED' in sub or sub in WARNING_ONLY


def severity(event):
    """
    The log has no severity column, so it comes from the event's figures:
    any death, or 100+ families or 500+ persons affected, is Extreme; any
    injury or anyone affected is Moderate; otherwise Low.
    """
    n = {k: event.get(k) or 0 for k in COUNTS}
    if n['fatalities'] > 0 or n['families'] >= 100 or n['persons'] >= 500:
        return 'Red'
    if n['injured'] > 0 or n['families'] > 0 or n['persons'] > 0:
        return 'Orange'
    return 'Green'


def _day(value):
    when = bfp.parse_when(value, None)
    return when.date() if when else None


def _casualties(event):
    known = [event[k] for k in ('injured', 'fatalities') if event[k] is not None]
    return sum(known) if known else None


def _figures(event):
    parts = []
    for key, label in (('injured', 'injured'), ('fatalities', 'dead'),
                       ('families', 'families affected'), ('persons', 'persons affected')):
        if event[key] is not None:
            parts.append(f'{event[key]:,} {label}')
    return ', '.join(parts)


def _description(event, families_here, barangays):
    text = [event['impact']] if event['impact'] else []
    if families_here is not None:
        text.append(f'Families evacuated in this barangay: {families_here:,}.')
    # One barangay's record holds the event's figures; the others say what they were
    figures = _figures(event)
    if figures and barangays > 1:
        text.append(f'Whole event ({barangays} barangays): {figures}.')
    if event['source']:
        text.append('Sources: ' + ' '.join(event['source'].split()))
    return ' '.join(text)


def source_ref(day, hazard, barangay_text):
    """The key that stops a re-import adding the same event in the same barangay twice."""
    key = f'{day.isoformat()}|{hazard}|{canonical(barangay_text) if barangay_text else ""}'
    return REF_PREFIX + hashlib.sha1(key.encode('utf-8')).hexdigest()[:16]


def _places(place):
    """The parts of a place cell that may name a purok, parentheses dropped."""
    return re.sub(r'\([^)]*\)', '', place).replace('/', ',')


def _new_report(read):
    return {'read': read, 'imported': 0, 'skipped_existing': 0, 'linked': 0, 'barangay_only': 0,
            'outside_city': [], 'bad_date': [], 'warnings_skipped': [], 'no_barangay': [],
            'unknown_hazards': [], 'duplicate_events': [], 'splits_without_event': [],
            'unknown_barangays': [], 'unlinked': {}, 'to_check': []}


def _where(event):
    return f'{event["sheet"]} row {event["row"]}'


def _group_splits(splits):
    """{(day, hazard): [(barangay text, [places], families)]}, barangays in sheet order."""
    grouped = {}
    for s in splits:
        groups = grouped.setdefault((_day(s['date']), s['hazard']), {})
        key = canonical(s['barangay']) if s['barangay'] else ''
        entry = groups.setdefault(key, {'barangay': s['barangay'], 'places': [], 'families': None, 'rows': []})
        if s['place']:
            entry['places'].append(s['place'])
        if s['families'] is not None:
            entry['families'] = (entry['families'] or 0) + s['families']
        entry['rows'].append(s['row'])
    return {k: list(v.values()) for k, v in grouped.items()}


def plan_import(events, splits, existing_refs, barangays, puroks_by_barangay, variants, include_warnings=False):
    """(records to create, report). Each record has 'hazard' (type name) and 'purok_names' for the command."""
    report = _new_report(len(events))
    by_event = _group_splits(splits)
    records, keys_seen = [], set()

    for event in events:
        if not event['city'].upper().startswith('TALISAY'):
            report['outside_city'].append(_where(event))
            continue
        when = bfp.parse_when(event['date'], event['time'])
        if when is None:
            report['bad_date'].append(_where(event))
            continue
        hazard = HAZARDS.get(event['hazard'])
        if hazard is None:
            report['unknown_hazards'].append(_where(event))
            continue
        key = (when.date(), event['hazard'])
        if key in keys_seen:
            report['duplicate_events'].append(_where(event))
            continue
        keys_seen.add(key)
        if is_warning(event) and not include_warnings:
            report['warnings_skipped'].append(_where(event))
            continue
        if re.search(r'\bCHECK\b(?! resolved)', event['remarks']):
            report['to_check'].append(f'{when.date()} {hazard}: {event["location"]}')

        groups = by_event.get(key) or [{'barangay': '', 'places': [], 'families': None}]
        if not groups[0]['barangay']:
            report['no_barangay'].append(_where(event))
        casualties = _casualties(event)
        figures = {'injured': event['injured'], 'fatalities': event['fatalities'],
                   'families_affected': event['families'], 'persons_affected': event['persons']}
        for i, group in enumerate(groups):
            ref = source_ref(when.date(), event['hazard'], group['barangay'])
            if ref in existing_refs:
                report['skipped_existing'] += 1
                continue
            barangay = match_barangay(group['barangay'], barangays) if group['barangay'] else None
            if group['barangay'] and barangay is None:
                report['unknown_barangays'].append(group['barangay'])
            purok_names = []
            if barangay is not None:
                names = puroks_by_barangay.get(barangay.id, [])
                own_variants = variants.get(canonical(barangay.name), {})
                for place in group['places']:
                    _, candidates = split_address(_places(place), [])
                    found = find_purok(candidates, names, own_variants)
                    if found and found not in purok_names:
                        purok_names.append(found)
                    elif not found:
                        report['unlinked'].setdefault(barangay.name, {})[place] = _close(_places(place), names)
                report['linked' if purok_names else 'barangay_only'] += 1
            if group['barangay']:
                location = (f'{"; ".join(group["places"])}, ' if group['places'] else '') + f'BRGY {group["barangay"]}'
            else:
                location = event['location']
            records.append({
                'hazard': hazard,
                'occurred_at': when,
                'barangay': barangay,
                'purok_names': purok_names,
                'severity_level': severity(event),
                'description': _description(event, group['families'], len(groups)),
                'hazard_subcategory': event['subcategory'][:60],
                'cause': event['cause'][:CAUSE_MAX],
                # Stored once per event, so city totals in Reports add up
                **{k: (v if i == 0 else None) for k, v in figures.items()},
                'total_casualties': casualties if i == 0 else None,
                'total_displaced': None,  # the log counts persons affected, not displaced
                'location_text': location,
                'source_ref': ref,
                'is_sample': False,
            })

    for key, groups in by_event.items():
        if key not in keys_seen:
            report['splits_without_event'].extend(f'{SPLIT_SHEET} row {r}' for g in groups for r in g['rows'])
    report['imported'] = len(records)
    return records, report


# --- Closing a flood or landslide in the app: the log's columns H to N -------

def close_fields(data, hazard):
    """
    (fields, errors) for resolving a hazard of this type (its name): the
    HistoricalRecord values from the close form, and {field: message} for
    what is missing or wrong. A type with no sub category list (anything but
    a flood or landslide) is not asked for one. The server's side of
    eventClose.js, with the same words.
    """
    fields, errors = {}, {}

    choices = SUBCATEGORIES.get(hazard)
    sub = _text(data.get('hazard_subcategory')).upper() if choices else ''
    if choices and sub not in choices:
        errors['hazard_subcategory'] = 'Choose the sub category.'
    fields['hazard_subcategory'] = sub

    fields['cause'] = _text(data.get('cause'))
    if len(fields['cause']) > CAUSE_MAX:
        errors['cause'] = f'Keep the cause under {CAUSE_MAX} characters.'

    for key in CLOSE_COUNTS:
        fields[key], ok = bfp._whole(data.get(key))
        if not ok:
            errors[key] = 'Enter a whole number, 0 or more.'

    known = [fields[k] for k in ('injured', 'fatalities') if fields[k] is not None]
    fields['total_casualties'] = sum(known) if known else None
    fields['summary'] = (data.get('summary') or '').strip()
    return fields, errors
