"""Join stored GFS runs into one hourly series, place it, and total Manila days.

Pure Python: no models, no database. Times are aware UTC datetimes.
"""
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Iterable

from apps.history.hazard_data import MANILA

GRID = ((10.25, 123.75), (10.25, 124.0), (10.5, 123.75), (10.5, 124.0))
CITY = (10.2835, 123.8212)
UPLAND = (10.325, 123.795)
SOURCE_PREFERENCE = {'gfs-nomads': 1, 'gfs-dynamical': 0}

_HOUR = timedelta(hours=1)


@dataclass(frozen=True)
class RunData:
    """Hour k (1-based) covers init_time + (k-1) h to init_time + k h."""
    source: str
    init_time: datetime
    series: dict


def stitched(runs: Iterable[RunData]) -> dict:
    """Per hour start (UTC): grid values from the newest run covering it.

    A tie on init_time goes to the higher SOURCE_PREFERENCE.
    """
    best = {}  # hour -> (rank, values)
    for run in runs:
        rank = (run.init_time, SOURCE_PREFERENCE.get(run.source, -1))
        length = min((len(run.series.get(p, ())) for p in GRID), default=0)
        for k in range(length):
            hour = run.init_time + k * _HOUR
            if hour not in best or rank > best[hour][0]:
                best[hour] = (rank, {p: run.series[p][k] for p in GRID})
    return {hour: best[hour][1] for hour in sorted(best)}


def at_point(grid_values: dict, point: tuple) -> float:
    lat, lon = point
    wy = (lat - 10.25) / 0.25
    wx = (lon - 123.75) / 0.25
    return ((1 - wy) * ((1 - wx) * grid_values[(10.25, 123.75)] + wx * grid_values[(10.25, 124.0)])
            + wy * ((1 - wx) * grid_values[(10.5, 123.75)] + wx * grid_values[(10.5, 124.0)]))


def place_hours(hours: dict, point: tuple) -> dict:
    """Only hours that carry all 4 grid points."""
    return {h: at_point(v, point) for h, v in hours.items() if all(p in v for p in GRID)}


def manila_day_total(hours: dict, day: date) -> tuple:
    """Sum of the 24 hours from day 00:00 Asia/Manila, and whether all 24 are present."""
    start = datetime.combine(day, time(0), tzinfo=MANILA).astimezone(timezone.utc)
    total, count = 0.0, 0
    for k in range(24):
        value = hours.get(start + k * _HOUR)
        if value is not None:
            total += value
            count += 1
    return total, count == 24
