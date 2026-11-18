# Rain Watch Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a free, automatic "Next 3 days" Rain watch for flood and landslide. It colours each
barangay Yellow, Orange or Red from the GFS rain forecast, wet ground and terrain, and is never calmer
than PAGASA's alerts or a DRRMO override.

**Architecture:**
- **Forecast job:** a GitHub Actions job (`tools/rain_forecast/`) fetches GFS rain for 4 grid points
  every 6 h and POSTs it to a new Django app, `apps/rainwatch`.
- **PAGASA check:** Render reads PAGASA's CAP feed at most hourly, started by the existing
  `/api/hazards/` ping.
- **Colours:** `GET /api/rain-watch/` works them out on request with plain Python and NumPy:
  joined-up forecast hours, Balanced cut-offs, barangay limits, PAGASA and DRRMO floors, and who is
  asking.
- **Frontend:** a third map view, a banner, and a DRRMO dashboard card.

**Tech Stack:**
- Django 4.2, DRF, PostGIS (GEOS for polygon tests), `ArrayField` (`django.contrib.postgres.fields`),
  `requests`.
- React 18 (react-scripts, Jest), react-leaflet.
- The job only: Python 3.12, `eccodes`, `numpy`, `requests`, and `dynamical-catalog`, `icechunk` and
  `zarr` for the fallback.

**Spec:** `docs/design/specs/2026-11-18-rain-watch-design.md` (approved 2026-11-18). Read it beside
this plan; section numbers (6.3, 7.1…) refer to it.

## Global Constraints

**Process rules**
- **Never commit or push.** No task has a commit step. Leave every file uncommitted. The user puts the
  workflow on `main` themselves (Task 12).
- **One migration:** `backend/apps/rainwatch/migrations/0001_initial.py` (schema plus the Balanced
  rules row). It is applied to the shared database **only in Task 12**, after a backup and the user's
  go-ahead.
- **No Open-Meteo, no paid service.**
- **Render stays light:**
  - `apps/rainwatch` never imports `eccodes`, `xarray`, `zarr`, `icechunk`, `dynamical_catalog` or
    `pandas`.
  - Those packages appear only in `tools/rain_forecast/requirements.txt`.
  - No new line in `backend/requirements/`.
- **No network in tests.** Every outside call takes an injectable `get=` (or `post=`/`exists=`), and
  tests pass fakes.
- **Backend test command `<T>`** (Git Bash, from `backend/`), with the private test database. Never
  the shared `test_postgres`.

  ```
  PYTHONPATH="C:/Users/Sannichigetsu/.geoalert-test" DJANGO_SETTINGS_MODULE=geo_test_settings venv/Scripts/python.exe manage.py test <labels> --noinput > "C:/Users/Sannichigetsu/.geoalert-test/last.log" 2>&1; tail -n 15 "C:/Users/Sannichigetsu/.geoalert-test/last.log"
  ```
- **Frontend test command `<F>`** (from `frontend/`): `CI=true npx react-scripts test --watchAll=false <pattern>`.
- **Tool test command `<J>`** (from `backend/`):
  `venv/Scripts/python.exe -m unittest discover -s ../tools/rain_forecast -p "test_*.py" -v`.
- **Times:** store UTC. "Today", "Tomorrow" and "Day after" are `Asia/Manila` calendar days
  (`apps.history.hazard_data.MANILA`).

**Fixed values (spec 6.1–6.8)**
- **Grid points** (lat, lon): `(10.25, 123.75), (10.25, 124.0), (10.5, 123.75), (10.5, 124.0)`.
- **Places:** `CITY = (10.2835, 123.8212)`, `UPLAND = (10.325, 123.795)`.
- **Bilinear weights:** `wy = (lat − 10.25) / 0.25`, `wx = (lon − 123.75) / 0.25`, and
  v = (1−wy)·((1−wx)·v(10.25,123.75) + wx·v(10.25,124.0)) + wy·((1−wx)·v(10.5,123.75) + wx·v(10.5,124.0)).
- **Balanced rules (the seed row):**

  | Field | Value |
  |---|---|
  | `flood_dry` | `[30, 60, 120]` |
  | `flood_wet` | `[20, 40, 80]` |
  | `slide_dry` | `[50, 80, 120]` |
  | `slide_wet` | `[25, 40, 60]` |
  | `wet_14day_mm` | `156.5` |
  | `flood_exposure_min` | `190` |
  | `steep_share_min` | `0.40` |
  | `stale_hours` | `12` |
  | `note` | `'Balanced (backtest 2026-11-18)'` |

  A level is reached when the rain is `≥` its cut-off.
- **Flood rain:** the day's total at the worse of CITY and UPLAND. **Landslide rain:** the day plus
  the 2 days before, at UPLAND.
- **Barangay limits** (from `apps/history/data/`):
  - Flood full level: `exposure ≥ 190` gives ids `{1, 2, 5, 6, 8, 10, 11, 12, 16, 17, 18, 19, 20, 21}`.
    Every other barangay is one step lower.
  - Landslide: `slope_gt18 ≥ 0.40` gives ids `{4, 7, 8, 13, 14, 22, 23}`. Every other barangay has no
    landslide colour.
- **PAGASA:**
  - feed `https://publicalert.pagasa.dost.gov.ph/feeds/`
  - Talisay point `(10.2835, 123.8212)`, Cebu PSGC `072200000`
  - checked at most every 3,600 s; 20 s timeouts; User-Agent `GeoAlert-Talisay/1.0 (PAGASA alerts)`
- **Job:**
  - cron `'17 4,10,16,22 * * *'`
  - newest run: hours 1–96
  - gap-fill: hours 1–6 for up to 12 missing runs from the last 72 h
  - NOMADS paced at 1 request/s; POST retried 3 times
  - sources `'gfs-nomads'`, `'gfs-dynamical'`
- **Ingest checks:**
  - exactly the 4 grid points
  - 1–120 finite values ≥ 0 each, all the same length
  - `init_time` on a 00/06/12/18 UTC hour, not later than now + 1 h and not older than 10 days
- **Stale:** the newest run with `hours ≥ 72` arrived more than `stale_hours` ago, or there is none.
- **Overrides:** `ends_at` later than now and at most now + 72 h; a non-blank `note` of at most 300
  characters.
- **Cache:** results are cached 300 s per audience and cleared on any new run, alert or override.
- **Who sees Yellow:** `DRRMO_Officer` and `System_Admin` get every level. Everyone else gets `"none"`
  in place of `"Green"` and `"Yellow"`, and no reasons on those.

**Exact copy**
- **Map note:** `'Automatic estimate from weather forecasts (NOAA GFS) and PAGASA alerts. Not an official warning. Follow DRRMO and PAGASA.'`
- **Credits:** `'Forecast: NOAA GFS (dynamical.org when NOAA is late). Alerts: PAGASA, CC BY 4.0. Rain so far: NASA POWER.'`
- **Monthly note:** `'Floods and landslides are rare in any one month, so this view stays mostly green, even in the rainy season. For rain that is coming, see Next 3 days.'`
- **Reasons:**

  | When | Text |
  |---|---|
  | Flood forecast | `'Forecast {mm:.0f} mm'` |
  | Landslide forecast | `'{mm:.0f} mm over 3 days'` |
  | Wet ground (suffix) | `'; ground already wet'` |
  | Partial data (suffix) | `' (partial)'` |
  | Barangay limited | `'Fewer homes in flood-prone ground: one step lower'` |
  | PAGASA floor | `'Raised to {Level}: PAGASA {event}'` |
  | DRRMO floor | `'Raised by DRRMO: {note}'` |
  | Stale | `'Forecast out of date'` |
  | Wetness unknown (staff only) | `'Ground wetness unknown'` |

## Review Focus

These conditions are implied by the spec but no other test exercises them. Each has a test in the
task named.

1. **No runs stored yet** (the first deploy, before the job has run): every level is `"unknown"`,
   `stale: true`, no crash, and the map shows "No forecast yet". Tested in Tasks 7 and 9.
2. **A malformed PAGASA feed or CAP file** (an HTML error page, a missing `<expires>`, broken XML):
   the entry is skipped and logged, other entries are still stored, and `/api/hazards/` still
   answers 200. Tested in Task 5.
3. **A barangay in the database but missing from the terrain or exposure CSV:** treated as not flood
   exposed and not steep, with no KeyError. Tested in Task 7.
4. **The ingest token is unset on the server** (empty setting): every POST gets a 403, even one whose
   header is `Bearer ` with an empty token. Tested in Task 4.
5. **The newest run is too short to reach the Day after** (only gap-fill runs arrived): that day's
   forecast part is `"unknown"` with `' (partial)'` in staff reasons, and earlier days are unaffected.
   Tested in Task 7.

---

## File structure

**Backend: new app `backend/apps/rainwatch/`**

| File | What it does |
|---|---|
| `__init__.py`, `apps.py` | `RainwatchConfig(name='apps.rainwatch', label='rainwatch')` |
| `models.py` | The five tables (spec 6.2) and `RainWatchRules.current()` |
| `migrations/0001_initial.py` | Schema plus the Balanced row |
| `admin.py` | Rules: add-only, prefilled from the newest row. Other tables: view-only |
| `rules.py` | Pure level arithmetic and barangay limits (spec 6.3–6.4) |
| `series.py` | Pure joining of runs, bilinear weights, Manila day totals (spec 6.3) |
| `pagasa.py` | Feed and CAP parsing, coverage, active check, floor mapping, `check_feed`, background start (spec 6.5) |
| `assess.py` | Loads everything, builds the response, public filter, cache (spec 6.7–6.8) |
| `auth.py` | `IngestTokenPermission` |
| `serializers.py` | Ingest payload and override validation |
| `views.py`, `urls.py` | The endpoints in spec 6.7 |

**Backend: changes and tests**
- **Modify:**
  - `backend/config/settings/base.py`: `LOCAL_APPS`, plus `RAIN_WATCH_INGEST_TOKEN` and
    `PAGASA_FEED_WRITER`.
  - `backend/config/urls.py`: add `api/rain-watch/`.
  - `backend/apps/hazards/views.py`: the hourly PAGASA start.
  - `deploy/render.env.example`, `deploy/FREE_HOSTING.md`, `README.md`.
- **Tests:**
  - `backend/tests/test_rainwatch_models.py`, `test_rainwatch_rules.py`, `test_rainwatch_series.py`,
    `test_rainwatch_ingest.py`, `test_rainwatch_pagasa.py`, `test_rainwatch_overrides.py`,
    `test_rainwatch_assess.py`
  - fixtures in `backend/tests/fixtures/pagasa/`

**Tool**
- `tools/rain_forecast/gfs.py`: NOMADS and dynamical.org reading, and per-hour conversion.
- `tools/rain_forecast/fetch.py`: run planning, payload, posting, and the CLI.
- `tools/rain_forecast/requirements.txt`, `tools/rain_forecast/test_rain_forecast.py`.
- `.github/workflows/rain-forecast.yml`.
- Modify `.github/workflows/ci.yml`: one step running `<J>`.

**Frontend**
- `frontend/src/api/rainWatchApi.js`
- `frontend/src/components/RainWatch/`:
  - `rainWatchLevels.js` (pure helpers) and its `.test.js`
  - `RainWatchDayPicker.jsx`, `RainWatchBanner.jsx`, `RainWatchLegend.jsx`
  - `RainWatchCard.jsx` and `RainWatchOverrideForm.jsx`, with tests
  - `rainWatch.css`
- **Modify:**
  - `frontend/src/pages/PublicMap.jsx`
  - `frontend/src/pages/Dashboard/DRRMODashboard.jsx`
  - `frontend/src/components/Forecast/forecastLevels.js` (adds `FLOOD_LANDSLIDE_MONTHLY_NOTE`)

---

### Task 1: App, models, migration, settings and admin

**Files:**
- Create: `backend/apps/rainwatch/{__init__,apps,models,admin}.py`, `backend/apps/rainwatch/migrations/{__init__,0001_initial}.py`
- Modify: `backend/config/settings/base.py` (add `'apps.rainwatch'` to `LOCAL_APPS`; add `RAIN_WATCH_INGEST_TOKEN = env('RAIN_WATCH_INGEST_TOKEN', default='')` and `PAGASA_FEED_WRITER = env.bool('PAGASA_FEED_WRITER', default=False)` beside `HAZARD_LOG_WRITER`, each with a two-line comment)
- Test: `backend/tests/test_rainwatch_models.py`

**Interfaces:**
- **Produces** these models (table names as in spec 6.2):
  - **`RainForecastRun`:**
    - `source` (`CharField(20)`, choices `gfs-nomads` / `gfs-dynamical`), `init_time`, `received_at`
      (`auto_now_add`), `job_version` (`CharField(40, blank=True)`), `hours` (`PositiveSmallIntegerField`)
    - `UniqueConstraint(fields=['source', 'init_time'], name='rain_forecast_run_unique')`
  - **`RainForecastSeries`:**
    - `run` (FK, PROTECT, `related_name='series'`), `lat` (`DecimalField(5, 2)`), `lon`
      (`DecimalField(6, 2)`), `first_hour_start`, `mm_per_hour` (`ArrayField(FloatField())`)
    - unique on (run, lat, lon)
  - **`PagasaAlert`:** the fields in spec 6.2. `identifier` is unique; `effective` and `expires` are
    nullable; `fetched_at` is `auto_now_add`.
  - **`RainWatchOverride`:**
    - `hazard` (choices Flood / Landslide / Both), `level` (choices Yellow / Orange / Red),
      `starts_at` (default `timezone.now`), `ends_at`, `note` (`CharField(300)`)
    - `created_by` (FK User, PROTECT), `created_at`
    - `cancelled_at` and `cancelled_by` (both nullable)
  - **`RainWatchRules`:**
    - `flood_dry`, `flood_wet`, `slide_dry`, `slide_wet` (each `ArrayField(FloatField(), size=3)`)
    - `wet_14day_mm`, `flood_exposure_min`, `steep_share_min` (floats), `stale_hours` (small int)
    - `note`, `created_by` (nullable), `created_at`
    - `@classmethod current() -> RainWatchRules` (newest by `created_at`, then `id`). Task 2 adds
      `as_rules()`.
- **Insert-only:** `RainForecastRun`, `RainForecastSeries` and `RainWatchRules` raise `ValueError` in
  `save()` when `self.pk` is already set.

- [ ] **Step 1: Write the failing tests** in `backend/tests/test_rainwatch_models.py`:

```python
class RainWatchModelsTest(TestCase):
    def test_migration_seeds_balanced_rules(self):
        r = RainWatchRules.current()
        self.assertEqual(list(r.flood_dry), [30, 60, 120]); self.assertEqual(list(r.flood_wet), [20, 40, 80])
        self.assertEqual(list(r.slide_dry), [50, 80, 120]); self.assertEqual(list(r.slide_wet), [25, 40, 60])
        self.assertEqual((r.wet_14day_mm, r.flood_exposure_min, r.steep_share_min, r.stale_hours), (156.5, 190, 0.40, 12))

    def test_newest_rules_row_wins(self):  # add a row with flood_dry [40, 80, 160]; current() returns it

    def test_run_unique_per_source_and_init(self):  # second create with same source+init_time -> IntegrityError

    def test_runs_series_and_rules_are_insert_only(self):  # obj.save() after creation -> ValueError
```

- [ ] **Step 2: Run** `<T> tests.test_rainwatch_models`. Expected: an ImportError (no app yet).
- [ ] **Step 3: Implement** the app, the models, the migration (`makemigrations rainwatch`, then
  append a `RunPython` that inserts the Balanced row, with a no-op reverse) and the settings lines.
- [ ] **Step 4: Implement the admin** in `admin.py`:
  - `RainWatchRulesAdmin`: `has_change_permission` and `has_delete_permission` return False.
    `get_changeform_initial_data` returns the newest row's values. `save_model` sets `created_by`.
  - Register `RainForecastRun`, `PagasaAlert` and `RainWatchOverride` view-only (add, change and
    delete all False).
- [ ] **Step 5: Run** `<T> tests.test_rainwatch_models`. Expected: 4 tests OK.

### Task 2: Colour rules (pure)

**Files:**
- Create: `backend/apps/rainwatch/rules.py`
- Modify: `backend/apps/rainwatch/models.py` (add `RainWatchRules.as_rules()`)
- Test: `backend/tests/test_rainwatch_rules.py`

**Interfaces:**
- **Produces:**
  - `GREEN, YELLOW, ORANGE, RED = 0, 1, 2, 3` and `LEVEL_NAMES = ('Green', 'Yellow', 'Orange', 'Red')`
  - `@dataclass(frozen=True) class Rules`, with fields `flood_dry`, `flood_wet`, `slide_dry`,
    `slide_wet` (each `tuple[float, float, float]`), `wet_14day_mm: float`,
    `flood_exposure_min: float`, `steep_share_min: float`, `stale_hours: int`
  - `BALANCED: Rules`, set to the Fixed values
  - `band(mm: float, cutoffs: tuple[float, float, float]) -> int`
  - `flood_level(mm_day: float, wet: bool, rules: Rules) -> int`
  - `slide_level(mm_3day: float, wet: bool, rules: Rules) -> int`
  - `one_step_lower(level: int) -> int`
  - `flood_exposed_ids(exposure: dict[int, dict[str, float]], rules: Rules) -> set[int]`, reading key
    `'exposure'`
  - `steep_ids(terrain: dict[int, dict[str, float]], rules: Rules) -> set[int]`, reading key
    `'slope_gt18'`
  - `combine(forecast: int | None, floors: Iterable[int]) -> int | None`: the highest of the forecast
    and the floors. `None` only when the forecast is `None` and there are no floors.

- [ ] **Step 1: Write the failing tests** (values from the backtest, spec 10):

```python
def test_tino_day_is_red(self):            self.assertEqual(flood_level(192.5, False, BALANCED), RED)
def test_limited_barangay_one_step_lower(self): self.assertEqual(one_step_lower(flood_level(192.5, False, BALANCED)), ORANGE)
def test_wet_ground_lowers_flood_cutoffs(self):
    self.assertEqual(flood_level(23, True, BALANCED), YELLOW); self.assertEqual(flood_level(23, False, BALANCED), GREEN)
def test_cutoff_is_inclusive(self):        self.assertEqual(flood_level(30, False, BALANCED), YELLOW)
def test_landslide_pileups(self):
    self.assertEqual(slide_level(55.5, False, BALANCED), YELLOW); self.assertEqual(slide_level(48.7, True, BALANCED), ORANGE)
    self.assertEqual(slide_level(226.4, False, BALANCED), RED); self.assertEqual(slide_level(31.1, False, BALANCED), GREEN)
def test_one_step_lower_floors_at_green(self): self.assertEqual(one_step_lower(GREEN), GREEN)
def test_limits_from_repo_files(self):
    self.assertEqual(flood_exposed_ids(read_exposure(), BALANCED), {1, 2, 5, 6, 8, 10, 11, 12, 16, 17, 18, 19, 20, 21})
    self.assertEqual(steep_ids(read_terrain(), BALANCED), {4, 7, 8, 13, 14, 22, 23})
def test_combine(self):
    self.assertEqual(combine(YELLOW, [ORANGE]), ORANGE); self.assertEqual(combine(RED, [YELLOW]), RED)
    self.assertIsNone(combine(None, [])); self.assertEqual(combine(None, [YELLOW]), YELLOW)
def test_model_row_converts(self): self.assertEqual(RainWatchRules.current().as_rules(), BALANCED)
```

  `read_exposure` comes from `apps.history.exposure` and `read_terrain` from
  `apps.history.hazard_data`. The last test needs the database (`TestCase`); the rest can be a
  `SimpleTestCase`.
- [ ] **Step 2: Run** `<T> tests.test_rainwatch_rules`. Expected: ImportError.
- [ ] **Step 3: Implement** `rules.py` and `as_rules()`.
- [ ] **Step 4: Run** `<T> tests.test_rainwatch_rules`. Expected: OK.

### Task 3: Joining runs and Manila day totals (pure)

**Files:**
- Create: `backend/apps/rainwatch/series.py`
- Test: `backend/tests/test_rainwatch_series.py`

**Interfaces:**
- **Produces:**
  - `GRID: tuple[tuple[float, float], ...]`, `CITY`, `UPLAND` (Fixed values)
  - `SOURCE_PREFERENCE = {'gfs-nomads': 1, 'gfs-dynamical': 0}`
  - `@dataclass(frozen=True) class RunData`: `source: str`, `init_time: datetime` (aware, UTC),
    `series: dict[tuple[float, float], list[float]]`. Hour k (1-based) covers
    `init_time + (k−1) h` to `init_time + k h`.
  - `stitched(runs: Iterable[RunData]) -> dict[datetime, dict[tuple[float, float], float]]`: for each
    hour start (UTC), the grid values from the newest run covering it; on a tie, the higher
    `SOURCE_PREFERENCE`.
  - `at_point(grid_values: dict[tuple[float, float], float], point: tuple[float, float]) -> float`:
    the bilinear formula in Fixed values.
  - `place_hours(hours: dict[datetime, dict], point) -> dict[datetime, float]`: only hours that have
    all 4 grid points.
  - `manila_day_total(hours: dict[datetime, float], day: date) -> tuple[float, bool]`: the sum over
    the 24 hours from `day 00:00 Asia/Manila`, and whether all 24 are present.

- [ ] **Step 1: Write the failing tests:**

```python
INIT = datetime(2026, 11, 17, 18, tzinfo=timezone.utc)           # 02:00 PHT on 18 Nov
def flat(mm, n): return {p: [mm] * n for p in GRID}

def test_bilinear_corners_and_city(self):
    v = {(10.25, 123.75): 0, (10.25, 124.0): 100, (10.5, 123.75): 0, (10.5, 124.0): 100}
    self.assertAlmostEqual(at_point(v, CITY), 28.48, places=2)
    v2 = {(10.25, 123.75): 0, (10.25, 124.0): 0, (10.5, 123.75): 100, (10.5, 124.0): 100}
    self.assertAlmostEqual(at_point(v2, CITY), 13.4, places=2)
    self.assertEqual(at_point(v, (10.25, 124.0)), 100)

def test_day_missing_first_two_hours_is_partial(self):
    h = place_hours(stitched([RunData('gfs-nomads', INIT, flat(1.0, 96))]), CITY)
    self.assertEqual(manila_day_total(h, date(2026, 11, 18)), (22.0, False))
    self.assertEqual(manila_day_total(h, date(2026, 11, 19)), (24.0, True))

def test_older_run_fills_earlier_hours(self):
    older = RunData('gfs-nomads', INIT - timedelta(hours=6), flat(2.0, 6))
    h = place_hours(stitched([older, RunData('gfs-nomads', INIT, flat(1.0, 96))]), CITY)
    self.assertEqual(manila_day_total(h, date(2026, 11, 18)), (26.0, True))

def test_newest_run_wins_and_nomads_wins_ties(self):
    a = RunData('gfs-dynamical', INIT, flat(5.0, 6)); b = RunData('gfs-nomads', INIT, flat(1.0, 6))
    self.assertEqual(stitched([a, b])[INIT][(10.25, 123.75)], 1.0)
```

- [ ] **Step 2: Run** `<T> tests.test_rainwatch_series`. Expected: ImportError.
- [ ] **Step 3: Implement** `series.py` with NumPy-free plain Python. The data are tiny.
- [ ] **Step 4: Run** `<T> tests.test_rainwatch_series`. Expected: OK.

### Task 4: Ingest and status endpoints

**Files:**
- Create: `backend/apps/rainwatch/{auth,serializers,views,urls}.py`, and `assess.py` with only
  `bump()` for now (Task 7 fills the rest)
- Modify: `backend/config/urls.py`, adding `path('api/rain-watch/', include('apps.rainwatch.urls'))`
- Test: `backend/tests/test_rainwatch_ingest.py`

**Interfaces:**
- **Produces:**
  - `auth.IngestTokenPermission`: allows a request only when `settings.RAIN_WATCH_INGEST_TOKEN` is
    non-empty and `hmac.compare_digest` matches it against the token from `Authorization: Bearer <t>`.
  - The views set `authentication_classes = []`, so there is no session and no CSRF.
  - `serializers.ForecastRunSerializer` validates the body in spec 6.1 against the Fixed values.
  - `POST /api/rain-watch/forecast-runs/`:
    - creates the run and its 4 series atomically, with `hours = len(mm_per_hour)`
    - returns `201 {"created": true}`; a duplicate returns `200 {"created": false}`
    - calls `assess.bump()`
  - `GET /api/rain-watch/forecast-runs/status/`: `{"runs": [{"source", "init_time", "hours"}]}` for
    `init_time ≥ now − 3 days`, newest first.
  - `assess.bump() -> None`: increments the cache key `'rainwatch:version'`.

- [ ] **Step 1: Write the failing tests** with `override_settings(RAIN_WATCH_INGEST_TOKEN='s3cret')`:
  - `test_valid_post_creates_run_and_four_series`
  - `test_duplicate_post_is_a_noop`: the second call returns 200, still 1 run.
  - `test_missing_or_wrong_token_403`
  - `test_empty_server_token_rejects_everything` (Review Focus 4): with the setting `''`, a header of
    `'Bearer '` gets 403.
  - `test_rejects_bad_bodies`: each gets 400:
    - 3 points
    - a point off the grid
    - a negative value
    - `float('nan')` sent as the string `'NaN'`
    - lists of unequal length
    - 121 values
    - init at 03:00 UTC
    - init 11 days old
    - init 2 h in the future
  - `test_status_lists_recent_runs_with_hours`
  - `test_post_bumps_cache_version`
- [ ] **Step 2: Run** `<T> tests.test_rainwatch_ingest`. Expected: failures (no URLs yet).
- [ ] **Step 3: Implement** the files above.
- [ ] **Step 4: Run** `<T> tests.test_rainwatch_ingest`. Expected: OK.

### Task 5: PAGASA feed reader and the hourly start

**Files:**
- Create: `backend/apps/rainwatch/pagasa.py`, `backend/tests/fixtures/pagasa/feed.xml`,
  `gfa_south_cotabato.cap`, `tc_alert_samuel.cap`. Copy them from
  `C:\Users\SANNIC~1\AppData\Local\Temp\claude\de7ff8623febfdf5\d2376158-421d-4107-a21c-5c7cc0673f28\scratchpad\pagasa\`
  (`feed.xml`, `one.cap`, `tc.cap`). If that folder is gone, save the live feed and any one
  General Flood Advisory and one Tropical Cyclone Alert with `curl` once. They are CC BY 4.0.
- Modify: `backend/apps/hazards/views.py` (after the warm-up block, around lines 124–141)
- Test: `backend/tests/test_rainwatch_pagasa.py`

**Interfaces:**
- **Produces:**
  - `FEED_URL`, `TALISAY = (10.2835, 123.8212)`, `CEBU_PSGC = '072200000'`,
    `CHECK_KEY = 'geoalert:pagasa-feed-check'`, `CHECK_EVERY = 3600`
  - `parse_feed(text: str) -> list[tuple[str, str]]`: (CAP identifier with `urn:uuid:` stripped, CAP
    URL) per entry.
  - `parse_cap(text: str, url: str) -> dict`: keys matching the `PagasaAlert` fields, plus
    `polygons: list[list[tuple[float, float]]]` (CAP order: lat,lon pairs) and
    `geocodes: list[str]`. Raises `ValueError` on broken XML or a missing `identifier`, `sent` or
    `expires`.
  - `covers_talisay(cap: dict) -> bool`: true if any of these hold:
    - a polygon contains `TALISAY` (GEOS `Polygon` built from `(lon, lat)`)
    - a geocode equals `CEBU_PSGC`
    - there are no polygons and `'cebu'` appears in `area_desc` (any case)
  - `floor_for`, `is_active` and `referenced_identifiers` take `PagasaAlert` instances (anything
    with those attribute names). `parse_cap` and `covers_talisay` work on the parsed dict before it is
    saved.
  - `floor_for(alert) -> dict[str, int]`: event names are matched in lower case. With severity rank
    Moderate = 1, Severe = 2, Extreme = 3 and anything else 0:
    - an event containing `'flood'` gives `{'Flood': max(YELLOW, sev)}`
    - an event containing `'tropical cyclone'` or `'rainfall'` gives `{'Flood': sev, 'Landslide': sev}`
      when sev > 0, otherwise `{}`
    - any other event gives `{}`
  - `is_active(alert, now, newer_references: set[str]) -> bool`: all of these hold:
    - `covers_talisay`
    - (`effective` or `sent`) ≤ now < `expires`
    - `msg_type != 'Cancel'`, `response_type != 'AllClear'`, `urgency != 'Past'`
    - `identifier not in newer_references`
  - `referenced_identifiers(alerts) -> set[str]`: the second comma-field of each space-separated
    entry in `references`.
  - `check_feed(get=None, now=None) -> int`: stores new alerts and returns how many. A bad entry is
    logged at WARNING and skipped. Calls `assess.bump()` when the count is above 0.
  - `check_in_background() -> bool`: starts a daemon thread named `'pagasa-feed-check'` unless one is
    alive. The thread runs `check_feed`, logs any exception and closes the DB connection.
- **The `/api/hazards/` hook:** when `settings.PAGASA_FEED_WRITER` is true and
  `cache.add(CHECK_KEY, 1, timeout=CHECK_EVERY)` succeeds (or the cache fails), call
  `pagasa.check_in_background()`. All of this sits inside `try/except Exception` with
  `logger.exception`.

- [ ] **Step 1: Write the failing tests:**
  - **`test_parse_feed_fixture`:** 15 entries; the first identifier is
    `'bd7f6925-22e0-459a-83ce-c499ac546cf7'`.
  - **`test_parse_gfa_fixture`:** event `'General Flood Advisory (Final)'`, severity `'Minor'`,
    response_type `'AllClear'`, `covers_talisay` False (South Cotabato).
  - **`test_parse_tc_fixture`:** event `'Tropical Cyclone Alert'`, severity `'Minor'`, `expires` set.
  - **`test_covers_by_polygon_geocode_and_name`:**
    - a square `10.0,123.5 10.5,123.5 10.5,124.0 10.0,124.0 10.0,123.5` covers Talisay
    - geocode `'072200000'` alone covers it
    - `area_desc 'Cebu'` with no polygon covers it
    - South Cotabato's polygon doesn't
  - **`test_floor_mapping`:**
    - Flood + Minor gives Flood Yellow
    - Flood + Severe gives Flood Orange
    - TC + Severe gives both Orange
    - TC + Extreme gives both Red
    - TC + Minor gives `{}`
    - `'Thunderstorm Advisory'` + Severe gives `{}`
  - **`test_active_rules`:** expired → False; Cancel → False; referenced by a newer alert → False;
    otherwise True.
  - **`test_check_feed_stores_new_and_skips_known`:** a fake `get` serves the fixtures. The second
    call returns 0.
  - **`test_malformed_entries_are_skipped`** (Review Focus 2):
    - one CAP fake returns `'<html>502</html>'` and one has no `<expires>`, while the third is stored
      (count 1)
    - a feed fake returning HTML gives 0 and raises nothing
  - **`test_hazard_list_survives_a_failing_check`:** with `PAGASA_FEED_WRITER=True` and
    `check_in_background` patched to raise, `GET /api/hazards/` returns 200.
  - **`test_hook_runs_at_most_hourly`:** two GETs give one `check_in_background` call; with the
    setting False, none.
- [ ] **Step 2: Run** `<T> tests.test_rainwatch_pagasa`. Expected: ImportError.
- [ ] **Step 3: Implement** `pagasa.py` with `xml.etree.ElementTree` and the CAP 1.2 namespace
  `urn:oasis:names:tc:emergency:cap:1.2`, plus the hook in `hazards/views.py`.
- [ ] **Step 4: Run** `<T> tests.test_rainwatch_pagasa tests.test_alert_jobs`. Expected: OK.

### Task 6: DRRMO overrides

**Files:**
- Modify: `backend/apps/rainwatch/{serializers,views,urls}.py`
- Test: `backend/tests/test_rainwatch_overrides.py`

**Interfaces:**
- **Consumes:** `utils.permissions.IsDRRMOOfficer` and `assess.bump()`.
- **Produces:**
  - `GET /api/rain-watch/overrides/`: active and the last 20, each
    `{id, hazard, level, starts_at, ends_at, note, created_by_name, cancelled_at}`.
  - `POST /api/rain-watch/overrides/` with `{hazard, level, ends_at, note}`: returns 201.
  - `POST /api/rain-watch/overrides/<id>/cancel/`: returns 200, or **409** when already cancelled.
  - Every write calls `bump()`.
  - `assess.active_overrides(now) -> list[RainWatchOverride]`: not cancelled, and
    `starts_at ≤ now < ends_at`. Task 7 uses it.

- [ ] **Step 1: Write the failing tests:**
  - **`test_drrmo_and_admin_can_create`**
  - **`test_barangay_bfp_and_anonymous_get_403_or_401`**
  - **`test_validation`:** each gets 400:
    - `ends_at` in the past
    - `ends_at` at now + 73 h
    - a blank note
    - a 301-character note
    - level `'Green'`
    - hazard `'Fire'`
  - **`test_cancel_and_double_cancel_409`**
  - **`test_active_overrides_excludes_cancelled_and_ended`**
- [ ] **Step 2: Run** `<T> tests.test_rainwatch_overrides`. Expected: failures.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `<T> tests.test_rainwatch_overrides`. Expected: OK.

### Task 7: Working out the levels, and `GET /api/rain-watch/`

**Files:**
- Modify: `backend/apps/rainwatch/assess.py`, `views.py`, `urls.py`
- Test: `backend/tests/test_rainwatch_assess.py`

**Interfaces:**
- **Consumes:**
  - Task 2: `Rules`, the level functions, `combine`, the limit functions
  - Task 3: `RunData`, `stitched`, `place_hours`, `manila_day_total`, `CITY`, `UPLAND`
  - Task 5: `PagasaAlert`, `pagasa.floor_for`, `pagasa.is_active`, `pagasa.referenced_identifiers`
  - Task 6: `active_overrides`
  - Rain: `apps.history.rain.read_rain_csv`, `recent_rain`
  - Limits: `apps.history.exposure.read_exposure`, `apps.history.hazard_data.read_terrain`
- **Produces:**
  - `DAY_KEYS = ('today', 'tomorrow', 'day_after')`
  - `wet_ground(today: date, rules: Rules, rain_file=None, recent=None) -> dict`:
    - Returns `{'mm_14_days': float | None, 'wet': bool | None}`.
    - Uses the latest 14 consecutive days with values ending before `today`, from the file chained
      with `recent_rain(rf.cells, after=rf.last_day, today=today)`. Take any one barangay's series;
      they all share one cell.
    - Fewer than 14 such days within the 20 before today gives `None` / `None`.
  - `latest_runs(now) -> list[RunData]`: runs with `init_time ≥ now − 4 days`.
  - `is_stale(now, rules) -> bool`: per Fixed values.
  - `build(now, rules, runs, wet, alerts, overrides, exposure, terrain, barangays: dict[int, str]) -> dict`:
    pure. Returns the staff response with exactly the shape in spec 6.7, including `pagasa_alerts`
    and `overrides`.
  - `public_view(result: dict) -> dict`: Green and Yellow become `"none"`, their reasons are emptied,
    `pagasa_alerts` and `overrides` are dropped, and floors whose level is Yellow are removed.
  - `rain_watch(now=None, staff=False) -> dict`: loads everything, caches 300 s under
    `f'rainwatch:result:{version}:{"staff" if staff else "public"}'`, returns `build` or
    `public_view(build)`.
  - `GET /api/rain-watch/`: `AllowAny`. `staff` is true when the user's role name is in
    `('DRRMO_Officer', 'System_Admin')`.

**How `build` decides each level.** For each day key, barangay and hazard:
1. **Forecast level:**
   - Flood: `flood_level(max(city_day, upland_day), wet)`.
   - Landslide: `slide_level(sum of the 3 upland days, wet)`.
   - `wet = bool(wet['wet'])`.
   - Any needed day that is incomplete counts as missing when there is no value at all. If there
     *is* a value, the level is still computed and `' (partial)'` is added to the reason.
   - When `is_stale`, or when the needed days have no hours at all, the forecast level is `None` and
     the reason is `'Forecast out of date'`.
2. **Limits:**
   - Flood: not in `flood_exposed_ids` gives `one_step_lower`, with the limited reason.
   - Landslide: not in `steep_ids` gives `landslide: null`.
   - A barangay missing from either CSV counts as not exposed and not steep.
3. **Floors:**
   - Active PAGASA alerts whose period overlaps the Manila day, through `floor_for`.
   - Active overrides overlapping the day (`'Both'` covers both hazards).
   - Each floor goes through the same limits: flood floors one step lower for barangays that aren't
     flood-exposed, landslide floors only for steep ones.
   - Each applied floor adds its reason.
4. **Final:** `combine(forecast, floors)`. `None` serializes as `"unknown"`.

- [ ] **Step 1: Write the failing tests.** Use real CSV limits; runs, alerts and overrides are built
  in memory for `build`, in the database for `rain_watch`.
  - **`test_tino_like_run`:** an upland and city series giving 192 mm tomorrow on dry ground.
    Tomorrow: Bulacao (id 2) flood Red, with reason `'Forecast 192 mm'`; Camp IV (id 4) flood Orange
    with the limited reason; Camp IV landslide Red; Biasong (id 1) landslide `None` (JSON `null`).
  - **`test_wet_ground_reason`:** 23 mm and wet gives Yellow with `'Forecast 23 mm; ground already
    wet'`.
  - **`test_pagasa_floor_raises_only`:** a Severe TC alert covering Talisay and active today, over a
    dry forecast: today's flood is Orange in exposed barangays and Yellow in limited ones; landslide
    is Orange only in steep ones; the reason is `'Raised to Orange: PAGASA Tropical Cyclone Alert'`.
    It never lowers a Red forecast.
  - **`test_override_floor_and_reason`:** a DRRMO Red override with note "HRW #3" gives `'Raised by
    DRRMO: HRW #3'`.
  - **`test_stale_hides_forecast_keeps_floors`:** newest full run received 13 h ago: forecast levels
    are `"unknown"` and `stale: true`, while an active override still shows its level.
  - **`test_no_runs_yet`** (Review Focus 1): no runs and no floors: every level is `"unknown"`,
    `stale: true`, `updated_at: null`.
  - **`test_newest_run_too_short_for_day_after`** (Review Focus 5): gap-fill runs only after an old
    full run that ends before the Day after. The Day after is `"unknown"`; today has a level.
  - **`test_barangay_missing_from_csv`** (Review Focus 3): an extra barangay id 99 gets a flood level
    one step lower and landslide `null`, with no error.
  - **`test_public_view_hides_yellow_and_green`:** anonymous `GET /api/rain-watch/` gets no
    `'Yellow'`/`'Green'` anywhere; DRRMO sees `'Yellow'`; barangay personnel see the public version.
  - **`test_cache_cleared_by_new_run`:** GET, then POST a run, then GET again: the response changes.
  - **`test_wet_ground_from_file_and_recent`:** a toy rain file plus a fake recent dict sum the right
    14 days; a gap gives `None`.
  - **`test_wetness_unknown_uses_dry_cutoffs`:** `wet = {'mm_14_days': None, 'wet': None}` and 23 mm
    give Green, with `'Ground wetness unknown'` in the staff reasons and not in the public view.
- [ ] **Step 2: Run** `<T> tests.test_rainwatch_assess`. Expected: failures.
- [ ] **Step 3: Implement** `assess.py` and the view.
- [ ] **Step 4: Run** `<T> tests.test_rainwatch_assess tests.test_rainwatch_ingest tests.test_rainwatch_overrides`.
  Expected: OK.

### Task 8: The forecast job (GitHub Actions)

**Files:**
- Create: `tools/rain_forecast/{gfs,fetch}.py`, `tools/rain_forecast/requirements.txt`,
  `tools/rain_forecast/test_rain_forecast.py`, `.github/workflows/rain-forecast.yml`
- Modify: `.github/workflows/ci.yml` (one step after the backend tests:
  `run: python -m unittest discover -s ../tools/rain_forecast -p "test_*.py"`)

**Interfaces:**
- **Produces** (no Django; `eccodes`, `dynamical_catalog`, `icechunk` and `zarr` imported only inside
  the functions that need them):
  - **`gfs.GRID`**: as in Fixed values.
  - **`gfs.nomads_url(cycle: datetime, hour: int) -> str`:**
    - `filter_gfs_0p25.pl` with `dir=/gfs.YYYYMMDD/HH/atmos`, `file=gfs.tHHz.pgrb2.0p25.fFFF`
    - `var_APCP=on&lev_surface=on&subregion=&toplat=10.5&leftlon=123.75&rightlon=124&bottomlat=10.25`
    - *Changed during the build (ruling of 2026-11-18):* NOMADS `PRATE` turned out to be an
      instantaneous rate, which failed the acceptance check (up to 8.7 mm a day off). The job reads
      `APCP` (rain accumulated since the last 6-hour reset) and converts it with
      `gfs.per_hour_from_acc`. That matches dynamical.org to within 0.006 mm a day.
  - **`gfs.per_hour_from_avg(avgs: list[float]) -> list[float]`:** see the algorithm below.
  - **`gfs.fetch_nomads(cycle, hours: int, get=None, decode=None, pause=1.0) -> dict[tuple[float, float], list[float]]`:**
    - `get(url) -> bytes`; `decode(bytes) -> dict[(lat, lon), float]` (mm/s; the default uses
      eccodes)
    - raises `RuntimeError` if any hour is missing
  - **`gfs.fetch_dynamical(hours: int, newest_before: datetime) -> tuple[datetime, dict]`:** the
    newest archived run, `precipitation_surface × 3600`, leads 1..hours.
  - **`gfs.latest_cycle(now, exists=None) -> datetime | None`:** the newest of the last 4 cycles at or
    before `now − 3 h` whose f096 file `exists(url)`.
  - **`fetch.plan_runs(now, held: list[dict], newest: datetime | None) -> list[tuple[datetime, int]]`:**
    - `(newest, 96)` when no held run for `newest` has ≥ 72 hours
    - then `(cycle, 6)` for each cycle in `(now − 72 h, newest)` with no held run, newest first, at
      most 12
  - **`fetch.payload(source, init, series, version) -> dict`:** the body in spec 6.1, with
    `first_hour_start = init`.
  - **`fetch.main(argv=None, env=os.environ, get=..., post=..., exists=...) -> int`:**
    - `--dry-run` prints the plan and payload sizes and posts nothing
    - `--compare YYYYMMDDHH` fetches that cycle from both sources and prints per-point daily
      differences
    - returns non-zero when the newest run could not be posted after 3 tries
- **Workflow** `rain-forecast.yml`:
  - `on: schedule: [{cron: '17 4,10,16,22 * * *'}]` and
    `workflow_dispatch: inputs: dry_run (boolean, default false)`
  - `permissions: contents: read`; `concurrency: rain-forecast`; `timeout-minutes: 15`
  - steps: checkout, setup-python 3.12, `pip install -r tools/rain_forecast/requirements.txt`, run
    `python tools/rain_forecast/fetch.py` with `env: RAIN_WATCH_API_URL` and
    `RAIN_WATCH_INGEST_TOKEN` from `secrets`, adding `--dry-run` when the input is true
  - a top comment saying it must be on `main` to run on schedule, and never pushes

**Algorithm** (GFS PRATE averages reset every 6 hours):

```python
def per_hour_from_avg(avgs):          # avgs[f-1] = mean rate (mm/s) from the last 6-h boundary to hour f
    out = []
    for f, a in enumerate(avgs, start=1):
        k = (f - 1) % 6 + 1           # hours since the boundary
        prev = avgs[f - 2] if k > 1 else 0.0
        out.append(max(0.0, (k * a - (k - 1) * prev) * 3600.0))
    return out
```

- [ ] **Step 1: Write the failing tests** in `test_rain_forecast.py` (`unittest`, no network):
  - **`test_per_hour_from_avg`:** hourly rain `[1, 2, 3, 0, 0, 6, 4]` mm becomes averages
    `[1, 1.5, 2, 1.5, 1.2, 2, 4]` mm/h ÷ 3600, which come back as `[1, 2, 3, 0, 0, 6, 4]`
    (`assertAlmostEqual`, places = 6). Constant input stays constant.
  - **`test_plan_runs`:**
    - nothing held gives `(newest, 96)` and then up to 12 `(cycle, 6)`
    - newest held with 96 hours gives no full run
    - newest held with only 6 hours gives `(newest, 96)` again
  - **`test_payload_shape`:** 4 points, `first_hour_start == init` in ISO UTC.
  - **`test_main_dry_run_posts_nothing`** and **`test_main_retries_then_fails`** (fake `post` always
    raises: return code 1, 3 attempts).
  - **`test_fetch_nomads_uses_decode_per_hour`**, with fake `get` and `decode`.
- [ ] **Step 2: Run** `<J>`. Expected: ImportError.
- [ ] **Step 3: Implement** `gfs.py`, `fetch.py`, `requirements.txt` (pin `requests`, `numpy`,
  `eccodes`, `dynamical-catalog>=0.8.0`, `icechunk` and `zarr` at their current versions), the
  workflow and the CI step.
- [ ] **Step 4: Run** `<J>`. Expected: OK.
- [ ] **Step 5: Acceptance check** (manual, network, outside the project).
  - **Setup:** in the scratch venv
    `C:\Users\SANNIC~1\AppData\Local\Temp\claude\de7ff8623febfdf5\d2376158-421d-4107-a21c-5c7cc0673f28\scratchpad\backtest\venv`,
    or a fresh one, run `pip install eccodes requests`.
  - **Run:** `python -I tools/rain_forecast/fetch.py --compare <a cycle from 1–3 days ago>`.
  - **Expected:** every point's daily difference ≤ 0.1 mm.
  - **If it differs:** fix `per_hour_from_avg` or the hour alignment before going on.

### Task 9: The public map

**Files:**
- Create: `frontend/src/api/rainWatchApi.js`
- Create in `frontend/src/components/RainWatch/`: `rainWatchLevels.js`, `rainWatchLevels.test.js`,
  `RainWatchDayPicker.jsx`, `RainWatchBanner.jsx`, `RainWatchLegend.jsx`, `rainWatch.css`
- Modify: `frontend/src/pages/PublicMap.jsx`, `frontend/src/components/Forecast/forecastLevels.js`

**Interfaces:**
- **`rainWatchApi`:**
  - `get({ background })`: GET `/api/rain-watch/`. Spread `BACKGROUND` from `./axiosClient` into the
    request config when `background` is set, as `hazardsApi` does.
  - `overrides()`, `createOverride({ hazard, level, endsAt, note })`, `cancelOverride(id)`.
- **`rainWatchLevels.js`:**
  - **`RAIN_LEVELS`:** `Red #c81e1e` (rank 3), `Orange #ef7d22` (2), `Yellow #f4c430` (1),
    `Green #3a9d5d` (0), `none` (no fill, label `'No rain watch'`, −1), `unknown #9aa3b2`
    (label `'Out of date'`, −2).
  - `RAIN_FILL_OPACITY = 0.4`, `RAIN_WATCH_NOTE`, `RAIN_WATCH_CREDITS` (exact copy).
  - `dayData(data, key)`.
  - `barangayLevel(row, activeTypes) -> string`: the worst of the visible Flood/Landslide levels;
    ignores a `null` landslide.
  - `laterDayHint(data, activeTypes, currentKey) -> {key, level, count} | null`: the first day after
    `currentKey` with any Orange or Red.
  - `bannerInfo(data, activeTypes) -> {key, level, count} | null`: the first day, from Today, with any
    Orange or Red.
  - `dayLabel(day, index, now) -> 'Today' | 'Tomorrow' | 'Wed'`.
  - `updatedText(updatedAt, now) -> 'Updated just now' | 'Updated 3 h ago' | 'No forecast yet'`.
  - `rainWatchTooltip(name, barangayId, data, dayKey, activeTypes) -> string`: HTML with the name
    escaped. A three-day strip (`'Today – · Tomorrow Orange · Wed Red'`) plus the chosen day's reasons
    per hazard.
- **`FLOOD_LANDSLIDE_MONTHLY_NOTE`** in `forecastLevels.js` (exact copy).

- [ ] **Step 1: Write the failing helper tests** in `rainWatchLevels.test.js`:
  - `barangayLevel` picks the worse of the two hazards, respects the ticks, and ignores a `null`
    landslide.
  - `laterDayHint` returns `{key: 'day_after', level: 'Red', count: 6}` for a fixture with 6 Red
    barangays on the day after; `null` when nothing is above Yellow.
  - `bannerInfo` ignores Yellow.
  - `updatedText(null) === 'No forecast yet'`, and 3 h gives `'Updated 3 h ago'`.
  - `rainWatchTooltip` escapes `<b>` in names.
  - A stale fixture (all levels `'unknown'`, Review Focus 1) gives `barangayLevel` `'unknown'` and
    `bannerInfo` null.
- [ ] **Step 2: Run** `<F> rainWatchLevels`. Expected: failures.
- [ ] **Step 3: Implement** `rainWatchApi.js` and `rainWatchLevels.js`.
- [ ] **Step 4: Run** `<F> rainWatchLevels`. Expected: PASS.
- [ ] **Step 5: Write the failing component tests:**
  - `RainWatchDayPicker`: three buttons with `aria-pressed`; the third reads `'Wed (less certain)'`.
  - `RainWatchLegend`: shows `RAIN_WATCH_NOTE`, the credits and `'Updated 3 h ago'`; when stale,
    shows `'Out of date: last forecast 13 h ago'`; with no runs, `'No forecast yet'`.
  - `RainWatchBanner`: text `'Rain watch: Red expected Wed → view'`, and calls `onView('day_after')`.

  Use the `createRoot` + `act` pattern from
  `frontend/src/components/Tutorials/CategoryPicker.test.js`.
- [ ] **Step 6: Implement** the three components and `rainWatch.css`. They must fit a 360 px phone
  screen: the picker wraps, the banner is one line with ellipsis.
- [ ] **Step 7: Wire up `PublicMap.jsx`:**
  - **The view and day:** `VIEWS` gains `{ key: 'next3', label: 'Next 3 days', note: null }`. Add
    state `rainWatch` (null) and `rainDay` (`'today'`).
  - **Loading:** fetch `rainWatchApi.get({ background: true })` on mount and every 10 minutes, in any
    view, for the banner. On error keep the last data.
  - **Shading:** a `barangayStyle` branch for `'next3'` (fill from `RAIN_LEVELS`; `none` gives
    opacity 0; `unknown` gives grey at 0.25).
  - **Tooltip:** an `onEachFeature` branch for `'next3'` using `rainWatchTooltip`.
  - **Picker:** show the day picker in place of `ForecastPeriodPicker` when `view === 'next3'`.
  - **Legend:** `RainWatchLegend` when `view === 'next3'`.
  - **Banner:** `RainWatchBanner` whenever `bannerInfo` is non-null. `onView` sets view `'next3'` and
    `rainDay`.
  - **Hint:** the later-day hint under the picker, from `laterDayHint`.
  - **Monthly note:** `FLOOD_LANDSLIDE_MONTHLY_NOTE`, with a "Next 3 days" button, in the legend when
    `view === 'likely'` and Flood or Landslide is ticked.
  - **Rebuilds:** add `rainWatch?.updated_at` and `rainDay` to the `GeoJSON` `key` when the view is
    `'next3'`.
- [ ] **Step 8: Run** `<F> RainWatch rainWatchLevels forecastLevels PublicMap`. Expected: PASS.
  Then run `npm run build` (CI treats warnings as errors). Expected: compiled with no warnings.

### Task 10: DRRMO dashboard card and override form

**Files:**
- Create: `frontend/src/components/RainWatch/RainWatchCard.jsx`, `RainWatchOverrideForm.jsx`,
  `RainWatchCard.test.js`, `RainWatchOverrideForm.test.js`
- Modify: `frontend/src/pages/Dashboard/DRRMODashboard.jsx`, adding a `<section className="adm-card">`
  with `<h2>Rain watch</h2>` just above the "Likely hazards" card (around line 746)

**Interfaces:**
- **Consumes:** `rainWatchApi` and the `rainWatchLevels` helpers (Task 9), and `Modal`, `Toast` and
  `timeAgo` from `pages/Dashboard/admin/adminShared`.
- **Produces:**
  - **`<RainWatchCard />`:**
    - loads `rainWatchApi.get()` every 5 minutes
    - shows `updatedText`, and a red "Out of date" line when stale
    - a table of barangays with any level above Green on any day: rows of barangay × hazard, columns
      Today / Tomorrow / Day after, each cell the level with its reasons as a `title`
    - a line "All other barangays: Green"
    - the PAGASA alerts (headline, severity, until, "Applied" / "Not applied")
    - the active overrides, each with **Cancel** (confirm in a `Modal`)
    - a button **"Set a level by hand"** opening the form
  - **`<RainWatchOverrideForm onSaved onCancel />`:**
    - Hazard select (Flood / Landslide / Both), Level select (Yellow / Orange / Red)
    - "Until" `datetime-local`, defaulting to now + 12 h, at most now + 72 h
    - Note textarea: required, at most 300 characters, placeholder
      `'e.g. PAGASA Visayas heavy rainfall warning #3, Orange'`
    - shows server field errors with `fieldErrors`

- [ ] **Step 1: Write the failing tests:**
  - **Card:** with a mocked `get` (1 Yellow, 1 Red, a not-applied PAGASA alert, 1 override), it
    renders 2 rows, "All other barangays: Green", "Not applied" and a Cancel button. Cancel then
    confirm calls `cancelOverride(id)` and reloads.
  - **Form:** submitting with a blank note shows `'Add a note saying where the warning came from.'`
    and does not call the API. A valid submit calls `createOverride` with the ISO `endsAt`. A 400
    with `{note: ['…']}` shows the message.
- [ ] **Step 2: Run** `<F> RainWatchCard RainWatchOverrideForm`. Expected: failures.
- [ ] **Step 3: Implement** both components and the dashboard section.
- [ ] **Step 4: Run** `<F> RainWatch DRRMODashboard`. Expected: PASS. Then `npm run build`.
  Expected: no warnings.

### Task 11: Docs, attribution, full runs

**Files:**
- Modify: `deploy/render.env.example` (add `RAIN_WATCH_INGEST_TOKEN=`, `PAGASA_FEED_WRITER=true`,
  `HAZARD_LOG_WRITER=true`, each with a one-line comment)
- Modify: `deploy/FREE_HOSTING.md` (a new section "Rain watch: GitHub job", covering the steps of spec
  6.10, the $0 spending limit, and re-enabling a paused workflow)
- Modify: `README.md` (one paragraph on the Rain watch and `tools/rain_forecast`)
- Modify: `backend/apps/history/data/ATTRIBUTION.md` (NOAA GFS, dynamical.org CC BY 4.0, PAGASA
  CC BY 4.0)

- [ ] **Step 1: Write the docs above.** Wording is plain, matching the files' existing style.
- [ ] **Step 2: Full backend suite:** `<T> tests apps`. Expected: everything OK (compare with the
  last full log; no new failures).
- [ ] **Step 3: Full frontend suite:** `CI=true npx react-scripts test --watchAll=false`, then
  `npm run build`. Expected: PASS, no warnings.
- [ ] **Step 4: Tool tests:** `<J>`. Expected: OK.
- [ ] **Step 5: Light-Render check:** `grep -rnE "eccodes|xarray|zarr|icechunk|dynamical_catalog|pandas" backend/apps/rainwatch`.
  Expected: no matches.

### Task 12: Go-live (STOP: each numbered item needs the user's go-ahead)

- [ ] **Step 1:** Ask the user for the go-ahead to migrate. Then back up the shared Supabase database
  to Downloads, the same way as for migrations 0001–0008, and confirm the file's size is non-zero.
  Also report the database's current size (`SELECT pg_size_pretty(pg_database_size(current_database()))`),
  because the free plan goes read-only above 500 MB.
- [ ] **Step 2:** Apply `rainwatch.0001_initial` to the shared database. Check that
  `RainWatchRules.current()` returns the Balanced row.
- [ ] **Step 3:** The user sets these on Render: `RAIN_WATCH_INGEST_TOKEN` (a long random value; give
  them one generated with `python -c "import secrets; print(secrets.token_urlsafe(48))"`),
  `PAGASA_FEED_WRITER=true`, and a check that `HAZARD_LOG_WRITER=true`.
- [ ] **Step 4:** The user sets up GitHub:
  - adds secrets `RAIN_WATCH_INGEST_TOKEN` and `RAIN_WATCH_API_URL`
    (`https://geoalert-rvqc.onrender.com`)
  - sets the Actions spending limit to $0
  - checks whether the repo is public or private
- [ ] **Step 5:** The user deploys the feature branch, and puts `.github/workflows/rain-forecast.yml`
  and `tools/rain_forecast/` on `main`.
- [ ] **Step 6:** The user runs the workflow by hand: first with `dry_run`, then for real. Then check:
  - `GET /api/rain-watch/forecast-runs/status/` (with the token) lists the newest run with 96 hours
    and up to 12 short runs
  - the map's Next 3 days view shows "Updated … ago"
  - the DRRMO card loads
  - within an hour, `pagasa_alert` has rows
- [ ] **Step 7:** Update the memory note and the research doc's section 0 with what went live.
