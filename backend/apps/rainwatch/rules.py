"""Colour rules: rain in mm to Green/Yellow/Orange/Red. Pure, no database."""
from dataclasses import dataclass
from typing import Iterable, Optional, Tuple

GREEN, YELLOW, ORANGE, RED = 0, 1, 2, 3
LEVEL_NAMES = ('Green', 'Yellow', 'Orange', 'Red')

Cutoffs = Tuple[float, float, float]


@dataclass(frozen=True)
class Rules:
    flood_dry: Cutoffs
    flood_wet: Cutoffs
    slide_dry: Cutoffs
    slide_wet: Cutoffs
    wet_14day_mm: float
    flood_exposure_min: float
    steep_share_min: float
    stale_hours: int


BALANCED = Rules(
    flood_dry=(30.0, 60.0, 120.0),
    flood_wet=(20.0, 40.0, 80.0),
    slide_dry=(50.0, 80.0, 120.0),
    slide_wet=(25.0, 40.0, 60.0),
    wet_14day_mm=156.5,
    flood_exposure_min=190.0,
    steep_share_min=0.40,
    stale_hours=12,
)


def band(mm: float, cutoffs: Cutoffs) -> int:
    """Level reached: one step per cut-off the rain meets or passes."""
    return sum(1 for c in cutoffs if mm >= c)


def flood_level(mm_day: float, wet: bool, rules: Rules) -> int:
    return band(mm_day, rules.flood_wet if wet else rules.flood_dry)


def slide_level(mm_3day: float, wet: bool, rules: Rules) -> int:
    return band(mm_3day, rules.slide_wet if wet else rules.slide_dry)


def one_step_lower(level: int) -> int:
    return max(GREEN, level - 1)


def flood_exposed_ids(exposure: dict, rules: Rules) -> set:
    return {i for i, row in exposure.items() if row['exposure'] >= rules.flood_exposure_min}


def steep_ids(terrain: dict, rules: Rules) -> set:
    return {i for i, row in terrain.items() if row['slope_gt18'] >= rules.steep_share_min}


def combine(forecast: Optional[int], floors: Iterable[int]) -> Optional[int]:
    """Highest of the forecast and the floors; None only when there is neither."""
    levels = list(floors)
    if forecast is not None:
        levels.append(forecast)
    return max(levels) if levels else None
