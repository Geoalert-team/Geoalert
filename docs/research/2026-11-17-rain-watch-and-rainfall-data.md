# Rain watch and better rainfall data for flood and landslide

*Written 2026-11-17. Nothing in this document has been built yet; it records an investigation, the
recommendations, and what the user decided, so the next session can continue without redoing them.*

---

## 0. For the next session: read this first

**Where things stand**
- The user asked for an analysis-only investigation ("why are flood and landslide always green, and
  how do we improve the rain data?"). That analysis is complete, and its results are in this document.
- The user then said **"ok start with it"**. Brainstorming (the `superpowers:brainstorming` skill) had
  just started when the session ran out. No approaches had been laid out yet. No design doc and no
  plan have been written.
- The next step is to resume brainstorming at section 12 ("Where to resume").

**Rules that still apply**
- **Never commit or push.** Leave every file uncommitted.
- **Nothing is built until the user approves a design.** The order is: approaches, then a design doc,
  then approval, then a plan (`superpowers:writing-plans`).
- **Zero cost.** The user said: "we don't want to pay anything though, so GitHub repos and such will
  work."
- **Do not use Open-Meteo** unless the user brings it back up. They ruled it out on 2026-11-13: its
  free tier is non-commercial only.
- **Ask design questions with the AskUserQuestion tool**, one at a time, with previews where it
  helps. If the user answers "expound", explain again in plain words using a real example from
  their data.
- **The shared Supabase database:** back it up before any migration, and only migrate with the
  user's go-ahead.

---

## 1. The plain-language summary

- **Why the map is always green:** the flood and landslide colours come from what *usually* happens
  in a month, averaged over 19 past years of rain, compared with cut-offs that were made for fire.
  The actual weather this week never changes the colour. It isn't mainly a "too little data"
  problem.
- **About "fewer than 50 records":** this is the number of flood and landslide *incidents*, not
  rain. We already have 20 years of daily rain, and we can get 40+ years for free today. What we
  are short of is recorded floods and landslides: 5 flood days and 8 landslide days.
- **The fix:** add a new **"Rain watch: next 3 days"** map layer, separate from the monthly outlook,
  which stays as it is.
  - It reads a free rain **forecast** from the big weather agencies. GeoAlert does not predict rain
    itself.
  - It checks how wet the last two weeks were (soil acts like a sponge) and how risky each place is
    (low land near rivers floods; steep slopes slide).
  - It then gives each barangay a colour: 🟢 Green, 🟡 Yellow, 🟠 Orange or 🔴 Red.
  - It is never calmer than PAGASA's own warning.
- **Later, once a year:** the system tests on its own whether there are now enough recorded
  incidents to train a smarter method. If one is clearly better, the admin is notified with a plain
  report and decides. It never switches by itself.
- **Cost:** all free. Forecasts are free, GitHub runs the automatic jobs, and the existing free
  Supabase, Render and Vercel plans stay.

---

## 2. How the flood and landslide forecast works today

| Step | Code | What happens |
|---|---|---|
| Rain | `backend/apps/history/rain.py` | NASA POWER `PRECTOTCORR`, the corrected daily rain from the MERRA-2 reanalysis plus GEOS-IT for recent days. It arrives about 2–3 days late. **One grid cell for the whole city:** 10.5 N, 123.75 E, 0.5° × 0.625°, about 55 × 69 km. The cell edge at 10.25 N runs through Talisay. `manage.py fetch_rain` writes `data/rain_daily.csv` (2006-12-18 to 2026-11-12, 7,270 days). `recent_rain()` fetches the days after the file live, cached for 3 h. |
| Inputs | `hazard_data.py` (`rain_windows`, `build_dataset`) | Rain totals over the day and the last 1, 3, 7 and 14 days (`r0, r1, r3, r7, r14`). Each barangay also has terrain shares. Flood: HAND under 2 m and under 5 m, elevation under 10 m, water within 200 m, coast within 500 m, building density. Landslide: slope over 18° and over 30°, relief, road within 50 m, stream within 150 m. |
| Model | `hazard_models.py`, `hazard_scoring.py`, `data/hazard_model_report.json` | An L2 logistic regression is fitted offline (`manage.py test_hazard_models`), saved as numbers, and scored on the site with NumPy. It predicts "a *reported* event in barangay b on day d", over 2021–2025 (40,172 rows). Flood: 18 positive barangay-days on **5 days**. Landslide: 8 on **8 days**. The Firth "two-part" model was tested on 2026-11-16 and **not adopted** for either hazard. |
| Day → month | `hazard_scenarios.py` | The month's days are replayed over every complete past rain year (2007–2025). The month chance is 1 − ∏(1 − p) per year, **averaged over the 19 years**. |
| Level | `hazard_forecast.py` (`_set_model`, about line 457); `model_forecast.py:64` and `level_for` at about line 105 | High if the month chance is 25% or more, Moderate if 15% or more, otherwise Low. These are **fire's** cut-offs, used for every hazard. |
| Colours | `frontend/src/components/Forecast/forecastLevels.js:10` | High red, Moderate amber, Low green, None grey. There is no orange step on this map; Green/Orange/Red only exist on alerts DRRMO issues by hand. |
| Map period | `forecastLevels.js:186` (`defaultPeriod`); `views.py` about line 428 | The map defaults to **next month with no year**, which means the pure 19-year average. Rain already recorded only appears as the "With rain so far" line (`BarangayLikelihood.jsx:206`) and **never sets the colour**. |
| All hazards | `hazard_forecast.combine` | The combined chance 1 − ∏(1 − p) including fire. Fire's monthly 10–36% dominates, so the map colours are mostly fire's. |
| Prediction log | `prediction_log.py`, migration 0008 | Insert-only log of the chances shown. It only writes on the machine with `HAZARD_LOG_WRITER=true`. That setting is **missing from `deploy/render.env.example`**, so check that Render has it set. |

Data scaling (log1p, scaling, filling missing values) is fine and is not a cause.

---

## 3. Why it is always green: the evidence

All numbers below were recomputed read-only from the saved fits and `rain_daily.csv` on 2026-11-17.

1. **The colour reads a 19-year average, not the weather.** The default view is next month with no
   year, and the level comes from the average over past years.
2. **The cut-offs cannot be reached.**
   - The highest month chance any barangay can get is **4.4% for flood** (Bulacao and Tabunok,
     October) and **9.7% for landslide** (Camp IV, October).
   - So **0 of 264 barangay-months can ever be Moderate (15%)**.
   - Even using each year's own rain instead of the average, only 23 of 5,016 (flood) and 6 of
     5,016 (landslide) barangay-months reach 15%, and none reach 25%.
3. **The target is rare by design.** "Reported, in one barangay, on one day" happens on 0.045%
   (flood) and 0.02% (landslide) of barangay-days. Heavy-rain days with no report count as "no
   event", so the chances read low.
4. **The rain source flattens storms.**
   - Typhoon Tino: POWER recorded **64.19 mm on 3 Nov and 31.43 mm on 4 Nov 2025**. PAGASA's
     Mactan station measured **183 mm in 24 h**, and Bagakay in Toledo 428 mm.
   - In POWER, **all 13 event days had under 50 mm** on the day. The 2023-06-26 landslide day had
     0.42 mm, and the 2025-10-07 flash flood 9.35 mm.
   - Since 2006, POWER has only **2 days of 100 mm or more** and 39 days of 50 mm or more.
   - So PAGASA's 50/100/200 mm bands can never fire on POWER data.
5. **No forecast and a 2–3-day lag.** Forecast rain was deliberately left out ("Mode B" in the
   2026-11-12 spec), so the system can never warn ahead.
6. **Too few incidents.** There are 11 flood inputs on 5 event days, and the coefficients flip sign
   (`r3` and `r7` are negative). With 5 days, the best possible two-sided sign test is p = 0.0625.
   This limits proof, not the colour.
7. **Tino day itself:** the in-sample flood chance was 6.4% for the worst barangay (Bulacao). Out of
   sample, the barangay that actually flooded got 0.43%.

**Rain on the 13 recorded event days**

The 3-day and 14-day columns show the NASA POWER totals and their percentile among all days,
2006–2026.

| Hazard | Day | 1-day mm | 3-day mm (percentile) | 14-day mm (percentile) |
|---|---|---|---|---|
| Flood | 2021-06-12 | 19.99 | 39 (88th) | 216 (98th) |
| Flood | 2025-08-12 | 17.81 | 30 (81st) | 69 (44th) |
| Flood | 2025-08-18 | 14.06 | 27 (78th) | 144 (87th) |
| Flood | 2025-10-07 | 9.35 | 18 (64th) | 192 (96th) |
| Flood | 2025-11-04 (Tino) | 31.43 | 101 (99th) | 210 (98th) |
| Landslide | 2021-11-04 | 12.5 | 32 (83rd) | 137 (85th) |
| Landslide | 2022-04-08 | 30.31 | 98 (99th) | 178 (94th) |
| Landslide | 2022-07-13 | 10.82 | 18 (63rd) | 90 (60th) |
| Landslide | 2023-06-26 | 0.42 | 14 (55th) | 126 (80th) |
| Landslide | 2024-10-01 | 9.19 | 9 (44th) | 57 (36th) |
| Landslide | 2025-08-25 | 24.98 | 37 (87th) | 170 (92nd) |
| Landslide | 2025-11-04 (Tino) | 31.43 | 101 (99th) | 210 (98th) |
| Landslide | 2025-12-12 | 9.44 | 13 (53rd) | 136 (85th) |

**What this shows:** the last 14 days were usually very wet before an event (soaked ground). That
supports using "wet ground" as one input of the Rain watch.

**Percentiles of POWER rain (all days, 2006–2026)**

| Percentile | 3-day | 14-day |
|---|---|---|
| 85th | 34 mm | 138 mm |
| 90th | 42 mm | 156 mm |
| 95th | 54 mm | 185 mm |
| 98th | 74 mm | 213 mm |

---

## 4. Rain data sources (all free)

| Source | Rain so far | Forecast | History | Grid | Access | Verdict |
|---|---|---|---|---|---|---|
| **NASA POWER** (current) | Daily, 2–3 days late | — | 1981– | ~55 km | JSON, no key, CC BY 4.0 | **Keep** for history and the monthly outlook |
| **NASA GPM IMERG** | Early run 4 h late, Late run 12–14 h, half-hourly | — | 1998– | 0.1° (~11 km) | Free Earthdata account | Optional, for the latest days POWER hasn't filled. It showed Tino at about 246 mm over 2 days in the 2026-11-13 test, but it was worse as model training data there |
| **ECMWF Open Data** (IFS/AIFS) | — | 15 days. IFS 00/12z: 0–144 h by 3 h, then to 360 h by 6 h. 06/18z: 0–144 h. AIFS: 0–360 h by 6 h. Total precipitation `tp` included. Ensemble rain probabilities: ≥ 1/5/10/20 mm confirmed, 25/50 mm likely | Only the last 12 runs (2–3 days) | 0.25°, and **0.1° since 2026-10-20** | GRIB2, CC BY 4.0, free | **Main forecast** |
| **NOAA GFS** | — | 16 days; hourly to 120 h, then every 3 h to 384 h | About 4 weeks on AWS | 0.25° | GRIB2; the NOMADS grib filter cuts out a tiny box on the server | **Fallback / second opinion** |
| **dynamical.org GFS archive** | — | Past GFS forecasts *as they were issued* | **2021-05-01 to now** | 0.25° | Zarr/Icechunk, anonymous, CC BY 4.0 | **For the backtest** (section 10) |
| **dynamical.org / Source Cooperative ECMWF IFS ENS archive** | — | Past ECMWF ensemble forecasts | GRIB 2016-03-08 to 2024-04-01 (still being filled in) | 0.25° | Anonymous, CC BY 4.0 | Optional second backtest |
| **PAGASA** | Mactan synoptic station; heavy rainfall warnings | Official warnings and advisories | Station daily data for decades | Points | No public API. Data costs about Php 360 per year per parameter (charter, may be out of date), so to stay free: **FOI request or university letter** | Official top layer, and ground truth |
| **DOST-ASTI PhilSensors** | Gauges every 10–15 min | — | Station history | Points | API for government and academe, on request | Request it. Whether a gauge exists near Talisay or the Mananga River is not confirmed |
| CHIRPS v3 / CHIRPS-GEFS | Days late | 16-day, matched to CHIRPS | 1981– | 0.05° | No account | Optional, 3–5-day totals only (its daily values are not independent) |
| MET Norway Locationforecast | — | About 9 days, ECMWF-based outside the Nordics | — | — | JSON, no key, needs an identifying User-Agent | Only if the licence for points outside the Nordics is confirmed (its docs are unclear) |
| Open-Meteo | — | — | — | — | Free tier non-commercial | **Excluded** (user decision) |
| JAXA GSMaP, paid APIs | — | — | — | — | Restrictive terms or cost | Not used |

**Decision: add sources, don't replace POWER.**
- POWER stays as the long, consistent record.
- ECMWF supplies the forward look, with GFS as fallback.
- PAGASA is the authority.
- Station data shows how far off each source is for Talisay.

**PAGASA's two warning scales** (both use yellow, orange and red; don't mix them up)
- *Heavy rainfall warning*, by rain in the last hour that is likely to continue for the next 2 h:
  Yellow 7.5–15 mm/h, Orange 15–30 mm/h, Red over 30 mm/h.
- *Weather advisory*, by expected 24-h total: Yellow 50–100 mm, Orange 100–200 mm, Red over 200 mm.

---

## 5. The proposal: "Rain watch, next 3 days"

### 5.1 What it does, step by step (runs on its own every 6 hours)

1. **Read the forecast:** how much rain is expected over Talisay in the next 24–72 h (ECMWF, with
   GFS as fallback).
2. **Read the rain so far:** the last 14 days (NASA POWER, plus IMERG or the forecast's first hours
   for the days POWER hasn't filled yet).
3. **Read the place:** flood exposure (UP NOAH shares, HAND, buildings, from
   `data/barangay_exposure.csv`) and slope (`data/barangay_terrain.csv`).
4. **Pick a colour** per barangay and per hazard, using the rules below.
5. **Save and show:** store the result in Supabase, and show it on the map as the "Next 3 days"
   layer.

### 5.2 The rules

The numbers here are **placeholders**. The backtest (section 10) and DRRMO will set the real ones.

| | Flood | Landslide |
|---|---|---|
| Main rain signal | **Next 24 h forecast** (heavy rain soon) | **3-day total**: last 2 days + next day (rain piling up) |
| Base colour | Under 50 mm Green · 50–100 Yellow · 100–200 Orange · over 200 Red (PAGASA advisory bands) | Above about the 95th percentile Yellow, about the 98th Orange, and higher Red (in the forecast's own units) |
| Wet ground | If the last 14 days are unusually wet (for example above the 90th percentile), **one step up** | Same |
| Which barangays can reach the top colours | Only those with real flood exposure; the others stay one step lower | Only the steep ones (Camp IV, Manipis, Tapul, Jaclupan); flat ones stay Green or Yellow |
| Safety floor | Never calmer than PAGASA's current warning for Cebu | Same |

**Important:** the forecast must not be fed into the current logistic regression. That model
learned on POWER's flattened rain scale, and ECMWF's storm totals are 2–3 times higher.

### 5.3 Worked example: Typhoon Tino, as seen on the morning of 3 November 2025

- **Rain so far (real figure):** the last 14 days had 210 mm in POWER, the 98th percentile. That
  counts as wet ground.
- **Forecast (made-up figure, until the backtest shows the real one):** about 150 mm in the next
  24 h.

| Barangay | Flood | Landslide |
|---|---|---|
| Bulacao, Tabunok (exposed lowland) | 150 mm → Orange; wet ground → **Red** | Flat → **Green** |
| Camp IV, Manipis (steep upland) | Little flood exposure → **Orange** | 11 mm + 150 mm = 161 mm over 3 days → Orange; wet ground → **Red** |
| A barangay with neither | **Yellow** | **Green** |

For comparison, the current system showed Low (green) everywhere for that month.

### 5.4 A rough test on POWER (in-sample, for intuition only; not proof)

The rule tested:
- **Red** if the 14-day total is at or above the 95th percentile **and** the 3-day total at or above
  the 98th.
- **Orange** if the 14-day total is at or above the 90th percentile **and** the 3-day total at or
  above the 95th.
- **Yellow** if the 14-day total is at or above the 85th percentile, **or** the 3-day total at or
  above the 95th.

What it gave on POWER, 2006–2026:
- About **51 yellow, 6.6 orange and 3.3 red days a year**.
- Tino → Red. 2022-04-08 landslide → Orange.
- Several other events → Yellow, and a few → Green.

**Lesson:** a rain-based layer does respond to real storms, but yellow would be too frequent at
these settings. The real thresholds need DRRMO's false-alarm tolerance.

### 5.5 Known limits

- Short, local downpours, such as **2025-08-18 Bulacao** (14 mm in POWER) and **2025-10-07**, are
  too small for any 0.1–0.25° forecast. Only rain gauges or radar catch them.
- Forecast rain also reads lower than gauges, so the bands may need lowering. That can be checked
  once logged forecasts can be compared with what actually fell.
- No rule can be proven on 5 or 8 event days.

### 5.6 The monthly outlook stays

The monthly outlook (the existing model) answers a different question: "which months and places
are usually riskiest?". The proposal is to **also** make its wording or levels honest. Options:
- per-hazard levels;
- relative levels, such as "2.3× Camp IV's usual chance";
- a clear "seasonal average" label.

This reopens the user's 2026-11-12 choice of one 15%/25% scale for every hazard.

---

## 6. Warnings and notifications (recommended; not yet confirmed by the user)

- **DRRMO is told; the public is not alerted automatically.** When the Rain watch turns orange or
  red for a barangay, DRRMO staff get a message, for example: *"Rain watch: Bulacao flood risk Red
  for tomorrow. Forecast 150 mm, ground already soaked."*
- **DRRMO decides** whether to send an official alert to residents, through GeoAlert's existing
  alert flow (Low / Moderate / Extreme, with its approval step and notifications).
- **The Rain watch colours stay visible** on the public map either way.
- **Why not alert residents automatically:** the rules are untested on Talisay's storms (false
  alarms make people ignore warnings), and official warnings belong to PAGASA and DRRMO.
- **Revisit later:** automatic public alerts could be reconsidered after about a full rainy season
  with a good track record.

---

## 7. The yearly self-test and admin approval

### 7.1 How it works

Every January, after the June–December rainy season:

1. **Count** the recorded flood days and landslide days. Every hazard DRRMO closes in the app adds a
   HistoricalRecord. If there aren't enough, stop: nothing changes.
2. **Train** the next method on the "upgrade ladder" (section 8), using our recorded incidents plus
   the rain data, and **test** it on past storms against the current rules.
3. **If it isn't clearly better** (the existing rules (a)/(b) in `hazard_verdict.py`), save the
   report quietly. Nothing changes.
4. **If it is better, notify the admin** in the GeoAlert dashboard with a plain report.
5. **Only after the admin clicks "Approve"** does the map use the new method. "Not now" keeps the
   old one. The admin can **undo** it later. Every decision is saved: who, when, and the report they
   saw.

**The user's understanding, confirmed in conversation:** it checks, trains and tests on its own,
but **it asks first and switches only after approval.** It never switches by itself.

This changes an earlier preference: on 2026-11-16 the user chose "the server switches itself". It
also needs a small database table recording which method is active, and who approved it, when. That
reopens the 2026-11-13 decision of "no model registry table". Confirm both with the user.

### 7.2 Example of what the admin would see (example numbers only)

```
🔔 A better landslide method is ready for your review

Tested on 31 recorded landslide days (2021–2028)
                              Current rules    New method
Warned in time                  20 of 31        25 of 31
False alarms per year              9               6
Big events missed                 none            none
Typhoon Tino 2025 (Camp IV)       Red             Red

What changes: Camp IV and Manipis turn orange about a day earlier.
Risk: tested mostly on Camp IV and Manipis; other hills have few records.

[ Approve switch ]   [ Not now ]      You can undo this at any time.
```

### 7.3 Warnings on the approve screen

- **During an active orange or red, or a PAGASA warning:** "A rain warning is active. Switching may
  slow the site for a short while; better wait until it passes." During a red, the button can be
  held until the storm is over.
- **The report's limits in plain words.**
- **"You can undo this at any time."**

### 7.4 Does the test affect the live site?

- **No.** The test runs on **GitHub's free machines**, not on Render. It reads the records (a quick
  read) and saves its report as a new "waiting for review" item. It never changes the active method.
- **Give it its own database login** that can only read the records and add reports.
- **If the test crashes,** nothing on the site changes, and the developers get GitHub's error email.
- **The only live effect** is right after "Approve": the site loads the new method once and may be
  slower for a short while, as after a restart today.

### 7.5 When is coding still needed?

- **Never for the planned upgrade steps.** Those are all built in from the start, so moving from
  simple rules to smarter models needs no coding.
- **A programmer is needed only for something new:**
  - a new data source (for example, river water-level sensors);
  - a weather service shutting down or changing;
  - a completely different kind of method nobody prepared in advance.

---

## 8. When is there "enough data"? Count incident days, not years

| Step | Needs (per hazard, from consistent records) | Allows |
|---|---|---|
| 0 (now) | — | Fixed rules plus terrain. The models only drive the monthly outlook |
| 1 | About 20–30 independent event days, plus at least 1 rainy season of logged forecasts | A small fitted "when" model (2–3 rain inputs, Firth) may replace the rule's thresholds |
| 2 | About 50 event days, 5–10 in each exposed barangay | Effects per barangay |
| 3 | 100–200 event days | Flexible machine learning, as a challenger only |

**How fast we get there:**
- At the 2021–2025 recording rate (about 1 flood day and 1.6 landslide days a year), 10 years adds
  roughly 10 and 16 more.
- That is still short of step 1 for flood. **Waiting 10 years is not enough on its own.**

**Recording incidents is the real lever:**
- **Recover past floods from the news.** Examples not in the database: 2009-08-17, 2011-01-18,
  2011-01-28, and 2019-08-20 (Linao, Bulacao). 2021-06-12 is already recorded; it affected about
  841–1,154 families.
- **Other records:** DRRMO logbooks and DSWD DROMIC reports.
- **"Heavy rain, no flood" confirmations** from DRRMO.
- **Record every flood and landslide the same way every year.** The empty 2023–2024 flood years
  suggest this isn't happening today.

**Data quality needed:**
- One event definition, kept the same every year.
- Date **and time** for each event.
- Barangay, ideally with a map point.
- The source.
- The same rain product and version throughout.

**How a new method is judged (prospective, from the log):**
- Hits, misses and false alarms per colour (POD, FAR, false alarms per event).
- Peirce and SEDI scores.
- Lead time gained.
- Log score with a cluster bootstrap.
- Brier skill against the seasonal average.
- An event-by-event table.
- At least one full rainy season.
- PAGASA floor kept. Shadow first. Undo always available.

---

## 9. Zero-cost architecture

```
GitHub Actions (free, runs from main)                  Supabase (free)            Render (free)              Vercel (free)
 every 6 h: ECMWF / GFS forecast        ─┐             rain_forecast              /api/rain-watch/           map "Next 3 days"
 daily:     POWER (+IMERG) rain so far  ─┼─ windows ─> rain_observation      ──>  reads rows, NumPy only ──>
            PAGASA warning check        ─┘  + levels > rain_watch_level           /api/history/forecast/ (unchanged)
 yearly:    self-test (section 7) ─> report saved as "waiting for review" ─> admin approves in GeoAlert
 manual:    backtest on the dynamical.org GFS archive vs the 13 event days
cron-job.org (free, as now): keeps Render awake; can also restart the workflow if GitHub pauses it
```

**Where each part lives in the code**
- `rain.py` becomes one of several "source adapters": POWER, ECMWF, GFS, IMERG, PAGASA.
- A new rain-watch module gives the same output shape as the monthly one: barangay, hazard, period,
  level, reasons, method and version. A future model is then just another "assessor", with no
  redesign needed.
- `hazard_forecast.py` (the monthly outlook) stays as it is.
- The heavy tools (reading forecast files, `xarray`, `eccodes`/`cfgrib`, `ecmwf-opendata`,
  `herbie-data`) run **only on GitHub's machine**. The Render image keeps NumPy only. Render's free
  plan has 512 MB of memory and about 0.1 CPU.

**Free-tier traps**
1. **GitHub timers only run from the default branch (`main`).** The site deploys from
   `feature/geoalert-updates`, so the workflow file must also be on `main`.
2. **GitHub turns timers off after 60 days with no repository activity** (public repos). The page
   should show "updated X h ago" and grey out when the data is more than 12 h old. cron-job.org or
   a keep-alive action can restart the timer.
3. **Never let the bot commit data to code branches.** `.github/workflows/ci.yml` runs the full
   tests on every push, and Render and Vercel rebuild on pushes. Data goes to Supabase.
4. **GitHub Actions minutes:** unlimited for public repos; **2,000 a month** for private repos on the
   free plan (not re-checked; CI already uses some). A 6-hourly job of about 3 minutes uses roughly
   360 a month. **The repo's visibility (`Geoalert-team/Geoalert`) is not known**, so check it. Keep
   the Actions spending limit at **$0** so it can never bill.
5. **Supabase free plan:** the database goes **read-only above 500 MB** and **pauses after 7 days**
   with no activity (daily writes prevent that). Check current usage. Store forecasts as daily
   totals per grid cell, which is tiny. Give the GitHub writer its own database role that can only
   add rows to the rain tables. Its password goes in GitHub Secrets.
6. **Vercel Hobby is non-commercial.** It's the same kind of clause that ruled out Open-Meteo. Fine
   for the thesis; check it before any handover to the city.

---

## 10. Step 1: the backtest (recommended first, before any design)

**Why first:** it answers the biggest unknown. Did the forecasts actually see the 13 recorded events
1–3 days ahead, and how many false alarms would the rules have raised in 2021–2025? The answer sets
the real thresholds and may change the design. For example, if forecasts missed the small events,
gauges or IMERG matter more.

**Proposed as a throwaway experiment** in the session scratchpad: a separate Python environment,
**nothing in the project changed**, nothing written to the database. **The user has not yet said
yes to it**; ask first.

**Data access (checked 2026-11-17)**
- STAC: `https://stac.dynamical.org/noaa-gfs-forecast/collection.json`
- Data: `https://dynamical-noaa-gfs.s3.us-west-2.amazonaws.com/noaa-gfs-forecast/v0.2.7.icechunk`.
  Anonymous; also at `s3://dynamical-noaa-gfs/noaa-gfs-forecast/v0.2.7.icechunk/` with `anon: true`,
  region us-west-2.
- Opening it in Python: `dynamical_catalog.open("noaa-gfs-forecast", chunks=None)` (package
  `dynamical-catalog>=0.8.0`), or `icechunk` + `xr.open_zarr`.
- The old `data.dynamical.org` address **stopped working on 2026-09-30**.
- Coverage: forecasts from **2021-05-01**, every 6 h; hourly to 120 h, then every 3 h to 384 h;
  0.25°.
- Rain variable: `precipitation_surface` (`prate`), in kg m⁻² s⁻¹, which is mm per second.
  Multiply by 3,600 for mm per hour and add up over time.
- Licence: CC BY 4.0. Credit "NOAA GFS from dynamical.org".

**Local tools**
- `backend/venv`: Python 3.11.9 with numpy 2.4.2, scipy 1.17.1, scikit-learn 1.9.1 and requests.
  **No** xarray, zarr, icechunk or pandas.
- System Python is 3.14.6. `uv` is not installed.
- So the experiment needs its own environment. Do not add packages to the backend.

**What to compute**
- **Points:** Talisay's grid points (the city spans roughly 10.23–10.30 N, 123.80–123.88 E; read the
  real boundaries from the barangays, or use the city average point), plus one upland point for
  Camp IV and Manipis.
- **For each event day,** using the runs issued 24, 48 and 72 h before: the forecast 24-h and 72-h
  rain.
- **Repeat for every day 2021-05 → 2025-12,** to count how often each candidate rule fires.
- **Compare** with POWER and, if possible, IMERG.
- **Report** hits, misses and false alarms per year for each candidate threshold set, plus an
  event-by-event table.

---

## 11. Decisions

**Made by the user**
- Zero cost; GitHub is fine (2026-11-17).
- No Open-Meteo (2026-11-13).
- NASA POWER stays as the rain history.
- **"ok start with it"** (2026-11-17): go ahead with designing this direction.
- The yearly self-test should **ask before switching**. The user described it that way and agreed.

**Recommended, still to confirm** (ask one at a time, with AskUserQuestion)
1. Rain watch as a **separate** "Next 3 days" layer, keeping the monthly outlook as it is.
2. **Start with the backtest** as a throwaway experiment.
3. Forecast source: **ECMWF Open Data** first, with GFS as fallback.
4. DRRMO is notified; **no automatic public alerts** at first.
5. Storage in **new Supabase tables**, written by GitHub Actions. This needs a migration on the
   shared database, with a backup first.
6. Admin approval in the GeoAlert dashboard, plus a small "active method" table. This reopens the
   2026-11-13 "no registry table" choice and the 2026-11-16 "switches itself" choice.
7. Make the monthly outlook's levels or wording honest (section 5.6).
8. Data requests: PAGASA Mactan daily rain (FOI or university letter, free) and DOST-ASTI gauges.
   Decide who sends them.
9. Check that `HAZARD_LOG_WRITER=true` is set on Render.

**Proposed order of work** (these are separate projects; brainstorm them one at a time)
1. **Backtest** (experiment).
2. **Rain watch:** scheduled job, tables, rules, API, map layer.
3. **DRRMO notifications** from the Rain watch.
4. **Yearly self-test** with admin approval.

Also, outside the code:
- monthly outlook wording;
- recovering past incidents;
- data requests.

---

## 12. Where to resume

Invoke `superpowers:brainstorming` for **project 1–2 (backtest, then Rain watch)**. The context is
already gathered here, so don't redo the investigation.

The first message should do three things:
1. Play back the request in a few lines.
2. Say that this is several projects and give the proposed order.
3. Ask the user, with AskUserQuestion, whether to run the backtest first as a throwaway experiment.

Then follow the usual flow: approaches, design doc, approval, plan.

---

## 13. Sources

- PAGASA warnings: [Varsitarian explainer](https://varsitarian.net/sci-tech/20250724/explainer-how-do-pagasas-rainfall-warnings-and-weather-advisories-work), [Northlink](https://northlinkblog.com/the-philippine-rainfall-warning-system-explained/), [Inquirer](https://newsinfo.inquirer.net/215587/pagasa-unveils-color-coding-for-rain-alerts)
- Tino: [PAGASA preliminary report](https://pubfiles.pagasa.dost.gov.ph/pagasaweb/files/tamss/weather/tcprelimsummary/PAGASA_Prelim_2025_TINO_rev1.pdf), [Manila Bulletin](https://mb.com.ph/2025/11/06/typhoon-tino-dumps-rare-1-in-20-year-rainfall-across-visayas-pagasa-says), [SunStar](https://www.sunstar.com.ph/cebu/why-typhoon-tino-triggered-deadly-floods-in-cebu)
- NASA POWER: [data sources](https://power.larc.nasa.gov/docs/methodology/data/sources/), [FAQ](https://power.larc.nasa.gov/docs/faqs/data/)
- IMERG: [Early Run](https://gpm.nasa.gov/taxonomy/term/1357), [V07B](https://gpm.nasa.gov/data/news/imerg-v07b-early-and-late-run-begin-production)
- ECMWF: [Open Data](https://www.ecmwf.int/en/forecasts/datasets/open-data), [Set X](https://www.ecmwf.int/en/forecasts/datasets/set-x)
- GFS: [NOMADS grib filter](https://nomads.ncep.noaa.gov/cgi-bin/filter_gfs_0p25.pl), [AWS](https://docs.opendata.aws/noaa-gfs-pds/readme.html)
- dynamical.org: [GFS forecast catalogue](https://dynamical-org.pages.dev/catalog/noaa-gfs-forecast), [STAC](https://stac.dynamical.org/noaa-gfs-forecast/collection.json), [ECMWF IFS ENS](https://dynamical-org.pages.dev/catalog/ecmwf-ifs-ens-forecast-15-day-0-25-degree), [Source Cooperative ECMWF GRIB](https://source.coop/dynamical/ecmwf-ifs-grib)
- MET Norway: [Locationforecast](https://api.met.no/weatherapi/locationforecast/2.0/documentation), [licence](https://docs.api.met.no/doc/License), [data model](https://docs.api.met.no/doc/locationforecast/datamodel)
- Open-Meteo: [pricing](https://open-meteo.com/en/pricing)
- CHIRPS-GEFS: [Scientific Data paper](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC9246965/)
- DOST-ASTI: [PhilSensors](https://philsensors.asti.dost.gov.ph/site/about), [FOI example](https://foi.gov.ph/agencies/asti/request-for-bicol-river-basin-philsensors-rainfall-and-water-level-data-for-thesis/)
- PAGASA data: [Citizen's Charter](https://pubfiles.pagasa.dost.gov.ph/pagasaweb/files/PAGASA%27s_CITIZENS_CHARTER_4th_EDITION_FINAL.pdf), [Mactan FOI](https://foi.gov.ph/requests/daily-rainfall-data-for-the-mactan-dumaguete-tagbilaran-and-tacloban-stations)
- GitHub: [disabling and enabling workflows](https://docs.github.com/en/enterprise-server@3.13/actions/how-tos/managing-workflow-runs-and-deployments/managing-workflow-runs/disabling-and-enabling-a-workflow), [keepalive-workflow](https://npmjs.com/package/keepalive-workflow)
- Supabase free tier: [summary](https://automationatlas.io/answers/supabase-free-tier-limits-2026/), [pricing guide](https://www.jetadmin.io/blog/supabase-pricing-2026-guide-to-plans-limits-and-real-world-costs/)
- Past Talisay floods: [Philstar 2021](https://www.philstar.com/the-freeman/cebu-news/2021/06/15/2105585/floods-affect-least-1-thousand-families-talisay), [SunStar Bulacao](https://www.sunstar.com.ph/cebu/bulacao-flood-causes-hours-long-traffic-jam), [GMA upland Talisay](https://www.gmanetwork.com/regionaltv/news/109671/flood-hits-upland-talisay-city-cebu-over-200-affected/story), [Philstar 2009](https://philstar.com/cebu-news/2009/08/17/496391/floods-hit-talisay-city-barangay), [Philstar 2011](https://philstar.com/metro-cebu/2011/01/18/648877/heavy-rains-flood-talisay-barangays)
