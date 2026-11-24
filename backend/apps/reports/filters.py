"""
The filters every Reports & Analytics endpoint shares: a period, a hazard type
and a barangay, read the same way everywhere so the same filters give the same
totals on every screen.

Dates are calendar days in Manila time; `date_to` runs to the end of its day.
A record belongs to a barangay when it is filed under it or linked to one of
its puroks, as on the History page (apps.history.area.barangay_records).
"""
from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Optional
from zoneinfo import ZoneInfo

from django.utils import timezone

from apps.barangays.models import Barangay
from apps.hazards.models import HazardType
from apps.history.area import barangay_records

MANILA = ZoneInfo('Asia/Manila')


class FilterError(ValueError):
    """A filter value the screen should show back to the user as a sentence."""


@dataclass(frozen=True)
class ReportFilters:
    date_from: Optional[date]
    date_to: Optional[date]
    hazard_type: Optional[HazardType]
    barangay: Optional[Barangay]


EARLIEST, LATEST = date(1900, 1, 1), date(2100, 12, 31)


def _date(params, key):
    raw = (params.get(key) or '').strip()
    if not raw:
        return None
    try:
        value = date.fromisoformat(raw[:10])
    except ValueError:
        raise FilterError(f'{key} must be a date like 2026-01-31.') from None
    # A half-typed year (0202) or a far one would make period arithmetic fail
    if not EARLIEST <= value <= LATEST:
        raise FilterError('Dates must be between 1900 and 2100.')
    return value


def _row(params, key, model, unknown):
    raw = (params.get(key) or '').strip()
    if not raw:
        return None
    # isascii: isdigit() alone accepts '²', which int() then rejects
    if not (raw.isascii() and raw.isdigit() and int(raw) > 0):
        raise FilterError(f'{key} must be an id.')
    found = model.objects.filter(pk=int(raw)).first()
    if found is None:
        raise FilterError(unknown)
    return found


def parse_report_filters(params):
    """ReportFilters from a QueryDict or dict; FilterError for a value that can't be used."""
    date_from = _date(params, 'date_from')
    date_to = _date(params, 'date_to')
    if date_from and date_to and date_from > date_to:
        raise FilterError('The start date is after the end date.')
    # With no end date the range runs to today, so a future start is backwards too
    if date_from and not date_to and date_from > timezone.localdate():
        raise FilterError('The start date is in the future.')
    return ReportFilters(
        date_from=date_from,
        date_to=date_to,
        hazard_type=_row(params, 'hazard_type', HazardType, 'Unknown hazard type.'),
        barangay=_row(params, 'barangay', Barangay, 'Unknown barangay.'),
    )


def day_start(d):
    """00:00 on this day, Manila time."""
    return datetime.combine(d, time.min, tzinfo=MANILA)


def day_end(d):
    """The last instant of this day, Manila time."""
    return datetime.combine(d, time.max, tzinfo=MANILA)


def filter_records(queryset, f):
    """HistoricalRecord rows that match the filters."""
    if f.date_from:
        queryset = queryset.filter(occurred_at__gte=day_start(f.date_from))
    if f.date_to:
        queryset = queryset.filter(occurred_at__lte=day_end(f.date_to))
    if f.hazard_type:
        queryset = queryset.filter(hazard_type=f.hazard_type)
    if f.barangay:
        queryset = queryset.filter(id__in=barangay_records(f.barangay))
    return queryset


def criteria_text(f):
    """The filters in the words the audit log has always used for reports."""
    return (f'date_from={f.date_from.isoformat() if f.date_from else "-"} '
            f'date_to={f.date_to.isoformat() if f.date_to else "-"} '
            f'barangay={f.barangay.name if f.barangay else "all"} '
            f'hazard_type={f.hazard_type.name if f.hazard_type else "all"}')
