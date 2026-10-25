"""
Reading the BFP Talisay fire log (manage.py import_bfp_fires).

One sheet, three header rows, then one fire per row. The file is typed by
hand: most dates are Excel dates, a few are text ("JULY 16,2023", with the
time as "1158H/16 JULY 2023"), and a blank cell means nobody filled it in,
which is kept apart from a zero.

Plain functions so they test without the database; the command does the
lookups and the one transaction.
"""
import hashlib
import re
from datetime import date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

MANILA = ZoneInfo('Asia/Manila')
EXCEL_EPOCH = date(1899, 12, 30)

# Injured, then fatalities; firefighter then civilian; male then female
CASUALTY_FIELDS = (
    'injured_ff_male', 'injured_ff_female', 'injured_civ_male', 'injured_civ_female',
    'fatal_ff_male', 'fatal_ff_female', 'fatal_civ_male', 'fatal_civ_female',
)

# Column letter -> key. K, N and Q are per-group totals the BFP leaves at 0
# even when a male/female cell is filled, so they are not read.
COUNT_COLUMNS = {
    'I': 'injured_ff_male', 'J': 'injured_ff_female', 'L': 'injured_civ_male', 'M': 'injured_civ_female',
    'O': 'fatal_ff_male', 'P': 'fatal_ff_female', 'R': 'fatal_civ_male', 'S': 'fatal_civ_female',
    'T': 'total_hurt', 'V': 'structures_affected',
}
TEXT_COLUMNS = {'E': 'city', 'F': 'location', 'G': 'category', 'H': 'subcategory'}

LOW_ALARMS = {'FIRE OUT UPON ARRIVAL', 'UNRESPONDED', '1ST ALARM'}
HIGH_ALARMS = {'3RD ALARM', '4TH ALARM', '5TH ALARM', 'GENERAL ALARM'}


def _col(letter):
    return ord(letter) - ord('A')


def _count(value):
    if value is None or str(value).strip() == '':
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _money(value):
    if value is None or str(value).strip() == '':
        return None
    try:
        return Decimal(str(value).replace(',', ''))
    except InvalidOperation:
        return None


def _text(value):
    return ' '.join(str(value).split()) if value is not None else ''


def read_sheet(path):
    """One dict per row below the headers that names a location (column F)."""
    import openpyxl

    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        rows = []
        for number, cells in enumerate(wb.worksheets[0].iter_rows(min_row=4, values_only=True), start=4):
            cells = tuple(cells) + (None,) * (23 - len(cells))  # a row can stop before column W
            if not _text(cells[_col('F')]):
                continue
            row = {'row': number, 'date': cells[_col('A')], 'time': cells[_col('B')]}
            row.update({key: _text(cells[_col(c)]) for c, key in TEXT_COLUMNS.items()})
            row['location'] = str(cells[_col('F')]).strip()
            row.update({key: _count(cells[_col(c)]) for c, key in COUNT_COLUMNS.items()})
            row['damage_cost'] = _money(cells[_col('U')])
            row['alarm'] = _text(cells[_col('W')]).upper()
            rows.append(row)
        return rows
    finally:
        wb.close()


def _parse_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if value is None:
        return None
    try:
        return EXCEL_EPOCH + timedelta(days=int(float(value)))
    except (TypeError, ValueError):
        pass
    try:
        return datetime.strptime(''.join(str(value).split()), '%B%d,%Y').date()
    except ValueError:
        return None


def _parse_time(value):
    if value is None or str(value).strip() == '':
        return time(0, 0)
    if isinstance(value, time):
        return value
    text = str(value).strip()
    match = re.match(r'(\d{1,4})H', text, re.I)
    try:
        hhmm = int(match.group(1)) if match else int(float(text))
        hours, minutes = divmod(hhmm, 100)
        return time(hours, minutes)
    except (TypeError, ValueError):
        return time(0, 0)


def parse_when(date_value, time_value):
    """When the alarm was raised, in Manila time, or None when the date can't be read."""
    day = _parse_date(date_value)
    if day is None:
        return None
    return datetime.combine(day, _parse_time(time_value), tzinfo=MANILA)


def severity_for_alarm(alarm):
    """(severity code, whether the alarm level is one we know)."""
    alarm = _text(alarm).upper()
    if alarm in LOW_ALARMS:
        return 'Green', True
    if alarm == '2ND ALARM':
        return 'Orange', True
    if alarm in HIGH_ALARMS or alarm.startswith('TF '):
        return 'Red', True
    return 'Green', False


def total_casualties(row):
    """
    The larger of column T and the sum of the male/female cells. Column T is
    read as everyone hurt or killed: it holds 1 whenever anyone was, even
    where the cells say otherwise. None when nothing was filled in.
    """
    cells = [row.get(k) for k in CASUALTY_FIELDS]
    known = [c for c in cells if c is not None]
    total = row.get('total_hurt')
    if not known and total is None:
        return None
    return max(sum(known), total or 0)


def source_ref(when, location):
    """The key that stops a re-import adding the same fire twice."""
    key = f'{when.isoformat()}|{" ".join(location.upper().split())}'
    return 'bfp:' + hashlib.sha1(key.encode('utf-8')).hexdigest()[:16]


def is_talisay(row):
    return _text(row.get('city')).upper().startswith('TALISAY')
