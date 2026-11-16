# Analytics redesign and the History split — design

Date: 2026-10-20
Status: draft for review
Branch: merge-scout

## Why

The Analytics tab (Reports › Analytics, `frontend/src/pages/Analytics.jsx`) works but
reads as a stack of equal-weight boxes, and an audit of the whole system on 2026-10-20
found it overlaps with History and with the Reports tab:

| What | Where it appears today | Same data? |
|---|---|---|
| "Likely next month" barangay table | DRRMO Dashboard (top 5), Analytics (top 5), History (full) | Same component, same endpoint |
| Hazard events per month | History "Events over time", Analytics "Recorded hazard events" | Same table (`HistoricalRecord`) |
| Events by type / severity / barangay | History (3 charts), Reports › Hazard Summary (same 3 charts, same filters) | Same table; History always counts sample data, Reports leaves it out by default, so the two can disagree |
| Zones by type / severity / barangay | Analytics | Mostly the same hazards: every resolved zone is archived as a `HistoricalRecord` |
| Seasonal 3-month outlook, Extreme share | History only | Analysis, not archive |
| The record list | History only | The archive |

Problems seen on the current tab (screenshots at 1366 px and 390 px, stub data):

1. The month-by-month tooltip says "N events" for every measure, and its table is headed
   "Label / Events".
2. The shaded fill under that line is always navy, whatever colour the line is.
3. The month-by-month card has two table toggles ("Show the figures", "Show the numbers")
   that show overlapping tables.
4. Narrowing the window after load (snap to half screen, rotate a tablet) leaves the four
   chart cards at 544 px inside a 390 px viewport: 170 px of sideways scroll. A fresh
   load at phone width is fine. Cause: grid items default to `min-width: auto`, so a
   Chart.js canvas holds its column open.
5. `tension: 0.25` smoothing can bend the line past the real monthly counts.
6. Tile labels are Title Case ("Active Zones Now") through `text-transform: capitalize`,
   against sentence case everywhere else.
7. Ten headline numbers carry the same weight; nothing leads.
8. Only one measure is visible at a time on the trend chart.
9. Severity is ordered by count, not Extreme → Moderate → Low.
10. Two tall all-navy top-10 barangay charts list barangays in different orders, so
    comparing one barangay's zones and reports means hunting across both.
11. The four series colours fail the dataviz validator (navy below the lightness band and
    chroma floor, teal below the chroma floor), and two collide with hazard colours shown
    on the same page: alert orange `#c2410c` beside Fire `#f4511e`.
12. Charts draw in Segoe UI; the page uses Atkinson Hyperlegible.

## Goals

- Each page has one job: **History** is the archive, **Reports** is official printable
  figures, **Analytics** is patterns and the outlook, **Dashboard** is today's work.
- Analytics leads with clear bands (Activity, Response), shows all four monthly trends at
  once, and carries the seasonal outlook and full barangay likelihood moved from History.
- One filter row scopes the whole Analytics tab: period and hazard type.
- Sample data follows one rule across Reports and Analytics: left out unless asked for.
- Fix problems 1–12 above.

## Non-goals

- Changing the Reports tab's layout, its two reports, or their endpoints. (The chart font
  change in `chartTheme.js` applies to every chart in the app, Reports included.)
- Changing who can see what: History and Reports stay DRRMO and Admin only.
- Changing the outlook or likelihood methods (`riskOutlook.js`, `apps/history/forecast.py`).
- Previous-period comparison on the tiles (considered, not chosen).
- A barangay filter on Analytics (the barangay table and likelihood table cover it).
- Dark mode (the app has none).
- Unifying the DRRMO Dashboard's `adm-metric` tiles with the `db-stat` tiles.
- Removing `/api/history/trends/` (see Noticed, separate).

## Decisions taken in review (2026-10-20)

| Question | Choice |
|---|---|
| Headline numbers | Two bands: Activity tiles with sparklines; Response with two meters and three median tiles |
| Month by month | Small multiples, 2×2 |
| Breakdowns | Compact type and severity charts plus one barangay activity table |
| History | Archive only; its analysis moves to Analytics |
| Analytics filters | Period + hazard type, in one row |
| Sample data in moved parts | Left out by default, checkbox to include |
| Zone or event breakdowns | Zones only (event breakdowns stay in Reports › Hazard Summary) |
| Small extras | One Export menu; amber sample-data notice; charts in the page font |

## Design

### 1. What each page does

**History (`/app/history`, `HistoricalData.jsx`)** becomes "Historical records":

- Keeps: hazard-type tabs, barangay and date filters, the sample-data note, the record
  list with its pager. Sample handling is unchanged (History is the archive and badges
  each sample row, as `utils/sampling.py` describes).
- The header reads "Historical records" with the sub line "Archived hazard events in
  Talisay City." and a link: "Trends and the seasonal outlook are in Reports › Analytics"
  to `/app/reports?tab=analytics`.
- The record count moves into the Records card heading ("188 records").
- Removed from the page: the three stat tiles, Seasonal risk outlook, Likelihood by
  barangay, Events over time, By hazard type, Most affected barangays, Severity
  distribution, and the `historyApi.trends` call.
- The sample note drops its last sentence ("Trends and the outlook below include them").

**DRRMO Dashboard**: the compact "Likely next month" card stays. Its "See every barangay
and month" link goes to `/app/reports?tab=analytics` instead of `/app/history`.

**Analytics**: section 2. **Reports tab**: unchanged.

### 2. Analytics, top to bottom

1. **Filter row** (one card, hidden in print):
   - Period: segmented `3 / 6 / 12 / 24 months` (as today).
   - Hazard: `<select>` with "All types" plus every type from `hazardsApi.types()`.
   - Right side: "Include sample data" checkbox (secondary styling), and an **Export**
     button opening a menu of Download CSV, Save as PDF, Print. Each item logs through
     `reportsApi.printed('analytics', criteria, via)` exactly as today, with `via` still
     `csv`, `pdf` or `print`. The menu closes on choice, outside click and Escape; the
     button carries `aria-expanded`.
   - Under the card, the period line: "Last 12 months, from November 2025 · Flood ·
     Generated by …, …". "· Flood" appears only when a type is picked.
   - When samples are included: an amber notice (`--db-medium-tint` background, heading
     ink text, not the red `db-error` style): "Includes sample data. These figures count
     seeded test rows, so they are not an official record."
2. **Activity** band, heading "Activity":
   - Five tiles: Active zones now (no sparkline: it is a right-now count), Zones
     published, Alerts issued, Incident reports, Recorded hazard events. Each of the last
     four has a sparkline of that measure across the window's months.
   - Hints as today: "N more withdrawn as errors", "N Extreme", "N still pending" /
     "none pending".
   - Labels in sentence case.
3. **Response** band, heading "Response", sub line as today:
   - Two meters, "Alert notices opened" (`read_rate`, caption "1,225 of 1,914 sent") and
     "Incident reports reviewed" (`review_rate`, caption "104 validated, 29 rejected").
   - Three tiles: median time to open an alert, to review a report, and a zone stayed
     active, using the existing `duration()` wording.
   - A null rate shows "—" with an empty track and the caption "None sent in this
     period" or "None submitted in this period".
4. **Month by month**:
   - A 2×2 grid of small line charts (one column below 640 px): Zones published, Alerts
     issued, Incident reports, Recorded hazard events. Each panel shows its title, its
     total for the window, and a 150 px line with its own y-scale.
   - One "Show the numbers" table under the grid, all four measures by month (as today).
     No per-panel table.
   - Tooltips name the measure: "Mar 2026: 5 zones", "1 alert", and so on.
5. **Seasonal outlook**, moved from History unchanged in content: confidence badge,
   3-month lookahead cards, watch list, the five bullet lines, the "statistical pattern,
   not a forecast" note and "How this is calculated".
   - Adds a summary line at the top for the two History tiles that move with it:
     "Extreme severity share: 19% · Outlook for {focus month}: Elevated" (the
     `redShare` and `focus` values `buildRiskOutlook` already returns).
   - Sub line: "From the whole archive for {all hazard types | Flood}. The period above
     does not apply."
   - Data: `historyApi.list({ hazard_type })` (the full list, as History fetches today),
     dropping `is_sample` rows unless samples are included, then `buildRiskOutlook`.
6. **Likelihood by barangay**: the full `BarangayLikelihood` (not compact), with its
   month picker. The hazard type comes from the filter row, not its own picker.
7. **Breakdowns**:
   - "Zones by hazard type" and "Zones by severity" side by side. Severity always lists
     Extreme, Moderate, Low in that order, zeros included; with no zones at all in the
     window both cards show "No zones in this period." instead. When one hazard type is
     picked, the by-type card is hidden and severity spans the row.
   - "Barangay activity" table: Barangay | Zones | Incident reports. Each count cell
     shows the number and a thin inline bar scaled to that column's largest value.
     Column headers are buttons that sort (with `aria-sort`); the default is zones, most
     first. The first 10 rows show, then a "Show all N barangays" toggle. Print shows
     every row. Empty: "No zones or incident reports in this period."

The tab's "Likely next month" compact card is removed (item 6 replaces it).

### 3. Backend

**`apps/reports/analytics.py`, `GET /api/reports/analytics/`**

- New query parameter `hazard_type` (a hazard type id). It filters zones (and the active
  count) by `hazard_type_id`, alerts by `hazard_zone__hazard_type_id` (notices follow
  alerts), incidents by `hazard_type_id`, and events by `hazard_type_id`.
- A non-numeric or unknown id falls back to all types, the way an unknown `months` falls
  back to 12. The response carries `hazard_type: {id, name}` or `null`, so the screen
  labels itself with what was actually counted.
- `zones_by_barangay` and `incidents_by_barangay` are replaced by `barangays`:
  `[{barangay, zones, incidents}]` for every barangay with at least one zone or incident
  in the window, ordered by zones, then incidents (both most first), then name. A
  missing barangay name reads "Unspecified".
- New pure helpers, unit tested: `hazard_type_param(raw)` (id or `None`) and
  `barangay_activity(zone_rows, incident_rows)` (the merge and ordering).
- The audit line names the type: "Analytics — last 12 month(s), Flood." Samples are noted
  as today.

**`apps/history/views.py`, `GET /api/history/forecast/`**

- New opt-in parameter `exclude_samples=true` drops `is_sample` records before both the
  forecast and the profile. Without it, behaviour is exactly as today, so the public map
  and the Dashboard card do not change. `basis.sample_records` then reports 0.
- A small helper, `drop_samples(events, exclude)`, unit tested.

No model or migration changes.

### 4. Frontend components and visual standard

New or changed pieces:

| File | Change |
|---|---|
| `pages/Analytics.jsx` | Container: filter row, data fetch, band layout. Smaller than today; sections move out |
| `components/Analytics/ActivityBand.jsx` | Activity tiles + sparklines |
| `components/Analytics/ResponseBand.jsx` | Meters + median tiles |
| `components/Analytics/MonthlyMultiples.jsx` | 2×2 small multiples + one table |
| `components/Analytics/BarangayActivity.jsx` | Sortable table with inline bars |
| `components/Analytics/barangaySort.js` | Pure sort helper for that table, unit tested |
| `components/Analytics/ExportMenu.jsx` | Export button and menu |
| `components/Forecast/SeasonalOutlook.jsx` | The outlook card body, moved from `HistoricalData.jsx` |
| `components/Charts/Sparkline.jsx` | Inline SVG, 2px navy line, end dot; a `<title>` gives low and high in words |
| `components/Charts/Meter.jsx` | Track and fill, `role="meter"` with `aria-valuenow/min/max` and a text label |
| `components/Charts/TrendLine.jsx` | `unit` prop for tooltips ({ one, many }); fill derived from `color`; `cubicInterpolationMode: 'monotone'`; `table` prop passed to ChartFrame |
| `components/Charts/ChartFrame.jsx` | `table` prop (default true) to leave out its own table |
| `components/Charts/CategoryBars.jsx` | `thin` prop (default false) for slimmer bars |
| `components/Charts/chartTheme.js` | Font family led by Atkinson Hyperlegible; charts redraw once `document.fonts.ready` resolves |
| `components/Forecast/BarangayLikelihood.jsx` | `hazardTypes` picker replaced by a controlled `hazard` prop (type name, '' = all) and an `excludeSamples` prop; History was the picker's only user |
| `utils/analyticsCsv.js` | `analyticsCsv()` moved out of `Analytics.jsx` so it can be tested |
| `pages/css/Analytics.css` | Bands, meters, multiples, table, notice, phone and print rules |
| `pages/HistoricalData.jsx` | Section 1 |
| `pages/Dashboard/DRRMODashboard.jsx` | One link target |

Visual rules:

- **Colour:** every Analytics line, sparkline and meter is navy (`INK.navy`). The
  four-colour `SERIES` palette is dropped: it failed the validator, two of its colours
  collided with hazard colours, and each panel's title already names it. Hazard and
  severity colours keep their reserved meaning in the breakdown charts only.
- **Marks:** 2px lines and points with a 2px surface ring, as `chartTheme` does today.
  Analytics' breakdown bars get thinner through a new `CategoryBars` prop (`thin`,
  `barPercentage` 0.6); the default, and so the Reports tab, is unchanged. Barangay
  inline bars are 6px tall,
  navy at 70% opacity, with the number beside them in body ink.
- **Type:** tile values stay in Bricolage Grotesque with proportional figures; table
  numbers use `tabular-nums`.
- **Layout:** grid children get `min-width: 0` (problem 4). Activity tiles: five across
  on desktop, two below 640 px. Meters stack below 640 px. Filter row items wrap without
  orphaning one segment button.
- **Busy state:** previous render held at reduced opacity on refetch, as today.

**CSV export** (`utils/analyticsCsv.js`): meta gains "Hazard type" (the name, or "All
types"). The two top-10 barangay sections become one "Barangay activity" section
(Barangay, Zones, Incident reports, every row). Severity rows in Extreme, Moderate, Low
order. The outlook and likelihood stay out of the CSV, as the likelihood is today.

**Print**: filter row and Export hidden; period line, notice and every table shown;
small multiples print 2×2; cards avoid page breaks inside.

## Error handling

- Analytics fetch fails: the existing card message (403 or general). The outlook and
  likelihood load separately and fail on their own: "The seasonal outlook could not be
  loaded right now." The rest of the tab still renders.
- Hazard types fail to load: the Hazard picker shows only "All types".
- An unknown `hazard_type` reaches the backend: counts fall back to all types, and the
  period line names no type (as for all types) because the response's `hazard_type` is
  `null`.
- A null median or rate shows "—", never 0.

## Testing

- **Backend** (`SimpleTestCase`, no database, run as
  `python manage.py test tests.test_analytics tests.test_forecast`):
  - `hazard_type_param`: "3" gives 3; "", "abc", None give None.
  - `barangay_activity`: union of both lists; a barangay in only one gets 0 for the
    other; ordering zones then incidents then name; None name becomes "Unspecified".
  - `drop_samples`: keeps everything when not excluding; drops `is_sample` rows when
    excluding.
- **Frontend** (Jest, `CI=true npm test -- --watchAll=false`):
  - `analyticsCsv`: hazard type meta row; the barangay section with every row; severity
    order.
  - The barangay sort helper: default order, sort by incidents, ties by name.
- **Existing tests** still pass: `csv.test.js` and the rest.

## Verification (before calling it done)

Screenshots with the stub-data script (scratchpad, not committed), compared before and
after:

- Analytics at 1366 px, all types, then with Flood picked (by-type card hidden, period
  line says Flood).
- Analytics at 390 px from a fresh load, and after resizing from 1366 px:
  `scrollWidth - innerWidth` is 0 in both.
- Analytics with print media emulated: no filter row, tables expanded, 2×2 multiples.
- History at 1366 px and 390 px: archive only, link to Analytics works.
- DRRMO Dashboard: the link opens the Analytics tab.
- Export: each of CSV, PDF and Print calls `/api/reports/printed/` with the right `via`
  before acting.

## Files touched

Backend: `apps/reports/analytics.py`, `apps/history/views.py`, `tests/test_analytics.py`,
`tests/test_forecast.py`.

Frontend: the table in section 4, plus `api/reportApi.js` (comment for the new
parameter) and new tests `utils/analyticsCsv.test.js` and
`components/Analytics/barangaySort.test.js`.

## Noticed, separate

- The admin password in `README.md` is rejected by the current database. The README is
  out of date or the account has changed.
- `/api/history/trends/` loses its only caller. It is left in place; removing it is a
  separate change.
- ESLint warns about a byte-order mark at the top of `src/App.jsx`,
  `src/api/hazardsApi.js` and `src/pages/HistoricalData.jsx` (all three already
  had it before this change).
