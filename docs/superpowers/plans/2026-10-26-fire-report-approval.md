# Fire Report Approval Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A DRRMO officer decides a fire report in one step: approve it as a new fire, attach it to a nearby active fire, or reject it. An approved fire goes live on the public map as a pin at each of its puroks, at a level that starts from those puroks' fire history.

**Architecture:**
- **Pure modules carry the rules**, each tested without a database:
  - `apps/history/purok_levels.py`: levels from history
  - `apps/reports/decide.py`: pins, the fire's shape, nearby fires, the level choice and whether a report can still be decided
- **One view orchestrates them**, using the existing alert machinery: `issue_alert`, `needs_second_approval` / `approvers_for`, `request_raise` / `apply_raise`, `notify`, `log_event`.
- **The public map draws pins** for fires made from reports.

**Tech Stack:** Django 4.2 + GeoDjango + DRF, React 18 + react-leaflet, Jest.

**Spec:** `docs/superpowers/specs/2026-10-25-report-driven-fire-hazards-design.md`:
- section 3 "The DRRMO decision"
- section 5 "Pins on the map" (pins only, without the related-pin badge)
- the Decisions rows "Alert level" and "Extreme"
- change 3 in "Changes to the hazard-levels spec": the level for a set of puroks

The rest of the hazard-levels work is out of scope: purok shading and the publish-panel level.

## Global Constraints

- **No commits.** The user said "dont commit anything yet". Every commit step is replaced by leaving the change in the working tree.
- **Nothing is written to the shared database** without the user's OK at that moment. Dry runs go inside a transaction that is rolled back.
- **Levels:**
  - Codes are `Green`, `Orange` and `Red`, with the labels Low, Moderate and Extreme.
  - The settings are `history.period_years` (5, range 1–20), `history.moderate_at` (3, range 2–50) and `history.extreme_at` (5, range 3–100).
  - 0 past fires means no level. Puroks with no history count as Low.
- **Fire shape:** a 25 m circle round each pin, used only to find which barangays to alert. "Nearby" means within 500 m.
- **Messages:**

  | Situation | Message |
  |---|---|
  | Level below history | `Can't be lower than {Label}: this purok's history sets it.` |
  | Report already decided | `Already decided by {name} at {HH:MM}.` |
  | Attaching to a closed fire | `That fire is no longer active.` |
  | Reject without a note | `Say why the report is rejected.` |
  | Fire report sent to the old review endpoint | `Fire reports are approved or rejected with the fire decision.` |

- **Reports that can be decided:**
  - `Pending` fire reports.
  - `Validated` fire reports with no zone, which were validated under the old flow. These can still be approved or attached.

## Review Focus

- **The user's existing report, validated under the old flow:** it can be approved and then appears on the map. Covered by `decision_error` with `status='Validated', hazard_zone_id=None`, and by the Task 6 dry run.
- **Two officers decide the same report:** the second gets "Already decided …", not a second fire. Test: Task 2, `test_a_decided_report_cannot_be_decided_again`.
- **Extreme history with another officer on duty:** the zone waits for approval and is not on the public map. Covered by the Task 6 dry run (status `Awaiting_Approval` when approvers exist) and `choose_level` tests.
- **Pins for a report whose barangay has no puroks:** the fire uses the report's location. Test: Task 2, `test_pins_fall_back_to_the_report_location`.
- **Public map:** a report-made fire draws pins only, with no terrain shading and no outline. Test: Task 5, `markerSpots` and `drawsShading`.

---

### Task 1: Levels from purok history

**Files:**
- Create: `backend/apps/history/purok_levels.py`
- Modify: `backend/utils/system_settings.py` (three entries)
- Modify: `frontend/src/pages/Dashboard/admin/SettingsTab.jsx` (group `{ prefix: 'history.', title: 'Hazard levels from history' }`)
- Test: `backend/tests/test_purok_levels.py`

**Interfaces:**
- Produces:
  - `RANK = {'Green': 1, 'Orange': 2, 'Red': 3}` and `LABEL = {'Green': 'Low', 'Orange': 'Moderate', 'Red': 'Extreme'}`
  - `thresholds() -> {'years': int, 'moderate': int, 'extreme': int}`: read through `get_setting`. If `extreme <= moderate`, all three defaults are used.
  - `level_for(count: int, t: dict) -> str | None`
  - `highest(levels) -> str`: the highest code, or `'Green'` when there is none (`None` entries are ignored)
  - `purok_levels(purok_ids, hazard_type, now) -> dict[int, {'count': int, 'level': str | None}]`: counts `HistoricalRecord` rows of that hazard type through `puroks`, with `occurred_at >= now - years*365 days`. Every id is present, with count 0 when it has no history.

- [ ] **Step 1: Write the failing tests**

```python
T = {'years': 5, 'moderate': 3, 'extreme': 5}

def test_level_for_each_boundary(self):
    self.assertEqual([level_for(n, T) for n in range(7)], [None, 'Green', 'Green', 'Orange', 'Orange', 'Red', 'Red'])

def test_contradicting_settings_fall_back_to_the_defaults(self):
    values = {'history.period_years': 2, 'history.moderate_at': 6, 'history.extreme_at': 4}
    with mock.patch('apps.history.purok_levels.get_setting', side_effect=values.get):
        self.assertEqual(thresholds(), {'years': 5, 'moderate': 3, 'extreme': 5})

def test_settings_are_used_when_they_agree(self):
    values = {'history.period_years': 3, 'history.moderate_at': 2, 'history.extreme_at': 4}
    with mock.patch('apps.history.purok_levels.get_setting', side_effect=values.get):
        self.assertEqual(thresholds(), {'years': 3, 'moderate': 2, 'extreme': 4})

def test_highest(self):
    self.assertEqual(highest(['Green', 'Red', 'Orange']), 'Red')
    self.assertEqual(highest([None, 'Orange']), 'Orange')
    self.assertEqual(highest([]), 'Green')
```

- [ ] **Step 2: Run the tests to verify they fail**

Run (from `backend/`): `venv/Scripts/python.exe manage.py test tests.test_purok_levels`
Expected: an ERROR, because the module doesn't exist.

- [ ] **Step 3: Implement, add the settings and the Settings group**

`purok_levels.py` imports `get_setting` at module level, so the tests can patch it. The settings labels are:
- `History period for hazard levels`
- `Past events for orange (Moderate)`
- `Past events for red (Extreme)`

- [ ] **Step 4: Run the tests to verify they pass**

Run: the command from Step 2
Expected: `OK`

---

### Task 2: Decision rules

**Files:**
- Create: `backend/apps/reports/decide.py`
- Test: `backend/tests/test_fire_decision.py`

**Interfaces:**
- Consumes: `RANK` and `LABEL` (Task 1)
- Produces:
  - `PIN_RADIUS_M = 25`, `NEARBY_M = 500`
  - `report_pins(report) -> list[Point]`: `point_on_surface` of each of `report.puroks.all()`, or else `[report.location]` when set, or else `[]`
  - `fire_geometry(points, radius_m=PIN_RADIUS_M) -> MultiPolygon` (SRID 4326): each point is buffered by `radius_m` metres in EPSG:32651 (UTM 51N) and transformed back, then unioned
  - `is_nearby(geometry, points, metres=NEARBY_M) -> bool`: the distance is measured in EPSG:32651
  - `choose_level(history_level: str, requested: str | None) -> tuple[str | None, str | None]`: returns `(level, error)`
  - `decision_error(report) -> str | None`:
    - `'Only fire reports are decided here.'` for a type other than Fire
    - `'Already decided by {name} at {HH:MM}.'` (Asia/Manila time) when the report is `Rejected`, or `Validated` with a `hazard_zone_id`
    - `None` otherwise

- [ ] **Step 1: Write the failing tests**

Fakes:
- `Fake(**kw)`
- `puroks` is an object whose `.all()` returns a list
- `square` is as in the other tests
- the points `A = Point(123.85, 10.25)` and `B = Point(123.86, 10.25)`, about 1.1 km apart

```python
def test_pins_are_the_puroks_centres(self):
    sambag = Fake(boundary=square(123.85, 10.25, 123.855, 10.255))
    pins = report_pins(Fake(puroks=Puroks([sambag]), location=Point(1, 1, srid=4326)))
    self.assertEqual(len(pins), 1)
    self.assertTrue(sambag.boundary.contains(pins[0]))

def test_pins_fall_back_to_the_report_location(self):
    self.assertEqual(report_pins(Fake(puroks=Puroks([]), location=A)), [A])
    self.assertEqual(report_pins(Fake(puroks=Puroks([]), location=None)), [])

def test_fire_geometry_is_a_25_m_circle_per_pin(self):
    shape = fire_geometry([A, B])
    self.assertEqual(len(shape), 2)
    area = shape.transform(32651, clone=True).area
    self.assertAlmostEqual(area / (2 * math.pi * 25 ** 2), 1, delta=0.05)

def test_nearby_is_within_500_m(self):
    shape = fire_geometry([A])
    self.assertTrue(is_nearby(shape, [Point(123.8536, 10.25, srid=4326)]))    # ~390 m
    self.assertFalse(is_nearby(shape, [Point(123.8565, 10.25, srid=4326)]))   # ~710 m

def test_choose_level(self):
    self.assertEqual(choose_level('Orange', None), ('Orange', None))
    self.assertEqual(choose_level('Green', 'Red'), ('Red', None))
    self.assertEqual(choose_level('Orange', 'Green'), (None, "Can't be lower than Moderate: this purok's history sets it."))

def test_a_decided_report_cannot_be_decided_again(self):
    officer = Fake(full_name='Ana Cruz')
    at = datetime(2026, 10, 26, 0, 20, tzinfo=timezone.utc)   # 08:20 Manila
    fire = Fake(name='Fire')
    self.assertIsNone(decision_error(Fake(hazard_type=fire, status='Pending', hazard_zone_id=None)))
    self.assertIsNone(decision_error(Fake(hazard_type=fire, status='Validated', hazard_zone_id=None)))  # validated before this flow
    self.assertEqual(decision_error(Fake(hazard_type=fire, status='Validated', hazard_zone_id='z', reviewed_by=officer, reviewed_at=at)),
                     'Already decided by Ana Cruz at 08:20.')
    self.assertEqual(decision_error(Fake(hazard_type=Fake(name='Flood'), status='Pending', hazard_zone_id=None)),
                     'Only fire reports are decided here.')
```

The points `A` and `B` carry `srid=4326`.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `venv/Scripts/python.exe manage.py test tests.test_fire_decision`
Expected: an ERROR, because the module doesn't exist.

- [ ] **Step 3: Implement `decide.py`**

- [ ] **Step 4: Run the tests to verify they pass**

Run: the command from Step 2
Expected: `OK`

---

### Task 3: Decision endpoint, review refusal, zone pins

**Files:**
- Modify: `backend/apps/reports/views.py`:
  - new `IncidentReportDecideView`
  - `IncidentReportReviewView.patch` refuses Fire reports with 400 `{'error': …}`
- Modify: `backend/apps/reports/urls.py`: `path('incidents/<uuid:pk>/decide/', IncidentReportDecideView.as_view(), name='incident-decide')`
- Modify: `backend/apps/hazards/serializers.py`: `HazardZoneGeoSerializer.pins`
- Modify: `backend/apps/hazards/views.py`: `HazardZoneListView` adds `prefetch_related('incidentreport_set__puroks')`

**Interfaces:**
- Consumes: Tasks 1–2; `apps.hazards.alerts` (`issue_alert`, `needs_second_approval`, `approvers_for`, `approval_due_at`, `notify`, `affected_barangays`, `where_text`, `type_name`, `request_raise`, `apply_raise`); `utils.audit.log_event`.

**`GET /api/reports/incidents/<id>/decide/`** returns:

```
{
  "error": decision_error or null,
  "puroks": [{"id", "name", "count", "level"}],
  "level": highest of those levels,
  "thresholds": {...},
  "nearby": [{"id", "severity", "status", "activated_at", "reports": n, "puroks": [names]}]
}
```

`nearby` lists Fire zones in `Active` or `Awaiting_Approval` where `is_nearby(zone.geometry, report_pins(report))`.

**`POST /api/reports/incidents/<id>/decide/`** runs in one `transaction.atomic()`. When `decision_error` is set, it returns 409 `{'error': …}`.

- **`{"action": "approve", "severity"?: code, "note"?: str}`:**
  - `choose_level` returns any error as 400 `{'severity': …}`.
  - Creates a `HazardZone`:
    - `barangay`, `hazard_type` and `description` come from the report.
    - `published_by` is the officer and `severity` is the chosen level.
    - `geometry = fire_geometry(report_pins(report))`.
  - It is held when `needs_second_approval(level) and approvers_for(user).exists()`. The status is then `Awaiting_Approval`, and the approvers get the same notice text `HazardZoneCreateView` sends.
  - Otherwise the status is `Active` and `issue_alert(zone, user)` runs. For Red with no second officer, `auto_released=True` is set first.
  - The report gets `status='Validated'`, `hazard_zone=zone`, `reviewed_by`, `reviewed_at`, `validated_by`, `validated_at` and `review_note=note`.
  - `log_event(request, 'APPROVE_FIRE_REPORT', 'hazard_zone', zone.id, …)`.
  - Returns 201 `{'report': IncidentReportSerializer(...), 'zone': HazardZoneSerializer(zone).data, 'held': bool}`.
- **`{"action": "attach", "zone": id}`:**
  - The zone must be Fire and `Active` or `Awaiting_Approval`. Otherwise it returns 409 `That fire is no longer active.`
  - `before = affected_barangays(zone)`. The geometry becomes the union of the zone and `fire_geometry(report_pins(report))`, then it is saved.
  - Barangays newly reached are notified the way the reshape path does it, with the text `Fire alert ({severity}) now covers {where}: another report joined the fire. Tap to see it and what to do.`
  - When the report's history level is above the zone's severity:
    - a raise to Red with approvers available → `request_raise(zone, user)` and save
    - a raise to Red with no approvers → `apply_raise(zone, auto=True)` and `issue_alert(zone, user, suffix=' Raised to Extreme.')`
    - any other raise → set `severity`, `reset_verification()` and save
  - The report is linked as in approve, and `log_event` records `ATTACH_FIRE_REPORT`.
  - Returns 200 `{'report', 'zone'}`.
- **`{"action": "reject", "note": str}`:** a blank note gives 400 `{'note': 'Say why the report is rejected.'}`. Otherwise `status='Rejected'`, `review_note`, `reviewed_by` and `reviewed_at` are set, `log_event` records `REJECT_FIRE_REPORT`, and it returns 200 `{'report'}`.

**`HazardZoneGeoSerializer.pins`:** `[{lat, lng, purok_name}]`, one per distinct purok across `obj.incidentreport_set.all()`. A linked report with no puroks but a location gives `purok_name: None`. A zone not made from reports gives `[]`. Add `'pins'` to `Meta.fields`.

- [ ] **Step 1: Implement the view, URL, review refusal and serializer field**
- [ ] **Step 2: Run the backend tests**

Run: `venv/Scripts/python.exe manage.py test tests.test_fire_decision tests.test_purok_levels tests.test_fire_report tests.test_report_serializer_wiring tests.test_reports_fire_fields`
Expected: `OK`. Then `manage.py check`, expecting no issues.

---

### Task 4: DRRMO decision dialog

**Files:**
- Create: `frontend/src/pages/Dashboard/fireDecision.js`
- Test: `frontend/src/pages/Dashboard/fireDecision.test.js`
- Modify: `frontend/src/api/reportApi.js`: `decision(id)` (GET) and `decide(id, body)` (POST)
- Modify: `frontend/src/pages/Dashboard/DRRMODashboard.jsx`

**Interfaces:**
- Produces (in `fireDecision.js`):
  - `LEVELS = [{code: 'Green', label: 'Low'}, {code: 'Orange', label: 'Moderate'}, {code: 'Red', label: 'Extreme'}]`
  - `levelLabel(code) -> string`
  - `raiseOptions(historyLevel) -> LEVELS` at or above it
  - `isFireReport(report) -> boolean` (from `hazard_type_details.name`)
  - `canDecide(report) -> boolean`: a fire report that is `Pending`, or `Validated` with no `hazard_zone`
  - `historyLine(purok, years) -> string`, e.g. `'Purok Sambag: 3 fires in 5 years → Moderate'`, `'1 fire'` in the singular, or `'… no fires in 5 years → Low'`

- [ ] **Step 1: Write the failing tests**

```js
test('raise options start at the history level', () => {
  expect(raiseOptions('Orange').map((l) => l.code)).toEqual(['Orange', 'Red']);
  expect(raiseOptions('Green').map((l) => l.code)).toEqual(['Green', 'Orange', 'Red']);
});
test('which reports the fire decision takes', () => {
  const fire = { hazard_type_details: { name: 'Fire' } };
  expect(canDecide({ ...fire, status: 'Pending', hazard_zone: null })).toBe(true);
  expect(canDecide({ ...fire, status: 'Validated', hazard_zone: null })).toBe(true);
  expect(canDecide({ ...fire, status: 'Validated', hazard_zone: 'z' })).toBe(false);
  expect(canDecide({ hazard_type_details: { name: 'Flood' }, status: 'Pending' })).toBe(false);
});
test('history line', () => {
  expect(historyLine({ name: 'Purok Sambag', count: 3, level: 'Orange' }, 5)).toBe('Purok Sambag: 3 fires in 5 years → Moderate');
  expect(historyLine({ name: 'Purok Lubi', count: 1, level: 'Green' }, 5)).toBe('Purok Lubi: 1 fire in 5 years → Low');
  expect(historyLine({ name: 'Purok Pinya', count: 0, level: null }, 5)).toBe('Purok Pinya: no fires in 5 years → Low');
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run (from `frontend/`): `CI=true npx react-scripts test --watchAll=false src/pages/Dashboard/fireDecision.test.js`
Expected: FAIL (module missing).

- [ ] **Step 3: Implement the helpers and the dialog**

`FireDecisionDialog({ report, onCancel, onDone })` in `DRRMODashboard.jsx`:
- **On open:** loads `reportsApi.decision(report.id)`. While loading it shows "Loading…". If the load fails, it shows "Couldn't load the fire's history. Try again." with a retry button.
- **Body:**
  - one `historyLine` per purok
  - **Level**: radios from `raiseOptions(level)`, pre-set to `level`
  - **Fires nearby**: each with "Attach to this fire" (shown only when `nearby` isn't empty)
  - **Note**: a textarea, required for Reject
- **Footer:** Cancel, Reject (danger) and **Approve as new fire** (primary).
- **Errors:** server errors (409, 400) show in the dialog.
- **On success:** `onDone(message)`, with one of:
  - `Fire approved: it is on the map.`
  - `Fire approved: waiting for a second officer.`
  - `Report attached to the fire.`
  - `Report rejected.`

Wiring:
- For reports where `canDecide`, the Validate / Reject buttons (row and detail) open this dialog instead of `ReviewDialog`.
- A `Validated` fire report with no zone shows **Approve to map** in the detail footer in place of "Publish hazard here".
- Fire reports never show "Publish hazard here".

- [ ] **Step 4: Run the frontend tests**

Run: `CI=true npx react-scripts test --watchAll=false`
Expected: all pass.

---

### Task 5: Pins on the public map

**Files:**
- Create: `frontend/src/components/Map/hazardPins.js`
- Test: `frontend/src/components/Map/hazardPins.test.js`
- Modify: `frontend/src/pages/PublicMap.jsx`:
  - `featureToItem` adds `pins: p.pins || []`
  - shading and outlines use only items where `drawsShading`
  - markers come from `markerSpots`

**Interfaces:**
- Produces:
  - `markerSpots(item) -> [{key, position: [lat, lng], purok: string | null}]`: one per pin when `item.pins` isn't empty (key `${item.id}:${i}`), otherwise one at `item.position` (key `item.id`)
  - `drawsShading(item) -> boolean`: `true` when the item has no pins

- [ ] **Step 1: Write the failing tests**

```js
test('a report-made fire is one marker per purok, no shading', () => {
  const fire = { id: 'z', position: [10, 123], pins: [{ lat: 10.1, lng: 123.1, purok_name: 'Purok Sambag' }, { lat: 10.2, lng: 123.2, purok_name: null }] };
  expect(markerSpots(fire)).toEqual([
    { key: 'z:0', position: [10.1, 123.1], purok: 'Purok Sambag' },
    { key: 'z:1', position: [10.2, 123.2], purok: null }]);
  expect(drawsShading(fire)).toBe(false);
});
test('a drawn zone keeps one marker and its shading', () => {
  const flood = { id: 'f', position: [10, 123], pins: [] };
  expect(markerSpots(flood)).toEqual([{ key: 'f', position: [10, 123], purok: null }]);
  expect(drawsShading(flood)).toBe(true);
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `CI=true npx react-scripts test --watchAll=false src/components/Map/hazardPins.test.js`
Expected: FAIL.

- [ ] **Step 3: Implement and wire it in**

- Each marker uses the existing `pinIcon(h, …)` and click handler.
- `title` is `` `${spot.purok || h.location}: ${h.type}, ${severityInfo(h.severity).label}` ``.
- `useHazardLevelLayer` and `zoneOutlines` get `hazards.filter(drawsShading)` / `visibleHazards.filter(drawsShading)`.

- [ ] **Step 4: Run all frontend tests and the build**

Run: `CI=true npx react-scripts test --watchAll=false`, then `npx react-scripts build`.
Expected: all pass, and the build shows no warnings beyond the existing "Unicode BOM" ones.

---

### Task 6: Check against the database, then the user tries it

- [ ] **Step 1: Dry run (rolled back)**

In `manage.py shell`, inside `transaction.atomic()` with `transaction.set_rollback(True)` at the end:
- Call `IncidentReportDecideView` through `APIRequestFactory` for the user's Validated Jaclupan fire report:
  - first GET,
  - then POST `approve` as a DRRMO officer from the database.
- Print the GET payload, the POST status code, `zone.status`, `HazardZoneGeoSerializer(zone).data['properties']['pins']` and the number of alert notifications created.

Expected:
- GET `error` is null, and `level` is `Green` (no history in Jaclupan's puroks).
- POST gives 201. The zone is `Active`, or `Awaiting_Approval` only for Red.
- There's one pin, at Purok Sambag.
- After the rollback, `HazardZone.objects.count()` is unchanged.

- [ ] **Step 2: Restart the dev servers and ask the user to approve their report from the DRRMO dashboard**

The user should then see it on the public map as a pin at Purok Sambag. Approving in the UI is the user's own action on the shared database.
