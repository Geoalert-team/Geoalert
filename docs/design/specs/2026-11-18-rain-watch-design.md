# Rain watch: next 3 days (design)

*Written 2026-11-18. Status: **waiting for the user's approval.** Nothing is built yet.*
*Builds on `docs/research/2026-11-17-rain-watch-and-rainfall-data.md` (the investigation) and the
GFS backtest of 2026-11-18 (summarised in section 10). Uncommitted, like all work here.*

---

## 1. Why

Flood and landslide show **green on the map almost all the time.** The colour comes from a 19-year
average of rain, measured against cut-offs made for fire. This week's weather never changes it.
During Typhoon Tino (4 Nov 2025) the whole city stayed green. The forecast had seen it coming:
GFS forecast 192 mm for Talisay the day before, and about 170 mm three days ahead.

The Rain watch adds a **"Next 3 days"** view. It colours each barangay Yellow, Orange or Red when
heavy rain is forecast, taking into account how wet the ground already is and each barangay's
terrain. It is never calmer than PAGASA's own alerts.

**What it can and can't do (from the backtest):**
- It warns about **big storms**, 1 to 3 days ahead.
- It **will not catch most small local floods or slides.** Most of our recorded events happened on
  ordinary rainy days (10–30 mm forecast). Three had almost no rain in the forecast at all.

## 2. Goals, non-goals, anti-goals

**Goals**
- An automatic, free "Next 3 days" view for flood and landslide, refreshed every 6 hours.
- Residents see Orange and Red. DRRMO and admins also see Yellow, as an early heads-up.
- Never calmer than PAGASA. DRRMO can raise a level by hand for warnings the feed doesn't carry.
- Every forecast is kept, so the yearly self-test (a later project) can judge new methods.
- An honest note on the monthly view explaining why flood and landslide stay green there.

**Non-goals (later projects or out of scope)**
- DRRMO notifications (project 3) and the yearly self-test with admin approval (project 4).
- ECMWF as a live source. It may be logged later as a second opinion.
- Automatic public alerts. Official alerts stay with DRRMO's existing alert flow.
- Changing the monthly model or its levels.
- Rain per barangay (the forecast grid is about 25 km), IMERG, and rain gauges.
- An admin dashboard screen for editing the cut-offs (they live in a settings table; section 6.6).

**Anti-goals (failure even if it "works")**
- Slowing or crashing the website during a storm, when the most people open it.
- Showing old colours as if they were current, whether an old Red or an old Green.
- A colour calmer than an active PAGASA alert for Cebu.
- Training residents to ignore it. That is why the public never sees Yellow.
- Any cost, any Open-Meteo use, or a bot committing data to code branches.

## 3. Constraints

- **Zero cost.** GitHub Actions and the free Supabase, Render, Vercel and cron-job.org plans only.
  Set the Actions spending limit to **$0**.
- **No Open-Meteo** (the user's decision of 2026-11-13).
- **Never commit or push** (the user's rule). The user puts the workflow on `main` themselves.
- **Shared Supabase database:** back it up before the migration, and migrate only on the user's
  go-ahead.
- **Render free:** 512 MB of memory and about 0.1 CPU. Kept awake by a cron-job.org request to
  `/api/hazards/` every minute. No heavy weather libraries on Render (NumPy is already there).
- **GitHub timers** run only from the default branch (`main`). The site deploys from
  `feature/geoalert-updates`. On public repos, timers pause after 60 days without repository
  activity.
- **Licences and credit:** NOAA GFS is public domain. dynamical.org (fallback) is CC BY 4.0: credit
  "NOAA GFS from dynamical.org". PAGASA's alert feed is CC BY 4.0: credit PAGASA. NASA POWER is
  already credited.

## 4. Approaches considered

| | How | Trade-off | Verdict |
|---|---|---|---|
| **A** | A **GitHub Actions job** fetches the GFS forecast every 6 h and sends it to the site. **Render** checks PAGASA hourly and works out the colours when the map asks | The heavy tools stay off the website. Fresh data (about 4 h after each run). About 300 Actions minutes a month. Needs the workflow on `main` | **Chosen by the user** (2026-11-18) |
| B | Render does everything, from its warm-up thread | No GitHub setup, but heavy libraries on a 512 MB machine inside the live site. Forecast about 10 h old (dynamical.org) unless GRIB tools are added to Render | Rejected: risks the site during storms |
| C | Like A, with ECMWF as the live forecast | ECMWF is usually more accurate, but our cut-offs were tuned on GFS and can't be checked for ECMWF (its free archive covers 5 of our 13 days). Whole-world downloads | Rejected for now; may be logged later as a second opinion |

**Storage:** new tables in Supabase, in every approach. DRRMO overrides and the forecast log need
real tables, so a stored file was not an option.

## 5. Decisions

**Made by the user**

| Date | Decision |
|---|---|
| 2026-11-17 | Zero cost; GitHub is fine. NASA POWER stays as the rain history. "Start with it." |
| 2026-11-13 | No Open-Meteo |
| 2026-11-18 | Run the backtest first (done; section 10) |
| 2026-11-18 | **Balanced** sensitivity (cut-offs in 6.3), kept as settings |
| 2026-11-18 | **The public sees Orange and Red.** DRRMO officers and system admins also see Yellow |
| 2026-11-18 | **PAGASA floor:** read PAGASA's alert feed automatically, **plus a DRRMO override** by hand |
| 2026-11-18 | **Monthly view:** add a plain note; the colours and the 15%/25% scale stay |
| 2026-11-18 | **Day picker:** Today / Tomorrow / Day after, each coloured on its own, opening on Today, with a hint when a later day is Orange or Red |
| 2026-11-18 | **Approach A** (GitHub job plus website), fully automatic after a one-time setup |

**My calls, for the user to check while reading.** Each is marked *(my call)* where it appears.
1. Barangay limits: flood can reach Red in the 14 flood-prone barangays, and one step lower
   elsewhere. Landslide colours only in the 7 steep barangays (6.4).
2. How PAGASA alerts map to colours (6.5).
3. The DRRMO override can only **raise** a level, never lower one (6.5).
4. The GitHub job **posts to the site's API** with a secret token, instead of writing to the database
   directly (6.1).
5. The cut-offs live in a settings table edited through Django admin; there is no new dashboard
   screen (6.6).
6. When the forecast is out of date (over 12 h), forecast colours grey out, but PAGASA and DRRMO
   floors still show (6.8).
7. A small banner on the public map, in any view, when Orange or Red is coming. The map's default
   view stays "Past hazards" (7.1).
8. Barangay personnel and BFP accounts see the public version: no Yellow (6.7).

---

## 6. The design

### 6.0 Overview

```
Every 6 h   GitHub Actions (on main)              Render (Django)                       Map / dashboard
            tools/rain_forecast/fetch.py
            NOAA NOMADS: GFS rain, 4 grid
            points around Talisay, hours 1-96  ── POST /api/rain-watch/forecast-runs/ ─> rain_forecast_run
            (fallback: dynamical.org archive)     (secret token)                          rain_forecast_series

Every hour                                        PAGASA feed check, started by the
                                                  existing cron-job.org ping            pagasa_alert

Any time                                          DRRMO sets or cancels an override     rain_watch_override

On request                                        GET /api/rain-watch/: works out the
                                                  levels from forecast + wet ground
                                                  (NASA POWER) + barangay limits
                                                  + PAGASA floor + DRRMO floor  ──────>  "Next 3 days" view
```

**Philippine days:** "Today", "Tomorrow" and "Day after" are Philippine calendar days (UTC+8). All
stored times are UTC.

### 6.1 The forecast job (GitHub Actions)

- **Files:**
  - `.github/workflows/rain-forecast.yml`
  - `tools/rain_forecast/fetch.py`: standalone, no Django
  - `tools/rain_forecast/requirements.txt`: pinned versions; `eccodes` for GRIB, plus the
    dynamical.org fallback libraries (`icechunk`, `zarr`, `dynamical-catalog`)

  All three must be on `main` for the timer to run.
- **Schedule:**
  - `cron: '17 4,10,16,22 * * *'`, about 4 h 17 min after each GFS run (00/06/12/18 UTC), when
    NOMADS normally has it.
  - Also `workflow_dispatch`, with a `dry_run` input that prints instead of posting.
  - Settings: `timeout-minutes: 15`, `permissions: contents: read`, and a `concurrency` group.
  - The job **never** pushes to the repository.
- **What it fetches:**
  - GFS 0.25° surface precipitation for the **4 grid points** around Talisay: 10.25 and 10.5 N,
    123.75 and 124.0 E.
  - Forecast hours **1 to 96**, hourly.
  - It uses the NOMADS grib filter with a server-side box (about 400 bytes per hour), paced at about
    one request a second.
  - It must produce **per-hour rain in mm** for each point. GFS stores rate and amount as averages
    or totals since the last 6-hour reset, so the script turns those into per-hour values.
  - **Acceptance check:** for one run, the per-hour values must match the dynamical.org archive for
    the same run, within 0.1 mm a day. The archive is what the backtest used.
- **Fallback:** if NOMADS fails or the run is incomplete, read the same run, or the newest one
  available, from the dynamical.org archive (`noaa-gfs-forecast`, `precipitation_surface` × 3,600).
  The fallback is about 10 h behind.
- **Filling gaps:**
  - First the job asks the site which runs from the last 3 days it already holds
    (`GET .../forecast-runs/status/`).
  - It posts the newest run in full (hours 1–96).
  - For each **missing older run** from those 3 days (up to 12), it posts **hours 1–6 only**. Older
    runs only supply their first hours to the joined-up series (6.3), so this is all the landslide
    rule needs, and it is only 6 small requests per run. NOMADS keeps about 10 days.
  - This covers missed timers and the first launch: one manual run fills the last 3 days.
- **Posting:**
  - `POST /api/rain-watch/forecast-runs/` with `Authorization: Bearer <RAIN_WATCH_INGEST_TOKEN>`.
  - Body: `{source: "gfs-nomads" | "gfs-dynamical", init_time, job_version,
    points: [{lat, lon, first_hour_start, mm_per_hour: [96 floats]}]}`.
  - Retry 3 times with backoff, then fail the job. GitHub then emails the failure.
  - On the server, compare the token in constant time. The endpoint uses neither session login nor
    CSRF.
  - *(my call: post through the API instead of a separate database login. Django checks the data,
    and the token can do nothing but add forecasts.)*

### 6.2 Storage: new app `apps/rainwatch`, migration `0001`

| Table | Columns (main) | Notes |
|---|---|---|
| `rain_forecast_run` | id, source, init_time, received_at, job_version | Unique (source, init_time). Never deleted, kept forever. A repeat post with the same or fewer hours is a no-op; one with more hours replaces the run's series, hours, `job_version` and `received_at` (see below) |
| `rain_forecast_series` | id, run → run, lat, lon, first_hour_start, mm_per_hour `real[]` | 4 rows per run (about 6,000 a year, a few MB). Never deleted, kept forever (the yearly self-test reads it). Only edited by the longer-copy replacement below |
| `pagasa_alert` | id, identifier (unique), sent, msg_type, references, event, category, response_type, urgency, severity, certainty, effective, expires, headline, description, area_desc, covers_talisay, cap_url, raw_xml, fetched_at | One row per CAP alert, kept for the record |
| `rain_watch_override` | id, hazard (Flood / Landslide / Both), level (Yellow / Orange / Red), starts_at, ends_at, note, created_by, created_at, cancelled_at, cancelled_by | Rows are only added; cancelling fills in the two cancel fields |
| `rain_watch_rules` | id, flood_dry, flood_wet, slide_dry, slide_wet (3 numbers each), wet_14day_mm, flood_exposure_min, steep_share_min, stale_hours, note, created_by, created_at | Insert-only; the **newest row is in force**, so changes keep their history. A data migration adds the Balanced row |

**The one exception to "never edited":** a run first stored short (a gap-fill) is replaced by a longer copy of the same run (same source and start time). Its first hours are the same forecast, so nothing the yearly self-test needs is lost. The server answers 200 with `"created": false, "upgraded": true`. The same or fewer hours is still a no-op (200, `"created": false`).

The migration is applied only after a backup and the user's go-ahead. See 6.10.

### 6.3 The colour rules

All numbers come from the newest `rain_watch_rules` row. The starting values are the user's
**Balanced** choice.

**Rain per day.**
- Build one hourly series per grid point. For each hour, take the newest stored run that covers it.
  Older hours come from older runs' first hours, which are close to what actually fell.
  - If NOMADS and dynamical.org both hold the same run, prefer NOMADS.
  - An hour no run covers counts as missing, and the reasons say "partial".
- Turn the 4 grid points into two places, with the same bilinear weights as the backtest:
  - **city**: 10.2835 N, 123.8212 E
  - **upland**: 10.325 N, 123.795 E
- Add up each Philippine day.

**Wet ground.** NASA POWER's total over its latest 14 complete days, from the existing
`rain_daily.csv` plus `recent_rain()` (cached 3 h). The ground counts as wet at
**156.5 mm or more**, POWER's 90th percentile from 2006 to 2026. POWER runs 2–3 days behind, as in
the backtest. If POWER can't be read, use the dry-ground cut-offs and show staff "ground wetness
unknown".

**Flood.** The day's rain at the **worse of city and upland**:

| | Yellow | Orange | Red |
|---|---|---|---|
| Dry ground | 30 mm | 60 mm | 120 mm |
| Wet ground | 20 mm | 40 mm | 80 mm |

**Landslide.** Rain over **3 days** (that day plus the 2 days before) at the **upland** point:

| | Yellow | Orange | Red |
|---|---|---|---|
| Dry ground | 50 mm | 80 mm | 120 mm |
| Wet ground | 25 mm | 40 mm | 60 mm |

Wet ground **lowers the cut-offs**. It never raises a colour on its own: the backtest showed that
stepping up by one colour would turn the city Yellow about 35 days a year.

### 6.4 Barangay limits *(my call, from the repo's terrain files)*

- **Flood:** the barangays with an `exposure` of 190 or more in `barangay_exposure.csv` get the full
  level. That is the average of the NOAH 25-year, NOAH 100-year and HAND-under-2-m building counts.
  The rest get **one step lower** (Red → Orange, Orange → Yellow, Yellow → Green).
  - **Full level (14):** Bulacao, Tabunok, Linao, Biasong, Cansojong, Dumlog, Lawaan II, Lawaan III,
    Poblacion, Pooc, San Isidro, San Roque, Tangke, Lagtang.
  - **One step lower (8):** Camp IV, Manipis, Tapul, Maghaway, Jaclupan, Cadulawan, Lawaan I, Mohon.
- **Landslide:** only barangays with 40% or more of their land steeper than 18°
  (`slope_gt18 ≥ 0.40` in `barangay_terrain.csv`) get a colour.
  - **Steep (7):** Camp IV, Manipis, Tapul, Maghaway, Lagtang, Jaclupan, Cadulawan.
  - The other 15 have no landslide colour.
- The two cut-offs (190 and 0.40) are stored in `rain_watch_rules`. The lists are worked out from the
  CSVs, not typed in. Match barangays by `barangay_id`, as `hazard_data.py` already does.

### 6.5 PAGASA floor and the DRRMO override

**Reading PAGASA's feed** (`https://publicalert.pagasa.dost.gov.ph/feeds/`, Atom, CC BY 4.0, live
on 2026-11-18)
- **Where it runs:** on the machine with `PAGASA_FEED_WRITER=true` (Render only), at most once an
  hour.
- **What starts it:** the existing `/api/hazards/` request, using the same `cache.add` gate and
  daemon-thread pattern as `warm_in_background()` in `apps/hazards/views.py`. It has its own cache
  key, valid for 1 hour.
- **Timeouts:** 20 s per request. A failure is logged and never affects the hazard list.
- **New entries:** for each feed entry not yet stored, fetch its CAP 1.2 file, parse it and save a
  `pagasa_alert` row.
- **Why hourly:** the feed only holds about the last 15 alerts.
- **Covers Talisay** if any of these hold:
  - an `<area>` polygon contains 10.2835 N, 123.8212 E (GEOS is available). A polygon only counts
    when it is about province-sized: its bounding box spans at most 3° of latitude and 3° of
    longitude. PAGASA draws Tropical Cyclone Alerts over the whole Philippine Area of Responsibility,
    so those count only when they name Cebu (a geocode or `areaDesc`) *(user decision, 2026-11-18)*
  - a geocode is Cebu's PSGC, `072200000`
  - failing both, `areaDesc` names Cebu
- **Active** means all of these:
  - it covers Talisay
  - `sent`/`effective` ≤ now < `expires`
  - `msgType` is not `Cancel`, `responseType` is not `AllClear` and `urgency` is not `Past`
  - no newer alert lists it in `references`
- **Mapping** *(my call; DRRMO may adjust)*. Event types seen so far are "General Flood Advisory"
  and "Tropical Cyclone Alert".

| Event | Floor |
|---|---|
| Event name contains "Flood" | **Flood** at least Yellow; Orange if severity is Severe; Red if Extreme |
| Event name contains "Tropical Cyclone" or "Rainfall" | **Both hazards**: Moderate → Yellow, Severe → Orange, Extreme → Red; Minor → none |
| Any other event | Stored and listed on the DRRMO dashboard as "not applied", so new kinds get reviewed |

- **Which barangays:**
  - A PAGASA flood floor applies at its full level in all 22 barangays, so the map is never calmer
    than PAGASA *(user decision, 2026-11-18)*.
  - A landslide floor applies to the 7 steep barangays only.
  - A DRRMO floor goes through the same barangay limits as the forecast: the full level in the 14
    flood-prone barangays and one step lower in the rest.
- **Which days:** a floor applies to every day its active period overlaps.

**DRRMO override**
- **Who:** DRRMO officers and system admins (`IsDRRMOOfficer`).
- **Fields:**
  - hazard: Flood, Landslide or Both
  - level: Yellow, Orange or Red
  - **end time:** required, at most 72 h ahead
  - **note:** required, for example "PAGASA Visayas heavy rainfall warning #3, Orange"
- **How it works:**
  - It is a floor, so it **only raises** colours *(my call)*.
  - It goes through the same barangay limits as the forecast.
  - It can be cancelled early.
  - When several are active, the highest wins.

**Final level** for each barangay, hazard and day: the highest of the forecast level, the PAGASA
floor and the DRRMO floor.

### 6.6 Settings *(my call)*

- The cut-offs live in `rain_watch_rules`. They can be changed in **Django admin**
  (`/django-admin/`) by a staff account, with no code change and no redeploy.
- Each change adds a row: who, when, and a note.
- New environment settings:
  - `RAIN_WATCH_INGEST_TOKEN` (Render, and as a GitHub secret)
  - `PAGASA_FEED_WRITER` (Render only)
  - `RAIN_WATCH_API_URL` (a GitHub secret or variable)

  Add them to `deploy/render.env.example`, along with the missing `HAZARD_LOG_WRITER`.

### 6.7 API

**`GET /api/rain-watch/`** (public, `AllowAny`). One call returns all three days.

```json
{
  "updated_at": "2026-11-18T12:40:00Z",
  "run_init": "2026-11-18T06:00:00Z",
  "source": "gfs-nomads",
  "stale": false,
  "stale_hours": 12,
  "wet_ground": {"mm_14_days": 168.2, "wet": true},
  "days": [
    {"key": "today",     "date": "2026-11-18", "less_certain": false, "barangays": [...]},
    {"key": "tomorrow",  "date": "2026-11-19", "less_certain": false, "barangays": [...]},
    {"key": "day_after", "date": "2026-11-20", "less_certain": true,  "barangays": [...]}
  ],
  "floors": [{"source": "PAGASA", "hazard": "Flood", "level": "Orange", "until": "...", "text": "..."}]
}
```

- **Each barangay:** `{id, name, flood: {level, reasons}, landslide: {level, reasons} | null}`.
  `landslide` is null for the 15 flat barangays.
- **Reasons are short, plain sentences**, for example:
  - "Forecast 140 mm; ground already wet"
  - "Raised to Orange: PAGASA General Flood Advisory"
  - "Raised by DRRMO: PAGASA heavy rainfall warning #3"
- **Who sees Yellow:** DRRMO officers and system admins get every level. Everyone else gets no
  Yellow: it is returned as `"none"`, and Green is returned as `"none"` too. That includes anonymous
  visitors, barangay personnel and BFP *(my call)*.
- **Staff extras:** DRRMO and admins also get `pagasa_alerts`, all recent alerts with applied or not
  applied, and the active `overrides`. Each `pagasa_alerts` entry carries `covers_talisay` and
  `mapped` (whether its event type has a floor mapping), so the dashboard can tell "not for Talisay"
  and "new kind: please review" from a plain "not applied".
- **`stale_hours`** is the stale limit from the rules, sent so the map uses the same limit as the
  server.
- **Hidden levels over an unknown forecast:** when a part's forecast is unknown and its real level
  is hidden from the public (Green or Yellow), it is returned as `"unknown"` with the reason
  "Forecast out of date", not `"none"`, so an out-of-date map never looks calm. Orange and Red are
  unchanged.
- **Caching:** the result is cached for 5 minutes per audience (public or staff). The cache is
  cleared on a new run, a new PAGASA alert, or an override change.

**Other endpoints**
- `POST /api/rain-watch/forecast-runs/` and `GET /api/rain-watch/forecast-runs/status/`: token only;
  for the GitHub job.
- `GET/POST /api/rain-watch/overrides/` and `POST /api/rain-watch/overrides/<id>/cancel/`: DRRMO
  officers and system admins.

**Checks on posted runs** (rejected with a 400, so the job fails visibly):
- exactly 4 points
- 1 to 120 values each
- no negatives and no NaN
- a sensible `init_time`: not in the future, at most 10 days old

### 6.8 Freshness and failure

- `stale` is true when the newest **full** run (one reaching 72 hours or more) arrived more than
  `stale_hours` (12) ago. That means two missed jobs in a row. The short gap-fill runs don't count.
- **When stale:**
  - The forecast colours are not shown. The API returns `"unknown"` and the map greys them out:
    "Out of date: last forecast 14 h ago".
  - PAGASA and DRRMO floors still show, because they are current.
  - Staff see the data's age prominently on the dashboard.
- **No runs at all** (for example, right after launch) is shown the same way as stale.
- **GitHub job failure:** GitHub emails the person who last changed the workflow's schedule (the
  `cron` line) or who last re-enabled the workflow. That email is the only alarm, so that person
  should be someone who reads it. The site goes stale after 12 h.
  If the timer pauses after 60 days (public repo), re-enable the workflow in the Actions tab.
- **Wet ground** is worked out in the background, at most once an hour, and a request never waits
  for it. Until the first result, wetness is unknown and the dry cut-offs apply.
- **PAGASA feed down:** keep the last stored alerts until they expire, and log the failure.

### 6.9 Tests (CI runs on its own database; never the shared one)

- **Rules**, using the backtest's real numbers:
  - 192 mm on dry ground → flood Red in Bulacao, Orange in Camp IV.
  - 23 mm on wet ground (like 2021-06-12) → Yellow.
  - Landslide: 55 mm over 3 days on dry ground → Yellow; 49 mm on wet ground → Orange.
  - Flat barangays get no landslide colour.
- **Day sums:** joining runs, Philippine day boundaries, and a missing run.
- **CAP:** fixtures saved from the live feed (General Flood Advisory, Tropical Cyclone Alert) plus a
  made-up alert covering Cebu. Also: expiry, Cancel/AllClear, newer alerts replacing older ones, and
  unknown event types not applied.
- **Audience:** anonymous and barangay accounts never receive Yellow; DRRMO does.
- **Ingest:** token required, a repeat post with the same or fewer hours does nothing, a longer copy of a stored run replaces it (`"upgraded": true`), bad bodies get a 400.
- **Stale behaviour,** and override permissions, end time and cancelling.
- **The fetch script:** per-hour conversion and day sums, on saved GRIB fixtures. Builder's choice
  whether to run these in CI or locally. There must be no network calls in any test.

### 6.10 Setup and go-live order

1. Build on `feature/geoalert-updates`; nothing is committed by the assistant.
2. Back up the shared Supabase database (as for migrations 0001–0008; backups in Downloads), then
   apply `rainwatch` 0001 **on the user's go-ahead**.
3. Set up Render:
   - Set `RAIN_WATCH_INGEST_TOKEN` (a long random value) and `PAGASA_FEED_WRITER=true`.
   - Check that `HAZARD_LOG_WRITER=true` is also set.
4. Set up GitHub:
   - Add secrets `RAIN_WATCH_INGEST_TOKEN` and `RAIN_WATCH_API_URL`.
   - Set the Actions spending limit to $0.
   - Check whether `Geoalert-team/Geoalert` is public or private. Private repos get 2,000 free minutes
     a month; each run installs the forecast libraries and fetches, so this job uses roughly 500 to
     700 minutes a month. Free on a public repo.
5. **The user** puts `.github/workflows/rain-forecast.yml` and `tools/rain_forecast/` on `main`.
6. Run the workflow once by hand. Check the map, the DRRMO dashboard and the data's age.
7. Watch the first days. Compare a few days' forecasts with what POWER later records.

## 7. What people see

### 7.1 Public map (`frontend/src/pages/PublicMap.jsx`)

- **The view:**
  - `VIEWS` gains `{ key: 'next3', label: 'Next 3 days' }`.
  - When it is selected, a day picker appears where the month picker sits:
    **Today · Tomorrow · Wed (less certain)**. It opens on Today.
- **Shading:**
  - Barangays are filled Orange or Red from the API.
  - With no rain watch, a barangay has **no fill** (not green), and the legend says "No rain watch".
  - The Flood and Landslide layer ticks decide which hazards count, handled the same way as
    `activeTypes` in the monthly view. When both are ticked, the fill is the worse of the two.
- **Hint:** if a later day has Orange or Red, show "Red expected Wed in 6 barangays → see Wed".
- **Banner** *(my call)*: when Orange or Red is coming in the 3 days, a slim banner shows in any view:
  "Rain watch: Red expected tomorrow → view". The default view stays "Past hazards".
- **Tapping a barangay:** a strip of the three days' colours ("Today – · Tomorrow Orange · Wed
  Red"), plus the reasons.
- **Footer:**
  - "Updated 3 h ago."
  - "Automatic estimate from weather forecasts (NOAA GFS) and PAGASA alerts. Not an official
    warning. Follow DRRMO and PAGASA."
  - Credits.
- **Stale:** the fills are greyed and the "Out of date" line shows.
- **Phones:** it must fit phone screens, like the recent mobile work.
- **Colours:** Yellow, Orange and Red are their own set. They must not be confused with the monthly
  view's High/Moderate/Low or the alert pins.

### 7.2 DRRMO dashboard

A **Rain watch** card with:
- a 3-day table of barangay × hazard, with every colour including Yellow, and each reason
- the data's age
- the PAGASA alerts, applied and not applied
- the override form (hazard, level, end time, note), and the active overrides with Cancel

### 7.3 Monthly view note

When "Likely by month" shows flood or landslide, add this note:

> "Floods and landslides are rare in any one month, so this view stays mostly green, even in the
> rainy season. For rain that is coming, see **Next 3 days**."

The existing disclaimer stays.

## 8. Left to the builder

- Converting GFS's 6-hour-reset values to per-hour rain, NOMADS file names, pacing and retries.
- Component structure, CSS, the exact wording of reasons, and cache keys.
- Indexes, admin registration and serializer shapes, within the contracts above.
- Whether the fetch-script tests run in CI.

## 9. Checks before or at go-live

- Repository visibility (Actions minutes) and the $0 spending limit.
- Supabase usage. The new tables are tiny, but the database goes read-only above 500 MB.
- Vercel Hobby is non-commercial. Fine for the thesis; revisit before any handover to the city.
- **Missing records:** the backtest flagged three possible floods that aren't recorded.
  - Typhoon Odette, 16 Dec 2021 (93 mm forecast)
  - 6 Dec 2025 (230 mm forecast, a tropical depression)
  - 2 Jan 2023 (131 mm forecast)

  Checking the news improves the false-alarm counts and the future self-test. Not part of this
  build.

## 10. Backtest summary (2026-11-18, throwaway, scratchpad only)

- **Data:** GFS from the dynamical.org archive, 8,108 runs. The forecast is the one you could read at
  8 am the day before.
- **Period:** scored on 2021-05-06 to 2025-12-31 (4.65 years).

| Day | Event | Forecast, day before | Seen? |
|---|---|---|---|
| 2025-11-04 | Tino flood + landslide | 192 mm (about 169 mm 3 days ahead); PAGASA Mactan measured 183, POWER 31 | Yes |
| 2022-04-08 | Landslide | 32 mm; 56 mm over 3 days | Partly |
| 2025-08-25 | Landslide | 24 mm; 49 mm over 3 days; wet ground | Partly |
| 2021-06-12 | Flood | 23 mm; ground very wet (202 mm) | With wet ground only |
| 2025-08-12 | Flash flood | 23 mm | No (only on the most sensitive setting) |
| 2025-10-07, 2021-11-04, 2022-07-13, 2023-06-26 | Flood / landslides | 9–15 mm | No |
| 2025-08-18, 2024-10-01, 2025-12-12 | Flood / landslides | under 6 mm | No (nothing forecast) |

**Balanced** (the chosen setting) caught 5 of the 13 days. False alarms per year, counting each run
of raised days once:

| | Yellow+ | Orange+ | Red |
|---|---|---|---|
| Flood | 5.8 | 1.5 | 0.6 |
| Landslide | 8.6 | 3.9 | 1.3 |

A single "worst of 3 days" colour roughly doubles these (flood Orange+ 3.9, landslide 8.6), which is
why there is a day picker. The results are indicative only: there are 5 flood days and 8 landslide
days. The backtest scripts and the full report are in the 2026-11-18 session's scratchpad; ask to
keep them in the repo if wanted.
