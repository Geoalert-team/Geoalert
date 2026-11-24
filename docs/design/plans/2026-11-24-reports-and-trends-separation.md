# Reports & Analytics and Trend Analysis Separation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split the module into two pages: Reports & Analytics (`/app/reports`: summary with impact and completeness, operations, models & data) and Trend Analysis (`/app/trends`: key changes, over time, seasons, places, hazard mix, compare), each with its own filters, sections and exports.

**Architecture:** Backend adds `summary/`, `trends/patterns/`, `trends/places/`, extends `trends/` and `analytics/`, bounds dates in the shared parser; pure statistics live in `apps/reports/stats.py`. Frontend gets two page shells reusing `FilterBar` (apply mode for Reports & Analytics, live mode for Trend Analysis), section components per page under `pages/reportsAnalytics/` and `pages/trendAnalysis/`, and a Leaflet choropleth for places.

**Tech Stack:** Django 5.2/DRF (loads on 4.2), PostGIS; React 18 CRA, react-router 6, Chart.js 4, react-leaflet 4; Jest (react-dom/client + act).

**Spec:** `docs/design/specs/2026-11-24-reports-and-trends-separation-design.md`

## Global Constraints

- Never commit (user rule).
- Permission `IsAuthenticated, IsDRRMOOfficer` on every endpoint; route gates `["System_Admin", "DRRMO_Officer"]`.
- Nav labels exactly `Reports & Analytics` and `Trend Analysis`; routes `/app/reports`, `/app/trends`.
- No number not counted from the database; impact figures carry `recorded_on`/`of`; `total_displaced` never charted, shown "Not recorded".
- Manila time; barangay rule `barangay_records` for filtering; rankings by filed barangay, Unspecified last.
- Exports logged first via `printed`, never blocked by a failed log, criteria from the loaded answer, disabled while loading.
- No schema change. Old endpoints `hazard-summary/`, `response-status/` keep working.

## Review Focus

1. A hazard with fewer than 5 complete years: no direction word ("increasing"/"decreasing") anywhere, only counts and "too few years".
2. Years with no records inside a hazard's span: counted as 0 in yearly series and stated as possibly missing data, never as "safe".
3. Re-applying identical filters on Reports & Analytics: no new request, no new audit row.
4. Typing a custom date on Trend Analysis: one request when the field is committed (blur/Enter), none per keystroke.
5. A barangay with no boundary: listed in the places table with density "—", left off the map, no crash.

---

### Task 1: Shared filter bounds (backend)

**Files:** Modify `backend/apps/reports/filters.py`; Test `backend/tests/test_report_filters.py`.

**Produces:** `parse_report_filters` raises `FilterError('Dates must be between 1900 and 2100.')` for a date outside 1900-01-01..2100-12-31, and `FilterError('The start date is in the future.')` when `date_from > localdate()` and no `date_to`.

- [ ] Tests `test_dates_are_bounded` (0202-01-01, 2101-01-01, 9999-12-31 → sentence), `test_future_start_without_end` → fail.
- [ ] Implement; run `bt.sh tests.test_report_filters tests.test_trends tests.test_analytics tests.test_report_views` → OK.

### Task 2: Pure statistics (backend)

**Files:** Create `backend/apps/reports/stats.py`; Test `backend/tests/test_report_stats.py` (SimpleTestCase).

**Produces:**
- `mann_kendall(values: list[int]) -> {'s': int, 'z': float, 'p': float}` (tie-corrected variance, continuity correction, two-sided p via `math.erfc`; n < 3 → s 0, z 0.0, p 1.0).
- `sens_slope(values) -> float` (median of pairwise slopes; n < 2 → 0.0).
- `trend_verdict(values, min_years=5) -> 'too_few_years' | 'increasing' | 'decreasing' | 'no_clear_trend'` (p < 0.05 and sign of slope).
- `unusual(count, baseline: list[int], min_baseline=3, min_count=3) -> bool` (count > mean + 2·sd (population sd), baseline ≥ 3 values, count ≥ 3).
- `recurrence(year_counts: list[int], min_years=3) -> 'too_few_years' | 'every_year' | 'most_years' | 'some_years' | 'latest_only' | 'none'` (most_years: ≥ 2/3 of years; latest_only: only the last year > 0).
- `change_vs_earlier(values) -> {'latest': int, 'earlier_mean': float | None, 'pct': int | None}` (pct None when earlier mean is 0 or no earlier years).

- [ ] Tests: `[1,2,3,4,5,6]` increasing p < 0.05; `[5,5,5,5,5]` no_clear_trend; `[3,1,4]` too_few_years; ties `[1,1,2,2,3,3]` S=12; sens `[1,3,5]` = 2.0; unusual(14,[5,6,7]) True, unusual(14,[5,6]) False, unusual(2,[0,0,0]) False; recurrence cases; change cases.
- [ ] Implement; run `bt.sh tests.test_report_stats` → OK.

### Task 3: Trends endpoint extensions (backend)

**Files:** Modify `backend/apps/reports/trends.py`; Test `backend/tests/test_trends.py`.

**Produces:** `GRANULARITIES = ('day','week','month','quarter','year')`; `bucket_start/key/label` for day (`2026-03-04`, `4 Mar 2026`) and week (ISO week Monday: `2026-W10`, `Week of 2 Mar 2026`); limits: day ≤ 92 buckets, week ≤ 105 buckets else 400 `'Too many periods: choose a longer step.'`; auto never picks day/week. Each series row gains `partial: bool` (bucket not fully inside [from, to]). Response gains `calendar: [{year, months: [12 ints], total}]` (years from range start to end), `month_average: [{hazard, years, months: [12 floats, 2 dp]}]` (years = complete-or-partial calendar years from the hazard's first record year in range to range end year), `weekday: [{day: 1..7 (Mon..Sun), label, counts, total}]`, `severity_by_year: [{year, counts: {Red, Orange, Green}}]`.

- [ ] Tests: `test_partial_buckets` (12-month default Dec 2025 – Nov 2026 by year → 2025 partial, 2026 partial), `test_day_and_week_steps`, `test_too_many_periods`, `test_calendar_and_weekday`, `test_month_average_per_year`, `test_severity_by_year`.
- [ ] Implement (`TruncDay`/`TruncWeek` via `Trunc(kind)`, `ExtractIsoWeekDay`, `ExtractYear` with `tzinfo=MANILA`); run `bt.sh tests.test_trends` → OK.

### Task 4: Patterns and places endpoints (backend)

**Files:** Create `backend/apps/reports/trend_patterns.py` (`PatternsView`, `PlacesView`); Modify `backend/apps/reports/urls.py` (`trends/patterns/`, `trends/places/`); Test `backend/tests/test_trend_patterns.py`.

**Produces:**
- `GET /api/reports/trends/patterns/` → `{range, filters, generated_at, generated_by, hazards: [{hazard, first, last, years: [{year, count}], complete_years, verdict, slope, p, change: {...}, so_far: {year, count, through} | null, sentence}], unusual_months: [{hazard, year, month, label, count, baseline_mean, baseline_min, baseline_max, baseline_years}]}`. Complete years: Jan–Dec fully inside [range from, range to] and ≤ last year ending before today; yearly series from max(hazard first year, range start year). `sentence` built only from those numbers. Logged `GENERATE_REPORT` "Trend patterns — criteria".
- `GET /api/reports/trends/places/` → `{range, filters, years: [int], barangays: [{id, name, area_km2 | null, total, per_km2 | null, years: [int per year], years_with_events, recurrence, change}], unspecified: {total}}`; all barangays listed (zeros included), hazard and date filters applied, barangay filter returned as `selected` only; area from `Area(Transform('boundary', 32651))`. Logged "Trend places — criteria".

- [ ] Tests: patterns verdict too_few_years with 3 years; increasing with 6 rising years; sentence never contains "increasing" when too_few_years; unusual month flagged; places zeros listed, per_km2, recurrence, no-boundary barangay density null; permissions; audit rows; bad filter 400.
- [ ] Implement; run `bt.sh tests.test_trend_patterns` → OK.

### Task 5: Summary endpoint, operations and printed keys (backend)

**Files:** Create `backend/apps/reports/summary.py` (`SummaryView`); Modify `urls.py` (`summary/`), `analytics.py` (`zones_by_status`), `views.py` (`REPORTS['models'] = 'Models and data'`, table for models `historical_record`); Test `backend/tests/test_report_summary.py`.

**Produces:** `GET /api/reports/summary/` → `{range, filters, generated_at, generated_by, holdings: {archive: [{hazard, records, first, last}], zones: {count, first}, alerts: {count, first}, notices: {count}, incident_reports: {count, first}, barangays, puroks}, events, impact: {deaths, injured, families_affected, persons_affected, structures_affected, damage_cost: {value, recorded_on, of}}, displaced: null, by_hazard: [{hazard, events, deaths, injured, families_affected, persons_affected, structures_affected, damage_cost}], by_barangay: [{id, name, events, ...same}], by_purok: [{id, name, events}] (barangay filter only), severity: [{severity, count}], fire: {property_category: [{label, count}], alarm_level: [...]} | null, flood_landslide: {subcategory: [...], cause: [...]} | null, completeness: [{key, label, count, of}]}`. Deaths = `fatalities` + sum of `fatal_*`; injured = `injured` + sum of `injured_*`; recorded_on = records where any of those fields is not null. Logged "Hazard Summary — N record(s). criteria".
`analytics/` adds `zones_by_status: {Active, Resolved, Archived, Retracted}` within the period.

- [ ] Tests: impact sums mixing fire cells and flood fields with recorded_on; holdings unfiltered; by_barangay Unspecified last; by_purok only with barangay; fire/flood blocks present only in scope; completeness; zones_by_status; printed models; permissions; audit.
- [ ] Implement; run all report test modules → OK.

### Task 6: Filters per module (frontend)

**Files:** Modify `frontend/src/pages/reportsAnalytics/filters.js`, `FilterBar.jsx`, `useReportFilters.js`, `frontend/src/api/reportApi.js`; Tests `filters.test.js`, `filterBar.test.js`.

**Produces:** `REPORT_PRESETS` (3m, 6m, 12m, year, 5y, all, custom; default 12m), `TREND_PRESETS` (all, 10y, 5y, 3y, year, custom; default all); `filtersFromParams(params, kind = 'reports')`, `filtersToParams(filters, base, kind)`, `defaultFilters(kind)`, `isDefault(filters, kind)`; `resolveRange` handles `Ny` (first day of the year N−1 years before). `useReportFilters(kind)`. `FilterBar` props `kind`, `mode: 'apply' | 'live'`: apply mode keeps a draft and shows **Apply** (disabled when unchanged or invalid) and calls `onChange(draft)` once; live mode sends presets/selects at once and dates on blur/Enter. `namesFor` falls back to `Unknown barangay (#id)`. API: `summary`, `trendPatterns`, `trendPlaces`.

- [ ] Tests first (presets per kind, round trip per kind, apply sends once, unchanged apply disabled, live date commits on blur only, unknown id wording); implement; run `ft.sh src/pages/reportsAnalytics` → PASS.

### Task 7: Reports & Analytics page (frontend)

**Files:** Rewrite `frontend/src/pages/ReportsAnalytics.jsx`; create `pages/reportsAnalytics/SummarySection.jsx`, `OperationsSection.jsx`, `ModelsSection.jsx`, `sectionExport.js` (`useSectionExport(report, csvFor)`), `summaryCsv.js`; reuse `ResponseBand`, `StatTile`, `BarangayActivity`, `CategoryBars`, `ExportMenu`, forecast components; delete `ReportsView.jsx`, `ReportDocument.jsx`, `reportTables.js` (move `withShares`/`formatShare` to `summaryCsv.js`) and their tests, `ResponseSection.jsx`, `ForecastsSection.jsx`, `TrendAnalysisView.jsx`, `HazardHistorySection.jsx` (moves to Trend), `views.js` (paths move to `pages/paths.js`).

**Produces:** sections tabs `summary | operations | models` in `?section=`; each section fetches once per applied-filter key (models: once), shows loading/empty/error, a print header, and its export (`hazard-summary`, `response-status`, `models`). `pages/paths.js`: `TRENDS_PATH='/app/trends'`, `MODELS_PATH='/app/reports?section=models'`, `legacyRedirect(search) -> string | null`.

- [ ] Tests first: section switching keeps filters; Apply → one request per open section; same filters → none; summary renders impact "recorded on N of M" and "Not recorded" displaced; export logs first with the answer's criteria, disabled while loading; `?tab=models` → models; `?view=trends`/`?tab=analytics` → `/app/trends` with filters.
- [ ] Implement; run `ft.sh src/pages` → PASS.

### Task 8: Trend Analysis page (frontend)

**Files:** Create `frontend/src/pages/TrendAnalysis.jsx`, `pages/trendAnalysis/{KeyChanges,OverTime,Seasons,Places,HazardMix,ComparePeriods}.jsx`, `trendAnalysis/CalendarHeatmap.jsx`, `trendAnalysis/PlacesMap.jsx` (react-leaflet GeoJSON, shaded by per_km2 in 5 navy steps, tooltip with name, count, density), `trendAnalysis/trendCsv.js` (moved), `trendAnalysis/useTrendData.js` (fetch `trends`, `patterns`, `places` for the filter key, stale guard); reuse `StackedBars`, `CategoryBars`, `SeasonalOutlook`.

**Produces:** sections with headings "Key changes", "Over time", "Seasons", "Places", "Hazard mix", "Compare periods"; partial buckets drawn lighter and labelled "(partial)"; rainfall note text: "GeoAlert keeps no rainfall record, so these months are not compared with rain."; export of all tables.

- [ ] Tests first: key changes sentence and no direction word under 5 years; unusual months list; partial label; calendar cells; places table and map fallback (no boundary → not drawn); compare differences; export criteria from answers.
- [ ] Implement; run `ft.sh src/pages` → PASS.

### Task 9: Navigation, routes, links, styles, verification

**Files:** Modify `App.jsx` (routes `/app/trends`, redirects), `PublicNavbar.jsx` (+ `TRENDS` entry for DRRMO/Admin) and test, `HistoricalData.jsx`, `DRRMODashboard.jsx`, `BarangayLikelihood.jsx` + `forecastFilters.test.js`, `pages/css/ReportsAnalytics.css` (+ `TrendAnalysis.css`), `docs/CODEBASE_GUIDE.md` links.

- [ ] Tests first (nav items, redirects); implement; full frontend suite, build, full backend suite, headless-Chrome walk-through (desktop and 375 px, print emulation) against the local sample DB.
