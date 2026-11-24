# Reports & Analytics Remake Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild F7 as one "Reports & Analytics" section with two views, Reports (printable report documents) and Trend Analysis (every chart, centred on the hazard history), sharing one filter bar the backend enforces.

**Architecture:** Backend: one shared filter parser for the report endpoints, a new aggregate endpoint `GET /api/reports/trends/` over `HistoricalRecord`, custom dates and barangay on `GET /api/reports/analytics/`, database aggregates in the two reports. Frontend: a new page shell with URL-held filters and view, a Reports view of document-style tables, and a Trend Analysis view of three sections built on the existing Chart.js components plus one new stacked-bar chart.

**Tech Stack:** Django 5.2 / DRF 3.18 (must also load on 4.2), PostgreSQL + PostGIS; React 18 (CRA), react-router 6, Chart.js 4 via react-chartjs-2; Jest with `react-dom/client` + `act` (no Testing Library).

**Spec:** `docs/design/specs/2026-11-24-reports-analytics-remake-design.md`

## Global Constraints

- Never commit (user rule). Each task ends with a test checkpoint instead of a commit.
- Permission on every endpoint used: `IsAuthenticated, IsDRRMOOfficer`. Route gate `["System_Admin", "DRRMO_Officer"]`.
- Nav label exactly `Reports & Analytics`; views exactly `Reports` and `Trend Analysis`; route `/app/reports`.
- Old links keep working: `/app/analytics` → `/app/reports?view=trends`; `?tab=analytics` → trends; `?tab=models` → trends with Forecasts & models opened.
- No number not counted from the database; `total_displaced` is never charted and is shown as "Not recorded" when null.
- Barangay rule: a record belongs to a barangay when filed under it or linked to one of its puroks (`apps.history.area.barangay_records`).
- Dates are Manila time (`Asia/Manila`); `date_to` is inclusive to the end of the day.
- Report generation, analytics/trends loads and every print/PDF/CSV stay audit-logged (`GENERATE_REPORT`, `PRINT_REPORT`, `EXPORT_REPORT`).
- Charts use `components/Charts/*` and colours from `chartTheme.js` (`hazardSeriesColor`, `severitySeriesColor`); every chart shows its figures as a table.
- Dashboard tokens from `pages/css/Dashboard.css` (`--db-*`).

## Review Focus

1. Custom range with the start after the end: the filter bar says so inline and sends no request; the backend answers 400 with a sentence if called anyway.
2. A stale URL naming a barangay or hazard type that no longer exists: a 400 "Unknown barangay." / "Unknown hazard type."; the page shows the message instead of crashing.
3. A range with no records at all: every section shows its own empty state; no `NaN%`, no division by zero; the comparison reads "No records in the previous period".
4. Records with no barangay or no hazard type: counted in totals and shown as "Unspecified", so table shares add up to 100%.
5. An event at 00:30 on 1 January, Manila time (16:30 UTC on 31 December): counted in January of the new year, inside a range starting 1 January and outside one ending 31 December.

---

### Task 1: Shared report filters (backend)

**Files:**
- Create: `backend/apps/reports/filters.py`
- Test: `backend/tests/test_report_filters.py`

**Interfaces:**
- Produces:
  - `class FilterError(ValueError)`: message is a sentence for the screen.
  - `@dataclass(frozen=True) class ReportFilters: date_from: date | None; date_to: date | None; hazard_type: HazardType | None; barangay: Barangay | None`
  - `parse_report_filters(params) -> ReportFilters` (params is a QueryDict or dict). Reads `date_from`, `date_to` (first 10 chars, `date.fromisoformat`, so `2026-01-31T23:59:59` still works), `hazard_type` and `barangay` (positive integer ids looked up in the database). Raises `FilterError` with exactly: `'date_from must be a date like 2026-01-31.'`, `'date_to must be a date like 2026-01-31.'`, `'The start date is after the end date.'`, `'hazard_type must be an id.'`, `'Unknown hazard type.'`, `'barangay must be an id.'`, `'Unknown barangay.'`.
  - `day_start(d: date) -> datetime` (aware, 00:00 Asia/Manila) and `day_end(d: date) -> datetime` (aware, 23:59:59.999999 Asia/Manila).
  - `filter_records(queryset, f: ReportFilters) -> QuerySet` for `HistoricalRecord`: `occurred_at__gte=day_start(date_from)`, `occurred_at__lte=day_end(date_to)`, `hazard_type=f.hazard_type`, and `id__in=barangay_records(f.barangay)`, each only when set.
  - `criteria_text(f: ReportFilters) -> str`: `'date_from=2026-01-01 date_to=2026-06-30 barangay=Lagtang hazard_type=Flood'`, with `-` for an unset date and `all` for an unset barangay or type (the format the reports already log).

- [ ] **Step 1: Write the failing tests** (`TestCase`, creating one Barangay, one HazardType and records as `tests/fire_setup.py` does):
  - `test_empty_params_mean_no_filters`: `parse_report_filters({}) == ReportFilters(None, None, None, None)`.
  - `test_date_to_with_a_time_is_read_as_its_day`: `parse_report_filters({'date_to': '2026-01-31T23:59:59'}).date_to == date(2026, 1, 31)`.
  - `test_bad_values_raise_sentences`: each bad input above raises `FilterError` with its exact message (`'2026-13-01'`, `'x'` for an id, `'99999'` for an unknown id, from `2026-02-01` to `2026-01-01`).
  - `test_day_bounds_are_manila`: `day_start(date(2026,1,1)).isoformat() == '2026-01-01T00:00:00+08:00'`; `day_end(date(2026,1,1))` ends `23:59:59.999999+08:00`.
  - `test_new_year_in_manila` (Review Focus 5): a record at `2025-12-31 16:30 UTC` is in `filter_records` for `date_from=2026-01-01`, and not for `date_to=2025-12-31`.
  - `test_barangay_rule_counts_linked_puroks`: a record filed under barangay B but linked to a purok of barangay A is matched by `barangay=A`.
- [ ] **Step 2: Run them to see them fail.** Run `python manage.py test tests.test_report_filters --noinput` (from `backend/`). Expected: ImportError for `apps.reports.filters`.
- [ ] **Step 3: Implement `apps/reports/filters.py`** with the interfaces above (`zoneinfo.ZoneInfo('Asia/Manila')` for the bounds).
- [ ] **Step 4: Run them to see them pass.** Same command. Expected: OK.
- [ ] **Step 5: Checkpoint (no commit).**

### Task 2: Trends endpoint (backend)

**Files:**
- Create: `backend/apps/reports/trends.py`
- Modify: `backend/apps/reports/urls.py` (add `path('trends/', TrendsView.as_view(), name='report-trends')`)
- Test: `backend/tests/test_trends.py`

**Interfaces:**
- Consumes: Task 1 (`parse_report_filters`, `FilterError`, `filter_records`, `criteria_text`, `day_start`, `day_end`).
- Produces:
  - `pick_granularity(start: date, end: date) -> str`: `'month'` when the range spans 24 months or fewer (counting the start and end months), `'quarter'` when 72 or fewer, else `'year'`.
  - `buckets(start: date, end: date, granularity: str) -> list[tuple[str, str]]`: every bucket from start's to end's, keys `'2026-03'` / `'2026-Q1'` / `'2026'`, labels `'Mar 2026'` / `'Q1 2026'` / `'2026'`.
  - `bucket_key(d: date, granularity: str) -> str`.
  - `previous_window(start: date, end: date) -> tuple[date, date]`: the same number of days, ending the day before `start`.
  - `TrendsView` at `GET /api/reports/trends/`: query `date_from`, `date_to`, `hazard_type`, `barangay`, `granularity` (`month|quarter|year`, else 400 `'granularity must be month, quarter or year.'`). Response exactly the spec's JSON (`range`, `filters`, `generated_at`, `generated_by`, `totals` with `by_type` and `previous`, `series`, `month_of_year`, `severity`, `barangays`, `coverage`). Records with no hazard type count under the key `'Unspecified'`; with no barangay, under `{"id": null, "name": "Unspecified"}`. Hazard order: Fire, Flood, Landslide, then others by name, `Unspecified` last. `barangays` sorted by total desc then name; with a barangay filter it holds that barangay alone. `share` is `total / totals.events` rounded to 3 places, `null` when there are no events. `coverage` ignores the date filters, honours hazard and barangay. Logged once: `log_event(request, 'GENERATE_REPORT', 'historical_record', '', f'Trend analysis — {criteria_text(f)}')`.
  - Counting: `TruncMonth`/`TruncQuarter`/`TruncYear('occurred_at', tzinfo=MANILA)` and `ExtractMonth('occurred_at', tzinfo=MANILA)` with `Count`; `Sum('total_casualties')` (0 when null); zero-filling in Python from `buckets()`.

- [ ] **Step 1: Write the failing tests:**
  - Pure (`SimpleTestCase`): `pick_granularity(date(2025,1,1), date(2026,12,31)) == 'month'`, `(date(2021,1,1), date(2026,12,31)) == 'quarter'`, `(date(2015,1,1), date(2026,12,31)) == 'year'`; `buckets(date(2025,11,5), date(2026,2,1), 'month')` keys `['2025-11','2025-12','2026-01','2026-02']`, labels start `'Nov 2025'`; `buckets(date(2025,8,1), date(2026,1,1), 'quarter')` keys `['2025-Q3','2025-Q4','2026-Q1']`; `previous_window(date(2026,1,1), date(2026,1,31)) == (date(2025,12,1), date(2025,12,31))`.
  - API (`TestCase`, an officer via `force_login`, records across two years, two types, two barangays, one with no barangay):
    - `test_series_is_zero_filled`: every month in the range appears; empty months have `total == 0` and a count for every hazard in play.
    - `test_previous_period_counts_the_window_before`: `totals.previous.events` equals the records in `previous_window`; `null` when `date_from` is absent.
    - `test_shares_include_unspecified` (Review Focus 4): the `Unspecified` barangay row is present and the shares sum to 1.0 (±0.002).
    - `test_empty_range` (Review Focus 3): a range with no records gives `events == 0`, every share `null`, `series` zero-filled, 200.
    - `test_bad_input_is_a_400_with_a_sentence` (Review Focus 1, 2): from after to, unknown barangay, `granularity=week`, each a 400 whose body `error` is the sentence.
    - `test_month_of_year_has_twelve_rows` and `test_coverage_ignores_dates`.
    - `test_buckets_in_manila_time` (Review Focus 5): a record at `2025-12-31 16:30 UTC` lands in the `'2026-01'` series bucket and in `month_of_year` month 1.
    - `test_hazard_and_barangay_filters`: `hazard_type` narrows every block except `coverage` rows for other types; `barangay` counts a record linked by purok to that barangay, and `barangays` holds that barangay alone.
    - `test_only_drrmo_and_admin`: Barangay personnel and BFP get 403; anonymous 403.
    - `test_load_is_audited`: one `AuditLog` row, action `GENERATE_REPORT`, details starting `'Trend analysis — '`.
- [ ] **Step 2: Run them to see them fail.** `python manage.py test tests.test_trends --noinput`. Expected: ImportError / 404.
- [ ] **Step 3: Implement `apps/reports/trends.py` and the URL.** A `FilterError` becomes `Response({'error': str(exc)}, status=400)`. Without `date_from`, the range starts at the earliest matching record (today when there is none) and `range.all_records` is `true`; without `date_to`, today (Manila).
- [ ] **Step 4: Run them to see them pass.** Same command. Expected: OK.
- [ ] **Step 5: Checkpoint (no commit).**

### Task 3: Analytics endpoint takes dates and a barangay (backend)

**Files:**
- Modify: `backend/apps/reports/analytics.py`
- Test: `backend/tests/test_analytics.py` (add a `TestCase` class; keep the existing tests)

**Interfaces:**
- Consumes: Task 1.
- Produces: `months_between(start: date, end: date) -> list[date]` (first day of every month from start's to end's). `AnalyticsView` behaviour: when `date_from`, `date_to` or both are given, the range is `(date_from or first_record or first day of this month, date_to or today)`, `starts = months_between(range)`, and `months` is ignored; otherwise the existing `months` window. `barangay` filters zones (`barangay`), alerts (`hazard_zone__barangay`), incident reports (`barangay`), records (`barangay_records`); `active_zones_now` follows hazard and barangay but not dates. Response adds `range: {"from", "to"}` and `first_record` (earliest date among `HazardZone.activated_at`, `HazardAlert.created_at`, `IncidentReport.submitted_at`, or `null`). Bad filters → 400 `{'error': sentence}`. Existing keys unchanged.

- [ ] **Step 1: Write the failing tests:** `test_months_between_spans_the_new_year`; `test_date_range_replaces_the_window` (`kpis.zones_published` counts only zones activated inside the dates); `test_barangay_filters_every_count` (zones, alerts, incidents, recorded events for one barangay only); `test_active_now_ignores_dates`; `test_range_and_first_record_in_response`; `test_bad_dates_are_a_400`; `test_months_still_works` (no dates, `months=3` → `len(monthly) == 3`).
- [ ] **Step 2: Run them to see them fail.** `python manage.py test tests.test_analytics --noinput`.
- [ ] **Step 3: Implement** the interfaces above in `analytics.py`, reusing `parse_report_filters` and `day_start`/`day_end`.
- [ ] **Step 4: Run them to see them pass.** Same command. Expected: OK, old tests included.
- [ ] **Step 5: Checkpoint (no commit).**

### Task 4: Hazard Summary and Response Status on the shared filters (backend)

**Files:**
- Modify: `backend/apps/reports/views.py` (`HazardSummaryReportView`, `ResponseStatusReportView`, `ReportPrintedView.REPORTS`)
- Test: `backend/tests/test_report_views.py` (new)

**Interfaces:**
- Consumes: Task 1.
- Produces (response shapes unchanged except where stated):
  - Hazard Summary: records via `filter_records`; `total_occurrences = count()` once; `total_casualties = Sum or 0`; `total_displaced = Sum` (stays `null` when no selected record has it); breakdowns as today; criteria via `criteria_text`. Bad filters → 400 `{'error': sentence}`.
  - Response Status: zones by `activated_at` and alerts by `created_at` within `day_start`/`day_end`; `barangay` filters zones (`barangay`) and alerts (`hazard_zone__barangay`); new `hazard_type` filters zones (`hazard_type`) and alerts (`hazard_zone__hazard_type`). Bad filters → 400.
  - `ReportPrintedView.REPORTS['analytics'] = 'Trend Analysis'`.

- [ ] **Step 1: Write the failing tests:** `test_summary_counts_with_aggregates` (totals equal a hand count); `test_displaced_is_null_when_never_recorded`; `test_summary_barangay_rule` (record linked by purok is counted); `test_response_status_filters_hazard_type`; `test_response_status_alerts_follow_barangay`; `test_bad_dates_are_a_400` (both endpoints, previously a 500); `test_no_data_answer_unchanged` (empty selection still 200 with the existing `error` sentence); `test_printed_analytics_says_trend_analysis` (audit details start `'Trend Analysis '`).
- [ ] **Step 2: Run them to see them fail.** `python manage.py test tests.test_report_views --noinput`.
- [ ] **Step 3: Implement** the changes in `views.py`.
- [ ] **Step 4: Run backend checks.** `python manage.py test tests.test_report_views tests.test_analytics tests.test_trends tests.test_report_filters --noinput` and `python manage.py makemigrations --check --dry-run`. Expected: OK; "No changes detected".
- [ ] **Step 5: Checkpoint (no commit).**

### Task 5: Filter model, URL hook and filter bar (frontend)

**Files:**
- Create: `frontend/src/pages/reportsAnalytics/filters.js` (pure, no React)
- Create: `frontend/src/pages/reportsAnalytics/useReportFilters.js`
- Create: `frontend/src/pages/reportsAnalytics/FilterBar.jsx`
- Modify: `frontend/src/api/reportApi.js` (add `trends: (params) => client.get('/api/reports/trends/', { params }).then((r) => r.data)`)
- Test: `frontend/src/pages/reportsAnalytics/filters.test.js`, `frontend/src/pages/reportsAnalytics/filterBar.test.js`

**Interfaces:**
- Produces:
  - `PRESETS = [{key:'3m',label:'3 months'},{key:'6m',label:'6 months'},{key:'12m',label:'12 months'},{key:'year',label:'This year'},{key:'5y',label:'5 years'},{key:'all',label:'All records'},{key:'custom',label:'Custom'}]`
  - `DEFAULT_FILTERS = { period: '12m', from: '', to: '', hazard: '', barangay: '' }`
  - `filtersFromParams(params: URLSearchParams) -> filters` (unknown period → `'12m'`; URL keys `period`, `from`, `to`, `hazard`, `barangay`).
  - `filtersToParams(filters, base: URLSearchParams) -> URLSearchParams`: keeps other keys (`view`), drops keys equal to the default, drops `from`/`to` unless `period === 'custom'`.
  - `resolveRange(filters, today: Date) -> { from: 'YYYY-MM-DD' | null, to: 'YYYY-MM-DD' }`: `Nm` → first day of the month N−1 months before today's month, to today; `year` → 1 January; `5y` → as `60m`; `all` → `from: null`; `custom` → `from || null`, `to || today`.
  - `rangeError(filters) -> string | null`: `'The start date is after the end date.'` when custom from > to.
  - `requestParams(filters, today) -> { date_from?, date_to, hazard_type?, barangay? }` (`date_from` omitted for `all`; `date_to` always sent).
  - `namesFor(filters, hazardTypes, barangays) -> { hazardName: string | null, barangayName: string | null }` (`null` for "all" or an id not in the lists).
  - `describeFilters(filters, { hazardName, barangayName }, today) -> string`, e.g. `'Dec 2025 – Nov 2026 · All hazards · All barangays'`, `'All records to Nov 2026 · Flood · Lagtang'`.
  - `criteriaText(filters, { hazardName, barangayName }, today) -> string`: the audit format the backend logs, `'date_from=2025-12-01 date_to=2026-11-24 barangay=Lagtang hazard_type=Flood'`, `-` for no start date, `all` for no barangay or type.
  - `useReportFilters() -> [filters, setFilters(patch), resetFilters()]` on `useSearchParams` (`replace: true` for filter changes).
  - `<FilterBar filters onChange onReset hazardTypes barangays today />`: preset chips (`aria-pressed`), date inputs only for `custom`, hazard and barangay selects, the `describeFilters` line, a Reset button when not default, the `rangeError` message (`role="alert"`).

- [ ] **Step 1: Write the failing tests** (`filters.test.js`, fixed `today = new Date(2026, 10, 24)`): `resolveRange({...DEFAULT_FILTERS}, today)` is `{from:'2025-12-01', to:'2026-11-24'}`; `'3m'` from `'2026-09-01'`; `'year'` from `'2026-01-01'`; `'all'` from `null`; round trip `filtersFromParams(filtersToParams(f, new URLSearchParams('view=trends')))` equals `f` and keeps `view`; defaults produce an empty query apart from `view`; `rangeError` for custom `2026-02-01`→`2026-01-01`; `requestParams` for `all` has no `date_from`; `describeFilters` and `criteriaText` strings above; `namesFor` with an unknown id gives `null`. (`filterBar.test.js`): clicking "6 months" calls `onChange({ period: '6m' })`; picking "Custom" shows two date inputs; a backwards custom range shows the alert text.
- [ ] **Step 2: Run them to see them fail.** `CI=true npm test -- --watchAll=false src/pages/reportsAnalytics` (from `frontend/`).
- [ ] **Step 3: Implement** the three files and the API method.
- [ ] **Step 4: Run them to see them pass.** Same command. Expected: PASS.
- [ ] **Step 5: Checkpoint (no commit).**

### Task 6: Stacked bar chart (frontend)

**Files:**
- Create: `frontend/src/components/Charts/StackedBars.jsx`
- Create: `frontend/src/components/Charts/stackedData.js` (pure)
- Test: `frontend/src/components/Charts/stackedData.test.js`

**Interfaces:**
- Produces:
  - `stackedData(rows: [{label, counts: {[series]: n}}], series: string[], colorFor: (name) => hex) -> { labels: string[], datasets: [{ label, data: number[], color }] }` (missing counts are 0).
  - `stackTable(labels, datasets) -> { head: string[], rows: (string|number)[][] }` with a Total column.
  - `<StackedBars labels datasets horizontal={false} height={280} valueHead="Events" empty="No records for these filters." />`: Chart.js `Bar` with `stacked: true` on both axes, legend shown (more than one series), tooltip lists each series and the total; `ChartFrame` with `table={false}` plus its own "Show the figures" table from `stackTable`; empty message when every value is 0.

- [ ] **Step 1: Write the failing test:** `stackedData([{label:'2025', counts:{Fire:2}}, {label:'2026', counts:{Fire:1, Flood:3}}], ['Fire','Flood'], () => '#000')` gives `labels ['2025','2026']`, Fire `[2,1]`, Flood `[0,3]`; `stackTable` rows `[['2025',2,0,2],['2026',1,3,4]]` and head `['', 'Fire', 'Flood', 'Total']`.
- [ ] **Step 2: Run it to see it fail.** `CI=true npm test -- --watchAll=false src/components/Charts/stackedData`.
- [ ] **Step 3: Implement** both files, following `TrendLine.jsx` (`BASE_OPTIONS`, `axisScales`, `TOOLTIP`).
- [ ] **Step 4: Run it to see it pass.**
- [ ] **Step 5: Checkpoint (no commit).**

### Task 7: Page shell, navigation and old links (frontend)

**Files:**
- Create: `frontend/src/pages/ReportsAnalytics.jsx`
- Modify: `frontend/src/App.jsx` (route `/app/reports` → `ReportsAnalytics`; `/app/analytics` → `<Navigate to="/app/reports?view=trends" replace />`)
- Modify: `frontend/src/components/Navbar/PublicNavbar.jsx` (`REPORTS.label = "Reports & Analytics"`; comment)
- Modify: `frontend/src/pages/HistoricalData.jsx:166`, `frontend/src/pages/Dashboard/DRRMODashboard.jsx:758`, `frontend/src/components/Forecast/BarangayLikelihood.jsx:154` (links → `/app/reports?view=trends`, words "Reports & Analytics › Trend Analysis")
- Delete: `frontend/src/pages/ReportingAnalytics.jsx`, `frontend/src/pages/reportingAnalyticsTabs.test.js`, `frontend/src/pages/css/ReportingAnalytics.css`
- Test: `frontend/src/pages/reportsAnalytics/page.test.js`; update `frontend/src/components/Navbar/PublicNavbar.test.js` if it names the label

**Interfaces:**
- Consumes: Task 5 (`useReportFilters`, `FilterBar`).
- Produces: `VIEWS = [{key:'reports', label:'Reports'}, {key:'trends', label:'Trend Analysis'}]`; `viewFromParams(params) -> { view: 'reports'|'trends', focus: 'models'|null }` (`view` param; legacy `tab=analytics` → trends; `tab=models` → trends + `focus:'models'`; anything else → reports); `export const TRENDS_PATH = '/app/reports?view=trends'`, used by the `/app/analytics` redirect in `App.jsx` and by the three inbound links. The page fixes `today` once on mount (`useState(() => new Date())`) and loads hazard types (`hazardsApi.types()`) and barangays (`barangaysApi.list()`) once and renders `<ReportsView filters today hazardTypes barangays />` and `<TrendAnalysisView filters today hazardTypes barangays focus />` (Tasks 8, 10), each mounted on first open and kept mounted (`hidden` when inactive), as the old page did. Header: `Reports & Analytics` and one sentence; view switch as `role="tablist"` tabs.

- [ ] **Step 1: Write the failing tests** (views stubbed with `jest.mock`): tabs read exactly `['Reports', 'Trend Analysis']`; `/app/reports` selects Reports; `?view=trends`, `?tab=analytics` and `?tab=models` select Trend Analysis and `?tab=models` passes `focus === 'models'`; `viewFromParams(new URL(TRENDS_PATH, 'http://x').searchParams).view === 'trends'` (the `/app/analytics` target); switching views keeps `period=6m` in the URL; the navbar shows `Reports & Analytics` for a DRRMO officer.
- [ ] **Step 2: Run them to see them fail.**
- [ ] **Step 3: Implement** the page, routes, label and links; delete the old shell and its test.
- [ ] **Step 4: Run them to see them pass.** `CI=true npm test -- --watchAll=false src/pages src/components/Navbar`.
- [ ] **Step 5: Checkpoint (no commit).**

### Task 8: Reports view (frontend)

**Files:**
- Create: `frontend/src/pages/reportsAnalytics/ReportsView.jsx`, `frontend/src/pages/reportsAnalytics/ReportDocument.jsx`, `frontend/src/pages/reportsAnalytics/reportTables.js` (pure)
- Delete: `frontend/src/pages/Reports.jsx`
- Test: `frontend/src/pages/reportsAnalytics/reportTables.test.js`, `frontend/src/pages/reportsAnalytics/reportsView.test.js`

**Interfaces:**
- Consumes: Task 5 (`requestParams`, `describeFilters`, `criteriaText`, `namesFor`, `rangeError`), `SEVERITY_LABEL` (`utils/severity.js`), `reportsApi.hazardSummary/responseStatus/printed`, `utils/csv.js` (`toCsv`, `downloadCsv`, `csvFilename`).
- Produces:
  - `REPORTS = [{key:'hazard-summary', label:'Hazard Summary', blurb}, {key:'response-status', label:'Response Status', blurb}]` (blurbs from `Reports.jsx`).
  - `withShares(rows, labelOf) -> [{ label, count, share }]` (`share` 0..1, `null` when the total is 0); `formatShare(share) -> '42%' | '—'`.
  - `reportCsv(type, report, criteriaWords) -> string` (moved from `Reports.jsx`; displaced cell `'Not recorded'` when `null`).
  - `<ReportDocument type report criteria onExport />`: header block ("GeoAlert Talisay · City DRRMO", title, `criteria`, generated by/at), key figures, tables (label, count, share), the existing withdrawn-zones note for Response Status, footer note, buttons Download CSV / Save as PDF / Print calling `onExport('csv'|'pdf'|'print')`.
  - `ReportsView({ filters, today, hazardTypes, barangays })`: report choice, explicit Generate (disabled while `rangeError`), the stale notice `'This report used the earlier filters. Generate it again to apply the new ones.'` when filters changed after generating, states as today (no report yet, generating, slow after 8000 ms, the endpoint's "insufficient data" sentence, 403 sentence, other error, a 400's `error` sentence shown as is), exports logged first via `reportsApi.printed(type, criteriaText(filters, namesFor(...), today), via)` (Task 5) and never blocked by a failed log. The criteria are those the report on screen was generated with, not the current filters.

- [ ] **Step 1: Write the failing tests:** `withShares([{n:'A',count:3},{n:'B',count:1}], r=>r.n)` shares `0.75`, `0.25`; all-zero → shares `null` and `formatShare(null) === '—'`; `reportCsv('hazard-summary', {...total_displaced:null})` contains `Total displaced,Not recorded`. View (API mocked): Generate calls `hazardSummary` with `requestParams` output; changing filters after a report shows the stale notice; Download CSV calls `printed('hazard-summary', …, 'csv')` before `downloadCsv`; a rejected `printed` still downloads; a 400 shows its `error` text.
- [ ] **Step 2: Run them to see them fail.**
- [ ] **Step 3: Implement** the three files; delete `Reports.jsx`.
- [ ] **Step 4: Run them to see them pass.**
- [ ] **Step 5: Checkpoint (no commit).**

### Task 9: Trend Analysis, Hazard history section (frontend)

**Files:**
- Create: `frontend/src/pages/reportsAnalytics/trendShapes.js` (pure), `frontend/src/pages/reportsAnalytics/HazardHistorySection.jsx`
- Test: `frontend/src/pages/reportsAnalytics/trendShapes.test.js`, `frontend/src/pages/reportsAnalytics/hazardHistory.test.js`

**Interfaces:**
- Consumes: Task 2's response, Task 5 (`requestParams`), Task 6 (`StackedBars`, `stackedData`), `CategoryBars`, `hazardSeriesColor`, `severitySeriesColor` (`components/Charts/chartTheme.js`), `SEVERITY_LABEL`, `SEVERITY_ORDER` (`utils/severity.js`).
- Produces:
  - `hazardsIn(trends) -> string[]` (Fire, Flood, Landslide, others, `Unspecified` last; only hazards with a count somewhere, or the filtered one).
  - `comparison(totals) -> { text, direction: 'up'|'down'|'same'|null }`: `'+4 (11%) vs the previous period'`, `'−3 (8%) vs the previous period'`, `'Same as the previous period'`, `'No records in the previous period'` (previous events 0), `null` when `previous` is null.
  - `headline(trends) -> { events, casualties, busiest: { name, total } | null, commonest: { hazard, count } | null }` (busiest skips `Unspecified`).
  - `HazardHistorySection({ filters, today, onData })`: calls `onData(trends | null)` after each load (for the export); fetches `reportsApi.trends({...requestParams(filters, today), ...(granularity !== 'auto' && { granularity })})`; granularity switch Auto/Month/Quarter/Year; key figures; "Events over time" (`StackedBars` vertical from `series`); "When hazards occur" (`StackedBars` from `month_of_year`); "Severity mix" (`StackedBars` horizontal: rows per hazard, series Extreme/Moderate/Low in that order with severity colours); "Barangays" (`CategoryBars` of the top ten totals, then a full table: barangay, a column per hazard, total, share); the coverage line `'Records on file: Fire 2023–2026 (221), Flood 2021–2026 (24), …'`. Own loading (`'Loading the hazard history…'`), empty (`'No hazard records for these filters.'`) and error (the 400 sentence, else `'The hazard history could not be loaded right now.'`) states. Refetches when filters or granularity change; ignores a stale response.

- [ ] **Step 1: Write the failing tests:** `comparison({events:41, previous:{events:37}})` → `'+4 (11%) vs the previous period'`, `direction 'up'`; previous 0 → `'No records in the previous period'`; previous null → `null`; `headline` picks the busiest named barangay over `Unspecified`. Section (API mocked with a fixture, charts mocked): shows the five key figures; switching to Year calls `trends` with `granularity: 'year'`; an empty response shows the empty sentence; a rejected call with `data.error` shows that sentence.
- [ ] **Step 2: Run them to see them fail.**
- [ ] **Step 3: Implement** both files.
- [ ] **Step 4: Run them to see them pass.**
- [ ] **Step 5: Checkpoint (no commit).**

### Task 10: Trend Analysis, Response and Forecasts sections, view and export (frontend)

**Files:**
- Create: `frontend/src/pages/reportsAnalytics/ResponseSection.jsx`, `frontend/src/pages/reportsAnalytics/ForecastsSection.jsx`, `frontend/src/pages/reportsAnalytics/TrendAnalysisView.jsx`, `frontend/src/utils/trendCsv.js`
- Delete: `frontend/src/pages/Analytics.jsx`, `frontend/src/pages/PredictiveModels.jsx`, `frontend/src/components/Analytics/ActivityBand.jsx`, `frontend/src/components/Analytics/MonthlyMultiples.jsx`, `frontend/src/utils/analyticsCsv.js`, `frontend/src/utils/analyticsCsv.test.js`, `frontend/src/pages/analyticsPanel.test.js`, `frontend/src/pages/predictiveModels.test.js`
- Modify: `frontend/src/components/Analytics/bands.test.js` (keep the ResponseBand tests only)
- Test: `frontend/src/utils/trendCsv.test.js`, `frontend/src/pages/reportsAnalytics/trendView.test.js`

**Interfaces:**
- Consumes: Task 3's response, Task 9, existing `ResponseBand`, `StatTile`, `BarangayActivity`, `ExportMenu`, `usePrintOpensDetails`, `SeasonalOutlook`, `BarangayLikelihood`, `FloodReadiness`, `ModelUpdates`, `ForecastAccuracy`.
- Produces:
  - `ResponseSection({ filters, today, onData })`: fetches `reportsApi.analytics(requestParams(filters, today))`; tiles (`StatTile`): zones published (hint withdrawn), alerts issued (hint Extreme), incident reports (hint pending), active zones now; `ResponseBand`; zones by hazard type and zones by severity (`CategoryBars` from `zones_by_type`/`zones_by_severity`, kept from today's Analytics tab since the spec drops only the monthly multiples); `BarangayActivity`; the line `'GeoAlert's own records begin on <first_record>, so short ranges here are expected to be thin.'` when `first_record` is set; own loading/empty/error states; calls `onData(data)` for the export.
  - `ForecastsSection({ hazardTypeId, hazardName, open })`: the note `'These use every past year and the trained models, not the period above.'`; `SeasonalOutlook`, `BarangayLikelihood`; a `<details>` "Model accuracy and data readiness" holding `FloodReadiness`, `ModelUpdates`, `ForecastAccuracy`, open when `open`; `id="forecasts"`, scrolled into view when `open`.
  - `TrendAnalysisView({ filters, today, hazardTypes, barangays, focus })`: the three sections in order with headings "Hazard history", "Response", "Forecasts & models"; `usePrintOpensDetails(bodyRef)` on the view body, and the Forecasts section marked to hide in print (print = sections 1 and 2); `ExportMenu` that logs `reportsApi.printed('analytics', criteriaText(filters, namesFor(...), today), via)` first, then `downloadCsv(csvFilename('trend-analysis'), trendCsv(trends, analytics, criteriaWords))` or `window.print()`; `HazardHistorySection` also gets `onData` for the export.
  - `trendCsv(trends, analytics, criteriaWords) -> string`: sections Key figures, Events over time, When hazards occur, Severity mix, Barangays, Response; a section is left out when its data is missing.

- [ ] **Step 1: Write the failing tests:** `trendCsv(fixtureTrends, fixtureAnalytics, 'Dec 2025 – Nov 2026')` has the six section titles and a row `Lagtang,…`; with `analytics` null it has no Response section. View (sections' APIs mocked): headings in order; `focus='models'` opens the details; export CSV logs `printed('analytics', …, 'csv')` before downloading; the Response section's thin-data line names `first_record`.
- [ ] **Step 2: Run them to see them fail.**
- [ ] **Step 3: Implement** the four files; delete the obsolete ones; trim `bands.test.js`.
- [ ] **Step 4: Run the whole frontend suite.** `CI=true npm test -- --watchAll=false`. Expected: all suites pass (no reference to a deleted file left).
- [ ] **Step 5: Checkpoint (no commit).**

### Task 11: Styles, responsiveness, print, and end-to-end check

**Files:**
- Create: `frontend/src/pages/css/ReportsAnalytics.css` (imported by `ReportsAnalytics.jsx`; carries the `an-*` rules still used by `ResponseBand`, `StatTile`, `BarangayActivity`, `ExportMenu` from the old `Analytics.css`)
- Delete: `frontend/src/pages/css/Analytics.css`

**Interfaces:**
- Consumes: every component above. Class prefix `ra-` for new rules; tokens `--db-*` only.

- [ ] **Step 1: Style** the header and view switch, the sticky filter bar (static below 760 px), the report document (print shows only `.ra-report-doc`), the three Trend Analysis bands (two columns from 960 px, one below; tables scroll inside their card), the loading/empty/error blocks.
- [ ] **Step 2: Build.** `CI=true npm run build` (from `frontend/`). Expected: "Compiled successfully." (a warning fails the build).
- [ ] **Step 3: Full test runs.** Frontend `CI=true npm test -- --watchAll=false`; backend `python manage.py test tests apps --noinput`. Expected: all pass.
- [ ] **Step 4: Manual check against a local copy** (local PostGIS with the scrubbed data from `deploy/make_dev_database.py`, `runserver` + `npm start`): every preset and a custom range; each hazard; one barangay; both reports generated, CSV opened, print preview showing only the report; Trend Analysis granularity switch; `?tab=models` lands open; a 375 px wide viewport; `/app/analytics` redirects.
- [ ] **Step 5: Checkpoint (no commit).** Report results to the user; leave everything uncommitted.
