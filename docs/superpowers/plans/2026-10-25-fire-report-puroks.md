# Fire Report Puroks Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A fire report names one or more puroks (up to 10) from the barangay's list. The map in "Where exactly" is a preview that outlines each chosen purok with a pin at its centre. The server sets the report's location from those puroks.

**Architecture:**
- **Backend:** `IncidentReport` gets a `puroks` many-to-many field. The single `purok` / `purok_other` fields from round 1 leave the model, but their columns stay in the database, because the shared database also serves teammates' copies of the app. All the fire rules move into one pure function, `prepare_report`, which the create serializer calls.
- **Frontend:** the form logic stays in `fireReport.js`. The new non-clickable map is a small component.
- **Review findings:** this plan also closes the round-1 review findings that still apply.

**Tech Stack:** Django 4.2 + GeoDjango + DRF (`SimpleTestCase`), React 18 + react-leaflet, Jest via react-scripts 5.

**Spec:** `docs/superpowers/specs/2026-10-25-report-driven-fire-hazards-design.md`, specifically:
- the Decisions row "Puroks on a fire report"
- "Data model › IncidentReport"
- "Design › 1. Submitting a fire report"

This plan replaces round 1's purok and pin handling (`docs/superpowers/plans/2026-10-25-fire-report-form.md`).

## Global Constraints

- **Fire only.** Flood, Landslide and other types keep today's form: the clickable pin and "How serious is it?".
- **No "Not on the list"** and no typed purok names.
- **Database:** don't drop `incr_prk_id` or `incr_purok_other`. The model forgets them; the columns stay.
- **Nothing is written to the shared database** (`migrate`) without the user's OK at that moment.
- **Messages** (the backend and frontend use the same words):

  | Field | Messages |
  |---|---|
  | `started_at` | `Say when the fire started.` / `The start time can't be in the future.` |
  | `puroks` | `Choose the purok or sitio where the fire is.` / `That purok is not in Barangay {name}.` / `Choose at most 10 puroks.` |
  | `puroks`, frontend only | `The purok list didn't load. Try again.` |
  | `barangay` | `Choose the barangay where this is happening.` |

- **Limits:**
  - At most 10 puroks per report.
  - A start time up to 5 minutes ahead of the server clock is accepted, because phone clocks drift.

## Review Focus

- **A fire report sent with photos (multipart) and two puroks:** both puroks must be saved. Covered by the database check in Task 5, Step 2 (a `QueryDict` with `puroks` repeated).
- **A teammate's copy of the app (round 1) sends `purok` instead of `puroks`:** it gets a clear error under `puroks`, not a 500. Test: Task 2, `test_a_fire_report_needs_a_purok`.
- **A dashboard left open for hours, then Fire is chosen:** the start time becomes the current time unless the reporter already changed it. Test: Task 3, `withHazardType`.
- **The purok list fails to load:** the form says so and doesn't call the purok optional. Test: Task 3, `validateReport` with `purokStatus: 'failed'`.
- **The same purok picked twice:** it's stored once. The form hides puroks already chosen, and the server removes duplicates. Tests: Task 2, `test_duplicate_puroks_count_once`; Task 3, `purokOptions` excludes chosen ones.

---

### Task 1: `puroks` on the report, old fields out of the model

**Files:**
- Modify: `backend/apps/reports/models.py` (remove `purok` and `purok_other`, add `puroks`)
- Create: `backend/apps/reports/migrations/0006_fire_report_puroks.py` (written by hand; see Step 3)
- Modify: `backend/apps/reports/serializers.py` (output: `puroks` nested; remove `purok`, `purok_name` and `purok_other`)
- Modify: `backend/apps/reports/views.py` (`IncidentReportListCreateView.get`: add `select_related('barangay', 'hazard_type', 'submitted_by', 'reviewed_by')` and `prefetch_related('puroks')` next to `photos`)
- Test: `backend/tests/test_reports_fire_fields.py` (update)

**Interfaces:**
- Produces:
  - `IncidentReport.puroks = models.ManyToManyField(Purok, blank=True, related_name='incident_reports', db_table='incident_report_purok')`
  - `ReportPurokSerializer` (in `apps/reports/serializers.py`): fields `id`, `name`, `lat` and `lng`. `lat`/`lng` are the purok's `boundary.point_on_surface`, rounded to 6 decimals.
  - `IncidentReportSerializer` outputs `puroks` (that serializer, `many=True`) in place of `purok`, `purok_name` and `purok_other`. `started_at` stays.

- [ ] **Step 1: Update the tests**

In `test_reports_fire_fields.py`, keep `test_purok_other_has_a_database_default` (0005 is unchanged) and replace the output test:

```python
def test_report_output_carries_start_time_and_puroks(self):
    fields = set(IncidentReportSerializer.Meta.fields)
    self.assertTrue({'started_at', 'puroks'} <= fields)
    self.assertFalse({'purok', 'purok_name', 'purok_other'} & fields)

def test_a_purok_is_shown_with_its_centre(self):
    purok = Purok(id=3, name='Purok Sambag', boundary=MultiPolygon(square(123.85, 10.25, 123.86, 10.26)))
    data = ReportPurokSerializer(purok).data
    self.assertEqual((data['id'], data['name']), (3, 'Purok Sambag'))
    self.assertTrue(10.25 <= data['lat'] <= 10.26 and 123.85 <= data['lng'] <= 123.86)

def test_old_columns_stay_in_the_database(self):
    ops = import_module('apps.reports.migrations.0006_fire_report_puroks').Migration.operations
    split = [op for op in ops if isinstance(op, migrations.SeparateDatabaseAndState)]
    self.assertEqual(len(split), 1)
    self.assertEqual(split[0].database_operations, [])
    self.assertEqual(sorted(op.name for op in split[0].state_operations), ['purok', 'purok_other'])
    sql = ' '.join(op.sql for op in ops if isinstance(op, migrations.RunSQL))
    self.assertIn('INSERT INTO incident_report_purok', sql)  # round-1 puroks carried over
```

`square` is the same helper as in `test_load_puroks.py`.

- [ ] **Step 2: Run the tests to verify they fail**

Run (from `backend/`): `venv/Scripts/python.exe manage.py test tests.test_reports_fire_fields`
Expected: FAIL or ERROR (no `ReportPurokSerializer`, no 0006).

- [ ] **Step 3: Change the model, write 0006 and update the serializer and view**

Migration 0006 depends on `('reports', '0005_fire_report_fields')`. Its operations, in order:
1. `SeparateDatabaseAndState(state_operations=[RemoveField('incidentreport', 'purok'), RemoveField('incidentreport', 'purok_other')], database_operations=[])`. The state removal comes first so the two `incident_reports` reverse names never coexist.
2. `AddField` for `puroks`, as in Produces.
3. `RunSQL` with:
   - `"INSERT INTO incident_report_purok (incidentreport_id, purok_id) SELECT incr_id, incr_prk_id FROM incident_report WHERE incr_prk_id IS NOT NULL"`
   - reverse `"DELETE FROM incident_report_purok"`

Add a comment explaining why the old columns stay. Then run `makemigrations reports --check --dry-run`. Expected: `No changes detected`.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `venv/Scripts/python.exe manage.py test tests.test_reports_fire_fields`
Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add backend/apps/reports backend/tests/test_reports_fire_fields.py
git commit -m "A report holds several puroks; the single purok fields leave the model"
```

---

### Task 2: Fire rules on the server

**Files:**
- Modify: `backend/apps/reports/fire_report.py` (rewrite)
- Modify: `backend/apps/reports/serializers.py` (`IncidentReportCreateSerializer`: fields, `validate` and `create`)
- Test: `backend/tests/test_fire_report.py` (rewrite)

**Interfaces:**
- Consumes: `IncidentReport.puroks` (Task 1).
- Produces:
  - `MAX_PUROKS = 10`, `CLOCK_SKEW = timedelta(minutes=5)`
  - `fire_report_errors(attrs: dict, barangay, has_puroks: bool, now: datetime) -> dict[str, str]`. `attrs['puroks']` is a list of objects with `.id` and `.barangay_id`.
  - `prepare_report(attrs: dict, now: datetime, has_puroks: Callable[[barangay], bool]) -> tuple[dict, dict]`: returns `(attrs, errors)`.
    - **Not a Fire report:** returns attrs without `started_at` and `puroks`, and `{}`.
    - **Fire without a barangay:** `{'barangay': 'Choose the barangay where this is happening.'}`.
    - **Fire:**
      - Removes duplicate puroks, keeping their order.
      - Validates with `fire_report_errors`.
      - When there are no errors, sets `attrs['location']`, overwriting any pin the client sent. It uses the first purok's `boundary.point_on_surface`, or else the barangay's, or else `None`.
    - Fire is detected as `attrs['hazard_type'].name.lower() == 'fire'`.

- [ ] **Step 1: Write the failing tests**

`BRGY = FakeBarangay(19, 'San Roque', square(123.85, 10.25, 123.86, 10.26))`. `FakePurok(id, barangay_id, boundary)`. `SAMBAG = FakePurok(3, 19, square(123.85, 10.25, 123.855, 10.255))`, `AGOHO = FakePurok(6, 19, square(123.855, 10.255, 123.86, 10.26))`. `FIRE` and `FLOOD` are `FakeType` objects with `.name`. `NOW` is 2026-10-25 14:00 Manila. `ok(**kw)` returns:
- `hazard_type=FIRE`, `barangay=BRGY`
- `started_at=NOW - 1h`
- `puroks=[SAMBAG]`
- `location=None`, `description='Smoke from a house'`

`kw` overrides any of these. `yes = lambda b: True`, `no = lambda b: False`.

```python
def test_a_complete_fire_report_gets_its_location_from_the_first_purok(self):
    attrs, errors = prepare_report(ok(puroks=[SAMBAG, AGOHO], location=Point(1, 1, srid=4326)), NOW, yes)
    self.assertEqual(errors, {})
    self.assertTrue(SAMBAG.boundary.contains(attrs['location']))       # the client's pin is ignored

def test_start_time_is_required_and_not_in_the_future(self):
    self.assertEqual(prepare_report(ok(started_at=None), NOW, yes)[1], {'started_at': 'Say when the fire started.'})
    self.assertEqual(prepare_report(ok(started_at=NOW + timedelta(minutes=10)), NOW, yes)[1],
                     {'started_at': "The start time can't be in the future."})
    self.assertEqual(prepare_report(ok(started_at=NOW + timedelta(minutes=2)), NOW, yes)[1], {})

def test_a_fire_report_needs_a_purok(self):
    self.assertEqual(prepare_report(ok(puroks=[]), NOW, yes)[1], {'puroks': 'Choose the purok or sitio where the fire is.'})

def test_puroks_must_be_in_the_barangay_and_at_most_ten(self):
    self.assertEqual(prepare_report(ok(puroks=[FakePurok(7, 8, SAMBAG.boundary)]), NOW, yes)[1],
                     {'puroks': 'That purok is not in Barangay San Roque.'})
    many = [FakePurok(i, 19, SAMBAG.boundary) for i in range(11)]
    self.assertEqual(prepare_report(ok(puroks=many), NOW, yes)[1], {'puroks': 'Choose at most 10 puroks.'})

def test_duplicate_puroks_count_once(self):
    attrs, errors = prepare_report(ok(puroks=[SAMBAG, AGOHO, SAMBAG]), NOW, yes)
    self.assertEqual([p.id for p in attrs['puroks']], [3, 6])

def test_no_puroks_in_the_barangay_uses_its_centre(self):
    attrs, errors = prepare_report(ok(puroks=[]), NOW, no)
    self.assertEqual(errors, {})
    self.assertTrue(BRGY.boundary.contains(attrs['location']))

def test_a_fire_report_needs_a_barangay(self):
    self.assertEqual(prepare_report(ok(barangay=None), NOW, yes)[1],
                     {'barangay': 'Choose the barangay where this is happening.'})

def test_other_hazards_drop_the_fire_fields(self):
    attrs, errors = prepare_report(ok(hazard_type=FLOOD, location=Point(123.851, 10.251, srid=4326)), NOW, yes)
    self.assertEqual(errors, {})
    self.assertNotIn('started_at', attrs)
    self.assertNotIn('puroks', attrs)
    self.assertEqual(attrs['location'].x, 123.851)                     # a flood keeps its own pin
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `venv/Scripts/python.exe manage.py test tests.test_fire_report`
Expected: an ERROR, because `prepare_report` can't be imported.

- [ ] **Step 3: Implement and wire it in**

- `IncidentReportCreateSerializer`:
  - `puroks = serializers.PrimaryKeyRelatedField(queryset=Purok.objects.all(), many=True, required=False)`.
  - `Meta.fields` gains `started_at` and `puroks`, and loses `purok` and `purok_other`.
  - At the end of `validate`: `attrs, errors = prepare_report(attrs, timezone.now(), lambda b: Purok.objects.filter(barangay=b).exists())`, and raise `ValidationError(errors)` when there are any.
  - In `create`, pop `puroks` before `super().create` and call `report.puroks.set(...)` afterwards. The view's transaction keeps it all-or-nothing.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `venv/Scripts/python.exe manage.py test tests.test_fire_report tests.test_reports_fire_fields`
Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add backend/apps/reports/fire_report.py backend/apps/reports/serializers.py backend/tests/test_fire_report.py
git commit -m "Fire reports: one or more puroks, location from the puroks, server-side rules"
```

---

### Task 3: Form logic

**Files:**
- Modify: `frontend/src/pages/Dashboard/fireReport.js` (rewrite)
- Test: `frontend/src/pages/Dashboard/fireReport.test.js` (rewrite)

**Interfaces:**
- Consumes:
  - `puroksOf` from `components/Map/purokStyle.js`
  - purok features: `feature.id`, `properties.name`, `properties.label_point = [lng, lat]`
- Produces:
  - `MAX_PUROKS = 10`
  - `isFireType(hazardTypes, id)`, `localNow(now)`: unchanged
  - `purokOptions(geo, barangayId, chosen: string[] = []) -> Array<{id, label}>`: as in round 1, minus the chosen ones
  - `purokPins(geo, ids: string[]) -> Array<{id, name, lat, lng}>`: in the order of `ids`
  - `withHazardType(form, id, { fire, now = new Date() }) -> form`: sets `hazard_type`. When `fire` and `!form.started_at_edited`, it also sets `started_at: localNow(now)`.
  - `withBarangay(form, id) -> form`: sets `barangay` and empties `puroks`
  - `hazardSwitchErrors(errors) -> errors`: without `started_at`, `puroks`, `location` and `severity_estimate`
  - `validateReport(form, { fire, hasPuroks, purokStatus, now = new Date() })`:
    - `purokStatus` is `'loading'`, `'ready'` or `'failed'`
    - non-fire: unchanged
    - fire: checks `started_at`, then `puroks`. When `purokStatus === 'failed'` the message is `The purok list didn't load. Try again.`; otherwise none-but-`hasPuroks` and more than `MAX_PUROKS` give their messages. There is no `location` check for fire.
  - `reportPayload(form, { fire })`:
    - fire: `{…base, started_at, puroks: number[]}`, with no `location`, `severity_estimate`, `purok` or `purok_other`
    - non-fire: unchanged (`location` and `severity_estimate`)
  - `placeLabel(report) -> string | null`: `report.puroks` names joined with `', '`, or `null`
  - Form state: `puroks: string[]` and `started_at_edited: boolean` replace `purok` and `purok_other`.

- [ ] **Step 1: Write the failing tests**

Keep the round-1 GEO fixture. Add `properties.label_point` (the square's lower-left corner + 0.005) to each feature, and change `FIRE` to `puroks: ['3', '6'], started_at_edited: false`, removing `purok` and `purok_other`. The tests:

```js
test('options leave out puroks already chosen', () => {
  expect(purokOptions(GEO, '19', ['3']).map((o) => o.label))
    .toEqual(['Purok Agoho', 'Unnamed area 2 (no name yet)', 'Unnamed area 10 (no name yet)']);
});
test('pins sit at each chosen purok, in order', () => {
  expect(purokPins(GEO, ['6', '3'])).toEqual([
    { id: '6', name: 'Purok Agoho', lat: 10.255, lng: 123.865 },
    { id: '3', name: 'Purok Sambag', lat: 10.255, lng: 123.855 }]);
});
test('choosing Fire refreshes a start time nobody touched', () => {
  const later = new Date(2026, 9, 25, 14, 0);
  expect(withHazardType({ ...FIRE, started_at: '2026-10-25T08:00' }, '2', { fire: true, now: later }).started_at).toBe('2026-10-25T14:00');
  expect(withHazardType({ ...FIRE, started_at: '2026-10-25T08:00', started_at_edited: true }, '2', { fire: true, now: later }).started_at)
    .toBe('2026-10-25T08:00');
});
test('changing barangay empties the puroks', () => {
  expect(withBarangay(FIRE, '8').puroks).toEqual([]);
});
test('switching hazard clears the fire errors', () => {
  expect(hazardSwitchErrors({ puroks: 'x', started_at: 'y', location: 'z', description: 'd' })).toEqual({ description: 'd' });
});
test('fire report checks', () => {
  const opts = { fire: true, hasPuroks: true, purokStatus: 'ready', now: NOW };
  expect(validateReport(FIRE, opts)).toEqual({});
  expect(validateReport({ ...FIRE, location: null }, opts)).toEqual({});           // no pin needed
  expect(validateReport({ ...FIRE, puroks: [] }, opts).puroks).toBe('Choose the purok or sitio where the fire is.');
  expect(validateReport({ ...FIRE, puroks: Array.from({ length: 11 }, (_, i) => String(i)) }, opts).puroks).toBe('Choose at most 10 puroks.');
  expect(validateReport({ ...FIRE, puroks: [] }, { ...opts, purokStatus: 'failed', hasPuroks: false }).puroks)
    .toBe("The purok list didn't load. Try again.");
  expect(validateReport({ ...FIRE, puroks: [] }, { ...opts, hasPuroks: false })).toEqual({});
  expect(validateReport({ ...FIRE, started_at: '2026-10-25T14:10' }, opts).started_at).toBe("The start time can't be in the future.");
});
test('payload: fire sends puroks, no pin; other types keep the pin', () => {
  const fire = reportPayload(FIRE, { fire: true });
  expect(fire.puroks).toEqual([3, 6]);
  ['location', 'severity_estimate', 'purok', 'purok_other'].forEach((k) => expect(fire).not.toHaveProperty(k));
  const flood = reportPayload({ ...FIRE, severity_estimate: 'Moderate' }, { fire: false });
  expect(flood).toMatchObject({ severity_estimate: 'Moderate', location: [10.255, 123.855] });
  ['started_at', 'puroks'].forEach((k) => expect(flood).not.toHaveProperty(k));
});
test('place label lists the puroks', () => {
  expect(placeLabel({ puroks: [{ name: 'Purok Santol' }, { name: 'Purok Lubi' }] })).toBe('Purok Santol, Purok Lubi');
  expect(placeLabel({ puroks: [] })).toBeNull();
  expect(placeLabel({})).toBeNull();
});
```

Keep the round-1 tests `isFireType` and `localNow`.

- [ ] **Step 2: Run the tests to verify they fail**

Run (from `frontend/`): `CI=true npx react-scripts test --watchAll=false src/pages/Dashboard/fireReport.test.js`
Expected: FAIL (missing exports or old behaviour).

- [ ] **Step 3: Implement**

Rewrite `fireReport.js` to the Produces list.

- [ ] **Step 4: Run the tests to verify they pass**

Run: the command from Step 2
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/Dashboard/fireReport.js frontend/src/pages/Dashboard/fireReport.test.js
git commit -m "Fire form logic: several puroks, pins from puroks, fresh start time"
```

---

### Task 4: The form, the preview map and the API call

**Files:**
- Create: `frontend/src/components/Map/PurokPreviewMap.jsx`
- Modify: `frontend/src/api/reportApi.js` (`submit`)
- Modify: `frontend/src/pages/Dashboard/BarangayDashboard.jsx`

**Interfaces:**
- Consumes: Task 3's exports; `LocationPicker.css`'s `.lp-pin` style; `barangaysApi.puroks()`.
- Produces: `PurokPreviewMap({ barangay, puroks, pins })`
  - `barangay` is a feature or `null`; `puroks` is an array of chosen purok features; `pins` comes from `purokPins`.
  - It renders a `MapContainer` with no click handler, the barangay outline, the chosen outlines and a non-interactive `Marker` per pin.
  - It fits to the chosen puroks' bounds when there are any, otherwise to the barangay, the way `LocationPicker`'s `FitTo` does.
  - Under the map: *"The pins show the puroks you chose."*

- [ ] **Step 1: `reportsApi.submit`**

- Replace the `purok` / `purok_other` parameters with `puroks = []`.
- JSON: `body.puroks = puroks` when non-empty.
- Multipart: append each id under `puroks`. `Object.entries(body).forEach(...)` would turn the array into `"3,6"`, so leave `puroks` out of `body` on that path and append the ids one by one.

- [ ] **Step 2: The form**

- **State:**
  - `emptyForm` gets `puroks: []` and `started_at_edited: false`, and drops `purok` and `purok_other`.
  - `purokStatus` starts as `'loading'` and becomes `'ready'` or `'failed'`.
  - `loadPuroks()` is called on mount and again by a **Try again** button shown when the status is `failed`.
- **Handlers:**
  - Hazard choice: `setForm((f) => withHazardType(f, id, { fire: isFireType(hazardTypes, id) }))` and `setErrors(hazardSwitchErrors)`.
  - Barangay `<select>`: `withBarangay`.
  - Start time input: sets `started_at` and `started_at_edited: true`.
- **When `fire`**, instead of `LocationPicker` and the single-purok `<select>`:
  - **Purok / Sitio** (`*` when `hasPuroks`): one chip per chosen purok (name + `×` button, `aria-label="Remove {name}"`). Below them, a `<select>` with the placeholder "+ Add another purok", listing `purokOptions(purokGeo, form.barangay, form.puroks)`. It is disabled once `form.puroks.length === MAX_PUROKS`. Picking an option appends it and resets the select.
  - **Where exactly**: `<PurokPreviewMap barangay={…} puroks={chosen features} pins={purokPins(purokGeo, form.puroks)} />`.
- **When not fire:** unchanged (`LocationPicker`, optional pin, "How serious is it?").
- **Validation:** `validateReport(form, { fire, hasPuroks, purokStatus })`.

- [ ] **Step 3: Run the frontend tests and the build**

Run (from `frontend/`):
- `CI=true npx react-scripts test --watchAll=false`
- `npx react-scripts build`

Expected: all suites pass, and the build has no new warnings (the "Unicode BOM" warnings come from files this plan doesn't touch).

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/Map/PurokPreviewMap.jsx frontend/src/api/reportApi.js frontend/src/pages/Dashboard/BarangayDashboard.jsx
git commit -m "Fire form: pick several puroks; the map previews their pins"
```

---

### Task 5: Shared database and a real check (needs the user's OK)

- [ ] **Step 1: Migrate**

Ask the user, then run (from `backend/`): `venv/Scripts/python.exe manage.py migrate reports`
Expected: `Applying reports.0006_fire_report_puroks... OK`.

Then confirm in `information_schema` that `incr_prk_id` and `incr_purok_other` still exist and `incident_report_purok` was created.

- [ ] **Step 2: Check the serializer against the database without saving**

In `manage.py shell`, validate a multipart-shaped `QueryDict`. It holds a Fire `hazard_type`, `barangay` San Roque, `started_at` 20 minutes ago, `description`, and `puroks` repeated with the ids of Purok Sambag and Purok Agoho.
Expected: `is_valid()` is `True`, `validated_data['puroks']` has 2 puroks, and `validated_data['location']` lies inside Purok Sambag.

- [ ] **Step 3: Restart the dev servers and ask the user to try it**

Restart the backend and frontend if they're running. Then ask the user to send one fire report with two puroks and check that:
- the map shows both pins,
- × removes one,
- "My reports" and the DRRMO dashboard list both puroks.
