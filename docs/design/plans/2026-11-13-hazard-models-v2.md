# Hazard Models v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the flood and landslide models with the report's two-part model (a "when" chance
times a fixed "where" share) where a pre-written rule says it is better, test a pooled Poisson
fire model with building exposure the same way, serve saved fits with NumPy, and log every
prediction in a table that is never overwritten.

**Architecture:**
- **Offline:** `fetch_rain` (now from 2006), `fetch_storms` (new), `build_hazard_features` (adds a
  NOAH and buildings exposure file) and `test_hazard_models` (fits both contenders, runs the four
  test designs, applies the rule, writes report version 2 with the fitted numbers).
- **At request time:** flood and landslide score the in-use fit from the report with NumPy (no
  scikit-learn); fire keeps refitting on request but chooses between its two models by the rule.
- **Log:** `log_hazard_predictions` (also run once a day by the warm-up thread) inserts day and month
  chances into `hazard_prediction_log`, which a trigger keeps unchangeable.

**Tech Stack:** Django 4.2 + DRF + PostGIS (GeoDjango GDAL for reading shapefiles), NumPy, SciPy,
scikit-learn 1.9.1 (fire only), `requests`; React (react-scripts, Jest).

**Spec:** `docs/design/specs/2026-11-13-hazard-models-v2-design.md` (approved 2026-11-13). Read
it beside this plan; section numbers (1.3, 2.5, 3.4…) refer to it.

## Global Constraints

**Process rules:**
- **Never commit.** No task has a commit step. Leave every file uncommitted.
- **One migration only:** `apps/history/migrations/0008_hazard_prediction_log.py`. It is applied to
  the shared database only in Task 16, after the user's go-ahead, with a backup first.
- **No hazard is forecast by counting.** A model that cannot run gives `method: "unavailable"` with a
  reason. Counting-style rates appear only as benchmark rows in tests.
- **No new Python dependency.** `xgboost-cpu` is removed from `requirements/base.txt`.
  `firthmodels` is used only in a throwaway check outside the project (Task 1).
- **NumPy-only serving:** `apps/history/firth.py`, `two_part.py`, `hazard_scoring.py` and
  `storms.py` never import scikit-learn or xgboost.
- **Backend test command** (Git Bash, from `backend/`), private test database:
  `PYTHONPATH="C:/Users/Sannichigetsu/.geoalert-test" DJANGO_SETTINGS_MODULE=geo_test_settings venv/Scripts/python.exe manage.py test <labels> --noinput > "C:/Users/Sannichigetsu/.geoalert-test/last.log" 2>&1; tail -n 15 "C:/Users/Sannichigetsu/.geoalert-test/last.log"`
  Called **`<T>`** below. Never run tests against the shared `test_postgres`. Keep the full log.
- **Frontend test command** (from `frontend/`): `CI=true npx react-scripts test --watchAll=false <pattern>`.
  Called **`<F>`**.
- **Downloads in tests:** never. Every network call takes an injectable `get=` and tests pass fakes.

**Fixed values (spec Sections 1–4):**
- Study period: `STUDY_START = date(2021, 1, 1)`, `STUDY_END = date(2025, 12, 31)` (unchanged).
- Rain: NASA POWER `PRECTOTCORR`, the city cell (10.5, 123.75); `ARCHIVE_FIRST_DAY = date(2006, 12, 18)`.
- Rain windows (unchanged, inclusive, ending on day d): r0 = d, r1 = d−1, r3 = d−2..d, r7 = d−6..d,
  r14 = d−13..d; any missing day makes the window missing.
- "When" features: Flood `('log1p_r3', 'storm72')`; Landslide `('log1p_r3', 'log1p_r14')`.
- Eras: `'geoalert'` (study period) and `'catalogue'` (2007-01-01 to the last day of the month of the
  catalogue's latest record). 2018–2020 are never rows.
- Storm flag: `STORM_RADIUS_KM = 300.0`, `STORM_HOURS = 72`, IBTrACS `ISO_TIME` (UTC), `LAT`, `LON`,
  all storm types, no interpolation.
- Catalogue: `CATALOGUE_RADIUS_KM = 20.0`; records with "negros" (any case) in their text are dropped.
- Exposure: E_b = (noah25_mh + noah100_mh + hand_lt2_buildings) / 3, Medium/High = `Var` ≥ 2.
- Shares: a_b = 1 − exp(−λ·score_b), score = E_b (flood) or exp(β·slope_gt18) (landslide); λ solves
  Σ_b a_b = k̄ (training mean of distinct barangays per event day).
- Leave one storm out: event days < 14 days apart merge into a cluster; a cluster's block is
  [first − 7, last + 7]; other days form calendar-month blocks; training excludes every day within
  `BUFFER_DAYS = 14` of the block.
- Bootstrap: `BOOTSTRAP_REPS = 1000`, seed 0. Landslide rule gate: `STEEP_GATE = 0.10`.
- PAGASA bands on 1-day rain (mm): `(50, 100, 200)`. Band/class chance = (events + 0.5) / (days + 1).
- Level cut-offs unchanged: High ≥ 0.25, Moderate ≥ 0.15 (`model_forecast.level_for`).
- Fire: `PENALTIES = (0.001, 0.003, 0.01, 0.03, 0.1, 0.3, 1.0)`, `INNER_MONTHS = 6`,
  `TEST_MONTHS = 9` (unchanged), `DISPERSION_FLAG = 1.5`, `MORAN_PERMUTATIONS = 999`, `MORAN_FLAG_P = 0.05`.
- Log: `BACKFILL_DAYS = 30`; rain source text `'NASA POWER PRECTOTCORR'`.
- Model names: flood/landslide `'two_part'` and `'logistic_regression'` (the current model); fire
  `'pooled_exposure'` (F1) and `'current'` (F0).

**URLs:**
- IBTrACS: `https://www.ncei.noaa.gov/data/international-best-track-archive-for-climate-stewardship-ibtracs/v04r01/access/csv/` +
  `ibtracs.WP.list.v04r01.csv` | `ibtracs.last3years.list.v04r01.csv` | `ibtracs.ACTIVE.list.v04r01.csv`.
- NOAH: `https://huggingface.co/datasets/bettergovph/project-noah-hazard-maps/resolve/main/Flood/25yr/Cebu.zip`
  and `.../Flood/100yr/Cebu.zip`; inside, `Cebu/PH072200000_FH_25yr.shp` / `..._FH_100yr.shp`, field `Var`.
- Catalogue: `https://data.nasa.gov/docs/legacy/Global_Landslide_Catalog_Export/Global_Landslide_Catalog_Export_rows.csv`
  (redirects to S3; follow redirects).

**Credits (exact copy, report `credits`):**
- All: `'Rain: NASA POWER (CC BY 4.0).'`
- Flood: `'Storm tracks: IBTrACS v04r01 (NOAA NCEI).'`, `'Flood exposure: UP NOAH flood hazard maps (ODbL), via the bettergovph mirror.'`, `'Buildings: Microsoft Global ML Building Footprints (ODbL).'`
- Landslide: `'Landslide timing also learned from NASA Global Landslide Catalog days near Talisay, 2007–2017.'`

## Review Focus

1. **An old (version 1) report on disk after the code changes** — the forecast and the accuracy card
   must say "run manage.py test_hazard_models" (`REPORT_OLD`), never crash. Tests in Tasks 10 and 11.
2. **Storm data that does not reach the recent days** (stale file, no network on the ping) — those
   days get no flood chance, the month rows still come from the model, nothing raises. Test in Task 11.
3. **A rain file that still starts in 2016** — `test_hazard_models` stops with "run fetch_rain"
   before writing anything; the old report stays. Test in Task 10.
4. **A barangay missing from the exposure file** — its flood row is unavailable with
   "No exposure figures for this barangay yet.", never a chance of 0. Test in Task 11.
5. **The log table not yet migrated on the database the warm-up runs against** — the forecast is
   still served; the writer logs one warning and returns False. Test in Task 13.

---

### Task 1: Firth logistic regression, FLIC and the conditional logit

**Files:**
- Create: `backend/apps/history/firth.py`
- Test: `backend/tests/test_firth.py`

**Interfaces:**
- Produces:
  - `class FitFailed(Exception)`
  - `@dataclass(frozen=True) class LogitFit: coef: np.ndarray; iterations: int` (one coefficient per
    column of X; intercept columns are ordinary indicator columns).
  - `firth_logit(X: np.ndarray, y: np.ndarray, offset: np.ndarray | None = None) -> LogitFit`
  - `flic(X: np.ndarray, y: np.ndarray, fit: LogitFit, intercept_columns: Sequence[int]) -> LogitFit`
    — keeps every other coefficient; re-fits each intercept column by plain maximum likelihood on
    the rows where that column is 1, with offset = X[:, slopes] @ coef[slopes]. Raises `FitFailed`
    when such rows hold no event or no non-event.
  - `firth_conditional_logit(groups: np.ndarray, s: np.ndarray, hit: np.ndarray) -> float` — rows are
    (event day, barangay); returns β.

- [ ] **Step 1: Write the failing tests** in `tests/test_firth.py` (`SimpleTestCase`):

```python
def test_intercept_only_matches_the_closed_form(self):
    for k, n, want in ((0, 20, math.log(0.5 / 20.5)), (3, 10, math.log(3.5 / 7.5))):
        y = np.r_[np.ones(k), np.zeros(n - k)]
        fit = firth_logit(np.ones((n, 1)), y)
        self.assertAlmostEqual(fit.coef[0], want, places=6)

def test_two_by_two_adds_a_half_to_each_cell_even_when_separated(self):
    # a=4 (x=1,y=1), b=0 (x=1,y=0), c=1 (x=0,y=1), d=5 (x=0,y=0)
    x = np.r_[np.ones(4), np.zeros(1), np.zeros(5)]
    y = np.r_[np.ones(4), np.ones(1), np.zeros(5)]
    fit = firth_logit(np.c_[np.ones(10), x], y)
    self.assertAlmostEqual(fit.coef[1], math.log(33), places=6)          # ln(4.5*5.5/(0.5*1.5))
    self.assertAlmostEqual(fit.coef[0], math.log(1.5 / 5.5), places=6)

def test_flic_reproduces_the_observed_rate(self):
    rng = np.random.default_rng(0)
    X = np.c_[np.ones(2000), rng.normal(size=(2000, 2))]
    y = np.zeros(2000); y[np.argsort(X[:, 1])[-6:]] = 1           # 6 events, all at high x1
    fixed = flic(X, y, firth_logit(X, y), [0])
    p = 1 / (1 + np.exp(-(X @ fixed.coef)))
    self.assertAlmostEqual(p.mean(), y.mean(), places=10)
    np.testing.assert_allclose(fixed.coef[1:], firth_logit(X, y).coef[1:])

def test_flic_fits_each_era_intercept_on_its_own_rows(self):
    # columns: [is_geoalert, is_catalogue, x]; each era's mean predicted chance equals its own rate
def test_flic_refuses_an_era_without_events(self):     # raises FitFailed
def test_offset_shifts_the_linear_predictor(self):     # firth_logit(X, y, offset=c) == coef of (X, y) with c folded in
def test_non_convergence_raises(self):                 # patched MAX_ITER = 1 → FitFailed
def test_conditional_logit_is_stationary_and_finite(self):
    # 2 event days over barangays s=[0.0, 0.5, 1.0]; day 1 hits the barangay with s=1.0, day 2 s=0.5
    beta = firth_conditional_logit(groups, s, hit)
    self.assertTrue(np.isfinite(beta) and beta > 0)
    # the penalised conditional log-likelihood's derivative at beta, by central differences (h=1e-5), is < 1e-6
def test_conditional_logit_stays_finite_when_the_steepest_is_always_hit(self):
```

- [ ] **Step 2: Run** `<T> tests.test_firth` — Expected: FAIL (`ModuleNotFoundError: apps.history.firth`).

- [ ] **Step 3: Implement `firth.py`** (spec 1.2). Newton on the modified score
  U* = Xᵀ(y − p + h ⊙ (½ − p)), h = diag(W^½ X (XᵀWX)⁻¹ Xᵀ W^½), step-halving while the penalised
  log-likelihood ℓ + ½·log|XᵀWX| falls; `TOL = 1e-8` on the largest coefficient change;
  `MAX_ITER = 100` then `FitFailed`. The conditional logit: per group, P(hit) = softmax(β·s) over the
  group's rows; maximise Σ log-likelihood + ½·log I(β) by 1-D Newton with step-halving.

- [ ] **Step 4: Run** `<T> tests.test_firth` — Expected: all PASS.

- [ ] **Step 5: Throwaway cross-check (outside the project).** In the scratchpad, create a fresh venv,
  `pip install firthmodels numpy`, fit the same random design (seed 0, 2,000 rows, 3 columns, 6 events)
  with both, and confirm the coefficients agree within 1e-6. Delete the venv. Record the result in
  the task report; nothing is added to the project.

---

### Task 2: Rain from 2006

**Files:**
- Modify: `backend/apps/history/rain.py:34-35` (`ARCHIVE_FIRST_DAY`, `CSV_FIRST_DAY_LIMIT`)
- Modify: `backend/apps/history/management/commands/fetch_rain.py` (help text: "2006-12-18")
- Test: `backend/tests/test_rain.py`

**Interfaces:**
- Produces: `rain.ARCHIVE_FIRST_DAY == date(2006, 12, 18)`; `rain.CSV_FIRST_DAY_LIMIT == date(2006, 12, 18)`.

- [ ] **Step 1: Update the tests** in `tests/test_rain.py`: wherever a test pins 2016-12-18 or
  2020-12-18, pin `date(2006, 12, 18)`; add `test_archive_reaches_back_to_2006` asserting both
  constants, and that `download_archive` with a fake getter asks POWER for the year spans 2006–end
  (first request ends at the end date, last starts on 2006-12-18).

- [ ] **Step 2: Run** `<T> tests.test_rain` — Expected: FAIL on the new values.

- [ ] **Step 3: Change the two constants and the help text.**

- [ ] **Step 4: Run** `<T> tests.test_rain tests.test_hazard_scenarios` — Expected: PASS.

---

### Task 3: Storm days from IBTrACS

**Files:**
- Create: `backend/apps/history/storms.py`
- Create: `backend/apps/history/management/commands/fetch_storms.py`
- Test: `backend/tests/test_storms.py`

**Interfaces:**
- Produces (all in `storms.py`):
  - `STORM_RADIUS_KM = 300.0`, `STORM_HOURS = 72`, `WP_URL`, `LAST3_URL`, `ACTIVE_URL`,
    `STORM_FILE = DATA_DIR / 'storm_days.csv'`, `META_FILE = DATA_DIR / 'storm_days.meta.json'`.
  - `@dataclass(frozen=True) class TrackPoint: sid: str; name: str; time: datetime; lat: float; lon: float` (time aware, UTC).
  - `@dataclass class StormDays: days: dict[date, tuple[str, str, float]]; first_day: date; last_day: date`
    with `flag(day: date) -> int | None` (1/0 inside [first_day, last_day], else None) and
    `name(day) -> str | None`.
  - `haversine_km(lat1, lon1, lat2, lon2) -> float`
  - `talisay_centre() -> tuple[float, float]` — (lat, lon) of the centroid of the union of barangay
    boundaries (database).
  - `parse_ibtracs(lines: Iterable[str], centre, since: date) -> list[TrackPoint]` — CSV with a header
    row then a units row (skipped); keeps points within `STORM_RADIUS_KM` with `ISO_TIME` on or after
    `since`.
  - `flag_days(points, centre) -> dict[date, tuple[str, str, float]]` — day → (sid, name, closest km).
  - `covered_through(last_modified: datetime) -> date` — the Manila date of `last_modified`, minus 1 day.
  - `write_storm_days(sd: StormDays, source: str, fetched: datetime, centre, path=STORM_FILE, meta_path=META_FILE)`,
    `read_storm_days(path=STORM_FILE, meta_path=META_FILE) -> StormDays` (FileNotFoundError when missing).
  - `merge(a: StormDays, b: StormDays) -> StormDays`
  - `refresh_recent(get=None, now=None) -> bool` — downloads the last-3-years file, at most once per
    Manila day, into the Django cache key `'hazard-storms-recent'` as a `StormDays`; False on failure
    (logged), never raises.
  - `live_storm_days(base: StormDays, today: date, get=None) -> StormDays` — base ∪ the cached recent
    copy ∪ the active file (cache key `'hazard-storms-active'`, 3 hours). Coverage: `today − 1` when
    the active file was read and the recent copy's `last_day` is at most 7 days before today;
    otherwise the furthest `last_day` available.

- [ ] **Step 1: Write the failing tests** (`SimpleTestCase`, a fixed centre (10.2447, 123.8494)):

```python
def test_a_point_late_on_a_manila_day_flags_that_day_and_the_next_two(self):
    p = point('2025-11-04 15:59:00')                 # UTC = 23:59 Manila on 4 Nov
    self.assertEqual(sorted(flag_days([p], CENTRE)), [date(2025, 11, 4), date(2025, 11, 5), date(2025, 11, 6)])

def test_a_point_at_manila_midnight_belongs_to_the_day_before(self):
    p = point('2025-11-04 16:00:00')                 # 00:00 Manila on 5 Nov = end of 4 Nov
    self.assertEqual(sorted(flag_days([p], CENTRE)), [date(2025, 11, 4), date(2025, 11, 5), date(2025, 11, 6)])

def test_points_beyond_300_km_are_dropped(self):    # 299 km kept, 301 km dropped (offsets along a meridian)
def test_units_row_is_skipped_and_since_is_respected(self):
def test_closest_distance_and_name_are_kept_per_day(self):
def test_covered_through_is_the_manila_day_before_the_file_time(self):
    self.assertEqual(covered_through(datetime(2026, 11, 12, 10, 6, 46, tzinfo=UTC)), date(2026, 11, 11))
def test_flag_is_none_outside_coverage(self):
def test_write_and_read_round_trip(self):           # tmp dir
def test_live_coverage_reaches_yesterday_only_with_a_fresh_recent_copy_and_the_active_file(self):
def test_live_coverage_falls_back_when_the_active_file_fails(self):   # fake get raises → last_day = recent copy's
def test_refresh_recent_runs_once_a_day_and_never_raises(self):
```

- [ ] **Step 2: Run** `<T> tests.test_storms` — Expected: FAIL (module missing).

- [ ] **Step 3: Implement `storms.py`.** Download with `requests` (stream, `iter_lines(decode_unicode=True)`),
  the `Last-Modified` header gives coverage. Use `rain.USER_AGENT`. `talisay_centre` uses
  `Barangay.objects.exclude(boundary__isnull=True).aggregate(Union('boundary'))` then `.centroid`.

- [ ] **Step 4: Implement `fetch_storms`** (`--recent` reads only the last-3-years file and merges into
  the existing file; without it, reads the WP file from `rain.ARCHIVE_FIRST_DAY`, then merges the
  last-3-years file). Prints days flagged, first/last covered day and the centre.

- [ ] **Step 5: Add** `test_command_writes_the_files_with_a_fake_download` (`TestCase`, patched
  `storms.get`, two barangays with boundaries, `DATA_DIR` pointed at a temp dir).

- [ ] **Step 6: Run** `<T> tests.test_storms` — Expected: PASS.

---

### Task 4: The exposure file (NOAH and buildings)

**Files:**
- Create: `backend/apps/history/exposure.py`
- Modify: `backend/apps/history/management/commands/build_hazard_features.py`
- Modify: `backend/apps/barangays/purok_estimate.py` (receives `BUILDINGS_INDEX`, `BUILDINGS_TILE`)
- Modify: `backend/apps/barangays/management/commands/build_purok_estimates.py:34-35` (imports them)
- Create: `backend/apps/history/data/ATTRIBUTION.md`
- Test: `backend/tests/test_exposure.py`

**Interfaces:**
- Consumes: `susceptibility.city_grid`, `draw_polygons(grid, polygons)`, `count_points(grid, points)`,
  `compute_factors(...)['hand']`, `purok_estimate.building_centres(lines, bbox)`.
- Produces (in `exposure.py`):
  - `NOAH_URLS = {25: ..., 100: ...}`, `NOAH_LAYERS = {25: 'Cebu/PH072200000_FH_25yr.shp', 100: 'Cebu/PH072200000_FH_100yr.shp'}`
  - `EXPOSURE_FILE = DATA_DIR / 'barangay_exposure.csv'`
  - `EXPOSURE_COLUMNS = ('buildings', 'noah25_mh', 'noah100_mh', 'hand_lt2_buildings', 'exposure')`
  - `download_noah(cache_dir: Path, period: int, refresh: bool, log, get=None) -> Path`
  - `noah_polygons(path: str, bbox) -> list[tuple[int, list]]` — any OGR-readable path (`/vsizip/...`
    for the zips); each feature's `Var` and its geometry clipped to `bbox = (south, west, north, east)`,
    as `(var, [outer_ring, hole, ...])` per polygon, lng/lat.
  - `city_buildings(cache_dir: Path, bbox, refresh: bool, log, get=None) -> list[tuple[float, float]]`
    — its own cache file `ms_buildings_city_<tile>.json` (the purok build's cache is never widened).
  - `exposure_rows(labels, counts, noah25, noah100, hand, barangay_ids) -> dict[int, dict[str, float]]`
  - `write_exposure(path, rows, names)`, `read_exposure(path=EXPOSURE_FILE) -> dict[int, dict[str, float]]`

- [ ] **Step 1: Write the failing tests:**

```python
def test_exposure_counts_buildings_inside_each_layer(self):
    labels = np.array([[1, 1], [2, 2]]); counts = np.array([[3., 1.], [2., 0.]])
    noah25 = np.array([[2, 0], [3, 3]]); noah100 = np.array([[2, 2], [1, 3]]); hand = np.array([[1., 5.], [1., 1.]])
    rows = exposure_rows(labels, counts, noah25, noah100, hand, [1, 2])
    self.assertEqual(rows[1], {'buildings': 4, 'noah25_mh': 3, 'noah100_mh': 4, 'hand_lt2_buildings': 3,
                               'exposure': (3 + 4 + 3) / 3})
    self.assertEqual(rows[2]['noah100_mh'], 0)        # Var 1 is Low, not Medium/High

def test_noah_polygons_reads_var_and_clips_to_the_box(self):
    # a GeoJSON file in a temp dir with two squares, Var 2 and Var 3, one half outside the box
def test_round_trip_and_column_order(self):
def test_buildings_never_overwrite_the_purok_cache(self):     # fake get; the purok file's bytes are unchanged
```

- [ ] **Step 2: Run** `<T> tests.test_exposure` — Expected: FAIL.

- [ ] **Step 3: Implement `exposure.py`** with `django.contrib.gis.gdal.DataSource` and
  `OGRGeometry.intersection` against the box envelope. Move `BUILDINGS_INDEX`/`BUILDINGS_TILE` into
  `purok_estimate.py` and import them in `build_purok_estimates.py`.

- [ ] **Step 4: Extend `build_hazard_features`:** after the terrain rows, download the two NOAH zips,
  rasterise `Var` on the same grid (`draw_polygons`, values 1–3), count city buildings per cell, write
  `barangay_exposure.csv`, and print each barangay's row. Write `ATTRIBUTION.md` (by hand, once):
  the exposure file is derived from UP NOAH flood hazard maps (ODbL, via the bettergovph mirror) and
  Microsoft Global ML Building Footprints (ODbL) and is offered under the ODbL; `storm_days.csv` is
  derived from IBTrACS v04r01 (NOAA NCEI; commercial use subject to WMO Resolution 40).

- [ ] **Step 5: Run** `<T> tests.test_exposure tests.test_purok_estimate` — Expected: PASS.

---

### Task 5: The NASA landslide catalogue

**Files:**
- Create: `backend/apps/history/landslide_catalogue.py`
- Create: `backend/apps/history/data/landslide_catalogue_exclusions.csv` (header `event_id,reason` only)
- Test: `backend/tests/test_landslide_catalogue.py`

**Interfaces:**
- Consumes: `storms.haversine_km`, `apps.barangays.aliases.canonical`.
- Produces:
  - `CATALOGUE_URL`, `CACHE_NAME = 'nasa_global_landslide_catalog.csv'`, `CATALOGUE_RADIUS_KM = 20.0`,
    `EXCLUSIONS_FILE = DATA_DIR / 'landslide_catalogue_exclusions.csv'`
  - `@dataclass(frozen=True) class CatalogueRecord: event_id: str; day: date; lat: float; lon: float; accuracy: str; text: str`
    (`text` joins `event_title`, `location_description`, `admin_division_name`, `gazeteer_closest_point`).
  - `ensure_catalogue(cache_dir: Path, get=None) -> Path` — downloads (following redirects) only when
    the cached file is missing.
  - `read_catalogue(path) -> list[CatalogueRecord]` — `event_date` like `08/01/2008 12:00:00 AM` →
    `date(2008, 8, 1)`; rows without a date or coordinates are skipped.
  - `load_exclusions(path=EXCLUSIONS_FILE) -> dict[str, str]`
  - `near(records, centre, excluded: Mapping[str, str], radius_km=CATALOGUE_RADIUS_KM) -> list[CatalogueRecord]`
  - `era_end(records) -> date` — last day of the month of the latest record (all records).
  - `named_barangay(record, names: Mapping[int, str]) -> int | None` — the one barangay whose
    canonical name appears in `location_description`, only when the text also contains "talisay";
    "Camp 4" and "Camp IV" both name Camp IV.

- [ ] **Step 1: Write the failing tests** with a 6-row CSV fixture string (real column order from the
  spec's header):

```python
def test_dates_coordinates_and_text_are_read(self):
def test_near_keeps_20_km_and_drops_negros_and_listed_ids(self):
    # rows: 5 km (kept), 25 km (dropped), 3 km with admin 'Negros Occidental' (dropped), 4 km listed in exclusions (dropped)
def test_era_end_is_the_month_end_of_the_latest_record(self):      # latest 2017-09-12 → date(2017, 9, 30)
def test_named_barangay_needs_talisay_and_one_name(self):
    self.assertEqual(named_barangay(rec('Sitio X, Manipis, Talisay City'), NAMES), MANIPIS_ID)
    self.assertEqual(named_barangay(rec('Camp 4, Talisay, Cebu'), NAMES), CAMP_IV_ID)
    self.assertIsNone(named_barangay(rec('Manipis Road, Toledo'), NAMES))     # no "talisay"
def test_ensure_downloads_only_when_missing(self):
```

- [ ] **Step 2: Run** `<T> tests.test_landslide_catalogue` — Expected: FAIL.

- [ ] **Step 3: Implement.** Add a "camp 4" alias in `aliases.py` only if `canonical('Camp 4') != canonical('Camp IV')`.

- [ ] **Step 4: Run** `<T> tests.test_landslide_catalogue tests.test_load_puroks` — Expected: PASS.

---

### Task 6: The two-part model

**Files:**
- Create: `backend/apps/history/two_part.py`
- Test: `backend/tests/test_two_part.py`

**Interfaces:**
- Consumes: Task 1 (`firth_logit`, `flic`, `firth_conditional_logit`, `FitFailed`), Task 3 (`StormDays`),
  `hazard_data.rain_windows`.
- Produces:
  - `FEATURES = {'Flood': ('log1p_r3', 'storm72'), 'Landslide': ('log1p_r3', 'log1p_r14')}`
  - `when_row(hazard: str, rain: Mapping[date, float | None], storms: StormDays | None, day: date) -> list[float] | None`
    — None when a rain window is missing or (flood) the storm flag is None.
  - `raw_rain(rain, day) -> dict[str, float] | None` — the r0..r14 sums (for `training_max` and the log).
  - `@dataclass class WhenFit: features: tuple[str, ...]; coef: np.ndarray; intercepts: dict[str, float]`
    with `chance(X: np.ndarray, era: str = 'geoalert') -> np.ndarray`.
  - `fit_when(X: np.ndarray, y: np.ndarray, era: np.ndarray | None = None) -> WhenFit` — design
    [one indicator per era present, then X]; Firth then FLIC on every indicator.
  - `solve_lambda(scores: Mapping[int, float], k: float) -> float` — raises `ValueError` when k is not
    below the number of barangays with a positive score.
  - `flood_shares(exposure: Mapping[int, float], k: float) -> tuple[dict[int, float], float]`
  - `landslide_shares(steep: Mapping[int, float], events: Sequence[set[int]], k: float) -> tuple[dict[int, float], float, float]`
    — (shares, λ, β).
  - `@dataclass class TwoPartFit: hazard: str; when: WhenFit; shares: dict[int, float]; lam: float; beta: float | None; training_max: dict[str, float]`
    with `to_json() -> dict` and `TwoPartFit.from_json(data) -> TwoPartFit` (barangay keys as strings
    in JSON, ints in Python; `kind: 'two_part'`).
  - `NO_EXPOSURE = 'No exposure figures for this barangay yet.'`

- [ ] **Step 1: Write the failing tests:**

```python
def test_when_row_uses_trailing_windows_and_the_storm_flag(self):
    row = when_row('Flood', rain, storms, date(2025, 11, 4))
    self.assertEqual(row, [math.log1p(rain_sum(2025-11-02..2025-11-04)), 1.0])
    self.assertIsNone(when_row('Flood', rain, storms_ending_nov_3, date(2025, 11, 4)))   # flag unknown
def test_landslide_when_row_needs_14_days(self):
def test_fit_when_flood_has_one_intercept_and_reproduces_the_rate(self):
def test_fit_when_landslide_has_an_intercept_per_era_and_uses_geoalert_by_default(self):
def test_solve_lambda_hits_the_target_and_keeps_the_ranking(self):
    shares, lam = flood_shares({1: 10.0, 2: 40.0, 3: 0.0, 4: 100.0}, k=1.5)
    self.assertAlmostEqual(sum(shares.values()), 1.5, places=9)
    self.assertEqual(shares[3], 0.0)
    self.assertEqual(sorted(shares, key=shares.get), [3, 1, 2, 4])
def test_solve_lambda_refuses_an_impossible_target(self):          # k=3 with 3 positive scores → ValueError
def test_landslide_shares_rank_steeper_barangays_higher(self):     # events all in the steepest → beta > 0
def test_round_trip_json(self):                                    # from_json(to_json(f)) gives equal chances
def test_no_sklearn_import(self):                                  # subprocess: import two_part; 'sklearn' not in sys.modules
```

- [ ] **Step 2: Run** `<T> tests.test_two_part` — Expected: FAIL.

- [ ] **Step 3: Implement `two_part.py`** (spec 1.3–1.4). `solve_lambda` by bisection on λ ∈ (0, ∞)
  (expand the upper bound until Σ a_b > k, then 200 bisection steps).

- [ ] **Step 4: Run** `<T> tests.test_two_part` — Expected: PASS.

---

### Task 7: The current model exported, NumPy scoring, trees removed

**Files:**
- Create: `backend/apps/history/hazard_scoring.py`
- Modify: `backend/apps/history/hazard_models.py` (remove RF, XGBoost, Platt, `select_winner`,
  `calibration_reason`, `fit_candidate`, `predict`, `Fitted`, `MONOTONE`, `SPEED_OVERRIDES`,
  the old `bootstrap`/`calibration`/`threshold_metrics`, `evaluate_hazard` and its helpers,
  `_monthly_check`; keep `LR_SETTINGS`, `scores`, `benchmark_probs`, `no_skill`, `to_json_safe`,
  `read_report`, `REPORT_PATH`, `timing_auc`, `place_auc`, `_auc`)
- Modify: `backend/requirements/base.txt` (delete the `xgboost-cpu` line and its comment)
- Modify: `backend/tests/test_hazard_models.py` (delete tests of the removed functions; `ReportTests`
  and `ReportCommandTests` are rewritten in Task 10 — mark them `@skip('rewritten in Task 10')` now)
- Test: `backend/tests/test_hazard_scoring.py`

**Interfaces:**
- Produces:
  - `hazard_models.make_logistic() -> Pipeline` (median imputer, log1p on the 5 rain columns, scaler,
    `LogisticRegression(**LR_SETTINGS)` — the existing `make_pipeline('logistic_regression', ...)`).
  - `hazard_models.export_logistic(pipeline, features: tuple[str, ...], X_train: np.ndarray) -> dict` —
    `{'kind': 'logistic_regression', 'features', 'medians', 'log_columns': [0, 1, 2, 3, 4], 'mean',
    'scale', 'coef', 'intercept', 'training_max': {feature: max over X_train}}`.
  - `hazard_scoring.FitError(Exception)`
  - `hazard_scoring.score_logistic(fit: dict, X: np.ndarray) -> np.ndarray`
  - `hazard_scoring.score_two_part(fit: dict, when_X: np.ndarray, day_index: np.ndarray, barangay_ids: np.ndarray) -> np.ndarray`
    — q per day row times the barangay's share (`FitError` for a barangay without a share).

- [ ] **Step 1: Write the failing tests:**

```python
def test_numpy_scoring_matches_the_pipeline(self):
    terrain, rain, pos = toy_inputs(n_barangays=4)
    ds, _ = build_dataset('Flood', terrain, rain, pos, STUDY_START, STUDY_END)
    X = ds.X.copy(); X[::50, 6] = np.nan                     # imputation is exercised
    pipe = make_logistic().fit(X, ds.y)
    fit = export_logistic(pipe, ds.features, X)
    np.testing.assert_allclose(score_logistic(fit, X), pipe.predict_proba(X)[:, 1], atol=1e-9, rtol=0)
def test_two_part_scoring_is_q_times_share(self):
def test_a_barangay_without_a_share_is_an_error(self):
def test_scoring_imports_no_sklearn(self):                  # subprocess check, as Task 6
def test_xgboost_is_not_required(self):                     # 'xgboost' not in requirements/base.txt
```

- [ ] **Step 2: Run** `<T> tests.test_hazard_scoring` — Expected: FAIL.

- [ ] **Step 3: Implement** the export and `hazard_scoring.py`; remove the listed code and tests; edit
  requirements.

- [ ] **Step 4: Run** `<T> tests.test_hazard_scoring tests.test_hazard_models tests.test_hazard_data`
  — Expected: PASS (skips allowed only on the two marked classes).

---

### Task 8: Test designs, contenders and baselines

**Files:**
- Create: `backend/apps/history/hazard_tests.py` (part 1)
- Test: `backend/tests/test_hazard_tests.py`

**Interfaces:**
- Consumes: Tasks 5–7, `hazard_data.Dataset`, `build_dataset`, `benchmark_probs`.
- Produces:
  - `@dataclass class HazardData:` `hazard: str`; `rows: Dataset` (study barangay-days, the current
    model's features); `city_day: np.ndarray` (datetime64[D], study days with complete "when" inputs,
    sorted); `city_X`, `city_y` (any kept record that day, barangay known or not); `extra_day`,
    `extra_X`, `extra_y` (landslide catalogue era, else None); `place: dict[int, float]` (E_b or
    `slope_gt18`); `named_events: list[tuple[date, set[int]]]`; `extra_named: list[tuple[date, set[int]]]`;
    `rain: dict[date, float | None]` (the city series); `records: list[Record]`.
  - `build_hazard_data(hazard, terrain, rain_file, storms, exposure, records, excluded, catalogue=None, names=None) -> HazardData`
  - `@dataclass(frozen=True) class Block: label: str; kind: str; start: date; end: date` (`kind` is
    `'event'` or `'month'`).
  - `BUFFER_DAYS = 14`, `CLUSTER_GAP_DAYS = 14`, `CLUSTER_PAD_DAYS = 7`
  - `event_clusters(event_days: Sequence[date]) -> list[list[date]]`
  - `loso_blocks(days: Sequence[date], event_days: Sequence[date]) -> list[Block]`
  - `train_mask(days: np.ndarray, block: Block) -> np.ndarray` (True = more than 14 days from the block)
  - Contender protocol: `name: str`; `fit(data: HazardData, train: np.ndarray) -> object` (`train` is a
    boolean mask over `data.city_day`); `predict(fitted, data, days: np.ndarray) -> np.ndarray` (chance
    for every `data.rows` row whose day is in `days`, in row order).
  - Contenders: `TwoPartContender(hazard)`, `LogisticContender(hazard)`.
  - Baselines: `Climatology`, `BarangayRate`, `PagasaBands`, `RainOnly`, `Persistence`, `ReturnLevel`,
    `SevenDayP95`, with `name` values `'climatology', 'rate', 'pagasa_bands', 'rain_only', 'persistence',
    'return_level', 'p95_7day'`; `BASELINES = {'Flood': ('climatology', 'rate', 'pagasa_bands',
    'rain_only', 'persistence'), 'Landslide': ('climatology', 'rate', 'persistence', 'return_level',
    'p95_7day')}`.
  - `out_of_fold(contender, data: HazardData, blocks: list[Block]) -> np.ndarray` — one chance per
    `data.rows` row; asserts (raises `LeakageError`) when a training day lies within 14 days of its block.
  - `yearly_folds(contender, data) -> list[dict]` (FOLDS as before: test 2023, 2024, 2025).
  - `cluster_bootstrap(row_day: np.ndarray, blocks: list[Block], losses: dict[str, np.ndarray], reps=1000, seed=0) -> dict`
    — `{'intervals': {name: (low, high)}, 'differences': {(a, b): (mean, low, high)}}` of mean row losses.

- [ ] **Step 1: Write the failing tests** (synthetic data from `tests/hazard_fixtures.toy_inputs`):

```python
def test_flood_clusters_merge_days_under_14_apart(self):
    days = [date(2022, 7, 1), date(2025, 8, 12), date(2025, 8, 18), date(2025, 10, 7), date(2025, 11, 4)]
    self.assertEqual(len(event_clusters(days)), 4)
def test_blocks_cover_every_day_once(self):
def test_event_block_is_padded_seven_days(self):            # 2025-08-12..18 → 2025-08-05..2025-08-25
def test_training_never_touches_the_buffer(self):          # for every block, no train day within 14 days
def test_out_of_fold_gives_every_row_one_chance_and_raises_on_leakage(self):
def test_two_part_contender_refits_lambda_from_training_events_only(self):
def test_landslide_catalogue_rows_are_always_in_training(self):
def test_pagasa_bands_use_the_half_and_one_smoothing(self):   # 1 event in 3 training days of band → 1.5/4
def test_rules_spread_evenly_over_the_steep_gate(self):       # barangays below 0.10 steep share get 0
def test_return_level_uses_gumbel_moments_on_training_years(self):
def test_bootstrap_keeps_a_day_together_and_is_seeded(self):
```

- [ ] **Step 2: Run** `<T> tests.test_hazard_tests` — Expected: FAIL.

- [ ] **Step 3: Implement part 1 of `hazard_tests.py`.** Gumbel by moments: β = s·√6/π, μ = mean − 0.5772·β,
  T₂ = μ − β·ln(−ln(0.5)). Rule baselines give each gated barangay (city chance) × k̄ / (number gated)
  capped at 1; non-rule baselines without a "where" give (city chance) × k̄ / 22.

- [ ] **Step 4: Run** `<T> tests.test_hazard_tests` — Expected: PASS.

---

### Task 9: Scores, the event table, the outside test and the rule

**Files:**
- Modify: `backend/apps/history/hazard_tests.py` (part 2)
- Test: `backend/tests/test_hazard_tests.py`

**Interfaces:**
- Consumes: Task 8.
- Produces:
  - `model_scores(y, p, p_climatology, p_rate) -> dict` — `log_loss, brier, brier_skill_climatology,
    brier_skill_rate, pr_auc, no_skill_pr_auc, roc_auc`.
  - `when_scores(data, p) -> dict` (`auc`, `log_loss` on city-days, city chance 1 − Π(1 − p)).
  - `where_scores(data, p) -> dict` (`auc` mean over event days with both outcomes, `lift` = share of
    hit rows in the day's top 5 by chance ÷ (5/22)).
  - `level_tables(data, p, cutoffs=(0.25, 0.15)) -> list[dict]` — barangay-months, chance
    1 − Π(1 − p); per cut-off `hits, misses, false_alarms, correct_negatives, pod, far, peirce, sedi,
    false_alarms_per_event` (None when undefined).
  - `breakeven(cutoffs=(0.25, 0.15)) -> list[dict]` — `{'cutoff': c, 'false_alarms_per_event': (1-c)/c}`.
  - `per_year(data, p) -> list[dict]` — `year, observed, expected, low, high` (exact Poisson:
    `chi2.ppf(0.025, 2k)/2`, `chi2.ppf(0.975, 2k+2)/2`).
  - `event_table(data, preds: dict[str, np.ndarray]) -> list[dict]` — per event day: `day, subtypes,
    storm, r1, r3, band, models: {name: {hit_chance, hit_chance_before, city_chance, high_barangays}}`.
  - `outside_test(data: HazardData, current_fit: dict) -> dict | None` — None for flood. Landslide:
    `{'current': {'auc', 'observed', 'expected'}, 'catalogue_to_geoalert': {'auc', 'slopes'},
    'geoalert_to_catalogue': {'auc', 'slopes'}}`; `current_fit` is the exported logistic fit on the
    study period; the two cross-era "when" fits are made inside with `fit_when` (spec 2.1 item 3).
  - `verdict(data, p_new, p_cur, differences, levels_new, levels_cur) -> dict` — `{adopted, rule, reasons}`.
  - `evaluate(data: HazardData, reps=1000) -> dict` — `{'tests': {'loso': ..., 'yearly': ...,
    'events': ..., 'outside': ...}, 'verdict': ..., 'in_use': 'two_part' | 'logistic_regression'}`.

- [ ] **Step 1: Write the failing tests:**

```python
def test_sedi_and_peirce_on_a_known_table(self):
    # hits 3, misses 1, false alarms 10, correct negatives 86: H=0.75, F=10/96
    t = _table(3, 1, 10, 86)
    self.assertAlmostEqual(t['peirce'], 0.75 - 10 / 96)
    self.assertAlmostEqual(t['sedi'], sedi_formula(10 / 96, 0.75))
    self.assertAlmostEqual(t['false_alarms_per_event'], 10 / 4)
def test_breakeven_is_5_7_and_3_0(self):
    self.assertEqual([round(b['false_alarms_per_event'], 2) for b in breakeven()], [3.0, 5.67])
def test_exact_poisson_interval_for_zero_and_five(self):
def test_lift_ratio(self):
def test_rule_a_adopts_when_the_interval_is_below_zero(self):
def test_rule_b_needs_every_event_day_no_worse_and_most_better(self):
def test_rule_b_refuses_extra_false_alarms_at_high(self):
def test_not_adopted_names_the_day_it_lost(self):
    self.assertIn('2025-08-18', ' '.join(v['reasons']))
def test_evaluate_on_toy_flood_has_every_field_the_card_reads(self):
def test_outside_test_scores_catalogue_days_by_auc_only(self):
```

- [ ] **Step 2: Run** `<T> tests.test_hazard_tests` — Expected: new tests FAIL.

- [ ] **Step 3: Implement part 2** (spec 2.2–2.5). Reasons are plain sentences, for example
  `'It gave a lower chance to the hit barangays on 2025-08-18.'`, `'It raised more false alarms per
  real event at High (4.0 against 2.5).'`, `'The interval of the log-score difference does not lie
  wholly below zero.'`

- [ ] **Step 4: Run** `<T> tests.test_hazard_tests` — Expected: PASS.

---

### Task 10: Report version 2, the command, limits and accuracy entries

**Files:**
- Modify: `backend/apps/history/management/commands/test_hazard_models.py`
- Modify: `backend/apps/history/hazard_models.py` (`REPORT_VERSION = 2`, `REPORT_OLD`, `accuracy_entries`,
  `report_limits`, `credits_for`)
- Modify: `backend/tests/hazard_fixtures.py` (add `toy_report_v2(...)`)
- Test: `backend/tests/test_hazard_models.py` (rewrite `ReportTests`, `ReportCommandTests`)

**Interfaces:**
- Consumes: Tasks 3–9.
- Produces:
  - Report shape (spec 3.1): top level `version, generated, study, files, hazards`; per hazard
    `hazard, in_use, verdict, fits {two_part, logistic_regression}, rows, positives, positive_days,
    event_days, tests, limits, credits, data_signature, excluded, logged` (`logged` is None until Task 13).
  - `files` adds `exposure_sha1`, `storms_sha1`, `catalogue_sha1` (landslide), `catalogue_exclusions_sha1`.
  - `REPORT_OLD = 'The model report is from an older version; run manage.py test_hazard_models.'`
  - `accuracy_entries(today) -> list[dict]` — each `{**entry without 'fits', 'hazard', 'kind': 'rain_terrain',
    'status': 'in_use', 'stale', 'study', 'tested_at'}` or `{'hazard', 'kind', 'status': 'unavailable', 'reason'}`.
  - `report_limits(hazard, entry, *, barangays: int) -> list[str]`; `credits_for(hazard) -> list[str]`
    (the exact credit lines in Global Constraints).
  - `hazard_fixtures.toy_report_v2(path, hazards=('Flood', 'Landslide'), in_use='two_part', shares=None) -> dict`.

- [ ] **Step 1: Write the failing tests:**

```python
def test_command_refuses_a_rain_file_that_starts_after_2006(self):
    # rain file from 2016-12-18 → CommandError mentioning "fetch_rain"; the existing report is unchanged
def test_command_refuses_missing_exposure_storms_or_catalogue(self):     # each names its command; no report written
def test_command_writes_version_2_with_fits_and_verdict(self):           # fake catalogue in a temp cache dir
def test_report_is_strict_json_and_reloads_into_fits(self):              # TwoPartFit.from_json works on it
def test_accuracy_entries_flag_an_old_report(self):
    write {'generated': ..., 'hazards': {...}} without 'version' → every entry 'unavailable' with REPORT_OLD
def test_accuracy_entries_drop_the_fits_and_keep_stale(self):
def test_limits_are_plain_sentences_from_the_numbers(self):
    # includes: f"{positives} reported flood barangay-days fall on {days} distinct days"; the 0.0625 sign-test
    # sentence for 5 event days; the one-rain-cell sentence; the reported-not-happened sentence; the
    # "cut-offs and earlier choices were made after seeing 2023-2025" sentence
def test_credits_are_the_exact_lines(self):
```

- [ ] **Step 2: Run** `<T> tests.test_hazard_models` — Expected: FAIL.

- [ ] **Step 3: Implement the command:** read rain (CommandError unless `rain.first_day <= ARCHIVE_FIRST_DAY`),
  terrain, exclusions, exposure, storms, catalogue (`ensure_catalogue(BASE_DIR / '.hazard_cache')`,
  catalogue exclusions), names from the database, `talisay_centre()`; for each hazard
  `build_hazard_data` → `evaluate` → fit both contenders on all rows → `export_logistic` /
  `TwoPartFit.to_json()`; write atomically as now (`.partial` then `os.replace`). Keep `--hazard`
  with the same merge rule over the extended `files`.

- [ ] **Step 4: Run** `<T> tests.test_hazard_models tests.test_hazard_tests` — Expected: PASS.

---

### Task 11: Serving from saved fits

**Files:**
- Modify: `backend/apps/history/hazard_forecast.py`
- Test: `backend/tests/test_hazard_forecast.py`, `backend/tests/test_forecast_combined.py` (fixtures move to `toy_report_v2`)

**Interfaces:**
- Consumes: Task 3 (`read_storm_days`, `live_storm_days`, `refresh_recent`), Task 6 (`when_row`,
  `TwoPartFit`, `NO_EXPOSURE`), Task 7 (`score_logistic`, `score_two_part`), Task 10 (report v2,
  `REPORT_OLD`).
- Produces:
  - `Deployed` fields: `hazard, name, version, fit (dict), daily, reasons, complete_years, rain,
    terrain, storms` (`model` is gone; `name` is `'two_part'` or `'logistic_regression'`; `version` is
    `f'{name}@{report_sha1[:12]}'`).
  - `_inputs` key over: hazard, report sha1, rain sha1, terrain sha1, storms sha1 (records and
    exclusions no longer enter the key). Version ≠ 2 → `Unavailable(REPORT_OLD)`.
  - `_warm()` first calls `storms.refresh_recent()`.
  - Row field `model` carries `Deployed.name`.

- [ ] **Step 1: Write the failing tests:**

```python
def test_build_scores_without_fitting(self):            # patch LogisticRegression.fit to raise; deployed() still works
def test_two_part_daily_chance_is_q_times_share(self):
def test_old_report_makes_rows_unavailable_with_report_old(self):
def test_barangay_without_exposure_is_unavailable_not_zero(self):
    row = flood_row(result, barangay_without_share)
    self.assertEqual((row['method'], row['reason']), ('unavailable', NO_EXPOSURE))
def test_recent_days_without_storm_coverage_get_no_flood_chance(self):
    # storms cover to 2026-11-05, rain file to 2026-11-04, live rain to 2026-11-10: recorded days stop at 11-05;
    # month rows still have method 'model'; no exception
def test_landslide_ignores_storm_coverage(self):
def test_scenario_years_start_in_2007_with_rain_from_2006(self):
def test_cache_key_changes_with_the_storm_file(self):
def test_warm_refreshes_storms_first(self):
```

- [ ] **Step 2: Run** `<T> tests.test_hazard_forecast tests.test_forecast_combined` — Expected: FAIL.

- [ ] **Step 3: Implement.** `_build`: read report, rain, terrain, storms (`live_storm_days(read_storm_days(), today)`);
  two_part: one `when_row` per rain-file day, `score_two_part`; logistic_regression: `build_dataset`
  rows, `score_logistic`. Barangays without a share get `NO_EXPOSURE` (flood) or `NO_TERRAIN`
  (landslide) in `reasons`. `_recorded_chances` scores late days the same way, from file + live rain
  and the live storm days. Delete `_models()`.

- [ ] **Step 4: Run** `<T> tests.test_hazard_forecast tests.test_forecast_combined tests.test_hazard_scenarios` — Expected: PASS.

---

### Task 12: The fire contender

**Files:**
- Create: `backend/apps/history/fire_candidate.py`
- Modify: `backend/apps/history/model_forecast.py` (`neighbours()`, `evaluate(..., table_fn=rates_table)`,
  `_fitted` chooses by the rule, key `forecast-model-v3` + exposure sha1, `version` in its result,
  `accuracy_reports` adds `candidate`)
- Test: `backend/tests/test_fire_candidate.py`, `backend/tests/test_model_forecast.py`

**Interfaces:**
- Consumes: Task 4 (`read_exposure`), `model_forecast.rates_table`, `_index`, `_span`, `_known`.
- Produces:
  - `F1_NAME = 'pooled_exposure'`, `F0_NAME = 'current'`, `PENALTIES`, `INNER_MONTHS = 6`,
    `DISPERSION_FLAG = 1.5`, `MORAN_PERMUTATIONS = 999`, `MORAN_FLAG_P = 0.05`
  - `read_buildings(path=EXPOSURE_FILE) -> dict[int, int]`
  - `exposure_rates_table(events, places, buildings, *, until=None, today) -> dict | None` (same
    contract as `rates_table`)
  - `choose_penalty(events, places, buildings, until, today) -> float`
  - `one_month_ahead(table_fn, events, places, months: range, today) -> np.ndarray`
  - `dm_hln(d: np.ndarray, h: int = 1) -> dict` (`statistic`, `p`)
  - `coverage80(y, rates) -> float`; `pit_histogram(y, rates, bins=10, seed=0) -> list[int]`;
    `dispersion(y, rates, n_params) -> float`
  - `morans_i(values: dict[int, float], neighbours: dict[int, set[int]], permutations=999, seed=0) -> dict` (`i`, `p`)
  - `compare(events, places, buildings, neighbours, today) -> dict` — `{in_use, verdict: {adopted, reasons},
    window, models: {current, pooled_exposure}, difference: {mean, low, high, dm}, secondary,
    dispersion, dispersion_flag, morans_i}`.
  - `model_forecast.neighbours() -> dict[int, set[int]]` (PostGIS: boundaries within 1 m in SRID 32651).
  - `model_forecast.warm_fire(today: date) -> None` — runs `_fitted` for fire on the real records so the
    cache is filled; `hazard_forecast._warm` calls it after the flood and landslide models (spec 4.6).

- [ ] **Step 1: Write the failing tests:**

```python
def test_offset_trick_matches_a_true_offset(self):
    # intercept only (one all-zero column, penalty 1e-12): rate per building == total fires / total building-months
def test_scaling_buildings_scales_rates_exactly(self):
def test_penalty_is_chosen_without_the_test_months(self):     # patch to record months seen; none ≥ until
def test_dm_hln_on_a_known_series(self):
def test_coverage_and_pit_on_known_counts(self):
def test_morans_i_finds_a_clustered_pattern(self):            # 4 barangays in a line, values [3,3,-3,-3] → i>0, p<0.05
def test_rule_keeps_current_unless_the_interval_is_below_zero(self):
def test_untestable_without_buildings_keeps_current_with_a_reason(self):
def test_fitted_uses_the_winner_and_reports_the_candidate(self):     # tests.test_model_forecast, real fire setup
def test_cache_key_changes_with_the_exposure_file(self):
def test_warm_fills_the_fire_cache_too(self):               # after hazard_forecast._warm(), _fitted for fire is a cache hit
```

- [ ] **Step 2: Run** `<T> tests.test_fire_candidate tests.test_model_forecast` — Expected: FAIL.

- [ ] **Step 3: Implement** (spec 4.2–4.6). `PoissonRegressor(alpha=penalty, max_iter=2000)` on
  `y / buildings` with `sample_weight=buildings`; X = one dummy per barangay + sin/cos of 2πm/12 and
  4πm/12. Month-block bootstrap over the window's months, 1,000 replicates, seed 0. HLN: DM ×
  √((T + 1 − 2h + h(h − 1)/T)/T), Student t with T − 1 degrees of freedom.

- [ ] **Step 4: Run** `<T> tests.test_fire_candidate tests.test_model_forecast tests.test_forecast_combined` — Expected: PASS.

---

### Task 13: The prediction log

**Files:**
- Modify: `backend/apps/history/models.py` (add `HazardPredictionLog`)
- Create: `backend/apps/history/migrations/0008_hazard_prediction_log.py` (makemigrations, then add the trigger `RunSQL`)
- Create: `backend/apps/history/prediction_log.py`
- Create: `backend/apps/history/management/commands/log_hazard_predictions.py`
- Modify: `backend/apps/history/views.py` (extract `forecast_result(...)` from `ForecastView.get`)
- Modify: `backend/apps/history/hazard_forecast.py` (`_warm` ends with `prediction_log.log_once_today`)
- Modify: `backend/apps/history/management/commands/test_hazard_models.py` (fills `logged`)
- Test: `backend/tests/test_prediction_log.py`

**Interfaces:**
- Consumes: Task 11 (`deployed(h).version`, `_recorded_chances`), Task 12 (`_fitted(...)['version']`).
- Produces:
  - Model fields exactly as spec 3.4, `db_table = 'hazard_prediction_log'`, `UniqueConstraint(fields=
    ['hazard', 'barangay', 'kind', 'period_start', 'issued_on', 'model_version'], name='hazard_prediction_log_unique')`,
    check constraints on `hazard`, `kind`, `level` and 0 ≤ `probability` ≤ 1, `Index(fields=['hazard', 'period_start'])`,
    `barangay = ForeignKey(Barangay, on_delete=PROTECT)`.
  - Trigger SQL:

```sql
CREATE FUNCTION hazard_prediction_log_frozen() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'hazard_prediction_log rows are never changed'; END $$;
CREATE TRIGGER hazard_prediction_log_frozen BEFORE UPDATE OR DELETE ON hazard_prediction_log
FOR EACH ROW EXECUTE FUNCTION hazard_prediction_log_frozen();
```
    Reverse: `DROP TRIGGER hazard_prediction_log_frozen ON hazard_prediction_log; DROP FUNCTION hazard_prediction_log_frozen();`
  - `views.forecast_result(*, month, day, year, included, barangay, years, exclude_samples, now) -> dict`
    (the view calls it; behaviour unchanged).
  - `prediction_log.BACKFILL_DAYS = 30`, `write_day_rows(today) -> int`, `write_month_rows(today) -> int`,
    `log_once_today(today) -> bool` (cache marker `f'hazard-log-done:{today.isoformat()}'`; catches
    `DatabaseError`, logs one warning, returns False), `logged_summary(hazard: str, records) -> dict | None`.

- [ ] **Step 1: Write the failing tests** (`TestCase` for writes; `TransactionTestCase` for the trigger):

```python
def test_update_and_delete_are_refused(self):
    row = make_row()
    with self.assertRaises(DatabaseError):
        with transaction.atomic():
            HazardPredictionLog.objects.filter(pk=row.pk).update(probability=0.5)
    with self.assertRaises(DatabaseError):
        with transaction.atomic():
            HazardPredictionLog.objects.filter(pk=row.pk).delete()
def test_rerun_adds_no_rows(self):
def test_day_rows_never_reach_back_more_than_30_days(self):
def test_day_rows_carry_rain_storm_and_outside_training(self):
def test_month_rows_match_what_the_forecast_shows(self):     # same probability and level as forecast_result
def test_unavailable_rows_are_not_logged(self):
def test_missing_table_logs_a_warning_and_returns_false(self):
    # patch write_day_rows to raise ProgrammingError → log_once_today returns False; the forecast endpoint still 200
def test_logged_summary_scores_new_events(self):
def test_migration_is_reversible(self):                     # tests.test_history_migrations style: migrate to 0007 and back
def test_forecast_view_unchanged_after_extraction(self):    # existing tests.test_forecast_combined pass
```

- [ ] **Step 2: Run** `<T> tests.test_prediction_log` — Expected: FAIL.

- [ ] **Step 3: Implement** (spec 3.4–3.5); `makemigrations history` on the private settings, then append
  the `RunSQL`. `write_*` use `bulk_create(ignore_conflicts=True)`; `model_version` from
  `Deployed.version` and fire's `_fitted()['version']`.

- [ ] **Step 4: Run** `<T> tests.test_prediction_log tests.test_history_migrations tests.test_forecast_combined tests.test_hazard_forecast` — Expected: PASS.

---

### Task 14: The accuracy card and the copy

**Files:**
- Modify: `backend/apps/history/views.py` (`BASIS_METHOD`)
- Modify: `frontend/src/components/Forecast/ForecastAccuracy.jsx`
- Modify: `frontend/src/components/Forecast/forecastLevels.js` (`MODEL_LABELS`)
- Test: `frontend/src/components/Forecast/forecastAccuracy.test.js`, `backend/tests/test_forecast_combined.py`

**Interfaces:**
- Consumes: Task 10 entry shape, Task 12 `candidate` block.
- Produces:
  - `BASIS_METHOD = ("From each hazard's trained model: a Poisson regression on past fires for fire, and a rain "
    "model for flood and landslide (with storm tracks, terrain and flood-hazard exposure). Every chance is of a "
    "reported event. Counting past years is only a benchmark in the accuracy check.")`
  - `MODEL_LABELS = { logistic_regression: 'pooled logistic regression', two_part: 'two-part model (rain-day chance × barangay share)', pooled_exposure: 'pooled Poisson with building exposure', current: 'Poisson regression' }`
  - Opening line: adopted → `` `${hazard}: ${label}, in use — adopted under rule (${rule}).` ``; not adopted →
    `` `${hazard}: ${label}, in use. The two-part model was tested and not adopted: ${reasons.join(' ')}` ``.
  - Tables: "Event by event" (Date | Storm | 1-day rain | PAGASA band | then per model: Hit barangays' chance, day before, City chance, At High that month);
    "Against the baselines" (Model | Log score | Brier skill vs overall rate | Brier skill vs barangay rate | PR-AUC (no skill));
    lines for "when", "where" and lift; break-even sentence ``At these cut-offs a warning pays off only if acting on about ${n} false alarms per real event is acceptable.``;
    landslide outside test; "Since logging began" when `logged` is not null; limits; credits list.

- [ ] **Step 1: Write the failing frontend tests** (`<F> forecastAccuracy`): renders the adopted line,
  the not-adopted line with its reason, the event table with five flood days, the credits, no
  "Since logging began" when `logged` is null, the unavailable card with `REPORT_OLD`, and the fire
  card's "tested, not better" line with 80% coverage. Backend: `BASIS_METHOD` text in the forecast payload.

- [ ] **Step 2: Run** `<F> forecastAccuracy` — Expected: FAIL.

- [ ] **Step 3: Implement** the card from the entry fields (remove reads of `winner`, `candidates`,
  `calibration`, `monthly_levels`, `lobo_auc`).

- [ ] **Step 4: Run** `<F> forecastAccuracy` then `<F> Forecast` and `<T> tests.test_forecast_combined` — Expected: PASS.

---

### Task 15: Docs, real data runs and verification

**Files:**
- Modify: `README.md` (the flood and landslide section, spec 3.3)
- Modify: `backend/apps/history/data/` (generated files)

- [ ] **Step 1: README.** Order `fetch_rain`, `fetch_storms`, `build_hazard_features`, `test_hazard_models`;
  what each downloads (no account or key); the daily line beside the alert-jobs one:
  `schtasks /Create /TN "GeoAlert prediction log" /SC DAILY /ST 06:00 /TR "...python.exe ...manage.py log_hazard_predictions"`
  and `0 6 * * *  cd /path/to/backend && venv/bin/python manage.py log_hazard_predictions`.

- [ ] **Step 2: Run the data commands** (dev settings, reads the shared database only):
  `fetch_rain`, `fetch_storms`, `build_hazard_features`, `test_hazard_models`. Expected: rain from
  2006-12-18; storm days include 2025-11-04 (Kalmaegi/Tino); every barangay has an exposure row;
  the report has `version: 2`.

- [ ] **Step 3: Check the catalogue filter on real data:** no kept record dated 2012-09-05 names
  "Camp 5"; if one does, add its `event_id` to `landslide_catalogue_exclusions.csv` with the reason
  "Talisay, Negros Occidental" and rerun `test_hazard_models`.

- [ ] **Step 4: Full suites:** `<T> tests` and `<F>` (all). Expected: all pass; record the counts.

- [ ] **Step 5: Show the user** each hazard's `in_use`, `verdict`, the event table, the baselines, the
  landslide outside test, and fire's `candidate` block — before anything else.

---

### Task 16 (gated): Apply the migration to the shared database

Only after the user says go.

- [ ] **Step 1: Back up** (dev settings): `manage.py dumpdata history barangays --indent 1 > "C:/Users/Sannichigetsu/Downloads/geoalert-before-0008-2026-11-13.json"`; confirm the file is non-empty.
- [ ] **Step 2: Migrate:** `manage.py migrate history 0008`; Expected: "Applying history.0008_hazard_prediction_log... OK".
- [ ] **Step 3: First log run:** `manage.py log_hazard_predictions`; Expected: day and month row counts printed; a second run prints 0 new rows.
