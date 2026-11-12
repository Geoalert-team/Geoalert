"""
Rain scenarios and period chances, as pure functions.

The flood and landslide models give a chance per day. A month or a week is
answered by replaying the rain recorded in past years ("scenarios"): each
scenario year s lays the period's dates over year s, the model gives a chance
for each day, and the days combine into one chance for the period. The answer
is the average over the scenarios, with the lowest and highest as its range.

Kept apart from the forecast module so the model module can import these
without a cycle.
"""

from calendar import monthrange
from dataclasses import dataclass
from datetime import date, timedelta
from math import prod

from . import forecast


@dataclass
class PeriodChance:
    probability: float  # mean over scenarios of 1 - prod(1 - p)
    expected: float     # mean over scenarios of sum(p)
    low: float          # lowest scenario chance
    high: float         # highest scenario chance
    years: list         # scenario years used, ascending


def period_dates(month, day, base_year):
    """The days of the period in `base_year`, the same period the history uses."""
    start, end = forecast.period_window(base_year, month, day)
    return [start + timedelta(days=i) for i in range((end - start).days)]


def shift_dates(dates, base_year, s):
    """
    The dates moved from `base_year` to scenario year `s`. Each keeps its
    offset in years from `base_year`; a day past the month's end becomes its
    last day (29 February to 28), and a date that lands twice is kept once.
    """
    out = []
    for d in dates:
        year = s + (d.year - base_year)
        moved = date(year, d.month, min(d.day, monthrange(year, d.month)[1]))
        if moved not in out:  # 29 and 28 February must not both count as the 28th
            out.append(moved)
    return out


def scenario_dates(month, day, year, complete):
    """
    {scenario year: its dates}, ascending. Without a `year` (the month view)
    every complete year is a scenario with its own month. With a year, only
    earlier years are: a month is moved into each (shift_dates), a date's
    week is the history's window for that year. A scenario is
    dropped when any of its dates is in a year without complete rain.
    """
    have = set(complete)
    out = {}
    for s in sorted(have):
        if year is None:
            dates = period_dates(month, None, s)
        elif s < year and day is None:
            dates = shift_dates(period_dates(month, None, year), year, s)
        elif s < year:
            # the history's own window for year s, so the two always agree
            dates = period_dates(month, day, s)
        else:
            continue
        if all(d.year in have for d in dates):
            out[s] = dates
    return out


def _summary(per_scenario):
    """PeriodChance from {s: (P_s, expected_s)}, or None when empty."""
    if not per_scenario:
        return None
    n = len(per_scenario)
    probs = [p for p, _ in per_scenario.values()]
    return PeriodChance(
        probability=float(sum(probs) / n),
        expected=float(sum(e for _, e in per_scenario.values()) / n),
        low=float(min(probs)),
        high=float(max(probs)),
        years=sorted(per_scenario),
    )


def period_chance(p_of, dates_by_s):
    """
    The chance of at least one event in the period. `p_of(date)` is the
    day's chance or None; a scenario with any None day is skipped.
    """
    per = {}
    for s, dates in dates_by_s.items():
        ps = [p_of(d) for d in dates]
        if any(p is None for p in ps):
            continue
        per[s] = (1.0 - prod(1.0 - p for p in ps), sum(ps))
    return _summary(per)


def pair_chance(pf_of, pl_of, dates_by_s):
    """
    The chance of at least one flood or landslide. Inside each scenario, a
    day has neither with chance (1 - pf)(1 - pl). `expected` counts both
    hazards. A scenario where either function gives None is skipped.
    """
    per = {}
    for s, dates in dates_by_s.items():
        pairs = [(pf_of(d), pl_of(d)) for d in dates]
        if any(pf is None or pl is None for pf, pl in pairs):
            continue
        per[s] = (
            1.0 - prod((1.0 - pf) * (1.0 - pl) for pf, pl in pairs),
            sum(pf + pl for pf, pl in pairs),
        )
    return _summary(per)


def any_chance(parts):
    """The chance that at least one of independent `parts` happens."""
    return float(1.0 - prod(1.0 - p for p in parts))
