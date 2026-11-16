# Flood prediction for GeoAlert (Talisay City, Cebu): methods, free data and verified licences

Research date: 2026-11-13. Labels used in this file:
- **[V]** verified this session on the official page, licence file or primary paper.
- **[S]** secondary source (news, mirror, search summary), or an official page that was only partly readable.
- **[NV]** not verified this session (from prior knowledge or inferred). Check before relying on it.

GeoAlert facts (18 flood barangay-days on 5 storm days, PR-AUC 0.05, leave-one-barangay-out AUC 0.36, NASA POWER rain, terrain exposure features) come from the project's model report of 2026-11-13, as given in the assignment. They were not re-checked here.

---

## Q1. Standard methods for (a) susceptibility, (b) occurrence given observed rain, (c) short-term forecasting, and how comparable the benchmarks are

### Takeaway
These are three different questions. Susceptibility asks *where* flooding tends to happen and needs a mapped flood inventory plus static factors (FR, AHP, LR, RF, XGBoost, SVM, MaxEnt, HAND/TWI). Occurrence asks *whether* a flood happens on a given day and is usually done with rainfall thresholds or logistic models on antecedent rain, checked against impact records. Forecasting adds lead time and needs forecast rain plus hydrologic or hydraulic models, or a flash flood guidance system. Published accuracy figures are site- and inventory-specific and cannot be compared with GeoAlert's barangay-day scores.

### Cited findings
**(a) Susceptibility mapping**
- Reviews list frequency ratio (FR, bivariate) and logistic regression (LR, multivariate) as the most popular statistical methods for flood susceptibility mapping. Machine learning, fuzzy logic and metaheuristics have spread in recent years. AHP is a semi-quantitative multi-criteria method that is "still a viable option" for regional work [S, search summary of Kaya & Derin 2023 and related reviews] — [Parameters and methods used in flood susceptibility mapping: a review](https://avesis.ankara.edu.tr/yayin/881ff4b9-4515-4f6e-96c5-aa7e811135a2/parameters-and-methods-used-in-flood-susceptibility-mapping-a-review)
- A 2024 review of machine-learning and deep-learning hazard susceptibility mapping found random forest, artificial neural networks and SVM to be the most used techniques across hazards [S] — [Remote Sensing 2024 review (DOAJ record)](https://doaj.org/article/07f870bce37c4cbc802cdb3bafd9e9ba)
- Mosavi, Ozturk & Chau (2018), *Water* 10(11):1536, doi:10.3390/w10111536: "Flood Prediction Using Machine Learning Models: Literature Review". It screened over 6,000 articles down to 180 influential studies. It names hybrid, decomposition and ensemble methods as the main ways to improve ML flood models, and ANFIS, SVM and WNN as effective for short- and long-term prediction [S, read from mirrors, not the MDPI page] — [Academia.edu mirror](https://www.academia.edu/37658945/Flood_Prediction_Using_Machine_Learning_Models_Literature_Review)
- **Nearest local example:** a frequency ratio susceptibility map for **Mandaue City, Cebu** used eight factors (elevation, slope, TWI, curvature, river density, land use, NDVI, rainfall) and reports AUC 0.902 [S] — [Using frequency ratio model for flood susceptibility mapping of Mandaue City, Cebu](https://publish.mersin.edu.tr/index.php/igd/article/view/1220)
- A UP Cebu paper (ACRS 2023) mapped urban flood probability in Mandaue City with a probability-density approach and random forest in R, using elevation, land use and historical flood records [S] — [ACRS 2023 paper](https://a-a-r-s.org/proceeding/ACRS2023/Remote%20Sensing%20Applications/ACRS2023041.pdf)
- A random forest study of typhoon risk at grid level in Cebu City, using Sentinel-1 SAR backscatter change as the impact label, reports a modest average AUC of about 0.59 [S] — [IGES: neighbourhood-scale typhoon risk mapping](https://www.iges.or.jp/en/pub/neighbourhood-scale-typhoon-risk-mapping-using-machine-learning-and-sar-derived-impact-0)
- **MaxEnt in Python:** `elapid` describes itself as "Species distribution modeling tools, including a python implementation of Maxent". Licence: **MIT** [V, repository page]. Dependencies are scikit-learn, rasterio, geopandas and numpy, with glmnet optional — [earth-chris/elapid](https://github.com/earth-chris/elapid)
- **HAND:** a ready-made Global 30 m HAND layer, derived from Copernicus GLO-30 (2021) by the Alaska Satellite Facility, is licensed **CC0 1.0**. It sits on AWS (`s3://glo-30-hand`, us-west-2) and can be read with `--no-sign-request`, so no account is needed [V] — [AWS Registry: Global 30m HAND](https://registry.opendata.aws/glo-30-hand/)

**(b) Occurrence given observed rain (rainfall–impact thresholds, logistic models)**
- Papagiannaki et al. (NHESS 2015) studied a decade of flash floods in highly urbanised Attica, Greece. They derived triggering rainfall thresholds and linked rainfall to damage, using **fire-service call-outs to flooded properties as the impact record**. This is the closest analogue to DRRMO incident records [S, search summary; paper not opened] — [NHESS 15, 1859–1871, 2015](https://nhess.copernicus.org/articles/15/1859/2015/nhess-15-1859-2015.pdf)
- Jang (Water, 2015) proposed splitting urban rainfall thresholds into two groups, **drainage overload** and **disastrous runoff**, to grade warning levels. This maps directly onto GeoAlert's drainage-versus-river split [S] — [Water 2015 (DOAJ)](https://doaj.org/article/9c5aa53dbb2f4b83a781c9d1a803027b)
- A review of flood early-warning case studies (Henao Salgado & Zambrano Nájera, Frontiers in Climate 2022) concludes that indicators and predictor variables should be tuned to the local warning system, depending on the rainfall-threshold method chosen [S] — [Frontiers in Climate 2022](https://www.frontiersin.org/journals/climate/articles/10.3389/fclim.2022.787042/full)
- A 2026 NHESS discussion paper reviews rainfall thresholds and early warning. A referee noted that its thresholds came from a spatially unrepresentative corpus (42 flash-flood events) and questioned whether they form a "globally comparable baseline". That supports the view that thresholds do not transfer between sites [S, only the discussion page was seen] — [NHESS discussion 26, 5073, 2026](https://nhess.copernicus.org/articles/26/5073/2026/nhess-26-5073-2026-discussion.html)
- **Small-sample logistic regression:** van Smeden et al. (BMC Med Res Methodol 2016) found the evidence behind events-per-variable (EPV) rules weak, and showed that logistic coefficients carry small-sample bias that systematically overestimates associations [S, summary] — [BMC MRM 2016](https://link.springer.com/article/10.1186/s12874-016-0267-3)
- Firth penalised likelihood reduces small-sample bias, also handles separation, and costs almost nothing extra to compute. Allison argues for using it routinely; his rule of thumb is that 20 events in n=1000 is "a problem" [S, practitioner blog] — [Statistical Horizons](https://statisticalhorizons.com/?p=1076)
- Simulations summarised in Williams' notes report that King & Zeng's rare-events correction over-corrects when n is small (<200), while penalised ML estimates stay roughly unbiased even with very few events [S, secondary summary of a working paper] — [R. Williams, Analyzing Rare Events with Logistic Regression](https://www3.nd.edu/~rwilliam/stats3/RareEvents.pdf)

**(c) Short-term forecasting with lead time**
- PAGASA takes part in the WMO **Southeastern Asia-Oceania Flash Flood Guidance System (SAOFFGS)**. Members are Brunei, Indonesia (regional centre), Malaysia, Papua New Guinea, the Philippines and Timor-Leste, and PAGASA hosted SAOFFGS operations training in September 2018 [S] — [WMO community page](https://community.wmo.int/ar/node/36128); [PAGASA photo gallery](https://www.pagasa.dost.gov.ph/index.php/news-and-events/photo-gallery/17)
- Mosavi et al. (2018) argue that physically based models are poorly suited to short-term prediction because of accuracy, complexity, computing cost and robustness. That is the authors' opinion, not a benchmark result [S] — [mirror](https://www.academia.edu/37658945/Flood_Prediction_Using_Machine_Learning_Models_Literature_Review)

### Inferences
- GeoAlert's current model mixes all three questions in one barangay-day logistic regression. The pooled ROC-AUC of 0.96 comes almost entirely from the "when" signal: storm days against the other ~1,800 days. The leave-one-barangay-out AUC of 0.36 shows the "where" part has not been learned. That fits a design with 18 positives and about 11 predictors, roughly 1.6 events per variable by barangay-day and fewer than 1 by distinct event day.
- Susceptibility AUCs in the literature, such as Mandaue's 0.902, are usually computed on random pixel splits of a mapped inundation inventory, where spatial autocorrelation inflates the score. They are not comparable with a leave-one-barangay-out score on 22 units. **[NV]** The general point about inflation is widely made but was not sourced this session.
- For 5 event days the defensible route is: (a) take "where" from external physically based hazard maps (NOAH, see Q2) plus HAND, not from fitting; (b) keep "when" as a city-level model with very few parameters, or as an explicit threshold rule; (c) take lead time from PAGASA products rather than building a forecast model.

### Gaps
- Full texts of the Kaya & Derin (2023) and Viloria et al. (2024) reviews were not opened, so method-by-method accuracy summaries are not reported.
- No head-to-head benchmark of FR, AHP, LR, RF, XGBoost, SVM and MaxEnt under very small inventories (<20 events) was found.
- No published, validated SAOFFGS flash flood guidance product for Cebu was found. Public access to SAOFFGS output was not established, but it appears to be limited to national meteorological services **[NV]**.

---

## Q2. Philippine impact-based forecasting and official hazard products (510, PAGASA, NOAH, DOST/MGB); studies on Talisay, Metro Cebu, Mananga and Kinalumsan

### Takeaway
510's typhoon models are XGBoost impact models trained on about 39–60 typhoons that predict house damage per municipality, not flooding. Their code is **GPL-3.0** and both repositories are archived. Running the operational pipeline needs 510 credentials, so it is unusable as-is. **UP NOAH flood hazard maps (5-, 25- and 100-year) are published as shapefiles under ODbL.** They are the strongest free, commercially usable prior for "where" in Talisay. PAGASA warning thresholds are public and can be used directly as rule features. I found no peer-reviewed flood study of Talisay City, Mananga or Kinalumsan. Only news and a 2006 MGB assessment report exist.

### Cited findings
**510 Global (Netherlands Red Cross) typhoon impact-based forecasting**
- `rodekruis/Typhoon-Impact-based-forecasting-model` was built "as a trigger mechanism for the typhoon Early action protocol of the Philippines Red Cross FbF project". Its target is the "percentage of completely damaged houses per municipality". Licence **GPL-3.0**. It was archived (read-only) on 19 Nov 2025. The operational pipeline needs a Data.zip from SharePoint (link expired 2022-10-25) and 510 Datalake/FTP credentials obtained by contacting 510 [V, repository page] — [GitHub](https://github.com/rodekruis/Typhoon-Impact-based-forecasting-model)
- The model was approved in 2019 as the trigger for the Philippine Red Cross typhoon Early Action Protocol and in 2021 for the UN OCHA anticipatory action pilot. It is XGBoost with classification and regression parts, trained on 60+ historical events, and runs operationally on ECMWF forecasts [S, search summary] — [PreventionWeb case study](https://www.preventionweb.net/resource/case-study/impact-based-forecasting-anticipatory-action-typhoons-philippines)
- Kooshki Forooshani et al. (2024), "Towards a global impact-based forecasting model for tropical cyclones", NHESS 24:309–329, CC BY 4.0 [V]:
  - Two-stage XGBoost ("2SG-Global+"): a classifier with a 10% damage threshold and undersampling, then a regressor on high-damage cells. Linear regression and random forest did slightly worse.
  - Features: maximum wind (CLIMADA/Holland model); **GPM rainfall maximum 6 h and 24 h, plus ~3-day total**; **track distance from IBTrACS**; SRTM slope, elevation and coastline length; Relative Wealth Index; population; land-use shares; 5-year historical damage.
  - Data: 39 Philippine typhoons, 2006–2020, on a 0.1° grid (3,726 cells).
  - Result: F1 about 0.65 for >10% damage, against 0.58 for the municipal model.
  - **NOAH hazard maps were used as local features in the original municipal model** but left out of the global one.
  - Source: [NHESS 2024](https://nhess.copernicus.org/articles/24/309/2024/)
- `rodekruis/GlobalTropicalCycloneModel`: licence **GPL-3.0**, archived 10 Mar 2026. Data comes from a shared Google Drive folder [V] — [GitHub](https://github.com/rodekruis/GlobalTropicalCycloneModel)

**PAGASA warnings**
- Hourly colour-coded Heavy Rainfall Warnings: **Yellow 7.5–15 mm/h, Orange 15–30 mm/h, Red >30 mm/h**, expected to continue for about the next 2 hours (older reports say 3 hours). The system has been in use since 2012 [S, news and explainers; no official PAGASA page was fetched] — [Varsitarian explainer 2025](https://varsitarian.net/sci-tech/20250724/explainer-how-do-pagasas-rainfall-warnings-and-weather-advisories-work); [Reportr](https://www.reportr.world/news/rainfall-warning-color-meaning-pagasa-a4373-20210721); [Inquirer 2012](https://newsinfo.inquirer.net/215587/pagasa-unveils-color-coding-for-rain-alerts)
- A separate accumulated-rainfall advisory scale is reported as **Yellow 50–100 mm, Orange 100–200 mm, Red >200 mm** [S, search summary attributed to the explainers above; check against an official PAGASA bulletin].
- PAGASA station data: requests "aimed for noncommercial activities such as for academic research purposes are provided free of charge. Otherwise, the applicable fees shall be based on the most recently approved schedule of fees". Requests go through forms (CADS-01B, a signed CADS-07 Terms and Conditions), an ID and a request letter, either by email or the eFOI portal. Telemetered data takes 5–7 days to process [S, search summary of PAGASA documents] — [CADS-07 Terms and Conditions (PDF)](https://pubfiles.pagasa.dost.gov.ph/pagasaweb/files/climate/CADS-07-Rev-2-Terms-and-Conditions-of-Use-for-Climatological-Data-1.pdf); [PAGASA Citizen's Charter](https://pubfiles.pagasa.dost.gov.ph/pagasaweb/files/PAGASA%27s_CITIZENS_CHARTER_4th_EDITION_FINAL.pdf); [UP IESM data page](https://iesm.science.upd.edu.ph/?p=7395)

**UP NOAH flood hazard maps**
- NOAH hazard maps are "available for the public to download under an Open Data Commons Open Database License", as ESRI shapefiles. Flood maps cover several rainfall return periods, use NAMRIA IfSAR and NOAH LiDAR terrain, and were validated with Sentinel-2 [S, Space Climate Observatory page; noah.up.edu.ph itself was not fetched] — [SCO: NOAH](https://www.spaceclimateobservatory.org/noah)
- A third-party mirror (bettergovph on Hugging Face, tagged `odbl`):
  - Return periods 5, 25 and 100 years; flood coverage 80 provinces.
  - Flood `Var` field: 1 = low (0–0.5 m), 2 = medium (0.5–1.5 m), 3 = high (>1.5 m). Fast, shallow flow may be rated higher.
  - Flood maps produced by PAGASA. The mirror links the official Google Drive folder.
  - Cebu is implied but not named.
  - [V, mirror page] — [Hugging Face: project-noah-hazard-maps](https://huggingface.co/datasets/bettergovph/project-noah-hazard-maps); official Drive folder linked there: https://drive.google.com/drive/folders/1ALE4-E9c-4AGjm1fqiPprWHrLUskeY9o
- The NOAH site carries a beta disclaimer: "Project NOAH is still in beta release… to complete the hazard maps" [S] — [NOAH Know Your Hazards](https://noah.up.edu.ph/know-your-hazards)
- A 2025 report says current NOAH maps use only 30 years of PAGASA rainfall data and that funding is planned to update them [S] — [Philstar 2025-12-26](https://www.philstar.com/headlines/2025/12/26/2496800/project-noah-improve-hazard-maps)

**DENR-MGB and GeoRiskPH**
- MGB flood susceptibility (Low, Moderate, High, Very High) is served as a public ArcGIS REST layer on the GeoRiskPH domain [S] — [MGBPublic/Flood MapServer](https://ulap-hazards.georisk.gov.ph/arcgis/rest/services/MGBPublic/Flood/MapServer/0?f=pjson)
- HazardHunterPH disclaims liability and tells users to contact DENR-MGB for detailed or archived flood data. No reuse licence was found [S] — [About HazardHunterPH](https://hazardhunter.georisk.gov.ph/about-hazardhunterph); [FAQs](https://hazardhunter.georisk.gov.ph/faqs)

**Talisay, Metro Cebu, Mananga and Kinalumsan**
- In 2006 DENR-MGB was asked to assess Talisay's flood-prone areas. **Seven barangays along the Mananga River** were identified as flood-prone. No published results of that assessment were found [S, news] — [Philstar 2006](https://philstar.com/cebu-news/2006/07/02/345125/denr-assesses-talisays-7-flood-prone-areas)
- Typhoon Tino (Kalmaegi), November 2025: about **5,000 families in 10 barangays along the Mananga River** were affected. Deaths were tied to families living on riverbanks and in dried riverbeds [S, news] — [SunStar: Riverside living 'worsened' Tino damage](https://www.sunstar.com.ph/cebu/riverside-living-worsened-tino-damage)
- In the 24 hours before Kalmaegi's landfall, the area around Cebu City received **183 mm** [S, AFP via Business Recorder] — [Business Recorder](https://www.brecorder.com/news/amp/40390882)
- Mananga channel sections once about 30 m wide have shrunk to nearly half through encroachment and sediment. DPWH plans widening and dredging in 2026 [S] — [SunStar: DPWH to widen Mananga River](https://www.sunstar.com.ph/cebu/dpwh-to-widen-mananga-river-to-stop-severe-flooding); [Mananga rehab fast-tracked, Jan 2026](https://test2.proudbisayabai.ph/story/2026/01/27/race-with-rains-mananga-river-rehab-fast-tracked-ahead-of-rainy-season)
- A June 2021 headline: "Floods affect at least 1 thousand families in Talisay" [S, headline only] — [Philstar 2021-06-15](https://www.philstar.com/the-freeman/cebu-news/2021/06/15/2105585/floods-affect-least-1-thousand-families-talisay)
- Reported **Kinalumsan** overflows (for example 4 Aug 2022) were in **Cebu City** (Duljo, Mambaling, Vestil Bridge). Talisay flood reports instead mention the **Candulawan River** [S, news] — [Inquirer 2022](https://newsinfo.inquirer.net/1641378/heavy-rains-trigger-floods-in-some-parts-of-metro-cebu); [Philstar 2022: easement upstream of Kinalumsan](https://www.philstar.com/the-freeman/cebu-news/2022/08/12/2202173/3-meter-easement-restored-upstream-kinalumsan-river)
- Multi-temporal SAR images detected Kalmaegi flooding in Cebu, among other provinces (Observatory Philippines maps) [S; licence of these maps not checked] — [Observatory Philippines: Impacts of Typhoon Kalmaegi in Visayas](https://mapsanddata.observatory.ph/?p=20775); [Cebu page](https://mapsanddata.observatory.ph/?p=20787)

### Inferences
- **NOAH 5/25/100-year flood hazard is the most defensible "where" prior for Talisay.** It is physically modelled with LiDAR/IfSAR, so it does not depend on GeoAlert's 18 records. It is ODbL, so commercial use is allowed with attribution, and share-alike applies to derived databases. 510 also used NOAH maps as features. Suggested features: share of each barangay (or each record's sitio) in hazard classes 2–3 at 25-year and 100-year return periods.
- The 510 models predict typhoon house damage, not floods. Two parts transfer to GeoAlert: the feature design (max 6 h and 24 h rain, 3-day total, track distance, historical impact) and the two-stage "is it a significant event, then where" structure. The code (GPL-3.0, archived, credential-gated data) is not worth adopting.
- GeoAlert flood records already include the 2025-11-04 Tino event. If the 2021-06-15 Talisay flood is not among the 5 event days, under-recording is confirmed and that date could be added after DRRMO checks it.
- The Mananga widening and dredging planned for 2026 will change river-flood hazard. Any model fitted on 2021–2025 should be expected to drift.
- GeoAlert lists "Kinalumsan" as a main Talisay river, but news places Kinalumsan floods in Cebu City. Talisay records should be checked for Candulawan versus Kinalumsan naming.

### Gaps
- The licence statement was **not read on noah.up.edu.ph itself**; it came from SCO (an international initiative page) and a mirror. Confirm on the NOAH site or with UPRI before production. It was also not confirmed that the official Google Drive folder opens without a Google sign-in.
- No licence or terms for reusing MGB/GeoRiskPH flood layers was found. Treat them as "view only, licence unknown".
- No official PAGASA page for the warning thresholds was fetched. The figures come from consistent news and explainer sources.
- No peer-reviewed hydrologic or flood study of the Mananga or Kinalumsan watersheds was found.
- No Copernicus EMS rapid-mapping activation for Cebu during Kalmaegi was confirmed.

---

## Q3. Typhoon / tropical-cyclone features (IBTrACS)

### Takeaway
IBTrACS can be downloaded with no account (CSV, netCDF, shapefile) and is updated about 3 times a week. Distance to track and maximum wind are standard predictors in Philippine impact models (510). Its use policy is WMO-based full and open access, with **WMO Resolution 40 given as the guide for commercial use**. There is no named open licence. This is "free, no account, practically usable", with a licensing ambiguity that should be noted.

### Cited findings
- Downloads [V]: [netCDF](https://www.ncei.noaa.gov/data/international-best-track-archive-for-climate-stewardship-ibtracs/v04r01/access/netcdf/), [CSV](https://www.ncei.noaa.gov/data/international-best-track-archive-for-climate-stewardship-ibtracs/v04r01/access/csv/) and [shapefile](https://www.ncei.noaa.gov/data/international-best-track-archive-for-climate-stewardship-ibtracs/v04r01/access/shapefile/).
- Subsets: ALL, since1980, last3years, active (last 7 days) and per basin. No login is needed. An optional Google Form asks how the data is used [V] — [NCEI IBTrACS](https://www.ncei.noaa.gov/products/international-best-track-archive)
- Use policy follows the World Data Center for Meteorology (full and open access). Regional Specialized Meteorological Centres agreed to open distribution. "For commercial use", the page points to **WMO Resolution 40**. No named licence such as Creative Commons is given [V] — [NCEI IBTrACS](https://www.ncei.noaa.gov/products/international-best-track-archive)
- Updated three times a week (Sun, Tue, Thu) per the Update Schedule; the Release Information section says weekly, so the page contradicts itself. Provisional data is included for recent storms. Variables include positions, wind and pressure from several agencies, translation speed and direction, `dist2land` and landfall flags. Citation: Knapp et al. 2010 (doi:10.1175/2009BAMS2755.1) plus Gahtan et al. 2024 (doi:10.25921/82ty-9e16) [V] — [NCEI IBTrACS](https://www.ncei.noaa.gov/products/international-best-track-archive)
- 510's global model uses IBTrACS track distance and modelled maximum wind (CLIMADA/Holland) as core hazard features [V] — [NHESS 2024](https://nhess.copernicus.org/articles/24/309/2024/)

### Inferences
- GeoAlert's 5 flood days are storm days (Tino alone gave 10 of 18 records). A day-level flag such as "a TC centre within R km of Talisay in the past 24–72 h" (R = 100, 200, 300 km) together with an IBTrACS wind value is likely to separate flood days from heavy-rain non-storm days better than city-cell rain alone. This also partly corrects the coarse NASA POWER cell missing local TC rain. Test it with leave-one-event-day-out, not random folds.
- IBTrACS is fine for **history** (training). For **real-time** use it is too slow: about 3 updates a week, with provisional data only. Live track data would have to come from PAGASA or JTWC bulletins; their licensing was not checked.
- Southwest monsoon (habagat) enhanced by distant TCs can flood without a nearby track. A "TC within 500–800 km" flag may also matter. **[NV]** This is a hypothesis to test, not a sourced fact.

### Gaps
- WMO Resolution 40's exact conditions for commercial reuse of IBTrACS-like "essential" data were not read this session.
- Licensing and machine-readable access for live PAGASA or JTWC track bulletins were not checked.
- Whether all 5 GeoAlert event days fall within a TC's influence was not checked. This needs the project's dates (only 2025-11-04 and 2025-08-18 are known here).

---

## Q4. Free, no-account rainfall data finer than NASA POWER

### Takeaway
**CHIRPS is the clear qualifier.**
- v2: public-domain waiver. v3: CC BY 4.0 plus a copyright waiver.
- 0.05° (about 5.5 km) against POWER's ~0.5° cell.
- Open HTTP directory with no login.
- Preliminary data 2 days after each pentad; final data in the third week of the next month.
- Catch: daily values are disaggregated from pentads. v3 splits pentads using ERA5 or IMERG daily rain, so single-day timing is not a direct observation.

**PERSIANN-CDR** (0.25°, daily, NOAA ERDDAP metadata says "No constraints on data access or use", updated quarterly) also qualifies for training. PDIR-Now and the PERSIANN CHRS portal carry "All rights reserved" with no licence, so they are not cleared.

**Disqualified:** GSMaP (registration), MSWEP (CC BY-NC and a request form), ERA5 through the CDS (account). PAGASA station data is free only for non-commercial research. Commercial use has fees and a signed T&C, so it is conditional at best.

### Cited findings
**CHIRPS v2 / v3 (Climate Hazards Center, UCSB)**
- v2: 0.05°, 50°S–50°N, 1981 to near-present. Pete Peterson "has waived all copyright and related or neighboring rights to CHIRPS"; the data "is in the public domain as registered with Creative Commons". **v2 production ends after December 2026** and users are told to move to v3 [V] — [CHC CHIRPS](https://www.chc.ucsb.edu/data/chirps); [data directory](https://data.chc.ucsb.edu/products/CHIRPS-2.0/)
- v3: 0.05°, 60°N–60°S, 1981 to near-present, licensed **CC BY 4.0**. CHC "has waived copyright and related rights" to CHIRPS3 as far as possible [V] — [CHC CHIRPS3](https://www.chc.ucsb.edu/data/chirps3)
- v3 latency: **preliminary 2 days after each pentad ends** (on the 2nd, 7th, 12th, 17th, 22nd and 27th); **final in the third week of the following month** [V] — [CHC CHIRPS3](https://www.chc.ucsb.edu/data/chirps3)
- v3 daily data is disaggregated from pentads using **ERA5 daily ('rnl')** or **IMERG Late V07 daily ('sat')**. The page says "Daily dates are consistent labels from the disaggregation process, not uniform observation windows". v3 adds gauge-undercatch correction, about 4× more gauge sources than v2, and a CHIRP3 algorithm that better captures high-rainfall events [V] — [CHC CHIRPS3](https://www.chc.ucsb.edu/data/chirps3)
- The v3 directory is an open "Index of" listing with no login. Folders include daily/, pentads/, prelim/, monthly/ and others, plus README-CHIRPSv3.0.txt [V] — [data.chc.ucsb.edu/products/CHIRPS/v3.0/](https://data.chc.ucsb.edu/products/CHIRPS/v3.0/)
- In the Philippines, a 9-product evaluation in the Magat River Basin (Gacu et al., Remote Sensing 2025) found CHIRPS "excels in detecting high-intensity and erosive rainfall events" [S] — [Remote Sensing 17(19):3375](https://www.mdpi.com/2072-4292/17/19/3375)

**PERSIANN family (UC Irvine CHRS)**
- The CHRS Data Portal lists PERSIANN, PERSIANN-CCS, PERSIANN-CDR, PDIR-Now and PERSIANN-CCS-CDR v2.0. Its footer says "Copyright © 2015 CHRS, UC Irvine. All rights reserved". No licence or terms of use appear on the landing page [V] — [CHRS Data Portal](https://chrsdata.eng.uci.edu/)
- PDIR-Now: hourly, about 0.04°, 15–60 min latency, meant to replace PERSIANN-CCS [S, search summary of published papers] — [CHRS portal paper (NOAA repository)](https://repository.library.noaa.gov/view/noaa/24173)
- **PERSIANN-CDR at NOAA NCEI**: daily, 0.25°, 60°S–60°N, 1982/83 to present, updated **quarterly**. ERDDAP metadata licence: **"No constraints on data access or use."** Cite Sorooshian et al. (2014), doi:10.7289/V51V5BWQ [S, NCEI ERDDAP metadata via search summary] — [NCEI PERSIANN CDR](https://www.ncei.noaa.gov/products/climate-data-records/precipitation-persiann); [ERDDAP](https://www.ncei.noaa.gov/erddap/griddap/cdr_persiann_by_time_lon_lat.html)
- Over Philippine typhoon heavy-rain events, IMERG agreed well with gauges, while IMERG and PERSIANN underestimated considerably in some cases (Aryastana et al. 2022) [S] — [Earth and Space Science 2022 (DOAJ)](https://doaj.org/article/3bd470a9ec03494181871b8b5421fbed)

**Disqualified or conditional**
- **GSMaP (JAXA):**
  - G-Portal requires registration to download.
  - JAXA's Research Data terms allow commercial use without a fee, but users must **notify JAXA in advance**.
  - The search summary claimed a "G-Portal Repo" needs no registration; not verified.
  - [S] — [GSMaP registration/terms](https://sharaku.eorc.jaxa.jp/GSMaP/registration.html); [JAXA data policy](https://earth.jaxa.jp/en/data/policy/); [G-Portal Repo terms](https://repo.gportal.jaxa.jp/G-PortalRepo_Policy_e.html)
  - **Disqualified** (registration plus notification).
- **MSWEP (GloH2O):**
  - **CC BY-NC 4.0**.
  - A request form needs a work or academic email and confirmation that the requester is "not affiliated with a commercial entity".
  - Download goes through Google Drive with Rclone browser authentication.
  - Commercial access only through the GloH2O API, pricing not stated.
  - 0.1°, hourly; NRT latency given as <2 h and ~3 h on the same page.
  - [V] — [GloH2O MSWEP](https://www.gloh2o.org/mswep/)
  - **Disqualified.**
- **ERA5 / ERA5-Land through the Copernicus CDS:** needs an account. **Disqualified** via that route.
- **ERA5 via Google ARCO-ERA5:** the `gcp-public-data-arco-era5` bucket may allow anonymous reads (community examples use `token='anon'`). The data is under the Copernicus licence, which allows commercial use; the repository code reportedly Apache-2.0. [S, unconfirmed] — [google-research/arco-era5](https://github.com/google-research/arco-era5)
  - **Conditional, not verified.** ERA5's ~0.25° convective rain is also unlikely to beat CHIRPS locally **[NV]**.
- **NASA IMERG:** Earthdata login required. Already excluded by the project and stays excluded. CHIRPS v3 'sat' daily files *embed* IMERG timing but need no login.
- **PAGASA station data:** free only for "noncommercial activities such as for academic research"; otherwise fees apply. A signed T&C (CADS-07) and request forms are required [S] — [CADS-07](https://pubfiles.pagasa.dost.gov.ph/pagasaweb/files/climate/CADS-07-Rev-2-Terms-and-Conditions-of-Use-for-Climatological-Data-1.pdf)
  - **Disqualified as a primary source** for a commercial deployment (fees, signed terms, recurring requests). Possibly usable for one-off validation under an academic or LGU request.

### Inferences
- **Best rain test for GeoAlert:** extract CHIRPS v3 (final, plus prelim for recent days) for the CHIRPS cells over Talisay. Compare against POWER on the 5 event days and on heavy-rain non-event days, using 3-day and 5-day sums (pentad-scale) rather than single days, since daily CHIRPS timing is disaggregated. Note that the 'sat' disaggregation embeds IMERG Late timing, which is what POWER's coarse cell lacks.
  - The 2025-08-18 flood showed only 7 mm in POWER. If CHIRPS also shows little rain, that record is probably very local convection or not rain-driven (for example drainage blockage). If CHIRPS shows heavy rain, POWER's coarse cell is the problem.
- Talisay City spans a few 0.05° cells. CHIRPS will give some spatial contrast between the upland Mananga catchment and the coastal lowlands, but not true barangay-scale rain. Upstream catchment rain (Mananga headwaters) is probably more predictive of river floods than rain over the flooded barangay itself **[NV, hypothesis]**.
- **Real-time:** CHIRPS prelim lags by up to ~7 days (pentad plus 2 days), so it cannot drive same-day alerts. Same-day operation needs PAGASA warnings (Q2) or a still-unlicensed near-real-time product (PDIR-Now). For training and back-testing, CHIRPS v3 final plus PERSIANN-CDR are both cleared.

### Gaps
- PDIR-Now / PERSIANN-CCS licence is unknown. The portal says "All rights reserved" with no terms. Ask CHRS before any commercial use.
- No study was found evaluating daily CHIRPS against gauges over Cebu, or for typhoon-day timing in the Philippines.
- The CHIRPS v3 README was not opened. Licence wording comes from the CHC web page.
- Anonymous access to ARCO-ERA5 and its exact data licence were not confirmed.

---

## Q5. Free terrain and hydrography data, and their licences

### Takeaway
**Cleared for commercial use with no account:** Copernicus DEM GLO-30 (free, any legal person, attribution notices required; AWS bucket), ASF Global 30 m HAND (CC0), JRC Global Surface Water (Copernicus, "without restriction of use"), ESA WorldCover (CC BY 4.0), GHSL (CC BY 4.0), HydroSHEDS/HydroRIVERS (free for commercial use, direct download), OSM (ODbL: attribution plus share-alike for derived databases). **Disqualified:** FABDEM (CC BY-NC-SA; commercial use needs a Fathom licence) and MERIT Hydro (registration form plus emailed password; its commercial option is ODbL share-alike).

### Cited findings
- **Copernicus DEM GLO-30**, full licence text read [V]:
  - Rights granted to "any natural or legal person": reproduction; distribution; communication to the public; "adaptation, modification and combination with other data". Rights are "worldwide and without limitation in time" and "free of charge".
  - **No non-commercial restriction.**
  - Required notice: "© DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018 provided under COPERNICUS by the European Union and ESA; all rights reserved". For modified data: "produced using Copernicus WorldDEM-30 …".
  - A no-liability sentence must be passed on to users. Users must not imply endorsement.
  - [Licence COP-DEM-GLO-30-F (PDF)](https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/Data/DEM/resources/license/License-COPDEM-30.pdf)
  - The AWS bucket `copernicus-dem-30m` can be listed without an account. The bucket readme links an older, more restrictive licence. Downloading from the Copernicus Data Space needs a CDSE account [S] — [AWS Registry](https://registry.opendata.aws/copernicus-dem/); [Sentinel Hub forum](https://forum.sentinel-hub.com/t/copernicus-dem-license-update-on-aws/3815)
- **Global 30 m HAND (ASF):** derived from GLO-30 2021, **CC0 1.0** plus Copernicus attribution, no account [V] — [AWS Registry: glo-30-hand](https://registry.opendata.aws/glo-30-hand/)
- **FABDEM:**
  - **CC BY-NC-SA 4.0** for non-commercial use; commercial use through Fathom (fabdem@fathom.global).
  - The Bristol repository labels it "Non-Commercial Government Licence", which is inconsistent.
  - [S] — [Fathom: License the data](https://www.fathom.global/insight/fabdem-download/); [GEE community catalog](https://gee-community-catalog.org/projects/fabdem/)
  - **Disqualified.** The Bristol data page timed out this session.
- **MERIT Hydro:**
  - Dual licence, **CC BY-NC 4.0 or ODbL 1.0**. Under ODbL "derived data must be made publicly available under ODbL"; the example given is a commercial flood hazard map service having to publish its map under ODbL.
  - Download needs a Google Form registration and an emailed password.
  - Redistributing the whole dataset unchanged needs written permission. Resolution is 3 arc-seconds (~90 m).
  - [V] — [MERIT Hydro](https://global-hydrodynamics.github.io/MERIT_Hydro/)
  - **Disqualified** (registration).
- **HydroSHEDS / HydroRIVERS:**
  - "freely available for scientific, educational and commercial use". Full agreement in HydroSHEDS_TechDoc_v1_4.pdf.
  - Direct download, no login mentioned.
  - HydroRIVERS is extracted at **15 arc-seconds (~500 m)**.
  - Cite Lehner & Grill (2013), Hydrological Processes 27(15).
  - [V] — [HydroRIVERS](https://www.hydrosheds.org/products/hydrorivers)
  - The general site terms say only that each product has its own licence [V] — [HydroSHEDS terms](https://www.hydrosheds.org/terms-of-use)
- **JRC Global Surface Water:**
  - "produced under the Copernicus Programme and is provided free of charge, without restriction of use".
  - Cite Pekel et al. 2016 (Nature 540:418–422). Map credit "Source: EC JRC/Google".
  - Tiles download from the browser; a Python script is offered for the full v1.5 set; 30 m; 1984–2024.
  - [V] — [GSW download](https://global-surface-water.appspot.com/download)
- **ESA WorldCover 10 m:** "free of charge, without restriction of use", **CC BY 4.0**. Also on AWS Open Data [S] — [WorldCover 2021 download](https://worldcover2021.esa.int/download); [AWS Registry](https://registry.opendata.aws/esa-worldcover-vito/index.html)
- **GHSL (GHS-BUILT-S etc.):** **CC BY 4.0** per JRC. On S3 (`s3://jrc-ghsl/`) with no account. Latest built-up surface found: R2023A. One LifeWatch catalogue record is inconsistent (labels it CC0) [S] — [AWS Registry: GHS-BUILT-S](https://registry.opendata.aws/ghs-built-s/); [GHSL how to cite](https://human-settlement.emergency.copernicus.eu/GHSLhowToCite.php)
- **OpenStreetMap (ODbL):**
  - Credit OSM, make clear the data is ODbL, and link to the copyright page.
  - "If you alter or build upon our data, you may distribute the result only under the same license."
  - The page leaves the derivative-database versus produced-work line to the legal code.
  - Service limits (tiles, Nominatim) are separate from the licence.
  - [V] — [OSM copyright](https://www.openstreetmap.org/copyright)

### Inferences
- Under ODbL, GeoAlert's per-barangay features computed from OSM (distance to river, building density) are arguably a derived database. If GeoAlert ever *distributes* that feature table publicly, share-alike may apply. Maps and risk scores shown to users are more likely "Produced Works", which need attribution only. Keep OSM-derived tables internal, and put "© OpenStreetMap contributors, ODbL" on map views. **[NV, legal interpretation, not legal advice]**
- NOAH maps are also ODbL (Q2), so the same rule applies to any NOAH-derived barangay table.
- HydroRIVERS at ~500 m will miss Talisay's small creeks and drainage lines. It adds little over OSM rivers plus GLO-30 HAND. JRC GSW mainly shows permanent or seasonal water and probably misses brief urban flooding. Its value is checking river-channel positions and migration along the Mananga. **[NV]**
- Comparing ASF HAND against GeoAlert's own HAND is a quick consistency check, since both come from GLO-30. Any difference shows how sensitive the HAND<2 m and HAND<5 m flags are to the stream-initiation threshold. **[NV]**

### Gaps
- The MERIT DEM licence was not confirmed this session.
- The HydroSHEDS TechDoc licence text was not read; the summary comes from the product page.
- The FABDEM Bristol repository page timed out, so the licence label conflict is unresolved. It does not change the outcome: no non-commercial licence qualifies.

---

## Q6. Open-source physically based and hydrologic tools: licences and feasibility for 22 barangays with no gauges

### Takeaway
Most tools are free and permissively or copyleft licensed: SWMM (public domain), ANUGA (Apache-2.0), LISFLOOD (EUPL-1.2), LISFLOOD-FP 8 (GPL-3.0), Delft3D FM engines (AGPL-3.0/GPL-3.0; GUIs need registration), NeuralHydrology (BSD-3-Clause). HEC-RAS/HMS are free US-government software with terms-of-use conditions, not open source. With no stream gauges, no drainage-network data and only 5 event days, **none can be calibrated** for Talisay. A home-built hydraulic model would mostly reproduce what NOAH already did with LiDAR. The realistic uses are SWMM for a drainage study of Tabunok if the city has drain inventories, or ANUGA / LISFLOOD-FP for design-storm "what-if" maps.

### Cited findings
- **EPA SWMM:** the source code is "released in the Public Domain". It is a "dynamic hydrology-hydraulic water quality simulation model for stormwater, wastewater, and combined sewer collection systems", maintained by US EPA ORD [V, README; LICENSE file path not found] — [USEPA/Stormwater-Management-Model](https://github.com/USEPA/Stormwater-Management-Model)
- **ANUGA:** **Apache License 2.0** (LICENSE.txt read). Finite-volume shallow-water model for "floods, tsunamis and storm surges". ANUGA 4.0 added a GPU/multicore solver. Installs with `conda install anuga` (conda-forge) [V] — [anuga-community/anuga_core](https://github.com/anuga-community/anuga_core); [LICENSE.txt](https://raw.githubusercontent.com/anuga-community/anuga_core/main/LICENSE.txt)
- **LISFLOOD (EC JRC):** **EUPL-1.2**. The hydrological model behind EFAS/GloFAS. Needs Python ≥3.10 <3.13, PCRaster and GDAL, or Docker [V] — [ec-jrc/lisflood-code](https://github.com/ec-jrc/lisflood-code)
- **LISFLOOD-FP 8.0:** "freely available under the GPL v3 license". Solvers: DG2 and FV1 shallow-water, plus the original local-inertia (ACC) solver. Runs on multi-core CPUs and GPUs [S, GMD paper and Zenodo via search] — [GMD 14, 3577, 2021](https://gmd.copernicus.org/articles/14/3577/2021/); [Zenodo](https://zenodo.org/record/4073011)
- **Delft3D / Delft3D FM:**
  - Engine source on GitHub. "Most simulation engines are licensed under AGPL-3.0 or GPL-3.0", utilities LGPL-2.1.
  - Precompiled Windows GUIs for Delft3D 4 need registration on the Deltares site. Full packages come with paid service packages.
  - [S] — [Deltares/Delft3D](https://github.com/Deltares/Delft3d)
- **HEC-RAS (USACE):**
  - Older manuals state the software is public domain and "may be used, copied, distributed, or redistributed freely", with acknowledgement.
  - Users must accept Terms and Conditions for Use. Derived products may not use the "HEC-RAS" name. US export rules apply.
  - FEMA's model list marks HEC-RAS 6.0+ as "Public Domain: No", which conflicts with the manuals.
  - [S] — [HEC-RAS 5.0 Reference Manual](https://uon.sdsu.edu/HEC-RAS_5.0_Reference_Manual.pdf); [FEMA national models list](https://www.fema.gov/es/node/618464)
  - HEC-HMS terms were not checked.
- **NeuralHydrology:** **BSD-3-Clause**. A "Python library to train neural networks with a strong focus on hydrological applications", built on PyTorch [V] — [neuralhydrology/neuralhydrology](https://github.com/neuralhydrology/neuralhydrology)

### Inferences
- **NeuralHydrology** (LSTM rainfall-runoff) needs long discharge records from many gauged basins. Talisay has no gauges, so it is **infeasible**. It also brings PyTorch into a CPU-only stack for no gain.
- **LISFLOOD (JRC)** is a catchment-to-continental water-balance model needing many gridded inputs and calibration. It is far too heavy for this setting.
- **SWMM** is the only tool built for urban drainage (Tabunok). It needs drain and culvert geometry, inverts and subcatchments that the city probably lacks. It is worth it only if Talisay's engineering office holds a drainage master plan. Python wrappers exist (pyswmm, swmm-toolkit), but their licences were **[NV]**.
- **ANUGA** (Apache-2.0, CPU-capable) or **LISFLOOD-FP** (GPL-3.0) could run uncalibrated design-storm simulations on GLO-30 or better terrain for the lower Mananga. Without validation data they give relative "where" maps, which is what NOAH already provides at LiDAR resolution. Use NOAH first and model only if NOAH has gaps over Talisay.
- GPL, AGPL and EUPL tools are fine to *run* commercially. Copyleft duties start when the software is distributed (for AGPL, also when offered over a network). Running them offline to make data layers creates no source-release duty for GeoAlert. **[NV, general licence reading, not legal advice]**

### Gaps
- No public drainage inventory for Talisay was found; whether one exists is unknown.
- Current HEC-RAS 6.x or HEC-HMS terms were not read directly from hec.usace.army.mil.
- The exact SWMM LICENSE file text was not found (the raw path returned 404).

---

## Q7. Global flood services and their access rules (Google Flood Hub, GloFAS/CEMS, NASA GFMS)

### Takeaway
All three are **disqualified as data sources** under the no-account / no-key rule:
- Google's Flood Forecasting API needs a waitlist, a Google Cloud project and an API key. The data itself is CC BY 4.0.
- GloFAS data needs EWDS registration, and some data is restricted.
- GFMS has no clear current download route; its archived data goes through Earthdata.

The Flood Hub web map can still be *viewed* by DRRMO staff as situational awareness.

### Cited findings
- **Google Flood Forecasting API:** "Submit the waitlist form… Google emails you once you're approved". You need a Google Cloud account, an **API key** and to enable the API in a Cloud project. The API is "offered at no charge"; data licensed **CC BY 4.0**. The country coverage list is on a separate page [V] — [developers.google.com/flood-forecasting](https://developers.google.com/flood-forecasting)
  - The Flood Hub web interface lists the Philippines among covered locations [S] — [Flood Hub help](https://support.google.com/flood-hub)
  - **Disqualified** (waitlist, account, API key).
- **GloFAS / CEMS-Floods:** hosted on the Copernicus **Early Warning Data Store (EWDS)**; "freely accessible upon registration to ECMWF". Some EFAS/GloFAS data is restricted under Art. 12 of Delegated Regulation (EU) 1159/2013 [S] — [CEMS-FLOODS licence](https://ewds.climate.copernicus.eu/licences/cems-floods); [GloFAS forecast dataset](https://ewds.climate.copernicus.eu/datasets/cems-glofas-forecast)
  - **Disqualified** (account).
- **NASA GFMS:** no current bulk download or API documentation found at flood.umd.edu. The archived IFloodS GFMS subset (0.25°, 3-hourly, 2013) is distributed via NASA GHRC / Earthdata Search [S] — [data.gov record](https://catalog.data.gov/dataset/gpm-ground-validation-global-flood-monitoring-system-gfms-flood-maps-ifloods-v1-d9aca); [NASA Earthdata floods tools](https://www.earthdata.nasa.gov/topics/floods/data-access-tools?page=0%2C1)
  - **Disqualified / not verifiable** for real-time use.
- **Also disqualified (from Q4/Q5):**
  - GSMaP: registration, plus advance notice to JAXA for commercial use.
  - MSWEP: CC BY-NC, request form, paid commercial API.
  - ERA5 via CDS: account.
  - IMERG: Earthdata login.
  - MERIT Hydro: registration form and password.
  - FABDEM: non-commercial; commercial licence from Fathom.
  - 510 operational pipeline: credentials.
  - PAGASA station data for commercial use: fees and signed T&C.
  - SAOFFGS: closed to the public **[NV]**.

### Inferences
- The Mananga is a short coastal river. Even where Flood Hub or GloFAS model a reach nearby, their skill on small, steep, ungauged Visayas catchments is unknown and probably low. Their value to GeoAlert would be situational awareness at most, even if access were allowed. **[NV]**

### Gaps
- Whether Flood Hub or GloFAS include a Mananga River forecast point was not checked; that needs a login or API.
- No public current GFMS download or licence was found.

---

## Q8. With only 5 flood days, what gives the most defensible improvement?

### Takeaway
Stop trying to *learn* "where" from 18 records. **Split the model:** (1) a city-level "flood day" model with 1–3 inputs (multi-day rain from a better rain source, plus a tropical-cyclone proximity flag), fitted with Firth or Bayesian shrinkage or set as transparent PAGASA-style thresholds; (2) a fixed, externally sourced "where" layer: NOAH 25/100-year flood hazard shares plus HAND, with river versus drainage handled separately. Evaluate by event day (leave-one-event-day-out; hits, misses and false-alarm days per year), not by pooled AUC. Every recommended input passed the licence checks above.

### Cited findings (supporting evidence, from Q1–Q7)
- Small-sample logistic regression overestimates associations, and EPV rules are weakly supported. Firth penalisation is the standard low-cost fix — [van Smeden 2016](https://link.springer.com/article/10.1186/s12874-016-0267-3); [Statistical Horizons](https://statisticalhorizons.com/?p=1076); [Williams notes](https://www3.nd.edu/~rwilliam/stats3/RareEvents.pdf)
- Urban rainfall thresholds work better when split into drainage-overload and disastrous-runoff levels — [Jang, Water 2015](https://doaj.org/article/9c5aa53dbb2f4b83a781c9d1a803027b)
- Impact-record-based thresholds (fire-service call-outs) have been derived for urban flash floods — [Papagiannaki et al., NHESS 2015](https://nhess.copernicus.org/articles/15/1859/2015/nhess-15-1859-2015.pdf)
- The operational Philippine impact model relies on max 6 h and 24 h rain, a ~3-day total, track distance and wind, uses NOAH hazard maps as local features, and uses a two-stage design — [NHESS 2024](https://nhess.copernicus.org/articles/24/309/2024/)
- NOAH flood hazard maps (5/25/100-year, depth classes) are downloadable under ODbL — [SCO](https://www.spaceclimateobservatory.org/noah); [HF mirror](https://huggingface.co/datasets/bettergovph/project-noah-hazard-maps)
- CHIRPS v3 at 0.05° is CC BY 4.0 with no login, and has better high-rainfall capture than v2 — [CHC CHIRPS3](https://www.chc.ucsb.edu/data/chirps3)
- IBTrACS has no account and full, open access — [NCEI IBTrACS](https://www.ncei.noaa.gov/products/international-best-track-archive)
- PAGASA accumulated-rain advisory bands (50/100/200 mm) and hourly bands (7.5/15/30 mm/h) [S] — [Varsitarian explainer](https://varsitarian.net/sci-tech/20250724/explainer-how-do-pagasas-rainfall-warnings-and-weather-advisories-work)
- The 2006 MGB assessment found 7 flood-prone barangays along the Mananga. About 5,000 families in 10 Mananga barangays were hit by Tino — [Philstar 2006](https://philstar.com/cebu-news/2006/07/02/345125/denr-assesses-talisays-7-flood-prone-areas); [SunStar](https://www.sunstar.com.ph/cebu/riverside-living-worsened-tino-damage)

### Inferences (ranked by expected value per unit of effort; all **[NV]** design judgements)
1. **Separate "when" from "where".**
   - "When": one row per city-day, outcome = any flood record that day (5 positives out of ~1,826 days).
   - Use at most 2–3 predictors: a 3-day rain sum, a TC-within-R-km flag and possibly a 1-day sum. Fit with Firth logistic, or a Bayesian logistic with weakly informative priors (for example a positive prior on rain coefficients).
   - Alternatively, publish a **threshold rule** anchored to PAGASA's 50/100/200 mm accumulated bands and calibrated on the 5 days. A rule is easier to defend to DRRMO than a coefficient.
2. **Fix "where" from external evidence, not fitting.**
   - Barangay or sitio prior = share of area or buildings in NOAH 25-year and 100-year hazard class ≥2, plus HAND<2 m and HAND<5 m shares.
   - Combine as P(flood at b | flood day) ∝ prior(b). Check against the 18 records only as a sanity check (do records fall in high-prior barangays?). Do not fit weights on them.
   - This replaces the 0.36 leave-one-barangay-out component with something that does not depend on 18 points.
3. **Two hazard channels.**
   - River overflow (8 records): driven by Mananga *catchment* rain (upstream CHIRPS cells, 1–3-day sums) times NOAH/HAND exposure along the river.
   - Drainage / pluvial (Tabunok-type): driven by short intense rain (PAGASA hourly bands, when available live) times built-up share (GHSL/WorldCover) and low local relief.
   - Each channel gets its own small threshold. With 3 Tabunok records, the drainage channel should be framed as "elevated when hourly warning is orange/red", not as a fitted model.
4. **Upgrade rain for training:** add CHIRPS v3 (0.05°) and, as a cross-check, PERSIANN-CDR (0.25°) for 2021–2025. Keep POWER as the low-latency fallback. Compare all sources on the 5 event days before choosing. If none shows heavy rain on 2025-08-18, treat that record as non-rain-driven or mis-dated and flag it for DRRMO review.
5. **Add storm context from IBTrACS:** minimum distance from Talisay to any TC centre over the past 72 h, and that storm's maximum wind. This is likely the single most informative "when" feature given the records cluster on storm days.
6. **Tackle under-recording, which affects precision more than any model change:**
   - Treat "no record" as "unknown", not "no flood" (a presence-only / positive-unlabelled view). elapid's MaxEnt (MIT) suits *spatial* presence-only fitting, but with 18 presences it is still weak. Prefer the external prior in step 2.
   - Mine news archives (for example the 2021-06-15 Talisay floods headline) and DRRMO logbooks for missed events, with a source per event, as was done for the 2026-11-08 sourced seed.
7. **Evaluate honestly:**
   - Leave-one-event-day-out for "when".
   - For "where", report the share of records falling in NOAH high-hazard areas against the share of area that is high-hazard (a lift ratio). Skip leave-one-barangay-out AUC, which is meaningless with 0–3 records per barangay.
   - Report false-alarm days per year at the chosen threshold, which is what DRRMO acts on.
8. **Do not** build a hydraulic model, use NeuralHydrology, or move to ML ensembles. Nothing in the evidence suggests they can beat a small model plus NOAH priors with 5 event days.

**Licence summary of what is recommended** (all verified above unless marked):

| Input | Licence / access | Status |
|---|---|---|
| CHIRPS v3 (and v2 until end of 2026) | CC BY 4.0 + waiver (v3); public-domain waiver (v2); open HTTP | Qualifies [V] |
| PERSIANN-CDR (NCEI) | "No constraints on data access or use" (ERDDAP metadata) | Qualifies [S] |
| IBTrACS | WDC full and open access; commercial use guided by WMO Res. 40; no login | Qualifies with a note [V] |
| NOAH flood hazard 5/25/100-year | ODbL (attribution; share-alike on derived DBs) | Qualifies; confirm on the NOAH site [S] |
| Copernicus DEM GLO-30 | Free, any legal person, attribution notices; AWS no account | Qualifies [V] |
| ASF GLO-30 HAND | CC0 1.0; AWS no account | Qualifies [V] |
| JRC GSW / ESA WorldCover / GHSL | Copernicus "without restriction" / CC BY 4.0 / CC BY 4.0 | Qualifies [V]/[S]/[S] |
| OSM | ODbL | Qualifies with obligations [V] |
| elapid (MaxEnt) | MIT | Qualifies [V] |
| ANUGA / SWMM | Apache-2.0 / public domain | Qualifies [V]; not recommended now |
| scikit-learn, statsmodels, XGBoost, PyMC, a Firth implementation | BSD-3 / BSD-3 / Apache-2.0 / Apache-2.0 / ? | **[NV] this session** |

### Gaps
- Licences of the Python libraries GeoAlert would use for steps 1–2 (scikit-learn, statsmodels, XGBoost, PyMC, any `firthlogist`-type package, pysheds/whitebox for HAND) were not checked this session. Read each LICENSE file before adding a dependency.
- No published study was found that tested a split "when" model plus external-prior "where" model against a pooled ML model on a few-event city dataset. The recommendation rests on the small-sample statistics and impact-forecasting practice above, not on a direct benchmark.
- Whether GeoAlert's 5 event days coincide with TCs, and what CHIRPS shows on them, can only be checked with the project's own data. That is the first experiment to run.
