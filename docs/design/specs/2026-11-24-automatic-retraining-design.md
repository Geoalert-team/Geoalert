# Automatic retraining of the fire and flood models: design

Date: 2026-11-24. Status: draft, waiting for the user's approval.

Resumes the brainstorm paused on 2026-11-16 ("auto model switch"). Builds on
the fire purok model (docs/design/specs/2026-11-22-fire-purok-model-design.md),
the flood susceptibility model (docs/design/specs/2026-11-24-flood-susceptibility-model-design.md)
and the Predictive models tab (docs/design/specs/2026-11-24-predictive-models-tab-design.md).

## 1. Intent

The user wants GeoAlert to get better on its own as it is used ("plan for
growth", 2026-11-16).

- **Fire** retrains on its own as new fires are recorded.
- **Flood** retrains on its own too. Once GeoAlert has enough located flood
  records of its own, it stops learning from outside flood records (the 2017
  UP Mananga survey) and learns from ours.

Today both models are trained by hand on a developer machine
(`train_fire_model`, `train_flood_model`), written to JSON files in
`backend/apps/history/data/`, committed and deployed. Nothing retrains or
switches on its own.

## 2. Decisions the user made

| Question | Answer (2026-11-16 and 2026-11-24) |
|---|---|
| Who switches the model | The system switches by itself, logged and shown on the Predictive models tab. No person approves a switch. |
| Cost | Nothing to pay. GitHub is fine ("we don't want to pay anything, so GitHub repos and such will work", 2026-11-17). |
| What our own flood records replace | **The answers only.** GeoAlert's located flood records replace the survey's flood spots as what the model learns from. The land clues stay: ground height, distance to a river, and UP NOAH's flood map, which is kept only while the automatic test shows it helps. |
| How often | **Fire monthly, flood yearly.** Fire runs on the 2nd of each month. Flood runs once a year in January, after the wet season. |
| How a new model reaches the live site | **A: token handoff.** A GitHub Actions job fetches the training records from GeoAlert with a secret token, trains and tests, and sends the result back. GeoAlert stores every attempt in a database table and switches only on a pass. |

## 3. Goals, non-goals, anti-goals

**Goals**
- Fire retrains every month on all recorded fires, and the new fit goes live
  only if it does at least as well as the live one on months it never saw.
- Flood checks every January whether our own located flood spots are enough.
  When they are, it trains an own-data model, and that model goes live only if
  it passes the flood model's checks.
- Every attempt is saved, whatever its result, and shown on the Predictive
  models tab with its reason.
- It costs nothing, and the database password never leaves Render.

**Non-goals**
- No change to either model's recipe: the same candidates, choice rules and
  level cut-off rules. Only the data and the test window move.
- No flood *forecast* (predicting when a flood comes). The readiness panel
  keeps counting flood days for that; it is separate, later work.
- No landslide. It joins the same scheme once its rebuild is done.
- No email or push notice when a model switches. The tab shows it.
- No training on Render.

**Anti-goals** (failures even if it technically works)
- A switch to a model that did worse on unseen data.
- A record's location in a model file, a report, a job log or a public
  endpoint.
- A token or secret that can change anything beyond "fetch training records,
  send a fit".
- The flood map changing in the middle of a wet season.
- Any cost.
- The site breaking or going blank when the job fails or a fit is bad. The
  live model stays until a better one passes.

## 4. Constraints

- **Render free plan:** about a tenth of a CPU, 512 MB, a 120 s request
  limit, no worker, and a disk wiped on restart. It also sleeps when idle, so
  the first request can take about a minute.
- **GitHub Actions:** scheduled workflows run only from `main`, so the user
  pushes the workflow file. Runners are throw-away. Logs may be public (the
  repository's visibility is unknown here), so the job prints counts and
  scores only, never a coordinate. A private repository gets 2,000 free
  minutes a month. The dry run measures how long a fire run takes, and
  13 runs a year must fit well inside that allowance with no paid minutes.
- **Shared database:** the new table needs a migration. Like every
  shared-database step, it runs only after the user's explicit yes and a
  `pg_dump` backup to Downloads. History migration 0011 (the flood log) is
  still waiting for its own go-ahead, so this one comes after it.
- **Outside data stays private.** The Mananga survey, Annex 11 and the EOS-RS
  map stay in `backend/.hazard_cache`. They never go to GitHub, and the job
  never uses the survey.
- **Model files** never hold a record coordinate or a domain outline. A
  rounded outline once let a reviewer recover flood spots to within 5-10 m.
- **History is not prediction.** History levels are not touched.
- **Nothing is committed by Claude.** The user commits and pushes.

## 5. Approaches considered

- **A. Token handoff (chosen).** GitHub fetches records from GeoAlert with a
  token, trains, and posts the fit back. GeoAlert stores every attempt and
  switches on a pass. Fully automatic, and the database password stays on
  Render. It is the most to build: two token endpoints, a table, a migration,
  and one secret on Render and GitHub.
- **B. Pull request.** GitHub opens a pull request with the new model files
  and a person merges it. Not automatic (12 merges a year for fire), and it
  still needs a way to get the records to GitHub.
- **C. Direct database.** GitHub holds the database password and reads and
  writes directly. Least code, but a leaked secret would expose the whole
  shared database. The rain-forecast job deliberately avoided this.
- **Train on Render** was ruled out by the limits in section 4.

## 6. How it works

### 6.1 The flow

```
GitHub Actions (fire: 2nd of each month · flood: every January · "Run now" button)
  1. GET  training data           (bearer token)  <- GeoAlert
  2. rebuild nothing secret; download public land data if needed (cached)
  3. train with the existing recipe, test on held-back data
  4. POST the fit + its test result (bearer token) -> GeoAlert
GeoAlert
  5. checks the fit (shape, purok map version) and saves the attempt
  6. passed -> it becomes the live fit;  not passed -> the live one stays
  7. the site reads the live fit; the Predictive models tab lists the attempt
```

The schedule (Manila, UTC+8): fire at 03:17 on the 2nd of each month, cron
`17 19 1 * *` UTC; flood at 03:17 on 5 January, cron `17 19 4 1 *` UTC.
Changed in the final review: GitHub may drop :00 runs.

If a run fails partway (a download is down, GeoAlert is asleep too long), the
job posts a "Failed" attempt with its reason when it can. It tries again at
the next scheduled run. Anyone with access can press "Run now"
(workflow_dispatch) in GitHub.

### 6.2 Fire, every month (on the 2nd, Manila time)

- **Data:** every fire record (date in Manila time, purok ids, barangay,
  record id) and the purok map's version. No coordinates. The purok features
  come from the committed `fire_purok_features.csv`.
- **Purok map changed:** if the features file's map version differs from
  GeoAlert's current one, the run stops and saves "Skipped: the purok map
  changed; rebuild the fire features by hand". Purok reloads are rare, and
  rebuilding features needs large downloads.
- **Moving test window.** The hand-run command fixes the test to 2026. An
  automatic run instead holds back the **newest 12 full months** and develops
  on everything before them, keeping the existing leave-one-year-out steps,
  with years counted back from the window. The deployed fit is then refitted
  on every full month, exactly as the hand run does.
- **When it switches:** the job refits the live model's family and settings
  the same way (trained without the window) and scores both on the window by
  log loss, the score fire's choice rule already uses.
  - The new fit goes live if its log loss is **no higher** than the live
    settings' log loss.
  - If both use the same family and settings, their window scores are equal,
    and the new fit goes live: it is the same recipe trained on more fires.
  - The new fit must also beat "same chance everywhere" on the window (the
    comparison the report already scores). If not, the run saves "Kept
    current: no better than the same chance everywhere".
- Fires that name no purok are still left out and listed, never guessed (the
  user's 2026-11-22 choice).

### 6.3 Flood, every January

**Step 1: are our own records enough to try?**
- **Spots** are located flood records with a map point, plus "Affected here"
  field marks on flood zones. Records linked to a purok but with no point
  count in the readiness panel's flood days, but not as training spots: a
  purok is too coarse for a point model.
- **Floor to try:** at least **100 spots in at least 5 barangays**. That is
  about the survey's 105 spots, but spread across the city. Below the floor,
  the run saves "Not tried: N of 100 spots, B of 5 barangays", and the current
  map stays exactly as it is. Retraining on the survey would give the same
  answer, because the survey never changes.

**Step 2: train and test the own-data model**
- **Training spots** are our spots from before the newest wet season.
- **Held-back test:** the newest wet season's spots (1 June to 31 December
  of last year). The run needs at least **10** of them. Fewer saves "Not
  tried: too few new spots to test; tries again next January".
- **Clues:** ground height, distance to a river and UP NOAH's map, sampled
  from the same public sources `build_flood_features` downloads (Copernicus
  DEM, OpenStreetMap, UP NOAH on Hugging Face, Microsoft buildings). These are
  cached between runs in GitHub's cache.
- **Background** is the buildings inside the domain, the same as the survey
  model.
- **Domain:** our spots' convex hull, buffered 300 m and clipped to the city.
  It is never written out.
- Same candidates (logistic regression, MaxEnt, XGBoost, neural network),
  same choice rule, same Red and Orange cut-off walk.

**Step 3: the checks it must pass to go live.** These are the same four
checks the survey model faces, with the test points swapped for the
held-back season:
1. Better than UP NOAH's map on its own: the lower end of the AUC gain's 95%
   interval is above zero (judged on AUC, as the user approved).
2. The held-back season's spots are in Red or Orange: at least
   `test_hits_needed(n)` of them, the existing rule (3 of 4, else 75%
   rounded up).
3. Red and Orange cover at most half the buildings in the domain.
4. Test data is seen last: the choice and cut-offs are fixed before any
   held-back spot is loaded.

The Tino satellite map test stays as a shown-only check when its download
works. It is never a gate.

**Later Januaries,** once an own-data model is live: the new fit must pass
the four checks **and** put at least as many of the newest season's spots in
Red or Orange as the live one did. That comparison is fair: last January's
live model never saw this season either.

**Outside the domain** (my call; see section 9): puroks keep their current
NOAH-based level, marked "From UP NOAH's map; outside the area GeoAlert's
records cover". No purok loses its level because our records don't reach it
yet.

### 6.4 What GeoAlert stores and serves

- **A new table** (history migration 0012) holds one row per attempt: hazard,
  version, the time the attempt was made, the result (Switched, Kept
  current, Not tried, Skipped, Failed), the reason sentence, the purok map
  version, the model JSON and report JSON (empty when not trained), and
  whether it is the live fit. At most one live fit per hazard.
- **Which model the site uses:** the newer, by `built_at`, of the table's
  live fit and the committed file, provided its purok map version is current.
  A developer's hand retrain, committed and deployed, still takes over
  naturally. Rechecked at most every 60 s, as the files are today.
- **Undo:** an admin can mark an earlier fit as live in Django admin (my
  call).
- **Endpoints:**
  - `GET` training data for one hazard (token only). Fire: dates, purok ids,
    barangays, record ids. Flood: spot points, dates, barangays, plus the
    purok and barangay outlines the job needs to place points. Never cached,
    never public.
  - `POST` an attempt (token only). GeoAlert checks the shape and the purok
    map version, saves the attempt, and makes it live only if its result is
    a pass.
  - `GET` the attempt list (public, cached, no model bodies, no locations),
    for the tab.
- **The token** is one secret, set on Render and in GitHub. It allows only
  these two token endpoints, using the same bearer check the rain-forecast
  job used. With no token set, both endpoints refuse everything.
- **The prediction log** keys rows by model version, so a switch starts new
  log rows on the next log run. The log run itself stays as it is today:
  manual, on one machine (`HAZARD_LOG_WRITER`).

### 6.5 What officers see (Predictive models tab)

A new **Model updates** card, below Flood data readiness:

```
Model updates
  Fire    2 Feb 2027   Switched        Scored 0.0401 vs 0.0408 on Feb 2026 to Jan 2027
  Fire    2 Jan 2027   Kept current    The new fit scored worse (0.0412 vs 0.0405)
  Flood   5 Jan 2027   Not tried       38 of 100 located flood spots, 4 of 5 barangays
  Fire    2 Dec 2026   Skipped         The purok map changed; rebuild the fire features by hand
```

The Flood data readiness card gains one line: "Located flood spots with a
map point: N of 100, in B of 5 barangays", using the same count as step 1.
The Model accuracy card shows whichever fit is live.

Every sentence that names the 2017 Mananga survey as the flood map's source
switches to naming GeoAlert's located flood records while an own-data fit is
live. That covers the forecast disclaimer, the readiness card's "trained on"
line, the accuracy card and the survey credit. Each follows the live fit
rather than being hard-coded.

## 7. How the job runs the training (left to the plan, with my lean)

The job must produce exactly what the hand-run command would produce for the
same records and date. Two ways:
- **(lean)** Start a throw-away PostGIS service container in the job, load
  the fetched records and outlines into it, and run the existing commands
  with new flags (fire: moving window; flood: own data). The training code
  keeps one path.
- Change the training code to accept records passed in, without a database.

## 8. Testing

- The usual backend and frontend suites on private test databases, with
  unique names.
- Moving window: a fixed set of fires gives the expected development and
  test months for a given run date.
- Switch rules: a worse fit is kept out; same settings switch; "same chance
  everywhere" blocks a fit that doesn't beat it; a flood fit that fails any
  check is not live; a later-January fit with fewer season hits is not live.
- The flood floor and the held-back season's minimum, at and around their
  numbers.
- Endpoints: no token, a wrong token or an empty server setting all refuse.
  A stale purok map version is refused. The public list has no coordinates
  (the same "no POINT, no 4-decimal coordinate" check as the readiness
  endpoint) and no model bodies.
- Which model the site uses: table versus file by `built_at`, a stale map
  version ignored, and an undo honoured.
- A dry-run mode for the job (posts nothing) and one real run, done by hand
  with the user, before the schedule is trusted.

## 9. Calls I made (for the user to check)

1. Flood floor: **100 spots in 5 barangays**; the held-back season needs
   **10** spots.
2. Purok-only flood records count as readiness days but **not** as training
   spots.
3. Outside our records' area, puroks **keep their NOAH-based level**
   (labelled) rather than becoming "not assessed".
4. Fire stops and logs when the purok map changed, rather than rebuilding
   features in the job.
5. The newer of the table fit and the committed file wins, so a hand retrain
   still works.
6. An admin can undo a switch in Django admin. No email or push notice.
7. The attempt list is public (counts and scores only), like the readiness
   endpoint.

## 10. Go-live order (each shared step needs the user's yes)

1. The user approves this design; I write the plan; the build runs on the
   local branch, uncommitted.
2. Backup, then history 0011 (pending from the flood work), then 0012.
3. The user sets the token on Render and in GitHub, commits, and pushes to
   `main`.
4. A dry run from GitHub ("Run now", dry run), then one real fire run,
   checked together.
5. The schedule takes over.
