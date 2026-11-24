# Flood susceptibility by purok — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add flood to GeoAlert's predictive analytics ("Likely by month"): a Red/Orange/Green flood-susceptibility level per purok from a machine-learning model trained offline on the 2017 UP Mananga survey's 169 located flood reports, with NOAH and terrain inputs, "not assessed yet" outside the evidence, and no human able to touch a prediction.

**Architecture:** Offline commands build per-building flood features from static layers (`build_flood_features`), then train, choose and gate the candidates against NOAH-only and write a model file and a report (`train_flood_model`). The website only reads those files (`flood_purok.py`) and adds Flood to `/api/history/forecast/` and the accuracy card; an insert-only table logs each published version. History is not touched.

**Tech Stack:** Django 4.2 / DRF / PostGIS; NumPy, SciPy, scikit-learn 1.9.1; xgboost 3.2.0 and pypdf (offline only); React (react-scripts, Jest) with Leaflet.

**Spec:** `docs/design/specs/2026-11-24-flood-susceptibility-model-design.md` (section 0 governs). Evidence: `docs/research/2026-11-24-flood-prediction-assessment.md`. Probe scripts: `.superpowers/sdd/2026-11-24-flood-assessment/probe/`.

## Global Constraints

- **Never `git commit`.** Every commit step reads "Leave uncommitted" (the user's standing rule).
- **History is not modified.** Do not edit `apps/history/purok_levels.py`, `apps/history/area.py`, `apps/reports/decide.py`, `apps/reports/decide_views.py`, the `history.*` entries of `utils/system_settings.py`, `frontend/src/components/Map/purokLevels.js`, the Past hazards view or the History page. An approved flood report keeps its history-based level.
- **Landslide is out of scope.**
- **Shared database:** the only new migration is `history 0011`; it is applied to the shared database only in Task 11, after a backup and the user's go-ahead. Nothing is dropped or deleted.
- **Outside data stays private:** the Mananga PDF, the parsed Annex 11 CSV and the EOS-RS files live only in `backend/.hazard_cache/` (git-ignored). They are never written to `apps/history/data/`, never served, never in a response.
- **Model inputs are exactly** `noah25_class`, `noah5_class` (only when it passes the consistency check), `rel_height_river_m`, `dist_river_m` (used as `log1p`), `depression_m`, `built_share`.
- **Candidates (fixed settings, background weighted so presences and background carry equal total weight):**
  - `logistic_regression`: `LogisticRegression(penalty=None, max_iter=5000)` on standardised inputs. Separation guard: if it does not converge or any |coefficient| > 20, refit with `penalty='l2', C=1.0` and record `separation_guard: true`.
  - `maxent_hinge`: per-feature `SplineTransformer(degree=1, n_knots=5, knots='quantile')` then `LogisticRegression(penalty='l2', C=1.0, max_iter=5000)` — the MaxEnt-equivalent logistic form (Fithian & Hastie 2013), used instead of `elapid` because `elapid` pulls in geopandas/rasterio.
  - `xgboost`: `XGBClassifier(max_depth=2, n_estimators=300, learning_rate=0.05, subsample=0.8, random_state=0, monotone_constraints=…)` with +1 for `noah25_class`, `noah5_class`, `depression_m`; −1 for `rel_height_river_m`, `dist_river_m`; 0 for `built_share`.
  - `neural_network`: `MLPClassifier(hidden_layer_sizes=(8,), alpha=1e-3, early_stopping=False, max_iter=2000)`, seeds 0–4, probabilities averaged; `sample_weight` passed to `fit`.
  - `noah_only` (benchmark B0): score = `noah25_class / 3`.
- **Scores:** every candidate's output on a 0–1 scale (`predict_proba[:, 1]`; for `maxent_hinge` the logistic output).
- **Folds:** 5 spatial blocks by the barangay holding the spot or building: `Lawaan III`, `Biasong`, `Lawaan II`, `Pooc`, `Dumlog` + `San Isidro`.
- **Boyce index:** continuous; moving window = 0.1 × score range; 101 evaluation points; Spearman correlation of predicted/expected ratio against window centre.
- **Bootstrap:** 1,000 repeats, seed 0, resampling spots and background with replacement within each fold.
- **Choice:** simplest first (`logistic_regression` < `maxent_hinge` < `xgboost` < `neural_network`); a more complex one wins only if its Boyce gain over the current choice has a bootstrap interval wholly above 0.
- **Evidence domain:** buildings inside the convex hull of the distinct positive spots buffered 300 m (UTM 51N, EPSG:32651), clipped to the city; a building is out of range if any feature is outside the background's 1st–99th percentile; a purok is assessed when ≥ 50% of its buildings are in the domain and in range.
- **Cut-offs:** rank assessed puroks by mean building score; Red until ≥ 50% of field spots are held; Orange until Red + Orange ≥ 90%; if 90% is not reached before scores tie at the bottom, Orange stops at the last distinct score.
- **Acceptance (all four):** (1) Boyce gain over `noah_only` with bootstrap interval wholly above 0; (2) ≥ 3 of the 4 GeoAlert Mananga test points in a Red or Orange purok (a point in a not-assessed purok is a miss); (3) Red + Orange ≤ 50% of domain buildings; (4) choice and cut-offs fixed before any test data is loaded. Failing any → NOAH fallback.
- **NOAH fallback coverage:** puroks with ≥ 50% of buildings inside, or within 300 m of, a NOAH 25-year polygon; cut-offs by the same walk on all field spots.
- **Uncertain:** class differs from the published class in > 20% of 200 bootstrap refits (seed 0).
- **NOAH consistency slack:** 2% of flooded city area (`a5 ≤ 1.02·a25`; `a100 ≥ 0.98·a25`).
- **Monitoring:** "under review" when fewer than 80% of the last ≥ 10 new located floods fall in Red or Orange.
- **Downloads (checksums SHA-256):**
  - Mananga report `https://dream.upd.edu.ph/assets/Publications/LiDAR-Technical-Reports/USC/LiDAR-Surveys-and-Flood-Mapping-of-Mananga-River.pdf` — `616821337324a60f1ec24be47c3d292e001a2f942f482bd77df0ebba1e99be11`
  - EOS-RS Tino map `https://sentinel-asia.org/EO/2025/article20251104PH/EOS-RS_20251104_FPM_S1/EOS-RS_20251104_FPM_S1_Central_Philippines_Typhoon_Kalmaegi_v0.9_shp.zip` — `5855f2d05d645f84625ed2379ee85b2b643c8dc0a0713433f6554cb2963d730c`
  - NOAH `https://huggingface.co/datasets/bettergovph/project-noah-hazard-maps/resolve/main/Flood/{5yr,25yr,100yr}/Cebu.zip` — 5yr `d41f470285a91cddcd56af867012f492632805fc6000617ebc3640a65d275fac`, 25yr `bb630ac3bd360ad0686d7945ea7c389986e3d97f7d76cf5109645e46941c1ffe` (already cached as `noah_cebu_25yr.zip`), 100yr `52c7b3e0a6db23439499d1f5ce281774e60e1dbb5fc845ea7ace374f7b66f9af` (cached as `noah_cebu_100yr.zip`); shapefile `Cebu/PH072200000_FH_{5yr,25yr,100yr}.shp`, field `Var` (1 low, 2 medium, 3 high).
- **Copy, verbatim:**
  - `NOT_TRAINED = "The flood model has not been trained yet."`
  - `STALE = "The purok map changed since the flood model was trained; rerun build_flood_features and train_flood_model."`
  - `UNREADABLE = "The flood model file could not be read; rerun train_flood_model."`
  - `REPORT_MISSING = "The flood model's report is missing; rerun train_flood_model."`
  - `HAND_LEVELS = "Levels come from the hazard models and can't be changed by hand."`
  - `FORECAST_ONLY = "Only fire and flood have prediction models for now."` (backend) / `"Only fire and flood have a prediction for now."` (frontend note)
  - `NOT_BY_MONTH = "Flood susceptibility does not change by month."`
  - Level words: Red `"High flood susceptibility"`, Orange `"Moderate flood susceptibility"`, Green `"Low flood susceptibility (within the assessed floodplain)"`, none `"Not assessed yet"`.
  - Not-assessed reasons: `"Outside the surveyed floodplain"`, `"No buildings in this area"`, `"Its ground is unlike the surveyed floodplain"`, `"No NOAH flood model information here"`.
  - `UNDER_REVIEW = "Under review: recent floods fall outside the flagged areas"`
  - `BASIS_MODEL = "From a machine-learning model of where floods reached in the 2017 UP Mananga flood survey (typhoons of 1990-2014), with UP NOAH flood depths and terrain. It shows how flood-prone an area is, not whether a flood is coming, and it is the same in every month."`
  - `BASIS_NOAH = "From UP NOAH's 25-year flood model, classed by where floods reached in the 2017 UP Mananga flood survey. It shows how flood-prone an area is, not whether a flood is coming, and it is the same in every month."`
  - Legend: `"Flood: where floods tend to reach (from a machine-learning model; the same in every month, not a forecast of a flood)"`; with the NOAH fallback the parenthesis reads `"(from UP NOAH's 25-year flood model; the same in every month, not a forecast of a flood)"`.
- **Credits** (report and ATTRIBUTION.md): "Flood survey points: E. C. Paringit and R. S. Otadoy (eds.) (2017), LiDAR Surveys and Flood Mapping of Mananga River, UP Training Center for Applied Geodesy and Photogrammetry / University of San Carlos (Phil-LiDAR 1), used for research and education with acknowledgement"; "UP NOAH flood hazard maps (ODbL), via the bettergovph mirror"; "Tino flood proxy map: Earth Observatory of Singapore – Remote Sensing Lab (EOS-RS); contains modified Copernicus Sentinel data (2025)"; the existing Copernicus DEM notice, ESA WorldCover (CC BY 4.0), © OpenStreetMap contributors, Microsoft building footprints (ODbL).
- **Tests run on a private test database:** create `C:\Users\Sannichigetsu\.geoalert-test\geo_test_settings_flood.py` as a copy of `geo_test_settings_fire.py` with `TEST NAME = "test_geoalert_flood_susc"` and cache `C:/Users/Sannichigetsu/.geoalert-test/cache-flood`.
  - Backend (from `backend/`): `PYTHONPATH="C:/Users/Sannichigetsu/.geoalert-test" venv/Scripts/python.exe manage.py test <labels> --settings=geo_test_settings_flood --noinput`
  - Frontend (from `frontend/`): `CI=true npm test -- --watchAll=false <path>`

## Review Focus

1. **Purok map reloaded after training** → the forecast's flood block is `available: false` with `STALE`, `flood_results` is empty, fire is unaffected, and the map shows the reason instead of breaking. Tests: Task 6 (`test_stale_outlines_make_flood_unavailable_not_fire`), Task 9 (`flood unavailable shows the reason`).
2. **Fire and Flood both ticked, a purok with a fire level but flood not assessed** → its fill is the fire level, and the hover names both ("Flood: Not assessed yet (…)"). Test: Task 9 (`combined fill keeps the fire level when flood is not assessed`).
3. **Any period asked (past month, a year before fire records, a date)** → flood values are identical and `varies_by_month` is false, even when fire is unavailable for that period. Test: Task 6 (`test_flood_is_the_same_for_every_period`).
4. **`?hazards=Flood` alone** → no fire rows, the 12-month chart unavailable with `NOT_BY_MONTH`, flood block present. Test: Task 6 (`test_flood_only_request`).
5. **An old client sending `severity` in a resolve PATCH** → 400 with `HAND_LEVELS` and nothing changes; a resolve without `severity` still works. Test: Task 8 (`test_resolve_with_severity_is_refused_whole`).

---

### Task 1: Flood label sources (training side only)

**Files:**
- Create: `backend/apps/history/flood_labels.py`, `backend/apps/history/downloads.py`
- Modify: `backend/requirements/development.txt` (add `pypdf==<the version pip installs>`)
- Test: `backend/tests/test_flood_labels.py`

**Interfaces:**
- Produces:
  - `parse_annex11(text: str, expected: int = 169) -> list[dict]` — rows `{point: int, lat: float, lon: float, modelled_m: float, reported_m: float, event: str}`; raises `ValueError("Annex 11 must have 169 rows, found N.")` otherwise.
  - `downloads.fetch_verified(url: str, sha256: str, dest: Path, session=None) -> Path` — downloads when `dest` is missing, writes via `dest.with_suffix('.part')`, raises `RuntimeError` and deletes the part file on checksum mismatch. Shared by labels (Task 1) and features (Task 2), so neither imports the other.
  - `annex_points(cache_dir: Path, refresh: bool = False) -> list[dict]` — reads/writes `cache_dir / 'mananga_annex11_points.csv'`, extracting the PDF text with pypdf when the CSV is missing.
  - `spots(points: list[dict]) -> list[dict]` — one per distinct (lat, lon): `{lat, lon, events: list[str], max_depth: float, positive: bool}` (`positive` = any reported depth > 0).
  - `eosrs_polygons(cache_dir: Path) -> list` — GEOS polygons, SRID 4326, from the verified zip extracted to `cache_dir / 'eosrs_tino_fpm'`.
  - `geoalert_flood_points() -> list[dict]` — read-only: Flood `HistoricalRecord`s with a `location`: `{source_ref, day, barangay, lat, lon, precision}`.

- [ ] **Step 1: Write the failing tests**

```python
FIXTURE = "1 10.23583619 123.8315539 0.21 0.3 0.0081 Seniang 100-Year\n2 10.23583619 123.8315539 0.71 1.2 0.2401 Ruping 100-Year\n"

def test_parse_rows_and_count_check(self):
    with self.assertRaisesMessage(ValueError, 'Annex 11 must have 169 rows, found 2.'):
        parse_annex11(FIXTURE)
    rows = parse_annex11(FIXTURE * 1, expected=2)  # expected defaults to 169
    self.assertEqual(rows[0], {'point': 1, 'lat': 10.23583619, 'lon': 123.8315539, 'modelled_m': 0.21,
                               'reported_m': 0.3, 'event': 'Seniang'})

def test_spots_merge_events_and_mark_positive(self):
    pts = [{'lat': 1.0, 'lon': 2.0, 'reported_m': 0.0, 'event': 'Ruby'},
           {'lat': 1.0, 'lon': 2.0, 'reported_m': 0.5, 'event': 'Seniang'},
           {'lat': 3.0, 'lon': 4.0, 'reported_m': 0.0, 'event': 'Ruby'}]
    s = {(x['lat'], x['lon']): x for x in spots(pts)}
    self.assertTrue(s[(1.0, 2.0)]['positive']); self.assertEqual(s[(1.0, 2.0)]['max_depth'], 0.5)
    self.assertFalse(s[(3.0, 4.0)]['positive'])

def test_checksum_mismatch_keeps_nothing(self):  # session stub returns b'abc'
    with self.assertRaises(RuntimeError):
        fetch_verified('http://x', '0' * 64, self.tmp / 'f.pdf', session=StubSession(b'abc'))
    self.assertFalse((self.tmp / 'f.pdf').exists()); self.assertFalse((self.tmp / 'f.part').exists())
```

- [ ] **Step 2: Run** `... manage.py test tests.test_flood_labels ...` — Expected: FAIL (module missing).
- [ ] **Step 3: Implement `downloads.py` and `flood_labels.py`** with the signatures above. Normalise whitespace per line, then match `^(\d+) (10\.\d+) (123\.\d+) ([\d.]+) ([\d.]+) ([\d.]+) (.+?) 100-Year$`. Install pypdf into the venv and pin it in `requirements/development.txt` (not `base.txt`). Module docstring states the files are private and live only in `.hazard_cache`.
- [ ] **Step 4: Run the tests** — Expected: PASS. Then a one-off real check: `venv/Scripts/python.exe -c "…annex_points(Path('.hazard_cache'))…"` returns 169 rows and 107 distinct spots, 2 never-positive.
- [ ] **Step 5: Leave uncommitted.**

### Task 2: Flood features (static inputs per building)

**Files:**
- Create: `backend/apps/history/flood_features.py`, `backend/apps/history/management/commands/build_flood_features.py`
- Modify: `backend/apps/history/data/ATTRIBUTION.md` (flood inputs and credits)
- Test: `backend/tests/test_flood_features.py`

**Interfaces:**
- Consumes: `apps.hazards.susceptibility.city_grid`, `load_inputs`, `draw_polygons`, `draw_lines`, `distance_to`, `fill_depressions`; `apps.history.fire_sources.worldcover`, `footprints`; `apps.history.fire_features.points_inside`.
- Produces:
  - `FEATURE_COLUMNS = ('noah25_class', 'noah5_class', 'rel_height_river_m', 'dist_river_m', 'depression_m', 'built_share')`
  - `FEATURES_FILE = DATA_DIR / 'flood_purok_features.csv'`, `FEATURES_META = DATA_DIR / 'flood_purok_features.meta.json'`, `BUILDINGS_FILE = 'flood_building_features.npz'` (in the cache dir)
  - `noah_class_grid(grid, polygons_by_class: dict[int, list]) -> np.ndarray` (uint8, highest class per cell)
  - `noah_consistent(areas: dict[int, float], slack: float = 0.02) -> dict[int, bool]` (25 always True)
  - `river_relative(dem: np.ndarray, river_mask: np.ndarray, res: float) -> tuple[np.ndarray, np.ndarray]` → (height above nearest river cell floored at 0, metres to it)
  - `depression_depth(dem: np.ndarray) -> np.ndarray`
  - `built_share_at(classes: np.ndarray, transform, points_ll: np.ndarray, radius_m: float = 100) -> np.ndarray`
  - `read_features(csv_path=FEATURES_FILE, meta_path=FEATURES_META, cache_dir=None) -> FloodFeatures` with `.buildings` (dict of arrays: `lon`, `lat`, `barangay_id`, each feature), `.membership` (two int arrays: building index, purok id), `.areas` (rows: `purok_id, barangay_id, barangay, name, confidence, buildings`), `.meta` (incl. `outlines_version`, `noah_layers_used`, `noah_check`)

- [ ] **Step 1: Write the failing tests**

```python
def test_noah_class_grid_keeps_the_highest_class(self):  # two overlapping squares, classes 1 and 3
    g = noah_class_grid(self.grid, {1: [self.sq_a], 3: [self.sq_b]})
    self.assertEqual(g[self.overlap_cell], 3); self.assertEqual(g[self.a_only_cell], 1); self.assertEqual(g[self.outside_cell], 0)

def test_noah_consistency(self):
    self.assertEqual(noah_consistent({5: 1.0, 25: 1.0, 100: 0.5}), {5: True, 25: True, 100: False})
    self.assertEqual(noah_consistent({5: 1.03, 25: 1.0, 100: 1.2}), {5: False, 25: True, 100: True})

def test_river_relative_and_depression(self):
    dem = np.array([[3., 2., 1.], [3., 2., 1.]]); river = np.zeros_like(dem, bool); river[:, 2] = True
    h, d = river_relative(dem, river, res=10.0)
    np.testing.assert_allclose(h[0], [2., 1., 0.]); np.testing.assert_allclose(d[0], [20., 10., 0.])
    pit = np.array([[5., 5., 5.], [5., 1., 5.], [5., 5., 5.]])
    self.assertAlmostEqual(depression_depth(pit)[1, 1], 4.0, places=2)

def test_feature_module_reads_no_flood_records(self):
    src = Path(flood_features.__file__).read_text(encoding='utf-8')
    for name in ('HistoricalRecord', 'flood_labels', 'purok_levels', 'forecast'):
        self.assertNotIn(name, src)
```

- [ ] **Step 2: Run** `... manage.py test tests.test_flood_features ...` — Expected: FAIL.
- [ ] **Step 3: Implement `flood_features.py`.** Smooth the DEM with `gaussian_filter(sigma=1)` as `compute_factors` does; river mask = `draw_lines` of OSM waterways with `kind == 'river'`; `river_relative` uses `distance_transform_edt(..., return_indices=True)`. Sample each grid feature at building centres (Microsoft footprints, as fire). NOAH zips come through `downloads.fetch_verified` with the pinned checksums (the 25- and 100-year zips are already cached). `noah5_class` column is written always; `meta['noah_layers_used']` lists the layers that passed `noah_consistent` on city-clipped flooded areas; the 100-year layer is checked and reported but never a feature.
- [ ] **Step 4: Implement `build_flood_features`** (`--cache-dir` default `backend/.hazard_cache`, `--refresh`): writes the CSV, meta (with `Purok.outlines_version()`, NOAH check results, counts) and the building npz; prints counts and any dropped NOAH layer by name. Update ATTRIBUTION.md with the credits from Global Constraints.
- [ ] **Step 5: Run the tests** — Expected: PASS (`tests.test_flood_labels` still PASS).
- [ ] **Step 6: Leave uncommitted.**

### Task 3: Metrics and rules (pure functions)

**Files:**
- Create: `backend/apps/history/flood_rules.py`
- Test: `backend/tests/test_flood_rules.py`

**Interfaces:**
- Produces:
  - `boyce_index(presence: np.ndarray, background: np.ndarray, window_frac=0.1, n_points=101) -> float`
  - `boyce_gain(folds_p, folds_b, a_p, a_b, b_p, b_b, reps=1000, seed=0) -> tuple[float, float, float]` → (gain of A over B, 2.5%, 97.5%), resampling within folds
  - `choose(scores: dict[str, tuple[np.ndarray, np.ndarray]], folds_p, folds_b, order=ORDER) -> tuple[str, list[dict]]` with `ORDER = ('logistic_regression', 'maxent_hinge', 'xgboost', 'neural_network')`
  - `Cutoffs` dataclass `(red: float, orange: float | None, red_recall: float, orange_recall: float, target_reached: bool)`; `cutoff_walk(purok_scores: dict[int, float], spots_in: dict[int, int], red=0.5, orange=0.9) -> Cutoffs`
  - `classify(score: float, cutoffs: Cutoffs) -> str` (`'Red' | 'Orange' | 'Green'`)
  - `acceptance(gain_low: float, test_levels: list[str | None], flagged_share: float) -> tuple[bool, list[str]]` (gates 1–3; each failure a plain sentence)
  - `uncertain_puroks(published: dict[int, str], refits: list[dict[int, str]], limit=0.2) -> set[int]`
  - `monitoring(levels: list[str | None], min_n=10, target=0.8) -> dict` → `{'n', 'in_red_orange', 'under_review'}`

- [ ] **Step 1: Write the failing tests**

```python
def test_boyce_positive_for_a_good_ranking_and_near_zero_for_noise(self):
    rng = np.random.default_rng(0); bg = rng.uniform(size=5000)
    self.assertGreater(boyce_index(rng.beta(5, 1, 300), bg), 0.8)
    self.assertLess(abs(boyce_index(rng.uniform(size=300), bg)), 0.5)

def test_cutoff_walk(self):
    c = cutoff_walk({1: .9, 2: .8, 3: .5, 4: .2, 5: .1}, {1: 5, 2: 1, 3: 3, 4: 1})
    self.assertEqual((c.red, c.orange), (.9, .5)); self.assertTrue(c.target_reached)  # 5/10 then 9/10

def test_cutoff_walk_stops_at_the_last_distinct_score(self):
    c = cutoff_walk({1: .9, 2: 0., 3: 0.}, {1: 5, 2: 3, 3: 2})
    self.assertEqual(c.orange, None); self.assertFalse(c.target_reached); self.assertEqual(c.red_recall, .5)

def test_choice_keeps_the_simpler_model_unless_clearly_better(self):  # identical scores → logistic_regression
    name, _ = choose({n: (self.p, self.b) for n in ORDER}, self.fp, self.fb)
    self.assertEqual(name, 'logistic_regression')

def test_acceptance_gates(self):
    ok, why = acceptance(0.01, ['Red', 'Orange', 'Green', 'Red'], 0.4); self.assertTrue(ok)
    ok, why = acceptance(-0.01, ['Red', None, 'Green', 'Red'], 0.6)
    self.assertFalse(ok); self.assertEqual(len(why), 3)

def test_uncertain_and_monitoring(self):
    self.assertEqual(uncertain_puroks({1: 'Red', 2: 'Green'}, [{1: 'Red', 2: 'Orange'}] * 3 + [{1: 'Red', 2: 'Green'}] * 7), {2})
    self.assertFalse(monitoring(['Red'] * 8 + ['Green'] * 2)['under_review'])  # 80%: not below the target
    self.assertTrue(monitoring(['Red'] * 7 + ['Green'] * 4)['under_review'])   # 64%
    self.assertFalse(monitoring(['Green'] * 9)['under_review'])  # fewer than 10
```

- [ ] **Step 2: Run** `... manage.py test tests.test_flood_rules ...` — Expected: FAIL.
- [ ] **Step 3: Implement `flood_rules.py`.** Boyce: evaluation points evenly spaced across [min, max] of all scores; window half-width = `window_frac × range / 2`; ratio = (presence share in window) / (background share in window), windows with no background skipped; Spearman via `scipy.stats.spearmanr`. `uncertain_puroks` counts a purok when it differs in more than `limit` of refits (3/10 > 0.2 in the test). `classify` with `orange is None` gives Red at or above `red`, else Green.
- [ ] **Step 4: Run** — Expected: PASS.
- [ ] **Step 5: Leave uncommitted.**

### Task 4: Training core (domain, candidates, folds, purok scores, fallback, stability)

**Files:**
- Create: `backend/apps/history/flood_training.py`
- Test: `backend/tests/test_flood_training.py`

**Interfaces:**
- Consumes: `FloodFeatures` (Task 2); `spots()` output (Task 1); `flood_rules` (Task 3).
- Produces:
  - `FOLDS = {'Lawaan III': 0, 'Biasong': 1, 'Lawaan II': 2, 'Pooc': 3, 'Dumlog': 4, 'San Isidro': 4}`
  - `design_matrix(table: dict[str, np.ndarray], columns: tuple[str, ...]) -> np.ndarray` (`dist_river_m` → `log1p`)
  - `domain(lon: np.ndarray, lat: np.ndarray, spots: list[dict], city, buffer_m=300) -> tuple[np.ndarray, object]` → (bool mask, hull polygon in 4326)
  - `in_range(X: np.ndarray, X_background: np.ndarray, lo=1, hi=99) -> np.ndarray`
  - `fit(name: str, X: np.ndarray, y: np.ndarray, w: np.ndarray) -> object`; `score(name: str, model, X: np.ndarray) -> np.ndarray`
  - `out_of_fold(name, X_p, X_b, folds_p, folds_b) -> tuple[np.ndarray, np.ndarray]`
  - `purok_scores(building_scores: np.ndarray, membership: tuple[np.ndarray, np.ndarray], valid: np.ndarray, total_per_purok: dict[int, int]) -> dict[int, dict]` → `{pid: {'score', 'valid', 'total', 'assessed'}}` (`assessed` = valid ≥ 50% of total)
  - `not_assessed_reason(total: int, in_domain: int, valid: int) -> str | None` (the four reason strings)
  - `noah_fallback(noah25: np.ndarray, near_noah: np.ndarray, membership, total_per_purok, spot_purok: dict[int, int]) -> dict` → per-purok `{score, level, not_assessed_reason}` plus `Cutoffs`
  - `stability(name, X_p, X_b, w, building_X, membership, valid, total, cutoffs, reps=200, seed=0) -> list[dict[int, str]]`

- [ ] **Step 1: Write the failing tests** (small synthetic arrays; no database)

```python
def test_domain_is_the_buffered_hull(self):
    mask, hull = domain(self.lon, self.lat, self.spots, self.city, buffer_m=300)
    self.assertTrue(mask[self.inside_idx]); self.assertFalse(mask[self.far_idx])  # far = 1 km outside the hull

def test_in_range_uses_the_background_percentiles(self):
    Xb = np.arange(100.).reshape(-1, 1)
    np.testing.assert_array_equal(in_range(np.array([[50.], [-5.], [200.]]), Xb), [True, False, False])

def test_every_candidate_scores_between_0_and_1_and_ranks_a_clear_signal(self):
    for name in ('logistic_regression', 'maxent_hinge', 'xgboost', 'neural_network'):
        m = fit(name, self.X, self.y, self.w); s = score(name, m, self.X)
        self.assertTrue(((s >= 0) & (s <= 1)).all(), name)
        self.assertGreater(s[self.y == 1].mean(), s[self.y == 0].mean(), name)

def test_out_of_fold_never_scores_a_fold_with_a_model_that_saw_it(self):
    # a marker column is 1 only for fold-0 presences: a model that saw fold 0 scores them near 1
    p, b = out_of_fold('logistic_regression', self.Xp_marked, self.Xb, self.fp, self.fb)
    seen = score('logistic_regression', fit('logistic_regression', self.X_all_marked, self.y_all, self.w_all), self.Xp_marked)
    fold0 = self.fp == 0
    self.assertLess(p[fold0].mean(), seen[fold0].mean() - 0.2)
    self.assertEqual(p.shape, (len(self.Xp_marked),)); self.assertEqual(b.shape, (len(self.Xb),))

def test_purok_assessed_only_with_half_its_buildings_valid_and_reasons(self):
    out = purok_scores(np.array([.9, .8, .1]), (np.array([0, 1, 2]), np.array([7, 7, 8])),
                       np.array([True, False, True]), {7: 2, 8: 1})
    self.assertTrue(out[7]['assessed']); self.assertAlmostEqual(out[7]['score'], .9)
    self.assertEqual(not_assessed_reason(0, 0, 0), 'No buildings in this area')
    self.assertEqual(not_assessed_reason(10, 2, 2), 'Outside the surveyed floodplain')
    self.assertEqual(not_assessed_reason(10, 10, 3), 'Its ground is unlike the surveyed floodplain')
```

- [ ] **Step 2: Run** `... manage.py test tests.test_flood_training ...` — Expected: FAIL.
- [ ] **Step 3: Implement `flood_training.py`** with the Global Constraints' candidate settings. Standardise inputs with a `StandardScaler` fitted on each training fold only. Presence weight = `n_background / n_presence`, background weight = 1. Hull and buffer in EPSG:32651 via GEOS `transform`, as `decide.fire_geometry` does. `noah_fallback` uses the same `cutoff_walk` on all field spots.
- [ ] **Step 4: Run** — Expected: PASS.
- [ ] **Step 5: Leave uncommitted.**

### Task 5: `train_flood_model` (orchestration, ordering, files, report)

**Files:**
- Create: `backend/apps/history/management/commands/train_flood_model.py`, `backend/apps/history/flood_run.py`
- Modify: `backend/apps/history/flood_features.py` (add `MODEL_FILE`, `REPORT_FILE`)
- Test: `backend/tests/test_flood_run.py`

**Interfaces:**
- Consumes: Tasks 1–4.
- Produces:
  - `MODEL_FILE = DATA_DIR / 'flood_purok_model.json'`, `REPORT_FILE = DATA_DIR / 'flood_purok_report.json'` (defined in `flood_features.py` beside `FEATURES_FILE`)
  - `run(features: FloodFeatures, train_spots: list[dict], city, load_tests: Callable[[], dict], log=print) -> tuple[dict, dict]` → (model JSON, report JSON). `load_tests()` returns `{'geoalert_points': [...], 'eosrs': [...], 'barangay_records': [...]}` and is called only after `report['choice']` and `report['cutoffs']` are set.
  - Model JSON keys: `version` (`"<chosen or noah_fallback>@<sha1 of features csv + labels csv + settings, 12 chars>"`), `source` (`'model' | 'noah'`), `chosen`, `built_at` (ISO, Manila), `outlines_version`, `cutoffs`, `domain` (`buffer_m`, hull WKT), `inputs` (sha1 per input file, `noah_layers_used`), `areas: {purok_id: {barangay_id, level, score, uncertain, not_assessed_reason, estimated_outline, buildings}}` (`estimated_outline` = the area's `confidence == 'low'`).
  - Report JSON keys: `version`, `source`, `candidates` (out-of-fold Boyce and AUC with intervals), `choice`, `acceptance` (`adopted`, `gates`, `reasons`), `cutoffs`, `temporal_test` (the 4 Mananga points with levels; 2 Manipis points listed as not assessed; EOS-RS Boyce/AUC; the 2 always-dry spots' scores vs presences), `barangay_check`, `classes` (puroks, buildings, field spots per level; not-assessed counts by reason), `limits` (plain sentences), `credits`.

- [ ] **Step 1: Write the failing tests** (synthetic `FloodFeatures`, stub `load_tests`)

```python
def test_tests_load_only_after_choice_and_cutoffs(self):
    seen = {}
    def load_tests():
        seen['choice'] = 'choice' in self.report_so_far; seen['cutoffs'] = 'cutoffs' in self.report_so_far
        return {'geoalert_points': self.test_points, 'eosrs': [], 'barangay_records': []}
    model, report = run(self.features, self.spots, self.city, load_tests, log=self.capture)
    self.assertEqual(seen, {'choice': True, 'cutoffs': True})

def test_failed_gate_ships_the_noah_fallback(self):  # test points placed in Green puroks
    model, report = run(self.features, self.spots, self.city, lambda: self.tests_in_green)
    self.assertEqual(model['source'], 'noah'); self.assertTrue(model['version'].startswith('noah_fallback@'))
    self.assertFalse(report['acceptance']['adopted']); self.assertTrue(report['acceptance']['reasons'])

def test_every_area_has_a_level_or_a_reason(self):
    model, _ = run(self.features, self.spots, self.city, lambda: self.tests_ok)
    for a in model['areas'].values():
        self.assertTrue((a['level'] in ('Red', 'Orange', 'Green')) != bool(a['not_assessed_reason']))

def test_no_raw_points_in_the_written_files(self):
    model, report = run(self.features, self.spots, self.city, lambda: self.tests_ok)
    text = json.dumps([model, report])
    for s in self.spots: self.assertNotIn(str(s['lat']), text)
```

- [ ] **Step 2: Run** `... manage.py test tests.test_flood_run ...` — Expected: FAIL.
- [ ] **Step 3: Implement `flood_run.run`** (expose the in-progress report to the test through the `log` callback or a returned object, as convenient) **and the command** (`--cache-dir`). The command reads features, labels (`annex_points` → `spots`), the city outline (union of barangay boundaries), builds `load_tests` from `geoalert_flood_points()`, `eosrs_polygons()` and barangay records, then writes both JSON files to `.tmp` and swaps them in, as `train_fire_model` does. Prints the verdict in one line. Add the credits to the report.
- [ ] **Step 4: Run** — Expected: PASS.
- [ ] **Step 5: Leave uncommitted.**

### Task 6: Serving: `flood_purok.py`, the forecast API and the accuracy card entry

**Files:**
- Create: `backend/apps/history/flood_purok.py`
- Modify: `backend/apps/history/views.py` (`FORECAST_HAZARDS`, `parse_hazards`, `forecast_result`, `HistoricalForecastView` docstring, `ForecastAccuracyView`, new `flood_accuracy_entry`), `README.md` (a short "Flood predictive analytics" paragraph: what it shows, the two commands, the private data)
- Test: `backend/tests/test_flood_purok.py`, `backend/tests/test_forecast_api.py` (extend)

**Interfaces:**
- Consumes: `MODEL_FILE`, `REPORT_FILE` (Task 5); `flood_rules.monitoring` (Task 3).
- Produces:
  - `FloodModel` dataclass `(version: str, source: str, built_at: str, areas: dict[int, dict], cutoffs: dict, report: dict | None)`; `load() -> FloodModel | str` (same caching and stale check as `fire_purok.load`); `clear_cache()`.
  - `purok_rows(model: FloodModel) -> list[dict]` → `{purok_id, barangay_id, level, uncertain, not_assessed_reason, estimated_outline}`
  - `flood_block(model: FloodModel | str) -> dict` → `{available, reason, source, model_version, built_at, basis, varies_by_month: False}`
  - `since_publishing(model: FloodModel) -> dict` → `flood_rules.monitoring` over new located floods after `built_at` (Flood records with a `location` or puroks; `Affected` field marks on Flood zones), each mapped to the smallest purok holding it, plus the list of misses (date, purok name, level).
  - `views.parse_hazards(params) -> list[str]`: no names → `['Fire']`; names among fire/flood (any case) → those, in the order `('Fire', 'Flood')`; any other name → `ValueError(FORECAST_ONLY)`.
  - `views.flood_accuracy_entry() -> dict` → `{'hazard': 'Flood', 'kind': 'flood_purok', 'status': 'in_use' | 'unavailable', ...report, 'since_publishing': ...}` or with `reason`.

- [ ] **Step 1: Write the failing tests**

```python
def test_flood_only_request(self):
    data = self.get('/api/history/forecast/?hazards=Flood&month=7').data
    self.assertEqual(data['results'], []); self.assertEqual(data['purok_results'], [])
    self.assertEqual(data['profile_method'], 'unavailable'); self.assertEqual(data['profile_reason'], NOT_BY_MONTH)
    self.assertTrue(data['flood']['available']); self.assertFalse(data['flood']['varies_by_month'])
    self.assertEqual({r['purok_id'] for r in data['flood_results']}, set(self.model_areas))

def test_flood_is_the_same_for_every_period(self):
    a = self.get('/api/history/forecast/?hazards=Fire,Flood&month=1').data['flood_results']
    b = self.get('/api/history/forecast/?hazards=Fire,Flood&month=7&year=2022').data['flood_results']
    c = self.get('/api/history/forecast/?hazards=Fire,Flood&date=2027-11-15').data['flood_results']
    self.assertEqual(a, b); self.assertEqual(a, c)

def test_stale_outlines_make_flood_unavailable_not_fire(self):
    self.write_model(outlines_version='old')
    data = self.get('/api/history/forecast/?hazards=Fire,Flood').data
    self.assertFalse(data['flood']['available']); self.assertEqual(data['flood']['reason'], STALE)
    self.assertEqual(data['flood_results'], [])
    self.assertNotEqual(data['results'], [])  # fire rows still there

def test_other_names_are_refused_and_no_names_still_means_fire(self):
    self.assertEqual(self.get('/api/history/forecast/?hazards=Landslide').status_code, 400)
    self.assertNotIn('flood_results', self.get('/api/history/forecast/').data)

def test_accuracy_lists_fire_then_flood(self):
    kinds = [h['kind'] for h in self.get('/api/history/forecast/accuracy/').data['hazards']]
    self.assertEqual(kinds, ['fire_purok', 'flood_purok'])

def test_report_missing_keeps_the_forecast(self):  # model file present, report absent
    self.assertEqual(flood_accuracy_entry()['reason'], REPORT_MISSING)
    self.assertTrue(self.get('/api/history/forecast/?hazards=Flood').data['flood']['available'])
```

- [ ] **Step 2: Run** `... manage.py test tests.test_flood_purok tests.test_forecast_api ...` — Expected: FAIL.
- [ ] **Step 3: Implement.** `forecast_result` gains `hazards: list[str]`; fire's path runs only when `'Fire' in hazards` (unchanged otherwise); when only Flood is asked, `results` and `purok_results` are `[]` and the profile is unavailable with `profile_reason = NOT_BY_MONTH`. `flood` and `flood_results` appear only when Flood is asked. Existing fire assertions in `test_forecast_api` keep passing.
- [ ] **Step 4: Run** the two modules plus `tests.test_forecast tests.test_fire_purok` — Expected: PASS.
- [ ] **Step 5: Leave uncommitted.**

### Task 7: Insert-only flood log (migration `history 0011`)

**Files:**
- Modify: `backend/apps/history/models.py` (new `FloodPurokSusceptibilityLog`), `backend/apps/history/prediction_log.py` (new `write_flood_rows`, called from `log_in_background`), `backend/apps/history/management/commands/log_hazard_predictions.py`
- Create: `backend/apps/history/migrations/0011_flood_purok_susceptibility_log.py`
- Test: `backend/tests/test_flood_log.py`

**Interfaces:**
- Produces:
  - Model `FloodPurokSusceptibilityLog`, table `flood_purok_susceptibility_log`, columns `fpsl_id` (BigAuto), `fpsl_purok_id` (integer, no FK), `fpsl_purok_name`, `fpsl_brgy_id` (FK Barangay, PROTECT), `fpsl_model_version`, `fpsl_source`, `fpsl_level` (null or Red/Orange/Green, check constraint), `fpsl_score` (float, null), `fpsl_uncertain` (bool), `fpsl_not_assessed_reason` (text, default ''), `fpsl_outlines_version`, `fpsl_published_on` (date, Manila), `fpsl_created_at`; unique (`purok_id`, `model_version`); insert-only trigger as in 0010.
  - `prediction_log.write_flood_rows(today) -> int` — one row per area of the loaded flood model; 0 when `HAZARD_LOG_WRITER` is off or the model is unavailable; `bulk_create(ignore_conflicts=True)`.

- [ ] **Step 1: Write the failing tests**

```python
def test_rows_once_per_version(self):
    with self.settings(HAZARD_LOG_WRITER=True):
        self.assertEqual(write_flood_rows(date(2026, 12, 1)), len(self.model_areas))
        self.assertEqual(write_flood_rows(date(2026, 12, 2)), 0)

def test_nothing_without_the_writer_setting(self):
    with self.settings(HAZARD_LOG_WRITER=False):
        self.assertEqual(write_flood_rows(date(2026, 12, 1)), 0)

def test_rows_cannot_change(self):
    row = self.make_row()
    with self.assertRaises(DatabaseError), transaction.atomic(): FloodPurokSusceptibilityLog.objects.filter(pk=row.pk).update(fpsl_level='Green')
    with self.assertRaises(DatabaseError), transaction.atomic(): FloodPurokSusceptibilityLog.objects.filter(pk=row.pk).delete()
```

- [ ] **Step 2: Run** `... manage.py test tests.test_flood_log ...` — Expected: FAIL.
- [ ] **Step 3: Implement** the model, the migration (copy 0010's trigger SQL with the new names), `write_flood_rows`, and the command: it logs flood rows too and reports both counts; a missing fire model no longer stops flood rows (and the reverse).
- [ ] **Step 4: Run** `tests.test_flood_log tests.test_prediction_log` and `manage.py makemigrations --check --dry-run --settings=geo_test_settings_flood` — Expected: PASS; "No changes detected".
- [ ] **Step 5: Leave uncommitted.** Do **not** migrate the shared database (Task 11).

### Task 8: No hand on a level; retire the weighted flood layer; guards

**Files:**
- Modify: `backend/apps/hazards/views.py` (`HazardZoneDetailView.patch`), `backend/apps/hazards/susceptibility.py` (`FACTORS`, `build_layers`, `barangay_stats`), `backend/apps/hazards/management/commands/build_hazard_index.py` (`--drop-layer`), `frontend/src/api/reportApi.js` (stale `severity?` comment), `frontend/public/hazard-index/index.json`, `frontend/public/hazard-index/all.png`; delete `frontend/public/hazard-index/flood.png`
- Test: `backend/tests/test_security_gaps.py` (extend), `backend/tests/test_hazard_index.py` (extend), `backend/tests/test_flood_guards.py`

**Interfaces:**
- Produces: `susceptibility.drop_layer(out_dir: Path, layer: str) -> dict` — removes the layer's PNG and its entries in `index.json` (`layers`, `factors`, `barangays[*]`), rebuilds `all.png` as the per-cell maximum of the remaining hazard PNGs' classes, returns the new index.

- [ ] **Step 1: Write the failing tests**

```python
def test_severity_can_never_be_set_by_hand(self):  # NoReopeningTests style, flood and fire zones
    for zone in (self.zone(self.near, hazard_type=self.flood), self.zone(self.near, hazard_type=self.fire_type)):
        r = self.patch(zone, {'severity': 'Red'})
        self.assertEqual((r.status_code, r.data['error']), (400, HAND_LEVELS)); zone.refresh_from_db(); self.assertNotEqual(zone.severity, 'Red')

def test_resolve_with_severity_is_refused_whole(self):
    zone = self.zone(self.near, hazard_type=self.flood)
    self.assertEqual(self.patch(zone, {'status': 'Resolved', 'severity': 'Orange', **self.figures}).status_code, 400)
    zone.refresh_from_db(); self.assertEqual(zone.status, 'Active')
    self.assertEqual(self.patch(zone, {'status': 'Resolved', **self.figures}).status_code, 200)

def test_drop_layer(self):  # tmp copy of a tiny index with flood/landslide/fire PNGs
    index = drop_layer(self.tmp, 'flood')
    self.assertNotIn('flood', index['layers']); self.assertFalse((self.tmp / 'flood.png').exists())
    self.assertEqual(self.classes(self.tmp / 'all.png').tolist(), np.maximum(self.landslide, self.fire).tolist())
    self.assertNotIn('flood', FACTORS)

def test_no_setting_or_view_can_change_a_flood_prediction(self):
    self.assertFalse([k for k in SETTINGS if 'flood' in k.lower()])
    for path in Path(settings.BASE_DIR, 'apps').rglob('views*.py'):
        self.assertNotIn('flood_purok_model', path.read_text(encoding='utf-8'))
    self.assertNotIn('HistoricalRecord', Path(flood_features.__file__).read_text(encoding='utf-8'))
```

- [ ] **Step 2: Run** `... manage.py test tests.test_security_gaps tests.test_hazard_index tests.test_flood_guards ...` — Expected: FAIL.
- [ ] **Step 3: Implement.** In `patch`, return 400 `{'error': HAND_LEVELS}` whenever `'severity' in request.data`, before anything else changes. Remove the now-unused officer-raise branch (`raising`/`hold_raise` from a PATCH); keep `pending_severity`, approve and refuse-raise (automatic raises from attaching a Red-level report still use them). Remove `'flood'` from `FACTORS`, from `barangay_stats`' hazard tuple, and build `all` from landslide and fire. Add `--drop-layer` to `build_hazard_index` calling `drop_layer`.
- [ ] **Step 4: Run the tests** — Expected: PASS. Then run `venv/Scripts/python.exe manage.py build_hazard_index --drop-layer flood --out ../frontend/public/hazard-index` (use the command's existing output option) and check `index.json` has no `flood` key and `flood.png` is gone. `terrain.png` and `elevation.png` are untouched.
- [ ] **Step 5: Run the full backend suite** (`manage.py test tests ...`) — Expected: all pass (update any older test that asserted officer PATCH raises; list each in the task notes).
- [ ] **Step 6: Leave uncommitted.**

### Task 9: Frontend — Flood in "Likely by month", panel list, "This spot"

**Files:**
- Modify: `frontend/src/components/Forecast/forecastLevels.js`, `frontend/src/pages/PublicMap.jsx`, `frontend/src/components/Map/BarangayPanel.jsx`, `frontend/src/components/Map/SpotReading.jsx`, `frontend/src/utils/spotText.js`, `frontend/src/api/historyApi.js` (comment)
- Create: `frontend/src/components/Map/FloodPuroks.jsx`, `frontend/src/components/Map/FloodOverlay.jsx`
- Test: `frontend/src/components/Forecast/forecastLevels.test.js`, `frontend/src/components/Map/floodPuroks.test.js`, `frontend/src/utils/spotText.test.js`

**Interfaces:**
- Consumes: forecast response `flood` and `flood_results` (Task 6).
- Produces:
  - `hazardsParam(types) -> '' | 'Fire' | 'Flood' | 'Fire,Flood'`
  - `purokLikelyLevels(likely) -> Map<purokId, { Fire?: {level, probability, limited_data}, Flood?: {level, uncertain, not_assessed_reason} }>`
  - `FLOOD_WORD = { Red: 'High flood susceptibility', Orange: 'Moderate flood susceptibility', Green: 'Low flood susceptibility (within the assessed floodplain)' }`, `NOT_ASSESSED = 'Not assessed yet'`, `floodLegend(source) -> string` (the two legend strings), `floodTip(row, name) -> string`, `FORECAST_ONLY_NOTE = 'Only fire and flood have a prediction for now.'` (replaces `FIRE_ONLY_NOTE` everywhere it is shown)
  - `<FloodPuroks rows purokNames />`: top 5 by level (Red, Orange, Green), then "Show all"; not-assessed puroks grouped under their reason with a count; uncertain rows tagged "Uncertain"; rows with `estimated_outline` tagged "Estimated outline" (also appended to `floodTip`).
  - `<FloodOverlay geo levels />`: in the likely view with Flood ticked, not-assessed puroks drawn light grey (`#c9c9c9`, fill 0.35) with a dashed outline (`dashArray: '4 3'`), uncertain puroks with a dashed outline over their colour; non-interactive, above the fills.
  - `describeFloodAtSpot(flood) -> string` → `"Flood: High flood susceptibility (Sitio X)"`, `"Flood: Not assessed yet (Outside the surveyed floodplain)"`, or `"Flood: unavailable (<reason>)"`.

- [ ] **Step 1: Write the failing tests**

```js
test('hazardsParam asks for the ticked predicted hazards', () => {
  expect(hazardsParam(['Fire', 'Flood', 'Landslide'])).toBe('Fire,Flood');
  expect(hazardsParam(['Flood'])).toBe('Flood'); expect(hazardsParam(['Landslide'])).toBe('');
});
test('combined fill keeps the fire level when flood is not assessed', () => {
  const levels = purokLikelyLevels({ purok_results: [{ purok_id: 4, level: 'Orange', probability: 0.02 }],
    flood_results: [{ purok_id: 4, level: null, uncertain: false, not_assessed_reason: 'Outside the surveyed floodplain' }] });
  expect(purokLevel(levels.get('4'), ['Fire', 'Flood'])).toBe('Orange');
  expect(floodTip(levels.get('4').Flood, 'Purok A')).toBe('Purok A: Not assessed yet (Outside the surveyed floodplain)');
});
test('flood unavailable shows the reason', () => {
  expect(describeFloodAtSpot({ available: false, reason: 'The flood model has not been trained yet.' }))
    .toBe('Flood: unavailable (The flood model has not been trained yet.)');
});
test('FloodPuroks groups not-assessed areas by reason', () => {
  render(<FloodPuroks rows={rows} purokNames={names} />);
  expect(screen.getByText('Outside the surveyed floodplain (3)')).toBeInTheDocument();
});
```

- [ ] **Step 2: Run** `CI=true npm test -- --watchAll=false src/components src/utils` — Expected: FAIL.
- [ ] **Step 3: Implement.** In `PublicMap.jsx`: the likely view's types become the ticked subset of `['Fire', 'Flood']` (replacing `FIRE_TYPES` in the likely `PurokHistoryLayer`); add `<FloodOverlay>`; the legend shows `floodLegend(likely.flood.source)` when Flood is ticked and available, else its reason; purok and barangay tooltips add a Flood line; the 12-month chart shows `NOT_BY_MONTH` text when only Flood is ticked. For "This spot": fetch `historyApi.forecast({ hazards: 'Flood' })` once when a spot is first tapped, find the purok with `purokAt(purokGeo, lng, lat)`, pass `flood` to `BarangayPanel` → `SpotReading`. `SpotReading`'s raster list no longer finds a flood layer (Task 8) and shows `describeFloodAtSpot` instead. Past hazards code paths are not changed.
- [ ] **Step 4: Run** the whole frontend suite and `npm run build` — Expected: all suites pass; build compiles with no "not defined" or "unused" errors.
- [ ] **Step 5: Leave uncommitted.**

### Task 10: Frontend — flood section on the accuracy card

**Files:**
- Modify: `frontend/src/components/Forecast/ForecastAccuracy.jsx`
- Test: `frontend/src/components/Forecast/forecastAccuracy.test.js`

**Interfaces:**
- Consumes: `flood_accuracy_entry()` shape (Task 6) and the report keys (Task 5).
- Produces: `export function ForecastAccuracyEntry({ entry })` (picks the fire or flood section by `entry.kind`, or shows `entry.reason` when `status === 'unavailable'`; factor it out of the existing `ForecastAccuracy` render), and `export function FloodModelReport({ report })` rendering, in order: the source line (`BASIS_MODEL` / `BASIS_NOAH` text from `report`), the candidates table (Boyce and AUC with intervals), the choice and acceptance verdicts with each gate's sentence, the temporal test (4 Mananga points with levels, Manipis points "not assessed (upland road runoff is a different kind of flood)", EOS-RS Boyce/AUC, dry-spot check), the barangay check, the class table, "Since publishing" (with `UNDER_REVIEW` when flagged), limits, credits. An `unavailable` entry shows its reason.

- [ ] **Step 1: Write the failing tests**

```js
test('the card shows the flood verdict, gates and credits', () => {
  render(<FloodModelReport report={floodReport} />);
  expect(screen.getByText(/NOAH fallback|in use/i)).toBeInTheDocument();
  expect(screen.getByText(/UP Training Center for Applied Geodesy and Photogrammetry/)).toBeInTheDocument();
});
test('under review is shown when monitoring flags it', () => {
  render(<FloodModelReport report={{ ...floodReport, since_publishing: { n: 11, in_red_orange: 8, under_review: true, misses: [] } }} />);
  expect(screen.getByText('Under review: recent floods fall outside the flagged areas')).toBeInTheDocument();
});
test('an unavailable flood entry shows its reason', () => {
  render(<ForecastAccuracyEntry entry={{ hazard: 'Flood', kind: 'flood_purok', status: 'unavailable',
    reason: 'The flood model has not been trained yet.' }} />);
  expect(screen.getByText('The flood model has not been trained yet.')).toBeInTheDocument();
});
```

- [ ] **Step 2: Run** `CI=true npm test -- --watchAll=false src/components/Forecast` — Expected: FAIL.
- [ ] **Step 3: Implement** `FloodModelReport` and render it for entries with `kind === 'flood_purok'`; the fire section is unchanged.
- [ ] **Step 4: Run** the whole frontend suite and `npm run build` — Expected: PASS and compiled.
- [ ] **Step 5: Leave uncommitted.**

### Task 11: Real run and go-live steps (ask the user before each shared-database step)

**Files:**
- Produces: `backend/apps/history/data/flood_purok_features.csv`, `flood_purok_features.meta.json`, `flood_purok_model.json`, `flood_purok_report.json` (uncommitted; the user commits them)

- [ ] **Step 1:** Run `venv/Scripts/python.exe manage.py build_flood_features` (from `backend/`). Expected: 670 areas; the NOAH check line names any dropped layer (the 100-year layer is expected to fail); no error.
- [ ] **Step 2:** Run `venv/Scripts/python.exe manage.py train_flood_model`. Expected: one verdict line (`model` adopted, or `noah_fallback` with the failed gates); both JSON files written. Reading the shared database here is read-only.
- [ ] **Step 3:** Show the user the report numbers and the map on the stubbed local site (`C:/Users/Sannichigetsu/.geoalert-test/run_readonly_site.py`, backend port 8001, frontend 3001): Likely by month with Flood ticked, a not-assessed purok, an uncertain purok if any, Fire + Flood together, "This spot", the accuracy card. Wait for the user's word.
- [ ] **Step 4 (shared database — ask first):** back up with `pg_dump` to `Downloads/Geoalert-Full-Backup-before-history-0011-<date>.dump` and check the table and row counts, as for 0010. Then `manage.py migrate history 0011` (development settings).
- [ ] **Step 5 (shared database — ask first):** `HAZARD_LOG_WRITER=true manage.py log_hazard_predictions` once. Expected: one flood row per area; a rerun adds 0.
- [ ] **Step 6:** Run the full backend suite (private test DB) and the whole frontend suite plus `npm run build`. Expected: all pass. Report `git status --short` to the user; the user commits and pushes the code and the four data files. **Leave uncommitted.**
