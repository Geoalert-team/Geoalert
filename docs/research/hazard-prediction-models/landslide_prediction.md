# Landslide prediction for GeoAlert (Talisay City, Cebu): susceptibility, occurrence given rain, and short-term forecasting, with verified licences

Research date: 2026-11-13. Scope: landslide only. Labels used below:
- **[V]** = verified in this session from the primary page, file or repository (licence text read, URL fetched, or HTTP request made without any login).
- **[S]** = taken from a secondary source or a search-result summary of the primary source; not read in full.
- **[A]** = assumption or prior knowledge, not re-verified in this session.

GeoAlert baseline these notes evaluate against (from the project's model report, 2026-11-13; not re-verified here): barangay-day panel 2021-2025 (~40,172 rows); 8 landslide barangay-days on 8 dates (7 Manipis, 1 Camp IV); logistic regression on NASA POWER PRECTOTCORR daily rain (one ~0.5 degree cell; same-day, 1/3/7/14-day sums) times terrain exposure (share of ground >15 degrees from Copernicus DEM, 150 m grid). Place AUC 0.96, leave-one-barangay-out AUC 0.90, timing AUC ~0.80.

Three different prediction problems, which these notes keep apart:
1. **Susceptibility** (where): a static map of how likely a place is to have landslides. It does not change with weather.
2. **Occurrence given rain** (when, given observed rain): the probability that a landslide happens on a day or in an event, given the rain that has fallen. This is the rainfall-threshold and space-time model family. GeoAlert's current model belongs here.
3. **Short-term forecasting or early warning** (when, ahead of time): the same model driven by rain *forecasts* or near-real-time rain, giving lead time. Its accuracy depends on how accurate and how quick the rain input is.

---

## 1. Susceptibility methods and evidence (LR, FR, WoE, RF, SVM, XGBoost, CNN; spatial cross-validation; mapping units)

### Takeaway
The literature is dominated by logistic regression and other statistical/ML classifiers, but high-quality evaluations are rare and results are not comparable across sites. With only 8 local positives (7 in one barangay), the evidence favours simple, low-variance models (logistic regression with few covariates, penalised LR, or heuristic/expert weighting) evaluated with spatial cross-validation, over RF/XGBoost/CNN. Flexible learners overfit when tested outside the training area, and non-spatial CV inflates their scores.

### Cited Findings
- Reichenbach, Rossi, Malamud, Mihir & Guzzetti (2018), "A review of statistically-based landslide susceptibility models", *Earth-Science Reviews* 180:60–91, doi:10.1016/j.earscirev.2018.03.001. They compiled 565 peer-reviewed articles (1983–2016) and recorded 31 categories of information for each [S]. — [CNR-IRPI manuscript PDF](https://geomorphology.irpi.cnr.it/publications/repository/public/journals/2018/susceptibility_revision_esjr_manuscript.pdf); [Durham repository record](https://durham-repository.worktribe.com/output/1177876/a-review-of-statistically-based-landslide-susceptibility-models)
- Reichenbach et al. 2018: the most common methods were logistic regression, neural networks, data overlay, index-based and weights-of-evidence analyses, with machine-learning use growing. Model quality has improved, but "top-quality" assessments are rare, few studies evaluate model uncertainty, and study sites cluster in China, India, Italy and Turkey [S]. — [CNR-IRPI manuscript PDF](https://geomorphology.irpi.cnr.it/publications/repository/public/journals/2018/susceptibility_revision_esjr_manuscript.pdf)
- Brenning (2005), "Spatial prediction models for landslide hazards: review, comparison and evaluation", *NHESS* 5:853–862. Using a resampling approach that accounts for spatial autocorrelation, logistic regression with stepwise backward selection "yields lowest error rates and demonstrates the best generalization capabilities". Tree-based methods (bagging, double-bagging) "tend to overfit the data", as shown by evaluation outside the training area. SVMs were also compared. Study area: Ecuadorian Andes [V, abstract]. — [NHESS 5:853](https://nhess.copernicus.org/articles/5/853/2005/)
- Schratz, Muenchow, Iturritxa, Richter & Brenning (2019), *Ecological Modelling* 406:109–120, doi:10.1016/j.ecolmodel.2019.06.002. Non-spatial CV was over-optimistic compared with spatial CV, with performance differences up to 47%. Spatial vs non-spatial partitioning for hyperparameter tuning made little difference in most cases, but spatial tuning is still recommended. The case study is forest disease, not landslides, so it transfers only by analogy [S]. — [RePEc record](https://econpapers.repec.org/RePEc:eee:ecomod:v:406:y:2019:i:c:p:109-120); [arXiv 1803.11266 listing](https://www.emergentmind.com/papers/1803.11266)
- The R package `sperrorest` (spatial error estimation; Brenning as author and maintainer) is licensed **GPL-3**, per its DESCRIPTION file, version 3.0.5 [V]. — [sperrorest DESCRIPTION](https://raw.githubusercontent.com/pat-s/sperrorest/master/DESCRIPTION)
- Philippine multi-event evidence: Jones, Bennett, Abancó, Matera & Tan (2023), *NHESS* 23:1095–1115. They fitted binary logistic regression with LASSO selection (R `glmnet`) on 5 m cells, using 9 factors (geology, soil type, aspect, land use, distance to channels, elevation, plan curvature, profile curvature, slope). Data were three typhoon inventories: Parma 2009 (1,912 landslides), Mangkhut 2018 (956), Kammuri 2019 (1,964). Single-event models were about 6–10% worse at classifying another typhoon's landslides. A model combining two typhoons was only about 1–3% worse. AUROC was about 78–82% at Itogon and about 65% at Abuan. The paper itself is inconsistent on the Abuan range (65–82% in one section, 65–68% in another) [S, from article page]. — [NHESS 23:1095](https://nhess.copernicus.org/articles/23/1095/2023/)
- Cebu Province: Sañez, Arizapa, Padrones & Tiburan (2026), *ISPRS Annals* X-5/W4-2025:377–384. They compared frequency ratio and logistic regression using an inventory for 2009–2023 "compiled from news reports and validated using Google Earth imagery". Seven factors: slope, elevation, aspect, TWI, TPI, soil texture, curvature. The article page gives LR AUC 0.9151 vs FR 0.8955; a search snippet of the same paper gives 0.8817 (LR) vs 0.8317 (FR), so the numbers conflict. Talisay is not mentioned. Licence CC BY 4.0 [V for page; numbers conflict]. — [ISPRS Annals article](https://isprs-annals.copernicus.org/articles/X-5-W4-2025/377/2026/); conflicting figure in [ResearchGate listing](https://www.researchgate.net/publication/400647516_A_Comparative_Study_of_Frequency_Ratio_FR_and_Logistic_Regression_LR_in_Landslide_Susceptibility_Mapping_for_Cebu_Province_Philippines)
- Mapping units: Alvioli et al. (2016), "Automatic delineation of geomorphological slope units with r.slopeunits v1.0 and their optimization for landslide susceptibility modeling", *GMD* 9:3975–3991. r.slopeunits is a Python module for GRASS GIS that builds slope units from a DEM [S]. The module exists in the official `grass8` add-ons branch [V, HTTP 200 on `src/raster/r.slopeunits/r.slopeunits.py`]. Its own licence header was not found by text search [A: GRASS add-ons are normally GPL-2+]. — [GMD 9:3975 PDF](https://gmd.copernicus.org/articles/9/3975/2016/gmd-9-3975-2016.pdf); [CNR-IRPI slope units page](https://www.irpi.cnr.it/en/focus/slope-units/)
- Slope-unit susceptibility at national scale: Loche, Alvioli, Marchesini, Bakka & Lombardo (2022), *Earth-Science Reviews* 232, built slope-unit susceptibility from the Italian national inventory, implemented in R-INLA [S]. — [search summary via University of Twente record](https://research.utwente.nl/en/publications/landslide-susceptibility-maps-of-italy-lesson-learnt-from-dealing-2/)
- Licences of candidate ML libraries, read from the LICENSE/COPYING files [V]: scikit-learn **BSD-3-Clause** ([COPYING](https://raw.githubusercontent.com/scikit-learn/scikit-learn/master/COPYING)); XGBoost **Apache-2.0** ([LICENSE](https://raw.githubusercontent.com/dmlc/xgboost/master/LICENSE)); statsmodels **BSD-style (3-clause)** ([LICENSE.txt](https://raw.githubusercontent.com/statsmodels/statsmodels/master/LICENSE.txt)); PyMC **Apache-2.0** ([LICENSE](https://raw.githubusercontent.com/pymc-devs/pymc/master/LICENSE)); Bambi **MIT** ([LICENSE](https://raw.githubusercontent.com/bambinos/bambi/master/LICENSE)).

### Inferences
- **Results are not comparable across sites.** The AUCs above (0.65–0.92) come from different inventories, unit sizes, sampling designs and CV schemes. GeoAlert's place AUC 0.96 is computed over 22 barangays with 8 positive days, and 7 of those are one barangay. It mostly measures "Manipis/Camp IV vs flat lowland barangays", which slope alone separates. It is not evidence of fine-grained skill.
- **Avoid flexible learners.** With ~8 local positive barangay-days, RF/XGBoost/CNN susceptibility models are not defensible: Brenning 2005 showed tree methods overfit outside the training area even with far more data. GeoAlert's choice of logistic regression over RF/XGBoost is consistent with the evidence.
- **Barangays are a coarse mapping unit.** Each barangay mixes steep and flat ground. GeoAlert's "share of ground >15 degrees" is a sensible within-unit summary. A finer unit (slope units from r.slopeunits, or 150 m grid cells aggregated to barangay for display) would only help if positives carry usable coordinates. The current 8 events and most external records (see section 6) do not have them at that accuracy.
- **Use spatial CV to report honest scores.** Leave-one-barangay-out is a form of spatial CV, but with 7/8 positives in Manipis the fold that holds out Manipis decides the score. Report per-fold results and the number of positives in each fold, not just a pooled AUC.
- **Useful middle ground: penalised LR on a pooled multi-event inventory.** Jones et al. 2023 found combined-event models transfer much better than single-event models. For Talisay, the analogue is pooling the 2021–2025 events with the 2007–2017 NASA GLC records (section 6).

### Gaps
- No susceptibility study specific to Talisay City or its upland barangays (Manipis, Camp IV, Tapul, Jaclupan) was found in the peer-reviewed literature.
- The licence of the r.slopeunits add-on itself was not confirmed from its file header.
- Brenning (2012) on spatial CV (IGARSS/sperrorest) was not opened; its content is not cited here.

---

## 2. Rainfall thresholds for occurrence and early warning (ID, ED, antecedent, CTRL-T, probabilistic/Bayesian, few-event thresholds, Philippine thresholds)

### Takeaway
Empirical rainfall thresholds are the standard tool for "occurrence given rain", but reliable thresholds need many events: one widely cited analysis puts the figure at about 175 events to keep threshold uncertainty below 10%. They also usually need sub-daily rain (the intensity-duration (ID) family and CTRL-T need hourly gauges). GeoAlert has 8 events and daily, city-wide rain, so the defensible route is a probabilistic multi-duration daily threshold (what the current logistic regression already is), anchored by (a) more events from the NASA GLC and (b) an inventory-free return-period rule like the one PHIVOLCS-Dynaslope uses. Philippine thresholds are few and site-specific (Benguet/Baguio, Albay), and the tropical literature warns that generic thresholds such as Caine 1980 are too low.

### Cited Findings
- Guzzetti, Peruccacci, Rossi & Stark (2007), "Rainfall thresholds for the initiation of landslides in central and southern Europe", *Meteorology and Atmospheric Physics* 98:239–267. They used 853 rainfall events and derived minimum ID and normalised-ID thresholds. Lower average intensity was needed in mountain climates than in Mediterranean climates. The authors suggest using the thresholds where local ones are lacking [S]. — [CNR-IRPI record](https://www.irpi.cnr.it/publication/rainfall-thresholds-for-the-initiation-of-landslides-in-central-and-southern-europe)
- A later Guzzetti et al. (2008) global compilation grew to 2,626 rainfall events (855 in Italy), as cited by Brunetti et al. 2010 [S]. — [Brunetti et al. 2010, NHESS 10:447](https://nhess.copernicus.org/articles/10/447/2010/nhess-10-447-2010.pdf)
- Segoni, Piciullo & Gariano (2018), "A review of the recent literature on rainfall thresholds for landslide occurrence", *Landslides* 15:1483–1501. It covered 115 thresholds published over nine years (a full-text snippet says 105). Validation is seldom done and rain-gauge selection is rarely explained. Progress includes thresholds at different exceedance probabilities for warning levels [S]. — [CNR-IRPI record](https://www.irpi.cnr.it/publication/a-review-of-the-recent-literature-on-rainfall-thresholds-for-landslide-occurrence)
- Minimum sample size: Peruccacci et al. (2012) proposed a bootstrap technique to find the minimum number of rainfall conditions needed for reliable thresholds. A later paper reports their suggestion that "a minimum number of 175 landslide events is required to limit the rainfall threshold uncertainty below 10%". The minimum depends on the data's distribution and temporal resolution [S, secondary]. — [Rossi et al. 2017 post-print (search snippet; fetch returned 403)](https://research.unipg.it/bitstream/11391/1406843/5/Rossi_et_al_2017_post_print.pdf); [Natural Hazards 2019 paper citing the method](https://link.springer.com/article/10.1007/s11069-019-03830-x)
- Under-recording matters: a 2015 EGU abstract by Gariano et al. observes that "even a very small underestimation in the number of landslides can result in a significant decrease in the performance of a threshold" [S]. — [search result: Gariano et al. 2019 PDF repository listing](https://geomorphology.irpi.cnr.it/publications/repository/public/journals/2019/gariano-et-al-2019-howmuchdoestherainfalltemporalresolutionaffectrainfallthresholds.pdf)
- Probabilistic/Bayesian thresholds: Berti, Martina, Franceschini, Pignone, Simoni & Pizziolo (2012), "Probabilistic rainfall thresholds for landslide occurrence using a Bayesian approach", *JGR Earth Surface* 117:F04006, doi:10.1029/2012JF002367. They argue that because the same rainfall can give either outcome, a probabilistic threshold is preferable. The method gives P(landslide) between 0 and 1 for each combination of rainfall variables and uses both landslide and no-landslide events. In Emilia-Romagna (>4,000 historical events), duration, intensity and total rain mattered most and antecedent rain less [S]. — [Univ. Bologna record](https://cris.unibo.it/handle/11585/129156)
- **CTRL-T** (Melillo, Brunetti, Peruccacci, Gariano, Roccati & Guzzetti 2018, *Environmental Modelling & Software* 105:230–243, doi:10.1016/j.envsoft.2018.03.024) is written in **R**. It works on a continuous **hourly** record from a single rain gauge (hourly values below gauge sensitivity, e.g. 0.2 mm, are treated as noise). It reconstructs events and outputs cumulated event rainfall E and duration D for thresholds [S]. — [CNR-IRPI CTRL-T page](https://geomorphology.irpi.cnr.it/tools/rainfall-events-and-landslides-thresholds/ctrl-t-algorithm); [CNR-IRPI "How to define rainfall thresholds automatically"](https://www.irpi.cnr.it/en/focus/how-to-define-rainfall-thresholds-automatically/)
- **CTRL-T licence: none stated.** The download page offers one file, `CTRL-T_code.R` (80 KB, last modified 2018-06-01). It shows no licence, no terms of use and no registration requirement, only a site-wide footer "©2005 - 2018 Istituto di Ricerca per la Protezione Idrogeologica" [V]. A direct download attempt by script returned a NotFound JSON, so the script header was not inspected [V]. — [CTRL-T code page](https://geomorphology.irpi.cnr.it/tools/rainfall-events-and-landslides-thresholds/ctrl-t-algorithm/ctrl-code)
- Philippines, Benguet: Javier & Kumar (2018), "Deriving the rainfall threshold for shallow landslide early warning during tropical cyclones: a case study in northern Philippines", *Natural Hazards* 90(2):921–941, doi:10.1007/s11069-017-3081-2. In an independent test set, 93% of landslide-triggering rain events fell above the derived ID threshold [S]. A related thesis reports early-warning options of 70 mm in 24 h, I = 6.46 D^-0.28, or normalised NI = 0.002 D^-0.28 (Tublay, Benguet) [S]. — [IDEAS/RePEc](https://ideas.repec.org/a/spr/nathaz/v90y2018i2d10.1007_s11069-017-3081-2.html); [UNE thesis record](https://rune.une.edu.au/web/handle/1959.11/27377)
- Philippines, Baguio: Nolasco-Javier et al. (2015) "Rapid appraisal of rainfall threshold and selected landslides in Baguio" proposed a tentative minimum triggering threshold of 70 mm in 24 h (Typhoon Parma/Pepeng context) [S]. — [Springer, Natural Hazards](https://link.springer.com/article/10.1007/s11069-015-1790-y)
- Philippines, Itogon (Typhoon Mangkhut 2018): Abancó, Bennett, Matthews, Matera & Tan (2021), *NHESS* 21:1531–1550 [V, article page]. Key points:
  - Inventory: 1,101 landslides over 570 km².
  - Rain: IMERG showed ~360 mm over 44 h, while the Baguio gauge recorded 794 mm on 12–15 Sept, so satellite estimates under-measure extremes. Antecedent rain was up to 245 mm in the prior 2 weeks.
  - Earlier 2018 events with similar or higher intensities, under saturated soils (SMAP-L4), did not trigger widespread landsliding: "more rainfall intensity does not mean more landslides".
  - Many non-triggering events exceeded Caine's (1980) global ID threshold, so such curves may be too low for the tropics.
  - The proposed 500 mm seasonal-antecedent threshold (Nolasco-Javier & Kumar 2018) was passed on 14 June 2018 without failures; the authors estimate ~2,600 mm would have been needed.
  - They conclude no reliable early-warning threshold can be drawn from one event, thresholds must be derived from the same rain data source used operationally, and (at the time) rainfall thresholds were not used for early warning in the Philippines.
  — [NHESS 21:1531](https://nhess.copernicus.org/articles/21/1531/2021/)
- Philippines, MGB Albay study ("Establishing landslide early warning system using rainfall"): lower, middle and upper thresholds from combined 3-day cumulative rain and event rainfall, retested on Oct–Dec 2020 data. Reported figures are 200 mm/day intensity and 260 mm total event rainfall. The warning bulletin used 12-h *forecast* rainfall rather than real-time values [S; the PDF returned HTTP 403 to the fetch tool, so content comes from search summaries only]. — [MGB PDF](https://mgb.gov.ph/images/Research__Development/12_-_T06_ESTABLISHING_LANDSLIDE_EARLY_WARNING_SYSTEM_USING_RAINFALL.pdf)
- Philippines, PHIVOLCS-Dynaslope (operational community early warning): a Dynaslope paper states the deep-seated landslide early-warning threshold is based on **one-day cumulative rainfall with a two-year return period**, and that antecedent rain is not explicitly considered. A 2017 Dynaslope field report (Kibawe, Bukidnon) found ground movement correlated with rain exceeding **half of the two-year maximum daily rainfall** [S, secondary; the official alert-protocol document was not retrieved]. — [ResearchGate: Bias correction of real-time GSMaP rainfall for landslide early warning](https://www.researchgate.net/publication/394425059_Bias_Correction_of_Real-Time_GSMaP_Satellite-Retrieved_Rainfall_Data_in_the_Context_of_Landslide_Monitoring_and_Early_Warning); [Academia.edu: Kibawe 2017 assessment report](https://www.academia.edu/38157252/Assessment_Report_of_the_April_May_2017_Landslide_Event_in_Puroks_1_2_and_3_Brgy_Magsaysay_Kibawe_Bukidnon); [Rappler explainer](https://www.rappler.com/philippines/how-phivolcs-dynaslope-warning-system-help-avert-disasters-landslide-prone-areas/)
- Philippines, Bicol (Catanduanes): a study links precipitation thresholds to slope gradient using daily rain from the Virac synoptic station, 2016–2022 [S]. — [SSRN 4761538](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4761538)

### Inferences
- **The ID and ED families do not fit GeoAlert's data.** They need event intensity and duration in hours. NASA POWER is daily, and one ~0.5 degree cell covers the whole city, so ID/ED thresholds and CTRL-T (hourly, single gauge) are mismatched. CTRL-T also has **no stated licence**, so under the project's rules it is **not cleared** for deployment regardless of data fit.
- **The current model is already a probabilistic threshold.** GeoAlert's logistic regression on 1/3/7/14-day sums is effectively a multi-duration probabilistic daily threshold in the spirit of Berti et al. 2012, because it uses both landslide and no-landslide days. That is the right family. Its weakness is the 8 positives, not the method.
- **Add an inventory-free baseline.** A return-period rule (e.g. 1-day rain above the 2-year return level, or above half of it, as Dynaslope uses) can be computed from a long daily rain record without any landslide data (NASA POWER daily goes back decades [A]; CHIRPS v3 back to 1981 [V, section 7]). It gives interpretable warning tiers and a baseline to beat. With 8 events, GeoAlert should report whether its LR beats this rule on the same days.
- **Generic thresholds do not transfer.** Abancó et al. 2021 shows that thresholds from other Philippine sites (500 mm seasonal; 70 mm/24 h) and global curves did not separate triggering from non-triggering events in Benguet. Thresholds must also be derived from the same rain product used operationally. GeoAlert should therefore not import Benguet/Albay numbers. It should derive its own from NASA POWER, or from whichever product it adopts.
- **Under-recording biases thresholds.** Missing landslides mean "no-landslide" days include unrecorded events, which pushes probabilistic thresholds up and lowers apparent skill (Gariano et al.). This argues for adding external records (NASA GLC, news) before tuning cut-offs.

### Gaps
- The exact Caine (1980) ID equation was not re-verified this session [A: commonly given as I = 14.82 D^-0.39, I in mm/h and D in h].
- The figure "50% landslide probability at 54.40 mm one-day effective rainfall" for the Philippines surfaced in a search summary without a traceable primary source. Not used.
- No official PAGASA or MGB rainfall-threshold table for Cebu or Central Visayas was found. The official Dynaslope alert protocol (exact 1-day/3-day criteria) was not retrieved.
- The Peruccacci et al. 2012 original (the 175-event figure) was not opened.

---

## 3. Physically based slope-stability models (TRIGRS, SHALSTAB, SINMAP, r.slope.stability, Iverson infiltration, Landlab) and their licences; feasibility with SoilGrids

### Takeaway
Licence-wise, the cleanest physically based options are **TRIGRS (USGS, public domain)**, **Landlab's LandslideProbability component (MIT)** and **GRASS r.shalstab (GPL-2+)**. Practically, they need soil depth, hydraulic and strength parameters that do not exist for Talisay at useful resolution. With 8 events to calibrate against, their parameters would be unconstrained. They are a low-priority, explanatory add-on, not the main improvement.

### Cited Findings
- **TRIGRS** (Transient Rainfall Infiltration and Grid-based Regional Slope-stability), USGS, Fortran. LICENSE.md [V]: "This software is in the public domain because it contains materials that originally came from the United States Geological Survey". It includes two Netlib files (`calerf.f`, `derfc.f`) described as freely available. It compiles with free gfortran. — [LICENSE.md on code.usgs.gov](https://code.usgs.gov/usgs/landslides-trigrs/-/raw/master/LICENSE.md); [GitHub mirror LICENSE.md](https://raw.githubusercontent.com/usgs/landslides-trigrs/master/LICENSE.md)
- TRIGRS development moved to code.usgs.gov and the GitHub mirror is archived. A USGS code.json lists the licence as "Public Domain, CC0-1.0" [S]. — [USGS software page](https://www.usgs.gov/software/serial-and-parallel-versions-transient-rainfall-infiltration-and-grid-based-regional-slope); [code.json via mirror](https://github.kxpsado.workers.dev/usgs/landslides-trigrs/blob/master/code.json)
- **Landlab** is licensed **MIT** ("Copyright (c) 2013 The Landlab Team") [V]. Its `LandslideProbability` component implements Strauch et al. (2018, *Earth Surface Dynamics* 6:49–75). It couples an infinite-slope factor of safety with steady-state subsurface flow and runs Monte Carlo over soil and recharge distributions (recharge options: uniform, lognormal, lognormal_spatial, data_driven_spatial). Hydrologic forcing is annual-maximum daily recharge from a macroscale hydrologic model [S]. — [Landlab LICENSE.md](https://raw.githubusercontent.com/landlab/landlab/master/LICENSE.md); [Landlab docs, landslides component](https://landlab.readthedocs.io/en/latest/generated/api/landlab.components.landslides.landslide_probability.html); [ESurf 6:49](https://esurf.copernicus.org/articles/6/49/2018/)
- **GRASS GIS** core is **GPL-2.0-or-later** [V]. — [GRASS COPYING](https://raw.githubusercontent.com/OSGeo/grass/master/COPYING)
- **r.shalstab** (GRASS add-on, `grass8` branch) implements the Montgomery & Dietrich (1994) SHALSTAB algorithm; "(C) 2013 by Andrea Filipello & Daniele Strigaro", GPL (>= v2) per the file header [V]. — [r.shalstab.py](https://raw.githubusercontent.com/OSGeo/grass-addons/grass8/src/raster/r.shalstab/r.shalstab.py)
- **r.slope.stability** (Mergili et al. 2014, *GMD* 7:2969–2982) is a physically based 3-D slope-stability model coupled to GRASS GIS (C and Python) [S]. It was **not found** in the official `grass8` add-ons tree (HTTP 404 at the expected path) and the grass-stable manual page returned 404 [V]. Its licence was not confirmed. — [GMD 7:2969 PDF](https://gmd.copernicus.org/articles/7/2969/2014/gmd-7-2969-2014.pdf); [CNR-IRPI record](https://www.irpi.cnr.it/publication/r-slope-stability)
- **SINMAP**: the Philippine UP NOAH shallow-landslide hazard maps were produced with SINMAP (per the NOAH data mirror) [S]. — [Hugging Face mirror of NOAH hazard maps](https://huggingface.co/datasets/bettergovph/project-noah-hazard-maps)
- **SoilGrids 2.0** gives soil properties at six standard depths with quantified uncertainty (90% prediction interval) [V for the uncertainty statement]. It is CC BY 4.0 and accessible anonymously over WebDAV (details in section 7). — [ISRIC SoilGrids docs](https://docs.isric.org/globaldata/soilgrids/)

### Inferences
- **The models' inputs are missing locally.** TRIGRS, SHALSTAB and SINMAP need soil depth, saturated hydraulic conductivity or transmissivity, cohesion, friction angle and unit weight. SoilGrids supplies texture and bulk density at 250 m but not geotechnical strength. It does not obviously supply depth to bedrock either [A: SoilGrids 2.0 lists no depth-to-bedrock layer; not re-checked]. Every key parameter would be guessed or set from textbook ranges, then tuned on 8 events. That is weaker than the empirical model, not stronger.
- **Landlab is the best licence fit if a physical layer is wanted.** Its LandslideProbability is MIT, Python and CPU-only, and its Monte Carlo design reports parameter uncertainty honestly. It suits a static "probability of failure under wet conditions" layer (a physically informed susceptibility covariate), not daily forecasting.
- **TRIGRS can forecast in principle but not with GeoAlert's rain.** TRIGRS (public domain) is the only one of these designed for transient, rain-history-driven forecasting. It needs sub-daily rainfall intensity series and calibrated hydraulic diffusivity, which GeoAlert lacks.
- **Running GPL tools offline does not make GeoAlert GPL.** Using GPL GRASS tools (r.shalstab, r.slopeunits) to *produce* raster layers does not place GeoAlert's own code under the GPL, as long as GeoAlert does not link or redistribute the GPL code [A: general GPL reading; not legal advice].

### Gaps
- No Talisay or Cebu geotechnical parameter data (soil depth, strength) was found.
- The licences of SINMAP (original Utah State/Tarboton release) and TauDEM were not confirmed; the TauDEM LICENSE path returned 404.
- The Iverson (2000) infiltration model is implemented inside TRIGRS [A]; no separate implementation was checked.

---

## 4. Global and regional systems: NASA LHASA v1/v2, NASA Global Landslide Catalog / COOLR (licences and access; disqualified items)

### Takeaway
LHASA **code** is under the NASA Open Source Agreement 1.3. That licence is royalty-free and permits use, modification and redistribution (commercial included), but it is not MIT/Apache/BSD and carries copyleft-like obligations. **Running LHASA v2 needs a NASA Earthdata login and a PPS registration (for IMERG), so running it is disqualified.** The README also says the released code **cannot be retrained** on new data or domains. LHASA's **published outputs** (NCCS datashare) and the **global susceptibility map** download without a login. The **NASA Global Landslide Catalog** legacy CSV also downloads without a login and contains about 13 Talisay City records (2010–2016), but it has **no explicit licence** (data.nasa.gov: "License not specified").

### Cited Findings
- **LHASA licence:** `LICENSE.pdf` in nasa/LHASA is the **NASA Open Source Agreement version 1.3** ("Government Agency Original Software Designation: GSC-18,595-1 … LHASA Version 2.0") [V, full text read]. Key terms:
  - Grant: a non-exclusive, worldwide, royalty-free licence to Use, Distribute, Reproduce, Modify, Redistribute and Display, plus a patent licence including Sale.
  - Redistribution must stay under NOSA, include the agreement, and make source available if binaries are distributed.
  - Modifications need a change log identifying the contributor.
  - No implied NASA endorsement.
  - Registration is only *requested*: "User Registration Requested. Please Visit https://opensource.gsfc.nasa.gov".
  - In a Larger Work, the NOSA portions remain under NOSA.
  - Export-control notice; termination if breach not cured in 30 days; US federal law governs.
  — [nasa/LHASA LICENSE.pdf](https://github.com/nasa/LHASA/blob/master/LICENSE.pdf)
- The GitHub API reports the repository licence as "Other / NOASSERTION"; last push 2026-10-30 [V]. — [GitHub API nasa/LHASA](https://api.github.com/repos/nasa/LHASA)
- A `LICENSE.pdf` also exists at tag v1.1.1 (HTTP 200) [V]; its contents were not opened [A: likely the same NOSA]. — [LHASA v1.1.1 release](https://github.com/nasa/LHASA/releases/tag/v1.1.1)
- **LHASA access requirements** (README) [V]:
  - Setup writes Earthdata credentials to `.netrc` ("machine urs.earthdata.nasa.gov login <uid> password <password>").
  - It adds a PPS login "only necessary for downloading IMERG HDF5" (registration.pps.eosdis.nasa.gov).
  - Static inputs `static.zip`, `exposure.zip` and `ref_data.zip` download from gpm.nasa.gov.
  - Environment: conda with python 3.12, xgboost 2.0, rioxarray, dask, netcdf4 (lhasa.yml).
  - Quote: "The software released here enables the user to run the global landslide forecast, but it does not enable the user to retrain the model on new datasets or domains".
  — [nasa/LHASA README](https://github.com/nasa/LHASA); [lhasa.yml](https://raw.githubusercontent.com/nasa/LHASA/master/lhasa.yml)
- **LHASA outputs:** "The latest predictions can be downloaded from https://portal.nccs.nasa.gov/datashare/landslides/ … NASA provides these data on a best-effort basis, typically twice each day, but with frequent server downtime. Users requiring a fully operational system are encouraged to clone this repository and run LHASA" [V, README]. The datashare URL returned HTTP 200 without login in this session [V]. A long-term archive is at GES DISC (`Global_Landslide_Nowcast_2.0.0`) [V, README link]. — [NCCS datashare](https://portal.nccs.nasa.gov/datashare/landslides/); [GES DISC dataset](https://disc.gsfc.nasa.gov/datasets/Global_Landslide_Nowcast_2.0.0/summary)
- **LHASA v1.1** "requires … the 95th percentile rainfall and the global landslide susceptibility map". The README adds: "Users are encouraged to map susceptibility with current information on their own study areas, as well as update the rainfall threshold as needed" [V]. The global susceptibility GeoTIFF downloaded with HTTP 200, 33,493,474 bytes, no login [V]. — [global-landslide-susceptibility-map-2-27-23.tif](https://gpm.nasa.gov/sites/default/files/downloads/global-landslide-susceptibility-map-2-27-23.tif)
- **LHASA science:**
  - v1: Kirschbaum & Stanley (2018), *Earth's Future* 6(3):505–523, doi:10.1002/2017EF000715. It uses GPM rain from the past 7 days. A nowcast is issued "when rainfall is considered to be extreme and susceptibility values are moderate to very high". Retrospective moderate- and high-hazard nowcasts coincided with a catalogued landslide up to 60% of the time [S]. — [PMC6839699](https://pmc.ncbi.nlm.nih.gov/articles/PMC6839699)
  - Susceptibility: Stanley & Kirschbaum (2017), *Natural Hazards* 87:145–164, a heuristic fuzzy overlay of slope, faults, geology, forest loss and road networks, evaluated against the GLC [S]. — [Springer PDF](https://link.springer.com/content/pdf/10.1007/s11069-017-2757-y.pdf)
  - v2: Stanley et al. (2021), *Frontiers in Earth Science*, doi:10.3389/feart.2021.640043. XGBoost trained on 2015–2018 and evaluated on 2019–2020, with IMERG and SMAP inputs. It was "twice as likely to predict the occurrence of historical landslides as LHASA version 1, given the same global false positive rate" [S]. — [NTRS PDF](https://ntrs.nasa.gov/api/citations/20210015014/downloads/Stanley_et_al_Frontiers_2021.pdf)
  - Resolution: the README describes LHASA 2 as ~1 km (30 arcsec), daily [V]. Stanley et al. 2025 (*JAMC* 64(10):1379–1394) found better satellite precipitation algorithms "slightly improved" landslide hazard assessment [V, README citation]. — [nasa/LHASA README](https://github.com/nasa/LHASA)
- **NASA Global Landslide Catalog (GLC):**
  - data.nasa.gov lists "License not specified", access level public, and "To export GLC data, you must agree to the 'Terms and Conditions'". It requests citation of Kirschbaum et al. 2010 (*Natural Hazards*, doi:10.1007/s11069-009-9401-4) and Kirschbaum, Stanley & Zhou 2015 (*Geomorphology*, doi:10.1016/j.geomorph.2015.03.016). It says the export is "current as of March 7, 2016" [V]. — [data.nasa.gov GLC export](https://data.nasa.gov/dataset/global-landslide-catalog-export)
  - The legacy CSV downloaded with **no login and no click-through** in this session (8.48 MB, 11,033 records). Its event dates actually run 1988-11-07 to **2017-09-28**, which conflicts with the "March 7, 2016" statement [V, computed]. — [CSV](https://data.nasa.gov/docs/legacy/Global_Landslide_Catalog_Export/Global_Landslide_Catalog_Export_rows.csv)
- **COOLR** (Cooperative Open Online Landslide Repository, which continues the GLC):
  - Download is via the Landslide Viewer, where users tick "I agree to the above terms and conditions". Downloading means accepting the "NASA GLC Permission to Use, Reproduce, and Distribute" [S].
  - The ArcGIS service metadata carries an Apache-style "Permission to Use, Reproduce, and Distribute" text (perpetual, worldwide, royalty-free) [S].
  - The ArcGIS REST endpoints cited in search results returned HTTP 404 in this session [V].
  — [COOLR exporting guide PDF](https://gpm.nasa.gov/landslides/guides/COOLRGuide_Exporting.pdf); [gpm.nasa.gov COOLR page](https://gpm.nasa.gov/applications/landslides/coolr)
- NASA's general data policy: "NASA Earth Science Data: Yours to Use, Fully and Without Restrictions". Data are available to any user for any purpose, including private industry, with listed exceptions under SPD-41a [S]. — [Earthdata article](https://earthdata.nasa.gov/learn/articles/nasa-earth-science-data-yours-use-fully-and-without-restrictions); [Earthdata data and information policy](https://www.earthdata.nasa.gov/data-and-information-policy)

### Inferences
- **LHASA code is usable but not a preferred licence.** NOSA 1.3 is royalty-free and allows commercial use, so the code itself is not disqualified. But it is not MIT/Apache/BSD, has copyleft-like file obligations, and the FSF considers it non-free and GPL-incompatible [A, not verified this session]. Treat it as **"usable with obligations; not preferred"**.
- **Running LHASA v2 is disqualified, and wouldn't help anyway.** It needs an Earthdata login and IMERG via PPS registration. Even if run, the released code cannot be retrained on Talisay data.
- **LHASA v1 logic can be re-implemented, not reused.** The v1 rule (7-day antecedent rain above a local 95th percentile AND susceptibility moderate or higher) can be rebuilt from the published description with NASA POWER or CHIRPS rain. GeoAlert would not need the NOSA code or IMERG, and the README explicitly encourages local thresholds and susceptibility. It makes a good second baseline next to the Dynaslope-style return-period rule.
- **LHASA v2 outputs could serve as an external check.** The NCCS datashare needs no login. But it is best-effort, has "frequent server downtime", and its archive sits behind GES DISC [A: GES DISC requires an Earthdata login]. At ~1 km it gives roughly a few dozen cells over Talisay [A: area-based estimate]. Use it only as a validation comparison, never as a dependency.
- **The GLC is the most valuable free dataset found, but it is not licence-cleared.** It has no explicit licence; NASA's general policy says "without restrictions"; the viewer has a click-through. Classification: **"no account needed; licence implicit, not explicit; needs written confirmation before commercial redistribution"**. Internal use to train or validate a model, without republishing the records, is lower risk [A, not legal advice].

### Gaps
- The full text of the COOLR "Permission to Use, Reproduce, and Distribute" was not retrieved (the REST endpoints returned 404).
- It was not confirmed whether COOLR holds post-2017 Talisay records; the live viewer export needs the click-through.
- The OSI-approval and FSF status of NOSA 1.3 were not re-verified this session.

### Disqualified or not-cleared items (this section)
| Item | Status | Reason |
|---|---|---|
| Running LHASA v2 (nasa/LHASA) | **Disqualified** | Needs NASA Earthdata login (`.netrc`) and PPS registration for IMERG [V, README] |
| NASA IMERG (any version) | **Disqualified** | Earthdata/PPS account required [V for the PPS path in the LHASA README; project rule] |
| SMAP L4 soil moisture (LHASA v2 input; Abancó 2021) | **Disqualified** | Earthdata login [A] |
| GES DISC LHASA archive | **Disqualified** | Earthdata login [A] |
| LHASA code itself | Usable, not preferred | NOSA 1.3: royalty-free, commercial use allowed, copyleft-like obligations [V] |
| NASA GLC / COOLR records | Conditional | No login for the legacy CSV [V]; no explicit licence [V]; viewer click-through T&C [S] |

---

## 5. Spatiotemporal landslide modelling (where × when; Lombardo 2020; slope-unit Bayesian INLA; hazard = susceptibility × trigger probability)

### Takeaway
The accepted framing is landslide hazard = P(where | static terrain) combined with P(when | trigger). It is either multiplied (LHASA; GeoAlert's current LR × terrain exposure) or fitted jointly (Lombardo et al. 2020's Bayesian space-time log-Gaussian Cox process on slope units, fitted with INLA). With 8 events, a joint latent space-time model is not identifiable. The defensible version is a separable model: fit timing on a regional landslide-day series (more events), fit or fix place with a terrain prior, and add partial pooling only through informative priors.

### Cited Findings
- Lombardo, Opitz, Ardizzone, Guzzetti & Huser (2020), "Space-time landslide predictive modelling", *Earth-Science Reviews* 209:103318, doi:10.1016/j.earscirev.2020.103318 [S]:
  - Area of 79 km² split into 889 slope units, with a 3,379-landslide multi-temporal inventory grouped into six periods.
  - A Bayesian Log-Gaussian Cox Process framework compared five models of increasing complexity, the most complex with latent spatial dependence between neighbouring slope units.
  - Spatial skill tested by 10-fold CV, temporal skill by leave-one-out.
  - Keywords include INLA and slope unit.
  — [HAL open-access PDF](https://hal.inrae.fr/hal-03164998v1/document); [arXiv 1912.01233](https://pdf.arxiv.org/pdf/1912.01233)
- **R-INLA:** the hrue/r-inla repository LICENSE is an MIT-style permission text ("Copyright 2025 Haavard Rue Permission is hereby granted, free of charge…") [V]. — [r-inla LICENSE](https://raw.githubusercontent.com/hrue/r-inla/master/LICENSE)
- LHASA v1 is an operational example of the multiplicative/decision-tree form: extreme 7-day rain AND moderate-to-very-high susceptibility gives a nowcast [S]. — [Kirschbaum & Stanley 2018, PMC6839699](https://pmc.ncbi.nlm.nih.gov/articles/PMC6839699)
- Jones et al. 2023 report "some time dependency between typhoons" and tentatively "possible spatial dependency" in Philippine susceptibility models [S]. — [NHESS 23:1095](https://nhess.copernicus.org/articles/23/1095/2023/)
- Python Bayesian tools with permissive licences: PyMC (Apache-2.0) and Bambi (MIT) [V, section 1 links].

### Inferences
- **Fit timing regionally.** All 22 barangays share one NASA POWER cell, so GeoAlert's rain covariates carry **no spatial information**. Every barangay sees the same rain on the same day. The timing model is therefore really a *city-wide* "is today a landslide day?" model. Fitting it on a regional landslide-day series (Talisay plus neighbouring upland Cebu City and Minglanilla records from the GLC, section 6) is legitimate and multiplies the number of positive days.
- **Allocate the daily probability across barangays by susceptibility.** Recommended structure: P(any landslide in the Talisay uplands on day t | rain) × share(barangay b | landslide day), where the share comes from a terrain-based susceptibility with a weak prior. This keeps the 7-of-8 Manipis concentration from being learned as pure "Manipis-ness".
- **Partial pooling helps only with an informative prior.** A barangay random effect (PyMC/Bambi, or INLA) fitted on 8 events would mostly encode "Manipis". The terrain covariate should carry the place signal, and the random effect should be given a tight prior so it shrinks toward the terrain prediction.
- **Treat a reporting-bias signal as exposure.** The concentration in Manipis may partly reflect reporting along the Manipis road: several GLC titles name the road, and news reports describe repeated closures (section 6). Distance to road (OSM) as an exposure or detection covariate is better than letting the model attribute it to terrain.

### Gaps
- No published space-time landslide model for a Philippine city with fewer than ~20 events was found.
- Lombardo et al. 2020's covariates and performance numbers were not read in full.

---

## 6. Philippine and Cebu context (MGB geohazard maps, Naga 2018, Cebu inventories, NOAH, Talisay-specific)

### Takeaway
The single most useful Cebu-specific finding is that the **NASA GLC already holds ~13 landslide records in Talisay City (Cebu) on 11 dates in 2010–2016, 5 of them in Manipis, and 74 records on 51 dates within 20 km**. Those 51 dates, against GeoAlert's 8, give a timing model about six times as many event days, using the same free NASA POWER rain. Official MGB 1:10,000 maps and NOAH maps exist as reference layers, but neither is a clean, explicitly licensed, commercial-use dataset. The Naga 2018 disaster was a quarry-adjacent rockslide-debris avalanche, not a model for shallow rain-triggered slides.

### Cited Findings
- **GLC records near Talisay** [V, computed in this session from the legacy CSV](https://data.nasa.gov/docs/legacy/Global_Landslide_Catalog_Export/Global_Landslide_Catalog_Export_rows.csv):
  - Within 20 km of an assumed Talisay centre (10.244 N, 123.849 E [A]): **74 records on 51 distinct dates, 2007–2017**.
  - Location accuracy: exact 3, 1 km 12, 5 km 30, 10 km 16, 25 km 13.
  - Triggers: downpour 36, rain 19, tropical_cyclone 10, continuous_rain 6, unknown 2, construction 1.
  - Records per year: 2007: 2, 2008: 4, 2009: 2, 2010: 17, 2011: 12, 2012: 6, 2013: 12, 2014: 6, 2015: 1, 2016: 7, 2017: 5.
  - **Talisay City (Cebu) records**, identified by text matching on place names:

    | Date | Place named in the record | Note |
    |---|---|---|
    | 2010-08-24 | Lagtang / Lawaan-3 sitios (Burlas, Crasher, Tiguib) | 3 records |
    | 2010-10-18 | sitio Telepono, barangay Manipis | |
    | 2010-12-10 | Lawaan | |
    | 2011-10-12 | Lower Kaduldolan | |
    | 2012-10-25 | "Talisay City" | trigger: tropical cyclone |
    | 2013-08-14 | Sitio Tangub, Lagtang | trigger: construction |
    | 2014-09-17 | Manipis | trigger: tropical cyclone |
    | 2014-10-19 | Sitio Caduldulan, Lawaan 3 | geocoded to Minglanilla |
    | 2016-08-01 | Manipis | |
    | 2016-09-08 | "Landslide on Manipis Road" | |
    | 2016-10-07 | Manipis | |

    That is about 13 records on 11 dates, and **Manipis has 5 records on 5 dates**.
  - Name trap: a record "Sitio Camp 5, Talisay City" (2012-09-05, 10.747 N 122.967 E) is Talisay, **Negros Occidental** and must be excluded.
  - Several Cebu-Talisay points carry a wrong admin region ("Western Visayas"), so the coordinates and text, not the admin field, should be trusted.
  - Philippine records by year in the export: 2007: 37 … 2011: 146 … 2016: 51.
- **MGB geohazard maps:**
  - The 1:10,000 landslide and flood maps were posted "for free viewing and download" as JPEG at 150 dpi via the MGB website / Geohazard Web Portal [S, 2015 news]. — [MGB news item 303](https://mgb.gov.ph/en/2015-05-13-02-02-11/mgb-news/303-mgb-s-geohazard-maps-nowviewable-and-downloadable-)
  - MGB-7 points LGUs to www.mgb.gov.ph or gdis.mgb.gov.ph/mgbpublic. The National Geohazard Assessment Program completed 1:10,000 assessments of 1,634 cities and municipalities by 2014 [S]. — [MGB-7 article](https://r7.mgb.gov.ph/mgb-7-encourages-lgus-to-utilize-geohazard-maps/)
- **Talisay assessments:**
  - A Feb–Mar 2012 MGB-7 1:10,000 assessment found 77% of Talisay's 22 barangays at high risk of landslides or flooding. Highly susceptible sitios were listed in Camp 4, Manipis and Tapul [S]. — [Philstar 2012-09-10](https://www.philstar.com/cebu-news/2012/09/10/847422/talisays-landslide-and-flood-prone-areas-identified); [MGB-7 PR Sept 2012](https://r7.mgb.gov.ph/pr-08-september-2012)
  - A 2018 follow-up reported 33 landslide-prone sitios in 4 barangays (14,662 residents), including 10 sitios in Campo IV (3,480 people) and 5 in Manipis (2,588) [S; the specific article was not opened]. — [Cebu Daily News](https://cebudailynews.inquirer.net/?p=195696)
- **Repeated Manipis road events:** MGB-7 urged relocation after boulders hit homes (2014) and recommended engineering intervention for Manipis (2016). The Manipis road was closed after slides. Continuous rains triggered landslides in Talisay in July 2022, including Sitio Langoyon, Manipis [S]. — [Philstar 2014-08-30](https://philstar.com/metro-cebu/2014/08/30/1363433/landslide-spot-still-unstable-risky); [Philstar 2016-02-01](https://philstar.com/metro-cebu/2016/02/01/1548845/talisay-landslide-prone-areas-warned); [Inquirer: Manipis road closure](https://newsinfo.inquirer.net/1510430/landslide-prompts-closure-of-upland-manipis-road-in-talisay/amp); [ABS-CBN 2022-07-13](https://www.abs-cbn.com/news/07/13/22/continuous-rains-trigger-more-landslides-in-parts-of-cebu)
- **Philippine government works and copyright:** under RA 8293 Section 176.1, no copyright subsists in Philippine government works, "but prior approval of the government agency or office wherein the work is created shall be necessary for exploitation of such work for profit". The agency may impose conditions such as royalties [S]. — [NDV Law commentary](https://ndvlaw.com/does-copyright-subsist-in-works-of-the-government/)
- **Naga City, Cebu (20 Sept 2018):** Lagmay et al. (2020), "Anatomy of the Naga City Landslide", *Frontiers in Earth Science*, doi:10.3389/feart.2020.00312 [S]:
  - Sitio Sindulan, Barangay Tinaan; 78 dead, 18 injured, 6 missing.
  - Classified as a rockslide-debris avalanche in the largely uncemented Carcar and Barili formations.
  - Most fatalities ~1.2 km from a 200 m headscarp; fractures were seen about a month earlier.
  - MGB-7 noted limestone cracks at an adjacent quarry tenement.
  — [Frontiers article](https://www.frontiersin.org/articles/10.3389/feart.2020.00312); [MGB-7 2018-09-23](https://r7.mgb.gov.ph/2018/09/23)
- **UP NOAH:**
  - Hazard maps are described as downloadable shapefiles under the **Open Data Commons Open Database License (ODbL)** with attribution. Landslide layers: shallow landslide susceptibility (SINMAP), structurally controlled (Matterocking, Conefall), debris flow/alluvial fan (Flow-R), as one ZIP per province [S; both sources are secondary].
  - The official noah.up.edu.ph page fetched in this session showed only its title, so the licence statement was not seen on the official domain [V].
  — [Space Climate Observatory profile](https://www.spaceclimateobservatory.org/noah); [Hugging Face mirror (BetterGov.PH, unofficial)](https://huggingface.co/datasets/bettergovph/project-noah-hazard-maps); [NOAH](https://noah.up.edu.ph/know-your-hazards)
- **Cebu Province susceptibility study** (ISPRS Annals 2026, news-derived inventory 2009–2023; section 1) [V]. — [ISPRS Annals](https://isprs-annals.copernicus.org/articles/X-5-W4-2025/377/2026/)

### Inferences
- **Use the GLC to extend timing data and as an independent test.** The 2010–2016 Talisay records fall before GeoAlert's 2021–2025 window. NASA POWER daily rain covers those years [A, POWER daily record starts in 1981]. They can be used (a) to **test the existing model out of period**, which is the strongest honest check available, and (b) as extra positives for the timing model. Records at 5–25 km accuracy should be used for timing (regional landslide-day) only, not for barangay placement, unless the text names the barangay.
- **The GLC supports Manipis as a hotspot independently.** 5 GLC records in Manipis from 2010–2016, plus repeated road closures, back up the 2021–2025 concentration. But road-related reporting (two records explicitly name the road) points to detection bias along the road, which is consistent with the exposure argument in section 5.
- **MGB maps: reference/validation layer only.** They are the authoritative local susceptibility zoning, but only JPEG rasters (150 dpi) and not vectors. Under RA 8293 §176, use "for profit" needs MGB approval. For a city DRRMO (government, non-profit) this is likely fine [A]. For a commercial redistribution it fails the "no hidden restrictions" test. Note: the project's memory records that an "official hazard maps" feature was cancelled by the user on 2026-11-05. Using MGB maps purely as a validation reference is different, but should be cleared with the user first.
- **NOAH under ODbL is free for commercial use, with share-alike.** Any public derived *database* must also be ODbL. Its SINMAP shallow-landslide layer is a ready physically based reference for Talisay [A: Cebu inclusion not confirmed]. Confirm the licence on the official NOAH download page before use.

### Gaps
- No peer-reviewed landslide inventory or study specific to Talisay City was found. The MGB-7 2012 report itself (sitio-level table) was not retrieved.
- It was not confirmed whether the NOAH landslide shapefiles cover Cebu, or which licence the official NOAH site states.
- No Cebu-specific rainfall threshold was found.
- The geology of Talisay's uplands (whether the Carcar/Barili formations or others underlie Manipis/Camp IV) was not established.

---

## 7. Additional free, no-account input data, and the consolidated licence/access register (data and code)

### Takeaway
Verified free, no-account inputs that meet the project's rules:
- **Copernicus DEM GLO-30** (free licence with attribution, AWS no-sign).
- **SoilGrids 2.0** (CC BY 4.0, anonymous WebDAV; REST API paused).
- **ESA WorldCover** (CC BY 4.0, AWS no-sign).
- **Sentinel-2 L2A via Element84 Earth Search** (no account; Copernicus free-and-open terms).
- **CHIRPS v3 daily** (0.05 degrees, 1981–present, no login).
- **NASA global landslide susceptibility map** (no login).
- **OSM roads** (ODbL).

GLiM's licence is unverified and its open grid is too coarse.

### Cited Findings
- **Copernicus DEM GLO-30** (licence PDF read) [V]:
  - Rights: "The rights granted under this Licence are worldwide and without limitation in time … reproduction; distribution; communication to the General Public; adaptation, modification and combination with other data", and "The use rights granted under this licence are free of charge to the User".
  - Required notices: "© DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018 provided under COPERNICUS by the European Union and ESA; all rights reserved", or for modified data "produced using Copernicus WorldDEM-30 …".
  - Users "must accept the terms" (acceptance, not registration).
  - The N10 E123 tile in the public `copernicus-dem-30m` S3 bucket returned HTTP 200 without credentials [V].
  - Search results note two countries' tiles are excluded from the public release [S].
  — [Licence PDF](https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/Data/DEM/resources/license/License-COPDEM-30.pdf); [AWS registry](https://registry.opendata.aws/copernicus-dem/)
- **SoilGrids 2.0:** "The SoilGrids maps are publicly available under the CC-BY 4.0 License" [V]. The WebDAV index at files.isric.org/soilgrids/latest/data/ answered as "Authenticated user: 'anonymous'" [V]. The **REST API is paused**: "we are currently experiencing issues with the REST API for SoilGrids, and have decided to temporarily pause the service … still under active development (beta stage)" [V]. — [ISRIC SoilGrids docs](https://docs.isric.org/globaldata/soilgrids/); [WebDAV](https://files.isric.org/soilgrids/latest/data/)
- **ESA WorldCover** 10 m (2020 v100, 2021 v200): "provided free of charge, without restriction of use", CC BY 4.0 [V]. Account-free download via `aws s3 sync s3://esa-worldcover/v200/2021/map … --no-sign-request` or Zenodo [V]. The InputQuality layer needs login options [V]. — [ESA WorldCover data access](https://esa-worldcover.org/en/data-access)
- **Sentinel-2 L2A (for NDVI)** via Element84 Earth Search STAC, no account [V]:
  - A query for Jan–Mar 2025 over Talisay matched 18 scenes (tile 51PWM), with public COG assets on `sentinel-cogs.s3.us-west-2.amazonaws.com`.
  - The collection's licence field is "proprietary", linking to the Sentinel Data Legal Notice [V].
  - The Copernicus programme's data policy "ensures access on a full, open and free-of-charge basis as a rule" [V, quoted in the Copernicus DEM licence preamble].
  — [Earth Search STAC](https://earth-search.aws.element84.com/v1/collections/sentinel-2-l2a); [Sentinel Data Legal Notice](https://sentinel.esa.int/documents/247904/690755/Sentinel_Data_Legal_Notice)
- **CHIRPS v3 daily** (readme read) [V]:
  - 0.05 degree grid. "rnl" (ERA5-disaggregated) runs 1981–present; "sat" (IMERG-Late-disaggregated) runs 1998–present. The preliminary daily product uses "sat".
  - **"Daily CHIRPS is therefore not an independent daily product"**: daily values split pentadal totals, can create "artificial wet-day sequences", and "Daily extremes are pentadal amounts redistributed".
  - CHIRPS v2's last month of operation will be December 2026.
  - The HTTPS directory lists without login [V].
  - Licence: the CHC site states CHIRPS3 is under CC BY 4.0 [S]; CHIRPS v2 is listed as public domain on Earth Engine and NOAA ERDDAP [S].
  — [CHIRPS v3 daily readme](https://data.chc.ucsb.edu/products/CHIRPS/v3.0/daily/readme.txt); [CHC CHIRPS page](https://chc.ucsb.edu/node/497); [NOAA ERDDAP CHIRPS](https://coastwatch.pfeg.noaa.gov/erddap/griddap/chirps20GlobalDailyP05.html)
- **NASA global landslide susceptibility map (1 km):** no-login download [V], from Stanley & Kirschbaum 2017 [S]. — [GeoTIFF](https://gpm.nasa.gov/sites/default/files/downloads/global-landslide-susceptibility-map-2-27-23.tif)
- **GLiM** (Hartmann & Moosdorf 2012, *G-Cubed* 13:Q12004): 1,235,400 polygons from 92 regional maps. PANGAEA hosts a coarse (0.5 degree) grid; full-resolution GIS files are linked via Dropbox. **Licence not confirmed** [S]. — [PANGAEA](https://doi.pangaea.de/10.1594/PANGAEA.788537); [CSDMS](https://csdms.colorado.edu/wiki/Alldata:GLiM)
- **Terrain derivative tools:** WhiteboxTools **MIT** (TWI, curvature, flow accumulation, distance to streams) [V]; pysheds **GPL-3.0** [V]; GRASS **GPL-2+** [V]. — [WhiteboxTools LICENSE.txt](https://raw.githubusercontent.com/jblindsay/whitebox-tools/master/LICENSE.txt); [pysheds LICENSE](https://raw.githubusercontent.com/mdbartos/pysheds/master/LICENSE); [GRASS COPYING](https://raw.githubusercontent.com/OSGeo/grass/master/COPYING)
- **OpenStreetMap** roads: ODbL 1.0 [A: not re-fetched this session]. — [OSM copyright](https://www.openstreetmap.org/copyright)

### Consolidated licence/access register

Primary candidates:

| Item | Licence | Account/key? | Verdict |
|---|---|---|---|
| scikit-learn | BSD-3 [V] | No | Cleared |
| statsmodels | BSD-3 style [V] | No | Cleared |
| XGBoost | Apache-2.0 [V] | No | Cleared (not recommended for 8 events) |
| PyMC | Apache-2.0 [V] | No | Cleared |
| Bambi | MIT [V] | No | Cleared |
| R-INLA | MIT-style LICENSE [V] | No [A] | Cleared [A: optional PARDISO solver has its own licence, not needed] |
| Landlab | MIT [V] | No | Cleared |
| WhiteboxTools | MIT [V] | No | Cleared |
| TRIGRS | Public domain (USGS) [V] | No | Cleared |
| GRASS GIS / r.shalstab | GPL-2+ [V] | No | Cleared for offline layer production (copyleft) |
| sperrorest | GPL-3 [V] | No | Cleared for offline evaluation (copyleft) |
| pysheds | GPL-3 [V] | No | Copyleft; prefer WhiteboxTools |
| Copernicus DEM GLO-30 | Free Copernicus licence with attribution [V] | No [V] | Cleared |
| SoilGrids 2.0 | CC BY 4.0 [V] | No (WebDAV) [V] | Cleared; REST API paused |
| ESA WorldCover | CC BY 4.0 [V] | No (S3/Zenodo) [V] | Cleared |
| Sentinel-2 L2A (Earth Search) | Copernicus free/open legal notice [V link; terms A] | No [V] | Cleared [A on exact terms] |
| CHIRPS v3 | CC BY 4.0 [S] | No [V] | Cleared, pending check of the licence text |
| NASA POWER | CC BY 4.0 (project's prior check) | No | Cleared (already in use) |
| NASA global susceptibility map | NASA open data policy [S] | No [V] | Cleared [A: no explicit file licence] |
| OSM | ODbL [A] | No | Cleared (share-alike for derived databases) |

Conditional or not cleared:

| Item | Status | Reason |
|---|---|---|
| LHASA code | Usable, not preferred | NOSA 1.3 [V] |
| NASA GLC / COOLR | Conditional | No explicit licence [V]; click-through T&C [S] |
| UP NOAH maps | Conditional | ODbL per secondary sources only [S] |
| MGB 1:10,000 maps | Conditional | Gov work; prior approval needed for profit (RA 8293 §176) [S]; JPEG only |
| CTRL-T | **Not cleared** | No licence stated [V] |
| r.slope.stability | Not cleared | Licence unverified; not in grass8 add-ons [V] |
| GLiM | Not cleared | Licence unverified [S] |
| SINMAP/TauDEM | Not cleared | Not verified |

Disqualified (account, token or paid access needed):

| Item | Reason |
|---|---|
| IMERG | Earthdata/PPS [V via the LHASA README] |
| Running LHASA v2 | Earthdata + PPS [V] |
| SMAP | Earthdata [A] |
| GES DISC archives | Earthdata [A] |
| ERA5 via Copernicus CDS | Account [A] |
| GSMaP (JAXA) | Registration [A] |
| SoilGrids via Google Earth Engine | Account [A] |
| ESA WorldCover InputQuality layer | Login [V] |
| Open-Meteo | Non-commercial free tier; excluded by the project |

### Inferences
- **The best new terrain covariates are free and cleared.** From the Copernicus DEM, using MIT WhiteboxTools: plan/profile curvature, TWI, distance to streams and relief. Add distance to OSM roads (road cuts, and a reporting-bias proxy) and WorldCover class (cleared land vs tree cover). These are the same predictor family that Jones et al. 2023 and the Cebu ISPRS study used. Use them in a penalised LR (LASSO, or a ridge prior in PyMC) to avoid overfitting 8–20 positives.
- **CHIRPS v3 is the only no-account rain upgrade found, with a catch.** It is 0.05 degrees (about 5.5 km [A]) vs POWER's ~0.5 degrees, so it could give Talisay's uplands and lowlands different rain series. But its daily values are pentad totals redistributed by ERA5/IMERG, so day-level timing, which is what GeoAlert models, is no better than the disaggregating reanalysis. Use it as a **sensitivity test** (do multi-day sums from CHIRPS predict better than POWER's?), not as an automatic replacement. Its 3–14-day sums are more trustworthy than its same-day values.
- **SoilGrids adds little.** At 250 m with wide uncertainty it is a weak predictor for a 40 km²-scale city [A]. It is useful mainly if a physical model (Landlab) is attempted.

### Gaps
- The CHIRPS v3 licence text was not read on the CHC data server itself.
- The exact Sentinel Data Legal Notice text was not opened.
- No Philippine geological map with an explicit open licence and vector format was found for Cebu (MGB geologic maps were not located online).

---

## 8. Given 8 events (7 in Manipis), what improves GeoAlert's landslide prediction most defensibly?

### Takeaway
In order of defensibility:
1. Add the ~13 Talisay and ~74 nearby NASA GLC records (2007–2017) to get more landslide days and an out-of-period test.
2. Restructure into a city-wide timing model fitted on a regional landslide-day series, times a terrain-based allocation across barangays.
3. Benchmark against two inventory-free rules: a Dynaslope-style 2-year return-period daily threshold and an LHASA-v1-style 95th-percentile 7-day rule.
4. Add a small set of cleared terrain/exposure covariates in a penalised or Bayesian LR with strong priors.

Better rain data (CHIRPS v3) and physical models are second-order. ML upgrades (RF/XGBoost/CNN/neural networks) are not defensible.

### Cited Findings
- Reliable empirical thresholds need many events: about 175 for under 10% uncertainty, per Peruccacci et al. 2012 as cited [S]. — [Rossi et al. 2017 post-print](https://research.unipg.it/bitstream/11391/1406843/5/Rossi_et_al_2017_post_print.pdf)
- Under-counting landslides significantly degrades threshold performance (Gariano et al.) [S]. — [CNR-IRPI repository](https://geomorphology.irpi.cnr.it/publications/repository/public/journals/2019/gariano-et-al-2019-howmuchdoestherainfalltemporalresolutionaffectrainfallthresholds.pdf)
- Multi-event pooled LR transfers better than single-event models (1–3% vs 6–10% loss) [S]. — [Jones et al. 2023](https://nhess.copernicus.org/articles/23/1095/2023/)
- LR generalises better than tree methods outside the training area [V, abstract]. — [Brenning 2005](https://nhess.copernicus.org/articles/5/853/2005/)
- Non-spatial CV can overstate performance by up to 47% [S]. — [Schratz et al. 2019](https://econpapers.repec.org/RePEc:eee:ecomod:v:406:y:2019:i:c:p:109-120)
- The GLC holds ~13 Talisay records on 11 dates (2010–2016) and 74 records on 51 dates within 20 km, downloadable without login [V, computed]. — [GLC CSV](https://data.nasa.gov/docs/legacy/Global_Landslide_Catalog_Export/Global_Landslide_Catalog_Export_rows.csv)
- The Dynaslope operational threshold uses one-day rain with a 2-year return period [S]. — [ResearchGate](https://www.researchgate.net/publication/394425059_Bias_Correction_of_Real-Time_GSMaP_Satellite-Retrieved_Rainfall_Data_in_the_Context_of_Landslide_Monitoring_and_Early_Warning)
- LHASA v1 combines 7-day rain extremes with susceptibility, and its README encourages local thresholds and susceptibility [V]. — [nasa/LHASA](https://github.com/nasa/LHASA)
- Thresholds must be derived from the same rain source used operationally, and generic or other-site thresholds failed in Benguet [V]. — [Abancó et al. 2021](https://nhess.copernicus.org/articles/21/1531/2021/)

### Inferences

**Recommended plan for GeoAlert, ranked by expected gain per unit of risk.** All steps use only cleared or conditional free sources, CPU only.

1. **External events: out-of-period validation first, then training.**
   - Pull the GLC legacy CSV and filter to Talisay plus adjacent upland barangays (Cebu City's Kalunasan, Buhisan, Sapangdaku, Pamutan, Tabunan, Busay; Minglanilla), keeping only records whose text names a place and whose date is exact.
   - Join to NASA POWER daily rain for 2007–2017.
   - First, score the *existing* 2021–2025 model on these unseen years (timing AUC and Brier on landslide-days vs all other days). This is the most honest test GeoAlert can run.
   - Then refit with the extra days. Mark the GLC as "licence implicit (NASA policy), records not republished" until NASA confirms terms.
2. **Separate "when" from "where".**
   - Timing: logistic or complementary log-log regression for P(≥1 landslide in the Talisay/Metro Cebu uplands on day t) on 1/3/7/14-day POWER sums. This has roughly 50+ positive days instead of 8.
   - Place: allocate across barangays with a terrain-share model, e.g. P(b | landslide day) ∝ exp(β·terrain_b), with β fitted, or given a strong prior, from the pooled 2007–2025 barangay-named events.
   - This mirrors LHASA's structure and the hazard = susceptibility × trigger framework, while staying identifiable.
3. **Benchmarks that need no inventory.**
   - (a) 1-day (and 3-day) POWER rain above the 2-year return level, and above half of it (Dynaslope style).
   - (b) 7-day antecedent rain above the local 95th percentile, gated by terrain exposure (LHASA v1 style).
   - Report whether the fitted model beats them on the same days. If it does not, the rules are the safer operational alert tiers.
4. **Terrain beyond slope share, kept small.**
   - Add 2–4 cleared covariates: plan curvature or convergence (WhiteboxTools), TWI, distance to OSM road (cuts and detection bias), WorldCover tree-cover share.
   - Fit with LASSO (scikit-learn/statsmodels) or a PyMC/Bambi logistic model with weakly informative priors. Evaluate with leave-one-barangay-out and leave-one-year-out CV, and report the positives in each fold.
5. **Bayesian pooling, carefully.** A barangay random intercept with a tight prior centred on the terrain prediction (PyMC/Bambi or R-INLA) gives honest uncertainty bands for barangays with zero recorded events (Tapul, Jaclupan), instead of near-zero point estimates. Do not let it absorb the Manipis concentration freely: 7/8 events in one barangay would make the random effect a "Manipis indicator".
6. **Rain-data sensitivity test, not a swap.** Compare CHIRPS v3 (0.05 degrees, rnl and sat variants) multi-day sums against POWER on the same events. Keep POWER unless CHIRPS clearly improves out-of-period skill, because CHIRPS daily timing is synthetic within pentads.
7. **Reference maps for sanity checks only.** Compare the barangay ranking with the NASA global susceptibility map (no login), MGB 1:10,000 zones (JPEG, gov-work approval caveat; check with the user given the cancelled official-maps feature) and NOAH SINMAP layers (ODbL, if Cebu is covered). Disagreement is a flag, not a training signal.
8. **Not recommended now.**
   - RF/XGBoost/CNN/neural networks for either susceptibility or timing (too few events; Brenning 2005).
   - CTRL-T (no licence; hourly data needed).
   - TRIGRS/SHALSTAB as main models (no geotechnical data).
   - Running LHASA v2 (account required; cannot retrain).
   - Importing Benguet/Albay threshold numbers (site- and data-specific; Abancó 2021).

**Statistical caution on current metrics.** With 8 positives, an AUC of 0.80 or 0.96 has a wide sampling interval [A: standard AUC variance reasoning; not computed here]. GeoAlert's reports should show bootstrap confidence intervals and per-event predicted probabilities, so DRRMO users see how thin the evidence is.

### Gaps
- No study was found that quantifies how much external-inventory pooling improves a city-scale timing model with fewer than 20 local events. The ranking above is reasoned from the cited evidence, not measured.
- It is unknown whether GeoAlert's 8 events overlap any COOLR records after 2017, and whether COOLR holds 2018–2025 Talisay records. That needs the viewer download and its click-through terms.
- The 2-year return-level values for Talisay from NASA POWER were not computed in this session.
