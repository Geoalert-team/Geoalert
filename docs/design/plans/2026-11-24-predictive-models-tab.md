# "Predictive models" tab and flood data readiness — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a third tab, "Predictive models", to the Reporting and Analytics page, holding a new "Flood data readiness" card and the existing "Model accuracy" card (moved there from Analytics, unchanged).

**Architecture:**
- A new read-only, public, cached endpoint, `GET /api/history/forecast/readiness/`, counts located flood days and new located floods since the flood map was published.
- Its "located flood" query is factored out of `flood_purok.since_publishing`, so both use one definition.
- The frontend adds a self-fetching `FloodReadiness` card and a `PredictiveModelsPanel` as the third tab, and drops Model accuracy from Analytics.

**Tech Stack:** Django 4.2 / DRF / PostGIS; React (react-scripts, Jest), react-router.

**Spec:** `docs/design/specs/2026-11-24-predictive-models-tab-design.md`.

## Global Constraints

- **Never `git commit`.** Every commit step reads "Leave uncommitted".
- **History records are read, never written.** Do not touch the History page, `purok_levels.py`, `decide*.py` or the flood model's training code.
- **Nothing automatic.** The endpoint is GET-only and returns aggregate counts and model metadata, never a location or coordinate. No retraining, switching or prediction change anywhere.
- **`flood_purok.since_publishing`'s output must not change.** That includes the order of its `misses`: records by `occurred_at` first, then marks by `created_at`.
- **The page gate is unchanged:** `/app/reports` stays for `System_Admin` and `DRRMO_Officer`. The new endpoint is `AllowAny` with `_public` (Cache-Control public, max-age 600), like `forecast/accuracy/`.
- **Thresholds:**
  - `flood_rules.MONITOR_MIN` (10) is the review threshold.
  - New constants `flood_rules.FORECAST_DAYS_MIN = 20` and `FORECAST_DAYS_MAX = 30`, with a comment citing `docs/research/2026-11-24-flood-prediction-assessment.md`.
- **A located flood** is a history record with `hazard_type__name='Flood'` and either `location` not null or at least one purok, OR a `ZoneFieldMark` with `kind='Affected'` on a zone with `hazard_type__name='Flood'`.
- **A located flood day** is a distinct date of `timezone.localtime(when)`.
- **Copy, verbatim:**
  - Tab label: `Predictive models`; key `models`.
  - Tab blurb: `How the prediction models were built and tested, and whether there is enough data to improve them.`
  - Card title: `Flood data readiness`.
  - Card subtitle: `Whether there is enough located flood data to improve the flood predictions. It only counts: nothing here changes a prediction.`
  - Days line: `Located flood days on record: {n}. Flood forecasting needs about {min}–{max}.`
  - Status, under the minimum: `Not enough located flood days to try flood forecasting yet.`
  - Status, at the minimum or above: `There are enough located flood days to consider building a flood forecast. That needs a rebuild by a developer.`
  - Since line: `New located floods since the flood map was published: {n}. The map is reviewed after {review_after}.`
  - Under review: the existing `UNDER_REVIEW` from `ForecastAccuracy.jsx`.
  - No usable map: `flood_map.reason`, or else `No flood map has been published yet.`
  - Training line: `The flood map comes from the {trained_on} ({survey_spots} flood spots), not from these records. Built {YYYY-MM-DD}.` Drop the parenthesis when `survey_spots` is null, and drop `Built …` when `built_at` is null.
  - `trained_on` (backend constant `TRAINED_ON`): `2017 UP Mananga flood survey`.
  - Loading: `Loading the readiness check…`
  - Error: `The readiness check could not be loaded right now.`
- **Tests run on the private test database:**
  - Backend (from `backend/`): `PYTHONPATH="C:/Users/Sannichigetsu/.geoalert-test" venv/Scripts/python.exe manage.py test <labels> --settings=geo_test_settings_flood --noinput`
  - Frontend (from `frontend/`): `CI=true npm test -- --watchAll=false <path>`

## Review Focus

1. **Two located floods on the same local day, and two an hour apart across local midnight (23:30 and 00:30 Manila).** The first pair counts as 1 day and the second as 2: local dates, not UTC. Test: Task 1 `test_days_are_distinct_local_dates`.
2. **A flood model file that is missing, stale or unreadable.** The endpoint still answers 200 with the counts, `flood_map.available` false with the model's reason, and `since_publishing` null. The card shows that reason in place of the since line. Tests: Task 1 `test_counts_without_a_usable_model`; Task 2 `shows the model's reason when there is no usable map`.
3. **A model whose report file is missing.** `flood_map.available` stays true, `survey_spots` is null, and the training line drops the parenthesis. Tests: Task 1 `test_report_missing_leaves_survey_spots_empty`; Task 2 `the training line drops what it does not know`.
4. **Records that are not located floods:** fire or landslide records with a point, a flood record with neither a point nor a purok, and a "Clear here" mark on a flood zone. None is counted. Test: Task 1 `test_only_located_floods_count`.
5. **The readiness request fails.** The readiness card shows its error line and the Model accuracy card on the same tab still loads. Test: Task 3 `a failed readiness check leaves Model accuracy working`.

---

### Task 1: Backend — located floods, readiness and the endpoint

**Files:**
- Modify: `backend/apps/history/flood_rules.py` (constants beside `MONITOR_MIN`)
- Modify: `backend/apps/history/flood_purok.py` (`located_floods`, `readiness`, `TRAINED_ON`; `since_publishing` uses `located_floods`)
- Modify: `backend/apps/history/views.py` (`FloodReadinessView`), `backend/apps/history/urls.py` (route)
- Test: `backend/tests/test_flood_readiness.py` (new; `FireSetupMixin` + `TestCase`, as `tests/test_flood_purok.py` `SincePublishingTests`)

**Interfaces:**
- Produces:
  - `flood_rules.FORECAST_DAYS_MIN: int = 20`, `flood_rules.FORECAST_DAYS_MAX: int = 30`
  - `flood_purok.located_floods(since: datetime | None = None) -> list[tuple[datetime, HistoricalRecord | ZoneFieldMark]]`. It returns located Flood records with `occurred_at > since` (all records when `since` is None), ordered by `occurred_at`, then Affected marks on Flood zones with `created_at > since`, ordered by `created_at`.
  - `flood_purok.readiness() -> dict` with this shape:

    ```python
    {
        'located_flood_days': int,
        'forecast_days_needed': {'min': 20, 'max': 30},
        'enough_for_forecasting': bool,
        'flood_map': {
            'available': bool,
            'reason': str | None,
            'version': ...,
            'built_at': ...,
            'trained_on': TRAINED_ON,
            'survey_spots': int | None,
        },
        'since_publishing': {'n': int, 'review_after': 10, 'under_review': bool} | None,
    }
    ```

    When the model is unusable, `flood_map` is just `{'available': False, 'reason': <load() string>}` and `since_publishing` is None.
  - `GET /api/history/forecast/readiness/`, URL name `history-forecast-readiness`, returns `readiness()`.

- [ ] **Step 1: Write the failing tests** in `backend/tests/test_flood_readiness.py`. Create records with `HistoricalRecord.objects.create(barangay=…, hazard_type=self.flood, severity_level='Orange', occurred_at=…, location=…)` and marks as in `SincePublishingTests`.

```python
def test_days_are_distinct_local_dates(self):
    tz = timezone.get_current_timezone()
    for when in (datetime(2026, 8, 12, 9, tzinfo=tz), datetime(2026, 8, 12, 15, tzinfo=tz),    # same day: 1
                 datetime(2026, 9, 1, 23, 30, tzinfo=tz), datetime(2026, 9, 2, 0, 30, tzinfo=tz)):  # across midnight: 2
        self.flood_at(self.near, when)
    with flood_model_files(None):
        self.assertEqual(flood_purok.readiness()['located_flood_days'], 3)

def test_only_located_floods_count(self):
    self.flood_at(self.near, self.day1)                                  # counted
    self.record(self.fire, self.near, self.day2)                         # fire with a point: no
    self.record(self.landslide, self.near, self.day3)                    # landslide: no
    HistoricalRecord.objects.create(..., hazard_type=self.flood, occurred_at=self.day4, location=None)  # no point, no purok: no
    linked = HistoricalRecord.objects.create(..., hazard_type=self.flood, occurred_at=self.day5, location=None)
    linked.puroks.add(self.far)                                          # purok only: counted
    ZoneFieldMark.objects.create(zone=self.zone(self.far, hazard_type=self.flood), kind='Affected', ...)  # counted (today)
    ZoneFieldMark.objects.create(zone=self.zone(self.far, hazard_type=self.flood), kind='Clear', ...)     # no
    with flood_model_files(None):
        self.assertEqual(flood_purok.readiness()['located_flood_days'], 3)

def test_counts_without_a_usable_model(self):
    self.flood_at(self.near, self.day1)
    for ctx, reason in ((flood_model_files(None), NOT_TRAINED),
                        (flood_model_files({self.near: 'Red'}, outlines_version='old'), STALE)):
        with ctx:
            r = self.client.get('/api/history/forecast/readiness/')
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r.data['located_flood_days'], 1)
            self.assertEqual(r.data['flood_map'], {'available': False, 'reason': reason})
            self.assertIsNone(r.data['since_publishing'])
            self.assertFalse(r.data['enough_for_forecasting'])
            self.assertIn('public', r['Cache-Control'])

def test_since_publishing_and_the_map(self):   # model built 2026-11-01 (flood_model_files)
    self.flood_at(self.near, datetime(2026, 11, 25, 6, tzinfo=tz))   # after: counted in n
    self.flood_at(self.far, datetime(2025, 1, 5, 6, tzinfo=tz))      # before: a day, not in n
    with flood_model_files({self.near: 'Red', self.far: 'Green'}):
        r = flood_purok.readiness()
    self.assertEqual(r['since_publishing'], {'n': 1, 'review_after': 10, 'under_review': False})
    self.assertEqual(r['flood_map']['trained_on'], '2017 UP Mananga flood survey')
    self.assertTrue(r['flood_map']['available'])
    self.assertEqual(r['forecast_days_needed'], {'min': 20, 'max': 30})

def test_enough_days_at_the_minimum(self):     # 20 distinct days → True; 19 → False
    ...

def test_report_missing_leaves_survey_spots_empty(self):
    with flood_model_files({self.near: 'Red'}, report=False):
        fm = flood_purok.readiness()['flood_map']
    self.assertTrue(fm['available'])
    self.assertIsNone(fm['survey_spots'])

def test_no_location_in_the_response(self):
    self.flood_at(self.near, self.day1)
    with flood_model_files({self.near: 'Red'}):
        text = json.dumps(self.client.get('/api/history/forecast/readiness/').data)
    self.assertNotIn('POINT', text)
    self.assertNotIn(str(self.near.boundary.point_on_surface.x)[:7], text)
```

  - The test helpers:
    - `flood_at(purok, when)`: a Flood record at `purok.boundary.point_on_surface`.
    - `record(hazard_type, purok, when)`: the same for any hazard type.
    - `self.day1`…`self.day5`: five distinct local dates.
    - `tz = timezone.get_current_timezone()`.
  - `self.fire`, `self.flood`, `self.zone` and `self.officer` come from `FireSetupMixin`. It has no Landslide type, so create one in `setUp`: `HazardType.objects.create(name='Landslide', logo_class='landslide', is_active=True)`.
  - The REPORT fixture in `tests/flood_model_file.py` has no `survey_spots`. Add `'survey_spots': 105` to its `REPORT` dict, and assert `fm['survey_spots'] == 105` in `test_since_publishing_and_the_map`.

- [ ] **Step 2: Run** `... manage.py test tests.test_flood_readiness ...`. Expected: FAIL/ERROR (`readiness` not defined, 404 on the URL).

- [ ] **Step 3: Implement.**
  - Add the constants to `flood_rules.py`.
  - Factor `located_floods(since=None)` out of `since_publishing`, and make `since_publishing` call `located_floods(built)` and resolve each item's puroks. A record resolves to its location's smallest purok when it has a point, else its puroks. A mark resolves to its location's smallest purok.
  - Add `TRAINED_ON = '2017 UP Mananga flood survey'` and `readiness()`. It counts days with `{timezone.localtime(w).date() for w, _ in located_floods()}` and reads `survey_spots` from `model.report.get('survey_spots')` when the report exists.
  - Add `FloodReadinessView(APIView)` with `permission_classes = [AllowAny]`; its `get` returns `_public(Response(flood_purok.readiness()))`. Give it a docstring in the style of `ForecastAccuracyView`.
  - Add the route `path('forecast/readiness/', FloodReadinessView.as_view(), name='history-forecast-readiness')` next to `forecast/accuracy/`.

- [ ] **Step 4: Run** `... manage.py test tests.test_flood_readiness tests.test_flood_purok tests.test_flood_log ...`. Expected: PASS. `SincePublishingTests` stays green unchanged, which proves `since_publishing` kept its output.

- [ ] **Step 5: Leave uncommitted.**

### Task 2: Frontend — the `FloodReadiness` card

**Files:**
- Modify: `frontend/src/api/historyApi.js` (add `forecastReadiness`)
- Create: `frontend/src/components/Forecast/FloodReadiness.jsx`
- Test: `frontend/src/components/Forecast/floodReadiness.test.js` (new; `createRoot` + `act`, `jest.mock('../../api/historyApi', …)` as `forecastAccuracy.test.js`)

**Interfaces:**
- Consumes: the Task 1 response shape.
- Produces:
  - `historyApi.forecastReadiness(): Promise<object>`, which GETs `/api/history/forecast/readiness/` and returns `r.data`. Add a one-line comment in the style of `forecastAccuracy`.
  - `export default function FloodReadiness()`. It fetches once on mount and renders the card body: `<h2>` title, subtitle, days line, status, since line or reason, training line. It does not render the `db-card` wrapper, which is the panel's job.

- [ ] **Step 1: Write the failing tests.**

```js
const ready = {
  located_flood_days: 6, forecast_days_needed: { min: 20, max: 30 }, enough_for_forecasting: false,
  flood_map: { available: true, reason: null, version: 'noah_fallback@9aba6d331a4b', built_at: '2026-11-24T07:17:00+08:00',
    trained_on: '2017 UP Mananga flood survey', survey_spots: 105 },
  since_publishing: { n: 0, review_after: 10, under_review: false },
};
test('shows the counts against the thresholds', async () => {
  historyApi.forecastReadiness.mockResolvedValue(ready);
  const el = await render();
  expect(el.querySelector('h2').textContent).toBe('Flood data readiness');
  expect(el.textContent).toContain('Located flood days on record: 6. Flood forecasting needs about 20–30.');
  expect(el.textContent).toContain('Not enough located flood days to try flood forecasting yet.');
  expect(el.textContent).toContain('New located floods since the flood map was published: 0. The map is reviewed after 10.');
  expect(el.textContent).toContain('The flood map comes from the 2017 UP Mananga flood survey (105 flood spots), not from these records. Built 2026-11-24.');
});
test('enough days says a rebuild is worth asking for', async () => { /* enough_for_forecasting true, 22 days → ENOUGH copy */ });
test('under review is shown', async () => { /* since_publishing.under_review true → UNDER_REVIEW text */ });
test("shows the model's reason when there is no usable map", async () => {
  historyApi.forecastReadiness.mockResolvedValue({ ...ready, flood_map: { available: false, reason: 'The flood model has not been trained yet.' }, since_publishing: null });
  const el = await render();
  expect(el.textContent).toContain('The flood model has not been trained yet.');
  expect(el.textContent).not.toContain('New located floods since');
  expect(el.textContent).toContain('Located flood days on record: 6.');
});
test('the training line drops what it does not know', async () => { /* survey_spots null → '…flood survey, not from these records.' with no '(' */ });
test('says so when it cannot load', async () => { /* reject → 'The readiness check could not be loaded right now.' */ });
```

- [ ] **Step 2: Run** `CI=true npm test -- --watchAll=false src/components/Forecast/floodReadiness`. Expected: FAIL (module not found).

- [ ] **Step 3: Implement** `FloodReadiness.jsx` with the verbatim copy from Global Constraints. Import `UNDER_REVIEW` from `./ForecastAccuracy`. Use `fc-note` / `db-card-sub` / `db-empty` / `db-error` classes as `ForecastAccuracy` does. When `flood_map.available` is false, show `flood_map.reason || 'No flood map has been published yet.'` and no training line.

- [ ] **Step 4: Run** the same command. Expected: PASS.

- [ ] **Step 5: Leave uncommitted.**

### Task 3: Frontend — the third tab; Model accuracy moves

**Files:**
- Create: `frontend/src/pages/PredictiveModels.jsx`
- Modify: `frontend/src/pages/ReportingAnalytics.jsx` (`TABS`, panel switch, header comment), `frontend/src/pages/Analytics.jsx` (drop the `ForecastAccuracy` import, its card and its docstring line)
- Test: `frontend/src/pages/reportingAnalyticsTabs.test.js` (new), `frontend/src/pages/analyticsPanel.test.js` (update)

**Interfaces:**
- Consumes: `FloodReadiness` (Task 2), `ForecastAccuracy` (existing, unchanged).
- Produces: `export default function PredictiveModelsPanel()`, which renders `<div className="db-card"><FloodReadiness /></div>` then `<div className="db-card"><ForecastAccuracy /></div>`.

- [ ] **Step 1: Write the failing tests.**
  - In `reportingAnalyticsTabs.test.js`, mock `../components/Navbar/PublicNavbar` and `./Reports` / `./Analytics` / `./PredictiveModels` as stubs rendering `REPORTS` / `ANALYTICS` / `MODELS`. Render inside `MemoryRouter`.

```js
test('the third tab is Predictive models and ?tab=models opens it', async () => {
  const el = await renderAt('/app/reports?tab=models');
  expect([...el.querySelectorAll('[role="tab"]')].map((t) => t.textContent)).toEqual(['Reports', 'Analytics', 'Predictive models']);
  expect(el.querySelector('[role="tab"][aria-selected="true"]').textContent).toBe('Predictive models');
  expect(el.textContent).toContain('How the prediction models were built and tested, and whether there is enough data to improve them.');
  expect(el.querySelector('#ra-panel-models').hidden).toBe(false);
  expect(el.textContent).toContain('MODELS');
});
test('an unknown tab still opens Reports', async () => { /* ?tab=nope → Reports selected */ });
```

  - In a new `predictiveModels.test.js` (or in the same file without the panel mock, using `jest.isolateModules`), test the real panel with `historyApi` mocked:

```js
test('a failed readiness check leaves Model accuracy working', async () => {
  historyApi.forecastReadiness.mockRejectedValue(new Error('down'));
  historyApi.forecastAccuracy.mockResolvedValue({ hazards: [] });
  const el = await render(<PredictiveModelsPanel />);
  expect(el.textContent).toContain('The readiness check could not be loaded right now.');
  expect([...el.querySelectorAll('h2')].map((h) => h.textContent)).toEqual(['Flood data readiness', 'Model accuracy']);
});
```

  - In `analyticsPanel.test.js`, change the headings assertion so `'Model accuracy'` is no longer expected, and add `expect(headings).not.toContain('Model accuracy')`. Keep `'Seasons on record'` and `'Likelihood by barangay'`.

- [ ] **Step 2: Run** `CI=true npm test -- --watchAll=false src/pages`. Expected: FAIL (no third tab; Analytics still shows Model accuracy; module not found).

- [ ] **Step 3: Implement.**
  - Add `{ key: 'models', label: 'Predictive models', blurb: <verbatim> }` as the third `TABS` entry.
  - The panel switch renders `PredictiveModelsPanel` for `models`.
  - Add one line to the header comment ("Predictive models: how the prediction models were built and tested, and whether there is enough flood data to improve them").
  - Remove the Model accuracy card from `Analytics.jsx`, and its "Model accuracy" line from the docstring list.

- [ ] **Step 4: Run** the whole frontend suite (`CI=true npm test -- --watchAll=false`) and `npm run build`. Expected: all suites pass; "Compiled successfully" with no unused-import warning (`ForecastAccuracy` must be gone from `Analytics.jsx`).

- [ ] **Step 5: Run** the full backend suite (`... manage.py test tests apps ...`). Expected: all pass.

- [ ] **Step 6: Leave uncommitted.** Report `git status --short` for the new and changed files.
