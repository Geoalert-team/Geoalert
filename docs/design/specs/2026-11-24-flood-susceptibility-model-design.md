# Flood susceptibility by purok: a learned model of where Mananga floods reach

*Design, 2026-11-24. Uncommitted, per the standing rule. Built on the assessment
`docs/research/2026-11-24-flood-prediction-assessment.md` (read it for the evidence behind every
number here).*

## 0. Decisions the user made (2026-11-24, AskUserQuestion)

| Question | Answer |
|---|---|
| Approach | **Learned susceptibility**: a model per purok/sitio area that learns where floods reach, with NOAH and terrain inputs. It is used only if it beats the NOAH map on its own. Puroks without flood evidence show "not assessed yet". No forecast |
| If the learned model fails its test | **NOAH-based classes**: ship the UP NOAH 25-year layer, classified by the same rules and labelled as NOAH's physics model, until a learned model passes |
| Outside data | **Use both privately**: train on the 2017 UP Mananga report's 169 field points; test on the EOS-RS Tino satellite map. Only fitted numbers reach the app. Raw points are never shown or redistributed. Both are credited |
| Existing mechanisms | Remove the **manual severity edit**. "IN the history, dont change but change the predictive so humans cant interfere. do what is best, no more manual severity or manual setting of levels" |

**History and predictive analytics are separate parts of GeoAlert** (the user's correction, 2026-11-24): "Those thresholds to determine the severity level on the history [are] already given by the barangay hall BUT that predictive analytics USES machine learning models and neural networks to predict."

- **History: untouched by this build.**
  - Past records and the History page.
  - The Past hazards map fills, purok history levels (`purok_levels.py`, `area.py`).
  - The barangay hall's thresholds held in Settings (`history.*`).
  - The history-based alert level an approved flood report takes from its puroks (`reports/decide_views._level`, `_history`).
- **Predictive analytics: what this build adds.**
  - Flood joins the forecast ("Likely by month", `/api/history/forecast/`, the accuracy card, the prediction log), which today covers fire only.
  - A machine-learning model makes every flood prediction, and no person can set, raise, approve or adjust one.
- **Also removed, as the user picked:** `severity` leaves `PATCH /api/hazards/<id>/` for every hazard type, so no one can change a live level by hand. No screen uses it today.
- **Replaced (designer's call, under "do what is best"):** the hand-weighted flood raster in `hazards/susceptibility.py` (AUC 0.51, no skill) feeds the map's "This spot" reading. It is a prediction-like layer, so it is replaced by this model's output.
- **Landslide is out of scope** (the user: "just the flood").

## 1. Intent

The DRRMO and residents need to know **which puroks floods tend to reach**, from evidence rather than a hand-made formula or counts. They also need to know where GeoAlert cannot honestly say.

GeoAlert's own records are too few to learn from: 6 flood days and 5 purok links. The 2017 UP Mananga flood-mapping survey, however, recorded 169 located flood depths from 6 typhoons (1990-2014) along the lower Mananga. That is enough to learn, and test, a small susceptibility model for that floodplain.

The result is a **susceptibility** map. It describes how flood-prone a place is when a flood happens. It never claims a flood is coming.

The thesis panel will look for three things in the predictive analytics: real machine learning, no counting, and no human hand on any prediction. The design gives all three, and states its limits on the model card.

## 2. Goals, non-goals, anti-goals

**Goals**
1. A Red / Orange / Green flood susceptibility class per purok area, learned from located flood observations, with puroks outside the evidence shown as **not assessed yet**.
2. Adoption by a rule fixed before training: the learned model must beat NOAH-only on held-out data. Otherwise NOAH-based classes ship (the user's choice).
3. Classes from validated recall targets, with false negatives counted directly.
4. Fully automatic predictions: no setting, screen or endpoint lets a person set, raise, approve or adjust a flood prediction.
5. Every published susceptibility kept in an insert-only log. New located floods are checked against it automatically.

**Non-goals**
- Flood forecasting of any kind: no daily or monthly flood chance and no rain input. Strategy A is gated (section 11).
- Landslide.
- **Anything in History:** records, Past hazards, purok history levels, the barangay hall's thresholds, and the history-based alert level of approved flood reports.
- Automatic retraining on a schedule. The user chose on 2026-11-24 to make retraining automatic later, once all hazards' models exist. Retraining here is a documented command, which the brief permits.
- Rebuilding a hydraulic model.

**Anti-goals** (it would count as failure even if it "works")
- Any purok coloured without evidence behind it.
- Susceptibility worded as "flood likely" or "risk now".
- A class that a count, an admin setting or a person can change.
- An "everything is red" map. Today's layer flags 69% of houses High or Very High.
- Raw field points or satellite data shown or redistributed.

## 3. Data

### 3.1 Labels (training module only)

| Set | Use | Where it lives |
|---|---|---|
| **Annex 11 field points**: 169 rows, 107 distinct spots, 6 typhoons, reported depth > 0 for 164 | **Training presences**: one per distinct spot with any depth > 0. Each spot keeps its events and maximum depth for reporting | Parsed by the train command from the report PDF (downloaded once, checksum pinned) into `backend/.hazard_cache/mananga_annex11_points.csv`. Git-ignored and never committed |
| Annex 11 zero-depth reports (5 rows: **2 spots dry in every event**; 3 spots dry in one event but flooded in another, which count as presences) | Negative check only: the 2 always-dry spots should score below the presences | Same file |
| **GeoAlert's 6 map points** (`HistoricalRecord.location`, Flood) | **Held-out temporal test** (2021-2025). The 4 Mananga points are inside the evidence domain. The 2 Manipis road points should come out "not assessed" (a different mechanism), and the card says so | Shared database, read-only |
| **EOS-RS Tino flood proxy map** (Sentinel-1, 4 Nov 2025) | **Second held-out test**: flagged 30 m pixels inside the domain against unflagged buildings | Shapefile downloaded once (checksum pinned) into `backend/.hazard_cache/`. Git-ignored |
| GeoAlert barangay-only flood records | Barangay-level check on the card only | Shared database, read-only |

**Not used:**
- Copernicus GFM: it cannot see 89% of the city.
- Counts of any kind.
- Severity codes on records.
- News or DROMIC reconstruction. That can come later, for monitoring and Strategy A; it is not needed here.

### 3.2 Inputs (features); the allowlist is fixed before training

They are computed on the existing hazard grid (`susceptibility.city_grid`, zoom 14, about 9.4 m cells), then sampled at each building centre (Microsoft footprints, as for fire).

| Feature | Definition | Expected direction |
|---|---|---|
| `noah25_class` | UP NOAH 25-year flood class at the cell: 0 none, 1 low (< 0.5 m), 2 medium (0.5-1.5 m), 3 high (> 1.5 m) | up |
| `noah5_class` | The same for the 5-year map. **Included only if it passes the consistency check** (3.3); otherwise dropped and reported | up |
| `rel_height_river_m` | Smoothed DEM height minus the height of the nearest point on a mapped river centreline (OSM `waterway=river`), floored at 0 | down |
| `dist_river_m` | Distance to the nearest river centreline, used as log(1 + m) | down |
| `depression_m` | Depth of the cell's sink: the filled DEM minus the DEM (`fill_depressions` already exists) | up |
| `built_share` | ESA WorldCover built-up share within 100 m | (no constraint) |

These are the only columns a model may read. A test enforces the allowlist (section 7).

The 100-year NOAH layer is **excluded** unless it passes 3.3. Our copy currently has less flood area than the 25-year layer in many barangays.

### 3.3 Input checks (run by the feature command; results go on the card)

- **NOAH consistency:** the 5-year layer must lie within 25-year, and 25-year within 100-year. Allowed slack: 2% of flooded area [my call]. A failing layer is dropped and named.
- **DEM:** the city has ground above sea level. This existing guard is reused.
- **Coverage:** every area has its building count. Areas with no building get "not assessed (no buildings)".

### 3.4 Evidence domain (where the learned model may speak)

- **Domain:** buildings inside the convex hull of the 107 field spots, buffered by 300 m and clipped to the city [my call].
- **Out-of-distribution buildings:** a building whose features fall outside the 1st-99th percentile range of the training background is out-of-distribution. It is left out of its purok's score.
- **Assessed purok:** at least half of its buildings are in the domain and in range [my call].
- **Everything else** is "not assessed yet", with the reason:
  - outside the surveyed floodplain;
  - no buildings;
  - inputs out of range.

## 4. The model

### 4.1 Framing

A **presence-background** model:
- **Presences:** the field spots.
- **Background:** *target-group* background, meaning every building in the evidence domain, which the survey could have visited. This corrects for the survey route ([Phillips et al. 2009](https://www.whoi.edu/cms/files/Phillips_EcolApp_2009_53454.pdf)).
- **Output:** a **relative** susceptibility score, not a probability. Background buildings are "unknown", not "dry", so a calibrated probability cannot exist. The card says so in one plain sentence.

### 4.2 Candidates (fixed settings; no tuning on the test data)

| | Candidate | Settings |
|---|---|---|
| C1 | Logistic regression, presence vs. background | Background weighted so total weights are equal; unpenalised. If it fails to converge or any coefficient exceeds 20 on standardised inputs (separation), refit with a light ridge penalty (C = 1) and record it. This stands in for Firth's correction, which needs a package not installed |
| C2 | MaxEnt-type model | Linear plus hinge features (scikit-learn `SplineTransformer`, degree 1, 5 quantile knots) in a ridge logistic regression with C = 1: the logistic form of MaxEnt (Fithian & Hastie 2013). Chosen over the `elapid` package, which pulls in geopandas and rasterio |
| C3 | XGBoost with monotone constraints | The directions in 3.2; depth 2; 300 trees; learning rate 0.05; subsample 0.8 |
| C4 | MLP ensemble (scikit-learn) | 5 seeds; one hidden layer of 8; weight decay 1e-3; early stopping off |
| B0 | **NOAH-only benchmark** | Score = `noah25_class` |

Settings are the designer's calls, fixed before any fit. The builder may correct obvious defects, but only before the first real run, and records why.

### 4.3 Folds and the choice rule (pre-registered)

- **Folds:** spatial blocks by barangay, using the 6 barangays with field spots, with San Isidro's single spot merged into Dumlog. That gives 5 folds. A fold's spots and its background buildings are held out together.
- **Primary metric:** the continuous Boyce index on pooled out-of-fold scores ([Hirzel et al. 2006](https://www.unil.ch/biomapper/Download/Hirzel-EcoMod-2006.pdf)).
- **Secondary metric:** AUC against background.
- **Choice:** the simplest candidate (C1 < C2 < C3 < C4) wins, unless a more complex one beats it on Boyce by a paired bootstrap interval that lies wholly above zero. The bootstrap uses 1,000 repeats, resampling spots and background buildings with replacement **within each fold**, and recomputes both models' pooled out-of-fold Boyce each time.
- **Boyce settings:** the usual continuous form (moving window of one-tenth of the score range, 101 evaluation points, Spearman correlation), as in `ecospat.boyce`. The builder may use an equivalent published implementation.
- **Score scale:** every candidate's output is taken on its 0-1 scale (C1 and C4 predicted probability from the weighted fit, C2 cloglog, C3 predicted probability). That keeps the purok means in 5.1 comparable.
- **Final fit:** the chosen candidate is refit on all field spots.

### 4.4 Acceptance against NOAH-only (pre-registered; decides what ships)

The chosen model is adopted only if **all** of these hold:
1. **Better than NOAH:** its out-of-fold Boyce beats B0's, with the paired block-bootstrap interval wholly above zero.
2. **Temporal test:** at least 3 of the 4 GeoAlert Mananga test points fall in a Red or Orange purok. A point counts by the purok that holds it; a point in a not-assessed purok is a miss.
   - These points lie 16-78 m from survey spots (measured 2026-11-24). This gate therefore tests whether the places the 1990-2014 survey found still flood in 2021-2025, under a different source (news rather than interviews). It is a test across time, not across space.
   - The spatial blocks in 4.3 test new places.
3. **Not everything flagged:** Red + Orange hold no more than 50% of the domain's buildings.
4. **Test data seen last:** the model choice and the cut-off scores are written to the report before the code loads any test point or the EOS-RS map. A unit test checks the order.

The EOS-RS Tino test (Boyce and AUC inside the domain) is reported beside these, with the producer's caveat about urban areas. It is **not** a gate [my call], because the map misses pinned spots by 200-340 m.

**If any gate fails, NOAH-based classes ship** (section 5.3), and the card gives the failed gate in plain words.

## 5. Score → Red / Orange / Green

### 5.1 Purok score
- **Learned model:** the mean model score over the purok's valid domain buildings.
- **NOAH fallback:** the mean `noah25_class` over its buildings (5.3).

### 5.2 Cut-offs (from out-of-fold scores, fixed before the temporal test is opened)

1. Rank the assessed puroks by score.
2. **Red:** walk down the ranking until the Red puroks hold at least 50% of the field spots.
3. **Orange:** continue until Red + Orange hold at least 90% (false-negative emphasis).
4. **Green:** everything after that, within the assessed set.
5. If 90% cannot be reached before the scores tie at the bottom, Orange stops at the last distinct score, and the card states the recall actually reached.

The thresholds are stored as score values and applied to every assessed purok, including those with no field spot.

Labels shown:
- **Red**: "High flood susceptibility"
- **Orange**: "Moderate flood susceptibility"
- **Green**: "Low flood susceptibility (within the assessed floodplain)"
- **Grey**: "Not assessed yet", with the reason

The words "risk now", "likely" and "expected" never appear.

### 5.3 The NOAH fallback (the user's choice)

- **Coverage:** puroks with at least half their buildings inside any NOAH 25-year polygon, or within 300 m of one [my call]. Elsewhere, "not assessed" ("no NOAH flood model information").
- **Classes:** the same cut-off rule as 5.2, on all 169 field points. The labels name the source: "From UP NOAH's 25-year flood model".
- **The card states** that NOAH misses 32% of the reported flood spots.

### 5.4 Uncertainty

- **Stability:** refit the chosen model on 200 bootstrap resamples of spots and background. A purok whose class differs from its published class in more than 20% of the refits [my call] is published with an **"uncertain"** mark (hatched), with its class still shown.
- **Outlines:** areas with a low-confidence outline (263 of 670) carry "estimated outline" in their detail text.

## 6. Validation report (what the card shows; written by the train command)

- **Candidates:**
  - out-of-fold Boyce and AUC, with intervals;
  - the choice-rule verdict;
  - the acceptance verdict, with each gate.
- **Temporal test:** the 4 Mananga points with their classes; the 2 Manipis points shown as "not assessed (upland road runoff is a different kind of flood)"; EOS-RS Boyce and AUC; the 5 zero-depth reports' scores against the presences.
- **Barangay check:** the share of each Tino-recorded barangay's buildings in Red or Orange, against the others.
- **Class table:**
  - buildings and puroks per class;
  - field spots captured per class;
  - assessed and not assessed counts, with reasons.
- **Limits, in plain words:**
  - presence-only data;
  - one survey route;
  - events from 1990-2014;
  - the river works planned for 2026;
  - estimated outlines;
  - not a forecast;
  - the NOAH beta status and the dropped layers.
- **Credits:**
  - UP-TCAGP / University of San Carlos, Phil-LiDAR 1 (2017);
  - UP NOAH (ODbL);
  - EOS-RS / contains modified Copernicus Sentinel data (2025);
  - Copernicus DEM notice;
  - ESA WorldCover;
  - OpenStreetMap;
  - Microsoft footprints.
- **Since publishing:** new located floods (a pin or purok on a flood record, or an "Affected here" field mark on a flood zone) and the class each fell in. A flood in Green or Grey is listed as a miss. If, over the last 10 or more new located floods, fewer than 80% fall in Red or Orange [my call], the card shows **"Under review: recent floods fall outside the flagged areas"**. Nobody reclassifies by hand. The maintainer reruns training.

## 7. Guards (no counting, no hand on a level)

- The feature builder does not import `HistoricalRecord`, the history loaders, `forecast.py` or `purok_levels`. A test checks the imports.
- A test fails if a model input is not on the 3.2 allowlist.
- Labels are built only in the training module.
- No system setting, admin screen or endpoint writes a flood prediction class, a cut-off or a score. A test checks that `system_settings` has no flood-prediction keys and that no view writes the model files. The `history.*` settings belong to History and are not touched.
- `PATCH /api/hazards/<id>/` with `severity` in the body returns 400: "Levels come from the hazard models and can't be changed by hand." This applies to every hazard type.

## 8. Integration

### 8.1 Offline commands (on the developer's machine, as for fire)

**`manage.py build_flood_features`:**
- reuses the cached DEM, OSM and footprints;
- fetches and caches the NOAH 5-year layer from the mirror;
- runs the 3.3 checks;
- writes `apps/history/data/flood_purok_features.csv`: one row per area, with its building counts, domain share and `Purok.outlines_version()`;
- writes building-level features to `.hazard_cache` (git-ignored; too big to commit);
- updates `ATTRIBUTION.md`.

**`manage.py train_flood_model`:**
- fetches the label files if missing (checksums pinned), parses Annex 11 and reads GeoAlert's points read-only. The PDF parse needs `pypdf` (BSD-3), a local-only dependency like scikit-learn. The parse keeps only the table rows of the form `n lat lon modelled reported error event 100-Year`, and must give 169 rows, or the command stops;
- runs sections 4-6;
- writes `flood_purok_model.json` and `flood_purok_report.json`.

`flood_purok_model.json` holds:
- the version `<model or noah_fallback>@<sha1 of features + labels + settings, 12 chars>`;
- the source (`model` or `noah`) and the chosen candidate;
- the cut-off scores and the domain definition;
- the input hashes and the outlines version;
- per area: score, class, flags (`uncertain`, `not_assessed` with reason), building counts.

Training needs scikit-learn, xgboost and pypdf locally. **Production needs none of them**: the site reads per-area results.

The maintainer reruns both commands after a purok reload, after new located floods, or when NOAH publishes new maps. The brief permits that.

### 8.2 The website (reads files)

- **New `apps/history/flood_purok.py`**, modelled on `fire_purok.py`: load, mtime cache, the stale-outlines check. Unavailable reasons:
  - "The flood model has not been trained yet."
  - "The purok map changed since the flood model was trained; rerun build_flood_features and train_flood_model."
  - "The flood model file could not be read; rerun train_flood_model."
- **The forecast API (`views.forecast_result`, `/api/history/forecast/`):**
  - `FORECAST_HAZARDS` becomes `('Fire', 'Flood')`.
  - When Flood is included, the response gains `flood_results`: `purok_id`, `barangay_id`, `level` (`Red` / `Orange` / `Green` / null), `uncertain`, `not_assessed_reason`.
  - It also gains a flood block: `available`, `reason`, `source` (`model` / `noah`), `model_version`, `built_at`, and `basis` (one plain sentence saying it is susceptibility and does not change by month).
  - Flood's values are the same for every month, day and year asked. The response says so (`varies_by_month: false`), so the page never implies a monthly flood forecast.
  - Fire's rows and behaviour are unchanged.
- **The accuracy view** gains a flood entry from `flood_purok_report.json`, plus the live "since publishing" block (6).
- **Not changed:** `reports/decide_views` (an approved flood report keeps its history-based level, which is History), `purok_levels`, `area.py` and the `history.*` settings.
- **`HazardZoneDetailView.patch`:**
  - `severity` is rejected (7);
  - the resolve path is unchanged;
  - `pending_severity` and the second-officer approve / refuse flow stay, because automatic raises from attaching a Red-level report still use them;
  - the stale "severity?" comment in `reportApi.js` is fixed.
- **Hazard index:**
  - `FACTORS['flood']` is removed from `susceptibility.py`, so no future build makes the weighted flood layer;
  - `flood.png` and its `index.json` entry are removed, and `all` is rebuilt from landslide and fire only. Decoding the two published PNGs is enough; the full build need not rerun;
  - `terrain.png` and the observed-depth drawing tool stay.

### 8.3 Insert-only log (new table; migration only after a backup and the user's go-ahead)

- **Table:** `flood_purok_susceptibility_log`.
- **Columns:**
  - `purok_id` (plain integer, **no foreign key**), `purok_name`, `barangay` (foreign key, protect);
  - `model_version`, `source`;
  - `level` (null when not assessed), `score`, `uncertain`, `not_assessed_reason`;
  - `outlines_version`, `published_on`.
- Unique on (`purok_id`, `model_version`). Insert-only by trigger, as migrations 0008 and 0010 do.
- Written once per new model version by `log_hazard_predictions` under `HAZARD_LOG_WRITER`.

### 8.4 Frontend

- **Map, "Likely by month" (the predictive view):** Flood becomes a hazard choice beside Fire.
  - With Flood ticked, puroks are filled Red, Orange or Green; grey and hatched for not assessed; hatched for uncertain.
  - The legend reads "Flood: where floods tend to reach (from a machine-learning model; the same in every month, not a forecast of a flood)" and names the source (model or NOAH fallback).
  - With both Fire and Flood ticked, a purok takes the higher of its two levels, and hovering names both. This follows the combined-view pattern the map already uses in Past hazards.
  - It is public, like the fire view.
- **Past hazards (History):** no change.
- **Barangay panel:** the barangay's puroks listed by flood class (top 5, then "show all"), not-assessed ones grouped with their reason.
- **"This spot" reading:** the Flood part shows the class of the purok holding the spot, from the API ("Flood: High susceptibility (Sitio X)" or "Flood: not assessed yet"). It no longer reads the weighted raster. The builder finds the purok either from the purok outlines the map already loads for Past hazards, or with a small lookup endpoint, whichever the code supports more simply. Where areas overlap, the smallest area holding the spot is used.
- **Accuracy card:** a flood section (6), with the credits.
- **Decision dialog:** no change (a flood report's level is History's).

### 8.5 Tests

**Backend** (private test database, never the shared one):
- the feature functions on small synthetic grids;
- the NOAH consistency check;
- domain and out-of-distribution rules;
- the choice rule and acceptance gates on synthetic scores;
- the cut-off walk, including the unreachable-90% case;
- the stale outlines, missing file and unreadable file cases;
- the forecast API with Flood (shape, `varies_by_month: false`, fire unchanged);
- the decide flow for floods unchanged (still history-based);
- PATCH `severity` rejected for flood and fire, with resolve still working;
- the log is insert-only;
- the guards in 7.

**Frontend:** Flood in "Likely by month" (fills, legend, combined Fire + Flood), panel list, spot text and the accuracy section.

## 9. Rollout (each shared-database step needs a backup in Downloads and the user's go-ahead)

1. Build and test on the private test database.
2. `build_flood_features` and `train_flood_model` (offline; reading the shared database is read-only).
3. The user reviews the card and map on the stubbed local site (`run_readonly_site.py`).
4. Backup, then migrate the log table. **Shared database.**
5. First log run. **Shared database.**
6. The user commits and pushes: the code plus the `flood_purok_*` data files.

## 10. Approaches considered

| | **Chosen: learned susceptibility** | NOAH map only | Susceptibility + forecast now |
|---|---|---|---|
| What | Presence-background ML on 169 field spots; NOAH as an input and the benchmark | NOAH 25-year classes per purok | Also a city-level rain-driven flood watch |
| Why or why not | Real learning from located evidence, tested on held-out data, honest about where it can't speak | Simpler, but no learning; NOAH misses 32% of reported spots. Kept as the fallback | The forecast part cannot be validated with 6 flood days, and needs live feeds. Gated for later (11) |

## 11. Strategy A gate (recorded, not built)

Reopen flood forecasting when either:
- at least 20 dated, located flood days have been logged since this build; or
- a rain or water-level feed for the Mananga is secured (a DOST-ASTI PhilSensors request).

Until then, GeoAlert makes no flood forecast.

## 12. Calls the designer made (the user can overrule any)

1. Evidence domain = the field spots' hull plus 300 m; a purok is assessed when at least half its buildings are inside and in range.
2. Recall targets: Red 50%, Red + Orange 90%; at most 50% of the domain's buildings Red or Orange.
3. Gate 2 is "3 of 4" Mananga test points, read as a test across time. A 100 m exclusion rule would have dropped all four, since they lie 16-78 m from survey spots.
4. EOS-RS is reported, not a gate.
5. The uncertain mark appears when the class flips in more than 20% of 200 bootstrap refits.
6. The candidate settings in 4.2.
7. The NOAH fallback covers puroks with at least half their buildings in or within 300 m of a NOAH 25-year polygon.
8. NOAH layers that fail the consistency check (the 100-year copy, today) are dropped.
9. Flood shows inside "Likely by month" (the predictive view), labelled as not changing by month, rather than in a view of its own.
10. The Extreme second-officer approval stays. It belongs to live alerts, not to predictive analytics.
11. The flood prediction is public, like fire's.
12. "Since publishing" monitoring: under review below 80% over the last 10 or more located floods.

## 13. Settled with the user

- **Puroks outside the floodplain** when the learned model passes: **grey, "not assessed yet"** (the user's choice, 2026-11-24).
- **Landslide:** out of scope ("just the flood").
- **History vs predictive:** History is not changed (section 0).

## 14. Left to the builder

- File and function layout inside the modules named above.
- How the hull and buffer are computed (metric CRS UTM 51N, as `decide.py` uses).
- Caching and progress output for the commands.
- Exact copy wording within the rules above.
