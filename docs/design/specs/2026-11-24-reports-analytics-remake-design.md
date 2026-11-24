# Reports & Analytics remake: design

Date: 2026-11-24. Module F7 (Reporting and Analytics), with F5's trend charts.
Status: approved in conversation; written up here before planning.

## Why

The team wants Reports and Analytics to feel like one purpose-built module for a
DRRMO office: one place to produce an official figure, and one place to see how
hazards behave over time. Today it is a page with three tabs whose Analytics tab
charts the system's own activity (zones, alerts, incident reports), which only
began on 9 November 2026, so its 3–24 month charts are almost empty, while the
archive that does hold years of hazard history (255 events, 2021–2026) is barely
charted. The remake makes the history the centre of the analysis, keeps every
existing capability, and redesigns the screens rather than relabelling them.

Users: DRRMO officers and System Administrators (the existing F7 permission).

## Goals

1. One main navigation item, **Reports & Analytics**, with exactly two views
   inside: **Reports** and **Trend Analysis** (the renamed Analytics).
2. Reports: structured, printable reports (Hazard Summary, Response Status) as
   figures and tables; CSV, Save as PDF and Print, each written to the audit log
   as today.
3. Trend Analysis: every chart and statistical view, organised so an officer can
   read historical patterns: trends by month, quarter or year; flood and landslide
   patterns; distribution across barangays; severity mix; this period against the
   previous one; response performance; the forecasts and model results that
   already exist.
4. One filter bar (period, hazard type, barangay) for both views, and every chart,
   table and report actually follows it, enforced by the backend.
5. Clear loading, empty and error states per section; responsive; printable.

## Non-goals

- New prediction models or new forecast logic (the existing forecast, likelihood
  and model-accuracy components are regrouped, not rewritten).
- Changes to the History page beyond its link to this module.
- New roles or permissions.

## Anti-goals (would make this a failure even if it works)

- Any number not counted from the database, any placeholder chart, or a chart of
  a field that is never recorded (`total_displaced` is null in every record).
- Two charts that say the same thing.
- Losing an existing feature, an audit entry, or an old link (`/app/analytics`,
  `?tab=analytics`, `?tab=models`).
- A Reports view that re-generates (and re-logs) on every filter change.

## What exists today (audit)

| Today | Where | Data | Goes to |
|---|---|---|---|
| Nav item "Reports" (DRRMO, Admin) | `PublicNavbar.jsx` | — | renamed **Reports & Analytics** |
| Page "Reporting and Analytics", tabs Reports / Analytics / Predictive models, `?tab=` in URL | `ReportingAnalytics.jsx` | — | rebuilt: two views, `?view=` |
| Hazard Summary report: totals, by type, by severity, affected barangays (bar charts), filters date/barangay/type | `Reports.jsx` → `GET /api/reports/hazard-summary/` | `HistoricalRecord` | Reports view, as tables |
| Response Status report: active/resolved/archived/withdrawn zones, alerts by severity, filters date/barangay | `Reports.jsx` → `GET /api/reports/response-status/` | `HazardZone`, `HazardAlert` | Reports view, as tables; gains hazard type |
| CSV / Save as PDF / Print, logged first (`POST /api/reports/printed/`) | `Reports.jsx`, `utils/csv.js` | — | kept for both reports and Trend Analysis |
| "Insufficient data" answer, 403 message, slow-generation notice (8 s) | `Reports.jsx` | — | kept |
| Analytics: activity tiles + sparklines, response meters + medians, month-by-month small multiples, zones by type, zones by severity, barangay activity table; window 3/6/12/24 months + hazard type | `Analytics.jsx`, `components/Analytics/*` → `GET /api/reports/analytics/` | zones, alerts, notifications, incident reports, records | Trend Analysis › Response (operational figures) |
| Seasons on record (next three months from every past year) | `Forecast/SeasonalOutlook.jsx` (`utils/riskOutlook.js`) | whole archive via `/api/history/` | Trend Analysis › Forecasts & models |
| Likelihood by barangay (fire model) | `Forecast/BarangayLikelihood.jsx` → `/api/history/forecast/` | model | Trend Analysis › Forecasts & models |
| Flood data readiness, model updates, model accuracy | `PredictiveModels.jsx` → `/api/history/forecast/readiness|updates|accuracy/` | model reports | Trend Analysis › Forecasts & models |

Data facts that shape the design (live database, 2026-11-24):

- `HistoricalRecord`: Fire 2023–2026 (221), Flood 2021, 2022, 2025, 2026 (24),
  Landslide 2021–2026 (10). Severity: Green 217, Red 25, Orange 13. All 22
  barangays appear. Casualties recorded on 20 records; displaced on none.
- Operational tables (zones, alerts, notifications, incident reports) start on
  2026-11-09: 11 zones, 11 alerts, 2 reports.

## Constraints

- Permission: `IsAuthenticated, IsDRRMOOfficer` (DRRMO and Admin) on every endpoint
  this module uses, as now. Route gate `System_Admin`, `DRRMO_Officer`.
- Audit: generating a report, loading analytics, and every print/PDF/CSV are
  logged today; keep that, and log Trend Analysis loads the same way analytics
  loads are logged (`GENERATE_REPORT`).
- Old links keep working: `/app/analytics` and `?tab=analytics` land on Trend
  Analysis; `?tab=models` lands on Trend Analysis' Forecasts & models section.
- Chart.js through the existing chart components (`components/Charts/*`), each
  with its figures as a table underneath (`ChartFrame`); colours from
  `chartTheme.js` (hazard and severity series); dashboard tokens from
  `Dashboard.css` (`--db-*`).
- Barangay rule: a record belongs to a barangay when filed under it or linked to
  one of its puroks (`apps/history/area.barangay_records`), as on the History
  page. Reports and Trend Analysis use the same rule, so the same filters give the
  same totals everywhere.
- Code must keep loading on Django 4.2 and 5.2 (team transition).

## Approaches considered

1. **Rebuild the screens and extend the backend** (chosen). New page and view
   components on the existing chart primitives; one new aggregate endpoint for the
   history (`/api/reports/trends/`); custom dates and barangay on the analytics
   endpoint; hazard type on Response Status; database aggregates in the reports.
   Trades a backend change for filters that genuinely apply everywhere and
   quarterly/yearly history the screens cannot compute well on their own.
2. **Frontend-only regroup.** Move today's components into two views and restyle.
   Rejected: the analytics endpoint has no custom dates or barangay, so a shared
   filter bar would silently not apply to half the charts, and multi-year history
   would mean downloading the whole archive into the browser.
3. **A dashboard framework or new chart library.** Rejected: Chart.js and the
   chart components already exist, tested and accessible; a second library adds
   weight for no new capability.

## Design

### Navigation and URL

- Nav item label **Reports & Analytics**, same route `/app/reports`, same roles.
- `?view=reports` (default) or `?view=trends`. `?tab=analytics` → trends;
  `?tab=models` → trends, scrolled to Forecasts & models. `/app/analytics` →
  `/app/reports?view=trends`.
- Filters also live in the URL (`period`, `from`, `to`, `hazard`, `barangay`), so
  a link or refresh reproduces the screen and both views share them.
- Inbound links updated: History page, DRRMO dashboard, BarangayLikelihood
  "more" link.

### Page layout

```
Reports & Analytics                              [ Reports | Trend Analysis ]
DRRMO figures and hazard trends for Talisay City
┌ Filters ──────────────────────────────────────────────────────────────────┐
│ Period: (3 mo)(6 mo)(12 mo)(This year)(5 yr)(All)(Custom ▾)  Hazard ▾  Brgy ▾ │
│ Showing: Nov 2025 – Nov 2026 · All hazards · All barangays     [Reset]       │
└────────────────────────────────────────────────────────────────────────────┘
(view content)
```

- Header with title, one-line description, and the view switch (segmented
  control, keyboard-accessible tabs).
- Sticky filter bar under it on wide screens; folds on phones. Period presets:
  last 3, 6, 12 months (default 12), this year, last 5 years, all records, custom
  (from/to dates; from after to is refused with a message). Hazard: all, Fire,
  Flood, Landslide (from `/api/hazards/types/`). Barangay: all or one (from
  `/api/barangays/`). A "Showing …" line states the resolved range and filters.

### Reports view

```
[ Hazard Summary ]  [ Response Status ]          ← report choice
Report built from the filters above.   [Generate report]
┌ GeoAlert Talisay · City DRRMO ─────────────────────────────────────────┐
│ HAZARD SUMMARY REPORT                       [CSV] [Save as PDF] [Print] │
│ Period · hazard · barangay · generated by · generated at                │
│ Key figures: occurrences | casualties | displaced: not recorded         │
│ Table: by hazard type (count, share)                                    │
│ Table: by severity (count, share)                                       │
│ Table: affected barangays (count, share), every barangay with any       │
│ Note: source and audit line                                             │
└─────────────────────────────────────────────────────────────────────────┘
```

- Two report choices, each with a one-line description. Generate is explicit (it
  is audit-logged); when the filters change after a report was generated, a line
  says the report on screen used the earlier filters and offers to regenerate.
- The report is a document: header block with office name, report title, the
  criteria in words, who generated it and when; key figures; tables with count and
  share of total; a footer note on sources. No charts (charts live in Trend
  Analysis).
- Hazard Summary: occurrences, casualties, displaced shown as "Not recorded"
  (the field is never filled), by hazard type, by severity (Extreme, Moderate,
  Low), affected barangays.
- Response Status: active, resolved, archived, withdrawn zones; total hazard
  events; alerts issued; alerts by severity; the existing note on withdrawn zones.
  Now also filtered by hazard type.
- CSV, Save as PDF, Print exactly as today (logged first, never blocked by a
  failed log). The print stylesheet prints only the report document.
- States: no report yet (what to do), generating, slow (after 8 s), not enough
  data (the endpoint's message), permission error, other error.

### Trend Analysis view

Three sections, each a titled band, in reading order. A section loads and fails
on its own.

**1. Hazard history** (from `/api/reports/trends/`, follows every filter)

- Key figures: events in the period; change against the previous period of the
  same length (count and per cent, or "no records in the previous period");
  casualties recorded; the busiest barangay; the most common hazard type. No
  comparison for "All records".
- Events over time: stacked columns by hazard type, with a Month / Quarter / Year
  switch (default: month up to 24 months, quarter up to 6 years, year beyond).
  Every bucket in the range is present, empty ones as zero.
- When hazards occur: events by calendar month (Jan–Dec) in the range, stacked by
  type: the flood and landslide season pattern.
- Severity mix: events by severity per hazard type (horizontal stacked bars).
- Barangays: every barangay with events in the range, ranked, with its count by
  type and its share; horizontal bars for the top ten, the full list in the table
  underneath.
- An availability line under the section: earliest and latest record per hazard
  type, so a sparse type (flood, landslide) is read as sparse, not as safe.

**2. Response** (from `/api/reports/analytics/`, follows period, hazard and barangay)

- Figures: zones published (and withdrawn), alerts issued (Extreme count),
  incident reports (pending), active zones now.
- Alert notices opened and incident reports reviewed (meters), median time to open
  an alert, to review a report, a zone stayed active.
- Barangay activity table (zones and reports per barangay).
- A line stating that the system's own records start on the date of the earliest
  one, so short ranges are expected to be thin. The month-by-month small multiples
  are dropped: with operational data since November 2026 they draw flat lines, and
  Events over time already carries the trend.

**3. Forecasts & models** (do not follow the period filter; labelled so)

- Seasons on record (`SeasonalOutlook`, follows the hazard filter as today).
- Likelihood by barangay (`BarangayLikelihood`).
- Flood data readiness, model updates, model accuracy (`FloodReadiness`,
  `ModelUpdates`, `ForecastAccuracy`), in a collapsible group, collapsed by
  default, since they are technical.

Export for Trend Analysis: CSV of section 1 and 2 figures, Save as PDF, Print,
logged first via `POST /api/reports/printed/` with `report: 'analytics'` as today.

### Backend

**New: `GET /api/reports/trends/`** (`IsAuthenticated, IsDRRMOOfficer`)

Parameters: `date_from`, `date_to` (ISO dates, both optional; `date_to`
inclusive to the end of the day, Manila time), `hazard_type` (id), `barangay`
(id), `granularity` (`month` | `quarter` | `year`, optional: chosen from the
range as above). Bad values are a 400 with a sentence, never a 500.

Response:

```json
{
  "range": {"from": "2025-12-01", "to": "2026-11-24", "granularity": "month",
            "all_records": false},
  "filters": {"hazard_type": {"id": 2, "name": "Flood"} | null,
              "barangay": {"id": 7, "name": "Lagtang"} | null},
  "generated_at": "...", "generated_by": "...",
  "totals": {"events": 41, "casualties": 3,
             "by_type": [{"hazard": "Fire", "count": 30}, ...],
             "previous": {"from": "...", "to": "...", "events": 37} | null},
  "series": [{"period": "2025-12", "label": "Dec 2025",
              "counts": {"Fire": 3, "Flood": 0, "Landslide": 0}, "total": 3}, ...],
  "month_of_year": [{"month": 1, "label": "Jan", "counts": {...}, "total": 2}, ...],
  "severity": [{"hazard": "Fire", "counts": {"Red": 2, "Orange": 1, "Green": 27}}, ...],
  "barangays": [{"id": 7, "name": "Lagtang", "total": 9,
                 "counts": {"Fire": 8, "Flood": 1}, "share": 0.22}, ...],
  "coverage": [{"hazard": "Flood", "first": "2021-...", "last": "2026-...",
                "records": 24}, ...]
}
```

Counted with database aggregates (`TruncMonth`/`TruncQuarter`/`TruncYear` in
Manila time, `Count`, `Sum`), zero-filled in Python. The barangay rule is
`barangay_records`. Logged as `GENERATE_REPORT` "Trend analysis — criteria".

Settled details (builder's calls, recorded here):
- Previous period: the window of the same number of days ending the day before
  `from`, filtered the same way. `null` when there is no `from` (all records).
- No `date_from`: the range starts at the earliest matching record (its month,
  quarter or year), `all_records: true`. No `date_to`: today (Manila).
- Granularity when not given: month if the range is 24 months or less, quarter if
  6 years or less, otherwise year.
- `month_of_year` always has 12 rows; `series` has every bucket from the range's
  first to its last.
- `POST /api/reports/printed/` keeps the `analytics` key for Trend Analysis
  exports; its audit wording becomes "Trend Analysis".

**Changed: `GET /api/reports/analytics/`**: also accepts `date_from`/`date_to`
(taking precedence over `months`) and `barangay`; `months` keeps working.
Barangay filters zones by `barangay`, incident reports by `barangay`, alerts by
their zone's barangay, records by `barangay_records`; "active zones now" follows
the hazard and barangay filters but not the dates. Response shape unchanged
plus `range` and `first_record` (the date the system's own operational records
begin, for the "thin data" line). Bad dates → 400.

**Changed: Hazard Summary and Response Status**: database aggregates instead of
Python loops (`Sum`, one `count()`); barangay via the shared rule (Hazard
Summary); Response Status accepts `hazard_type`; `total_displaced` returned as
`null` when no record in the selection has it; bad dates → 400 instead of 500.
Response shapes otherwise unchanged, so existing callers keep working.

Note on the shared barangay rule: a Hazard Summary for one barangay will now
also count records filed under a neighbouring barangay but linked to one of this
barangay's puroks, matching what the History page and the map already show for
that barangay. Totals for "all barangays" are unchanged.

### Accessibility, responsiveness, print

- Each chart has its figures in a table underneath (`ChartFrame`) and a heading
  that says what it counts. Colour is never the only carrier (values as text).
- Layout: two columns from 960 px, one below; filter bar wraps; tables scroll
  horizontally inside their card on phones.
- Print: only the active view; Reports prints the report document; Trend Analysis
  prints sections 1 and 2 with the "Show the figures" tables opened
  (`usePrintOpensDetails`).

## Testing

- Backend: unit tests for the trends endpoint (zero-filled buckets per
  granularity, Manila-time bucketing, previous-period range, barangay rule,
  hazard filter, 400s, permission, audit row); analytics with date range and
  barangay; reports with aggregates, hazard type on Response Status, displaced
  null, 400 on bad dates; existing tests kept passing.
- Frontend: view switch and URL (incl. legacy `?tab=` and `/app/analytics`);
  filter bar state ↔ URL ↔ request parameters; Reports explicit generate and
  stale-filter notice; report tables and exports logged first; Trend Analysis
  sections render real responses, empty and error states; granularity switch;
  nav label. Existing tests for components that stay are kept; tests for removed
  components are replaced.
- Manual: build, then run the page against a local copy and check every filter,
  both views, print preview, a phone-width viewport.

## Left to the builder

- Component and file names within `pages/` and `components/`, and how the
  filter state is shared (a small hook or context).
- Exact preset labels and the granularity thresholds' edge handling.
- The visual details within the dashboard tokens: spacing, the segmented control,
  the sticky filter bar's behaviour on small screens.
- Whether the Trend Analysis CSV is one file with sections (as today) or one per
  section.

## Calls made in the design (for review)

1. Reports carry no charts; all charts are in Trend Analysis, as requested.
2. Predictive models is no longer a tab; it is Trend Analysis' third section.
3. Month-by-month small multiples of operational counts are dropped (flat lines on
   two weeks of data; Events over time carries the trend).
4. Displaced is shown as "Not recorded", never as 0.
5. Default period is the last 12 months for both views.
6. Reports keep an explicit Generate (audit-logged); Trend Analysis follows the
   filters live.
