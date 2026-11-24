# Flood prediction for GeoAlert: what the data can support

*Assessment, 2026-11-24. Nothing was built or changed. The shared database was read in read-only sessions. No project file was edited; this document and the probe folder named in the appendix are new and uncommitted. The scripts behind every number marked "measured" are in `.superpowers/sdd/2026-11-24-flood-assessment/probe/`.*

Markers used below:
- **[measured]**: computed this round from GeoAlert's database, its cached files or a downloaded dataset.
- **[earlier run]**: from GeoAlert's own model reports of 2026-11-12 and 2026-11-16.
- **[source]**: stated by the cited page or paper.
- **[my call]**: a proposal you can change.

---

## Summary

**The flood data cannot support a machine-learning flood forecast at any level, nor a learned model at the purok level from GeoAlert's own records.** GeoAlert holds 23 flood records, and they collapse onto 6 flood days (2021-06-12, about 2022-07-08, and four days in 2025). Only 5 records name a purok and only 6 have a map point. None records a water depth, and none confirms a place that did *not* flood. Prediction is limited by the number of independent flood days, not by the choice of algorithm. Two earlier rounds of real model runs (2026-11-12 and 2026-11-16) already showed it: no flood model could be shown to beat a flat city average.

**This round found more outside evidence than expected, and tested it against Talisay's own records:**

| Evidence | What it gives | How it did against Talisay's records [measured] |
|---|---|---|
| UP-TCAGP/USC *LiDAR Surveys and Flood Mapping of Mananga River* (2017), Annex 11 | **169 located flood-depth reports** at 107 spots: 6 typhoons, 1990-2014, 41 GeoAlert areas, 6 barangays, plus 5 "no flood here" reports | Not tested itself: it became the test set for the rows below |
| UP NOAH 25-year flood hazard map (cached) | Physics-based flood depth classes from LiDAR and FLO-2D | Separates the 169 reported flood spots from ordinary buildings in the same barangays: **AUC 0.70**. Covers all 4 pinned Mananga flood records, but **32% of the reported flood spots fall outside it** |
| UP NOAH 100-year map (cached mirror) | The same, for 100-year rain | **Internally inconsistent**: less flood area than the 25-year map in many barangays. Not usable until checked against the official source |
| EOS-RS Sentinel-1 flood proxy map, Typhoon Tino, 4 Nov 2025 | 30 m pixels "likely flooded" | Barangay AUC **0.75** against the Tino records. Misses the 3 pinned Tino spots by 200-340 m, and shows 0% in Lawaan III (1,200 houses flooded) |
| Copernicus GFM archive (Sentinel-1, 20 m, 2015 onward, no login) | Flooded / not flooded at every satellite pass | **Radar cannot see 89% of Talisay** (built-up or vegetated). The Tino-week passes over Talisay came a day after the peak and saw nothing. Not a usable label source |
| The map's current flood layer (hand-weighted overlay) | Five classes from fixed weights | **AUC 0.51 (no skill)**; marks 69% of ordinary buildings High or Very High |
| The terrain layer (HAND, height above nearest drainage, from the 30 m Copernicus DEM) | Height above the nearest channel | **AUC 0.46 (no skill)** |

**Recommendation: Strategy B, done honestly.** Build a **flood susceptibility model per purok**: *where floods tend to reach*, never *a flood is coming*. It would be a learned presence-background model, trained on the 169 field reports and GeoAlert's own points, with NOAH and terrain features. It would be tested on data it never saw: the 2021-2025 records and the satellite map of Tino. It ships only if it beats NOAH on its own (NOAH-only is the benchmark). It is assessed only where flood evidence exists, mainly the Mananga floodplain. Every other purok is shown as **"not assessed yet"** rather than given an invented level. Classes come from validated recall targets. It runs with no human in the loop and needs no live data feed.

**Strategy A (forecasting) is not recommended now.** It needs live forecast and observed rain plus far more dated flood days than exist, and it could not be validated: with 5-6 flood days, even a model that is perfect on every one reaches at best p = 0.0625. It becomes possible once the DRRMO's own logging (Section F) builds up about 20-30 dated, located flood days, or once a rain or river gauge feed for the Mananga is secured.

**Decisions for you** (asked separately):
1. Which approach.
2. What ships if the learned model fails its test.
3. Whether the two outside datasets (Annex 11 and the EOS-RS Tino map) may be used privately.
4. Which existing manual or counting mechanisms to remove (Section G).

---

## A. Existing data audit

### A.1 What GeoAlert holds today [measured, read-only, 2026-11-24]

| Item | What exists | Notes |
|---|---|---|
| Flood history records | **23** (`historical_record`, type Flood) | All sourced from news or reports (field `source` filled). Imported from the sourced sheet on 2026-11-08 |
| Independent flood days | **6**: 2021-06-12 (7 records), ~2022-07-08 (4), 2025-08-12 (1), 2025-08-18 (1), 2025-10-07 (1), 2025-11-04 Tino (9) | The 2022 date is approximate ("~8 Jul", source article blocked). **No flood recorded in 2023 or 2024** |
| Years covered | 2021-2025 | Nothing before 2021 in the database |
| Barangays named | 12, plus 1 city-wide Tino record | Tabunok 3; Dumlog, Lawaan II, Lawaan III, Lagtang, Biasong, San Isidro, Bulacao, Manipis 2 each; Jaclupan, Linao, Mohon 1 |
| Purok/sitio links | **5 records** (Sitio Bahala, Purok Kaimito, Sitio Camp 5, Sitio Paglaom, Isla Verde) | |
| Map points | **6** (4 named places, 2 landmarks) | 4 on the lower Mananga, 2 on the Manipis road |
| Kind of flood | River overflow 16, road flooding 4, flash flood 2, road flash flood 1 | Three different mechanisms: river, upland runoff, urban drainage |
| Severity | Red 16, Orange 1, Green 6 | **Not measured**: set at import by a rule on deaths and families affected (`flood_landslide.severity`) |
| Water depth or extent | **None** | |
| Time of day | 2 records have an hour; the rest are dated at midnight, with "Night" or "Morning" in the text | |
| Confirmed "no flood" observations | **None** | The app has "Clear here" field marks (`hazard_zone_mark`), but no flood zone has used them |
| App flood reports | 0 incident reports; 3 flood hazard zones, all retracted | Floods have not yet come in through the app |
| Rainfall | **None in the project now** | The NASA POWER rain file was removed on 2026-11-22 with the old models. `rain_forecast_run` keeps 27 GFS runs from the deleted Rain watch |
| Terrain | Copernicus GLO-30 DEM (a surface model, which includes buildings and trees), resampled to about 9.4 m; HAND derived from it; OSM waterways | `backend/.hazard_cache`, plus the published `frontend/public/hazard-index/terrain.png` |
| Other static layers | Microsoft building points (78,931), ESA WorldCover 2021, WorldPop 2025, UP NOAH 25-year and 100-year flood maps | All cached |
| Boundaries | 22 barangay outlines; **670 purok/sitio areas, all estimated** | Confidence: 141 high, 251 medium, 263 low, 15 blank. Official lines are still pending |
| Old prediction log | 902 flood rows (770 day, 132 month), 2026-10-17 to 2026-11-20 | From the deleted logistic model. Insert-only, so kept as history |

### A.2 Data quality, gaps and bias

- **Under-recording, not absence.** 2023 and 2024 have no flood records, while the earlier rain analysis (2026-11-17) found heavy-rain days in those years. The Mananga report adds flood events in 1990, 2013 and 2014 that GeoAlert does not hold: Ruping, Yolanda, Basyang, Queenie, Ruby and Seniang. An empty day means "not recorded", never "did not flood".
- **Reporting bias toward dramatic river floods.** 16 of 23 records are Mananga overflows. The coastal lowlands have **no** flood records, yet the NOAH 25-year map marks large shares of them medium or high depth: San Roque 45%, Tangke 22%, Pooc 13%. The Mananga field survey found 32 flood reports in Pooc. Quiet flooding goes unrecorded.
- **One storm dominates.** Tino supplies 9 of 23 records, so anything fitted to them mostly learns "which barangays flooded on 4 November 2025".
- **Mixed mechanisms.** River overflow (Mananga), upland road runoff (Manipis) and drainage ponding (Bulacao, Tabunok) have different causes. Each non-river mechanism has only 1-3 events.
- **Coarse places.** 15 of 23 records name only a barangay. All purok outlines are estimates.
- **No measured severity.** "Red" on a record means people died or many families were affected, not deep water. It cannot train a depth or severity model.
- **The river is changing.** DPWH plans to widen and dredge the Mananga in 2026 ([SunStar](https://www.sunstar.com.ph/cebu/dpwh-to-widen-mananga-river-to-stop-severe-flooding)) [source], so the hazard learned from the past will shift.

### A.3 The flood prediction code today

Flood and landslide prediction was deleted on 2026-11-22. What still touches flood levels:

| Mechanism | Where | What it is | Under your brief |
|---|---|---|---|
| Flood report alert level | `reports/decide_views._level`, which calls `history/purok_levels.py` | When a flood report is approved, its level comes from its puroks' flood history, using the **barangay hall's thresholds** held in Settings (`history.moderate_at` = 2, `history.extreme_at` = 4, `history.period_years` = 5) | **History, not predictive analytics. Unchanged** (the user's correction, 2026-11-24) |
| Manual severity edit | `PATCH /api/hazards/<id>/` (`HazardZoneDetailView.patch`) | An officer can send `severity` and change a live zone's level. No screen uses it today (the screens use PATCH only to resolve), but the API accepts it, for fires too | **Manual override. Must go** |
| Public "hazard index" flood layer | `hazards/susceptibility.py` `FACTORS['flood']`, files in `public/hazard-index/flood.png` | A weighted overlay with hand-picked weights (0.25/0.25/0.20/0.15/0.15) and fixed class breaks, shown on the public map | **Arbitrary formula. AUC 0.51 on the field points. Retire or replace** |
| Past hazards purok fills | `history/purok_levels.py`, `area.py` | Count-based history colours | History, not prediction. You asked on 2026-11-22 to keep history as it is. It must never be labelled a prediction |
| Record severity | `flood_landslide.severity()` | A rule on impact counts, applied when records are imported or closed | A description of the record, not a prediction. Keep, but never use it as a model input or a level |
| Seasonal counting | `history/forecast.py` | Counting kept only for history columns and as a benchmark | Allowed as a benchmark only |
| "Draw a flood from an observed depth" | `terrain.png` (HAND) on the map | An officer enters an observed depth and the map fills ground below it | An observation tool, not a prediction. HAND from the 30 m DEM scored AUC 0.46, so the drawn extents are rough |

---

## B. Data sufficiency

### B.1 Your six questions

| Can the data support... | Answer | Why |
|---|---|---|
| 1. Training an ML model | **No, from GeoAlert's records alone** | 6 independent flood days. Sample-size rules (Riley et al., `pmsampsize`) allow about 1-3 parameters at this event count ([prior report §A](hazard-prediction-models.md)) |
| 2. Learning temporal patterns | **No** | Two of five years have no records, from under-recording. Seasonality would be learned from 6 dates |
| 3. Rain-flood relationships | **Only crudely, city-wide** | There is no rain data in the project, and the free gridded rain badly under-reads local storms: NASA POWER gave 31-64 mm for Tino against PAGASA Mactan's 183 mm (2026-11-17 analysis) |
| 4. Predicting future floods | **Not verifiably** | Even a model right on all 5-6 days cannot reach p < 0.05 on a sign test (the best possible is p = 0.0625) |
| 5. Purok-level prediction | **Not from GeoAlert's records** (5 purok links). **Partly with the Mananga field reports**, inside the floodplain they cover | Section B.3 |
| 6. Distinguishing risk levels | **Not as severity**: no depth or extent was recorded. **As susceptibility classes, yes**, if validated against located reports | |

**Thousands of rows are not thousands of events.** The deleted model trained on 40,172 barangay-days, but they held 18 positives on 5 days [earlier run]. Every barangay-day without a record was treated as "no flood", which your brief now rightly rules out.

### B.2 What the earlier real runs already showed [earlier run]

- **2026-11-12 (logistic regression, rain and terrain):**
  - Timing was learnable at the city level: year-by-year AUC 0.75.
  - Place was not: a barangay the model never saw scored AUC 0.36, worse than chance.
  - No barangay-month ever reached Moderate.
- **2026-11-16 (pooled logistic vs. a two-part NOAH model):**
  - The two-part model was not adopted.
  - The NOAH share used then (an average of the 25-year and 100-year maps with HAND) ranked flooded barangays *below* the others (AUC 0.436).
  - Neither model put a flooded barangay at Moderate or High in the month it flooded.
- **This round explains part of that:** the 100-year layer it averaged in is internally inconsistent (A.1, D.1), and the record set mixes three flood mechanisms.

### B.3 Purok level: what is and isn't possible

- **Boundaries:** all 670 outlines are estimates. A purok value can be computed honestly from the buildings and ground inside its estimated outline. It is only as good as the outline, so each value carries the outline's confidence.
- **Labels:** GeoAlert's own records give 5 linked puroks. The Mananga field reports add located observations in **41 areas**, all in the lower Mananga floodplain (Lawaan III 39 reports, Biasong 38, Lawaan II 34, Pooc 32, Dumlog 25, San Isidro 1) [measured]. They were collected along the river, so they say nothing about upland or coastal puroks.
- **Environmental resolution:** rain products are 5-55 km cells, larger than all of Talisay, so rain cannot tell puroks apart. Only static ground features can: depth classes, relative height, distance to channel, built cover. That suits susceptibility, not forecasting.
- **Neighbouring puroks:** floodplain puroks share the river, so their hazard is linked along it. That link is captured by river-relative features (height above the Mananga channel, distance along it, upstream area). A graph network is not needed and could not be trained (Section C).
- **Conclusion:**
  - Genuine purok-level **susceptibility** is defensible in the Mananga floodplain, where located evidence exists.
  - Elsewhere it would be extrapolation, and those puroks must be shown as "not assessed yet".
  - Purok-level **forecasting** is not supported anywhere.
  - Nothing here divides barangay predictions into puroks.

---

## C. Model comparison

How much training data each family needs, set against what GeoAlert has: at most about 200 located positive observations across 6 historical events, plus 6 recent records, with almost no confirmed negatives.

| Model | What it needs to train | Learns time patterns | Uses place | Fit to our data | Overfit risk | Compute | Interpretable | Upkeep | Verdict |
|---|---|---|---|---|---|---|---|---|---|
| Logistic / presence-background GLM (Firth-penalised) | Tens of events for a few predictors | No (static) | Through its features | **Good** for 3-6 features | Low | Seconds, CPU | High | Low | **Primary candidate** |
| MaxEnt-type presence-only model (`elapid`, MIT) | Same as above; designed for presence-only data | No | Through its features | **Good**: built for "flood seen here, unknown elsewhere" | Low-moderate | Seconds | Moderate | Low | **Candidate** (mathematically close to the GLM) |
| Random Forest | Hundreds of positives and real negatives | No | Through its features | Weak; tree models overfit spatial clusters (Brenning 2005) | High | Low | Moderate | Low | Challenger only |
| XGBoost / LightGBM (monotone-constrained) | Hundreds or more | No | Through its features | Weak | High without constraints | Low | Moderate | Low | Challenger only |
| SVM | Hundreds; tuning-sensitive | No | Through its features | Weak | Moderate | Low | Low | Low | Drop |
| MLP | Typically 10× the events of a GLM (van der Ploeg 2014) | No | Through its features | Weak; the 2026-11-12 fire test showed MLPs "worked only when forced nearly linear" | High | Low | Low | Moderate | **Tested as a challenger** (your neural-network priority) |
| CNN (image patches) | Thousands of labelled patches | No | Yes | Poor: 107 spots | Very high | GPU helpful | Low | High | Drop |
| LSTM / GRU / TCN | Long continuous series of floods or river flow at many sites. Google's flood LSTM trained on 5,680 gauges ([Nearing et al. 2024](https://www.nature.com/articles/s41586-024-07145-1)); "never train an LSTM on a single basin" ([Kratzert et al. 2024](https://hess.copernicus.org/articles/28/4187/2024/)) | Yes | No | **None**: no river-flow series, 6 dated days | Extreme | Moderate | Low | High | Drop |
| CNN-LSTM hybrid | Both of the above | Yes | Yes | None | Extreme | High | Low | High | Drop |
| Graph neural network | Many events, or thousands of hydraulic simulations. SWE-GNN and mSWE-GNN learn from simulated floods, not observations ([Bentivoglio et al. 2023](https://hess.copernicus.org/articles/27/4227/2023/); [2025](https://nhess.copernicus.org/articles/25/335/2025/)) | Yes | Yes | None: we would first have to build and run our own hydraulic model | Extreme | High | Low | High | Drop |
| Physically based hydraulic model (HEC-RAS, FLO-2D, SWMM) | Calibration data: gauges and drainage | Event-based | Yes | Already done for the Mananga by UP (NOAH). Redoing it needs gauge and drainage data we lack | n/a | High | High | High | **Use its output (NOAH) as a feature and as the benchmark**, not a rebuild |

What the literature says, briefly:
- Across 71 clinical comparisons at low risk of bias, logistic regression and machine learning tied (Christodoulou et al. 2019).
- Flexible learners need many more events per variable (van der Ploeg 2014).
- Ordinary cross-validation overstates spatial models by up to 47% (Schratz 2019).
- Logistic regression generalised best across space in Brenning's landslide comparison (2005).
- These were all compiled and checked in the [2026-11-13 report](hazard-prediction-models.md).
- Flood susceptibility reviews still find Random Forest the most common choice, while noting that deep learning "require[s] longer historical data" ([review](https://arxiv.org/pdf/2502.09045)) [source].
- Positive-unlabeled (PU) learning has been applied to urban flood susceptibility specifically because unflooded-looking areas "are prone to be contaminated by positive data" ([Li et al. 2022, *Land*](https://www.mdpi.com/2073-445X/11/11/1971)) [source]. That is GeoAlert's situation exactly.

**Which approach balances performance and practicality:** a presence-background GLM (or its MaxEnt equivalent), with 3-6 physically meaningful features and target-group background sampling. Monotone XGBoost and an MLP ensemble run as pre-registered challengers. A neural network is tested, not assumed. It is adopted only if it beats the GLM and NOAH on held-out events.

---

## D. External data sources

### D.1 Tested this round [measured]

1. **Mananga flood-mapping report (UP-TCAGP and the University of San Carlos, Phil-LiDAR 1, 2017)** ([PDF](https://dream.upd.edu.ph/assets/Publications/LiDAR-Technical-Reports/USC/LiDAR-Surveys-and-Flood-Mapping-of-Mananga-River.pdf)). This is the model behind NOAH's Talisay map.
   - **Method:** HEC-HMS on 39 sub-basins, calibrated on a 15-17 March 2017 event against a rating curve at the Camp 4 Bridge (Nash-Sutcliffe 0.85), then HEC-RAS and FLO-2D on the LiDAR DEM.
   - **Rain input:** Mactan RIDF (rainfall intensity-duration-frequency curves), 5 to 100 years. One passage says "Laoag", an inconsistency.
   - **Its own validation** against 169 points from resident interviews (11-12 January 2016): **22.5% exact depth class, RMSE 1.95 m**, mostly over-estimates.
   - **Annex 11** lists every point: latitude/longitude, modelled depth, reported depth, typhoon. Counts: Seniang 80, Ruby 35, Ruping 23, Queenie 20, Yolanda 9, Basyang 2. Reported depths: 0 m ×5, under 0.5 m ×35, 0.5-1.5 m ×104, over 1.5 m ×25. Parsed into `mananga_annex11_points.csv`.
   - **Terms:** "may be copied and distributed for research and educational purposes with proper acknowledgement". Commercial use is not stated.
2. **UP NOAH 25-year map (cached, ODbL via the bettergovph mirror [source, not re-verified]).**
   - Barangay share of medium/high depth against the Tino records: AUC 0.73. Against any flood record: 0.66.
   - All 4 riverine pins are inside High (over 1.5 m). Both Manipis upland pins are outside it, 1.0 and 1.8 km away. A different mechanism.
   - At the 169 field spots, against 2,000 random buildings in the same six barangays: **AUC 0.70**.
   - 54 of 169 reported flood spots (32%) are outside any 25-year polygon.
   - NOAH calls itself beta and plans new maps ([Philstar 2025](https://www.philstar.com/headlines/2025/12/26/2496800/project-noah-improve-hazard-maps)) [source].
3. **UP NOAH 100-year map (cached mirror):** less flood area than the 25-year map where it should be more. For example, medium/high share in Tabunok is 19.8% at 25 years but 4.5% at 100 years, and in San Isidro 11.5% vs 6.4%. Barangay AUC against Tino is 0.58. **Do not use it until it is checked against the official NOAH files.** The mirror also lists a 5-year layer, not yet downloaded.
4. **EOS-RS Flood Proxy Map, Typhoon Kalmaegi/Tino (Sentinel-1, 4 Nov 2025, v0.9)** ([Sentinel Asia](https://sentinel-asia.org/EO/2025/article20251104PH.html); shapefile downloaded without login).
   - Inside Talisay: 2.52 km² in 17 barangays, touching 258 of 670 areas.
   - Barangay AUC against the Tino records: 0.75.
   - The 3 pinned Tino spots are 204-338 m from the nearest flagged pixel. Lawaan III shows 0%.
   - The producer states it is preliminary, ~30 m, and "may be less reliable over urban and vegetated areas". No licence is stated; credits are required. Usable as an **independent test** of the susceptibility map, not as training labels.
5. **Copernicus Global Flood Monitoring (GFM)**, through the EODC STAC API ([collection](https://stac.eodc.eu/api/v1/collections/GFM); [EODC tutorial](https://docs.eodc.eu/tutorials/download_gfm_python.html)).
   - **Access:** works with **no account**. 20 m, Sentinel-1, 2015 onward. Licence: the [CEMS terms](https://global-flood.emergency.copernicus.eu/terms-of-service/) (described as free and open with attribution [source, secondary]).
   - **Coverage:** in the Tino week, 16 scenes; only 2 cover Talisay (5 Nov, 05:31 and 17:57 Manila), both after the peak, both with 0 flooded pixels.
   - **The killer:** GFM's exclusion mask removes **98,981 of 111,029 city pixels (89%)**, and only 48 of 670 areas are at least half visible. **Rejected as a label source for Talisay.**
6. **DSWD DROMIC situation reports:** Tino Report No. 76 put Talisay's evacuees at 5,419 in 18 centres ([SunStar](https://www.sunstar.com.ph/cebu/over-8000-typhoon-tino-survivors-remain-in-central-visayas-evacuation-centers)) [source]. DROMIC tables can name affected barangays per event back to about 2012. Evacuation is not flooding (it can be pre-emptive), so each row must be confirmed against another source.
7. **DOST-ASTI PhilSensors** ([about](https://philsensors.asti.dost.gov.ph/site/about)): near-real-time rain and water-level stations are public to view. Historical data comes on request, and the API is "for government and academe institutions" [source]. Whether a Talisay or Mananga station exists was not confirmed. The 2017 report used a rating curve at the Camp 4 Bridge, so a gauge existed then. **The DRRMO, as a government office, is eligible to ask.**

### D.2 Source table

The licence readings are practical, not legal advice.

| Source | Provides | Resolution | History | Free | Commercial use | Account/token | Contribution | How it fits GeoAlert |
|---|---|---|---|---|---|---|---|---|
| UP NOAH flood hazard 5/25/100-yr ([mirror](https://huggingface.co/datasets/bettergovph/project-noah-hazard-maps)) | Modelled flood depth classes | LiDAR-based polygons (metres) | Static scenarios | Yes | ODbL per [Space Climate Observatory](https://www.spaceclimateobservatory.org/noah) [source]; licence PDF in the mirror not read | No | **Main "where" feature and benchmark** | Already cached; intersect with buildings per purok |
| Mananga report Annex 11 | 169 located flood depths, 6 events | Point | 1990-2014 | Yes | Research/education with acknowledgement | No | **Training labels** (positives plus 5 negatives) | One-time CSV with traced source |
| GeoAlert records and pins | 23 records, 6 points | Barangay/point | 2021-2025 | Own | Own | n/a | **Temporal test set**; new events for monitoring | Already in the database |
| EOS-RS Tino flood proxy map | Likely flooded pixels | ~30 m | One event | Yes | Not stated (credit required) | No | **Independent test** | One-time shapefile |
| Copernicus GLO-30 DEM | Surface heights | 30 m | Static | Yes | Yes, with notice | No | Relative height, distance, upstream area | Cached; known urban noise (it includes buildings) |
| ASF GLO-30 HAND ([AWS](https://registry.opendata.aws/glo-30-hand/)) | Height above drainage | 30 m | Static | Yes | CC0 per the 2026-11-13 report | No | Cross-check only (our HAND scored 0.46) | Optional |
| ESA WorldCover 2021 | Land cover (built, trees, water) | 10 m | 2020-21 | Yes | CC BY 4.0 | No | Built-up share (runoff, drainage floods) | Cached |
| Microsoft building footprints | Buildings | Point/footprint | ~2023 | Yes | ODbL | No | Exposure weights for purok aggregation | Cached |
| WorldPop 2025 | Population | 100 m | 2025 | Yes | CC BY 4.0 | No | Optional exposure weight | Cached |
| OSM waterways | River and drain lines | Vector | Current | Yes | ODbL | No | Channel geometry for river-relative features | Cached |
| SoilGrids 2.0 | Soil texture | 250 m | Static | Yes | CC BY 4.0 | No | Little: null over Tabunok and San Isidro (urban mask) | Skip |
| IBTrACS ([NCEI](https://www.ncei.noaa.gov/products/international-best-track-archive)) | Storm tracks | Track points | 1840s onward | Yes | Open (WMO Res. 40) | No | **Confirms the dates of historical typhoon events** | One-time lookup |
| NASA POWER | Daily rain and soil wetness (GWETTOP/GWETROOT, MERRA-2) | 0.5° × 0.625° | 1981 onward | Yes | Open | No | Strategy A only; too coarse for puroks. POWER's root-zone metadata has a known depth error ([Earthdata forum](https://forum.earthdata.nasa.gov/viewtopic.php?p=24413)) | Was integrated before |
| CHIRPS v3 ([CHC](https://www.chc.ucsb.edu/data/chirps3)) | Rain | 0.05° | 1981 onward | Yes | CC BY 4.0 | No | Strategy A sensitivity test; daily values are not independent (pentad-based) | Strategy A only |
| GFS (NOAA NOMADS), ECMWF Open Data | Forecast rain | 0.25° (ECMWF finer since late 2026 per the 2026-11-17 doc) | Live | Yes | Public domain / CC BY 4.0 | No | Strategy A lead time | Built and deleted before (Rain watch) |
| PAGASA public alerts (CAP feed) | Official rain/flood advisories | Province/area | Live | Yes | CC BY 4.0 (2026-11-18 check) | No | Strategy A context | Built and deleted before |
| PhilSensors (DOST-ASTI) | Rain and water level | Station | Varies | Yes | API for government/academe | Request needed | **Best upgrade for Strategy A** if a Mananga station exists | DRRMO request |
| DSWD DROMIC, NDRRMC/OCD sitreps, news | Event dates, affected barangays | Barangay | ~2012 onward | Yes | Government works (Sec. 176 IP Code: prior approval for profit) | No | **Event-date reconstruction** | One-time manual extraction, every row traced |
| Copernicus GFM | Satellite flood extent | 20 m | 2015 onward | Yes | CEMS terms | No | **Rejected**: 89% of the city excluded | n/a |

### D.3 Not recommended

- **IMERG, GSMaP, ERA5/ERA5-Land, GloFAS, Google Flood Hub API:** need accounts or keys (2026-11-13 report).
- **Open-Meteo:** ruled out by you.
- **FABDEM and MERIT Hydro's non-commercial licence:** non-commercial.
- **UP LiPAD 1 m LiDAR:** the single biggest terrain upgrade, but it needs registration and an agreement. Worth requesting as government data later.
- **Training on GFM floods from elsewhere in the Visayas, then transferring to Talisay:** dropped. The urban exclusion and the timing problem make the transfer untestable here.

### D.4 Multi-year reconstruction: what it can and cannot give

The year-by-year reconstruction you describe is feasible in this form:

| Field | Source | Resolution |
|---|---|---|
| Event date | IBTrACS / PAGASA for named typhoons; news, DROMIC and DRRMO logs for others | **Day** (event-level for Annex 11; no hours) |
| Where | Annex 11 points; GeoAlert pins; barangay names from records/DROMIC | Point, else barangay |
| Status | **confirmed flood** (a located report) / **confirmed no flood** (Annex 11's 5 zero-depth reports; future "Clear here" marks) / **unknown** (everything else) | Per place and event |
| Environment | Static features per cell/building; daily rain kept only for Strategy A | Static; daily |
| Provenance | Source, page or row, extraction date, confidence | Every row |

What it yields:
- About **12-18 dated flood events** from 1990 to 2025 (GeoAlert's 6; Annex 11's 6 typhoons; news candidates such as 2009-08-17, 2011-01-18/28, 2019-08-20, Odette 2021-12-16 and 2025-12-06, each to be confirmed).
- **Located evidence concentrated in the Mananga floodplain.**

What it cannot yield:
- Purok-by-day observations across the city.
- Confirmed "no flood" days for wet weather.
- Hourly data: no hourly source without an account.

**Rules kept:**
- Nothing is labelled flood-free for lack of a record.
- Unknown stays unknown, which is why the recommended model is presence-background (PU) rather than flood/no-flood classification.
- Dates and places carry their source.
- Test data (2021-2025, and the Tino satellite map) never enters training.

---

## E. Strategy A vs Strategy B

**Flood forecasting** estimates whether a flood will happen in a coming period, from current or forecast conditions. **Flood susceptibility** says which places are inherently more prone to flooding when floods happen. B's output must never be shown as "a flood is likely now".

### E.1 Comparison

| | A: combined historical + environmental (forecast) | B: susceptibility (static "where") |
|---|---|---|
| Data needed | Live forecast rain; observed antecedent rain; ideally a river gauge; many dated flood days for training | Static layers (NOAH, DEM, land cover, buildings); located flood observations |
| What it predicts | City- or basin-level chance of a flood in the next 1-3 days | Relative flood-proneness per purok |
| Expected reliability now | **Unknown and unprovable** (5-6 days, p ≥ 0.0625); free rain under-reads local storms | **Testable**: about 175 located observations for training, plus an independent 2021-2025 test and the Tino satellite map |
| Geographic resolution | City or basin only: rain cells exceed the city | Purok, within the evidence domain |
| Maintenance | Continuous feeds (6-hourly forecast jobs), outage handling, yearly retraining | Rebuild when inputs change (new records, official purok lines, new NOAH maps), about yearly |
| Infrastructure | A scheduler (GitHub Actions or the server), internet for the feeds | None live; runs offline once built |
| DRRMO effort | None for predictions; they must accept feed outages | None for predictions |
| Limits | Event budget; rain-source bias; no gauge | Shows where floods reach, not when; extrapolation outside the floodplain is withheld; outlines are estimates |
| Long-term | Becomes viable once logging builds up events, or a gauge feed exists | Durable; improves with every located flood the app records |

### E.2 Recommendation: B now, A gated for later

- **B (build).**
  - **Unit:** the purok/sitio area, computed from buildings and ~20-30 m cells inside it, never from a barangay value.
  - **Features [my call]:** 3-6 of the following:
    - NOAH 25-year depth class (and 5-year once the layer is checked);
    - height above the Mananga channel;
    - distance to the channel;
    - upstream contributing area;
    - local depression depth;
    - built-up share.
  - **Labels:** Annex 11 positives, plus the 5 zero-depth negatives as checks.
  - **Background:** buildings in the surveyed floodplain (target-group background, which corrects survey-route bias; [Phillips et al. 2009](https://www.whoi.edu/cms/files/Phillips_EcolApp_2009_53454.pdf)).
  - **Model candidates:** Firth presence-background GLM; MaxEnt-type (`elapid`); monotone XGBoost; MLP ensemble.
  - **Benchmark:** NOAH-25 on its own.
- **A (gated).** Reopen only when either:
  - 20-30 dated, located flood days have been logged; or
  - a rain or water-level feed for the Mananga is secured (PhilSensors request).
  
  Until then, GeoAlert makes no flood forecast claims.

### E.3 How the recommended model is judged (validation, reliability, uncertainty)

- **Splits:**
  - leave-one-event-out over Annex 11's typhoons (no event's points in its own training);
  - spatial blocks (leave-one-barangay-out within the floodplain);
  - **temporal test, held out and opened once:** GeoAlert's 2021-2025 points and records, then the EOS-RS Tino map as a second independent check.
- **Metrics that apply to presence-only data:**
  - **continuous Boyce index** ([Hirzel et al. 2006](https://www.unil.ch/biomapper/Download/Hirzel-EcoMod-2006.pdf));
  - AUC against background;
  - success-rate curves (share of flood reports captured vs. share of buildings flagged);
  - **recall of Orange+Red**, so false negatives are counted directly;
  - the confusion matrix against the 5 confirmed negatives.
- **Metrics that do not apply here, and why:**
  - precision, F1, PR-AUC and the Brier score need true negatives, which we lack;
  - background points are "unknown", not "dry", so precision against them would be misleading.
  
  The report will say this rather than print them.
- **Probability calibration:** a presence-background model gives a **relative** susceptibility, not a calibrated probability. It is shown as a class with its basis, never as a percentage.
- **Class cut-offs [my call, fixed before the test is opened]:**
  - **Red** = the smallest set of top-scoring buildings holding ≥50% of training-fold flood reports;
  - **Red+Orange** ≥ 90% of them (false-negative emphasis);
  - at most half of the assessed buildings may be Red+Orange, so "everything is red" is impossible (today's layer flags 69%);
  - the purok class = where its buildings fall;
  - each class is shown with its building shares.
- **Acceptance rule [my call, pre-registered]:** the learned model is adopted only if all three hold:
  1. its leave-one-event-out Boyce/AUC beats NOAH-only, with a paired bootstrap interval that excludes zero;
  2. its Red+Orange recall on the held-out 2021-2025 riverine records and the Tino map is ≥ 80%;
  3. the model choice and cut-offs are fixed before any test data is loaded.
  
  The 4 test points lie 16-78 m from survey spots, so they test whether flood places persist from 1990-2014 into 2021-2025 (across time); the spatial folds test new places.
  
  If it fails, the decision in question 2 applies.
- **"Not assessed" (never guessed):**
  - puroks outside the evidence domain (no located flood report of the same mechanism nearby);
  - puroks whose features fall outside the training range;
  - puroks whose class flips in more than 20% of bootstrap refits [my call];
  - puroks with a low-confidence outline, flagged as "uncertain".
- **Monitoring:**
  - every new flood record or field mark is scored against the published class on arrival;
  - a flood in Green counts as a miss;
  - if recall over the last 10 new located floods falls below 80%, the model card says "under review" and the next scheduled retrain runs;
  - nobody reclassifies by hand.

---

## F. DRRMO recommendation

**Yes: move to a flood susceptibility model (Strategy B) now, and stop presenting any flood level as a forecast.** The combined forecasting approach is neither reliable (it cannot be validated) nor sustainable (live feeds, no gauge) with today's data.

What the DRRMO can collect so the system improves, with no analytical work on their side:
1. **Every flood logged in the app** with the purok, a pin, the date and hour, and the water depth if known. The report form already carries puroks and pins; a depth field is the one addition worth designing.
2. **"Clear here" marks** during rainfall warnings. The `hazard_zone_mark` feature already exists. These are the only way to get confirmed non-flood observations, the missing half of any forecast model.
3. **A data request to DOST-ASTI (PhilSensors)** for any rain or water-level station on the Mananga, and to PAGASA (via FOI) for Mactan daily rain. Government offices qualify.
4. **Official purok boundaries.** Recomputing the features needs no retraining.
5. **The city DRRM plan's list of flood-prone sitios**, used only as a check, never as labels or levels.
6. **A request to UP for the 1 m LiDAR terrain (LiPAD).** It would replace the noisy 30 m surface model.

Maintenance after turnover: none for predictions. A scheduled job rebuilds the susceptibility when its inputs change and publishes only if the acceptance rule passes. It needs no internet once built, and no paid service.

---

## G. Automation assessment

### G.1 The automated pipeline (no human in any prediction)

1. Collect inputs: flood records, field marks, purok outlines, static layers. Hash each one.
2. Build features per cell and building, then aggregate per purok.
3. Train the candidates with fixed seeds. Validate them under the pre-registered rule; it alone decides adoption.
4. Score every purok, apply the locked cut-offs, and attach the uncertainty and "not assessed" flags.
5. Write to an **insert-only** prediction table. Each row holds:
   - purok, score, class, flags;
   - model version, input hashes;
   - built-at time, valid-from date;
   - the reason for any "not assessed".
6. The API and the map read the latest published version. No approval step.
7. Repeat on a schedule [my call: monthly check] or when an input hash changes.

Retraining is a documented command anyone may start. It cannot replace the deployed model unless the rule passes, and it records why it failed when it doesn't.

### G.2 Mechanisms that must go (they let a person or a hand-made formula touch a prediction)

**Correction, 2026-11-24.** History and predictive analytics are separate parts of GeoAlert. History's levels use the barangay hall's thresholds and are not predictions. This includes the history-based level that an approved flood report takes, and it stays unchanged. An earlier draft of this list wrongly included it.

1. **`severity` in `PATCH /api/hazards/<id>/`.** Removed, as the user picked, so no officer can set or raise a live level by hand. The endpoint is shared, so this covers fire too.
2. **The weighted-overlay flood layer** behind the map's "This spot" reading (AUC 0.51). Replaced by the model's output.
3. **Never connect History** to the flood prediction: not `purok_levels`, not the `history.*` thresholds, not `flood_landslide.severity()`. The prediction model reads none of them, and they keep serving History as they do today.

Admin powers left, all on the permitted side of your brief: maintain source data, start retraining, view reports and logs. No setting will change a level, a threshold or a probability.

**One point to confirm with you:** the Extreme second-officer approval for live alerts concerns confirming a real event, not a prediction. The susceptibility layer itself publishes with no approval. Tell me if you want the alert workflow treated as prediction too.

---

## H. Implementation roadmap (after your approval; every shared-database step needs a backup and your go-ahead)

1. **Design:** a spec written from your answers, approved before a plan (brainstorming, then writing-plans), per your standing rule. Never committed.
2. **Data preparation:** the Annex 11 CSV with provenance; event dates confirmed via IBTrACS; the NOAH 25-year layer re-checked against the official source; the 5-year layer fetched; the 100-year inconsistency resolved or that layer excluded; the EOS-RS Tino map stored as test data.
3. **Optional reconstruction:** news and DROMIC event dates from 2009 to 2025, at barangay level, each row confirmed. This feeds monitoring and the future Strategy A, not the susceptibility model.
4. **Feature engineering:** cell and building features and purok aggregation, offline (`build_flood_features`), reusing the cached layers.
5. **Model selection and validation:** `train_flood_model`, with the candidates, the pre-registered rule, the locked cut-offs and the report JSON.
6. **Automated classification:** done inside training; no settings.
7. **Backend:** the insert-only susceptibility log table (migration); flood added to the forecast API; removing PATCH severity; scoring new records on arrival. History, including the flood report level, is unchanged.
8. **Frontend:**
   - a "Flood-prone puroks (susceptibility)" layer with "not a forecast" copy and a grey "not assessed yet" state;
   - the model report card (Boyce, recall, limits);
   - the old flood index retired.
9. **Testing and documentation:** test-first; private test database (never the shared one); README and attribution: UP-TCAGP/USC, UP NOAH (ODbL), EOS-RS / Copernicus Sentinel.
10. **Deployment and maintenance:** migration with a backup; first build; the scheduled rebuild check; the monitoring rule. The Strategy A gate is reviewed when the logged-event count reaches the threshold.

---

## Appendix 1. Probes run this round (all read-only)

Folder: `.superpowers/sdd/2026-11-24-flood-assessment/probe/`.

| Script | What it did |
|---|---|
| `audit_db.py` | Database audit (records, days, links, reports, zones, puroks, prediction log), in a read-only transaction |
| `eosrs_check.py`, `eosrs_agree.py` | EOS-RS Tino flood proxy map against barangays, puroks, records and pins |
| `gfm_list.py`, `gfm_count.py`, `gfm_window.py` | GFM STAC queries and window reads of flood, exclusion and reference-water rasters over Talisay |
| `noah_agree.py` | NOAH 25/100-year shares per barangay against the records and pins |
| `annex11.py`, `annex11_check.py` | Parsing Annex 11; placing the points in areas and barangays; NOAH-25, HAND and public flood layer against 2,000 random buildings in the same barangays |
| `mananga_annex11_points.csv` | The 169 parsed points (point, lat, lon, modelled 100-year depth, reported depth, event) |

Downloaded data (EOS-RS shapefile, GFM windows read remotely, the Mananga PDF) stayed in the session scratchpad and was not added to the project.

## Appendix 2. Main sources

- GeoAlert internal: [hazard-prediction-models.md](hazard-prediction-models.md) (2026-11-13, sample-size and model evidence, licences); [2026-11-17-rain-watch-and-rainfall-data.md](2026-11-17-rain-watch-and-rainfall-data.md) (rain sources, the Tino rain comparison); [2026-11-22-fire-purok-prediction-audit.md](2026-11-22-fire-purok-prediction-audit.md) (purok outline facts).
- Paringit & Otadoy (eds.) 2017, *LiDAR Surveys and Flood Mapping of Mananga River*, UP-TCAGP: [PDF](https://dream.upd.edu.ph/assets/Publications/LiDAR-Technical-Reports/USC/LiDAR-Surveys-and-Flood-Mapping-of-Mananga-River.pdf).
- EOS-RS Flood Proxy Map, Typhoon Kalmaegi: [Sentinel Asia](https://sentinel-asia.org/EO/2025/article20251104PH.html); Manila Observatory: [Impacts of Typhoon Kalmaegi in Cebu](https://mapsanddata.observatory.ph/20787/impacts-of-typhoon-kalmaegi-in-cebu/).
- Copernicus GFM: [STAC collection](https://stac.eodc.eu/api/v1/collections/GFM), [EODC tutorial](https://docs.eodc.eu/tutorials/download_gfm_python.html), [CEMS terms](https://global-flood.emergency.copernicus.eu/terms-of-service/), [TU Wien](https://tuwien.at/en/mg/geo/rs/open-data/gfm).
- UP NOAH: [mirror](https://huggingface.co/datasets/bettergovph/project-noah-hazard-maps), [Space Climate Observatory](https://www.spaceclimateobservatory.org/noah), [Philstar 2025](https://www.philstar.com/headlines/2025/12/26/2496800/project-noah-improve-hazard-maps).
- DOST-ASTI [PhilSensors](https://philsensors.asti.dost.gov.ph/site/about); DROMIC via [SunStar](https://www.sunstar.com.ph/cebu/over-8000-typhoon-tino-survivors-remain-in-central-visayas-evacuation-centers).
- Methods: [Li et al. 2022 PU flood](https://www.mdpi.com/2073-445X/11/11/1971); [PU bagging, landslides](https://pmc.ncbi.nlm.nih.gov/articles/PMC10965908); [Phillips et al. 2009](https://www.whoi.edu/cms/files/Phillips_EcolApp_2009_53454.pdf); [Hirzel et al. 2006](https://www.unil.ch/biomapper/Download/Hirzel-EcoMod-2006.pdf); [Nearing et al. 2024](https://www.nature.com/articles/s41586-024-07145-1); [Kratzert et al. 2024](https://hess.copernicus.org/articles/28/4187/2024/); [Bentivoglio et al. 2023](https://hess.copernicus.org/articles/27/4227/2023/), [2025](https://nhess.copernicus.org/articles/25/335/2025/); [susceptibility review](https://arxiv.org/pdf/2502.09045); [Brenning 2005](https://nhess.copernicus.org/articles/5/853/2005/). The sample-size, calibration and rare-event sources are cited in [hazard-prediction-models.md](hazard-prediction-models.md) §A and §F.
- Data: [CHIRPS v3](https://www.chc.ucsb.edu/data/chirps3); [IBTrACS](https://www.ncei.noaa.gov/products/international-best-track-archive); [ASF HAND](https://registry.opendata.aws/glo-30-hand/); [MERRA-2 FAQ](https://gmao.gsfc.nasa.gov/gmao-products/merra-2/faq_merra-2/).
