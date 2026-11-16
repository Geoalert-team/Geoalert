# Spatial, spatiotemporal and Bayesian hierarchical models for GeoAlert (fire, flood, landslide), with verified licences

Research date: 2026-11-13. Evidence labels used below:
- **[V]** verified this session from the primary page, a LICENSE/DESCRIPTION file, or source code.
- **[S]** taken from an abstract or a search-result summary of the abstract; I did not read the full text.
- **[A]** assumed or from prior knowledge; not re-checked this session.

GeoAlert facts (from the project's 2026-11-13 model report, given in the brief): 22 barangays. Flood/landslide unit is the barangay-day (40,172 rows, 2021-2025). Flood has 18 positives on only 5 storm days; landslide has 8 positives (7 in Manipis, 1 in Camp IV). Fire is 219 fires since 2023-01, modelled per barangay-month. Fire Poisson GLM: Brier 0.140, which is not significantly better than a plain per-barangay average. The neighbours term had an uncertain gain (Brier 0.1380 vs 0.1394, interval -0.0040 to +0.0010). Flood leave-one-barangay-out (LOBO) AUC is 0.36; landslide 0.90.

---

## Q1. Bayesian hierarchical / multilevel models with partial pooling (BYM, BYM2, Leroux, Knorr-Held space-time): behaviour with very few events, priors, implementations

### Takeaway
BYM2 is the standard modern areal model. It is a Poisson or binomial GLM plus one barangay random effect, split into a structured (ICAR neighbour) part and an unstructured part, with interpretable penalised-complexity (PC) priors. The literature says it shrinks well, but that the data alone cannot pick the form and amount of spatial correlation, and that spatial random effects can distort covariate effects. With 22 areas and about 219 fires, the real gain to expect is stabilised per-barangay rates with honest intervals, not sharper discrimination. All the main Python implementations (PyMC, NumPyro, Stan via CmdStanPy) use permissive licences.

### Cited Findings
**Model family and theory**
- BYM is from Besag, York & Mollié (1991), "Bayesian image restoration, with two applications in spatial statistics", *Ann. Inst. Stat. Math.* 43:1-20 [V citation] — [OpenAlex/DOI](https://doi.org/10.1007/BF00116466)
- The Leroux CAR model (Leroux et al. 2000) and the "localised" CAR model (Lee et al. 2015) are both implemented in CARBayes, alongside BYM [V, CARBayes DESCRIPTION] — [CARBayes DESCRIPTION](https://raw.githubusercontent.com/duncanplee/CARBayes/master/DESCRIPTION); Leroux DOI [10.1007/978-1-4612-1284-3_4](https://doi.org/10.1007/978-1-4612-1284-3_4)
- Riebler, Sørbye, Simpson & Rue (2016), *Statistical Methods in Medical Research* 25:1145-1165:
  - In classical BYM "the spatially structured component cannot be seen independently from the unstructured component", which makes hyperpriors hard to set.
  - The BYM2 reparameterisation scales the ICAR component so that hyperpriors become interpretable and "transferable between spatial applications with different graph structures".
  - It uses PC priors.
  - In simulation BYM2 showed "good learning abilities and good shrinkage behaviour".
  - On model-choice criteria it "performs at least equally well as existing parameterisations".
  - [S, abstract] — [DOI](https://doi.org/10.1177/0962280216660421)
- PC priors penalise departure from a simpler base model (for example, no spatial effect), are "designed to support Occam's razor" and have "excellent robustness properties" (Simpson et al. 2017, *Statistical Science*) [S, abstract] — [DOI](https://doi.org/10.1214/16-STS576)
- Wakefield (2006), *Biostatistics*:
  - Hierarchical models "can provide robust estimation of area-level risk parameters".
  - Sensitivity to the spatial model and to variance priors must be checked.
  - "Spatial ecological regression is a far more hazardous enterprise". When residual spatial dependence is modelled and the exposure is spatially structured, the estimated exposure effects change, and "the data alone cannot choose the form and extent of spatial correlation that is appropriate".
  - [S, abstract] — [DOI](https://doi.org/10.1093/biostatistics/kxl008)
- Hodges & Reich (2010), *The American Statistician* 64:325-334:
  - Adding a spatially correlated random effect is equivalent to adding a saturated set of shrunken canonical regressors, and it can change fixed-effect estimates substantially (spatial confounding).
  - They "debunk the common belief that adding a spatially-correlated random effect adjusts fixed-effect estimates for spatially-structured missing covariates".
  - Proposed fix: restricted spatial regression.
  - [S, abstract] — [DOI](https://doi.org/10.1198/tast.2010.10052)
- Knorr-Held space-time interactions. The Type IV model uses intrinsic Markov random fields with identifiability constraints. INLA handles the constraints by "conditioning by kriging", and this gets expensive as the number of areas and time points grows; the HyMiK approach is 2-4x faster (Aanes & Storvik 2023) [S, abstract] — [arXiv DOI](https://doi.org/10.48550/arxiv.2304.11851). Original reference: Knorr-Held (2000), *Statistics in Medicine* 19:2555-2567 [A, citation from memory, not fetched].
- Rare events in plain logistic regression:
  - Logistic regression "can sharply underestimate the probability of rare events"; corrections are proposed (King & Zeng 2001, *Political Analysis* 9:137-163) [S] — [DOI](https://doi.org/10.1093/oxfordjournals.pan.a004868)
  - Problems at low events-per-variable depend on more than EPV (for example total sample size). Separation can dominate results, and Firth's correction "can be used to improve the accuracy of regression coefficients and alleviate the problems associated with separation" (van Smeden et al. 2016) [S] — [DOI](https://doi.org/10.1186/s12874-016-0267-3)

**Implementations (code-level checks)**
- **Stan ICAR/BYM/BYM2 case study (Mitzi Morris)** [V]:
  - ICAR is coded as a pairwise difference, `target += -0.5 * dot_self(phi[node1] - phi[node2])`, with a soft sum-to-zero constraint `sum(phi) ~ normal(0, 0.01 * N)`.
  - BYM2 combines the parts as `sqrt(1 - rho) * theta + sqrt(rho / scaling_factor) * phi`, with priors `rho ~ beta(0.5, 0.5)` and `sigma ~ normal(0, 1)`.
  - The BYM hyperpriors depend on the average number of neighbours and "may not work so well for data with a different spatial structure". Without hyperpriors "the sampler will go very slowly or fail to fit the data altogether".
  - A disconnected graph needs special handling: 8 NYC tracts were dropped for this reason.
  - [Stan case study](https://mc-stan.org/learn-stan/case-studies/icar_stan.html); peer-reviewed version: Morris et al. 2019, *Spatial and Spatio-temporal Epidemiology* 31:100301 — [DOI](https://doi.org/10.1016/j.sste.2019.100301)
- **PyMC** has native `CAR` (proper) and `ICAR` classes in `pymc/distributions/multivariate.py`. `ICAR.dist(W, sigma=1, zero_sum_stdev=0.001)` has a built-in soft sum-to-zero constraint [V, source] — [pymc multivariate.py](https://github.com/pymc-devs/pymc/blob/main/pymc/distributions/multivariate.py)
- **PyMC BYM example** (NYC, N = 1921 tracts, 5,461 edges) [V] — [PyMC example](https://www.pymc.io/projects/examples/en/latest/spatial/nyc_bym.html):
  - It uses `pm.ICAR("phi", W=W_nyc, ...)`.
  - The BYM2 scaling factor is computed in Python from the adjacency matrix (value 0.7137 for the NYC graph).
  - Priors are `rho ~ Beta(0.5, 0.5)` and `sigma ~ HalfNormal(1)`, with a Poisson likelihood and an exposure offset.
  - The notebook notes that `pm.CAR` "scales worse" than BYM.
- **NumPyro** has a `CAR` distribution with an `is_sparse=True` option for sparse adjacency matrices [V, source] — [numpyro continuous.py](https://github.com/pyro-ppl/numpyro/blob/master/numpyro/distributions/continuous.py). I found no separate ICAR class in that grep; an ICAR can be written by hand as a pairwise-difference factor, as in the Stan case study [A].
- **Bambi** has hierarchical group-specific terms and an HSGP (Hilbert-space Gaussian process) term module, `bambi/terms/hsgp.py` [V, file exists] — [bambi repo](https://github.com/bambinos/bambi). I found no CAR/ICAR term in the Bambi README [V for the README grep; absence elsewhere is assumed]. A BYM2 model would need raw PyMC.
- **R options:**
  - CARBayes (v6.1.1) and CARBayesST (v4.0) give MCMC CAR models (BYM, Leroux, localised, and spatiotemporal variants in ST).
  - R-INLA has `bym2`, `besag` and space-time interaction models.
  - brms supports CAR terms.
  - (Licences under Q8.) [V for versions from CRAN DESCRIPTION files.]

### Inferences
- **Fire:**
  - The current Poisson GLM uses barangay *fixed* effects (22 free intercepts). A BYM2 or plain random-intercept model replaces them with *partially pooled* intercepts. Low-count barangays get pulled toward the city mean (iid part) or toward their neighbours (ICAR part).
  - With about 219 fires across 22 barangays (about 10 per barangay on average, fewer in quiet ones), shrinkage should mainly improve the low-count barangays. The Brier score is dominated by the busy ones, so a small or null change in the overall score is likely.
  - The project already found that the per-barangay average is about as good as the GLM, and that the neighbour term is uncertain (interval crosses 0). Both suggest weak spatial structure; expect the BYM2 posterior for `rho` to stay close to its prior.
- **Flood:**
  - 18 positives on 5 storm days amount to about 5 effective events. No hierarchical model can add information the data lack.
  - A Bayesian model with a **day-level random effect** (storm severity not captured by one NASA POWER cell), crossed with a barangay effect, would give more honest, wider uncertainty than the current logistic model.
  - LOBO performance would likely stay poor: for an unseen barangay the prediction falls back on the fixed terrain coefficients, which is the very part that fails now (AUC 0.36).
- **Landslide:** the 0.90 AUC rests on 8 events, 7 of them in one barangay. A hierarchical model would shrink the Manipis effect and widen the intervals. This is more honest, though perhaps less "impressive".
- **Informative priors:** external data could set priors, for example national or provincial BFP fire rates per household for the intercept, or published rain thresholds for the flood/landslide rain coefficient. I found no ready-made Philippine prior source (see Gaps). Weakly informative priors (normal(0, 1) on logit or log coefficients) act as a Firth-like penalty and stop separation with 8-18 positives [A].
- Spatial confounding (Hodges & Reich) matters for GeoAlert's terrain covariates (HAND, elevation, slope share are themselves spatially smooth). Adding an ICAR effect may move or weaken their coefficients. The reported terrain effects should be read as conditional on the spatial effect, or a restricted spatial regression should be used.

### Gaps
- I found no simulation study that tests BYM/BYM2/Leroux behaviour specifically at about 20 areas with about 200 events or fewer. Lee (2011, *Spatial and Spatio-temporal Epidemiology*) compares CAR priors, but I could not retrieve its abstract, so I report no numbers from it.
- I found no Philippine or Cebu source of external priors (fire rates by barangay type, flood rain thresholds) that is openly licensed.
- The exact INLA default PC prior for BYM2 (commonly quoted as P(σ>1)=0.01, P(ρ<0.5)=2/3) is from memory [A]; check the INLA `bym2` documentation before use.

---

## Q2. Hazard applications: INLA slope-unit space-time landslide models, Bayesian flood occurrence models, Bayesian structure-fire models

### Takeaway
Bayesian space-time landslide models (Lombardo et al. 2020, R-INLA) are mature, but they were built for hundreds of slope units and thousands of landslides. GeoAlert has 22 barangays and 8 landslides. The closest flood analogue is a Bayesian hierarchical model of daily weather-related insurance claims per municipality in Norway. I found no Bayesian barangay-day flood-occurrence model. Bayesian spatial models of residential fires exist; the best quantified one gives modest point-accuracy gains and its main value is probabilistic forecasts.

### Cited Findings
- **Lombardo, Opitz, Ardizzone, Guzzetti & Huser (2020)**, "Space-time landslide predictive modelling", *Earth-Science Reviews* 209:103318 [S, abstract and search summaries] — [DOI](https://doi.org/10.1016/j.earscirev.2020.103318); [HAL full text](https://hal.inrae.fr/hal-03164998v1/document):
  - The model is a log-Gaussian Cox process with a Poisson count per terrain unit plus Gaussian latent effects for covariates and for unobserved space-time controls. It was fitted in INLA for weather-triggered slides.
  - Collazzone (Umbria) setting: 79 km² split into 889 slope units, 3,379 landslides, six inventory periods, five models of increasing complexity [S, search summary].
- Follow-ups:
  - Loche et al. (2022, *Earth-Science Reviews* 104125) built Italy-wide slope-unit susceptibility in R-INLA that accounts for mapping bias [S] — [PDF](https://geomorphology.irpi.cnr.it/publications/repository/public/journals/2022/loche-earthscirev-104125_2022.pdf/@@download/file/Loche-EarthSciRev-104125_2022.pdf)
  - Lim et al. (2024) report a neural space-time landslide model for Vietnam that uses daily rainfall time series rather than scalar cumulative rain, with 14-day accumulation working best for the scalar baseline [S] — [DOI](https://doi.org/10.1016/j.jag.2024.104037)
- **Flood-like analogue:** Scheel et al. (2013, *JRSS C* 62:85-100) modelled daily weather-related insurance claims in 319 Norwegian municipalities (1997-2006). They used GLMs with "spatially smoothed variable selection" (Gibbs and reversible-jump MCMC) and report "precise out-of-sample predictions" (no numbers in the abstract) [S] — [DOI](https://doi.org/10.1111/j.1467-9876.2012.01039.x)
- A Bayesian hierarchical SPDE-INLA model of extreme-rainfall frequencies in Denmark found clustering in space and explanatory roles for atmospheric water content, instability and distance to the sea. This concerns rainfall, not flood occurrence [S] — [DOI](https://doi.org/10.1007/s00477-025-03054-5)
- **Fire:** see Q3 (Buffington et al. 2021; Rohde et al. 2010; Li et al. 2022).

### Inferences
- The Lombardo framework transfers to GeoAlert conceptually: Poisson or Bernoulli per areal unit and time step, terrain covariates, a structured spatial effect and a temporal or rain effect. Two things do not transfer:
  - Their spatial units are slope units (hundreds), not barangays.
  - Their event counts are about 400 times larger.
- At 22 units with 8 events, a space-time interaction term is unidentifiable. Only main effects plus maybe an iid barangay effect are realistic.
- For landslide, the literature suggests the spatial unit matters more than the model class. Splitting barangays into slope units (from the DEM GeoAlert already uses for steep-slope share) would add spatial units but not events. It would sharpen *where within Manipis*, but would not raise the 8-event ceiling.

### Gaps
- I found no published Bayesian (or any) model of flood *occurrence* at barangay or village-day level in the Philippines. Flood-specific analogues found were insurance claims (Norway) and rainfall extremes (Denmark), not inundation reports.
- I did not read the Lombardo 2020 full text for predictive skill numbers, so I report no AUC values from it.

---

## Q3. Urban fire risk prediction literature: models, predictors, and whether spatial or Bayesian models beat plain GLMs

### Takeaway
City fire-risk work splits into two strands:
- building-level machine-learning ranking (Firebird Atlanta, FDNY FireCast);
- area-level count models (census-tract Poisson/NB, Bayesian CAR, space-time Bayesian).

In the only quantified area-level comparison found (Buffington et al. 2021, 3,392 tracts):
- a Bayesian hierarchical Poisson regression cut RMSE by 9%;
- a residual spatial kernel step brought the gain to 15%;
- the CAR model had *worse* point forecasts but gave probabilistic forecasts.

The predictors that matter are socioeconomic disadvantage, building or property size and use, and population. In the Philippines, the BFP repeatedly names electrical ignition, cigarettes and open flames as leading causes. None of these settings is comparable to 22 barangays and 219 fires.

### Cited Findings
- **Buffington, Scott & Ezekoye (2021)**, "Combining spatial and sociodemographic regression techniques to predict residential fire counts at the census tract level", *Computers, Environment and Urban Systems* 88:101633 [S, abstract via search summary] — [DOI](https://doi.org/10.1016/j.compenvurbsys.2021.101633):
  - Five-year residential fire-count forecasts for 3,392 tracts (over 13 million residents). Trained on NFIRS 2006-2011, tested on 2012-2016.
  - The Bayesian hierarchical Poisson regression on ACS variables had 9% lower RMSE than the base model; a spatial kernel regression on its residuals gave a 15% RMSE improvement.
  - The CAR model had less accurate point forecasts but "allows for the generation of probabilistic forecasts and gives spatially-informed statistical estimates".
  - Risk per person was higher in tracts with lower median income and fewer college graduates.
- **Rohde, Corcoran & Chhetri (2010)**, "Spatial forecasting of residential urban fires: A Bayesian approach", *CEUS* 34(1):58-69 [V citation only; no abstract retrieved] — [DOI](https://doi.org/10.1016/j.compenvurbsys.2009.09.001)
- **Li et al. (2022)**, *Applied Geography*:
  - England 2010-2019: a spatial-temporal Bayesian regression of fire-related dwelling casualties on the Index of Multiple Deprivation.
  - The IMD effect varied a lot between areas; risk clustered in the North West and northern West Midlands, where risk rose by 26%-83%.
  - [S] — [DOI](https://doi.org/10.1016/j.apgeog.2022.102718)
- **Ardianto & Chhetri (2018)**, Melbourne, 10 years of data, Markov-chain model:
  - "Fire risk reduces in a neighborhood when there is at least one fire in the last 1 month", with a threshold of about 2 months.
  - Risk rises when there has been no fire in the last month within about 5 km.
  - [S] — [DOI](https://doi.org/10.1007/s13753-018-0209-2)
- **Wu et al. (2026)**, *Scientific Reports*, Xiaoshan (China):
  - 4,967 incidents (2020-2023); grid size chosen with Moran's I plus silhouette score; negative binomial regression with land use, population density and socioeconomic factors.
  - Risk followed an "80/20 rule" (a few cells hold most of the risk).
  - [S] — [DOI](https://doi.org/10.1038/s41598-026-38373-2)
- **Firebird (Madaio et al., KDD 2016, Atlanta)** [V, ar5iv full text] — [arXiv](https://arxiv.org/abs/1602.09067); [ar5iv](https://ar5iv.labs.arxiv.org/html/1602.09067):
  - Data: 8,223 commercial properties and 2,543 fire incidents (Jul 2011-Mar 2015); "only about 6% of the properties ... had fires".
  - Features: 252 variables, reduced to 58 and then one-hot encoded to 1,127.
  - Models compared: logistic regression, gradient boosting, SVM and random forest. True-positive rate at 20% false-positive rate: SVM 71.36%, RF 69.28%.
  - Testing AUC by training window (RF / SVM): 0.7624/0.7614 (2011-12), 0.8030/0.7914 (2011-13), 0.8246/0.8079 (2011-14).
  - Top RF features: floor size, land area, number of units, appraised value, number of buildings, total taxes, multi-family type, lot size, living units, percent leased.
  - No logistic-regression score was reported.
- **FDNY FireCast** [S, 2014-2015 press]:
  - FireCast 2.0 uses about 60 risk factors from five agencies, including building age, foreclosure proceedings and tax liens.
  - FireCast 3.0 was planned to use 17 agencies plus 311, up to 7,500 factors.
  - Buildings are scored and ranked daily; the system is proprietary.
  - [GovTech](https://www.govtech.com/public-safety/New-York-City-Fights-Fire-with-Data.html); [Urban Omnibus](https://urbanomnibus.net/the-analytics-of-fire)
- **Philippines:**
  - Agent-based fire-spread model for dense Barangay Addition Hills (Mandaluyong), which had major fires in 2016 and 2020; uses the BFP Operational Procedures Manual (ISPRS Archives 2021). This is a spread model, not an occurrence model [S] — [DOI](https://doi.org/10.5194/isprs-archives-xlvi-4-w6-2021-35-2021)
  - BFP causes, national Q1 2024: cigarettes, open-flame cooking and electrical ignition were the top causes, with most fires in homes [S, news] — [PTV News](https://ptvnews.ph/bfp-smoking-open-flames-top-causes-of-fire-incidents-in-2024-so-far/); [Inquirer](https://newsinfo.inquirer.net/1912533/fwd-number-of-fires-so-far)
  - BFP December 2024: the "majority" were electrical ignition [S, news] — [Inquirer](https://newsinfo.inquirer.net/2020131/fwd-bfp-941-fire-incidents-recorded-in-dec-2024-lower-than-dec-2023/amp)

### Inferences
- **Comparability:** Buffington (thousands of tracts, five-year totals, tens of thousands of fires) and Firebird (property-level, about 500 burned properties) are 1-2 orders of magnitude larger than GeoAlert. Their gains (9-15% RMSE, AUC about 0.8) cannot be transferred.
- The Buffington pattern is the one most relevant to GeoAlert: hierarchical shrinkage helped point accuracy, while full CAR mainly bought calibrated uncertainty.
- **Predictors** that plausibly transfer to barangay-month level, all as offsets or covariates:
  - population or household count per barangay (exposure offset);
  - share of informal or light-material dwellings;
  - poverty proxies;
  - building density (already computed for flood);
  - dry-season months (already in the seasonal terms).
- Electrical ignition dominating BFP causes argues for a season or holiday term (December spikes are reported) more than for neighbour terms.
- The Melbourne "no repeat within about 2 months" finding agrees with GeoAlert's null recent-fires term. Short-term self-excitation is weak, or slightly negative, at neighbourhood scale.

### Gaps
- I found no published barangay-level statistical fire-occurrence model built on BFP data. Search found citywide time-series work (Davao) and spread models, but I could not confirm the Davao study's details or link, so it is not cited as fact.
- FireCast performance figures are not public in the sources found.
- The Rohde et al. (2010) methods and results were not retrieved.

---

## Q4. Geographically weighted regression (GWR), GW logistic, multiscale GWR (mgwr, PySAL): unit requirements and whether 22 barangays is enough

### Takeaway
GWR, and especially MGWR, is a poor fit for GeoAlert:
- pysal `mgwr` fits GWR for Gaussian, Poisson and binomial families, but MGWR only for Gaussian;
- there is no formal minimum number of units, but published experiments use a few hundred or more;
- GWR assumes one observation per location, while GeoAlert's data are repeated barangay-days or months at 22 centroids.

### Cited Findings
- The pysal/mgwr README states: "GWR model calibration via iteratively weighted least squares for Gaussian, Poisson, and binomial probability models"; "MGWR model calibration via GAM iterative backfitting for Gaussian model" [V] — [mgwr README](https://github.com/pysal/mgwr). Licence BSD-3-Clause [V] — [mgwr repo](https://github.com/pysal/mgwr); `spglm` (its GLM backend) is BSD-3-Clause [V] — [spglm](https://github.com/pysal/spglm)
- Search summaries of the literature [S]:
  - No fixed minimum exists. Larger samples make very small bandwidths less likely and local fits more robust, and sample size often cannot be increased when tied to administrative units (Kang & Oshan 2025) — [J. Geogr. Syst. 2025](https://link.springer.com/10.1007/s10109-025-00468-1)
  - Earlier experiments used "a few hundred spatial units" (Wolf, Oshan & Fotheringham 2018) — [NSF PAR](https://par.nsf.gov/servlets/purl/10141801)
  - Esri says other tools may be more appropriate for smaller datasets — [ArcGIS MGWR doc](https://pro.arcgis.com/en/pro-app/tool-reference/spatial-statistics/how-multiscale-geographically-weighted-regression-mgwr-works.htm)

### Inferences
- With 22 units, an adaptive bisquare kernel fits each local regression on a handful of neighbouring barangays. With 3-6 covariates the local fits are nearly saturated, and AICc bandwidth selection will most likely push the bandwidth to (nearly) all 22 units, which reproduces the global model.
- GWR-Poisson (counts) or GWR-binomial (logistic) is technically available in `mgwr`. But fire and flood data have many rows per centroid (barangay × month or day), so coordinates repeat and the local design is degenerate.
- Verdict: use GWR at most as an exploratory map of barangay-level residuals, not as a predictive model.

### Gaps
- I did not retrieve the original MGWR paper (Fotheringham, Yang & Kang 2017) or the Wolf et al. 2018 simulation tables, which might give numeric small-n guidance.

---

## Q5. Spatial autocorrelation diagnostics (PySAL esda: Moran's I, LISA) for residual checks; licences

### Takeaway
`esda` (BSD-3-Clause) provides global Moran's I, rate-adjusted Moran (`Moran_Rate`), bivariate Moran, and local Moran/LISA (`Moran_Local`, `Moran_Local_Rate`), with permutation inference. Weights come from `libpysal` (BSD-3-Clause). It is the right free tool to test whether barangay-level residuals of the current GLM still carry spatial structure before building any CAR model. With n = 22, power is low.

### Cited Findings
- esda licence BSD-3-Clause [V] — [esda repo](https://github.com/pysal/esda). Classes in `esda/moran.py`: `Moran`, `Moran_BV`, `Moran_Rate`, `Moran_Local`, `Moran_Local_BV`, `Moran_Local_Rate` [V, source] — [moran.py](https://github.com/pysal/esda/blob/main/esda/moran.py)
- libpysal's LICENSE text is BSD 3-clause (the GitHub API reports "NOASSERTION" only because the file has a custom header) [V] — [libpysal LICENSE.txt](https://github.com/pysal/libpysal/blob/main/LICENSE.txt)
- A Xiaoshan fire-mapping study used Moran's I (with silhouette score) to choose the analysis grid size [S] — [Sci Rep 2026](https://doi.org/10.1038/s41598-026-38373-2)

### Inferences
- **Practical recipe:**
  1. Aggregate out-of-sample residuals, for example Pearson residuals (observed - expected)/sqrt(expected), per barangay over the whole period.
  2. Build queen contiguity from the barangay polygons (libpysal `Queen.from_dataframe`).
  3. Run `esda.Moran` with 9,999 permutations.
- With only 22 areas and a test p-value, a non-significant result does not prove "no spatial structure". It agrees with the neighbour-term result, though: both say any spatial effect is small.
- `Moran_Local` LISA maps on 22 units with multiple testing will rarely show significant clusters. Use them descriptively only.

### Gaps
- I did not find a published power analysis of Moran's I at n ≈ 20 to quote.

---

## Q6. Spatial ML (RFsp buffer distances, spatial lag features, Gaussian processes, kriging, GAMs with spatial smooths): licences and suitability with 22 areal units

### Takeaway
All the Python options are permissively licensed:

| Package | Licence |
|---|---|
| scikit-learn | BSD-3 |
| GPyTorch | MIT |
| PyKrige | BSD-3 |
| pyGAM | Apache-2.0 |
| statsmodels | BSD-3 |

These methods were designed for many point locations, not 22 polygons. With 22 areal units, kriging and GP variograms or kernels are barely estimable, and RFsp-style buffer distances mainly re-encode barangay identity. GeoAlert has already found that RF, XGBoost, LightGBM and MLP do no better. mgcv is GPL.

### Cited Findings
- RFsp (Hengl et al. 2018, *PeerJ* 6:e5518) uses "buffer distances from observation points ... as explanatory variables". It reached accuracy equal to kriging on textbook point datasets under five-fold cross-validation [S] — [DOI](https://doi.org/10.7717/peerj.5518)
- Licences [V, GitHub API / LICENSE]:
  - scikit-learn BSD-3-Clause — [repo](https://github.com/scikit-learn/scikit-learn)
  - GPyTorch MIT — [repo](https://github.com/cornellius-gp/gpytorch)
  - PyKrige BSD-3-Clause (last push 2025-10-16) — [repo](https://github.com/GeoStat-Framework/PyKrige)
  - pyGAM Apache-2.0 (last push 2026-04-21) — [repo](https://github.com/dswah/pyGAM)
  - statsmodels BSD-3-Clause — [repo](https://github.com/statsmodels/statsmodels)
- R mgcv (v1.9-5) licence GPL (>= 2) [V, CRAN DESCRIPTION] — [CRAN mgcv](https://cran.r-project.org/package=mgcv)
- Bambi provides an HSGP term (an approximate GP usable in hierarchical models) [V, file exists] — [bambi](https://github.com/bambinos/bambi)

### Inferences
- **Kriging / GP (scikit-learn GPR, GPyTorch, PyKrige):** with 22 barangay centroids, the length-scale or variogram range is estimated from 22 locations, so uncertainty is huge. Kriging also assumes point support, while barangays are areas, so area-to-point mismatch adds further error. Not recommended as a fire or flood model. A GP on barangay centroids inside a Bayesian GLM is equivalent in spirit to a CAR random effect and would behave the same (prior-dominated).
- **Spatial lag features** (neighbour-average fire rate) are what GeoAlert already tested as the "neighbours term"; they gave a small, uncertain gain.
- **GAM with spatial smooth** (pyGAM `te(lon, lat)` or mgcv `s(x, y)`): with 22 distinct coordinates the smooth has at most 22 effective levels. It is equivalent to a penalised barangay effect, so it adds nothing over a random intercept. pyGAM is a permissive alternative to mgcv for seasonal smooths (cyclic month) only.
- **Where spatial ML could help:** only if the unit changes, for example a 100-250 m grid with building footprints, giving thousands of cells. Even then the 219 fires stay the binding constraint.

### Gaps
- I did not verify PyTorch's licence (a GPyTorch dependency) this session; it is BSD-style [A].
- I did not retrieve a published rule for the minimum points needed for variogram estimation. A figure of 100+ points is commonly quoted [A].

---

## Q7. CPU feasibility and runtime of MCMC (PyMC / NumPyro / Stan) for about 1,000-40,000 rows, and deploying a fitted Bayesian model inside Django

### Takeaway
Fitting is feasible on a modest CPU. Published examples:
- Stan BYM2 on 56 areas: about 4.9 s total for 4 chains;
- PyMC BYM on 1,921 areas with the nutpie sampler: about 31 s (versus about 12 min with the default sampler on the author's machine).

GeoAlert's fire model (about 800 barangay-months, about 25-30 parameters) should take seconds to a minute. The flood/landslide logistic models on 40,172 rows are heavier per gradient but still in the minutes range [A, extrapolated]. Deploy by refitting offline (cron or management command) and storing posterior draws or summaries, so the web process only does numpy arithmetic.

### Cited Findings
- Stan case study, Scotland lip cancer (56 areas): BYM and BYM2 each took about 4.7-4.8 s per chain, "4.9 seconds" total for 4 chains (hardware not stated) [V] — [Stan case study](https://mc-stan.org/learn-stan/case-studies/icar_stan.html)
- PyMC NYC BYM (N = 1,921): "Sampling for 31 seconds" with `nuts_sampler="nutpie"`, 4 chains × 1,000 draws. A comment says the default sampler "took roughly 12 minutes on my machine" [V] — [PyMC example](https://www.pymc.io/projects/examples/en/latest/spatial/nyc_bym.html)
- nutpie is MIT-licensed and actively maintained (pushed 2026-11-10) [V] — [nutpie](https://github.com/pymc-devs/nutpie)
- Also actively maintained: NumPyro (Apache-2.0, on JAX Apache-2.0) and CmdStanPy/CmdStan (BSD-3-Clause) [V] — [numpyro](https://github.com/pyro-ppl/numpyro); [jax](https://github.com/jax-ml/jax); [cmdstanpy](https://github.com/stan-dev/cmdstanpy); [cmdstan](https://github.com/stan-dev/cmdstan)
- ArviZ (diagnostics: R-hat, ESS, LOO; InferenceData storage) is Apache-2.0 [V] — [arviz](https://github.com/arviz-devs/arviz)
- INLA (deterministic approximation, no MCMC) speeds up Knorr-Held Type IV fits; HyMiK gives a further 2-4x [S] — [arXiv](https://doi.org/10.48550/arxiv.2304.11851)

### Inferences
- **Size estimates** [A]:
  - Fire: about 22 × 36 = 792 rows (if the series runs Jan 2023-Dec 2025), Poisson, BYM2 (2 × 22 latent + 3 hyper) plus 4-6 seasonal coefficients. This is far smaller than the 1,921-area NYC example, so expect well under a minute with nutpie or NumPyro on CPU.
  - Flood/landslide: 40,172 rows. Each NUTS gradient touches every row, but a logistic model with 22 + 5 random effects and fewer than 10 fixed effects typically samples in a few minutes on CPU.
  - Rows with zero rain could be collapsed (aggregated binomial by barangay × rain bin) to cut cost if needed.
- **Deployment pattern** for Django/DRF:
  1. A management command or the existing background cache job refits monthly (fire) or after new events (flood/landslide), writing an ArviZ `InferenceData` netCDF file or a compact `.npz` of, say, 1,000 thinned draws per parameter.
  2. It stores per-barangay posterior summaries (mean, 10%/50%/90% quantiles of P(≥1 fire next month)) in a PostgreSQL table.
  3. The API reads the table. For rain-driven daily flood/landslide risk, the API computes `mean(sigmoid(X_today @ beta_draws + b_draws))` in numpy at request time (milliseconds).
  4. No sampler, PyTensor compiler or JAX is needed in the web worker.
- **Toolchain note:** PyMC's default backend (PyTensor) compiles C, so it needs a C compiler on the training host. nutpie uses its own compiled backend. NumPyro needs jaxlib CPU wheels. Training can run on a separate machine or container from the web server [A].
- **Convergence gate:** refuse to publish a refit unless R-hat < 1.01 and bulk ESS > 400 for all hyperparameters. Log divergences. With 22 areas, BYM2 `rho` may mix slowly, so watch it [A].

### Gaps
- I have no measured runtimes on GeoAlert-sized data. A short benchmark on the actual server is needed.
- I did not verify current jaxlib Windows CPU wheel support; it is only relevant if training runs on Windows.

---

## Q8. Licence verification (implementations, repos, dependencies, R-INLA) and practical meaning of GPL tools in a commercial Django backend; disqualified items

### Takeaway
The whole Python Bayesian/spatial stack is permissive and needs no account (MIT / BSD-3 / Apache-2.0):

| Package | Licence |
|---|---|
| PyMC | Apache-2.0 |
| PyTensor | BSD-3 |
| nutpie | MIT |
| NumPyro | Apache-2.0 |
| JAX | Apache-2.0 |
| Bambi | MIT |
| ArviZ | Apache-2.0 |
| Stan, Stan Math, CmdStan, CmdStanPy | BSD-3 |
| esda, libpysal, mgwr, spglm | BSD-3 |
| statsmodels, scikit-learn, PyKrige | BSD-3 |
| pyGAM | Apache-2.0 |
| GPyTorch | MIT |

The R options are GPL (CARBayes, CARBayesST, brms, mgcv, spdep, lme4, rstan, rstanarm). glmmTMB is AGPL-3.

R-INLA's R package **changed from GPL (>= 2) to MIT**: the NEWS entry is 25.01.23, and the first MIT stable build is 25.06.07. However, its compiled `inla` program uses GNU GSL (GPL-3), and PARDISO support (formerly licence-keyed) was **removed in 26.09.04**. Used offline for training, none of the GPL items imposes obligations on GeoAlert's Django code.

### Cited Findings
**Permissive (eligible for primary recommendation)** — all [V] via GitHub licence metadata and/or LICENSE file text, 2026-11-13:
- PyMC: LICENSE says "PyMC is distributed under the Apache License, Version 2.0" and "Contains code from AePPL, which is distributed under the MIT License" (the GitHub API shows "NOASSERTION" because of the custom header) — [PyMC LICENSE](https://github.com/pymc-devs/pymc/blob/main/LICENSE)
- PyTensor: BSD-style ("Redistribution and use in source and binary forms..."; Theano/Aesara/PyMC copyright) — [PyTensor doc/LICENSE.txt](https://github.com/pymc-devs/pytensor/blob/main/doc/LICENSE.txt)
- pymc-extras: Apache-2.0 — [LICENSE](https://github.com/pymc-devs/pymc-extras/blob/main/LICENSE)
- Bambi MIT; NumPyro Apache-2.0; JAX Apache-2.0; nutpie MIT; ArviZ Apache-2.0 — repos linked in Q7
- Stan, Stan Math, CmdStan, CmdStanPy: BSD-3-Clause — [stan](https://github.com/stan-dev/stan), [math](https://github.com/stan-dev/math), [cmdstan](https://github.com/stan-dev/cmdstan), [cmdstanpy](https://github.com/stan-dev/cmdstanpy)
- cmdstanr (R interface): "BSD_3_clause + file LICENSE" — [DESCRIPTION](https://github.com/stan-dev/cmdstanr/blob/master/DESCRIPTION)
- esda, mgwr, spglm: BSD-3-Clause; libpysal BSD-3 text — [esda](https://github.com/pysal/esda), [mgwr](https://github.com/pysal/mgwr), [libpysal LICENSE.txt](https://github.com/pysal/libpysal/blob/main/LICENSE.txt)
- scikit-learn BSD-3; statsmodels BSD-3; PyKrige BSD-3; pyGAM Apache-2.0; GPyTorch MIT — repos linked in Q6

**R packages (CRAN DESCRIPTION, 2026-11-13)** [V] — [CRAN](https://cran.r-project.org/web/packages/):

| Package | Version | Licence |
|---|---|---|
| CARBayes | 6.1.1 | GPL (>= 2) |
| CARBayesST | 4.0 | GPL (>= 2) |
| brms | 2.23.0 | GPL-2 |
| mgcv | 1.9-5 | GPL (>= 2) |
| rstan | 2.32.7 | GPL (>= 3) |
| rstanarm | 2.32.2 | GPL (>= 3) |
| spdep | 1.4-2 | GPL (>= 2) |
| lme4 | 2.1-0 | GPL (>= 2) |
| glmmTMB | 1.1.15.2 | **AGPL-3** |
| spaMM | 4.7.17 | CeCILL-2 |

- brms on GitHub reports GPL-2.0 — [brms](https://github.com/paul-buerkner/brms)
- The CARBayes GitHub mirror is stale (DESCRIPTION v5.2.5, 2021; last push 2022-09-06). CRAN is the current source [V].

**R-INLA (not on CRAN)** [V]:
- Licence history from the official repository's PACKAGES index ([inla.r-inla-download.org PACKAGES](https://inla.r-inla-download.org/R/stable/src/contrib/PACKAGES)):
  - GPL (>= 2) up to 20.03.17;
  - "GPL (>= 2) + file LICENSE" from 21.02.23 to 24.12.11;
  - "MIT + file LICENSE" from 25.06.07, 25.10.19 and 26.08.07 (latest stable).
  - The testing channel's latest is 26.08.22 (MIT).
- The NEWS entry for 25.01.23 reads "New license: MIT" — [INLA NEWS (r-universe)](https://test.r-universe.dev/INLA/NEWS)
- The GitHub repo `hrue/r-inla` LICENSE is the MIT text, "Copyright 2025 Haavard Rue". The devel DESCRIPTION (version 26.11.08) says "License: MIT + file LICENSE" — [r-inla LICENSE](https://github.com/hrue/r-inla/blob/devel/LICENSE)
- PARDISO, per the NEWS:
  - "Link with PARDISO8-library ..., get license at 'https://panua.ch'" (23.12.06);
  - "Support for PARDISO is removed" (26.09.04).
  - Earlier: "MKL-versions are included for MacOSX, and Linux" (18.12.01) and Intel MKL dropped on Mac (24.01.18).
  - [INLA NEWS](https://test.r-universe.dev/INLA/NEWS)
- The compiled inla-program's GMRFLib headers include GNU GSL (30 `gsl` matches in `gmrflib/GMRFLib.h`, 10 in `inlaprog/src/inla.h`) [V, source grep] — [GMRFLib.h](https://github.com/hrue/r-inla/blob/devel/gmrflib/GMRFLib.h). GSL's COPYING is GNU GPL Version 3 [V via a GitHub mirror of GSL, not gnu.org, whose page failed to load] — [GSL COPYING (ampl mirror)](https://github.com/ampl/gsl/blob/master/COPYING)
- Installation and access:
  - The stable repository is anonymous HTTPS (fetched without credentials this session) [V].
  - The newest devel code installs the R package with `remotes::install_github(...)` and fetches the binary from GitHub releases [V, `rinla/R/upgrade.R`] — [upgrade.R](https://github.com/hrue/r-inla/blob/devel/rinla/R/upgrade.R)
  - The old r-inla.org download page returned HTTP 404 (the site is migrating) [V].

**GPL/AGPL obligations (FSF GPL FAQ)** [V] — [GPL FAQ](https://www.gnu.org/licenses/gpl-faq.html):
- "The GPL does not require you to release your modified version, or any part of it". An organisation "can make a modified version and use it internally without ever releasing it outside the organization" (#GPLRequireSourcePostedPublic). Copies within one organisation are not distribution, but sharing with outside parties, including off-site contractors, is (#InternalDistribution).
- Running a GPL program on a server without distributing it creates no source obligation; the AGPL adds that obligation for modified versions used over a network (#UnreleasedMods, #UnreleasedModsAGPL).
- "The output of a program is not, in general, covered by the copyright on the code of the program" (#WhatCaseIsOutputGPL).
- Pipes, sockets and command-line arguments "are communication mechanisms normally used between two separate programs", unless "the semantics of the communication are intimate enough" (#MereAggregation).

**Disqualified / not usable as a tool (account, token, paid, or proprietary)**:
- **PARDISO solver for INLA:** required a licence key from panua.ch (23.12.06 NEWS); support removed in 26.09.04. Disqualified historically, now moot [V].
- **FDNY FireCast / RBIS:** proprietary city system, not downloadable. Usable only as literature [S].
- **Esri ArcGIS Pro MGWR tool:** needs a paid ArcGIS licence [A on licence terms; the tool doc is V]. Use pysal `mgwr` instead.
- **Semantic Scholar API:** rate-limited without a key during this research. Not part of GeoAlert; noted only because the research hit it.

### Inferences
- **Recommended stack (zero licence risk):** PyMC + nutpie (or NumPyro) + ArviZ + libpysal/esda, all inside GeoAlert's Python environment. No account, no key, no cloud. Stan via CmdStanPy is equally clean (BSD-3) if the Stan ICAR case study code is reused.
- **R-INLA status:** it is now MIT at the R-package level, a big change from earlier GPL versions.
  - The bundled `inla` executable links GSL (GPL-3). Under FSF's interpretation, a distributed binary that combines with GSL must be distributed under GPL-3 terms (source for the GSL-linked binary) [A on static vs dynamic linking mode; GSL inclusion is V].
  - Practical effect: running R + INLA **offline on the training server** and writing numbers into PostgreSQL creates **no obligation** on the Django code. The output is not covered, internal use is not distribution, and a subprocess or CSV hand-off is mere aggregation.
  - Obligations arise only if GeoAlert is *shipped* to a third party (for example a vendor installing it on the DRRMO's server) with the INLA binary included. Then the INLA binary must come with GPL-3 compliance (source availability); the Django code still need not be GPL.
  - Older INLA builds (≤ 24.12.11) were GPL (>= 2) at the package level too, so pin to ≥ 25.06.07 if INLA is used.
- **CARBayes / CARBayesST / brms / mgcv / rstan:** the same logic applies. They are fine for offline training via `Rscript`. Avoid importing R into the Django process through rpy2 or similar if GeoAlert might ever be distributed, because in-process linking is the "intimate communication" grey zone [A; rpy2's own licence not checked this session].
- **glmmTMB (AGPL-3):** avoid in any network-served path. If modified and exposed through a web API, the source must be offered to users.
- Running R adds a second runtime to deploy and patch. That operational cost is a reason to prefer the Python stack even though the licences allow R.

### Gaps
- I did not inspect the full INLA source tarball LICENSE or the binary's third-party notices (METIS, TAUCS, MKL builds). Linking mode (static or dynamic GSL) is unverified.
- I did not re-verify the licences of datasets used to make spatial weights or exposure offsets:
  - barangay polygons (PSA/NAMRIA, or own data);
  - OSM building footprints (ODbL, which requires attribution, plus share-alike for publicly distributed derived databases [A]);
  - PSA census population.
- I did not verify the licences of Stan's bundled C++ dependencies (Boost BSL-1.0, Eigen MPL-2.0, SUNDIALS BSD-3, TBB Apache-2.0) [A].

---

## Q9. Verdict: is a Bayesian hierarchical spatial model a better fit than the current GLM/logistic models for fire, flood and landslide? Plausible gains and risks

### Takeaway
- **Fire:** yes, as a *replacement* for the fixed-effect Poisson GLM. Use a Poisson (or negative-binomial) model with a partially pooled barangay effect: an iid random intercept first, BYM2 only if residual Moran's I or LOO favours it. Expect at most a small Brier gain (likely within the current noise band, about 0.001-0.005). The real gains are credible intervals, sensible estimates for low-count barangays, and a principled way to add exposure offsets.
- **Flood and landslide:** a Bayesian version mainly gives honest (wide) uncertainty and stable coefficients under separation. It will not fix the 0.36 LOBO AUC, because 5 storm days and 8 landslides carry too little information.
- **Spatial ML, GWR and kriging:** unsuitable at 22 units.

### Cited Findings
- Best quantified area-level fire comparison: hierarchical Bayesian Poisson gave 9% lower RMSE than the base model; residual spatial kernel smoothing gave 15%; CAR gave worse point forecasts but probabilistic output [S] — [Buffington et al. 2021](https://doi.org/10.1016/j.compenvurbsys.2021.101633)
- BYM2 shrinks well and is "at least equally" good on model-choice criteria as other parameterisations [S] — [Riebler et al. 2016](https://doi.org/10.1177/0962280216660421)
- Data alone cannot choose the form or extent of spatial correlation, and results are sensitive to priors [S] — [Wakefield 2006](https://doi.org/10.1093/biostatistics/kxl008)
- Spatial random effects can change fixed effects, and they do not fix missing spatial covariates [S] — [Hodges & Reich 2010](https://doi.org/10.1198/tast.2010.10052)
- Logistic regression underestimates rare-event probabilities; Firth or penalised fits reduce separation problems [S] — [King & Zeng 2001](https://doi.org/10.1093/oxfordjournals.pan.a004868); [van Smeden et al. 2016](https://doi.org/10.1186/s12874-016-0267-3)
- Space-time Bayesian landslide models work at hundreds of units and thousands of events [S] — [Lombardo et al. 2020](https://doi.org/10.1016/j.earscirev.2020.103318)

### Inferences
**Fire (main use case): recommended specification and test plan** [A, design inference]
- Model: y_bt ~ Poisson(μ_bt), or NegBin if overdispersed, with
  log μ_bt = log(E_b) + β0 + seasonal(month) + u_b
  - E_b is the exposure: households or buildings per barangay (needs an open-licence source).
  - u_b starts as iid Normal(0, σ) (pure partial pooling). Upgrade to BYM2 only if (a) Moran's I of the iid-model barangay residuals is positive, or (b) PSIS-LOO or rolling-origin Brier/log score favours it.
  - Priors: β0 centred on log(city-wide rate), month terms ~ Normal(0, 0.5), σ ~ HalfNormal(1) or a PC prior; for BYM2, `rho ~ Beta(0.5, 0.5)` as in the Stan and PyMC examples.
- Evaluation: the same rolling monthly hold-out used for the GLM. Compare Brier **and log score**, plus calibration of the 80% intervals (do 80% of monthly counts fall inside?). Use a paired bootstrap against (i) the per-barangay average and (ii) the current GLM.
- Plausible gain: small. The fixed-effect GLM already equals the per-barangay average, and shrinkage helps mainly where counts are small. A Brier change of the same order as the neighbour-term gain (about 0.001) is the realistic expectation. Interval calibration is where a real improvement can be shown.

**Flood**
- Option: a Bayesian logistic with crossed random effects (storm-day + barangay), terrain fixed effects under weakly informative priors, and possibly an informative prior on the rain coefficient.
- Benefit: credible intervals that honestly show "about 5 independent events", and no separation blow-ups.
- Not expected: better LOBO AUC. The failure is about which barangays flood on those 5 days not following the terrain features. The fix is more or better events and better spatial rain, not model class.
- Cheaper equivalent: Firth-penalised logistic (statsmodels lacks it natively; a weakly-informative-prior Bayesian logistic in PyMC is the permissive route).

**Landslide**
- Option: Bayesian logistic with a barangay random intercept and slope-share fixed effect.
- Expect the posterior to say "Manipis is high-risk under heavy rain; others uncertain". Present that honestly instead of a 0.90 AUC that rests on 7 events in one place.

**Risks**
1. Prior-dominated results at 22 units: `rho` and σ in BYM2 barely learned. Report prior-vs-posterior plots.
2. Spatial confounding of terrain covariates (Hodges & Reich).
3. Disconnected adjacency (a barangay with no land neighbour) needs special handling (Stan case study).
4. MCMC convergence failures need an automated gate.
5. Users may over-read interval maps; DRRMO staff need simple wording.
6. An R/INLA route adds a second runtime and a GPL-3 binary (fine offline, but a deployment burden).
7. Gains may not be statistically detectable with 219 fires. Report "no worse than baseline, with honest intervals" as an acceptable outcome.

### Gaps
- No study found tests BYM2 vs GLM on about 20 areas with about 200 events. GeoAlert's own rolling evaluation will be the only evidence.
- No openly licensed barangay-level exposure data (households, informal-settlement share) was verified in this research. These are likely the strongest fire covariates per the literature (Buffington; Li et al.).
