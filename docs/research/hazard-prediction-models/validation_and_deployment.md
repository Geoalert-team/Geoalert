# Validation methodology for rare-event hazard models, and a low-maintenance deployment/MLOps architecture for GeoAlert (Django + PostgreSQL/PostGIS), with verified licences

Researched 2026-11-13. How each item was checked:
- **[V]**: confirmed this session by fetching or searching the source.
- **[V-lic]**: licence read this session from the project's LICENSE file (raw.githubusercontent.com) and/or its PyPI metadata (pypi.org JSON API, latest version and upload date as of 2026-11-13).
- **[K]**: a well-known paper or document cited from prior knowledge. The URL/DOI is given but was not re-fetched this session, so check exact wording before quoting.
- **Inferences** are my reasoning applied to GeoAlert, not source claims.

Local context checked (read only, nothing changed): `backend/requirements/base.txt` pins Django==4.2.13, djangorestframework==3.15.1, djangorestframework-gis==1.0, scikit-learn==1.9.1, xgboost-cpu==3.2.0, scipy==1.17.1 and numpy==2.4.2. It has no Celery, Redis or other task queue. Gunicorn is in production.txt. The flood/landslide models are in `apps/history/hazard_models.py` and the likelihood model is in `apps/history/model_forecast.py` (per comments in the requirements file). Row count check: 22 barangays × 1,826 days (2021-01-01..2025-12-31) = 40,172. Flood prevalence 18/40,172 = 0.000448; landslide 8/40,172 = 0.000199 (computed).

---

## Q1. Cross-validation design for clustered, very rare spatiotemporal events

### Takeaway
Random row-level CV is invalid here, and blocked CV must use the *event day* (storm) as the block. GeoAlert should keep rolling-origin yearly folds as the honest "deployment-like" estimate. It should add (a) leave-one-event-day-out CV with a temporal buffer, so every fold trains on all other storms, and (b) a split into "when" skill (which days) and "where" skill (which barangays on an event day). It should also report the area of applicability, for days whose rain lies outside anything seen in training. With 5 flood event days, no CV scheme can produce a stable single number. CV here is for spotting failure, not for proving superiority.

### Cited Findings
- Roberts et al. 2017 (Ecography 40:913–929) review blocked CV for temporal, spatial, hierarchical and phylogenetic structure. Random CV ignores dependence and underestimates predictive error. In their simulations and case studies, block CV did better than random CV at predicting to new data or new predictor space and at choosing causal predictors. They recommend blocking whenever dependence exists, *even when model residuals show no visible correlation* [V] — [doi:10.1111/ecog.02881](https://doi.org/10.1111/ecog.02881); [PDF](https://www.biometrie.uni-freiburg.de/mitarbeiter/dormann/roberts-et-al-2017-ecography.pdf); [summary record](https://pred.uni-regensburg.de/id/eprint/1455/)
- Ploton et al. 2020 (Nat Commun 11:4540) used an 11.8-million-tree inventory in central Africa. Non-spatial validation said a random forest explained more than half of biomass variation. Spatial validation that accounts for spatial autocorrelation found "quasi-null predictive power". The usual validation that ignores spatial structure "leads to overoptimistic assessment" [V] — [doi:10.1038/s41467-020-18321-y](https://doi.org/10.1038/s41467-020-18321-y); [DOAJ](https://doaj.org/article/628f13be6ee34becb88ef385ebe283e3)
- Meyer & Pebesma 2021 (MEE 12(9):1620–1633) define the **area of applicability (AOA)**. A dissimilarity index (DI) measures distance to the training data in importance-weighted predictor space, and is computed with the *same CV strategy* as the model. The AOA threshold is the outlier-removed maximum training DI. Inside the AOA, prediction error matches CV error; outside it, the CV error does not apply. They recommend publishing a DI map alongside prediction maps. The arXiv preprint used a 0.95 quantile; the published version uses outlier-removed maximum [V] — [doi:10.1111/2041-210X.13650](https://doi.org/10.1111/2041-210X.13650); [arXiv 2005.07939](https://arxiv.org/pdf/2005.07939)
- Meyer & Pebesma 2022 (Nat Commun 13:2208) argue that global ML maps are often validated with random CV and published without an assessment of where predictions can be trusted [K] — [doi:10.1038/s41467-022-29838-9](https://doi.org/10.1038/s41467-022-29838-9)
- Meyer et al. 2018 (Environ. Modelling & Software 101:1–9) introduce "target-oriented" validation: leave-location-out, leave-time-out and **leave-location-and-time-out (LLTO)** CV for spatio-temporal ML. Random CV overestimated performance [K] — [doi:10.1016/j.envsoft.2017.12.001](https://doi.org/10.1016/j.envsoft.2017.12.001)
- Counterpoint: Wadoux et al. 2021 (Ecol. Modelling 457:109692), "Spatial cross-validation is not the right way to evaluate map accuracy". When validation data are a *probability sample* of the map area, design-based random validation is unbiased, and spatial CV can be *pessimistic* [K] — [doi:10.1016/j.ecolmodel.2021.109692](https://doi.org/10.1016/j.ecolmodel.2021.109692)
- Brenning 2012 (IGARSS) is the R package `sperrorest` for spatial CV and bootstrap error estimation; it showed non-spatial CV is over-optimistic for remote-sensing classifiers [K] — [doi:10.1109/IGARSS.2012.6352393](https://doi.org/10.1109/IGARSS.2012.6352393)
- Buffered (spatial) leave-one-out removes training points within a distance of the held-out point: Le Rest et al. 2014, Global Ecol. Biogeogr. [K] — [doi:10.1111/geb.12161](https://doi.org/10.1111/geb.12161). blockCV R package: Valavi et al. 2019 MEE [K] — [doi:10.1111/2041-210X.13107](https://doi.org/10.1111/2041-210X.13107); licence GPL-3 [V-lic] — [LICENSE.md](https://raw.githubusercontent.com/rvalavi/blockCV/HEAD/LICENSE.md)
- Time-series CV: Tashman 2000 (IJF 16:437–450) reviews out-of-sample tests, including rolling-origin (updated) evaluation versus a fixed origin [K] — [doi:10.1016/S0169-2070(00)00065-0](https://doi.org/10.1016/S0169-2070(00)00065-0). Bergmeir, Hyndman & Koo 2018 (CSDA 120:70–83) show standard K-fold CV is valid for *purely autoregressive* models with uncorrelated errors, but not in general [K] — [doi:10.1016/j.csda.2017.11.003](https://doi.org/10.1016/j.csda.2017.11.003). Bergmeir & Benítez 2012 (Inf. Sci. 191:192–213) compare blocked CV with last-block evaluation [K] — [doi:10.1016/j.ins.2011.12.028](https://doi.org/10.1016/j.ins.2011.12.028). Rolling-origin is explained in Hyndman & Athanasopoulos FPP3 §5.10 [K] — [otexts.com/fpp3/tscv.html](https://otexts.com/fpp3/tscv.html)
- Event- and time-interval holdouts in hazard ML:
  - A space-time landslide model fitted on five time intervals and tested on the sixth, rotating through all six [V] — [arXiv 1912.01233](https://arxiv.org/pdf/1912.01233)
  - An earthquake-landslide study (Nepal) argues that "automated Grouped Cross-Validation, where correlated groups of points are left out" suits point-pattern data better [V] — [arXiv 2507.08742](https://arxiv.org/pdf/2507.08742)
  - An operational flood ML study trains on all events except the highest-stage one and validates on it ("leave-extreme-out"), to test extrapolation to unprecedented floods [V] — [arXiv 2111.02780](https://arxiv.org/pdf/2111.02780)
  - I found no paper using the exact phrase "leave-one-event-out" for floods or landslides [V] (search above)
- Nested CV is needed when CV also chooses hyperparameters or thresholds: the inner loop selects, the outer loop estimates. Selecting and estimating on the same folds is a known source of optimism. Roberts et al. 2017 also discuss blocking for model selection [V, same source as above].

### Inferences
- **Why the current rolling-origin flood folds are weak.** Each fold had one training flood day, so the model effectively learns "rain like that one day". The 2023/2024/2025 tests then measure whether the next storm resembles it. Keep this as the primary, deployment-realistic estimate, but it cannot rank models with any confidence.
- **Add leave-one-event-day-out (LOEO) CV:**
  - Groups are *event clusters*: the event day plus a buffer of ±k days, with k at least the longest antecedent-rain window in the features (e.g. 3–7 days). This stops the training set from sharing rain windows with the test storm.
  - Non-event days go into contiguous date blocks (e.g. calendar months), with the same buffer.
  - Use `sklearn.model_selection.LeaveOneGroupOut` or `GroupKFold` with these groups.
  - This lets each fold train on 4 of the 5 flood storms. It breaks strict time order, so report it as an "exchangeable-storms" estimate beside rolling-origin, never instead of it.
  - For landslides, 8 events on 8 days with 7 in one barangay: LOEO is possible, but leave-one-barangay-out (LOBO) is near-meaningless. Seven of the eight positives sit in one held-out group, and every other group has 0–1 positives.
- **Split the skill into two parts:**
  - Temporal ("when"): aggregate to city-day, e.g. the max or sum of barangay probabilities, and score whether event days rank above other wet days (AUC/PR among days, or among days with rain > X mm).
  - Spatial ("where"): only on event days, score whether affected barangays rank above unaffected ones. This is computable on the typhoon day with 10/22 positives and nearly meaningless on single-positive days.
  - Pooled row-level ROC-AUC 0.96 mostly reflects the "when" part, because tens of thousands of dry days are easy negatives. LOBO AUC 0.36 says the "where" part does not transfer to unseen barangays, which matches Ploton et al.
- **Area of applicability.** Compute a DI on the (rain, antecedent rain, terrain) feature vector for each forecast day, against the training set, with scikit-learn NearestNeighbors on standardised, importance-weighted features. Show "outside model experience" when DI exceeds the training threshold. This matters most for record typhoon rainfall, which is exactly when a warning is needed.
- **Fire (monthly counts per barangay).** Use rolling-origin by month or season blocks with a buffer for lag features. A LOBO-style check is meaningful only if the model is meant to transfer across barangays; if barangay-level effects are part of the model, it is not.

### Gaps
- I found no peer-reviewed methods paper that specifically formalises leave-one-storm-day-out CV for barangay- or municipality-day flood occurrence. The recommendation is adapted from Roberts et al. (blocking by dependence structure) and Meyer et al. (LLTO).
- No published guidance found on buffer length for antecedent-rainfall features; it has to be set from the feature windows.
- The CAST R package (AOA implementation) licence could not be verified: no LICENSE file at the standard GitHub paths. A Python implementation would need to be written in-house.

---

## Q2. Data leakage sources specific to this setting

### Takeaway
The most likely leaks in GeoAlert are:
- inventory-derived features or baselines computed over all years, including the test year;
- same-day or future rain in the features, reported as if it were a forecast;
- thresholds and hyperparameters tuned after seeing the 2023–2025 tests;
- one physical event counted many times as independent rows;
- training on revised "final" reanalysis rain while serving on near-real-time values.

Each needs an explicit guard in the training command.

### Cited Findings
- Kapoor & Narayanan 2023 (Patterns) found leakage in at least 294 studies across 17 fields and grouped it into eight types. The types include preprocessing on train+test together, illegitimate features, temporal leakage, sampling bias, and non-independence between train and test. In their civil-war case study, once leakage was fixed, ML models "no longer perform substantively better" than decades-old logistic regression. They propose "model info sheets" to prevent each type [V] — [PMC10499856](https://pmc.ncbi.nlm.nih.gov/articles/PMC10499856); [project page](https://reproducible.cs.princeton.edu/)
- Kaufman et al. 2012 (ACM TKDD) give the classic leakage definition: the model uses information that would not legitimately be available at prediction time [K] — [doi:10.1145/2382577.2382579](https://doi.org/10.1145/2382577.2382579)
- Fitting a calibrator on the training outputs "would thus result in a biased calibrator that maps to probabilities closer to 0 and 1 than it should" (scikit-learn). The same logic applies to any post-processing step fitted on data the model has already seen [V] — [scikit-learn calibration](https://scikit-learn.org/stable/modules/calibration.html)
- Roberts et al. 2017: dependence between train and test (spatial, temporal, hierarchical) inflates apparent skill even when residuals look independent [V] — [doi:10.1111/ecog.02881](https://doi.org/10.1111/ecog.02881)

### Inferences (GeoAlert-specific leakage checklist)
1. **Rolling rain windows.** A trailing window (e.g. 3-day antecedent rain ending on day t−1) that crosses the train/test date is *not* leakage, because the data are known at forecast time.
   - Leakage happens if windows are centred or forward-looking, if the day-t total is used while the product is described as a forecast for day t, or if storm totals are computed after the event.
   - Decide and document whether the product is a *nowcast/hindcast* (observed day-t rain) or a *forecast*, which must use forecast rain.
   - In any group-CV, put a buffer of at least the window length around each held-out block.
2. **Inventory-derived features.** Leaky if computed over the full 2021–2025 record and then used in folds that test on part of that record. Examples: "past flood count per barangay", "distance to past landslide", "barangay prior rate", or terrain variables sampled at event locations, such as slope at mapped landslide points versus barangay means.
   - The per-barangay historical-rate *baseline* has the same problem: recompute it from training years only in every fold.
3. **Tuning on the test year.** The 15%/25% level cut-offs, XGBoost hyperparameters, the choice of rain windows, and the decision to keep Poisson over the NN for fire were all made after looking at 2023–2025 results. Those years are therefore no longer clean tests for those choices.
   - Freeze the choices, then hold out the next season (2026 wet season) as a true prospective test, or use nested CV.
4. **Duplicates of one event.** The same flood can be logged by several sources or on consecutive days, and multi-barangay floods are counted once per barangay.
   - Deduplicate at the record level: same hazard, barangay and date or date window, linked sources.
   - Treat multi-barangay or multi-day occurrences as one *cluster* for resampling and CV, not as independent positives. The single typhoon day with 10 positives is one cluster.
5. **Future-revised data.** Training should use the same vintage and latency of rain data that will be available live; otherwise the live model sees noisier inputs than it was trained on.
   - Store the raw rain value used for each live prediction, so later re-verification uses what the model actually saw.
6. **Labels that depend on the response.** Under-recording, where floods are only recorded when reported, makes labels correlate with population and road access. This is not leakage strictly, but it biases both training and evaluation. State it as a limitation.

### Gaps
- I did not verify NASA POWER's revision/latency policy (near-real-time versus final values) this session. Check the POWER documentation before claiming whether revisions occur.
- I found no published leakage case study specific to barangay-level flood or landslide records in the Philippines.

---

## Q3. Metrics for extreme imbalance and probabilistic forecasts

### Takeaway
Use the log score and Brier score (with skill scores against climatology *and* against the per-barangay-rate baseline) as primary metrics. Add PR-AUC read against its prevalence baseline, reliability shown as observed-vs-expected counts (bins are too sparse here), and event-level tables. For yes/no levels, use base-rate-robust verification scores (Peirce/HK, SEDI) rather than CSI/ETS alone. ROC-AUC alone is uninformative at a prevalence of 0.00045.

### Cited Findings
- Definitions and caveats from the WWRP/WCRP Joint Working Group on Forecast Verification Research (JWGFVR) site. The old CAWCR URL now 301-redirects there. H = hits, M = misses, F = false alarms, C = correct negatives, T = total [V] — [jwgfvr.github.io/forecastverification](https://jwgfvr.github.io/forecastverification) (old: https://www.cawcr.gov.au/projects/verification/)
  - POD (hit rate) = H/(H+M). Can be inflated by issuing more "yes" forecasts; pair it with FAR.
  - FAR = F/(H+F). "Very sensitive to climatological frequency".
  - POFD = F/(F+C).
  - CSI = H/(H+M+F). Ignores correct negatives and is lower for rarer events.
  - ETS (Gilbert skill score) = (H−H_rand)/(H+M+F−H_rand), with H_rand = (H+M)(H+F)/T. Range −1/3..1.
  - Peirce/Hanssen–Kuipers = POD − POFD. "Does not depend on climatological frequency"; for rare events it is dominated by POD.
  - HSS needs a large sample so all cells are filled.
  - Odds ratio and ORSS (Yule's Q) are hard to hedge, but unusable if any cell is 0.
  - EDI = (ln F − ln H)/(ln F + ln H), with H = POD and F = POFD. It and SEDI are base-rate independent.
  - Brier score: "rare events can get a good BS with no real skill". It decomposes into reliability, resolution and uncertainty (Murphy 1973).
  - BSS = 1 − BS/BS_ref: "unstable on small samples, and rarer events need more samples"; not strictly proper.
  - Reliability diagram: points below the diagonal mean over-forecasting; the histogram shows sharpness.
  - ROC: insensitive to bias, so a miscalibrated forecast can score well.
  - Relative value: a skill score of expected expense versus climatology as a function of the cost/loss ratio C/L.
- Ferro & Stephenson 2011 (Weather and Forecasting 26(5):699–713): traditional performance measures "degenerate to trivial values as events become rarer". They introduce EDI and the symmetric SEDI as improvements on the extreme dependency score (EDS; Stephenson et al. 2008). ECMWF and the UK Met Office have since used SEDI for precipitation verification [V] — [doi:10.1175/WAF-D-10-05030.1](https://doi.org/10.1175/WAF-D-10-05030.1); [Exeter repository](https://ore.exeter.ac.uk/repository/handle/10871/8521); [ECMWF extremes verification](https://www.ecmwf.int/sites/default/files/elibrary/2014/10909-verification-extreme-weather-events-discrete-predictands.pdf)
- Hogan et al. 2010 (WaF 25:710–726), "Equitability revisited: why the 'equitable threat score' is not equitable" [K] — [doi:10.1175/2009WAF2222350.1](https://doi.org/10.1175/2009WAF2222350.1)
- Saito & Rehmsmeier 2015 (PLoS ONE 10:e0118432): on imbalanced data the precision-recall plot is more informative than ROC, and the no-skill PR baseline equals the positive fraction, P/(P+N) [K] — [doi:10.1371/journal.pone.0118432](https://doi.org/10.1371/journal.pone.0118432)
- scikit-learn: Brier score and log loss are strictly proper and mix calibration, resolution and uncertainty. "A lower Brier loss … does not necessarily mean a better calibrated model". `calibration_curve`/`CalibrationDisplay` bin predictions and plot the fraction of positives [V] — [scikit-learn calibration](https://scikit-learn.org/stable/modules/calibration.html)
- Gneiting & Raftery 2007 (JASA 102:359–378) is the reference on strictly proper scoring rules (log, Brier/quadratic) [K] — [doi:10.1198/016214506000001437](https://doi.org/10.1198/016214506000001437)
- Bröcker & Smith 2007 (WaF 22:651–661) add consistency bars to reliability diagrams to show sampling variability [K] — [doi:10.1175/WAF993.1](https://doi.org/10.1175/WAF993.1)
- Count forecasts (fire): Czado, Gneiting & Held 2009 (Biometrics 65:1254–1261) give PIT histograms for count data and proper scores (log, ranked probability, Dawid–Sebastiani) [K] — [doi:10.1111/j.1541-0420.2009.01191.x](https://doi.org/10.1111/j.1541-0420.2009.01191.x)
- Standard texts: Wilks, *Statistical Methods in the Atmospheric Sciences* (4th ed., Elsevier 2019), forecast verification chapters [K] — [ScienceDirect book page](https://www.sciencedirect.com/book/9780128158234/statistical-methods-in-the-atmospheric-sciences); Jolliffe & Stephenson (eds.), *Forecast Verification: A Practitioner's Guide* (2nd ed., Wiley 2012) [K]
- Murphy 1993 (WaF 8:281–293), "What is a good forecast?", separates consistency, quality and value [K] — [doi:10.1175/1520-0434(1993)008<0281:WIAGFA>2.0.CO;2](https://doi.org/10.1175/1520-0434(1993)008%3C0281:WIAGFA%3E2.0.CO;2)
- Python verification libraries, licences verified [V-lic]:
  - `scores` 2.7.0 (2026-09-05), Apache-2.0 — [PyPI](https://pypi.org/project/scores/), [LICENSE](https://raw.githubusercontent.com/nci/scores/HEAD/LICENSE). Provenance [K]: the Australian Bureau of Meteorology's verification library, hosted under the NCI GitHub org, with contingency-table scores and Brier/proper scores.
  - `xskillscore` 0.0.29 (2026-02-18), Apache-2.0 — [PyPI](https://pypi.org/project/xskillscore/)
  - `properscoring` 0.1, Apache, last release 2015, so stale — [PyPI](https://pypi.org/project/properscoring/)

### Inferences
- **Read PR-AUC against its baseline.** The pooled flood PR-AUC of 0.05 against a prevalence of 0.00045 is about 110× the no-skill baseline: real but very imprecise ranking skill. Always print the baseline beside PR-AUC; for landslides it is 0.0002.
- **Brier/BSS.** With prevalence this low, a constant climatology forecast already gives BS ≈ 0.00045. Report BSS against (a) climatology and (b) the per-barangay training-years rate. Use the log score as the tie-breaker: it punishes confident misses on event days hardest, which matches the DRRMO's main concern.
- **Reliability.** Ten-bin reliability diagrams will have 0–2 positives per bin. Use instead: observed versus expected counts per year, season and barangay group, plus calibration-in-the-large and calibration slope (Q6), with Bröcker–Smith consistency bars if a diagram is shown.
- **Categorical levels (Low/Moderate/High).** Report a 2×2 table per cut-off (Moderate+ and High) with H, M, F, C. Use POD and FAR (for communication), Peirce/HK (base-rate independent), SEDI (rare-event robust), and *false alarms per hit*.
  - CSI/ETS can be listed for familiarity, but they degenerate as events become rarer (Ferro & Stephenson).
- **Event-level scoring.** For each recorded event (barangay-day), show the probability and level each model gave, and the level the day before. For each event day, show how many barangays were flagged High and how many of them had events.
  - Five storms plus eight landslides is few enough to list in full in the report, and that table is more convincing to a DRRMO than any pooled metric.
- **Fire.** Use Poisson log score or deviance and MAE of counts against (a) the per-barangay mean rate and (b) a seasonal climatology. Add a PIT histogram and observed-vs-expected totals by barangay and month.

### Gaps
- I could not verify a single authoritative statement of the best metric for barangay-day flood occurrence; the recommendations combine meteorological verification practice with clinical prediction practice.
- I did not check whether `scores` implements SEDI specifically. A hand-written SEDI is about five lines of numpy.

---

## Q4. Statistical comparison against baselines with few events; power; honest reporting

### Takeaway
With 5 flood storm days and 8 landslide days, almost no test can show that a new model is better.
- A paired sign test over 5 storm days cannot reach two-sided p < 0.05 even if the new model wins on every day (minimum p = 0.0625).
- AUC standard errors are ±0.1–0.25 once clustering is respected.
- Validation guidance in prediction modelling asks for at least 100 events, preferably 200 or more, which is roughly a century of flood event-days at the observed rate.

GeoAlert should therefore use cluster (event-day) bootstrap intervals, paired per-event comparisons, and a pre-registered decision rule. "Not yet distinguishable from baseline" is a legitimate, reportable outcome.

### Cited Findings
- Collins, Ogundimu & Altman 2016 (Stat Med 35:214–226): an external validation needs **at least 100 events, preferably 200 or more**. A review found just under half of external validation studies used fewer than 100 events [V] — [PMC4738418](https://pmc.ncbi.nlm.nih.gov/articles/PMC4738418); [Northumbria record](https://researchportal.northumbria.ac.uk/en/publications/sample-size-considerations-for-the-external-validation-of-a-multi/)
- Riley et al. 2021 (Stat Med 40:4230–4251) give a calculation-based minimum sample size for external validation of binary-outcome models, targeting precision of the O/E ratio, calibration slope and C-statistic [K] — [doi:10.1002/sim.9025](https://doi.org/10.1002/sim.9025)
- DeLong, DeLong & Clarke-Pearson 1988 (Biometrics 44:837–845) give a nonparametric comparison of correlated AUCs on the same cases [K] — [doi:10.2307/2531595](https://doi.org/10.2307/2531595). A fast algorithm is Sun & Xu 2014 (IEEE SPL 21:1389–1393) [K] — [doi:10.1109/LSP.2014.2337313](https://doi.org/10.1109/LSP.2014.2337313)
- Obuchowski 1997 (Biometrics 53:567–578) extends DeLong's structural-components approach to **clustered** ROC data, using design-effect and effective-sample-size ideas, without specifying the within-cluster correlation. Wu 2020 argues the estimator is not efficient. Cleveland Clinic provides R code [V] — [doi:10.2307/2533958](https://doi.org/10.2307/2533958); [clusteredROC help](https://www.lerner.ccf.org/quantitative-health/documents/clusteredROC_help.pdf)
- Hanley & McNeil 1982 (Radiology 143:29–36) give an approximate standard error of the AUC as a function of the numbers of positives and negatives [K] — [doi:10.1148/radiology.143.1.7063747](https://doi.org/10.1148/radiology.143.1.7063747)
- Diebold & Mariano 1995 (JBES 13:253–263) give a test of equal predictive accuracy on loss differentials [K] — [doi:10.1080/07350015.1995.10524599](https://doi.org/10.1080/07350015.1995.10524599)
  - Diebold 2015 (JBES 33(1)) says the DM test was meant for comparing *forecasts*, not *models*, and that simpler full-sample procedures exist for model comparison [V] — [doi:10.1080/07350015.2014.983236](https://doi.org/10.1080/07350015.2014.983236); [NBER w18391](https://nber.org/papers/w18391)
  - Harvey, Leybourne & Newbold 1997 (IJF 13(2):281–291) give the small-sample modified DM statistic, because DM over-rejects in small samples [V] — [IDEAS/RePEc listing](https://ideas.repec.org/p/yor/yorken/15-15.html); [doi:10.1016/S0169-2070(96)00719-4](https://doi.org/10.1016/S0169-2070(96)00719-4) [K for DOI]
- Field & Welsh 2007 (JRSS-B 69:369–390), "Bootstrapping clustered data": resample at the cluster level to keep within-cluster dependence [K] — [doi:10.1111/j.1467-9868.2007.00593.x](https://doi.org/10.1111/j.1467-9868.2007.00593.x)
- The JWGFVR site says BSS is "unstable on small samples, and rarer events need more samples" [V] — [JWGFVR](https://jwgfvr.github.io/forecastverification)
- Computed this session (Hanley–McNeil approximation, 40,172 rows):

  | AUC | positives | SE | approx. 95% CI half-width |
  |---|---|---|---|
  | 0.90 | 18 (all flood positives, assumed independent) | 0.049 | ±0.095 |
  | 0.90 | 5 (one per storm day, i.e. effective clusters) | 0.092 | ±0.18 |
  | 0.96 | 5 | 0.061 | ±0.12 |
  | 0.75 | 8 (landslides) | 0.100 | ±0.20 |

  These are illustrative only: Hanley–McNeil assumes independence, so the clustered truth is wider still. Source formula: Hanley & McNeil 1982 (above).
- Computed this session: for a paired sign test where the new model beats the baseline on *every* event day, the minimum two-sided p is 0.0625 with 5 days, 0.0078 with 8 days, and 0.002 with 10 days. One-sided: 0.031 with 5 days, 0.0039 with 8 days.

### Inferences
- **Recommended baselines:**
  1. *Climatology*: constant prevalence from training years.
  2. *Per-barangay historical rate* from training years only, with shrinkage, e.g. (events + α·city rate)/(days + α), because most barangays have 0 events.
  3. *Rainfall-threshold rule*: either a fixed, untuned rule from PAGASA's 24-h advisory bands (≥50, ≥100, ≥200 mm/24 h), which carries no tuning leakage, or a threshold tuned on training years only. For landslides, the intensity-duration threshold literature applies, e.g. Guzzetti et al. 2008, Landslides 5:3–17 [K] — [doi:10.1007/s10346-007-0112-1](https://doi.org/10.1007/s10346-007-0112-1).
  4. *Persistence*: event yesterday → high today. It matters for multi-day typhoons.
  5. *Rain-only logistic regression* (1–2 features). This is the strongest "simple" challenger. Kapoor & Narayanan found that leak-free ML often does not beat simple logistic regression.
- **Comparison protocol** (pre-register it in the report before running):
  - (a) Paired difference in log score and Brier between new and current model on the *same* test rows.
  - (b) A 95% interval for each difference from a **cluster bootstrap** that resamples event clusters (event day ± buffer) and non-event blocks (weeks or months) separately, with all 22 barangays of a day kept together.
  - (c) A per-event-day table of wins and losses (sign test) as a transparent second view.
  - (d) DeLong/Obuchowski for AUC only as a secondary measure.
  - With 5 clusters the bootstrap distribution has very few distinct resamples, so percentile intervals are crude. Say so rather than reporting false precision.
- **Decision rule suggestion.** Promote a new model only if:
  - the cluster-bootstrap interval for the log-score difference excludes zero in its favour; **or**
  - it is no worse than the current model on every event day *and* better on the majority, with no increase in false alarms per hit at the High cut-off; **and**
  - it passes the leakage checklist (Q2) and the AOA check.
  Otherwise report "not yet distinguishable; the current model is kept".
- **Wording for "not yet distinguishable".** For example: "On the 5 flood event days available (2021–2025), the new model gave higher probability on 4/5 days. This difference is not statistically distinguishable (sign test p = 0.38 two-sided; the minimum achievable p with 5 days is 0.06). The bootstrap interval for the log-score difference spans zero. We will re-assess after the 2026 wet season."
- **When a difference becomes detectable.** At about 1 flood event-day per year, the 100-event guidance cannot be met in any realistic time. This is the strongest argument for (a) keeping models simple, with few parameters, (b) using prior physical knowledge such as rain thresholds, and (c) presenting outputs as relative risk levels, not precise probabilities.
- **Fire (219 events).** Fire has enough events for conventional paired comparison of monthly Poisson log scores (DM with HLN correction, or a paired block bootstrap by month). This is where a "better model" claim can actually be supported.

### Gaps
- I found no published power analysis for comparing Brier or log scores with fewer than 10 event clusters. The sign-test minimum p-values above are exact arithmetic, not from a source.
- I found no open-source Python implementation of Obuchowski's clustered AUC with a verified licence. The reference code is R from Cleveland Clinic, and its licence was not checked. A clustered bootstrap of AUC is the practical substitute.

---

## Q5. Thresholds and risk classification (cost-based thresholds, decision curves, economic value, top-k, PAGASA alignment)

### Takeaway
A probability cut-off is an implicit statement of how many false alarms the DRRMO will accept per real event: the 15% cut-off accepts up to about 5.7 false alarms per hit, and 25% about 3. Cut-offs should be chosen from that cost/loss reasoning with the DRRMO, fixed *before* testing, and checked with decision curves or relative economic value curves. PAGASA's colours are rain-based official warnings: an hourly nowcast scale and a 24-hour advisory scale. GeoAlert's model levels should not reuse yellow/orange/red unless they are explicitly tied to PAGASA's bulletins, to avoid confusion with official warnings.

### Cited Findings
- Vickers & Elkin 2006 (Med Decis Making 26(6):565–574), decision curve analysis: net benefit = TP/n − (FP/n) × p_t/(1 − p_t), plotted against the threshold probability p_t. p_t is where the expected benefit of acting equals that of not acting [V] — [doi:10.1177/0272989X06295361](https://doi.org/10.1177/0272989X06295361); [PMC2577036](https://pmc.ncbi.nlm.nih.gov/articles/PMC2577036)
- Richardson 2000 (QJRMS 126:649–668), relative economic value in the cost-loss model: a *reliable* probabilistic forecast gives maximum value to a user when the probability threshold equals that user's cost/loss ratio C/L. This is the origin of potential economic value curves [V] — [doi:10.1002/qj.49712656313](https://doi.org/10.1002/qj.49712656313); [ECMWF predictability and economic value](https://www.ecmwf.int/sites/default/files/elibrary/2003/11922-predictability-and-economic-value.pdf)
- JWGFVR: the relative value score is a skill score of expected expense with climatology as reference, plotted against C/L [V] — [JWGFVR](https://jwgfvr.github.io/forecastverification)
- Van Calster et al. 2016: "moderate" calibration (risks match observed rates at each risk level) guarantees non-harmful decisions at any threshold. Poorly calibrated models can do harm in threshold-based decisions [V] — [repub.eur.nl/pub/87511](https://repub.eur.nl/pub/87511); [doi:10.1016/j.jclinepi.2015.12.005](https://doi.org/10.1016/j.jclinepi.2015.12.005)
- Python `dcurves` (decision curve analysis, MSKCC) 1.1.7 (2025-10-24), Apache-2.0 [V-lic] — [PyPI](https://pypi.org/project/dcurves/); [LICENSE](https://raw.githubusercontent.com/MSKCC-Epi-Bio/dcurves/HEAD/LICENSE)
- **PAGASA heavy rainfall warning**: observation/nowcast based, issued about every 3 hours, often down to municipality level. Yellow ("Be Alert") 7.5–15 mm/h; Orange ("Be Prepared") 15–30 mm/h; Red ("Take Action") > 30 mm/h [V] — [Varsitarian explainer, 2025-07-24](https://varsitarian.net/sci-tech/20250724/explainer-how-do-pagasas-rainfall-warnings-and-weather-advisories-work)
  - Cebu Daily News's explainer says Yellow means 7.5–15 mm "within one hour and this will continue in the next two hours". Orange: floods and landslides likely, evacuation may be needed. Red: triggers emergency measures such as preemptive and mandatory evacuation [V] — [Cebu Daily News explainer](https://cebudailynews.inquirer.net/546122/explainer-what-do-color-coded-rainfall-warnings-mean)
  - Older PAGASA material also cited 3-hour accumulations (45–65 mm for Orange, > 65 mm for Red), and the system dates to 2012 [V, secondary] — [GMA News](https://www.gmanetwork.com/news/topstories/nation/380006/yellow-orange-and-red-pagasa-s-bright-colors-mean-wet-and-dreary/story)
- **PAGASA weather advisory**: issued every 6 hours, forecasting 24-hour rainfall over provinces or regions. Yellow 50–100 mm, Orange 100–200 mm, Red > 200 mm [V] — [Varsitarian](https://varsitarian.net/sci-tech/20250724/explainer-how-do-pagasas-rainfall-warnings-and-weather-advisories-work)
- PAGASA's Weather and Flood Forecasting Center issues the alerts "through its Weather Division and Regional Services Divisions" [V] — [Varsitarian](https://varsitarian.net/sci-tech/20250724/explainer-how-do-pagasas-rainfall-warnings-and-weather-advisories-work). The NDRRMC is the emergency-alert *channel*, not the originator of the levels [V, secondary] — [Cebu Daily News](https://cebudailynews.inquirer.net/546122/explainer-what-do-color-coded-rainfall-warnings-mean)
- Local practice: a Yellow Heavy Rainfall Warning over Metro Cebu cities in July 2026 was followed by class and work suspensions [V, news] — [Manila Bulletin 2026-07-31](https://mb.com.ph/2026/07/31/classes-work-suspended-as-flood-swamps-metro-cebu). A search summary reported that Mandaue's DRRMO prepared for 50–200 mm of forecast rain, which shows LGUs act on the 24-h advisory scale. Which article this came from is uncertain; the likely source is [Proud Bisaya Bai, 2025-12-04](https://proudbisayabai.ph/story/2025/12/04/heavy-rains-to-soak-cebu-officials-urge-early-evacuation), not opened directly

### Inferences
- **Translate cut-offs for the DRRMO.** At break-even, p_t = C/L, and the accepted false alarms per hit = (1 − p_t)/p_t (computed). That gives about 5.7 at 15% and 3.0 at 25%.
  - Ask the DRRMO directly how many false "High" barangay-days they will act on per real flood. Set High from that answer and Moderate from a cheaper action, e.g. "monitor / check drainage".
  - This needs calibrated probabilities (Q6), otherwise the cut-offs do not mean what they say.
- **Fix thresholds before testing.** Choose cut-offs on training or inner-CV data, or from the DRRMO's cost/loss judgement. Then report net benefit across a range of p_t (e.g. 2–40%) on the outer test folds, against "treat all", "treat none" and the rain-threshold rule.
- **Top-k as a complementary output.** On a day the model or PAGASA flags as risky, rank barangays and show the top 3–5 "most likely affected". Score with hit-rate-in-top-k on event days. Ranking is more robust than absolute probability when calibration is uncertain.
- **Aligning with PAGASA.** GeoAlert's barangay-*day* model matches PAGASA's **24-hour advisory** scale (50/100/200 mm) more closely than the hourly warning. NASA POWER daily rain cannot reproduce hourly intensities.
  - Recommended display: keep GeoAlert's Low/Moderate/High labels and colours different from PAGASA's yellow/orange/red. Show the current official PAGASA status *alongside*, as "official warning", and let the official status override any model level in the UI text.
  - This avoids a model "High" being read as an official Red warning.
- **Fire.** Monthly fire levels are less time-critical, so a top-k "barangays to prioritise for inspection this month" view is more actionable than probability cut-offs.

### Gaps
- I could not fetch PAGASA's own official page for the current thresholds; the figures come from 2025 secondary explainers and Cebu news. Check them against pagasa.dost.gov.ph and PAGASA-Visayas PRSD before display.
- I found no NDRRMC or OCD Region VII document that sets mandatory LGU actions per warning colour. Talisay City DRRMO's own operations manual, if one exists, would be the authority.

---

## Q6. Probability calibration when positives are very few

### Takeaway
With 8–18 positives, only the weakest levels of calibration can be estimated: calibration-in-the-large (observed/expected) and, roughly, a calibration slope. Isotonic and binned calibration are not feasible. Use (1) a model that does not distort probabilities (no class re-weighting, or a prior/intercept correction if re-weighting is used), (2) at most a 1–2 parameter logistic recalibration fitted on out-of-fold predictions, and (3) published O/E with wide intervals.

### Cited Findings
- scikit-learn:
  - Platt/sigmoid calibration "is most effective for small sample sizes".
  - Isotonic "is more prone to overfitting, especially on small datasets" and only "perform[s] as well as or better than 'sigmoid' when there is enough data (greater than ~ 1000 samples)".
  - Sigmoid "can be a problem for highly imbalanced classification problems, where outputs do not have equal variance".
  - Isotonic introduces ties, which change AUC; sigmoid preserves ranking.
  - Calibrators must be fitted on data disjoint from the model's training data, e.g. via `CalibratedClassifierCV` or `FrozenEstimator` [V] — [scikit-learn calibration](https://scikit-learn.org/stable/modules/calibration.html)
- Van Calster et al. 2016 define four levels of calibration: mean (calibration-in-the-large), weak (intercept and slope), moderate (flexible calibration curve) and strong. A flexible calibration assessment in small validation sets is problematic [V] — [repub.eur.nl/pub/87511](https://repub.eur.nl/pub/87511); [doi:10.1016/j.jclinepi.2015.12.005](https://doi.org/10.1016/j.jclinepi.2015.12.005). Van Calster et al. 2019 (BMC Med 17:230), "Calibration: the Achilles heel of predictive analytics" [K] — [doi:10.1186/s12916-019-1466-7](https://doi.org/10.1186/s12916-019-1466-7)
- Niculescu-Mizil & Caruana 2005 (ICML) found that boosted trees push probabilities away from 0 and 1, that Platt scaling suits small calibration sets, and that isotonic needs more data [K] — [doi:10.1145/1102351.1102430](https://doi.org/10.1145/1102351.1102430)
- XGBoost docs: if you care only about AUC, "Balance the positive and negative weights via `scale_pos_weight`". If you "care about predicting the right probability … you cannot re-balance the dataset"; set `max_delta_step` to a finite value (say 1) to help convergence [V] — [XGBoost parameter tuning notes](https://xgboost.readthedocs.io/en/stable/tutorials/param_tuning.html)
- King & Zeng 2001 (Political Analysis 9(2):137–163): logistic regression can "sharply underestimate the probability of rare events". They propose a *prior correction* of the intercept using the population event fraction τ when the sample's event fraction differs (case-control or undersampling), and a weighting alternative; R Zelig `relogit` implements both [V] — [gking.harvard.edu](https://gking.harvard.edu/publication/logistic-regression-in-rare-events-data/); [Zelig relogit](https://iqss.github.io/Zelig/articles/zelig_relogit.html). Caveats from secondary sources: the correction can over-correct when n < 200, and Firth's penalised likelihood is suggested instead [V, secondary] — [Leitgöb presentation](https://www.europeansurveyresearch.org/conf/uploads/494/678/167/PresentationLeitg_b.pdf); [P. Johnson blog](https://pj.freefaculty.org/blog/?p=192)

### Inferences
- **Prior correction formula.** As I recall it from King & Zeng, re-check against the paper: β̂₀,corrected = β̂₀ − ln[((1−τ)/τ)·(ȳ/(1−ȳ))], where ȳ is the sample event fraction and τ the true fraction.
  - Applying this to the logit of an XGBoost or logistic output undoes undersampling or class weighting.
  - If `scale_pos_weight = w` was used, the effect is similar to oversampling positives w-fold, so the analogous offset is ln(w). This is an inference: verify on out-of-fold data.
- **Recalibration workflow.**
  1. Get out-of-fold predictions from the Q1 CV scheme.
  2. Fit logit(y) ~ a + b·logit(p̂) (two parameters), or only an intercept shift if positives are under 10.
  3. Report a (calibration-in-the-large) and b (slope; below 1 means over-confident) with cluster-bootstrap intervals.
  4. Apply the recalibration in serving as a stored, versioned transform.
  - Isotonic is ruled out because the binding constraint is the number of *positives*, not rows.
- **Under-recording.** If events are under-recorded, all calibrated probabilities are "probability of a *recorded* flood". State this on the map legend and in the model card. A prior correction toward an assumed true rate would be speculative without independent data.
- **Fire (Poisson).** Check O/E per barangay and per season, and a dispersion statistic (Pearson χ²/df). If it is overdispersed, a negative-binomial or quasi-Poisson model gives honest intervals; statsmodels is BSD-3 [V-lic] — [PyPI](https://pypi.org/project/statsmodels/).

### Gaps
- I did not verify the exact King & Zeng prior-correction formula text this session.
- No verified, licence-checked Python Firth logistic regression package was checked this session. statsmodels and scikit-learn do not provide Firth, as far as I know [K].

---

## Q7. Reporting standards (TRIPOD+AI, model cards)

### Takeaway
Write each model's accuracy report as a TRIPOD+AI-structured document plus a model card, generated from the training command's JSON. It should include intended use, data provenance and under-recording, the validation design, all baselines, event-level tables, calibration, and an explicit "limitations / not yet distinguishable" section.

### Cited Findings
- TRIPOD+AI (Collins et al., BMJ 2024;385:e078378, 16 April 2024; erratum BMJ 2024;385:q902) gives harmonised reporting guidance for prediction-model studies "irrespective of whether regression modelling or machine learning methods have been used". It has a 27-item checklist (52 sub-items), an expanded checklist and a 13-item abstract checklist, and it supersedes TRIPOD 2015 [V] — [doi:10.1136/bmj-2023-078378](https://doi.org/10.1136/bmj-2023-078378); [full-text PDF](https://epub.ub.uni-muenchen.de/116670/1/bmj-2023-078378.full.pdf); [Birmingham record](https://research.birmingham.ac.uk/en/publications/tripodai-statement-updated-guidance-for-reporting-clinical-predic/)
- Mitchell et al. 2019 (FAT* '19), "Model Cards for Model Reporting". Sections: model details, intended use, factors, metrics, evaluation data, training data, quantitative analyses, ethical considerations, caveats and recommendations [K] — [arXiv 1810.03993](https://arxiv.org/abs/1810.03993); [doi:10.1145/3287560.3287596](https://doi.org/10.1145/3287560.3287596)
- Kapoor & Narayanan 2023 propose "model info sheets" to document freedom from each leakage type [V] — [PMC10499856](https://pmc.ncbi.nlm.nih.gov/articles/PMC10499856)
- Meyer & Pebesma 2021 recommend publishing DI/AOA maps alongside predictions [V] — [doi:10.1111/2041-210X.13650](https://doi.org/10.1111/2041-210X.13650)

### Inferences
- TRIPOD+AI is clinical in wording, but its items map onto GeoAlert directly: source of data, outcome definition (what counts as a recorded flood), predictors and their timing, sample size (number of *events*), missing data, validation design, performance measures with CIs, calibration, and model updating.
- The model card should also state:
  - the product type (nowcast versus forecast);
  - the rain source and its latency;
  - the training window;
  - the number of event clusters;
  - the AOA rule;
  - the cost/loss rationale for the cut-offs;
  - the person who signed off.
- Generate the card from the same JSON report, e.g. a Markdown template rendered by the management command, so it never drifts from the numbers.

### Gaps
- No hazard-specific (flood/landslide) equivalent of TRIPOD+AI was found. Using TRIPOD+AI with a model card is an adaptation.

---

## Q8. Running training and prediction in Django (cron/management commands vs Celery, django-q2, APScheduler, Huey, Procrastinate, Django 6 Tasks), with licences

### Takeaway
For one daily flood/landslide prediction run, a monthly fire run, and occasional retraining on a modest CPU server, the lowest-maintenance option is **Django management commands triggered by the OS scheduler** (cron or a systemd timer on Linux, Task Scheduler on Windows). It needs no broker and no worker daemon. If on-demand jobs from the UI are needed, use a **PostgreSQL-backed** queue (Procrastinate, MIT; or django-q2 with the ORM broker, MIT; or the django-tasks database backend, BSD-3). Avoid Celery plus Redis: Celery is fine (BSD-3), but Redis ≥ 8 is tri-licensed and adds an ops dependency. Avoid APScheduler inside gunicorn workers, because jobs run more than once.

### Cited Findings
- Django 6.0 added a built-in Tasks framework (`django.tasks`, `@task`, `.enqueue()`). It "does not provide a worker mechanism to run Tasks"; the built-in `ImmediateBackend` and `DummyBackend` "are for development and testing only". Production needs a third-party backend with a worker and a durable queue. Arguments and results must be JSON-serialisable. Enqueue inside transactions with `transaction.on_commit()`. The page says nothing about periodic scheduling. For older Django, the `django-tasks` backport applies [V] — [Django 6.0 Tasks docs](https://docs.djangoproject.com/en/6.0/topics/tasks/)
- APScheduler FAQ: "Sharing a persistent job store among two or more processes will lead to incorrect scheduler behavior" (duplicate or missed runs), because there is no interprocess synchronisation. It recommends running the scheduler "in a dedicated process" [V] — [APScheduler 3.x FAQ](https://apscheduler.readthedocs.io/en/3.x/faq.html)
- django-q2 brokers: Redis (default), IronMQ, SQS, MongoDB, the **Django ORM**, or a custom broker. The ORM broker "should probably not be your first choice for a high traffic setup", but for "a medium message rate and scheduled tasks, this is the most convenient guaranteed delivery broker" [V] — [django-q2 brokers](https://django-q2.readthedocs.io/en/master/brokers.html)
- Procrastinate is a PostgreSQL-based task queue (PostgreSQL 13+) with Django integration. It has a `@periodic(cron=...)` decorator, a `max_delay` setting to avoid replaying missed runs after downtime, and a documented pattern for dynamic schedules stored in the DB [V] — [Procrastinate docs](https://procrastinate.readthedocs.io/); [API reference](https://procrastinate.readthedocs.io/en/main/reference.html)
- Huey has a Django integration (`huey.contrib.djhuey`), periodic tasks, and Redis or SQLite storage [K] — [Huey Django docs](https://huey.readthedocs.io/en/latest/django.html)
- Licences and versions [V-lic] (PyPI JSON plus LICENSE files, 2026-11-13):

  | Package | Version (date) | Licence | Source |
  |---|---|---|---|
  | celery | 5.7.0 (2026-11-05) | BSD-3-Clause | [PyPI](https://pypi.org/project/celery/), [LICENSE](https://raw.githubusercontent.com/celery/celery/HEAD/LICENSE) |
  | django-celery-beat | 2.9.0 | BSD | [PyPI](https://pypi.org/project/django-celery-beat/) |
  | django-q2 | 1.11.1 (2026-08-26) | MIT | [LICENSE](https://raw.githubusercontent.com/django-q2/django-q2/HEAD/LICENSE) |
  | APScheduler | 3.11.3 (2026-06-28) | MIT | [LICENSE.txt](https://raw.githubusercontent.com/agronholm/apscheduler/HEAD/LICENSE.txt) |
  | huey | 3.5.4 (2026-11-01) | MIT-style permission grant in LICENSE (PyPI licence field is empty) | [LICENSE](https://raw.githubusercontent.com/coleifer/huey/HEAD/LICENSE) |
  | procrastinate | 3.11.0 (2026-11-11) | MIT | [LICENSE.md](https://raw.githubusercontent.com/procrastinate-org/procrastinate/HEAD/LICENSE.md) |
  | django-tasks | 0.12.0 (2026-02-06) | BSD-3-Clause | [PyPI](https://pypi.org/project/django-tasks/) |
  | rq | 3.0.0 (2026-10-28) | BSD-2-Clause (needs Redis/Valkey) | [PyPI](https://pypi.org/project/rq/) |
  | dramatiq | 2.2.1 (2026-09-02) | LGPL-3.0+ (copyleft; usable, but not MIT/BSD/Apache) | [PyPI](https://pypi.org/project/dramatiq/) |
  | Django | 6.1.3 latest (2026-11-03) | BSD-3-Clause | [PyPI](https://pypi.org/project/Django/) |

- Broker server licences [V-lic]:
  - Redis's LICENSE.txt says that "Starting with Redis 8, Redis Open Source is moving to a tri-licensing model" [V] — [redis LICENSE.txt](https://raw.githubusercontent.com/redis/redis/HEAD/LICENSE.txt). The three licences are RSALv2, SSPLv1 and AGPLv3 [K].
  - Valkey (the Linux Foundation fork) is BSD-3-Clause [V] — [valkey COPYING](https://raw.githubusercontent.com/valkey-io/valkey/HEAD/COPYING).
  - The Python clients `redis` 8.1.0 and `valkey` 6.2.0 are MIT [V-lic].
- Django custom management commands are the documented way to add `manage.py` jobs [K] — [Django docs: custom management commands](https://docs.djangoproject.com/en/4.2/howto/custom-management-commands/)
- Django 4.2 LTS extended support ended in April 2026 [K, not re-fetched] — [Django supported versions](https://www.djangoproject.com/download/#supported-versions). GeoAlert pins Django==4.2.13 ([backend/requirements/base.txt](C:/Users/Sannichigetsu/Geoalert/backend/requirements/base.txt)).

### Inferences
- **Recommended setup**, simplest first:
  - `manage.py predict_hazards --date=YYYY-MM-DD` daily, e.g. 05:00 PHT after NASA POWER updates. It must be idempotent: upsert on (hazard, barangay, valid_date, model_version).
  - `manage.py predict_fire --month=YYYY-MM` monthly.
  - `manage.py train_hazard_models --candidate` writes a *candidate* version and report, and never promotes.
  - `manage.py promote_model <hazard> <version>` is a separate, human-run step (Q12).
  - Wrap each in a lock (e.g. `pg_try_advisory_lock`) so overlapping runs cannot double-write, and log start, end and row counts to a `job_run` table.
- **If a queue is later needed** (an admin "re-run prediction" button):
  - Choose Procrastinate or django-q2 with the ORM broker, so PostgreSQL remains the only stateful dependency.
  - Django 6.x plus a database Tasks backend is the most future-proof API, but it requires upgrading from 4.2, which is overdue for security anyway.
  - Celery is the most capable option, but it adds a broker and worker supervision that a small team does not need for 1–2 jobs a day.
- **APScheduler** is acceptable only as a single dedicated process (not inside gunicorn workers); at that point cron is simpler.
- **Supabase specifics.** The training job should connect directly or through a session-mode connection, not a transaction-mode pooler, if it holds advisory locks or long transactions. Procrastinate's LISTEN/NOTIFY also needs session semantics. This is an inference: see Gaps.

### Gaps
- Not verified: whether Procrastinate works through Supabase's transaction-mode pooler (LISTEN/NOTIFY and advisory locks), and whether the `django-tasks` database backend supports Django 4.2. Check each project's docs and compatibility matrix.
- I did not verify django-q2's Schedule/cron model features on its docs page (the brokers page mentions only "scheduled tasks").

---

## Q9. Model serialisation and security (pickle/joblib, skops, ONNX, XGBoost native format, version pinning)

### Takeaway
Never load pickles from anywhere but GeoAlert's own training job.
- Store the XGBoost flood/landslide models in **XGBoost's native JSON/UBJSON** format: stable across versions and not executable.
- Store scikit-learn objects (the Poisson fire model, scalers, the recalibration) with **skops** (MIT), or as plain JSON coefficients for linear/Poisson models.
- Optionally export to **ONNX** for a sandboxed, dependency-light runtime.
- Record and pin library versions per model, and verify a SHA-256 hash before loading.

### Cited Findings
- scikit-learn model persistence [V] — [scikit-learn model persistence](https://scikit-learn.org/stable/model_persistence.html):
  - pickle and joblib: "Loading can execute arbitrary code"; "You should never load a pickle file from an untrusted source".
  - skops.io is "More secure than `pickle` based formats", because loading "doesn't automatically allow arbitrary code execution". It works with `sio.get_untrusted_types()` and an explicit `trusted=` list.
  - ONNX is the "Most secure option", but "Not all scikit-learn models are supported" and the Python object is lost. Serve ONNX "in a sandboxed environment" because arbitrary computation can be expressed.
  - "There are no supported ways to load a model trained with a different version of scikit-learn". Serve with "the same **packages** and the same **versions**".
  - Save metadata: a training-data snapshot reference, the source code, library versions and the CV score.
- XGBoost Model IO [V] — [XGBoost: Introduction to Model IO](https://xgboost.readthedocs.io/en/stable/tutorials/saving_model.html):
  - UBJSON has been the default since 2.1.0; use `.json` or `.ubj`.
  - "We guarantee backward compatibility for models but not for memory snapshots" (pickles).
  - For long-term storage use `save_model`.
  - "The `pickle` Python module is NOT secure".
  - "Only load models from JSON files that were produced by XGBoost".
  - Custom objectives and callbacks are not saved.
- Licences [V-lic]:

  | Package | Version | Licence | Source |
  |---|---|---|---|
  | skops | 0.16.0 (2026-09-24) | MIT ("MIT License … Copyright (C) 2021 Hugging Face Inc.") | [LICENSE](https://raw.githubusercontent.com/skops-dev/skops/HEAD/LICENSE) |
  | onnx | 1.23.2 (2026-10-06) | Apache-2.0 | [LICENSE](https://raw.githubusercontent.com/onnx/onnx/HEAD/LICENSE) |
  | onnxruntime | 1.31.1 (2026-10-26) | MIT (Microsoft) | [LICENSE](https://raw.githubusercontent.com/microsoft/onnxruntime/HEAD/LICENSE) |
  | skl2onnx (sklearn-onnx) | 1.20.0 (2026-01-30) | Apache-2.0 | [LICENSE](https://raw.githubusercontent.com/onnx/sklearn-onnx/HEAD/LICENSE) |
  | onnxmltools (XGBoost → ONNX) | 1.16.0 (2026-01-30) | Apache-2.0 | [LICENSE](https://raw.githubusercontent.com/onnx/onnxmltools/HEAD/LICENSE) |
  | xgboost / xgboost-cpu | 3.4.1 latest (2026-08-15); GeoAlert pins 3.2.0 | Apache-2.0 | [LICENSE](https://raw.githubusercontent.com/dmlc/xgboost/HEAD/LICENSE) |
  | scikit-learn | 1.9.1 (2026-09-10), the version GeoAlert pins | BSD-3-Clause | [PyPI](https://pypi.org/project/scikit-learn/) |

- skops also has optional Hugging Face Hub helpers, which need an account. `skops.io` alone does not [K] — [skops docs](https://skops.readthedocs.io/)

### Inferences
- **Artifact layout.** One directory per version, e.g. `models/flood/2026-11-13_ab12cd/`, containing:
  - `model.ubj` (XGBoost) or `model.skops` / `coefs.json`;
  - `calibration.json` (a, b);
  - `features.json` (ordered feature names and windows);
  - `env.json` (Python, numpy, scikit-learn and xgboost versions);
  - `report.json` and `model_card.md`;
  - `sha256` hashes of each file, also stored in the DB registry row.
- **Before loading**, check the hash and refuse a library version mismatch, using scikit-learn's `InconsistentVersionWarning` raised as an error. This keeps models trained under one environment from silently misbehaving after a `pip install -U`.
- **Linear/Poisson GLMs.** For the fire model, if it is a GLM, store the coefficients as JSON and compute predictions with numpy. That is the most transparent and version-proof option; a DRRMO auditor can read the coefficients.
- **ONNX** is optional here. It reduces runtime dependencies (onnxruntime instead of xgboost plus scikit-learn) and is useful if prediction ever moves into a separate small service. The local file is still the trust boundary, so ONNX adds little when the same server trains and serves.

### Gaps
- skl2onnx's converter coverage for `PoissonRegressor` and `CalibratedClassifierCV` was not checked against the current supported-operators list.
- I did not confirm whether skops 0.16 can persist an XGBoost sklearn-wrapper object; use XGBoost's native format instead.

---

## Q10. Model versioning and experiment tracking without accounts (plain files + DB registry, MLflow, DVC), and disqualified tools

### Takeaway
For a 2–4 model, small-team system, a **database registry table plus versioned artifact folders** (Q9) covers versioning, lineage and champion/challenger with no new service. MLflow (Apache-2.0, self-hosted, no account) is a legitimate optional upgrade for comparing many experiment runs. It must stay local-only, because the tracking server has a recent record of unauthenticated RCE CVEs. DVC (Apache-2.0, now stewarded by lakeFS) is useful for snapshotting the input datasets (BFP sheet, NASA POWER pulls, event inventory). W&B, Neptune and Comet are disqualified, and so are WhyLabs' platform and alibi-detect (see Q13).

### Cited Findings
- MLflow 3.18.0 (2026-11-03): LICENSE.txt is "Copyright 2018 Databricks, Inc." with the Apache License 2.0 [V-lic] — [LICENSE.txt](https://raw.githubusercontent.com/mlflow/mlflow/HEAD/LICENSE.txt); [PyPI](https://pypi.org/project/mlflow/). `mlflow-skinny` 3.18.0 is the same licence [V-lic].
- MLflow model registry: "starting in MLflow 2.9, model registry stages would be marked as deprecated", in favour of aliases such as `@champion` and `@challenger`, with stage removal planned for a future major release [V] — [mlflow/mlflow#10336](https://github.com/mlflow/mlflow/issues/10336). Version detail on when aliases arrived (2.8 vs 2.9) is inconsistent across third-party guides [V].
- MLflow tracking-server security advisories [V]:
  - **CVE-2025-11201**: directory traversal to RCE in model creation, *no authentication required*. Affects versions before 3.0.0 and 3.1.0rc0. Published around October 2025 — [GitLab advisory](https://advisories.gitlab.com/pkg/pypi/mlflow/CVE-2025-11201/)
  - **CVE-2026-2033**: artifact-handler directory traversal RCE, unauthenticated, ZDI-26-105, February 2026 — [ZDI-26-105](https://zerodayinitiative.com/advisories/ZDI-26-105); [GitLab advisory](https://advisories.gitlab.com/pypi/mlflow/CVE-2026-2033/)
  - **CVE-2026-53995**: FileStore trace-ID traversal, reportedly ≤ 3.17.1. Single source only — [OpenCVE](https://app.opencve.io/cve/CVE-2026-53995)
  - Earlier traversal CVEs: CVE-2023-1177, CVE-2023-6018, CVE-2024-1483 — [ZeroPath summary](https://zeropath.com/blog/cve-2025-11201-mlflow-directory-traversal-rce)
- `mlflow.sklearn` saves with pickle or cloudpickle by default, so MLflow model artifacts carry the same trust rules as pickles [K] — [MLflow sklearn API](https://mlflow.org/docs/latest/python_api/mlflow.sklearn.html)
- DVC 3.67.1 (2026-03-31), Apache-2.0. The source URL is now `github.com/treeverse/dvc` [V-lic] — [LICENSE](https://raw.githubusercontent.com/treeverse/dvc/HEAD/LICENSE); [PyPI](https://pypi.org/project/dvc/). lakeFS (Treeverse) acquired the DVC open-source project from Iterative.ai, announced on 18 November 2025, and committed to keep DVC, DVCLive and the VS Code extension maintained [V] — [lakeFS blog](https://lakefs.io/blog/lakefs-acquires-dvc/); [DVC FAQ](https://dvc.org/blog/dvc-joins-lakefs-your-questions-answered/). DVC remotes can be local or SSH; DVC Studio, the hosted UI, is optional [K].
- **W&B**:
  - The SDK is MIT [V-lic] — [LICENSE](https://raw.githubusercontent.com/wandb/wandb/HEAD/LICENSE).
  - But "All Self-Managed deployments require a valid W&B Server license. Without a license, W&B Server can't start" [V] — [W&B self-managed requirements](https://docs.wandb.ai/platform/hosting/self-managed/requirements).
  - The free licence is generated from W&B's Deployer, which needs an account [V] — [wandb/local](https://github.com/wandb/local).
  - The $0 Personal tier is one seat, personal projects only, "corporate use is not allowed" [V] — [W&B privately hosted pricing](https://wandb.ai/site/pricing-privately-hosted/).
- **Neptune**: being acquired by OpenAI. The hosted app and API were shut down in early March 2026 (5 March 10:00 PST per the transition hub; 6 March 12:00 UTC per a later support article) and the data was deleted. The self-hosted Helm and container repositories were to be deleted on 8 March 2026 [V] — [Neptune transition hub](https://docs.neptune.ai/transition_hub); [support: service shutdown](https://support.neptune.ai/en/articles/13925165-service-shutdown-overview)
- **Comet**: `comet-ml` 3.58.12 SDK is MIT [V-lic] — [PyPI](https://pypi.org/project/comet-ml/). The platform needs a Comet account and API key [K]. Comet's Opik is Apache-2.0 but is an LLM-evaluation tool, not relevant here [V-lic] — [Opik LICENSE](https://raw.githubusercontent.com/comet-ml/opik/HEAD/LICENSE).

### Inferences
- **Registry table** `ml_model_version` (Django model), with these columns:
  - `id`; `hazard` (flood, landslide, fire); `version` (date plus git short hash, e.g. "2026-11-13_ab12cd"); `algorithm`
  - `artifact_path`, `artifact_sha256`, `feature_spec` (JSON), `env` (JSON)
  - `train_start` / `train_end`, `data_snapshot_ref` (DVC hash or backup file name)
  - `report` (JSONB: metrics, CIs, event tables), `model_card` (text)
  - `status`, constrained to candidate, shadow, champion or retired, with a **partial unique index allowing one champion per hazard**
  - `created_at`, `promoted_at`, `promoted_by` (FK to user), `promotion_note`
- This gives MLflow-style aliases (champion/challenger) with a database constraint and an audit trail, and no extra server.
- **If MLflow is adopted later**, use it only as a local experiment log: `mlflow ui` bound to 127.0.0.1 with a SQLite or PostgreSQL backend. Keep the *serving* path reading from GeoAlert's own registry. Never expose the MLflow server on the public network, given the CVE history.
- **DVC** fits the data side best: version `data/puroks`, the BFP fire sheet, the event inventory export and the NASA POWER cache, so every model row can point to the exact data snapshot. It adds Git-adjacent workflow overhead; plain dated backups plus SHA-256 in the registry is the minimal alternative.

### Gaps
- I did not check whether MLflow 3.18 changed the default sklearn serialisation (e.g. adding skops) or the default backend store (FileStore versus SQLite).
- I did not verify DVC's current release cadence under lakeFS beyond the 3.67.1 release (2026-03-31).

---

## Q11. Storing and serving predictions and versions in PostgreSQL/PostGIS (table design, spatial joins, GeoJSON to Leaflet, caching)

### Takeaway
Store every prediction as an immutable row keyed by (hazard, barangay, valid period, model_version). Join it to barangay geometry only at serving time. Serve a pre-simplified GeoJSON per (hazard, date) for the live champion, cached in GeoAlert's existing file cache. This makes the map fast and every past warning auditable, and it is a prerequisite for prospective verification and shadow mode.

### Cited Findings
- djangorestframework-gis is already in use. GeoAlert pins 1.0; the latest is 1.3.0 (2026-09-01). The PyPI classifier says "BSD License", while LICENSE contains an MIT-style permission grant ("Copyright (C) 2013-2014 Douglas Meehan … Permission is hereby granted, free of charge …"). Both are permissive, but the metadata conflicts [V-lic] — [PyPI](https://pypi.org/project/djangorestframework-gis/); [LICENSE](https://raw.githubusercontent.com/openwisp/django-rest-framework-gis/HEAD/LICENSE). It provides `GeoFeatureModelSerializer` for GeoJSON FeatureCollections [K] — [DRF-GIS README](https://github.com/openwisp/django-rest-framework-gis)
- PostGIS is GPL-2.0 [V-lic] — [COPYING](https://raw.githubusercontent.com/postgis/postgis/HEAD/COPYING). This is fine for use as a database server, and GeoAlert already uses it via Supabase. PostGIS geometry simplification functions (`ST_SimplifyPreserveTopology`) and `ST_AsGeoJSON` are standard [K] — [PostGIS reference](https://postgis.net/docs/reference.html)
- scikit-learn persistence guidance recommends keeping training-data references and versions with each model [V] — [scikit-learn model persistence](https://scikit-learn.org/stable/model_persistence.html)

### Inferences
- **Proposed tables:**
  - `hazard_prediction`:
    - Columns: `id` bigserial; `hazard` (enum); `barangay_id` (FK to the barangay table, which holds a MultiPolygon in SRID 4326); `period_start` (date, the valid day or month start); `period_type` (day or month); `model_version_id` (FK to `ml_model_version`); `probability` (or expected count for fire); `level`; `inputs` (JSONB snapshot of the features used, e.g. rain values and their source); `issued_at`; `aoa_inside` (bool).
    - `UNIQUE(hazard, barangay_id, period_start, model_version_id)`; index on `(hazard, period_start)`.
    - No geometry column: join to barangays at read time. 22 polygons is trivial.
  - `hazard_level_config`: (hazard, version, cutoffs, label text, rationale, approved_by). Cut-offs are versioned data, not constants in code.
  - `observed_event`: the existing history records, used to join predictions to outcomes for verification.
  - `job_run`: an audit of each prediction or training run.
- **Serving:**
  - The endpoint `/api/hazard-levels/?hazard=flood&date=YYYY-MM-DD` returns a FeatureCollection for the current champion only: barangay name and simplified geometry, probability, level, model version and "outside model experience" flag.
  - Precompute simplified geometries once, in a column or materialised view, rather than per request.
  - Cache key: (hazard, date, champion_version). Invalidate it when a prediction run completes or a model is promoted. GeoAlert already uses a file-based cache, which is enough at this scale.
- **Immutability.** Never overwrite a past prediction when a model is retrained; the new version writes its own rows. That enables "what did GeoAlert show on the morning of the flood?" audits, prospective scoring, and champion-versus-challenger comparison on identical days.
- **Fire.** Use the same table with `period_type = month` and the expected count in `probability` (or a separate `expected_count` column), with the level computed from count-based cut-offs.

### Gaps
- I did not check GeoAlert's current history and prediction schema in depth (research only). The design above should be reconciled with the existing `apps/history` models before any migration, using the project's review-migration discipline.

---

## Q12. Monitoring, drift, retraining cadence, human sign-off, shadow mode / champion-challenger

### Takeaway
With about one flood event-day a year, *performance* drift cannot be monitored statistically. Monitor what can be measured:
- data health: NASA POWER freshness, missing values, range checks;
- input drift: the rain distribution against training, and the share of days outside the AOA;
- output drift: the share of barangay-days at Moderate or High;
- cumulative observed-versus-expected events per season;
- an event-by-event review after every recorded flood, landslide, or monthly fire batch.

Retrain on a fixed schedule (after each wet season or yearly) or when new verified events arrive. Run the challenger in shadow mode, writing predictions without display, and promote only with recorded human sign-off. Evidently (Apache-2.0) is the only full drift toolkit that clearly passes the licence and maintenance bar; simple custom SQL checks may be enough.

### Cited Findings
- Evidently 0.7.23 (2026-09-11), Apache-2.0 [V-lic] — [LICENSE](https://raw.githubusercontent.com/evidentlyai/evidently/HEAD/LICENSE); [PyPI](https://pypi.org/project/evidently/)
  - The library can be used "by itself, without an account", and includes a lightweight self-hostable UI. Evidently Cloud, the hosted service, is optional [V] — [Evidently OSS vs Cloud](https://docs.evidentlyai.com/faq/oss_vs_cloud); [self-hosting](https://docs.evidentlyai.com/docs/setup/self-hosting)
  - Conflict: one official self-hosting page says Evidently Cloud "is no longer available as a SaaS product", while others still promote it [V] (same pages). This does not affect the OSS library.
- NannyML 0.13.1, last release 2025-07-12, Apache-2.0 [V-lic] — [LICENSE](https://raw.githubusercontent.com/NannyML/nannyml/HEAD/LICENSE); [PyPI](https://pypi.org/project/nannyml/). Soda acquired NannyML on 9 June 2025 [V] — [Soda blog](https://soda.io/blog/soda-acquires-nannyml). No later PyPI release was found as of 2026-11-13, so its maintenance status is uncertain.
- whylogs 1.6.4, last release 2024-12-03, Apache-2.0 [V-lic] — [LICENSE](https://raw.githubusercontent.com/whylabs/whylogs/HEAD/LICENSE). WhyLabs' founders joined Apple after an acquisition reported in 2025, and the hosted WhyLabs platform was discontinued. Its code was released as open source, but hosted deployments "may no longer be accessible" [V, partly secondary] — [GeekWire](https://www.geekwire.com/2025/founders-at-seattle-startup-whylabs-join-apple-following-under-the-radar-acquisition); [ZenML docs](https://docs.zenml.io/stacks/data-validators/whylogs)
- Frouros 0.9.0 (2024-10-05), BSD-3-Clause (CSIC), a drift-detection library [V-lic] — [LICENSE](https://raw.githubusercontent.com/IFCA-Advanced-Computing/frouros/HEAD/LICENSE)
- alibi-detect 0.13.0 (2025-12-11): **Business Source License 1.1** (Licensor: Seldon Technologies), with the PyPI classifier "Other/Proprietary License" [V-lic] — [LICENSE](https://raw.githubusercontent.com/SeldonIO/alibi-detect/HEAD/LICENSE); [PyPI](https://pypi.org/project/alibi-detect/)
- Deepchecks 0.19.1 (2024-12-15): AGPL-3.0-or-later [V-lic] — [PyPI](https://pypi.org/project/deepchecks/)
- MLflow aliases (champion/challenger) replace stages [V] — [mlflow/mlflow#10336](https://github.com/mlflow/mlflow/issues/10336)
- Production-ML practice:
  - Sculley et al. 2015 (NeurIPS), "Hidden Technical Debt in Machine Learning Systems": feedback loops, monitoring and configuration debt [K] — [NeurIPS paper](https://papers.nips.cc/paper/5656-hidden-technical-debt-in-machine-learning-systems)
  - Breck et al. 2017, "The ML Test Score" rubric, including monitoring tests [K] — [doi:10.1109/BigData.2017.8258038](https://doi.org/10.1109/BigData.2017.8258038)
  - Google, "Rules of Machine Learning" [K] — [developers.google.com](https://developers.google.com/machine-learning/guides/rules-of-ml)
- Meyer & Pebesma 2021: the AOA/DI flags predictions outside the training feature space [V] — [doi:10.1111/2041-210X.13650](https://doi.org/10.1111/2041-210X.13650)

### Inferences
- **Custom checks**, as SQL or Python in the daily command, written to `job_run` and shown on an admin page:
  1. *Freshness*: today's NASA POWER value exists, and its lag is under N days. Alert if not.
  2. *Range and missing*: rain is ≥ 0, below a physical maximum, and has no null barangays.
  3. *Input drift*: the monthly distribution of daily rain against the training-years distribution for the same month (KS test or PSI). This works because rain has 1,826 daily values, unlike events.
  4. *AOA share*: the % of barangay-days with DI above the threshold.
  5. *Output drift*: the % of barangay-days at Moderate+ and High per month, against the training-period expectation.
  6. *Observed vs expected*: the cumulative Σp̂ against the observed count per season, with an exact Poisson interval. Flag when the observed count falls outside it. This is the only realistic calibration-drift check for floods and landslides; for fire it can run monthly with real power.
  7. *Event review*: whenever a new event is recorded, automatically produce a one-row card showing what the champion and challenger said that day, the day before, and the level shown.
- **Evidently** (Apache-2.0) can generate monthly HTML drift reports from two DataFrames (reference = training features, current = last month) without an account. It is useful but optional. NannyML and whylogs carry maintenance risk; alibi-detect is disqualified (BSL); Deepchecks is AGPL.
- **Retraining cadence and triggers:**
  - (a) Scheduled: once a year after the wet season, roughly December to January in Cebu. This is an inference: confirm local seasonality.
  - (b) Event-driven: any new verified flood or landslide event-day. With so few events, each one materially changes the training set.
  - (c) Data or pipeline change: a new rain source, recomputed boundaries (purok/sitio changes), or a change to the event inventory.
  - Never retrain and promote automatically.
- **Shadow mode / champion-challenger:** the challenger writes rows to `hazard_prediction` with `status = shadow` and is not shown. At the end of the season, the comparison report (Q4 protocol) runs on identical days.
- **Promotion and rollback:** promotion is a management command or admin action. It requires a signed-off checklist (leakage checklist passed, report reviewed, model card updated, cut-offs approved) and records the user and note in `ml_model_version`. Rollback means re-pointing the champion to the previous version. Because predictions are immutable per version, the last good version's rows can be re-shown instantly.
- **Who signs off:** the DRRMO head, or a designated officer, as the domain owner, plus the developer. A model change alters public-facing risk levels, so it should be treated as an operational decision, not a code deploy.

### Gaps
- I found no published guidance on retraining frequency for barangay- or municipality-scale flood occurrence models; the cadence above is an inference.
- I did not test Evidently's current API for this data shape (daily rain features), and did not verify its dependency footprint on a CPU-only server.

---

## Q13. Licensing verification of every tool (qualified vs disqualified)

### Takeaway
Every recommended primary tool is MIT, BSD or Apache-2.0, and none needs an account, token or paid service:
- core: scikit-learn, XGBoost, statsmodels, SciPy;
- serialisation: skops, ONNX, onnxruntime, skl2onnx, onnxmltools;
- versioning: MLflow, DVC;
- jobs: Procrastinate, django-q2, Huey, APScheduler, Celery, django-tasks, Django;
- monitoring and verification: Evidently, scores, xskillscore, dcurves, Frouros;
- serving: DRF-GIS.

Disqualified: W&B (licence-gated server, no corporate use on the free tier), Neptune (service shut down), Comet platform (account/API key), the WhyLabs platform (discontinued), and alibi-detect (BSL 1.1, source-available). Flagged but not disqualified: Redis ≥ 8 (tri-licence including RSAL/SSPL; use Valkey, BSD-3), Deepchecks (AGPL-3.0), Dramatiq (LGPL-3.0), PostGIS (GPL-2.0, fine as a server), blockCV (GPL-3, R).

### Cited Findings
- **Qualified (primary recommendations)**, all [V-lic] from LICENSE files and/or PyPI JSON, 2026-11-13:

  | Tool | Licence | Latest version (date) | Account/token needed? | Notes |
  |---|---|---|---|---|
  | scikit-learn | BSD-3-Clause | 1.9.1 (2026-09-10) | No | [PyPI](https://pypi.org/project/scikit-learn/) |
  | xgboost / xgboost-cpu | Apache-2.0 | 3.4.1 (2026-08-15) | No | [LICENSE](https://raw.githubusercontent.com/dmlc/xgboost/HEAD/LICENSE) |
  | statsmodels | BSD-3-Clause | 0.15.0 (2026-08-27) | No | [PyPI](https://pypi.org/project/statsmodels/) |
  | scipy | BSD | 1.18.1 (2026-08-21) | No | [PyPI](https://pypi.org/project/scipy/) |
  | skops | MIT | 0.16.0 (2026-09-24) | No (Hub helpers optional) | [LICENSE](https://raw.githubusercontent.com/skops-dev/skops/HEAD/LICENSE) |
  | onnx | Apache-2.0 | 1.23.2 (2026-10-06) | No | [LICENSE](https://raw.githubusercontent.com/onnx/onnx/HEAD/LICENSE) |
  | onnxruntime | MIT | 1.31.1 (2026-10-26) | No | [LICENSE](https://raw.githubusercontent.com/microsoft/onnxruntime/HEAD/LICENSE) |
  | skl2onnx | Apache-2.0 | 1.20.0 (2026-01-30) | No | [LICENSE](https://raw.githubusercontent.com/onnx/sklearn-onnx/HEAD/LICENSE) |
  | onnxmltools | Apache-2.0 | 1.16.0 (2026-01-30) | No | [LICENSE](https://raw.githubusercontent.com/onnx/onnxmltools/HEAD/LICENSE) |
  | MLflow (+ mlflow-skinny) | Apache-2.0 | 3.18.0 (2026-11-03) | No (self-hosted) | Keep local-only; see CVEs in Q10. [LICENSE.txt](https://raw.githubusercontent.com/mlflow/mlflow/HEAD/LICENSE.txt) |
  | DVC | Apache-2.0 | 3.67.1 (2026-03-31) | No (DVC Studio optional) | Now treeverse/dvc (lakeFS). [LICENSE](https://raw.githubusercontent.com/treeverse/dvc/HEAD/LICENSE) |
  | Django | BSD-3-Clause | 6.1.3 (2026-11-03) | No | [PyPI](https://pypi.org/project/Django/) |
  | django-tasks | BSD-3-Clause | 0.12.0 (2026-02-06) | No | [LICENSE](https://raw.githubusercontent.com/RealOrangeOne/django-tasks/HEAD/LICENSE) |
  | procrastinate | MIT | 3.11.0 (2026-11-11) | No | [LICENSE.md](https://raw.githubusercontent.com/procrastinate-org/procrastinate/HEAD/LICENSE.md) |
  | django-q2 | MIT | 1.11.1 (2026-08-26) | No | [LICENSE](https://raw.githubusercontent.com/django-q2/django-q2/HEAD/LICENSE) |
  | huey | MIT text (PyPI field empty) | 3.5.4 (2026-11-01) | No | [LICENSE](https://raw.githubusercontent.com/coleifer/huey/HEAD/LICENSE) |
  | APScheduler | MIT | 3.11.3 (2026-06-28) | No | [LICENSE.txt](https://raw.githubusercontent.com/agronholm/apscheduler/HEAD/LICENSE.txt) |
  | celery | BSD-3-Clause | 5.7.0 (2026-11-05) | No (needs a broker) | [PyPI](https://pypi.org/project/celery/) |
  | django-celery-beat | BSD | 2.9.0 (2026-02-28) | No | [PyPI](https://pypi.org/project/django-celery-beat/) |
  | rq | BSD-2-Clause | 3.0.0 (2026-10-28) | No (needs Redis/Valkey) | [PyPI](https://pypi.org/project/rq/) |
  | Valkey (server) | BSD-3-Clause | n/a | No | [COPYING](https://raw.githubusercontent.com/valkey-io/valkey/HEAD/COPYING) |
  | evidently | Apache-2.0 | 0.7.23 (2026-09-11) | No (Cloud optional) | [LICENSE](https://raw.githubusercontent.com/evidentlyai/evidently/HEAD/LICENSE) |
  | frouros | BSD-3-Clause | 0.9.0 (2024-10-05) | No | Slower release cadence. [LICENSE](https://raw.githubusercontent.com/IFCA-Advanced-Computing/frouros/HEAD/LICENSE) |
  | scores | Apache-2.0 | 2.7.0 (2026-09-05) | No | [LICENSE](https://raw.githubusercontent.com/nci/scores/HEAD/LICENSE) |
  | xskillscore | Apache-2.0 | 0.0.29 (2026-02-18) | No | [LICENSE.txt](https://raw.githubusercontent.com/xarray-contrib/xskillscore/HEAD/LICENSE.txt) |
  | dcurves | Apache-2.0 | 1.1.7 (2025-10-24) | No | [LICENSE](https://raw.githubusercontent.com/MSKCC-Epi-Bio/dcurves/HEAD/LICENSE) |
  | djangorestframework-gis | MIT text in LICENSE; PyPI classifier says BSD (conflict, both permissive) | 1.3.0 (2026-09-01) | No | [LICENSE](https://raw.githubusercontent.com/openwisp/django-rest-framework-gis/HEAD/LICENSE) |

- **Usable with caveats** (not MIT/BSD/Apache, or maintenance risk) [V-lic]:
  - NannyML: Apache-2.0, but no release since 2025-07-12 after the Soda acquisition — [Soda](https://soda.io/blog/soda-acquires-nannyml)
  - whylogs: Apache-2.0, but no release since 2024-12-03, and the WhyLabs platform is discontinued — [ZenML note](https://docs.zenml.io/stacks/data-validators/whylogs)
  - Deepchecks: AGPL-3.0+ — [PyPI](https://pypi.org/project/deepchecks/)
  - Dramatiq: LGPL-3.0+ — [PyPI](https://pypi.org/project/dramatiq/)
  - Redis server ≥ 8: tri-licence — [LICENSE.txt](https://raw.githubusercontent.com/redis/redis/HEAD/LICENSE.txt)
  - PostGIS: GPL-2.0 — [COPYING](https://raw.githubusercontent.com/postgis/postgis/HEAD/COPYING)
  - blockCV (R): GPL-3 — [LICENSE.md](https://raw.githubusercontent.com/rvalavi/blockCV/HEAD/LICENSE.md)
  - properscoring: Apache, but stale since 2015
- **Disqualified:**
  - **Weights & Biases**. The SDK is MIT, but the server will not start without a W&B licence, which needs an account through the Deployer. The free Personal tier bans corporate use. The SaaS needs an account and API key [V] — [requirements](https://docs.wandb.ai/platform/hosting/self-managed/requirements); [wandb/local](https://github.com/wandb/local); [pricing](https://wandb.ai/site/pricing-privately-hosted/)
  - **Neptune.ai**. The SaaS was shut down in March 2026 after the OpenAI acquisition, data was deleted, and the self-hosted images were removed [V] — [transition hub](https://docs.neptune.ai/transition_hub); [shutdown overview](https://support.neptune.ai/en/articles/13925165-service-shutdown-overview)
  - **Comet (comet_ml platform)**. The SDK is MIT, but tracking needs a Comet account and API key [V-lic for the SDK; K for the account requirement] — [PyPI](https://pypi.org/project/comet-ml/)
  - **WhyLabs platform**. The hosted service was discontinued [V, secondary] — [GeekWire](https://www.geekwire.com/2025/founders-at-seattle-startup-whylabs-join-apple-following-under-the-radar-acquisition)
  - **alibi-detect**. Business Source License 1.1 (source-available, not open source; production use restricted under the licence's terms) [V-lic] — [LICENSE](https://raw.githubusercontent.com/SeldonIO/alibi-detect/HEAD/LICENSE)
  - **Evidently Cloud / NannyML Cloud / DVC Studio** (hosted tiers). These are only optional add-ons; the OSS libraries qualify without them [V for Evidently; K for the others].

### Inferences
- Recommended minimal stack, which adds no new licences beyond what GeoAlert already ships:
  - scikit-learn, XGBoost native JSON/UBJSON, skops (if a scikit-learn object must be stored), statsmodels/SciPy for tests;
  - Django management commands plus OS cron;
  - a DB registry table and a `hazard_prediction` table;
  - optionally Evidently for monthly drift HTML and dcurves for decision curves.
- Only skops, and optionally Evidently and dcurves, are new dependencies.
- GeoAlert pins Django 4.2.13 and djangorestframework-gis 1.0. Plan the upgrade to a supported Django (5.2 LTS or 6.x) before adding Django 6 Tasks. This is an inference: the Django support dates were not re-fetched.

### Gaps
- I did not read the full text of each LICENSE file; checks covered headers and the SPDX/PyPI fields. In particular I did not inspect NOTICE files or bundled third-party licences (e.g. onnxruntime ThirdPartyNotices).
- The CAST (R) licence was not found at standard paths.
- The GitHub API rate limit blocked repo-level checks, so I could not see archived status, last commit dates or open issues. Release dates come from PyPI.
- I did not verify Comet's account/API-key requirement from Comet's own docs this session.
