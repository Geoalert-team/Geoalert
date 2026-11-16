# Hazard models v2: two-part flood and landslide, pooled fire, saved fits and a prediction log — design

Date: 2026-11-13
Status: APPROVED 2026-11-13. Sections 1–5 were approved one by one in the design discussion, then
the written spec was approved, with the user choosing all 19 rain years for the month scenarios
(3.2).
Branch: merge-scout. Never committed (the project rule): this file, the plan and the code stay
uncommitted.

**Why.** The research report `reports/GeoAlert hazard prediction models.md` (section G) found that
the number of events, not the algorithm, limits GeoAlert's models: flood has 18 reported
barangay-days on 5 storm days, landslide 8 days (7 in Manipis). It recommends a small two-part
model for flood and landslide, outside evidence for "where" and for more landslide days, a pooled
Poisson model with an exposure offset for fire, saved fits served without machine-learning
libraries, and a log of every prediction so the 2026 wet season becomes a real test. The user asked
to "do what is recommended, what is best for each hazard", on two conditions: **only if it is
better, and never counting.**

**Decisions made in the design discussion (2026-11-13):**
- UP NOAH flood-hazard maps may be used as a **hidden input** to the flood model, never drawn on the
  map. This does not revive the official-hazard-maps display cancelled on 2026-11-05.
- The NASA Global Landslide Catalog (no licence stated) is used to **train and test, kept private**:
  raw records live only in the git-ignored `backend/.hazard_cache/`; only fitted numbers reach the app.
- Scope: **models + saved fits + an insert-only prediction log.** No model-version registry table,
  no shadow mode, no promote command.
- Approach A: Firth-penalised logistic regression with the FLIC intercept correction, written in
  NumPy, fitted offline. Not PyMC (too slow for ~65 refits per hazard and needs a C compiler), not
  rules as the live forecast (they give no month chances).
- A new model goes live only under a rule written here, before any run. Otherwise the current model
  stays and the accuracy card says why. **No hazard is ever forecast by counting**; a counting-style
  rate appears only as a benchmark row in the tests, as today.

**Sections:**
1. Flood and landslide models
2. Testing, and the rule for replacing the current model
3. Saved fits, serving, and the prediction log
4. Fire
5. Accuracy card, rollout and tests

---

## Section 1 — Flood and landslide models

### 1.1 The shared form

For barangay *b* on day *d*:

  p(b, d) = q(d) × a_b

- **q(d), "when":** the chance that day *d* is an event day — a reported flood anywhere in Talisay,
  or a reported landslide in Talisay and the neighbouring uplands.
- **a_b, "where":** the chance that barangay *b* has a reported event, given that the day is an
  event day. It is fixed per barangay; it does not depend on the day.

Every chance is a chance of a **reported** event: "no record" means "not recorded", not "nothing
happened". Both factors lie in [0, 1], so p does too.

### 1.2 Firth's method and FLIC (new module `apps/history/firth.py`, NumPy only)

- **Firth logistic regression.** Maximises the log-likelihood plus ½·log|I(β)| (the Jeffreys
  penalty). Newton iterations on the modified score U*(β) = Xᵀ(y − p + h ⊙ (½ − p)), with h the
  diagonal of the hat matrix W^½X(XᵀWX)⁻¹XᵀW^½, and step-halving when the penalised likelihood
  falls. Converged when the largest change in β is under 1e-8; more than 100 iterations raises an
  error (never a silent result). Coefficients stay finite under perfect separation.
- **FLIC.** Firth pulls the average chance toward one half. FLIC keeps Firth's slopes and re-fits
  only the intercept by ordinary maximum likelihood with the offset Xβ (slopes fixed), so the mean
  predicted chance on the training rows equals the observed event rate. With several intercepts
  (landslide's two eras, 1.4), each is re-fitted on its own rows.
- **Firth conditional logit** (for landslide's "where", 1.4): on each event day, the chance that
  barangay *b* is the one hit is exp(β·s_b) / Σ_j exp(β·s_j). One parameter, fitted by Newton on
  the conditional log-likelihood plus ½·log I(β).
- No new dependency. `firthmodels` (MIT, one maintainer, beta, no FLIC) is used once, in a
  throwaway check outside the project, to confirm the fits agree; it is not added to requirements.

### 1.3 Flood

**When.** One row per city-day from 2021-01-01 to 2025-12-31 (the study period, unchanged), about
1,826 days.
- Outcome: 1 when any kept flood record (real, not excluded by `hazard_model_exclusions.csv`) is
  dated that day. A record with no barangay still counts here; it counts toward no barangay in
  "where".
- Inputs, fixed now: **log(1 + 3-day rain)** (r3, the NASA POWER sum of days d−2..d), and the
  **storm flag** (1.5).
- Fit: Firth, then FLIC. 1-day rain is left out: the event budget (about 3–6 parameters for 18
  events, fewer for 5 storm days) does not allow it.

**Where.** A fixed exposure score E_b per barangay, built before any test and never fitted to the
records:

  E_b = (buildings in NOAH 25-year Medium/High + buildings in NOAH 100-year Medium/High
         + buildings on ground under 2 m above drainage) / 3

- Buildings: the Microsoft building-footprint centres already cached in `.hazard_cache`
  (`ms_buildings_132330002.json`, ODbL). The cached centres are clipped to an earlier bounding
  box; `build_hazard_features` reuses them only when they cover the city's bounding box, and
  otherwise downloads the tile again (about 31 MB).
- NOAH: the Cebu shapefiles from the bettergovph mirror on Hugging Face (`Flood/25yr/Cebu.zip`
  16 MB, `Flood/100yr/Cebu.zip` 103 MB, no login, ODbL). Each holds 3 multipolygons with field
  `Var`: 1 Low, 2 Medium (over 0.5 m), 3 High (over 1.5 m); WGS84. Medium/High = `Var` ≥ 2.
- Height above drainage: the `hand` layer that `susceptibility.compute_factors` already computes
  from the Copernicus DEM.
- A building belongs to a barangay when its centre falls in a grid cell labelled with that barangay
  (the existing `draw_polygons` labels). NOAH polygons are clipped to the city box and rasterised on
  the same grid.

  a_b = 1 − exp(−λ · E_b)

- λ is the only number taken from the records: it is solved (one-dimensional, monotone) so that
  Σ_b a_b equals the mean number of barangays hit per flood day in the training rows (3.6 on the
  whole study period: 18 ÷ 5). λ does not change the ranking of barangays, so the "where" ranking
  is scored on the 18 records with nothing fitted to them.
- **Not done:** a separate drainage-flood channel. Only 3 records are drainage floods (Tabunok), and
  the report itself says that channel cannot be fitted.

### 1.4 Landslide

**When.** One row per region-day, in two eras:
- **Catalogue era:** 2007-01-01 to the last day of the month of the catalogue's last record (the
  catalogue ends in 2017). Outcome: 1 when a NASA Global Landslide Catalog record within **20 km**
  of the Talisay centre (1.5) is dated that day (`event_date`, read as the local date given).
  Records excluded: any whose text fields name Negros (the 2012-09-05 "Sitio Camp 5" record is
  Talisay, Negros Occidental), plus any listed in a new hand-kept file
  `data/landslide_catalogue_exclusions.csv` (`event_id,reason`; ids and reasons only, never the
  records).
- **GeoAlert era:** 2021-01-01 to 2025-12-31. Outcome: 1 when any kept GeoAlert landslide record is
  dated that day.
- 2018–2020 are left out: neither source covers them.
- Inputs, fixed now: **log(1 + 3-day rain)**, **log(1 + 14-day rain)**, and **one intercept per
  era** (no common intercept). The catalogue covers a wider area and was compiled from news, so its
  base rate differs; the slopes are shared. The forecast uses the **GeoAlert-era intercept**.
- Rain: the same NASA POWER city cell (10.5, 123.75) for every day in both eras, because thresholds
  must come from the rain source used live. `fetch_rain` therefore reaches back to 2006-12-18.
- Fit: Firth, then FLIC on each era's own rows.

**Where.**

  a_b = 1 − exp(−λ · exp(β · s_b)),  s_b = share of the barangay steeper than 18° (`slope_gt18`)

- β is fitted with the Firth conditional logit (1.2) on event days that name a Talisay barangay:
  GeoAlert's 8 records, plus catalogue records whose `location_description` names a Talisay
  barangay (matched with `apps/barangays/aliases.canonical`, so "Camp 4" is Camp IV). A catalogue
  record placed only by coordinates never decides a barangay.
- λ is solved so that Σ_b a_b equals the mean number of barangays per landslide day in the named
  training events (1.0 today).

### 1.5 The storm flag and the Talisay centre

- **Talisay centre:** the centroid of the union of the barangay boundaries, computed once in
  `fetch_storms` and in `test_hazard_models` from the database and written into their outputs.
- **Storm flag for day d:** 1 when any IBTrACS track point (fields `ISO_TIME` in UTC, `LAT`, `LON`;
  every storm type, tropical depressions included) lies within **300 km** (great-circle) of the
  Talisay centre at a time t with (end of day d in Asia/Manila) − 72 h < t ≤ (end of day d in
  Asia/Manila). Track points are used as given (3-hourly); no interpolation. The 300 km radius is
  fixed now, not tuned.

### 1.6 The current model and what is removed

- **The model in use today**, pooled logistic regression (`logistic_regression` in
  `hazard_models.py`: 5 rain sums and 6 flood or 5 landslide terrain features, median imputation,
  log rain, scaling, L2), stays as the model the new one must beat. Its features and settings do not
  change.
- **Removed:** the random forest and XGBoost candidates, `select_winner`, the Platt calibration that
  only trees used, and `xgboost-cpu` from `requirements/base.txt`. Both lost to logistic regression
  in the 2026-11-12 test.
- The landslide catalogue era is used only by the new model. The current model trains on the
  GeoAlert era only, as now.

---

## Section 2 — Testing, and the rule for replacing the current model

New module `apps/history/hazard_tests.py`. Both models, and every baseline, are scored on the same
rows. Every fit sees its fold's training rows only.

### 2.1 Four test designs

1. **Yearly folds** (as now): train on 2021–2022 → test 2023; 2021–2023 → 2024; 2021–2024 → 2025.
   For landslide's new model the catalogue era is always in training (it lies before 2021).
   Reported fold by fold with the events in each fold; not used by the rule.
2. **Leave one storm out (the main comparison).**
   - Event days less than 14 days apart are merged into one cluster (flood's 2025-08-12 and
     2025-08-18 become one, so flood has 4 clusters).
   - Blocks: each cluster's block runs from 7 days before its first event day to 7 days after its
     last. Every other study day belongs to its calendar-month block (what is left of the month).
   - For each block: train on every study day more than **14 days** away from the block (the
     longest rain window, so no window overlaps the test), then predict the block.
   - Every study day gets exactly one out-of-fold chance from each model. For landslide this design
     runs on the GeoAlert era (the only era the current model has); catalogue-era rows are always in
     the new model's training.
   - "Where" is refitted per fold too: flood's λ, landslide's β and λ, from the training events only.
3. **Landslide outside test.**
   - The current model, fitted on 2021–2025, is scored on the catalogue-era days it never saw:
     its city chance (1 − Π_b(1 − p(b, d))) against catalogue landslide days, by ROC-AUC and
     observed against expected. No log score: the catalogue covers a wider area, so its base rate
     is not comparable.
   - The new "when" model is trained on one era and scored on the other (both directions), by
     ROC-AUC, with each era's rain slopes and their intervals.
4. **Future test:** the prediction log (3.5) scores the 2026 wet season as it happens.

### 2.2 Scores

On the leave-one-storm-out rows unless stated:
- **Barangay-day:** log score (mean log loss, the main score); Brier score; Brier skill against
  climatology and against the shrunken per-barangay rate; PR-AUC printed beside its no-skill value
  (the event rate); observed against expected events per year, with an exact Poisson 95% interval;
  calibration slope.
- **"When":** per day, the city chance 1 − Π_b(1 − p(b, d)) against whether the day had an event:
  ROC-AUC and city-day log score.
- **"Where":** on each event day with both hit and unhit barangays, the ROC-AUC of chance against
  hit (the mean over days); and the **lift ratio**: the share of hit barangay-days that fall in the
  5 barangays with the highest chance, divided by 5/22.
- **Levels** (barangay-months, the month chance from recorded rain, 15% and 25% cut-offs
  unchanged): at each cut-off, hits, misses, false alarms and correct negatives, with POD, FAR, the
  Peirce skill score, SEDI, and false alarms per real event. The card also states what the cut-offs
  imply at break-even: (1 − p) ÷ p, about 5.7 and 3.0 false-alarm barangay-days per real event.
- **Event-by-event table:** for each event day: date, record subtypes, storm name when the flag is
  on, 1-day and 3-day rain, the PAGASA band of the 1-day rain; for each model, the mean chance of
  the hit barangays on the day and on the day before, the city chance, and how many barangays were
  at High that month (recorded rain).

### 2.3 Baselines (fitted in-fold, on the same rows)

Rules with no "where" of their own spread the city chance evenly: each barangay gets
(city chance) × k̄ ÷ 22, with k̄ the training mean of barangays per event day.
- **Climatology:** the training event rate.
- **Shrunken per-barangay rate:** the existing `benchmark_probs` (barangay × calendar month, shrunk
  toward the training rate). Benchmark only, never a forecast.
- **Flood — PAGASA 24-hour bands:** 1-day rain under 50 mm, 50–100, 100–200, over 200. City chance
  per band = (training event days in the band + 0.5) ÷ (training days in the band + 1).
- **Flood — rain only:** the new model without the storm flag (same allocation), which shows what
  the flag adds.
- **Flood and landslide — persistence:** the training event rate on days after an event day, and on
  other days.
- **Landslide — 2-year return-level rule (Dynaslope style):** T₂ = the 2-year return level of the
  annual maximum 1-day rain (Gumbel, method of moments, complete training years). Three classes:
  1-day rain ≥ T₂, ≥ T₂/2, below; city chance per class as for the PAGASA bands.
- **Landslide — 7-day 95th-percentile rule (LHASA v1 style):** the 95th percentile of 7-day rain on
  training days; two classes, city chance per class as above.
- Both landslide rules spread their city chance evenly over the barangays with `slope_gt18` ≥ 0.10
  (fixed now), and give the others nothing.

### 2.4 Intervals

A **cluster bootstrap**: event-cluster blocks and month blocks are resampled separately, with
replacement, keeping their counts, and all 22 barangays of a day stay together. 1,000 replicates,
seed 0. It gives intervals for each score and for paired differences (new − current, and each model
against each baseline).

### 2.5 The rule for replacing the current model (written before any run)

The new model replaces the current one for a hazard only if **(a) or (b)**, **and (c)**:
- **(a)** the 95% bootstrap interval of the paired log-score difference (new − current) on the
  leave-one-storm-out rows lies wholly below zero; or
- **(b)** on every event day the new model gives the hit barangays a mean log score no worse than
  the current model's, a better one on more than half of the event days, and no more false alarms
  per real event at High (barangay-months) than the current model;
- **(c)** the leakage checks pass: the test suite's leakage tests, and a run-time assertion in the
  command that no training row lies within 14 days of its held-out block.

Otherwise the current model stays. The report stores the verdict (`adopted`, which rule, and plain
reasons such as "it gave a lower chance on 2025-08-18"), and the card shows it. For landslide the
rule is judged on GeoAlert-era rows.

---

## Section 3 — Saved fits, serving, and the prediction log

### 3.1 The report, version 2 (`data/hazard_model_report.json`)

`test_hazard_models` fits both contenders on the whole study period (landslide's new model with the
catalogue era as well) and writes:
- top level: `version: 2`, `generated`, `study`, `files` (sha1 of every input file), `hazards`;
- per hazard: `in_use` (`two_part` or `logistic_regression`), `verdict`, `fits`, `tests` (Section 2),
  `limits` (plain sentences rebuilt from the report's numbers), `credits`, `data_signature`,
  `excluded`.
- `fits.two_part`: `when` — feature names, coefficients, the intercept in use (landslide: the
  GeoAlert-era one, with the catalogue-era one kept for the record); `where` — kind (`exposure` or
  `terrain`), λ, β (landslide), and each barangay's share a_b.
- `fits.logistic_regression`: feature names, the imputation medians, which columns are log-transformed, the
  scaler's means and scales, coefficients and intercept.

### 3.2 Serving with NumPy

- New module `apps/history/hazard_scoring.py` (NumPy only; imports no scikit-learn): turns a saved
  fit and the daily inputs into a chance for every barangay-day.
- `hazard_forecast._build` stops fitting. It reads the in-use fit from the report, the rain file
  and the storm days, and scores every barangay-day of the rain file. The `Deployed` structure, the
  6-hour cache, the lock and the warm-up thread stay; the cache key adds the storm file's sha1. The
  "model libraries are not installed" path goes away for flood and landslide.
- A day the storm data does not cover gets no chance from a model that uses the flag (like a day
  with missing rain). The month forecasts are unaffected, since they replay past years.
- Scenario years: the forecast already replays every complete rain year in the file. With rain from
  2006-12-18 that becomes 2007 onward (19 years instead of 9), which steadies the month chances. This
  is intended.
- Production needs scikit-learn only for fire (Section 4); `xgboost-cpu` goes.

### 3.3 Data files and commands

| File | Made by | Holds | In git |
|---|---|---|---|
| `rain_daily.csv` | `fetch_rain` (archive start moved to 2006-12-18) | NASA POWER daily rain | yes, as now |
| `storm_days.csv` + `storm_days.meta.json` (new) | `fetch_storms` (new) | each day with the storm flag on: date, storm id, name, closest distance (km); the meta file holds the source, the first and last day covered, and when it was fetched | yes (IBTrACS is open access) |
| `barangay_exposure.csv` (new) | `build_hazard_features` | per barangay: total buildings, buildings in NOAH 25-yr Medium/High, in NOAH 100-yr Medium/High, on ground under 2 m above drainage, and E_b | yes, with `data/ATTRIBUTION.md` (derived from UP NOAH and Microsoft footprints, ODbL) |
| `landslide_catalogue_exclusions.csv` (new) | by hand | catalogue event ids left out, with the reason | yes |
| NASA Global Landslide Catalog CSV | `test_hazard_models` downloads it when missing (data.nasa.gov, no login) | raw records | **no**, `.hazard_cache` only |
| NOAH Cebu zips, IBTrACS WP file | the commands above, cached | raw downloads | no, `.hazard_cache` only |

- `test_hazard_models` needs every input: when the exposure file, the storm days or the catalogue
  (cached or downloadable) is missing, it stops with an error naming the command to run, and writes
  no partial report. The saved report stays as it was.
- `fetch_storms`: streams the IBTrACS western Pacific CSV (115 MB, read once, never kept whole) for
  2006-12-18 onward; `--recent` reads only the last-3-years file (12 MB) and merges it in.
- **Keeping storms current live:** once a day, the warm-up thread (started by the cron-job.org ping)
  refreshes the last-3-years file into the Django cache. Requests also read the active-storms file
  (67 KB), cached 3 hours. Storm coverage runs to today when the active file was read and the cached
  last-3-years copy is at most 7 days old; otherwise to the last track time in the files.
- README: the order becomes `fetch_rain`, `fetch_storms`, `build_hazard_features`,
  `test_hazard_models`, plus a daily schedule line for `log_hazard_predictions` beside the alert-jobs
  line.

### 3.4 The prediction log (`hazard_prediction_log`)

New model `HazardPredictionLog` in `apps/history/models.py`, migration `0008_hazard_prediction_log`.

| Column | Type | Notes |
|---|---|---|
| id | bigint | |
| hazard | text | CHECK in (Fire, Flood, Landslide) |
| barangay | FK | ON DELETE PROTECT |
| kind | text | CHECK in (`day`, `month`): one rain day's chance, or the month's chance as the forecast page shows it |
| period_start | date | the day, or the month's first day |
| issued_on | date | Asia/Manila date of writing |
| model_version | text | flood/landslide: `<in_use>@<report sha1, 12 characters>`; fire: `<model>@<sha1 of the records tag, 12>` |
| probability | double | CHECK 0 ≤ p ≤ 1 |
| expected_events | double, null | fire only |
| level | text, null | Low/Moderate/High on `month` rows; null on `day` rows (levels are monthly) |
| inputs | jsonb | `day` rows: rain sums used, rain source, storm flag and name, `outside_training` (any input above the training maximum); `month` rows: method, `in_training`, scenario years |
| created_at | timestamptz | |

- Unique key: (hazard, barangay, kind, period_start, issued_on, model_version). Writes use
  `bulk_create(ignore_conflicts=True)`, so repeated runs add nothing.
- **Never changed:** a trigger (`RunSQL`, reversible) raises on any UPDATE or DELETE of a row. Row
  triggers do not fire on TRUNCATE, so test teardown still works.
- Index on (hazard, period_start).
- **Writer:** command `log_hazard_predictions`:
  - `day` rows for flood and landslide: every rain day with a chance after the last day logged for
    this model version, at most 30 days back;
  - `month` rows for all three hazards: the current month's chance and level per barangay, from
    the same service the forecast API uses, one snapshot per `issued_on`.
  The warm-up thread also runs it, at most once per Manila day (a cache marker).
- Size: about 110 rows a day, roughly 40,000 a year.

### 3.5 Scoring the log

`test_hazard_models` adds a `logged` block per hazard: first and last logged day, rows, events on
logged days, the sum of logged chances against observed events (exact Poisson interval), and for
each new event its logged chance on the day and the day before, under the model version in use at
the time. Fire likewise from its `month` rows.

---

## Section 4 — Fire

`apps/history/model_forecast.py` keeps today's model. New module `apps/history/fire_candidate.py`
holds the contender and the comparison.

### 4.1 Today's model (F0, the one to beat)

Unchanged: Poisson regression with a term per barangay, 11 month terms, log area, log puroks and
purok density; penalty 0.01; refitted from the records.

### 4.2 The contender (F1), fixed now

  expected fires(b, m) = buildings_b × exp(μ + u_b + Σ_{k=1,2} [a_k·sin(2πkm/12) + c_k·cos(2πkm/12)])

- **Exposure offset:** the barangay's building count from `barangay_exposure.csv`. It replaces area
  and puroks as the measure of size.
- **Season:** two yearly waves (4 numbers) instead of 11 month terms.
- **Pooled barangay terms:** u_b for every barangay, pulled toward the city level by a penalty
  chosen inside the training months only: each value in {0.001, 0.003, 0.01, 0.03, 0.1, 0.3, 1} is
  fitted on the training months except the last 6 and scored (Poisson log score) on those 6; the
  best is refitted on all training months.
- Fitted with scikit-learn's `PoissonRegressor` using the offset trick: target fires ÷ buildings,
  sample weight = buildings (the same fit as a log offset; a test checks it). The penalty also
  touches the 4 season terms; that is accepted.
- A barangay with no building count makes F1 untestable; F0 stays and the report says why.

### 4.3 The test

- **Main window:** the last 9 full months of the record (as now). Both models are refitted each
  month on every earlier month and forecast one month ahead.
- **Paired score** per barangay-month: the Poisson log score (expected count floored at 0.01, as
  now). Month means of the difference (F1 − F0); a month-block bootstrap (1,000 replicates, seed 0)
  gives the 95% interval; the Diebold–Mariano test with the Harvey–Leybourne–Newbold small-sample
  correction (horizon 1, t with T − 1 degrees of freedom) is reported beside it.
- **Also, for both:** Brier score, AUC, top-5 capture, the share of counts inside each model's 80%
  Poisson range (10th–90th percentile), and a randomised PIT histogram (10 bins, seed 0).
- **Secondary window**, labelled less clean: from 2025-01 (the first month with 100 earlier fires)
  to the last full month. Today's settings were chosen on those years.

### 4.4 The rule

F1 replaces F0 only if, on the main window, the mean paired log-score difference is below zero
**and** its 95% bootstrap interval lies wholly below zero. Otherwise F0 stays, and the card says
"tested, not better".

### 4.5 Checks reported, not built on

- The Pearson dispersion of the in-use model's training fit (0.99 today). Above 1.5, the report
  flags a negative-binomial model as worth trying.
- Moran's I of each barangay's leftover error over the main window (observed − expected), with
  barangays that share a border as neighbours (PostGIS: boundaries that touch or lie within 1 m),
  999 permutations, seed 0. A p-value under 0.05 flags a spatial model as worth trying.

### 4.6 Serving

As now: refitted on request and cached 6 hours. `_fitted` runs the comparison and uses the winner
under 4.4; the existing test against counting (`evaluate`, status `in_use` or `in_use_not_better`)
runs on the model in use. The cache key moves to `forecast-model-v3` and adds the exposure file's
sha1. The comparison is about 150 small fits (a few seconds once per cache period); the warm-up
thread warms fire too.

---

## Section 5 — Accuracy card, rollout and tests

### 5.1 Accuracy endpoint and card

`GET /api/history/forecast/accuracy/`: flood and landslide entries carry the version 2 report
fields (`in_use`, `verdict`, `tests`, `limits`, `credits`, `logged`); the old `winner`,
`candidates`, `calibrated_*` fields go. Fire entries gain a `candidate` block (both models' scores,
the interval, the DM test, coverage, PIT, dispersion, Moran's I, the verdict).

`frontend/src/components/Forecast/ForecastAccuracy.jsx`, per flood and landslide card:
- one opening line naming the model in use and the verdict, for example "Two-part model (rain-day
  chance × barangay share), adopted under rule (b)", or "Pooled logistic regression. The two-part
  model was tested and not adopted: it gave a lower chance on 2025-08-18.";
- the event-by-event table, the baselines table (log score and Brier skill), "when", "where" and
  the lift ratio, what the cut-offs imply, landslide's outside test, the logged block once rows
  exist, and the limits sentences;
- credits: NASA POWER; IBTrACS; UP NOAH flood-hazard maps (ODbL); Microsoft building footprints
  (ODbL); and "landslide timing also learned from NASA Global Landslide Catalog days near Talisay,
  2007–2017" (the source is credited; no record is shown).

The fire card adds the new-against-current comparison, the 80% range coverage and the two checks.
The forecast's method line says chances are of **reported** events.

### 5.2 Rollout, in order

1. Code, test-first, on the private test database (`C:\Users\Sannichigetsu\.geoalert-test\
   geo_test_settings.py`, a unique database name), never the shared `test_postgres`.
2. Data runs: `fetch_rain` (to 2006), `fetch_storms`, `build_hazard_features` (downloads the NOAH
   Cebu zips, about 120 MB, into `.hazard_cache`), `test_hazard_models`. The real report is shown to
   the user before anything else.
3. The migration goes onto the shared database **only after the user's go-ahead**, with a backup in
   Downloads first. It is additive: one new table, a trigger and its function.
4. `requirements/base.txt` loses `xgboost-cpu`; README updated (3.3).
5. Nothing is committed.

### 5.3 Tests

- Firth: intercept only gives logit((k + ½)/(n + 1)); a 2×2 table gives the log odds ratio with ½
  added to each cell; finite coefficients under perfect separation; FLIC reproduces the observed
  rate; each era's FLIC intercept reproduces its own rate. Conditional logit: matches a hand-worked
  two-day example.
- Allocation: Σ_b a_b equals the target; λ never changes the ranking.
- Storm flag: a tiny IBTrACS sample checks the 300 km distance, the 72-hour window and the Manila
  day boundary.
- Catalogue filter: the 20 km radius, the Negros exclusion, the exclusion file, and barangays taken
  only when the text names one.
- Leakage: no training row lies within 14 days of its held-out block; inventory-based baselines are
  rebuilt per fold.
- Serving: NumPy scoring of the saved pooled logistic regression matches the scikit-learn pipeline
  to 1e-9; the two-part scoring matches q(d) × a_b.
- The replacing rule: each branch of (a), (b) and (c), and fire's rule.
- Log table: UPDATE and DELETE are refused; a rerun adds no rows; `day` rows never reach back more
  than 30 days.
- Fire: the offset trick gives the same fit as a true offset; the penalty is chosen without the
  test months.
- The accuracy card: frontend tests for adopted, not adopted, unavailable, and with and without
  logged rows.

### 5.4 Files

- New: `apps/history/firth.py`, `two_part.py`, `hazard_tests.py`, `hazard_scoring.py`,
  `storms.py`, `landslide_catalogue.py`, `fire_candidate.py`, `prediction_log.py`; commands
  `fetch_storms.py`, `log_hazard_predictions.py`; migration `0008_hazard_prediction_log.py`; data
  `storm_days.csv`, `storm_days.meta.json`, `barangay_exposure.csv`,
  `landslide_catalogue_exclusions.csv`, `ATTRIBUTION.md`.
- Changed: `hazard_models.py` (RF, XGBoost and Platt removed; pooled logistic regression export
  added), `hazard_data.py`, `hazard_forecast.py`, `model_forecast.py`, `rain.py`, `models.py`,
  commands `fetch_rain.py`, `build_hazard_features.py`, `test_hazard_models.py`, `views.py` (accuracy
  entries), `requirements/base.txt`, `README.md`, `ForecastAccuracy.jsx` and its test, and the
  existing tests that name the removed candidates.

### 5.5 Out of scope

A drainage-flood channel; CHIRPS or PERSIANN rain; PyMC; a BYM2 spatial model or a negative-binomial
model (only flagged by 4.5); a model registry, shadow mode or promote command; LHASA; Google Flood
Hub; sitio-level allocation; new level cut-offs (the DRRMO's call); a Django upgrade.

### 5.6 Limits the card and the thesis must state

- With 5 flood storm days, no model can be shown statistically better: a model that wins on every
  storm day reaches at best p = 0.0625 on a sign test.
- One NASA POWER rain cell for the whole city; the 10.25° N cell edge splits Talisay.
- Under-recording: every chance is of a reported event and reads low.
- NOAH's maps are labelled beta, use about 30 years of rain, and come from a community mirror; the
  Mananga River works planned for 2026 will shift river-flood hazard.
- The NASA catalogue states no licence; its locations are often only good to 5–25 km; its years
  (2007–2017) are not the forecast's years.
- The 15% and 25% cut-offs and several earlier choices were made after seeing 2023–2025, so the 2026
  season is the clean test.
