# Landslide susceptibility by purok — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add landslide to GeoAlert's predictive analytics: a Red/Orange/Green landslide susceptibility level per purok from a neural network trained once, offline, on landslides mapped after Philippine typhoons (plus world events only if a held-out typhoon test shows they help), benchmarked against UP NOAH's landslide map, and retrained by the January job only once GeoAlert has 30 located landslide spots of its own.

**Architecture:** A one-time command turns the open inventories into a committed training table of clues (no coordinates). A second command computes the same clues at Talisay's buildings and road points. A third trains, chooses (NN unless clearly worse), gates against NOAH and writes a model file and report. The site only reads those files and the live `model_fit`. The retraining job gains a landslide branch that does nothing below the floor. History is not touched.

**Tech Stack:** Django 4.2 / DRF / PostGIS (`django.contrib.gis.gdal` reads shapefiles and the File GDB); NumPy, SciPy, scikit-learn 1.9.1; xgboost 3.2.0 (offline and in the job only); React (react-scripts, Jest) with Leaflet; GitHub Actions.

**Spec:** `docs/design/specs/2026-11-24-landslide-susceptibility-model-design.md` (section 0 governs). Pattern: the flood build (`docs/design/plans/2026-11-24-flood-susceptibility-model.md`, `apps/history/flood_*.py`) and the retraining build (`apps/history/model_job.py`, `model_fits.py`, `.github/workflows/model-retrain.yml`).

## Global Constraints

- **Never `git commit`.** Every commit step reads "Leave uncommitted" (the user's standing rule).
- **History is not modified.** Do not edit `apps/history/purok_levels.py`, `apps/history/area.py`, `apps/reports/decide.py`, `apps/reports/decide_views.py`, the `history.*` entries of `utils/system_settings.py`, `frontend/src/components/Map/purokLevels.js`, the Past hazards view or the History page. An approved landslide report keeps its history-based level. Fire's and flood's models and outputs are not changed.
- **Shared database:** new migrations `history 0013` (log) and `history 0014` (model_fit hazard). They and the deletion of the two test records are applied only in Task 14, each after a `pg_dump` backup to Downloads and the user's go-ahead.
- **Training landslides (pinned):**
  - NASA COOLR new events: `https://ndownloader.figshare.com/files/54363830` → `backend/.hazard_cache/nasa_coolr_new_events.zip`, SHA-256 `2a019c6a955a4e9ae8da9b8740c1f64c3cd9a162e90972bb03509a5f119dfd38`; File GDB `nasa_coolr_new_events/nasa_coolr_new_events.gdb`, layer `nasa_coolr_events_new_point` (15,274 points; fields `ev_date`, `ctry_name`, `storm_name`, `latitude`, `longitude`, `ev_id`). CC BY 4.0.
  - Mangkhut, Itogon: `https://data-package.ceh.ac.uk/data/32765a61-8510-4dfc-b7c7-58bad12f8497.zip` → `.hazard_cache/eidc_mangkhut_itogon.zip`. The package wrapper may be regenerated, so pin the inner files: `data/itogon_inventory_v11_wgs84utm51.shp` `fd28551e09f95c87c9db234d9c0dbcc2e8e381d76d657277c230bec5c8ad8099`, `.dbf` `89beefb3f3f3c998300b0e12fbff95d6df6b4fac71974f90c7bb6197d600ca84`, `.shx` `d4d8563a08834cd1ea928d1b8252a30394025c8e6cfc100be3d90a0e69e9b79a`. 1,101 polygons, EPSG:32651. Open Government Licence. Parma is not used.
- **Events and folds** (key → date, fold, region, land cover year): `egay` 2023-07-26 → `egay`, ph, 2022; `paeng` 2022-10-28 → `paeng`, ph, 2021; `agaton` 2022-04-10 → `agaton`, ph, 2021; `mangkhut` 2018-09-14 → `mangkhut`, ph, 2017; each of the 19 other COOLR events (grouped by `ev_date` + `ctry_name`) → its own key, fold `world`, region world, land cover year = event year − 1. COOLR's Philippine rows split by `ev_date`: 2023-07-26 Egay, 2022-10-28 Paeng, 2022-04-10 Agaton.
- **NOAH landslide maps:** `https://huggingface.co/datasets/bettergovph/project-noah-hazard-maps/resolve/main/Landslide/LandslideHazards/{Province}.zip`, field `HAZ` (1 low, 2 medium, 3 high; outside every polygon = 0). Provinces: `Abra`, `IlocosNorte`, `IlocosSur`, `Benguet`, `Maguindanao`, `Cotabato`, `Leyte`, `SouthernLeyte`, `Cebu` (Talisay). Pin each SHA-256 at first download in a `NOAH_LANDSLIDE` dict (the flood plan's `NOAH` pattern). ODbL.
- **Land cover:** Esri / Impact Observatory 10 m annual LULC v003, public blob (no account): `https://lulctimeseries.blob.core.windows.net/lulctimeseriesv003/lc{year}/{zone}{band}_{year}0101-{year+1}0101.tif` (UTM tile, e.g. `51P`), CC BY 4.0, years 2017–2023 (Talisay uses the newest year that answers HTTP 200). Classes grouped: 2 trees → `lc_trees`; 11 rangeland → `lc_rangeland`; 5 crops → `lc_crops`; 7 built → `lc_built`; 8 bare → `lc_bare`; others count in the denominator only. Share within 50 m. If the blob cannot be range-read without an account, `LANDCOVER_OK = False`: every `lc_*` column is dropped before any fit and the report says so.
- **Grid and tiles:** Copernicus GLO-30 on the zoom-14 web-mercator grid (`susceptibility.Grid`, `fetch_copernicus`). Training tiles are 12 km squares (2 km pad around an inner 8 km square), laid on a regular lattice over each event's sampling area; a point is computed only in the tile whose inner square holds it. Talisay uses `city_grid(extent, zoom=14, pad_m=2000)` so its upstream areas are cut no closer than the training tiles'.
- **Model inputs are exactly** (`FEATURE_COLUMNS`): `slope_deg`, `relief_m`, `profile_curv`, `plan_curv`, `hand_m`, `twi`, `dist_stream_m` (used as `log1p`), `dist_road_m` (used as `log1p`), `lc_trees`, `lc_rangeland`, `lc_crops`, `lc_built`, `lc_bare`. `TERRAIN_COLUMNS` = the first seven. `CLIP_COLUMNS` = `dist_road_m` and the `lc_*`. Absolute height and NOAH are never inputs.
- **Clue definitions:** smoothed DEM = `gaussian_filter(sigma=1)` (as `compute_factors`); slope and relief (150 m window) as `compute_factors`; curvature = Zevenbergen–Thorne profile and plan curvature on the smoothed DEM, in 1/m; channels = DEM-derived only, `flow_accumulation(fill_depressions(smooth)) >= STREAM_AREA_KM2·1e6` on land (no OSM waterways, whose coverage differs by region); `hand_m` = filled height minus the nearest channel cell's, floored at 0; `twi = ln((area/res) / max(tan(slope), 0.001))`; `dist_stream_m` = distance to a channel cell; `dist_road_m` = distance to an OSM `highway` line (roads-only Overpass query, the `ROAD_TYPES` set).
- **"No" points:** per event, uniform over the union of 2 km discs around its slides, at least 60 m from any slide of that event, 3 per slide, seed 0. Distances in local equirectangular metres around the event's mean latitude.
- **Polygons → points:** a Mangkhut polygon becomes the centre of its highest DEM cell (the scar).
- **Road check:** an event keeps `dist_road_m` only if its OSM road density (km per km² over its sampling area) is at least 0.1 × Talisay's road density on grid cells with `slope_deg >= 10`; otherwise its rows get `dist_road_m = NaN`.
- **Candidates (fixed):**
  - `neural_network`: `make_pipeline(StandardScaler(), MLPClassifier(hidden_layer_sizes=(32, 16), activation='relu', solver='adam', alpha=1e-3, max_iter=500, early_stopping=False, random_state=10*seed+s))`, s = 0..4, probabilities averaged; `ConvergenceWarning` silenced.
  - `logistic_regression`: `make_pipeline(StandardScaler(), LogisticRegression(C=1.0, max_iter=5000))`.
  - `xgboost`: `XGBClassifier(max_depth=3, n_estimators=400, learning_rate=0.05, subsample=0.8, random_state=seed, n_jobs=1, monotone_constraints=…)` with +1 `slope_deg`, `relief_m`, `twi`; −1 `dist_stream_m`, `dist_road_m`; 0 others. Gets `NaN` for missing roads.
  - `noah_only` (B0): score = `noah_class / 3` (Philippine rows only; world rows have none).
  - NN and LR get missing `dist_road_m` filled with the training rows' median plus a 0/1 `road_unknown` column (Talisay: always 0). Outside rows weight 1; own rows (and their "no" points) weight 10.
- **Folds:** `egay`, `mangkhut`, `paeng`, `agaton` (+ `talisay` in own mode). World rows are training-only and never scored.
- **Bootstrap:** 1,000 repeats, seed 0, slides and "no" points resampled within each fold (`flood_rules.auc_gain`). AUC and its bootstrap are always **unweighted**; the weight of 10 enters only the fits and the cut-off walk.
- **Rule 1 (world):** per held-out Philippine fold, NN on the other Philippine folds vs NN on them + all world rows; the world joins if `auc_gain(B over A)` has its 2.5% bound > 0.
- **Rule 2 (model):** `neural_network` unless `logistic_regression` or `xgboost` beats it by `auc_gain` with 2.5% bound > 0; if both do, the higher pooled AUC wins, and on an exact tie `logistic_regression`.
- **Cut-offs:** `flood_rules.cutoff_walk` with each out-of-fold Philippine (and own) point as a unit, its score as the "purok score", and its slide weight as `spots_in` (1 per outside slide, 10 per own slide, 0 per "no" point). Red 0.5, Orange 0.9.
- **Talisay scoring points:** building centres (`fire_sources.footprints`) plus points every 20 m along OSM roads inside the city. A point is in range when every `TERRAIN_COLUMNS` value is inside the chosen training set's 1st–99th percentile (`flood_training.in_range`); `CLIP_COLUMNS` are clipped to that range. Purok score = `np.percentile(valid point scores, 90)`; assessed when valid ≥ 50% of its points.
- **Acceptance (all four):** (1) `auc_gain(model over noah_only)` on the Philippine folds, 2.5% bound > 0; (2) at least `flood_rules.test_hits_needed(n)` of the Talisay test puroks Red or Orange (0 test puroks = fail); (3) Red + Orange ≤ 50% of assessed scoring points; (4) training set, choice and cut-offs written to the report before `load_tests()` is called. Any fail → NOAH fallback.
- **NOAH fallback:** cut-offs = `cutoff_walk` on B0's Philippine out-of-fold points; Talisay purok score = 90th percentile of `noah_class / 3` over its points; every purok with points is assessed.
- **Uncertain:** class differs from the published class in > 20% of refits; 200 refits offline, 100 in the job; seed 0.
- **Monitoring:** "under review" when fewer than 80% of the last ≥ 10 new located landslides fall in Red or Orange (`flood_rules.monitoring`).
- **Own data (January job):** floor 30 spots in 3 barangays; held-back season = 1 June – 31 December of last year, at least 5 spots; "no" points around own spots by the same rule as outside; switch only if all four checks pass **and** new hits ≥ live hits (a tie switches); a `switched` landslide fit outside January–May (Manila) is saved as `kept` with `LANDSLIDE_SEASON_LOCK`.
- **Copy, verbatim** (backend constants in `landslide_purok.py` unless noted):
  - `NOT_TRAINED = "The landslide model has not been trained yet."`
  - `STALE = "The purok map changed since the landslide model was trained; rerun build_landslide_features and train_landslide_model."`
  - `UNREADABLE = "The landslide model file could not be read; rerun train_landslide_model."`
  - `REPORT_MISSING = "The landslide model's report is missing; rerun train_landslide_model."`
  - `NOT_BY_MONTH = "Landslide susceptibility does not change by month."`; with Flood and Landslide both asked and no Fire: `"Flood and landslide susceptibility do not change by month."` (`views.SUSCEPTIBILITY_NOT_BY_MONTH`)
  - `views.FORECAST_ONLY = "Only fire, flood and landslide have prediction models."`
  - Level words: Red `"High landslide susceptibility"`, Orange `"Moderate landslide susceptibility"`, Green `"Low landslide susceptibility"`, none `"Not assessed yet"`.
  - Not-assessed reasons: `"No buildings or roads in this area"`, `"Its ground is unlike the areas the model learned from"`.
  - `UNDER_REVIEW = "Under review: recent landslides fall outside the flagged areas"`
  - `BASIS_MODEL = "From a machine-learning model of where landslides started after Philippine typhoons (mapped from satellite images), applied to Talisay's terrain, land cover and roads. It shows how prone an area is to sliding, not whether a landslide is coming, and it is the same in every month."`
  - `BASIS_NOAH = "From UP NOAH's landslide hazard map, classed by where landslides started after Philippine typhoons. It shows how prone an area is to sliding, not whether a landslide is coming, and it is the same in every month."`
  - `BASIS_GEOALERT = "From a machine-learning model of where landslides started after Philippine typhoons and in GeoAlert's own located landslide records, applied to Talisay's terrain, land cover and roads. It shows how prone an area is to sliding, not whether a landslide is coming, and it is the same in every month."`
  - Legend: `"Landslide: where the ground tends to slide (from a machine-learning model; the same in every month, not a forecast of a landslide)"`; NOAH: `"Landslide: where the ground tends to slide (from UP NOAH's landslide hazard map; the same in every month, not a forecast of a landslide)"`.
  - Job (`landslide_own.py`): `LANDSLIDE_FLOOR = "{n} of 30 located landslide spots, {b} of 3 barangays"`, `LANDSLIDE_HELD = "Too few new spots to test ({n} of 5); tries again next January"`, `LANDSLIDE_WORSE = "Fewer of the {season} wet season's spots in Red or Orange than the map in use ({new} vs {live})"`, `LANDSLIDE_SWITCHED = "Passed all four checks; {hits} of {n} held-back spots in Red or Orange"`; `model_fits.LANDSLIDE_SEASON_LOCK = "Landslide maps change only between January and May"`.
  - Readiness line (frontend): `"Located landslide spots with a map point: {n} of 30, in {b} of 3 barangays"`.
  - Frontend: `FORECAST_ONLY_NOTE = "Pick fire, flood or landslide to see a prediction."`; `TICK_NOTE = "Tick the Fire, Flood or Landslide layer."`
- **Credits** (report and ATTRIBUTION.md): "Landslide inventories: NASA Cooperative Open Online Landslide Repository, Vershel et al. (2025), Open inventories of rainfall-triggered landslides, Figshare doi 10.6084/m9.figshare.26972467 (CC BY 4.0)"; "Abancó, C.; Jones, J.N. (2023). Areas affected by landslides following Typhoon Mangkhut in Itogon, Philippines, September 2018. NERC EDS Environmental Information Data Centre. doi 10.5285/32765a61-8510-4dfc-b7c7-58bad12f8497 (Open Government Licence)"; "UP NOAH landslide hazard maps (ODbL), via the bettergovph mirror"; "Esri / Impact Observatory 10 m annual land cover (CC BY 4.0)"; the existing Copernicus DEM notice; "© OpenStreetMap contributors (ODbL)"; "Microsoft building footprints (ODbL)". `landslide_training.csv` carries the notice "This table is a database derived from ODbL data and is shared under the ODbL."
- **No coordinates** in `landslide_training.csv`, the model file, the report, any endpoint except the token-only training data, the job's prints or its posted attempt.
- **Tests run on private test databases:** create `C:\Users\Sannichigetsu\.geoalert-test\geo_test_settings_landslide.py` (copy of `geo_test_settings_flood.py`, `TEST NAME = "test_geoalert_landslide_susc"`, cache `C:/Users/Sannichigetsu/.geoalert-test/cache-landslide`) and `geo_test_settings_landslide_b.py` (`test_geoalert_landslide_susc_b`, `cache-landslide-b`) for a task running in parallel.
  - Backend (from `backend/`): `PYTHONPATH="C:/Users/Sannichigetsu/.geoalert-test" venv/Scripts/python.exe manage.py test <labels> --settings=geo_test_settings_landslide --noinput`
  - Frontend (from `frontend/`): `CI=true npm test -- --watchAll=false <path>`
- **Parallel groups** (the user wants independent work run at the same time, each with its own test settings and a review limited to its paths): {1, 2, 3, 6} first; then {4, 5, 11}; then 7; then 8; then {9, 10, 12, 13}; then 14. Task 8 creates `landslide_own.py`'s constants and `floor()`, which Tasks 9 and 10 build on.

## Review Focus

1. **Talisay's homes are far more built-up than mountain ground, and road points sit on roads** → those points are clipped, not greyed; a flat, built-up purok comes out Green, not "not assessed". Test: Task 6 (`test_flat_built_up_purok_is_green_not_grey`).
2. **Purok map reloaded after training** → the landslide block is `available: false` with `STALE`, `landslide_results` is empty, fire and flood are unaffected. Test: Task 8 (`test_stale_outlines_make_landslide_unavailable_only`).
3. **Fire, Flood and Landslide all ticked, a purok Orange for fire, flood not assessed, landslide Red** → fill Red; the hover names all three. Test: Task 12 (`three hazards: the highest level fills and each is named`).
4. **A landslide fit posted in July, or with fewer held-back hits than the live own-data map** → saved `kept` with the sentence, live map unchanged. Tests: Task 10 (`test_switch_outside_january_to_may_is_kept`, `test_fewer_season_hits_is_kept`).
5. **A coordinate leaking into a written file** (training table, model, report, job print) → a test fails. Tests: Task 4 (`test_training_table_has_no_coordinates`), Task 7 (`test_no_coordinates_in_the_written_files`), Task 10 (`test_job_prints_and_posts_no_coordinate`).

---

### Task 1: Inventory readers (training side only)

**Files:**
- Create: `backend/apps/history/landslide_inventories.py`
- Test: `backend/tests/test_landslide_inventories.py`

**Interfaces:**
- Consumes: `apps.history.downloads.fetch_verified`.
- Produces:
  - `COOLR_URL`, `COOLR_SHA256`, `MANGKHUT_URL`, `MANGKHUT_FILES` (inner path → SHA-256), per Global Constraints.
  - `Event` dataclass `(key: str, date: date, fold: str, region: str, landcover_year: int, noah_provinces: tuple[str, ...])`.
  - `coolr_events(rows: list[dict]) -> dict[str, Event]` and `coolr_slides(rows: list[dict]) -> list[dict]` → `{'event': key, 'lon': float, 'lat': float}`; rows are dicts with the GDB field names.
  - `read_coolr(cache_dir: Path) -> list[dict]` (GDB rows via `django.contrib.gis.gdal.DataSource`).
  - `read_mangkhut(cache_dir: Path) -> list` (GEOS polygons, SRID 32651), checking each inner file's SHA-256 before reading.
  - `EVENT_NOAH = {'egay': ('Abra', 'IlocosNorte', 'IlocosSur'), 'mangkhut': ('Benguet',), 'paeng': ('Maguindanao', 'Cotabato'), 'agaton': ('Leyte', 'SouthernLeyte')}`

- [ ] **Step 1: Write the failing tests**

```python
ROWS = [{'ev_date': '2023/07/26 00:00:00+00', 'ctry_name': 'Philippines', 'storm_name': 'Typhoon Egay', 'latitude': 17.5, 'longitude': 120.9},
        {'ev_date': '2022/10/28 00:00:00+00', 'ctry_name': 'Philippines', 'storm_name': 'Tropical Storm', 'latitude': 6.9, 'longitude': 124.2},
        {'ev_date': '2022/04/10 00:00:00+00', 'ctry_name': 'Philippines', 'storm_name': 'Tropical Storm', 'latitude': 10.7, 'longitude': 124.85},
        {'ev_date': '2023/08/05 00:00:00+00', 'ctry_name': 'Vietnam', 'storm_name': '', 'latitude': 22.0, 'longitude': 103.0}]

def test_philippine_events_get_their_folds_and_the_rest_are_world(self):
    ev = coolr_events(ROWS)
    self.assertEqual((ev['egay'].fold, ev['egay'].landcover_year), ('egay', 2022))
    self.assertEqual((ev['paeng'].fold, ev['agaton'].fold), ('paeng', 'agaton'))
    world = [e for e in ev.values() if e.region == 'world']
    self.assertEqual(len(world), 1); self.assertEqual((world[0].fold, world[0].landcover_year), ('world', 2022))

def test_slides_keep_their_event_and_point(self):
    s = coolr_slides(ROWS)
    self.assertEqual(s[0], {'event': 'egay', 'lon': 120.9, 'lat': 17.5}); self.assertEqual(len(s), 4)

def test_an_unknown_philippine_date_is_refused(self):
    with self.assertRaisesMessage(ValueError, 'Unknown Philippine COOLR event 2024-01-01'):
        coolr_events([{**ROWS[0], 'ev_date': '2024/01/01 00:00:00+00'}])

def test_module_reads_no_geoalert_records(self):
    src = Path(landslide_inventories.__file__).read_text(encoding='utf-8')
    for name in ('HistoricalRecord', 'purok_levels', 'forecast'): self.assertNotIn(name, src)
```

- [ ] **Step 2: Run** `... manage.py test tests.test_landslide_inventories ...` — Expected: FAIL (module missing).
- [ ] **Step 3: Implement `landslide_inventories.py`.** World event keys are `f"{ctry_name.lower().replace(' ', '_')}_{yyyymmdd}"`. The Mangkhut event date is 2018-09-14. Module docstring: training data only, kept in `.hazard_cache`, never served.
- [ ] **Step 4: Run** — Expected: PASS. Then a one-off real check from `backend/`: `read_coolr(Path('.hazard_cache'))` gives 15,274 rows and `coolr_events` gives 22 events (3 Philippine); `read_mangkhut` gives 1,101 polygons.
- [ ] **Step 5: Leave uncommitted.**

### Task 2: Clue functions (shared by training tiles and Talisay)

**Files:**
- Create: `backend/apps/history/landslide_features.py`
- Test: `backend/tests/test_landslide_features.py`

**Interfaces:**
- Consumes: `apps.hazards.susceptibility` (`Grid`, `fill_depressions`, `flow_accumulation`, `draw_lines`, `distance_to`, `STREAM_AREA_KM2`, `ROAD_TYPES`); `apps.history.flood_features.sample_grid`.
- Produces:
  - `FEATURE_COLUMNS`, `TERRAIN_COLUMNS`, `CLIP_COLUMNS`, `LOG_COLUMNS = ('dist_stream_m', 'dist_road_m')`, `LANDCOVER_CLASSES = {2: 'lc_trees', 11: 'lc_rangeland', 5: 'lc_crops', 7: 'lc_built', 8: 'lc_bare'}`
  - `DATA_DIR`, `TRAINING_FILE = DATA_DIR / 'landslide_training.csv'`, `TRAINING_META = DATA_DIR / 'landslide_training.meta.json'`, `FEATURES_FILE = DATA_DIR / 'landslide_purok_features.csv'`, `FEATURES_META = DATA_DIR / 'landslide_purok_features.meta.json'`, `POINTS_FILE = 'landslide_points.npz'` (cache dir), `MODEL_FILE = DATA_DIR / 'landslide_purok_model.json'`, `REPORT_FILE = DATA_DIR / 'landslide_purok_report.json'`
  - `terrain_grids(dem: np.ndarray, res: float) -> dict[str, np.ndarray]` (the seven `TERRAIN_COLUMNS`, float32; `dist_stream_m` in metres)
  - `curvatures(smooth: np.ndarray, res: float) -> tuple[np.ndarray, np.ndarray]` (profile, plan)
  - `road_distance(grid: Grid, roads: list) -> np.ndarray` (metres)
  - `landcover_shares(classes: np.ndarray, res_m: float, radius_m: float = 50) -> dict[str, np.ndarray]`
  - `sample(grid: Grid, grids: dict, points_ll: np.ndarray) -> dict[str, np.ndarray]`

- [ ] **Step 1: Write the failing tests**

```python
def test_a_plane_has_its_slope_and_no_curvature(self):
    y, x = np.mgrid[0:60, 0:60].astype(float); dem = 100 + 0.5 * x * 10  # 0.5 m per m east, res 10 m
    g = terrain_grids(dem, res=10.0)
    self.assertAlmostEqual(float(np.median(g['slope_deg'])), np.degrees(np.arctan(0.5)), places=1)
    prof, plan = curvatures(ndimage.gaussian_filter(dem, 1.0), 10.0)
    self.assertLess(float(np.abs(prof[10:-10, 10:-10]).max()), 1e-6)

def test_a_hollow_has_concave_plan_curvature_and_wetter_twi(self):
    g = terrain_grids(self.valley_dem, res=10.0)  # V-shaped valley draining south
    self.assertGreater(g['twi'][self.axis_cell], g['twi'][self.ridge_cell])
    self.assertLess(g['hand_m'][self.axis_cell], g['hand_m'][self.ridge_cell])

def test_the_same_clues_for_a_training_window_and_the_city_grid(self):
    a = terrain_grids(self.dem, 9.4); b = terrain_grids(self.dem.copy(), 9.4)
    for c in TERRAIN_COLUMNS: np.testing.assert_array_equal(a[c], b[c])

def test_landcover_shares(self):
    cls = np.full((21, 21), 2); cls[:, 11:] = 7
    s = landcover_shares(cls, res_m=10.0, radius_m=50)
    self.assertAlmostEqual(float(s['lc_built'][10, 10]), 5 / 11, places=1)
    self.assertEqual(set(s), set(LANDCOVER_CLASSES.values()))

def test_feature_module_reads_no_landslide_records(self):
    src = Path(landslide_features.__file__).read_text(encoding='utf-8')
    for name in ('HistoricalRecord', 'landslide_inventories', 'purok_levels', 'forecast'): self.assertNotIn(name, src)
```

- [ ] **Step 2: Run** `... manage.py test tests.test_landslide_features ...` — Expected: FAIL.
- [ ] **Step 3: Implement** with the Global Constraints' clue definitions. Zevenbergen–Thorne on a 3×3 window: with `D = ((z_w+z_e)/2 − z_0)/res²`, `E = ((z_n+z_s)/2 − z_0)/res²`, `F = (−z_nw + z_ne + z_sw − z_se)/(4 res²)`, `G = (−z_w + z_e)/(2 res)`, `H = (z_n − z_s)/(2 res)`: profile = `−2(D G² + E H² + F G H)/(G² + H²)`, plan = `2(D H² + E G² − F G H)/(G² + H²)`, both 0 where `G² + H² < 1e-12`. Shares use a circular footprint of the given radius.
- [ ] **Step 4: Run** — Expected: PASS.
- [ ] **Step 5: Leave uncommitted.**

### Task 3: Sources: land cover, NOAH landslide classes, roads

**Files:**
- Create: `backend/apps/history/landslide_sources.py`
- Test: `backend/tests/test_landslide_sources.py`

**Interfaces:**
- Consumes: `downloads.fetch_verified`; `susceptibility.make_session`, `http_range_fetcher`, `overpass`, `draw_polygons`; `fire_sources` window helpers as fits.
- Produces:
  - `LANDCOVER_URL`, `utm_tile(lon: float, lat: float) -> str` (e.g. `'51P'`), `landcover_year_for(event_date: date) -> int` (`event year − 1`, at least 2017)
  - `landcover_classes(grid: Grid, year: int, cache_dir: Path, log=print) -> np.ndarray | None` (the class at each grid cell centre, nearest neighbour; `None` when the blob cannot be range-read; cached as `lulc_{year}_{tag}.npz`)
  - `NOAH_LANDSLIDE: dict[str, str]` (province → SHA-256), `noah_landslide_grid(grid: Grid, provinces: tuple[str, ...], cache_dir: Path) -> np.ndarray` (uint8, highest `HAZ` per cell, 0 outside)
  - `roads(bbox: tuple, cache_dir: Path, log=print) -> list` (OSM `highway` lines in `ROAD_TYPES`; roads-only query; cached as `osm_roads_{bbox digest}.json`)
  - `road_density_km_per_km2(grid: Grid, roads: list, mask: np.ndarray) -> float`

- [ ] **Step 1: Write the failing tests**

```python
def test_utm_tiles_and_years(self):
    self.assertEqual(utm_tile(123.85, 10.25), '51P'); self.assertEqual(utm_tile(120.9, 17.5), '51Q')
    self.assertEqual(utm_tile(124.2, 6.9), '51N')
    self.assertEqual(landcover_year_for(date(2018, 9, 14)), 2017); self.assertEqual(landcover_year_for(date(2017, 5, 1)), 2017)

def test_noah_grid_keeps_the_highest_class(self):  # two overlapping squares written as tiny shapefile-free dicts
    g = noah_landslide_grid_from({1: [self.sq_a], 3: [self.sq_b]}, self.grid)
    self.assertEqual(g[self.overlap_cell], 3); self.assertEqual(g[self.outside_cell], 0)

def test_unreadable_landcover_is_none_not_an_error(self):
    self.assertIsNone(landcover_classes(self.grid, 2022, self.tmp, fetch=failing_fetch))

def test_road_density(self):  # one 1 km road across a 1 km² mask
    self.assertAlmostEqual(road_density_km_per_km2(self.grid, [self.km_road], self.km2_mask), 1.0, delta=0.1)
```

- [ ] **Step 2: Run** `... manage.py test tests.test_landslide_sources ...` — Expected: FAIL.
- [ ] **Step 3: Implement.** Split `noah_landslide_grid` into a reader (zip → `{class: polygons}` via `DataSource`, with the flood code's unsafe-member check) and `noah_landslide_grid_from(polygons_by_class, grid)` so the test needs no file. The land cover reader range-reads the UTM tile (GDAL `/vsicurl/` through `django.contrib.gis.gdal.GDALRaster` is acceptable; else the COG range reader pattern of `fire_sources.read_window`), converts cell centres lon/lat → UTM with `CoordTransform`, and accepts a `fetch` argument for the test. Pin each NOAH province's SHA-256 on first download (record them in the dict; the plan's Task 4 real run downloads them).
- [ ] **Step 4: Run** — Expected: PASS.
- [ ] **Step 5: Leave uncommitted.**

### Task 4: `build_landslide_training` (tiles, "no" points, road check, the committed table)

**Files:**
- Create: `backend/apps/history/landslide_training_table.py`, `backend/apps/history/management/commands/build_landslide_training.py`
- Modify: `backend/apps/history/data/ATTRIBUTION.md`
- Test: `backend/tests/test_landslide_training_table.py`

**Interfaces:**
- Consumes: Tasks 1–3.
- Produces:
  - `sample_no_points(slides_xy: np.ndarray, per_slide: int = 3, radius_m: float = 2000, min_gap_m: float = 60, seed: int = 0) -> np.ndarray`
  - `scar_point(polygon, dem_grid: Grid, dem: np.ndarray) -> tuple[float, float]`
  - `tiles_for(points_ll: np.ndarray, inner_km: float = 8, pad_km: float = 2) -> list[dict]` → `{'bbox_inner', 'bbox_outer', 'index': np.ndarray}` (each point in exactly one tile)
  - `TABLE_COLUMNS = ('event', 'fold', 'region', 'label', *FEATURE_COLUMNS, 'noah_class')`
  - `write_table(rows: list[dict], meta: dict, path=TRAINING_FILE, meta_path=TRAINING_META)`; `read_table(path=TRAINING_FILE, meta_path=TRAINING_META) -> tuple[dict[str, np.ndarray], dict]`
  - Meta keys: `sources` (URL, SHA-256, licence each), `events` (key, fold, region, slides, no_points, landcover_year, road_kept), `road_check` (Talisay steep-ground density, each event's density), `landcover_ok`, `seed`, `talisay_steep_road_density`.

- [ ] **Step 1: Write the failing tests**

```python
def test_no_points_keep_their_distances_and_count(self):
    slides = np.array([[0., 0.], [5000., 0.]])
    nop = sample_no_points(slides, per_slide=3, seed=0)
    self.assertEqual(len(nop), 6)
    d = np.min(np.hypot(*(nop[:, None, :] - slides[None]).transpose(2, 0, 1)), axis=1)
    self.assertTrue(((d >= 60) & (d <= 2000)).all())
    np.testing.assert_array_equal(nop, sample_no_points(slides, per_slide=3, seed=0))

def test_no_points_are_uniform_over_overlapping_discs(self):  # 100 slides on one spot + 1 alone: about half each side
    slides = np.r_[np.zeros((100, 2)), [[10000., 0.]]]
    nop = sample_no_points(slides, per_slide=3, seed=0)
    near_lone = (np.hypot(nop[:, 0] - 10000, nop[:, 1]) < 2000).mean()
    self.assertGreater(near_lone, 0.35); self.assertLess(near_lone, 0.65)

def test_scar_point_is_the_highest_cell(self):
    self.assertEqual(scar_point(self.square_on_slope, self.grid, self.slope_dem), self.top_cell_centre_ll)

def test_every_point_in_one_tile_inner_square(self):
    t = tiles_for(self.points_ll)
    self.assertEqual(sorted(np.concatenate([x['index'] for x in t]).tolist()), list(range(len(self.points_ll))))

def test_training_table_has_no_coordinates(self):
    write_table(self.rows, self.meta, self.tmp / 't.csv', self.tmp / 't.json')
    head = (self.tmp / 't.csv').read_text(encoding='utf-8').splitlines()[1]
    self.assertEqual(head.split(','), list(TABLE_COLUMNS))  # line 0 is the ODbL notice
    self.assertNotIn('lat', head); self.assertNotIn('lon', head)
```

- [ ] **Step 2: Run** `... manage.py test tests.test_landslide_training_table ...` — Expected: FAIL.
- [ ] **Step 3: Implement `sample_no_points`** (rejection sampling, uniform over the union of discs):

```python
rng = np.random.default_rng(seed); tree = cKDTree(slides_xy); out = []
while len(out) < per_slide * len(slides_xy):
    c = slides_xy[rng.integers(len(slides_xy))]
    r, a = radius_m * np.sqrt(rng.random()), 2 * np.pi * rng.random()
    p = c + r * np.array([np.cos(a), np.sin(a)])
    if tree.query(p)[0] < min_gap_m: continue
    k = len(tree.query_ball_point(p, radius_m))   # discs covering p
    if rng.random() < 1.0 / k: out.append(p)
return np.asarray(out)
```

- [ ] **Step 4: Implement the command** (`--cache-dir`, default `backend/.hazard_cache`; `--events` to limit, for a trial): download and verify the inventories; build each event's slides (COOLR points; Mangkhut scar points); sample "no" points per event in local metres; for each tile: DEM (`fetch_copernicus`, cached per tile as `dem_cop30_{tag}.npy`), `terrain_grids`, roads and `road_distance`, `landcover_classes(year)` → `landcover_shares`, NOAH grid for Philippine events; `sample` at the tile's inner points; cache each tile's rows as `landslide_tile_{event}_{tag}.npz` so a rerun resumes. Apply the road check against Talisay's steep-ground density (computed from the Talisay grid of Task 5's `city_grid(pad_m=2000)`; the command builds that DEM if missing). Write the table and meta through `.tmp` and swap in. Print one line per event (slides, no points, road kept) and the total. Update ATTRIBUTION.md with the credits and the ODbL notice.
- [ ] **Step 5: Run the tests** — Expected: PASS (Tasks 1–3 tests still PASS).
- [ ] **Step 6: Leave uncommitted.**

### Task 5: `build_landslide_features` (Talisay scoring points)

**Files:**
- Create: `backend/apps/history/management/commands/build_landslide_features.py`
- Modify: `backend/apps/history/landslide_features.py` (add `scoring_points`, `LandslideFeatures`, `write_features`, `read_features`)
- Test: `backend/tests/test_landslide_features.py` (extend)

**Interfaces:**
- Consumes: Tasks 2–3; `susceptibility.city_grid`, `load_inputs`; `fire_sources.footprints`; `flood_features.membership`; `Purok.outlines_version()`.
- Produces:
  - `road_points(lines: list, step_m: float = 20) -> np.ndarray` (lon, lat; includes each line's start; no duplicates within 1 m)
  - `scoring_points(buildings_ll: np.ndarray, roads: list, city) -> tuple[np.ndarray, np.ndarray]` → (points lon/lat, kind: 0 building, 1 road), only inside the city
  - `LandslideFeatures` dataclass `(points: dict[str, np.ndarray], membership: tuple[np.ndarray, np.ndarray], areas: list[dict], meta: dict)`; `points` holds every `FEATURE_COLUMNS` array, `noah_class`, `kind`, `lon`, `lat` (the npz in the cache dir only)
  - `write_features(features, csv_path=FEATURES_FILE, meta_path=FEATURES_META, cache_dir=None)`; `read_features(csv_path=FEATURES_FILE, meta_path=FEATURES_META, cache_dir=None) -> LandslideFeatures`
  - `GRIDS_FILE = 'landslide_feature_grids.npz'` (cache dir: the Talisay clue grids, the grid's zoom and origin); `features_at(points_ll: np.ndarray, cache_dir) -> dict[str, np.ndarray]` (every `FEATURE_COLUMNS` value and `noah_class` at any Talisay point; the January job uses it for own spots and their "no" points)
  - CSV columns: `purok_id, barangay_id, barangay, name, confidence, points, buildings, road_points, noah_p90` (no coordinates). Meta: `outlines_version`, `landcover_year`, `landcover_ok`, `talisay_steep_road_density`, counts.

- [ ] **Step 1: Write the failing tests**

```python
def test_road_points_every_20_m(self):
    line = [(123.85, 10.25), (123.85 + 100 / (111320 * np.cos(np.radians(10.25))), 10.25)]  # 100 m east
    self.assertEqual(len(road_points([line], step_m=20)), 6)

def test_scoring_points_are_inside_the_city_and_tagged(self):
    pts, kind = scoring_points(self.buildings_ll, [self.road_line], self.city)
    self.assertTrue(set(kind.tolist()) <= {0, 1}); self.assertEqual(int((kind == 0).sum()), self.buildings_inside)

def test_features_csv_has_no_coordinates(self):
    write_features(self.features, self.tmp / 'f.csv', self.tmp / 'f.json', cache_dir=self.tmp)
    self.assertNotIn('lat', (self.tmp / 'f.csv').read_text(encoding='utf-8').splitlines()[0])
```

- [ ] **Step 2: Run** `... manage.py test tests.test_landslide_features ...` — Expected: FAIL.
- [ ] **Step 3: Implement** the functions and the command (`--cache-dir`, `--output-dir` defaulting to `DATA_DIR`, as `build_flood_features` has for the job): Talisay grid `city_grid(extent, pad_m=2000)`, DEM via `load_inputs`, `terrain_grids`, roads from the cached OSM file's `roads` lines, `landcover_classes(newest year)`, NOAH Cebu grid; sample at scoring points; membership by area; write CSV, meta and the points npz. Print counts per kind and the land cover year.
- [ ] **Step 4: Run** — Expected: PASS.
- [ ] **Step 5: Leave uncommitted.**

### Task 6: Training core (candidates, folds, rules, cut-offs, purok scores, fallback, stability)

**Files:**
- Create: `backend/apps/history/landslide_training.py`
- Test: `backend/tests/test_landslide_training.py`

**Interfaces:**
- Consumes: `flood_rules.auc_gain`, `auc_score`, `cutoff_walk`, `classify`, `Cutoffs`, `uncertain_puroks`; `flood_training.in_range`. Arrays only: no database, no files.
- Produces:
  - `CANDIDATES = ('neural_network', 'logistic_regression', 'xgboost')`, `PH_FOLDS = ('egay', 'mangkhut', 'paeng', 'agaton')`, `MONOTONE`, `ASSESSED_SHARE = 0.5`, `P90 = 90`, `NO_POINTS = 'No buildings or roads in this area'`, `UNLIKE = 'Its ground is unlike the areas the model learned from'`
  - `design_matrix(table: dict, columns: tuple, medians: dict | None) -> tuple[np.ndarray, tuple]` → (X, column names); `LOG_COLUMNS` → `log1p`; `medians=None` keeps `NaN` (xgboost), else fills and appends `road_unknown`
  - `fit(name, X, y, w, columns, seed=0)`; `score(name, model, X) -> np.ndarray` (0–1)
  - `out_of_fold(name, table, columns, folds_scored: tuple, w, seed=0) -> np.ndarray` (score per row; rows whose fold is not in `folds_scored`, e.g. world, stay `NaN` and are always in training)
  - `world_test(table, columns, seed=0, reps=1000) -> dict` → `{'joined': bool, 'gain': float, 'lo': float, 'hi': float}`
  - `choose(oof: dict[str, np.ndarray], y, folds, reps=1000, seed=0) -> tuple[str, dict]` → (chosen, per-candidate `{auc, gain_over_nn, lo, hi}`)
  - `point_cutoffs(scores: np.ndarray, y: np.ndarray, w: np.ndarray) -> Cutoffs` (wraps `cutoff_walk` with points as units)
  - `prepare_talisay(points: dict, train_table: dict, columns) -> tuple[dict, np.ndarray]` → (clipped point table, in-range mask on `TERRAIN_COLUMNS`)
  - `purok_scores(point_scores, membership, valid, total_per_purok: dict) -> dict[int, dict]` → `{pid: {'score', 'valid', 'total', 'assessed'}}` (score = 90th percentile of valid points)
  - `not_assessed_reason(total: int, valid: int) -> str | None`
  - `stability(name, table, columns, w, point_X, membership, valid, totals, cutoffs, reps=200, seed=0) -> list[dict[int, str]]`

- [ ] **Step 1: Write the failing tests** (synthetic arrays)

```python
def test_missing_roads_are_filled_with_an_indicator_except_for_xgboost(self):
    X, cols = design_matrix(self.table_with_nan_road, FEATURE_COLUMNS, medians={'dist_road_m': 50.0})
    self.assertIn('road_unknown', cols); self.assertFalse(np.isnan(X).any())
    X2, cols2 = design_matrix(self.table_with_nan_road, FEATURE_COLUMNS, medians=None)
    self.assertNotIn('road_unknown', cols2); self.assertTrue(np.isnan(X2).any())

def test_out_of_fold_never_scores_a_fold_with_a_model_that_saw_it(self):  # a marker column true only in egay slides
    s = out_of_fold('logistic_regression', self.marked, self.cols, PH_FOLDS, self.w)
    self.assertLess(np.nanmean(s[self.egay_slides]), self.seen_egay_mean - 0.2)
    self.assertTrue(np.isnan(s[self.world_rows]).all())

def test_the_nn_is_kept_unless_clearly_worse(self):
    same = {n: self.oof_good.copy() for n in CANDIDATES}
    self.assertEqual(choose(same, self.y, self.folds)[0], 'neural_network')
    better_lr = {**same, 'neural_network': self.oof_noise}
    self.assertEqual(choose(better_lr, self.y, self.folds)[0], 'logistic_regression')

def test_flat_built_up_purok_is_green_not_grey(self):
    clipped, valid = prepare_talisay(self.flat_city_points, self.mountain_table, FEATURE_COLUMNS)
    self.assertTrue(valid.all())  # terrain is in range; built-up share and road distance are clipped
    self.assertLessEqual(clipped['lc_built'].max(), np.percentile(self.mountain_table['lc_built'], 99) + 1e-9)
    out = purok_scores(np.full(len(valid), 0.01), self.one_purok_membership, valid, {7: len(valid)})
    self.assertTrue(out[7]['assessed'])
    self.assertEqual(classify(out[7]['score'], self.cutoffs_from_mountains), 'Green')

def test_purok_score_is_the_90th_percentile(self):
    out = purok_scores(np.arange(10) / 10, (np.arange(10), np.full(10, 3)), np.ones(10, bool), {3: 10})
    self.assertAlmostEqual(out[3]['score'], np.percentile(np.arange(10) / 10, 90))
    self.assertEqual(not_assessed_reason(0, 0), NO_POINTS); self.assertEqual(not_assessed_reason(10, 4), UNLIKE)
    self.assertIsNone(not_assessed_reason(10, 5))

def test_point_cutoffs_weight_own_slides(self):
    c = point_cutoffs(np.array([.9, .8, .7, .1]), np.array([1, 1, 0, 0]), np.array([1., 10., 1., 1.]))
    self.assertEqual(c.red, .8)  # the weight-10 slide at .8 holds half the weighted slides

def test_world_rows_join_only_when_they_help(self):
    self.assertFalse(world_test(self.table_world_noise, self.cols)['joined'])
```

- [ ] **Step 2: Run** `... manage.py test tests.test_landslide_training ...` — Expected: FAIL.
- [ ] **Step 3: Implement** with the Global Constraints' settings. `choose` computes each candidate's `auc_gain(candidate over neural_network)` on the Philippine (and own) folds; `world_test` builds both NN variants per held-out Philippine fold. `stability` resamples rows within each fold (slides and "no" points separately), refits, rescores Talisay, and reclassifies with the fixed `cutoffs`.
- [ ] **Step 4: Run** — Expected: PASS.
- [ ] **Step 5: Leave uncommitted.**

### Task 7: `train_landslide_model` (orchestration, order, gates, files, report)

**Files:**
- Create: `backend/apps/history/landslide_run.py`, `backend/apps/history/management/commands/train_landslide_model.py`
- Test: `backend/tests/test_landslide_run.py`

**Interfaces:**
- Consumes: Tasks 4–6.
- Produces:
  - `MODES = ('outside', 'own')`; `CODE_FILES = ('landslide_training.py', 'landslide_run.py', 'landslide_features.py')`; `code_digest() -> str`
  - `run(table: dict, table_meta: dict, features: LandslideFeatures, load_tests: Callable[[], dict], log=print, report=None, fingerprint: str = '', reps: int = 1000, stability_reps: int = 200, built_at: str | None = None, mode: str = 'outside', own_rows: dict | None = None) -> tuple[dict, dict]` (`table`, `table_meta` = `read_table()`). `load_tests()` returns `{'test_puroks': list[int], 'barangay_records': list[dict], 'catalogue_purok_ids': list[int | None]}` and is called only after `report['training_set']`, `report['choice']` and `report['cutoffs']` are set. In `'own'` mode `own_rows` is a table like `training` with fold `talisay`, weight 10, and `test_puroks` are the held-back season's puroks.
  - Model JSON: `version` (`"<chosen | noah_fallback>@<sha1 of training csv + features csv + settings + code_digest, 12 chars>"`), `source` (`'model' | 'noah' | 'geoalert'`), `chosen`, `training_set` (`'ph' | 'ph+world'`), `built_at` (ISO, Manila), `outlines_version`, `cutoffs`, `clip_ranges` (per `CLIP_COLUMNS`: p1, p99), `inputs` (sha1 per file, `landcover_ok`), `areas: {purok_id: {barangay_id, level, score, uncertain, not_assessed_reason, estimated_outline, points}}`.
  - Report JSON: `version`, `source`, `training_set` (`events` [{event, fold, region, slides}], `world` {joined, gain, lo, hi}), `candidates`, `choice`, `acceptance` (`adopted`, `gates`, `reasons`), `cutoffs`, `talisay_test` (`puroks` [{name, level}], `barangay_check`, `catalogue` [{level}]), `in_range` (share, clipped points per column), `road_check`, `classes`, `limits`, `credits`; own mode adds `own_spots`, `season`, `temporal_test.held_back` [{purok_id, level}].

- [ ] **Step 1: Write the failing tests** (synthetic table and features, stub `load_tests`)

```python
def test_tests_load_only_after_the_training_set_choice_and_cutoffs(self):
    seen = {}; report = {}
    def load_tests():
        seen.update({k: k in report for k in ('training_set', 'choice', 'cutoffs')}); return self.tests_ok
    run(self.table, self.table_meta, self.features, load_tests, report=report, reps=50, stability_reps=5)
    self.assertEqual(seen, {'training_set': True, 'choice': True, 'cutoffs': True})

def test_a_failed_gate_ships_the_noah_fallback(self):  # test puroks placed where the model says Green
    model, report = run(self.table, self.table_meta, self.features, lambda: self.tests_in_green, reps=50, stability_reps=5)
    self.assertEqual(model['source'], 'noah'); self.assertTrue(model['version'].startswith('noah_fallback@'))
    self.assertFalse(report['acceptance']['adopted']); self.assertTrue(report['acceptance']['reasons'])

def test_every_area_has_a_level_or_a_reason(self):
    model, _ = run(self.table, self.table_meta, self.features, lambda: self.tests_ok, reps=50, stability_reps=5)
    for a in model['areas'].values():
        self.assertTrue((a['level'] in ('Red', 'Orange', 'Green')) != bool(a['not_assessed_reason']))

def test_no_coordinates_in_the_written_files(self):
    model, report = run(self.table, self.table_meta, self.features, lambda: self.tests_ok, reps=50, stability_reps=5)
    text = json.dumps([model, report])
    for lon, lat in zip(self.features.points['lon'][:50], self.features.points['lat'][:50]):
        self.assertNotIn(f'{lat:.4f}', text); self.assertNotIn(f'{lon:.4f}', text)

def test_no_test_puroks_fails_gate_two(self):
    _, report = run(self.table, self.table_meta, self.features, lambda: {**self.tests_ok, 'test_puroks': []}, reps=50, stability_reps=5)
    self.assertFalse(report['acceptance']['gates']['talisay_test'])
```

- [ ] **Step 2: Run** `... manage.py test tests.test_landslide_run ...` — Expected: FAIL.
- [ ] **Step 3: Implement `run`** in the order: rule 1 → `report['training_set']`; out-of-fold for each candidate and B0 → rule 2 → `report['choice']`; final fit; Talisay `prepare_talisay`, scores, `purok_scores`; `point_cutoffs` on the chosen out-of-fold points → `report['cutoffs']`; classes; gate 1 and gate 3; only then `load_tests()` and gate 2; on any fail, the NOAH fallback classes; stability on the shipped classes (the fallback has none); assemble the files.
- [ ] **Step 4: Implement the command** (`--cache-dir`): reads the table and features; `load_tests` reads Landslide records and "Affected" marks on Landslide zones read-only (a point's smallest purok, a record's linked puroks), barangay records for the barangay check, and NASA catalogue points inside the city with `location_accuracy` in (`exact`, `1km`) from `.hazard_cache/nasa_global_landslide_catalog.csv` mapped to their purok; writes both JSON files through `.tmp` and swaps them in, as `train_flood_model` does. Prints one verdict line.
- [ ] **Step 5: Run** — Expected: PASS.
- [ ] **Step 6: Leave uncommitted.**

### Task 8: Serving: `landslide_purok.py`, the forecast API, the accuracy entry, readiness

**Files:**
- Create: `backend/apps/history/landslide_purok.py`, `backend/apps/history/landslide_own.py` (constants, the four sentences and `floor()` only; Task 10 adds the rest)
- Modify: `backend/apps/history/views.py` (`FORECAST_HAZARDS`, `FORECAST_ONLY`, `SUSCEPTIBILITY_NOT_BY_MONTH`, `parse_hazards`, `forecast_result`, `ForecastAccuracyView`, new `landslide_accuracy_entry`, `FloodReadinessView` response), `backend/apps/history/flood_purok.py` (`located_spots(hazard_name='Flood')`, `located_floods(since=None, hazard_name='Flood')`: a default argument only; flood behaviour unchanged), `README.md` (a short "Landslide predictive analytics" paragraph: what it shows, the three commands, the sources)
- Test: `backend/tests/test_landslide_purok.py`, `backend/tests/test_forecast_api.py` (extend), `backend/tests/test_flood_readiness.py` (extend)

**Interfaces:**
- Consumes: `MODEL_FILE`, `REPORT_FILE` (Task 2); `model_fits.live_fit_head`, `fit_body`, `newer_is_fit` (as `flood_purok.load` uses them); `flood_rules.monitoring`.
- Produces:
  - `LandslideModel` dataclass `(version, source, built_at, areas: dict[int, dict], cutoffs: dict, report: dict | None)`; `parse(model, report, outlines) -> LandslideModel | str`; `load() -> LandslideModel | str` (60 s recheck, stale check, live fit vs file by `built_at`); `clear_cache()`
  - `purok_rows(model) -> list[dict]` → `{purok_id, barangay_id, level, uncertain, not_assessed_reason, estimated_outline}`
  - `landslide_block(model | str) -> dict` → `{available, reason, source, model_version, built_at, basis, varies_by_month: False}`; `basis(model) -> str` (`BASIS_MODEL` / `BASIS_NOAH` / `BASIS_GEOALERT`)
  - `located_landslides(since=None) -> list` and `located_spots() -> list` (via the flood functions with `hazard_name='Landslide'`)
  - `since_publishing(model) -> dict`; `readiness_line() -> dict` → `{'n', 'barangays', 'needed': 30, 'barangays_needed': 3, 'enough'}` (from `landslide_own.floor(located_spots())`)
  - `landslide_own`: `OWN_MIN_SPOTS = 30`, `OWN_MIN_BARANGAYS = 3`, `HELD_MIN = 5`, `OWN_WEIGHT = 10`, `LANDSLIDE_FLOOR`, `LANDSLIDE_HELD`, `LANDSLIDE_WORSE`, `LANDSLIDE_SWITCHED`, `floor(spots) -> dict` (`{n, barangays, enough}`)
  - `views.landslide_accuracy_entry() -> dict` (`kind: 'landslide_purok'`); the readiness response gains `landslide_spots` (= `readiness_line()`).

- [ ] **Step 1: Write the failing tests**

```python
def test_landslide_only_request(self):
    data = self.get('/api/history/forecast/?hazards=Landslide&month=7').data
    self.assertEqual(data['results'], []); self.assertEqual(data['profile_reason'], NOT_BY_MONTH)
    self.assertTrue(data['landslide']['available']); self.assertFalse(data['landslide']['varies_by_month'])
    self.assertNotIn('flood_results', data)

def test_flood_and_landslide_without_fire(self):
    data = self.get('/api/history/forecast/?hazards=Flood,Landslide').data
    self.assertEqual(data['profile_reason'], SUSCEPTIBILITY_NOT_BY_MONTH)

def test_landslide_is_the_same_for_every_period(self):
    a = self.get('/api/history/forecast/?hazards=Fire,Landslide&month=1').data['landslide_results']
    b = self.get('/api/history/forecast/?hazards=Fire,Landslide&date=2027-11-15').data['landslide_results']
    self.assertEqual(a, b)

def test_stale_outlines_make_landslide_unavailable_only(self):
    self.write_model(outlines_version='old')
    data = self.get('/api/history/forecast/?hazards=Fire,Flood,Landslide').data
    self.assertEqual((data['landslide']['available'], data['landslide']['reason']), (False, STALE))
    self.assertEqual(data['landslide_results'], []); self.assertNotEqual(data['results'], [])
    self.assertIn('flood_results', data)

def test_unknown_names_are_refused(self):
    r = self.get('/api/history/forecast/?hazards=Tsunami')
    self.assertEqual((r.status_code, r.data['error']), (400, FORECAST_ONLY))

def test_accuracy_lists_fire_flood_landslide(self):
    kinds = [h['kind'] for h in self.get('/api/history/forecast/accuracy/').data['hazards']]
    self.assertEqual(kinds, ['fire_purok', 'flood_purok', 'landslide_purok'])

def test_readiness_has_the_landslide_line_and_no_location(self):
    data = self.get('/api/history/forecast/readiness/').data
    self.assertEqual({k: data['landslide_spots'][k] for k in ('needed', 'barangays_needed')}, {'needed': 30, 'barangays_needed': 3})
    self.assertNotRegex(json.dumps(data), r'\d+\.\d{4}')
```

- [ ] **Step 2: Run** `... manage.py test tests.test_landslide_purok tests.test_forecast_api tests.test_flood_readiness ...` — Expected: FAIL.
- [ ] **Step 3: Implement.** Keep the existing error key and shape `parse_hazards` uses. `forecast_result` adds `landslide` and `landslide_results` only when Landslide is asked; with no Fire, `profile_reason` is flood's, landslide's or `SUSCEPTIBILITY_NOT_BY_MONTH` by what was asked; with Landslide alone the basis method is the landslide basis. Fire and flood assertions already in `test_forecast_api` keep passing.
- [ ] **Step 4: Run** those modules plus `tests.test_flood_purok tests.test_fire_purok tests.test_forecast` — Expected: PASS.
- [ ] **Step 5: Leave uncommitted.**

### Task 9: Insert-only landslide log (migration `history 0013`)

**Files:**
- Modify: `backend/apps/history/models.py` (new `LandslidePurokSusceptibilityLog`), `backend/apps/history/prediction_log.py` (new `write_landslide_rows`, called where `write_flood_rows` is), `backend/apps/history/management/commands/log_hazard_predictions.py`
- Create: `backend/apps/history/migrations/0013_landslide_purok_susceptibility_log.py`
- Test: `backend/tests/test_landslide_log.py`

**Interfaces:**
- Produces:
  - Model `LandslidePurokSusceptibilityLog`, table `landslide_purok_susceptibility_log`, columns `lpsl_id` (BigAuto), `lpsl_purok_id` (integer, no FK), `lpsl_purok_name`, `lpsl_brgy_id` (FK Barangay, PROTECT), `lpsl_model_version`, `lpsl_source`, `lpsl_level` (null or Red/Orange/Green, check constraint), `lpsl_score` (float, null), `lpsl_uncertain` (bool), `lpsl_not_assessed_reason` (text, default ''), `lpsl_outlines_version`, `lpsl_published_on` (date, Manila), `lpsl_created_at`; unique (`purok_id`, `model_version`); insert-only trigger copied from 0011.
  - `prediction_log.write_landslide_rows(today) -> int` (0 without `HAZARD_LOG_WRITER` or with the model unavailable; `bulk_create(ignore_conflicts=True)`).

- [ ] **Step 1: Write the failing tests** — the three tests of the flood plan's Task 7 with `write_landslide_rows` and `LandslidePurokSusceptibilityLog` / `lpsl_level` in place of the flood names (`test_rows_once_per_version`, `test_nothing_without_the_writer_setting`, `test_rows_cannot_change`).
- [ ] **Step 2: Run** `... manage.py test tests.test_landslide_log ...` — Expected: FAIL.
- [ ] **Step 3: Implement** the model, the migration (depends on `0012_model_fit`), `write_landslide_rows`, and the command logging all three; a missing model never stops the others' rows.
- [ ] **Step 4: Run** `tests.test_landslide_log tests.test_flood_log tests.test_prediction_log` and `manage.py makemigrations --check --dry-run --settings=geo_test_settings_landslide` — Expected: PASS; "No changes detected".
- [ ] **Step 5: Leave uncommitted.** Do **not** migrate the shared database (Task 14).

### Task 10: The January job: own landslides (migration `history 0014`)

**Files:**
- Create: `backend/apps/history/migrations/0014_model_fit_landslide.py`
- Modify: `backend/apps/history/landslide_own.py` (add `own_rows`), `backend/apps/history/models.py` (`MODEL_FIT_HAZARDS` += `'landslide'`), `backend/apps/history/model_fits.py` (`LANDSLIDE_SEASON_LOCK`, the season lock for landslide, `site_check`, `training_data('landslide')`), `backend/apps/history/model_job.py` (`landslide_attempt`), `backend/apps/history/management/commands/run_model_job.py` (`--hazard landslide`), `backend/apps/history/views.py` (`ModelJobDataView` accepts `landslide`), `.github/workflows/model-retrain.yml`
- Test: `backend/tests/test_landslide_own.py`, `backend/tests/test_model_job.py` (extend), `backend/tests/test_model_fits.py` (extend), `backend/tests/test_model_job_api.py` (extend)

**Interfaces:**
- Consumes: `flood_own.season_split`, `local_day`, `compare`; `landslide_purok.located_spots`, `load`; Tasks 4–7.
- Produces:
  - `landslide_own.own_rows(spots: list[dict], features_at: Callable, seed: int = 0) -> dict` (spots as slides plus their "no" points from `sample_no_points`, fold `talisay`, weight `OWN_WEIGHT`, clues from Task 5's `features_at`); the constants and `floor()` come from Task 8
  - `model_job.landslide_attempt(data: dict, today, cache: Path, workdir: Path, reps: int, stability_reps: int, log, fetch=fetch) -> dict`
  - `training_data('landslide')` → `{'hazard': 'landslide', 'outlines_version', 'spots', 'floor', 'live'}` (+ outlines with `outlines=1`), live as flood's.
  - Workflow: cron `'17 19 5 1 *'` (landslide, 03:17 Manila on 6 January); `workflow_dispatch` option `landslide`; `HAZARD` resolves the new cron to `landslide`; `timeout-minutes: ${{ (inputs.hazard == 'landslide' || github.event.schedule == '17 19 5 1 *') && 360 || 120 }}`; the job passes `--stability-reps 100` for landslide.

- [ ] **Step 1: Write the failing tests**

```python
def test_floor_at_and_around_30_spots_and_3_barangays(self):
    self.assertFalse(floor(self.spots(29, barangays=3))['enough']); self.assertFalse(floor(self.spots(30, barangays=2))['enough'])
    self.assertTrue(floor(self.spots(30, barangays=3))['enough'])

def test_below_the_floor_is_not_tried_and_trains_nothing(self):
    a = landslide_attempt({'spots': self.spots(2, barangays=1), 'live': None, 'outlines_version': 'v'}, date(2027, 1, 6), ...)
    self.assertEqual((a['result'], a['reason']), ('not_tried', '2 of 30 located landslide spots, 1 of 3 barangays'))
    self.assertNotIn('model', a)

def test_too_few_held_back_spots(self):
    a = landslide_attempt(self.data(spots=self.spots(40, barangays=4, season_2026=4)), date(2027, 1, 6), ...)
    self.assertEqual(a['reason'], 'Too few new spots to test (4 of 5); tries again next January')

def test_fewer_season_hits_is_kept(self):  # live own-data map catches 5 of 5, the new fit 4 of 5
    self.assertEqual(self.attempt_with(new_hits=4, live_hits=5, live_source='geoalert')['result'], 'kept')

def test_a_tie_switches(self):
    self.assertEqual(self.attempt_with(new_hits=5, live_hits=5, live_source='geoalert')['result'], 'switched')

def test_switch_outside_january_to_may_is_kept(self):  # model_fits.record_attempt, Manila July
    with freeze_manila(2027, 7, 1):
        fit = record_attempt(self.switched_landslide_payload, 'v', check=None)
    self.assertEqual((fit.result, fit.reason, fit.is_live), ('kept', LANDSLIDE_SEASON_LOCK, False))

def test_job_prints_and_posts_no_coordinate(self):
    lines = []; a = landslide_attempt(self.data_enough, date(2027, 1, 6), ..., log=lines.append)
    self.assertNotRegex(' '.join(lines) + json.dumps(a), r'\b1[0-9]\.\d{4}|\b12[0-9]\.\d{4}')

def test_data_endpoint_serves_landslide_with_the_token_only(self):
    self.assertEqual(self.client.get('/api/history/model-job/data/?hazard=landslide').status_code, 401)
    self.assertEqual(self.token_get('/api/history/model-job/data/?hazard=landslide').data['hazard'], 'landslide')
```

- [ ] **Step 2: Run** `... manage.py test tests.test_landslide_own tests.test_model_job tests.test_model_fits tests.test_model_job_api ...` — Expected: FAIL.
- [ ] **Step 3: Implement.** `landslide_attempt`: floor → held-back split (`season_split`) → `load_outlines` → `build_landslide_features` into `workdir` → the committed training table (`read_table`) → `own_rows` from training spots → `landslide_run.run(mode='own', own_rows=…, stability_reps=stability_reps)` with the held-back season's puroks as `test_puroks` → kept on any failed gate (reasons joined), kept when `compare` gives fewer hits than a live `geoalert` map, else switched with `LANDSLIDE_SWITCHED`. The model's `outlines_version` is set to the server's, as flood does. Migration 0014 replaces the `model_fit_hazard` check constraint (remove and add) and alters the field's choices.
- [ ] **Step 4: Run** those modules — Expected: PASS. Then `manage.py makemigrations --check --dry-run` — "No changes detected".
- [ ] **Step 5: Leave uncommitted.** Do **not** migrate the shared database (Task 14).

### Task 11: Retire the weighted landslide layer; guards

**Files:**
- Modify: `backend/apps/hazards/susceptibility.py` (`FACTORS`, `build_layers`, `barangay_stats`), `frontend/public/hazard-index/index.json`, `frontend/public/hazard-index/all.png`; delete `frontend/public/hazard-index/landslide.png`
- Test: `backend/tests/test_hazard_index.py` (extend), `backend/tests/test_landslide_guards.py`

**Interfaces:**
- Consumes: `susceptibility.drop_layer` and `build_hazard_index --drop-layer` (both exist from the flood build).

- [ ] **Step 1: Write the failing tests**

```python
def test_no_hand_weighted_landslide_layer(self):
    self.assertNotIn('landslide', FACTORS)
    layers = build_layers(self.factors, self.city_mask)
    self.assertNotIn('landslide', layers)

def test_no_setting_or_view_can_change_a_landslide_prediction(self):
    self.assertFalse([k for k in SETTINGS if 'landslide' in k.lower()])
    for path in Path(settings.BASE_DIR, 'apps').rglob('views*.py'):
        self.assertNotIn('landslide_purok_model', path.read_text(encoding='utf-8'))

def test_model_inputs_are_the_allowlist(self):
    self.assertEqual(FEATURE_COLUMNS, ('slope_deg', 'relief_m', 'profile_curv', 'plan_curv', 'hand_m', 'twi',
        'dist_stream_m', 'dist_road_m', 'lc_trees', 'lc_rangeland', 'lc_crops', 'lc_built', 'lc_bare'))
    table = {c: np.ones(4) for c in (*FEATURE_COLUMNS, 'noah_class', 'label')}  # noah_class sits in every table
    _, cols = design_matrix(table, FEATURE_COLUMNS, medians={'dist_road_m': 1.0})
    self.assertEqual(set(cols) - set(FEATURE_COLUMNS), {'road_unknown'})  # noah_class never reaches a model
    self.assertNotIn('HistoricalRecord', Path(landslide_training.__file__).read_text(encoding='utf-8'))
```

- [ ] **Step 2: Run** `... manage.py test tests.test_hazard_index tests.test_landslide_guards ...` — Expected: FAIL.
- [ ] **Step 3: Implement.** Remove `'landslide'` from `FACTORS` and `barangay_stats`; `build_layers` keeps `fire` and builds `all` as the fire layer; `FLAT_SLOPE_DEG` goes if nothing else reads it. Check every reader of `all` and `landslide` in `frontend/src` (`SpotReading`, `LayerControl`, `hazardInfo`) and list them in the task notes; a reader of the removed layer shows nothing for it rather than breaking.
- [ ] **Step 4: Run** the tests, then `venv/Scripts/python.exe manage.py build_hazard_index --drop-layer landslide --out ../frontend/public/hazard-index` (the flood build's option). Check `index.json` has no `landslide` key and `landslide.png` is gone; `terrain.png` and `elevation.png` untouched.
- [ ] **Step 5: Run the full backend suite** — Expected: all pass (list any older test updated).
- [ ] **Step 6: Leave uncommitted.**

### Task 12: Frontend: Landslide in "Likely by month", the panel list, "This spot"

**Files:**
- Modify: `frontend/src/components/Forecast/forecastLevels.js`, `frontend/src/pages/PublicMap.jsx`, `frontend/src/components/Map/FloodPuroks.jsx`, `frontend/src/components/Map/FloodOverlay.jsx`, `frontend/src/components/Map/BarangayPanel.jsx`, `frontend/src/components/Map/SpotReading.jsx`, `frontend/src/utils/spotText.js`
- Test: `frontend/src/components/Forecast/forecastLevels.test.js`, `frontend/src/components/Map/floodPuroks.test.js`, `frontend/src/utils/spotText.test.js`

**Interfaces:**
- Consumes: forecast `landslide` and `landslide_results` (Task 8).
- Produces:
  - `hazardsParam(types)` over `['Fire', 'Flood', 'Landslide']`
  - `purokLikelyLevels(likely)` adds `Landslide: {level, uncertain, not_assessed_reason, estimated_outline}`
  - `LANDSLIDE_WORD`, `landslideLegend(source)`, `susceptibilityTip(row, name, words)` (`floodTip` and new `landslideTip` call it), `FORECAST_ONLY_NOTE` (new copy)
  - `FloodPuroks` gains `words` (default `FLOOD_WORD`); `FloodOverlay` gains `hazard` (default `'Flood'`)
  - `describeSusceptibilityAtSpot(entry, label, words)` (`describeFloodAtSpot` calls it); `SpotReading` gains `landslide`

- [ ] **Step 1: Write the failing tests**

```js
test('hazardsParam asks for every ticked predicted hazard', () => {
  expect(hazardsParam(['Landslide', 'Fire'])).toBe('Fire,Landslide');
  expect(hazardsParam(['Fire', 'Flood', 'Landslide'])).toBe('Fire,Flood,Landslide');
});
test('three hazards: the highest level fills and each is named', () => {
  const levels = purokLikelyLevels({ purok_results: [{ purok_id: 4, level: 'Orange', probability: 0.02 }],
    flood_results: [{ purok_id: 4, level: null, uncertain: false, not_assessed_reason: 'Outside the surveyed floodplain' }],
    landslide_results: [{ purok_id: 4, level: 'Red', uncertain: false, not_assessed_reason: '' }] });
  expect(purokLevel(levels.get('4'), ['Fire', 'Flood', 'Landslide'])).toBe('Red');
  expect(landslideTip(levels.get('4').Landslide, 'Landslide')).toBe('Landslide: High landslide susceptibility');
});
test('landslide unavailable at a spot shows the reason', () => {
  expect(describeSusceptibilityAtSpot({ available: false, reason: 'The landslide model has not been trained yet.' }, 'Landslide', LANDSLIDE_WORD))
    .toBe('Landslide: unavailable (The landslide model has not been trained yet.)');
});
test('the panel list uses the landslide words', () => {
  render(<FloodPuroks rows={[{ purok_id: 1, level: 'Orange' }]} purokNames={{ 1: 'Camp 6' }} words={LANDSLIDE_WORD} />);
  expect(screen.getByText(/Moderate landslide susceptibility/)).toBeInTheDocument();
});
```

- [ ] **Step 2: Run** `CI=true npm test -- --watchAll=false src/components src/utils` — Expected: FAIL.
- [ ] **Step 3: Implement.** `PublicMap.jsx`: `PREDICTED = ['Fire', 'Flood', 'Landslide']`, `TICK_NOTE` new copy, a second `<FloodOverlay hazard="Landslide">`, the landslide legend line or its unavailable reason, a Landslide line in the purok and barangay hovers, the panel's landslide list (`<FloodPuroks words={LANDSLIDE_WORD}>`), the 12-month chart text when no Fire is ticked (from the response's `profile_reason`), and the "This spot" landslide line fetched once with `hazards: 'Landslide'` beside flood's. Past hazards paths are unchanged.
- [ ] **Step 4: Run** the whole frontend suite and `npm run build` — Expected: all pass; compiles with no "not defined" or "unused" errors.
- [ ] **Step 5: Leave uncommitted.**

### Task 13: Frontend: the accuracy section, the readiness line, Model updates

**Files:**
- Modify: `frontend/src/components/Forecast/ForecastAccuracy.jsx`, `frontend/src/components/Forecast/FloodReadiness.jsx`, `frontend/src/components/Forecast/ModelUpdates.jsx`
- Test: `frontend/src/components/Forecast/forecastAccuracy.test.js`, `frontend/src/components/Forecast/floodReadiness.test.js`, `frontend/src/components/Forecast/modelUpdates.test.js`

**Interfaces:**
- Consumes: `landslide_accuracy_entry()` and the report keys (Tasks 7–8); readiness `landslide_spots` (Task 8); `model_fit` rows with `hazard: 'landslide'` (Task 10).
- Produces: `export function LandslideModelReport({ report })` rendering, in order: the source line (the basis text), the training set (events with slide counts and folds; whether the world events joined, with the gain and interval), the candidates table (pooled and per-fold AUC with intervals) and rule 2's verdict ("Neural network kept" or why a simpler model won), the acceptance verdict with each gate's sentence, the Talisay test (test puroks and levels, barangay check, catalogue points' levels), the in-range share and clipped counts, the class table, "Since publishing" (with `UNDER_REVIEW` when flagged), limits, credits. `ForecastAccuracyEntry` picks it for `kind === 'landslide_purok'`.

- [ ] **Step 1: Write the failing tests**

```js
test('the card shows the landslide verdict, the NN rule and credits', () => {
  render(<LandslideModelReport report={landslideReport} />);
  expect(screen.getByText(/Neural network kept/)).toBeInTheDocument();
  expect(screen.getByText(/Vershel et al\. \(2025\)/)).toBeInTheDocument();
});
test('under review is shown when monitoring flags it', () => {
  render(<LandslideModelReport report={{ ...landslideReport, since_publishing: { n: 12, in_red_orange: 8, under_review: true, misses: [] } }} />);
  expect(screen.getByText('Under review: recent landslides fall outside the flagged areas')).toBeInTheDocument();
});
test('the readiness card shows the landslide line', () => {
  renderReadiness({ ...readiness, landslide_spots: { n: 2, barangays: 1, needed: 30, barangays_needed: 3, enough: false } });
  expect(screen.getByText('Located landslide spots with a map point: 2 of 30, in 1 of 3 barangays')).toBeInTheDocument();
});
test('model updates name landslide rows', () => {
  renderUpdates([{ hazard: 'landslide', result: 'not_tried', reason: '2 of 30 located landslide spots, 1 of 3 barangays', created_at: '2027-01-06T03:17:00+08:00', is_live: false }]);
  expect(screen.getByText('Landslide')).toBeInTheDocument();
});
```

- [ ] **Step 2: Run** `CI=true npm test -- --watchAll=false src/components/Forecast` — Expected: FAIL.
- [ ] **Step 3: Implement.** Fire and flood sections unchanged.
- [ ] **Step 4: Run** the whole frontend suite and `npm run build` — Expected: PASS and compiled.
- [ ] **Step 5: Leave uncommitted.**

### Task 14: Real run and go-live steps (ask the user before each shared-database step)

**Files:**
- Produces: `backend/apps/history/data/landslide_training.csv`, `landslide_training.meta.json`, `landslide_purok_features.csv`, `landslide_purok_features.meta.json`, `landslide_purok_model.json`, `landslide_purok_report.json` (uncommitted; the user commits them)

- [ ] **Step 1 (shared database: ask first):** back up with `pg_dump` to `Downloads/Geoalert-Full-Backup-before-landslide-test-records-<date>.dump` and check the table and row counts. Show the user the two Purok Kaimito records (`7f9e98cc-e23f-4855-a39c-e7c2a2c4661f`, `049e301d-76f3-4beb-8c06-562d54e89328`) and their hazard zones (`c94e41e6-d4e0-4681-8b0a-3585c230ff62`, `5a43ed0d-0725-4f4d-89f3-a2d34e2222b5`), including anything else linked to those zones. On the user's yes, delete the two records and the two zones in one transaction. Expected after: 8 Landslide records, 2 with a point.
- [ ] **Step 2:** `venv/Scripts/python.exe manage.py build_landslide_training` (from `backend/`; long, resumable). Expected: 4 Philippine events plus 19 world, the road check line, `landcover_ok`, the table written. Record the NOAH SHA-256 values in `landslide_sources.NOAH_LANDSLIDE` if not yet pinned.
- [ ] **Step 3:** `manage.py build_landslide_features`. Expected: 670 areas; building and road point counts; the land cover year.
- [ ] **Step 4:** `manage.py train_landslide_model`. Expected: one verdict line (`neural_network` / another model adopted, or `noah_fallback` with the failed gates). Reading the shared database is read-only. Note the run time: it bounds the job's (Task 10's 360 minutes); if the stability step alone takes over 300 minutes, tell the user before go-live.
- [ ] **Step 5:** Show the user the report and the map on the stubbed local site (`C:/Users/Sannichigetsu/.geoalert-test/run_readonly_site.py`, backend 8001, frontend 3001): Landslide ticked, a not-assessed purok if any, an uncertain purok if any, all three hazards together, "This spot" in Manipis, the accuracy card, the readiness line. Wait for the user's word.
- [ ] **Step 6 (shared database: ask first):** back up to `Downloads/Geoalert-Full-Backup-before-history-0013-<date>.dump`, check the counts, then `manage.py migrate history 0014` (applies 0013 and 0014).
- [ ] **Step 7 (shared database: ask first):** `HAZARD_LOG_WRITER=true manage.py log_hazard_predictions` once. Expected: one landslide row per area; a rerun adds 0.
- [ ] **Step 8:** Full backend suite (private test database) and the whole frontend suite plus `npm run build`. Expected: all pass. Report `git status --short`; the user commits and pushes the code, the six data files and the workflow to `main`. **Leave uncommitted.**
- [ ] **Step 9 (with the user, after the deploy):** GitHub "Run workflow", hazard `landslide`, dry run ticked. Expected: "Not tried: 2 of 30 located landslide spots, 1 of 3 barangays", nothing posted.
