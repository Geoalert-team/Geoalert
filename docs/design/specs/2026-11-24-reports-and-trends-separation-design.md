# Reports & Analytics and Trend Analysis as two modules: design

Date: 2026-11-24. Supersedes the two-view page of
`2026-11-24-reports-analytics-remake-design.md` (kept for history); its backend
(shared filters, trends endpoint) is built on, not replaced.

Decided with the user: two nav items, two pages; no rainfall claimed (GeoAlert
stores none).

## Why

The two jobs are different. Reports & Analytics answers *what the system holds,
how operations went, and which official figures can be handed over*. Trend
Analysis answers *how hazards have behaved over the years, where they recur and
what changed*. The first build mixed them: operational response metrics and model
results sat inside Trend Analysis. Each module now has its own page, filters,
components and exports, and no chart appears in both.

## Research that shaped it

- **Sendai Framework indicators** (UNDRR): headline loss figures are deaths and
  missing (A), affected people (B), economic loss (C) and damage to critical
  infrastructure (D), disaggregated where data allows (sex, age). Reports &
  Analytics' impact summary follows this order with what the archive records.
- **NDRRMC / DSWD DROMIC situation reports**: affected barangays, families and
  persons; casualties split into dead, injured, missing. The barangay breakdown
  uses the same columns.
- **DesInventar** (UNDRR loss databases): every event, small ones included,
  recorded with time, place, type, cause, source and effects, then analysed as
  time series, crosstabs and thematic maps; results change as records are added.
  Trend Analysis uses the same three lenses: time, place, type.
- **Mann–Kendall with Sen's slope**: the usual non-parametric test of a monotonic
  trend in a yearly series; works from 4 values but has little power under ~10,
  and ties (repeated counts) need the tie-corrected variance. Trend Analysis
  reports a direction only with at least 5 complete years and states the count of
  years otherwise.
- **Emerging hot spot analysis** (Esri): places are classed as persistent,
  sporadic, new, intensifying and so on from their yearly series. With 22
  barangays and few years, Trend Analysis uses the plain-language core of it:
  events in every year, most years, some years, or only the latest.
- **Historical-limits aberration detection** (CDC EARS family): a period is
  unusual when it exceeds the mean of the same period in other years by two
  standard deviations, which needs a few years of baseline. Trend Analysis flags
  unusual months this way, only with at least 3 baseline years.
- **Choropleth practice**: raw counts on areas of different size mislead; map a
  rate. Barangays have boundaries but no population in GeoAlert, so the map
  shades events per km² and lists the counts beside it.
- **Climate**: no source found that states Talisay's Modified Coronas type or
  its rainy months, so the screens make no claim about wet or dry seasons.

## What the data supports (from the code; the screens show the live fill rates)

| Data | Source | Holds | Missing |
|---|---|---|---|
| Archive (`HistoricalRecord`) fires | BFP fire log import | date and time, barangay, purok, alarm level, property category and sub-category, damage cost, structures affected, injured and dead by firefighter/civilian and sex | displaced |
| Archive floods, landslides | DRRMO events sheet import | date, barangay, purok, sub-category, cause, injured, dead, families and persons affected | displaced, damage cost |
| Zones, alerts, notices, incident reports | GeoAlert itself | since the system went live (Nov 2026) | earlier years |
| Barangay boundaries | load_barangays | area | population |
| Rainfall | none (NASA POWER files removed 2026-11-22) | — | all |

Limits stated on screen: an absent year may be a gap in the archive, not a quiet
year; impact totals count only records that carry the figure ("recorded on N of
M"); hour of day is not analysed (many records carry a date only).

## Module 1: Reports & Analytics (`/app/reports`, nav "Reports & Analytics")

One filter bar (period presets, custom dates, hazard, barangay) with an **Apply**
button: the page always shows one applied set of filters, each Apply loads each
open section once and writes one audit row per section. Three sections, as tabs
inside the page (`?section=summary|operations|models`):

1. **Summary** (the Hazard Summary report), from new `GET /api/reports/summary/`:
   - *What GeoAlert holds* (not filtered): archive records per hazard with first
     and last date; zones, alerts, notices and incident reports with their first
     date; barangays and puroks on file.
   - *Impact* for the filters: events; deaths; injured; families affected;
     persons affected; structures affected; damage cost (₱). Each with "recorded
     on N of M records". Displaced: "Not recorded".
   - *By hazard type* and *by barangay* tables with the same impact columns
     (barangay = filed under; Unspecified last); *by purok* when one barangay is
     picked; *severity*.
   - *Fire details* (property category, alarm level) and *flood and landslide
     details* (sub-category, cause) when those hazards are in scope.
   - *Data completeness*: share of the selected records with a barangay, a purok,
     a map location, a casualty figure, a damage cost (fires), families affected
     (floods and landslides).
2. **Operations** (the Response Status report), from `GET /api/reports/analytics/`
   extended with `zones_by_status`: zones published, active now, resolved,
   archived, withdrawn; alerts by severity; alert notices opened and median time;
   incident reports by status, review rate and median time; median time a zone
   stayed active; barangay activity; the "records begin" line.
3. **Models & data**: likely fires by barangay (the fire model), flood data
   readiness, model updates, model accuracy. Not filtered by period (stated).

Each section exports CSV, Save as PDF and Print, logged first via
`POST /api/reports/printed/` (`hazard-summary`, `response-status`, new
`models`), criteria taken from the loaded answer, never from unapplied controls;
export is disabled while loading or with no answer. Print shows the active
section only, with a document header (office, title, filters, generated by and
at). The old `hazard-summary/` and `response-status/` endpoints stay for API
callers.

## Module 2: Trend Analysis (`/app/trends`, nav "Trend Analysis")

Historical archive only (`HistoricalRecord`). Filters live (presets: All records
(default), 10 years, 5 years, 3 years, This year, Custom; hazard; barangay);
custom dates commit on blur/Enter, not per keystroke. Sections in reading order:

1. **Key changes** (`GET /api/reports/trends/patterns/`): per hazard, the yearly
   counts over complete years; the Mann–Kendall/Sen verdict (`increasing`,
   `decreasing`, `no_clear_trend`, or `too_few_years` under 5 complete years);
   the latest complete year against the average of earlier years; this year so
   far. Each written as a sentence built from those numbers only, e.g. "Fire: 51,
   63, 78 events in 2023–2025. Three complete years are too few to call a trend."
   Then **unusual months**: a month whose count is above the mean + 2 SD of the
   same month in at least 3 other years, and at least 3 events.
2. **Over time** (`GET /api/reports/trends/`, extended): stacked events by hazard
   with Day/Week/Month/Quarter/Year (auto by range; day up to 92 days, week up to
   2 years); a period not fully inside the range is marked partial (lighter bar,
   "(partial)" in tables and CSV); a **calendar heatmap** (year × month).
3. **Seasons**: average events per calendar month per covered year (not raw
   sums), by hazard; day-of-week profile; the seasons-on-record outlook (existing
   `SeasonalOutlook`); the rainfall note.
4. **Places** (`GET /api/reports/trends/places/`): a barangay map shaded by events
   per km² for the range (counts in the tooltip and table); per barangay the
   yearly counts, years with events of years covered, and a recurrence class
   (every year, most years, some years, only the latest year, none; too few
   years under 3 complete years); latest year against the earlier average.
5. **Hazard mix**: hazard type × barangay crosstab (counts and row share);
   severity mix by year.
6. **Compare periods**: the range against the window of the same length before
   it, by hazard and by barangay, with the differences.

Export: CSV of every table, Save as PDF, Print, logged via `printed` with report
`analytics` (worded "Trend Analysis"), criteria from the loaded answers.

### Revision (2026-11-25): Trend Analysis made simple

At the user's request ("simple and easy to understand"), the screen keeps four
plain-language sections; the API keeps everything above.

1. **At a glance**: per hazard a status in plain words (Going up, Going down, No
   steady change, Not enough years yet, Gaps in the records), the last full
   year's count, how it compares with the years before, this year so far, one
   plain sentence and the yearly bars; then **Months that stood out**
   ("April 2024: 17 fire events. April usually has 9 to 14."). The method
   (Mann–Kendall, Sen's slope, two standard deviations) is in a closed "How we
   worked this out".
2. **Year by year**: one stacked chart, By year (default) or By month; periods
   cut by the range are marked "(part)".
3. **Busiest months**: the average per month, with each hazard's peak month in
   words, and the rainfall limit.
4. **Where it happens**: the map ("darker means more events for the barangay's
   size") beside the ten busiest barangays (events, most common hazard, how
   often), with all 22 on request.

Left off the screen: the calendar, day of week, severity by year, hazard-mix
table, compare-periods table and the Day/Week/Quarter steps. The seasonal
outlook moved to Reports & Analytics › Models & data (an outlook for planning,
beside the likelihood list it refers to). Trend verdicts also name no direction
when a tested year is empty (`gaps`), and the test stops at a hazard's last
record (later years are named as possible missing data). Month averages divide
each month by the years it was covered.

## Backend changes

- `filters.py`: dates must fall in 1900–2100 ("Dates must be between 1900 and
  2100."); a start date after today with no end date is a 400 ("The start date is
  in the future.").
- `trends/`: `partial` on each series bucket; granularity `day`, `week` added with
  limits (400 "Too many periods: choose a longer step."); `calendar`
  (year × month counts); `month_average` (per hazard, per month, average per
  covered year); `weekday`; `severity_by_year`.
- New `trends/patterns/` and `trends/places/` as above; new `summary/`.
- `analytics/`: adds `zones_by_status`.
- `printed/`: adds report key `models` ("Models and data").
- All: `IsAuthenticated, IsDRRMOOfficer`; logged `GENERATE_REPORT`; counted in
  the database (aggregates, `Trunc`/`Extract` in Manila time); loads on Django
  4.2 and 5.2; no schema change.

## Navigation and old links

- Nav (DRRMO, Admin): Dashboard, History, Reports & Analytics, Trend Analysis,
  Security. Route gates as now.
- `/app/analytics`, `/app/reports?view=trends`, `/app/reports?tab=analytics` →
  `/app/trends` (filters carried). `/app/reports?tab=models` →
  `/app/reports?section=models`. History links to Trend Analysis; the dashboard's
  and the likelihood card's "more" links go to Reports & Analytics › Models & data.

## Testing

Backend unit tests for every new computation (MK/Sen with ties, verdict rules,
unusual months, recurrence classes, partial buckets, density, impact sums with
recorded-on counts, date bounds) and API tests (filters, 400s, permissions,
audit). Frontend tests for both pages' wiring, filters (apply vs live, commit on
blur), sections' states, exports logged first with the loaded criteria, and the
redirects. Full suites, build, and the headless-Chrome walk-through against the
local sample database at desktop and 375 px.
