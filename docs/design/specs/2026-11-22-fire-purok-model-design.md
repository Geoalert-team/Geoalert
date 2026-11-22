# Fire risk by purok: Pittsburgh's fire risk model adapted to Talisay

*Design, 2026-11-22. Status: **approved by the user** ("Clean up then execute the fire hazard
model"), with the scope changes in section 0. Leave every file uncommitted (the user's standing
rule).*

---

## 0. Scope changes the user made on approval (these override anything below)

1. **Flood and landslide prediction is deleted for now, and the Rain watch with it.**
   - The user said: "For now, we delete the models for the flood and landslide for predictive because
     we will also rebuild them". Asked whether the Rain watch ("Next 3 days") goes too, they answered
     "Also delete the Rain watch".
   - The clean-up comes first (Part A, section 12).
   - "Likely by month" then covers **fire only**.
2. **The map:** with fire the only predicted hazard, "Likely by month" fills **each purok by its fire
   level**, and barangays get outlines only. This settles section 11.
3. **The 23 barangay-only fires:** build and test all the code now. **The real training run waits**
   until the user has placed the 23 (section 3). Until it runs, fire's "Likely by month" says the
   model has not been trained yet.

Background, audit, data checks and the research behind every choice:
`docs/research/2026-11-22-fire-purok-prediction-audit.md` ("the audit"). This document says what to
build.

---

## 1. Intent

GeoAlert's "Likely by month" view should show **each purok's own chance of a fire**. The chance
comes from a machine-learning model that learns how purok features relate to real fires. Today the
view shows one figure per barangay, and that figure leans on each barangay's own fire history.

The user's requirements (brief of 2026-11-22 and answers since):
- **Purok level.** It must not split a barangay's figure into pieces.
- **No counting as the prediction mechanism.** No past fire count may be an input, threshold or
  rule; this includes a per-area or per-barangay term fitted to that area's own fires. Fire records
  are only the label, the validation and the comparison baselines. The code must read that way too:
  a thesis panel reading it should find a yes/no `fire_occurred` label, not a count driving the
  prediction.
- **An existing model, trained on our data**, not a model of our own design. The user chose
  **adapting the City of Pittsburgh Bureau of Fire's open-source fire risk model**
  (`github.com/CityofPittsburgh/fire_risk_analysis`, MIT, © 2017 mmadaio; Madaio et al. 2016;
  Singh Walia et al. KDD 2018).
- **Neural networks are tested on merit**, not assumed better.
- **Red / Orange / Green** levels with cut-offs set by validation, kept apart from the probability.
  False negatives matter most.
- **Free, commercially usable data, no account**, where possible.

## 2. Goals, non-goals, anti-goals

**Goals**
- One probability and one level per purok (all 670 areas) per month, and from them per barangay.
- The model is chosen by a test fixed in advance, and its real scores are reported with their limits.
- Fire's figures feed the forecast API, the new purok prediction log and the accuracy card.

**Non-goals**
- A new flood or landslide model. Their prediction is deleted in Part A (section 0); rebuilding them
  is later work.
- **History stays exactly as it is.** The user said "There is levels, dont change the history and its
  functions, just the likely by month". That leaves alone:
  - `purok_levels.py` and `area.py`;
  - the "Past hazards" view and `/api/history/purok-levels/`;
  - the barangay panel's history;
  - the History page;
  - the "Seasons on record" card.
- No weather input (section 4.3).
- No training on the server.

**Anti-goals** (failure even if it runs)
- Any input derived from fire records: counts, rates, "had a fire before", neighbours' fires, or a
  barangay or purok identifier term.
- Claiming purok-level accuracy from past fires without the map-leak caveat (section 6.5).
- Probabilities shown more precisely than the data supports, or with no "Limited data" warning.
- A neural network adopted because it sounds advanced rather than because it won the test.

## 3. Prerequisite (the user's condition): place the 23 barangay-only fires first

**Building does not start until this is done.** 23 BFP fires name only a barangay. The user said
"we put it in a purok before doing this" and chose to look them up from evidence; the build waits.
- **The checklist:** `Downloads/Talisay-23-Fires-Without-Purok-2026-11-22.csv`, with date, Manila
  time, type, alarm, the address as logged, and blank purok and source columns.
- **The likely sources:** BFP Talisay's incident reports, or the Talisay City Fire Station's
  Facebook posts (needs a logged-in search).
- **When the checklist comes back:** add each placement to
  `backend/apps/barangays/data/puroks/fire_places.csv`, with its reason and source. Back up the fire
  links, then run `import_bfp_fires --relink`. The relink writes to the shared database, so it needs
  the user's go-ahead. Any fire still unplaced is left out of training and named in the report,
  never guessed.

## 4. The model

### 4.1 What is reused from Pittsburgh, and what is changed

| Pittsburgh (`riskmodel.py`, `Allmodels.py`) | GeoAlert | Why it is changed |
|---|---|---|
| One row per property per year; label `fire` 1/0 | One row per **area per month**; label `fire_occurred` 1/0 (1 if any fire is linked to the area that month) | The map view is by month; puroks are our unit |
| Features: property, parcel, inspection, tax and census records | Building, road, land-cover, station-access and population features (4.2) | Talisay has no property or inspection open data |
| Candidates: XGBoost (learning rate 0.13, 1,500 trees, depth 3, γ 0.5, colsample 0.6), random forest (500 trees, depth 10, log2 features), AdaBoost (1,000) | The same three, **with Pittsburgh's exact settings as one candidate each**, plus small re-tuned grids, plus logistic regression (imported in `riskmodel.py`) and a small **neural network** (MLP) | Their settings were tuned for about 20,000 properties; on 670 areas they may memorise, and the test will show whether they do |
| Train on earlier years, test on the final year | The same: test on 2026. Settings are chosen with leave-one-year-out inside the training years (6.1) | No setting is chosen on the test year |
| Confusion matrix, kappa, AUC, recall, precision and F1 at a 0.5 cut-off | Those, at our level cut-offs, plus log loss, Brier, PR-AUC and calibration (6.3) | At a 0.6% event rate a 0.5 cut-off flags nothing, and accuracy alone means nothing |
| `predict_proba` as the risk score | The calibrated `predict_proba` is the probability; levels come from validated cut-offs (5) | The probability and the level stay separate |

The code is Python 2 and uses removed scikit-learn modules, so it is **ported, not run**. The new
module's docstring and the report credit Pittsburgh, and the MIT notice is kept for any code taken
from it.

### 4.2 Units and inputs

- **Units:** the 670 areas in the `purok` table, as the map has them. Sitio areas that contain
  puroks (77 of them, holding 34 fire links) are units too, with features measured over their whole
  outline. Overlap is accepted and noted in the report.
- **Labels:**
  - a fire linked to two areas marks both;
  - months run from 2023-01 to the last full month before the run;
  - a fire's month is its Manila month, read as `views._forecast_events` reads it;
  - real records only: `is_sample` is false and the hazard type is Fire.
- **Inputs:** fixed in advance. Every one comes from a non-fire source. Names say what they measure.

| Input | Source (cached in `backend/.hazard_cache`) | Licence |
|---|---|---|
| `buildings_in_area` (log), `building_density_per_ha` (log) | Microsoft Global ML Building Footprints (already cached) | ODbL |
| `median_footprint_m2` | The same file, read as polygons (today's cache keeps only centres) | ODbL |
| `median_gap_to_nearest_building_m`, `share_crowded_10m` (share of buildings with 2 or more others within 10 m) | The same | ODbL |
| `road_density_m_per_ha`, `main_road_m`, `median_building_to_road_m` | OSM roads (cached) | ODbL |
| `road_distance_to_fire_station_m` (shortest path on the OSM road graph) | OSM roads and stations (cached) | ODbL |
| `share_built_up`, `share_grass_shrub_bare`, `share_tree_cover` | ESA WorldCover 2021 v200, tile N09E123, AWS `--no-sign-request` | CC BY 4.0 |
| `population` (log) | WorldPop constrained 100 m, latest year | CC BY 4.0. If no download path without an account works, drop it and say so |
| `distance_to_coast_m`, `distance_to_river_m` | OSM (cached) | ODbL |
| `month_sin`, `month_cos` | Calendar | — |

**Left out on purpose:**
- Area `kind` and "is a container". The audit (section 3) shows these partly reflect which names came
  from fire addresses.
- Area size itself, which comes straight from how the outlines were estimated.
- Every fire-derived value.
- Google Open Buildings 2.5D (heavy download, Philippine coverage unconfirmed): possible later work.

### 4.3 Time

The only time inputs are the two month-of-year waves. Weather is left out:
- Fire's earlier test found rain made it worse.
- The Fire Weather Index has no evidence for house fires.
- A future month's weather is unknown, so the model would fall back to a climate average, which is
  what the month waves already give.

If the test finds the waves do not help, every month gets the same purok figures, and the card says
so.

### 4.4 Candidates and the choice rule

| Candidate | Settings tried (inner validation picks one per family) |
|---|---|
| Logistic regression (penalised, standardised inputs) | C ∈ {0.01, 0.1, 1} |
| Random forest | Pittsburgh's (500, depth 10, log2), and depth ∈ {3, 5} × min leaf ∈ {20, 100} |
| AdaBoost | Pittsburgh's (1,000), and 100 trees × learning rate ∈ {0.1, 1} |
| XGBoost | Pittsburgh's exact settings, and learning rate ∈ {0.03, 0.1} × trees ∈ {100, 300} × depth ∈ {2, 3} × min child weight ∈ {5, 20} |
| Neural network (scikit-learn `MLPClassifier`) | 1 hidden layer of 8 or 32; weight decay α ∈ {1, 10}; average of 5 seeds |

- **No resampling and no class weights.** Both would distort the probabilities. Imbalance is handled
  in the cut-offs (5).
- **Selection is on leave-one-year-out log loss** over the training years. Brier score breaks ties.
- **The rule:** the best candidate replaces logistic regression only if its paired log-loss gain has
  a 95% bootstrap interval wholly below zero. The bootstrap resamples barangays, as in
  `fire_candidate.verdict`. Otherwise the simpler model is used. The card shows every candidate's
  scores.
- Seeds are fixed, so a rerun on the same data gives the same choice.

### 4.5 Calibration and the final fit

- A Platt recalibration (intercept and slope) is fitted on the winner's leave-one-year-out
  predictions.
- For the test, the winner and its calibration are refitted on 2023–2025 and scored once on 2026.
- For deployment, the same steps run on every month through the last full one.

## 5. Probability → Red / Orange / Green

- **The probability** is the calibrated chance of at least one recorded fire in the area in that
  month. It is always shown with the level.
- **Orange or higher:** the highest probability cut-off at which Orange and Red together catch
  **80% of the fires** in the leave-one-year-out predictions. This was the designer's call: the user
  said "refer to approach", and missed fires cost more than extra Orange puroks.
- **Red:** the lowest cut-off at which the area-months above it had **at least 2× the city-average
  fire rate**, with at least 10 fires above it. If none qualifies, nothing is Red, and the card says
  why.
- **Checked once on 2026,** reporting:
  - recall, precision, F1 and kappa per level;
  - the share of puroks in each level;
  - how many 2026 fires fell in Green.
- **Week and date periods:** the chance scales as today (rate × the week's share of the month), and
  the level stays the month's.
- **Barangays:** rate = Σ over its areas of −ln(1 − p); chance = 1 − e^(−rate). The barangay level
  keeps today's shared 15% / 25% cut-offs (`model_forecast.level_for`), so the combined chance
  across hazards stays on one scale.

**"Limited data" flag** on an area when either:
- its researched point has `confidence = low`; or
- its 80% interval (from 50 refits on barangay-resampled data) has an upper bound more than 3× its
  lower bound.

The level is still shown, with the flag beside it.

## 6. Validation

### 6.1 Splits
- **Inner validation (choosing settings, the model, calibration and cut-offs):** leave one year out
  of 2023, 2024 and 2025. This is safe here because no input depends on time beyond the month waves,
  and none comes from fires.
- **The test:** 2026-01 to the last full month, used once.
- **Leave one barangay out:** a robustness check on whether the inputs carry over to unseen places.
  It is reported, not used to choose.

### 6.2 Baselines (comparison only; each named "comparison" in code and report)
- the same chance everywhere;
- in proportion to `buildings_in_area`;
- the area's historical frequency (the counting the brief rules out, kept only to show what the
  model is measured against).

### 6.3 Metrics
- Log loss (the main score), Brier score, ROC-AUC and PR-AUC;
- calibration intercept and slope, and a reliability table by tenths;
- the share of fires caught by the top 10% and top 20% of areas;
- the level table from section 5.

Each comes with a 95% interval from resampling barangays. Accuracy is never reported alone.

### 6.4 Barangay check (clean of the map problem)
The same predictions, summed to barangay-months, are scored against BFP's own barangay field for
2026. They are compared with the comparison baselines of 6.2, computed at barangay level in the same
command on the same months. The retired barangay model's last reported figures are quoted only for
context, marked as covering a different window. This is the one retrospective score the purok map
cannot inflate.

### 6.5 The map-leak caveat and the sensitivity table
151 areas were drawn because a fire address named them (the audit, section 3). The report shows the
test scores separately for those 151 areas and for the other 519. The card states plainly that
purok-level scores from past fires are probably optimistic.

### 6.6 Going forward (the honest purok test)
A purok prediction log (8.3) keeps each month's figures as issued. The report scores them against
fires that came after each row was issued. The first verdict is due after about 12 months (about 55
fires).

## 7. The no-counting guard

- **The feature builder takes no fire records.** Its module does not import `HistoricalRecord`, the
  history loaders or `forecast.py`.
- **A test fails the build** if any input column is not on the allowlist in 4.2, or if the feature
  builder imports a fire-record source.
- **Labels are built in the training module only,** as yes/no `fire_occurred`.
- **The comparison baselines live only in the evaluation code,** under names that say "comparison".

## 8. Integration

### 8.1 Offline commands (run on the developer's machine, like flood and landslide's test command)
- **`manage.py build_fire_features`:**
  - downloads and caches WorldCover, WorldPop and the footprint polygons;
  - reuses the cached OSM and footprint data;
  - writes `backend/apps/history/data/fire_purok_features.csv`: one row per area (`purok_id`,
    barangay, name, the inputs, and `Purok.outlines_version()` at build time);
  - adds the sources to `apps/history/data/ATTRIBUTION.md`.
- **`manage.py train_fire_model`:**
  - reads the real fires from the shared database (read-only) and the features file;
  - runs 4.4–6.5 and writes:
    - `fire_purok_model.json`: the model used, its settings, the calibration, the cut-offs, the version
      (`<model>@<sha1 of features + fires + settings, 12 chars>`), the training span and the number of
      fires, and for every area 12 monthly probabilities, levels, 80% intervals and the limited-data
      flag;
    - `fire_purok_report.json`: everything the card shows;
  - needs scikit-learn and xgboost, which are already in the local venv. Production needs neither.
  - The user reruns both commands after a BFP import or a purok reload.

### 8.2 The website (reads files; no model library, no refit)
- **New `apps/history/fire_purok.py`:**
  - loads the model file;
  - checks its outlines version against `Purok.outlines_version()`. A mismatch means fire is
    unavailable with "The purok map changed since the fire model was trained; rerun build_fire_features
    and train_fire_model.";
  - if the model file is missing (a fresh deploy before the first run), fire is unavailable with
    "The fire model has not been trained yet." The user commits the data files, so a deploy carries
    them;
  - gives purok rows and the barangay table, `{barangay id: [12 monthly rates]}`, the shape
    `hazard_forecast.fire_month_table` returns today, so `combine()` and the prediction log keep
    working.
- **`views.forecast_result`:**
  - fire's rows come from `fire_purok` in place of `model_forecast.use_models`, with the same row
    fields (`probability`, `expected_events`, `level`, `method: 'model'`, `in_training`);
  - periods inside the training span are flagged `in_training`, and periods before 2023-01 stay
    unavailable ("Fire records start in January 2023.");
  - a new `purok_results` list appears when Fire is included: `purok_id`, `barangay_id`,
    `probability`, `level`, `interval`, `limited_data`;
  - `basis_method` names the new model.
- **`ForecastAccuracyView`:** fire's entry is `fire_purok_report.json` plus the purok log block.
- **`reports/decide_views._history`:** the approved report's level is the highest **model level** among
  its puroks for the current Manila month (the user's choice).
  - If the model is unavailable or a purok has no figure, the level falls back to Orange and the
    decision screen gives the reason. That fallback is the designer's call: a live fire needs a level,
    and Orange is the cautious middle.
  - `purok_levels.purok_levels` stays for history.
- **Removed (fire only):**
  - `model_forecast.py`'s barangay Poisson path and `warm_fire`;
  - `fire_candidate.py`;
  - their tests.

  Helpers that other modules import stay (`level_for`, `chance`, `plain_number`, `places`).
  `barangay_exposure.csv` stays (flood uses it). `forecast.py` stays (history rows and the baseline).

### 8.3 Purok prediction log (new table; migration only after a backup and the user's go-ahead)
- **Table:** `fire_purok_prediction_log`.
- **Columns:**
  - `purok_id` (a plain integer, **no foreign key**, so purok reloads never touch it);
  - `purok_name` and `barangay` (foreign key, protect) as they were then;
  - `period_start` (month), `issued_on`, `model_version`, `probability`, `level`, `limited_data`.
- Unique on (`purok_id`, `period_start`, `issued_on`, `model_version`). Insert-only by trigger, as
  migration 0008 does.
- Written by `log_hazard_predictions` under `HAZARD_LOG_WRITER`, one snapshot per Manila day for the
  current month.

### 8.4 Frontend
- **Map, "Likely by month":** puroks filled by their fire level. How purok fills and barangay fills
  share the map: **open, for the user** (section 11).
- **Barangay panel:** the fire row's text names the new model, and its puroks are listed by fire
  level (top 5, then "show all"), each with its probability and the limited-data flag.
- **`forecastLevels.js`:** a fire model label and the caveat text.
- **`ForecastAccuracy.jsx`:** the fire section shows:
  - the candidates table and the rule's verdict;
  - the 2026 test with intervals, and the level table;
  - the barangay check;
  - the 151 / 519 sensitivity table;
  - the prospective log block;
  - Pittsburgh credited.

### 8.5 Tests
- **Backend:**
  - feature functions on small synthetic arrays;
  - the no-counting guard (7);
  - the cut-off rules on hand-made predictions;
  - the barangay sum;
  - the stale-outlines check;
  - the forecast and accuracy response shapes;
  - the decide level and its fallback;
  - the log being insert-only.
- **Frontend:** purok fills in "Likely by month", the panel list, the accuracy card.
- Run on a private test database name (the shared test database collides).

## 9. Approaches considered

| | Chosen: **adapt Pittsburgh's model** (purok-months, yes/no label) | Grid cells summed to puroks | Ready-made model only |
|---|---|---|---|
| What | A published, deployed fire-department model's recipe, trained on our fires | A Poisson model on 50 m cells; fires as "somewhere in a purok" | FireCheck, or the Fire Weather Index |
| Why or why not | The user asked for an existing model and code a panel will not read as counting | Better isolated from the estimated outlines, but it is a design of our own and uses a count target | FireCheck does not cover Talisay and is not public; the Fire Weather Index is one citywide value, made for vegetation fires |

## 10. Calls the designer made (the user can overrule any of these)

1. The recall target is 80% for Orange + Red, and Red starts at 2× the city average.
2. Fire's barangay level keeps today's 15% / 25% cut-offs.
3. Area kind, container status and area size are not inputs.
4. No weather input; month waves only.
5. The fallback level on report approval is Orange when the model is unavailable.
6. The purok log stores `purok_id` without a foreign key.
7. Unplaced fires are left out of training and listed, never guessed.
8. Overlapping sitio containers are units, with features over their whole outline.
9. WorldPop is dropped if it needs an account.

## 11. Open for the user
- ~~How purok fire fills and barangay fills share the "Likely by month" map.~~ Settled by section 0:
  fire only, puroks filled.

## 12. Part A: the clean-up (before the fire build)

Everything removed is in git at HEAD `b829074`, so it can come back with `git checkout`. **Nothing in
the shared database is dropped or deleted.** The rainwatch tables, `hazard_prediction_log` and their
rows stay as they are; no migration removes them.

**Delete (flood and landslide prediction):**
- `backend/apps/history/`: `hazard_forecast.py`, `hazard_models.py`, `hazard_tests.py`,
  `hazard_verdict.py`, `hazard_scoring.py`, `hazard_scenarios.py`, `two_part.py`, `firth.py`,
  `storms.py`, `landslide_catalogue.py`, `rain.py`. Also the fire pieces this design replaces:
  `model_forecast.py` and `fire_candidate.py`.
- Commands: `test_hazard_models`, `fetch_rain`, `fetch_storms`, `build_hazard_features`.
- Data: `hazard_model_report.json`, `rain_daily.csv`, `storm_days.csv`, `storm_days.meta.json`,
  `barangay_terrain.csv`, `barangay_exposure.csv`, `hazard_model_exclusions.csv`,
  `landslide_catalogue_exclusions.csv`.
- `exposure.py`: delete. Its Microsoft footprint download helper moves to the fire feature builder.
- `hazard_data.py`: keep only what the remaining code imports (`MANILA`, if anything still uses it);
  delete the rest.
- `prediction_log.py`: rewrite for the new purok log (8.3). The `HazardPredictionLog` model class and
  migration 0008 stay, so the migration history stays consistent; nothing writes to that table
  any more.
- `apps/hazards/views.py`: remove the flood and landslide warm-up call.

**Delete (the Rain watch):**
- `backend/apps/rainwatch/`, plus its entries in `INSTALLED_APPS`, `config/urls.py` and
  `RAIN_WATCH_INGEST_TOKEN` in the settings.
- `tools/rain_forecast/`, `.github/workflows/rain-forecast.yml`, and the rain-forecast test step in
  `.github/workflows/ci.yml`.
- `frontend/src/components/RainWatch/`, `frontend/src/api/rainWatchApi.js`, the "Next 3 days" view and
  rain banner in `PublicMap.jsx`, and the DRRMO dashboard's rain watch card and override form.
- Rain watch lines in the deploy env examples and docs.
- The user removes the GitHub Actions secret and the Render env var themselves (outside the repo).

**Keep:**
- Flood and landslide **history**: records, `flood_landslide.py` (import and close form),
  `import_flood_landslide`, `place_history_records`, the History page and "Past hazards".
- `forecast.py`: history rows and the comparison baseline.
- The static hazard-index and terrain map layers (`susceptibility.js`, `terrain.js`, `SpotReading`,
  `build_hazard_index`). These are terrain maps, not prediction models. **This is the designer's
  reading; the user may say otherwise.**
- `HAZARD_LOG_WRITER` (the new purok log uses it).

**What changes in the API:**
- `/api/history/forecast/` covers Fire only. `hazards=` and `hazard_type_name=` accept `Fire`; any
  other name is a 400 with "Only fire has a prediction model for now."
- `combined` and the rain-based fields go.
- `results` (barangay rows), `purok_results` and `profile` stay for fire.
- `/api/history/forecast/accuracy/` returns fire's entry only.

**Tests:** delete the tests of the deleted modules, and update the rest so both suites pass before
Part B starts.
