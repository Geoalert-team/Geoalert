# Landslide susceptibility model: handoff (paused 2026-11-24 ~21:30, again 2026-11-24 late, and again 2026-11-25 ~00:20 Manila)

Uncommitted, per the user's standing rule: **never `git commit`** (the user commits and pushes).

## What this is

The user asked for a landslide predictive model built like the flood one: predictive analytics only (History untouched), no counting, neural networks much preferred, and a yearly January retrain that switches to GeoAlert's own landslide records automatically once there are enough, with no human involved.

- **Design (APPROVED 2026-11-24):** `docs/design/specs/2026-11-24-landslide-susceptibility-model-design.md`
- **Plan (APPROVED, 14 tasks):** `docs/design/plans/2026-11-24-landslide-susceptibility-model.md`
- **Execution:** subagent-driven (the user's choice), with independent tasks run in parallel (the user's standing preference).
- **Ledger (source of truth, rulings R1-R7, pre-flight table):** `.superpowers/sdd/2026-11-24-landslide-susceptibility-model/progress.md`
- **Constraints file given to every implementer and reviewer:** `.superpowers/sdd/2026-11-24-landslide-susceptibility-model/constraints.md`
- **Snapshots (no commits):** `.superpowers/sdd/2026-11-24-landslide-susceptibility-model/snap.sh` prints a git tree id of the working tree; `snap.sh pkg BASE HEAD OUT [paths]` writes a review package. Base T0 = `ee9d9bbaed11630973bbf92dc12de1a9d20e7778` (HEAD 741c437).

## Where it stands

**2026-11-25 06:37-06:38 Manila: STOPPED by the 5-hour usage limit (resets 10:50 Manila), then the session lost its login; every agent and both background runs are dead. Read the ledger's last section, "STOPPED 2026-11-25 06:37-06:38", and its RESUME steps: they are the current state.**

**Earlier, 2026-11-25 ~06:30 Manila: a newer session resumed and moved on (Tasks 6 and 11 complete; 4, 7, 8 in fix rounds or build; a pre-warm tile run started; rulings R21-R30). The ledger's sections from "RESUMED 2026-11-25 (new session)" on are the current state; the table below is older.** The user said (2026-11-25): never stop, no questions until finished; only Task 14's shared-DB steps 1, 6, 7 (and the GitHub dry run) wait for them (ruling in the ledger).

**Updated 2026-11-25 ~00:25 Manila.** If the ledger is newer than this table, trust the ledger. Read its section "PAUSED 2026-11-25".

The code under `backend/` is exactly as in tree `f13fca183ba7d9c36e7c5f68ad28a3207cd71387`, Task 5's final head. That was checked with `snap.sh` on 2026-11-25 00:23, and again after this doc was edited. The two agents stopped at this pause left no partial edits.

| Task | State |
|---|---|
| 2: clue functions (`landslide_features.py`) | **Complete, reviewed** (tree d3bf55a; 5 minors deferred) |
| 1: inventory readers | **Complete, reviewed** (tree 9e42477; COOLR 23 events = 3 PH + 20 world (R10), Mangkhut 1,100 polygons (R11); 7 minors deferred) |
| 3: sources (land cover, NOAH, roads, `dem_for`) | **Complete, reviewed** (tree d084fd1, after 1 fix round). The NOAH class field is `LH` or `HAZ` (R15). Land cover's newest year is 2023 (R14) |
| 5: Talisay grids and scoring points (`landslide_features.py` additions, `build_landslide_features` command) | **Complete, reviewed** (tree f13fca1). The command body never ran: it reads the shared DB, so its first run is Task 14 step 3 (R17) |
| 6: training core (`landslide_training.py`) | Review said **Needs fixes**. Fix round 1 was **stopped before it wrote anything**: the files are still at tree ae0b2fc. Open: I6.1 (fix by R19: drop the road clue in a fit with no road distances) and I6.2 (fix by R18: honest flat-ground fixtures plus a test that a flat purok is greyed when training has no flat ground) |
| 4: training table (`landslide_training_table.py`, its command, tests, attribution) | Implementer **stopped before writing any file**. Re-dispatch from scratch with the brief, R1, R6, R10, R15, R17 and **R20** (no NaN terrain in the table) |
| 11 | Not dispatched; waits for Task 6 complete (R16). Brief already extracted |
| 7-10, 12-14 | Not started |

Test command (PowerShell, from `backend/`): `$env:PYTHONPATH = 'C:/Users/Sannichigetsu/.geoalert-test'; venv\Scripts\python.exe manage.py test <labels> --settings=<file> --noinput`. Git Bash splits the `C:` in `PYTHONPATH`.

Stopped agents keep their transcripts: a later session cannot message this session's agents, so it re-dispatches with the brief, the report file and the open findings (the report file is the memory).

Order (ruling R3): {1, 2, 3, 6} → {4, 5, 11} → 7 → 8 → {9, 12, 13} → 10 → 14.

Private test settings already exist in `C:\Users\Sannichigetsu\.geoalert-test\`: `geo_test_settings_landslide`, `_b`, `_c`, `_d` (one per parallel task). Task 1 used the plain one, 2 `_b`, 3 `_c`, 6 `_d`; then 4 the plain one, 5 `_b`. Task 11 is to use `_c`.

## Facts the next session should not redo

- **Data:**
  - The shared DB holds 10 landslide records. Two are the Purok Kaimito test entries of 2026-11-17; the user chose to delete them in Task 14 step 1, after a backup and a go-ahead.
  - The 8 real records are 7 in Manipis and 1 in Camp IV. Two have points, in Camp 5 and Camp 6.
- **NASA COOLR new events** (Figshare file 54363830, CC BY 4.0): 15,274 points from 22 storms. The Philippine ones are Egay (3,183), Paeng (213) and Agaton (23). Pinned in the plan.
  - Keyed the brief's way, by (country, date), that makes 23 events: 3 Philippine and 20 world, because Cyclone Freddy counts once for Malawi and once for Mozambique (R10). Add Mangkhut and Task 14 step 2 expects 4 Philippine + 20 world.
- **Mangkhut, Itogon** (EIDC, Open Government Licence): 1,101 polygons. The zip wrapper may change, so its inner shp, dbf and shx are pinned.
- **UP NOAH landslide maps:** one zip per province on the bettergovph Hugging Face mirror (`HAZ` 1-3). Cebu's is 224 MB.
- **Esri annual land cover:** public blob `lulctimeseriesv003/lc{year}/{tile}_…`, which answers HTTP 200 with no account.
- **Local venv vs CI:** the local venv is Django 4.2.13, while requirements and CI are Django 5.2.19 (the user's commit 1fe5345). Code must run on both (ruling R7). Do not reinstall the venv without asking.

## Not yet verified

None of these is a gap now. Each has a planned first check.
- **Task 5's `build_landslide_features` command body** has never run, because it reads the shared DB (R17). Its first run is Task 14 step 3, asked first.
- **Eight of the nine NOAH province zips** have never been read. Only SouthernLeyte has: class field `LH`, EPSG 4326. The other eight are first read in Task 14 step 2, where a missing `LH`/`HAZ` field fails loudly (R15).
- **Flat or coastal puroks going grey** (out of range, R18): read the train command's in-range share before go-live. If many go grey, stop and ask the user.
- **RED evidence** is missing for Tasks 1 and 3's original work (stopped runs; minors M1.7, M3.9).

## Resume steps

(An earlier version of these steps said to re-dispatch Tasks 1, 3 and 6. That was the 2026-11-24 state. Tasks 1 and 3 are now complete, so don't redo them.)

1. Read the ledger (all of it) and the subagent-driven-development skill. If `superpowers:subagent-driven-development` won't load by name, read its SKILL.md from the plugin folder `~/.claude/plugins/synced/…/skills/subagent-driven-development/`.
2. Check that no code moved since the pause. Run `T=$(bash .superpowers/sdd/2026-11-24-landslide-susceptibility-model/snap.sh); git diff --stat f13fca183ba7d9c36e7c5f68ad28a3207cd71387 $T -- backend`. It should print nothing.
   - The whole-tree id is not f13fca1 any more, because the edits to this doc changed it. Only `backend/` is the check.
   - If it prints changes, read them and log them in the ledger before dispatching. The user may have committed or edited files; the ledger's tree ids still work as bases.
3. Dispatch these two in parallel. Their files are disjoint.
   - **Task 4 (fresh implementer):** opus, settings `geo_test_settings_landslide`, brief `task-4-brief.md`, base d084fd1. Give it rulings R1, R6, R10, R15 and R17 from the ledger, and R20. R17 means a network-only Agaton trial and no shared-DB read. R20 means `write_table` refuses NaN terrain, and the command drops those rows and prints the count per event.
   - **Task 6 fix round 1 (fresh implementer):** opus, settings `_d`. Give it `task-6-brief.md`, `task-6-report.md`, findings I6.1 and I6.2, and rulings R18 and R19 verbatim from the ledger. Tell it the stopped round left no edits.
4. Review as they report.
   - Task 4 gets a full review: package from base d084fd1, limited to its paths.
   - Task 6 gets a scoped re-review: FIX_BASE ae0b2fc, its two files only.
   - Then dispatch Task 11 (sonnet, `_c`, `task-11-brief.md`).
   - After Task 11's review, run the whole backend suite once (R9). Log every result in the ledger.
5. Continue in the R3 order: 7 → 8 → {9, 12, 13} → 10 → 14.
   - Task 7 should use Task 6's public helpers `medians_for` and `clip_ranges`.
   - Task 7 must cast `purok_scores`' `total` to int (deferred minor M6.5).
6. Ask the user before every Task 14 step that touches the shared database:
   - deleting the test records;
   - migrating history 0013/0014;
   - the first log run;
   - the GitHub dry run.
