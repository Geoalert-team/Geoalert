# BFP Fire History Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The BFP fire log is in the history table as one record per fire, each linked to its purok where the address names one, after the purok list has been cleaned up against the log.

**Architecture:** Pure, database-free modules do the work: `apps/history/bfp.py` reads the sheet, `apps/history/bfp_link.py` turns an address into a barangay and a purok, and `apps/history/bfp_import.py` decides what to write. A management command does the database I/O. `load_puroks` is changed to update puroks in place so their ids, and the history links to them, survive reloads. The data cleanup is research, verified by the import's dry-run report.

**Tech Stack:** Django 4.2.13 + GeoDjango, DRF, PostgreSQL/PostGIS (shared Supabase), openpyxl, Django `SimpleTestCase` tests.

**Spec:** `docs/superpowers/specs/2026-10-25-report-driven-fire-hazards-design.md` (sections "Data model › HistoricalRecord", "Importing the BFP fire log", "Order of work" steps 1–2). Import rules come from `docs/superpowers/specs/2026-10-23-purok-fire-data-design.md` ("Import", "Linking an address to a purok").

This is plan 1 of 3. Plan 2 is the hazard-levels spec with its amendments; plan 3 is the fire flow (report fields, decision, fire out / close, map, history panel).

## Global Constraints

- Tests are `SimpleTestCase` with no database, in `backend/tests/`. Run from `backend/`: `venv/Scripts/python.exe manage.py test tests.<module>`.
- New `HistoricalRecord` columns use the `hstr_` prefix; the purok link table is `historical_record_purok`.
- Times are local `Asia/Manila` (`settings.TIME_ZONE`), stored timezone-aware.
- Blank means "not known", never 0.
- BFP spelling wins for place names. No guessed positions: a name without a found location goes on the Barangay Hall list.
- One-off research scripts live in the session scratchpad, not the repo.
- **Nothing is written to the shared database without the user's OK at that moment:** `migrate`, `load_puroks` without `--dry-run`, `import_bfp_fires` without `--dry-run` or with `--relink`.
- The BFP `.xlsx` is not committed. Ask the user for the current file.
- `openpyxl==3.1.5` goes in `backend/requirements/base.txt`.

## Review Focus

- A purok renamed to BFP spelling during cleanup (Kamungay → Kamunggay) keeps its id on reload, so nothing linked to it is lost. Test in Task 3: `test_a_respelled_purok_keeps_its_id`.
- Text dates with odd spacing (`1130H/ 29 JULY 2023`) parse, and don't drop the fire. Test in Task 1: `test_text_dates_and_times`.
- An address that writes the barangay with Upper/Lower (`Lower Candulawan`, `Upper Mohon`) or misspelled (`Poblacio`, `Casojong`, `Lawa-an 1`) still finds its barangay. Tests in Task 2.
- Running the import again with a newer BFP file adds only the new rows. Test in Task 4: `test_existing_refs_are_skipped`.
- Two identical rows (rows 190 and 191 of the current file) count as one fire, not two. Test in Task 4: `test_an_exact_repeat_is_imported_once`.

---

### Task 1: BFP sheet reader

**Files:**
- Create: `backend/apps/history/bfp.py`
- Modify: `backend/requirements/base.txt` (add `openpyxl==3.1.5` under a `# Reading the BFP fire log (manage.py import_bfp_fires)` comment)
- Test: `backend/tests/test_bfp_reader.py`

**Interfaces:**
- Produces:
  - `read_sheet(path: str | Path) -> list[dict]`: one dict per sheet row below the three header rows that has a location (column F). Keys: `row` (sheet row number), `date`, `time` (raw cell values), `city` (E), `location` (F, as typed), `category` (G), `subcategory` (H), `injured_ff_male` (I), `injured_ff_female` (J), `injured_civ_male` (L), `injured_civ_female` (M), `fatal_ff_male` (O), `fatal_ff_female` (P), `fatal_civ_male` (R), `fatal_civ_female` (S), `total_hurt` (T), `damage_cost` (U, `Decimal | None`), `structures_affected` (V, `int | None`), `alarm` (W, stripped, upper case). The counts are `int | None`.
  - `parse_when(date_value, time_value) -> datetime | None`: timezone-aware Asia/Manila, or `None` when the date can't be read.
  - `severity_for_alarm(alarm: str) -> tuple[str, bool]`: `(code, known)`.
  - `total_casualties(row: dict) -> int | None`
  - `source_ref(when: datetime, location: str) -> str`
  - `is_talisay(row: dict) -> bool`

- [ ] **Step 1: Write the failing tests**

A helper `make_sheet(rows: list[dict]) -> Path` writes an `.xlsx` with openpyxl into a `tempfile.TemporaryDirectory`. It writes three header rows, then each dict as `{column letter: value}` from row 4.

```python
MNL = ZoneInfo('Asia/Manila')

def test_reads_rows_below_the_three_header_rows(self):
    path = make_sheet([{'A': 44952, 'B': 2036, 'E': 'Talisay_City_c', 'F': 'PUROK SAMBAG, BRGY CAMP 4',
                        'G': 'RESIDENTIAL', 'H': 'SINGLE AND TWO FAMILY DWELLING', 'I': 0, 'T': 0,
                        'U': 75000, 'V': 1, 'W': '1st alarm '}])
    [row] = bfp.read_sheet(path)
    self.assertEqual(row['row'], 4)
    self.assertEqual(row['location'], 'PUROK SAMBAG, BRGY CAMP 4')
    self.assertEqual(row['damage_cost'], Decimal('75000'))
    self.assertEqual(row['structures_affected'], 1)
    self.assertEqual(row['alarm'], '1ST ALARM')
    self.assertEqual(row['injured_ff_male'], 0)
    self.assertIsNone(row['fatal_civ_female'])          # blank cell: not known

def test_rows_without_a_location_are_skipped(self):
    self.assertEqual(bfp.read_sheet(make_sheet([{'A': 44952, 'B': 2036}])), [])

def test_serial_dates_and_hhmm_times(self):
    self.assertEqual(bfp.parse_when(44952, 2036), datetime(2023, 1, 26, 20, 36, tzinfo=MNL))
    self.assertEqual(bfp.parse_when('44972.0', '952.0'), datetime(2023, 2, 15, 9, 52, tzinfo=MNL))

def test_text_dates_and_times(self):
    self.assertEqual(bfp.parse_when('JULY 16,2023', '1158H/16 JULY 2023'), datetime(2023, 7, 16, 11, 58, tzinfo=MNL))
    self.assertEqual(bfp.parse_when('JULY 29,2023', '1130H/ 29 JULY 2023'), datetime(2023, 7, 29, 11, 30, tzinfo=MNL))

def test_blank_time_is_midnight_and_bad_date_is_none(self):
    self.assertEqual(bfp.parse_when(44952, None), datetime(2023, 1, 26, 0, 0, tzinfo=MNL))
    self.assertIsNone(bfp.parse_when('sometime', 1200))

def test_alarm_levels(self):
    for alarm, code in [('FIRE OUT UPON ARRIVAL', 'Green'), ('UNRESPONDED', 'Green'), ('1ST ALARM', 'Green'),
                        ('2ND ALARM', 'Orange'), ('3RD ALARM', 'Red'), ('4TH ALARM', 'Red'),
                        ('TF ALPHA', 'Red'), ('GENERAL ALARM', 'Red'), (' 2nd alarm ', 'Orange')]:
        self.assertEqual(bfp.severity_for_alarm(alarm), (code, True), alarm)
    self.assertEqual(bfp.severity_for_alarm('ALARM X'), ('Green', False))

def test_casualties_take_the_larger_of_column_t_and_the_cells(self):
    zeros = {k: 0 for k in bfp.CASUALTY_FIELDS}
    self.assertEqual(bfp.total_casualties({**zeros, 'total_hurt': 4}), 4)
    self.assertEqual(bfp.total_casualties({**zeros, 'injured_civ_male': 1, 'total_hurt': 1}), 1)
    self.assertEqual(bfp.total_casualties({**zeros, 'injured_civ_male': 2, 'fatal_civ_male': 1, 'total_hurt': 1}), 3)
    self.assertIsNone(bfp.total_casualties({**{k: None for k in bfp.CASUALTY_FIELDS}, 'total_hurt': None}))

def test_source_ref_ignores_spacing_and_case(self):
    when = datetime(2026, 4, 29, 10, 45, tzinfo=MNL)
    a = bfp.source_ref(when, 'Purok Sambag,  San Roque')
    self.assertEqual(a, bfp.source_ref(when, 'PUROK SAMBAG, SAN ROQUE'))
    self.assertTrue(a.startswith('bfp:'))
    self.assertEqual(len(a), 20)

def test_only_talisay_rows_count(self):
    self.assertTrue(bfp.is_talisay({'city': 'Talisay_City_c'}))
    self.assertFalse(bfp.is_talisay({'city': 'Toledo_City'}))
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `venv/Scripts/python.exe -m pip install openpyxl==3.1.5`, then `venv/Scripts/python.exe manage.py test tests.test_bfp_reader`
Expected: an ERROR, because `apps.history.bfp` doesn't exist.

- [ ] **Step 3: Implement `bfp.py`**

- `CASUALTY_FIELDS` is the tuple of the eight casualty keys in the order listed above.
- Read with `openpyxl.load_workbook(path, read_only=True, data_only=True)`, first sheet, `iter_rows(min_row=4)`.
- Excel serial dates count from `date(1899, 12, 30)`. Text dates use `%B %d,%Y` after collapsing spaces.
- A numeric time `HHMM` becomes `divmod(int(float(t)), 100)`. A text time is the digits before `H`.
- `source_ref` = `'bfp:' + sha1(f'{when.isoformat()}|{" ".join(location.upper().split())}').hexdigest()[:16]`.
- `severity_for_alarm`: Green for `FIRE OUT UPON ARRIVAL`, `UNRESPONDED` and `1ST ALARM`; Orange for `2ND ALARM`; Red for `3RD`–`5TH ALARM`, anything starting `TF ` and `GENERAL ALARM`; anything else gives `('Green', False)`.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `venv/Scripts/python.exe manage.py test tests.test_bfp_reader`
Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add backend/apps/history/bfp.py backend/tests/test_bfp_reader.py backend/requirements/base.txt
git commit -m "Read the BFP fire log sheet"
```

---

### Task 2: Address → barangay and purok

**Files:**
- Create: `backend/apps/history/bfp_link.py`
- Modify: `backend/apps/barangays/aliases.py`: add `'Poblacio'` to Poblacion, `'Cansojong': ['Casojong']`, and `'Lawa-an 1'`, `'Lawa-an 2'`, `'Lawa-an 3'` to Lawaan I/II/III.
- Test: `backend/tests/test_bfp_link.py`

**Interfaces:**
- Consumes: `aliases.canonical`, `aliases.match_barangay`, `purok_estimate.norm_name`.
- Produces:
  - `split_address(text: str, barangay_names: list[str]) -> tuple[str | None, list[tuple[str, str]]]`: the barangay (one of `barangay_names`, as given there) and the candidate places before it, in address order, as `(label, place)`. `label` is `'purok'`, `'sitio'` or `''`, and `place` is the text without its label.
  - `find_purok(candidates: list[tuple[str, str]], purok_names: list[str], variants: dict[str, str]) -> str | None`: purok-labelled candidates first, then the rest in order. A candidate matches a name when their `norm_name`s are equal, or when `variants[norm_name(place)]` is that name.
  - `load_variants(path) -> dict[str, dict[str, str]]`: `{canonical(barangay): {norm_name(variant): name}}` from a CSV with the columns `barangay,variant,name`.
  - `link_address(text, barangays, puroks_by_barangay: dict[int, list[str]], variants) -> tuple[barangay | None, str | None]`: `barangays` are objects with `.id`, `.name` and `.boundary`. Returns the matched barangay object and the purok name, or `None`.

- [ ] **Step 1: Write the failing tests** (`B` is the 22 barangay names as the shared database has them, including `'Tabunok'`)

```python
def test_split(self):
    cases = [
        ('PUROK SAMBAG, LARAY, BRGY SAN ROQUE', ('San Roque', [('purok', 'SAMBAG'), ('', 'LARAY')])),
        ('Purk Ilang-Ilang, San Roque, Linao, Talisay City Cebu', ('Linao', [('purok', 'Ilang-Ilang'), ('', 'San Roque')])),
        ('Rizal St., Zone 3, Dumlog, Talisay City, Cebu', ('Dumlog', [('', 'Zone 3')])),
        ('Block 6, Lot 9, Azienda Firenze, Camilla Homes Subd., Maghaway, Talisay City, Cebu',
         ('Maghaway', [('', 'Azienda Firenze'), ('', 'Camilla Homes Subd.')])),
        ('SRP, Lawaan 1, Talisay City, Cebu', ('Lawaan I', [])),
        ('Canizares St. Dumlog, Talisay City Cebu', ('Dumlog', [])),          # barangay at the end of a part
        ('Purok Mangga, Lower Candulawan, Talisay City, Cebu', ('Cadulawan', [('purok', 'Mangga')])),
        ('Bontory, Upper Mohon, Talisay City, Cebu', ('Mohon', [('', 'Bontory')])),
        ('Cebu Southroad, Linao, Talisay Cebu', ('Linao', [])),
        ('Zone 2, Brgy. Biasong, Talisay City', ('Biasong', [('', 'Zone 2')])),
        ('LAWA-AN 1, TALISAY CITY, CEBU', ('Lawaan I', [])),
        ('BRGY DUMLOG', ('Dumlog', [])),
        ('Sitio Napo, Talisay City Cebu', (None, [('sitio', 'Napo')])),
    ]
    for text, expected in cases:
        self.assertEqual(split_address(text, B), expected, text)

def test_misspelled_barangays(self):
    self.assertEqual(split_address('Purok Kamunggay, Poblacio, Talisay City, Cebu', B)[0], 'Poblacion')
    self.assertEqual(split_address('Cassare, Casojong, Talisay City Cebu', B)[0], 'Cansojong')

def test_find_purok(self):
    self.assertEqual(find_purok([('sitio', 'Libra'), ('purok', 'Kamungay')], ['Sitio Libra', 'Purok Kamunggay'], {}), 'Purok Kamunggay')
    self.assertEqual(find_purok([('', 'LARAY'), ('purok', 'SAMBAG')], ['Sitio Laray', 'Purok Sambag'], {}), 'Purok Sambag')
    self.assertEqual(find_purok([('', 'Paglaum')], ['Sitio Paglaom'], {'paglaum': 'Sitio Paglaom'}), 'Sitio Paglaom')
    self.assertIsNone(find_purok([('', 'Zone 3')], ['Purok 3'], {}))
    self.assertIsNone(find_purok([], ['Purok Sambag'], {}))

def test_load_variants(self):   # writes a temp CSV: "barangay,variant,name\nDumlog,Paglaum,Sitio Paglaom\n"
    self.assertEqual(load_variants(path), {'dumlog': {'paglaum': 'Sitio Paglaom'}})

def test_link_address(self):
    roque = FakeBarangay(19, 'San Roque', boundary=object())
    brgy, purok = link_address('PUROK SAMBAG, LARAY, BRGY SAN ROQUE', [roque], {19: ['Purok Sambag']}, {})
    self.assertEqual((brgy, purok), (roque, 'Purok Sambag'))
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `venv/Scripts/python.exe manage.py test tests.test_bfp_link`
Expected: an ERROR, because `apps.history.bfp_link` doesn't exist.

- [ ] **Step 3: Implement `bfp_link.py` and the alias additions**

Follow the 2026-10-23 spec's "Linking" steps 1–3, plus these:
- Drop parts made only of the words `TALISAY`, `CITY` and `CEBU`.
- Strip a leading `BRGY`/`BRGY.`/`BARANGAY`.
- The barangay is the **last** part that matches through `canonical`. If no part matches, try the part again without a leading `UPPER`/`LOWER`. If that fails too, match a barangay name at the **end** of a part (`Canizares St. Dumlog`).
- Labels: `PUROK`/`PRK`/`PURK` give `purok`, and `SITIO` gives `sitio`.
- These parts are not places and are dropped:
  - a first word of `BLK`, `BLOCK`, `LOT`, `PHASE` or `CLUSTER`
  - a leading house number
  - a last word in `ST`, `ST.`, `AVE`, `AVE.`, `RD`, `RD.`, `DRIVE` or `HIGHWAY`, or ending in `ROAD`
  - the bare word `SRP`

- [ ] **Step 4: Run the tests to verify they pass**

Run: `venv/Scripts/python.exe manage.py test tests.test_bfp_link tests.test_load_puroks`
Expected: `OK` (`test_load_puroks` guards the alias change).

- [ ] **Step 5: Commit**

```bash
git add backend/apps/history/bfp_link.py backend/apps/barangays/aliases.py backend/tests/test_bfp_link.py
git commit -m "Link BFP addresses to barangays and puroks"
```

---

### Task 3: Purok reloads keep their ids

**Files:**
- Modify: `backend/apps/barangays/purok_load.py` (`replace`, new `plan_replace`)
- Modify: `backend/apps/barangays/management/commands/load_puroks.py` (`DatabaseStore`, closing message)
- Test: `backend/tests/test_load_puroks.py` (rewrite `FakeStore` and `ReplaceTests`)

**Interfaces:**
- Produces:
  - `plan_replace(existing: list[tuple[int, int, str]], rows: list[dict]) -> dict`: `existing` is `(id, barangay_id, name)` for the puroks of the barangays in `rows`. Returns `{'update': [(id, row)], 'create': [row], 'delete': [id]}`, matched on `(barangay_id, norm_name(name))`.
  - `replace(rows, store) -> dict`: calls `store.existing(barangay_ids)`, then `store.apply(plan)`, and returns the plan.
- Store protocol: `existing(barangay_ids) -> list[tuple[int, int, str]]` and `apply(plan) -> None`.

- [ ] **Step 1: Write the failing tests**

```python
def test_matching_puroks_are_updated_new_created_missing_deleted(self):
    tunga, rattan = {'barangay_id': 21, 'name': 'Sitio Tunga'}, {'barangay_id': 21, 'name': 'Rattan'}
    plan = pl.plan_replace([(7, 21, 'Sitio Tunga'), (8, 21, 'Magay')], [tunga, rattan])
    self.assertEqual(plan, {'update': [(7, tunga)], 'create': [rattan], 'delete': [8]})

def test_a_respelled_purok_keeps_its_id(self):
    row = {'barangay_id': 16, 'name': 'Purok Kamunggay'}
    self.assertEqual(pl.plan_replace([(5, 16, 'Purok Kamungay')], [row])['update'], [(5, row)])

def test_only_the_barangays_in_the_file_are_touched(self):
    store = FakeStore(existing=[(7, 21, 'Sitio Tunga'), (9, 22, 'Purok 4')])
    pl.replace([{'barangay_id': 21, 'name': 'Sitio Tunga'}], store)
    self.assertEqual(store.asked, {21})
    self.assertEqual(store.applied['delete'], [])
```

`FakeStore(existing)` records `asked` (the barangay ids passed to `existing`) and `applied` (the plan). Its `existing` returns only the tuples whose barangay was asked for.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `venv/Scripts/python.exe manage.py test tests.test_load_puroks`
Expected: FAIL or ERROR, because `plan_replace` doesn't exist.

- [ ] **Step 3: Implement**

- `DatabaseStore.existing` reads `values_list('id', 'barangay_id', 'name')`.
- `DatabaseStore.apply`, in one `transaction.atomic()`:
  - update `name`, `kind`, `parent`, `boundary`, `source` and `confidence` in place
  - `bulk_create` the new puroks
  - delete the removed ones
- When the plan created or deleted anything, `load_puroks` ends with: `Puroks were added or removed: run "manage.py import_bfp_fires --relink" so fire history follows them.`

- [ ] **Step 4: Run the tests to verify they pass**

Run: `venv/Scripts/python.exe manage.py test tests.test_load_puroks tests.test_purok_estimate`
Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add backend/apps/barangays/purok_load.py backend/apps/barangays/management/commands/load_puroks.py backend/tests/test_load_puroks.py
git commit -m "Keep purok ids when reloading puroks"
```

---

### Task 4: History fields and `import_bfp_fires`

**Files:**
- Modify: `backend/apps/history/models.py` (fields below)
- Create: `backend/apps/history/migrations/0003_bfp_fields.py` (from `makemigrations history --name bfp_fields`)
- Create: `backend/apps/history/bfp_import.py`
- Create: `backend/apps/history/management/__init__.py`, `backend/apps/history/management/commands/__init__.py`, `backend/apps/history/management/commands/import_bfp_fires.py`
- Create: `backend/apps/barangays/data/puroks/name_variants.csv` (header only: `barangay,variant,name`)
- Test: `backend/tests/test_bfp_import.py`

**Interfaces:**
- Consumes: Task 1 (`read_sheet`, `parse_when`, `severity_for_alarm`, `total_casualties`, `source_ref`, `is_talisay`, `CASUALTY_FIELDS`) and Task 2 (`link_address`, `load_variants`).
- Produces:
  - `HistoricalRecord` fields:

    | Field | Definition |
    |---|---|
    | `puroks` | `ManyToManyField(Purok, blank=True, related_name='history', db_table='historical_record_purok')` |
    | `alarm_level` | `CharField(30, blank=True, default='')` |
    | `property_category` | `CharField(20, blank=True, default='')` |
    | `property_subcategory` | `CharField(40, blank=True, default='')` |
    | `damage_cost` | `DecimalField(14, 2, null=True, blank=True)` |
    | `structures_affected` | `IntegerField(null=True, blank=True)` |
    | `injured_ff_male`, `injured_ff_female`, `injured_civ_male`, `injured_civ_female`, `fatal_ff_male`, `fatal_ff_female`, `fatal_civ_male`, `fatal_civ_female` | `IntegerField(null=True, blank=True)` |
    | `location_text` | `TextField(blank=True, default='')` |
    | `source_ref` | `CharField(40, null=True, blank=True, unique=True)` |

    Every `db_column` is `hstr_<field name>`.
  - `plan_import(rows, existing_refs: set[str], barangays, puroks_by_barangay, variants) -> tuple[list[dict], dict]`. Each record dict holds the `HistoricalRecord` field values plus `barangay` (object or `None`) and `purok_name` (`str | None`). The report keys are:

    | Key | Value |
    |---|---|
    | `read` | int |
    | `imported` | int |
    | `skipped_existing` | int |
    | `linked` | int |
    | `barangay_only` | int |
    | `duplicates` | `[row numbers]` |
    | `outside_city` | `[row numbers]` |
    | `bad_date` | `[row numbers]` |
    | `no_barangay` | `[row numbers]` |
    | `unknown_alarms` | `{alarm: count}` |
    | `unlinked` | `{barangay name: {place as typed: {'fires': n, 'close': [purok names]}}}` |

  - Command: `import_bfp_fires [file] [--dry-run] [--relink] [--names-from CSV]`.

- [ ] **Step 1: Write the failing tests**

`row(**kw)` builds a `read_sheet`-shaped dict. Its defaults are:
- `row=5`, `date=44963`, `time=2242`, `city='Talisay_City_c'`
- `location='PUROK SAMBAG, LARAY, BRGY SAN ROQUE'`
- `category='RESIDENTIAL'`, `subcategory='SINGLE AND TWO FAMILY DWELLING'`
- every casualty field `0`, `total_hurt=0`
- `damage_cost=Decimal('625000')`, `structures_affected=76`, `alarm='2ND ALARM'`

`kw` overrides any of these. `ROQUE`, `MOHON` and `CANSOJONG` are `FakeBarangay` objects (as in `test_load_puroks.py`) with ids 19, 15 and 5 and a non-null `boundary`. `MNL` is `ZoneInfo('Asia/Manila')`.

```python
def test_a_new_row_becomes_one_record(self):
    [rec], report = plan_import([row(location='PUROK SAMBAG, LARAY, BRGY SAN ROQUE')], set(), [ROQUE], {ROQUE.id: ['Purok Sambag']}, {})
    self.assertEqual(rec['barangay'], ROQUE)
    self.assertEqual(rec['purok_name'], 'Purok Sambag')
    self.assertEqual(rec['severity_level'], 'Orange')
    self.assertEqual(rec['alarm_level'], '2ND ALARM')
    self.assertEqual(rec['description'], 'BFP: RESIDENTIAL – SINGLE AND TWO FAMILY DWELLING, 2ND ALARM')
    self.assertEqual(rec['location_text'], 'PUROK SAMBAG, LARAY, BRGY SAN ROQUE')
    self.assertEqual(rec['occurred_at'], datetime(2023, 2, 6, 22, 42, tzinfo=MNL))
    self.assertTrue(rec['source_ref'].startswith('bfp:'))
    self.assertEqual((report['imported'], report['linked']), (1, 1))

def test_existing_refs_are_skipped(self):
    r = row()
    records, report = plan_import([r], {bfp.source_ref(bfp.parse_when(r['date'], r['time']), r['location'])}, [ROQUE], {}, {})
    self.assertEqual((records, report['skipped_existing']), ([], 1))

def test_an_exact_repeat_is_imported_once(self):
    records, report = plan_import([row(row=190), row(row=191)], set(), [ROQUE], {}, {})
    self.assertEqual(len(records), 1)
    self.assertEqual(report['duplicates'], [191])

def test_same_time_and_place_but_a_different_fire_gets_its_own_ref(self):
    records, report = plan_import([row(row=7), row(row=8, subcategory='RUBBISH')], set(), [ROQUE], {}, {})
    self.assertEqual(len(records), 2)
    self.assertEqual(records[1]['source_ref'], records[0]['source_ref'] + ':2')
    self.assertEqual(report['duplicates'], [])

def test_rows_outside_talisay_and_bad_dates_are_listed_not_imported(self):
    records, report = plan_import([row(row=9, city='Toledo_City'), row(row=10, date='sometime')], set(), [ROQUE], {}, {})
    self.assertEqual(records, [])
    self.assertEqual((report['outside_city'], report['bad_date']), ([9], [10]))

def test_barangay_only_and_no_barangay(self):
    records, report = plan_import([row(row=4, location='Mohon, Talisay City Cebu'),
                                   row(row=5, location='Sitio Napo, Talisay City Cebu')], set(), [ROQUE, MOHON], {}, {})
    self.assertEqual([r['purok_name'] for r in records], [None, None])
    self.assertEqual(records[1]['barangay'], None)
    self.assertEqual((report['barangay_only'], report['no_barangay']), (1, [5]))

def test_unlinked_names_are_listed_with_close_purok_names(self):
    _, report = plan_import([row(location='Sitio Ibacan, Cansojong, Talisay City Cebu')], set(),
                            [CANSOJONG], {CANSOJONG.id: ['Sitio Ebacan']}, {})
    self.assertEqual(report['unlinked']['Cansojong']['Sitio Ibacan'], {'fires': 1, 'close': ['Sitio Ebacan']})

def test_unknown_alarm_is_low_and_listed(self):
    [rec], report = plan_import([row(alarm='ALARM X')], set(), [ROQUE], {}, {})
    self.assertEqual(rec['severity_level'], 'Green')
    self.assertEqual(report['unknown_alarms'], {'ALARM X': 1})
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `venv/Scripts/python.exe manage.py test tests.test_bfp_import`
Expected: an ERROR, because `apps.history.bfp_import` doesn't exist.

- [ ] **Step 3: Add the model fields and make the migration**

Run: `venv/Scripts/python.exe manage.py makemigrations history --name bfp_fields`
Expected: `0003_bfp_fields.py` with the fields above, depending on `('barangays', '0002_purok')`. Don't migrate yet (Task 6).

- [ ] **Step 4: Implement `plan_import`**

- **An exact repeat** has the same value in every key as an earlier row in this run, ignoring `row`. It goes in `duplicates` and is not imported.
- **A different row with an already-used `source_ref`** gets `:2`, then `:3` and so on. This is stable across re-runs of the same file.
- Check `existing_refs` against the final, suffixed ref.
- `close` comes from `difflib.get_close_matches(place, purok_names, n=3, cutoff=0.75)`, comparing `norm_name`s.
- The description is `f'BFP: {category} – {subcategory}, {alarm}'`.
- `total_displaced` is `None`. `is_sample` is `False`.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `venv/Scripts/python.exe manage.py test tests.test_bfp_import`
Expected: `OK`

- [ ] **Step 6: Implement the command**

- Requires `HazardType` `name__iexact='Fire'`. Otherwise it raises `CommandError('No "Fire" hazard type.')`.
- **Default:** reads Barangays and puroks from the database, `existing_refs` from `HistoricalRecord.source_ref`, and variants from `name_variants.csv`. It writes every record and its purok in one `transaction.atomic()`. The purok is found by `(barangay_id, name)`.
- **`--dry-run`:** writes nothing.
- **`--names-from CSV`** (a `purok_points.csv`-shaped file): purok names come from that CSV, with each row's barangay matched through `match_barangay`. It implies `--dry-run`, and it never queries `HistoricalRecord`. That way it works before the migration and before a purok reload.
- **`--relink`** (no file): re-runs `link_address` on every record whose `source_ref` starts with `bfp:`, then resets its `puroks`. It prints how many records are linked, how many are barangay-only, and how many changed.
- **Report:**
  - Each count on its own line.
  - Then the row lists.
  - Then `unlinked` per barangay, most fires first: `  Cansojong: Sitio Ibacan (1 fire) - close: Sitio Ebacan`.

- [ ] **Step 7: Check the command against the real file without touching the database's history**

Run: `venv/Scripts/python.exe manage.py import_bfp_fires <bfp.xlsx> --names-from apps/barangays/data/puroks/purok_points.csv`
Expected:
- `read 219`
- `outside city: 1`
- `duplicates: [191]`
- `bad dates: []`
- `imported 217`
- An `unlinked` list. Keep its output for Task 5.

- [ ] **Step 8: Run the backend tests and commit**

Run: `venv/Scripts/python.exe manage.py test tests`
Expected: `OK`

```bash
git add backend/apps/history backend/apps/barangays/data/puroks/name_variants.csv backend/tests/test_bfp_import.py
git commit -m "Import the BFP fire log as fire history"
```

---

### Task 5: Clean up the purok list against the BFP log

No new code. Each step is checked against the dry-run report from Task 4, Step 7.

**Files:**
- Modify: `backend/apps/barangays/data/puroks/purok_points.csv`, `community_outlines.geojson` (renamed outlines only), `name_variants.csv`, `SOURCES.md`, `talisay_puroks_estimated.geojson` (rebuilt)
- Create: `backend/apps/barangays/data/puroks/needs_barangay_check.csv` with the columns `barangay,name,kind,fires,example_address,searched`

- [ ] **Step 1: Respell to the BFP**

For each `unlinked` entry with a `close` match in the same barangay:
- Rename the CSV row to the BFP spelling. Where the BFP uses two spellings, use the one it uses most.
- Rename its outline in `community_outlines.geojson` if it has one, since outlines are keyed by `(barangay, name)`.
- Add the old spelling to `name_variants.csv`.

Then:
- Set every `Tabunoc` barangay cell to `Tabunok`.
- Add a row for each `unlinked` place labelled Purok or Sitio that isn't in the CSV. Its kind comes from the label, `sources` is `fire log`, and `lat`/`lng` are blank.

- [ ] **Step 2: Re-run the dry run**

Run: the command from Task 4, Step 7.
Expected: none of the `unlinked` entries has a `close` match left.

- [ ] **Step 3: Research a location for every BFP name that has none**

These are the rows whose `sources` include `fire log` and whose `lat` is blank (58 before Step 1).

- **Where to search:**
  - OpenStreetMap: Nominatim `q="<name>, <barangay>, Talisay, Cebu"`, one request a second with a User-Agent, and Overpass inside the barangay's bounding box
  - Overture Maps places, the newest release
  - Wikimapia
  - SunStar, The Freeman, GMA and DSWD DROMIC reports
- **When found:**
  - Fill `lat`, `lng` and `placed_by` in the style of the existing rows.
  - Set `confidence` by the rules in `SOURCES.md`.
  - Append the source to `sources`.
- **When not found:** add a row to `needs_barangay_check.csv` with:
  - its fire count
  - one example address
  - `searched` = the sources tried

Add any new source to the `SOURCES.md` table with today's date, and add the two new files to its files table.

- [ ] **Step 4: Rebuild the estimates**

Run: `venv/Scripts/python.exe manage.py build_purok_estimates`
Expected: `Wrote N estimated purok areas`. Then count features named `Unnamed area …` in the output file: there should be fewer than 131. Write the before/after numbers per barangay in the commit message.

- [ ] **Step 5: Dry-run the load and show the user**

Run: `venv/Scripts/python.exe manage.py load_puroks --dry-run`
Expected:
- No problems.
- `Dry run: N puroks checked, nothing saved.`
- The per-barangay overlap report.

Give the user the report and the unnamed-area numbers, then **stop for their OK** to load.

- [ ] **Step 6: Commit the data**

```bash
git add backend/apps/barangays/data/puroks
git commit -m "Clean up purok names and places against the BFP fire log"
```

---

### Task 6: Load and import on the shared database (each step needs the user's OK)

- [ ] **Step 1: Load the cleaned puroks**

Run: `venv/Scripts/python.exe manage.py load_puroks`
Expected: `Loaded N puroks for 22 barangays.`

- [ ] **Step 2: Migrate history**

Run: `venv/Scripts/python.exe manage.py migrate history`
Expected: `Applying history.0003_bfp_fields... OK`

- [ ] **Step 3: Dry-run the import against the database**

Run: `venv/Scripts/python.exe manage.py import_bfp_fires <bfp.xlsx> --dry-run`
Expected:
- `read 219`
- `imported 217`
- `skipped_existing 0`
- A `linked` count. Show the user the report.

- [ ] **Step 4: Import**

Run: `venv/Scripts/python.exe manage.py import_bfp_fires <bfp.xlsx>`, then run the same command again.
Expected: the first run says `imported 217`. The second says `imported 0`, `skipped_existing 217`.

- [ ] **Step 5: Spot-check**

Run: `venv/Scripts/python.exe manage.py shell -c "from apps.history.models import HistoricalRecord as H; q=H.objects.filter(source_ref__startswith='bfp:'); print(q.count(), q.filter(puroks__isnull=False).distinct().count())"`
Expected: `217 <linked count from Step 3>`.
