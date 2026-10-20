# Analytics Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild Reports › Analytics as banded, filterable analysis (Activity, Response, small multiples, seasonal outlook, barangay likelihood, breakdowns) and trim History to the record archive.

**Architecture:** The analytics endpoint gains a hazard-type filter and one merged barangay list; the forecast endpoint gains an opt-in sample exclusion. On the frontend, `Analytics.jsx` becomes a thin container (filters, fetch, layout) over small section components in `components/Analytics/`, two new chart primitives (Sparkline, Meter), and the outlook card moved out of `HistoricalData.jsx` into `components/Forecast/`. Pure helpers live in modules that do not import Chart.js so Jest can test them.

**Tech Stack:** Django 4.2 + DRF (Python 3.11.9 venv); React 18, react-chartjs-2 5 / Chart.js 4, Jest via react-scripts 5.0.1.

**Spec:** `docs/superpowers/specs/2026-10-20-analytics-redesign-design.md`

## Global Constraints

- No new frontend or backend dependencies. No model or migration changes.
- Backend tests: from `backend/`, `venv/Scripts/python.exe manage.py test tests.test_analytics tests.test_forecast`. `SimpleTestCase` only (any `TestCase` would create a test database on the team's shared Supabase server).
- Frontend tests: from `frontend/`, `CI=true npx react-scripts test --watchAll=false <file>`. Component tests use `createRoot` + `act` from `react`, the style of `src/components/Publish/PublishHazardPanel.spot.test.js`.
- Unit-tested helpers must not import `components/Charts/chartTheme.js` (it imports Chart.js).
- Analytics lines, sparklines and meters are navy only (`INK.navy` / `var(--db-navy)`). The `SERIES` colour list in `Analytics.jsx` is deleted. Hazard and severity colours appear only in the two breakdown charts.
- Severity order everywhere on Analytics and in its CSV: `Red` (Extreme), `Orange` (Moderate), `Green` (Low).
- Sample data: Analytics sends `include_samples: 'true'` only when the box is ticked; the forecast gets `exclude_samples: 'true'` unless ticked; the outlook drops `is_sample` records unless ticked. History, the public map and the Dashboard keep today's behaviour.
- Export logging is unchanged: `reportsApi.printed('analytics', criteria, via)` before acting, `via` ∈ `csv | pdf | print`, failures ignored.
- Copy, verbatim:
  - Sample notice: `Includes sample data. These figures count seeded test rows, so they are not an official record.` ("Includes sample data." in `<strong>`)
  - Outlook sub line: `From the whole archive for {all hazard types | <Type>}. The period above does not apply.`
  - Outlook error: `The seasonal outlook could not be loaded right now.`
  - Barangay table empty: `No zones or incident reports in this period.`
  - Zone breakdown empty: `No zones in this period.`
  - Null meter captions: `None sent in this period` (read rate), `None submitted in this period` (review rate)
  - History header `Historical records`; sub `Archived hazard events in Talisay City.`; link text `Trends and the seasonal outlook are in Reports › Analytics` → `/app/reports?tab=analytics`
- Dev servers are already running (frontend :3000, backend :8000) and reload on save.
- Commit on branch `merge-scout`; messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. **The user deferred committing the spec; ask before the first commit** and include the spec and this plan in it if they agree.

## Review Focus

1. Changing the hazard type (or period) twice quickly: the later choice wins everywhere, and a slow earlier response never overwrites it. Each fetching effect keeps a `live`/`cancelled` guard; pinned by a check in Task 11.
2. A hazard type with no activity at all: every section shows its empty state, rates show "—" with empty meters, no `NaN`/`Infinity`. Pinned in Task 4 (`meterPercent`) and Task 11 (stub with an all-zero payload).
3. Printing while the barangay table shows only 10 rows: every row prints. Pinned in Task 6 (rows past 10 carry `ba-more`, and only `.ba-table:not(.is-expanded) .ba-more` is hidden on screen) and checked in Task 11.
4. Export pressed while a refetch is in flight: Export is disabled while busy, so a CSV never mixes old figures with new filters. Pinned in Task 7 (`disabled` test).
5. The window narrowed after load: no sideways scroll. Pinned in Task 10 (`min-width: 0` rule) and checked in Task 11.

---

### Task 1: Analytics endpoint — hazard filter and barangay activity

**Files:**
- Modify: `backend/apps/reports/analytics.py`
- Test: `backend/tests/test_analytics.py`

**Interfaces:**
- Produces: `GET /api/reports/analytics/?months=&hazard_type=&include_samples=` response gains `hazard_type: {id: int, name: str} | null` and `barangays: [{barangay: str, zones: int, incidents: int}]`; `zones_by_barangay` and `incidents_by_barangay` are removed. Other keys unchanged.
- Produces: `hazard_type_param(raw) -> int | None`, `barangay_activity(zone_rows, incident_rows) -> list[dict]` (rows are `{'barangay__name': str | None, 'count': int}`).

- [ ] **Step 1: Write the failing tests** (append to `tests/test_analytics.py`, import the two helpers)

```python
class HazardTypeParamTests(SimpleTestCase):
    def test_reads_a_positive_id(self):
        self.assertEqual(hazard_type_param('3'), 3)

    def test_anything_else_means_all_types(self):
        for raw in (None, '', 'abc', '0', '-2', '3.5'):
            self.assertIsNone(hazard_type_param(raw), raw)


class BarangayActivityTests(SimpleTestCase):
    def test_joins_both_lists_with_zero_for_the_missing_side(self):
        rows = barangay_activity(
            [{'barangay__name': 'Tabunok', 'count': 4}],
            [{'barangay__name': 'Bulacao', 'count': 9}, {'barangay__name': 'Tabunok', 'count': 2}],
        )
        self.assertEqual(rows, [
            {'barangay': 'Tabunok', 'zones': 4, 'incidents': 2},
            {'barangay': 'Bulacao', 'zones': 0, 'incidents': 9},
        ])

    def test_orders_by_zones_then_incidents_then_name(self):
        rows = barangay_activity(
            [{'barangay__name': n, 'count': 1} for n in ('Pooc', 'Linao', 'Dumlog')],
            [{'barangay__name': 'Pooc', 'count': 3}],
        )
        self.assertEqual([r['barangay'] for r in rows], ['Pooc', 'Dumlog', 'Linao'])

    def test_missing_name_reads_unspecified(self):
        self.assertEqual(barangay_activity([{'barangay__name': None, 'count': 2}], [])[0]['barangay'], 'Unspecified')
```

- [ ] **Step 2: Run to verify they fail**

Run: `venv/Scripts/python.exe manage.py test tests.test_analytics`
Expected: ImportError for `hazard_type_param`.

- [ ] **Step 3: Implement the helpers in `apps/reports/analytics.py`**

`hazard_type_param`: `int(raw)` when `raw` is a string of digits and the value is > 0, else `None`. `barangay_activity`: merge by name (None → 'Unspecified'), sort key `(-zones, -incidents, barangay)`.

- [ ] **Step 4: Run to verify they pass**

Run: `venv/Scripts/python.exe manage.py test tests.test_analytics`
Expected: all pass.

- [ ] **Step 5: Wire the view (`AnalyticsView.get`)**

- `type_id = hazard_type_param(request.query_params.get('hazard_type'))`; `htype = HazardType.objects.filter(pk=type_id).first() if type_id else None` (import from `apps.hazards.models`).
- When `htype`: filter `zones_all` and `zones` by `hazard_type=htype`, `alerts` by `hazard_zone__hazard_type=htype`, `incidents` by `hazard_type=htype`, `events` by `hazard_type=htype`. Notices already follow `alerts`.
- Response: `'hazard_type': {'id': htype.id, 'name': htype.name} if htype else None`; replace the two barangay keys with `'barangays': barangay_activity(<published by barangay, no slice>, <incidents by barangay, no slice>)`.
- Audit detail: `f'Analytics — last {months} month(s){f", {htype.name}" if htype else ""}.'` followed by the existing samples suffix.
- Update the class docstring to list `hazard_type`.

- [ ] **Step 6: Smoke the endpoint shape without auth**

Run: `curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:8000/api/reports/analytics/?hazard_type=abc"`
Expected: `403` (still permission-gated; no 500 from the new parameter). Full shape is checked in Task 11.

- [ ] **Step 7: Commit** (after the user okays committing)

```bash
git add backend/apps/reports/analytics.py backend/tests/test_analytics.py
git commit -m "analytics: filter by hazard type and list barangay activity"
```

---

### Task 2: Forecast endpoint — opt-in sample exclusion

**Files:**
- Modify: `backend/apps/history/forecast.py` (new helper), `backend/apps/history/views.py` (`HistoricalForecastView.get`)
- Test: `backend/tests/test_forecast.py`

**Interfaces:**
- Produces: `drop_samples(events: list[dict], exclude: bool) -> list[dict]` in `apps/history/forecast.py`.
- Produces: `GET /api/history/forecast/?exclude_samples=true` drops `is_sample` events before both the forecast and the profile. Absent or any other value: unchanged behaviour.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_forecast.py`)

```python
class DropSamplesTests(SimpleTestCase):
    events = [{'barangay': 'A', 'is_sample': True}, {'barangay': 'B', 'is_sample': False}]

    def test_keeps_everything_unless_asked(self):
        self.assertEqual(drop_samples(self.events, False), self.events)

    def test_drops_sample_rows_when_asked(self):
        self.assertEqual(drop_samples(self.events, True), [{'barangay': 'B', 'is_sample': False}])
```

- [ ] **Step 2: Run to verify they fail**

Run: `venv/Scripts/python.exe manage.py test tests.test_forecast`
Expected: ImportError for `drop_samples`.

- [ ] **Step 3: Implement `drop_samples` and use it in the view**

In the view, after building `events`: `events = drop_samples(events, (request.query_params.get('exclude_samples') or '').strip().lower() in TRUTHY)` with `TRUTHY` imported from `utils.sampling`. Add `exclude_samples` to the view docstring.

- [ ] **Step 4: Run backend tests**

Run: `venv/Scripts/python.exe manage.py test tests.test_analytics tests.test_forecast`
Expected: all pass.

- [ ] **Step 5: Smoke both modes** (public endpoint, read-only)

Run (from `backend/`): `curl -s "http://127.0.0.1:8000/api/history/forecast/?month=11" | venv/Scripts/python.exe -c "import sys,json;print(json.load(sys.stdin)['basis']['sample_records'])"` then the same with `&exclude_samples=true`.
Expected: the first prints today's count (166 at the time of writing); the second prints `0`.

- [ ] **Step 6: Commit**

```bash
git add backend/apps/history/forecast.py backend/apps/history/views.py backend/tests/test_forecast.py
git commit -m "forecast: let a caller leave sample records out"
```

---

### Task 3: Chart fixes — units, fill, curve, table switch, thin bars, page font

**Files:**
- Create: `frontend/src/utils/color.js`, `frontend/src/utils/color.test.js`, `frontend/src/components/Charts/useFontsReady.js`
- Modify: `frontend/src/components/Charts/TrendLine.jsx`, `ChartFrame.jsx`, `CategoryBars.jsx`, `chartTheme.js`

**Interfaces:**
- Produces: `withAlpha(hex: string, alpha: number) -> string` ('#1c2e4a', 0.14 → 'rgba(28,46,74,0.14)'; 3-digit hex supported).
- Produces: `TrendLine({ points, height = 280, color = INK.navy, unit = { one: 'event', many: 'events' }, table = true, empty })`; tooltip body `` ` ${n} ${n === 1 ? unit.one : unit.many}` ``.
- Produces: `ChartFrame({ ..., table = true })`; `table={false}` renders the chart without its `<details>`.
- Produces: `CategoryBars({ ..., thin = false })`; `thin` sets `barPercentage: 0.6`.
- Produces: `useFontsReady() -> boolean` (true when `document.fonts` is missing or already loaded).

- [ ] **Step 1: Write the failing test** (`utils/color.test.js`)

```js
import { withAlpha } from './color';

test('six- and three-digit hex to rgba', () => {
  expect(withAlpha('#1c2e4a', 0.14)).toBe('rgba(28,46,74,0.14)');
  expect(withAlpha('#fff', 0)).toBe('rgba(255,255,255,0)');
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `CI=true npx react-scripts test --watchAll=false src/utils/color.test.js`
Expected: FAIL, cannot find module `./color`.

- [ ] **Step 3: Implement `withAlpha`, then the chart changes**

- `TrendLine`: gradient stops `withAlpha(color, 0.14)` → `withAlpha(color, 0)`; dataset `cubicInterpolationMode: 'monotone'`; `unit` and `table` props as above; add `unit` to the options memo's deps.
- `ChartFrame`: `table` prop; also `const fontsReady = useFontsReady();` and key the chart wrapper `key={fontsReady ? 'fonts' : 'fallback'}` so Chart.js redraws once web fonts load.
- `useFontsReady`: state from `document.fonts?.status === 'loaded'` (or true if `document.fonts` is undefined); effect `document.fonts.ready.then(() => setReady(true))` with an unmount guard.
- `CategoryBars`: `thin` prop.
- `chartTheme.js`: `FONT.family = "'Atkinson Hyperlegible', 'Segoe UI', system-ui, -apple-system, sans-serif"`.

- [ ] **Step 4: Run the frontend suite**

Run: `CI=true npx react-scripts test --watchAll=false`
Expected: all pass (existing suites plus `color.test.js`).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/utils/color.js frontend/src/utils/color.test.js frontend/src/components/Charts
git commit -m "charts: name the measure, tint the fill to the line, page font"
```

---

### Task 4: Sparkline and Meter

**Files:**
- Create: `frontend/src/components/Charts/Sparkline.jsx`, `frontend/src/components/Charts/Meter.jsx`, `frontend/src/components/Charts/sparkMeter.test.js`

**Interfaces:**
- Produces: `sparkPoints(values: number[], width: number, height: number, pad = 2) -> string` ("x,y x,y …", '' for fewer than 2 values; all-equal values draw a flat line at mid-height; each coordinate is `Number(n.toFixed(1))`, so whole numbers print without ".0").
- Produces: `sparkSummary(points: {label, value}[]) -> string`, e.g. `'lowest 2 in Jan 2026, highest 10 in Nov 2025'` (first occurrence on ties; '' for no points).
- Produces: `<Sparkline points={[{label, value}]} label="Zones published" width={120} height={32} />`: an `<svg>` with `<title>{label}: {sparkSummary}</title>`, a 2px `polyline` stroked `var(--db-navy)` and an end dot. Renders nothing for fewer than 2 points. No Chart.js.
- Produces: `meterPercent(value) -> number | null` (null/undefined/NaN → null; else `Math.round(value * 100)` clamped 0–100).
- Produces: `<Meter value={0.64} label="Alert notices opened" caption="1,225 of 1,914 sent" emptyCaption="None sent in this period" />`. With a number: `role="meter"`, `aria-valuemin=0`, `aria-valuemax=100`, `aria-valuenow`, `aria-valuetext="64%"`, big value "64%", filled track. With null: "—", empty track, `emptyCaption`, no `role="meter"`. Class names `an-meter`, `an-meter-track`, `an-meter-fill`.

- [ ] **Step 1: Write the failing tests** (`sparkMeter.test.js`)

```js
import { sparkPoints, sparkSummary } from './Sparkline';
import { meterPercent } from './Meter';

test('spark points span the box, top is the highest value', () => {
  expect(sparkPoints([0, 10], 100, 20, 0)).toBe('0,20 100,0');
  expect(sparkPoints([5], 100, 20)).toBe('');
});

test('a flat series sits at mid-height', () => {
  expect(sparkPoints([3, 3, 3], 100, 20, 0)).toBe('0,10 50,10 100,10');
});

test('summary names the low and high months', () => {
  const pts = [{ label: 'Nov 2025', value: 10 }, { label: 'Jan 2026', value: 2 }, { label: 'Feb 2026', value: 2 }];
  expect(sparkSummary(pts)).toBe('lowest 2 in Jan 2026, highest 10 in Nov 2025');
});

test('meter percent is null-safe and clamped', () => {
  expect(meterPercent(null)).toBeNull();
  expect(meterPercent(undefined)).toBeNull();
  expect(meterPercent(NaN)).toBeNull();
  expect(meterPercent(0.644)).toBe(64);
  expect(meterPercent(1.2)).toBe(100);
});
```

- [ ] **Step 2: Run to verify they fail**

Run: `CI=true npx react-scripts test --watchAll=false src/components/Charts/sparkMeter.test.js`
Expected: FAIL, cannot find modules.

- [ ] **Step 3: Implement both components and their helpers**

- [ ] **Step 4: Run to verify they pass**

Run: same command. Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/Charts/Sparkline.jsx frontend/src/components/Charts/Meter.jsx frontend/src/components/Charts/sparkMeter.test.js
git commit -m "charts: sparkline and meter"
```

---

### Task 5: Shared measures, severity order and the analytics CSV

**Files:**
- Create: `frontend/src/utils/severity.js`, `frontend/src/components/Analytics/measures.js`, `frontend/src/utils/analyticsCsv.js`, `frontend/src/utils/analyticsCsv.test.js`
- Modify: `frontend/src/components/Charts/chartTheme.js` (re-export `SEVERITY_LABEL`), `frontend/src/pages/Analytics.jsx` (import `analyticsCsv`, `duration`, `percent`, `monthLabel` from the new modules; delete the local copies)

**Interfaces:**
- Produces (`utils/severity.js`): `SEVERITY_LABEL = { Red: 'Extreme', Orange: 'Moderate', Green: 'Low' }`, `SEVERITY_ORDER = ['Red', 'Orange', 'Green']`, `inSeverityOrder(rows, key = 'severity') -> rows`: one row per code in `SEVERITY_ORDER` (count 0 when missing), then any unknown codes in their original order. `chartTheme.js` replaces its own definition with `export { SEVERITY_LABEL } from '../../utils/severity';`.
- Produces (`components/Analytics/measures.js`, no Chart.js): `MEASURES = [{ key: 'zones', label: 'Hazard zones published', unit: { one: 'zone', many: 'zones' } }, { key: 'alerts', label: 'Alerts issued', unit: { one: 'alert', many: 'alerts' } }, { key: 'incidents', label: 'Incident reports', unit: { one: 'report', many: 'reports' } }, { key: 'events', label: 'Recorded hazard events', unit: { one: 'event', many: 'events' } }]`, and `monthLabel`, `duration`, `percent` moved verbatim from `Analytics.jsx`.
- Produces (`utils/analyticsCsv.js`): `analyticsCsv(d) -> string`. As today's function, except: meta gains `['Hazard type', d.hazard_type?.name || 'All types']` after `Period`; the "By month" header uses `MEASURES` labels; "Zones by severity" uses `inSeverityOrder` with `SEVERITY_LABEL` names; the two top-10 barangay sections become one `Barangay activity` section, header `['Barangay', 'Zones', 'Incident reports']`, every row of `d.barangays`.

- [ ] **Step 1: Write the failing tests** (`utils/analyticsCsv.test.js`)

```js
import { analyticsCsv } from './analyticsCsv';
import { inSeverityOrder } from './severity';

const base = {
  months: 12, since: '2025-11-01', generated_at: '2026-10-20T08:00:00Z', generated_by: 'Officer',
  includes_samples: false, hazard_type: { id: 1, name: 'Flood' },
  kpis: {}, monthly: [{ month: '2026-10', zones: 1, alerts: 2, incidents: 3, events: 4 }],
  zones_by_type: [], zones_by_severity: [{ severity: 'Green', count: 2 }, { severity: 'Red', count: 1 }],
  barangays: [{ barangay: 'Tabunok', zones: 14, incidents: 28 }, { barangay: 'Pooc', zones: 0, incidents: 3 }],
};
const lines = (d) => analyticsCsv(d).split('\r\n');

test('names the hazard type, or all types', () => {
  expect(lines(base)).toContain('Hazard type,Flood');
  expect(lines({ ...base, hazard_type: null })).toContain('Hazard type,All types');
});

test('one barangay activity section with every row', () => {
  const l = lines(base);
  const at = l.indexOf('Barangay activity');
  expect(l.slice(at + 1, at + 4)).toEqual(['Barangay,Zones,Incident reports', 'Tabunok,14,28', 'Pooc,0,3']);
  expect(l.some((x) => x.includes('top 10'))).toBe(false);
});

test('severity rows run Extreme, Moderate, Low with zeros', () => {
  const l = lines(base);
  const at = l.indexOf('Zones by severity');
  expect(l.slice(at + 2, at + 5)).toEqual(['Extreme,1', 'Moderate,0', 'Low,2']);
});

test('inSeverityOrder keeps unknown codes at the end', () => {
  expect(inSeverityOrder([{ severity: 'Blue', count: 1 }]).map((r) => r.severity)).toEqual(['Red', 'Orange', 'Green', 'Blue']);
});
```

- [ ] **Step 2: Run to verify they fail**

Run: `CI=true npx react-scripts test --watchAll=false src/utils/analyticsCsv.test.js`
Expected: FAIL, cannot find modules.

- [ ] **Step 3: Implement the three modules and switch `Analytics.jsx` / `chartTheme.js` imports**

- [ ] **Step 4: Run the frontend suite**

Run: `CI=true npx react-scripts test --watchAll=false`
Expected: all pass. The dev server compiles without new warnings (check the `npm start` output).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/utils/severity.js frontend/src/utils/analyticsCsv.js frontend/src/utils/analyticsCsv.test.js frontend/src/components/Analytics/measures.js frontend/src/components/Charts/chartTheme.js frontend/src/pages/Analytics.jsx
git commit -m "analytics: CSV with hazard type, barangay activity and severity order"
```

---

### Task 6: Barangay activity table

**Files:**
- Create: `frontend/src/components/Analytics/barangaySort.js`, `frontend/src/components/Analytics/BarangayActivity.jsx`, `frontend/src/components/Analytics/barangayActivity.test.js`

**Interfaces:**
- Produces: `sortBarangays(rows, key: 'zones' | 'incidents') -> rows` (new array; key descending, then the other count descending, then name ascending).
- Produces: `<BarangayActivity rows={[{ barangay, zones, incidents }]} />`. Renders `table.db-table.ba-table` (plus `is-expanded` when expanded); `<th>` for Zones and Incident reports each hold a `<button>` and carry `aria-sort` (`descending` on the active column, `none` otherwise); default key `zones`. Each count cell: the number, then `span.ba-bar` with inline `width` as a % of that column's max (0 when the max is 0). Rows at index ≥ 10 get class `ba-more`. When `rows.length > 10`, a button below toggles between `Show all {n} barangays` and `Show top 10`. Empty `rows`: `<p className="db-empty">No zones or incident reports in this period.</p>`.

- [ ] **Step 1: Write the failing tests** (`barangayActivity.test.js`)

```js
import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import BarangayActivity from './BarangayActivity';
import { sortBarangays } from './barangaySort';

const rows = Array.from({ length: 12 }, (_, i) => ({ barangay: `B${String(i).padStart(2, '0')}`, zones: 12 - i, incidents: i }));

test('sorts by the chosen count, then the other, then name', () => {
  const r = [{ barangay: 'Linao', zones: 1, incidents: 0 }, { barangay: 'Dumlog', zones: 1, incidents: 0 }, { barangay: 'Pooc', zones: 1, incidents: 5 }];
  expect(sortBarangays(r, 'zones').map((x) => x.barangay)).toEqual(['Pooc', 'Dumlog', 'Linao']);
  expect(sortBarangays(r, 'incidents')[0].barangay).toBe('Pooc');
});

test('top 10 on screen, every row in the DOM for print, re-sorts on header click', () => {
  const el = document.createElement('div');
  act(() => { createRoot(el).render(<BarangayActivity rows={rows} />); });
  expect(el.querySelectorAll('tbody tr')).toHaveLength(12);
  expect(el.querySelectorAll('tbody tr.ba-more')).toHaveLength(2);
  expect(el.textContent).toContain('Show all 12 barangays');
  expect(el.querySelector('tbody tr td').textContent).toBe('B00');
  const incidents = [...el.querySelectorAll('th button')].find((b) => b.textContent.includes('Incident reports'));
  act(() => { incidents.click(); });
  expect(el.querySelector('tbody tr td').textContent).toBe('B11');
  expect(incidents.closest('th').getAttribute('aria-sort')).toBe('descending');
});

test('empty message when there are no rows', () => {
  const el = document.createElement('div');
  act(() => { createRoot(el).render(<BarangayActivity rows={[]} />); });
  expect(el.textContent).toBe('No zones or incident reports in this period.');
});
```

- [ ] **Step 2: Run to verify they fail**

Run: `CI=true npx react-scripts test --watchAll=false src/components/Analytics/barangayActivity.test.js`
Expected: FAIL, cannot find modules.

- [ ] **Step 3: Implement `sortBarangays` and `BarangayActivity`**

- [ ] **Step 4: Run to verify they pass**

Run: same command. Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/Analytics/barangaySort.js frontend/src/components/Analytics/BarangayActivity.jsx frontend/src/components/Analytics/barangayActivity.test.js
git commit -m "analytics: one sortable barangay activity table"
```

---

### Task 7: Export menu

**Files:**
- Create: `frontend/src/components/Analytics/ExportMenu.jsx`, `frontend/src/components/Analytics/exportMenu.test.js`

**Interfaces:**
- Produces: `<ExportMenu onExport={(via) => …} disabled={bool} />`. A `button.db-btn.db-btn-outline.db-btn-sm` "Export" with `aria-expanded`; when open, a list of three buttons: `Download CSV` (`'csv'`), `Save as PDF` (`'pdf'`, `title='Opens the print dialog. Choose "Save as PDF" as the printer.'`), `Print` (`'print'`). Choosing calls `onExport(via)` and closes. Escape and a `mousedown` outside close it. `disabled` disables the Export button and closes the menu. Wrapper has class `db-no-print`.

- [ ] **Step 1: Write the failing tests** (`exportMenu.test.js`)

```js
import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import ExportMenu from './ExportMenu';

function mount(props) {
  const el = document.createElement('div');
  document.body.appendChild(el);
  act(() => { createRoot(el).render(<ExportMenu onExport={() => {}} {...props} />); });
  return el;
}
const button = (el, text) => [...el.querySelectorAll('button')].find((b) => b.textContent === text);

test('opens, exports the chosen way, closes', () => {
  const onExport = jest.fn();
  const el = mount({ onExport });
  act(() => { button(el, 'Export').click(); });
  expect(button(el, 'Export').getAttribute('aria-expanded')).toBe('true');
  act(() => { button(el, 'Save as PDF').click(); });
  expect(onExport).toHaveBeenCalledWith('pdf');
  expect(button(el, 'Save as PDF')).toBeUndefined();
});

test('Escape closes the menu', () => {
  const el = mount({});
  act(() => { button(el, 'Export').click(); });
  act(() => { document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true })); });
  expect(button(el, 'Print')).toBeUndefined();
});

test('disabled while busy', () => {
  expect(button(mount({ disabled: true }), 'Export').disabled).toBe(true);
});
```

- [ ] **Step 2: Run to verify they fail**

Run: `CI=true npx react-scripts test --watchAll=false src/components/Analytics/exportMenu.test.js`
Expected: FAIL, cannot find module.

- [ ] **Step 3: Implement `ExportMenu`**

- [ ] **Step 4: Run to verify they pass**

Run: same command. Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/Analytics/ExportMenu.jsx frontend/src/components/Analytics/exportMenu.test.js
git commit -m "analytics: one Export menu for CSV, PDF and print"
```

---

### Task 8: Activity, Response and Month-by-month sections

**Files:**
- Create: `frontend/src/components/Analytics/ActivityBand.jsx`, `ResponseBand.jsx`, `MonthlyMultiples.jsx`

**Interfaces:**
- Consumes: `Sparkline`, `Meter` (Task 4); `TrendLine` with `unit`, `table`, `height` (Task 3); `MEASURES`, `monthLabel`, `duration` (Task 5).
- Produces: `<ActivityBand kpis={kpis} monthly={monthly} />`: `section.an-band` with `<h2>Activity</h2>` and `div.an-tiles` of five `db-stat` tiles (Active zones now; then one per `MEASURES` entry, using `zones_published`, `alerts_issued`, `incidents_submitted`, `recorded_events`). Hints exactly as today's tiles. The four measure tiles carry `<Sparkline points={monthly.map(m => ({ label: monthLabel(m.month), value: m[key] }))} label={measure.label} />`; Active zones now has none. Tile labels: "Active zones now", "Zones published", "Alerts issued", "Incident reports", "Recorded hazard events".
- Produces: `<ResponseBand kpis={kpis} />`: `section.an-band` with `<h2>Response</h2>`, today's sub line, two `Meter`s (`read_rate` with caption `` `${notices_read.toLocaleString()} of ${notices_sent.toLocaleString()} sent` ``; `review_rate` with caption `` `${incidents_validated} validated, ${incidents_rejected} rejected` ``; null captions from Global Constraints), and three tiles using `duration()` with today's wording ("to open an alert" / "from when it was sent", "to review a report" / "from submission to decision", "a zone stayed active" / "from publishing to resolved").
- Produces: `<MonthlyMultiples monthly={monthly} />`: `div.db-card` with `<h2>Month by month</h2>`, `div.an-multiples` of four `div.an-multiple` panels (each `<h3>{label}</h3>`, the window total, `<TrendLine points height={150} unit={measure.unit} table={false} />`), then today's single `<details className="an-table-wrap">` "Show the numbers" table with `MEASURES` columns.

- [ ] **Step 1: Implement the three components**

No new unit tests: their logic is the helpers already tested in Tasks 3–5; the layout is checked by screenshot in Task 11.

- [ ] **Step 2: Run the frontend suite**

Run: `CI=true npx react-scripts test --watchAll=false`
Expected: all pass.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/Analytics/ActivityBand.jsx frontend/src/components/Analytics/ResponseBand.jsx frontend/src/components/Analytics/MonthlyMultiples.jsx
git commit -m "analytics: activity and response bands, month-by-month small multiples"
```

---

### Task 9: Seasonal outlook card and the controlled likelihood table

**Files:**
- Create: `frontend/src/components/Forecast/SeasonalOutlook.jsx`
- Modify: `frontend/src/components/Forecast/BarangayLikelihood.jsx`

**Interfaces:**
- Produces: `<SeasonalOutlook hazardTypeId="" hazardName={null} includeSamples={false} />` (`hazardTypeId` is the id as a string, '' for all). Fetches `historyApi.list(hazardTypeId ? { hazard_type: hazardTypeId } : {})` with a `cancelled` guard, drops `is_sample` rows unless `includeSamples`, runs `buildRiskOutlook`. Renders `<h2>Seasonal outlook</h2>`, the outlook sub line (Global Constraints), the summary line `Extreme severity share: {redShare}% · Outlook for {focus.name}: {focus.level}`, then the content moved verbatim from `HistoricalData.jsx` (badge, `db-outlook-grid`, the five-item `db-outlook` list, the note, "How this is calculated"). No outlook: History's empty text. Fetch failure: the outlook error copy in `db-error`.
- Produces: `BarangayLikelihood({ compact = false, limit = 5, hazard = '', excludeSamples = false })`. The `hazardTypes` prop, its `<select>` and the internal `hazard` state are removed; `hazard` (a type name) and `exclude_samples: 'true'` (when `excludeSamples`) go into the `historyApi.forecast` params; both join the effect's deps. Dashboard usage (`compact limit={5}`) is unchanged.

- [ ] **Step 1: Implement both changes**

The outlook JSX moves rather than being rewritten; `HistoricalData.jsx` still has its copy until Task 10.

- [ ] **Step 2: Run the frontend suite**

Run: `CI=true npx react-scripts test --watchAll=false`
Expected: all pass. The dev server compiles; History still renders (its `hazardTypes` prop is now ignored until Task 10).

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/Forecast/SeasonalOutlook.jsx frontend/src/components/Forecast/BarangayLikelihood.jsx
git commit -m "forecast: outlook card component; likelihood takes its hazard from outside"
```

---

### Task 10: Assemble Analytics; trim History; repoint the Dashboard link

**Files:**
- Modify: `frontend/src/pages/Analytics.jsx`, `frontend/src/pages/css/Analytics.css`, `frontend/src/pages/HistoricalData.jsx`, `frontend/src/pages/Dashboard/DRRMODashboard.jsx:440`, `frontend/src/api/reportApi.js` (comment)

**Interfaces:**
- Consumes: everything from Tasks 3–9; the Task 1 response shape.

- [ ] **Step 1: Rewrite `Analytics.jsx` as the container**

- State: `months` (12), `hazardTypeId` ('' = all), `includeSamples` (false), `data`, `error`, `busy`, `hazardTypes` (from `hazardsApi.types()` once; on failure `[]`, so the picker shows only "All types").
- `const pickedName = hazardTypes.find((t) => String(t.id) === hazardTypeId)?.name || null;` feeds the outlook and likelihood, which need not wait for the analytics response.
- Fetch effect on `[months, hazardTypeId, includeSamples]`, keeping the `live` guard and today's error copy; params add `hazard_type: hazardTypeId` when set.
- Filter row (`div.db-card.an-toolbar.db-no-print`): period segmented control (as today); `<label className="db-field">Hazard <select>` with "All types" + `hazardTypes`; the sample checkbox with class `an-secondary`; `<ExportMenu onExport={exportAs} disabled={!data || busy} />`.
- `exportAs(via)`: log with criteria `` `months=${months}${data.hazard_type ? ` hazard_type=${data.hazard_type.name}` : ''}${includeSamples ? ' samples=included' : ''}` ``, then CSV download (`downloadCsv(csvFilename('analytics'), analyticsCsv(data))`) or `window.print()`.
- Under it: the period line (today's, plus ` · {data.hazard_type.name}` when set) and, when `data.includes_samples`, `<p className="an-notice" role="status">` with the sample notice copy.
- Body (`div.an-body`, `is-busy` while busy), in order: `ActivityBand`, `ResponseBand`, `MonthlyMultiples`, `db-card` with `SeasonalOutlook` (`hazardName` from the picked type), `db-card` "Likelihood by barangay" (History's sub line) with `BarangayLikelihood hazard={pickedName || ''} excludeSamples={!includeSamples}`, then the breakdowns: `div.an-grid` with "Zones by hazard type" (hidden when `data.hazard_type`) and "Zones by severity" (`inSeverityOrder` rows, `thin`), both mapped through today's `toRows` with `SEVERITY_LABEL` names and `hazardSeriesColor` / `severitySeriesColor`, both with rows `[]` when `kpis.zones_published === 0`, then `db-card` "Barangay activity" with `BarangayActivity rows={data.barangays}`.
- Delete the "Likely next month" card, `SERIES`, the series state, and the old `Stat` / response markup.

- [ ] **Step 2: Restyle in `Analytics.css`**

- `.an-band` (heading + content, 32px bottom margin); `.an-tiles` grid of five (`repeat(5, minmax(0, 1fr))`, two columns below 640px); tile labels `text-transform: none`; Bricolage proportional figures on tile values, `font-variant-numeric: tabular-nums` on `.db-table td`.
- `.an-meter*`: 8px track `var(--db-mist)`, fill `var(--db-navy)`, radius 4px; meters in two columns, stacked below 640px.
- `.an-multiples`: 2×2 grid, one column below 640px; `.an-multiple` padding and hairline border `var(--db-line)`.
- `.an-notice`: background `var(--db-medium-tint)`, text `var(--db-heading)`, left border 3px `var(--db-medium)`, radius 10px.
- `.an-secondary`: smaller, `var(--db-soft)` text.
- `.ba-table .ba-bar`: inline-block, height 6px, radius 3px, `var(--db-navy)` at 70% opacity, margin-left 8px, max width 120px; `.ba-table:not(.is-expanded) .ba-more { display: none; }`.
- Problem 4: `.an-grid > *, .an-multiples > *, .an-tiles > * { min-width: 0; }`.
- Below 640px the period control is one full-width row (`.an-seg { display: flex; width: 100%; flex-wrap: nowrap; }`, each button `flex: 1`, padding 8px 6px), so no single segment button wraps onto its own line; Hazard, the checkbox and Export wrap below it.
- Print: `.ba-table .ba-more { display: table-row; }`, `.an-multiples` stays 2×2, cards `break-inside: avoid`; keep the existing print rules.

- [ ] **Step 3: Trim `HistoricalData.jsx`**

Header, sub line and link per Global Constraints (`Link` from `react-router-dom`); the record count moves into the Records card (`<h2>{records.length} record(s)</h2>`, dropping the separate sub line); remove the stat tiles, outlook, likelihood, events-over-time and three breakdown cards, the `historyApi.trends` call and `trends` state, and the now-unused imports and helpers (`toRows`, `monthPoints`, `typeRows`, `severityRows`, `barangayRows`, `outlook`, `scopeLabel`); the sample note ends after "…not real events."

- [ ] **Step 4: Repoint the Dashboard link and update the API comment**

`DRRMODashboard.jsx:440`: `to="/app/reports?tab=analytics"`. `reportApi.js` analytics comment: list `hazard_type` and the `barangays` key.

- [ ] **Step 5: Run the frontend suite and check the dev build**

Run: `CI=true npx react-scripts test --watchAll=false`
Expected: all pass. The `npm start` output shows "Compiled" with no new ESLint warnings beyond the two existing BOM warnings.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/Analytics.jsx frontend/src/pages/css/Analytics.css frontend/src/pages/HistoricalData.jsx frontend/src/pages/Dashboard/DRRMODashboard.jsx frontend/src/api/reportApi.js
git commit -m "analytics: banded layout with hazard filter, outlook and likelihood; History is the archive"
```

---

### Task 11: Whole-feature check in the running app

**Files:**
- Modify (scratchpad, not committed): `C:\Users\SANNIC~1\AppData\Local\Temp\claude\c--Users-Sannichigetsu-Geoalert\a10223da-fd53-48b5-b79e-ba12bb96e4fd\scratchpad\shot\shot.js`

The script stubs `/api/auth/me/`, notifications, `/api/reports/printed/` and `/api/reports/analytics/` (the README admin password is rejected, and stubbing keeps the audit log clean). `/api/hazards/types/`, `/api/history/` and `/api/history/forecast/` are public and pass through.

- [ ] **Step 1: Update the stub to the new response shape**

`analytics(months, hazardTypeId)` returns `hazard_type` (`{ id: 1, name: 'Flood' }` when `hazardTypeId === '1'`, else `null`) and `barangays` (12 rows, both counts) instead of the two top-10 lists. Add a mode where every count is 0 and both rates are `null`. Record each `/api/reports/printed/` request body.

- [ ] **Step 2: Capture and look at each screen**

Take screenshots at `after-*.png` and look at every one:
- Analytics 1366 px, all types; then Flood picked (no by-type card; period line ends "· Flood").
- Analytics 390 px fresh load, and 1366 → 390 resize. Expected: `scrollWidth - innerWidth` logs `0` for both.
- `page.emulateMedia({ media: 'print' })` at 1366 px. Expected: no filter row, all 12 barangay rows, numbers tables open, 2×2 multiples.
- The all-zero mode. Expected: "—" meters with the null captions, the empty messages, no "NaN".
- History 1366 and 390 px. Expected: archive only, and the link opens `/app/reports?tab=analytics`.
- DRRMO Dashboard: "See every barangay and month" opens the Analytics tab.

- [ ] **Step 3: Check the interactions**

- Pick Flood then Fire within 200 ms (delay the stubbed analytics response for Flood by 1.5 s). Expected: the period line ends "· Fire" after both settle.
- Export → Download CSV, Save as PDF (stub `window.print`), Print. Expected: three `/api/reports/printed/` bodies with `via` `csv`, `pdf`, `print` and `report: 'analytics'`, each before its action; the CSV contains `Hazard type,` and `Barangay activity`.
- Tick "Include sample data". Expected: the amber notice appears, the forecast request no longer carries `exclude_samples`, and the analytics request carries `include_samples=true`.

- [ ] **Step 4: Run every test suite**

Run: `venv/Scripts/python.exe manage.py test tests.test_analytics tests.test_forecast` (from `backend/`) and `CI=true npx react-scripts test --watchAll=false` (from `frontend/`).
Expected: all pass.

- [ ] **Step 5: Report to the user** with the before/after screenshot paths and anything that failed. No commit in this task.
