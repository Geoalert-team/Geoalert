# Handoff: fire risk by purok — paused after the clean-up (Part A)

*Written 2026-11-22. The user said: "if the cleanup finishes, the deleting of the models and rain
watch is done, pause for now and detail everything for the next Claude to understand." Part A is
done and verified. Part B (the new fire model) has not started. Nothing is committed.*

---

## 0. Read this first

**Rules that still apply**
- **Never `git commit` or push.** The user commits themselves. Every plan step that says "commit"
  means "leave uncommitted".
- **Ask design questions with the AskUserQuestion tool,** with previews where it helps. If the user
  answers "expound", explain again in plain words with one real example from their data.
- **The shared Supabase database:** no write without a backup to Downloads and the user's plain
  go-ahead. That covers migrations, `import_bfp_fires --relink` and the prediction log. Reading is
  fine. Nothing in Part A touched the database.
- **No counting as the prediction mechanism.** No past fire count, rate, per-area term or
  per-barangay term may be a model input or a rule. Fire records are only the label
  (`fire_occurred`, yes or no), the validation and the baselines named `comparison_*`. The user is
  worried a thesis panel will read a "count" in the code as counting. Inputs are named for what they
  measure.
- **Free, commercially usable data with no account.** Open-Meteo is banned (the user ruled it out
  on 2026-11-13).
- **Tests use the private test settings** `C:\Users\Sannichigetsu\.geoalert-test\geo_test_settings_fire.py`
  (test DB `test_geoalert_fire_purok`). The shared test DB collides with other runs. From `backend/`:
  `PYTHONPATH="C:/Users/Sannichigetsu/.geoalert-test" venv/Scripts/python.exe manage.py test tests apps --settings=geo_test_settings_fire --noinput`
  (about 12 minutes). From `frontend/`: `CI=true npx react-scripts test --watchAll=false`; then
  `CI=true npm run build`, where warnings fail the build.
- **Browser checks** against the dev server must stub `GET /api/hazards/`: it releases overdue
  Extreme alerts on the shared database.
- **Tool gotcha:** a bash heredoc containing backticks gets cut or mangled in this environment (it
  happened three times). Write Python or JS with the Write tool to a scratch file, then run it.

## 1. Goal for the next session

Resume the plan at **Task B1** and run B1 to B8 inline. The user chose "Native" execution, which
means the `superpowers:executing-plans` skill: TDD per step and one whole-change review at the end.
**B9 (the real training run) waits for the user** (section 4).

- Plan: [2026-11-22-fire-purok-model.md](2026-11-22-fire-purok-model.md). Its Global Constraints and
  Review Focus are binding.
- Spec: [2026-11-22-fire-purok-model-design.md](../specs/2026-11-22-fire-purok-model-design.md).
  **Section 0 and Part A (section 12) override the rest.**
- Research and audit (why, with the real numbers):
  [docs/research/2026-11-22-fire-purok-prediction-audit.md](../../research/2026-11-22-fire-purok-prediction-audit.md).
- **Ledger:** `.superpowers/sdd/2026-11-22-fire-purok-model/progress.md` (git-ignored). It lists
  A1, A2 and A3 as complete and holds every `Ruling:` line made so far. Trust it over memory.
- Start with `executing-plans/scripts/task-start <plan> B1`. BASE is `b829074` for every task, since
  no commits are made.

## 2. What the user wants (decisions, in order, 2026-11-22)

1. **The brief** (a long pasted request):
   - rebuild fire prediction at **purok level**, fire only for now;
   - **no counting-based prediction**;
   - test neural networks on merit;
   - Red / Orange / Green levels from validated cut-offs, kept apart from the probability;
   - free data only.
2. **History stays as it is:** "There is levels, dont change the history and its functions, just the
   likely by month." That keeps `purok_levels.py`, `area.py`, the "Past hazards" view and the History
   page.
3. **Approving a fire report** takes the **model's purok level** instead of the count rule.
   Flood and landslide reports keep `purok_levels`.
4. **The 23 BFP fires that name only a barangay:** place them in a purok from evidence, and wait
   before training. Checklist: `C:\Users\Sannichigetsu\Downloads\Talisay-23-Fires-Without-Purok-2026-11-22.csv`
   (still blank). News searches found none of them. The evidence is in BFP Talisay's incident reports
   or the Talisay City Fire Station Facebook posts (a logged-in search).
5. **The model:**
   - "use an existing model… not building our own", then "train it with our data but then try to
     use github, or any sources that uses an existing model";
   - the user chose to **adapt the City of Pittsburgh Bureau of Fire's model**
     (`github.com/CityofPittsburgh/fire_risk_analysis`, MIT, © 2017 mmadaio; Python 2, so its recipe
     is ported, not run);
   - no ready-made model covers Talisay (audit §10a).
6. **Delete flood and landslide prediction** ("we will also rebuild them"), and **also delete the
   Rain watch**.
7. **Build now; train only once the 23 are placed.**
8. **Native execution.**

The designer's calls are listed in spec §10. Among them:
- Orange + Red must catch 80% of fires;
- Red starts at 2× the city-average rate;
- the fallback level on approval is Orange.

## 3. Part A, done and verified

Tests: backend `tests apps` **596 OK**. The baseline before any change was 993 under `tests` only;
the difference is the deleted tests. Frontend **61 suites / 387 tests OK**, against 65 / 464 before,
the difference being the removed rain watch and flood tests. The build compiles.

**Deleted** (all still in git at `b829074`, so `git checkout` restores any of it):
- **Backend, `apps/history`:**
  - `hazard_forecast`, `hazard_models`, `hazard_tests`, `hazard_verdict`, `hazard_scoring`,
    `hazard_scenarios`, `two_part`, `firth`, `storms`, `landslide_catalogue`, `rain`, `exposure`,
    `hazard_data`, `model_forecast` (the old barangay fire model) and `fire_candidate`;
  - the commands `test_hazard_models`, `fetch_rain`, `fetch_storms` and `build_hazard_features`;
  - their data files (report, rain, storms, terrain, exposure, exclusions) and their tests.
- **Rain watch:**
  - backend `apps/rainwatch` and its tests and PAGASA fixtures;
  - `tools/rain_forecast`, `.github/workflows/rain-forecast.yml` and the CI step for it;
  - frontend `components/RainWatch`, `api/rainWatchApi.js`, the "Next 3 days" view, the banner and
    the DRRMO dashboard card.

**Changed:**
- `views.py`:
  - the forecast is fire-only (`FIRE_ONLY = "Only fire has a prediction model for now."` is a 400 for
    any other hazard);
  - every fire row is unavailable with `NOT_TRAINED = "The fire model has not been trained yet."`;
  - the accuracy entry is `views.fire_accuracy_entry()`:
    `{'hazard':'Fire','kind':'fire_purok','status':'unavailable','reason':…}`.
- New `forecast_rows.py`: the row helpers, which B5 reuses.
- `prediction_log.py`: now a stub (`write_month_rows` returns 0).
- `log_hazard_predictions`: logs nothing for now.
- `hazards/views.py`: the warm-up hook is gone.
- Settings and URLs: `rainwatch`, `RAIN_WATCH_INGEST_TOKEN` and `PAGASA_FEED_WRITER` are gone.
- Frontend:
  - `forecastLevels.js` is fire-only (`hazardsParam`, `isFireOnly`, `FIRE_ONLY_NOTE`, the new
    `FORECAST_DISCLAIMER`, `unavailableNote(likely)`);
  - `BarangayLikelihood` and `ForecastAccuracy` are fire-only;
  - `PublicMap`'s likely view fills barangays from fire's barangay row. B7 replaces this with purok
    fills.
- Docs: README, CODEBASE_GUIDE, ATTRIBUTION.md, FREE_HOSTING.md and render.env.example.

**Kept:**
- flood and landslide history (`flood_landslide.py`, `import_flood_landslide`,
  `place_history_records`, close forms);
- `forecast.py` (history columns and the comparison baseline);
- the `HazardPredictionLog` model and migration 0008;
- `HAZARD_LOG_WRITER`;
- the static hazard-index and terrain map layers (`susceptibility.js`, `terrain.js`, `SpotReading`,
  `build_hazard_index`). That last one is my reading of "delete the models"; **the user has not
  confirmed it**.

**Database:** untouched. The `rainwatch` tables and `hazard_prediction_log` rows are still there,
unused and orphaned. Dropping them would need a backup and the user's go-ahead. Nobody asked for it.

## 4. Still open

- **The user, outside the repo, after they commit and push:**
  - delete Render env `RAIN_WATCH_INGEST_TOKEN` and `PAGASA_FEED_WRITER` (keep `HAZARD_LOG_WRITER=true`);
  - delete the GitHub secrets `RAIN_WATCH_INGEST_TOKEN` and `RAIN_WATCH_API_URL`;
  - disable the "Rain forecast" workflow if it is still listed.

  This is written in `deploy/FREE_HOSTING.md`.
- **The 23-fire checklist** must come back before B9.
- **B9, each step needing the user's go-ahead:**
  - back up the fire links, then `import_bfp_fires --relink`;
  - `build_fire_features` (downloads WorldCover and the footprint polygons, plus WorldPop if it needs
    no account);
  - `train_fire_model`;
  - back up the DB, then `migrate history 0009`, then `log_hazard_predictions`;
  - hand checks in the browser.
- **The whole-change review** (executing-plans "Final Review") is due after B8. It covers Parts A
  and B together.
- **Ask the user if it comes up:** whether the hazard-index and terrain layers should go too.

## 5. Facts the next session must not lose (details in the audit)

- **The map leak.** 151 of the 670 purok areas exist because a fire address named them. 86% of those
  have a fire, against 4% of the rest. A yes/no "named from a fire address" flag predicts the 2026
  fires better than any model (AUC 0.82). So purok scores from past fires are optimistic. The report
  must say so (verbatim caveat in plan B4) and show the 151 / 519 split. Area `kind`, container
  status and area size are **not** inputs.
- **The feasibility probe** (features only, no counts):
  - 2026 test AUC 0.67 (0.57–0.75); top 20% of areas held 41% of fires;
  - leave-one-barangay-out 0.60;
  - the MLP tied the regression; neighbour (graph) features added nothing;
  - catching 80% of fires flagged about 61% of areas.

  Scripts: `.superpowers/sdd/2026-11-22-fire-purok-model/probe/`.
- **Data:**
  - 220 real fires (2023-01-26 to 2026-11-20), 197 with a purok;
  - 670 areas, all with estimated outlines; 77 sitio containers hold 34 fire links;
  - cached inputs in `backend/.hazard_cache`: Microsoft building centres (78,931), OSM roads,
    stations and waterways, and the DEM.

## 6. Return

When B1–B8 are done, report the test counts, the rulings and any deferred minor issues. Then ask the
user to send back the 23-fire checklist and give the go-aheads for B9. Update the memory file
`fire-purok-rebuild-2026-11-22.md`.
