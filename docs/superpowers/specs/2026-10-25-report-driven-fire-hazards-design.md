# Report-driven fire hazards — design

Date: 2026-10-25
Status: draft for review
Branch: merge-scout

## Why

Today a DRRMO officer publishes every hazard by hand: they validate an incident report,
then open the map, draw an area and pick a level. A fire is reported by someone who is
standing in front of it, so the report already says when, where and what is burning.
Drawing it again adds nothing.

The new rule for fires: **a report is the only way a fire becomes an active hazard.**
Barangay staff submit it, DRRMO decides, the fire goes live as a pin, and when it is
over DRRMO closes it with the BFP figures. The closed fire becomes one history record in
the same shape as a row of the BFP fire log. Those records are what the purok colours
count.

## How this fits with the other specs

- **`2026-10-25-history-based-hazard-levels-design.md`** (teammate's): purok colours
  from history, thresholds in Settings, active hazards as pins. This spec builds on it
  and changes four things, listed in [Changes to the hazard-levels spec](#changes-to-the-hazard-levels-spec).
  That file is not edited.
- **`2026-10-23-purok-fire-data-design.md`**: designed the import of the BFP fire log.
  Its import rules (dates, alarm-to-level mapping, casualties, `source_ref`, address
  linking) are reused here, adapted to the `Purok` model that was actually built.
- Floods and landslides are out of scope: they keep today's form and manual publishing
  until there is matching data for them.

## Decisions (agreed 2026-10-25)

| Question | Choice |
|---|---|
| Which hazards use the new flow | Fire only, for now |
| How a fire becomes active | DRRMO approves a report; it goes live as pins at its puroks' centres. No drawing |
| Manual publishing | Removed for Fire. Floods and landslides keep it |
| Alert level | The highest history level among the report's puroks. The officer doesn't choose it (revised 2026-10-26: the decision shows the report, not a level picker) |
| Extreme | Always waits for a second officer, as today (auto-release after the approval window) |
| Same fire reported twice | Each report keeps its own pin. Pins of one fire are marked as related |
| How related pins count | One fire = one history record = +1 for each purok its pins sit in |
| What the report asks | When and where only: the BFP log's columns A–F, plus a description and photos. Everything from Property type on is DRRMO's, entered when closing (revised 2026-10-25) |
| Who reports | Barangay personnel accounts, as today |
| Puroks on a fire report | One or more, up to 10, from the barangay's list. The map is a preview, not clickable: it outlines each chosen purok with a pin at its centre. No "Not on the list" for now (revised 2026-10-25) |
| Closing a fire | Two steps: **Fire out** (all-clear, pin leaves the map) then **Resolved** (BFP figures, history written) |
| Reporter feedback | A step tracker on each report, with a notification at every step |
| History view | Tapping a barangay shows its whole history; picking a purok shows only that purok's |
| Purok colours when zoomed out | Stay per purok. A barangay is never filled with one merged colour |
| Where an active fire lives | `HazardZone`, so alerts, approval, reminders, all-clear and retraction are reused |
| BFP fire log | Imported as history. The purok list is cleaned up against it first (see Order of work) |

## Goals

- A fire can only go live from an approved report, and its level is never below what the
  purok's history says.
- One fire, however many people report it, is one alert, one pin group and one history
  record.
- A closed fire is a complete BFP-shaped record without anyone retyping it.
- A reporter can always see where their report is.

## Non-goals

- Floods and landslides (form, decision flow, publishing).
- Reopening a fire after "Fire out". A rekindled fire is reported again and approved as a
  new fire.
- Re-grading active fires when history changes.
- Official purok boundaries (the estimates stay until the Barangay Hall sends real ones).
- Geocoding BFP street addresses to points.

## Data model

All new fields are nullable or have defaults, so existing rows and sample data are
unaffected.

### `HazardZone` (`apps/hazards/models.py`)

- New status **`Resolving`** ("fire out, figures pending"), between `Active` and
  `Resolved`. Off the public map; counts as neither active nor history.
- `fire_out_at`, `fire_out_by` (FK `User`, `SET_NULL`): set by Fire out.
- For a fire, `geometry` is the union of 25 m circles around the pins of all its reports
  (one per purok on each report).
  It is only used to find the barangays to alert (`affected_barangays`). It is never
  drawn on the public map.

Status flow of a fire zone:

```
Awaiting_Approval ──approve / window──▶ Active ──Fire out──▶ Resolving ──Close──▶ Resolved
        │                                 │
        └──────────── Retract ────────────┘──▶ Retracted   (never becomes history)
```

### `IncidentReport` (`apps/reports/models.py`)

Statuses stay `Pending`, `Validated`, `Rejected`. For a fire, `Validated` always means
"approved and linked to a fire zone" (`hazard_zone` is set in the same transaction).
Several reports can link to one zone; those are the related pins.

New fields, used by fire reports:

| Field | What it holds |
|---|---|
| `started_at` | When the fire started (date and time); defaults to the submit time |
| `puroks` | M2M `Purok` through `incident_report_purok`. The puroks the fire is in, as the reporter chose them, in the barangay; up to 10 |

A fire report's pins are its puroks' centres (a point inside each purok,
`point_on_surface`). The reporter doesn't place a pin. `location` is set by the server
to the first purok's centre, or to the barangay's when it has no puroks, so screens
that show one point per report keep working. `severity_estimate` is no longer asked for
fires. Region, province and city are not asked: they are always Region 7, Cebu, Talisay
City.

The single `purok` and `purok_other` columns added first (migration `0005`) leave the
model. Their database columns stay until the copies of the app that read them are gone,
because the shared database serves more than one branch.

Property types, as they appear in the BFP log. DRRMO picks one when closing a fire:

| Category | Sub-categories |
|---|---|
| Residential | Single and two family dwelling |
| Non-residential | Business, Mercantile, Storage, Health care, Assembly, Educational, Industrial, Miscellaneous |
| Non-structural | Rubbish, Grass, Electrical pole |
| Transport | Automobile, Motorcycle, Truck, Bus, Tricycle, Jeepney, Locomotive |

The list lives in one backend module and is served to the close form, so adding a type
is one edit.

### `HistoricalRecord` (`apps/history/models.py`)

| Field | What it holds |
|---|---|
| `puroks` | M2M `Purok` through `historical_record_purok`. Every purok the event touched; +1 each |
| `alarm_level` | BFP alarm level as given (list below) |
| `property_category`, `property_subcategory` | Set by DRRMO when closing |
| `damage_cost` | Decimal, PHP |
| `structures_affected` | Integer |
| `injured_ff_male`, `injured_ff_female`, `injured_civ_male`, `injured_civ_female` | Integers |
| `fatal_ff_male`, `fatal_ff_female`, `fatal_civ_male`, `fatal_civ_female` | Integers |
| `location_text` | The address as BFP typed it (imports only). Staff only |
| `source_ref` | Unique import key; null for records made in the app |

Blank means "not known", not zero, as `_as_count` already treats it. `total_casualties`
is still filled (sum of the eight counts when any is known), so Analytics and Reports
keep working unchanged.

Alarm levels offered when closing: `FIRE OUT UPON ARRIVAL`, `1ST ALARM` … `5TH ALARM`,
`TF ALPHA` … `TF ECHO`, `GENERAL ALARM`, `UNRESPONDED`. The BFP log only uses 1st–4th,
TF Alpha, Fire out upon arrival and Unresponded; the rest is the BFP ladder and should
be confirmed (see Open questions).

## Design

### 1. Submitting a fire report

The form on the barangay dashboard (`pages/Dashboard/BarangayDashboard.jsx`) switches to
these fields when **Fire** is chosen:

| Field | Notes |
|---|---|
| When it started * | Date and time; set to now when Fire is chosen, unless the reporter already changed it; not in the future |
| Barangay * | Locked to the assigned barangay, as today |
| Purok / Sitio * | One or more of the barangay's puroks, shown as chips with ×, added from a "+ Add another" list. Optional when the barangay has no puroks. If the list can't be loaded, the form says so and offers to try again |
| Where exactly | A preview map, not clickable: the barangay's outline, each chosen purok outlined, and a pin at each one's centre |
| What's happening * | Description, as today |
| Photos | As today |
| Position, agency | As today |

These are the BFP log's columns A–F: date, time, region/province/city (filled in by the
system) and exact location. Property type, casualties, damage, structures and alarm
level are DRRMO's, entered when closing (section 4).

`POST /api/reports/incidents/` (existing) validates the fire fields when the hazard type
is Fire: a barangay, `started_at` required and not in the future, at least one purok
when the barangay has puroks, every purok in that barangay, at most 10. Any pin the
client sends is ignored; the server sets `location` from the puroks. Other hazard types
store no `started_at` or `puroks`, whatever the client sends.

### 2. The step tracker

Each report in "My reports" shows its steps, worked out from the report's status and its
linked zone's status, so nothing new is stored:

```
You sent ─▶ DRRMO approved ─▶ Active fire ─▶ Fire out ─▶ Resolved
        └─▶ Rejected: "<reason>"
```

- An Extreme fire waiting for a second officer shows "Awaiting a second officer" on the
  Active step.
- A report attached to an existing fire shows "Joined an active fire · N reports".
- The reporter gets a notification (existing `Notification`, existing bell) when their
  report is decided, when the fire goes live, at Fire out and at Resolved.

Floods and landslides get the same tracker for free: their steps stop at "DRRMO
validated" until an officer publishes a zone from the report.

### 3. The DRRMO decision

`GET /api/reports/incidents/<id>/decide/` returns what the decision dialog needs:

- the report's purok, its fire count in the period and its level, from the hazard-levels
  module (`level` for one purok, see change 3);
- **active fires nearby**: Active or Awaiting_Approval fire zones with any pin within
  500 m of this report's pin, each with its pins, report count, level and start time.

`POST /api/reports/incidents/<id>/decide/` (DRRMO Officer, System Admin), one
transaction:

| Body | Effect |
|---|---|
| `{"action": "approve", "note"?}` | Level = the highest level among the report's puroks (Low when none has history); any level the client sends is ignored. Creates a Fire `HazardZone` (25 m circles round the report's pins), links the report, sets it `Validated`. Red → `Awaiting_Approval`, approvers notified, as `HazardZoneCreateView` does. Otherwise `Active` and `issue_alert` |
| `{"action": "attach", "zone": "<id>"}` | Links the report to that zone, sets it `Validated`, adds circles round its pins to the geometry. Barangays newly covered are alerted through the same path as reshaping a zone. If any of the report's puroks has a level above the zone's level, the zone is raised through `request_raise` / `apply_raise`, so a raise to Red is held |
| `{"action": "reject", "note": "..."}` | Note required; report `Rejected` |

- The report must still be `Pending`; otherwise 409 *"Already decided by X at 08:20."*
- Attaching to a zone that is no longer Active or Awaiting_Approval → 409 *"That fire is
  no longer active."*
- Every decision is written to the audit log (`log_event`), as publishing is today.

The existing `PATCH /api/reports/incidents/<id>/review/` stays for flood and landslide
reports and refuses fire reports, so there is one way to decide a fire.

### 4. Fire out and closing

- `POST /api/hazards/<id>/fire-out/` (DRRMO): Active → `Resolving`; sets
  `fire_out_at/by`; sends `all_clear` to the alerted barangays; notifies the linked
  reports' reporters.
- The DRRMO dashboard gets a **Needs figures** list: fire zones in `Resolving`, oldest
  first. `nudge_stale_zones` also reminds the publisher about these each day ("Fire at
  Purok Sambag is still waiting for BFP figures").
- `POST /api/hazards/<id>/close/` (DRRMO): `Resolving` → `Resolved`. Body: `alarm_level`
  (required), the eight casualty counts, `damage_cost`, `structures_affected`,
  `property_category` and `property_subcategory` (required; the sub-category list
  follows the category), `summary`. Writes **one** `HistoricalRecord`:
  - `occurred_at` = the earliest `started_at` of the zone's reports;
  - `puroks` = the distinct puroks of the zone's reports;
  - `barangay` = the first report's barangay; `severity_level` = the zone's level;
  - `description` = the summary, or `BFP: <category> – <sub-category>, <alarm>`.
- The generic PATCH that resolves a zone refuses Fire zones, so fire history is only
  written by `close`.
- `ResponseStatusReportView` counts `Resolving` zones separately.

### 5. Pins on the map

- The hazard list the public map reads includes, for each fire zone, its `pins`:
  `[{lat, lng, purok_name}]`, one per purok of each linked report. No reporter names.
- Public map: only `Active` zones. Each pin is coloured by the zone's level. Pins of one
  fire share a count badge ("3"); tapping one highlights them all, joins them with thin
  dashed lines and opens the zone panel: *"Same fire · 3 reports · since 08:12"*.
- No shading, circle or outline is drawn for a fire.

### 6. Barangay and purok history

- Purok fills follow the hazard-levels spec, citywide, and stay per purok at every zoom;
  barangay borders are drawn as lines on top.
- **Tap** → the barangay under the tap is selected. Its panel shows, for the ticked
  types: the total in the period, each purok with its count and level, and a list of
  past events.
- **Pick a purok** (from the panel list, or by tapping it again on the map) → the panel
  shows that purok's history only, with "‹ San Roque" to go back.
- `GET /api/history/area/?barangay=<id>[&purok=<id>]&types=Fire` (public): `{count,
  level, thresholds, puroks: [{id, name, count, level}] (barangay only), events:
  [{date, type, property_category, property_subcategory, alarm_level,
  structures_affected}]}`. Staff also get `location_text` and `damage_cost`.
- A barangay's history = records whose `barangay` is it, plus records with a purok in it,
  each counted once.

### 7. Fire history and the BFP export (added 2026-10-26)

A closed fire is one BFP row: the report gave columns A–F (date, time, place), and the
close form gives the rest (G onward). The history page and the export show it that way.

**The close form**, for the officer:

| Field | Notes |
|---|---|
| Property type | Category, then the sub-categories for it (the BFP list) |
| Injured | Firefighter male / female, civilian male / female |
| Fatalities | Firefighter male / female, civilian male / female |
| Estimated cost of damage (PHP) | |
| Affected structures | |
| Alarm level | The BFP list |
| What happened | Optional summary |

- Alarm level, category and sub-category are required.
- The counts and the cost may be left blank for "not counted yet", which is not zero.
- The lists come from one backend module and are served by `GET /api/history/bfp-options/`.

**Everywhere a fire is resolved, it goes through the two steps.** The map's hazard panel
and the DRRMO "active zones" card show **Fire out** instead of "Resolve and archive". The
DRRMO dashboard lists fires waiting for figures, each with **Enter BFP figures**.

**History page.** A fire record also shows:
- alarm level
- property type
- injured and fatalities
- affected structures

Staff also see the exact location and the damage cost. Other hazards are unchanged.

**Export.** `GET /api/history/fires.xlsx` (DRRMO Officer, System Admin), with the history
page's date and barangay filters, downloads one sheet:
- **Header:** the BFP fire log's three header rows, with the same merged cells and words.
- **Rows:** one per fire, oldest first.
- **Columns A–W:**

  | Column | Content |
  |---|---|
  | A | Date |
  | B | Time of alarm, stored as the number HHMM and shown as HH:MM, as the BFP file does |
  | C–E | `Region_7`, `Cebu`, `Talisay_City_c` |
  | F | Exact location: the address as BFP typed it for imported fires; `PUROK X, PUROK Y, BRGY Z` for fires closed in the app |
  | G–H | Property category and sub-category |
  | I–T | Injured firefighter M, F, total; civilian M, F, total. Fatalities firefighter M, F, total; civilian M, F, total |
  | U | Damage (PHP) |
  | V | Structures |
  | W | Alarm |

- A blank count stays blank.
- The history page has an **Export fires (Excel)** button for staff. The export is
  logged, as the report prints are.

## Changes to the hazard-levels spec

| # | Hazard-levels spec | This spec |
|---|---|---|
| 1 | `purok_counts` counts records whose zone geometry intersects the purok | Counts through `HistoricalRecord.puroks`. A flood or landslide fills `puroks` from its polygon when resolved. This also counts imported BFP rows, which have no zone |
| 2 | Every hazard type is published from the panel | Fire is removed from the publish panel's types, and `HazardZoneCreateView` refuses Fire |
| 3 | `floor_for(geometry, hazard_type)` | Also `level_for_purok(purok, hazard_type)` for the decision dialog |
| 4 | Pins only | Pins only, plus related-pin badges, the barangay → purok tap behaviour, and per-purok colours at every zoom |

## Importing the BFP fire log

`manage.py import_bfp_fires <file.xlsx> [--dry-run]`, following
`2026-10-23-purok-fire-data-design.md` (dates, alarm → level, casualties rule,
`source_ref`, address linking), with these differences:

- It writes the new `HistoricalRecord` fields above; `puroks` gets the linked purok, if
  any.
- Linking matches against the built `Purok` model (`name`, `kind`, `parent`) and
  `apps/barangays/aliases.py`. There is no `PlaceName` table; names that don't link are
  listed in the command's report and the fire counts at barangay level.
- The file the team shared on 2026-10-25 has 219 rows (26 Jan 2023 – 20 Sep 2026); five
  (rows 20–24) have text dates. All are in Talisay except one Toledo City row, which is
  skipped and listed. Rows 190 and 191 are identical in every column; an exact repeat of
  a row is imported once and listed as a duplicate.
- Purok reloads (`load_puroks`) must keep a purok's id when its name stays the same, so
  history links survive rebuilt estimates and the official lines. `import_bfp_fires
  --relink` re-links every imported record from its `location_text` after a reload.

## Errors

- A purok from another barangay → 400 *"That purok is not in Barangay X."*
- Barangay with no puroks → the purok field is optional; the fire counts at barangay
  level only.
- Level lookup fails in the dialog → Approve is disabled with *"Couldn't work out the
  level from history. Try again."*; the server still checks on submit.
- Decision race, stale attach → 409 as above.
- Close with no `alarm_level` → 400. Any other figure may be blank.

## Testing

- Backend (`backend/tests/`), in the style of the existing tests:
  - decide: approve at the puroks' history level (a sent level ignored), Red held
    for a second officer, attach (geometry grows, new barangay alerted, level raised),
    reject without a note refused, already-decided 409, attach to a closed zone 409;
  - review endpoint refuses fire reports; manual create refuses Fire;
  - fire-out sends the all-clear and moves to Resolving; close writes exactly one record,
    `puroks` holds both puroks when the pins sit in two, blank figures stay null;
  - generic resolve PATCH refuses Fire zones;
  - import: the 2026-10-23 cases, plus `puroks` set when linked.
- Frontend (Jest): fire form fields and validation (at least one purok, at most 10, the
  start time refreshed when Fire is chosen), the close form's sub-category list follows the
  category, tracker steps for each status combination, related pins grouped by zone,
  panel switching between barangay and purok.
- Screenshots before handing over: the fire form, the decision dialog with a nearby fire,
  the map with related pins, the barangay and purok panels.

## Order of work

1. **Purok data cleanup** against the BFP log: fix spellings to the BFP's (e.g. Ebacan →
   Ibacan, Casare → Cassare), merge the "Tabunoc" entries into Tabunok, research
   locations for the 58 BFP place names that have none, rebuild the estimates, dry-run,
   then load to the shared database. Names that can't be found go on a list for the
   Barangay Hall. No guessed positions.
2. Model changes and `import_bfp_fires`. Change 1 below needs `HistoricalRecord.puroks`,
   and the import gives the levels real data to show.
3. The hazard-levels spec with the four changes above (agree them with its author first).
4. The fire flow: form, tracker, decision, fire out / close, map pins, history panel.

## Open questions

- The alarm levels above 4th alarm and TF Alpha: confirm the list with BFP.
- BFP column T: read as total people hurt or killed (2026-10-23 spec). Still to confirm
  with BFP.
