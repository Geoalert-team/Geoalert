# Fire risk by purok (adapted Pittsburgh model) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Delete flood/landslide prediction and the Rain watch, then give "Likely by month" a per-purok
fire probability and Red/Orange/Green level from the City of Pittsburgh Bureau of Fire's fire-risk
model recipe, trained offline on GeoAlert's BFP fires.

**Architecture:** Offline commands build per-purok features from non-fire sources
(`build_fire_features`). They then train and choose among Pittsburgh's model families plus logistic
regression and a small neural network, and write a model file and a report (`train_fire_model`). The
website only reads those files (`fire_purok.py`): purok rows, barangay sums, the accuracy card and the
report-approval level. A new insert-only table logs each month's purok figures for honest scoring
later.

**Tech Stack:**
- Django 4.2 / DRF / PostGIS; scikit-learn 1.9.1; xgboost 3.2.0 (offline only); NumPy/SciPy.
- React (react-scripts, Jest) with Leaflet.

**Spec:** `docs/design/specs/2026-11-22-fire-purok-model-design.md`. Section 0 and Part A (section
12) override the rest. Background: `docs/research/2026-11-22-fire-purok-prediction-audit.md`.

## Global Constraints

- **Never `git commit`.** Every "commit" step is "Leave uncommitted" (the user's standing rule).
- **Nothing is dropped or deleted in the shared database.** The rainwatch tables, `hazard_prediction_log`
  and their rows stay. The only new migration (Task B6) is applied to the shared database only in
  Task B9, after a backup and the user's go-ahead.
- **No input may be derived from fire records.** Fire records are only the label `fire_occurred`
  (1/0), validation and baselines named `comparison_*`.
- **Model inputs are exactly** `FEATURE_COLUMNS` (4.2) + `month_sin`, `month_cos`. Area `kind`,
  container status and area size are never inputs.
- **Candidates:**
  - `logistic_regression`, `random_forest`, `adaboost`, `xgboost`, `neural_network`;
  - each of RF, AdaBoost and XGBoost includes Pittsburgh's exact settings: XGB lr 0.13 / 1500 trees /
    depth 3 / γ 0.5 / colsample 0.6 / min_child_weight 1; RF 500 / depth 10 / log2; AdaBoost 1000;
  - no resampling and no class weights.
- **Choice rule:** lowest leave-one-year-out log loss per family. The best family replaces
  `logistic_regression` only if its paired log-loss gain has a 95% barangay-bootstrap interval
  (1000 reps, seed 0) wholly below 0.
- **Levels:**
  - Orange cut-off = the highest p at which Orange + Red catch ≥ 80% of fires (leave-one-year-out);
  - Red = the lowest p at which the rows at or above it have ≥ 2× the city-average rate with ≥ 10
    fires; else nothing is Red, with a reason.
- **Barangay level** keeps the 15% / 25% monthly cut-offs (`High` / `Moderate` / `Low`).
  Barangay rate = Σ −ln(1 − p).
- **Limited data** = purok `confidence == 'low'` or 80% interval high > 3 × low.
- **Copy strings, verbatim:**
  - `"The fire model has not been trained yet."`
  - `"The purok map changed since the fire model was trained; rerun build_fire_features and train_fire_model."`
  - `"Only fire has a prediction model for now."`
  - `"Fire records start in January 2023."`
- **Credit** in the module docstrings and the report: "Adapted from the City of Pittsburgh Bureau of
  Fire / Carnegie Mellon Metro21 fire risk model (github.com/CityofPittsburgh/fire_risk_analysis, MIT
  License, © 2017 mmadaio)".
- **Tests run on a private test database:**
  - create `C:\Users\Sannichigetsu\.geoalert-test\geo_test_settings_fire.py`, copying
    `geo_test_settings.py` with `TEST NAME = "test_geoalert_fire_purok"` and the cache in
    `.geoalert-test/cache-fire`;
  - backend command (from `backend/`): `PYTHONPATH="C:/Users/Sannichigetsu/.geoalert-test" venv/Scripts/python.exe manage.py test <labels> --settings=geo_test_settings_fire --noinput`;
  - frontend command (from `frontend/`): `CI=true npm test -- --watchAll=false <path>`.

## Review Focus

1. **The purok map is reloaded after training** (ids kept, some added or removed). Fire goes
   unavailable with the stale copy and never shows another purok's figures. Covered by
   B5 `test_stale_outlines_make_fire_unavailable`.
2. **A purok added since training** (not in the model file) gets no fill and no row, never a guessed
   level. The report-approval level falls back to Orange. Covered by B5
   `test_unknown_purok_has_no_row` and `test_decide_falls_back_to_orange`.
3. **A week or date period** uses the week's chance but the month's level. Covered by B5
   `test_week_scales_chance_keeps_month_level`.
4. **The candidate test on all-zero or tiny folds:**
   - a year with no fires in a family's held-out fold must not crash or pick that family by NaN;
   - cut-offs with fewer than 10 fires above any p give "nothing is Red" with a reason.

   Covered by B2 `test_fold_without_fires_scores_finite` and B3 `test_red_empty_when_too_few_fires`.
5. **Old clients asking `?hazards=Flood`** (cached pages, the Analytics filter) get a clear 400, not a
   500. Covered by A2 `test_flood_is_a_400`.

---

## Part A: the clean-up

### Task A1: Remove the Rain watch (backend, job, tool)

**Files:**
- Delete:
  - `backend/apps/rainwatch/` (whole app);
  - `backend/tests/test_rainwatch_*.py`;
  - `backend/tests/fixtures/pagasa/`;
  - `tools/rain_forecast/`;
  - `.github/workflows/rain-forecast.yml`.
- Modify:
  - `backend/config/settings/base.py`: drop `'apps.rainwatch'` (line 39), `RAIN_WATCH_INGEST_TOKEN`,
    `PAGASA_FEED_WRITER` and their comments;
  - `backend/config/urls.py`: drop `api/rain-watch/`;
  - `backend/apps/hazards/views.py`: drop the PAGASA block in `get` (after line 143);
  - `.github/workflows/ci.yml`: drop the `tools/rain_forecast` step (line 65) and its setup lines;
  - `deploy/render.env.example`, `deploy/production.env.example`, `deploy/FREE_HOSTING.md`: drop the
    `RAIN_WATCH_INGEST_TOKEN` / `PAGASA_FEED_WRITER` lines.

- [ ] **Step 0:** Create `C:\Users\Sannichigetsu\.geoalert-test\geo_test_settings_fire.py` (Global Constraints). Then, before any change, run the full backend suite and the frontend suite once, and record the pass counts as the baseline.
- [ ] **Step 1:** Check nothing else imports it. `grep -rn "rainwatch\|RAIN_WATCH\|PAGASA_FEED" backend config tools deploy .github --include=*.py --include=*.yml --include=*.md --include=*.example` lists only the files above.
- [ ] **Step 2:** Make the deletions and edits above.
- [ ] **Step 3:** Run `venv/Scripts/python.exe manage.py check --settings=geo_test_settings_fire`. Expected: "System check identified no issues".
- [ ] **Step 4:** Run `venv/Scripts/python.exe manage.py makemigrations --check --dry-run --settings=geo_test_settings_fire`. Expected: "No changes detected". The rainwatch tables stay in the database untouched.
- [ ] **Step 5:** Leave uncommitted.

### Task A2: Remove flood/landslide prediction and the old fire model; forecast API becomes fire-only

**Files:**
- Delete from `backend/apps/history/`:
  - `hazard_forecast.py`, `hazard_models.py`, `hazard_tests.py`, `hazard_verdict.py`,
    `hazard_scoring.py`, `hazard_scenarios.py`, `two_part.py`, `firth.py`, `storms.py`,
    `landslide_catalogue.py`, `rain.py`, `exposure.py`, `model_forecast.py`, `fire_candidate.py`;
  - `management/commands/{test_hazard_models,fetch_rain,fetch_storms,build_hazard_features}.py`;
  - `data/{hazard_model_report.json,rain_daily.csv,storm_days.csv,storm_days.meta.json,barangay_terrain.csv,barangay_exposure.csv,hazard_model_exclusions.csv,landslide_catalogue_exclusions.csv}`;
  - `hazard_data.py`, after confirming nothing kept imports it.
- Delete tests: `backend/tests/{test_hazard_forecast,test_hazard_models,test_hazard_tests,test_hazard_verdict,test_hazard_scoring,test_hazard_scenarios,test_two_part,test_firth,test_storms,test_landslide_catalogue,test_rain,test_exposure,test_hazard_data,test_model_forecast,test_fire_candidate,test_forecast_combined,test_prediction_log}.py`, `hazard_fixtures.py`, `test_zz_tmp_output.py`.
- Modify:
  - `backend/apps/history/views.py`: rewrite `forecast_result` and `basis_method`, and simplify
    `HistoricalForecastView` and `ForecastAccuracyView`;
  - `backend/apps/history/prediction_log.py`: reduced to a stub `write_month_rows(today) -> int`
    returning 0 (Task B6 fills it);
  - `management/commands/log_hazard_predictions.py`: calls only `write_month_rows`;
  - `backend/apps/hazards/views.py`: drop the warm-up block (lines ~124–142) and `WARM_CHECK_*`;
  - `backend/apps/history/forecast.py`: docstring lines 34 and 270–271 stop naming deleted modules.
- Create: `backend/tests/test_forecast_api.py`.

**Interfaces:**
- Produces:
  - `views.forecast_result(*, month, day, year, barangay, years, exclude_samples, now) -> dict`. Same
    keys as today minus `combined` / `hazards_included` / rain fields. Fire rows are `unavailable`
    with `"The fire model has not been trained yet."` until Task B5 wires in `fire_purok`.
  - `views.FIRE_ONLY = "Only fire has a prediction model for now."`

- [ ] **Step 1: Write the failing tests** in `test_forecast_api.py`, against `/api/history/forecast/` with two barangays and one real fire:
  - `test_default_is_fire_only`: 200; every `results` row has `hazard_type == 'Fire'`; no `combined` key.
  - `test_flood_is_a_400`: `?hazards=Flood` and `?hazard_type_name=Landslide` give 400 with `error == "Only fire has a prediction model for now."`.
  - `test_fire_is_unavailable_before_training`: `?hazards=Fire` rows have `method == 'unavailable'` and `reason == "The fire model has not been trained yet."`.
  - `test_accuracy_has_fire_only`: `/api/history/forecast/accuracy/` gives 200 and `[h['hazard'] for h in hazards] == ['Fire']`, with `status == 'unavailable'`.
- [ ] **Step 2:** Run `... manage.py test tests.test_forecast_api ...`. Expected: FAIL. `combined` is present, and Flood is accepted.
- [ ] **Step 3:** Make the deletions; rewrite `forecast_result` and the views to the interfaces above. `parse_hazards` moves into `views.py`, accepting only `Fire`, any case. `mark_unavailable` / `mark_profile_unavailable` move into `views.py` as private helpers.
- [ ] **Step 4:** Run the new tests plus the whole backend suite. Expected: all pass. Delete or adjust any remaining test that imported a deleted module; `test_history_migrations` stays as it is.
- [ ] **Step 5:** `grep -rn "hazard_forecast\|model_forecast\|fire_candidate\|hazard_models\|two_part\|firth\|apps.history.rain\|history.exposure\|hazard_data" backend --include=*.py` finds nothing outside `migrations/`.
- [ ] **Step 6:** Leave uncommitted.

### Task A3: Frontend clean-up (Rain watch, flood/landslide forecast bits)

**Files:**
- Delete: `frontend/src/components/RainWatch/`, `frontend/src/api/rainWatchApi.js`.
- Modify:
  - `frontend/src/pages/PublicMap.jsx`:
    - drop the `next3` view, the rain state, the poll, the banner, the day picker and the legend;
    - drop `combinedRows` and the rain notes;
    - the likely request sends `hazards: 'Fire'` only;
    - with Fire unticked, the likely view shows the note "Only fire has a prediction for now.";
  - `frontend/src/pages/Dashboard/DRRMODashboard.jsx`: drop `RainWatchCard` (line 18 and 747);
  - `frontend/src/components/Forecast/forecastLevels.js`: drop `RAIN_ATTRIBUTION`,
    `combinedByBarangay`, `combinedText`, `combinedUnavailable`, `rainYearsText`,
    `FLOOD_LANDSLIDE_MONTHLY_NOTE` and the flood/landslide entries of `MODEL_LABELS`;
  - `frontend/src/components/Forecast/BarangayLikelihood.jsx`: drop `RAIN_HAZARDS` and the combined
    and rain branches;
  - `frontend/src/components/Forecast/ForecastAccuracy.jsx`: drop `RainTerrainAccuracy`,
    `EventTable`, `BaselineTable`, `OutsideTest`, `FireCandidate` and the `rain_terrain` branch;
  - `frontend/src/api/historyApi.js`: the comment on line 15.
- Tests: update `forecastLevels.test.js`, `forecastAccuracy.test.js` and `forecastFilters.test.js` to drop cases for removed exports.

- [ ] **Step 1:** Update the three test files: remove the cases for deleted exports, and add `test('likely view asks for fire only')` in `forecastFilters.test.js`, asserting that the params helper returns `{ hazards: 'Fire' }` for any ticked set.
- [ ] **Step 2:** Run `CI=true npm test -- --watchAll=false src/components/Forecast`. Expected: FAIL on the new case.
- [ ] **Step 3:** Make the deletions and edits.
- [ ] **Step 4:** Run `CI=true npm test -- --watchAll=false` and `npm run build`. Expected: all suites pass; the build compiles with no "not defined" or "unused import" errors.
- [ ] **Step 5:** Leave uncommitted.

---

## Part B: the fire model

### Task B1: Feature sources and feature math, with the no-counting guard

**Files:**
- Create:
  - `backend/apps/history/fire_sources.py` (downloads and caches only);
  - `backend/apps/history/fire_features.py` (pure functions + file I/O);
  - `backend/apps/history/management/commands/build_fire_features.py`.
- Modify: `backend/apps/history/data/ATTRIBUTION.md` (Microsoft footprints ODbL, OSM ODbL, ESA WorldCover 2021 v200 CC BY 4.0, WorldPop CC BY 4.0; drop the deleted NOAH / IBTrACS / GFS / PAGASA lines).
- Test: `backend/tests/test_fire_features.py`.

**Interfaces:**
- Produces in `fire_features.py`:
  - `DATA_DIR = Path(__file__).parent / 'data'`.
  - `FEATURES_FILE = DATA_DIR / 'fire_purok_features.csv'` and `FEATURES_META = DATA_DIR / 'fire_purok_features.meta.json'`.
  - `FEATURE_COLUMNS: tuple[str, ...]`: exactly `('buildings_in_area', 'building_density_per_ha', 'median_footprint_m2', 'median_gap_to_nearest_building_m', 'share_crowded_10m', 'road_density_m_per_ha', 'main_road_m', 'median_building_to_road_m', 'road_distance_to_fire_station_m', 'share_built_up', 'share_grass_shrub_bare', 'share_tree_cover', 'population', 'distance_to_coast_m', 'distance_to_river_m')`.
  - `LOG_COLUMNS = ('buildings_in_area', 'building_density_per_ha', 'population')`.
  - `ID_COLUMNS = ('purok_id', 'barangay_id', 'barangay', 'name', 'confidence', 'from_fire_log')`. `from_fire_log` is a report-only column.
  - `@dataclass FeatureTable(rows: list[dict], outlines_version: str, built_at: str, sources: dict)`.
  - `building_features(centres_m: ndarray[n,2], footprint_m2: ndarray[n], inside: ndarray[bool], area_ha: float) -> dict`: the 5 building columns. `share_crowded_10m` = share of inside buildings with ≥ 2 others within 10 m.
  - `road_features(road_pts_m, main_pts_m, inside_road, inside_main, centres_inside_m, area_ha) -> dict`: road points are spaced every 10 m along the segments.
  - `station_distances(road_lines_m: list[ndarray], stations_m: ndarray, origins_m: ndarray) -> ndarray`: the shortest path on the road graph (vertices snapped at 1e-7°), from each origin's nearest vertex to any station.
  - `landcover_shares(classes: ndarray[int]) -> dict`: WorldCover codes 50 → built-up; 20, 30, 60 → grass/shrub/bare; 10 → tree.
  - `fire_log_names(points_csv: Path) -> set[tuple[str, str]]`: (barangay, name) where `sources` contains "fire log".
  - `write_features(table, csv_path=FEATURES_FILE, meta_path=FEATURES_META)` and `read_features(csv_path=FEATURES_FILE, meta_path=FEATURES_META) -> FeatureTable`.
- Produces in `fire_sources.py`:
  - `footprints(cache_dir, bbox, refresh, log) -> tuple[ndarray[n,2] lng/lat, ndarray[n] area_m2]`: reads polygons from the Microsoft tile `132330002` (index URL as in `barangays/purok_estimate.BUILDINGS_INDEX`);
  - `worldcover(cache_dir, bbox, refresh, log) -> tuple[ndarray classes, (west, north, dx, dy)]`: `s3://esa-worldcover/v200/2021/map/ESA_WorldCover_10m_2021_v200_N09E123_Map.tif` over HTTPS, no sign-in;
  - `worldpop(cache_dir, bbox, refresh, log) -> tuple[ndarray, transform] | None`: `None`, logged, when no account-free URL works;
  - `osm(cache_dir) -> dict`: the cached `osm_z14_*.json` (roads, main_roads, waterways, coastline, fire_stations).

- [ ] **Step 1: Write the failing tests:**
  - `test_building_features_on_a_grid`: 9 buildings 8 m apart inside 1 ha give `buildings_in_area == 9`, `building_density_per_ha == 9`, `median_gap_to_nearest_building_m == 8`, `share_crowded_10m == 1.0` (each has ≥ 2 within 10 m).
  - `test_landcover_shares`: `[50, 50, 30, 10]` gives built-up 0.5, grass/shrub/bare 0.25, tree 0.25.
  - `test_station_distance_follows_roads`: an L-shaped road of 100 m + 100 m with the station at its end and the origin at the other end gives ≈ 200, not the straight-line 141.
  - `test_feature_file_round_trip`: write then read gives the same rows, columns and `outlines_version`.
  - `test_no_fire_records_in_features` (**the guard**): parse `fire_features.py`, `fire_sources.py` and `build_fire_features.py` with `ast`; none imports `apps.history.models`, `HistoricalRecord`, `apps.history.forecast` or `apps.history.bfp*`.
  - `test_columns_are_the_allowlist`: `FEATURE_COLUMNS` equals the tuple above, and `ID_COLUMNS` and `FEATURE_COLUMNS` are disjoint.
- [ ] **Step 2:** Run `... manage.py test tests.test_fire_features ...`. Expected: FAIL (module missing).
- [ ] **Step 3:** Implement both modules. Metre coordinates use the equirectangular approximation at 10.27° N, as the audit's probe did. Each area uses its full outline (`Purok.boundary`).
- [ ] **Step 4:** Implement `build_fire_features [--refresh]`:
  - for every `Purok`: point-in-outline with a bbox prefilter, then the features;
  - writes the CSV and the meta (`outlines_version = Purok.outlines_version()`, `sources`, `built_at`);
  - prints how many areas have 0 buildings.
- [ ] **Step 5:** Run the tests. Expected: PASS.
- [ ] **Step 6:** Leave uncommitted. Do **not** run the real command here; it runs in B9.

### Task B2: Labels, panel, candidates and the choice rule

**Files:**
- Create: `backend/apps/history/fire_training.py`.
- Test: `backend/tests/test_fire_training.py`.

**Interfaces:**
- Consumes: `FeatureTable`, `FEATURE_COLUMNS`, `LOG_COLUMNS` (B1).
- Produces:
  - `MONTH_COLUMNS = ('month_sin', 'month_cos')`.
  - `@dataclass FireRecord(when: datetime  # Manila local, purok_ids: list[int], barangay_id: int | None)`.
  - `fire_records() -> list[FireRecord]`: real fires only (`is_sample=False`, hazard type Fire), read as `views._forecast_events` reads months. **The only function here that reads fire records.**
  - `labels(fires, purok_ids, first: int, end: int) -> tuple[dict[tuple[int, int], int], list[FireRecord]]`: (area id, month index) → 1, and the unplaced fires. Month index = year × 12 + month − 1.
  - `@dataclass Panel(X: ndarray, y: ndarray, purok: ndarray, barangay: ndarray, month: ndarray, columns: list[str])`, and `build_panel(table, label_map, months: range) -> Panel`: `log1p` on `LOG_COLUMNS`, then the month waves (sin/cos of 2πm/12).
  - `CANDIDATES: dict[str, list[dict]]`: the grids of spec 4.4, each dict with a `label`. Pittsburgh's settings carry `label='pittsburgh'`.
  - `make_model(family: str, settings: dict, seed: int = 27)`: a fitted-ready estimator with `predict_proba`. LR and MLP sit in a `StandardScaler` pipeline; MLP is a `SeedAverage` over seeds 0–4.
  - `oof(panel, family, settings) -> ndarray`: leave one calendar year out over the panel's years.
  - `@dataclass Choice(family, settings, oof, candidates: list[dict], verdict: dict)`, and `choose(panel) -> Choice`: the rule from Global Constraints. `candidates` rows: `{family, label, log_loss, brier}`. `verdict`: `{adopted, mean, low, high, reasons}`.
  - `fit_platt(p, y) -> tuple[float, float]` and `apply_platt(p, a, b) -> ndarray` (logistic on logit(p)).
  - `@dataclass Fitted(family, settings, model, platt)`, `fit_final(panel, choice) -> Fitted`, and `Fitted.predict(X) -> ndarray`.

- [ ] **Step 1: Write the failing tests** (synthetic: 12 areas in 3 barangays, 36 months):
  - `test_labels_mark_each_linked_area_once`: a fire in two puroks marks both; two fires in one area-month still give 1; a fire with no purok is returned as unplaced.
  - `test_month_is_manila`: a fire at 2024-01-31T17:00Z falls in month index 2024 × 12 + 1 (February).
  - `test_panel_columns_are_allowlist_plus_months`: `panel.columns == list(FEATURE_COLUMNS) + ['month_sin', 'month_cos']`.
  - `test_oof_never_trains_on_its_own_year`: with a spy estimator, the fold for year Y saw no rows of Y.
  - `test_fold_without_fires_scores_finite`: one year with no fires gives finite `log_loss` and `brier` for every candidate.
  - `test_tie_keeps_logistic_regression`: on pure-noise labels, `choose(panel).family == 'logistic_regression'` and `verdict['adopted'] is False`.
  - `test_clear_signal_can_be_adopted`: when y depends on an interaction no linear model captures, `choose` adopts a tree family with `high < 0`.
  - `test_choice_is_deterministic`: running twice gives the same family, settings and OOF.
  - `test_platt_recovers_scale`: with p = 0.5 × true rate, the calibrated mean is within 10% of the observed rate.
- [ ] **Step 2:** Run `... manage.py test tests.test_fire_training ...`. Expected: FAIL.
- [ ] **Step 3:** Implement. Clip OOF p to [1e-6, 1 − 1e-6] before scoring. The paired bootstrap resamples barangays (1000 reps, seed 0) over per-row log-loss differences (best − LR).
- [ ] **Step 4:** Run the tests. Expected: PASS. Then rerun B1's guard test: `fire_training.py` may import models; the guard covers only the feature modules.
- [ ] **Step 5:** Leave uncommitted.

### Task B3: Levels, scores, baselines and intervals

**Files:**
- Create: `backend/apps/history/fire_evaluation.py`.
- Test: `backend/tests/test_fire_evaluation.py`.

**Interfaces:**
- Consumes: `Panel`, `Choice`, `Fitted`, `make_model` (B2).
- Produces:
  - `@dataclass Cutoffs(orange: float, red: float | None, red_reason: str | None)`, and `cutoffs(p, y, recall=0.80, red_ratio=2.0, red_min_fires=10) -> Cutoffs`.
  - `level(p: float, c: Cutoffs) -> str`, returning `'Red' | 'Orange' | 'Green'`.
  - `scores(y, p, groups) -> dict`: `log_loss`, `brier`, `roc_auc`, `pr_auc`, `calibration_intercept`, `calibration_slope`, `top10_share`, `top20_share`, `kappa_at_orange`. Each is `{value, low, high}`, with the 95% interval from 1000 resamples of `groups` (seed 0). An undefined AUC is `None`, never an error.
  - `level_table(y, p, c) -> list[dict]`: per level `{level, rows, share, fires, recall, precision, f1}`, plus `green_fires`.
  - `comparison_baselines(panel_train, panel_test, buildings) -> dict[str, ndarray]`: keys `comparison_same_everywhere`, `comparison_buildings`, `comparison_historical_frequency`.
  - `barangay_rates(p_by_area: dict[int, float], area_barangay: dict[int, int]) -> dict[int, float]`: Σ −ln(1 − p).
  - `intervals(panel, choice, reps=50, seed=0) -> dict[int, list[tuple[float, float]]]`: per area, 12 (10th, 90th) percentiles over barangay-resampled refits.
  - `limited_data(confidence: str, low: float, high: float) -> bool`.

- [ ] **Step 1: Write the failing tests:**
  - `test_orange_catches_80_percent`: for hand-made p and y with 10 fires, the rows at or above `orange` hold ≥ 8 of them, and a higher cut would hold < 8.
  - `test_red_is_twice_the_city_rate`: the rows at or above `red` have rate ≥ 2 × mean(y) and ≥ 10 fires.
  - `test_red_empty_when_too_few_fires`: with only 9 fires anywhere, `red is None` and `red_reason` says fewer than 10 fires.
  - `test_level_boundaries`: `level(orange) == 'Orange'`, `level(red) == 'Red'`, just below orange gives `'Green'`.
  - `test_scores_handle_one_class`: all-zero y gives `roc_auc['value'] is None` and a finite `brier`.
  - `test_barangay_rate_sum`: p = [0.1, 0.2] in one barangay gives rate −ln 0.9 − ln 0.8.
  - `test_limited_data_rule`: `('low', .1, .1)` is True; `('high', .01, .04)` is True (4×); `('high', .01, .02)` is False.
  - `test_baseline_names_say_comparison`: every key starts with `comparison_`.
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement. Calibration slope and intercept come from logistic regression of y on logit(p).
- [ ] **Step 4:** Run. Expected: PASS.
- [ ] **Step 5:** Leave uncommitted.

### Task B4: `train_fire_model`, the model file and the report

**Files:**
- Create: `backend/apps/history/management/commands/train_fire_model.py`.
- Test: `backend/tests/test_train_fire_model.py`.

**Interfaces:**
- Consumes: B1–B3.
- Produces:
  - `fire_features.MODEL_FILE = DATA_DIR / 'fire_purok_model.json'` and `REPORT_FILE = DATA_DIR / 'fire_purok_report.json'`.
  - Model JSON schema:
    `{version, credit, model: {family, settings}, calibration: {a, b}, cutoffs: {orange, red, red_reason}, trained: {start, end, fires, unplaced: [{date, barangay}]}, outlines_version, areas: {"<purok_id>": {barangay_id, limited_data, months: [{p, level, low, high} ×12]}}}`.
    `version = f"{family}@{sha1(features csv + fire ids + settings)[:12]}"`.
  - Report JSON:
    `{version, credit, candidates, verdict, test: {window, scores, levels, green_fires, comparison: {name: scores}}, barangay_check: {scores, comparison}, sensitivity: {fire_log_named: scores, others: scores, named_areas, other_areas}, leave_one_barangay_out: scores, caveat, unplaced}`.
    The caveat is verbatim: "Purok-level scores from past fires are probably optimistic: 151 of the 670 areas were drawn because a fire address named them. Honest purok scores come from fires after the map was frozen (the prediction log)."
- Flow:
  1. `read_features()`; stop with an error if `outlines_version != Purok.outlines_version()`.
  2. `fire_records()` and `labels()` over months 2023-01 to the last full month.
  3. Development: `choose(panel 2023–2025)`, Platt on its OOF, `cutoffs` on calibrated OOF.
  4. Test: `fit_final` on 2023–2025, scored once on 2026-01 to the last full month: `scores`, `level_table`, baselines, barangay check (BFP barangay field), sensitivity split by `from_fire_log`, leave-one-barangay-out.
  5. Deployment: `choose`, Platt and `cutoffs` on all months; `fit_final`; per-area monthly p for months 1–12; `intervals`; `limited_data`.
  6. Write both files. Print the family, verdict, test log loss and the Orange/Red share of puroks.

- [ ] **Step 1: Write the failing tests** (a fixture of 6 puroks in 2 barangays, with fires across 2023–2026, a features file written by `write_features`, and the outlines version matched):
  - `test_writes_model_and_report`: both files exist; the model has 6 areas × 12 months; every `level` is in Red/Orange/Green; `0 < p < 1`.
  - `test_stops_on_stale_outlines`: a features file with another `outlines_version` raises `CommandError` mentioning `build_fire_features`.
  - `test_unplaced_listed_not_trained`: a fire with no purok appears in `trained.unplaced` and in no label.
  - `test_report_names_comparisons_and_caveat`: every key of `test.comparison` starts with `comparison_`, and `caveat` equals the verbatim text.
  - `test_credit_present`: `credit` contains "City of Pittsburgh" and "MIT".
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement the command (`--output-dir` defaults to `DATA_DIR`, so tests write to a temp dir).
- [ ] **Step 4:** Run. Expected: PASS.
- [ ] **Step 5:** Leave uncommitted.

### Task B5: Serving: forecast rows, purok rows, accuracy, report-approval level

**Files:**
- Create: `backend/apps/history/fire_purok.py`.
- Modify:
  - `backend/apps/history/views.py`: `forecast_result`, `basis_method`, `ForecastAccuracyView`;
  - `backend/apps/reports/decide_views.py`: `_history` for fire reports only; flood and landslide
    reports keep `purok_levels`.
- Test: `backend/tests/test_fire_purok.py`; extend `test_forecast_api.py`, `test_fire_decide_view.py` and `test_fire_decision.py`.

**Interfaces:**
- Consumes: `MODEL_FILE` / `REPORT_FILE` (B4).
- Produces:
  - `NOT_TRAINED`, `STALE`: the copy strings from Global Constraints.
  - `@dataclass FireModel(version, areas: dict[int, dict], cutoffs, trained, report)`.
  - `load() -> FireModel | str`: the model, or the reason it is unavailable. Cached per process by file mtime and `Purok.outlines_version()`, rechecked at most every 60 s.
  - `purok_rows(model, month: int, week_fraction: float = 1.0) -> list[dict]`: rows of `{purok_id, barangay_id, probability, level, interval, limited_data}`. For a week, `probability = 1 − (1 − p)^week_fraction` and `level` stays the month's.
  - `barangay_table(model) -> dict[int, list[float]]`: 12 monthly rates per barangay.
  - `BARANGAY_HIGH = 0.25`, `BARANGAY_MODERATE = 0.15`, and `barangay_level(chance) -> 'High' | 'Moderate' | 'Low'`.
  - `apply(result, model, month, day, year, today)`: fills fire rows (`probability`, `expected_events`, `level`, `method='model'`, `in_training` for periods inside `trained.start..trained.end`) and `result['purok_results']`. A period before 2023-01 is unavailable with `"Fire records start in January 2023."`.
  - `purok_level(purok_id: int, today: date) -> str | None`: the model's level for the current Manila month.
  - `views.basis_method()` returns: "From a fire risk model adapted from the City of Pittsburgh Bureau of Fire's, trained on BFP fires with building, road and land-cover features."
- `decide_views`:
  - a fire report's level = the highest `purok_level` among its puroks;
  - if any is `None`, the level is `'Orange'` and the response carries `level_reason = "The fire model has no level for these puroks right now, so the level is Moderate."`.

- [ ] **Step 1: Write the failing tests** (a model file written by a test helper for 3 puroks):
  - `test_rows_from_model`: purok rows carry the file's p and level for the month.
  - `test_week_scales_chance_keeps_month_level`: `?date=` gives a probability lower than the month's, with an equal level.
  - `test_barangay_sum`: the barangay row's probability is `1 − exp(−Σ −ln(1 − p))` over its puroks.
  - `test_stale_outlines_make_fire_unavailable`: after a purok's name changes (a new xmin), rows are `unavailable` with the `STALE` text, and `purok_results == []`.
  - `test_missing_file_is_not_trained`: the `NOT_TRAINED` text.
  - `test_unknown_purok_has_no_row`: a purok created after the file gets no `purok_results` row.
  - `test_before_records_unavailable`: `?month=6&year=2022` gives "Fire records start in January 2023.".
  - `test_in_training_flag`: `?month=6&year=2024` rows have `in_training: True`; next month's do not.
  - `test_accuracy_reads_report`: `/forecast/accuracy/` fire entry has `status == 'in_use'` and the report's `version`.
  - `test_decide_uses_model_level` (in `test_fire_decide_view.py`): a fire report on a Red purok gets level Red.
  - `test_decide_falls_back_to_orange`: a purok missing from the model gives Orange and `level_reason`.
  - `test_flood_report_still_uses_history` (in `test_fire_decision.py`): a flood report's level is unchanged from `purok_levels`.
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement `fire_purok.py`, then wire `views` and `decide_views`.
- [ ] **Step 4:** Run these and the whole backend suite. Expected: PASS.
- [ ] **Step 5:** Leave uncommitted.

### Task B6: Purok prediction log (table, writer, prospective score)

**Files:**
- Modify: `backend/apps/history/models.py` (add `FirePurokPredictionLog`; `HazardPredictionLog` stays as it is).
- Create: `backend/apps/history/migrations/0009_fire_purok_prediction_log.py`, with an insert-only trigger like 0008's: `fire_purok_prediction_log_frozen`.
- Modify:
  - `backend/apps/history/prediction_log.py`: rewrite;
  - `management/commands/log_hazard_predictions.py`;
  - `backend/apps/hazards/views.py`: a once-a-Manila-day `log_once_today` in a background thread, behind `HAZARD_LOG_WRITER`;
  - `backend/apps/history/views.py`: the accuracy fire entry gains `logged`.
- Test: `backend/tests/test_fire_purok_log.py`.

**Interfaces:**
- Produces:
  - Model fields:
    - `purok_id = BigIntegerField()` (**no FK**), `purok_name = TextField()`;
    - `barangay = FK(Barangay, PROTECT)`;
    - `period_start = DateField()`, `issued_on = DateField()`, `model_version = TextField()`;
    - `probability = FloatField()` (check 0–1), `level = TextField()` (check in Red/Orange/Green), `limited_data = BooleanField()`;
    - `created_at`;
    - unique on (`purok_id`, `period_start`, `issued_on`, `model_version`); `db_table = 'fire_purok_prediction_log'`.
  - `write_month_rows(today) -> int`: one row per purok in the model, for the current month, under the model version; `bulk_create(ignore_conflicts=True)`; returns new rows; writes nothing unless `settings.HAZARD_LOG_WRITER`.
  - `log_once_today(today) -> bool`.
  - `prospective_summary(today) -> dict | None`: `{rows, months, fires_after, scores}`, scoring only fires whose date is after the row's `issued_on` and inside its month.

- [ ] **Step 1: Write the failing tests:**
  - `test_rows_are_insert_only`: update and delete raise `DatabaseError` (the trigger).
  - `test_rerun_adds_nothing`: the second `write_month_rows` returns 0.
  - `test_writer_flag_off_writes_nothing`: with `HAZARD_LOG_WRITER=False`, the result is 0 rows.
  - `test_purok_reload_keeps_log`: deleting a `Purok` leaves its log rows in place.
  - `test_prospective_counts_only_later_fires`: a fire on the issue day before the row is not scored; one the day after is.
  - `test_migration_0009_matches_model`: `makemigrations --check` gives no changes.
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement the model, migration, writer, command and hook.
- [ ] **Step 4:** Run these and the whole backend suite. Expected: PASS. **The migration runs only on the private test DB here.**
- [ ] **Step 5:** Leave uncommitted.

### Task B7: Frontend: purok fills, panel list, accuracy card

**Files:**
- Modify:
  - `frontend/src/components/Forecast/forecastLevels.js`: add `FIRE_MODEL_LABEL`, `FIRE_CREDIT`, `PUROK_CAVEAT`, `purokLikelyLevels(likely)` and `purokLikelyTip(row, name)`;
  - `frontend/src/pages/PublicMap.jsx`:
    - in the likely view, puroks are filled by fire level, reusing `PurokHistoryLayer` with `levels = purokLikelyLevels(likely)`, `types = ['Fire']` and the likely tooltip;
    - barangays are outlined only;
    - the barangay tooltip shows the fire chance;
  - `frontend/src/components/Map/BarangayPanel.jsx`: new props `likelyPuroks` and `view`; in the likely view it renders `LikelyPuroks`;
  - `frontend/src/components/Forecast/ForecastAccuracy.jsx`: a new `FireModelReport` for the fire entry;
  - `frontend/src/components/Forecast/BarangayLikelihood.jsx`: the fire label and caveat.
- Create: `frontend/src/components/Map/LikelyPuroks.jsx`.
- Tests: `forecastLevels.test.js`, `forecastAccuracy.test.js`, and a new `frontend/src/components/Map/likelyPuroks.test.js`.

**Interfaces:**
- Consumes: the `purok_results` rows (B5) and the report JSON (B4) as served.
- Produces:
  - `purokLikelyLevels(likely) -> Map<string, { Fire: { level, probability, limited_data } }>`: the shape `filledPuroks` reads.
  - `purokLikelyTip(row, name) -> string`, e.g. `"Purok Sambag: Extreme, about 2% this month · Limited data"`. Level words are `{Red: 'Extreme', Orange: 'Moderate', Green: 'Low'}`; no "· Limited data" part when the flag is false.
  - `LikelyPuroks({ rows, purokNames })`: the 5 highest by probability, then a "Show all" button; each row shows its name, level word, percent and the limited-data tag.

- [ ] **Step 1: Write the failing tests:**
  - `purokLikelyLevels maps rows by purok id`: two rows give a Map of size 2 with `.get('12').Fire.level === 'Red'`.
  - `purokLikelyTip shows limited data`: the text above, exactly.
  - `LikelyPuroks shows top 5 then all`: 7 rows render 5, and clicking "Show all" renders 7, sorted by probability descending.
  - `FireModelReport renders candidates, verdict, caveat and credit`: from a fixture report, the verbatim caveat and "City of Pittsburgh" are present, and there is one row per candidate.
  - `FireModelReport shows not trained`: with `status: 'unavailable'`, the text "The fire model has not been trained yet." is shown.
- [ ] **Step 2:** Run `CI=true npm test -- --watchAll=false src/components`. Expected: FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run the whole frontend suite and `npm run build`. Expected: PASS and compiled.
- [ ] **Step 5:** Leave uncommitted.

### Task B8: Docs and full verification

**Files:**
- Modify:
  - `docs/CODEBASE_GUIDE.md`: the forecast section, the purok levels row (unchanged history), removed modules, new commands;
  - `README.md`: the hazard prediction paragraph;
  - `deploy/FREE_HOSTING.md`: `HAZARD_LOG_WRITER` now drives the purok log; no Rain watch.

- [ ] **Step 1:** Update the docs. Every command named exists: `build_fire_features`, `train_fire_model`, `log_hazard_predictions`.
- [ ] **Step 2:** Run the full backend suite on `geo_test_settings_fire`. Expected: OK; the total test count is printed.
- [ ] **Step 3:** Run the full frontend suite and the build. Expected: all pass.
- [ ] **Step 4:** Run `git status --short` and report the changed and deleted files. Leave uncommitted.

### Task B9: Real run (waits for the user)

**Starts only after the user returns the 23-fire checklist. Each shared-database step needs the user's go-ahead.**

- [ ] **Step 1:** Add each placement from `Downloads/Talisay-23-Fires-Without-Purok-2026-11-22.csv` to `backend/apps/barangays/data/puroks/fire_places.csv`, with its reason and source.
- [ ] **Step 2 (shared DB, go-ahead first):** Back up the fire links to Downloads (JSON of `historical_record_purok` for fires). Then run `import_bfp_fires --relink`. Report how many of the 23 now have a purok.
- [ ] **Step 3:** Run `build_fire_features`. This downloads WorldCover, the footprint polygons and WorldPop, if available. Report the WorldPop result and the areas with 0 buildings.
- [ ] **Step 4:** Run `train_fire_model`. Report the family chosen, the verdict, test log loss, Brier, ROC-AUC and PR-AUC with intervals, the level table, green fires, the barangay check and the sensitivity table, all as written in the report. Do not round away the intervals.
- [ ] **Step 5 (shared DB, go-ahead first):** Back up the database (a `pg_dump` to Downloads, as for 0008). Then run `migrate history 0009`, then `log_hazard_predictions` once. Report the rows written.
- [ ] **Step 6:** Hand checks in the browser. Stub `GET /api/hazards/`: it releases overdue alerts on the shared DB.
  - "Likely by month": purok fills, tooltips and the panel list;
  - the accuracy card;
  - approving a fire report shows the model level.
