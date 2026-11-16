# Five storm days cap GeoAlert's hazard models

No model available today can be shown to beat GeoAlert's current flood and landslide models. The limit is the number of events, not the choice of algorithm. Flood has 18 positive barangay-days that collapse onto **5 storm days**. Landslide has **8 positive days, 7 of them in Manipis**. So the best upgrades are not new model families. They are leaner, better-structured versions of the current models. The first is a Firth-penalised logistic regression (a bias-reduced fit that stays stable when events are very few) with an intercept correction, or its Bayesian equivalent. It would be rebuilt in two parts: a city-level "is today a flood (or landslide) day?" model with two or three predictors, and a separate "which barangays" step taken from outside terrain and hazard layers instead of being fitted to a handful of records. For landslides, the biggest single gain is more events. The NASA Global Landslide Catalog lists **74 records on 51 dates within 20 km of Talisay (2007–2017)**, about six times GeoAlert's 8 event days, but it states no licence, so its use is conditional. For fire, 219 events are enough to test a model properly. The recommended upgrade is a partially pooled Poisson or negative-binomial model with an exposure offset; it should mainly bring stable per-barangay rates and honest intervals, not a much lower Brier score. Every recommended library is MIT, BSD-3 or Apache-2.0, runs on a CPU, and needs no account, key or outside inference service. Disqualified options include TabPFN 2.5-and-later weights, TimesFM 3.0, Moirai, TimeGPT, Google's Flood Forecasting API, GloFAS, running NASA LHASA v2, IMERG, GSMaP, MSWEP and FABDEM. Deep learning, foundation models, random forests and boosted trees have no evidence of working at this event count, and every relevant benchmark points the other way. The bar for proof is steep: with 5 storm days, a new flood model that wins on every one still cannot reach two-sided p < 0.05 on a sign test (the smallest possible p is 0.0625). The honest claim for flood and landslide is therefore "simpler, better structured and no worse", to be checked on new data from the 2026 wet season on.

*Evidence markers.* **[V]** means verified in this research round on the primary page, licence file, package metadata or primary paper. **[S]** means taken from a secondary source, a search summary or an abstract only. **[A]** means assumed, inferred or from prior knowledge, and not re-checked. Arithmetic done by the research team is labelled "own calculation". GeoAlert's own figures (row counts, event counts, scores) come from the project's model report of 2026-11-13 and were not re-derived. Licence readings are practical interpretations, not legal advice. This report gives recommendations only; nothing in it has been built or changed in GeoAlert's code or database.

## A. Best overall candidates: eight options, all of them small

The brief asks for a ranking by predictive potential, fit to the data, commercial licensing, local deployment and maintenance. One fact outweighs all five: **how many independent events each hazard has**. Modern sample-size rules for prediction models set how many parameters a dataset can support. They work from the outcome rate, the expected explained variation and a target amount of overfitting, not from a fixed "10 events per variable" rule ([pmsampsize manual](https://cran.r-project.org/web/packages/pmsampsize/refman/pmsampsize.html); [van Smeden et al. 2019](https://dspace.library.uu.nl/bitstream/1874/387109/1/vansmeden.pdf)). The research team's own calculation under those rules gives about **3 to 6 parameters for 18 flood events and 1.3 to 2.9 for 8 landslide events**. Even that assumes every positive row is independent. Flood positives are not: they sit on 5 storm days, so the real budget is smaller. GeoAlert's flood model uses 5 rain and 6 terrain features (11 or more parameters), and its landslide model uses 6 or more, so both are over budget.

The wider evidence agrees that extra flexibility does not buy accuracy at this scale. These studies come from clinical prediction, not hazards, so they carry over as sample-size findings, not as hazard benchmarks. A review of 71 studies found **no difference in discrimination between logistic regression and machine learning in comparisons at low risk of bias (logit-AUC difference 0.00, 95% CI −0.18 to 0.18)** ([Christodoulou et al. 2019](https://med.mahidol.ac.th/ceb/sites/default/files/public/pdf/Repository/1-s2.0-S0895435618310813-main.pdf)). Random forests, SVMs and neural networks needed more than ten times the events per variable of logistic regression, and they were still unstable above 200 ([van der Ploeg et al. 2014](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC4289553/)). In a published case study, once data leakage was removed, machine-learning models "no longer perform substantively better" than an old logistic regression ([Kapoor & Narayanan 2023](https://pmc.ncbi.nlm.nih.gov/articles/PMC10499856)). GeoAlert's own finding is exactly what this evidence predicts: random forest, XGBoost, LightGBM and an MLP did no better than its GLMs.

| Rank | Candidate | Hazards | Predictive potential with current data | Code licence | Offline, no account | Maintenance |
|---|---|---|---|---|---|---|
| 1 | Two-part "when × where" model: Firth-penalised logistic regression with FLIC intercept correction for "when"; outside layers for "where" | Flood, landslide | Highest realistic: fewer parameters, no tuning knob, stable when events and non-events separate perfectly; cannot be proven better on 5–8 event days | firthmodels MIT [V]; statsmodels BSD-3 [V]; scikit-learn BSD-3 [V] | Yes [A] | Low; firthmodels is a Beta package with one maintainer, and the method is simple enough to re-implement [V] |
| 2 | Bayesian logistic regression with weakly informative priors, a storm-day effect and a tightly shrunk barangay effect | Flood, landslide | Same point accuracy as rank 1; adds honest, wide uncertainty bands | PyMC Apache-2.0, nutpie MIT, ArviZ Apache-2.0, Bambi MIT [V] | Yes; the training machine needs a C compiler for PyMC's default backend [A] | Moderate: every refit needs convergence checks |
| 3 | Partially pooled Poisson or negative-binomial GLM with exposure offset and seasonal terms; BYM2 spatial effect only if residuals call for it | Fire | Small Brier gain at most; real gain in stable rates for low-count barangays and calibrated intervals | PyMC stack [V]; glum BSD-3 [V]; esda and libpysal BSD-3 [V] | Yes [A] | Low to moderate |
| 4 | Rainfall rules that need no event inventory: PAGASA 24-hour advisory bands for flood; for landslide, a 2-year return-period daily rule (Dynaslope style) and a 7-day 95th-percentile rule gated by terrain (LHASA v1 style) | Flood, landslide | The baseline every model must beat; robust fallback alert levels | Own NumPy code written from published descriptions; no third-party licence | Yes | Very low |
| 5 | More events and storm context: NASA Global Landslide Catalog days near Talisay; tropical-cyclone distance from IBTrACS; events mined from news and DRRMO logbooks | Landslide (catalogue), flood (IBTrACS) | Biggest single lever for landslide timing (about 51 extra event dates); the storm flag is a hypothesis for flood | Catalogue: licence not specified [V]; IBTrACS: open access, commercial use referred to WMO Resolution 40 [V] | Yes; neither download needs a login [V] | Low once extracted |
| 6 | Fixed "where" layers from physics and terrain: UP NOAH flood and landslide hazard maps, ASF height-above-nearest-drainage (HAND), Copernicus DEM derivatives made with WhiteboxTools | Flood, landslide | Replaces the fitted "where" that failed out of sample (flood leave-one-barangay-out AUC 0.36) with evidence that does not depend on 18 records | WhiteboxTools MIT [V]; NOAH ODbL [S]; HAND CC0 [V]; Copernicus DEM free licence [V] | Yes; whether NOAH's official Google Drive folder needs a sign-in is unconfirmed [A] | Low (static layers) |
| 7 | Monotone-constrained shallow gradient boosting or Explainable Boosting Machine, as an offline challenger only | Flood, landslide, fire | No evidence of gain; useful to show the GLM is not missing non-linear signal | scikit-learn BSD-3, LightGBM MIT, interpret-core MIT [V] | Yes [A] | Moderate; default early-stopping settings are unsafe here [V] |
| 8 | Zero-shot time-series foundation model (Chronos-2 or TimesFM 2.5, pinned Apache-2.0 checkpoint), as an offline fire benchmark | Fire only | Low; documented bias on series that are mostly zeros [S] | Apache-2.0 code and weights, not gated [V] | Yes after a one-time weights download [V] | High for the value (PyTorch, plus licence re-checks on every upgrade) |

Ranks 1 and 2 are the same model idea fitted two ways. Firth's correction adds a fixed penalty (the same as a Jeffreys prior). The penalty keeps coefficients finite even when events and non-events separate perfectly ([firthmodels README](https://github.com/jzluo/firthmodels)). It also cuts the small-sample bias that makes ordinary logistic regression overstate effects ([van Smeden et al. 2016](https://link.springer.com/article/10.1186/s12874-016-0267-3)). It ranks first because the penalty has no tuning knob. Riley and colleagues warn that ridge and lasso penalties "are more unreliable when needed most", because their strength has to be estimated from the same small data ([Riley et al. 2021](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC8026952/)).

Firth has one known trap at GeoAlert's event rate: it pulls the average predicted probability toward one half. It must therefore be paired with **FLIC**, which re-fits only the intercept so that average predicted risk equals the observed rate ([Puhr et al. 2017](https://arxiv.org/pdf/2101.07620)). firthmodels (MIT, version 0.8.2, works with scikit-learn) gives the Firth fit and profile-likelihood intervals, but it has no FLIC option. FLIC would be a short hand-written step using an offset fit in statsmodels. statsmodels itself has had an open request for Firth since 2017. The older firthlogist package is archived and requires Python below 3.11, so it cannot be installed in GeoAlert's Python 3.11.9 environment ([firthmodels on PyPI](https://pypi.org/project/firthmodels/); [statsmodels issue #3561](https://github.com/statsmodels/statsmodels/issues/3561); [firthlogist on PyPI](https://pypi.org/project/firthlogist/)).

The Bayesian version ranks second only because it costs more to run and check. It gives the same kind of fit, but its output is a full distribution, so the DRRMO can see that the flood model rests on about five independent storms. It is fast enough on a CPU. A Stan BYM2 model on 56 areas sampled in about 4.9 seconds, and a PyMC model on 1,921 areas took 31 seconds with the nutpie sampler against about 12 minutes with the default one ([Stan case study](https://mc-stan.org/learn-stan/case-studies/icar_stan.html); [PyMC example](https://www.pymc.io/projects/examples/en/latest/spatial/nyc_bym.html)).

Rank 3 is the fire counterpart. Only one quantified area-level fire comparison was found (3,392 US census tracts). There, a Bayesian hierarchical Poisson regression cut forecast error (RMSE) by 9% against the base model. A full spatial CAR model gave worse point forecasts but usable probability forecasts ([Buffington et al. 2021](https://doi.org/10.1016/j.compenvurbsys.2021.101633)) [S]. The pattern is that pooling helps a little, and spatial structure mainly buys honest uncertainty. That fits GeoAlert's own result: its neighbours term moved the Brier score from 0.1394 to 0.1380, with an interval that spans zero.

Rank 4 is the yardstick. A rule built from PAGASA's 24-hour advisory bands (yellow 50–100 mm, orange 100–200 mm, red above 200 mm) involves no tuning at all ([Varsitarian explainer](https://varsitarian.net/sci-tech/20250724/explainer-how-do-pagasas-rainfall-warnings-and-weather-advisories-work)) [S]. PHIVOLCS-Dynaslope's operational landslide threshold uses one-day rain at the two-year return level ([Dynaslope paper](https://www.researchgate.net/publication/394425059_Bias_Correction_of_Real-Time_GSMaP_Satellite-Retrieved_Rainfall_Data_in_the_Context_of_Landslide_Monitoring_and_Early_Warning)) [S]. If a fitted model cannot beat such rules on the same days, the rule is the safer alert.

Ranks 5 and 6 are what make ranks 1 and 2 worth doing. They add information that the 40,172 rows lack: more landslide days, storm context and physically modelled flood depths. The alternative is squeezing more out of the same 26 positives. Rank 5 sits below rank 4 only because the landslide catalogue states no licence. Ranks 7 and 8 are challengers that let the team show the simple model is not missing anything. Neither should reach production unless it beats the GLM under the validation plan in Section F.

## B. Flood prediction: separate the storm-day signal from the barangay signal

### Susceptibility, occurrence and forecasting answer different questions

**Flood susceptibility** asks *where* floods tend to happen. It is a static map built from a mapped flood inventory plus terrain factors. The most common methods are frequency ratio and logistic regression. The analytic hierarchy process (AHP, an expert-weighting method) is still used for regional work, and machine learning is spreading ([Kaya & Derin review record](https://avesis.ankara.edu.tr/yayin/881ff4b9-4515-4f6e-96c5-aa7e811135a2/parameters-and-methods-used-in-flood-susceptibility-mapping-a-review)) [S]. The nearest local example is a frequency-ratio map of Mandaue City built from eight factors, which reports AUC 0.902 ([Mandaue study](https://publish.mersin.edu.tr/index.php/igd/article/view/1220)) [S]. A random-forest typhoon-impact model on a grid over Cebu City reached an average AUC of only about 0.59 ([IGES](https://www.iges.or.jp/en/pub/neighbourhood-scale-typhoon-risk-mapping-using-machine-learning-and-sar-derived-impact-0)) [S]. Neither number can be compared with GeoAlert's: the inventories, mapping units and validation designs all differ.

**Flood occurrence** asks *whether* a flood is recorded on a given day, given the rain that fell. This is GeoAlert's problem. The standard tools are rainfall–impact thresholds and logistic models on recent rain, checked against impact records. The closest published analogue used fire-service call-outs to flooded properties in Attica as its impact record ([Papagiannaki et al. 2015](https://nhess.copernicus.org/articles/15/1859/2015/nhess-15-1859-2015.pdf)) [S]. A 2015 study proposed separate urban thresholds for **drainage overload** and **disastrous runoff** ([Jang 2015](https://doaj.org/article/9c5aa53dbb2f4b83a781c9d1a803027b)) [S], a split that matches Talisay's drainage floods versus river floods. Thresholds do not travel well. A 2026 review of rainfall thresholds was criticised by a referee for treating a 42-event, spatially unrepresentative set of flash floods as a global baseline ([NHESS discussion](https://nhess.copernicus.org/articles/26/5073/2026/nhess-26-5073-2026-discussion.html)) [S].

**Short-term flood forecasting** adds lead time. It needs forecast rain plus hydrological or hydraulic modelling, or a flash-flood guidance system. PAGASA takes part in the WMO Southeastern Asia-Oceania Flash Flood Guidance System ([WMO](https://community.wmo.int/ar/node/36128)) [S], but public access to its output could not be confirmed [A]. GeoAlert's barangay-day model runs on observed NASA POWER rain, so it is an occurrence model: it describes the current or past day, not the coming one. Any lead time would have to come from feeding it forecast rain. The obvious forecast input is PAGASA's own 24-hour advisory, not a forecast system GeoAlert builds.

### The 0.96 AUC measures storm days, not places

GeoAlert's flood model reports a pooled ROC-AUC of 0.96, a PR-AUC of 0.05 and a leave-one-barangay-out (LOBO) AUC of 0.36. ROC-AUC is the chance that a random flood row ranks above a random non-flood row. PR-AUC is the area under the precision–recall curve, and its no-skill value equals the event rate ([Saito & Rehmsmeier 2015](https://doi.org/10.1371/journal.pone.0118432)) [A].

The three numbers tell one story. The pooled AUC is high because tens of thousands of dry days are easy to rank below five storm days. The PR-AUC is about **110 times the no-skill level of 0.00045**: real ranking skill, but very imprecise. The LOBO score below 0.5 says the terrain part of the model does not carry over to a barangay it has not seen. Typhoon Tino alone supplied 10 of the 18 positives, so the fitted terrain coefficients mostly describe which barangays flooded on that one day.

The uncertainty is large even before the clustering of positives on storm days is counted. The research team's Hanley–McNeil calculation puts the standard error of an AUC of 0.96 with 5 effective positives at about 0.061, an approximate 95% interval of ±0.12 ([Hanley & McNeil 1982](https://doi.org/10.1148/radiology.143.1.7063747)). The rolling-origin yearly folds that chose logistic regression over random forest and XGBoost are the right design. But the early folds trained on a single flood day, and 2023 and 2024 recorded no floods, so those folds could not rank models with confidence.

### Recommended: a two-part flood model with outside "where" evidence

The defensible structure stops trying to learn "where" from 18 records.

The **"when" part** becomes a city-day model: one row per day, with the outcome "any flood recorded in Talisay". That gives 5 positives in about 1,826 days. It should have **at most two or three predictors**: a 3-day rain sum, a tropical-cyclone distance flag, and possibly a 1-day sum. It would be fitted by Firth with FLIC, or by a Bayesian logistic regression with a positive prior on the rain coefficients. An equally valid choice is a published threshold rule tied to PAGASA's 50/100/200 mm bands and checked on the 5 days. A rule like that is easier to defend to a DRRMO than a coefficient.

The **"where" part** becomes a fixed allocation. Each barangay (or sitio) gets a score from two shares: its area or buildings in UP NOAH's 25-year and 100-year flood-hazard classes 2–3 (0.5–1.5 m and over 1.5 m depth), and its ground with HAND (height above nearest drainage) below 2 m and 5 m ([NOAH mirror](https://huggingface.co/datasets/bettergovph/project-noah-hazard-maps); [ASF HAND](https://registry.opendata.aws/glo-30-hand/)). The 18 records would serve only as a check, not to fit weights: do recorded floods fall in high-scoring barangays more often than their area share predicts? At most one scaling constant would come from the records: on average 3.6 barangays flooded per flood day (own calculation, 18 ÷ 5) [A].

This mirrors the Philippine typhoon impact model that 510 built for the Red Cross. It is a two-stage design: first "is this a significant event?", then "where does the damage fall?". It uses maximum 6-hour and 24-hour rain, a roughly 3-day total, distance to the storm track and wind speed. Its earlier municipal version used NOAH hazard maps as local features. Trained on 39 typhoons over a 0.1° grid, it reached an F1 of about 0.65 for over-10% house damage, against 0.58 for the municipal model ([Kooshki Forooshani et al. 2024](https://nhess.copernicus.org/articles/24/309/2024/)) [V]. That model cannot be reused directly. It predicts house damage, not flooding. Its code is GPL-3.0 and archived, and its data pipeline needs 510 credentials ([510 repository](https://github.com/rodekruis/Typhoon-Impact-based-forecasting-model)) [V]. Its choice of features does carry over.

Within the "where" layer, river floods and drainage floods deserve separate channels. River floods along the Mananga (8 of GeoAlert's records) should respond to rain over the upstream catchment, combined with NOAH and HAND exposure along the river. A 2006 DENR-MGB assessment flagged seven Mananga barangays as flood-prone, and Tino affected about 5,000 families in ten of them ([Philstar 2006](https://philstar.com/cebu-news/2006/07/02/345125/denr-assesses-talisays-7-flood-prone-areas); [SunStar](https://www.sunstar.com.ph/cebu/riverside-living-worsened-tino-damage)) [S]. Drainage flooding in Tabunok (3 records) is driven by short, intense rain and built-up cover. With three records, it should be framed as "elevated when PAGASA's hourly warning is orange or red", not as a fitted model.

The case for this design over the current one comes from its structure, not from a measurement. It fits fewer parameters. It removes the "where" component that scored 0.36 out of sample. And it takes its spatial pattern from hazard modelling built on LiDAR and IfSAR elevation data, which does not depend on GeoAlert's records ([Space Climate Observatory: NOAH](https://www.spaceclimateobservatory.org/noah)) [S]. No published study was found that tests this split design against a pooled model on a city dataset with few events.

### Better rain and storm inputs are worth testing, not assuming

NASA POWER's single ~0.5° cell gives every barangay the same rain. **CHIRPS v3** is the only no-account upgrade found. It has 0.05° resolution (about 5.5 km) and covers 1981 to the present under CC BY 4.0 with a copyright waiver. It downloads over open HTTP, with preliminary data two days after each five-day period and final data in the third week of the next month ([CHC CHIRPS3](https://www.chc.ucsb.edu/data/chirps3)) [V].

Its catch is serious for a day-level model. Daily values are five-day totals split into days using ERA5 or IMERG timing, and the product's own readme states that "Daily CHIRPS is therefore not an independent daily product" ([CHIRPS v3 daily readme](https://data.chc.ucsb.edu/products/CHIRPS/v3.0/daily/readme.txt)) [V]. It should be tested on 3- to 5-day sums, not swapped in automatically, and its delay rules it out for same-day alerts. CHIRPS v2 production ends after December 2026 ([CHC CHIRPS](https://www.chc.ucsb.edu/data/chirps)) [V]. PERSIANN-CDR (0.25°, updated quarterly, "No constraints on data access or use" per NOAA's metadata) can serve as a training-only cross-check ([NCEI PERSIANN-CDR](https://www.ncei.noaa.gov/products/climate-data-records/precipitation-persiann)) [S].

**IBTrACS** storm tracks download without a login and are the source of 510's track-distance feature ([NCEI IBTrACS](https://www.ncei.noaa.gov/products/international-best-track-archive)) [V]. A flag for "storm centre within R km in the past 72 hours" is the most promising untested "when" predictor, because flood days cluster on storm days. It is still a hypothesis, to be tested with leave-one-event-day-out validation. IBTrACS also updates only about three times a week, so live use would need PAGASA or JTWC bulletins, whose terms were not checked. For scale, about 183 mm fell around Cebu City in the 24 hours before Kalmaegi (Tino) made landfall ([Business Recorder/AFP](https://www.brecorder.com/news/amp/40390882)) [S].

The first experiment is cheap: compare POWER, CHIRPS and PERSIANN on the 5 event days and on heavy-rain days without a recorded flood. If no source shows heavy rain on a recorded flood day such as 2025-08-18, that record is very local convection, a non-rain flood such as blocked drains, or wrongly dated. It should then go to the DRRMO for review.

Four data questions would change any flood model and should be settled first:

1. **Missing events.** A June 2021 headline reports floods affecting at least 1,000 families in Talisay ([Philstar 2021](https://www.philstar.com/the-freeman/cebu-news/2021/06/15/2105585/floods-affect-least-1-thousand-families-talisay)) [S]. If that date is not among GeoAlert's 5 event days, floods are being under-recorded.
2. **River names.** News places "Kinalumsan" overflows in Cebu City, while Talisay reports name the Candulawan River ([Inquirer 2022](https://newsinfo.inquirer.net/1641378/heavy-rains-trigger-floods-in-some-parts-of-metro-cebu)) [S]. River names in the records should be checked.
3. **River works.** DPWH plans to widen and dredge the Mananga in 2026 ([SunStar](https://www.sunstar.com.ph/cebu/dpwh-to-widen-mananga-river-to-stop-severe-flooding)) [S]. That will shift river-flood hazard, so any model fitted on 2021–2025 will drift.
4. **NOAH itself.** The site describes itself as beta ([NOAH](https://noah.up.edu.ph/know-your-hazards)) [S]. Its maps use about 30 years of PAGASA rainfall and are due for an update ([Philstar 2025](https://www.philstar.com/headlines/2025/12/26/2496800/project-noah-improve-hazard-maps)) [S]. Its ODbL licence was read only on secondary pages, and it was not confirmed that the official download folder opens without a Google sign-in. GeoAlert's project records also show that an "official hazard maps" display feature was cancelled on 2026-11-05. Using NOAH as a model input is a different use, but it touches the same decision and needs the project owner's approval.

### What will not improve flood prediction now

Physically based flood models are freely licensed. EPA SWMM is public domain, ANUGA is Apache-2.0, JRC LISFLOOD is EUPL-1.2 and LISFLOOD-FP is GPL-3.0 ([SWMM](https://github.com/USEPA/Stormwater-Management-Model); [ANUGA](https://github.com/anuga-community/anuga_core); [LISFLOOD](https://github.com/ec-jrc/lisflood-code); [LISFLOOD-FP](https://gmd.copernicus.org/articles/14/3577/2021/)). But Talisay has no stream gauges, no drainage inventory and only 5 event days, so none of them can be calibrated. An uncalibrated run would mostly repeat what NOAH already did with LiDAR. SWMM becomes worthwhile only if the city holds a drainage master plan for Tabunok.

Deep learning is further away still. LSTM rainfall-runoff models succeed on hundreds of gauged river basins with continuous discharge records, and their authors argue that one should "never train an LSTM on a single basin" ([Kratzert et al. 2024](https://hess.copernicus.org/articles/28/4187/2024/)) [V]. GeoAlert has no discharge data and one rain cell.

Google's Flood Forecasting API, GloFAS and NASA GFMS are disqualified on access grounds (Section D), although DRRMO staff can still view the Flood Hub web map for awareness. Presence-only spatial models such as MaxEnt treat "no record" as "unknown", which suits under-recorded data in principle; the Python package elapid is MIT-licensed. With 18 presences, though, they are as weak as the current fitted terrain terms ([elapid](https://github.com/earth-chris/elapid)) [V].

## C. Landslide prediction: borrow events from the region, let terrain decide "where"

### Susceptibility, occurrence and forecasting are separate problems

**Landslide susceptibility** is a static "where" map. A review of 565 studies found logistic regression, neural networks, map overlay, index methods and weights of evidence most common. It also found top-quality assessments rare and study sites concentrated in four countries ([Reichenbach et al. 2018](https://geomorphology.irpi.cnr.it/publications/repository/public/journals/2018/susceptibility_revision_esjr_manuscript.pdf)) [S]. When models were tested outside their training area with resampling that respects spatial structure, logistic regression with backward selection gave the lowest error and generalised best, while tree-based methods overfit ([Brenning 2005](https://nhess.copernicus.org/articles/5/853/2005/)) [V]. In a related comparison, ordinary (non-spatial) cross-validation overstated performance by up to 47% ([Schratz et al. 2019](https://econpapers.repec.org/RePEc:eee:ecomod:v:406:y:2019:i:c:p:109-120)) [S].

The two most relevant Philippine studies point the same way. Across three typhoon landslide inventories in Luzon, LASSO logistic models trained on one typhoon lost 6–10% when classifying another typhoon's landslides. A model pooling two typhoons lost only 1–3% ([Jones et al. 2023](https://nhess.copernicus.org/articles/23/1095/2023/)) [S]. A 2026 Cebu Province study compared frequency ratio with logistic regression on a 2009–2023 inventory built from news reports. Its article page (LR 0.9151, FR 0.8955) and a listing of the same paper (0.8817 and 0.8317) give conflicting AUCs, and it does not discuss Talisay ([ISPRS Annals](https://isprs-annals.copernicus.org/articles/X-5-W4-2025/377/2026/)) [V for the page; the figures conflict].

**Landslide occurrence** asks whether slides happen on a given day, given the rain so far. This is the rainfall-threshold family. **Short-term landslide forecasting** runs the same logic on forecast or near-real-time rain to gain lead time. MGB's Albay early-warning study, for example, used 12-hour forecast rain in its bulletins ([MGB](https://mgb.gov.ph/images/Research__Development/12_-_T06_ESTABLISHING_LANDSLIDE_EARLY_WARNING_SYSTEM_USING_RAINFALL.pdf)) [S].

### Eight events cannot carry a threshold, and borrowed thresholds fail

Reliable rainfall thresholds need many events. A resampling analysis cited in the literature put the minimum at about **175 landslide events to keep threshold uncertainty under 10%** ([Rossi et al. 2017 post-print](https://research.unipg.it/bitstream/11391/1406843/5/Rossi_et_al_2017_post_print.pdf)) [S]. Even a small undercount of landslides markedly weakens a threshold ([Gariano et al.](https://geomorphology.irpi.cnr.it/publications/repository/public/journals/2019/gariano-et-al-2019-howmuchdoestherainfalltemporalresolutionaffectrainfallthresholds.pdf)) [S]. The classic intensity–duration thresholds need hourly rain. CTRL-T, the tool that derives them automatically, works from a single hourly rain gauge, and its download page states no licence at all, so it is not cleared ([CTRL-T code page](https://geomorphology.irpi.cnr.it/tools/rainfall-events-and-landslides-thresholds/ctrl-t-algorithm/ctrl-code)) [V].

GeoAlert's logistic regression on 1-, 3-, 7- and 14-day rain sums is already a **probabilistic threshold over several durations**. That is the kind Berti et al. argued for: using both landslide and non-landslide days gives a probability for every rain combination ([Berti et al. 2012](https://cris.unibo.it/handle/11585/129156)) [S]. The method is sound; the eight events are the weakness.

Thresholds from elsewhere in the Philippines are no shortcut. In Itogon during Typhoon Mangkhut, satellite rain showed about 360 mm against 794 mm at the Baguio gauge. Many storms that triggered no slides exceeded Caine's global threshold, and a proposed 500 mm seasonal threshold was passed without any failures. The authors concluded that no reliable threshold can come from one event, and that thresholds must be derived from the same rain source used operationally ([Abancó et al. 2021](https://nhess.copernicus.org/articles/21/1531/2021/)) [V]. Benguet's 70 mm in 24 hours ([Javier & Kumar 2018](https://ideas.repec.org/a/spr/nathaz/v90y2018i2d10.1007_s11069-017-3081-2.html)) [S] should therefore not be imported. GeoAlert's thresholds must come from NASA POWER, or from whichever rain product it adopts.

GeoAlert's landslide scores need the same careful reading as its flood scores. A place AUC of 0.96 and a LOBO AUC of 0.90 rest on 8 events, 7 in Manipis. Only one fold holds a non-Manipis event (the single Camp IV slide), so the 0.90 is close to anecdotal. The research team's Hanley–McNeil estimate gives an AUC of 0.75 with 8 positives an interval of about ±0.20. All 22 barangays share one rain cell, so the rain terms carry no spatial information. The timing part is really a **city-wide "is today a landslide day?" model**, and the place part mostly encodes "Manipis and Camp IV versus the flat lowlands". Some of the Manipis concentration is probably about where slides get noticed: the Manipis road has been closed by slides again and again, and several catalogue entries name it ([Inquirer](https://newsinfo.inquirer.net/1510430/landslide-prompts-closure-of-upland-manipis-road-in-talisay/amp); [Philstar 2016](https://philstar.com/metro-cebu/2016/02/01/1548845/talisay-landslide-prone-areas-warned)) [S].

### The NASA catalogue adds about 51 event days near Talisay

The most useful Cebu-specific finding of this research is in the NASA Global Landslide Catalog (GLC). Its legacy CSV downloads without a login or terms box and holds 11,033 records from 1988 to September 2017. The research team's filter found **74 records on 51 distinct dates within 20 km of central Talisay between 2007 and 2017**. These include about **13 Talisay City records on 11 dates, 5 of them in Manipis** ([GLC CSV](https://data.nasa.gov/docs/legacy/Global_Landslide_Catalog_Export/Global_Landslide_Catalog_Export_rows.csv)) [V, own computation]. Most were triggered by downpours or continuous rain, and ten by tropical cyclones.

Location precision varies: 3 records are exact, 12 are within 1 km, 30 within 5 km, and the rest within 10–25 km. One "Talisay City" record (2012-09-05, Sitio Camp 5) is actually Talisay in Negros Occidental and must be excluded.

The catch is the licence. data.nasa.gov lists the export as **"License not specified"** and refers to terms and conditions for export ([data.nasa.gov GLC](https://data.nasa.gov/dataset/global-landslide-catalog-export)) [V]. NASA's general policy describes its Earth science data as usable "fully and without restrictions" ([Earthdata policy](https://www.earthdata.nasa.gov/data-and-information-policy)) [S], and the successor COOLR viewer requires ticking a terms box ([COOLR](https://gpm.nasa.gov/applications/landslides/coolr)) [S]. That makes the GLC **conditional**. Using it internally to train and validate, without republishing the records, is the lower-risk path; written confirmation from NASA would close the gap [A, not legal advice].

Its best first use is as an **out-of-period test of the current model** on 2007–2017 rain, which is the strongest honest check available. Records located only to within 5–25 km should inform timing only. They should never be used to place a slide in a barangay unless the text names the barangay.

### A city-wide trigger model times a terrain allocation

The recommended landslide structure follows "hazard = susceptibility × trigger", the framing NASA's LHASA uses operationally ([Kirschbaum & Stanley 2018](https://pmc.ncbi.nlm.nih.gov/articles/PMC6839699)) [S], kept small enough to estimate.

The **trigger part** is a logistic (or complementary log-log) model of "at least one landslide in Talisay and the neighbouring uplands on day t". It would use one or two POWER multi-day rain sums and be fitted on GeoAlert's 8 days plus GLC days whose place has been checked, with Firth or weakly informative Bayesian priors.

The **allocation part** shares that daily probability across barangays in proportion to exp(β × terrain). Steep-slope share is the main term, with at most one or two more cleared covariates:

- plan curvature, or the topographic wetness index (TWI, which marks where water collects), computed from the Copernicus DEM with WhiteboxTools (MIT);
- distance to OSM roads, which captures road cuts and also stands in for where slides get reported;
- ESA WorldCover tree cover ([WhiteboxTools licence](https://raw.githubusercontent.com/jblindsay/whitebox-tools/master/LICENSE.txt); [WorldCover](https://esa-worldcover.org/en/data-access)) [V].

These are the same kinds of factors the Philippine and Cebu studies used. If a Bayesian barangay effect is added, its prior must be tight and centred on the terrain prediction. That keeps 7 Manipis events from turning it into a "Manipis indicator". It also gives barangays with no recorded slides, such as Tapul and Jaclupan, honest wide intervals instead of near-zero estimates.

Two rules that need no event inventory should be tested on the same days. One is Dynaslope style: 1-day rain above the 2-year return level, or above half of it. The other is LHASA v1 style: 7-day rain above the local 95th percentile, in barangays with high terrain exposure. LHASA's own README encourages users to map local susceptibility and update the rain threshold ([nasa/LHASA](https://github.com/nasa/LHASA)) [V]. Rebuilding the v1 logic from its published description therefore needs neither the NOSA-licensed code nor IMERG. CHIRPS v3 belongs here as a sensitivity test on 3- to 14-day sums, kept only if it clearly improves out-of-period skill.

Official maps are reference checks, not training signal. MGB-7's 2012 assessment at 1:10,000 scale rated 77% of Talisay's barangays at high landslide or flood risk. It listed highly susceptible sitios in Camp 4, Manipis and Tapul ([Philstar 2012](https://www.philstar.com/cebu-news/2012/09/10/847422/talisays-landslide-and-flood-prone-areas-identified)) [S]. But the maps are 150-dpi JPEGs. Under Section 176 of the Philippine Intellectual Property Code, using a government work "for profit" needs the agency's prior approval ([NDV Law](https://ndvlaw.com/does-copyright-subsist-in-works-of-the-government/)) [S]. NASA's 1 km global susceptibility map downloads without a login ([GeoTIFF](https://gpm.nasa.gov/sites/default/files/downloads/global-landslide-susceptibility-map-2-27-23.tif)) [V]. NOAH's shallow-landslide layer was built with the SINMAP slope-stability model ([NOAH mirror](https://huggingface.co/datasets/bettergovph/project-noah-hazard-maps)) [S], though it was not confirmed to cover Cebu. Disagreement between these maps and GeoAlert's ranking is a flag to investigate, not a fact to train on.

### Physical models, LHASA and deep learning are references, not engines

By licence, the cleanest physically based options are USGS TRIGRS (public domain), Landlab's LandslideProbability component (MIT) and GRASS r.shalstab (GPL-2-or-later) ([TRIGRS licence](https://code.usgs.gov/usgs/landslides-trigrs/-/raw/master/LICENSE.md); [Landlab licence](https://raw.githubusercontent.com/landlab/landlab/master/LICENSE.md); [r.shalstab](https://raw.githubusercontent.com/OSGeo/grass-addons/grass8/src/raster/r.shalstab/r.shalstab.py)) [V]. All of them need soil depth, hydraulic conductivity, cohesion and friction angle, and none of these exist for Talisay. SoilGrids 2.0 (CC BY 4.0) supplies soil texture and bulk density at 250 m, not geotechnical strength ([SoilGrids](https://docs.isric.org/globaldata/soilgrids/)) [V]. Every parameter would be guessed, then tuned on 8 events. Landlab's Monte Carlo design makes it the best fit if the team wants a static "chance of failure in wet conditions" layer. TRIGRS is the only one built for rain-driven forecasting, but it needs rain at finer than daily steps.

NASA's LHASA v2 is an XGBoost model. Its authors report it is twice as likely as v1 to catch historical landslides at the same false-alarm rate ([Stanley et al. 2021](https://ntrs.nasa.gov/api/citations/20210015014/downloads/Stanley_et_al_Frontiers_2021.pdf)) [S]. But running it requires an Earthdata login and PPS registration for IMERG. Its README also states that the released code "does not enable the user to retrain the model on new datasets or domains" ([nasa/LHASA](https://github.com/nasa/LHASA)) [V]. Its published nowcasts download without a login from a best-effort server with "frequent server downtime" ([NCCS datashare](https://portal.nccs.nasa.gov/datashare/landslides/)) [V], which makes them a validation comparison at most.

Deep learning has the same problem as for flood. The landslide deep-learning study with the most data had 2,472 landslide-triggering events among 780,766 rain events across Italy, and it found its network only "slightly" better than SVMs ([Mondini et al. 2023](https://www.nature.com/articles/s41467-023-38135-y)) [V]. That is roughly 300 times GeoAlert's event count. Finally, the 2018 Naga City disaster was a rockslide-debris avalanche next to a quarry, not a shallow rain-triggered slide, so it is not a template for Talisay's model ([Lagmay et al. 2020](https://www.frontiersin.org/articles/10.3389/feart.2020.00312)) [S].

## D. Comparative evaluation: restrictions sit in weights, data and services, not libraries

The tables below separate facts from judgment. Licence, account, API and deployment cells carry a marker. The "Expected advantages" and "Limitations" columns are the research team's judgments, drawn from the literature cited in Sections A–C and F. None has been measured on GeoAlert's data, except the CPU fit times, which come from a synthetic 40,172-row test in GeoAlert's Python environment.

Licences were read from each project's LICENSE file and/or PyPI, GitHub and Hugging Face metadata on 2026-11-13. A GitHub rate limit meant some checks relied on GitHub's own licence detection, and NOTICE files and bundled third-party licences were not inspected one by one. In the account and API columns, "No [A]" means a standard pip or conda install with no account step found. "No [V]" means the README was checked specifically because comparable tools do require an account.

| Model (implementation) | Hazard suitability | Expected advantages | Limitations | Commercial licence | Account required | API/token required | Local deployment |
|---|---|---|---|---|---|---|---|
| Plain logistic regression, current (scikit-learn, statsmodels) | Flood, landslide occurrence | Overall event rate matches the data by construction; readable odds ratios | Over the parameter budget (11+ flood terms on 18 events); breaks down when events separate perfectly; fitted "where" fails out of sample | BSD-3 [V] | No [A] | No [A] | Yes, CPU; fits in under 3 s on 40,172 rows [V, own synthetic timing] |
| Firth logistic + FLIC (firthmodels; FLIC via a statsmodels offset fit) | Flood, landslide occurrence | Finite estimates under perfect separation; less small-sample bias; no tuning; profile-likelihood intervals | Firth alone inflates rare-event probabilities, so FLIC must be hand-coded; Beta package with one maintainer | MIT [V]; statsmodels BSD-3 [V] | No [A] | No [A] | Yes, pure Python [V] |
| Ridge or lasso logistic with a fixed penalty (scikit-learn) | Flood, landslide | Shrinkage; trivial to deploy | Penalty strength cannot be tuned reliably on 5–18 events [S] | BSD-3 [V] | No [A] | No [A] | Yes [V] |
| Bayesian hierarchical logistic (PyMC + nutpie + ArviZ; Bambi) | Flood, landslide | Honest intervals; priors can encode "more rain never lowers risk"; separate storm-day and barangay effects | Priors dominate with 22 units; needs convergence checks; does not fix the LOBO 0.36 | Apache-2.0, MIT, Apache-2.0, MIT [V] | No [A] | No [A] | Yes; can serve from stored draws with NumPy only [A] |
| Partially pooled Poisson or negative binomial, optional BYM2 (PyMC; glum; statsmodels) | Fire | Stable rates for low-count barangays; exposure offset; calibrated intervals | Brier gain likely about 0.001; spatial effects can distort covariate effects [S] | Apache-2.0; glum BSD-3; statsmodels BSD-3 [V] | No [A] | No [A] | Yes [V] |
| Rainfall threshold rules (PAGASA 24-h bands; 2-year return level; 7-day 95th percentile) | Flood, landslide | No fitting, no leakage; easy to explain; matches official warning practice | Ignore terrain unless combined with a terrain filter; numbers do not transfer between sites [V] | Own code; methods unencumbered [A] | No | No | Yes |
| Generalised additive model (pyGAM; statsmodels GLMGam) | Fire seasonality; rain–risk curves | Smooth, plottable shape functions | Each smooth curve costs degrees of freedom the data lack; pyGAM 0.12 requires scipy below 1.17, conflicting with GeoAlert's 1.17.1 [V] | Apache-2.0; BSD-3 [V] | No [A] | No [A] | Yes [V] |
| Explainable Boosting Machine (interpret-core) | Challenger only | Readable per-feature shapes; monotone option | Default holds out 15% of rows for early stopping, about 2–3 flood positives [V]; no rare-event evidence | MIT [V] | No [A] | No [A] | Yes [A] |
| Monotone shallow gradient boosting (scikit-learn HGB; XGBoost; LightGBM) | Challenger only | Captures non-linearity under physical constraints | Needs far more data; automatic early stopping above 10,000 rows holds out about 2 positives [A]; reweighting classes distorts probabilities [V] | BSD-3; Apache-2.0; MIT [V] | No [A] | No [A] | Yes; XGBoost 3.4 needs Python 3.12+, and GeoAlert pins 3.2.0 [V] |
| Random forest, Extra Trees, SVM, MLP (scikit-learn, PyTorch) | Not recommended | None shown at this scale | Need more than 10× the events of LR; unstable even above 200 events per variable [S] | BSD-3; PyTorch BSD-style [V] | No [A] | No [A] | Yes |
| TabPFN with v2 weights (tabpfn) | Not recommended | Strong on small, balanced tables [S] | Biased toward the majority class under imbalance [S]; CPU cap of 1,000 rows by default; v2 weights require "Built with PriorLabs-TabPFN" on the product UI and docs; package defaults to non-commercial v3.5 weights | Code Apache-2.0 [V]; v2 weights Apache-2.0 plus attribution clause [V] | Unclear: README login flow covers only 2.5+ models; untested [A] | No for v2 [A] | Yes, with PyTorch |
| LSTM, TCN, Temporal Fusion Transformer, ConvLSTM, GNN (PyTorch, PyTorch Forecasting, Darts, neuralforecast, NeuralHydrology) | Not suitable | None at this data volume | Successful studies used hundreds of basins, 41 to about 130,000 dense series, or thousands of events; ConvLSTM and GNNs need gridded rain or gauge networks GeoAlert lacks [V] | BSD-style; MIT; Apache-2.0; Apache-2.0; BSD-3 [V] | No [A] | No [A] | Yes, CPU feasible [A] |
| Chronos-2, TimesFM 2.5 (pinned checkpoints) | Fire offline benchmark only | Zero-shot, no training | Quantile outputs cannot express 0.05% event probabilities; biased on series that are mostly zeros [S] | Apache-2.0 code and weights, ungated [V] | No [V] | No [V] | Yes after a one-time weights download [V] |
| Croston, SBA, TSB (statsforecast) | Fire baseline only | Simple per-series rates | No covariates; flat mean forecast [V] | Apache-2.0 [V] | No [A] | No [A] | Yes |
| Hawkes self-exciting process (tick) | Fire, not now | Models fires that follow recent fires nearby | No urban-fire evidence; few events per barangay; monthly data hides the days-to-weeks scale where such effects live [S] | BSD-3 [V] | No [A] | No [A] | Yes; Windows wheels exist [V] |
| GWR/MGWR (mgwr); kriging and Gaussian processes (PyKrige, GPyTorch) | Not suitable at 22 units | Local or smooth spatial effects | MGWR handles only Gaussian outcomes; 22 centroids with repeated rows; spatial correlation barely estimable [V/S] | BSD-3; BSD-3; MIT [V] | No [A] | No [A] | Yes |
| MaxEnt presence-only (elapid) | Spatial check only | Treats "no record" as unknown | 18 presences are too few | MIT [V] | No [A] | No [A] | Yes |
| Physical slope stability (TRIGRS, Landlab, r.shalstab) | Landslide static layer only | Physically interpretable | No local geotechnical parameters | Public domain; MIT; GPL-2+ [V] | No [A] | No [A] | Yes, offline |
| Hydraulic models (ANUGA, SWMM, LISFLOOD-FP) | Flood "what-if" maps only | Design-storm scenarios | Cannot be calibrated without gauges or drain data | Apache-2.0 [V]; public domain [V, README]; GPL-3.0 [S] | No [A] | No [A] | Yes, offline |
| R-INLA, CARBayes, brms (R route) | Fire spatial models, trained offline | Mature spatial model families | Second runtime to maintain; INLA's program includes GPL-3 GSL code; CARBayes and brms are GPL | INLA R package MIT since 25.06.07 [V]; others GPL [V] | No [V for the INLA download] | No | Yes, offline training only |
| Conformal and Venn-Abers tools (crepes, MAPIE, venn-abers) | Uncertainty communication only | Coverage guarantees without distribution assumptions | Per-class conformal needs at least 9 positives in a separate calibration set at 90% (19 at 95%) [own calculation] | BSD-3; BSD-3; MIT [V] | No [A] | No [A] | Yes |

The recommended models have no pretrained weights. The "training dataset" part of the licence check therefore reduces to the input data GeoAlert itself would use.

| Dataset | Role | Licence | Account or key | Verification and caveats |
|---|---|---|---|---|
| NASA POWER daily rain | Current rain input | CC BY 4.0 per the project's earlier check [A] | No [A] | Revision and delay policy not checked |
| CHIRPS v3 (0.05°) | Rain sensitivity test; training | CC BY 4.0 with waiver [V] | No; open HTTP [V] | Daily values are split from five-day totals [V]; v2 ends December 2026 [V] |
| PERSIANN-CDR (0.25°) | Training cross-check | "No constraints on data access or use" [S] | No [S] | Updated quarterly |
| IBTrACS | Storm distance for training | WMO full and open access; commercial use referred to WMO Resolution 40, no named licence [V] | No; optional usage form [V] | Not real-time (about three updates a week) [V] |
| UP NOAH flood and landslide hazard maps | Fixed "where" layer; reference | ODbL [S] | Whether the official Google Drive folder needs a sign-in is unconfirmed [A]; a third-party Hugging Face mirror exists | Licence not read on noah.up.edu.ph; beta disclaimer [S]; share-alike on derived databases |
| Copernicus DEM GLO-30 | Terrain | Free for any person or organisation, with attribution notices [V] | No via AWS [V]; the Copernicus Data Space route needs an account | The older AWS bucket readme links a more restrictive licence [S] |
| ASF GLO-30 HAND | Flood exposure | CC0 1.0 [V] | No [V] | Built from GLO-30 (2021) |
| ESA WorldCover 10 m | Land cover | CC BY 4.0 [V] | No [V]; the InputQuality layer needs a login [V] | |
| GHSL built-up surface | Drainage-flood exposure | CC BY 4.0 [S] | No [S] | One catalogue lists it as CC0 (inconsistent) |
| OpenStreetMap | Roads, rivers, buildings, basemap | ODbL [V] | No | Share-alike if a derived database is published; attribution on maps |
| SoilGrids 2.0 | Physical-model inputs only | CC BY 4.0 [V] | No; anonymous WebDAV [V] | REST API paused [V] |
| NASA Global Landslide Catalog (legacy CSV) | Extra landslide days; out-of-period test | "License not specified" [V] | No login or terms box for the CSV [V] | Conditional; the COOLR viewer has a terms box [S] |
| NASA global landslide susceptibility map | Reference | NASA open-data policy [S] | No [V] | No explicit file licence [A] |
| MGB 1:10,000 geohazard maps | Reference only | Government work; use for profit needs prior approval (RA 8293 s.176) [S] | No | JPEG only; conditional |
| HydroRIVERS | River network (coarse) | Free, including commercial use [V] | No [V] | At about 500 m it misses small creeks [A] |

Anything that needs an account, a token, a paid API or a non-commercial licence is listed separately.

| Disqualified alternative | What it would have offered | Why it fails the rules | Evidence |
|---|---|---|---|
| TabPFN 2.5, 2.6, 3, 3.5 and 3.5-Fast weights (package default) | Tabular foundation model | Non-commercial licence that excludes production systems; login at Prior Labs plus a TABPFN_TOKEN for unattended use | [V] [README](https://github.com/PriorLabs/TabPFN); [3.5 licence](https://huggingface.co/Prior-Labs/tabpfn_3_5/blob/main/LICENSE) |
| tabpfn-client; TabPFN-TS default setup | Hosted TabPFN inference | Outside inference API with an account; TabPFN-TS defaults to the cloud client and v3.5 weights | [V] [PyPI](https://pypi.org/project/tabpfn-client/); [repo](https://github.com/PriorLabs/tabpfn-time-series) |
| Google TimesFM 3.0 | Time-series foundation model | TimesFM Non-Commercial License, covering weights and inference code | [V] [licence](https://huggingface.co/google/timesfm-3.0-pytorch/blob/main/LICENSE) |
| Salesforce Moirai 1.x, MoE, 2.0 | Time-series foundation model | Weights are CC BY-NC 4.0 | [V] [model card](https://huggingface.co/Salesforce/moirai-2.0-R-small) |
| IBM ttm-research-r2 | Time-series foundation model | Weights are CC BY-NC-SA 4.0 | [V] [model card](https://huggingface.co/ibm-research/ttm-research-r2) |
| Nixtla TimeGPT | Hosted forecasting | API key; cloud-only inference | [V] [README](https://github.com/Nixtla/nixtla) |
| Google Flood Forecasting API | River flood forecasts | Waitlist, Google Cloud project and API key | [V] [docs](https://developers.google.com/flood-forecasting) |
| GloFAS / CEMS-Floods | Global river forecasts | Registration with ECMWF on the Early Warning Data Store; some data restricted | [S] [licence page](https://ewds.climate.copernicus.eu/licences/cems-floods) |
| NASA GFMS | Global flood monitoring | No current open download found; archive behind an Earthdata login | [S] [data.gov record](https://catalog.data.gov/dataset/gpm-ground-validation-global-flood-monitoring-system-gfms-flood-maps-ifloods-v1-d9aca) |
| Running NASA LHASA v2 | Global landslide nowcast | Earthdata login and PPS registration; cannot be retrained | [V] [README](https://github.com/nasa/LHASA) |
| NASA IMERG, SMAP, GES DISC archives | Rain, soil moisture, LHASA archive | Earthdata or PPS accounts | [V] for IMERG via the LHASA README; [A] for SMAP and GES DISC |
| JAXA GSMaP | Satellite rain | Registration; advance notice to JAXA for commercial use | [S] [terms](https://sharaku.eorc.jaxa.jp/GSMaP/registration.html) |
| MSWEP | Merged rain | CC BY-NC 4.0; request form; commercial access only through a paid API | [V] [GloH2O](https://www.gloh2o.org/mswep/) |
| ERA5 via the Copernicus Climate Data Store | Reanalysis rain | Account required; anonymous ARCO-ERA5 access unconfirmed | [S] [ARCO-ERA5](https://github.com/google-research/arco-era5) |
| PAGASA station data for commercial use | Gauge rain | Free only for non-commercial research; fees and signed terms otherwise | [S] [CADS-07 terms](https://pubfiles.pagasa.dost.gov.ph/pagasaweb/files/climate/CADS-07-Rev-2-Terms-and-Conditions-of-Use-for-Climatological-Data-1.pdf) |
| PDIR-Now and PERSIANN-CCS (CHRS portal) | Near-real-time rain | "All rights reserved"; no licence stated | [V] [portal](https://chrsdata.eng.uci.edu/) |
| Open-Meteo | Weather API | Free tier is non-commercial; excluded by the project | Project rule [A] |
| FABDEM | Bare-earth DEM | CC BY-NC-SA; commercial licence only from Fathom | [S] [Fathom](https://www.fathom.global/insight/fabdem-download/) |
| MERIT Hydro | Hydrography | Registration form and emailed password | [V] [MERIT Hydro](https://global-hydrodynamics.github.io/MERIT_Hydro/) |
| 510 typhoon impact pipeline | Philippine impact model | Needs 510 credentials and expired SharePoint data; GPL-3.0 and archived | [V] [repo](https://github.com/rodekruis/Typhoon-Impact-based-forecasting-model) |
| SAOFFGS output | Flash-flood guidance | Apparently limited to national weather services | [A] |
| CTRL-T | Landslide threshold tool | No licence stated | [V] [code page](https://geomorphology.irpi.cnr.it/tools/rainfall-events-and-landslides-thresholds/ctrl-t-algorithm/ctrl-code) |
| Weights & Biases | Experiment tracking | Self-hosted server needs a licence obtained through an account; free tier bans corporate use | [V] [requirements](https://docs.wandb.ai/platform/hosting/self-managed/requirements) |
| Comet platform | Experiment tracking | Account and API key | [A] |
| Neptune.ai | Experiment tracking | Service shut down in March 2026 | [V] [transition hub](https://docs.neptune.ai/transition_hub) |
| alibi-detect | Drift detection | Business Source License 1.1 | [V] [licence](https://raw.githubusercontent.com/SeldonIO/alibi-detect/HEAD/LICENSE) |
| PARDISO solver for INLA | Faster INLA fits | Licence key; support removed in INLA 26.09.04 | [V] [INLA NEWS](https://test.r-universe.dev/INLA/NEWS) |
| Esri ArcGIS Pro MGWR | GWR | Paid ArcGIS licence | [A] |
| SoilGrids via Google Earth Engine | Soil data | Earth Engine account (the WebDAV route above needs none) | [A] |

Several items fall between cleared and disqualified, and each would need an explicit decision:

- **NASA GLC:** no stated licence.
- **UP NOAH maps:** ODbL, known only from secondary pages.
- **MGB maps:** prior approval needed for use for profit.
- **IBTrACS:** commercial use is referred to WMO Resolution 40, whose conditions were not read.
- **LHASA code:** the NASA Open Source Agreement 1.3 is royalty-free and allows commercial use, but it adds copyleft-like file obligations and is not one of the preferred licences [V].
- **TabPFN v2 weights:** Apache-2.0 plus a mandatory "Built with PriorLabs-TabPFN" display.

Copyleft tools can be run offline to produce numbers without placing GeoAlert's own code under the GPL. These include GRASS (GPL-2+), LISFLOOD-FP (GPL-3), CARBayes and brms (GPL), and the INLA program, which includes GSL code (GPL-3). The FSF's FAQ says internal use is not distribution and that "the output of a program is not, in general, covered by the copyright on the code" ([GPL FAQ](https://www.gnu.org/licenses/gpl-faq.html)) [V]. Obligations would arise only if GeoAlert were shipped to an outside party with those programs inside. AGPL tools (glmmTMB, Deepchecks) should stay out of anything served over a network. Redis 8 and later has moved to a three-way licence that includes RSAL and SSPL ([Redis licence](https://raw.githubusercontent.com/redis/redis/HEAD/LICENSE.txt)) [V]. If a message broker is ever needed, Valkey is BSD-3 ([Valkey](https://raw.githubusercontent.com/valkey-io/valkey/HEAD/COPYING)) [V].

## E. Recommended architecture: three small models, scheduled commands and an immutable prediction table

The architecture has five rules:

- keep three separate models (flood, landslide, fire);
- train them offline in Django management commands;
- serve predictions from PostgreSQL using only NumPy arithmetic;
- never overwrite a stored prediction;
- promote a new model version only with human sign-off.

None of this needs a message broker, a cloud service or an account. The design is sized to GeoAlert's current stack, which per the project's requirements files is Python 3.11.9 with Django 4.2.13, Django REST Framework 3.15.1, djangorestframework-gis 1.0, scikit-learn 1.9.1, xgboost-cpu 3.2.0, scipy 1.17.1 and numpy 2.4.2, and no task queue.

| Stage | Flood model | Landslide model | Fire model |
|---|---|---|---|
| Prediction target | Chance of a recorded flood in barangay b on day t = chance day t is a city flood day × barangay b's allocation share | Chance of a recorded landslide in b on day t = chance day t is an upland landslide day × b's allocation share | Expected fires, and chance of at least one fire, in barangay b in month m |
| Training events | 18 barangay-days on 5 storm days, plus any DRRMO-verified additions | 8 days plus GLC days with checked places (about 51 dates within 20 km) | 219 fires since January 2023 |
| Fitted parameters | 2–3 (rain, storm flag, intercept) | 1–2 for timing, 1–3 for allocation | Intercept, 1–3 seasonal terms, pooled barangay effects |
| Fixed inputs | NOAH 25/100-year hazard share; share of ground with HAND below 2 m and 5 m; river or drainage channel | Steep-slope share; curvature or TWI; road distance | Exposure offset (buildings or population) |
| Method | Firth + FLIC, or Bayesian logistic | Firth + FLIC, or Bayesian logistic | Poisson or negative binomial with partial pooling |
| Baseline to beat | PAGASA 24-h bands; rain-only LR; shrunken per-barangay rate | 2-year return-level rule; 7-day 95th-percentile rule | Per-barangay average; current Poisson GLM |
| Run schedule | Daily, after the rain update | Daily, after the rain update | Monthly |
| Retraining trigger | After each wet season, any newly verified event day, or a data change | Same | Monthly or quarterly refit; yearly review |
| Stored artifact | Coefficients JSON (or posterior draws in .npz) plus calibration JSON | Same | Coefficients or draws plus dispersion |

### Preprocessing and features follow the event budget

Every training run should start with three steps. First, merge duplicate event records (same hazard, barangay and date window, from linked sources). Second, assign each event to an event cluster: the storm day plus a buffer. Third, record that "no record" means "not recorded", not "no flood". Every probability GeoAlert shows is a probability of a *recorded* event, and map legends should say so.

Rain features must use trailing windows that end on the prediction day for a same-day estimate, or forecast rain for a forecast. Centred windows, or windows that reach past the event, leak future information. Terrain and hazard-map features are computed once per barangay (and per sitio, where sitio outlines exist) from the Copernicus DEM, ASF HAND and NOAH. For the terrain calculations, WhiteboxTools (MIT) is preferred over pysheds (GPL-3) ([pysheds licence](https://raw.githubusercontent.com/mdbartos/pysheds/master/LICENSE)) [V].

The flood "where" score should be one composite built in advance, for example the share of buildings with HAND below 5 m or inside NOAH classes 2–3. It should not be six separately fitted terrain terms. For fire, the literature's most valuable addition is an exposure offset: households, buildings or population per barangay. No openly licensed barangay-level source for it was verified; OSM building counts (ODbL) are the fallback.

### Training, retraining and promotion stay under human control

Training runs as a management command that writes a *candidate* version and a report, never a live model. The candidate first runs in **shadow mode**: its predictions are stored but not shown. A separate, human-run promotion step then makes it the **champion**, the version users see.

Retraining happens in three cases: once a year after the wet season; whenever a new verified flood or landslide day arrives, since each one materially changes the training set; and whenever a data source, boundary set or event inventory changes. It never promotes a model automatically. Promotion should require a signed-off checklist (leakage checks passed, report reviewed, model card updated, cut-offs approved by the DRRMO) and be recorded with the approver's name. Rollback means pointing the champion back to the previous version. If Bayesian fits are used, a refit should be refused unless its convergence checks pass for every hyperparameter: R-hat below 1.01 and effective sample size above 400 [A].

### Prediction, calibration and risk levels are separate, versioned steps

A daily command (`predict_hazards`) and a monthly command (`predict_fire`) would run from the operating system's scheduler: cron or a systemd timer on Linux, Task Scheduler on Windows. Each run would be safe to repeat, because it inserts or replaces rows keyed by hazard, barangay, period and model version. Each would also take a PostgreSQL advisory lock so that overlapping runs cannot write twice.

**Calibration** relies on the model being calibrated by construction. A maximum-likelihood or Firth-plus-FLIC logistic regression reproduces the observed event rate on its training data. At most, an intercept shift (or an intercept and slope) fitted on out-of-fold predictions should be stored as a versioned adjustment. Two common fixes do not belong in the pipeline. Isotonic regression needs on the order of 1,000 samples and overfits small sets ([scikit-learn calibration guide](https://scikit-learn.org/stable/modules/calibration.html)) [V]. Reweighting classes or oversampling with SMOTE produces strongly overestimated probabilities without better discrimination ([van den Goorbergh et al. 2022](https://pmc.ncbi.nlm.nih.gov/articles/PMC9382395)) [S].

**Risk classification** turns probabilities into Low, Moderate and High. The cut-offs should be stored as versioned data with a rationale and an approver. A cut-off is a statement about how many false alarms are tolerable: at break-even, the false alarms accepted per real event equal (1 − p) ÷ p. GeoAlert's current 15% and 25% cut-offs therefore imply about **5.7 and 3.0 false-alarm barangay-days per real event** (own calculation from the cost–loss model of [Richardson 2000](https://doi.org/10.1002/qj.49712656313)). The DRRMO should set High from the false-alarm rate it is willing to act on, and Moderate from a cheaper action such as "monitor drainage".

The barangay-day model matches PAGASA's 24-hour advisory scale, not its hourly warnings. GeoAlert's levels should therefore keep their own labels and colours, show the official PAGASA status beside them, and let the official warning take precedence in the interface text. On flagged days, a ranking of the 3–5 most likely barangays is more robust than absolute probabilities while calibration is uncertain.

### Django, PostgreSQL/PostGIS and Leaflet integration

Because the recommended models are GLMs, the web process needs no machine-learning library at all. It reads coefficients, or a compact file of thinned posterior draws, from the registry and scores them with NumPy or even SQL.

Predictions would go into an immutable `hazard_prediction` table keyed by (hazard, barangay, period start, model version). Each row holds the probability or expected count, the level, a JSONB snapshot of the inputs actually used (rain value and source), the issue time and an "outside model experience" flag. The table needs no geometry column. The 22 barangay MultiPolygons are joined at read time, simplified once in advance with `ST_SimplifyPreserveTopology`, and served to Leaflet as GeoJSON through djangorestframework-gis's `GeoFeatureModelSerializer`. Responses can be cached per (hazard, date, champion version) in GeoAlert's existing file cache, and cleared when a run finishes or a model is promoted.

Immutability is the point. It lets anyone ask "what did GeoAlert show on the morning of the flood?", and it makes shadow comparison and scoring on new data possible.

Some licence and deployment notes for this layer:

- **OSM attribution.** Map views built on OSM need "© OpenStreetMap contributors, ODbL" ([OSM copyright](https://www.openstreetmap.org/copyright)) [V].
- **PostGIS.** It is GPL-2.0, which is fine for running a database server ([PostGIS COPYING](https://raw.githubusercontent.com/postgis/postgis/HEAD/COPYING)) [V].
- **djangorestframework-gis.** Its LICENSE file has MIT-style wording while PyPI says BSD; both are permissive ([DRF-GIS licence](https://raw.githubusercontent.com/openwisp/django-rest-framework-gis/HEAD/LICENSE)) [V].
- **Django version.** Extended support for Django 4.2 ended in April 2026 [A], so an upgrade to a supported release is due regardless of the models.
- **Job queue.** If an on-demand job queue is ever needed, a PostgreSQL-backed one such as Procrastinate (MIT) or django-q2 with its database broker (MIT) keeps PostgreSQL as the only service that stores state ([Procrastinate](https://procrastinate.readthedocs.io/); [django-q2 brokers](https://django-q2.readthedocs.io/en/master/brokers.html)) [V].
- **APScheduler.** It should not run inside Gunicorn workers. Its FAQ warns that sharing a job store between processes causes duplicate or missed runs ([APScheduler FAQ](https://apscheduler.readthedocs.io/en/3.x/faq.html)) [V].
- **Supabase.** Training jobs there should use a session-mode database connection if they hold advisory locks [A].

### Versioning and monitoring without a new service

An `ml_model_version` registry table gives champion/challenger versioning with an audit trail and no extra server. It would record:

- hazard, version (date plus git hash) and algorithm;
- artifact path and its SHA-256 hash;
- feature specification and environment (Python and library versions);
- training window and a reference to the data snapshot;
- the report (JSONB) and model card;
- status (candidate, shadow, champion or retired), with a partial unique index allowing one champion per hazard;
- who promoted it, and a promotion note.

Artifacts should be plain JSON for GLMs. If a scikit-learn object must be stored, skops (MIT) avoids pickle's risk of running arbitrary code on load. Any XGBoost challenger should use XGBoost's native JSON or UBJSON format ([scikit-learn persistence](https://scikit-learn.org/stable/model_persistence.html); [XGBoost model IO](https://xgboost.readthedocs.io/en/stable/tutorials/saving_model.html)) [V]. MLflow (Apache-2.0) is a legitimate optional experiment log. It must stay bound to localhost, because its tracking server has had recent CVEs allowing remote code execution without authentication ([ZDI-26-105](https://zerodayinitiative.com/advisories/ZDI-26-105)) [V]. DVC (Apache-2.0, now run by lakeFS) can snapshot the input data ([DVC licence](https://raw.githubusercontent.com/treeverse/dvc/HEAD/LICENSE)) [V].

With about one flood event-day a year, **drift in model performance cannot be tracked statistically**. Monitoring should cover what can be measured:

- whether rain data is fresh and within plausible ranges;
- the rain distribution against the training years for the same month;
- the share of days outside the model's "area of applicability", meaning days whose inputs lie further from the training data than anything seen in validation (after [Meyer & Pebesma 2021](https://doi.org/10.1111/2041-210X.13650)) [V];
- the share of barangay-days at Moderate and High;
- cumulative observed against expected events per season, with an exact Poisson interval.

Every new recorded event should automatically produce a card showing what the champion and challenger predicted on that day and the day before. Evidently (Apache-2.0, usable without an account) can produce monthly drift reports if wanted ([Evidently OSS vs Cloud](https://docs.evidentlyai.com/faq/oss_vs_cloud)) [V]. Plain SQL checks written to a job log are enough.

## F. Validation strategy: prove "no worse" before claiming "better"

With 5 storm days and 8 landslide days, validation cannot produce a single trustworthy headline score. Its job is to catch failures, to compare models on the same days, and to set up a test on future data that will eventually give a real answer.

### Split by storm and by year, never by row

Splitting rows at random is invalid for this data. A review of blocked cross-validation found that random splits underestimate error whenever data depend on each other in time, space or group structure, even when the model's errors look independent ([Roberts et al. 2017](https://www.biometrie.uni-freiburg.de/mitarbeiter/dormann/roberts-et-al-2017-ecography.pdf)) [V]. A central African forest-biomass study is a warning: a random forest that "explained more than half" of the variation under random validation had "quasi-null predictive power" under spatial validation ([Ploton et al. 2020](https://doi.org/10.1038/s41467-020-18321-y)) [V]. One counter-argument holds that spatial validation can be too pessimistic when the test points are a random probability sample of the map ([Wadoux et al. 2021](https://doi.org/10.1016/j.ecolmodel.2021.109692)) [A]. GeoAlert's event records are not such a sample, so it does not apply here.

Four designs together give an honest picture:

- **Rolling-origin yearly folds** (train on earlier years, test on the next year) stay as the estimate closest to real deployment.
- **Leave-one-event-day-out** validation holds out each storm (or landslide day) with a buffer on either side at least as long as the longest rain window. Non-event days go into whole-month blocks with the same buffer, so each flood fold trains on four of the five storms. Because it breaks time order, it is reported beside rolling-origin, never instead of it.
- **Out-of-period testing** scores the frozen current landslide model on GLC landslide days from 2007–2017 that it has never seen.
- **A test on future data** freezes every choice now and scores the 2026 wet season as it happens.

Skill should be split into "when" and "where":

- **"When"** is scored per city-day: do event days rank above other wet days?
- **"Where"** is scored only on event days: do affected barangays rank above unaffected ones? That is informative only on days when many barangays flooded, such as Tino's 10 of 22.

For a flood "where" taken from NOAH, the right check is a lift ratio, not a fitted LOBO AUC: the share of records inside high-hazard areas against the share of area that is high-hazard.

Leaving out one barangay at a time is still useful as a check of how the model handles barangays it has not seen. For landslides it is nearly meaningless, because 7 of the 8 positives fall in one held-out barangay. Results should be reported fold by fold, with the number of positives in each fold. Any hyperparameter or threshold chosen by cross-validation needs nested cross-validation: an inner loop chooses, and an outer loop measures.

### Leakage guards GeoAlert specifically needs

Leakage means using information that would not be available when the prediction is made. It was found in at least 294 published studies across 17 fields, and once it was removed, claimed machine-learning gains often disappeared ([Kapoor & Narayanan 2023](https://pmc.ncbi.nlm.nih.gov/articles/PMC10499856)) [V]. Five forms are real risks here:

- **Features built from the event inventory.** Past flood counts, per-barangay historical rates and distance to past landslides must be recomputed from training years only, inside every fold. The same goes for any baseline built from them.
- **Rain windows.** They must be trailing. A same-day total is legitimate for a same-day estimate, but not for anything described as a forecast.
- **Choices already tuned on the test years.** Several decisions were made after seeing the 2023–2025 results: the 15%/25% cut-offs, the choice of rain windows, keeping logistic regression over XGBoost, and keeping Poisson over the neural network. Those years are no longer clean tests of those choices, which is why the 2026 season matters.
- **Clustered events.** An event that spans several barangays or several days must count as one cluster in resampling, not as independent positives.
- **Rain data versions.** The version of rain data used in training must match what is available live. Storing the actual rain value used with each prediction keeps later checks honest.

Under-recording is not leakage. But it skews both training and evaluation toward places where events get reported, and it should be stated as a limitation.

### Imbalance belongs in the threshold, not the training data

Having far more non-events than events is not a defect to correct. A simulation and case study of imbalance fixes for logistic regression found that undersampling, oversampling and SMOTE "yielded poorly calibrated models", with the rare-class probability "strongly overestimated" and no better discrimination. Shifting the decision threshold gave the same trade-off ([van den Goorbergh et al. 2022](https://pmc.ncbi.nlm.nih.gov/articles/PMC9382395)) [S]. XGBoost's own documentation says that if the predicted probability matters, "you cannot re-balance the dataset" ([XGBoost tuning notes](https://xgboost.readthedocs.io/en/stable/tutorials/param_tuning.html)) [V].

SMOTE is also mechanically fragile here. Its defaults need at least six positive examples in every fold ([imbalanced-learn](https://imbalanced-learn.org/stable/references/generated/imblearn.over_sampling.SMOTE.html)) [V], and synthetic floods blended from two different storms are physically meaningless. If a challenger must drop rows (TabPFN's row cap would force this), the King–Zeng prior correction to the intercept should undo the effect ([King & Zeng 2001](https://gking.harvard.edu/publication/logistic-regression-in-rare-events-data/)) [S].

The threshold itself should come from the DRRMO's cost of a missed event against the cost of a false alarm. It should be checked with decision curves, which plot net benefit across thresholds against "warn everyone" and "warn no one" ([Vickers & Elkin 2006](https://pmc.ncbi.nlm.nih.gov/articles/PMC2577036)) [V]; the dcurves package is Apache-2.0 ([dcurves](https://pypi.org/project/dcurves/)) [V]. Cut-offs must be fixed before the final test folds are scored.

### Metrics and baselines that mean something at a 0.045% event rate

At an event rate of 0.00045, a constant forecast already scores a Brier score of about 0.00045, so raw Brier scores flatter every model. The main metrics should be the **log score**, which punishes confident misses on event days hardest, and **Brier skill** against two references: the overall rate (climatology) and the shrunken per-barangay training rate. PR-AUC should always be printed beside its no-skill level (0.00045 for flood, 0.0002 for landslide).

A ten-bin reliability diagram would hold 0–2 positives per bin. Calibration should instead be shown as observed against expected counts per year, season and barangay group, plus the overall calibration and the calibration slope, each with an interval. Flexible calibration curves need far more events ([Van Calster et al. 2016](https://repub.eur.nl/pub/87511)) [V].

For the Low/Moderate/High levels, each cut-off should get a 2×2 table of hits, misses, false alarms and correct negatives. From it, report the probability of detection and the false-alarm ratio, which are easy to communicate. Also report the Peirce skill score, which does not depend on how often events happen, and SEDI. SEDI was designed because traditional scores "degenerate to trivial values as events become rarer" ([Ferro & Stephenson 2011](https://doi.org/10.1175/WAF-D-10-05030.1); [JWGFVR verification guide](https://jwgfvr.github.io/forecastverification)) [V].

The most persuasive output for a DRRMO and a thesis panel is an **event-by-event table**. For each of the 5 storms and 8 landslide days, it shows the probability and level each model gave on that day and the day before, and how many barangays were flagged High.

Every model must be compared on the same days against the same baselines:

- climatology;
- the shrunken per-barangay rate;
- an untuned rule based on PAGASA's 24-hour bands;
- persistence (yesterday's event predicts today's);
- a rain-only logistic regression with one or two features;
- for landslides, the 2-year return-level rule and the 7-day 95th-percentile rule.

### What five storms can and cannot prove

The arithmetic sets hard limits. In a paired sign test, a new model that beats the current one on every event day reaches a smallest two-sided p of **0.0625 with 5 days**, 0.0078 with 8 and 0.002 with 10 (own calculation). The research team's Hanley–McNeil estimates give 95% half-widths of about ±0.18 for an AUC of 0.90 on 5 effective positives, and ±0.20 for an AUC of 0.75 on 8, before clustering widens them further. Guidance for validating prediction models asks for **at least 100 events, and preferably 200** ([Collins et al. 2016](https://pmc.ncbi.nlm.nih.gov/articles/PMC4738418)) [V]. At roughly one flood event-day a year, that is decades away.

Comparisons should therefore use paired differences in log score and Brier score on the same rows. Their intervals should come from a **cluster bootstrap**, which resamples event clusters and non-event blocks separately and keeps all 22 barangays of a day together. The event-by-event win/loss table goes alongside. AUC comparisons that account for clustering (DeLong or Obuchowski) are secondary ([Obuchowski 1997](https://doi.org/10.2307/2533958)) [V].

The promotion rule should be written down before testing. Promote a new model only if one of these holds:

- the bootstrap interval for the log-score difference excludes zero in the new model's favour; or
- the new model is no worse on every event day, better on most, and adds no false alarms per real event at High.

In both cases, it must also pass the leakage checklist and the area-of-applicability check.

Otherwise the honest report reads: "On the 5 flood event days available, the new model gave a higher probability on 4 of 5; this is not statistically distinguishable (the smallest achievable p with 5 days is 0.06); the current model is kept and will be reassessed after the 2026 wet season." Reports should follow TRIPOD+AI, the 2024 reporting guideline for prediction models, which applies "irrespective of whether regression modelling or machine learning methods have been used" ([Collins et al. 2024](https://doi.org/10.1136/bmj-2023-078378)) [V]. The model card should be generated from the same JSON as the metrics.

### Fire is the one hazard where "better" can be tested

With 219 fires, fire comparisons have real statistical power. The design is monthly rolling-origin folds with paired Poisson log scores. They would be tested with the Diebold–Mariano statistic using its small-sample correction ([Harvey, Leybourne & Newbold 1997](https://ideas.repec.org/p/yor/yorken/15-15.html)) [V], or with a bootstrap that resamples whole months; either can support a claim. The comparison should also check that 80% prediction intervals contain about 80% of monthly counts, and show PIT histograms (a check that predicted distributions match observed counts).

The headroom is small. GeoAlert's GLM Brier score of 0.140 is already not significantly better than the per-barangay average, so a gain of about 0.001 is the realistic size. "Equal accuracy with calibrated intervals" is an acceptable result. Leaving out one barangay at a time makes sense for fire only if the model is meant to carry over to new barangays. With barangay effects in the model, it is not.

## G. Final recommendation: penalised two-part models for flood and landslide, pooled Poisson for fire

None of these can be proven better than the current models with today's flood and landslide data. They are the strongest defensible choices, listed in the order they should be tested.

### Flood

**Model.** The recommendation is a two-part model, with separate river and drainage channels:

- **"When":** a city-day "flood day" logistic regression fitted with Firth's penalty and the FLIC intercept correction (firthmodels plus a statsmodels offset fit). It uses at most three predictors: a 3-day NASA POWER rain sum, a tropical-cyclone distance flag built from IBTrACS for training, and optionally a 1-day sum.
- **"Where":** a fixed barangay allocation from NOAH 25- and 100-year flood-hazard shares and ASF HAND shares.

A PyMC version with a positive prior on rain is the alternative if the team wants full uncertainty bands. PAGASA's 24-hour advisory bands serve as the published baseline and the fallback alert.

**Why.** It stays within the event budget. It drops the fitted "where" that failed out of sample. It takes its spatial pattern from physically based modelling that does not depend on 18 records. And it adds storm context that the single rain cell cannot see.

**What it could measurably improve.** Each of these must still be measured; none is guaranteed:

- fitted parameters drop from 11 or more to 3 or fewer;
- a better log score than the current model on leave-one-event-day-out folds;
- a higher lift ratio of recorded floods inside high-allocation barangays than the current terrain terms achieve;
- fewer false-alarm barangay-days per year at High for the same number of hits;
- at least equal performance to the PAGASA band rule.

**What it leaves unsolved:**

- Five storm days cannot statistically separate it from the current model.
- NOAH's licence was read only on secondary pages. Its maps are labelled beta and use about 30 years of rain. Using them needs the project owner's approval, given the cancelled hazard-maps feature.
- IBTrACS is not real-time, so live storm flags need PAGASA or JTWC bulletins, whose terms were not checked.
- One coarse rain cell remains.
- Under-recording caps every score.
- Mananga river works in 2026 will shift river hazard.

**Dependencies.** Software: numpy, scipy, scikit-learn, statsmodels and firthmodels, optionally with PyMC, nutpie and ArviZ. Data: NASA POWER, IBTrACS, NOAH, ASF HAND, the Copernicus DEM, and optionally CHIRPS v3 for testing.

**Licensing.** All code is MIT, BSD or Apache-2.0, with no pretrained weights and no account or key [V for the licences]. Among the data, CHIRPS, HAND and the Copernicus DEM are verified. NOAH (ODbL, with share-alike on derived databases) and IBTrACS (the WMO Resolution 40 note) need confirmation before production. **Offline:** yes. Training and prediction run entirely offline after installation; the only network step is the daily rain download from NASA POWER, which needs no account or key [A] and is a data download, not an inference service.

### Landslide

**Model.** The recommendation is a two-part model:

- **"When":** a regional "landslide day" logistic regression, fitted with Firth plus FLIC (or Bayesian with weakly informative priors), on one or two NASA POWER multi-day rain sums. It is trained on GeoAlert's 8 days plus place-checked NASA GLC days from Talisay and the neighbouring uplands.
- **"Where":** a terrain allocation proportional to exp(β × terrain), with steep-slope share as the main term and at most two more covariates (plan curvature or TWI from WhiteboxTools, distance to OSM roads).

It is benchmarked on the same days against a Dynaslope-style 2-year return-level rule and an LHASA-v1-style 7-day 95th-percentile rule. Before any refit, the current model should first be scored on the GLC's 2007–2017 days as an out-of-period test.

**Why.** It turns 8 event days into roughly 51. It accepts that one rain cell makes timing a city-wide question. It follows the evidence that pooled, low-parameter logistic models carry over better than flexible learners ([Brenning 2005](https://nhess.copernicus.org/articles/5/853/2005/); [Jones et al. 2023](https://nhess.copernicus.org/articles/23/1095/2023/)). And it derives thresholds from the rain product actually used, as the Itogon study requires ([Abancó et al. 2021](https://nhess.copernicus.org/articles/21/1531/2021/)).

**What it could measurably improve:**

- timing AUC and Brier score on landslide days that were never used in fitting;
- the share of recorded slides that fall in the top-ranked barangays;
- at least equal performance to both inventory-free rules on the same days.

The out-of-period test makes landslide the one rain-driven hazard where some real evidence of improvement is within reach.

**What it leaves unsolved:**

- The GLC states no licence, so it should be used internally without republishing the records, pending written confirmation from NASA.
- Many GLC locations are only good to within 5–25 km, and its records are from 2007–2017, while the model would run from 2021 on.
- The Manipis concentration partly reflects where slides get reported.
- There is no hourly rain, and no local geotechnical data.

**Dependencies.** The same software stack as flood, plus WhiteboxTools. Data: NASA POWER, the Copernicus DEM, OSM, ESA WorldCover and the GLC CSV.

**Licensing.** Code and terrain data are cleared [V]. The GLC is conditional. **Offline:** yes, after a one-time download of the catalogue and terrain data, plus the daily rain refresh.

### Fire

**Model.** A partially pooled Poisson GLM, switching to negative binomial if the counts vary more than Poisson allows. It has a barangay random intercept, one to three seasonal terms and an exposure offset. It would be upgraded to a BYM2 spatial effect only if the residual Moran's I or a leave-one-out comparison favours it.

It can be fitted in PyMC with nutpie and ArviZ. A frequentist equivalent uses glum, or scikit-learn's PoissonRegressor with a ridge penalty. Before any self-exciting (Hawkes) model, add last month's fire counts, for the same barangay and its neighbours, to the GLM and test whether they help. Chronos-2 or TimesFM 2.5 can serve only as an offline zero-shot benchmark.

**Why.** Pooling is the method behind the best area-level fire result found ([Buffington et al. 2021](https://doi.org/10.1016/j.compenvurbsys.2021.101633)). It gives low-count barangays stable rates, and with 219 events, a gain can actually be shown.

**What it could measurably improve.** Paired monthly log-score and Brier comparisons against the per-barangay average and the current GLM; 80% intervals that contain about 80% of counts; and PIT histograms. The realistic Brier gain is about 0.001.

**What it leaves unsolved.** Gains will be small. The exposure data source is unverified. The BYM2 mixing parameter will be dominated by its prior at 22 areas. Spatial effects can distort covariate estimates ([Hodges & Reich 2010](https://doi.org/10.1198/tast.2010.10052)) [S].

**Dependencies, licensing and offline use.** PyMC (Apache-2.0), PyTensor (BSD-3), nutpie (MIT) and ArviZ (Apache-2.0), or glum (BSD-3); esda and libpysal (BSD-3) for the residual checks [V]. All rules are satisfied, and it runs fully offline.

| | Flood | Landslide | Fire |
|---|---|---|---|
| Recommended model | Firth + FLIC city-day logistic × fixed NOAH/HAND allocation | Firth + FLIC regional landslide-day logistic × terrain allocation | Partially pooled Poisson or negative binomial with exposure offset; BYM2 only if needed |
| Fitted parameters | 3 or fewer | 1–2 for timing, 1–3 for allocation | Intercept, seasonal terms, pooled barangay effects |
| Baseline it must beat | PAGASA 24-h bands; rain-only LR | 2-year return-level rule; LHASA-v1-style rule | Per-barangay average; current GLM |
| Can it be shown better with current data? | No (5 storm days) | Partly, through the GLC out-of-period test | Yes, through paired monthly tests |
| Code licences | MIT, BSD-3, Apache-2.0 [V] | MIT, BSD-3, Apache-2.0 [V] | Apache-2.0, MIT, BSD-3 [V] |
| Data needing confirmation | NOAH (ODbL [S]); IBTrACS (WMO Resolution 40) | NASA GLC (no licence stated [V]) | Exposure data source unverified |
| Account, key or paid service | None | None | None |
| Runs offline after installation | Yes, apart from the daily rain download | Yes, apart from the daily rain download | Yes |

The licence chain for the recommended stacks covers every layer the brief asked about.

| Layer | Flood and landslide | Fire |
|---|---|---|
| Algorithm | Logistic regression, Firth penalty, FLIC ([Puhr et al. 2017](https://arxiv.org/pdf/2101.07620)): published statistical methods; no restriction found [A] | Poisson and negative-binomial GLMs, random effects, BYM2 ([Riebler et al. 2016](https://doi.org/10.1177/0962280216660421)): published methods; no restriction found [A] |
| Implementation | firthmodels MIT, statsmodels BSD-3, scikit-learn BSD-3; optional PyMC Apache-2.0, nutpie MIT, ArviZ Apache-2.0 [V] | PyMC Apache-2.0, PyTensor BSD-3, nutpie MIT, ArviZ Apache-2.0, or glum BSD-3; esda and libpysal BSD-3 [V] |
| Pretrained weights | None | None |
| Required dependencies | scipy BSD [V]; numpy and pandas BSD-style [A] | Same, plus a C compiler on the training machine for PyTensor [A] |
| Training and input data | GeoAlert records; NASA POWER [A]; IBTrACS [V]; NOAH [S]; ASF HAND CC0 [V]; Copernicus DEM [V]; OSM ODbL [V]; NASA GLC conditional [V] | GeoAlert's BFP-based fire records; exposure from OSM (ODbL) [V] or census data (licence unverified) |

## Conclusion

GeoAlert has already run the experiment the literature predicts: random forest, XGBoost, LightGBM and an MLP all tied or lost to its GLMs. Further shopping for algorithms is unlikely to pay. The comparison that matters now is between sources of information. Catalogued landslide days, storm tracks and physically modelled flood depths are independent evidence that 40,172 barangay-day rows cannot generate. So is each newly verified DRRMO record with an exact date, place and source, and every such record is worth more than any model change. That reframes what a thesis panel should value. A small, auditable model that names its five storms, shows its uncertainty and scores itself against official rain rules on new data is a stronger result than a higher pooled AUC, which at this event count mostly measures the difference between storm days and dry days.

Two consequences follow. First, at about one flood event-day a year, statistical proof is decades away. Physical hazard layers and official thresholds are therefore not a compromise: they are the only way to bring outside evidence into the model. The immutable prediction table is what turns each wet season into a genuine test. Second, licences change. During 2025–2026 the default checkpoints of TimesFM and TabPFN moved from permissive to non-commercial terms ([TimesFM 3.0 licence](https://huggingface.co/google/timesfm-3.0-pytorch/blob/main/LICENSE); [TabPFN README](https://github.com/PriorLabs/TabPFN)). Any dependency beyond the core GLM stack therefore needs pinned versions and a licence re-check at every upgrade. The recommended stack avoids the problem entirely because it uses no pretrained weights.
