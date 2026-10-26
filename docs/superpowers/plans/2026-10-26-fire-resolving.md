# Fire Resolving Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Resolving a fire takes two steps. **Fire out** sends the all-clear and takes the pin off the map. **Enter BFP figures** then fills columns G onward of the BFP fire log and closes the fire into one history record, which adds +1 to each of its puroks. The history page shows those figures, and staff can export fires as an Excel file in the BFP layout.

**Architecture:**
- **Pure backend functions** hold the BFP lists, check the close form and build its record fields, and build the BFP workbook. They are tested without a database.
- **Small views** do the status changes, the alerts, the history record and the download, with database-backed tests.
- **On the frontend:**
  - `ResolveHazardForm` turns into the Fire-out form for fire zones, so the map panel and the active-zones card both pick it up.
  - A "Waiting for BFP figures" card on the DRRMO dashboard holds the close form.
  - The history page gets the fire columns and the export button.

**Tech Stack:** Django 4.2 + GeoDjango + DRF, openpyxl 3.1.5, React 18, Jest.

**Spec:** `docs/superpowers/specs/2026-10-25-report-driven-fire-hazards-design.md`:
- "Data model" (`HazardZone` status `Resolving`, `fire_out_at` / `fire_out_by`; the `HistoricalRecord` fields)
- section 4 "Fire out and closing"
- section 7 "Fire history and the BFP export"

## Global Constraints

- **No commits** (the user's standing instruction). Each commit step means: leave the change in the working tree.
- **The shared database** (`migrate`) is touched only with the user's OK at that moment. Dry runs go in rolled-back transactions.
- **Fire zones only.** Floods and landslides keep "Resolve and archive" exactly as now.
- **Blank means not counted**, never 0, in the form, the record and the export.
- **The BFP lists live only in `apps/history/bfp.py`:**
  - `PROPERTY_TYPES`:
    - `RESIDENTIAL`: [`SINGLE AND TWO FAMILY DWELLING`]
    - `NON_RESIDENTIAL`: [`BUSINESS`, `MERCANTILE`, `STORAGE`, `HEALTH CARE`, `ASSEMBLY`, `EDUCATIONAL`, `INDUSTRIAL`, `MISCELLANEOUS`]
    - `NON_STRUCTURAL`: [`RUBBISH`, `GRASS`, `ELECTRICAL POLE`]
    - `TRANSPORT`: [`AUTOMOBILE`, `MOTORCYCLE`, `TRUCK`, `BUS`, `TRICYCLE`, `JEEPNEY`, `LOCOMOTIVE`]
  - `ALARM_LEVELS`: `FIRE OUT UPON ARRIVAL`, `1ST ALARM` … `5TH ALARM`, `TF ALPHA` … `TF ECHO`, `GENERAL ALARM`, `UNRESPONDED`
- **Messages:**
  - `Choose the alarm level.`
  - `Choose the property type.`
  - `Enter a whole number, 0 or more.`
  - `Enter an amount in pesos, 0 or more.`
  - `Only an active fire can be put out.`
  - `Only a fire that is out can be closed.`
  - `Fire zones are closed with Fire out, then the BFP figures.`

## Review Focus

- **Blank counts survive end to end.** A count left blank in the form stays `null` in the record and an empty cell in the export. Tests: Task 1 `test_blank_counts_stay_blank`; Task 3 `test_blank_counts_are_empty_cells`.
- **A fire closed with two reports in two puroks adds +1 to each.** Test: Task 2 `test_close_files_one_record_counting_each_purok_once`.
- **A fire that is out no longer shows on the public map, and closing it twice files one record.** Tests: Task 2 `test_fire_out_takes_it_off_the_map` and `test_closing_twice_files_one_record`.
- **The export round-trips.** Reading the exported file back through `bfp.read_sheet` gives the same date, location, alarm and figures. Test: Task 3 `test_export_reads_back_through_the_importer`.
- **Floods are untouched.** The generic resolve still works for a flood, and is refused for a fire. Test: Task 2 `test_generic_resolve_refuses_fires_not_floods`.

---

### Task 1: The BFP lists and the close-form rules

**Files:**
- Modify: `backend/apps/history/bfp.py` (add `PROPERTY_TYPES`, `ALARM_LEVELS`, `close_fields`, `exact_location`)
- Test: `backend/tests/test_fire_close.py`

**Interfaces:**
- Produces:
  - `PROPERTY_TYPES: dict[str, list[str]]`, `ALARM_LEVELS: list[str]` (Global Constraints)
  - `close_fields(data: dict) -> tuple[dict, dict]`: returns `(fields, errors)`.
    - It reads `alarm_level`, `property_category`, `property_subcategory`, the eight `CASUALTY_FIELDS`, `damage_cost`, `structures_affected` and `summary`.
    - `fields` holds `HistoricalRecord` field values. Counts are `int | None`, `damage_cost` is `Decimal | None`, and `total_casualties` is the sum of the known counts, or `None` when none is known.
    - The errors are keyed by field name.
  - `exact_location(purok_names: list[str], barangay_name: str | None) -> str`: e.g. `'PUROK SAMBAG, PUROK AGOHO, BRGY JACLUPAN'`, or `'BRGY JACLUPAN'`, or `''`.

- [ ] **Step 1: Write the failing tests**

```python
OK = {'alarm_level': '1ST ALARM', 'property_category': 'RESIDENTIAL',
      'property_subcategory': 'SINGLE AND TWO FAMILY DWELLING'}

def test_a_complete_close(self):
    fields, errors = close_fields({**OK, 'injured_civ_male': '2', 'fatal_ff_female': 0, 'damage_cost': '75000',
                                   'structures_affected': '1', 'summary': ' Out by 11:00 '})
    self.assertEqual(errors, {})
    self.assertEqual((fields['injured_civ_male'], fields['fatal_ff_female'], fields['damage_cost'], fields['structures_affected']),
                     (2, 0, Decimal('75000'), 1))
    self.assertEqual(fields['total_casualties'], 2)
    self.assertEqual(fields['summary'], 'Out by 11:00')

def test_blank_counts_stay_blank(self):
    fields, errors = close_fields({**OK, 'injured_civ_male': '', 'damage_cost': None})
    self.assertEqual(errors, {})
    self.assertIsNone(fields['injured_civ_male'])
    self.assertIsNone(fields['damage_cost'])
    self.assertIsNone(fields['total_casualties'])

def test_required_and_valid(self):
    self.assertEqual(close_fields({})[1]['alarm_level'], 'Choose the alarm level.')
    self.assertEqual(close_fields({**OK, 'alarm_level': '9TH ALARM'})[1]['alarm_level'], 'Choose the alarm level.')
    self.assertEqual(close_fields({**OK, 'property_subcategory': 'GRASS'})[1]['property_subcategory'], 'Choose the property type.')
    self.assertEqual(close_fields({**OK, 'injured_ff_male': '-1'})[1]['injured_ff_male'], 'Enter a whole number, 0 or more.')
    self.assertEqual(close_fields({**OK, 'injured_ff_male': '1.5'})[1]['injured_ff_male'], 'Enter a whole number, 0 or more.')
    self.assertEqual(close_fields({**OK, 'damage_cost': 'abc'})[1]['damage_cost'], 'Enter an amount in pesos, 0 or more.')

def test_exact_location(self):
    self.assertEqual(exact_location(['Purok Sambag', 'Purok Agoho'], 'Jaclupan'), 'PUROK SAMBAG, PUROK AGOHO, BRGY JACLUPAN')
    self.assertEqual(exact_location([], 'Jaclupan'), 'BRGY JACLUPAN')
    self.assertEqual(exact_location([], None), '')
```

- [ ] **Step 2: Run the tests to verify they fail**

Run (from `backend/`): `venv/Scripts/python.exe manage.py test tests.test_fire_close`
Expected: an ERROR (import).

- [ ] **Step 3: Implement**

`summary` is stripped. A category with a sub-category that isn't in its list is an error on `property_subcategory`.

- [ ] **Step 4: Run the tests to verify they pass**

Run: the command from Step 2
Expected: `OK`

---

### Task 2: Fire out, close, the waiting list and the options

**Files:**
- Modify: `backend/apps/hazards/models.py`:
  - add `('Resolving', 'Fire out, figures pending')` to `STATUS_CHOICES`
  - `fire_out_at = DateTimeField(null=True, blank=True, db_column='hzzn_fire_out_at')`
  - `fire_out_by = ForeignKey(User, SET_NULL, null=True, blank=True, related_name='fires_put_out', db_column='hzzn_fire_out_by')`
- Create: `backend/apps/hazards/migrations/<next>_fire_out.py` (with `makemigrations hazards --name fire_out`)
- Create: `backend/apps/hazards/fire_close_views.py`:
  - `FireOutView`
  - `FireCloseView`
  - `FiguresDueView`
  - `BfpOptionsView`
- Modify: `backend/apps/hazards/urls.py`:
  - `<uuid:pk>/fire-out/`
  - `<uuid:pk>/close/`
  - `figures-due/`
- Modify: `backend/apps/history/urls.py`: `bfp-options/`
- Modify: `backend/apps/hazards/views.py`:
  - `HazardZoneDetailView.patch` refuses a Fire zone going to `Resolved` / `Archived`, with 400 `{'error': 'Fire zones are closed with Fire out, then the BFP figures.'}`
  - `ResponseStatusReportView` in reports counts `resolving` (`apps/reports/views.py`)
- Modify: `backend/apps/hazards/alerts.py`: `nudge_stale_zones` also picks Fire zones in `Resolving` with the text `Fire at {where} is still waiting for BFP figures.`
- Test: `backend/tests/test_fire_close_views.py` (database-backed, set up as in `test_fire_decide_view.py`)

**Interfaces:**
- Consumes: Task 1 (`close_fields`, `exact_location`, `PROPERTY_TYPES`, `ALARM_LEVELS`); `alerts.all_clear`, `notify`, `type_name`, `where_text`; `utils.audit.log_event`.
- Produces:
  - **`POST /api/hazards/<id>/fire-out/`** (DRRMO), body `{note?}`:
    - The zone must be Fire and `Active`. Otherwise 409 `Only an active fire can be put out.`
    - Sets `status='Resolving'`, `fire_out_at`, `fire_out_by`.
    - Calls `all_clear(zone, user, note)`.
    - Notifies each linked report's `submitted_by`: `The fire you reported at {where} is out. DRRMO will record the BFP figures.`
    - `log_event('FIRE_OUT', …)`.
    - Returns 200 `HazardZoneSerializer`.
  - **`POST /api/hazards/<id>/close/`** (DRRMO), with the Task 1 fields:
    - The zone must be Fire and `Resolving`. Otherwise 409 `Only a fire that is out can be closed.`
    - Field errors give 400.
    - Otherwise, in one transaction:
      - creates **one** `HistoricalRecord`:
        - `hazard_zone=zone`, `hazard_type`, `barangay=zone.barangay`, `severity_level=zone.severity`
        - `occurred_at` = the earliest `started_at` of the linked reports, else `zone.activated_at`
        - `description` = the summary, or `f'BFP: {category} – {subcategory}, {alarm}'`
        - `location_text = exact_location(...)` over the distinct purok names and the barangay
        - the Task 1 fields, and `is_sample=zone.is_sample`
      - sets `puroks` to the distinct puroks of the linked reports
      - sets the zone to `Resolved` with `resolved_at`
      - `log_event('CLOSE_FIRE', …)`
    - Returns 201 `{'zone', 'record_id'}`.
  - **`GET /api/hazards/figures-due/`** (DRRMO): Fire zones in `Resolving`, oldest `fire_out_at` first. Each is `HazardZoneSerializer` data plus `puroks` (names), `barangay_name` and `started_at`.
  - **`GET /api/history/bfp-options/`** (DRRMO): `{'property_types': PROPERTY_TYPES, 'alarm_levels': ALARM_LEVELS}`.

- [ ] **Step 1: Write the failing tests**

The setup uses the same barangays, puroks, roles and users as `test_fire_decide_view.py`. `fire_zone(*puroks)` creates an Active Fire zone with linked Validated reports, one per purok, each with `started_at`. Closing uses `OK` from Task 1.

```python
def test_fire_out_takes_it_off_the_map(self):
    zone = self.fire_zone(self.near)
    self.assertEqual(self.post(zone, 'fire-out', {}).status_code, 200)
    zone.refresh_from_db()
    self.assertEqual((zone.status, zone.fire_out_by_id), ('Resolving', self.officer.id))
    self.assertFalse(HazardZone.objects.filter(status='Active').exists())
    self.assertTrue(Notification.objects.filter(recipient=self.reporter, content__contains='is out').exists())

def test_only_an_active_fire_can_be_put_out(self):
    zone = self.fire_zone(self.near, status='Resolving')
    self.assertEqual(self.post(zone, 'fire-out', {}).data['error'], 'Only an active fire can be put out.')

def test_close_files_one_record_counting_each_purok_once(self):
    zone = self.fire_zone(self.near, self.far, self.near, status='Resolving')
    response = self.post(zone, 'close', {**OK, 'injured_civ_male': 1, 'damage_cost': '5000'})
    self.assertEqual(response.status_code, 201)
    record = HistoricalRecord.objects.get(pk=response.data['record_id'])
    self.assertEqual(sorted(p.name for p in record.puroks.all()), ['Purok Far', 'Purok Near'])
    self.assertEqual((record.alarm_level, record.injured_civ_male, record.damage_cost), ('1ST ALARM', 1, Decimal('5000')))
    self.assertEqual(record.occurred_at, min(r.started_at for r in zone.incidentreport_set.all()))
    self.assertIn('PUROK NEAR', record.location_text)
    zone.refresh_from_db()
    self.assertEqual(zone.status, 'Resolved')

def test_closing_twice_files_one_record(self):
    zone = self.fire_zone(self.near, status='Resolving')
    self.post(zone, 'close', OK)
    self.assertEqual(self.post(zone, 'close', OK).status_code, 409)
    self.assertEqual(HistoricalRecord.objects.filter(hazard_zone=zone).count(), 1)

def test_close_refuses_bad_figures(self):
    zone = self.fire_zone(self.near, status='Resolving')
    self.assertEqual(self.post(zone, 'close', {**OK, 'alarm_level': ''}).status_code, 400)
    self.assertFalse(HistoricalRecord.objects.exists())

def test_generic_resolve_refuses_fires_not_floods(self):
    fire = self.fire_zone(self.near)
    flood = self.fire_zone(self.near, hazard_type=self.flood)
    self.assertEqual(self.patch(fire, {'status': 'Resolved'}).status_code, 400)
    self.assertEqual(self.patch(flood, {'status': 'Resolved'}).status_code, 200)

def test_figures_due_lists_fires_that_are_out(self):
    self.fire_zone(self.near)
    out = self.fire_zone(self.far, status='Resolving')
    self.assertEqual([z['id'] for z in self.get('figures-due').data], [str(out.id)])
```

`post(zone, action, body)` and `patch(zone, body)` run the views through `APIRequestFactory` as `self.officer`. `get('figures-due')` calls `FiguresDueView`.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `venv/Scripts/python.exe manage.py test tests.test_fire_close_views`
Expected: ERROR or FAIL.

- [ ] **Step 3: Implement the model change, migration, views, URLs, refusal and nudge**

Then run `makemigrations --check --dry-run`. Expected: `No changes detected`.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `venv/Scripts/python.exe manage.py test tests.test_fire_close_views tests.test_fire_close`
Expected: `OK`

---

### Task 3: The BFP Excel export

**Files:**
- Create: `backend/apps/history/bfp_export.py`
- Modify: `backend/apps/history/views.py` (add `FireExportView`) and `backend/apps/history/urls.py` (`fires.xlsx`)
- Test: `backend/tests/test_bfp_export.py`

**Interfaces:**
- Consumes: Task 1's fields; `bfp.read_sheet` for the round-trip test.
- Produces:
  - **`bfp_workbook(records) -> openpyxl.Workbook`**: `records` are objects with:
    - `occurred_at`
    - `location_text`
    - `property_category`, `property_subcategory`
    - the eight counts
    - `damage_cost`, `structures_affected`, `alarm_level`

    Layout:
    - Row 1: `A1` `Date of Fire\n (date-month-year)`, `B1` `Time of Alarm`, `C1` `Region`, `D1` `Province / District`, `E1` `City / Municipality`, `F1` `Exact Location`, `G1` `Property Type`, `I1` `Nr of Injured`, `N1` `Nr of Fatalities`, `U1` `Estimated Cost of Damage`, `V1` `Nr of Affected Structure`, `W1` `Alarm`
    - Row 2: `I2` `Firefighter`, `K2` `Total`, `L2` `Civilian`, `N2` `Total`, `O2` `Firefighter`, `Q2` `Total`, `R2` `Civilian`, `T2` `Total`
    - Row 3: `G3` `General Category`, `H3` `Sub Category`, `I3`/`L3`/`O3`/`R3` `Male`, `J3`/`M3`/`P3`/`S3` `Female`
    - Merges: `A1:A3, B1:B3, C1:C3, D1:D3, E1:E3, F1:F3, G1:H2, I1:M1, N1:T1, U1:U3, V1:V3, W1:W3, I2:J2, K2:K3, L2:M2, N2:N3, O2:P2, Q2:Q3, R2:S2, T2:T3`
    - Data from row 4:
      - A is a date (local, format `d-mmm-yy`). B is the time as the number HHMM with the format `00":"00`, so it shows as 10:10, as the BFP file stores it.
      - C–E are `Region_7` / `Cebu` / `Talisay_City_c`, F is `location_text`, G–H the property type.
      - I, J = injured firefighter M, F; K = their total. L, M = injured civilian M, F; N = their total.
      - O, P = fatal firefighter M, F; Q = their total. R, S = fatal civilian M, F; T = their total.
      - U is the damage (number format `"Php"#,##0.00`), V the structures, W the alarm.
      - A total is the sum when either part is known, else blank.
  - **`GET /api/history/fires.xlsx?from=&to=&barangay=`** (DRRMO): Fire `HistoricalRecord`s, oldest first. It sends the workbook as an attachment `talisay-fires-<from>-<to>.xlsx`. `log_event('EXPORT_FIRES', …)`.

- [ ] **Step 1: Write the failing tests**

```python
def rec(**kw):
    base = dict(occurred_at=datetime(2026, 10, 26, 10, 10, tzinfo=MNL), location_text='PUROK SAMBAG, BRGY JACLUPAN',
                property_category='RESIDENTIAL', property_subcategory='SINGLE AND TWO FAMILY DWELLING',
                injured_ff_male=0, injured_ff_female=0, injured_civ_male=2, injured_civ_female=1,
                fatal_ff_male=None, fatal_ff_female=None, fatal_civ_male=0, fatal_civ_female=0,
                damage_cost=Decimal('75000'), structures_affected=1, alarm_level='1ST ALARM')
    base.update(kw)
    return Fake(**base)

def test_header_matches_the_bfp_log(self):
    ws = bfp_workbook([]).active
    self.assertEqual((ws['A1'].value, ws['I1'].value, ws['N2'].value, ws['H3'].value), (
        'Date of Fire\n (date-month-year)', 'Nr of Injured', 'Total', 'Sub Category'))
    self.assertIn('I1:M1', [str(m) for m in ws.merged_cells.ranges])

def test_a_row_per_fire_with_totals(self):
    ws = bfp_workbook([rec()]).active
    self.assertEqual([ws[f'{c}4'].value for c in 'BCEFLMN'], [1010, 'Region_7', 'Talisay_City_c',
                                                             'PUROK SAMBAG, BRGY JACLUPAN', 2, 1, 3])
    self.assertEqual(ws['B4'].number_format, '00":"00')  # shows 10:10, as the BFP file does
    self.assertEqual((ws['U4'].value, ws['W4'].value), (75000, '1ST ALARM'))

def test_blank_counts_are_empty_cells(self):
    ws = bfp_workbook([rec()]).active
    self.assertEqual((ws['O4'].value, ws['P4'].value, ws['Q4'].value), (None, None, None))

def test_export_reads_back_through_the_importer(self):
    path = Path(self.tmp) / 'out.xlsx'
    bfp_workbook([rec()]).save(path)
    [row] = bfp.read_sheet(path)
    self.assertEqual(bfp.parse_when(row['date'], row['time']), datetime(2026, 10, 26, 10, 10, tzinfo=MNL))
    self.assertEqual((row['location'], row['alarm'], row['injured_civ_male'], row['damage_cost']),
                     ('PUROK SAMBAG, BRGY JACLUPAN', '1ST ALARM', 2, Decimal('75000')))
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `venv/Scripts/python.exe manage.py test tests.test_bfp_export`
Expected: an ERROR (import).

- [ ] **Step 3: Implement the builder and the view**

- [ ] **Step 4: Run the tests to verify they pass**

Run: the command from Step 2
Expected: `OK`

---

### Task 4: Fire out and the figures form (frontend)

**Files:**
- Create: `frontend/src/components/Resolve/fireClose.js`
- Test: `frontend/src/components/Resolve/fireClose.test.js`
- Create: `frontend/src/components/Resolve/FiguresDueCard.jsx`: the list, plus a `CloseFireForm` modal
- Modify: `frontend/src/components/Resolve/ResolveHazardForm.jsx`: a new `hazardType` prop. For `'Fire'` it renders the Fire-out form (a note plus a **Fire out** button) and calls `hazardsApi.fireOut`.
- Modify: `frontend/src/components/Map/HazardPanel.jsx` and `frontend/src/components/Resolve/ActiveZonesCard.jsx`: pass `hazardType`
- Modify: `frontend/src/api/hazardsApi.js`: `fireOut(id, note)`, `closeFire(id, body)`, `figuresDue()`
- Modify: `frontend/src/api/historyApi.js`: `bfpOptions()`, `exportFires(params) -> Blob`
- Modify: `frontend/src/pages/Dashboard/DRRMODashboard.jsx`: render `<FiguresDueCard />` next to `ActiveZonesCard`

**Interfaces:**
- Produces (in `fireClose.js`):
  - `COUNT_FIELDS`: the eight count field names
  - `emptyFigures()`: every field `''`
  - `figuresErrors(form, options) -> object`: the same words as Task 1
  - `figuresPayload(form) -> object`: blank counts become `null`, numbers become `Number`, and `summary` is trimmed

- [ ] **Step 1: Write the failing tests**

```js
const OPTIONS = { property_types: { RESIDENTIAL: ['SINGLE AND TWO FAMILY DWELLING'], NON_STRUCTURAL: ['GRASS'] },
                  alarm_levels: ['1ST ALARM', '2ND ALARM'] };
const OK = { ...emptyFigures(), alarm_level: '1ST ALARM', property_category: 'RESIDENTIAL',
             property_subcategory: 'SINGLE AND TWO FAMILY DWELLING' };
test('a complete form has no errors', () => expect(figuresErrors(OK, OPTIONS)).toEqual({}));
test('required and valid', () => {
  expect(figuresErrors({ ...OK, alarm_level: '' }, OPTIONS).alarm_level).toBe('Choose the alarm level.');
  expect(figuresErrors({ ...OK, property_subcategory: 'GRASS' }, OPTIONS).property_subcategory).toBe('Choose the property type.');
  expect(figuresErrors({ ...OK, injured_ff_male: '-1' }, OPTIONS).injured_ff_male).toBe('Enter a whole number, 0 or more.');
  expect(figuresErrors({ ...OK, damage_cost: 'x' }, OPTIONS).damage_cost).toBe('Enter an amount in pesos, 0 or more.');
});
test('payload keeps blanks as null', () => {
  const p = figuresPayload({ ...OK, injured_civ_male: '2', damage_cost: '75000', summary: ' out ' });
  expect(p).toMatchObject({ injured_civ_male: 2, injured_ff_male: null, damage_cost: 75000, summary: 'out' });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run (from `frontend/`): `CI=true npx react-scripts test --watchAll=false src/components/Resolve/fireClose.test.js`
Expected: FAIL.

- [ ] **Step 3: Implement the helpers and the UI**

- **`ResolveHazardForm` for a fire:**
  - Heading **Fire out**.
  - Text: *"This sends the all-clear and takes the fire off the public map. Record the BFP figures afterwards, from the DRRMO dashboard."*
  - An optional note and a **Fire out** button.
  - On success it calls `onResolved(zone)`, as today.
- **`FiguresDueCard`:**
  - A title, "Fires waiting for BFP figures", and one row per zone: puroks · barangay · "out since {time}", with an **Enter BFP figures** button.
  - Nothing is rendered when the list is empty.
- **`CloseFireForm` modal:**
  - The property category select, then the sub-category select filtered by the category.
  - Injured and Fatalities as two small grids: Firefighter / Civilian × Male / Female number inputs.
  - Damage (PHP), structures, the alarm select, and a "What happened" textarea.
  - The hint: *"Leave a count empty if it isn't in yet. Empty is recorded as not counted, which is not the same as zero."*
  - On success: close the modal, refresh the list, and show the toast *"Fire closed and filed in history."*

- [ ] **Step 4: Run all frontend tests**

Run: `CI=true npx react-scripts test --watchAll=false`
Expected: all pass.

---

### Task 5: History page fire columns and the export button

**Files:**
- Modify: `backend/apps/history/serializers.py`: `HistoricalRecordSerializer` adds `alarm_level`, `property_category`, `property_subcategory`, `structures_affected`, the eight counts, and `puroks` (names). `location_text` and `damage_cost` are only filled in for DRRMO Officer and System Admin; otherwise they come back `None`.
- Create: `frontend/src/pages/fireHistory.js`
- Test: `frontend/src/pages/fireHistory.test.js`
- Modify: `frontend/src/pages/HistoricalData.jsx`

**Interfaces:**
- Produces: `fireDetails(record) -> string[]`. Labelled parts in BFP order, skipping blanks: alarm level, property type, injured (FF m/f, civ m/f, shown as one total), fatalities likewise, structures and damage. Examples:
  - `['1ST ALARM', 'Residential · Single and two family dwelling', 'Injured 3', 'Structures 1', 'Damage ₱75,000']`
  - A record with no fire fields gives `[]`.

- [ ] **Step 1: Write the failing test**

```js
test('fire details in BFP order, blanks skipped', () => {
  expect(fireDetails({ alarm_level: '1ST ALARM', property_category: 'RESIDENTIAL',
    property_subcategory: 'SINGLE AND TWO FAMILY DWELLING', injured_civ_male: 2, injured_civ_female: 1,
    fatal_civ_male: null, structures_affected: 1, damage_cost: '75000.00' }))
    .toEqual(['1ST ALARM', 'Residential · Single and two family dwelling', 'Injured 3', 'Structures 1', 'Damage ₱75,000']);
  expect(fireDetails({ alarm_level: '', property_category: '' })).toEqual([]);
});
```

- [ ] **Step 2: Run it to verify it fails**

Run: `CI=true npx react-scripts test --watchAll=false src/pages/fireHistory.test.js`
Expected: FAIL.

- [ ] **Step 3: Implement**

- Each record row shows `fireDetails(r).join(' · ')` under the existing line.
- Staff also see the exact location.
- Staff get an **Export fires (Excel)** button next to the filters. It calls `historyApi.exportFires({from, to, barangay})` and saves the blob with the server's filename.

- [ ] **Step 4: Run all frontend tests and the build**

Run: `CI=true npx react-scripts test --watchAll=false`, then `npx react-scripts build`
Expected: all pass, with no new build warnings.

---

### Task 6: Migrate (with the user's OK), check against the database, and the user tries it

- [ ] **Step 1:** Ask the user, then run `venv/Scripts/python.exe manage.py migrate hazards`. Expected: the `fire_out` migration is applied.
- [ ] **Step 2:** Run the full backend suite. Expected: OK.
- [ ] **Step 3:** The user's Jaclupan fire is live. Ask the user to:
  1. Put it out from the map panel or the dashboard.
  2. Enter the BFP figures from "Fires waiting for BFP figures".
  3. Check that it shows on the history page with its figures.
  4. Export it, and check that the Excel opens with the BFP header and their row.
