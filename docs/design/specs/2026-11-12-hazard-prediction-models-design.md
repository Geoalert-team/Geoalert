# Hazard prediction models: flood, landslide and All hazards — design

Date: 2026-11-12
Status: draft for review. Section 1 approved 2026-11-12. Sections 2–4 written the same day,
on the user's instruction to continue to Section 4 without stopping to ask.
Branch: merge-scout

**Why.** The thesis brief asks for trained, feature-driven models for each hazard, with
counting allowed only as a benchmark. It also asks for one combined "All hazards" index, a
forecast that can be filtered by hazard, and outputs on a common 0–1 scale.

**Decisions made in the design discussion (2026-11-12):**
- Test logistic regression, random forest and XGBoost for each hazard, and keep the winner.
- 3 levels set by chance, the same for every hazard: High at 25% and up, Moderate at 15% and
  up, otherwise Low.
- All hazards = the chance that any hazard happens.
- Data files plus an offline test command, so the page request does no heavy work.

**Sections:**
1. Flood and landslide models (review and final specification)
2. From daily probabilities to the forecast
3. All hazards, filtering and outputs on a common scale
4. Accuracy card, tests and rollout

The fire model is unchanged in every section: same algorithm, features, training and
levels table.

**Amendment, 2026-11-12, after the build (the user's decision).** This resolves the conflict
between 2.6 ("Fire keeps its existing behaviour") and 3.4 ("no hazard is forecast by
counting"): fire never falls back to counting either.
- A fire model that does not beat counting stays in use, with status `in_use_not_better`.
- With too few records to train and test, or on a model error, fire is `unavailable` with a
  reason.
- A past period with fewer than 100 earlier fires uses the model trained on every record,
  with `in_training` set.
- A period from before the first fire record is `unavailable` ("Fire records start in
  January 2023.").
- The combined chance counts model figures only.

Before deciding, neural networks were tested against fire's Poisson model (MLP with a Poisson
loss; settings chosen on 2024–2025, one test on Feb–Oct 2026). The best tied it (Brier 0.1391
vs 0.1394) and fitted only when penalised into a nearly linear model, so Poisson stays. Script
and results: .superpowers/sdd/2026-11-12-hazard-prediction-models/fire-model-test-2026-11-12/.

**Amendment 2, 2026-11-13: the rain source is NASA POWER, not Open-Meteo (the user's decision:
"I will not use Open-Meteo, just keep it free").** Open-Meteo's free API is non-commercial only. Every
mention of Open-Meteo, ECMWF IFS and the 9 km grid below is superseded by this:
- **Source:** NASA POWER daily corrected rain (PRECTOTCORR, MERRA-2 and GEOS-IT models, local solar
  days). Free, no account, no restrictions on use (CC BY 4.0, commercial use included).
- **Grid:** 0.5 by 0.625 degrees, about 55 km. The whole city reads the one cell holding its average
  point (10.5 N, 123.75 E): the 10.25 N cell edge runs through Talisay, and the city is far smaller
  than a cell. Rain sets the timing; terrain alone sets barangays apart.
- **Delay:** a few days behind today. The live "rain so far" uses the same service, so training and
  live rain share one source.
- **Credit line:** "Rain data from NASA POWER (CC BY 4.0), processed into hazard chances by GeoAlert".
- **Evidence:** three sources were tested with the same records, terrain, folds and candidates. A
  scratch run on the Open-Meteo rain reproduced the shipped report exactly, so differences come from
  the rain alone.

  | | Flood: Open-Meteo / IMERG / POWER | Landslide: Open-Meteo / IMERG / POWER |
  |---|---|---|
  | Beats counting | yes / no (borderline) / yes | yes / yes / yes |
  | Timing ROC-AUC | 0.85 / 0.72 / 0.89 | 0.85 / 0.61 / 0.67 |
  | Pooled ROC-AUC | 0.93 / 0.87 / 0.96 | 0.98 / 0.94 / 0.95 |
  | Place AUC | 0.56 / 0.53 / 0.54 | 0.96 / 0.96 / 0.96 |
  | Calibration slope | 1.58 / 0.95 / 0.95 | 1.00 / 0.98 / 0.98 |

  NASA GPM IMERG Late (satellite, 0.1 degrees) needs an Earthdata account and missed small rain on
  several landslide days. POWER smooths storm peaks (Tino: 96 mm against 246 mm over two days), but
  the models learn on its scale. Scripts and results: .superpowers/sdd/2026-11-12-hazard-prediction-
  models/imerg-test/ (local, not in git).

No experiment in this document has been run under the design it specifies. Every number
below describes the data (counts, dates, availability checks), not model performance.

---

## Section 1 — Flood and landslide models: review and final specification

### A. Methodology assessment

#### What the original design gets right

- **One model per hazard, barangay-day rows, a binary "recorded" target.** This matches the
  data: records name a barangay and a date; only 8 of 31 have a map point.
- **No barangay names, IDs or past counts as inputs.** This keeps the models environmental.
- **Rain explains *when*, terrain explains *where*.** Both are physical drivers with data
  available for the whole city.
- **Three candidate algorithms, chosen by a held-out test, with counting kept as a
  benchmark.** This is the same discipline the fire model followed.
- **Log loss as the selection metric.** The app needs probabilities, not yes/no answers,
  and log loss scores probabilities directly.

#### Weaknesses found, and the change for each

| # | Weakness | Why it matters | Change |
|---|---|---|---|
| 1 | Leave-one-year-out validation | Trains on later years to predict earlier ones: temporal leakage | Rolling-origin folds (D.1) |
| 2 | Rain timing undefined | "Rain on the day" is only known after the day; forecast rain differs from recorded rain | Mode B with an end-of-day cutoff (B.3); forecast rain never enters these models |
| 3 | Study period "to the latest month" | The flood/landslide record was compiled from sources up to Dec 2025. 2026 has not been searched, so its days would enter as false non-events | Study period ends 2025-12-31 |
| 4 | Records with an approximate date | 4 flood records (8 Jul 2022) come from a blocked article, with the date given as "~8 Jul" | Left out of the main run; included in a sensitivity run (C.4) |
| 5 | Soil from SoilGrids | Blank (no value) in the built-up lowland, where floods happen; in the uplands, clay varies only 34–37% | Dropped from both models. Flood gets building density instead (B.1); landslide has no substitute (C.2) |
| 6 | Features that never change within a barangay | 22 barangays means 22 distinct terrain profiles. A tree model can learn "this profile = Manipis" and so count past events indirectly, the very thing the inputs rule forbids | Shallow trees, large leaves, physically signed monotonic constraints, and a leave-one-barangay-out robustness check (D.4) |
| 7 | Class imbalance handled by re-weighting | Weights and resampling distort probabilities, and too few events exist to recalibrate reliably | No re-weighting. Imbalance is handled through the metrics (PR-AUC, log loss) and model capacity (D.3) |
| 8 | Hyperparameter tuning | Training folds hold 1–5 event days; an inner tuning split would have 0–2 | Hyperparameters fixed in advance (B.4) and never changed after a test year is seen |
| 9 | Isotonic calibration | Needs hundreds of positives | Platt scaling only, and only when the inner calibration year has at least one event (D.5) |
| 10 | 40,000 rows read as 40,000 cases | Rows from the same day, storm and barangay are not independent | Uncertainty uses a block bootstrap that keeps each day's barangays and each week together (D.6) |
| 11 | Missing records read as "no event" | Records come from news reports, which cover notable events | The target is renamed "a *reported* event" throughout; added checks of ranking only (D.7) |

**Earlier exploratory figures are withdrawn.** Earlier in the design discussion I quoted
three figures from a quick exploratory check: 0.75 for flood timing, 0.80 for landslide
timing and 0.95 for where landslides happen. That check used leave-one-year-out (rejected
above), a rough 150 m elevation grid instead of the Copernicus rasters, and a two-part
model unlike the one specified here. Those figures are withdrawn and must not be cited.

---

### B. Final modeling specification

#### B.0 Targets

- **Flood target**: 1 if a flood (river overflow, flash flood or road flooding) was reported
  in barangay *b* on day *d*, otherwise 0.
- **Landslide target**: the same for landslides, including rockfall.
- **Day *d***: a calendar day in Asia/Manila time (UTC+8), 00:00–24:00. Record times are read
  in local time before taking the date.
- **Rows**: 22 barangays with boundaries × days from 2021-01-01 to 2025-12-31 =
  22 × 1,826 = **40,172 rows per hazard**.
- **Left out**:
  - sample records (`is_sample`)
  - records with no barangay (1 flood record, Tino city-wide)
  - records listed in `hazard_model_exclusions.csv` with a reason. In the main run this is
    the 4 flood records dated "~8 Jul 2022".
- If a barangay has more than one record on the same day, the row is still a single 1.

#### B.1 Flood inputs

**Rain** (B.3 defines the windows). All of these end at the end of day *d*:
- R0: rain on day *d*
- R1: rain on day *d*−1
- R3: the 3 days *d*−2 to *d*
- R7: the 7 days *d*−6 to *d*
- R14: the 14 days *d*−13 to *d*

**Terrain**: one value per barangay, the share of its 9.4 m grid cells that meet each
condition:

| Feature | Definition | Source in code |
|---|---|---|
| `hand_lt2` | height above nearest drainage < 2 m | `compute_factors()['hand']` |
| `hand_lt5` | height above nearest drainage < 5 m | same |
| `elev_lt10` | ground height < 10 m above the EGM2008 geoid (Copernicus' vertical reference, close to mean sea level) | `['elevation']` |
| `water_200` | within 200 m of a waterway: an OSM river, stream, canal, drain or ditch, or a channel traced from the heights with at least 0.25 km² draining into it | `['dist_water']` |
| `coast_500` | within 500 m of the coast (open sea or the OSM coastline) | `['dist_coast']` |
| `built_density` | mean buildings per hectare (replaces soil, see A #5) | `['building_density']` |

Building density stands in for paved, impervious ground. It targets road flooding (2 of
the 6 reported flood days) and has no gaps in the lowland, where SoilGrids is blank.

#### B.2 Landslide inputs

**Rain**: R0, R1, R3, R7 and R14, the same as flood.

**Terrain**: one value per barangay, the share of its 9.4 m grid cells that meet each
condition:

| Feature | Definition | Source in code |
|---|---|---|
| `slope_gt18` | slope > 18° | `['slope']` (from heights smoothed with σ = 1 cell) |
| `slope_gt30` | slope > 30° | same |
| `relief` | mean local relief: highest minus lowest ground within about 150 m | `['relief']` |
| `road_50` | within 50 m of an OSM road. This only stands in for possible road cuts; it does not show that a road cut exists | `['dist_road']` |
| `stream_150` | within 150 m of a waterway or traced channel (stream undercutting) | `['dist_water']` |

#### B.3 Rain timing: Mode B, an assessment using recorded rain

**Chosen: Mode B, with the cutoff at the end of day *d*.**
- The model answers: given the rain recorded through day *d*, how likely is a reported
  flood or landslide in barangay *b* on day *d*?
- Every rain input is from day *d* or earlier, and is recorded rain, never forecast rain.
- The output for day *d* is available once day *d*'s rain is in the archive, about one day
  later (on 2026-11-12 the archive ran to 2026-11-11).

**Why Mode B, from GeoAlert's existing requirements:**
- The GeoAlert forecast is a heads-up for preparing; the page itself says it is "not a
  warning". Live warnings come only from the DRRMO.
- Mode A (forecast rain) cannot be trained or tested honestly. Open-Meteo's archive of
  forecasts as they were issued starts in late 2024 for the 25 km ECMWF model and in 2025
  for the 9 km model. There are none for 2021–2023, so Mode A could see at most 4 flood days
  and 4 landslide days. (Checked 2026-11-12 with the Previous Runs API: no values for
  2021-06-11, 2022-07-07 or 2023-06-25; values present for 2024-09-30 at 25 km only, and
  for 2025-11-03.)
- **The two modes are not combined.** Forecast rain is never an input to these models.
  Section 2 will produce forward-looking chances by running the Mode B model over recorded
  rain from past years for the same calendar period (rain scenarios). Every input stays
  recorded rain. Mode A is deferred until several years of archived forecasts and enough
  events exist.

**Rain source, the same in training and in use:**
- Open-Meteo Historical Weather API, model `ecmwf_ifs` (ECMWF IFS, 9 km grid), variable
  `precipitation_sum`, timezone `Asia/Manila`.
- Read at each barangay's `point_on_surface`, a point guaranteed inside the boundary. The
  geometric centre can fall outside.
- **The most recent days** come from the Forecast API's `past_days` for the same model.
  Over 62 overlapping days these matched the archive exactly (checked 2026-11-12). That
  call's future days are discarded.
- **This rain is model-estimated, not measured by gauges.** The 9 km grid cannot resolve
  small storms. For example, the 18 Aug 2025 Bulacao road flood shows only 7 mm on its day.

**Window rules:**
- Windows are sums of the daily totals, inclusive, ending on day *d*.
- A window with any missing day is missing; it is never filled with 0.
- Rows with missing rain are dropped, and the number dropped is reported (none are
  expected; the 2021–2025 series was complete when downloaded).
- Logistic regression receives log(1 + mm), because rain amounts are heavily skewed. The
  tree models receive millimetres.
- The windows overlap (R3 is inside R7, which is inside R14). The L2 penalty and
  shallow trees handle that overlap. Logistic coefficients are read as a set, not one by
  one.

#### B.4 Preprocessing and candidate algorithms

The candidates for each hazard are below. Each one is a scikit-learn `Pipeline` fitted
only on the training fold:
1. `SimpleImputer(median)`, kept as a safety step; no gaps are expected.
2. `StandardScaler`, for logistic regression only.
3. The model.

Every candidate sees the same folds, the same rows and the same features.

| Candidate | Fixed settings, chosen in advance and never tuned on test years |
|---|---|
| Logistic regression | L2 penalty, C = 1.0, lbfgs, max_iter = 2000 |
| Random forest | 500 trees, max_depth = 3, min_samples_leaf = 200, max_features = "sqrt", monotonic constraints (below), random_state = 0 |
| XGBoost (`xgboost-cpu`) | 200 trees, max_depth = 2, learning_rate = 0.05, subsample = 0.8, reg_lambda = 1, min_child_weight = 0.1 (≈ 200 rows at this event rate), monotonic constraints, scale_pos_weight = 1, random_state = 0 |

**Monotonic constraints** (+1 means risk can only rise as the value rises):
- **Rain:** all five rain windows +1.
- **Flood:** `hand_lt2`, `hand_lt5`, `elev_lt10`, `water_200` and `built_density` +1;
  `coast_500` 0. The direction for the coast is unclear: no coastal barangay has a reported
  flood.
- **Landslide:** all five terrain inputs +1.

The constraints rule out splits that only separate one barangay from another without a
physical reason (A #6).

#### B.5 Selection rule

Defined in D.2 below; all three candidates are judged on the same held-out years.

---

### C. Data feasibility assessment

#### C.1 Available and verified

| Data | Where | Status |
|---|---|---|
| Flood and landslide records | `HistoricalRecord`: `occurred_at`, `barangay`, `hazard_type`, `hazard_subcategory`, `source`, `is_sample` | 23 flood + 8 landslide real records. 22 flood records have a barangay |
| Barangay boundaries | `Barangay.boundary` (PostGIS) | 22 with a boundary |
| Copernicus GLO-30 heights | `backend/.hazard_cache/dem_cop30_*.npy` (local, gitignored), read by `susceptibility.load_inputs` | Present. Resampled to the 9.4 m map grid |
| OSM waterways, coastline, roads, buildings | `backend/.hazard_cache/osm_*.json`, `ms_buildings_*.json` | Present (2026 snapshot) |
| Slope, relief, height above drainage, distances | `susceptibility.compute_factors()` | Present. The same code draws the map's susceptibility layers |
| Daily rain | Open-Meteo archive, `ecmwf_ifs` | Verified: complete 2021–2026, matches `past_days` |
| `xgboost-cpu` | PyPI | 3.2.0 available. New dependency |

#### C.2 Not available, and the alternative used

| Brief asks for | Status | Alternative |
|---|---|---|
| River level (stage) | No free history for the Mananga, Kinalumsan or Bulacao rivers | Rain over several days (R3, R7, R14) plus `hand_lt2`, `hand_lt5` and `water_200` |
| Soil type (SoilGrids) | Spot check, 6 points: blank in Tabunok and San Isidro (built-up areas are masked); 33.7–37.1% clay in Manipis, Tapul, Jaclupan and Camp IV | Flood: `built_density`. Landslide: none. Soil is noted as a limitation |
| Forecast rain for training (Mode A) | Archived forecasts only from late 2024 (25 km model) or 2025 (9 km model) | Mode B (B.3) |

#### C.3 What the records hold, after the exclusions

| Year | Flood rows = 1 (reported days) | Landslide rows = 1 (reported days) |
|---|---|---|
| 2021 | 7 (1: 12 Jun, river overflow) | 1 |
| 2022 | 0 (4 rows on ~8 Jul left out) | 2 |
| 2023 | 0 | 1 |
| 2024 | 0 | 1 |
| 2025 | 11 (4: 12 Aug, 18 Aug, 7 Oct, 4 Nov) | 3 (Camp IV on 25 Aug, the rest Manipis) |
| **Total** | **18 (5 days)**; prevalence 0.045% | **8 (8 days)**; prevalence 0.020% |

**What this means:**
- **Flood:** every training fold has one reported flood day (12 Jun 2021). Only the 2025
  test year has floods, so flood is really tested on one year, 4 days and 11 rows.
  Typhoon Tino alone (4 Nov 2025) is 8 of those 11 rows.
- **Landslide:** in every training fold, the only barangay with a landslide is Manipis.
  Where landslides happen is therefore learned from one barangay. Camp IV in 2025 is the
  single test of a barangay never seen with an event.
- **Flood types are mixed.** The 6 reported days cover three mechanisms:
  - river overflow (2021, Tino)
  - road flooding in the lowland (Jul 2022, Aug 2025)
  - flash floods in upland Manipis (Aug and Oct 2025)

  The lowland terrain inputs will not explain the Manipis flash floods. Results are
  reported for each type.

#### C.4 Records that are incomplete or unreliable

- **Reporting gaps.** The records were compiled from news (The Freeman, SunStar, GMA,
  Inquirer and others), which covers notable events. No flood is reported for 2022 (outside
  the excluded ~8 Jul records), 2023 or 2024. An empty barangay-day means "nothing was
  reported", not "nothing happened". Effects:
  - Chances describe *reported* events, so they read lower than the true rate.
  - The ranking (AUC, and which days and barangays rank highest) is the more reliable
    reading.
  - Heavy-rain days with no report count against every model as false alarms, even when
    the flood did happen.
- **Date accuracy.** Most records carry a date only. Some notes say "Night" or "After
  midnight", for example the 1 Oct 2024 landslide, so the true day can be off by one. The
  R1 input (rain on the day before) covers this partly. Every record keeps its recorded
  date; none are shifted.
- **Sensitivity runs:**
  1. The main design.
  2. With the ~8 Jul 2022 flood records included.

  Both are reported. Only run 1 chooses the model.
- **Better data, a recommendation for later:**
  - DSWD DROMIC and NDRRMC situation reports list affected barangays per typhoon and could
    fill 2022–2024.
  - Flood and landslide reports approved inside GeoAlert will add events from now on.

---

### D. Evaluation design

#### D.1 Rolling-origin temporal validation

| Fold | Train | Test | Flood test rows = 1 | Landslide test rows = 1 |
|---|---|---|---|---|
| 1 | 2021–2022 | 2023 | 0 | 1 |
| 2 | 2021–2023 | 2024 | 0 | 1 |
| 3 | 2021–2024 | 2025 | 11 | 3 |

- Each test year comes strictly after its training years.
- Everything fitted, including the imputer, scaler, Platt scaling, the benchmark and the
  alarm threshold, uses training years only.
- The test years are scored once, with the fixed settings in B.4. They are never used to
  change a model.

#### D.2 Metrics and model selection

For each fold, and pooled over 2023–2025 (all held-out rows together), the report gives:
- the number of rows = 1 and rows = 0, and the prevalence
- **log loss** (the selection metric)
- Brier score
- ROC-AUC
- PR-AUC
- precision, recall and a confusion matrix at the operational threshold below
- calibration (D.5)

ROC-AUC, PR-AUC and recall are undefined in a fold with no rows = 1 (flood folds 1–2); the
report says "undefined" there instead of filling in a number.

**Why PR-AUC.** At 0.02–0.045% prevalence, a model can raise hundreds of false alarms while
its false-positive rate stays tiny, because true negatives are so many. That keeps ROC-AUC
high. PR-AUC measures precision (how many alarms were real) against recall, so false
alarms show. A model with no skill scores the prevalence itself, about 0.0005, which is the
number to compare against. Accuracy is not reported: predicting "never" would score 99.95%.

**Operational threshold** (for evaluation only, not a hazard level):
- The cutoff value is set on the training years' own predictions, so that 1% of training
  barangay-days are flagged, about 80 barangay-days a year.
- Precision, recall and the confusion matrix on the test year use that cutoff.
- Hazard levels are left to Section 2.

**Selection:**
1. For each candidate, take the mean log loss over the three test years.
2. The lowest wins.
3. If a simpler candidate's log loss is within the 95% bootstrap interval of the
   difference (D.6), the simpler one is chosen. Simpler means logistic regression, then
   random forest, then XGBoost.
4. The winner is compared with the benchmark (D.3).
5. If it does not beat the benchmark, the report and the accuracy card say so. The winner
   still supplies the forecast (project rule); counting never replaces it.

#### D.3 The historical counting benchmark, and class imbalance

**Counting benchmark.** For test year *Y*, barangay *b*, and a day in calendar month *m*:

```
p = (k_bm + π · 30) / (n_m + 30)
```

- `k_bm`: rows = 1 for barangay *b* in month *m*, across the training years before *Y*
- `n_m`: days of month *m* across the training years before *Y*
- `π`: the training years' prevalence over all barangays
- 30: the strength of the prior, one month's worth of days. It keeps every probability
  above zero, so log loss stays finite.

This is the daily form of the app's own counting: a barangay's past frequency for the same
time of year, using only the years before. It is scored with exactly the same metrics.

**No-skill baseline.** The constant π is also reported. It is the floor for log loss and
Brier skill scores, and the PR-AUC baseline.

**Neither** is ever an input to a model.

**Class imbalance:**
- No re-weighting, oversampling or undersampling. These would inflate the probabilities
  that log loss scores and that GeoAlert shows, and there are too few events to
  recalibrate afterwards.
- Imbalance is handled by metrics that respect it (log loss, PR-AUC) and by limits on
  model capacity: large minimum leaf sizes and shallow trees.
- Logistic regression is fitted by penalised maximum likelihood, which is consistent for
  rare events. With this few events its coefficients are shrunk toward zero, which is noted
  as a limitation. Firth's correction would suit better but is not in scikit-learn; it is
  not added.

#### D.4 Spatial and temporal dependence

**Effective sample size.** The evidence comes closer to the number of reported days (5
flood, 8 landslide) than to the 40,172 rows. Rows share a day (the same rain across nearby
barangays), a storm (consecutive days) and a barangay (fixed terrain).

**Main evaluation:** rolling-origin, because the system predicts future conditions.

**Extra robustness check: leave-one-barangay-out over 2021–2025.**
- Train on 21 barangays and predict the 22nd.
- Report how well each barangay's average predicted risk ranks the barangays that ever had
  an event (AUC across barangays).
- **Why it is worth adding:** the forecast gives a number to every barangay, including the
  20 with no landslide report and the 12 with no flood report. This check shows whether
  terrain carries to barangays the model never saw with an event, or whether the model has
  memorised a barangay's terrain profile (A #6).
- It mixes years, so it is reported as a robustness check and never used for selection.
- The 2025 Camp IV landslide is the one strictly time-ordered test of a barangay never seen
  with an event, and it is reported on its own.

#### D.5 Calibration

- **Logistic regression** is not recalibrated: it is already a probability model fitted by
  likelihood.
- **Random forest and XGBoost:**
  - Platt scaling is fitted on an inner split of the training years only: train on all
    training years but the last, calibrate on the last.
  - If that last year has no rows = 1, Platt cannot be fitted, and the model runs
    uncalibrated. The report says which.
  - In practice: flood, never possible (2022 has no events in the main run); landslide,
    possible in every fold.
- **Isotonic regression** is not used: it needs far more positives.

**How calibration is judged:**
- **Observed against expected:** reported events compared with the sum of predicted
  probabilities, per test year and pooled. This is the main check.
- **Calibration slope:** pooled, with a bootstrap interval.
- Reliability diagrams are not drawn. With 1–11 events per year, every bin would be empty
  or hold one event.

#### D.6 Uncertainty

- **Method:** a moving-block bootstrap within each test year: 7-day blocks, all 22
  barangays kept together, 1,000 replicates.
- **Reported:** intervals for pooled log loss, Brier score, PR-AUC and the
  winner-minus-benchmark difference.
- **Used for:** the tie rule in D.2.
- With one storm-dominated flood test year, the flood intervals will be wide. That is the
  honest result.

#### D.7 Checks of ranking only (robust to under-reporting)

- **When:** across test days, does the city's highest predicted chance rank reported event
  days above the others? (AUC over days)
- **Where:** on test days with a reported event, does the model rank the hit barangays
  above the rest? (AUC over barangays, per event day)

These two checks split skill into timing and location. They depend less on whether a
quiet, heavy-rain day was a true non-event.

---

### E. Implementation plan (for Section 1's code only)

**New code:**
- `backend/apps/history/hazard_data.py`
  - Terrain features per barangay. It calls `susceptibility.load_inputs` and
    `compute_factors` on the cached heights and OSM data, then takes the share of grid
    cells inside each boundary.
  - Rain retrieval and window building (B.3).
  - Assembly of the barangay-day rows, targets and exclusions.
- `backend/apps/history/hazard_models.py`
  - Candidate pipelines, rolling-origin folds, benchmark, metrics, Platt, bootstrap,
    selection, and the leave-one-barangay-out check.
  - Produces one JSON report.

**New management commands:**
- `build_hazard_features` writes `apps/history/data/barangay_terrain.csv`.
- `fetch_rain` writes `apps/history/data/rain_daily.csv`: daily `ecmwf_ifs` rain per
  barangay point. It starts at the earliest day the archive serves for that model, and no
  later than 2020-12-18, so the first 14-day window of 2021 is complete. Earlier years add
  rain scenarios (Section 2). 2021–2026 was verified on 2026-11-12; a request for 2016–2017
  timed out, so the command logs the first day it actually got. It slows its requests to
  stay inside Open-Meteo's free limit.
- `test_hazard_models` runs D.1–D.7 and writes
  `apps/history/data/hazard_model_report.json`.

**New data files:**
- `apps/history/data/hazard_model_exclusions.csv`: `source_ref` and reason, starting
  with the 4 "~8 Jul 2022" flood records.

**New tests** (synthetic data, a private test database name; the shared test database
collides):
- `backend/tests/test_hazard_data.py`
  - window sums and missing days
  - the local-time day boundary
  - exclusions
  - share-of-cells features on a toy grid
- `backend/tests/test_hazard_models.py`
  - folds never train on test years
  - the benchmark uses training years only
  - metrics are undefined when a fold has no events
  - the tie rule
  - Platt is skipped when the calibration year has no events

**Changed:**
- `requirements/base.txt`: add `xgboost-cpu==3.2.0`.
- `apps/hazards/susceptibility.py`: possibly a small helper to return the grid and the
  factors without writing the map images. Behaviour unchanged.

**Not touched in Section 1:**
- `model_forecast.py` (fire)
- `forecast.py`
- the forecast views and serializers
- the frontend
- the database schema

**Note: a change to the approach chosen earlier.** That approach used "live rain: the last
92 days plus the next 16". Under Mode B the next-16-days forecast is dropped as a model
input. Only the recorded `past_days` remain.

---

### F. Methodology text for the capstone documentation

> **Flood and landslide prediction models.** GeoAlert estimates the probability that a
> flood or a landslide is reported in each of Talisay City's 22 barangays on a given day.
> One model is trained for each hazard on barangay-day observations from 1 January 2021 to
> 31 December 2025 (40,172 observations per hazard). The target is whether an event of
> that type was reported in the barangay on that day, compiled from news reports and
> official situation reports and linked to barangays. Sample records, records without an
> identifiable barangay, and records whose date could not be established are excluded.
> Because the sources report notable events, an observation without a report is treated
> as "not reported" rather than "did not occur", and predicted probabilities are
> interpreted as probabilities of a reported event.
>
> Predictors describe environmental conditions only. Barangay identifiers and historical
> event counts are excluded. Rainfall predictors are the daily totals on the day and the
> previous day and the 3-, 7- and 14-day totals ending on the day. They come from the
> ECMWF IFS 9 km model through the Open-Meteo Historical Weather API, and use only rainfall
> recorded up to the end of the day assessed. Terrain predictors are computed from the
> Copernicus GLO-30 elevation model and OpenStreetMap on a 9.4 m grid and summarised as the
> share of each barangay's area meeting physical conditions:
> - **Flood:** height above the nearest drainage below 2 m and below 5 m; elevation below
>   10 m; within 200 m of a waterway; within 500 m of the coast; and building density as a
>   proxy for impervious cover.
> - **Landslide:** slope above 18° and above 30°; local relief; within 50 m of a road, a
>   proxy for possible road cuts; and within 150 m of a stream.
>
> Soil texture from SoilGrids was considered but excluded: it is unavailable over Talisay's
> built-up lowland and nearly uniform across its uplands.
>
> Three algorithms are compared for each hazard: L2-regularised logistic regression, a
> depth-limited random forest, and depth-limited gradient-boosted trees (XGBoost). The tree
> models are constrained to respond monotonically in physically expected directions.
> Hyperparameters are fixed in advance because the small number of events does not
> support tuning. Models are evaluated by rolling-origin temporal validation: trained on
> 2021–2022 and tested on 2023, on 2021–2023 and tested on 2024, and on 2021–2024 and tested
> on 2025. All preprocessing and calibration are fitted on training years only.
>
> The selection criterion is mean log loss over the held-out years. The Brier score,
> ROC-AUC, PR-AUC, precision and recall at a threshold set on the training data, and
> observed-against-expected calibration are reported alongside it. Where candidates are
> statistically indistinguishable under a block bootstrap, the simpler model is preferred.
> The selected model is compared with a historical-frequency benchmark computed from
> training years only. A leave-one-barangay-out analysis tests whether the terrain
> predictors carry to barangays without recorded events.
>
> **Limitations.** The record contains 5 reported flood days and 8 reported landslide days.
> Only the 2025 test year contains floods, and every landslide in the training years
> occurred in a single barangay, so performance estimates carry wide uncertainty. Rainfall
> is model-estimated at 9 km and cannot resolve localised storms. River-stage observations
> are not available. The record under-reports events, which biases probabilities downward
> and penalises correct alarms on unreported days.

---

### Decisions in Section 1 (approved 2026-11-12)

1. **Mode B, with the cutoff at the end of day *d*.** Forecast rain is never a model input.
   The seasonal use in Section 2 runs the model over past years' recorded rain.
2. **The study period ends 2025-12-31.**
3. **The 4 "~8 Jul 2022" flood records are left out** of the main run and kept in a
   sensitivity run.
4. **Soil is dropped.** Building density replaces it for flood; landslide has no
   substitute.
5. **Hyperparameters are fixed in advance** (B.4), with monotonic constraints on the tree
   models.
6. **Leave-one-barangay-out is added** as a robustness check that never chooses the model.

---

## Section 2 — From daily probabilities to the forecast

Section 1's models give the chance of a reported event in one barangay on one day, using
rain recorded through that day. GeoAlert's forecast asks about a month, a month in a given
year, or the week around a date, often months ahead. This section turns one into the other
without ever feeding the models forecast rain.

### 2.1 The model in use

- `hazard_model_report.json` names each hazard's winning candidate and the study period it
  was tested on.
- When the cache is empty, the forecast refits that winner on the whole study period
  (2021-01-01 to 2025-12-31) with the fixed settings in B.4.
  - The deployed model is exactly the tested configuration, trained one fold later.
  - Records after the study period never enter it. They can enter only after the study end
    is moved and `test_hazard_models` is run again (4.6).
- **Calibration matches the test.** The deployed model is calibrated only if the winner was
  calibrated in all three test folds.
  - **Flood:** its tree models never are, because 2022, 2023 and 2024 have no flood events
    (D.5). So a flood winner is deployed uncalibrated, even though 2025 has events.
  - **Landslide:** its tree models are calibrated in every fold, so a landslide tree winner
    is deployed with Platt scaling, built the same way:
    1. Fit the base model on 2021–2024.
    2. Fit Platt on 2025.
    3. Refit the base model on all study years, keeping that Platt mapping.

    This is an approximation, and the accuracy card says so.
  - Logistic regression is never recalibrated (D.5).

### 2.2 Rain scenarios: the chance for a period

**Scenario years** are complete calendar years in `rain_daily.csv`: every day present for
every barangay, plus the 13 days before 1 January, so January's windows are complete.
- For a period in year *Y* (the Month-and-year or Exact-date views), only the years before
  *Y* count.
- For the plain Month view, every complete year counts.

Each scenario year is one plausible version of the period's weather. All of it is recorded
rain, so the inputs stay Mode B.

**For barangay *b*, hazard *h*, scenario year *s*, and the period's days *D* moved to year *s*:**

```
p(b, d; s) = the model's chance for b on day d, using rain windows computed from year s's
             recorded rain (including the 13 days before the period)
P_s(b)     = 1 - prod over d in D of (1 - p(b, d; s))     chance of at least one reported event
E_s(b)     = sum over d in D of p(b, d; s)                expected reported event-days
```

**What the forecast shows:**
- `probability` = the mean of `P_s` over the scenario years
- `expected_events` = the mean of `E_s`
- `range` = [lowest `P_s`, highest `P_s`], how much the weather alone moves the answer
- `rain_years` = the scenario years used

Scenario years count equally. Rain is climate, so the counting method's recency weighting
does not apply.

**Calendar rules:** 29 February maps to 28 February in a non-leap scenario year. A leap
scenario year keeps it only when the period contains it.

**Assumption:** days within a period are treated as independent given their rain. A storm
that causes reports on two days in a row is counted as two chances, which can overstate
`P`. The monthly levels check (4.2) shows whether it does.

### 2.3 The three period views

| View | Days *D* | Scenario years |
|---|---|---|
| Month | every day of month *m* | every complete year in the rain file |
| Month and year | every day of month *m* in year *Y* | complete years before *Y* |
| Exact date | the date ± 3 days (`forecast.DAY_WINDOW`) | complete years before the date's year |

**Levels** come from `model_forecast.level_for` (High from 25%, Moderate from 15%, otherwise
Low). They are always applied to the **month's** chance, also in the Exact-date view, where
the number shown is the week's. This is fire's existing rule, so every hazard and every
view reads its level the same way.

**Periods that have started or are over:**
- `probability` still uses only scenario years before *Y*. It is what the model would have
  said beforehand.
- The existing `actual` (events reported in the period) stays.
- **`recorded_rain_probability`** is new. It is present when at least one day of *D* has
  recorded rain in year *Y*:
  - Those days use the rain that actually fell; the remaining days use the scenarios.
  - This is the Mode B daily assessment the models were built for. The interface shows it
    as "With the rain recorded so far".
  - Days after the end of `rain_daily.csv` come from the live `past_days` call (cached for
    3 hours). If that call fails, those days count as not yet recorded, and the field
    covers only what the file holds.

**`in_training: true`** marks rows for periods inside the study period. The deployed model
learned from those records, so its figure there is not a fair test. The interface says "The
model learned from this period; see the accuracy check for results on years it never saw."
Fire's model avoids this by retraining before each period; flood and landslide can't, with
so few events before most periods.

### 2.4 Month-by-month profile

The 12-month chart uses each month's scenario chance (2.2), with the `year` parameter
respected as it is today:
- with a barangay: that barangay's chances
- with no barangay: the average over all barangays, as fire's chart does

### 2.5 Forecast rows

Every barangay with a boundary gets a row for each modelled hazard (22 per hazard), as
fire's rows do:

```
barangay_id, barangay, hazard_type
method: "model"
model: "logistic_regression" | "random_forest" | "xgboost"
probability, expected_events, level, range, rain_years
recorded_rain_probability    (only when 2.3 applies)
in_training                  (only when true)
years_hit, years_considered, events, last_occurred, typical_severity, actual
                             (history shown as context, from forecast.py; never part of the chance)
```

### 2.6 When a model cannot run

**Causes:**
- `hazard_model_report.json`, `rain_daily.csv` or `barangay_terrain.csv` is missing or
  can't be read
- scikit-learn or xgboost is not installed
- the fit fails
- there is no scenario year before the period

**What the forecast does:**
- That hazard's rows get `method: "unavailable"`, `probability: null`, `level: "None"`, and
  a `reason`.
- The hazard is listed in `unavailable_hazards`.
- The error is logged.
- (Amended 2026-11-12: fire no longer falls back to counting either; see the amendment at the top.)
- **Flood and landslide never fall back to counting** (the project rule). Fire keeps its
  existing behaviour.

### 2.7 Caching and cost

- **Cached for 6 hours, like fire's model:** the fitted pipeline and a table of daily
  chances for every barangay × scenario-year day.
- **Cache key:** the report, the rain file, the terrain file, and a signature of the
  study-period records (count, latest date, latest change).
- **Per request:** each view is then array sums over that table.
- **The live recent rain** (model `ecmwf_ifs`; its future days are dropped) is cached for
  3 hours.
  - It asks only for the days after `rain_daily.csv` ends, capped at `past_days=92`.
  - It sends one point per distinct Open-Meteo grid cell, not one per barangay.
    `fetch_rain` records the cell Open-Meteo actually served for each barangay, so
    barangays sharing a cell share one series.

**Many users (added 2026-11-12).** Browsers only ever call GeoAlert's server; no user
request reaches Open-Meteo. So Open-Meteo usage does not grow with the number of users:
- At most 8 live fetches a day, one per 3-hour cache window.
- Even counting every grid point and every 14 days of data as a separate call, that stays
  far below the free limit of 10,000 calls a day.

What a large audience does load is GeoAlert's own server. The design covers it:
- **One fit at a time.** A cache lock makes a single request refit the model after a
  restart or when the cache expires. Other requests wait for that result instead of each
  fitting their own.
- **Warm-up.** On the free host (Render) the disk and its file cache are wiped at every
  restart. The server is kept awake by the existing cron-job.org ping to `/api/hazards/`,
  so that ping also triggers the fit in the background if the cache is empty.
- **HTTP caching.** The forecast and accuracy responses are the same for everyone for a
  given set of parameters. They are sent with `Cache-Control: public, max-age=600`, so
  browsers (and a CDN, if the host has one) reuse them.
- **Open-Meteo is never required for the forecast.** If it is down, rate-limited or blocks
  the server, only "with the rain recorded so far" disappears. Every forecast comes from
  the files in the repo. This matters on shared hosts: Open-Meteo applies limits per IP
  address, so another app on the same address can use up the limit first.

### 2.8 Code

- **New: `apps/history/hazard_forecast.py`**
  - `use_hazard_models(result, events, period, hazards, barangay, today)`
  - plus the period and scenario helpers and the unavailable rows.
- **`HistoricalForecastView`** calls it after `model_forecast.use_models`, inside its own
  `try`, so a failure marks the hazard unavailable and never takes the forecast down.
- **`forecast.py` stays as it is.** It still supplies the history fields (2.5) and fire's
  counting fallback.

### Decisions in Section 2

1. Forward-looking chances come from running the Mode B model over recorded rain from past
   years (rain scenarios), never from forecast rain.
2. Scenario years count equally.
3. Levels are always applied to the month's chance, with fire's 15% and 25% cut-offs, in
   every view.
4. Periods that have started also show `recorded_rain_probability`, the daily assessment
   with the rain that fell.
5. Periods inside the study period are labelled `in_training`.
6. A model that can't run shows "unavailable", never counting.

---

## Section 3 — All hazards, filtering, and outputs on a common scale

### 3.1 One scale for every hazard

- Every row's `probability` is the chance of at least one reported event of that hazard in
  the period, from 0 to 1.
  - Fire: from its Poisson rate, as today.
  - Flood and landslide: from Section 2.
- Every `level` uses the same cut-offs on the month's chance.
- `"None"` is shown only when there is no figure: unavailable, or a hazard that wasn't asked
  for.

### 3.2 The combined chance ("All hazards")

The combined chance is the chance that at least one of the included hazards is reported in
the barangay in the period.

**Flood and landslide share the same storms.** So they are combined day by day inside each
rain scenario. Given the rain, they are assumed independent:

```
P_rain_s(b) = 1 - prod over d in D of (1 - p_flood(b, d; s)) * (1 - p_landslide(b, d; s))
P_rain(b)   = mean of P_rain_s over the scenario years
```

**Fire has no rain input,** so it is treated as independent of the rain-driven pair:

```
P_any(b) = 1 - (1 - P_fire(b)) * (1 - P_rain(b))
```

**Other rules:**
- A subset (for example "Fire, Flood") uses the same rule with only those hazards.
- `expected_events` is the sum over the hazards.
- The level comes from the combined chance for the month, with the same cut-offs.
- `top_hazard` is the hazard with the highest single chance, and `hazards` lists each
  included hazard's chance and level.
- An unavailable hazard is left out of the combined chance and named in `missing`.

**Limitations:**
- Combining within rain scenarios captures the main link between flood and landslide. Any
  link beyond the rain is ignored.
- Fire is assumed unrelated to rain.

The combined chance has no held-out test of its own (4.1).

### 3.3 API changes: `GET /api/history/forecast/`

**Parameters:**

| Parameter | Meaning |
|---|---|
| `hazards=Fire,Flood` | New. Comma list, case-insensitive. The rows and the combined chance cover only these. |
| `hazard_type_name=Flood` | Kept. The same as `hazards=Flood`. |
| neither | All three hazards. |

Giving both parameters returns 400. An unknown name returns 400 with the valid names.

**New and changed response keys:**
- `hazards_included`: the hazards this response covers.
- `combined`: one row per barangay:
  `barangay_id, barangay, probability, expected_events, level, top_hazard,
  hazards: [{hazard_type, probability, level}], missing: [...]`.
  Sorted by level, then chance.
- `by_barangay`: kept for the existing callers, now built from `combined` (level,
  top_hazard, probability, hazards). Its meaning changes from "the barangay's highest
  single level" to "the chance of any included hazard".
- `profile`: the single hazard's 12 months when one hazard is asked for; otherwise the
  combined chance month by month. `profile_method` is `"model"`.
- `model_hazards`: now lists every modelled hazard.
- `unavailable_hazards`: new.
- `results`: limited to the included hazards.

The view's docstring states the scale: chance from 0 to 1, levels Low, Moderate or High on
the month's chance.

### 3.4 Interface changes

**`forecastLevels.js`**
- `hazardsParam(types)` builds the `hazards` parameter.
- `combinedText(row)` gives "Fire 8% · Flood 3% · Landslide 30%".
- `FORECAST_DISCLAIMER` is reworded: fire from past fires; flood and landslide from rain and
  terrain over past years. It is still "a heads-up for preparing, not a warning"; live
  alerts still come only from the DRRMO.

**`BarangayLikelihood.jsx`** (Reports › Analytics and the DRRMO dashboard card)
- **When the page filter is All hazard types,** it shows a combined table: Barangay · All
  hazards (level) · Chance · Biggest share · Each hazard (`combinedText`) · What happened.
  The dashboard card shows the top 5 combined rows.
- **When one hazard is picked,** the per-hazard table stays:
  - The Chance column shows on every row.
  - A second line gives the `range` ("3–41% across past rain years").
  - A "With rain so far" figure appears when present.
  - The `in_training` note shows when it applies.
  - The "Past Novembers" column stays as history, retitled "On record in past Novembers".
- **"How this is calculated"** is rewritten:
  - one paragraph on fire's model (unchanged content)
  - one on flood and landslide (rain and terrain, with the winning model's name from the
    response)
  - one on the combined chance
  - the level cut-offs
  - Attribution, which the licence requires next to any place Open-Meteo data are
    displayed, not only in this explainer. The line "Rain data by
    [Open-Meteo.com](https://open-meteo.com/) (CC BY 4.0), processed into hazard chances by
    GeoAlert" appears:
    - under the "Likelihood by barangay" card
    - in the map legend of the Likely view
    - on the accuracy card

    "Processed into hazard chances" meets the licence's rule to say that changes were made.

  The counting paragraph goes, because no hazard is forecast by counting any more.

**`PublicMap.jsx`, "Likely" view**
- It requests `hazards=` the ticked layer types. Ticking or unticking refetches.
- Barangays are coloured by the `combined` level.
- The popup gives the combined chance and its breakdown, then each hazard's line.
- The legend title reads "chance of any of: …".
- The source note names the rain years for flood and landslide.
- With nothing ticked, there is no request and everything is grey, as today.

**`SeasonalOutlook.jsx`** (Analytics)
- Retitled "Seasons on record", with the sub line "What past years brought, counted from the
  archive. Not a prediction: the likelihood below comes from the models."
- Its contents stay. This keeps counting shown only as history (the brief's rule).

**`historyApi.js`:** comments updated for the new parameter and keys.

### Decisions in Section 3

1. The combined chance is worked out within each rain scenario for flood and landslide,
   then combined with fire as independent.
2. A new `hazards` parameter is added; `hazard_type_name` is kept; giving both is an error.
3. `by_barangay` keeps its shape but now means the combined chance.
4. The map colours barangays by the combined chance of the ticked layers.
5. The archive outlook is relabelled as history, not prediction.

---

## Section 4 — Accuracy card, tests and rollout

### 4.1 Accuracy endpoint: `GET /api/history/forecast/accuracy/`

**Fire:** `model_forecast.accuracy_reports` as it is today.

**Flood and landslide:** read from `hazard_model_report.json`, with `kind: "rain_terrain"`.

| `status` | When |
|---|---|
| `in_use` | The winner beats the counting benchmark on mean log loss, and the bootstrap interval of the difference excludes 0 |
| `in_use_not_better` | It does not. The model is still used; the card says it did not beat counting |
| `unavailable` | No report, or one that can't be read |

`stale: true` is added when the study-period records no longer match the signature saved in
the report (a record was added, changed or deleted). The card then asks for
`test_hazard_models` to be run again.

**Report fields:**
- study period; rows, rows = 1 and prevalence
- `winner`
- `candidates`: for each, mean log loss, pooled log loss, Brier, ROC-AUC and PR-AUC with
  bootstrap intervals, per-year figures, and whether it was calibrated
- `benchmark`, `no_skill`
- `threshold`: alarm rate, precision, recall, confusion matrix
- `calibration`: observed against expected events per year, plus the pooled slope with its
  interval
- `timing_auc`, `place_auc` (D.7), `lobo_auc` (D.4)
- `camp_iv` (landslide only)
- `sensitivity` (flood, with the ~8 Jul 2022 records)
- `by_type` (flood subtypes)
- `monthly_levels` and `monthly_brier` (4.2)
- `tested_at`, `data_signature`, `limits` (plain sentences for the card)

**Combined chance:** the response carries a note that it is built from the three tested
models and has no test of its own. A fair combined test would need all three hazards tested
on the same held-out years. Fire is tested on 2026, flood and landslide on 2023–2025.

### 4.2 Monthly check: the forecast as the app shows it

For each fold, `test_hazard_models` also scores the test year month by month, as the
forecast page would have shown it:
1. Each barangay-month gets its scenario chance (2.2), from the fold's model and rain years
   before the test year.
2. **Levels table:** for High, Moderate and Low, the barangay-months, the chance given, the
   share that had a reported event, and the events. This is the same layout as fire's
   table, and it checks the cut-offs and the day-independence assumption (2.2).
3. **Monthly Brier**, compared with the benchmark's monthly chance,
   `1 - prod(1 - p_bench)` over the month's days.
4. **Recorded-rain monthly chance** (2.3, using the test year's own rain): its Brier, so the
   daily assessment is scored too.

Fold 1 has only the rain years before 2023 that the file holds, which may be just 2021–2022.
The report lists the scenario years each fold used.

### 4.3 The accuracy card (`ForecastAccuracy.jsx`)

A new block for `kind: "rain_terrain"`:
- **Heading,** for example "Flood: rain and terrain model (logistic regression), in use".
  When `in_use_not_better`, it adds "did not beat counting on the years it never saw".
- **One line on the test:** "Tested on 2023, 2024 and 2025, each year trained only on the
  years before it: N reported rows on D days in those years."
- **Table 1:** each candidate's pooled log loss, Brier, ROC-AUC and PR-AUC, then the
  counting benchmark and no-skill rows, with the winner marked. Values that are undefined
  show as "–", with a footnote.
- **Table 2,** per test year: reported events, expected events (the sum of chances), and
  log loss for the winner and the benchmark.
- **Table 3:** the monthly levels (4.2).
- **Short robustness lines:** barangays it never saw (leave-one-barangay-out), the 2025
  Camp IV landslide, timing and place ranking, the sensitivity run.
- **The `limits` sentences.**
- **The card's sub line** becomes: "Fire uses its model only if it beats counting. Flood and
  landslide always use their rain and terrain model, and this card says when it does not
  beat counting."
- Tables scroll inside `fc-table-wrap` on narrow phones, as today.

### 4.4 Tests

**Backend** (Django test runner; run with a private test database through a throwaway
settings module, because `test_postgres` on the shared server collides):
- **`test_hazard_data.py`:**
  - window sums
  - a missing day makes its window missing
  - the Manila day boundary
  - exclusions
  - share-of-cells features on a toy grid
- **`test_hazard_models.py`:**
  - folds never train on their test year
  - the benchmark reads training years only
  - metrics are undefined in a fold with no events
  - the tie rule prefers the simpler model
  - Platt is skipped when the calibration year has no events
  - the fixed settings are used exactly
- **`test_hazard_forecast.py`:**
  - `1 − Π`, and the mean over scenario years, on toy daily chances
  - scenario years strictly before *Y*
  - 29 February
  - the ±3-day week
  - the level taken from the month's chance
  - `recorded_rain_probability` only when recorded days exist
  - `in_training` inside the study period
  - unavailable rows and no counting when a file is missing
  - every barangay gets a row
- **`test_forecast_combined.py`:**
  - the combined chance, worked by hand for one barangay
  - the flood and landslide pair combined within scenarios
  - subsets via `hazards=`
  - 400 for both parameters or an unknown name
  - the shape of `by_barangay`
  - `missing`
- **View tests:**
  - forecast and accuracy responses with a temporary report file
  - the `Cache-Control` header
  - only one fit when two requests find the cache empty (the fit is mocked)
  - the live recent-rain call asks only for days after the rain file ends, one point per
    grid cell
  - the forecast still answers when that call fails
- **Unchanged and still green:** `test_model_forecast.py`, `test_forecast.py`,
  `test_hazard_index.py`.

**Frontend** (`react-scripts test`):
- `forecastLevels` helpers (`hazardsParam`, `combinedText`)
- `forecastAccuracy.test.js`: the new block, undefined metrics, `in_use_not_better`,
  `stale`
- `forecastFilters.test.js` and `analyticsPanel.test.js`: the combined table when all
  hazards are shown
- a pure helper test for the map's combined colouring

### 4.5 Verification before calling it done

1. All backend and frontend tests pass. Full logs are saved to files, not filtered.
2. Run `fetch_rain`, `build_hazard_features` and `test_hazard_models` on the real data. Read
   the report and copy its numbers into the thesis from that file only.
3. Check by hand that one barangay's combined chance matches 3.2 from its row values.
4. Open the app (Analytics with All hazards and with each hazard, the public map with layers
   toggled, the DRRMO dashboard card, the accuracy card) and confirm each view.
5. Confirm the fire rows and fire's accuracy report are identical to before.

### 4.6 Rollout and upkeep

There is no database migration; the shared database is only read.

**Rollout, in order:**
1. `pip install -r requirements/base.txt` (adds `xgboost-cpu==3.2.0`).
2. `manage.py fetch_rain`: a few minutes, throttled.
3. `manage.py build_hazard_features`: reads `.hazard_cache`, or downloads Copernicus and
   OSM the way `build_hazard_index` does.
4. `manage.py test_hazard_models`: writes the report.
5. Restart the backend. Cache keys include the file signatures, so the old cache is not
   reused.

**Production** reads only the three data files in `apps/history/data/`, so it needs neither
`.hazard_cache` nor the Open-Meteo archive. It does call `past_days` for recent rain,
cached.

**Upkeep, written into the README:**
- Run `fetch_rain` once a year, or before a defence or demo, to add the newest complete
  year of rain scenarios.
- After flood or landslide records are added, or once 2026 has been searched:
  1. Move `STUDY_END` in `hazard_models.py`.
  2. Run `test_hazard_models`.
  3. Check the card.

**Licences and Open-Meteo's terms** (read on open-meteo.com on 2026-11-12):

**What the terms say:**
- **Data licence:** CC BY 4.0. Attribution with a link is required next to the displayed
  data (3.4).
- **The free API:** "for non-commercial use, rate-limited to 10,000 calls/day", 600 a
  minute, 5,000 an hour and 300,000 a month. It has "no uptime guarantee", and the pricing
  page says "Use the free tier for evaluation and prototyping."
- **Counted as non-commercial:** "Private or non-profit websites or apps that do not have
  subscriptions or advertising."
- **Counted as commercial:** "Websites or apps that have subscriptions or display
  advertisements", and commercial products.
- **Not addressed:** government or public-sector use, and the number of users.
- **Enforcement:** "We reserve the right to block applications and IP addresses that misuse
  our service without prior notice."

**What this means for GeoAlert:**
- GeoAlert is free, has no ads and no subscriptions, and serves the public, so it matches
  the non-commercial example.
- The number of users is not what the terms turn on. Ads, subscriptions and commercial
  products are.
- Government use is not named, and the free tier is described as for evaluation.

**Before go-live, a required step:** email info@open-meteo.com, describing GeoAlert as a
free public-safety information app run by the City of Talisay, with no ads or
subscriptions. Ask them to confirm in writing that the free API may be used, and keep the
reply with the project's records.

**If they say it counts as commercial:**
- **Take a paid plan.** Standard is 1 million calls a month, far more than needed; prices
  are given on request.
- **Or switch the rain source** to another openly licensed dataset, such as ERA5 from the
  Copernicus Climate Data Store. This means re-running all of Section 1's tests: training
  and live use must share one source (B.3), and ERA5 is coarser (25 km against 9 km).

Nothing is committed (the project's rule); the specs, plans and code stay uncommitted.

### 4.7 All files

**New:**
- `backend/apps/history/hazard_data.py`
- `backend/apps/history/hazard_models.py`
- `backend/apps/history/hazard_forecast.py`
- management commands `build_hazard_features`, `fetch_rain`, `test_hazard_models`
- data files `barangay_terrain.csv`, `rain_daily.csv`, `hazard_model_report.json`,
  `hazard_model_exclusions.csv` (in `backend/apps/history/data/`)
- `backend/tests/test_hazard_data.py`, `test_hazard_models.py`, `test_hazard_forecast.py`,
  `test_forecast_combined.py`

**Changed:**
- **Backend:** `backend/apps/history/views.py` (forecast and accuracy views),
  `backend/requirements/base.txt`, `backend/apps/hazards/susceptibility.py` (only a helper,
  if needed), the README (upkeep).
- **Frontend:** `components/Forecast/forecastLevels.js`, `BarangayLikelihood.jsx`,
  `ForecastAccuracy.jsx`, `SeasonalOutlook.jsx`, `pages/PublicMap.jsx`, `api/historyApi.js`,
  and their tests.

**Not changed:** `model_forecast.py` (fire), `forecast.py`, the database schema, and the
susceptibility map layers.

### Decisions in Section 4

1. Flood and landslide accuracy comes from the saved report, with a stale flag when records
   change.
2. The combined chance is labelled untested.
3. The monthly levels check validates the forecast as shown.
4. No migration.
5. A yearly rain refresh, and a rerun whenever records change.
