# Automatic retraining of the fire and flood models — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A free GitHub Actions job retrains the fire model every month, and checks every January whether the flood model can be trained on GeoAlert's own located flood records. Each attempt goes back to GeoAlert, which saves it and makes it the live model only on a pass.

**Architecture:**
- **Storage.** A new table, `ModelFit` (history migration 0012), holds every attempt. The fire and flood loaders use the newer of the live fit and the committed file.
- **Endpoints.** Two token-only endpoints hand training data to the job and take its attempt back. A public endpoint lists the attempts for a new "Model updates" card.
- **Fire.** Its training moves out of the command into `fire_run.train`, with a moving 12-month test window and a switch rule against the live settings.
- **Flood.** `flood_run.run` gains an own-data mode, driven by a new `flood_own` module.
- **The job.** The management command `run_model_job` runs in `.github/workflows/model-retrain.yml`, on a throw-away PostGIS database.

**Tech Stack:** Django 4.2 / DRF / PostGIS, numpy / scikit-learn / xgboost (offline only), React (react-scripts, Jest), GitHub Actions.

**Spec:** `docs/design/specs/2026-11-24-automatic-retraining-design.md` (approved 2026-11-24).

## Global Constraints

- **Never `git commit`.** Every commit step reads "Leave uncommitted". The user commits and pushes.
- **No shared-database step.** Never run `migrate` against the shared database. `makemigrations` writes `0012_model_fit.py`; applying it is a go-live step for the user.
- **Tests run on the private test database:**
  - Backend, from `backend/`: `PYTHONPATH="C:/Users/Sannichigetsu/.geoalert-test" venv/Scripts/python.exe manage.py test <labels> --settings=geo_test_settings_flood --noinput`.
  - Frontend, from `frontend/`: `CI=true npm test -- --watchAll=false <path>`.
- **Recipes unchanged.** Same candidates, choice rules, Platt step, cut-off walks and gates (`fire_training.choose`, `flood_rules.*`). Only the data, the test window and the domain move. The hand-run commands with no new flag must produce exactly what they do today, apart from the new `built_at` field in the fire model.
- **No coordinate leaves the server** in a model, a report, a public endpoint or a job log. Spot points travel only in the token-only training-data response. The flood model and report never hold a domain outline.
- **Outside data:**
  - The job never reads the Mananga survey or Annex 11.
  - EOS-RS (the Tino map) may be downloaded on the runner for the shown-only check. It is never served and never written to `apps/history/data`.
- **History is not prediction.** History levels, `purok_levels.py` and `decide*.py` are untouched.
- **Numbers (spec 6.2-6.3):**
  - Fire: test window `WINDOW_MONTHS = 12`.
  - Flood:
    - `OWN_MIN_SPOTS = 100`, `OWN_MIN_BARANGAYS = 5`, `HELD_MIN = 10`, `MAX_FOLDS = 5`.
    - The wet season runs 1 June to 31 December of `today.year - 1`.
    - The domain buffer is `flood_training.BUFFER_M` (300 m).
- **Schedule (Manila, UTC+8):**
  - Fire at 03:17 on the 2nd of each month: cron `17 19 1 * *` UTC.
  - Flood at 03:17 on 5 January: cron `17 19 4 1 *` UTC.
  - Changed in the final review: GitHub may drop :00 runs (both were 03:00, `0 19 ...`).
- **Reason sentences, verbatim** (Python `str.format` fields; log loss to 4 decimals; months as `%b %Y`, e.g. `Feb 2026`):
  - `FIRE_SWITCHED = 'Scored {new:.4f} vs {live:.4f} on {start} to {end}'`
  - `FIRE_SWITCHED_FIRST = 'Scored {new:.4f} on {start} to {end}; no model was in use'`
  - `FIRE_WORSE = 'The new fit scored worse ({new:.4f} vs {live:.4f})'`
  - `FIRE_BASELINE = 'No better than the same chance everywhere ({new:.4f} vs {base:.4f})'`
  - `FIRE_STALE_FEATURES = 'The purok map changed; rebuild the fire features by hand'`
  - `FLOOD_FLOOR = '{n} of 100 located flood spots, {b} of 5 barangays'`
  - `FLOOD_HELD = 'Too few new spots to test ({n} of 10); tries again next January'`
  - `FLOOD_FOLDS = 'Too few barangays before the {season} wet season to test the model'`
  - `FLOOD_WORSE = "Fewer of the {season} wet season's spots in Red or Orange than the map in use ({new} vs {live})"`
  - `FLOOD_SWITCHED = 'Passed all four checks; {hits} of {n} held-back spots in Red or Orange'`
  - A flood fit that fails a gate: `' '.join(report['acceptance']['reasons'])`.
  - `STALE_FIT = 'The purok map changed while it trained; the fit was not used'` (server).
  - `FAILED = 'Failed: {detail}'`, where `detail` is `f'{type(exc).__name__}: {str(exc)[:200]}'`.
- **Other copy, verbatim:**
  - `FROM_NOAH_NOTE = "From UP NOAH's map; outside the area GeoAlert's records cover"`.
  - `TRAINED_ON_GEOALERT = "GeoAlert's located flood records"`.
  - `BASIS_GEOALERT = "From a machine-learning model of where floods reached in GeoAlert's own located flood records, with UP NOAH flood depths and terrain. It shows how flood-prone an area is, not whether a flood is coming, and it is the same in every month."`
  - Flood gate 2's name in own mode: `Held-back wet season spots in Red or Orange`.
  - The own domain rule: `"Convex hull of GeoAlert's located flood spots before the held-back season, buffered 300 m, clipped to the city"`.
  - The own mode's not-assessed reason inside the domain: `UNLIKE_OWN = "Its ground is unlike the places GeoAlert's records flooded"`.
  - Card title `Model updates`. Subtitle: `Each automatic retraining: when it ran, what it decided and why. A new model goes live only when it does at least as well as the one in use.`
  - Result labels: `switched` → `Switched`, `kept` → `Kept current`, `not_tried` → `Not tried`, `skipped` → `Skipped`, `failed` → `Failed`. A live row's result cell adds ` (in use)`.
  - Empty: `No automatic retraining has run yet.` Loading: `Loading model updates…`. Error: `Model updates could not be loaded right now.`
  - Readiness spots line: `Located flood spots with a map point: {n} of {needed}, in {barangays} of {barangays_needed} barangays.`
  - Readiness training line, own data: `The flood map comes from {trained_on} ({own_spots} flood spots). Built {YYYY-MM-DD}.`
  - The disclaimer's phrase `from UP NOAH's flood maps and the 2017 UP Mananga flood survey` becomes `from UP NOAH's flood maps and recorded floods`.

## Review Focus

1. **`run_model_job` started on a laptop whose `.env` points at the shared database.** It must never write puroks or barangays there. Tests: Task 6 `test_load_outlines_refuses_without_scratch_flag`, `test_load_outlines_refuses_when_puroks_exist`.
2. **A fit trained on the old purok map arrives after a purok reload.** It is saved as `skipped` with `STALE_FIT`, and the live model stays. Test: Task 1 `test_stale_switched_fit_is_skipped`.
3. **A valid token posts a fit the site can't read** (a fire area without 12 months, an unknown flood source). The server refuses it with 400 and the live model is untouched. Test: Task 2 `test_unreadable_fit_is_refused`.
4. **Render is asleep or a download fails mid-run.** The job retries the fetch, and on any error posts a `failed` attempt before exiting non-zero. Tests: Task 6 `test_fetch_retries_then_raises`, `test_command_posts_failed_on_error`.
5. **Two attempts both make a fit live, or an admin undoes to a fit that never went live.** There is at most one live fit per hazard, and undo goes only to an earlier `switched` fit on the current map. Tests: Task 1 `test_one_live_fit_per_hazard`, `test_make_live_only_switched_on_current_map`.

---

### Task 1: The `ModelFit` table, its helpers and the admin undo

**Files:**
- Modify: `backend/apps/history/models.py` (new model at the end)
- Create: `backend/apps/history/migrations/0012_model_fit.py` (by `makemigrations history`)
- Create: `backend/apps/history/model_fits.py`
- Create: `backend/apps/history/admin.py`
- Test: `backend/tests/test_model_fits.py`

**Interfaces:**
- Produces:
  - `ModelFit`, db_table `model_fit`, column prefix `mfit_`:
    - `hazard` TextField, choices `HAZARDS = ('fire', 'flood')`, with a check constraint;
    - `result` TextField, choices `RESULTS = ('switched', 'kept', 'not_tried', 'skipped', 'failed')`, with a check constraint;
    - `reason` TextField; `version` TextField (blank); `outlines_version` TextField (blank);
    - `built_at` DateTimeField (null); `model` JSONField (null); `report` JSONField (null);
    - `is_live` BooleanField (default False); `created_at` (auto_now_add);
    - `UniqueConstraint(fields=['hazard'], condition=Q(is_live=True), name='model_fit_one_live_per_hazard')`;
    - Meta ordering `['-created_at', '-id']`.
  - `model_fits.live_fit(hazard: str) -> ModelFit | None`.
  - `model_fits.newer_is_fit(file_model: dict | None, fit: ModelFit | None) -> bool`:
    - True when there is a fit and either there is no file, the file has no parseable `built_at`, or `fit.built_at >= the file's built_at`.
  - `model_fits.record_attempt(payload: dict, outlines_version: str, check=None) -> ModelFit`:
    - Raises `ValueError(message)` on a bad payload.
    - `check(hazard, model, report, outlines_version)` returns `None` when the site can read the fit, or a reason string. Task 2 passes the real check.
    - The check runs only for a `switched` result on the current map, the only fits that can go live.
  - `model_fits.make_live(fit: ModelFit, outlines_version: str) -> None`, which raises `ValueError`.
  - `model_fits.attempts(limit: int = 24) -> list[dict]`. Each entry has the keys `hazard, result, reason, version, created_at (ISO), is_live`.
  - `model_fits.STALE_FIT`.

- [ ] **Step 1: Write the failing tests** in `backend/tests/test_model_fits.py` (TestCase). Use a helper `payload(result='switched', hazard='fire', outlines='v1', built_at='2027-02-02T03:00:00+08:00')` that returns `{'hazard', 'result', 'reason': 'r', 'model': {'version': 'x@1', 'outlines_version': outlines, 'built_at': built_at}, 'report': {'version': 'x@1'}}`.
  - `test_switched_fit_becomes_live`: `record_attempt(payload(), 'v1')`; `live_fit('fire').version == 'x@1'`; `is_live` is True.
  - `test_second_switch_replaces_the_first`: two switched attempts. Only the newer one is live; the first has `is_live` False.
  - `test_kept_fit_is_saved_not_live`: with result `kept`, `live_fit('fire') is None` and the row exists with its model.
  - `test_stale_switched_fit_is_skipped`: `record_attempt(payload(outlines='old'), 'v1')` → `result == 'skipped'`, `reason == STALE_FIT`, not live.
  - `test_not_tried_needs_no_model`: `{'hazard': 'flood', 'result': 'not_tried', 'reason': '7 of 100 …'}` is saved, with `model` and `report` None.
  - `test_bad_payloads_raise`, each raising `ValueError`:
    - an unknown hazard;
    - an unknown result;
    - an empty reason;
    - a reason over 500 characters;
    - switched without a model;
    - model and report versions that differ;
    - a `built_at` that won't parse.
  - `test_check_refusal_raises`: `check=lambda *a: 'cannot read'` → `ValueError('cannot read')`, and nothing is saved.
  - `test_one_live_fit_per_hazard`: a second `is_live=True` fire row created directly raises `IntegrityError` (use `transaction.atomic`). A live flood row beside a live fire row is fine.
  - `test_newer_is_fit`, cases:
    - no fit → False;
    - no file → True;
    - a file without `built_at` → True;
    - a file newer than the fit → False;
    - a file older than the fit → True;
    - equal times → True.
  - `test_make_live_only_switched_on_current_map`:
    - undo to an earlier switched fit makes it live and the other not;
    - a `kept` fit raises;
    - a switched fit with `outlines_version` 'old' raises when the current version is 'v1'.
  - `test_attempts_newest_first_without_bodies`: the keys are exactly `{'hazard', 'result', 'reason', 'version', 'created_at', 'is_live'}`, newest first, capped at `limit`.
  - `test_admin_action_undoes`: the admin action `make_live_action` on a switched fit makes it live. Use `admin.site._registry[ModelFit]`, a superuser request from `RequestFactory`, and a patched `Purok.outlines_version` returning the fit's version.

- [ ] **Step 2: Run them; expect failure.** Run: `… manage.py test tests.test_model_fits …`. Expected: ImportError (no `ModelFit`).

- [ ] **Step 3: Add `ModelFit`, run `makemigrations history`, and write `model_fits.py`.**
  - `record_attempt` validates, then saves in one `transaction.atomic()`.
  - For a `switched` result on the current map: `select_for_update` the hazard's live rows, set them not live, and save the new row live.
  - `built_at` is parsed with `datetime.fromisoformat`.
  - `admin.py` registers `ModelFit` read-only: list display hazard, created_at, result, is_live, version. The single action `make_live_action` calls `make_live(fit, Purok.outlines_version())` and reports a `ValueError` as an error message.

- [ ] **Step 4: Run them; expect pass.** Same command → OK. Also run `… manage.py makemigrations --check --dry-run --settings=geo_test_settings_flood` → "No changes detected".

- [ ] **Step 5: Leave uncommitted.**

---

### Task 2: The loaders read the live fit; flood's own-data source

**Files:**
- Modify: `backend/apps/history/fire_purok.py` (`_read` → `parse` + `_read`, and `load`)
- Modify: `backend/apps/history/flood_purok.py`:
  - `_read` → `parse` + `_read`, and `load`;
  - `BASIS_GEOALERT`, `basis`, `purok_rows`, `readiness`, `TRAINED_ON_GEOALERT`.
- Modify: `backend/apps/history/model_fits.py` (`site_check`)
- Test: `backend/tests/test_model_fit_loading.py`

**Interfaces:**
- Consumes: `live_fit`, `newer_is_fit`, `record_attempt(…, check=)` from Task 1.
- Produces:
  - `fire_purok.parse(data: dict, report: dict | None, outlines: str) -> FireModel | str` and `flood_purok.parse(data: dict, report: dict | None, outlines: str) -> FloodModel | str`. Each returns the same values and reasons `_read` gives today; `_read` now reads the files and calls `parse`.
  - `load()` in both modules:
    - picks the live fit when `newer_is_fit(file_data, fit)` is true, else the file;
    - its cache key adds the fit's id;
    - it still rechecks at most every `RECHECK_SECONDS`.
  - `FireModel` gains a last field, `model: dict | None = None`, set from `data.get('model')` (the family and settings). Task 5 and the `--window moving` command read the live settings from it.
  - Flood sources: `('model', 'noah', 'geoalert')`. `basis(model)` returns `BASIS_GEOALERT` for `geoalert`.
  - `flood_purok.purok_rows` rows gain `note`, taken from the area's `note`, else None.
  - `readiness()['flood_map']` gains `source` and `own_spots` (the report's `own_spots`, else None). Its `trained_on` is `TRAINED_ON_GEOALERT` when the source is `geoalert`.
  - `model_fits.site_check(hazard, model, report, outlines) -> str | None`: the matching `parse`, returning its string, or None.

- [ ] **Step 1: Write the failing tests** in `backend/tests/test_model_fit_loading.py`. Use `FireSetupMixin`; build the fire documents with `tests/fire_model_file.model_document`, the flood ones with `tests/flood_model_file.model_document`, and create fits with `ModelFit.objects.create(...)`. Call `clear_cache()` in setUp.
  - `test_fire_uses_a_newer_live_fit`: the file has `built_at` 2026-11-01 and the fit 2027-02-02, with a different version → `fire_purok.load().version` is the fit's.
  - `test_fire_file_wins_when_newer`: the file is 2027-03-01 and the fit 2027-02-02 → the file's version.
  - `test_fire_file_without_built_at_loses_to_a_fit` (the committed file today).
  - `test_stale_live_fit_falls_back_to_reason`: the newer fit's `outlines_version` differs → `STALE` (as for a file).
  - `test_flood_geoalert_source_is_read`: a fit with `source: 'geoalert'` loads; `basis(model) == BASIS_GEOALERT`.
  - `test_purok_rows_carry_the_note`: an area with `note: 'n1'` has `row['note'] == 'n1'`; others have `note` None.
  - `test_fire_model_keeps_family_and_settings`: `load().model == {'family': …, 'settings': …}`, taken from the document's `model`.
  - `test_readiness_names_geoalert_records`: a live geoalert fit whose report has `own_spots: 120` gives `flood_map['trained_on'] == TRAINED_ON_GEOALERT`, `source == 'geoalert'`, `own_spots == 120`.
  - `test_unreadable_fit_is_refused`, each raising `ValueError` and leaving `live_fit` unchanged:
    - `record_attempt(fire payload whose area has 11 months, Purok.outlines_version(), check=site_check)`;
    - a flood payload with `source: 'other'`.
- [ ] **Step 2: Run; expect failure.** `… test tests.test_model_fit_loading …` → failures (no `parse`, no `geoalert`).
- [ ] **Step 3: Implement the steps above.** `load()` reads the file JSON (None if missing), gets `live_fit(hazard)`, and parses whichever source wins. A missing file with no fit stays `NOT_TRAINED`.
- [ ] **Step 4: Run the new tests plus the existing loader suites; expect pass.** `… test tests.test_model_fit_loading tests.test_fire_purok tests.test_flood_purok tests.test_flood_readiness …` → OK.
- [ ] **Step 5: Leave uncommitted.**

---

### Task 3: Fire — `fire_run.train`, the moving window and the switch rule

**Files:**
- Modify: `backend/apps/history/fire_training.py` (`Panel.fold`, `build_panel(..., fold_end=None)`, `oof` uses the fold)
- Create: `backend/apps/history/fire_run.py` (the body of today's `Command.handle` and its helper methods, moved)
- Modify: `backend/apps/history/management/commands/train_fire_model.py` (now thin: arguments, file I/O, `--window`)
- Test: `backend/tests/test_fire_run.py`. The existing `tests.test_train_fire_model` and `tests.test_fire_training` must stay green unchanged.

**Interfaces:**
- Produces:
  - `Panel.fold: np.ndarray | None = None`, the last field. `oof` uses `panel.fold`, or `panel.month // 12` when it is None.
  - `build_panel(table, label_map, months, fold_end: int | None = None)`:
    - with `fold_end`, `fold = (fold_end - 1 - month) // 12`;
    - otherwise it is the calendar year.
  - `fire_run.WINDOW_MONTHS = 12`, plus the five `FIRE_*` sentences (see Global Constraints).
  - `fire_run.train(fires, table, names: dict, today: date, window: str = 'fixed', live: dict | None = None, csv_bytes: bytes = b'', boot_reps=fe.BOOT_REPS, interval_reps=fe.INTERVAL_REPS, log=print) -> tuple[dict, dict]`:
    - `live` is `{'family', 'settings'}` or None;
    - it raises `ValueError` where the command raised `CommandError`;
    - the model JSON gains `'built_at'` (Manila local, ISO, seconds).
  - In window `'moving'` (the window holds back `WINDOW_MONTHS`):
    - `end = today.year * 12 + today.month - 1` and `start = end - 12`;
    - development uses months `[FIRST_MONTH, start)` with `fold_end=start`, and needs at least 2 folds, else `ValueError('The moving window needs at least 13 months before the test window.')`;
    - the test window is `[start, end)`;
    - deployment is unchanged;
    - `report['test']['window']` names that window.
  - `report['switch']` (moving only) = `{'passed': bool, 'new_log_loss': float, 'live_log_loss': float | None, 'same_everywhere_log_loss': float, 'window': {'start': 'Feb 2026', 'end': 'Jan 2027'}, 'reason': str}`, where:
    - `new_log_loss` is the mean row log loss of the development fit on the window;
    - `live_log_loss` is the same score for `live`'s family and settings, refit identically: `oof` on development, `Choice(family, settings, oof, [], {})`, `fit_final`, predict the window;
    - `same_everywhere_log_loss` is `report['test']['comparison']['comparison_same_everywhere']['log_loss']['value']`;
    - `passed = new < base and (live is None or new <= live)`;
    - the reason is `FIRE_BASELINE` when `new >= base`, else `FIRE_WORSE` when `new > live`, else `FIRE_SWITCHED`, or `FIRE_SWITCHED_FIRST` when `live` is None.
  - The command: `train_fire_model --window {fixed,moving}`, default `fixed`. With `moving`, `live` comes from the model `fire_purok.load()` returns (its report's `model`), or None. File writing and the console summary stay in the command.

- [ ] **Step 1: Write the failing tests** in `backend/tests/test_fire_run.py`. Reuse `make_world` and `write_table` from `tests.test_train_fire_model` (import them). Use `boot_reps=20, interval_reps=3`.
  - `test_build_panel_counts_folds_back_from_the_window`: months `range(2023*12, 2026*12 + 1)` with `fold_end = 2026*12 + 1` → `fold` is 0 for Feb 2025-Jan 2026, 1 for the 12 months before that, and 2 for the rest.
  - `test_default_folds_are_calendar_years`: with no `fold_end`, `fold == month // 12`.
  - `test_fixed_window_matches_the_command`: `train(..., window='fixed')` gives the same `version`, `areas` and `report['test']['window']` as `call_command('train_fire_model', ...)` on the same world, ignoring `built_at`.
  - `test_moving_window_tests_the_newest_12_months`: with `today = date(2027, 2, 2)`, `report['test']['window'] == {'start': '2026-02', 'end': '2027-01'}` and `report['switch']['window'] == {'start': 'Feb 2026', 'end': 'Jan 2027'}`.
  - `test_moving_needs_13_months` raises `ValueError` with the message above.
  - `test_same_settings_switch`: `live` = the new fit's own `report['model']` → `new_log_loss == live_log_loss` and `passed` (if it beats the baseline).
  - `test_worse_new_fit_is_kept`: patch `fire_run._window_log_loss` so the new fit scores 0.05 and the live one 0.04 → `passed` False, reason `'The new fit scored worse (0.0500 vs 0.0400)'`.
  - `test_baseline_blocks`: patched new 0.05, base 0.04 → reason starts with `'No better than the same chance everywhere'`.
  - `test_first_fit_reason`: `live=None` → reason matches `FIRE_SWITCHED_FIRST`.
  - `test_model_has_built_at`: it parses with `datetime.fromisoformat`.
  - `test_command_moving_flag`: `call_command('train_fire_model', window='moving', today='2027-02-02', ...)` writes a report with a `switch` key.
- [ ] **Step 2: Run; expect failure.** `… test tests.test_fire_run …` → ImportError.
- [ ] **Step 3: Implement.** Move the code; don't rewrite it. Factor the window scoring into `fire_run._window_log_loss(dev, test, family, settings, choice=None) -> float` so the tests can patch it.
- [ ] **Step 4: Run; expect pass.** `… test tests.test_fire_run tests.test_train_fire_model tests.test_fire_training tests.test_fire_evaluation …` → OK.
- [ ] **Step 5: Leave uncommitted.**

---

### Task 4: Flood — the own-data mode

**Files:**
- Create: `backend/apps/history/flood_own.py`
- Modify: `backend/apps/history/flood_run.py` (`run(..., mode='survey', folds=None, outside=None)`, plus the own constants)
- Test: `backend/tests/test_flood_own.py`. The existing `tests.test_flood_run` stays green unchanged.

**Interfaces:**
- Produces:
  - `flood_own` constants: `OWN_MIN_SPOTS, OWN_MIN_BARANGAYS, HELD_MIN, MAX_FOLDS`, plus the `FLOOD_*` sentences (see Global Constraints).
  - A **spot** is `{'id': str, 'when': str (ISO, Manila), 'lon': float, 'lat': float, 'purok_id': int | None, 'barangay': str}`. A training spot also carries `'positive': True` and `'inputs': {column: float}`.
  - `flood_own.floor(spots) -> {'n': int, 'barangays': int, 'enough': bool}`. Barangays are the distinct non-empty `barangay` values.
  - `flood_own.season_split(spots, today: date) -> tuple[list, list, int]`, returning `(train, held, season)`:
    - `season = today.year - 1`;
    - `train` is every spot whose local date is before 1 June of the season;
    - `held` is 1 June to 31 December of the season;
    - later spots are in neither.
  - `flood_own.own_folds(spots) -> dict[str, int]`:
    - `k = min(MAX_FOLDS, number of barangays)`;
    - barangays sorted by spot count descending, then by name; each goes to the fold with the fewest spots so far, the lowest index on a tie.
  - `flood_own.compare(new_levels: list, live_levels: list) -> tuple[int, int]`, the hit counts.
  - `flood_own.train_own(features, train_spots, held_spots, city, outside: dict, season: int, fingerprint: str, eosrs_flagged=None, reps=1000, stability_reps=200, log=print) -> tuple[dict, dict]`:
    - it calls `run(..., mode='own', folds=own_folds(train_spots), outside=outside)`;
    - `load_tests` returns `{'geoalert_points': held_spots, 'eosrs_flagged': eosrs_flagged}`, with an all-False array of the buildings' length when `eosrs_flagged` is None.
  - `run` in `mode='own'`:
    - the folds come from `folds`;
    - the domain is built from the training spots (the same `tr.domain`);
    - a purok whose not-assessed reason would be `tr.OUTSIDE` takes `outside[pid]`'s `level`, `score` and `not_assessed_reason`, plus `'note': FROM_NOAH_NOTE` when it has a level. A purok missing from `outside` (no flood model was live) keeps the `tr.OUTSIDE` reason and no level;
    - `tr.UNLIKE` becomes `UNLIKE_OWN`;
    - gate 2 is named `Held-back wet season spots in Red or Orange` and scores **every** held spot's level on this composed map, inside or outside the domain;
    - `report['temporal_test'] = {'season': season, 'held_back': [{'day', 'barangay', 'purok_id', 'level'}], 'eosrs': …}`, with no `mananga_points`;
    - `source = 'geoalert'` and the version is `f'{chosen}@{sha}'`;
    - `basis = BASIS_GEOALERT`;
    - `own_spots = len(train positives)`, with no `survey_spots`;
    - `CREDITS_OWN` = CREDITS without the survey entry; `LIMITS_OWN` (see below);
    - the model `domain.rule` is the own rule.
  - When an own fit is not adopted, `areas` is still the composed map, with no NOAH-fallback substitution. The job won't make it live.
  - `LIMITS_OWN`:
    - `["The flood spots are places where GeoAlert recorded a flood. The other buildings are not known to be dry, so the levels show how flood-prone an area is compared with the rest, not a chance of flooding.",`
    - `"Outside the area GeoAlert's records cover, levels come from UP NOAH's map.",`
    - `'Purok outlines are estimates; areas with a low-confidence outline are marked.',`
    - `"UP NOAH's flood maps are labelled beta.",`
    - `'This is not a forecast: it is the same in every month and does not say a flood is coming.']`

- [ ] **Step 1: Write the failing tests** in `backend/tests/test_flood_own.py`. Use `synthetic_city()` from `tests.test_flood_run` for the features, spots and city, and spread the training spots over at least 5 barangays.
  - `test_floor`: 99 spots in 5 barangays → not enough; 100 in 4 → not; 100 in 5 → enough. Empty barangay names don't count.
  - `test_season_split`: with `today = date(2027, 1, 5)`:
    - 2026-05-31 23:30 Manila → train;
    - 2026-06-01 00:10 → held;
    - 2026-12-31 → held;
    - 2027-01-02 → neither;
    - season 2026.
  - `test_own_folds_are_balanced_and_stable`: counts {A:5, B:4, C:3, D:2, E:1, F:1} → k 5; A→0, B→1, C→2, D→3, E→4, F→4; the same result on shuffled input.
  - `test_own_folds_with_few_barangays`: 3 barangays → k 3.
  - `test_outside_puroks_keep_the_live_level`: the domain is built from spots in a few puroks. A purok outside it, with `outside[pid] = {'level': 'Red', 'score': 0.9, 'not_assessed_reason': None}`, ships `level 'Red'` with `note == FROM_NOAH_NOTE`. A not-assessed live row is copied as it is, with `note` absent or None.
  - `test_held_spots_scored_on_the_composed_map`: a held spot in that outside Red purok counts as a hit in gate 2's detail.
  - `test_own_report_has_no_survey_or_coordinates`:
    - `source == 'geoalert'` and `basis == BASIS_GEOALERT`;
    - `'survey_spots' not in report` and `'mananga_points' not in report['temporal_test']`;
    - no credit mentions `Paringit`;
    - `json.dumps(model) + json.dumps(report)` contains no spot's `f'{lon:.4f}'` and no `'POLYGON'`.
  - `test_survey_mode_unchanged`: the default `run(...)` result for the synthetic city has `source in ('model', 'noah')` and the same version as before (compare with a direct call without `mode`).
  - `test_compare`: levels `['Red', 'Green', 'Orange']` against `['Green', 'Green', 'Red']` → `(2, 1)`.
- [ ] **Step 2: Run; expect failure.** `… test tests.test_flood_own …` → ImportError.
- [ ] **Step 3: Implement.** Keep survey mode byte-identical. Every own-mode branch is behind `mode == 'own'`.
- [ ] **Step 4: Run; expect pass.** `… test tests.test_flood_own tests.test_flood_run tests.test_flood_rules tests.test_flood_training …` → OK.
- [ ] **Step 5: Leave uncommitted.**

---

### Task 5: Server endpoints, the token, the spots count

**Files:**
- Modify: `backend/config/settings/base.py`: add `MODEL_JOB_TOKEN = env('MODEL_JOB_TOKEN', default='')`, beside `HAZARD_LOG_WRITER`, with a two-line comment.
- Create: `backend/apps/history/job_auth.py`
- Modify: `backend/apps/history/flood_purok.py` (`located_spots()`; `readiness()` gains `own_spots`)
- Modify: `backend/apps/history/model_fits.py` (`training_data`)
- Modify: `backend/apps/history/views.py`, `backend/apps/history/urls.py`
- Test: `backend/tests/test_model_job_api.py`

**Interfaces:**
- Consumes: `record_attempt`, `site_check`, `attempts`, `live_fit` (Tasks 1-2); `flood_own.floor` (Task 4); the loaders' chosen model (Task 2).
- Produces:
  - `job_auth.ModelJobTokenPermission`: the bearer token compared with `hmac.compare_digest`. An empty `MODEL_JOB_TOKEN` refuses everything.
  - `flood_purok.located_spots() -> list[spot]`, oldest first:
    - Flood records **with a map point**, `id = f'r:{uuid}'`, with `barangay` = the record's barangay name, else the barangay containing the point;
    - then "Affected" marks on Flood zones, `id = f'm:{id}'`, with the containing barangay's name, else `''`;
    - `purok_id` = `_smallest_purok(point)`'s id, or None;
    - `when` = `timezone.localtime(...).isoformat(timespec='seconds')`.
  - `readiness()['own_spots'] = {'n', 'barangays', 'needed': 100, 'barangays_needed': 5, 'enough'}`, from `floor(located_spots())`.
  - `model_fits.training_data(hazard: str, outlines: bool = False) -> dict`:
    - **fire:** `{'hazard', 'outlines_version', 'barangays': {id: name}, 'fires': [{'record_id', 'when', 'purok_ids', 'barangay_id'}], 'live': {'version', 'family', 'settings'} | None}`:
      - the fires come from `fire_training.fire_records()`, with `when` as local ISO;
      - `live` comes from `fire_purok.load()`'s `version` and `model` (Task 2), and is None when that is a reason string or `model` is None.
    - **flood:** `{'hazard', 'outlines_version', 'spots': located_spots(), 'floor': floor(...), 'live': {'version', 'source', 'areas': {pid: {'level', 'score', 'not_assessed_reason'}}} | None}`. With `outlines=True` it adds:
      - `'barangays': [{'id', 'name', 'boundary': GeoJSON}]`;
      - `'puroks': [{'id', 'barangay_id', 'name', 'kind', 'parent', 'source', 'confidence', 'boundary': GeoJSON}]`.
    - It reads `Purok.outlines_version()` before and after. If they differ it raises `model_fits.OutlinesChanged`.
  - Views (DRF `APIView`, `authentication_classes = []`):
    - `ModelJobDataView`: GET `model-job/data/?hazard=fire|flood&outlines=1`; token; `Cache-Control: no-store`; 400 `{'detail': 'hazard must be fire or flood.'}`; 409 on `OutlinesChanged`.
    - `ModelJobAttemptView`: POST `model-job/attempts/`; token; returns 201 `{'id', 'result', 'is_live'}`, or 400 `{'detail': str(exc)}` on `ValueError`. It calls `record_attempt(request.data, Purok.outlines_version(), check=site_check)`.
    - `ModelUpdatesView`: GET `forecast/updates/`; `AllowAny`; `_public(Response({'updates': attempts()}))`.

- [ ] **Step 1: Write the failing tests** in `backend/tests/test_model_job_api.py`, with `@override_settings(MODEL_JOB_TOKEN='t0k')` and `FireSetupMixin`.
  - `test_token_required`: each of the two token endpoints gives 403 for:
    - no header;
    - `Bearer wrong`;
    - `MODEL_JOB_TOKEN=''` with an empty bearer.
  - `test_fire_data_has_no_coordinates`: a fire with a purok. The response holds `fires[0]['purok_ids']`, `outlines_version == Purok.outlines_version()`, and `Cache-Control` contains `no-store`. `'POINT'` is not in the JSON, and neither is any 4-decimal coordinate of the fire's location.
  - `test_flood_data_spots_and_outlines`:
    - a located flood record with a point, an Affected mark, and a purok-only record (excluded) → 2 spots with `purok_id`;
    - `puroks` is absent unless `outlines=1`, and then present with GeoJSON boundaries.
  - `test_bad_hazard_400`.
  - `test_outlines_changed_409`: patch `Purok.outlines_version` to return 'a' and then 'b'.
  - `test_post_switched_goes_live`:
    - a valid fire model from `tests.fire_model_file.model_document` with `built_at` and the current outlines → 201, `is_live` True;
    - `fire_purok.load()` (after `clear_cache()`) gives the posted version.
  - `test_post_unreadable_400`: a fire model with 11 months → 400, nothing live.
  - `test_updates_public_and_bare`:
    - `forecast/updates/` needs no token and has `Cache-Control` public;
    - the entries have no `model` or `report` key;
    - the JSON has no `'POINT'`.
  - `test_readiness_own_spots`: 2 spots in 1 barangay → `{'n': 2, 'barangays': 1, 'needed': 100, 'barangays_needed': 5, 'enough': False}`.
- [ ] **Step 2: Run; expect failure** (404s and ImportError). `… test tests.test_model_job_api …`
- [ ] **Step 3: Implement.** In `urls.py`, add the three paths, each with a one-line comment in the file's style.
- [ ] **Step 4: Run; expect pass.** `… test tests.test_model_job_api tests.test_flood_readiness tests.test_security_gaps …` → OK.
- [ ] **Step 5: Leave uncommitted.**

---

### Task 6: The job — `run_model_job` and the GitHub workflow

**Files:**
- Create: `backend/apps/history/model_job.py`
- Create: `backend/apps/history/management/commands/run_model_job.py`
- Create: `.github/workflows/model-retrain.yml`
- Modify: `README.md` (a short "Automatic retraining" section: the two secrets, the Render variable, the dry run)
- Test: `backend/tests/test_model_job.py`

**Interfaces:**
- Consumes: `fire_run.train` and its `report['switch']` (Task 3); `flood_own.*` (Task 4); the endpoint shapes (Task 5).
- Produces:
  - Environment: `MODEL_JOB_API_URL` (the site's base URL, no trailing slash), `MODEL_JOB_TOKEN`, and `MODEL_JOB_SCRATCH_DB` (`true` only in the workflow).
  - `model_job.fetch(hazard: str, outlines: bool = False, tries: int | None = None, wait: float = 30, timeout: float = 90) -> dict`:
    - `tries` defaults to `int(os.environ.get('MODEL_JOB_TRIES', '5'))`;
    - a GET with the bearer token;
    - it retries on a connection error, a timeout, 5xx and 409, sleeping `wait` between tries;
    - then raises `RuntimeError('GeoAlert did not answer after {tries} tries.')`.
  - `model_job.post(attempt: dict, timeout: float = 90) -> dict`, which raises `RuntimeError` on a non-201.
  - `model_job.fire_records_from(data: dict) -> list[FireRecord]`: `when` comes from `datetime.fromisoformat`, and `barangays` keys become ints.
  - `model_job.fire_attempt(data: dict, today: date, features_dir: Path, boot_reps: int, interval_reps: int, log) -> dict`:
    - the features table and bytes come from `features_dir` (the command passes `fire_features.DATA_DIR`, the checked-out files);
    - when `table.outlines_version != data['outlines_version']` it returns `skipped` / `FIRE_STALE_FEATURES` with no model;
    - otherwise it calls `fire_run.train(..., window='moving', live=data['live'])`;
    - the result is `switched` when `report['switch']['passed']`, else `kept`; the reason is `report['switch']['reason']`;
    - it includes the model and report.
  - `model_job.flood_attempt(data: dict, today: date, cache: Path, workdir: Path, reps: int, stability_reps: int, log, fetch=fetch) -> dict`:
    1. `floor` not enough → `not_tried` / `FLOOD_FLOOR`.
    2. `season_split`: held below `HELD_MIN` → `not_tried` / `FLOOD_HELD`.
    3. Fewer than 2 training barangays → `not_tried` / `FLOOD_FOLDS`.
    4. Otherwise:
       - `fetch('flood', outlines=True)` and `load_outlines(...)`;
       - `call_command('build_flood_features', cache_dir=cache, output_dir=workdir)`;
       - `ff.read_features` and `ff.features_at` for the training spots' inputs;
       - `city` = the union of the loaded barangays;
       - `eosrs_flagged` is computed the way `train_flood_model`'s `load_tests` computes it from `flood_labels.eosrs_polygons(cache)`, or None when that download fails;
       - `train_own(...)`, with `outside` from `data['live']['areas']` (int keys), or `{}` when `data['live']` is None.
    5. It sets `model['outlines_version']` to the server's `data['outlines_version']`.
    6. Not adopted → `kept` with the joined acceptance reasons.
    7. Adopted while the live source is `geoalert`, but `compare(new, live)` shows fewer hits → `kept` / `FLOOD_WORSE`. Here:
       - `new` is the `level` list from `report['temporal_test']['held_back']`;
       - `live` is `data['live']['areas'][str(purok_id)]['level']` for each held spot, None when missing.
    8. Otherwise `switched` / `FLOOD_SWITCHED`.
  - `model_job.load_outlines(data: dict) -> None`:
    - raises `RuntimeError('Outlines are loaded only into the job\'s own empty database (MODEL_JOB_SCRATCH_DB=true).')` unless `os.environ.get('MODEL_JOB_SCRATCH_DB') == 'true'` **and** `Purok.objects.count() == 0` **and** `Barangay.objects.count() == 0`;
    - creates the barangays, then the puroks, with their server ids.
  - The command `run_model_job --hazard {fire,flood} [--dry-run] [--today YYYY-MM-DD] [--cache-dir DIR]`:
    - builds the attempt;
    - a dry run prints `result: reason` and posts nothing;
    - otherwise it posts and prints the server's answer;
    - on any exception it posts `{'hazard', 'result': 'failed', 'reason': FAILED}` (unless it is a dry run) and raises `CommandError`.
    - It prints only counts, results and reasons, never a spot.
  - The workflow `model-retrain.yml`:
    - `on.schedule`: the two crons (see Global Constraints);
    - `workflow_dispatch` inputs: `hazard` (choice fire/flood) and `dry_run` (boolean);
    - `permissions: contents: read`; `concurrency: model-retrain`;
    - one job, `ubuntu-24.04`, `timeout-minutes: 120`, with the same PostGIS service, env, GDAL install and Python setup as `ci.yml`'s backend job;
    - steps: `python manage.py migrate --noinput` (the service DB), then `python manage.py run_model_job --hazard $HAZARD [--dry-run]`;
    - `HAZARD` is the dispatch input, or `flood` when `github.event.schedule == '17 19 4 1 *'` (changed in the final review: GitHub may drop :00 runs), else `fire`;
    - secrets `MODEL_JOB_API_URL` and `MODEL_JOB_TOKEN`; env `MODEL_JOB_SCRATCH_DB: 'true'`;
    - `actions/cache@v4` on `backend/.hazard_cache` with key `model-job-cache-v1`.

- [ ] **Step 1: Write the failing tests** in `backend/tests/test_model_job.py`. Patch `requests.get`, `requests.post` and `time.sleep` with `unittest.mock`.
  - `test_fetch_retries_then_raises`: 5 timeouts → `RuntimeError`, and `sleep` is called 4 times.
  - `test_fetch_retries_on_409_then_succeeds`.
  - `test_fetch_sends_the_bearer_token`.
  - `test_fire_attempt_skips_on_stale_features`: `data['outlines_version']` differs from the table's → `{'result': 'skipped', 'reason': FIRE_STALE_FEATURES}` with no `model` key.
  - `test_fire_attempt_switch_and_kept`: patch `fire_run.train` to return a report with `switch.passed` True, then False → `switched` and `kept`, each with the report's reason.
  - `test_flood_attempt_not_tried_below_floor`: 7 spots → `{'result': 'not_tried', 'reason': '7 of 100 located flood spots, 1 of 5 barangays'}`, and `fetch` is never called with `outlines=True`.
  - `test_flood_attempt_not_tried_few_held`: 120 spots in 6 barangays with 4 in the season → `FLOOD_HELD` with n 4.
  - `test_flood_attempt_kept_when_fewer_hits`:
    - patch `load_outlines`, `call_command`, `ff.read_features`, `ff.features_at` and `flood_own.train_own`;
    - the adopted report has 3 of 10 held spots flagged, and the live geoalert areas would give 5;
    - expect `kept` with `"Fewer of the 2026 wet season's spots in Red or Orange than the map in use (3 vs 5)"`.
  - `test_flood_attempt_sets_server_outlines_version`.
  - `test_load_outlines_refuses_without_scratch_flag`.
  - `test_load_outlines_refuses_when_puroks_exist`: with the flag set but `FireSetupMixin` puroks present → `RuntimeError`, and the purok count is unchanged.
  - `test_load_outlines_keeps_ids`: with the flag set on an empty test DB (delete the setup's rows first), the loaded ids equal the payload's.
  - `test_command_dry_run_posts_nothing`.
  - `test_command_posts_failed_on_error`:
    - `fire_attempt` raises `OSError('disk')` → `post` is called with `result 'failed'` and reason `'Failed: OSError: disk'`;
    - `CommandError` is raised.
  - `test_command_prints_no_coordinates`: the captured stdout of a flood dry run with spots contains no spot's `f'{lon:.4f}'`.
  - `test_workflow_file`: `yaml.safe_load` of the workflow has both crons, `MODEL_JOB_SCRATCH_DB: 'true'`, `contents: read`, and no `${{ secrets.DB_PASSWORD }}`. If PyYAML is missing from `requirements/development.txt`, parse the crons with a regex instead and note it as a ruling.
- [ ] **Step 2: Run; expect failure.** `… test tests.test_model_job …` → ImportError.
- [ ] **Step 3: Implement** `model_job.py`, the command, the workflow and the README section.
- [ ] **Step 4: Run; expect pass**, then the whole backend suite: `… manage.py test tests apps --settings=geo_test_settings_flood --noinput` → all OK. Report the count.
- [ ] **Step 5: A local dry run against nothing.** With `MODEL_JOB_API_URL=http://127.0.0.1:9`, run `… manage.py run_model_job --hazard fire --dry-run --settings=geo_test_settings_flood`. Expected: it fails with the `RuntimeError` after its retries (use `tries` patched down through an env `MODEL_JOB_TRIES=1`, read by `fetch`'s default) and posts nothing.
- [ ] **Step 6: Leave uncommitted.**

---

### Task 7: Frontend — the Model updates card, readiness, copy

**Files:**
- Modify: `frontend/src/api/historyApi.js` (`forecastUpdates()` → GET `/api/history/forecast/updates/`)
- Create: `frontend/src/components/Forecast/ModelUpdates.jsx` + `modelUpdates.test.js`
- Modify: `frontend/src/pages/PredictiveModels.jsx` (a third db-card, `ModelUpdates`, after `FloodReadiness`, before `ForecastAccuracy`) + `predictiveModels.test.js`
- Modify: `frontend/src/components/Forecast/FloodReadiness.jsx` (the spots line; the training line by source) + `floodReadiness.test.js`
- Modify: `frontend/src/components/Forecast/forecastLevels.js` (`FORECAST_DISCLAIMER` phrase) + its test
- Modify: `frontend/src/pages/PublicMap.jsx` (line ~739: copy `note`) and `frontend/src/utils/spotText.js` (`describeFloodAtSpot`) + `spotText.test.js`
- Modify: `frontend/src/components/Forecast/ForecastAccuracy.jsx` (`FloodModelReport` for `source === 'geoalert'`) + `forecastAccuracy.test.js`

**Interfaces:**
- Consumes: `GET /api/history/forecast/updates/` → `{updates: [{hazard, result, reason, version, created_at, is_live}]}` (Task 5); readiness `own_spots` and `flood_map.source`/`own_spots` (Tasks 2 and 5); purok rows `note` (Task 2); own-report keys `source`, `own_spots`, `temporal_test.season`, `temporal_test.held_back` (Task 4).
- Produces: `ModelUpdates` (default export, self-fetching, no props).

- [ ] **Step 1: Write the failing tests** (createRoot + act, as in `floodReadiness.test.js`):
  - `modelUpdates.test.js`:
    - **renders each attempt:** title and subtitle verbatim; one row per update, showing `Fire`/`Flood`, the date as `2 Feb 2027` (`toLocaleDateString('en-GB', {day: 'numeric', month: 'short', year: 'numeric'})`), the result label and the reason;
    - **live row:** it shows `Switched (in use)`;
    - **empty:** the empty line;
    - **loading:** the loading line;
    - **error:** the error line.
  - `predictiveModels.test.js`:
    - **card order:** the card titles in order are `Flood data readiness`, `Model updates`, `Model accuracy`;
    - **a failed updates request leaves the other cards working.**
  - `floodReadiness.test.js`:
    - **spots line:** `Located flood spots with a map point: 7 of 100, in 3 of 5 barangays.`;
    - **own-data training line:** with `flood_map.source === 'geoalert'` and `own_spots: 120`, the line is `The flood map comes from GeoAlert's located flood records (120 flood spots). Built 2027-01-05.`;
    - **survey line unchanged:** the survey line stays as it is today.
  - **Disclaimer:** `FORECAST_DISCLAIMER` contains `from UP NOAH's flood maps and recorded floods` and not `Mananga`.
  - `spotText.test.js`, `describeFloodAtSpot` with `note`:
    - with a note: `Flood: <FLOOD_AT_SPOT[level]> (Purok 1). From UP NOAH's map; outside the area GeoAlert's records cover.`;
    - without a note: unchanged.
  - `forecastAccuracy.test.js`, a geoalert report:
    - **caption:** `The 2026 wet season's flood spots, held back`;
    - **rows:** one row per `held_back` entry (day, barangay, level);
    - **no survey wording:** no `Mananga` and no `survey` text anywhere in the flood section.
- [ ] **Step 2: Run; expect failure.** `CI=true npm test -- --watchAll=false src/components/Forecast src/pages/predictiveModels.test.js src/utils/spotText.test.js` → failures.
- [ ] **Step 3: Implement.** In `FloodModelReport`, wherever the card names the survey (its spot count, its "trained on" wording, the Mananga points table), a geoalert report names GeoAlert's located flood records, `own_spots`, and the held-back table instead.
- [ ] **Step 4: Run; expect pass**, then the full frontend suite: `CI=true npm test -- --watchAll=false` → all pass (report the count). Then `npm run build` → "Compiled successfully".
- [ ] **Step 5: Leave uncommitted.**

---

## After the last task (not part of the build; each needs the user's yes)

Go-live follows spec section 10:
1. Back up, then apply history `0011`, then `0012`.
2. The user sets `MODEL_JOB_TOKEN` on Render and the two GitHub secrets, commits and pushes to `main`.
3. "Run now" with `dry_run`, then one real fire run, checked together.
