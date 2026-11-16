# Tabular ML classifiers and count models for rare-event hazard prediction (GeoAlert: flood, landslide, fire)

Research date: 2026-11-13. Evidence labels used below: **[V]** = verified this session from a primary source (PyPI JSON API, GitHub API, LICENSE text, official docs page fetched and searched); **[S]** = taken from search-engine summaries of abstracts/records (full text not opened); **[K]** = from prior knowledge, not re-opened this session (DOI/URL given so the writer can check). Results from different datasets are **not comparable** to each other or to GeoAlert's numbers. GeoAlert facts (18 flood positives on 5 storm days, 8 landslide positives, 219 fires, current model scores) come from the brief and were not re-checked. No GeoAlert code or data was touched; the CPU timings below use synthetic data only.

## 1. Which candidate models hold up with fewer than 20 positives and prevalence below 0.1%? (incl. TabPFN licensing)

### Takeaway
No method has direct evidence of good behaviour with 5-18 events at prevalence 0.02-0.05%. The best-supported choice is a very small penalized or Firth logistic regression (about 2-6 parameters). Use FLIC intercept correction with Firth so the predicted probabilities are not biased upward. Flexible learners (RF, Extra Trees, gradient boosting, SVM, neural nets) are documented as "data hungry". TabPFN's current default weights (2.5 through 3.5-Fast) are **non-commercial and need a Prior Labs account login, so they are DISQUALIFIED**. The older TabPFN-2 weights are commercially usable with an attribution clause. But on CPU they are capped at 1,000 rows by default, and there is no evidence for them at this level of imbalance.

### Cited Findings
**Logistic regression (L1/L2/elastic net)**
- Penalization/shrinkage "are not a 'carte blanche'; they do not guarantee a reliable prediction model is developed. They are more unreliable when needed most (i.e., when overfitting may be large)". The reason given is that the tuning parameters are estimated with uncertainty from the same small data [S] — [Riley et al. 2021, J Clin Epidemiol 132:88-96](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC8026952/)
- A follow-up Riley et al. (SMMR 2021) recommends using penalization in data that **meet or surpass** minimum sample size, and always examining the variability of performance and tuning parameters [S] — [Riley et al. record](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC8026952/); related: [Pavlou et al. 2024, Biometrical J (modified CV/bootstrap tuning)](https://discovery.ucl.ac.uk/10194305/1/Pavlou_Biometrical%20J%20-%202024%20-%20Pavlou%20-%20Penalized%20Regression%20Methods%20With%20Modified%20Cross%E2%80%90Validation%20and%20Bootstrap%20Tuning%20Produce%20%281%29.pdf)
- Secondary citation: Van Calster et al. and Riley et al. found that shrinkage improved accuracy *on average*, but between-sample variability of performance was high, especially in small samples [S] — [Keele repository paper citing both](https://keele-repository.worktribe.com/OutputFile/465799)

**Firth's bias-reduced (penalized-likelihood) logistic regression**
- Firth penalization gives finite estimates under (quasi-)complete separation, where ordinary maximum likelihood (MLE) gives infinite coefficients. Kosmidis & Firth (2021) proved finiteness whenever the model matrix has full rank [V] — [firthmodels README](https://github.com/jzluo/firthmodels)
- **Key rare-event caveat:** Firth penalization biases the *average predicted probability toward 1/2*, which inflates predictions when events are very rare. FLIC (Firth plus an intercept re-fit so mean predicted = observed event rate) and FLAC (Firth plus an added covariate) remove this bias. Both are in R `logistf` [S] — [Puhr, Heinze, Nold, Lusa, Geroldinger 2017, Stat Med 36:2302-2317 (arXiv 2101.07620)](https://arxiv.org/pdf/2101.07620); [logistf flic() docs](https://search.r-project.org/CRAN/refmans/logistf/html/flic.html)
- Python implementations:
  - `firthlogist` 0.5.0 (MIT, released 2022-08-07) declares `requires_python >=3.8,<3.11`, and its GitHub repo is **archived** (last push 2025-12-05) [V] — [PyPI firthlogist](https://pypi.org/project/firthlogist/), [GitHub jzluo/firthlogist](https://github.com/jzluo/firthlogist)
  - Its successor `firthmodels` 0.8.2 (released 2026-09-05; MIT per PyPI license_expression and GitHub; "Development Status :: 4 - Beta"; deps numpy, scipy, scikit-learn>=1.6; Python >=3.10) provides a scikit-learn-compatible `FirthLogisticRegression`, `FirthCoxPH`, `detect_separation`, profile-likelihood CIs (`conf_int(method='pl')`), a statsmodels-style `FirthLogit` adapter, and `penalty_weight` (0.5 = standard Firth/Jeffreys prior) [V] — [PyPI firthmodels](https://pypi.org/project/firthmodels/), [GitHub README](https://github.com/jzluo/firthmodels)
  - A search of the firthmodels README found **no FLIC/FLAC option** [V, absence in README only] — [firthmodels README](https://github.com/jzluo/firthmodels)
- **statsmodels has no built-in Firth logit.** Feature requests are still open: #3561 "ENH: Firth's penalized logit, GLM" (opened 2017-03-18), #8677 (Firth + ridge, 2023-02-16) and #8685 (Firth Poisson, 2023-02-19) [V] — [statsmodels issue #3561](https://github.com/statsmodels/statsmodels/issues/3561)

**King & Zeng rare-events logistic regression**
- Standard logit "can sharply underestimate the probability of rare events". Proposed remedies are prior correction, weighting, and a small-sample bias correction of the coefficients. The authors' software, ReLogit, was released for Stata and Gauss (no official Python) [S] — [King & Zeng 2001, Political Analysis 9(2):137-163](https://gking.harvard.edu/publication/logistic-regression-in-rare-events-data/); [PDF](https://dash.harvard.edu/bitstream/handle/1/4125045/relogit%20rare%20events.pdf)
- Secondary commentary (blog) reports a statistician preferring Firth's method over King-Zeng's intercept prior correction [S, secondary/opinion] — [pj.freefaculty.org](https://pj.freefaculty.org/blog/?p=192)

**Generalized additive models (GAMs)**
- pyGAM 0.12.0 (Apache-2.0, released 2025-12-18; offers LogisticGAM, PoissonGAM, tensor-product `te()` interactions) [V] — [PyPI pygam](https://pypi.org/project/pygam/), [pyGAM tour](https://pygam.readthedocs.io/en/latest/notebooks/tour_of_pygam.html)
- statsmodels 0.15.0 has `GLMGam`/`LogitGam` with penalized B-splines/cyclic splines and GAM cross-validation [V] — [statsmodels GAM docs](https://www.statsmodels.org/stable/gam.html)
- I found **no study of GAM performance with fewer than 20 events** (see Gaps).

**Explainable Boosting Machines (InterpretML)**
- EBM classifier defaults: `validation_size=0.15`, `outer_bags=14`, `learning_rate=0.015`, `max_rounds=50000`, `early_stopping_rounds=100`, `min_samples_leaf=4`, `max_leaves=2`, `smoothing_rounds=75`, and a `monotone_constraints` parameter (the docs recommend applying monotonicity post-fit with `monotonize`) [V] — [EBM API docs](https://interpret.ml/docs/python/api/ExplainableBoostingClassifier.html)
- No rare-event EBM study was found (see Gaps).

**Random Forest / Extra Trees / SVM / neural nets**
- SVM, neural nets and RF "may need over 10 times as many events per variable" as logistic regression to reach stable AUC and small optimism. RF, SVM and NN stayed unstable with high optimism even above 200 events per variable. Adequate accuracy needed 300 to 16,000 records depending on method and data. The authors conclude these methods should be used only "if very large data sets are available" [S] — [van der Ploeg, Austin, Steyerberg 2014, BMC Med Res Methodol 14:137](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC4289553/)

**Gradient boosting (HistGradientBoosting, XGBoost, LightGBM, CatBoost, NGBoost)**
- Across 176 datasets and 19 algorithms, a simple baseline often wins, or light GBDT tuning matters more than choosing between NN and GBDT. No algorithm dominates [S] — [McElfresh et al. 2023, NeurIPS D&B, arXiv 2305.02997](https://arxiv.org/abs/2305.02997v4)
- XGBoost's own tuning guide: if you care about AUC only, rebalance with `scale_pos_weight`. If you "care about predicting the right probability … you cannot re-balance the dataset"; set `max_delta_step` to a finite number (say 1) instead [V] — [XGBoost parameter tuning notes](https://xgboost.readthedocs.io/en/stable/tutorials/param_tuning.html)
- scikit-learn `HistGradientBoosting*` default signature includes `min_samples_leaf=20`, `early_stopping='auto'`, `validation_fraction=0.1`, `monotonic_cst=None`, `interaction_cst=None` [V] — [HistGradientBoostingRegressor docs](https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.HistGradientBoostingRegressor.html). The docs say `early_stopping='auto'` turns on automatically when n_samples > 10,000 [K, not grep-confirmed this session] — same page.
- NGBoost 0.6.0 (Apache-2.0, released 2026-11-07) does probabilistic boosting with a choice of distribution and proper scoring rule on top of scikit-learn [V] — [PyPI ngboost](https://pypi.org/project/ngboost/), [NGBoost README](https://github.com/stanfordmlgroup/ngboost). No rare-event evidence found.

**TabPFN (tabular foundation model)**
- *Evidence:* The Nature paper reports that TabPFN beats all previous methods on datasets **up to 10,000 samples** (and 500 features) "by a wide margin". In 2.8 s it beat an ensemble of the strongest baselines tuned for 4 h (classification) [S] — [Hollmann et al. 2025, Nature 637:319-326](https://pubmed.ncbi.nlm.nih.gov/39780007/); [PMC copy](https://pmc.ncbi.nlm.nih.gov/articles/PMC11711098/)
- McElfresh et al. found TabPFN (then v1) beat all other algorithms on average, but it was effectively limited to about 3,000 training samples [S] — [arXiv 2305.02997](https://arxiv.org/abs/2305.02997v4)
- *Imbalance evidence (mostly preprints):*
  - TabPFN is well calibrated on balanced data but becomes "increasingly majority-biased" as imbalance grows; simple thresholding (or downsampling) corrects this [S] — [McDowell et al., arXiv 2605.21742, ICML 2026](https://arxiv.org/abs/2605.21742)
  - TabPFN v2's F1/balanced accuracy fall well behind tree models and RealMLP on imbalanced data [S] — [Realistic Evaluation of TabPFN v2, arXiv 2505.16226](https://arxiv.org/pdf/2505.16226)
  - A perioperative clinical study found calibration "declined noticeably" at outcome incidence below 20% [S] — [UTS repository PDF](https://opus.lib.uts.edu.au/bitstream/10453/195405/2/Precision%20vs%20recall%20in%20surgical%20AI%20Performance%20and%20limitations%20of%20tabular%20foundation%20model%20for%20perioperative%20classification%20.pdf)
  - None of these studies tests prevalence near 0.05% or fewer than 20 positives.
- *Code license:* the `tabpfn` package is Apache-2.0 (PyPI license_expression; repo LICENSE text fetched). Latest release 9.2.0, 2026-10-12. Dependencies include torch>=2.5, huggingface-hub, lightgbm, skrub, matplotlib, pydantic [V] — [PyPI tabpfn](https://pypi.org/project/tabpfn/), [LICENSE](https://github.com/PriorLabs/TabPFN/blob/main/LICENSE)
- *Weights license, current models:* the README says "The TabPFN-2.5, TabPFN-2.6, TabPFN-3, TabPFN-3.5 and TabPFN-3.5-Fast model weights are released under non-commercial licenses … TabPFN-3.5 is used by default" [V] — [TabPFN README](https://github.com/PriorLabs/TabPFN). The TabPFN-3.5 License v1.0 (revised 2026-09-09) [V] — [HF tabpfn_3_5 LICENSE](https://huggingface.co/Prior-Labs/tabpfn_3_5/blob/main/LICENSE):
  - grants use "solely for your Non-Commercial Purposes"
  - excludes use "in direct or indirect interactions with end users or production systems"
  - limits Outputs to Non-Commercial Purposes and forbids any hosted/API/SaaS service "whether paid or free" without a commercial license
  - is "not available to consumers" under German BGB §13
  - routes commercial use to sales@priorlabs.ai, "may be subject to a fee"
- *Access, current models:* on first use the package opens a browser to log in at Prior Labs and accept the license. Headless use requires accepting the license at ux.priorlabs.ai and setting `TABPFN_TOKEN` [V] — [TabPFN README FAQ](https://github.com/PriorLabs/TabPFN). (The Hugging Face repos themselves report `gated: false` via the HF API [V] — [HF API Prior-Labs/tabpfn_3_5](https://huggingface.co/api/models/Prior-Labs/tabpfn_3_5). The license terms still apply on download.)
- *Weights license, TabPFN-2:* "Prior Labs License" Version 1.1 (May 2025). It is Apache 2.0 plus one added Paragraph 10, "Additional attribution", modelled on the Llama 3 license [V] — [HF TabPFN-v2-clf LICENSE.txt](https://huggingface.co/Prior-Labs/TabPFN-v2-clf/blob/main/LICENSE.txt):
  - if you distribute or make available the work, or a product or service containing it, you must include the license and "prominently display 'Built with PriorLabs-TabPFN'" on each related website, UI, blog post, about page or product documentation
  - models trained or improved from its outputs that are distributed must carry "TabPFN" at the start of their name
  - internal benchmarking without external communication is exempt
  - The README selects these weights via `ModelVersion.V2`; HF API reports `gated: false` for TabPFN-v2-clf/-reg [V] — [README](https://github.com/PriorLabs/TabPFN), [HF API](https://huggingface.co/api/models/Prior-Labs/TabPFN-v2-clf)
- *CPU feasibility:* "On CPU, only moderate datasets are feasible (TabPFN-3, TabPFN-3.5 and TabPFN-3.5-Fast allow up to 5000 samples; older versions up to 1000)". This limit can be overridden with `TABPFN_ALLOW_CPU_LARGE_DATASET=true` ("large datasets can still be slow on CPU"). Elsewhere the README says "TabPFN is slow to execute on a CPU" [V] — [TabPFN README](https://github.com/PriorLabs/TabPFN)
- *Hosted option:* `tabpfn-client` 0.7.1 (Apache-2.0 code, 2026-11-02) is the README's "free hosted inference" for users without a GPU. It sends data to Prior Labs' API, so **DISQUALIFIED** (external inference API plus an account) [V for the package metadata and README wording; account requirement inferred from the login/token flow] — [PyPI tabpfn-client](https://pypi.org/project/tabpfn-client/), [README](https://github.com/PriorLabs/TabPFN)
- *Telemetry flag:* `tabpfn-extensions` 0.6.3 depends on `tabpfn-common-utils[telemetry-interactive]` [V; what it collects not checked] — [PyPI tabpfn-extensions](https://pypi.org/project/tabpfn-extensions/)

**Measured CPU fit times.** Synthetic data: 40,172 rows × 12 features, 18 positives. Run in GeoAlert's backend venv (Python 3.11.9, scikit-learn 1.9.1, xgboost 3.2.0) on a 16-logical-CPU dev machine. The server will be slower. [V, own measurement; scratch script only]

| Model | Fit time | Predict time |
|---|---|---|
| LogisticRegression L2 (lbfgs) | 0.07 s | |
| LogisticRegression L1 (liblinear) | 0.43 s | |
| LogisticRegression elastic net (saga) | 2.10 s | |
| LogisticRegression, class_weight=balanced | 0.06 s | |
| RandomForest, 500 trees | 9.86 s | 0.51 s |
| ExtraTrees, 500 trees | 3.36 s | |
| HistGradientBoosting, 200 iterations | 2.79 s | |
| XGBoost hist, 300 trees, depth 3 | 1.01 s | |
| SVC rbf, probability=True | 6.72 s | |

### Inferences
- **Ranking for GeoAlert flood/landslide, given license and evidence:**
  1. Firth logistic regression with FLIC intercept correction (firthmodels, MIT). FLIC must be coded by hand: refit only the intercept by ordinary logistic regression with the Firth linear predictor as an offset, e.g. statsmodels GLM `offset=`.
  2. Ridge/L1 logistic regression with tuning that is *not* chosen by inner CV on 18 events. Use a fixed, pre-specified penalty or Bayesian-style weak priors.
  3. A monotone-constrained shallow GBM or EBM, used only as a challenger.
  4. RF/Extra Trees/SVM/NN/stacking: not recommended. Their documented data hunger is far beyond 5-18 events.
- **Firth without FLIC would make GeoAlert's flood probabilities systematically too high**, per Puhr 2017. The bias toward 0.5 matters most at prevalence 0.00045.
- **EBM defaults are risky here.** EBM holds out 15% for early stopping (≈2-3 flood positives) and bags 14 times. Each bag's stopping rule is driven by 2-3 events, so its shape functions will be noisy. Validation size and smoothing would have to be pinned by hand.
- **HistGradientBoosting has a similar trap.** With 40k rows, `early_stopping='auto'` would turn on and hold out 10% (≈2 positives). Set `early_stopping=False` and fix the iteration count.
- **TabPFN status:**
  - The default and all post-v2 checkpoints are **DISQUALIFIED**: non-commercial and non-production, account plus license click-through, token for headless use, and "production systems" is expressly excluded. Government DRRMO deployment is a production use.
  - TabPFN-2 weights pass the "commercial use" test, but add an attribution obligation on the product UI and docs. That obligation is explicit, not hidden, but it is more than plain Apache-2.0.
  - Practically, TabPFN-2 is capped at 1,000 CPU samples by default and was evaluated up to 10,000. Using it on 40,172 rows would mean subsampling negatives, which changes prevalence and needs King-Zeng prior correction. This brings no evidence of benefit with 18 positives and adds a ~127 MB (Windows) to ~539 MB (Linux default CUDA) torch wheel.
  - The package defaults to v3.5, so any use would have to pin `ModelVersion.V2` or `TABPFN_MODEL_VERSION=v2` explicitly to avoid silently loading non-commercial weights.
- **King-Zeng in Python:** there is no maintained implementation found. Its useful pieces can be done by hand: prior correction of the intercept after case-control subsampling, and bias correction. Firth (firthmodels) covers the bias-reduction role and is maintained.

### Gaps
- No peer-reviewed benchmark was found that compares these model families at fewer than 20 events and prevalence below 0.1%. Every comparison found has many more events.
- No published evidence was found for GAM, EBM, NGBoost or stacking specifically at fewer than 20 events.
- Whether `tabpfn` 9.x ever triggers the Prior Labs login for `ModelVersion.V2` was not tested. The README's login FAQ lists only 2.5+ models.
- TabPFN's behaviour at prevalence around 0.05% is untested in any source found.
- Full texts of Riley 2021, van der Ploeg 2014 and Puhr 2017 were not opened. Details come from abstracts and summaries.

## 2. What do sample-size / events-per-variable studies say about 5-18 events, and how do ML and logistic regression compare on small data?

### Takeaway
The "10 events per variable" rule is a weak heuristic. Modern criteria (Riley et al.) depend on prevalence, expected R², number of parameters and total n. At GeoAlert's prevalences they support only about **3-6 predictor parameters for flood (18 events)** and **about 1-3 for landslide (8 events)**, before even accounting for the fact that the flood events cluster on 5 storm days. Systematic reviews and simulations show no advantage of ML over logistic regression in fair comparisons, and much greater data needs for ML.

### Cited Findings
- **Older events-per-variable (EPV) rules:**
  - Peduzzi et al. (1996) Monte Carlo study: low EPV causes major problems; "no major problem occurred" above 10 EPV, which is the origin of the 10-EPV rule [S] — [Peduzzi et al., J Clin Epidemiol 49(12):1373-1379 (record)](https://papers.mewayz.com/paper/oa_W2037668591); [Wikipedia: One in ten rule](https://www.wikipedia.org/wiki/One_in_ten_rule)
  - Vittinghoff & McCulloch (2007): EPV 10 is "too conservative"; severe problems occur mainly at EPV 2-4 [S] — [Am J Epidemiol 165(6):710-718](https://www.bohrium.com/paper-details/relaxing-the-rule-of-ten-events-per-variable-in-logistic-and-cox-regression/812031627159928832-9082)
  - van Smeden et al. (2016): "The current evidence supporting EPV rules for binary logistic regression is weak" [S] — [BMC Med Res Methodol, "No rationale for 1 variable per 10 events"](https://link.springer.com/article/10.1186/s12874-016-0267-3)
- **Modern criteria:**
  - van Smeden et al. (2019): EPV "does not have a strong relation with metrics of predictive performance, and is not an appropriate criterion". Out-of-sample performance is better approximated by the number of predictors, the total sample size and the events fraction [S] — [Stat Methods Med Res 28(8):2455-2474](https://dspace.library.uu.nl/bitstream/1874/387109/1/vansmeden.pdf)
  - Riley et al. (BMJ 2020;368:m441) set minimum sample size from the number of candidate predictor parameters, the outcome proportion and the anticipated Cox-Snell R². The usual target is shrinkage ≥0.9 (≤10% overfitting). It is implemented in R `pmsampsize` (default shrinkage 0.9) [S] — [pmsampsize CRAN manual](https://cran.r-project.org/web/packages/pmsampsize/refman/pmsampsize.html); [secondary description](https://web3.arxiv.org/pdf/2207.12892); [Springer review](https://link.springer.com/10.1186/s12874-023-02008-1)
- **ML vs logistic regression:**
  - Christodoulou et al. (2019) reviewed 71 studies. In 145 low-risk-of-bias comparisons the difference in logit(AUC) between LR and ML was **0.00 (95% CI -0.18 to 0.18)**; in high-risk-of-bias comparisons ML was ahead by 0.34. Validation procedures were potentially biased in 68% of studies, and calibration was not addressed in 79% [S] — [J Clin Epidemiol 110:12-22](https://med.mahidol.ac.th/ceb/sites/default/files/public/pdf/Repository/1-s2.0-S0895435618310813-main.pdf)
  - van der Ploeg et al. (2014): RF/SVM/NN need >10× the EPV of LR [S] — [BMC Med Res Methodol 14:137](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC4289553/)
  - Grinsztajn et al. (2022): on 45 tabular datasets, tree-based models remain state of the art over deep learning on "medium-sized data (~10K samples)" [S] — [NeurIPS 2022, arXiv 2207.08815](https://arxiv.org/abs/2207.08815). This compares trees with neural nets, not with LR, and does not cover rare events.
  - McElfresh et al. (2023): light GBDT tuning or a simple baseline is often as good as or better than the NN-vs-GBDT choice; TabPFN does best on small datasets [S] — [arXiv 2305.02997](https://arxiv.org/abs/2305.02997v4)
- **Structured data and cross-validation:** for data with temporal, spatial or hierarchical structure, random cross-validation "regularly" underestimates predictive error. Block cross-validation is recommended wherever such dependence exists [S] — [Roberts et al. 2017, Ecography 40:913-929](https://www.biometrie.uni-freiburg.de/mitarbeiter/dormann/roberts-et-al-2017-ecography.pdf)

### Inferences
- **Own calculation, Riley 2020 criteria 1-3** (shrinkage 0.9; δ=0.05 for the Nagelkerke-optimism criterion; formula n = P / ((S−1)·ln(1−R²cs/S))), assuming independent rows:
  - **Flood** (prevalence 0.00045; max R²cs 0.0078):
    - With Riley's conservative default (R²cs = 15% of max = 0.00117), about 3.5 events are needed per parameter, so 18 events support about **5 parameters**.
    - With R²cs implied by C≈0.80, about 6.4 events per parameter, i.e. **about 3 parameters**.
    - With C≈0.90, about **6 parameters**.
  - **Landslide** (prevalence 0.0002): **about 1.3-2.9 parameters** for 8 events.
  - Criterion 3 (precise overall risk) is trivially met.
  - These figures are orientation only. They assume independence, while the flood events are 18 barangay-days on only 5 storm days. The effective number of independent events is closer to 5, so the true budget is smaller.
- **The current flood model is over budget.** It has 5 rain features plus 6 terrain features (11+ parameters) on 18 events in 5 storms. This is consistent with its pooled AUC of 0.96 collapsing to a leave-one-barangay-out (LOBO) AUC of 0.36: likely overfitting to which barangays flooded during Tino.
- **Landslide:** 6+ parameters on 8 events, 7 of them in Manipis. The model largely encodes "Manipis vs not". Its LOBO AUC of 0.90 rests on a single non-Manipis event (Camp IV), so it is very imprecise.
- **AUC precision, own calculation (Hanley-McNeil formula [K]):** a pooled AUC of 0.96 with 18 positives has a standard error of about 0.03 under independence. Storm clustering makes the real uncertainty larger. Because the PR-AUC baseline equals prevalence (Saito & Rehmsmeier 2015 [K] — [PLoS One 10:e0118432](https://doi.org/10.1371/journal.pone.0118432)), a flood PR-AUC of 0.05 is about 100× no-skill. But with 18 positives it is very noisy.
- **External-validation guidance** (Collins, Ogundimu & Altman 2016 [K] — [Stat Med 35:214-226](https://doi.org/10.1002/sim.6787)) asks for at least 100 events, preferably 200. None of GeoAlert's hazard validations can reach this, so all reported metrics should carry wide intervals.
- **Practical feature budget:** flood should use about 2-4 parameters. Example: one rain summary such as 3-day sum, possibly a 1-day sum, plus one composite terrain exposure score built *a priori* (e.g., share of buildings with HAND<5 m) rather than 6 separate terrain terms. Landslide should use 1-2 parameters (e.g., 3-day rain × steep-slope share).

### Gaps
- No study derives sample-size criteria for *clustered* rare events (many positives on one storm day). The effective-sample-size adjustment above is a judgement, not a sourced rule.
- The Riley BMJ 2020 full text and the R²-from-C conversion (Riley et al. 2022) were not opened. My C-to-R²cs mapping used a normal linear-predictor simulation, so treat it as approximate.

## 3. Class-imbalance handling: class weights, cost-sensitive learning, SMOTE, focal loss, undersampling

### Takeaway
For a risk-probability product, do **not** resample or reweight the training data. Imbalance correction (random under-/oversampling, SMOTE) produced strongly over-estimated minority-class probabilities without better discrimination. Threshold shifting gives the same sensitivity/specificity trade-off. If subsampling is unavoidable (e.g., for TabPFN-size limits), undo it with King-Zeng prior correction.

### Cited Findings
- **van den Goorbergh, van Smeden, Timmerman & Van Calster (JAMIA 2022;29(9):1525-1534):**
  - Tested standard and ridge logistic regression with no correction, random undersampling, random oversampling and SMOTE, using simulation and an ovarian cancer case study.
  - Imbalance correction "yielded poorly calibrated models: the probability to belong to the minority class was strongly overestimated", with no better discrimination.
  - "similar results were obtained by shifting the probability threshold instead"; imbalance "is not a problem in itself" [S] — [PMC9382395](https://pmc.ncbi.nlm.nih.gov/articles/PMC9382395); [arXiv 2202.09101](https://pdf.arxiv.org/pdf/2202.09101)
- **XGBoost docs:** to predict the right probability "you cannot re-balance the dataset" (avoid `scale_pos_weight`); use `max_delta_step` instead [V] — [XGBoost tuning notes](https://xgboost.readthedocs.io/en/stable/tutorials/param_tuning.html)
- **imbalanced-learn SMOTE** signature: `SMOTE(*, sampling_strategy='auto', random_state=None, k_neighbors=5)` [V] — [imblearn SMOTE docs](https://imbalanced-learn.org/stable/references/generated/imblearn.over_sampling.SMOTE.html). imbalanced-learn 0.14.2 (2026-06-07), MIT (PyPI classifier and GitHub) [V] — [PyPI](https://pypi.org/project/imbalanced-learn/)
- **TabPFN's majority-class bias** under imbalance is corrected by simple thresholding, with downsampling comparable [S] — [arXiv 2605.21742](https://arxiv.org/abs/2605.21742)
- **King & Zeng (2001)** propose prior correction and weighting to recover population probabilities after outcome-dependent (case-control) sampling [S] — [King & Zeng 2001](https://gking.harvard.edu/publication/logistic-regression-in-rare-events-data/). The prior-correction formula subtracts ln[((1−τ)/τ)·(ȳ/(1−ȳ))] from the intercept, with τ the population event fraction and ȳ the sample fraction [K] — same paper (PDF linked in section 1).

### Inferences
- **SMOTE is mechanically fragile here.** The default k_neighbors=5 needs at least 6 minority samples in every training fold. With 18 flood positives on 5 days in rolling-origin folds (no floods in 2023-2024), several folds have 0-8 positives. Interpolated "synthetic floods" between barangays/days would also be physically meaningless (blending two different storms' rain profiles).
- **`class_weight='balanced'` in scikit-learn LR** (or `scale_pos_weight` in XGBoost/LightGBM) shifts the intercept upward by roughly ln(weight). It does not change the ranking of a linear model. So it adds miscalibration without AUC gain, consistent with van den Goorbergh. If used, apply prior correction afterwards.
- **Focal loss** is not available as a built-in option in scikit-learn LR; it would need a custom GBM objective. Its outputs are not proper probability estimates without recalibration [K, general property of non-log-loss objectives]. With 18 positives there is nothing to recalibrate on, so it is not recommended. I found no tabular rare-event evidence for it.
- **The DRRMO's decision trade-off belongs in the threshold**, not in training. Example: alert when P(flood) > x, with x chosen from the cost of a missed flood vs a false alarm.

### Gaps
- The van den Goorbergh full text was not opened (simulation prevalences not checked; I believe they go down to a few percent, not 0.05%).
- No study of focal loss for tabular rare-event *risk* prediction was found.

## 4. Probability calibration and conformal prediction with fewer than 20 positives

### Takeaway
Post-hoc calibrators (Platt, isotonic, beta, Venn-Abers) and conformal methods all need a held-out calibration set containing positives. With 5-18 positives such a set either cannot be formed or gives meaningless maps. Isotonic is documented to need about 1,000 or more samples. Class-conditional conformal needs at least 1/α−1 positives in the calibration set. Prefer models that are calibrated by construction (MLE logistic, or Firth plus FLIC). Report calibration-in-the-large and slope with wide intervals. Use bootstrap or Venn-Abers-style intervals to *communicate* uncertainty rather than to "fix" calibration.

### Cited Findings
- **scikit-learn calibration guide:** isotonic "is more prone to overfitting, especially on small datasets" and performs as well as or better than sigmoid only "when there is enough data (greater than ~ 1000 samples)". Calibration can change ROC-AUC with isotonic because it introduces ties [V] — [scikit-learn calibration guide](https://scikit-learn.org/stable/modules/calibration.html)
- **Niculescu-Mizil & Caruana (ICML 2005):** isotonic regression "is more prone to overfitting, and thus performs worse than Platt Scaling, when data is scarce" [S] — [ICML 2005](https://mlanthology.org/icml/2005/niculescumizil2005icml-predicting)
- **Split-conformal threshold** is the ⌈(n+1)(1−α)⌉/n empirical quantile of calibration scores. Coverage holds for any n, and n≈1,000 calibration points is "sufficient for most purposes". The paper also has a class-conditional (Mondrian) section [S] — [Angelopoulos & Bates, arXiv 2107.07511](https://arxiv.org/pdf/2107.07511)
- **Firth and FLIC:** Firth biases average predictions toward 0.5; FLIC/FLAC restore mean predicted = observed proportion [S] — [Puhr et al. 2017](https://arxiv.org/pdf/2101.07620)
- **Tools and licenses:**
  - **crepes** 0.9.1 (2026-06-12; BSD-3-Clause per GitHub, "BSD License" per PyPI; deps numpy/pandas/scipy only) implements standard and **Mondrian** conformal classifiers and regressors [V] — [crepes README](https://github.com/henrikbostrom/crepes), [PyPI](https://pypi.org/project/crepes/)
  - **MAPIE** 1.6.0 (2026-10-19; BSD-3-Clause; deps numpy, scikit-learn>=1.4, scipy) docs cover conformal prediction, risk control, a "Calibration" section, binary set prediction and group-conditional sets [V for nav/structure; method details not read] — [MAPIE docs](https://mapie.readthedocs.io/en/latest/), [PyPI](https://pypi.org/project/MAPIE/)
  - **venn-abers** 1.5.4 (2026-08-12; MIT) [V] — [PyPI venn-abers](https://pypi.org/project/venn-abers/), [GitHub ip200/venn-abers](https://github.com/ip200/venn-abers)
  - **betacal** 1.1.0 (2021-04-01; MIT; repo last pushed 2024-02-12) — **stale** [V] — [PyPI betacal](https://pypi.org/project/betacal/), [GitHub betacal/python](https://github.com/betacal/python)
- **Method papers:** beta calibration (Kull, Silva Filho & Flach 2017, AISTATS [K]) and Venn-Abers predictors (Vovk & Petej 2014 [K]). Venn-Abers outputs an interval [p0, p1] whose width shrinks as calibration data grow [K].
- **Calibration hierarchy** (Van Calster et al. 2016, J Clin Epidemiol 74:167-176 [K] — [doi:10.1016/j.jclinepi.2015.12.005](https://doi.org/10.1016/j.jclinepi.2015.12.005)) recommends that flexible calibration curves need a substantial number of events (I recall about 200). Not re-verified.

### Inferences
- **Class-conditional conformal is infeasible** (own reading of the quantile formula above). For per-class conformal at α=0.10 the positive calibration set needs ≥9 events; at α=0.05 it needs ≥19. GeoAlert has 18 flood positives *in total* and 8 landslide. Marginal (non-Mondrian) conformal would be dominated by the ~40,000 negatives and would output {no-flood} almost always: valid coverage but useless.
- **Logistic regression fitted by MLE with an intercept** reproduces the observed event rate on its training data (score-equation property [K]). That is calibration-in-the-large by construction, and the most one can ask with 18 events. Check it out-of-time in rolling-origin folds. Expect years with no floods (2023-2024) to make calibration-in-the-large look poor.
- **To communicate uncertainty to the DRRMO**, use bootstrap or profile-likelihood intervals for the predicted probability (firthmodels supports profile CIs on coefficients). This is more honest than any post-hoc calibrator. Venn-Abers intervals would be very wide with so few positives, which is honest but may confuse non-specialists.
- **Platt scaling** of a GBM/RF output with 18 positives is fitting a 2-parameter logistic model on 18 events again. It adds little beyond fitting LR directly.

### Gaps
- Angelopoulos & Bates' section 4.2 text was not read. The ≥1/α−1 per-class requirement is derived from the quoted quantile formula, not quoted from the paper.
- Whether MAPIE 1.6.0 or crepes 0.9.1 include Venn-Abers calibrators was not verified.
- The Van Calster 2016 event-count recommendation was not re-verified.

## 5. Interpretability for a government DRRMO audience: SHAP, monotonic constraints, EBM and GAM shape functions

### Takeaway
With 2-6 parameters, logistic or Poisson coefficients are the explanation: odds or rate ratios per 10 mm of rain, plus probability-vs-rain curves. SHAP adds little for linear models. If a tree or boosted challenger is used, monotone constraints are available in every major library and encode physics (more rain never lowers flood risk). EBM and GAM shape plots are the most readable non-linear options, but each shape costs degrees of freedom the data cannot afford.

### Cited Findings
- **SHAP:** 0.54.1 (2026-10-16; MIT per PyPI and GitHub) requires **Python ≥3.12** and numpy≥2 [V] — [PyPI shap](https://pypi.org/project/shap/), [GitHub shap/shap](https://github.com/shap/shap)
- **Monotone constraints:**
  - scikit-learn HistGradientBoosting: `monotonic_cst` and `interaction_cst` parameters [V] — [HGB docs](https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.HistGradientBoostingRegressor.html)
  - LightGBM: `monotone_constraints`, with a doc note that constraints apply to split choice but not to linear models fitted in leaves when `linear_tree=true` [V] — [LightGBM parameters](https://lightgbm.readthedocs.io/en/stable/Parameters.html)
  - EBM: `monotone_constraints` (list of int); docs recommend post-fit `monotonize` instead [V] — [EBM API docs](https://interpret.ml/docs/python/api/ExplainableBoostingClassifier.html)
  - XGBoost `monotone_constraints`, CatBoost `monotone_constraints`, pyGAM `constraints='monotonic_inc'` [K] — [XGBoost params](https://xgboost.readthedocs.io/en/stable/parameter.html), [pyGAM docs](https://pygam.readthedocs.io/en/latest/notebooks/tour_of_pygam.html)
- **GAM shape functions and interactions:** pyGAM supports LogisticGAM/PoissonGAM and tensor-product interactions `te()` [V] — [pyGAM tour](https://pygam.readthedocs.io/en/latest/notebooks/tour_of_pygam.html); statsmodels `GLMGam` uses penalized B-splines [V] — [statsmodels GAM](https://www.statsmodels.org/stable/gam.html)

### Inferences
- **Python version conflict:** GeoAlert's backend venv runs **Python 3.11.9**. The latest SHAP (0.54.1, needs ≥3.12) cannot be installed there; pip would resolve an older SHAP. This was verified only as a PyPI `requires_python` mismatch; the last SHAP version supporting 3.11 was not identified.
- **Suggested DRRMO outputs:**
  - (a) a curve of P(flood) vs 3-day rain for "high-exposure" vs "low-exposure" barangays
  - (b) a table of odds ratios with profile-likelihood CIs
  - (c) for fire, each barangay's shrunken monthly rate with an interval
  - All three come straight from GLM coefficients and need no extra library.
- **Monotone constraints** (rain ↑ ⇒ risk ↑; steep share ↑ ⇒ landslide risk ↑) cut variance in any tree challenger and make it defensible to non-specialists. Combined with shallow depth (2-3) and strong `min_child_weight`/`min_samples_leaf`, such a model behaves close to a monotone GAM.
- **EBM shape plots are attractive**, but with 18 events each shape function will be jagged unless heavily smoothed. Any plot shown to the DRRMO should carry the bagged uncertainty bands EBM provides.

### Gaps
- No user study was found on which explanation formats DRRMO or civil-defence staff understand best.
- The XGBoost/CatBoost/pyGAM monotone parameters were not grep-confirmed this session; they are long-standing documented features.

## 6. Fire counts: Poisson vs negative binomial vs zero-inflated/hurdle vs GBM Poisson/Tweedie vs GAM

### Takeaway
For about 219 fires over 22 barangays by month (mean around 0.25 per barangay-month), a Poisson or negative-binomial GLM with partial pooling of barangay effects is the right baseline. It formalizes the "plain per-barangay average" that GeoAlert found hard to beat, ideally with an exposure offset (buildings or population). Many zeros alone do not justify zero-inflated or hurdle models: a Poisson with mean 0.25 already predicts about 78% zeros. GBM Poisson/Tweedie objectives exist in all major libraries, but with about 800-1,000 rows they are unlikely to beat a pooled GLM. That matches GeoAlert's RF/XGBoost/LightGBM result.

### Cited Findings
- **Edmonton, Canada (IEEE Access 2024):** negative binomial regression for fire and other emergency events at neighbourhood and fire-station-service-area level. It gave acceptable prediction errors at weekly and monthly resolution, with consistent accuracy at station level; COVID-19 significantly affected occurrence and performance. The abstract gives no metric values [V, abstract] — [Sharma et al., arXiv 2402.09553](https://arxiv.org/abs/2402.09553)
- **Atlanta "Firebird" (KDD 2016):** commercial-property fire risk for >5,000 buildings, with true positive rates "up to 71%". SVM vs random forest compared. It is a building-level classifier for inspection prioritisation, not barangay-month counts [S] — [Madaio et al., arXiv 1602.09067](https://arxiv.org/abs/1602.09067)
- **Fire-injury study (Baltimore tracts, CDC-hosted):** used negative binomial because the counts are "over-dispersed count data representing rare events" [S] — [CDC stacks](https://stacks.cdc.gov/view/cdc/30173/cdc_30173_DS1.pdf)
- **Zero-inflation debate:**
  - Allison: negative binomial is an alternative way to handle overdispersion; he "would almost always" choose NB over ZIP and advises fitting NB before zero-inflated models. Greene disputes some technical points (non-nested models) [S, expert blog] — [Statistical Horizons, "Do we really need zero-inflated models?"](https://statisticalhorizons.com/zero-inflated-models/)
  - A methods paper cites "little or no evidence for the need to explicitly model excess zeros", while noting ZINB is used by others [S] — [arXiv 2007.04177](https://ar5iv.arxiv.org/html/2007.04177)
- **Count objectives available:**
  - scikit-learn `HistGradientBoostingRegressor(loss='poisson')` (losses: squared_error, absolute_error, gamma, poisson, quantile) [V] — [HGB docs](https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.HistGradientBoostingRegressor.html)
  - XGBoost `count:poisson` (max_delta_step defaults to 0.7 for Poisson) and `reg:tweedie` [V] — [XGBoost parameters](https://xgboost.readthedocs.io/en/stable/parameter.html)
  - CatBoost `Poisson` and `Tweedie` objectives [V] — [CatBoost regression objectives](https://catboost.ai/docs/en/concepts/loss-functions-regression)
  - LightGBM `poisson`/`tweedie` objectives [K] — [LightGBM parameters](https://lightgbm.readthedocs.io/en/stable/Parameters.html)
  - pyGAM `PoissonGAM` [V] — [pyGAM tour](https://pygam.readthedocs.io/en/latest/notebooks/tour_of_pygam.html)
  - statsmodels 0.15.0 `HurdleCountModel` [V] — [statsmodels HurdleCountModel](https://www.statsmodels.org/stable/generated/statsmodels.discrete.truncated_model.HurdleCountModel.html). Its NB, ZIP/ZINB and GLM `offset`/`exposure` are long-standing features [K].
  - glum 3.4.1 (2026-05-06; BSD-3-Clause; elastic-net GLMs) [V] — [PyPI glum](https://pypi.org/project/glum/), [GitHub Quantco/glum](https://github.com/Quantco/glum)
- **Empirical-Bayes (gamma-Poisson) shrinkage** of small-area rates toward a global mean is the classic disease-mapping solution for unstable small-area counts [K] — [Clayton & Kaldor 1987, Biometrics 43:671-681](https://doi.org/10.2307/2532003)

### Inferences
- **Zero-inflation check, own arithmetic.** If the fire series covers about 36-46 months: 22 × 36-46 ≈ 790-1,010 barangay-months, mean ≈ 0.22-0.28 fires each. A Poisson then predicts P(0) ≈ e^(−0.25) ≈ 0.78. Compare observed zeros with this before considering zero-inflated or hurdle models. Test overdispersion (variance/mean, or NB2 α with its CI) before choosing NB.
- **Why the per-barangay average is so strong:** with about 10 fires per barangay over the period, the barangay mean *is* the signal. A Poisson GLM with barangay effects shrunk toward the city mean (empirical Bayes, a random intercept, or a ridge-penalized one-hot in glum or scikit-learn `PoissonRegressor(alpha=…)`) should match or beat the raw per-barangay average on Brier/deviance. It would also give the DRRMO stable rates for low-count barangays.
- **Exposure offset:** dividing by structures or population (OSM building count is already computed for flood) converts counts to rates. It is standard GLM practice and makes barangay comparisons fair.
- **Seasonality** (e.g., a dry-season effect, if the BFP data show one) can enter as 1-3 harmonic terms or a month-group factor. With about 219 events, a few such terms are within budget.
- **GBM Poisson/Tweedie on about 1,000 rows** with mostly barangay-ID and calendar features would mostly relearn barangay means, with more variance. This is consistent with GeoAlert's finding that RF/XGBoost/LightGBM did no better.

### Gaps
- No peer-reviewed comparison was found of Poisson vs NB vs ZI vs GBM for *urban structure-fire counts at neighbourhood-month level* with metrics. Edmonton reports none in its abstract, and Firebird is a building-level classifier.
- No Philippine (BFP) fire-count modelling study was found.
- The exact month span of GeoAlert's fire series was not stated in the brief.

## 7. Library licenses, releases, maintenance, footprint, CPU cost and Python/Django compatibility

### Takeaway
Every recommended library (scikit-learn, statsmodels, firthmodels, XGBoost, LightGBM, CatBoost, InterpretML, pyGAM, NGBoost, imbalanced-learn, MAPIE, crepes, SHAP, venn-abers, glum) is under MIT, Apache-2.0 or BSD-3. All are pip-installable, run locally on CPU, and need no account, key or token. The licensing **disqualifications** are TabPFN-2.5/2.6/3/3.5/3.5-Fast weights (non-commercial, login and license acceptance) and `tabpfn-client` (hosted API). Several packages conflict with GeoAlert's current backend venv (Python 3.11.9, scipy 1.17.1, scikit-learn 1.9.1).

### Cited Findings
License column: PyPI license_expression/classifier and GitHub API SPDX detection, checked 2026-11-13 [V]. Only TabPFN's LICENSE text was opened in full. "Last push" is the GitHub `pushed_at` date. Wheel sizes are from PyPI file listings (cp312 win_amd64 / manylinux x86_64, or pure-Python) [V].

| Library | License (source) | Latest release (date) | Last push / status | Python req. | Wheel size | Notable deps / notes |
|---|---|---|---|---|---|---|
| [scikit-learn](https://pypi.org/project/scikit-learn/) | BSD-3-Clause ([COPYING](https://github.com/scikit-learn/scikit-learn/blob/main/COPYING)) | 1.9.1 (2026-09-10) | 2026-11-12, 68k★ | ≥3.11 | 8.3 / 9.2 MB | Already in backend venv (1.9.1) |
| [statsmodels](https://pypi.org/project/statsmodels/) | BSD-3-Clause ([repo](https://github.com/statsmodels/statsmodels)) | 0.15.0 (2026-08-27) | 2026-11-11 | ≥3.10 | 11.3 / 12.0 MB | patsy, formulaic, pandas; no Firth (issue #3561 open) |
| [firthmodels](https://pypi.org/project/firthmodels/) | MIT ([repo](https://github.com/jzluo/firthmodels)) | 0.8.2 (2026-09-05) | 2026-11-02, Beta, 14★ | ≥3.10 | 0.1 MB pure | numpy, scipy, sklearn≥1.6; small single-maintainer project |
| [firthlogist](https://pypi.org/project/firthlogist/) | MIT | 0.5.0 (2022-08-07) | **archived** (2025-12-05) | **<3.11** | — | Not installable on Py 3.11.9; superseded |
| [xgboost](https://pypi.org/project/xgboost/) | Apache-2.0 ([repo](https://github.com/dmlc/xgboost)) | 3.4.1 (2026-08-15) | 2026-11-11 | **≥3.12** | 48.9 / 57.6 MB | On Linux pulls `nvidia-nccl-cu13`; CPU-only alternative [`xgboost-cpu`](https://pypi.org/project/xgboost-cpu/) 3.4.1 (numpy, scipy only); venv has 3.2.0 |
| [lightgbm](https://pypi.org/project/lightgbm/) | MIT (GitHub; PyPI license field empty) ([repo](https://github.com/lightgbm-org/LightGBM)) | 4.7.0 (2026-07-18; previous 4.6.0 was 2025-02-15) | 2026-11-12; repo now under `lightgbm-org` | ≥3.10 | 1.4 / 3.5 MB | numpy, scipy, narwhals |
| [catboost](https://pypi.org/project/catboost/) | Apache-2.0 ([repo](https://github.com/catboost/catboost)) | 1.2.10 (2026-02-18) | 2026-11-12 | not declared | 100.2 / 97.1 MB | graphviz, matplotlib, plotly, pandas, six |
| [interpret / interpret-core](https://pypi.org/project/interpret-core/) | MIT (GitHub; PyPI field empty) ([repo](https://github.com/interpretml/interpret)) | 0.7.8 (2026-03-17) | 2026-11-09 | not declared | 15.6 MB | `interpret-core` deps: numpy, pandas, sklearn≥1.6, joblib. `interpret` meta-package adds dash, plotly, shap, etc. |
| [pygam](https://pypi.org/project/pygam/) | Apache-2.0 ([repo](https://github.com/dswah/pyGAM)) | 0.12.0 (2025-12-18) | 2026-04-21 (slower) | ≥3.10,<3.15 | 0.1 MB | **pins `scipy<1.17`** (venv has 1.17.1) |
| [ngboost](https://pypi.org/project/ngboost/) | Apache-2.0 ([repo](https://github.com/stanfordmlgroup/ngboost)) | 0.6.0 (2026-11-07) | 2026-11-10 | ≥3.10,<3.15 | 0.1 MB | **on Python <3.14 pins `scikit-learn<1.7`** (venv has 1.9.1); lifelines, sympy, matplotlib |
| [imbalanced-learn](https://pypi.org/project/imbalanced-learn/) | MIT ([repo](https://github.com/scikit-learn-contrib/imbalanced-learn)) | 0.14.2 (2026-06-07) | 2026-06-29 | ≥3.10 | 0.2 MB | — |
| [MAPIE](https://pypi.org/project/MAPIE/) | BSD-3-Clause ([repo](https://github.com/scikit-learn-contrib/MAPIE)) | 1.6.0 (2026-10-19) | 2026-11-10 | ≥3.10 | 0.6 MB | numpy, sklearn≥1.4, scipy |
| [crepes](https://pypi.org/project/crepes/) | BSD-3-Clause ([repo](https://github.com/henrikbostrom/crepes)) | 0.9.1 (2026-06-12) | 2026-07-08 | ≥3.10 | <0.1 MB | numpy, pandas, scipy |
| [venn-abers](https://pypi.org/project/venn-abers/) | MIT ([repo](https://github.com/ip200/venn-abers)) | 1.5.4 (2026-08-12) | 2026-09-02 | not declared | — | — |
| [betacal](https://pypi.org/project/betacal/) | MIT ([repo](https://github.com/betacal/python)) | 1.1.0 (2021-04-01) | 2024-02-12 (**stale**) | — | — | — |
| [shap](https://pypi.org/project/shap/) | MIT ([repo](https://github.com/shap/shap)) | 0.54.1 (2026-10-16) | 2026-11-12 | **≥3.12** | 0.8 / 0.6 MB | numpy≥2, slicer, cloudpickle |
| [glum](https://pypi.org/project/glum/) | BSD-3-Clause (GitHub; PyPI "BSD") ([repo](https://github.com/Quantco/glum)) | 3.4.1 (2026-05-06) | 2026-11-07 | ≥3.10 | 0.4 / 2.7 MB | formulaic, narwhals, pyarrow, tabmat, numexpr |
| [tabpfn](https://pypi.org/project/tabpfn/) (code) | Apache-2.0 ([LICENSE](https://github.com/PriorLabs/TabPFN/blob/main/LICENSE)) | 9.2.0 (2026-10-12) | 2026-11-12 | ≥3.10 | 0.9 MB (+ torch) | **Weights: v2 = Prior Labs License 1.1 (Apache-2.0 + attribution); v2.5-v3.5 = non-commercial → DISQUALIFIED** |
| [tabpfn-client](https://pypi.org/project/tabpfn-client/) | Apache-2.0 (code) | 0.7.1 (2026-11-02) | — | ≥3.10 | — | **DISQUALIFIED**: hosted inference API with account/token |
| [torch](https://pypi.org/project/torch/) (TabPFN dep) | Apache-2.0 AND BSD-2/3 AND MIT AND others (PyPI license_expression) | 2.15.0 (2026-10-28) | — | ≥3.11 | 126.7 MB win / 539.2 MB Linux default | CPU-only build available from the PyTorch index (size not checked) |

- Measured CPU fit times at 40,172 rows × 12 features (synthetic, 16-thread dev machine): LR 0.06-2.1 s; XGBoost 1.0 s; HistGB 2.8 s; Extra Trees 3.4 s; SVC+Platt 6.7 s; RF 9.9 s [V, own measurement — see section 1]. Fire data (~1,000 rows) is trivially fast for all methods.
- The TabPFN README states CPU limits of 1,000 samples (v2) and 5,000 (v3+) by default [V] — [README](https://github.com/PriorLabs/TabPFN)

### Inferences
- **Python/Django compatibility.** None of these libraries touches Django. They run in the same process or in a management command / Celery-style job, and the model can be pickled or saved as plain coefficients. For LR/GLM models, storing coefficients in PostgreSQL and scoring in SQL or NumPy removes any runtime ML dependency. Within the current venv (Python 3.11.9):
  - **Installable without conflict:** scikit-learn, statsmodels 0.15, firthmodels, LightGBM 4.7, CatBoost, interpret-core, imbalanced-learn, MAPIE, crepes, venn-abers, glum, TabPFN code.
  - **Conflicts:** pyGAM 0.12 (scipy<1.17), NGBoost 0.6 (scikit-learn<1.7 on Py<3.14), latest SHAP and XGBoost (need Py≥3.12), firthlogist (Py<3.11).
  - A Python ≥3.12 upgrade would clear SHAP/XGBoost. pyGAM and NGBoost would still conflict until they relax their pins.
- **Leanest stack for the recommended models:** numpy + scipy + scikit-learn + statsmodels + firthmodels (all BSD-3/MIT, about 20 MB of wheels). CatBoost (100 MB, plotting deps) and TabPFN (torch) are the heaviest and add nothing proven here.
- **Maintenance risk:**
  - firthmodels: a 14-star single-maintainer Beta project. The method is simple enough (Newton iterations on the Jeffreys-penalized likelihood) to vendor or re-implement if it is abandoned. Its MIT license allows this.
  - betacal: stale.
  - pyGAM: slower cadence.
  - All others: active within the last 1-5 months.

### Gaps
- LICENSE files were not individually opened for libraries other than TabPFN (GitHub API rate limit hit). The SPDX IDs come from GitHub's own license detection plus PyPI metadata, which agree wherever both exist. LightGBM and interpret have empty PyPI license fields.
- Datasets: none of these libraries needs a bundled dataset. NASA POWER, Copernicus DEM and OSM data licensing is outside this note's scope.
- CPU times were measured on a 16-thread dev machine, not the "modest" production server. TabPFN, EBM, CatBoost, glum and pyGAM were not timed because they are not installed in the venv.
