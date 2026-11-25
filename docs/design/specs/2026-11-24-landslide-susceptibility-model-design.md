# Landslide susceptibility by purok: a neural network that learns from Philippine typhoon landslides

*Design, 2026-11-24. Uncommitted, per the standing rule ("never commit"). It follows the flood
susceptibility design (`docs/design/specs/2026-11-24-flood-susceptibility-model-design.md`) and the
automatic retraining design (`docs/design/specs/2026-11-24-automatic-retraining-design.md`). Where this
document says "as flood", the flood design and its code (`apps/history/flood_*.py`) are the pattern.*

## 0. Decisions the user made (2026-11-24, AskUserQuestion)

| Question | Answer |
|---|---|
| Scope | "same as flood, dont touch history, only predictive analytics". The model must **not use counting**. **Neural networks are much preferred** |
| Why outside data | GeoAlert has too few landslides to train a model properly, so find "an alternate same as flood" |
| What the model learns from | **The Philippine typhoon inventories, plus the world's tropical events only if they help.** Train on the mapped landslides of Typhoons Egay, Paeng, Agaton and Mangkhut. Add the other tropical rain events (NASA, about 11,000 slides) only if a test on a Philippine typhoon the model never saw shows they help. The test decides; no person picks |
| How strongly the neural network is preferred | **The NN, unless clearly worse.** The neural network is the model unless a simpler one beats it on the held-out typhoon test by a clear margin (interval wholly above zero). Whatever is picked must still beat NOAH's map, or NOAH's classes ship |
| What our own landslides do once there are enough | **Added to the outside slides**, with extra weight. A new fit switches only if it does at least as well on the newest season (6.3). Floor to try: 30 located spots in 3 barangays |
| The yearly retrain | "The january retrain is only for our own data of landslide then switch if we have enough, do what is best." The outside-trained model is built **once**, offline, as flood's survey model is. The January job only checks GeoAlert's own landslides and, once there are enough, trains with them and switches by itself if the new fit passes |

**History and predictive analytics stay separate** (the user's rule, 2026-11-24):
- **History: untouched.** Past records, the History page, Past hazards fills, purok history levels
  (`purok_levels.py`, `area.py`), the barangay hall's `history.*` thresholds, and the history-based
  alert level an approved landslide report takes (`reports/decide_views._level`, `_history`).
- **Predictive analytics: what this build adds.** Landslide joins "Likely by month",
  `/api/history/forecast/`, the accuracy card, the Predictive models tab, the prediction log and the
  automatic retraining job. A machine-learning model makes every landslide prediction, and no person
  can set, raise, approve or adjust one.
- **Replaced (designer's call, as flood):** the hand-weighted landslide raster in
  `hazards/susceptibility.py` (`FACTORS['landslide']`: slope 45%, relief 15%, and so on) feeds the
  map's "This spot" reading. It is a prediction made of hand-picked weights, so this model's output
  replaces it.

## 1. Intent

The DRRMO and residents need to know **which puroks sit on or below ground that tends to slide**, from
evidence rather than hand-picked weights or counts, and where GeoAlert cannot honestly say.

GeoAlert's own landslide records are far too few to learn from: 8 real records on 8 days, 7 in Manipis
and 1 in Camp IV once the two test entries are set aside (section 3.5), with 2 map points. A neural
network needs thousands of examples.

Those examples exist. After recent typhoons, NASA scientists mapped every visible landslide from
3 m PlanetScope images and published the inventories openly. Typhoon Egay (July 2023) alone left 3,183
mapped slides in northern Luzon. A model trained on how the ground looks where those slides happened
(slope, relief, slope shape, drainage, land cover, road cuts) can be applied to Talisay's ground,
because every clue comes from the same global maps in both places.

The result is a **susceptibility** map: how prone a place is to sliding when heavy rain comes. It never
claims a landslide is coming. It is the same every month.

The thesis panel will look for real machine learning, no counting, and no human hand on a prediction.
This design gives all three, prefers a neural network, and states its limits on the model card.

## 2. Goals, non-goals, anti-goals

**Goals**
1. A Red / Orange / Green landslide susceptibility class per purok area, from a model trained on
   mapped typhoon landslides, with puroks whose ground is unlike anything the model learned from shown
   as **not assessed yet**.
2. A neural network as the model, unless a simpler candidate is clearly better (4.3).
3. Adoption by a rule fixed before training: the model must beat UP NOAH's landslide map on typhoons it
   never saw. Otherwise NOAH-based classes ship, as for flood.
4. Classes from validated recall targets, with false negatives counted directly.
5. Fully automatic predictions: no setting, screen or endpoint lets a person set, raise, approve or
   adjust a landslide prediction.
6. Every published susceptibility kept in an insert-only log; new located landslides checked against
   it automatically.
7. Each January, the retraining job checks GeoAlert's own located landslides. Once there are enough, it
   trains with them added and switches by itself when the new fit passes (6.3).

**Non-goals**
- Landslide **forecasting**: no daily or monthly landslide chance and no rain input. There is no rain
  feed in GeoAlert since the Rain watch was deleted (2026-11-22), and 8 dated events cannot validate a
  trigger model. Gated for later (section 11).
- Anything in History (section 0).
- Retraining the outside-trained model on a schedule. The outside inventories do not change; the
  January job is only for GeoAlert's own landslides (the user's ruling).
- A physical slope-stability model (no local soil strength data exists; research report section C).
- Earthquake-triggered landslides. The 2025 Bogo earthquake slides are a different mechanism, and no
  open inventory of them was found.

**Anti-goals** (failure even if it "works")
- Any purok coloured without evidence behind it.
- Susceptibility worded as "landslide likely" or "risk now".
- A class that a count, an admin setting or a person can change.
- An "everything is red" map.
- A record's location in a model file, a report, a job log or a public endpoint.
- The neural network shipped although a simpler model was clearly better, or a model shipped that does
  no better than NOAH's map.

## 3. Data

### 3.1 Training landslides (outside inventories; all open licences)

| Set | What | Licence | Use |
|---|---|---|---|
| **NASA COOLR new events** (Vershel et al. 2025, Figshare doi 10.6084/m9.figshare.26972467, `nasa_coolr_new_events.zip`, 1.6 MB) | 15,274 landslide points from 22 rain events, 2019-2023, mapped by hand from PlanetScope images | CC BY 4.0 | Training and the held-out typhoon test |
| of which **Philippines** | Typhoon **Egay**, 26 Jul 2023, 3,183 slides (Abra, Ilocos; 17.2-18.5°N); Tropical Storm **Paeng**, 28 Oct 2022, 213 slides (Maguindanao); Tropical Storm **Agaton**, 10 Apr 2022, 23 slides (Leyte) | | Philippine training set and folds |
| of which **world** | 19 other events: Mexico (Agatha), Vietnam, Bangladesh, Malawi and Mozambique (Freddy), South Africa, China (Doksuri), Brazil, India, South Korea, Rwanda, Colombia, Indonesia, Puerto Rico (Fiona), DR Congo | | Joins training only if the world test passes (4.3) |
| **Typhoon Mangkhut, Itogon** (Abancó & Jones 2023, NERC EIDC doi 10.5285/32765a61-8510-4dfc-b7c7-58bad12f8497) | Landslide polygons, 13-15 Sep 2018, 570 km² study area, about 1,100 slides | Open Government Licence | Philippine training set and folds |
| ~~Typhoon Parma, Itogon~~ (same EIDC series) | Landslide polygons, Oct 2009, same area | Unconfirmed | **Not used**: no land cover map exists from before 2009 (3.2), and its licence is unconfirmed |

- **Points.** A COOLR row is one landslide as a point. A Mangkhut or Parma polygon becomes one point at
  its highest cell (the scar, where the slide starts) [my call: susceptibility is about where slides
  start; runout is covered by NOAH's map in the benchmark].
- **"No landslide" ground.** Inside the area an event's mappers looked at, ground with no mapped slide
  is a true "no". The COOLR file does not ship the mapped extents, so the mapped area is taken as
  **ground within 2 km of a mapped slide** of that event, and Mangkhut and Parma use their study area
  when the supporting documents give it [my call]. "No" points are sampled at random in that area, at
  least 60 m from any slide of that event, **3 per slide** [my call], with a fixed seed.
- **Not used:**
  - the NASA Global Landslide Catalog for training: its points are placed to within 5-25 km, too rough
    for puroks (its 1 km and exact Talisay points are a test only, 3.4);
  - GeoAlert's own records for the outside model (they are the Talisay test, 3.4, and later the own
    data, 6.3);
  - counts of any kind; severity codes.

### 3.2 Clues (features); the allowlist is fixed before training

Every clue is computed with **the same code and the same cell size** in the training areas and in
Talisay: Copernicus GLO-30 heights on the zoom-14 web-mercator grid (`susceptibility.city_grid` with a
training area's extent, about 9-9.5 m cells), annual land cover and OpenStreetMap roads.

**Land cover comes from the year before each event** (builder check, 2026-11-24). A map made after a
typhoon shows its scars as bare ground or grass, so it would partly encode the answer (WorldCover 2021
postdates Mangkhut 2018 and the 2019 KwaZulu-Natal event). The source is the Esri / Impact Observatory
10 m annual land cover (Sentinel-2, CC BY 4.0, one map per year from 2017):
- each training event reads the map of the year before it (Mangkhut 2017, Paeng and Agaton 2021,
  Egay 2022, and so on); Talisay reads the newest year;
- its classes are grouped into the `lc_*` shares below;
- if the builder cannot fetch it without an account, the `lc_*` clues are dropped before any fit, and
  the model trains on terrain and roads alone. The card says which.

| Feature | Definition | Expected direction |
|---|---|---|
| `slope_deg` | Slope of the smoothed DEM, in degrees | up |
| `relief_m` | Highest minus lowest height within about 150 m (the existing relief window) | up |
| `profile_curv` | Curvature down the slope (convex or concave), on the smoothed DEM | (none) |
| `plan_curv` | Curvature across the slope (hollows gather water) | (none) |
| `hand_m` | Height above the nearest DEM-derived channel (the existing HAND code), floored at 0 | (none) |
| `twi` | Topographic wetness index, ln(upslope area / tan slope) | up |
| `dist_stream_m` | Distance to a DEM-derived channel (`STREAM_AREA_KM2`), as log(1 + m) | down |
| `dist_road_m` | Distance to an OpenStreetMap road, as log(1 + m): road cuts trigger slides, and Talisay's recorded slides are mostly road slides | down |
| `lc_*` | Land cover share within 50 m, from the year-before map: trees, rangeland (shrub and grass), crops, built-up, bare | (none) |

- **Not a clue:** absolute height. Egay's slides sit at 300-1,500 m and Talisay's uplands at 100-600 m;
  height would teach the model "high means slides" in a way that does not transfer.
- **Not a clue: NOAH's landslide class.** NOAH covers only the Philippines, so the world rows could not
  have it, and the claim "beats NOAH" stays clean when NOAH is not an input. NOAH is the benchmark and
  the fallback (4.4, 5.3) [my call].
- A test fails if a model reads any column not on this list (section 7).

### 3.3 Input checks (run by the feature commands; results go on the card)

- **DEM:** the existing above-sea-level guard, for Talisay and every training area.
- **Roads:** OpenStreetMap road density (km per km²) in each training event's mapped area is reported
  beside Talisay's road density **on its steep ground** (grid cells with slope ≥ 10°), not the whole
  city's: the city figure (about 7 km/km²) is set by the lowland streets and would wrongly flag rural
  mountain areas. If an event's area has under a tenth of that [my call], its rows get `dist_road_m`
  set to missing, and the candidates handle missing values as section 4.2 says. The card reports how
  many training rows kept the road clue.
- **Coverage:** every Talisay area has its count of scoring points (3.5). Areas with none are
  "not assessed (no buildings or roads)".

### 3.4 Talisay tests (seen last; section 4.4)

| Set | Today | Use |
|---|---|---|
| Puroks holding a located GeoAlert landslide (a map point, a purok link, or an "Affected here" mark on a landslide zone) | Sitio Camp 5 and Camp 6 (Manipis), each with a point and a link | Gate 2 |
| Barangays of every real GeoAlert landslide | Manipis (7), Camp IV (1) | Barangay check on the card only |
| NASA Global Landslide Catalog points inside the Talisay grid placed to within 1 km or exactly | a few (2007-2017) | Shown on the card only; the catalogue's licence is unstated, so it stays private as decided on 2026-11-13 |

### 3.5 Where Talisay is scored

- **Scoring points:** building centres (Microsoft footprints, as for fire and flood) **plus points
  every 20 m along OpenStreetMap roads** [my call]. Homes are what the DRRMO protects, and roads are
  where Talisay's recorded slides happen (the Manipis road); a purok scored on homes alone would miss
  both of its located slides.
- **Out of range: terrain clues only.** A scoring point whose **terrain** clues (`slope_deg`,
  `relief_m`, `profile_curv`, `plan_curv`, `hand_m`, `twi`, `dist_stream_m`) fall outside the 1st-99th
  percentile of the chosen training set is left out of its purok's score.
- **Land cover and road distance are clipped, not dropped** (builder check, 2026-11-24). Talisay's homes
  stand in far more built-up ground than the mountain training ground (71% of its building centres have
  at least half built-up land within 100 m), and a road point sits on its road (`dist_road_m` = 0).
  Dropping those points would grey out most of the city and both located slides. Their `lc_*` and
  `dist_road_m` values are clipped to the training set's 1st-99th percentile range before scoring, and
  the card states how many points were clipped [my call].
- **Assessed purok:** at least half of its scoring points are in range [my call]. Else
  "not assessed yet", with the reason: "no buildings or roads" or "ground unlike the areas the model
  learned from". The train command reports the in-range share before any Talisay test is opened.
- **The two test entries.** The two Purok Kaimito records of 17 Nov 2026 are test entries
  ("sssssadawd", "ddddddddddddddddd", cause "sample test"), each closing a test hazard zone. **The user
  chose to delete them** (2026-11-24): rollout step 0 (section 9). That changes History's data, not how
  History works. The model then sees only the 8 real landslides, and no record-level exclusion list
  exists anywhere in the predictive code.

## 4. The model

### 4.1 Framing

A **presence-absence** model of where slides start. Mapped slides are "yes"; sampled ground in the
mapped area is "no". Unlike flood's survey, this gives true "no" examples, so the score is a real
classifier output. It is still not a calibrated chance per purok: "no" points are sampled 3 per slide,
which fixes the base rate, and the card says so in one plain sentence.

### 4.2 Candidates (fixed settings; no tuning on the test data)

| | Candidate | Settings |
|---|---|---|
| **NN** | **Neural network ensemble** (scikit-learn `MLPClassifier`) | 5 seeds averaged; two hidden layers of 32 and 16, ReLU; weight decay 1e-3; Adam, up to 500 iterations; inputs standardised on the training rows; missing `dist_road_m` filled with the training median plus a 0/1 "road unknown" input |
| C1 | Logistic regression | Ridge (C = 1) on the standardised inputs; the same missing-value handling |
| C2 | XGBoost with monotone constraints | The directions in 3.2; depth 3; 400 trees; learning rate 0.05; subsample 0.8; missing values native |
| B0 | **NOAH-only benchmark** | Score = NOAH landslide class at the point (0 none, 1 low, 2 medium, 3 high) |

Settings are the designer's calls, fixed before any fit. The builder may correct obvious defects only
before the first real run, and records why. Production needs none of these packages: the site reads
per-area results, as for fire and flood.

### 4.3 Folds and the choice rules (pre-registered)

- **Folds: leave one typhoon out.** Egay; Mangkhut (Itogon); Paeng; Agaton. A fold's
  slides and its "no" points are held out together. This asks the question that matters for Talisay:
  does what the model learned in one region work in another? Results are reported fold by fold with
  their slide counts; Agaton's 23 slides make its fold noisy, and the card says so.
- **Metric:** AUC on the pooled out-of-fold scores of the Philippine folds (slides against "no" points).
  Gate 1 for flood is judged on AUC too (the user approved that on 2026-11-24).
- **Intervals:** a paired bootstrap of 1,000 repeats that resamples slides and "no" points with
  replacement **within each fold**, as flood's `auc_gain` does.
- **Rule 1, the world test (first):** train the NN on the other Philippine folds alone, and on them
  plus all 19 world events, for each held-out Philippine typhoon. The world events join the training
  set only if the pooled AUC gain has its interval wholly above zero. Otherwise the model trains on the
  Philippines alone. Either way, the card says which and why.
- **Rule 2, the model (on the training set rule 1 chose):** the **NN is chosen** unless C1 or C2 beats
  it on pooled out-of-fold AUC with the interval wholly above zero. If both do, the better of the two by
  pooled AUC is chosen. This is the user's "NN unless clearly worse".
- **Final fit:** the chosen candidate is refit on every slide of the chosen training set.

### 4.4 Acceptance against NOAH (pre-registered; decides what ships)

The chosen model is adopted only if **all** of these hold:
1. **Better than NOAH:** on the Philippine held-out typhoons, its pooled out-of-fold AUC minus B0's has
   a paired bootstrap interval wholly above zero. B0 reads NOAH's landslide map for each training
   province (Abra, Ilocos Sur, Ilocos Norte, Benguet, Maguindanao and Leyte, plus any other province a
   fold's points fall in).
2. **Talisay test:** at least `test_hits_needed(n)` of the n Talisay puroks in 3.4 are Red or Orange
   (flood's rule: 75% rounded up, at least 1). Today that is 2 of 2 (Camp 5 and Camp 6). No test purok
   is no evidence, so a fail.
3. **Not everything flagged:** Red + Orange hold no more than 50% of Talisay's assessed scoring points.
4. **Test data seen last:** the training set, the model, and the cut-off scores are written to the
   report before any Talisay test record or catalogue point is loaded. A unit test checks the order.

**If any gate fails, NOAH-based classes ship** (5.3), and the card names the failed gate in plain words.

## 5. Score → Red / Orange / Green

### 5.1 Purok score

- **The model:** the 90th percentile of the model score over the purok's in-range scoring points
  [my call]. A purok is as exposed as its most exposed tenth: a steep road cut or a row of homes under
  a slope should not be averaged away by the flat rest of the purok.
- **NOAH fallback:** the 90th percentile of the NOAH class over its scoring points.

### 5.2 Cut-offs (from the out-of-fold scores, before any Talisay test is opened)

The cut-offs are score values found on the Philippine held-out slides, then applied to Talisay:
1. Rank all out-of-fold points (slides and "no" points) by score.
2. **Red:** the score above which the top-ranked points hold at least 50% of the held-out slides.
3. **Orange:** continue until Red + Orange hold at least 90% of them (false-negative emphasis).
4. **Green:** everything below.
5. If 90% cannot be reached before the scores tie at the bottom, Orange stops at the last distinct
   score, and the card states the recall reached.

Each assessed Talisay purok takes the class of its 5.1 score. Labels:
- **Red**: "High landslide susceptibility"
- **Orange**: "Moderate landslide susceptibility"
- **Green**: "Low landslide susceptibility". Flat lowland puroks land here: the training "no" points
  include flat valley floors, so the model has evidence for flat ground.
- **Grey**: "Not assessed yet", with the reason.

The words "risk now", "likely" and "expected" never appear.

### 5.3 The NOAH fallback

- **Source:** UP NOAH's landslide hazard map for Cebu (`Landslide/LandslideHazards/Cebu.zip` on the
  bettergovph Hugging Face mirror, 224 MB, ODbL; SINMAP, Matterocking and Conefall, and Flow-R on 1 m
  LiDAR and 5 m IfSAR). The classes: 0 none, 1 low, 2 medium, 3 high.
- **Classes:** the same cut-off walk as 5.2, run on B0's out-of-fold scores, which lands on NOAH's own
  class boundaries. The labels name the source: "From UP NOAH's landslide hazard map".
- **Coverage:** every purok with scoring points, since NOAH covers the whole province.

### 5.4 Uncertainty

- **Stability:** refit the chosen model on 200 bootstrap resamples of the training slides and "no"
  points (as flood). A purok whose class differs from its published class in more than 20% of the refits
  is published with an **"uncertain"** mark (hatched), its class still shown. The January job uses 100
  refits (6.3).
- **Outlines:** areas with a low-confidence outline carry "estimated outline" in their detail text.

## 6. Integration

### 6.1 Offline commands (on the developer's machine)

**`manage.py build_landslide_training`** (one time; rerun only if an inventory changes):
- downloads the COOLR zip from Figshare and the Itogon zip(s) from EIDC, checksums pinned, into
  `backend/.hazard_cache/` (git-ignored);
- for each event's mapped area: Copernicus GLO-30 tiles through the existing range fetcher, the
  year-before land cover map (3.2), OpenStreetMap roads, and the NOAH landslide map of each Philippine
  province, all cached;
- samples the "no" points (3.1) and computes the 3.2 clues and the B0 NOAH class at every point;
- writes **`apps/history/data/landslide_training.csv`**: one row per point with `event`, `fold`,
  `region` (`ph` or `world`), `label`, the clues and `noah_class`. **No coordinates.** Plus
  `landslide_training.meta.json` (sources, checksums, row counts, the road check, the sampling seed);
- updates `ATTRIBUTION.md`. Every source is open (CC BY 4.0, the Open Government Licence, ODbL for
  OpenStreetMap and NOAH, Copernicus DEM, Esri / Impact Observatory land cover CC BY 4.0), so the table is committed, unlike
  flood's survey points. The table is a database derived from ODbL data, so its notice says it is
  shared under ODbL.

**`manage.py build_landslide_features`** (Talisay; rerun after a purok reload):
- reuses the cached Talisay DEM, OpenStreetMap and footprints, and downloads and caches NOAH Cebu;
- computes the clues on the city grid and samples them at the scoring points (3.5);
- writes `apps/history/data/landslide_purok_features.csv` (one row per area: scoring-point counts,
  in-range share, NOAH 90th percentile, `Purok.outlines_version()`) and point-level clues to
  `.hazard_cache` (too big to commit);
- has no access to `HistoricalRecord` or any history loader (a test checks the imports).

**`manage.py train_landslide_model`:**
- reads the training table and the Talisay features, runs sections 4-5 in order, and only then reads
  GeoAlert's landslide records read-only and the catalogue points for the tests;
- writes `landslide_purok_model.json` (version `<model or noah_fallback>@<sha1 of training table +
  features + settings + code, 12 chars>`, the source, the chosen candidate and training set, the
  cut-offs, the input hashes, the outlines version, and per area its score, class, flags and counts)
  and `landslide_purok_report.json`.
- No coordinate, outline or point list goes in either file (the flood lesson: a rounded outline let a
  reviewer recover survey spots).

### 6.2 The website (reads files and the live fit)

- **New `apps/history/landslide_purok.py`**, modelled on `flood_purok.py`: load, the 60 s cache, the
  stale-outlines check, the live fit from `model_fit` against the committed file by `built_at`, and the
  three unavailable reasons in flood's wording, with "landslide" in place of "flood".
- **Forecast API (`/api/history/forecast/`):** `FORECAST_HAZARDS` becomes `('Fire', 'Flood',
  'Landslide')`. With Landslide asked for, the response gains `landslide_results` (`purok_id`,
  `barangay_id`, `level`, `uncertain`, `not_assessed_reason`) and a landslide block (`available`,
  `reason`, `source`, `model_version`, `built_at`, `basis`, `varies_by_month: false`). Fire and flood
  are unchanged.
- **Accuracy view:** a landslide entry from `landslide_purok_report.json`, plus the live "since
  publishing" block: new located landslides and the class each fell in. If, over the last 10 or more,
  fewer than 80% fall in Red or Orange, the card shows "Under review: recent landslides fall outside the
  flagged areas". Nobody reclassifies by hand.
- **Readiness panel** (`GET /api/history/forecast/readiness/`): a landslide line, "Located landslide
  spots with a map point: N of 30, in B of 3 barangays", from the same count the January job uses.
- **Hazard index:** `FACTORS['landslide']` is removed from `susceptibility.py`, as flood's was; the
  `landslide.png` layer and its `index.json` entry go; `all` becomes the fire layer alone (or is dropped
  if nothing else reads it; the builder checks). `terrain.png` and the drawing tools stay.
- **Not changed:** `reports/decide_views` (an approved landslide report keeps its history-based level),
  `purok_levels`, `area.py`, the `history.*` settings, and fire's and flood's models.

### 6.3 The January job: GeoAlert's own landslides

The user's ruling: the January retrain is only for GeoAlert's own landslide data, and it switches once
there is enough. The job reuses the retraining framework (`model_job.py`, `model_fits.py`, the
`model-retrain.yml` workflow, `ModelFit`).

- **Schedule:** 03:17 Manila on 6 January, cron `17 19 5 1 *` UTC, a day after flood [my call; the
  concurrency group would queue them anyway]. "Run workflow" gains `landslide`.
- **Spots:** located landslide records with a map point, plus "Affected here" marks on landslide zones,
  each with its date in Manila time and its barangay (flood's spot definition). Fetched with the job
  token, never cached, never public.
- **Step 1, the floor:** at least **30 spots in at least 3 barangays** (the user accepted these). Below
  it the job saves "Not tried: N of 30 located landslide spots, B of 3 barangays", and the live map
  stays exactly as it is. Nothing else is retrained: the outside model never changes.
- **Step 2, the held-back season:** the newest wet season's spots (1 June to 31 December of last year)
  are held back; at least **5** are needed [my call, scaled from flood's 10 for its floor of 100].
  Fewer saves "Not tried: too few new spots to test (N of 5); tries again next January".
- **Step 3, train:** the outside training table (as chosen by rule 1) **plus** GeoAlert's spots from
  before that season, with "no" points sampled on Talisay's grid within 2 km of an own spot, 3 per spot,
  at least 60 m from any spot (the same rule as 3.1). Talisay's spots form their own fold beside the
  typhoon folds. The same candidates, rule 2, cut-off walk and stability check.
- **The weight of 10** [my call, made precise after the builder check]:
  - it applies to each own spot **and** to its "no" points, so Talisay's rows keep the same 1-to-3
    balance as the typhoon rows (weighting only the spots would teach "Talisay-like ground slides");
  - it applies to the **fit** and to the **cut-off walk**: an own held-out slide counts 10 times in the
    50% and 90% recall shares, so the Red and Orange cut-offs follow Talisay's own slides once they
    exist;
  - AUC and its bootstrap stay unweighted, fold by fold, so gate 1 still asks whether the model ranks
    slides above "no" ground, and the Talisay fold's AUC is reported on its own.
- **Run time** [my call]: the landslide run gets `timeout-minutes: 360` (GitHub's limit for a job) and
  100 stability refits; fire's and flood's runs keep 120 minutes. The plan measures the offline run's
  time first; the free allowance (2,000 minutes a month on a private repository) still covers January's
  three runs.
- **Step 4, the checks to go live:**
  1. better than NOAH: pooled out-of-fold AUC gain over B0 across all folds, interval wholly above zero;
  2. the held-back season's spots: at least `test_hits_needed(n)` of their puroks Red or Orange;
  3. Red + Orange hold no more than 50% of Talisay's assessed scoring points;
  4. test data seen last;
  5. **and** no fewer of the held-back season's spots in Red or Orange than the live map. When the live
     map already catches them all, a tie switches, because the new fit is the same recipe with more
     local data (fire's tie rule).
- **The window:** a landslide fit can go live only between January and May, Manila time, between wet
  seasons, as `FLOOD_OPEN_MONTHS` does for flood.
- **Results saved** in `model_fit`: Switched, Kept current, Not tried, Skipped (purok map changed),
  Failed. The Model updates card lists them.
- **Database change:** `model_fit`'s check constraint lists the hazards, so adding `landslide` needs
  a migration (6.4).

### 6.4 Insert-only log and migrations (shared database steps need a backup and the user's go-ahead)

- **History 0013, `landslide_purok_susceptibility_log`:** `purok_id` (plain integer, no foreign key),
  `purok_name`, `barangay` (foreign key, protect), `model_version`, `source`, `level` (null when not
  assessed), `score`, `uncertain`, `not_assessed_reason`, `outlines_version`, `published_on`. Unique on
  (`purok_id`, `model_version`). Insert-only by trigger, as 0008, 0010 and 0011 do. Written once per
  new model version by `log_hazard_predictions` under `HAZARD_LOG_WRITER`.
- **History 0014:** `MODEL_FIT_HAZARDS` gains `landslide`, and the `model_fit_hazard` check constraint
  is replaced to match.

### 6.5 Frontend

- **Map, "Likely by month":** Landslide becomes a hazard choice beside Fire and Flood. Puroks are
  filled Red, Orange or Green; grey and hatched for not assessed; hatched for uncertain. The legend:
  "Landslide: where the ground tends to slide (from a machine-learning model; the same in every month,
  not a forecast of a landslide)", and it names the source. With several hazards ticked, a purok takes
  its highest level and the hover names each, as the flood build does. Public, like fire and flood.
- **Past hazards (History):** no change.
- **Barangay panel:** the barangay's puroks by landslide class (top 5, then "show all"), the not-assessed
  ones grouped with their reason, as flood.
- **"This spot":** the Landslide part shows the class of the purok holding the spot, the way flood's
  does now, and no longer reads the weighted raster.
- **Predictive models tab:** the accuracy card's landslide section (fold-by-fold AUC, the world test,
  rule 2's verdict, the gates, the class table, limits, credits); the readiness line; landslide rows in
  Model updates.
- **Decision dialog:** no change.

### 6.6 Validation report (what the card shows)

- **Training set:** events and slide counts per fold; whether the world events joined and why.
- **Candidates:** pooled and per-fold AUC with intervals; rule 2's verdict; the acceptance verdict with
  each gate.
- **Talisay test:** the test puroks and their classes; the barangay check (the share of Manipis's and
  Camp IV's scoring points in Red or Orange against the rest); the catalogue points' classes.
- **Class table:** puroks and scoring points per class; assessed and not-assessed counts with reasons.
- **Limits, in plain words:** learned in other regions and applied to Talisay; 30 m terrain; geology
  differs (Cebu's limestone and the Cordillera's volcanic and sedimentary rocks); the 3-per-slide base
  rate; few Talisay test slides, all on the Manipis road side; estimated outlines; not a forecast.
- **Credits:** NASA COOLR / Vershel et al. 2025 (CC BY 4.0); Abancó & Jones 2023, NERC EDS EIDC (Open
  Government Licence); UP NOAH (ODbL); Copernicus DEM notice; Esri / Impact Observatory annual land
  cover (CC BY 4.0); OpenStreetMap; Microsoft footprints.

## 7. Guards (no counting, no hand on a level)

- The feature builders do not import `HistoricalRecord`, the history loaders, `forecast.py` or
  `purok_levels`. A test checks the imports.
- A test fails if a model input is not on the 3.2 allowlist.
- Talisay's records are read only in the train command, after the cut-offs are written, and in the
  January job's fetch.
- No system setting, admin screen or endpoint writes a landslide class, cut-off or score; a test checks
  `system_settings` has no landslide-prediction keys and no view writes the model files. Undo stays
  Django admin's "mark an earlier fit live", as for fire and flood.
- `PATCH /api/hazards/<id>/` already refuses `severity` for every hazard type (flood build).

## 8. Tests

**Backend** (a private test database with a unique name, never the shared one):
- the clue functions on small synthetic grids, identical for a training window and the city grid;
- "no" point sampling (distance rules, 3 per slide, fixed seed);
- the road check and missing-value handling;
- the world rule and rule 2 on synthetic scores: the NN kept when tied or slightly worse, replaced when
  a simpler model's interval is wholly above zero;
- the acceptance gates, the cut-off walk (including the unreachable-90% case), the 90th-percentile
  purok score, out-of-range and assessed rules;
- the test-data-seen-last order;
- stale outlines, missing file and unreadable file;
- the forecast API with Landslide (shape, `varies_by_month: false`, fire and flood unchanged);
- the decide flow for landslides unchanged (still history-based);
- the log is insert-only; `model_fit` accepts `landslide`;
- the January job: the floor at and around 30 spots and 3 barangays; the held-back minimum of 5; the
  switch rules including the tie; the January-May window; no coordinates in what it prints or posts;
- the guards in section 7.

**Frontend:** Landslide in "Likely by month" (fills, legend, combined hazards), the panel list, the spot
text, the accuracy section, the readiness line and Model updates rows.

## 9. Rollout (each shared-database step needs a backup in Downloads and the user's go-ahead)

0. **Before the real training run:** back up the shared database, look at the two Purok Kaimito test
   records and their two hazard zones (ids `7f9e98cc-…` and `049e301d-…`; zones `c94e41e6-…` and
   `5a43ed0d-…`) to confirm they are only test data, then delete them. **Shared database.**
1. Build and test on a private test database.
2. `build_landslide_training`, `build_landslide_features`, `train_landslide_model` (offline; reading the
   shared database is read-only).
3. The user reviews the card and map on the stubbed local site (`run_readonly_site.py`).
4. Backup, then migrate history 0013 and 0014. **Shared database.**
5. First log run. **Shared database.**
6. The user commits and pushes the code, the `landslide_*` data files and the workflow change to `main`
   (Render deploys after CI, Vercel follows `main`).
7. A landslide dry run from GitHub ("Run workflow", dry run), checked together. It should save
   "Not tried: 2 of 30 located landslide spots, 1 of 3 barangays" without posting.

## 10. Approaches considered

**What the model learns from** (the user picked the first):

| | **Chosen: Philippine typhoons, world if it helps** | Philippines only | Learn NOAH's map |
|---|---|---|---|
| What | About 4,500 mapped typhoon slides; 11,000 more world slides only if the held-out typhoon test shows they help | The same, never the world | An NN trained to copy NOAH's Cebu map from terrain |
| Why or why not | Enough real slides for a neural network; same kind of typhoon rain; the test decides on the extra data | Simpler to explain, but less data and no evidence-based way to use more | Unlimited examples, but it can only copy NOAH, never beat it, and never sees a real landslide |

Also ruled out: training on the NASA Global Landslide Catalog near Talisay (points placed to 5-25 km;
about 15 within 1 km) and on GeoAlert's own 8 records (2 points).

**Where the outside training data lives** (the user said "do what is best"):

| | **Chosen: build once, keep in the project** | Rebuild every January | Keep it private |
|---|---|---|---|
| What | A one-time command writes a small table of clues (no coordinates), committed with credits | The job re-downloads inventories, tiles and NOAH for 5 provinces each January | The table stays in `.hazard_cache`, like flood's survey |
| Why or why not | The January job can add our spots to it; open licences allow it | Several GB each year for data that never changes | The January job could never add our spots to the outside slides |

## 11. Forecast gate (recorded, not built)

Reopen landslide forecasting (a rain-driven "when") only when both hold:
- a rain feed is back in GeoAlert (the Rain watch was deleted on 2026-11-22); and
- at least 20 dated, located landslide days have been logged since this build.

Until then GeoAlert makes no landslide forecast.

## 12. Calls the designer made (the user can overrule any)

1. A polygon becomes one point at its highest cell (the scar).
2. "No" ground = within 2 km of an event's mapped slides (or the study area), at least 60 m from a
   slide, 3 per slide.
3. The clue list in 3.2; absolute height left out; NOAH used as the benchmark and fallback, not as a
   clue.
4. Land cover from the year before each event (Esri / Impact Observatory, 2017 on); dropped from the
   clues if it cannot be fetched without an account; Parma left out.
5. The road check: under a tenth of Talisay's road density on steep ground sets `dist_road_m` to
   missing.
6. Talisay is scored at building centres plus road points every 20 m.
7. "In range" is judged on terrain clues only; land cover and road distance are clipped to the training
   range.
8. A purok's score is the 90th percentile of its points.
9. Assessed = at least half the scoring points in range.
10. Recall targets Red 50%, Red + Orange 90%; at most 50% of scoring points Red or Orange.
11. The candidate settings in 4.2.
12. Folds = leave one typhoon out (Egay, Mangkhut, Paeng, Agaton).
13. The NASA Global Landslide Catalog stays a private, shown-only check (the 2026-11-13 ruling).
14. The January job: 6 January; at least 5 held-back spots; own spots and their "no" points weighted
    10 in the fit and the cut-off walk, not in AUC; a tie switches; January-May window; 360 minutes
    and 100 refits.
15. Puroks outside the model's range stay grey ("not assessed yet"), as the user chose for flood,
    rather than taking NOAH's class.
16. Landslide shows inside "Likely by month", labelled as not changing by month; public.
17. "Since publishing" monitoring: under review below 80% over the last 10 or more located landslides.

## 13. Settled with the user after the builder check

- **The two test entries in Purok Kaimito (17 Nov 2026): delete them** (rollout step 0), after a backup
  and the user's go-ahead at that step.
- The builder check's other points (the out-of-range rule, land cover from after the event, the road
  check's comparison, the January job's run time, the reach of the weight of 10) were settled as
  designer's calls 4, 5, 7 and 14 in section 12.

## 14. Left to the builder

- File and function layout inside the modules named above (the flood modules are the pattern).
- How the 2 km mapped area and the "no" sampling are computed (a metric CRS per region; UTM 51N for the
  Philippines).
- Curvature and TWI formulas (any standard published form, applied identically everywhere).
- Caching and progress output for the commands; how the NOAH province files are fetched from the mirror.
- Exact copy wording within the rules above.
