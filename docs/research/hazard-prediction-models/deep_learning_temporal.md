# Deep learning and temporal models for GeoAlert flood, landslide and fire prediction (state as of 2026-11-13)

Scope note: notes for the report writer. Covers deep learning (DL) and temporal model families against GeoAlert's data: flood = 18 positive barangay-days on 5 storm days (40,172 barangay-day rows, 2021-2025, one ~0.5 degree NASA POWER rain cell); landslide = 8 positive days (7 in one barangay); fire = 219 fires, monthly x 22 barangays x ~46 months. Current models: logistic regression (flood, landslide) and Poisson GLM (fire); the MLP tied the GLM (Brier 0.1391 vs 0.1394) only when heavily regularized.

How things were checked: licences come from the repository LICENSE files (fetched raw from GitHub), PyPI JSON metadata and the Hugging Face (HF) model API (`gated`, `cardData.license`), all queried on 2026-11-13. Release dates are PyPI upload times. The GitHub API hit its rate limit, so GitHub "latest release" dates are missing for most repos. "Verified" means read from a primary source in this session. "Assumed" or "not re-verified" means taken from memory or a secondary summary.

---

## 1. What data volumes did successful flood/landslide DL studies use, what did they beat, and is there evidence DL works for binary occurrence with 5-18 event days?

### Takeaway
Every DL hazard success found here trained on hundreds to thousands of sites, or on thousands of labelled events. They also mostly predict a **continuous** target (streamflow, water level, displacement), not a rare binary label. The landslide-occurrence DL study with the most data (Mondini et al. 2023: 2,472 landslide-triggering rainfall events) still found only a "slight" edge over SVMs. No study was found showing DL working on 5-18 event days. GeoAlert has about 300x fewer landslide events than Mondini, and its flood signal comes down to 5 storm days seen through a single rain cell.

### Cited Findings
**LSTM rainfall-runoff (continuous streamflow target)**
- Kratzert et al. 2018 (HESS 22, 6005) used **241 CAMELS catchments**. The first **15 hydrological years** (mostly 1 Oct 1980-30 Sep 1995) were the calibration set and the rest was validation. The benchmark was SAC-SMA + Snow-17, and the LSTM beat it only after regional pre-training plus fine-tuning — [HESS 2018](https://hess.copernicus.org/articles/22/6005/2018/) (verified, full text).
- Kratzert et al. 2019 (HESS 23, 5089) trained one EA-LSTM on **531 CAMELS basins** using 5 daily Maurer forcings plus 27 static catchment attributes. Training ran 1 Oct 1999-30 Sep 2008 (about 9 years) and evaluation 1 Oct 1989-30 Sep 1999. Median NSE was **0.74 (ensemble of 8) / 0.71 (individual)**, against 0.31 for regionally calibrated VIC and 0.53 for mHM. Basin-calibrated SAC-SMA, VIC, FUSE, mHM and HBV were also compared, on the 447 basins that all models covered — [HESS 2019](https://hess.copernicus.org/articles/23/5089/2019/) (verified).
- Kratzert et al. 2024, "HESS Opinions: Never train an LSTM on a single basin" (HESS 28, 4187), compared single-basin LSTM ensembles (10 models per basin, about 10 years per split) with one regional model over all 531 basins. In the test period, **more than 6,000 observations exceeded the single-basin models' theoretical maximum prediction, against 10 for the regional model**. Median skill rose as more basins were added. The authors say there "should never be an excuse not to use at least hundreds of basins for training" — [HESS 2024](https://hess.copernicus.org/articles/28/4187/2024/) (verified).
- Nearing et al. 2024 (Nature 627) is an LSTM-based global model for ungauged basins. At a **5-day lead time** its reliability on extreme events was similar to or better than **GloFAS** nowcasts (0-day lead). Its accuracy on 5-year return-period events was similar to or better than GloFAS on 1-year events. It runs operationally in 80+ countries, and the authors call for more hydrological data — [Nature abstract via Semantic Scholar](https://www.nature.com/articles/s41586-024-07145-1). Training used **5,680 gauges** with daily GRDC discharge 1980-2023, plus inputs from IMERG, ERA5-Land and others — [Google Research blog](https://research.google/blog/using-ai-to-expand-global-access-to-reliable-flood-forecasts/). The gauge count comes from the blog via a search summary; it did not show up when the blog HTML was grepped, so treat it as lightly verified. The blog does confirm the LSTM architecture.

**Landslide occurrence (binary, the closest analogue to GeoAlert)**
- Mondini et al. 2023 (Nature Communications 14) used Italy-wide data from **Feb 2002-Dec 2020**. That gave **780,766 reconstructed rainfall events, of which 2,472 (0.3%) triggered at least one landslide**, with hourly rain. Training and validation sets were **balanced** by subsampling no-landslide events, and testing used an unbalanced set (ratio about 1/100,000). The authors write that SVMs "are known for their performance with small data sets"; that "we have no a priori justification for preferring our approach to SVMs, except that... non-linear SVMs performed slightly less well"; and that ConvLSTM "require[s] further research" for landslides with gridded rain — [Nature Comms 2023](https://www.nature.com/articles/s41467-023-38135-y), full text via [Europe PMC PMC10147618](https://pmc.ncbi.nlm.nih.gov/articles/PMC10147618/) (verified).
- Landslide **displacement** DL works on one monitored slope with a continuous target. One example is a day-ahead CNN on GNSS displacement at the Urbas landslide (Slovenia, monitored since 2019), whose stated aim is warnings near a displacement threshold — [Sci Rep 2025](https://doi.org/10.1038/s41598-025-29084-1). Another is an LSTM-SARIMA on open-pit slope displacement — [PLOS ONE 2025](https://doi.org/10.1371/journal.pone.0323650) (abstracts verified).

**ConvLSTM / GNN flood**
- Moishin et al. 2021 (IEEE Access) built a ConvLSTM to forecast a daily **Flood Index derived from precipitation** (a continuous index, not observed flood occurrence) at 9 rainfall sites in Fiji. 1-day RMSE was **0.101 vs 0.105 for the next best model** — [IEEE Access 2021](https://doi.org/10.1109/ACCESS.2021.3065939) (abstract verified).
- A Bangladesh ConvLSTM at 2 km on satellite imagery reported AUC > 0.9. It is a Research Square **preprint**, not peer-reviewed — [preprint](https://doi.org/10.21203/rs.3.rs-5409944/v1).
- Bentivoglio et al. 2023 (HESS 27, 4227), SWE-GNN, is a **surrogate of a numerical hydraulic solver**. It was trained on simulated dike-breach floods over randomly generated DEMs, with mean absolute error of 0.04 m for water depth on unseen topographies, and no observed events were used — [HESS 2023](https://hess.copernicus.org/articles/27/4227/2023/) (abstract verified).
- River-network GNNs train on continuous water-level series from gauge networks. Examples: a transformed GNN beat EA-LSTM on extreme water levels — [arXiv 2410.05536](https://arxiv.org/abs/2410.05536); FloodGTN uses station water levels, rainfall, tide and gate settings — [arXiv 2310.07631](https://arxiv.org/abs/2310.07631).

**Sample-size evidence for binary outcomes**
- van der Ploeg, Austin & Steyerberg 2014 ran a simulation study. Logistic regression reached a stable AUC at about **20-50 events per variable (EPV)**. **RF, SVM and neural nets "showed instability and a high optimism even with >200 events per variable"** — [BMC Med Res Methodol 2014](https://doi.org/10.1186/1471-2288-14-137) (abstract verified).
- Riley et al. 2020 (BMJ) give formal sample-size guidance for prediction models. They warn that many models are built "using a dataset that is too small for the total number of participants or outcome events" — [BMJ 2020](https://doi.org/10.1136/bmj.m441).

### Inferences
- GeoAlert's flood label carries about **5 independent events**. All barangays share one rain cell, so on a given day every barangay sees the same rain, and the 18 positive barangay-days collapse onto 5 storm days. Even with only 3-5 features that is about 1-2 EPV, below the comfortable range for logistic regression and roughly two orders of magnitude below where van der Ploeg saw neural nets stabilize. Landslide (8 events, 7 in one barangay) is worse.
- ConvLSTM and GNN models need a spatial input field (gridded radar or gauge rain) or a gauge graph with continuous water levels. GeoAlert has one 0.5 degree rain cell covering the whole city and no stage or discharge data, so there is nothing spatial for convolution or message passing to use.
- The hydrology successes (Kratzert, Nearing) are regression on dense continuous streamflow over hundreds to thousands of basins. They do not transfer to binary DRRMO incident labels. Kratzert 2024's single-basin finding (LSTMs trained on one basin cannot reach extremes outside their training range) is the closest analogy for a single-city model.
- Mondini's DL gain over SVM was "slight" even at 2,472 events. Nothing suggests DL would beat the current logistic regression at 5-8 events.

### Gaps
- No peer-reviewed study was found that trains DL for binary flood or landslide **occurrence** with fewer than about 50 events. A summary also mentioned an EGU23 abstract (Zhao & Chen, LSTM+TCN daily landslide probability, "90.33% vs 72.75%"). Its event count and its exact URL were not verified, so it is left out of the findings.
- The full Nature 2024 text (exact training sample counts, precision/recall by return period) could not be fetched because of a Nature login redirect.

---

## 2. DL vs simpler methods on small/tabular data and on time-series benchmarks

### Takeaway
Independent benchmarks agree that simple statistical or tree models are hard to beat on small or medium data. Pure ML lost in M4. Trees beat DL on tabular data of about 10K samples. One-layer linear models beat Transformers on standard long-horizon benchmarks. DL or ML wins (M5 LightGBM, N-BEATS, the ES-RNN hybrid) came with tens of thousands of series. GeoAlert's own MLP-ties-GLM result matches this.

### Cited Findings
- **M4** (100,000 series, 61 methods). "The six pure ML methods performed poorly, with none of them being more accurate than the combination benchmark and only one being more accurate than Naïve2". Of the 17 most accurate methods, 12 were combinations of mostly statistical approaches — [Makridakis et al. 2018 IJF 34(4)](https://econpapers.repec.org/RePEc:eee:intfor:v:34:y:2018:i:4:p:802-808). The same point is in the full 2020 paper — [IJF 36(1) 54-74](https://doi.org/10.1016/j.ijforecast.2019.04.014) — and the [SAS blog commentary](https://blogs.sas.com/content/forecasting/2020/01/08/m4-forecasting-competition-results-and-commentary).
- The M4 winner was a hybrid. N-BEATS (pure DL) later reported +3% over "last year's winner of the M4 competition, a domain-adjusted hand-crafted hybrid between neural network and statistical time series models", tested on M3/M4/TOURISM, which are large collections — [arXiv 1905.10437](https://arxiv.org/abs/1905.10437).
- **M5** (42,840 hierarchical Walmart sales series, about 5,500 teams in Accuracy). The winner was an equal-weighted ensemble of LightGBM models, and **45 of the top 50 used LightGBM**. "Relatively straightforward ML models improved... benchmarks by up to roughly 20%" — [Makridakis et al. 2022 IJF 38(4)](https://doi.org/10.1016/j.ijforecast.2021.11.013), [PDF](https://statmodeling.stat.columbia.edu/wp-content/uploads/2021/10/M5_accuracy_competition.pdf). These are search-summary quotes from the paper; no per-intermittency breakdown was found.
- **Grinsztajn, Oyallon & Varoquaux 2022** (NeurIPS) used 45 tabular datasets and about 20,000 compute-hours of hyperparameter search per learner. "Tree-based models remain state-of-the-art on medium-sized data (~10K samples)". Neural nets are less robust to uninformative features and favour smooth solutions — [arXiv 2207.08815](https://arxiv.org/abs/2207.08815) (abstract verified).
- **Zeng et al. 2023** (AAAI) found "embarrassingly simple one-layer linear models" (LTSF-Linear / DLinear) "outperform existing sophisticated Transformer-based LTSF models in all cases" on 9 benchmarks — [arXiv 2205.13504](https://arxiv.org/abs/2205.13504) (abstract verified). This is contested: a Hugging Face blog shows Autoformer beating DLinear on MASE for Traffic, Exchange and Electricity (e.g. 0.910 vs 0.965) — [HF blog 2023](https://huggingface.co/blog/autoformer). That rebuttal is a non-peer-reviewed blog.
- N-HiTS reports about 20% better accuracy than recent Transformers on long-horizon benchmarks at 1/50 the compute — [arXiv 2201.12886](https://arxiv.org/abs/2201.12886). These are again large dense benchmark datasets.

### Inferences
- All of these benchmarks have far more data than GeoAlert (M4: 100K series; M5: 42,840; Grinsztajn: about 10K rows per dataset with dense labels). Even there, simple models are competitive or better. At GeoAlert's scale (1,012 fire barangay-months; 5 flood event-days) the burden of proof sits with DL.
- GeoAlert's MLP only matched the GLM once heavily regularized toward linear. That is the expected small-data behaviour (Grinsztajn's smooth-solution bias; van der Ploeg's optimism), and it suggests the problem's signal is close to linear on a log scale.
- These benchmarks are not hazard datasets and use different metrics (sMAPE/MASE/WRMSSE, not Brier). They support a general direction, not a GeoAlert-specific number.

### Gaps
- No benchmark was found that compares DL against GLMs for **sparse count or binary hazard outcomes** at GeoAlert's scale. The intermittent-series breakdown inside M5 was not retrieved.

---

## 3. Temporal Fusion Transformer (TFT): data needs, interpretability claims, implementations and licences

### Takeaway
TFT was shown on large panels (41 to about 130,000 entities, mostly hourly or daily). It is built for multi-horizon forecasting of continuous targets with many covariates. Its interpretability comes from variable-selection weights and attention. Three permissively licensed CPU-capable implementations exist (PyTorch Forecasting MIT; Darts and neuralforecast Apache-2.0). Nothing suggests it suits 5-18 binary events or 1,012 monthly count cells.

### Cited Findings
- Lim et al. 2021 (IJF 37(4)) combine recurrent layers for local processing with "interpretable self-attention layers for long-term dependencies", plus feature-selection and gating components. They show "significant performance improvements over existing benchmarks" and "three practical interpretability use-cases" — [arXiv 1912.09363](https://arxiv.org/abs/1912.09363), [IJF DOI](https://doi.org/10.1016/j.ijforecast.2021.03.012).
- Datasets in the TFT paper (Table 1): **Electricity, 370 customers, hourly; Traffic, 440 SF Bay freeways, hourly; Retail (Favorita), about 130k entities; Volatility, 41 entities** — [ar5iv full text](https://ar5iv.labs.arxiv.org/html/1912.09363) (verified).
- PyTorch Forecasting lists TFT as outperforming "DeepAR by Amazon by 36-69% in benchmarks". It runs on CPU via PyTorch Lightning ("allow training on CPUs, single and multiple GPUs out-of-the-box") — [README](https://github.com/sktime/pytorch-forecasting) (verified). Licence: **MIT** — [LICENSE](https://github.com/sktime/pytorch-forecasting/blob/main/LICENSE). Latest **1.8.0 (2026-06-24)**, Python <3.15 — [PyPI](https://pypi.org/project/pytorch-forecasting/) (verified).
- Darts (TFTModel) is **Apache-2.0**, latest 0.48.1 (2026-10-16) — [LICENSE](https://github.com/unit8co/darts/blob/master/LICENSE), [PyPI](https://pypi.org/project/darts/). neuralforecast (TFT) is **Apache-2.0**, latest 3.3.1 (2026-11-10) — [LICENSE](https://github.com/Nixtla/neuralforecast/blob/main/LICENSE), [PyPI](https://pypi.org/project/neuralforecast/). Licences and versions were verified; the TFT class names in Darts and neuralforecast were not re-fetched this session (assumed from their documentation).
- Count or binary output heads exist: Darts has `PoissonLikelihood`, `NegativeBinomialLikelihood` and `BernoulliLikelihood` — [darts source](https://github.com/unit8co/darts/blob/master/darts/utils/likelihood_models/torch.py). neuralforecast `DistributionLoss` wraps torch `Poisson`, `NegativeBinomial` and `Bernoulli` — [neuralforecast losses](https://github.com/Nixtla/neuralforecast/blob/main/neuralforecast/losses/pytorch.py) (verified in source).

### Inferences
- TFT's smallest showcase panel (Volatility, 41 entities, daily, dense continuous target) already has far more dense signal than GeoAlert's fire panel (22 series x 46 monthly points, at least about 78% zeros (219 fires cannot fill more than 21.6% of about 1,012 cells)). The model has many parameters (LSTM encoder plus attention plus variable-selection networks), so overfitting on 219 fires is very likely.
- TFT's interpretability (variable-selection weights, attention over time) is not more trustworthy than GLM coefficients with confidence intervals. For a DRRMO audience, the GLM's "rate ratio per mm of rain" is easier to defend.
- CPU training is feasible at GeoAlert's size (minutes; assumed, not benchmarked). Compute is not the obstacle; data is.

### Gaps
- No published TFT application to rare binary hazard occurrence was found. There is no published minimum-data guidance for TFT.

---

## 4. Libraries: exact licences, latest releases, CPU feasibility

### Takeaway
Every general-purpose framework and forecasting library checked is permissively licensed (MIT, Apache-2.0 or BSD-3) and needs no account. All run on CPU. Licensing does not block any library. The restrictions sit in some **pretrained weights** (section 5) and in **cloud APIs** (TimeGPT, TabPFN client).

### Cited Findings
Verified 2026-11-13 (LICENSE file plus PyPI metadata). Dates are PyPI upload dates.

| Library | Licence (LICENSE URL) | Latest (date) | Python | CPU / notes |
|---|---|---|---|---|
| PyTorch | BSD-style custom text ([LICENSE](https://github.com/pytorch/pytorch/blob/main/LICENSE)); GitHub API reports NOASSERTION; PyPI expression lists BSD-3-Clause plus bundled Apache-2.0/MIT/BSD-2/BSL-1.0/ISC/Zlib parts | torch 2.15.0 (2026-10-28) | >=3.11 | CPU wheels standard |
| TensorFlow | Apache-2.0 ([LICENSE](https://github.com/tensorflow/tensorflow/blob/master/LICENSE)) | 2.21.0 (2026-03-06) | >=3.10 | CPU OK |
| Keras | Apache-2.0 ([LICENSE](https://github.com/keras-team/keras/blob/master/LICENSE)) | 3.15.1 (2026-07-29) | >=3.11 | CPU OK |
| PyTorch Lightning / lightning | Apache-2.0 ([LICENSE](https://github.com/Lightning-AI/pytorch-lightning/blob/main/LICENSE)) | 2.6.6 (2026-09-10) | >=3.10 | CPU OK |
| PyTorch Forecasting | MIT ([LICENSE](https://github.com/sktime/pytorch-forecasting/blob/main/LICENSE)) | 1.8.0 (2026-06-24) | 3.10-3.14 | CPU OK (README) |
| Darts | Apache-2.0 ([LICENSE](https://github.com/unit8co/darts/blob/master/LICENSE)) | darts 0.48.1 (2026-10-16); u8darts 0.41.0 (2026-02-10) | >=3.11 | CPU OK |
| neuralforecast | Apache-2.0 ([LICENSE](https://github.com/Nixtla/neuralforecast/blob/main/LICENSE)) | 3.3.1 (2026-11-10) | >=3.11 | CPU OK |
| statsforecast | Apache-2.0 ([LICENSE](https://github.com/Nixtla/statsforecast/blob/main/LICENSE)) | 2.1.1 (2026-07-16) | >=3.10 | CPU-native (numba) |
| mlforecast | Apache-2.0 ([LICENSE](https://github.com/Nixtla/mlforecast/blob/main/LICENSE)) | 1.1.0 (2026-07-10) | >=3.10 | CPU |
| hierarchicalforecast | Apache-2.0 ([LICENSE](https://github.com/Nixtla/hierarchicalforecast/blob/main/LICENSE)) | 1.5.3 (2026-09-24) | 3.10-3.x | CPU |
| GluonTS | Apache-2.0 ([LICENSE](https://github.com/awslabs/gluonts/blob/master/LICENSE)) | 0.17.0 (2026-07-31) | 3.10-3.14 | CPU OK |
| sktime | BSD-3-Clause ([LICENSE](https://github.com/sktime/sktime/blob/main/LICENSE)) | 1.3.0 (2026-11-08) | 3.11-3.15 | CPU |
| NeuralHydrology | BSD-3-Clause ([LICENSE](https://github.com/neuralhydrology/neuralhydrology/blob/master/LICENSE)) | 1.13.0 (2026-01-14) | >=3.10 | CPU possible; designed for CAMELS-style continuous discharge |
| tsai | Apache-2.0 ([LICENSE](https://github.com/timeseriesAI/tsai/blob/main/LICENSE)) | 1.0.1 (2026-05-27) | >=3.10 | CPU OK |
| statsmodels | BSD-3-Clause | 0.15.0 (2026-08-27) | >=3.10 | CPU |
| scikit-learn | BSD-3-Clause | 1.9.1 (2026-09-10) | >=3.11 | CPU |
| tick (Hawkes) | BSD-3-Clause ([LICENSE.txt](https://github.com/X-DataInitiative/tick/blob/master/LICENSE.txt)) | 0.8.0.2 (2026-05-04) | >=3.11 | Pre-built wheels for Linux/macOS/Windows ([README](https://github.com/X-DataInitiative/tick)) |
| hawkeslib | MIT ([LICENSE](https://github.com/canerturkmen/hawkeslib/blob/master/LICENSE)) | 0.2.2 (**2019-06-18**, stale) | - | CPU; unmaintained |
| EasyTPP (neural TPPs) | Apache-2.0 ([LICENCE](https://github.com/ant-research/EasyTemporalPointProcess/blob/main/LICENCE)) | easy-tpp 0.3.0 (2026-07-13) | - | PyTorch only since 2025 ([README](https://github.com/ant-research/EasyTemporalPointProcess)) |

Sources: PyPI pages, e.g. [torch](https://pypi.org/project/torch/), [statsforecast](https://pypi.org/project/statsforecast/), [sktime](https://pypi.org/project/sktime/), [tick](https://pypi.org/project/tick/), [easy-tpp](https://pypi.org/project/easy-tpp/), [neuralhydrology](https://pypi.org/project/neuralhydrology/).
- statsforecast includes `CrostonClassic`, `CrostonOptimized`, `CrostonSBA` (code: Croston mean x 0.95), `TSB`, `ADIDA` and `IMAPA` — [models.py](https://github.com/Nixtla/statsforecast/blob/main/python/statsforecast/models.py) (verified in source).

### Inferences
- Python version constraints matter. torch, sktime, darts and neuralforecast need >=3.11. granite-tsfm needs <3.14 (section 5). Pin versions if anything is ever added.
- Adding torch to a modest Django CPU server brings a large install footprint and maintenance burden for no shown accuracy gain. Running any DL experiment **offline** in a notebook is cleaner than putting it in production.
- tick is the most practical permissively licensed Hawkes library (maintained, Windows wheels). hawkeslib has had no release since 2019.

### Gaps
- GitHub "latest release" dates were not retrievable (API rate limit), so PyPI dates are used. Transitive dependency licences (e.g. numba, pandas, pyarrow) were not audited individually; they are generally BSD or Apache, but that is assumed, not verified.

---

## 5. Time-series foundation models (TSFMs): licences of code AND weights, gating, CPU, covariates, binary/count support

### Takeaway
Only some TSFMs pass GeoAlert's licence rules:
- **Pass:** Amazon **Chronos / Chronos-Bolt / Chronos-2** (Apache-2.0, not gated), Google **TimesFM 1.0/2.0/2.5** (Apache-2.0, not gated), **Lag-Llama** (Apache-2.0), IBM **TTM r1/r2** (Apache-2.0), plus Sundial and Time-MoE.
- **Fail:** **TimesFM 3.0** (Aug 2026, Non-Commercial licence), **all Moirai** (CC BY-NC 4.0), **TTM research-r2** (CC BY-NC-SA), **TabPFN 2.5/2.6/3/3.5** (non-commercial plus login/token), **TimeGPT** (API key) and the **TabPFN client** (cloud).

Even the licensable ones produce **quantile or point forecasts of continuous values**. None has a binary or rare-event output, and their training data under-represents sparse, zero-heavy series. For flood and landslide they are unsuitable. For fire they are at most a cheap offline zero-shot challenger to the Poisson GLM. Re-checked against evidence, the earlier "skip Chronos/TimesFM" note holds for production.

### Cited Findings
**Licence and access status (HF API `gated` and card licence verified 2026-11-13)**

| Model | Code licence | Weights licence (HF) | Gated? | Covariates | CPU | Status |
|---|---|---|---|---|---|---|
| Chronos (T5), e.g. [amazon/chronos-t5-small](https://huggingface.co/amazon/chronos-t5-small) | Apache-2.0 ([LICENSE](https://github.com/amazon-science/chronos-forecasting/blob/main/LICENSE)); chronos-forecasting 2.3.2 (2026-09-08) | apache-2.0 | No | Only via external regressor ("per-timestep effects") | Yes | Allowed |
| Chronos-Bolt, [amazon/chronos-bolt-small](https://huggingface.co/amazon/chronos-bolt-small) (also -base; created 2024-11-25) | Apache-2.0 | apache-2.0 | No | Same as Chronos | Card: `device_map="cpu"` supported; "up to 250 times faster... than original Chronos" | Allowed |
| Chronos-2, [amazon/chronos-2](https://huggingface.co/amazon/chronos-2) (released 20 Oct 2025; **120M params**) | Apache-2.0 | apache-2.0 | No | **Native past-only and known-future covariates**, multivariate; context 8192, horizon 1024 | "supporting both GPU and CPU inference" (card) | Allowed |
| TimesFM 1.0 / 2.0 / 2.5, [google/timesfm-2.5-200m-pytorch](https://huggingface.co/google/timesfm-2.5-200m-pytorch) (created 2025-09-02) | Apache-2.0 ([LICENSE](https://github.com/google-research/timesfm/blob/master/LICENSE)); timesfm 3.0.2 (2026-09-09) | apache-2.0 (1.0-200m, 2.0-500m, 2.5-200m all checked) | No | 2.5: covariates "through XReg" (added back Oct 29 2025) | Assumed feasible (200M params); not benchmarked | Allowed (pin the 2.5 checkpoint) |
| **TimesFM 3.0**, [google/timesfm-3.0-pytorch](https://huggingface.co/google/timesfm-3.0-pytorch) (created 2026-08-24) | Repo Apache-2.0, but the model licence covers "weights, parameters and inference code" | **TimesFM Non-Commercial License v1.0** ("non-commercial and non-production use"; [LICENSE](https://huggingface.co/google/timesfm-3.0-pytorch/blob/main/LICENSE)) | No | Native covariates | - | **Disqualified** (non-commercial) |
| Moirai 1.1 / MoE / 2.0, e.g. [Salesforce/moirai-2.0-R-small](https://huggingface.co/Salesforce/moirai-2.0-R-small), [moirai-1.1-R-small](https://huggingface.co/Salesforce/moirai-1.1-R-small) | uni2ts Apache-2.0 ([LICENSE.txt](https://github.com/SalesforceAIResearch/uni2ts/blob/main/LICENSE.txt)); uni2ts 2.0.0 (2025-11-04) | **cc-by-nc-4.0** (all three checked) | No | Yes | - | **Disqualified** (non-commercial weights) |
| Lag-Llama, [time-series-foundation-models/Lag-Llama](https://huggingface.co/time-series-foundation-models/Lag-Llama) | Apache-2.0 ([LICENSE](https://github.com/time-series-foundation-models/lag-llama/blob/main/LICENSE)); **no PyPI package** (404) | apache-2.0 | No | **Univariate only** ("uses lags as covariates") | Yes (small) | Allowed but stale (HF last modified 2024-05-14) |
| IBM TTM r1/r2, [granite-timeseries-ttm-r2](https://huggingface.co/ibm-granite/granite-timeseries-ttm-r2) | Apache-2.0 ([LICENSE](https://github.com/ibm-granite/granite-tsfm/blob/main/LICENSE)); granite-tsfm 0.3.12 (2026-10-29), Python <3.14 | apache-2.0 | No | Exogenous only via **fine-tuning** | "can be executed even on CPU-only machines" | Allowed, but **monthly unsupported: "minimum context length of 512 or 1024"** (r2.1 adds daily/weekly) |
| IBM [ttm-research-r2](https://huggingface.co/ibm-research/ttm-research-r2) | Apache-2.0 | **cc-by-nc-sa-4.0** | No | - | - | **Disqualified** |
| TabPFN-TS ([repo](https://github.com/PriorLabs/tabpfn-time-series), Apache-2.0; tabpfn-time-series 1.4.0, 2026-10-28) | Apache-2.0 | Defaults (since v1.3.0) use **TabPFN-3.5**, a non-commercial licence; `LOCAL` mode needs you to "accept the license at ux.priorlabs.ai" (login, `TABPFN_TOKEN`); the **default engine is the cloud `tabpfn-client`** | Login | Yes (covariates) | TabPFN README: on CPU "only moderate datasets... (TabPFN-3/3.5 up to 5000 samples; older versions up to 1000)" | **Disqualified as shipped** |
| TabPFN-v2 weights ([TabPFN-v2-reg](https://huggingface.co/Prior-Labs/TabPFN-v2-reg), [-clf](https://huggingface.co/Prior-Labs/TabPFN-v2-clf)) | tabpfn Apache-2.0 | "Prior Labs License" = Apache-2.0 **plus Paragraph 10**: if you make available a product or service containing the weights you must "prominently display 'Built with PriorLabs-TabPFN'" ([LICENSE.txt](https://huggingface.co/Prior-Labs/TabPFN-v2-reg/blob/main/LICENSE.txt)) | No | - | Up to about 1000 samples on CPU | **Conditional** (attribution clause; needs pinning old TabPFN-TS that used v2) |
| TabPFN-2.5 ([tabpfn_2_5](https://huggingface.co/Prior-Labs/tabpfn_2_5)), 3, 3.5 | - | "TABPFN-2.5 Non-Commercial License" ("non-commercial and non-production use"); 3 and 3.5 also non-commercial | Login required by tabpfn | - | - | **Disqualified** |
| Nixtla TimeGPT | nixtla SDK Apache-2.0 ([LICENSE](https://github.com/Nixtla/nixtla/blob/main/LICENSE)); nixtla 0.9.0 (2026-09-21) | Closed; served by API | `NixtlaClient(api_key=...)`, "Obtain an API key via nixtla.io/free-trial" ([README](https://github.com/Nixtla/nixtla)) | Yes | Cloud only | **Disqualified** (API key, cloud inference) |
| Also checked: [thuml/sundial-base-128m](https://huggingface.co/thuml/sundial-base-128m), [Maple728/TimeMoE-50M](https://huggingface.co/Maple728/TimeMoE-50M) | - | apache-2.0 | No | - | - | Allowed (not evaluated further) |

**Training-data licences**
- Chronos-2's card lists `autogluon/chronos_datasets` and `Salesforce/GiftEvalPretrain`. GiftEvalPretrain and LOTSA are Apache-2.0. `chronos_datasets` has an overall "other" licence with per-subset licences (CC BY 4.0, MIT, ...) — [chronos_datasets](https://huggingface.co/datasets/autogluon/chronos_datasets), [GiftEvalPretrain](https://huggingface.co/datasets/Salesforce/GiftEvalPretrain), [lotsa_data](https://huggingface.co/datasets/Salesforce/lotsa_data) (verified via HF API).
- TTM r2's card lists Monash/Zenodo datasets plus LOTSA subsets. A separate non-commercial "research" variant exists — [TTM r2 card](https://huggingface.co/ibm-granite/granite-timeseries-ttm-r2).

**Capability and evidence**
- Chronos pretrains T5 models (20M-710M) on tokenized series plus Gaussian-process synthetic data. On 42 datasets it is "comparable and occasionally superior" zero-shot — [arXiv 2403.07815](https://arxiv.org/abs/2403.07815).
- Chronos-2 is state of the art on fev-bench, GIFT-Eval and Chronos Benchmark II, with the largest gains on covariate tasks, and was trained on synthetic multivariate structures — [arXiv 2510.15821](https://arxiv.org/abs/2510.15821). The card says it produces "multi-step-ahead quantile forecasts" — [card](https://huggingface.co/amazon/chronos-2).
- TimesFM 2.5 output is "(mean, then 10th to 90th quantiles)" — [card](https://huggingface.co/google/timesfm-2.5-200m-pytorch). Original paper: [arXiv 2310.10688](https://arxiv.org/abs/2310.10688).
- Moirai was trained on LOTSA, 27B observations — [arXiv 2402.02592](https://arxiv.org/abs/2402.02592).
- TTM starts at 1M params — [arXiv 2401.03955](https://arxiv.org/abs/2401.03955). TabPFN-TS treats forecasting as tabular regression with an 11M-param TabPFN-v2 — [arXiv 2501.02945](https://arxiv.org/abs/2501.02945).
- **Sparse and intermittent data are a known weak spot.** EXAONE Demand (preprint, Sept 2026) says demand data has "short histories, frequent zeros..." that TSFM corpora "rarely contain" — [arXiv 2609.30880](https://arxiv.org/abs/2609.30880). NetBurst (preprint) says TSFMs "are designed for dense, periodic benchmark datasets", whereas rare-event series need special handling; it reports large error reductions over Chronos-2 on bursty data — [arXiv 2510.22397](https://arxiv.org/abs/2510.22397). A 38-method intermittent spare-parts benchmark (preprint) found accuracy rank negatively correlated with service rank (-0.555), and that Chronos-2's instance normalization biases it toward **over-prediction during zero-demand periods** — [arXiv 2609.13840](https://arxiv.org/abs/2609.13840). All three are preprints, not peer-reviewed.

### Inferences
- **Flood and landslide: not suitable.** The targets are binary with prevalence about 0.00045 and about 0.0002. A quantile forecaster (TimesFM 2.5 outputs the 10th-90th quantiles) returns 0 at every quantile, so no flood probability can be read out. The mean head would only echo the in-context base rate. The driver is exogenous rain, not the series' own history, and Chronos-2 in-context covariate learning over a context holding 5 positive days does no better than logistic regression on the same 5 events.
- **Fire: technically possible as an offline zero-shot benchmark.** Chronos-2 and TimesFM 2.5 accept short context (46 monthly points) and are Apache-2.0. Running 22 series is trivial on CPU (assumed). TimesFM's mean output could be read as a Poisson rate so Brier can be computed as 1-exp(-mean). Expected gain is low: the series are at least about 78% zeros (219 fires cannot fill more than 21.6% of about 1,012 cells), the preprints document TSFM bias on zero-heavy series, and zero-shot TSFMs cannot use barangay covariates as directly as the GLM. TTM is ruled out (monthly not supported; min context 512). Lag-Llama is univariate and stale.
- **Pinning hazard.** Newer default checkpoints have become non-commercial (TimesFM 3.0 in Aug 2026; TabPFN 2.5+ and TabPFN-TS since v1.1/1.3). Any use must pin an Apache-2.0 checkpoint (e.g. `google/timesfm-2.5-200m-pytorch`, `amazon/chronos-2`) and a library version, and re-check licences on upgrade. The TimesFM 3.0 licence defines the model to include "inference code", which leaves it unclear whether the `timesfm3` code paths in the Apache-2.0 repo are restricted. Treat it as excluded.
- The CC BY attribution licences on some training subsets are not judged to restrict use of Apache-2.0 weights. That is a legal judgement, not verified.

### Gaps
- The Chronos-2 quantile grid range (whether it reaches 0.01/0.99) was not verified. No CPU latency benchmarks for Chronos-2 or TimesFM 2.5 on a modest server were found.
- Not every sub-dataset licence in `chronos_datasets` was enumerated. No peer-reviewed TSFM study on hazard event counts was found.

---

## 6. Fire monthly counts per barangay: can intermittent-demand methods, ETS/ARIMA, hierarchical forecasting or self-exciting point processes beat a Poisson GLM with 219 fires?

### Takeaway
Probably not, and there is little headroom. Croston-family methods (statsforecast, Apache-2.0) give per-series point rates with no covariates. ETS/ARIMA assume Gaussian-like errors. Hierarchical reconciliation adds little when a pooled GLM's barangay means already sum coherently. Hawkes models have strong RCT evidence for **crime**, but no urban-fire Hawkes application was found. Estimation with few events per sequence is known to be biased and overfit. The cheapest real test is to add lagged fire counts (own and neighbouring barangay) to the existing GLM.

### Cited Findings
- statsforecast intermittent models (`CrostonClassic`, `CrostonOptimized`, `CrostonSBA` = Croston x 0.95, `TSB`, `ADIDA`, `IMAPA`) return a constant mean forecast per series — [models.py](https://github.com/Nixtla/statsforecast/blob/main/python/statsforecast/models.py) (verified: `"mean": _repeat_val(...)`). Licence Apache-2.0 — [LICENSE](https://github.com/Nixtla/statsforecast/blob/main/LICENSE).
- Hierarchical reconciliation library: hierarchicalforecast 1.5.3, Apache-2.0 — [LICENSE](https://github.com/Nixtla/hierarchicalforecast/blob/main/LICENSE).
- **Self-exciting models for crime.** Mohler et al. 2011 (JASA 106) adapted seismology's self-exciting point processes to LAPD **residential burglary** data. It used "a fully nonparametric estimation methodology" for the triggering function and background rate — [JASA 2011](https://doi.org/10.1198/jasa.2011.ap09546) (abstract verified via OpenAlex). Mohler et al. 2015 (JASA 110) ran RCTs in LA (3 divisions) and Kent (2 divisions). ETAS forecasts "predicted 1.4-2.2 times as much crime" as analysts' hotspot maps, and ETAS-directed patrols gave "an average 7.4% reduction in crime volume as a function of patrol time"; analyst-based patrols showed no significant effect — [JASA 2015](https://doi.org/10.1080/01621459.2015.1077710), [RePEc](https://econpapers.repec.org/RePEc:taf:jnlasa:v:110:y:2015:i:512:p:1399-1411).
- **Contrary evidence:** an RCT in Montevideo found "the implementation of an international predictive policing software did not outperform local crime analysts" — [SSRN 2022](https://doi.org/10.2139/ssrn.4080483).
- Reinhart & Greenhouse 2018 (JRSS-C) extend self-exciting models with spatial covariates on Pittsburgh crime — [arXiv 1708.03579](https://arxiv.org/abs/1708.03579). Knox-type tests detect clustering but "spatiotemporal clustering could have various explanations"; a Hawkes model is used to separate background heterogeneity from contagion — [arXiv 1611.06713](https://arxiv.org/abs/1611.06713).
- **Fires.** Residential-fire clustering in Çankaya (Ankara) was analysed with Diggle's D-function and the space-time K-function, with no self-exciting model — [Fire Safety Journal 2013](https://doi.org/10.1016/j.firesaf.2013.01.024). An arson study found an "enhanced likelihood of near repeat follow-up incidents" — [UCF STARS record](https://stars.library.ucf.edu/scopus2015/3495). Wildfire space-time scan clustering (Portugal) is driven by weather and climate — [Sci Total Environ 2016](https://doi.org/10.1016/j.scitotenv.2016.03.129).
- **Small-data Hawkes estimation.** "When only short sequences are available, the lack of data amplifies the risk of overfitting and regularization becomes critical" — Salehi et al., NeurIPS 2019, "Learning Hawkes Processes from a Handful of Events" — [arXiv 1911.00292](https://arxiv.org/abs/1911.00292). Libraries: tick (BSD-3, Hawkes with exponential / sum-of-exponential / basis kernels) — [README](https://github.com/X-DataInitiative/tick); EasyTPP (Apache-2.0, neural TPPs) — [repo](https://github.com/ant-research/EasyTemporalPointProcess).
- Intermittent benchmarks with foundation models show accuracy and decision quality diverging (-0.555 rank correlation) — [arXiv 2609.13840](https://arxiv.org/abs/2609.13840) (preprint).

### Inferences
- **Headroom is small.** 219 fires over about 1,012 barangay-months is a mean of about 0.216 per cell, so P(at least one fire) is roughly 0.19 if the rate were uniform. A climatology Brier would then be about 0.15-0.17, and GeoAlert's GLM sits at 0.139. Poisson noise sets a floor no model can pass, so a new method can only shave thousandths. The GLM-MLP tie (0.1391 vs 0.1394) is what that looks like.
- **Croston/SBA/TSB/ADIDA/IMAPA** were designed for inventory (point demand per period) and use no covariates. With about 10 fires per barangay they reduce to a smoothed per-barangay rate, which a GLM with barangay effects and an offset already captures, along with covariates and calibrated probabilities. They are useful only as naive baselines, not as replacements.
- **ETS/ARIMA** on at least about 78%-zero integer series with 46 points: Gaussian errors, possible negative forecasts, and too few points for seasonal fits. Not appropriate.
- **Hierarchical forecasting:** the sum of the GLM's barangay expectations is already a coherent city total. Reconciliation (MinT etc.) helps mainly when separately fitted base models disagree, so little benefit is expected.
- **Hawkes / self-exciting:** the crime evidence is strong where repeat victimisation has a behavioural mechanism (burglary). For urban fire the mechanism is weaker (arson is the exception, and its near-repeat signal is documented). With about 10 events per barangay, per-barangay triggering parameters are not identifiable. A city-pooled kernel over 219 events could be fitted with tick, but monthly aggregation erases the days-to-weeks timescale where near-repeat effects live. A **diagnostic first step**: add "fires in the same barangay last month" and "fires in neighbouring barangays last month" to the Poisson GLM (an INGARCH/self-exciting-lite term). If the coefficients are near zero under rolling-origin CV, a Hawkes model is very unlikely to help. If they are positive, test a daily-resolution pooled Hawkes model with tick.
- Neural TPPs (EasyTPP) need many sequences of events. They are not suitable at 219 events.

### Gaps
- No peer-reviewed Hawkes or self-exciting application to **urban structural fires** was found, and no study directly comparing Croston-type methods with Poisson GLMs on fire incident counts. The Kourentzes 2013 study "Intermittent demand forecasts with neural networks" (IJPE) was located but its abstract could not be retrieved, so its findings are not reported. The fraction of GeoAlert barangay-months with at least one fire is unknown here, so the climatology Brier above is approximate.

---

## 7. Overall verdict per model family

### Takeaway
None of the DL or temporal families is suitable for GeoAlert now. The data (5 flood event-days, 8 landslide days, 219 fires) is two to four orders of magnitude below what the successful studies used, and the binary/sparse targets do not fit how these models output predictions. Keep the logistic regression and Poisson GLM. Revisit DL only if continuous gauge data arrives or labelled events reach the hundreds to thousands.

### Cited Findings
Evidence base (see sections 1-6):
- LSTMs need "at least hundreds of basins" — [Kratzert 2024](https://hess.copernicus.org/articles/28/4187/2024/).
- Landslide DL used 2,472 events and beat SVM only "slightly" — [Mondini 2023](https://www.nature.com/articles/s41467-023-38135-y).
- Neural nets were unstable even at >200 EPV — [van der Ploeg 2014](https://doi.org/10.1186/1471-2288-14-137).
- Pure ML lost in M4 — [Makridakis 2018](https://econpapers.repec.org/RePEc:eee:intfor:v:34:y:2018:i:4:p:802-808).
- Trees beat DL at about 10K tabular samples — [Grinsztajn 2022](https://arxiv.org/abs/2207.08815).
- Linear beat Transformers on LTSF benchmarks — [Zeng 2023](https://arxiv.org/abs/2205.13504).
- TSFMs are weak on zero-heavy series — [arXiv 2609.30880](https://arxiv.org/abs/2609.30880), [arXiv 2510.22397](https://arxiv.org/abs/2510.22397).
- Licence status is from the HF API and LICENSE files (section 5).

### Inferences
The thresholds in "suitable only if" are reasoned extrapolations from the cited studies, not published cut-offs.

| Family | Verdict now | Becomes worth testing if... | Licence status (primary option) |
|---|---|---|---|
| LSTM / GRU (incl. NeuralHydrology EA-LSTM) | **Not suitable.** 5 flood event-days and 1 rain cell; can't learn rain-to-flood sequences; overfits | Continuous **stage/discharge gauges** exist for years (regression target), or about **hundreds of independent flood event-days** with per-barangay rain (radar/gauges). Even then, regional pre-training (Caravan/CAMELS-style) beats single-site | PyTorch BSD / NeuralHydrology BSD-3: OK |
| TCN | **Not suitable** (same reasons as LSTM; no advantage at this size) | Same as LSTM | PyTorch / Darts / tsai Apache-2.0: OK |
| Transformers / TFT | **Not suitable.** Shown on 41 to about 130k entities of dense data; Zeng 2023 doubts gains even there | Thousands of dense multivariate series | PyTorch Forecasting MIT; Darts / neuralforecast Apache-2.0: OK |
| N-BEATS / N-HiTS | **Not suitable** (univariate point forecasting of dense series; results on M3/M4-scale data) | Fire panel grows to many hundreds of series (e.g. pooled multi-city BFP data) | neuralforecast / Darts Apache-2.0: OK |
| ConvLSTM | **Not suitable.** No spatial rain field (one 0.5 degree cell); Mondini notes ConvLSTM still needs research for landslides | Gridded radar or satellite rain at sub-km resolution **plus** hundreds of mapped events | Keras / PyTorch: OK |
| Graph neural networks | **Not suitable.** Need gauge graphs with continuous water levels, or a hydraulic simulator to emulate | A 2D hydraulic model of Talisay exists (GNN as surrogate, as in Bentivoglio 2023), or a gauge network | PyTorch: OK (PyG licence not checked) |
| TSFMs, flood/landslide | **Not suitable.** Quantile outputs can't express 0.05% event probabilities; driver is exogenous | Not foreseeable for binary rare events | Chronos-2 / TimesFM 2.5 Apache-2.0 OK; TimesFM 3.0, Moirai, TabPFN 2.5+ disqualified |
| TSFMs, fire | **Not for production.** Optional **offline zero-shot benchmark** only (Chronos-2 or TimesFM 2.5, pinned checkpoints), compared on the same rolling-origin Brier; low expected gain | Gains shown on GeoAlert's own backtest beyond about 0.001 Brier, plus pinned Apache-2.0 checkpoint | Chronos/Chronos-Bolt/Chronos-2, TimesFM 1.0-2.5, Lag-Llama, TTM r1/r2: Apache-2.0, ungated |
| Intermittent methods (Croston/SBA/TSB/ADIDA/IMAPA) | **Baseline only.** No covariates; per-series point rates; unlikely to beat GLM | - | statsforecast Apache-2.0: OK |
| ETS / ARIMA | **Not suitable** for 46-point, at least about 78%-zero count series | Long monthly city-level totals (aggregate) | statsforecast / statsmodels: OK |
| Hierarchical reconciliation | **Little benefit** (GLM is already coherent) | Separate models per level are introduced | hierarchicalforecast Apache-2.0: OK |
| Hawkes / self-exciting | **Not now.** First test lagged-count terms in the GLM | Lag terms prove predictive **and** fires are kept with daily dates and coordinates over several more years (pooled kernel) | tick BSD-3 OK; hawkeslib MIT (stale); EasyTPP Apache-2.0 (neural, needs far more events) |
| TabPFN-TS | **Disqualified as shipped** (default cloud client; TabPFN-3.5 non-commercial with login/token) | Only by pinning an old version with TabPFN-v2 weights, accepting the "Built with PriorLabs-TabPFN" attribution clause; CPU limit about 1000 samples | Conditional / disqualified |

**Disqualified (account, token, API or non-commercial):**
- **Nixtla TimeGPT:** API key, cloud inference.
- **TabPFN client:** cloud, account.
- **TabPFN 2.5 / 2.6 / 3 / 3.5 weights:** non-commercial, and need a login at ux.priorlabs.ai plus `TABPFN_TOKEN`.
- **TabPFN-TS default configuration:** cloud client by default; TabPFN-3.5 weights.
- **Google TimesFM 3.0:** TimesFM Non-Commercial License v1.0.
- **Salesforce Moirai 1.0/1.1/MoE/2.0:** CC BY-NC 4.0.
- **IBM ttm-research-r2:** CC BY-NC-SA 4.0.

The extra tooling also costs something. torch and transformer checkpoints of 100-500 MB add install size, upgrade risk and licence re-checks to a modest CPU Django server, with no shown gain. Better uses of effort: more and better-dated event records, per-barangay or radar rainfall, and GLM refinements (lag terms, neighbourhood effects).

### Gaps
- The "becomes worth testing if" thresholds are reasoned from the cited studies, not published cut-offs. No source gives a minimum event count for DL hazard occurrence models.
- PyTorch Geometric's licence was not checked (believed MIT; unverified).
- A short GeoAlert-specific backtest of Chronos-2 / TimesFM 2.5 on the fire panel would settle the fire question empirically. It was not run (research only; codebase untouched).
