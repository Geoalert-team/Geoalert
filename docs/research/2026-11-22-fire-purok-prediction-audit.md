# Fire prediction at the purok level: audit, research and recommended architecture

*Written 2026-11-22. Nothing here has been built. This records the audit of today's fire prediction,
a feasibility test on the real data, the research, and the recommended design, so the decisions can
be made before the rebuild starts. Flood and landslide are out of scope.*

*Probe scripts (read-only, throwaway): `.superpowers/sdd/2026-11-22-fire-purok-model/probe/`
(git-ignored). Every number below comes from those scripts run on the shared database on 2026-11-22.*

---

## 1. Summary

1. **Today's fire prediction is barangay-level only, and its main input is each barangay's own fire
   history.** The Poisson model in `model_forecast.py` gives every barangay its own term, fitted to
   that barangay's past fires. That term is a smoothed count, which is the kind of counting the brief
   rules out. The purok colours on the map are plain counting (2 fires in 5 years is Moderate, 4 is
   Extreme), and the same rule sets the alert level when the DRRMO approves a fire report.
2. **The purok map was partly built from the fire records.** 151 of the 670 purok areas exist
   because a BFP fire address named them. 86% of those 151 have a recorded fire, against 4% of the
   other 519. A yes/no flag for "a fire address named this area" predicts where the 2026 fires
   landed better than any real model (AUC 0.82, against 0.67). **So no purok-level accuracy measured
   on past fires can be trusted as it stands.** An honest purok-level test needs fires recorded
   after the map is frozen, or fire coordinates.
3. **Purok features do carry some real signal, but it is modest.** In a model with no fire counts
   as inputs, building and road features ranked the puroks that burned in 2026 with AUC 0.67 (95%
   interval 0.57–0.75), above both counting benchmarks. The 20% of areas it ranked highest held about
   40% of the 2026 fires. On barangays the model had never seen, it scored AUC 0.60. Part of this
   skill may come from the map problem in point 2.
4. **Neural networks:** a small multilayer perceptron tied the plain Poisson regression on the time
   test, and did worse on unseen barangays. Neighbour (graph) features added nothing. LSTM, temporal
   and hybrid spatio-temporal networks cannot be trained on this data: the whole city has 46 months
   of fires, and 99.4% of purok-months have none.
5. **Recommendation:** a "where × when" Poisson model on a fixed grid of small cells. Each fire is
   counted as "somewhere in this purok", or "somewhere in this barangay" when that is all the address
   says. Purok and barangay chances are sums over their cells. A pre-registered test chooses between
   a penalised regression, boosted trees, a multilayer perceptron ensemble and a graph variant. Fire
   counts are never inputs; they are only labels and benchmarks. Sections 7 and 8 have the design and
   the alternatives.

---

## 2. Audit: what exists today

### 2.1 The fire forecast (barangay level)

| Part | Where | What it does |
|---|---|---|
| Model in use ("current") | `backend/apps/history/model_forecast.py` `rates_table` | Poisson regression per barangay-month: a one-hot term per barangay, 11 month terms, log area, log purok count, puroks per km². Penalty 0.01. Refitted from the records when they change; cached a week. |
| Contender ("pooled_exposure") | `backend/apps/history/fire_candidate.py` | Building count as exposure, 2 yearly waves, a penalised term per barangay. Compared one month ahead on each rebuild; adopted only if the paired log-score interval lies below 0. Not adopted on the real data. |
| Levels | `model_forecast.level_for` | High at a 25% monthly chance, Moderate at 15%, otherwise Low. |
| Benchmark | `backend/apps/history/forecast.py` | Counting: the share of past years with a fire in that month. Only used to score the model, and on the "Seasons on record" card. |
| Accuracy card | `ForecastAccuracyView`, `frontend/src/components/Forecast/ForecastAccuracy.jsx` | The held-back 9-month test against counting, the contender comparison, and the prediction log score. |
| Prediction log | `HazardPredictionLog`, `prediction_log.py`, `manage.py log_hazard_predictions` | Insert-only daily and monthly chances per **barangay**. Written only where `HAZARD_LOG_WRITER` is on. |
| Map | `frontend/src/pages/PublicMap.jsx`, "Likely by month" view | Fills **barangays** by the combined chance of the ticked hazards (`hazard_forecast.py`, 1 − Π(1 − p)). |

The latest real report (2026-11-12): Brier 0.140 against counting 0.175, AUC 0.68 against 0.62.
It does not significantly beat a plain per-barangay average. Most of its skill is knowing which
barangays burn more, and that knowledge comes from each barangay's own term, which is fitted to its
own count.

### 2.2 Counting found in the prediction system

| # | Mechanism | Where | Used by | Verdict under the brief |
|---|---|---|---|---|
| 1 | A purok's level = number of its past events in 5 years against thresholds (defaults 2 = Moderate, 4 = Extreme; Admin settings `history.period_years`, `history.moderate_at`, `history.extreme_at`) | `backend/apps/history/purok_levels.py` | `/api/history/purok-levels/` (map "Past hazards" purok fills, `purokLevels.js`); `area.py` (barangay panel per-purok levels, `AreaHistory.jsx`) | Counting turned into risk levels. Remove the levels for fire. Plain history (dates, counts) can stay as history if it is not labelled as risk. **Decision needed.** |
| 2 | A newly approved fire report's alert level = the highest count level among its puroks | `backend/apps/reports/decide_views.py` `_history` | DRRMO "Validate and push". An Extreme level triggers second-officer approval and alerts. | Counting decides a live alert. Replace it. **Decision needed** on what replaces it. |
| 3 | One term per barangay fitted to its own fires | `model_forecast.rates_table`, `fire_candidate` (u_b) | The fire forecast | A smoothed count presented as a model. Remove. |
| 4 | Share of past years with a fire in the month | `forecast.py` | Benchmark; "Seasons on record" card | Allowed: validation only, and the card is history, not prediction. Keep. |
| 5 | Count thresholds in the fake-hazard seeder | `seed_fake_hazards.py` | Test data only | Follows #1. |

### 2.3 Integration points to keep

- `/api/history/forecast/`: `results` rows (`barangay_id`, `hazard_type`, `probability`,
  `expected_events`, `level`, `method`, `in_training`), `combined`, `by_barangay`, `profile`, and the
  `hazards=` parameter. Flood and landslide keep their models; fire's chance still enters the
  combined chance as an independent hazard.
- The map's "Likely by month" view, `BarangayLikelihood.jsx`, `forecastLevels.js` and the accuracy
  card.
- The purok outlines (`/api/barangays/puroks/`, `PurokLayer`, sitio "leftover" geometry) and the
  purok panel (`AreaHistory.jsx`).
- The prediction log conventions: insert-only, `HAZARD_LOG_WRITER`, migrations only after a backup
  and the user's go-ahead.
- Deployment: Render's free plan (about 0.1 CPU, 512 MB, 120 s timeout, disk wiped on restart). This
  rules out training on the server. The flood and landslide pattern fits it: fit offline in a
  command, save the numbers, score with NumPy.

---

## 3. The data and its limits

| Item | Value |
|---|---|
| Real fires | 220, 2023-01-26 to 2026-11-20. By year: 36 in 2023 (likely under-recorded), 72, 63, and 49 so far in 2026 |
| Placed in a purok | 197. Another 23 name only a barangay; 6 fires sit in two puroks |
| Fire types (BFP) | 116 residential, 38 non-residential, 29 transport (vehicles), 37 non-structural (rubbish, grass, electric poles) |
| Cause | Empty on all 220 |
| Coordinates | None. A fire is placed by matching its address text to a purok name |
| Purok areas | 670, **all estimated** (`source = estimated`): 235 puroks, 223 sitios, 191 subdivisions, 21 zones. Point confidence is high for 141, medium for 251 and low for 260. 115 sit inside a sitio, so outlines overlap |
| Areas with any recorded fire | 152 of 670; 518 have none |
| Base rate | A fire in a given area in a given month: 0.64%. In a year: 7.4% |

**The map problem in detail.** `purok_points.csv` records where each name came from.

| Area's name came from | Areas | With a recorded fire |
|---|---|---|
| A BFP fire address | 151 | 130 (86%) |
| Other sources only | 501 | 22 (4%) |
| Not in the points file | 18 | 0 |

87% of all fire-to-area links land in areas that the fire log named. The purok research used the
2026 fires too, so the 2026 "test" fires helped draw the 2026 map. The outlines were then grown from
those points to hold each area's share of the barangay's houses. As a result, whether an area exists,
how big it is and what kind it is all depend partly on where fires happened. Features can partly pick
this up: building and road features tell "fire-log" areas from the rest with AUC 0.64 on unseen
barangays (fire-log areas are larger, have more buildings, and are more often sitios than
subdivisions).

Only 2 fires were recorded after 2026-09-20, and 1 after the last purok change (2026-11-12). There is
no clean purok-level test set yet.

---

## 4. Feasibility probe (throwaway, read-only)

**Inputs per area**, all from files already cached in `backend/.hazard_cache`:
- Microsoft building footprints: 78,931 building centres.
- OpenStreetMap: roads, main roads, waterways, coastline, 18 fire stations, 501 points of interest.

The features were: area, building count, building density, median spacing to the nearest building,
crowding (buildings within 10 m and 25 m), road density, main-road share, distance to a main road,
the coast and a fire station, building-to-road distance, points of interest, and the area's kind.
**No fire counts went in.**

**Test A, over time:** learn from 2023–2025 (154 fire-area links), test on 2026 (49 links in 45 areas).

| Model | Log score (lower is better) | AUC | PR-AUC (base 0.067) | Top 10% of areas hold | Top 20% hold | AUC inside each barangay |
|---|---|---|---|---|---|---|
| Same chance everywhere | 0.2687 | 0.50 | 0.067 | 4% | 12% | 0.50 |
| In proportion to buildings | 0.2728 | 0.61 | 0.105 | 22% | 37% | 0.58 |
| Barangay rate split evenly [counting, benchmark] | 0.2692 | 0.58 | 0.093 | 14% | 27% | 0.50 |
| The area's own past count [counting, benchmark] | 0.2858 | 0.61 | 0.101 | 22% | 39% | 0.60 |
| Poisson regression on features | 0.2617 | 0.67 | 0.144 | 27% | 41% | 0.70 |
| Boosted trees on features | 0.2598 | 0.68 | 0.143 | 33% | 45% | 0.68 |
| MLP ensemble on features | 0.2635 | 0.67 | 0.148 | 27% | 39% | 0.70 |
| Regression + neighbour features (simplified graph) | 0.2638 | 0.65 | 0.167 | 24% | 43% | 0.68 |

The 95% interval for the regression's AUC (resampling barangays) is 0.57–0.75. For the own-count
benchmark it is 0.52–0.68.

**Test B, over place:** leave one barangay out, all years. The features model scored AUC 0.60, the
MLP 0.55, boosted trees 0.60, and buildings alone 0.60. Inside each barangay, AUC was about 0.62.

**What carried the signal** (standardised regression coefficients): more buildings (+0.11);
subdivision rather than purok or sitio (−0.10, so formal subdivisions burn less); larger area
(+0.08); sitio (+0.06); and wider building spacing, which lowers the chance (−0.06).

**The operational trade-off** (regression, 2026). To catch 50% of the fires you must flag the top 25%
of areas; for 70%, the top 51%; for 80%, the top 61%; for 90%, the top 77%. At random you would need
50%, 70%, 80% and 90%.

**Reading it.** There is real but modest skill, enough to rank puroks inside a barangay, which a
split barangay figure cannot do (inside-barangay AUC 0.50). But the predicted rates are flat: a
typical area is 0.076 fires a year and the highest is 0.118. The model can rank areas but cannot
strongly separate them. Point 2 of the summary means these numbers are probably optimistic. The
hyperparameters were not tuned rigorously; this was a feasibility check, not the final evaluation.

---

## 5. Which model families fit this data

| Family | Fits the data? | Evidence here | Overfitting risk | Runs on the server? | Explainable? | Verdict |
|---|---|---|---|---|---|---|
| Penalised Poisson regression (GLM), optionally with spline terms | Yes: it is made for rare counts with exposure | Best or tied on both probe tests | Low | Yes (NumPy) | Yes: one number per feature | **Baseline and likely winner** |
| Multilayer perceptron (MLP), Poisson loss, small, weight decay, 5–10 seed ensemble | Yes, as a challenger: about 16k cells × 15 features is enough to fit a small one | Tied on time; worse on unseen barangays (0.55); the 2026-11-12 barangay test tied only when forced nearly linear | Medium | Yes (weights + NumPy forward pass; trained with scikit-learn, no new dependency) | Partly (permutation importance, partial dependence) | **Candidate in the test** |
| Gradient-boosted trees, monotone constraints, shallow | Yes, as a challenger | Tied (AUC 0.68) | Medium; needs fixed early stopping | Yes | Partly | **Candidate in the test** |
| Graph neural network, full GCN / GraphSAGE / GAT | No: about 200 events over 670 nodes leave too few positives to learn message-passing weights | — | High | Would need PyTorch | Low | Not trained |
| Simplified graph convolution (SGC; neighbour-averaged features into the regression or MLP) | Yes: it is the graph idea at the size the data allows | No gain (AUC 0.65–0.67) | Low | Yes | Yes | **Candidate in the test** |
| LSTM / temporal CNN / transformer | No: 46 citywide months; per-purok series are 99.4% zeros | Not trainable | Very high | No | No | Excluded; revisit at several thousand fires or with daily data |
| Hybrid spatio-temporal GNN (e.g. ConvLSTM, ST-GCN) | No: needs years of dense incidents | — | Very high | No | No | Excluded |
| Bayesian hierarchical / BYM2 random effects per area | Statistically sound, but each area's own effect is learned from its own fires | — | Low | Offline only | Yes | **Excluded by the brief** (a per-area effect is a shrunk count) |

Published benchmarks agree. On ordinary tables, tree models and linear models usually match or beat
deep networks, especially on small data (Grinsztajn et al. 2022). The urban fire systems actually
deployed (Atlanta's Firebird, Pittsburgh's risk pipeline) used tree models and logistic regression on
building and inspection records (Madaio et al. 2016; Singh Walia et al. 2018). Spatio-temporal neural
networks for urban fire are trained on far denser incident logs.

---

## 6. Features and data sources

Kept only where there is a fire-risk reason. **Free, commercial use allowed, no account** unless
marked.

| Feature | Why it matters for fire | Source | Licence | Account? | Resolution | Verdict |
|---|---|---|---|---|---|---|
| Building count, footprint area, spacing, crowding (within 10/25 m) | Exposure; tight spacing spreads fire and slows response; small, crowded roofs point to informal housing | Microsoft Global ML Building Footprints (cached; polygons need re-reading for areas) | ODbL | No | Per building | **Core** |
| Building presence by year, heights | Growth of new informal blocks; one-storey light materials versus taller concrete | Google Open Buildings 2.5D Temporal (2016–2023, 4 m) | CC BY 4.0 or ODbL | No (public download; check Philippine coverage) | 4 m | **Test** |
| Road access: road density, distance from buildings to a road a fire truck can use, main-road share | Response access; vehicle and electric-pole fires sit on roads | OpenStreetMap (cached) | ODbL | No | Per segment | **Core** |
| Travel distance to the nearest fire station along roads | Response time | OSM roads + stations (cached); BFP Talisay station list | ODbL | No | Per cell | **Core** |
| Land cover: built-up, grass, trees, bare | Grass and rubbish fires (26 of 220); built-up share | ESA WorldCover 2021 v200, 10 m | CC BY 4.0 | No (AWS `--no-sign-request`) | 10 m | **Core** |
| Population per cell | People and cooking or electrical load per area | WorldPop constrained 100 m (2015–2030) | CC BY 4.0 | No (HDX / WorldPop server; confirm) | 100 m | **Test** (100 m is coarse beside 50 m cells) |
| Points of interest: markets, shops, LPG and fuel sellers, schools | Commercial fire load; non-residential fires (38) | OSM (cached), Overture Maps places | ODbL; CDLA-Permissive 2.0 | No | Point | **Test** |
| Power lines | Electric-pole fires (11); electrical causes lead BFP's national figures | OSM `power=line/minor_line` (patchy) | ODbL | No | Line | **Test**; drop if OSM coverage is poor |
| Area kind (subdivision / sitio / purok) | Formal subdivisions versus older or informal settlements | GeoAlert's purok table | — | — | Area | **Use with care**: partly an artefact of naming (section 3) |
| Elevation, slope, distance to the coast or river | Coastal and riverbank informal settlements | Copernicus DEM (cached), OSM | Copernicus licence (free); ODbL | No | 30 m | **Test** |
| Weather: daily heat, humidity, wind, 30-day rain (dryness) | When: dry, hot months raise grass and electrical fires | NASA POWER (already used for rain), one cell for the whole city | NASA open data | No | 0.5° | **Test** in the "when" part; earlier tests found rain made fire worse |
| Month of year, holidays (New Year, Christmas) | Fireworks, cooking, March as BFP Fire Prevention Month | Calendar | — | — | — | **Test** |

**Left out:** NASA FIRMS hotspots (need a key; urban house fires are too small to detect); night
lights (need an account); poverty data (PSA publishes it only per municipality); Open-Meteo (ruled
out by the user on 2026-11-13).

**Missing data that limits purok-level accuracy, most important first:**
1. **Fire coordinates.** Ask BFP Talisay whether their incident system records GPS points. GeoAlert's
   own fire reports already require a pin, so new fires reported through GeoAlert will carry one.
2. **Official purok boundaries** from the barangay halls (still pending).
3. **Fire causes** (empty on all 220), which would allow separate electrical and cooking models.
4. **More years.** About 55 fires a year means each extra year adds roughly a quarter of the data.

---

## 7. Recommended architecture

### 7.1 The model

Fires are treated as a Poisson process over small grid cells and months:

```
expected fires in cell c in month t = exp( f(features of c)  +  g(month t) )

  f = "where": learned from cell features only (buildings, spacing, roads, land cover, ...)
  g = "when":  learned from the month (and, if it earns its place, citywide weather)

purok chance in month t    = 1 − exp( − Σ over the purok's cells )
barangay chance in month t = 1 − exp( − Σ over the barangay's cells )
```

- **Cells:** a fixed grid of about 50 m (about 16,000 cells over the city). The features are computed
  per cell, so they do not depend on the estimated purok outlines.
- **Labels:** each fire is "somewhere in this purok". It is "somewhere in this sitio" or "somewhere
  in this barangay" when that is all the address names. In the likelihood, a fire's chance is the sum
  over the cells it could be in. This is disaggregation regression (Nandi et al. 2023), the method
  malaria mapping uses for counts reported over large areas. The 23 barangay-only fires and the
  sitio-level fires therefore count without being given precision they do not have.
- **Fitting:** expectation-maximisation. The fires are shared out over their possible cells in
  proportion to the current rates, the model is fitted on those shares, and the two steps repeat
  until stable. Every candidate (regression, boosted trees, MLP) can then be fitted with scikit-learn
  as it is installed today. Because the model splits into "where" and "when", the spatial fit uses
  cell totals and the temporal fit uses citywide monthly totals, so both are small and fast.
- **No counting:** no input is a past fire count: not the purok's, its neighbours', or its
  barangay's, and no per-area or per-barangay term. Fires are only labels, validation and benchmarks.
- **One model for all fire types:** at 220 fires, splitting by type leaves too little in each. The
  features cover each type's exposure (buildings, roads, vegetation, power lines).

### 7.2 Choosing the model (pre-registered)

Candidates for "where":
- penalised Poisson regression (with optional splines);
- monotone shallow boosted trees;
- a Poisson-loss MLP ensemble (5–10 seeds, 1 hidden layer of 8–32 units, weight decay);
- SGC, which feeds neighbour-averaged features into the winner of the first three.

Candidates for "when":
- constant;
- two yearly waves;
- the waves plus NASA POWER heat and dryness;
- holiday flags.

All settings are chosen inside the training folds only, from small fixed grids.

**The rule:** a candidate replaces the penalised regression only if its paired log-score gain on the
held-out folds has a 95% interval wholly below zero. This is the rule `fire_candidate.verdict`
already uses. Ties go to the simpler model. The neural network is in the test on equal terms. It is
not favoured and it is not left out.

### 7.3 Validation

| Level | Labels | Split | Why |
|---|---|---|---|
| Barangay (sum of cells) | BFP's barangay field: **clean** | Rolling by year: learn 2023–24, test 2025; learn 2023–25, test 2026 | The one leak-free retrospective test; also compares with today's model |
| Purok, inside each barangay | Purok links: **leaky** (section 3) | Same years + leave one barangay out | Shows whether the model ranks puroks; reported with the caveat, never as proof |
| Purok, going forward | Fires after the map freeze | Prospective | **The only honest purok-level accuracy.** A purok prediction log, insert-only like today's. A first verdict after about 12 months (about 55 fires) |

**Metrics:**
- Poisson log score, the main one (proper and rare-event safe);
- Brier score;
- ROC-AUC and PR-AUC;
- calibration intercept and slope, plus a reliability plot by deciles;
- the share of fires caught by the top 10% and 20% of puroks;
- recall, precision and F1 at the chosen level cut-offs.

Each comes with a resampled 95% interval (by month and by barangay). Accuracy alone is never
reported.

**Class imbalance:** the Poisson likelihood models rare events directly, so there is no
oversampling or SMOTE, which would break calibration. Imbalance is handled where it matters
operationally, in the level cut-offs (7.4).

**Calibration:** if held-out reliability is off, a single recalibration (intercept and slope) is
fitted on the validation folds and checked on the test year.

### 7.4 From probability to Red / Orange / Green

The **probability** (the chance of at least one recorded fire in the purok in the period) is always
shown on its own. The **level** is an operational call made from it:
- **Orange or higher:** the cut-off is set on validation (never the test year) so that Orange + Red
  catch a target share of held-out fires. This is the false-negative guard.
- **Red:** the cut-off is where held-out puroks above it burned at no less than 2× the city average.
- Both cut-offs are then checked once on the test year and reported with their recall, precision
  and the share of puroks flagged.

The recall target is a DRRMO policy choice (section 10). At today's model strength, catching 80% of
fires means flagging about 60% of puroks Orange or Red.

### 7.5 Not overstating confidence

- Each purok's chance carries an interval from the ensemble or bootstrap spread.
- A **"Limited data"** flag shows where the purok's point confidence is low, its features fall outside
  the training range, or its interval is wide.
- The page states that the boundaries are estimates and how many fires the model learned from.

### 7.6 Integration

| Piece | Change |
|---|---|
| `manage.py build_fire_cells` (new) | Downloads and caches the sources, builds the cell features (`.hazard_cache` + a saved file in `apps/history/data/`) |
| `manage.py train_fire_model` (new) | Runs the test in 7.2–7.4 and writes the saved fit (weights, cut-offs, report JSON). Offline, as flood and landslide already work |
| Website | Loads the saved fit and scores cells with NumPy; purok and barangay sums. No refit on the server |
| `/api/history/forecast/` | Fire's barangay rows come from the cell sums (same shape); a new purok-level fire result |
| Map | "Likely by month" fills fire puroks by level, and barangays stay summed. The panel shows probability, level, the "Limited data" flag and the main reasons (top features) |
| Accuracy card | The new report: clean barangay test, purok test with its caveat, prospective log |
| Purok prediction log | A new insert-only table (migration only after a backup and your go-ahead) |
| Removed | The fire barangay one-hot model; the `pooled_exposure` contender; fire's count-based purok levels and the count-based report alert level (subject to section 10) |

---

## 8. Approaches considered

| | A. Purok areas as the units | **B. Grid cells summed to puroks (recommended)** | C. Buildings as the units |
|---|---|---|---|
| How | One row per purok; features over its estimated outline | 50 m cells; fires "somewhere in purok P"; sums per purok | One row per building; purok = sum of its buildings |
| Good | Simplest; quickest to build | Features independent of the estimated outlines; uses the barangay-only and sitio fires honestly; official boundaries later only re-sum, with no new features | Finest detail for house fires |
| Bad | Bakes the estimated outlines (shaped partly by fire addresses) into every feature; drops the 23 barangay-only fires; rebuild everything when boundaries change | More work (grid, shared-out fitting); results still limited by the leaky labels | 30% of fires are not building fires (vehicles, poles, grass, rubbish); 79k rows; footprints carry little per-building detail |

---

## 9. What would change the picture

- **Fire coordinates** (BFP data or GeoAlert report pins): clean labels at any scale. This is the
  largest improvement available.
- **Official purok boundaries:** under B only the sums change, and the purok-level test becomes cleaner.
- **More fires:** at about 1,000 a networked or temporal model might be worth retesting; at about
  55 a year that is many years away. The candidate test reruns on each retrain, so a neural network
  that starts winning would be adopted by the rule.

---

## 10. Decisions needed

1. Approach A, B or C (B recommended).
2. The recall target for Orange + Red (how many fires the flagged puroks must catch), which sets how
   many puroks are flagged.
3. The "Past hazards" purok colours: count-based levels today.
4. The alert level of an approved fire report: count-based today.

---

## 10a. Added later on 2026-11-22: the user's answers and existing models

**Answers so far:**
- **History stays as it is.** "Past hazards", its levels and the barangay panel are unchanged. Only
  "Likely by month" is rebuilt.
- **Approved fire reports** take the model's purok level instead of the count rule.
- **The 23 barangay-only fires** must be placed in a purok before the build, from evidence. The build
  waits until then. Their addresses name only the barangay, and four news searches found none of them.
  The checklist is `Downloads/Talisay-23-Fires-Without-Purok-2026-11-22.csv`. The likely sources are
  BFP's incident reports and the Talisay City Fire Station's Facebook posts (a logged-in search).
- **The user prefers an existing model**, trained on our data, over a model of our own design. A
  further concern: a panel reading the code might take a "count" in it for counting.

**Existing models checked:**

| Model | What it is | Can GeoAlert use it? |
|---|---|---|
| City of Pittsburgh / CMU `fire_risk_analysis` (GitHub, **MIT**, © 2017 mmadaio) | The Bureau of Fire's structure fire risk model (Madaio et al.; Singh Walia et al. KDD 2018). One row per property with a yes/no "fire" label. XGBoost classifier (learning rate 0.13, 1,500 trees, depth 3), with random forest and AdaBoost as the other candidates (`Allmodels.py`). Tested on the final year; scored with the confusion matrix, kappa, AUC, recall, precision and F1; risk = `predict_proba` | **Yes, as the reference recipe**: same model families, label, split and metrics, ported to Python 3 with credit. Its code cannot run as is: Python 2, removed scikit-learn modules, and Pittsburgh data feeds. Its settings were tuned for about 20,000 properties, so they run as one candidate next to re-tuned ones |
| DeKalb County `FIRE-2023` (GitHub, **MIT**) | Random forest and AdaBoost tuned on Brier and log loss, ranking 1,046 multifamily properties | A second reference for tuning on probability scores |
| San Francisco `datasci-firerisk` | Notebooks | **No licence**: not reusable |
| UP Cebu FireCheck (DOST-PCIEERD, 2019–2020) | Expert-weighted fire hazard maps (building density, construction materials, urban heat island) for Cebu City, Mandaue and Lapu-Lapu | Does not cover Talisay; not public; method not published |
| Fire Weather Index (Canadian system; ASMC publishes it for ASEAN) | Weather-based danger for vegetation fires | One citywide value; no evidence for house fires. At most a candidate input for timing |
| HazardHunterPH (PHIVOLCS) | Seismic, volcanic and hydro-meteorological hazards | No fire layer |

No ready-made model covers Talisay's puroks. Every urban fire system found is retrained on its own
city's fires.

**What the panel concern changes:** the label is a yes/no `fire_occurred` per purok-month, as in
Pittsburgh's `fire` column. No input is built from fire records, and a test fails the build if one
ever is. Features are named for what they measure. The historical-frequency baseline lives only in
the evaluation command and is named as a comparison.

## 11. Sources

- Nandi, A. K., Lucas, T. C. D., Arambepola, R., Gething, P., & Weiss, D. J. (2023). disaggregation:
  An R package for Bayesian spatial disaggregation modeling. *Journal of Statistical Software*,
  106(11). https://doi.org/10.18637/jss.v106.i11
- Madaio, M., et al. (2016). Firebird: Predicting fire risk and prioritizing fire inspections in
  Atlanta. *KDD 2016*. https://arxiv.org/abs/1602.09067
- Singh Walia, B., et al. (2018). A dynamic pipeline for spatio-temporal fire risk prediction.
  *KDD 2018*. https://www.cmu.edu/metro21/projects/smart-infrastructure/fire-risk-analysis.html
- Grinsztajn, L., Oyallon, E., & Varoquaux, G. (2022). Why do tree-based models still outperform deep
  learning on typical tabular data? *NeurIPS Datasets and Benchmarks*.
- Wu, F., et al. (2019). Simplifying graph convolutional networks. *ICML 2019*.
- Buffington et al. (2021), area-level fire forecasting over 3,392 US tracts.
  https://doi.org/10.1016/j.compenvurbsys.2021.101633 (via the 2026-11-13 report)
- Jennings, C. R. (2013). Social and economic characteristics as determinants of residential fire
  risk in urban neighborhoods: A review. *Fire Safety Journal*, 62, 13–19.
- Ma et al. (2025). From occurrence to consequence: A comprehensive data-driven analysis of building
  fire risk. https://arxiv.org/abs/2503.22689
- Roberts, D. R., et al. (2017). Cross-validation strategies for data with temporal, spatial,
  hierarchical, or phylogenetic structure. *Ecography*, 40, 913–929.
- Gneiting, T., & Raftery, A. E. (2007). Strictly proper scoring rules, prediction, and estimation.
  *JASA*, 102, 359–378.
- Van Calster, B., et al. (2019). Calibration: the Achilles heel of predictive analytics. *BMC
  Medicine*, 17, 230.
- Google Open Buildings 2.5D Temporal (CC BY 4.0 or ODbL).
  https://developers.google.com/earth-engine/datasets/catalog/GOOGLE_Research_open-buildings-temporal_v1
- ESA WorldCover 2021 v200 on AWS (CC BY 4.0, no account). https://registry.opendata.aws/esa-worldcover-vito/
- WorldPop constrained population, Philippines (CC BY 4.0). https://geo.btaa.org/catalog/2b23fa77-c529-4978-90d7-21a89851c7f4
- BFP on electrical causes and informal settlements (news).
  https://www.sunstar.com.ph/davao/residential-squatter-areas-susceptible-to-fire-incidents
- Earlier GeoAlert research: `docs/research/hazard-prediction-models.md` (2026-11-13).
