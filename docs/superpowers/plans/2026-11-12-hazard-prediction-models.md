# Hazard Prediction Models Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build rain-and-terrain models for flood and landslide, chosen by an honest
held-out test. Turn their daily chances into GeoAlert's month and week forecast through
rain scenarios, and add an "All hazards" combined chance with hazard filtering on one
0–1 scale.

**Architecture:**
- **Offline:** three commands build data files in `backend/apps/history/data/`: terrain per
  barangay, daily rain, and the model test report.
- **At request time:** the forecast refits the tested winner (cached for 6 hours, behind a
  lock), predicts daily chances over past rain years, and aggregates them into periods.
  Then it combines hazards.
- **Fire:** its model (`model_forecast.py`) is untouched and is only read.

**Tech Stack:**
- **Backend:** Django 4.2 + DRF, numpy, scikit-learn 1.9.1, `xgboost-cpu==3.2.0` (new),
  Open-Meteo HTTP via `requests`.
- **Frontend:** React (react-scripts, Jest).

**Spec:** `docs/superpowers/specs/2026-11-12-hazard-prediction-models-design.md` (approved
2026-11-12). Read it alongside this plan. Section and item numbers below (B.3, D.5, 2.3…)
refer to it.

## Global Constraints

**Process rules:**
- **Never commit.** The project rule: leave all specs, plans and code uncommitted. No
  task has a commit step.
- **No database migration.** Code only reads the shared database.
- **Fire unchanged.** `apps/history/model_forecast.py` and `apps/history/forecast.py` are
  not edited. Fire's rows, levels and accuracy report stay identical.
- **No counting for flood or landslide.** A model that can't run shows
  `method: "unavailable"`, never counting.
- **Backend test command** (Git Bash, from `backend/`). The shared `test_postgres`
  collides with other runs, so tests use a private database:
  `PYTHONPATH="C:/Users/Sannichigetsu/.geoalert-test" DJANGO_SETTINGS_MODULE=geo_test_settings venv/Scripts/python.exe manage.py test <labels> --noinput > "C:/Users/Sannichigetsu/.geoalert-test/last.log" 2>&1; tail -n 15 "C:/Users/Sannichigetsu/.geoalert-test/last.log"`.
  Call this **`<T>`** below. Keep the full log; never filter tracebacks out.
- **Frontend test command** (from `frontend/`):
  `CI=true npx react-scripts test --watchAll=false <pattern>`. Call this **`<F>`**.

**Study design:**
- **Study period:** `STUDY_START = date(2021, 1, 1)`, `STUDY_END = date(2025, 12, 31)`.
- **Day:** a calendar day in `Asia/Manila`. Record times are converted to local time
  before taking the date.
- **Rain:** Open-Meteo, `models=ecmwf_ifs`, `daily=precipitation_sum`,
  `timezone=Asia/Manila`, at each barangay's `point_on_surface`. Forecast rain is never a
  model input.
- **Rain windows**, inclusive and ending on day *d*:
  `r0`=d, `r1`=d−1, `r3`=d−2..d, `r7`=d−6..d, `r14`=d−13..d. Any missing day makes the
  window missing, and the row is dropped.
- **Flood terrain:** `hand_lt2` (HAND < 2 m), `hand_lt5` (< 5 m), `elev_lt10`
  (elevation < 10 m), `water_200` (dist_water < 200 m), `coast_500` (dist_coast < 500 m),
  `built_density` (mean building_density).
- **Landslide terrain:** `slope_gt18`, `slope_gt30`, `relief` (mean), `road_50`
  (dist_road < 50 m), `stream_150` (dist_water < 150 m).
- **Feature order:** rain features first, then terrain, in the order listed.
- **Excluded source_refs** (the main run):
  - `flood-landslide:d2d9fa7d9b088324` (Bulacao)
  - `flood-landslide:ba57920aece010af` (Tabunok)
  - `flood-landslide:a0c6189d03dfc448` (Linao)
  - `flood-landslide:aaa56259189e9d34` (Jaclupan)

**Models and evaluation:**
- **Candidates, simplest first:** `logistic_regression`, `random_forest`, `xgboost`.
  - LR: L2, C=1.0, lbfgs, max_iter=2000, with log1p of the rain features and
    StandardScaler.
  - RF: n_estimators=500, max_depth=3, min_samples_leaf=200, max_features="sqrt",
    random_state=0.
  - XGB: n_estimators=200, max_depth=2, learning_rate=0.05, subsample=0.8, reg_lambda=1,
    min_child_weight=0.1, scale_pos_weight=1, random_state=0.
  - All three start with SimpleImputer(median). No re-weighting.
- **Monotonic constraints (RF and XGB):** every rain feature +1. Flood terrain +1 except
  `coast_500` = 0. Landslide terrain all +1.
- **Folds:** train 2021–2022 / test 2023; train 2021–2023 / test 2024; train 2021–2024 /
  test 2025.
- **Benchmark:** `p = (k_bm + π·30) / (n_m + 30)`, using training years only. No-skill =
  π.
- **Alarm threshold:** set on training predictions so that 1% of training barangay-days
  are flagged.
- **Bootstrap:** moving blocks of 7 days within each test year, all barangays together,
  1,000 replicates, seed 0.
- **Selection:** lowest mean log loss over the 3 test years. A simpler candidate wins if
  the 95% interval of its log-loss difference from the leader includes 0.
- **Platt scaling:** RF and XGB only, and only when the last training year has at least
  one event. Fit the base model on the training years before the last, fit Platt on the
  last, then refit the base model on all training years, keeping the Platt mapping.
  Isotonic is never used.

**Forecast:**
- **Levels:** `model_forecast.level_for` (High ≥ 0.25, Moderate ≥ 0.15, else Low), always
  on the **month's** chance. The week view: date ± 3 days (`forecast.DAY_WINDOW`).
- **Caching:** the fitted model for 6 h, behind a lock. Live recent rain for 3 h; a failed
  fetch is cached for 15 min. `past_days` = min(92, days since the rain file ends), one
  point per distinct grid cell.
- **HTTP:** the forecast and accuracy responses carry `Cache-Control: public, max-age=600`.

**Interface copy (exact):**
- **Attribution:** "Rain data by Open-Meteo.com (CC BY 4.0), processed into hazard chances
  by GeoAlert". Link "Open-Meteo.com" to `https://open-meteo.com/` and "CC BY 4.0" to
  `https://creativecommons.org/licenses/by/4.0/`.
- **Disclaimer:** "Fire is estimated from past fires; flood and landslide from rain and
  terrain in past years. It is a heads-up for preparing, not a warning that a hazard is
  coming. Live alerts come only from the DRRMO."
- **Accuracy card sub line:** "Fire uses its model only if it beats counting. Flood and
  landslide always use their rain and terrain model, and this card says when it does not
  beat counting."
- **In-training note:** "The model learned from this period; see the accuracy check for
  results on years it never saw."
- **Seasonal outlook:** title "Seasons on record"; sub line "What past years brought,
  counted from the archive. Not a prediction: the likelihood below comes from the models."

## Review Focus

Each of these has its test in the task that owns the code:
1. **A flood or landslide record dated after `STUDY_END`** (an approved 2026 report).
   Expected: the forecast and the fit don't change, and the card is not marked stale.
   Tests: Task 4 `test_signature_ignores_records_after_study_end`, Task 9
   `test_record_after_study_end_keeps_fit`.
2. **A barangay with a boundary but no terrain row or no rain series** (a boundary added
   later). Expected: its flood and landslide rows are unavailable with a reason, the other
   barangays are normal, and its combined row lists `missing`. Test: Task 9
   `test_barangay_without_terrain_is_unavailable_alone`.
3. **An exact date whose week crosses New Year** (2026-12-30). Expected: scenario dates
   run into year s+1, and a scenario year without s+1 rain is skipped. Test: Task 7
   `test_week_crossing_new_year_needs_next_year_rain`.
4. **A period with no complete rain year before it** (Month and year: January 2021).
   Expected: unavailable, reason "no rain years before this period", not 0%. Test: Task 9
   `test_no_rain_year_before_period_is_unavailable`.
5. **Open-Meteo down, slow or rate-limiting the live call.** Expected: the forecast still
   answers, `recorded_rain_probability` is left out, and nothing is retried for 15
   minutes. Tests: Task 3 `test_recent_rain_failure_is_cached_15_minutes`, Task 10
   `test_forecast_answers_when_live_rain_fails`.

---

### Task 1: Records, exclusions and rain windows

**Files:**
- Create: `backend/apps/history/hazard_data.py`
- Create: `backend/apps/history/data/hazard_model_exclusions.csv`
- Test: `backend/tests/test_hazard_data.py`

**Interfaces:**
- Produces:
  - constants `STUDY_START`, `STUDY_END`, `HAZARDS = ('Flood', 'Landslide')`,
    `RAIN_FEATURES = ('r0','r1','r3','r7','r14')`, `TERRAIN_FEATURES: dict[str, tuple[str, ...]]`
    (the order in Global Constraints), `DATA_DIR = Path(__file__).parent / 'data'`
  - `@dataclass(frozen=True) Record(source_ref: str, hazard: str, barangay_id: int | None, day: date, subtype: str, is_sample: bool)`
  - `load_records(hazard: str) -> list[Record]`: from `HistoricalRecord`, `day` in Manila
    local time
  - `load_exclusions(path: Path = DATA_DIR / 'hazard_model_exclusions.csv') -> dict[str, str]`
    (source_ref → reason)
  - `positives(records, barangay_ids: set[int], start: date, end: date, excluded: set[str]) -> set[tuple[int, date]]`
  - `rain_windows(daily: Mapping[date, float | None], day: date) -> dict[str, float] | None`

- [ ] **Step 0: Create the private test settings** (outside the repo):
  `C:\Users\Sannichigetsu\.geoalert-test\geo_test_settings.py` with
  `from config.settings.development import *` and
  `DATABASES["default"]["TEST"] = {"NAME": "test_geoalert_hazard_models"}`.

- [ ] **Step 1: Write the failing tests** in `test_hazard_data.py`

```python
class RainWindowTests(SimpleTestCase):
    def test_windows_are_inclusive_sums_ending_on_the_day(self):
        daily = {date(2024, 1, i): float(i) for i in range(1, 21)}
        w = rain_windows(daily, date(2024, 1, 14))
        self.assertEqual(w, {'r0': 14, 'r1': 13, 'r3': 39, 'r7': 77, 'r14': 105})

    def test_a_missing_day_makes_the_row_missing(self):
        daily = {date(2024, 1, i): 1.0 for i in range(1, 21)}
        daily[date(2024, 1, 9)] = None
        self.assertIsNone(rain_windows(daily, date(2024, 1, 14)))
        self.assertIsNone(rain_windows(daily, date(2024, 1, 5)))   # window reaches before the data

class PositiveTests(SimpleTestCase):
    # rec(ref, barangay, day, sample=False) builds a Record
    def test_rules(self):
        recs = [rec('a', 1, date(2021, 6, 12)), rec('b', 1, date(2021, 6, 12)),      # same barangay-day: one row
                rec('c', None, date(2021, 6, 12)), rec('d', 2, date(2022, 7, 8)),    # no barangay; excluded ref
                rec('e', 2, date(2026, 1, 3)), rec('f', 2, date(2023, 6, 26), sample=True)]
        got = positives(recs, {1, 2}, STUDY_START, STUDY_END, excluded={'d'})
        self.assertEqual(got, {(1, date(2021, 6, 12))})

    def test_exclusions_file_lists_the_four_jul_2022_records(self):
        self.assertEqual(set(load_exclusions()), {
            'flood-landslide:d2d9fa7d9b088324', 'flood-landslide:ba57920aece010af',
            'flood-landslide:a0c6189d03dfc448', 'flood-landslide:aaa56259189e9d34'})

class RecordDayTests(TestCase):
    def test_day_is_manila_local(self):
        # HazardType Flood, Barangay with boundary; HistoricalRecord occurred_at 2022-07-07T16:00Z
        self.assertEqual(load_records('Flood')[0].day, date(2022, 7, 8))
```

- [ ] **Step 2: Run** `<T> tests.test_hazard_data`. Expected: FAIL (ImportError).

- [ ] **Step 3: Implement** the Interfaces above in `hazard_data.py`. Write the exclusions
  CSV with header `source_ref,reason`, one row per excluded ref. Each reason is "Date given
  as ~8 Jul 2022 in the source sheet; article blocked (<barangay>)".

- [ ] **Step 4: Run** `<T> tests.test_hazard_data`. Expected: all PASS.

### Task 2: Terrain features per barangay

**Files:**
- Modify: `backend/apps/history/hazard_data.py`
- Create: `backend/apps/history/management/commands/build_hazard_features.py`
- Test: `backend/tests/test_hazard_data.py`

**Interfaces:**
- Consumes: `susceptibility.city_grid(extent, zoom=14, pad_m=500)`,
  `load_inputs(grid, bbox, log, cache_dir=...)`, `draw_polygons(grid, polygons)`,
  `compute_factors(grid, dem, osm, city_mask, log)`.
- Produces:
  - `terrain_shares(labels: np.ndarray, factors: dict[str, np.ndarray], barangay_ids) -> dict[int, dict[str, float]]`:
    all 11 features, plus `cells`
  - `write_terrain(path, rows: dict[int, dict], names: dict[int, str])`
  - `read_terrain(path=DATA_DIR / 'barangay_terrain.csv') -> dict[int, dict[str, float]]`
  - The CSV has columns `barangay_id, barangay, cells`, then the 11 features in Global
    Constraints order (flood, then landslide).

- [ ] **Step 1: Write the failing tests**

```python
def test_terrain_shares_on_a_toy_grid(self):
    labels = np.array([[1, 1, 2, 2], [1, 1, 2, 0]])
    f = {k: np.zeros((2, 4)) for k in ('hand', 'elevation', 'dist_water', 'dist_coast',
                                       'building_density', 'slope', 'relief', 'dist_road')}
    f['hand'][:] = [[1, 3, 6, 1], [1, 1, 9, 0]]
    f['slope'][:] = [[20, 35, 0, 19], [0, 0, 40, 90]]
    f['building_density'][:] = [[4, 0, 10, 0], [0, 0, 20, 99]]
    rows = terrain_shares(labels, f, [1, 2])
    self.assertEqual(rows[1]['hand_lt2'], 0.75)       # 3 of 4 cells
    self.assertAlmostEqual(rows[2]['hand_lt2'], 1 / 3)  # label-0 cell ignored
    self.assertEqual(rows[1]['slope_gt18'], 0.5)
    self.assertEqual(rows[1]['slope_gt30'], 0.25)
    self.assertEqual(rows[2]['built_density'], 10.0)  # mean of 10, 0, 20
    self.assertEqual(rows[1]['cells'], 4)

def test_terrain_csv_round_trip(self): ...           # write_terrain then read_terrain gives the same floats
```

- [ ] **Step 2: Run** `<T> tests.test_hazard_data`. Expected: the 2 new tests FAIL.

- [ ] **Step 3: Implement** `terrain_shares`, `write_terrain` and `read_terrain`.

- [ ] **Step 4: Implement the `build_hazard_features` command.** Assemble the polygons and
  extent exactly as `build_hazard_index.handle` does. Use
  `cache_dir=Path(settings.BASE_DIR) / '.hazard_cache'` and `--refresh` like that
  command, `labels = draw_polygons(grid, polygons)` and `city_mask = labels > 0`. Write
  `DATA_DIR / 'barangay_terrain.csv'` and print one line per barangay.

- [ ] **Step 5: Run** `<T> tests.test_hazard_data`. Expected: PASS. Then
  `venv/Scripts/python.exe manage.py build_hazard_features`. Expected: 22 rows, each with
  `cells > 0`. Spot check: Manipis `slope_gt18` is well above Tabunok's.

### Task 3: Rain from Open-Meteo

**Files:**
- Create: `backend/apps/history/rain.py`
- Create: `backend/apps/history/management/commands/fetch_rain.py`
- Test: `backend/tests/test_rain.py`

**Interfaces:**
- Produces:
  - `representative_points() -> dict[int, tuple[float, float]]`: (lat, lon) of each
    boundary's `point_on_surface`
  - `download_archive(points, start: date, end: date, get=None, sleep=time.sleep, log=print) -> tuple[dict[int, dict[date, float | None]], dict[int, tuple[float, float]]]`:
    the rain, and the grid cell Open-Meteo served for each barangay
  - `@dataclass RainFile(rain, cells, first_day, last_day)`; `write_rain_csv(path, rain, cells)`;
    `read_rain_csv(path=DATA_DIR / 'rain_daily.csv') -> RainFile`
  - `complete_years(rf: RainFile) -> list[int]`
  - `recent_rain(cells, after: date, today: date, get=None) -> dict[int, dict[date, float]] | None`
  - `get(url, params) -> dict`: requests, timeout 60, User-Agent
    `GeoAlert-Talisay/1.0 (hazard model rain)`

- [ ] **Step 1: Write the failing tests.** Use a fake `get` that records its calls and
  returns Open-Meteo's multi-location list shape.

```python
def test_download_sends_at_most_100_points_and_waits_13_s(self):   # 150 points → 2 requests per year span; sleep called with 13
def test_download_drops_years_with_no_values_and_logs_the_first_day(self):  # all-None 2016-2019 → first_day 2020-12-18 logged
def test_download_fails_when_the_archive_starts_after_2020_12_18(self):     # raises CommandError
def test_cells_are_the_grid_points_open_meteo_served(self):        # response latitude/longitude, not the asked point
def test_complete_years_need_every_day_and_13_days_before(self):   # 2021 complete only if 2020-12-19..2020-12-31 present
def test_recent_rain_asks_once_per_cell_for_days_after_the_file(self):
    # 3 barangays, 2 distinct cells → 1 request with 2 points; past_days == 10 for after=today-10
    # result keeps only after < d < today, and each barangay maps to its cell's series
def test_recent_rain_caps_past_days_at_92(self):
def test_recent_rain_failure_is_cached_15_minutes(self):
    # get raises → returns None; a second call within 15 min makes no request; after cache.clear it retries
```

- [ ] **Step 2: Run** `<T> tests.test_rain`. Expected: FAIL.

- [ ] **Step 3: Implement `rain.py`.**
  - Archive URL: `https://archive-api.open-meteo.com/v1/archive`.
  - Live URL: `https://api.open-meteo.com/v1/forecast`, with `forecast_days=1`. Drop
    today and future days.
  - `download_archive` tries from `date(2016, 12, 18)`, one request per calendar year per
    chunk of 100 points, with `sleep(13)` between requests.
  - Cache keys: `hazard-rain-recent:<sha1 of cells, after, today>`. Live result 3 h;
    failure (`None`) 15 min.

- [ ] **Step 4: Implement the `fetch_rain` command.** It downloads to `today − 1` and
  writes `DATA_DIR / 'rain_daily.csv'` (columns `barangay_id, cell_lat, cell_lon, date, mm`;
  blank mm = missing). It prints the first day, the last day and the distinct cells.

- [ ] **Step 5: Run** `<T> tests.test_rain`. Expected: PASS. Then
  `venv/Scripts/python.exe manage.py fetch_rain`. Expected: it finishes; the first day is
  ≤ 2020-12-18 and the last day is yesterday.

### Task 4: The barangay-day dataset

**Files:**
- Modify: `backend/apps/history/hazard_data.py`
- Create: `backend/tests/hazard_fixtures.py`
- Test: `backend/tests/test_hazard_data.py`

**Interfaces:**
- Produces:
  - `@dataclass Dataset(X: np.ndarray, y: np.ndarray, barangay_id: np.ndarray, day: np.ndarray, features: tuple[str, ...])`,
    where `day` is `datetime64[D]`. `Dataset.subset(mask) -> Dataset` and
    `Dataset.years -> np.ndarray`.
  - `build_dataset(hazard, terrain, rain, pos: set[tuple[int, date]], start, end) -> tuple[Dataset, int]`:
    the dataset and the number of rows dropped for missing rain
  - `records_signature(records, start, end) -> str`: sha1 over sorted
    `(source_ref, barangay_id, day)` of the non-sample records in the period
  - `tests/hazard_fixtures.py`:
    `toy_inputs(n_barangays=3, start=date(2021,1,1), end=date(2025,12,31), seed=0) -> (terrain, rain, pos)`:
    rain that is heavy on a few known days, with positives on some of those days.
    Task 9 adds `write_toy_files` to the same file.

- [ ] **Step 1: Write the failing tests**

```python
def test_rows_features_and_targets(self):
    terrain, rain, pos = toy_inputs(n_barangays=2, start=date(2024,1,1), end=date(2024,1,10))
    ds, dropped = build_dataset('Flood', terrain, rain, pos, date(2024,1,1), date(2024,1,10))
    self.assertEqual(ds.features, RAIN_FEATURES + TERRAIN_FEATURES['Flood'])
    self.assertEqual(len(ds.y) + dropped, 20)
    self.assertEqual(int(ds.y.sum()), len({p for p in pos if date(2024,1,1) <= p[1] <= date(2024,1,10)}))

def test_barangay_missing_from_terrain_or_rain_is_left_out(self):
def test_signature_changes_with_study_records_only(self):
def test_signature_ignores_records_after_study_end(self):   # Review Focus 1: adding a 2026-02-01 record keeps the signature
```

- [ ] **Step 2: Run** `<T> tests.test_hazard_data`. Expected: the new tests FAIL.

- [ ] **Step 3: Implement** `Dataset`, `build_dataset`, `records_signature` and the
  fixtures.

- [ ] **Step 4: Run** `<T> tests.test_hazard_data`. Expected: PASS.

### Task 5: Candidates, folds, benchmark and metrics

**Files:**
- Create: `backend/apps/history/hazard_models.py`
- Modify: `backend/requirements/base.txt`: add `xgboost-cpu==3.2.0` under the
  "likelihood model" block; then
  `venv/Scripts/python.exe -m pip install xgboost-cpu==3.2.0`
- Test: `backend/tests/test_hazard_models.py`

**Interfaces:**
- Consumes: `Dataset` (Task 4).
- Produces:
  - `CANDIDATES`, `FOLDS = [((2021, 2022), 2023), ((2021, 2022, 2023), 2024), ((2021, 2022, 2023, 2024), 2025)]`,
    `MONOTONE: dict[str, dict[str, int]]`, `PRIOR_DAYS = 30`, `ALARM_RATE = 0.01`
  - `SPEED_OVERRIDES: dict[str, dict] = {}`: merged into a model's settings by
    `make_pipeline`. Empty in production; tests patch it to shrink the tree models for
    speed.
  - `make_pipeline(name: str, hazard: str) -> sklearn.pipeline.Pipeline`
  - `benchmark_probs(train: Dataset, test: Dataset) -> np.ndarray`
  - `no_skill(train: Dataset) -> float`
  - `scores(y, p) -> dict`, with keys `log_loss, brier, roc_auc, pr_auc, n, positives, prevalence`.
    `roc_auc` and `pr_auc` are None without both classes. Probabilities are clipped to
    [1e-6, 1 − 1e-6] for log loss.
  - `threshold_metrics(p_train, y_test, p_test, rate=ALARM_RATE) -> dict`, with keys
    `cutoff, tp, fp, fn, tn, precision, recall`. Precision and recall are None when
    undefined.

- [ ] **Step 1: Write the failing tests**

```python
def test_fixed_settings_are_used_exactly(self):
    lr = make_pipeline('logistic_regression', 'Flood')[-1]
    self.assertEqual((lr.C, lr.penalty, lr.solver, lr.max_iter), (1.0, 'l2', 'lbfgs', 2000))
    rf = make_pipeline('random_forest', 'Flood')[-1]
    self.assertEqual((rf.n_estimators, rf.max_depth, rf.min_samples_leaf, rf.max_features, rf.random_state),
                     (500, 3, 200, 'sqrt', 0))
    self.assertEqual(list(rf.monotonic_cst), [1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 1])
    xgb = make_pipeline('xgboost', 'Landslide')[-1].get_params()
    for k, v in dict(n_estimators=200, max_depth=2, learning_rate=0.05, subsample=0.8, reg_lambda=1,
                     min_child_weight=0.1, scale_pos_weight=1, random_state=0).items():
        self.assertEqual(xgb[k], v)
    self.assertEqual(tuple(xgb['monotone_constraints']), (1,) * 10)

def test_folds_never_train_on_their_test_year_or_later(self):
    for train, test in FOLDS: self.assertTrue(max(train) < test)

def test_benchmark_reads_training_years_only(self):
    # train 2021-2022, barangay 1 has 1 January event; π = train prevalence
    # expect p for barangay 1 on a January test day == (1 + π*30) / (62 + 30)
    # adding test-year positives leaves benchmark_probs unchanged

def test_scores_are_undefined_without_events(self):
    s = scores(np.zeros(50, bool), np.full(50, 0.01))
    self.assertIsNone(s['roc_auc']); self.assertIsNone(s['pr_auc']); self.assertTrue(np.isfinite(s['log_loss']))

def test_threshold_is_set_on_training_predictions(self):   # cutoff = 99th percentile of p_train; counts on test
```

- [ ] **Step 2: Run** `<T> tests.test_hazard_models`. Expected: FAIL.

- [ ] **Step 3: Implement.** For logistic regression, a `ColumnTransformer` applies
  `np.log1p` to the first 5 columns (rain), then `StandardScaler`. Monotonic vectors follow
  the `ds.features` order.

- [ ] **Step 4: Run** `<T> tests.test_hazard_models`. Expected: PASS.

### Task 6: Calibration, bootstrap and selection

**Files:**
- Modify: `backend/apps/history/hazard_models.py`
- Test: `backend/tests/test_hazard_models.py`

**Interfaces:**
- Produces:
  - `@dataclass Fitted(name, pipeline, platt: tuple[float, float] | None)`
  - `fit_candidate(name, hazard, train: Dataset) -> Fitted`: the Platt rule in Global
    Constraints
  - `predict(f: Fitted, X) -> np.ndarray`
  - `day_blocks(days: np.ndarray, block=7) -> list[np.ndarray]`: row indices per block of
    7 consecutive days within one year
  - `bootstrap(days, y, preds: dict[str, np.ndarray], reps=1000, seed=0) -> dict`:
    `{'intervals': {name: {metric: (lo, hi)}}, 'diff': {(a, b): (lo, hi)}}`. The metrics
    are log_loss, brier and pr_auc; `diff` is the log loss of a minus b.
  - `select_winner(mean_log_loss: dict[str, float], diff: dict) -> str`
  - `calibration(y, p, years) -> dict`:
    `{'per_year': [{'year', 'observed', 'expected'}], 'slope', 'slope_ci'}`

- [ ] **Step 1: Write the failing tests**

```python
def test_platt_is_skipped_when_the_calibration_year_has_no_events(self):   # rf, last train year 0 events → platt None
def test_platt_is_fitted_for_trees_only(self):        # rf with events in last year → platt set; lr → always None
def test_tie_rule_prefers_the_simpler_model(self):
    means = {'logistic_regression': 0.0105, 'random_forest': 0.0100, 'xgboost': 0.0110}
    self.assertEqual(select_winner(means, {('logistic_regression', 'random_forest'): (-0.0002, 0.0012)}),
                     'logistic_regression')
    self.assertEqual(select_winner(means, {('logistic_regression', 'random_forest'): (0.0001, 0.0009)}),
                     'random_forest')
def test_blocks_are_7_days_and_never_cross_a_year(self):
def test_calibration_compares_observed_and_expected_per_year(self):  # expected == sum of p per year
```

- [ ] **Step 2: Run** `<T> tests.test_hazard_models`. Expected: the new tests FAIL.

- [ ] **Step 3: Implement.** Platt is fitted as `LogisticRegression(C=1e6)` on
  `logit(p_base)`. The calibration slope is the coefficient of the same fit on the test
  predictions, and its interval comes from `bootstrap`.

- [ ] **Step 4: Run** `<T> tests.test_hazard_models`. Expected: PASS.

### Task 7: Rain scenarios and period chances (pure)

**Files:**
- Create: `backend/apps/history/hazard_forecast.py`
- Test: `backend/tests/test_hazard_forecast.py`

**Interfaces:**
- Produces:
  - `period_dates(month: int, day: int | None, base_year: int) -> list[date]`: the month,
    or date ± `forecast.DAY_WINDOW`, placed in `base_year`. It may run into the
    neighbouring year.
  - `shift_dates(dates: list[date], base_year: int, s: int) -> list[date]`: each date
    keeps its offset in years from `base_year`; the day is clamped to the month's length
    (29 Feb → 28).
  - `scenario_dates(month, day, year: int | None, complete: list[int]) -> dict[int, list[date]]`:
    - Month view (`year` None): every complete s, using `period_dates(month, None, s)`.
    - Otherwise: s < year, with `shift_dates(period_dates(month, day, year), year, s)`.
    - Drops s when any date falls in a year that isn't complete.
  - `@dataclass PeriodChance(probability: float, expected: float, low: float, high: float, years: list[int])`
  - `period_chance(p_of: Callable[[date], float | None], dates_by_s) -> PeriodChance | None`:
    skips scenarios with a None day, and returns None when none are left
  - `pair_chance(pf_of, pl_of, dates_by_s) -> PeriodChance | None`: the flood × landslide
    product, per day, inside each scenario
  - `any_chance(parts: list[float]) -> float`: `1 − Π(1 − p)`

- [ ] **Step 1: Write the failing tests**

```python
def test_period_chance_is_the_mean_of_one_minus_the_product(self):
    dates = {2021: [date(2021,3,1), date(2021,3,2)], 2022: [date(2022,3,1), date(2022,3,2)]}
    pc = period_chance(lambda d: 0.1 if d.year == 2021 else 0.0, dates)
    self.assertAlmostEqual(pc.probability, 0.095); self.assertAlmostEqual(pc.expected, 0.1)
    self.assertEqual((pc.low, round(pc.high, 2), pc.years), (0.0, 0.19, [2021, 2022]))
def test_scenario_years_are_strictly_before_the_year(self):   # year 2024, complete 2021-2025 → {2021, 2022, 2023}
def test_feb_29_becomes_feb_28_in_a_non_leap_year(self):
def test_month_view_uses_each_scenario_years_own_month(self):  # Feb in 2024 has 29 days
def test_week_is_the_date_plus_minus_3_days(self):
def test_week_crossing_new_year_needs_next_year_rain(self):    # Review Focus 3
    got = scenario_dates(12, 30, 2026, complete=[2021, 2022, 2023, 2024, 2025])
    self.assertEqual(sorted(got), [2021, 2022, 2023, 2024])   # 2025 needs 2026 rain
    self.assertEqual(got[2024][-1], date(2025, 1, 2))
def test_pair_chance_combines_inside_each_scenario(self):
    dates = {2021: [date(2021,8,1)], 2022: [date(2022,8,1)]}
    pc = pair_chance(lambda d: 0.5 if d.year == 2021 else 0.0, lambda d: 0.5 if d.year == 2021 else 0.0, dates)
    self.assertAlmostEqual(pc.probability, 0.375)               # not 1 - 0.75*0.75 = 0.4375
def test_any_chance(self): self.assertAlmostEqual(any_chance([0.2, 0.375]), 0.5)
```

- [ ] **Step 2: Run** `<T> tests.test_hazard_forecast`. Expected: FAIL.

- [ ] **Step 3: Implement** the functions above.

- [ ] **Step 4: Run** `<T> tests.test_hazard_forecast`. Expected: PASS.

### Task 8: The test report (`test_hazard_models`)

**Files:**
- Modify: `backend/apps/history/hazard_models.py`
- Create: `backend/apps/history/management/commands/test_hazard_models.py`
- Test: `backend/tests/test_hazard_models.py`

**Interfaces:**
- Consumes: Tasks 1–7.
- Produces:
  - `evaluate_hazard(hazard, ds: Dataset, rain: RainFile, terrain, records, sensitivity_ds: Dataset | None) -> dict`
  - `REPORT_PATH = DATA_DIR / 'hazard_model_report.json'`
  - `read_report(path=REPORT_PATH) -> dict | None`
- **Report shape**, top level: `{generated, study: {start, end}, files: {rain_sha1, terrain_sha1}, hazards: {Flood: {...}, Landslide: {...}}}`.
- **Per hazard:** `rows, positives, prevalence, positive_days, winner, calibrated_all_folds,
  candidates, benchmark, no_skill, beats_benchmark, threshold, calibration, timing_auc,
  place_auc, lobo_auc, camp_iv, sensitivity, by_type, monthly_levels, monthly_brier,
  scenario_years_by_fold, data_signature, limits, excluded`.
  - `candidates` maps each name to
    `{mean_log_loss, pooled: {log_loss, brier, roc_auc, pr_auc}, intervals, per_year: [{year, positives, expected, log_loss, brier, roc_auc, pr_auc}], calibrated: [bool per fold]}`.
  - `beats_benchmark` = the winner's mean log loss is below the benchmark's, and the
    interval of (winner − benchmark) is entirely below 0.
  - `camp_iv` and `sensitivity` are null where they don't apply.

**What each check does:**
- **`monthly_levels`** (4.2): each barangay-month of each test year gets
  `period_chance(...)` from the fold's model over scenario years before the test year. It
  is then grouped by `level_for` into `{level, rows, chance, happened, events}`, in the
  order High, Moderate, Low.
- **`monthly_brier`:** `{scenario, recorded_rain, benchmark}`.
- **`lobo_auc`:** the winner is trained on 21 barangays (2021–2025) and predicts the 22nd.
  The AUC compares each barangay's mean predicted chance with whether it ever had an
  event.
- **`camp_iv`** (landslide): the percentile rank of the 2025-08-25 Camp IV row among the
  fold-3 test rows.
- **`by_type`** (flood): test positives and their mean chance, per `subtype`.
- **`sensitivity`** (flood): the winner's pooled scores with no exclusions.

- [ ] **Step 1: Write the failing tests** (on `toy_inputs`; tree settings are patched down
  for speed with `mock.patch.dict` on a `SPEED_OVERRIDES` hook used only in tests)

```python
def test_report_has_every_field_the_card_reads(self):          # assertLessEqual(set(SPEC_KEYS), set(report))
def test_each_fold_is_scored_on_its_test_year_only(self):      # spy pipeline records fit years; never ≥ test year
def test_beats_benchmark_needs_the_whole_interval_below_zero(self):
def test_monthly_levels_use_scenario_years_before_the_test_year(self):
def test_command_writes_the_report_with_signatures(self):      # tmp DATA_DIR; files.rain_sha1 present; data_signature matches records_signature
```

- [ ] **Step 2: Run** `<T> tests.test_hazard_models`. Expected: the new tests FAIL.

- [ ] **Step 3: Implement** `evaluate_hazard` and the command (`--hazard Flood|Landslide`
  runs one). The command loads `load_records`, `load_exclusions`, `read_rain_csv` and
  `read_terrain`. It builds the main dataset over the study period and, for flood, the
  sensitivity dataset. It writes `REPORT_PATH` and prints each winner and
  `beats_benchmark`.

- [ ] **Step 4: Run** `<T> tests.test_hazard_models`. Expected: PASS.

### Task 9: The deployed model and forecast rows

**Files:**
- Modify: `backend/apps/history/hazard_forecast.py`
- Test: `backend/tests/test_hazard_forecast.py`

**Interfaces:**
- Consumes: `read_report`, `fit_candidate`, `predict`, `read_rain_csv`, `recent_rain`,
  `read_terrain`, `rain_windows`, `records_signature`, `model_forecast.level_for`.
- Produces:
  - `class Unavailable(Exception)`, raised with a plain-language reason
  - `@dataclass Deployed(hazard, model, daily: dict[int, dict[date, float]], reasons: dict[int, str], complete_years: list[int], rain: RainFile, terrain)`
  - `deployed(hazard: str) -> Deployed`:
    - refits the winner on the whole study period; Platt only when the report says
      `calibrated_all_folds`
    - predicts every barangay-day of the rain file with complete windows
    - caches under `hazard-model:<sha1>` for 6 h. The sha1 covers the report, rain and
      terrain sha1s and `records_signature` over the study period.
    - Lock: `cache.add('hazard-model-lock:<sha1>', 1, 300)` plus a module
      `threading.Lock`. A request that finds the lock held polls the cache every 0.5 s
      for up to 60 s, then raises `Unavailable('The model is being prepared; try again in a minute.')`.
  - `use_hazard_models(result: dict, *, month, day, year, hazards: list[str], barangay: int | None, places: list[dict], today: date) -> dict[str, dict]`:
    - mutates `result` per spec 2.3–2.6 and returns
      `{hazard: {'deployed': Deployed | None, 'chances': {barangay_id: PeriodChance}}}` for
      Task 10
    - `places` is `model_forecast.places()`
    - rows follow spec 2.5; their level comes from the month's `period_chance`
    - `recorded_rain_probability` is present when year Y has recorded days in the period
      (the file plus `recent_rain`)
    - `in_training` is set when `STUDY_START <= the period start <= STUDY_END`
    - unavailable rows: `method: 'unavailable', probability: None, expected_events: None, level: 'None', reason`
  - `warm_in_background() -> bool`: starts a daemon thread that calls `deployed()` for
    both hazards when either cache key is missing and no lock is held. It returns whether
    a thread started.

- [ ] **Step 0: Add the fixture** to `tests/hazard_fixtures.py`:
  `write_toy_files(dirpath, barangay_ids, winner='logistic_regression')`. It writes the
  four data files built from `toy_inputs`, plus a minimal report in Task 8's shape: winner
  set, `calibrated_all_folds: false`, a `data_signature`, and the `files` sha1s.

- [ ] **Step 1: Write the failing tests.** `TestCase`, three barangays with boundaries,
  `write_toy_files(tmp, ids)`, with `hazard_data.DATA_DIR` and `REPORT_PATH` patched to
  `tmp` and `cache.clear()` in `setUp`.

```python
def test_every_barangay_gets_a_row_per_modelled_hazard(self):
def test_rows_carry_the_model_its_chance_range_and_rain_years(self):
def test_level_comes_from_the_months_chance_in_the_week_view(self):
def test_recorded_rain_probability_only_when_the_period_has_recorded_days(self):
def test_in_training_marks_periods_inside_the_study(self):
def test_missing_report_gives_unavailable_rows_not_counting(self):   # probability None, method 'unavailable', reason set
def test_barangay_without_terrain_is_unavailable_alone(self):        # Review Focus 2
def test_no_rain_year_before_period_is_unavailable(self):             # Review Focus 4: month 1, year 2021
    # reason == 'no rain years before this period'
def test_record_after_study_end_keeps_fit(self):                      # Review Focus 1: same cache key, same chances
def test_only_one_fit_when_two_requests_find_the_cache_empty(self):   # 2 threads, fit_candidate mocked with a 0.5 s sleep → called once per hazard
def test_warm_in_background_starts_only_when_cold(self):
```

- [ ] **Step 2: Run** `<T> tests.test_hazard_forecast`. Expected: the new tests FAIL.

- [ ] **Step 3: Implement** the Interfaces above. The 12-month profile for one flood or
  landslide hazard is `period_chance` per month: the barangay's own chances, or the mean
  over barangays. It is written to `result['profile']` with `profile_method = 'model'`.

- [ ] **Step 4: Run** `<T> tests.test_hazard_forecast tests.test_model_forecast tests.test_forecast`.
  Expected: all PASS (fire unchanged).

### Task 10: The API: filter, combined chance, headers, accuracy, warm-up

**Files:**
- Modify: `backend/apps/history/views.py`
  - `HistoricalForecastView`: its docstring and `get`
  - `ForecastAccuracyView.get`
- Modify: `backend/apps/history/hazard_forecast.py` (`combine`)
- Modify: `backend/apps/history/hazard_models.py` (`accuracy_entries`)
- Modify: `backend/apps/hazards/views.py`: `HazardZoneListView.get` calls
  `warm_in_background()` inside `try/except` + `logger.exception`, right after
  `release_overdue_quietly()`
- Test: `backend/tests/test_forecast_combined.py`

**Interfaces:**
- Consumes: Task 9's return value. Fire's monthly table is read with
  `model_forecast._fitted('Fire', fire_events, until, today)['table']` (read only).
  `chance(rate)` gives the month; the week is `rate × 7 / days_in_month`, as fire's
  `apply_table` does.
- Produces:
  - `parse_hazards(params, valid: list[str]) -> list[str]`: splits on commas, trims,
    matches case-insensitively and removes duplicates, in the order Fire, Flood,
    Landslide. It raises `ValueError(message)` for both parameters given, or for an unknown
    name (the message lists the valid names).
  - `combine(result, scen: dict, fire_table: dict | None, included: list[str], month, day, year, barangay, places, today) -> None`:
    - fills `combined` and `by_barangay` (spec 3.3 shape) and `hazards_included`
    - filters `results` to the included hazards
    - sets `profile` to the combined chance per month when more than one hazard is
      included
    - uses `pair_chance` for flood and landslide when both are included, then `any_chance`
      with fire
    - a hazard whose row is not a model row goes into `missing`, and is left out
  - `accuracy_entries(today) -> list[dict]`: flood and landslide entries from
    `read_report()`, with `kind: 'rain_terrain'`, `status` (spec 4.1) and
    `stale = records_signature(...) != report.data_signature`
  - View responses: both endpoints set `Cache-Control: public, max-age=600`.
    `ForecastAccuracyView` returns `{'hazards': [fire report] + accuracy_entries(today), 'combined_note': 'Built from the three tested models; not tested on its own.'}`.

- [ ] **Step 1: Write the failing tests**

```python
def test_combined_chance_matches_the_rule_for_one_barangay(self):
    # row values: fire 0.2; flood and landslide per-scenario as in Task 7 → combined == 0.5
def test_hazards_param_limits_rows_and_the_combined_chance(self):   # ?hazards=Fire,Flood → no Landslide rows; hazards_included == ['Fire', 'Flood']
def test_hazards_param_ignores_case_spaces_and_duplicates(self):    # 'fire, Flood,flood' → ['Fire', 'Flood']
def test_both_parameters_is_a_400(self):
def test_unknown_hazard_is_a_400_listing_the_valid_names(self):
def test_by_barangay_keeps_its_shape_and_follows_combined(self):
def test_unavailable_hazard_is_named_in_missing(self):
def test_profile_is_combined_for_several_and_single_for_one(self):
def test_both_endpoints_send_cache_control(self):                   # response['Cache-Control'] == 'public, max-age=600'
def test_forecast_answers_when_live_rain_fails(self):               # Review Focus 5: get raises → 200, no recorded_rain_probability
def test_accuracy_status_in_use_not_better_unavailable_and_stale(self):
def test_fire_rows_are_unchanged(self):     # fire rows equal those from seasonal_forecast + model_forecast.use_models alone
def test_hazard_list_ping_warms_the_models(self):                   # warm_in_background mocked, called once by GET /api/hazards/
```

- [ ] **Step 2: Run** `<T> tests.test_forecast_combined`. Expected: FAIL.

- [ ] **Step 3: Implement.**
  - The view counts with `events` filtered to the included hazards.
  - It calls `model_forecast.use_models(... hazard=included[0] if len(included) == 1 else None ...)`.
  - Then `scen = hazard_forecast.use_hazard_models(...)`, then
    `hazard_forecast.combine(...)`. Each step sits in its own `try` that logs and marks
    the hazard unavailable.

- [ ] **Step 4: Run**
  `<T> tests.test_forecast_combined tests.test_hazard_forecast tests.test_model_forecast tests.test_forecast tests.test_hazard_index`.
  Expected: all PASS.

### Task 11: Frontend helpers and the likelihood card

**Files:**
- Modify: `frontend/src/components/Forecast/forecastLevels.js`
- Modify: `frontend/src/components/Forecast/BarangayLikelihood.jsx`
- Modify: `frontend/src/api/historyApi.js` (comments only)
- Test: `frontend/src/components/Forecast/forecastLevels.test.js` (create)
- Test: `frontend/src/components/Forecast/forecastFilters.test.js`

**Interfaces:**
- Produces, in `forecastLevels.js`:
  - `hazardsParam(types: Iterable<string>) => string`: sorted as Fire, Flood, Landslide,
    joined with ","
  - `combinedText(row) => string`, e.g. `"Fire 8% · Flood 3% · Landslide 30%"`
  - `rangeText(row) => string`, e.g. `"3–41% across past rain years"`
  - `levelLabel(row) => string`: "Unavailable right now" for `method === 'unavailable'`,
    otherwise `likelihoodInfo(row.level).label`
  - `RAIN_ATTRIBUTION = { text, links: [{label, href}] }` (the exact copy in Global
    Constraints)
  - `FORECAST_DISCLAIMER` (the exact new copy)
  - `periodPastHeader(p)` now returns `On record in past ${Month}s`, or for a date
    `On record in past years, week of Nov 15`
  - `IN_TRAINING_NOTE` (the exact copy)

- [ ] **Step 1: Write the failing tests**

```js
test('hazardsParam orders and joins', () => expect(hazardsParam(new Set(['Landslide', 'Fire']))).toBe('Fire,Landslide'));
test('combinedText lists each hazard with its chance', () =>
  expect(combinedText({ hazards: [{ hazard_type: 'Fire', probability: 0.08 }, { hazard_type: 'Flood', probability: 0.031 },
    { hazard_type: 'Landslide', probability: 0.3 }] })).toBe('Fire 8% · Flood 3% · Landslide 30%'));
test('rangeText', () => expect(rangeText({ range: [0.03, 0.41] })).toBe('3–41% across past rain years'));
test('an unavailable row says so instead of None on record', () =>
  expect(levelLabel({ method: 'unavailable', level: 'None' })).toBe('Unavailable right now'));
// forecastFilters.test.js
test('all hazard types shows the combined table with each hazard', ...);  // headers: Barangay, All hazards, Chance, Biggest share, Each hazard
test('one hazard shows its range, rain so far and the in-training note', ...);
test('the rain attribution sits under the card with both links', ...);
test('the dashboard card shows the top 5 combined rows', ...);
```

- [ ] **Step 2: Run** `<F> forecastLevels forecastFilters`. Expected: the new tests FAIL.

- [ ] **Step 3: Implement.**
  - **All hazards:** when `hazard === ''`, render the table from `data.combined`.
  - **One hazard:** the per-hazard table shows Chance on every model row, `rangeText` as a
    second line in that cell, "With rain so far: N%" when `recorded_rain_probability` is
    present, and `IN_TRAINING_NOTE` above the table when any row has `in_training`.
  - **"How this is calculated":** rewrite it as spec 3.4. Fire's paragraph keeps its
    content; then flood and landslide, naming `rows[0].model`; then the combined chance;
    then the cut-offs. Drop the counting paragraph.
  - **Attribution:** render `RAIN_ATTRIBUTION` under the card whenever any flood or
    landslide model row is shown.
  - Existing tests that assert the old counting text are updated to the new copy.

- [ ] **Step 4: Run** `<F> forecastLevels forecastFilters forecastPeriods analyticsPanel`.
  Expected: PASS.

### Task 12: The public map's Likely view and the outlook title

**Files:**
- Modify: `frontend/src/pages/PublicMap.jsx` (the likely fetch around line 628; the style
  and popup around 640–810; the legend around 1011)
- Modify: `frontend/src/components/Forecast/SeasonalOutlook.jsx`
- Modify: `frontend/src/components/Forecast/forecastLevels.js`
- Test: `frontend/src/components/Forecast/forecastLevels.test.js`
- Test: `frontend/src/components/Forecast/forecastFilters.test.js`

**Interfaces:**
- Produces: `combinedByBarangay(likely) => Map<string, combinedRow>` in `forecastLevels.js`,
  keyed by `String(barangay_id)`.

- [ ] **Step 1: Write the failing tests**

```js
test('combinedByBarangay keys combined rows by barangay id', ...);
test('the outlook is titled as history, not prediction', ...);   // 'Seasons on record' + the exact sub line
```

- [ ] **Step 2: Run** `<F> forecastLevels forecastFilters`. Expected: the new tests FAIL.

- [ ] **Step 3: Implement.**
  - **Fetch:** `historyApi.forecast({ ...periodParams(likelyPeriod), hazards: hazardsParam(activeTypes) })`,
    refetched when `activeTypes` changes. Nothing is fetched when `activeTypes.size === 0`.
  - **Colour:** each barangay's fill comes from `combinedByBarangay(likely)`.
  - **Popup:** first line
    `All shown hazards: <level>, about <N>% (<combinedText>)`, then the existing
    per-hazard lines.
  - **Legend:** the title is
    `Likely in <period>: chance of any of <layerName lowercased>`. The note names
    `rain_years` for flood and landslide. `RAIN_ATTRIBUTION` is shown as links.
  - **SeasonalOutlook:** the title and sub line become the exact copy.

- [ ] **Step 4: Run** `<F> forecastLevels forecastFilters`. Expected: PASS. Then
  `CI=true npx react-scripts test --watchAll=false`. Expected: the whole frontend suite
  passes; save the output to a file.

### Task 13: The accuracy card for rain-and-terrain models

**Files:**
- Modify: `frontend/src/components/Forecast/ForecastAccuracy.jsx`
- Test: `frontend/src/components/Forecast/forecastAccuracy.test.js`

**Interfaces:**
- Consumes: the `accuracy_entries` shape (Task 10). The model labels are
  `{logistic_regression: 'logistic regression', random_forest: 'random forest', xgboost: 'XGBoost'}`.

- [ ] **Step 1: Write the failing tests**

```js
test('a rain and terrain model names itself and its test years', ...);
// 'Flood: rain and terrain model (logistic regression), in use'
// 'Tested on 2023, 2024 and 2025, each year trained only on the years before it'
test('not beating counting is said plainly but the model stays', ...);
// heading ends ' — did not beat counting on the years it never saw'
test('undefined metrics show as a dash with a footnote', ...);
test('a stale report asks for the test to be run again', ...);
test('the card shows the new sub line, the combined note and the attribution', ...);
test('the fire block is unchanged', ...);                     // the existing fire tests keep passing
```

- [ ] **Step 2: Run** `<F> forecastAccuracy`. Expected: the new tests FAIL.

- [ ] **Step 3: Implement `RainTerrainAccuracy`,** chosen when `report.kind === 'rain_terrain'`:
  - Table 1: candidates, then the benchmark and no-skill rows, with the winner marked.
  - Table 2: per test year.
  - Table 3: `monthly_levels`.
  - Robustness lines: `lobo_auc`, `camp_iv`, `timing_auc` and `place_auc`, `sensitivity`.
  - The `limits` list.
  - Tables are wrapped in `fc-table-wrap`.

  Add `in_use_not_better` and `unavailable` to `VERDICT`. Replace the sub line with the
  exact copy, and show `combined_note`.

- [ ] **Step 4: Run** `<F> forecastAccuracy`. Expected: PASS.

### Task 14: Real data, README and verification

**Files:**
- Create (generated): `backend/apps/history/data/barangay_terrain.csv`, `rain_daily.csv`,
  `hazard_model_report.json`
- Modify: `README.md` (a new "Hazard models" section next to "Alert jobs")

- [ ] **Step 1: Generate the data.** Run, in order:
  1. `manage.py fetch_rain`
  2. `manage.py build_hazard_features`
  3. `manage.py test_hazard_models > "C:/Users/Sannichigetsu/.geoalert-test/report-run.log" 2>&1`

  Expected: the report exists with both hazards, and `winner` is one of `CANDIDATES`.

- [ ] **Step 2: Read the report.**
  - Check `positives` (Flood 18 on 5 days; Landslide 8 on 8 days) and `excluded` (the 4
    refs).
  - Check that flood folds 2023 and 2024 show `roc_auc: null`.
  - Write the winner, `beats_benchmark` and the pooled scores into the session notes.
  - These are the only figures allowed in the thesis.

- [ ] **Step 3: Write the README section.** It covers the three commands, the yearly
  `fetch_rain`, and moving `STUDY_END` then rerunning after new records. It also has the
  Open-Meteo step: before go-live, email info@open-meteo.com for written confirmation of
  free use (spec 4.6), with the paid plan or ERA5 as the fallback.

- [ ] **Step 4: Run the full backend suite**
  `<T> tests` and save the log. Expected: every test passes, apart from failures that also
  happen on an untouched checkout. List those failures by name, with their log lines.

- [ ] **Step 5: Check one barangay by hand.** Call
  `GET /api/history/forecast/?month=11` for one barangay. Recompute
  `1 − (1 − fire)(1 − P_rain)` from its `combined.hazards` and `results`.
  `P_rain` is shown as `pair_chance` in a Django shell. Expected: it matches to 3
  decimals.

- [ ] **Step 6: Check the app.** Use the `run` skill to open:
  - Reports › Analytics with All hazard types and with each hazard
  - the public map's Likely view, with layers ticked and unticked
  - the DRRMO dashboard card
  - the accuracy card

  Confirm each against spec 3.4 and 4.3, including the attribution in all three places.
  Confirm that fire's rows and fire's accuracy block read exactly as before.
