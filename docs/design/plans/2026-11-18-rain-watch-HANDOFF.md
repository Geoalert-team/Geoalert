# Handoff: Rain watch build (2026-11-18)

*For the next Claude session. Read this whole file first. Nothing is committed (user rule); the
uncommitted files on disk are the only copy.*

> **Update, 2026-11-18 (resumed session): the build is finished.**
> - **Task 7** was reviewed: spec ✅, approved. One fix round added a comment stating a guard's contract.
> - **Full suites (Task 11, Steps 2–4):** all green, then re-run after the fix wave:
>   - backend: 1,007 tests OK
>   - frontend: 464 tests OK, and `CI=true npm run build` compiles
>   - tool: 36 tests OK
> - **The final whole-branch review (opus)** said "with fixes". One fix wave ran in two parallel lanes
>   (backend + tool; frontend + docs + spec), and the scoped re-review found every finding addressed.
> - **The user decided two rules** (now in spec 6.5):
>   1. A PAGASA alert counts for Talisay only if it names Cebu (geocode or `areaDesc`) or its polygon
>      is about province-sized, at most 3° by 3°. Typhoon alerts are drawn over the whole Philippine
>      area.
>   2. PAGASA flood floors are never lowered by the 8-barangay limit. DRRMO overrides and the
>      forecast still are.
> - **Other changes in the wave:**
>   - Wet ground is computed in a background thread, never inside a request.
>   - A short stored run is upgraded when the same run arrives longer.
>   - The public view gets "unknown", not "none", over an out-of-date forecast.
>   - The map tooltips refresh when floors or staleness change.
>   - The API has new fields `stale_hours`, `covers_talisay` and `mapped`.
>   - `dynamical-catalog==1.1.1` is pinned.
> - **Rulings and small parked items:** in the ledger, from the "FINAL REVIEW" line on.
> - **Go-live (Task 12), steps 1–2 DONE on 2026-11-18, with the user's yes each time:**
>   1. Backup: `Downloads/Geoalert-Full-Backup-before-rainwatch-0001-2026-11-18.dump` (547,870 bytes;
>      31 tables; row counts match live; database 26 MB).
>   2. `rainwatch.0001_initial` APPLIED to the shared database. The Balanced row is present, and the
>      old tables are unchanged apart from Django's own bookkeeping.
> - **Next: go-live step 3** (Render settings; section 4, step 5.3). Ask the user before **each**
>   step. The site code itself still has to be committed and pushed by the user (see
>   `deploy/FREE_HOSTING.md` step 2).

## 0. Rules (from the user; strict)
- **Never commit, stage, stash, reset, checkout or push.** Leave every file uncommitted. Don't create
  a worktree; work in `C:/Users/Sannichigetsu/Geoalert` on branch `feature/geoalert-updates`
  (HEAD `807e2af`, unchanged).
- **No migration on the shared Supabase database without the user's explicit go-ahead,** and always
  back it up first (to Downloads, as for history migrations 0001–0008).
- Zero cost. No Open-Meteo. Ask design questions one at a time with AskUserQuestion. If the user
  answers "expound", explain in plain words with a real example from the data.
- The user is not a weather or machine-learning expert: explain simply.
- The user asked for parallel work ("if you can run it simultaneously, much better").

## 1. What this is
**The feature:** a "Rain watch: Next 3 days" view for flood and landslide. A free GitHub Actions job
fetches GFS rain every 6 h and POSTs it to the site. The site reads PAGASA's CAP alert feed hourly
and works out each barangay's Yellow/Orange/Red on request. The public sees Orange and Red; DRRMO
and admins also see Yellow. There is a DRRMO override, and a note on the monthly view.

**Documents:**
- **Spec (approved 2026-11-18):** `docs/design/specs/2026-11-18-rain-watch-design.md`
- **Plan (12 tasks):** `docs/design/plans/2026-11-18-rain-watch.md`
- **Background investigation and backtest:** `docs/research/2026-11-17-rain-watch-and-rainfall-data.md`,
  plus the spec's section 10.

**Execution:** the `superpowers:subagent-driven-development` skill, adapted:
- Lanes run in parallel.
- No commits. Each task's review diff is a before/after snapshot of its files.

**Ledger** (source of truth for progress, rulings and deferred minors):
`.superpowers/sdd/2026-11-18-rain-watch/progress.md` (git-ignored, local only).

**The same folder holds:**
- task briefs `task-N-brief.md`
- implementer reports `task-N-report.md`
- review diffs `review-task-*.diff`
- `global-constraints.md`
- `snap.sh` (`snap.sh TASK before|after paths…`) and `pkg.sh` (`pkg.sh TASK paths…`, which writes
  the review diff)
- `snap/task-N/{before,after,fixbase-r1}`

## 2. Status (as of 2026-11-18)

| Task | What | Status |
|---|---|---|
| 1 | App, models, migration 0001 (+ Balanced seed), settings, admin | ✅ reviewed, clean |
| 2 | `rules.py` colour rules | ✅ reviewed, clean |
| 3 | `series.py` joining runs, Manila day totals | ✅ reviewed, clean |
| 4 | Ingest and status endpoints (token) | ✅ reviewed, 1 fix round |
| 5 | `pagasa.py` feed reader and hourly hook in `apps/hazards/views.py` | ✅ reviewed, 1 fix round |
| 6 | DRRMO override endpoints | ✅ reviewed, clean |
| 7 | `assess.py` and `GET /api/rain-watch/` | ✅ reviewed, 1 fix round (resumed session) |
| 8 | `tools/rain_forecast` job, `.github/workflows/rain-forecast.yml`, CI step | ✅ reviewed, 1 fix round (APCP ruling) |
| 9 | Public map: Next 3 days view, picker, banner, legend, monthly note | ✅ reviewed, 1 fix round |
| 10 | DRRMO dashboard card and override form | ✅ reviewed, 1 fix round |
| 11 | Docs: `render.env.example`, `FREE_HOSTING.md`, README, `ATTRIBUTION.md` | ✅ docs reviewed (1 fix round); full suites green (resumed session) |
| — | Final whole-branch review + one fix wave | ✅ re-review clean (resumed session) |
| 12 | Go-live | ⛔ NOT started; needs the user's go-ahead at every step |

**Task 7:** the implementer finished, DONE_WITH_CONCERNS. 52 tests pass across the assess, ingest,
overrides, rules and series test files, on the private test DB. Report:
`.superpowers/sdd/2026-11-18-rain-watch/task-7-report.md`. **Its review has NOT been dispatched.**

Task 7's concerns, for the reviewer to judge:
1. **Reason text for a day the forecast doesn't reach** is `'Forecast out of date (partial)'`; a
   stale forecast gets exactly `'Forecast out of date'`. The brief and Review Focus 5 disagreed.
2. **A fix outside the brief, in `assess.bump()`:** it added `cache.touch(VERSION_KEY, None)`.
   Django's file cache `incr()` let the version key expire after 300 s, so a stale answer could be
   served for up to 5 minutes. A test covers it.
3. **New class:** `StoredRun(RunData)` adds `received_at` and `hours`, so `build` can know when the
   newest full run arrived.
4. **Review Focus 5 test:** it only works with an old full run marked as received recently.
5. **Rules changes:** editing the rules in Django admin doesn't clear the cache, so a change takes up
   to 5 minutes to show.

**What "reviewed" means:** a fresh reviewer subagent checked spec compliance and quality on the
task's before/after diff, and every Important finding was fixed and re-reviewed. Test evidence comes
from the implementers' runs, recorded in their report files. No full suite has been run since the
build started.

## 3. Decisions and rulings made during the build (details in the ledger)
- **Parallel lanes:**
  - backend B1 (Tasks 1→2→5→7)
  - backend B2 (Tasks 3, 4, 6)
  - tool (Task 8)
  - frontend (Tasks 9→10)

  Three private test DBs, one per concurrent backend run (section 6).
- **Task 8 reads NOMADS `var_APCP` with `per_hour_from_acc`, not the plan's `PRATE`.** NOMADS PRATE
  is an instantaneous rate and failed the acceptance check (8.7 mm a day off dynamical.org). APCP
  passed: 0.006 mm a day worst, for cycle 2026111612. The plan text is already corrected.
- **Task 10:** reasons are shown as visible text in the DRRMO table, not only as a hover title.
  Spec 7.2 is binding over the plan.
- **Task 9:** the client also treats data over 12 h old as stale (`withClientStale`). No forecast at
  all shows grey (`mapLevel`).
- **Task 11 was split:** the docs are done; the full suites run after Task 7.

## 4. Exact next actions, in order
1. **Read the ledger tail and Task 7's report:**
   `tail -40 .superpowers/sdd/2026-11-18-rain-watch/progress.md`, then
   `.superpowers/sdd/2026-11-18-rain-watch/task-7-report.md`.
   - If Task 7 is not DONE, re-dispatch it from `task-7-brief.md` and the report file.
2. **Review Task 7:**
   `bash .superpowers/sdd/2026-11-18-rain-watch/pkg.sh 7 backend/apps/rainwatch/assess.py backend/apps/rainwatch/views.py backend/apps/rainwatch/urls.py backend/tests/test_rainwatch_assess.py`.
   The before-snapshot already exists. Then dispatch a task reviewer (sonnet) with:
   - `task-7-brief.md`
   - `task-7-report.md`
   - the printed diff
   - the binding values from `global-constraints.md`

   Run the fix loop if needed: resume the same implementer, then a scoped re-review.
3. **Task 11 Steps 2–4: full suites,** run once, sequentially:
   - Backend (from `backend/`):
     `PYTHONPATH="C:/Users/Sannichigetsu/.geoalert-test" DJANGO_SETTINGS_MODULE=geo_test_settings venv/Scripts/python.exe manage.py test tests apps --noinput > "C:/Users/Sannichigetsu/.geoalert-test/full.log" 2>&1; tail -n 30 "C:/Users/Sannichigetsu/.geoalert-test/full.log"`
   - Frontend (from `frontend/`): `CI=true npx react-scripts test --watchAll=false`, then `npm run build`
     (warnings fail CI).
   - Tool (from `backend/`): `venv/Scripts/python.exe -m unittest discover -s ../tools/rain_forecast -p "test_*.py"`.
4. **Final whole-branch review** (opus): follow the skill's `references/final-review.md`. Point it at
   all `Task N: minor (deferred)` lines in the ledger so it can choose which to fix before go-live.
5. **Task 12, go-live: STOP and ask the user before each step** (plan Task 12).
   1. Back up the shared DB and report its size.
   2. `python manage.py showmigrations rainwatch`, then `python manage.py migrate rainwatch`.
   3. Render env: `RAIN_WATCH_INGEST_TOKEN`, `PAGASA_FEED_WRITER=true`, check
      `HAZARD_LOG_WRITER=true`.
   4. GitHub secrets: `RAIN_WATCH_INGEST_TOKEN`, `RAIN_WATCH_API_URL=https://geoalert-rvqc.onrender.com`.
      Set the $0 spending limit and check the repo's visibility.
   5. The **user** puts the workflow and `tools/rain_forecast/` on `main`.
   6. Run the workflow by hand: dry run first, then for real.

## 5. Unverified (say so; don't assume)
- No full backend or frontend suite has run since the build started.
- The real job → site POST and status calls have never run, end to end.
- No phone-width layout has been checked in a browser (map view, DRRMO table with visible reasons).
- The PAGASA feed with a real Cebu alert hasn't been seen live; tests use saved fixtures and
  synthetic alerts.

## 6. Environment gotchas
- **Private test DBs** (settings files in `C:/Users/Sannichigetsu/.geoalert-test/`): never the
  shared `test_postgres`, and never two runs on the same DB at once.
  - `geo_test_settings` → `test_geoalert_hazard_models`
  - `geo_test_settings_b` → `test_geoalert_rainwatch_b`
  - `geo_test_settings_c` → `test_geoalert_rainwatch_c`
- **Scratchpad folders may be cleared:** the backtest venv, the PAGASA samples, the NOMADS test
  files. The PAGASA fixtures are already copied into `backend/tests/fixtures/pagasa/`.
- **Task 8's `--compare` check** needs network and a venv with eccodes, dynamical-catalog, icechunk
  and zarr. Never install those into `backend/venv`: the Render image stays NumPy-only.
- **The site deploys from `feature/geoalert-updates`,** but GitHub timers run only from `main`.

## 7. Changed files (all uncommitted)
- **Modified:**
  - `.github/workflows/ci.yml`, `README.md`
  - `backend/apps/hazards/views.py`, `backend/apps/history/data/ATTRIBUTION.md`
  - `backend/config/settings/base.py`, `backend/config/urls.py`
  - `deploy/FREE_HOSTING.md`, `deploy/render.env.example`
  - `frontend/src/components/Forecast/forecastLevels.js`
  - `frontend/src/pages/Dashboard/DRRMODashboard.jsx`, `frontend/src/pages/PublicMap.jsx`
- **New:**
  - `.github/workflows/rain-forecast.yml`
  - `backend/apps/rainwatch/`, `backend/tests/fixtures/`, `backend/tests/test_rainwatch_*.py` (7 files)
  - `docs/design/plans/2026-11-18-rain-watch.md` (+ this file), `docs/design/specs/2026-11-18-rain-watch-design.md`
  - `docs/research/2026-11-17-rain-watch-and-rainfall-data.md`
  - `frontend/src/api/rainWatchApi.js`, `frontend/src/components/RainWatch/`
  - `tools/rain_forecast/`

## 8. Skills review
- ✅ superpowers:brainstorming / writing-plans: the design was approved with 8 "my calls"; the plan
  self-reviewed.
- ⚠️ superpowers:subagent-driven-development: adapted for no-commits (snapshot diffs) and parallel
  lanes (separate test DBs). It worked, but the full-suite gate is still outstanding.
- ⚠️ Testing: several implementers wrote code before seeing the test fail (noted in their reports);
  the reviews checked that the tests assert real behaviour.
