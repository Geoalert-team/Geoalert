# Handoff: automatic retraining of the fire and flood models (2026-11-24)

**Paused at the user's request on 2026-11-24, after Task 6 was built and before its review finished.**

- Repo: `c:\Users\Sannichigetsu\Geoalert`. Branch: `merge-scout`. HEAD: `d24bce8` (the user's commit). Everything below is **uncommitted** in the working tree.
- Spec (approved): `docs/design/specs/2026-11-24-automatic-retraining-design.md`
- Plan: `docs/design/plans/2026-11-24-automatic-retraining.md` (7 tasks)
- Execution: subagent-driven (the user chose it). Tasks run in parallel where their files don't overlap (the user asked for speed).
- **Ledger:** `.superpowers/sdd/2026-11-24-automatic-retraining/progress.md` (git-ignored). It holds every ruling, every deferred minor, and the snapshot ids. **Read it first.**
- The workspace folder also holds:
  - task briefs `task-N-brief.md`;
  - reports `task-N-report.md`;
  - review packages `task-N-review.md`;
  - test logs `tN-*`;
  - `constraints.md`, the plan's Global Constraints and Review Focus, extracted;
  - `snap.sh` (see "How diffs work here").

## What is being built (one paragraph)

1. A free GitHub Actions job runs `manage.py run_model_job --hazard fire|flood`. Fire runs on the 2nd of each month at 03:17 Manila; flood runs on 5 January at 03:17. Both were moved from :00 in the final review, because GitHub can drop runs scheduled on the hour. It runs on a throw-away PostGIS database.
2. It fetches training data from GeoAlert's token-only endpoint and retrains:
   - **fire:** moving 12-month test window;
   - **flood:** tries a model trained on GeoAlert's own located flood spots once there are ≥100 spots in ≥5 barangays, testing on the newest wet season.
3. It posts the attempt back. The server stores every attempt in a new `ModelFit` table (history migration 0012) and makes it live only on a pass.
4. The site reads the newer of the live fit and the committed model file. A "Model updates" card on the Predictive models tab lists every attempt.

## Status

| Task | What | State | Verified by |
|---|---|---|---|
| 1 | `ModelFit` table, `model_fits.py`, migration 0012, superuser-only admin undo | **DONE**, review clean after 1 fix round | `tests.test_model_fits` 14 OK; `makemigrations --check` "No changes detected" |
| 2 | Loaders read the live fit (`parse` split, `FireModel.model`, flood source `geoalert`, `BASIS_GEOALERT`, purok-row `note`, readiness `source`/`own_spots`, `site_check`, `make_live(check=)`) | **DONE**, review clean | 96 tests in 9 suites OK (6 Supabase timeouts; that suite passed alone) |
| 3 | Fire: `fire_run.train` (pipeline moved out of the command), moving window, switch rule | **DONE**, review clean (opus checked the moved code line by line) | 89 tests OK |
| 4 | Flood own-data mode (`flood_own.py`, `run(mode='own', …)`), wording rulings RA/RB/RC, spot-hash in version, golden fixture | **DONE**, review clean after 1 fix round | 51 tests OK; golden made from the unmodified code; mutation checks fail as they should |
| 5 | Token permission, `GET model-job/data/`, `POST model-job/attempts/`, public `GET forecast/updates/`, `located_spots()` (with lon/lat, token response only), readiness `own_spots` | **DONE**, review clean after 1 fix round | 18 tests (fix round); 52 OK earlier |
| 6 | `model_job.py`, `run_model_job` command, `.github/workflows/model-retrain.yml`, README section | **BUILT, review NOT done.** The review was stopped mid-run at the user's pause. | `tests.test_model_job` 31 OK; dry run against `http://127.0.0.1:9` failed as designed; full backend suite 873 (14 Supabase network errors; those modules pass alone, 67 OK) |
| 7 | Frontend: `ModelUpdates.jsx` card, readiness spots line, own-data training line, neutral disclaimer, spot note, geoalert accuracy report | **DONE**, review clean | full frontend 445 tests pass; `npm run build` "Compiled successfully" |
| — | Final whole-branch review + its single fix wave | **NOT STARTED** | — |
| — | Go-live (migrations, secrets, first runs) | **NOT STARTED**; each step needs the user's yes | — |

Snapshot trees (from `snap.sh`; no commits): T0 `9d399a9…`, T1 `e00f260…`, T2 `46ec11a…`, T3/T4 `d69263e…`, T4 fix `5e153e0…`, T5 `4457590…`, T5 fix `3709f17…`, **T6 `e2570e8e8125e0871d08f22ca20ced738ec2485e`**, T7 `808b52b…`. The full ids are in the ledger.

## Decisions (the most load-bearing; all rulings with costs are in the ledger)

**User decisions:**
- Our own flood records replace only the survey's flood spots; the land clues stay.
- Fire retrains monthly, flood yearly.
- Approach A: the token handoff.
- The server switches models by itself.
- Nothing paid; GitHub is fine.
- Run tasks in parallel when possible.

**Controller rulings:**
- **Fire (R1, R2, Task 3):**
  - the live fire settings come from `FireModel.model`;
  - the fold formula is `(fold_end-1-month)//12`, so the oldest fold can be 1 month;
  - the same-settings test uses `report['test']['chosen']`.
- **Flood (R3, RA, RB, RC, Task 4):**
  - a golden fixture guards survey mode, compared with rounded floats so CI on Linux can't flake;
  - `acceptance(..., own=True)` gives own-mode sentences, so no "Mananga" or "surveyed" appears;
  - `OUTSIDE_OWN` wording;
  - the NOAH note is added only when the live source is noah or geoalert;
  - the own version hashes the training spots.
- **Endpoints (Task 5):**
  - spots carry lon/lat only in the token response;
  - the fire `live` picks family/settings behind a dict guard.
- **The job (Task 6):**
  - it never uses EOS-RS (the Tino map), because spec §4 says it never goes to GitHub;
  - failed reasons mask decimal numbers with `#`;
  - reasons are truncated to 500 characters;
  - the flood fingerprint is the sha1 of the features CSV and meta.
- **Task 2:** `make_live` runs `site_check`, so an undo can't make the site's model unreadable.
- **Tests:** they run on private test DBs `geo_test_settings_retrain_t2/t4/t5/t6` (DBs `test_geoalert_retrain_tN`), because `test_geoalert_flood_susc` was held by another session.
- **Local servers:** the old local preview servers (8001/3001) were stopped. The loaders now query `model_fit`, which the shared DB lacks until 0012 is applied.

## Changes (all uncommitted)

- **New files:**
  - backend: `backend/apps/history/{admin.py, fire_run.py, flood_own.py, job_auth.py, model_fits.py, model_job.py, migrations/0012_model_fit.py, management/commands/run_model_job.py}`;
  - backend tests: `backend/tests/{test_fire_run.py, test_flood_own.py, test_model_fit_loading.py, test_model_fits.py, test_model_job.py, test_model_job_api.py, fixtures/flood_survey_golden.json}`;
  - the workflow: `.github/workflows/model-retrain.yml`;
  - frontend: `frontend/src/components/Forecast/{ModelUpdates.jsx, modelUpdates.test.js}`;
  - the spec, the plan and this handoff.
- **Modified files:**
  - backend: `backend/apps/history/{fire_purok, fire_training, flood_purok, flood_rules, flood_run, models, urls, views}.py`, `management/commands/train_fire_model.py`, `backend/config/settings/base.py` (adds `MODEL_JOB_TOKEN`);
  - `README.md`;
  - frontend: `frontend/src/{api/historyApi.js, components/Forecast/{FloodReadiness.jsx, ForecastAccuracy.jsx, forecastLevels.js}, pages/{PredictiveModels.jsx, PublicMap.jsx}, utils/spotText.js}` and their tests.

## Verification

- Per-task test runs are listed in the Status table, with logs in the workspace (`tN-*`).
- **UNVERIFIED:**
  - No full backend suite has run after Task 5's fix round and Task 6's EOS-RS fix, both of which landed after T6's suite run.
  - No full frontend suite has run since Task 7. The backend changes since then don't touch the frontend.
  - No whole-branch review has been done.
  - The workflow has never run on GitHub.
  - Migration 0012 has been applied only to the private test DBs.
  - No real fire or flood job run has been made.
  - Whether the flood work's migration `0011` was ever applied to the shared DB is **unknown**. It was pending the user's yes; ask, don't assume.

## Blockers

- **Go-live** needs the user's explicit yes at each step:
  1. a `pg_dump` backup to Downloads;
  2. `migrate history 0011` (if not already applied), then `0012`;
  3. the user sets `MODEL_JOB_TOKEN` on Render, and the GitHub secrets `MODEL_JOB_API_URL` and `MODEL_JOB_TOKEN`, then commits and pushes to `main` (scheduled workflows run only from `main`);
  4. a GitHub "Run now" with dry_run;
  5. one real fire run, checked together.
- Nothing blocks the remaining **build** steps.

## Next action (in order)

1. **Confirm nothing changed since T6.** From the repo root, run `bash .superpowers/sdd/2026-11-24-automatic-retraining/snap.sh`. It should print `e2570e8e8125e0871d08f22ca20ced738ec2485e`.
   - If it prints a different id, someone edited the tree. Diff it with `bash …/snap.sh pkg e2570e8… <new> /tmp/x.md` before going on.
2. **Re-dispatch the Task 6 review** on opus. Use the subagent-driven skill's `task-reviewer-prompt.md`, with:
   - brief: `task-6-brief.md`;
   - report: `task-6-report.md`;
   - package: `task-6-review.md` (base tree `445759072272a4cac411e952c237c9b2d2e3076b`, head `e2570e8…`);
   - the Task 6 rulings from the ledger (outside_source, the fingerprint, the 500-char truncation, `kept` carries a model, the regex workflow test, decimal masking, no EOS-RS, spots carry lon/lat).

   Ask the reviewer to check deliberately:
   - the `load_outlines` shared-DB guard, including a partial load after a crash;
   - failure posting on every exception path, and what happens when the failure post itself fails;
   - retry statuses (401/403/400 must not loop);
   - no coordinate or token in logs;
   - the workflow: `contents: read`, the crons, how the hazard is picked from `github.event.schedule`, and the dry-run input's string-vs-boolean handling;
   - `fire_attempt` and `flood_attempt` rule order and verbatim reasons.
3. Run the fix loop if needed (resume a fresh implementer with the findings; `references/fix-loop.md`), then mark "Task 6: complete" in the ledger.
4. **Final whole-branch review.** Follow the subagent-driven skill's `references/final-review.md`.
   - Package T0 `9d399a9c824954b2d9d1eff73f59aa9622a4f521` → a fresh snapshot of the whole tree (`snap.sh pkg 9d399a9… <now> <out>`, no paths).
   - Dispatch on opus, pointing at the spec, the plan, the ledger's `Ruling:` lines and every `minor (deferred)` line.
   - Re-grade the findings by effect, then run one fix wave (each fix test-first), then the full suites:
     - backend: `cd backend && PYTHONPATH="C:/Users/Sannichigetsu/.geoalert-test" venv/Scripts/python.exe manage.py test tests apps --settings=geo_test_settings_retrain_t6 --noinput`, in the background, a long run;
     - frontend: `cd frontend && CI=true npm test -- --watchAll=false`, then `npm run build`.
5. **Report to the user.** Include:
   - what was built;
   - the test counts;
   - "Rulings I made" (every ledger `Ruling:` line, with its cost);
   - "Deferred minors" (every `minor (deferred)` line);
   - the go-live steps, each needing their yes.

   Keep the workspace: nothing is committed, so the ledger is the only record. Do not commit.

## Environment gotchas

- **Never `git commit`/`add`/`stash`/`checkout`.** The user commits. `snap.sh` makes tree objects through a temporary index; it never touches HEAD, refs or the real index.
- **The default `backend/.env` is the shared database.** Every `manage.py` call needs `--settings=geo_test_settings_retrain_tN` plus `PYTHONPATH="C:/Users/Sannichigetsu/.geoalert-test"`. Never `migrate` the shared DB without a backup and the user's yes.
- **The remote test DB (Supabase) is slow.** Runs take minutes, and setUp sometimes fails with "statement timeout" or DNS errors. Rerun that suite alone and report both runs.
- **Never run `run_model_job` without `--dry-run`** outside GitHub, and never set `MODEL_JOB_SCRATCH_DB=true` in a shell.
- **Windows:** two files differing only by case clash in webpack. Bash is Git Bash. Python is `backend/venv/Scripts/python.exe`. PyYAML is not installed.
- **Parallel subagents:** give each one its own test-DB settings file and a path-limited review package (`snap.sh pkg A B OUT <paths…>`).
- **The user's own dev servers.** At handoff, two `manage.py runserver` and two `npm start` processes were running. These sessions did not start them, so leave them alone.
  - They read the working tree and the shared DB.
  - Since Task 2, the fire and flood loaders query the `model_fit` table, which the shared DB doesn't have until 0012 is applied. Until then, a local runserver can error on forecast, accuracy and readiness pages.
  - This is expected. It is not a bug to fix in code.

## Skills Review

- ✅ brainstorming: the user's three choices (own data, frequency, handoff) were each asked with previews. The design was written, self-checked as a builder, and approved.
- ✅ writing-plans: 7 tasks with pinned interfaces. Pre-flight found 5 plan defects, all ruled before dispatch.
- ⚠️ subagent-driven-development: deviated by running tasks in parallel, at the user's request, with disjoint files, separate test DBs and path-limited packages, all ruled in the ledger. Reviews caught 4 real cross-task or contract gaps:
  - the undo permission;
  - the version collision;
  - spots without points;
  - EOS-RS caching on GitHub.
- ⚠️ test-driven-development: some RED runs were cut short by the slow remote DB (Task 2), and one golden was relaxed to rounded floats. Both were ruled.
- ✅ verification-before-completion: every completion is backed by a logged test run. The UNVERIFIED items are listed above.

**Environment review (most severe first):**
1. Automated checks: the remote Supabase test DB is slow and flaky. A local PostGIS (Docker) test DB would cut minutes per run and remove the timeout reruns. Proposal: a `geo_test_settings_local` against a Docker PostGIS.
2. Navigation: the per-task snapshot workflow (`snap.sh`) exists only in this workspace. If it proves useful, move it to a repo `tools/` script.
3. Information access: whether migration 0011 is on the shared DB can't be seen without touching it. A read-only `showmigrations` needs the user's OK.
