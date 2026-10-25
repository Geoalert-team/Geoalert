# Fire Report Form Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When barangay personnel report a fire, the form asks only when and where (the BFP log's columns A–F): start time, a required pin, and the purok (picked from the pin, or typed when it isn't on the list), plus description and photos.

**Architecture:** Three new fields on `IncidentReport` (`started_at`, `purok`, `purok_other`). Fire-only rules live in one pure backend function, `fire_report_errors`, which the create serializer calls when the hazard type is Fire. On the frontend, the form's decisions (validation, payload, purok options, labels) live in a plain module, `fireReport.js`, which the barangay dashboard uses. Both are tested without a database or a browser. Other hazard types keep today's form.

**Tech Stack:** Django 4.2 + GeoDjango + DRF (backend, `SimpleTestCase`), React 18 with react-scripts 5 / Jest (frontend).

**Spec:** `docs/superpowers/specs/2026-10-25-report-driven-fire-hazards-design.md`. This plan covers "Data model › IncidentReport" (`started_at`, `purok`, `purok_other`) and "Design › 1. Submitting a fire report", plus showing the start time and purok wherever reports are listed. The DRRMO decision, tracker, fire out / close, map and history panel are later plans.

## Global Constraints

- Only Fire reports change. Flood, Landslide and other types keep today's fields, including "How serious is it?".
- Reports are still submitted only by barangay personnel; permissions are unchanged.
- New `incident_report` columns use the `incr_` prefix.
- **A new NOT NULL text column also gets a database default `''` in its migration.** Code from other branches still writes to the shared database, and Django drops a column's default after adding it.
- Nothing is written to the shared database (`migrate`) without the user's OK at that moment. Nothing is pushed.
- Messages (the backend and frontend use the same words):
  - `started_at`: `Say when the fire started.` / `The start time can't be in the future.`
  - `location`: `Drop a pin where the fire is.` / `The pin is outside Barangay {name}.`
  - `purok`: `That purok is not in Barangay {name}.` / `Choose the purok or sitio, or pick 'Not on the list' and type its name.` / `Choose a purok from the list or type one, not both.`
- Tolerances:
  - A start time up to 5 minutes ahead of the server clock is accepted, to allow for phone clocks.
  - A pin up to 0.001° (about 110 m) outside the barangay's boundary is accepted, because the PSA lines are approximate.

## Review Focus

- **A barangay with no puroks loaded:** the purok is optional and the form still submits. Tests: Task 2 `test_no_puroks_means_no_purok_needed`, Task 3 `validateReport … hasPuroks false`.
- **A pin just over an inaccurate barangay line (≤ 110 m):** accepted. Test: Task 2 `test_pin_is_required_and_inside_the_barangay`.
- **A phone clock a few minutes fast:** "now" is not rejected as the future. Tests: Task 2 `test_start_time_is_required_and_not_in_the_future` (+2 min passes), Task 3 the same in `validateReport`.
- **Switching from Fire to Flood after filling the fire fields:** the flood report sends no `started_at` or `purok`, and asks for severity again. Test: Task 3 `reportPayload` for a non-fire report.
- **Code from other branches writing reports after the migration:** `incr_purok_other` has a database default. Test: Task 1 `test_purok_other_has_a_database_default`.

---

### Task 1: Report fields and migration

**Files:**
- Modify: `backend/apps/reports/models.py` (`IncidentReport`)
- Create: `backend/apps/reports/migrations/0005_fire_report_fields.py` (from `makemigrations reports --name fire_report_fields`, then add the `RunSQL` below)
- Modify: `backend/apps/reports/serializers.py` (`IncidentReportSerializer`: output fields)
- Test: `backend/tests/test_reports_fire_fields.py`

**Interfaces:**
- Produces:

  | Field | Definition |
  |---|---|
  | `started_at` | `DateTimeField(null=True, blank=True, db_column='incr_started_at')` |
  | `purok` | `ForeignKey(Purok, on_delete=SET_NULL, null=True, blank=True, related_name='incident_reports', db_column='incr_prk_id')` |
  | `purok_other` | `CharField(max_length=100, blank=True, default='', db_column='incr_purok_other')` |

  - `IncidentReportSerializer` outputs `started_at`, `purok`, `purok_name` (`CharField(source='purok.name', read_only=True, default=None)`) and `purok_other`.

- [ ] **Step 1: Write the failing tests**

```python
class FireReportFieldsTests(SimpleTestCase):
    def test_purok_other_has_a_database_default(self):
        migration = import_module('apps.reports.migrations.0005_fire_report_fields').Migration
        sql = ' '.join(op.sql for op in migration.operations if isinstance(op, migrations.RunSQL))
        self.assertIn("ALTER COLUMN incr_purok_other SET DEFAULT ''", sql)

    def test_report_output_carries_start_time_and_place(self):
        fields = set(IncidentReportSerializer.Meta.fields)
        self.assertTrue({'started_at', 'purok', 'purok_name', 'purok_other'} <= fields)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run (from `backend/`): `venv/Scripts/python.exe manage.py test tests.test_reports_fire_fields`
Expected: ERROR or FAIL (no migration 0005; fields missing).

- [ ] **Step 3: Add the fields, generate the migration, add the default, extend the output serializer**

Run: `venv/Scripts/python.exe manage.py makemigrations reports --name fire_report_fields`. Then append to its operations:

`migrations.RunSQL("ALTER TABLE incident_report ALTER COLUMN incr_purok_other SET DEFAULT ''", "ALTER TABLE incident_report ALTER COLUMN incr_purok_other DROP DEFAULT")`

Add a comment explaining why, like the one in `apps/history/migrations/0004_bfp_text_defaults.py`.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `venv/Scripts/python.exe manage.py test tests.test_reports_fire_fields`
Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add backend/apps/reports/models.py backend/apps/reports/migrations/0005_fire_report_fields.py backend/apps/reports/serializers.py backend/tests/test_reports_fire_fields.py
git commit -m "Add start time and purok to incident reports"
```

---

### Task 2: Fire report rules on the server

**Files:**
- Create: `backend/apps/reports/fire_report.py`
- Modify: `backend/apps/reports/serializers.py` (`IncidentReportCreateSerializer`: fields and `validate`)
- Test: `backend/tests/test_fire_report.py`

**Interfaces:**
- Consumes: Task 1's fields.
- Produces:
  - `fire_report_errors(attrs: dict, barangay, has_puroks: bool, now: datetime) -> dict[str, str]`
    - `attrs` holds `started_at`, `location` (a `Point` or `None`), `purok` (an object with `barangay_id`, or `None`) and `purok_other` (str).
    - `barangay` has `.id`, `.name` and `.boundary`.
    - Returns `{}` when the report is fine.
  - Constants `CLOCK_SKEW = timedelta(minutes=5)` and `PIN_TOLERANCE_DEG = 0.001`.

- [ ] **Step 1: Write the failing tests**

`BRGY` is a `FakeBarangay(19, 'San Roque', square(123.85, 10.25, 123.86, 10.26))`, using `square` as in `test_load_puroks.py`. `NOW = datetime(2026, 10, 25, 14, 0, tzinfo=ZoneInfo('Asia/Manila'))`. `ok(**kw)` returns a valid `attrs`:
- `started_at=NOW - 1h`
- `location=Point(123.855, 10.255, srid=4326)`
- `purok=FakePurok(barangay_id=19)`
- `purok_other=''`

`kw` overrides any of these.

```python
def test_a_complete_fire_report_has_no_errors(self):
    self.assertEqual(fire_report_errors(ok(), BRGY, True, NOW), {})

def test_start_time_is_required_and_not_in_the_future(self):
    self.assertEqual(fire_report_errors(ok(started_at=None), BRGY, True, NOW), {'started_at': 'Say when the fire started.'})
    self.assertEqual(fire_report_errors(ok(started_at=NOW + timedelta(minutes=10)), BRGY, True, NOW),
                     {'started_at': "The start time can't be in the future."})
    self.assertEqual(fire_report_errors(ok(started_at=NOW + timedelta(minutes=2)), BRGY, True, NOW), {})

def test_pin_is_required_and_inside_the_barangay(self):
    self.assertEqual(fire_report_errors(ok(location=None), BRGY, True, NOW), {'location': 'Drop a pin where the fire is.'})
    self.assertEqual(fire_report_errors(ok(location=Point(123.90, 10.255, srid=4326)), BRGY, True, NOW),
                     {'location': 'The pin is outside Barangay San Roque.'})
    self.assertEqual(fire_report_errors(ok(location=Point(123.8605, 10.255, srid=4326)), BRGY, True, NOW), {})  # ~55 m out

def test_purok_must_be_in_the_barangay(self):
    self.assertEqual(fire_report_errors(ok(purok=FakePurok(barangay_id=7)), BRGY, True, NOW),
                     {'purok': 'That purok is not in Barangay San Roque.'})

def test_one_of_purok_or_a_typed_name(self):
    self.assertEqual(fire_report_errors(ok(purok=None), BRGY, True, NOW),
                     {'purok': "Choose the purok or sitio, or pick 'Not on the list' and type its name."})
    self.assertEqual(fire_report_errors(ok(purok_other='Purok Boongon'), BRGY, True, NOW),
                     {'purok': 'Choose a purok from the list or type one, not both.'})
    self.assertEqual(fire_report_errors(ok(purok=None, purok_other='Purok Boongon'), BRGY, True, NOW), {})

def test_no_puroks_means_no_purok_needed(self):
    self.assertEqual(fire_report_errors(ok(purok=None), BRGY, False, NOW), {})
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `venv/Scripts/python.exe manage.py test tests.test_fire_report`
Expected: an ERROR, because `apps.reports.fire_report` doesn't exist.

- [ ] **Step 3: Implement `fire_report_errors` and wire it into the create serializer**

- `fire_report_errors` returns at most one message per key, checking in the order of the tests above. The pin check is `barangay.boundary.buffer(PIN_TOLERANCE_DEG).contains(location)`.
- In `IncidentReportCreateSerializer`:
  - Add `'started_at'`, `'purok'` and `'purok_other'` to `Meta.fields`.
  - At the end of `validate`, when `attrs['hazard_type']` is named Fire (case-insensitive) and `attrs['barangay']` is set, `purok_other` is stripped and errors come from `fire_report_errors(attrs, attrs['barangay'], Purok.objects.filter(barangay=attrs['barangay']).exists(), timezone.now())`.
  - Any errors are raised as `serializers.ValidationError(errors)`. The existing city check stays and runs first.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `venv/Scripts/python.exe manage.py test tests.test_fire_report tests.test_reports_fire_fields`
Expected: `OK`

- [ ] **Step 5: Check the serializer against the database without saving**

Run: `venv/Scripts/python.exe manage.py shell -c "from apps.reports.serializers import IncidentReportCreateSerializer as S; from apps.hazards.models import HazardType; from apps.barangays.models import Barangay; b=Barangay.objects.get(name='San Roque'); s=S(data={'barangay': b.id, 'hazard_type': HazardType.objects.get(name__iexact='Fire').id, 'description': 'Smoke from a house near the chapel'}); print(s.is_valid(), dict(s.errors))"`

Expected: `False` and errors for `started_at` and `location`. (This is valid only after Task 1's migration is applied locally. If the shared database hasn't been migrated yet, do this step after Task 4's migration step.)

- [ ] **Step 6: Commit**

```bash
git add backend/apps/reports/fire_report.py backend/apps/reports/serializers.py backend/tests/test_fire_report.py
git commit -m "Check fire reports for start time, pin and purok"
```

---

### Task 3: Form decisions on the frontend

**Files:**
- Create: `frontend/src/pages/Dashboard/fireReport.js`
- Test: `frontend/src/pages/Dashboard/fireReport.test.js`

**Interfaces:**
- Consumes: `puroksOf` and `purokAt` from `components/Map/purokStyle.js`. Purok GeoJSON features carry the purok id as `feature.id` and `properties.name` / `properties.barangay`.
- Produces:
  - `NOT_LISTED = 'other'`
  - `isFireType(hazardTypes: Array<{id, name}>, id: string|number) -> boolean`
  - `localNow(now = new Date()) -> string`: a `datetime-local` value, `YYYY-MM-DDTHH:mm`, in local time
  - `purokOptions(geo, barangayId) -> Array<{id: string, label: string}>`: named puroks A–Z, then "Unnamed area k" in number order, each labelled `Unnamed area k (no name yet)`
  - `purokAtPin(geo, barangayId, location: [lat, lng] | null) -> string | null`
  - `validateReport(form, { fire, hasPuroks, now = new Date() }) -> object`: field → message. It covers the existing checks (`barangay`, `hazard_type`, `description` ≥ 10 characters) and, for fire, `started_at`, `location` and `purok`; for other types, `severity_estimate`. Messages are in Global Constraints. The existing non-fire messages are kept word for word from `BarangayDashboard.validate`.
  - `reportPayload(form, { fire }) -> object`: the argument object for `reportsApi.submit`, without photos
  - `placeLabel(report) -> string | null`: `report.purok_name`, or `` `${report.purok_other} (not on the list)` ``, or `null`

- [ ] **Step 1: Write the failing tests**

```js
const square = (id, name, barangay, x0, y0) => ({ type: 'Feature', id, properties: { name, barangay },
  geometry: { type: 'Polygon', coordinates: [[[x0, y0], [x0 + 0.01, y0], [x0 + 0.01, y0 + 0.01], [x0, y0 + 0.01], [x0, y0]]] } });
const GEO = { type: 'FeatureCollection', features: [
  square(5, 'Unnamed area 10', 19, 123.80, 10.20), square(3, 'Purok Sambag', 19, 123.85, 10.25),
  square(4, 'Unnamed area 2', 19, 123.82, 10.20), square(6, 'Purok Agoho', 19, 123.86, 10.25), square(7, 'Kimba', 8, 123.90, 10.30)] };
const FIRE = { barangay: '19', hazard_type: '2', description: 'Smoke from a house near the chapel',
  started_at: '2026-10-25T13:00', location: [10.255, 123.855], purok: '3', purok_other: '', severity_estimate: '' };
const NOW = new Date('2026-10-25T14:00');

test('purok options: named first A-Z, then unnamed areas by number', () => {
  expect(purokOptions(GEO, '19').map((o) => o.label)).toEqual(
    ['Purok Agoho', 'Purok Sambag', 'Unnamed area 2 (no name yet)', 'Unnamed area 10 (no name yet)']);
});
test('the pin picks its purok, only in the right barangay', () => {
  expect(purokAtPin(GEO, '19', [10.255, 123.855])).toBe('3');
  expect(purokAtPin(GEO, '19', [10.305, 123.905])).toBeNull();
  expect(purokAtPin(GEO, '19', null)).toBeNull();
});
test('a complete fire report passes; each missing part is named', () => {
  expect(validateReport(FIRE, { fire: true, hasPuroks: true, now: NOW })).toEqual({});
  expect(validateReport({ ...FIRE, location: null }, { fire: true, hasPuroks: true, now: NOW }).location).toBe('Drop a pin where the fire is.');
  expect(validateReport({ ...FIRE, started_at: '2026-10-25T14:10' }, { fire: true, hasPuroks: true, now: NOW }).started_at)
    .toBe("The start time can't be in the future.");
  expect(validateReport({ ...FIRE, started_at: '2026-10-25T14:02' }, { fire: true, hasPuroks: true, now: NOW })).toEqual({});
  expect(validateReport({ ...FIRE, purok: NOT_LISTED, purok_other: ' ' }, { fire: true, hasPuroks: true, now: NOW }).purok)
    .toBe("Choose the purok or sitio, or pick 'Not on the list' and type its name.");
  expect(validateReport({ ...FIRE, purok: '' }, { fire: true, hasPuroks: false, now: NOW })).toEqual({});
  expect(validateReport(FIRE, { fire: true, hasPuroks: true, now: NOW }).severity_estimate).toBeUndefined();
});
test('other hazards still ask how serious it is', () => {
  expect(validateReport({ ...FIRE, location: null }, { fire: false, hasPuroks: true, now: NOW }))
    .toEqual({ severity_estimate: 'Choose how serious it looks.' });
});
test('payload: fire sends start time and place; other types send neither', () => {
  const fire = reportPayload({ ...FIRE, purok: NOT_LISTED, purok_other: ' Purok Boongon ' }, { fire: true });
  expect(fire).toMatchObject({ barangay: 19, hazard_type: 2, purok_other: 'Purok Boongon', location: [10.255, 123.855] });
  expect(fire.started_at).toBe(new Date('2026-10-25T13:00').toISOString());
  expect(fire).not.toHaveProperty('purok');
  expect(fire).not.toHaveProperty('severity_estimate');
  expect(reportPayload(FIRE, { fire: true }).purok).toBe(3);
  const flood = reportPayload({ ...FIRE, severity_estimate: 'Moderate' }, { fire: false });
  expect(flood.severity_estimate).toBe('Moderate');
  ['started_at', 'purok', 'purok_other'].forEach((k) => expect(flood).not.toHaveProperty(k));
});
test('place label', () => {
  expect(placeLabel({ purok_name: 'Purok Sambag', purok_other: '' })).toBe('Purok Sambag');
  expect(placeLabel({ purok_name: null, purok_other: 'Purok Boongon' })).toBe('Purok Boongon (not on the list)');
  expect(placeLabel({ purok_name: null, purok_other: '' })).toBeNull();
});
test('localNow is a datetime-local value', () => {
  expect(localNow(new Date(2026, 9, 25, 9, 5))).toBe('2026-10-25T09:05');
});
```

`reportPayload` carries `position`, `agency` and `location` through unchanged. The test `FIRE` has neither `position` nor `agency`, and `toMatchObject` ignores them.

- [ ] **Step 2: Run the tests to verify they fail**

Run (from `frontend/`): `CI=true npx react-scripts test --watchAll=false src/pages/Dashboard/fireReport.test.js`
Expected: FAIL, because `./fireReport` can't be found.

- [ ] **Step 3: Implement `fireReport.js`**

Write the exports listed under Interfaces.

- [ ] **Step 4: Run the tests to verify they pass**

Run: the command from Step 2
Expected: `Tests: 7 passed`

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/Dashboard/fireReport.js frontend/src/pages/Dashboard/fireReport.test.js
git commit -m "Decide the fire report form's fields, checks and payload"
```

---

### Task 4: The form, the API call and where reports are shown

**Files:**
- Modify: `frontend/src/api/reportApi.js` (`submit`)
- Modify: `frontend/src/pages/Dashboard/BarangayDashboard.jsx` (`emptyForm`, data loading, `validate` and `submit`, the form's step 1 and step 2, the "My reports" meta line)
- Modify: `frontend/src/pages/Dashboard/DRRMODashboard.jsx` (`ReportRow` meta line, `ReportDetail` "Submission details")

**Interfaces:**
- Consumes: everything in Task 3's Produces list; Task 1's output fields `started_at`, `purok_name` and `purok_other`; `barangaysApi.puroks()`.

- [ ] **Step 1: `reportsApi.submit` passes the new fields through**

Add `started_at = null`, `purok = null` and `purok_other = ''` to the parameters. Each goes in the body only when it is non-empty, the same way `location` is handled today, so the JSON and multipart paths both carry them.

- [ ] **Step 2: Wire the form**

- `emptyForm` adds `started_at: localNow()`, `purok: ''` and `purok_other: ''`. Load `barangaysApi.puroks()` once into `purokGeo`, with a fallback to `null` on error.
- Work out:
  - `fire = isFireType(hazardTypes, form.hazard_type)`
  - `options = purokOptions(purokGeo, form.barangay)`
  - `hasPuroks = options.length > 0`
- **When `fire`:**
  - Step 1 shows **When it started** (`<input type="datetime-local" max={localNow()}>`, required).
  - The pin label loses "optional", and its hint becomes *"Drop a pin where the fire is."*
  - **Purok / Sitio**: a `<select>` of `options` plus `<option value={NOT_LISTED}>Not on the list…</option>`. When `NOT_LISTED` is chosen, a text input (max 100) follows, placeholder *"Name of the purok or sitio"*.
  - The select appears only when `hasPuroks`. Without puroks, only the text input shows, marked optional.
  - The pin's `onChange` also sets `purok` to `purokAtPin(purokGeo, form.barangay, v)` when that isn't null.
  - The "How serious is it?" block is not rendered.
- `validate()` returns `validateReport(form, { fire, hasPuroks })`. `submit` calls `reportsApi.submit({ ...reportPayload(form, { fire }), photos: photos.map((p) => p.file) })`. After a successful send, the form reset keeps today's behaviour, with `started_at` set to a fresh `localNow()`.
- The description placeholder for fire is *"What is burning, how big it is, whether it is spreading, and what help is needed."*

- [ ] **Step 3: Show the start time and place**

- In "My reports" and DRRMO's `ReportRow` meta lines, add `<span>Started {formatDateTime(r.started_at)}</span>` when `started_at` is set, and `<span>{placeLabel(r)}</span>` when it isn't null.
- In `ReportDetail` "Submission details", add `<dt>Started</dt>` and `<dt>Purok / Sitio</dt>` rows with the same values.

- [ ] **Step 4: Run the frontend tests and the build**

Run (from `frontend/`):
- `CI=true npx react-scripts test --watchAll=false`
- `npx react-scripts build`

Expected: all suites pass, and the build ends with `Compiled successfully` or only warnings that already existed. Compare the warnings against a build on the base commit if any appear.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/reportApi.js frontend/src/pages/Dashboard/BarangayDashboard.jsx frontend/src/pages/Dashboard/DRRMODashboard.jsx
git commit -m "Fire report form: when it started, pin and purok; show them on reports"
```

- [ ] **Step 6: Migrate the shared database (with the user's OK) and try it**

Ask the user, then run (from `backend/`): `venv/Scripts/python.exe manage.py migrate reports`
Expected: `Applying reports.0005_fire_report_fields... OK`

Then run Task 2, Step 5's check. Ask the user to submit one fire report from a barangay personnel account and confirm that:
- the purok is pre-selected from the pin,
- "Not on the list" asks for a name,
- the report shows its start time and purok in "My reports" and on the DRRMO dashboard.
