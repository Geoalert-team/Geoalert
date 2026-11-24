"""
The statistics behind Trend Analysis, kept pure so they can be checked by hand.

- Mann–Kendall test with Sen's slope: the usual non-parametric test of a
  steady rise or fall in a yearly series. It needs no normal distribution and
  copes with repeated counts (ties). With few years it has little power, so a
  direction is only named from five complete years up (trend_verdict).
- Unusual counts: the historical-limits rule used in surveillance (CDC's EARS
  family): above the mean of the same period in other years by two standard
  deviations, with at least three such years to compare against.
- Recurrence: how many of the years covered had any event, the plain core of
  the recurring/persistent/new classes in emerging hot spot analysis.
"""
from collections import Counter
from math import erfc, sqrt
from statistics import mean, median, stdev

MIN_TREND_YEARS = 5
MIN_BASELINE_YEARS = 3
MIN_UNUSUAL_COUNT = 3
MIN_RECURRENCE_YEARS = 3


def mann_kendall(values):
    """{'s', 'z', 'p'}: the S statistic, its normal score and two-sided p (tie-corrected)."""
    n = len(values)
    if n < 3:
        return {'s': 0, 'z': 0.0, 'p': 1.0}
    s = sum((values[j] > values[i]) - (values[j] < values[i]) for i in range(n - 1) for j in range(i + 1, n))
    ties = sum(t * (t - 1) * (2 * t + 5) for t in Counter(values).values() if t > 1)
    var = (n * (n - 1) * (2 * n + 5) - ties) / 18
    if var <= 0 or s == 0:
        return {'s': s, 'z': 0.0, 'p': 1.0}
    z = (s - 1) / sqrt(var) if s > 0 else (s + 1) / sqrt(var)
    return {'s': s, 'z': round(z, 3), 'p': round(erfc(abs(z) / sqrt(2)), 4)}


def sens_slope(values):
    """The median of every pairwise slope (events per year for a yearly series)."""
    slopes = [(values[j] - values[i]) / (j - i) for i in range(len(values) - 1) for j in range(i + 1, len(values))]
    return float(median(slopes)) if slopes else 0.0


def trend_verdict(values, min_years=MIN_TREND_YEARS):
    """'too_few_years', 'increasing', 'decreasing' or 'no_clear_trend' (5% level)."""
    if len(values) < min_years:
        return 'too_few_years'
    test = mann_kendall(values)
    if test['p'] >= 0.05:
        return 'no_clear_trend'
    direction = sens_slope(values) or test['s']
    return 'increasing' if direction > 0 else 'decreasing'


def unusual(count, baseline, min_baseline=MIN_BASELINE_YEARS, min_count=MIN_UNUSUAL_COUNT):
    """Above the baseline's mean + 2 sample standard deviations (and not a trivial count)."""
    if len(baseline) < min_baseline or count < min_count:
        return False
    return count > mean(baseline) + 2 * stdev(baseline)


def recurrence(year_counts, min_years=MIN_RECURRENCE_YEARS):
    """How often a place had events across the years covered, oldest year first."""
    if len(year_counts) < min_years:
        return 'too_few_years'
    hit = sum(1 for c in year_counts if c > 0)
    if hit == 0:
        return 'none'
    if hit == len(year_counts):
        return 'every_year'
    if hit == 1 and year_counts[-1] > 0:
        return 'latest_only'
    return 'most_years' if hit >= 2 * len(year_counts) / 3 else 'some_years'


def change_vs_earlier(values):
    """The latest value against the average of the ones before it."""
    if not values:
        return {'latest': None, 'earlier_mean': None, 'pct': None}
    earlier = values[:-1]
    if not earlier:
        return {'latest': values[-1], 'earlier_mean': None, 'pct': None}
    avg = round(mean(earlier), 2)
    pct = round((values[-1] - avg) / avg * 100) if avg else None
    return {'latest': values[-1], 'earlier_mean': avg, 'pct': pct}
