"""
Importing the BFP fire log and the flood and landslide log, from the command
line (manage.py import_bfp_fires, import_flood_landslide) and from the History
page (import_views.py), through the same functions so the two can't drift.

Each reads the workbook, plans the records without the database
(bfp_import.plan_import, flood_landslide.plan_import) and, when told to save,
creates them in one transaction. A re-import adds only rows whose source_ref
is new, so the same log can be brought in again after rows are added to it.
"""
from pathlib import Path

from django.db import transaction

from apps.barangays.models import Barangay, Purok
from apps.hazards.models import HazardType
from apps.history import bfp
from apps.history import flood_landslide as fl
from apps.history.bfp_import import plan_import as plan_fires
from apps.history.bfp_link import load_link_index
from apps.history.models import HistoricalRecord

# Other spellings, unplaced puroks' sitios, and landmarks and streets by area (load_link_index)
PUROK_DATA = Path(__file__).resolve().parents[1] / 'barangays' / 'data' / 'puroks'

FIRE, FLOODS = 'fire', 'flood_landslide'
KIND_LABELS = {FIRE: 'BFP fire log', FLOODS: 'Flood and landslide log'}
# The sheet the History page's export writes (export.to_xlsx)
EXPORT_SHEET = 'History'


class ImportProblem(Exception):
    """The file, or the database, can't be imported from; the message says why."""


def _rewind(source):
    if hasattr(source, 'seek'):
        source.seek(0)


def kind_of(source):
    """
    FLOODS for a workbook with a Flood or Landslide sheet, FIRE for any other.
    A file the History page exported is refused: its records are already in
    the history, and its floods sit in the fire log's columns.
    """
    import openpyxl

    try:
        wb = openpyxl.load_workbook(source, read_only=True)
    except Exception:
        raise ImportProblem('This is not an Excel workbook (.xlsx).')
    try:
        names = list(wb.sheetnames)
    finally:
        wb.close()
        _rewind(source)
    if names and names[0] == EXPORT_SHEET:
        raise ImportProblem('This file was exported from the History page. Its records are already in the history.')
    return FLOODS if set(fl.EVENT_SHEETS) & set(names) else FIRE


def purok_index():
    """({barangay id: [purok names]}, {(barangay id, purok name): purok id})."""
    by_barangay, ids = {}, {}
    for pk, barangay_id, name in Purok.objects.values_list('id', 'barangay_id', 'name'):
        by_barangay.setdefault(barangay_id, []).append(name)
        ids[(barangay_id, name)] = pk
    return by_barangay, ids


def import_fires(source, save=False):
    """The BFP fire log: its report (bfp_import.plan_import), with the fires saved when save."""
    fire = HazardType.objects.filter(name__iexact='Fire').first()
    if fire is None:
        raise ImportProblem('There is no "Fire" hazard type. Run seed_data first.')
    try:
        rows = bfp.read_sheet(source)
    except Exception:
        raise ImportProblem('The fire log could not be read. Is it the BFP .xlsx?')
    by_barangay, ids = purok_index()
    existing = set(HistoricalRecord.objects.filter(source_ref__isnull=False).values_list('source_ref', flat=True))
    records, report = plan_fires(rows, existing, list(Barangay.objects.all()), by_barangay,
                                 load_link_index(PUROK_DATA))
    if save:
        with transaction.atomic():
            for rec in records:
                purok_name = rec.pop('purok_name')
                record = HistoricalRecord.objects.create(hazard_type=fire, **rec)
                if purok_name:
                    record.puroks.add(ids[(rec['barangay'].id, purok_name)])
    return report


def import_floods(source, save=False, include_warnings=False, replace=False):
    """
    The flood and landslide log: its report (flood_landslide.plan_import),
    with the records saved when save. replace deletes every record an
    earlier import of this log made first; report['replaced'] says how many.
    """
    types = {t.name: t for t in HazardType.objects.filter(name__in=fl.HAZARDS.values())}
    missing = sorted(set(fl.HAZARDS.values()) - set(types))
    if missing:
        raise ImportProblem(f'There is no hazard type named {", ".join(missing)}. Run seed_data first.')
    try:
        events, splits = fl.read_workbook(source)
    except ValueError as e:
        raise ImportProblem(f'{e} The flood and landslide log has the sheets Flood, Landslide and By Barangay.')
    except Exception:
        raise ImportProblem('The flood and landslide log could not be read.')

    by_barangay, ids = purok_index()
    earlier = HistoricalRecord.objects.filter(source_ref__startswith=fl.REF_PREFIX)
    existing = set() if replace else set(earlier.values_list('source_ref', flat=True))
    records, report = fl.plan_import(events, splits, existing, list(Barangay.objects.all()), by_barangay,
                                     load_link_index(PUROK_DATA), include_warnings=include_warnings)
    report['replaced'] = earlier.count() if replace else 0
    if save:
        with transaction.atomic():
            if replace:
                report['replaced'] = earlier.delete()[1].get('history.HistoricalRecord', 0)
            for rec in records:
                purok_names = rec.pop('purok_names')
                record = HistoricalRecord.objects.create(hazard_type=types[rec.pop('hazard')], **rec)
                if purok_names:
                    record.puroks.add(*(ids[(rec['barangay'].id, n)] for n in purok_names))
    return report


# What each report's lists of rows mean, in the order the History page shows them
FIRE_PROBLEMS = (('outside_city', 'Outside Talisay City'), ('bad_date', 'Date could not be read'),
                 ('duplicates', 'Same row typed twice'), ('no_barangay', 'No barangay found in the address'))
FLOOD_PROBLEMS = (('warnings_skipped', 'Warnings only, left out'), ('outside_city', 'Outside Talisay City'),
                  ('bad_date', 'Date could not be read'), ('unknown_hazards', 'Not a flood or landslide'),
                  ('duplicate_events', 'Same event twice'), ('no_barangay', 'No barangay named'),
                  ('splits_without_event', 'By Barangay rows with no event'),
                  ('unknown_barangays', 'Barangay not recognised'))


def summary(kind, report):
    """One shape for either report, for the History page's import window."""
    problems = FIRE_PROBLEMS if kind == FIRE else FLOOD_PROBLEMS
    out = {
        'kind': kind,
        'kind_label': KIND_LABELS[kind],
        'read': report['read'],
        'new': report['imported'],
        'already': report['skipped_existing'],
        'linked': report['linked'],
        'barangay_only': report['barangay_only'],
        'replaced': report.get('replaced', 0),
        # The fire log's rows are numbers, the flood log's already say "Flood row 4"
        'problems': [{'label': label, 'rows': [f'row {r}' if isinstance(r, int) else r for r in report[key]]}
                     for key, label in problems if report[key]],
        'unlinked': [],
        'to_check': report.get('to_check', []),
    }
    if kind == FIRE and report['unknown_alarms']:
        out['problems'].append({'label': 'Alarm level not recognised (filed as Low)',
                                'rows': [f'{alarm or "(blank)"} ×{n}' for alarm, n in report['unknown_alarms'].items()]})
    for barangay in sorted(report['unlinked']):
        for place, entry in sorted(report['unlinked'][barangay].items()):
            # The fire log counts fires per place; the flood log lists close names only
            close = entry['close'] if isinstance(entry, dict) else entry
            count = entry['fires'] if isinstance(entry, dict) else None
            out['unlinked'].append({'barangay': barangay, 'place': place, 'count': count, 'close': close})
    return out
