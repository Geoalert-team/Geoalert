# Purok history on the map — design

Date: 2026-10-26
Status: draft for review
Branch: merge-scout

## Why

The map's "History" view draws each past event as a round spot: at its hazard zone if it
kept one, otherwise at the middle of its barangay. Of the 220 records today (all fires),
3 have a zone, so 217 spots sit on barangay centres and the shading follows no purok.
103 of those fires already name a purok (82 puroks in all), but nothing on the map
reads that link. Tapping a barangay shows only its active hazards, not its history.

## How this fits with the other specs

This builds what two agreed specs describe and adds the History page filter. Neither
file is edited.

- **`2026-10-25-history-based-hazard-levels-design.md`** (teammate's): section 6, "The
  map", in full, and the purok counting of section 1. Its publishing sections (4 and 5)
  are not part of this.
- **`2026-10-25-report-driven-fire-hazards-design.md`**: section 6, "Barangay and purok
  history", and amendment 1 (counting through `HistoricalRecord.puroks`).

## Decisions (agreed 2026-10-26)

| Question | Choice |
|---|---|
| Scope on the map | The hazard-levels spec's whole map section: **Past hazards** (default) and **Likely by month**; "Active hazards" and "History" go |
| Purok colour | Count of past events in the period: 1–2 Low, 3–4 Moderate, 5+ Extreme (the existing `history.*` settings), per type; with several types ticked, the highest. 0 = no fill |
| Active hazards | Pins only, coloured by alert level. No live shading, zone outlines or public cordon hatching. The staff draft outline and cordon preview stay |
| Barangay → purok | Tap a barangay: its whole history. Pick a purok (panel list, or tap it again on the map): that purok only, with "‹ San Roque" back |
| Where | The map's barangay panel and the History page |
| Records with no purok | Counted in the barangay's total and listed as "Purok not recorded"; they colour no purok |
| A barangay's history | Records whose `barangay` is it, plus records with a purok in it, each counted once. The same rule in the map panel, the hazard panel's "Area disaster history" and the History page (trends and the forecast keep filing by `barangay`) |
| Period | Map colours, panel counts and the panel's list: the `history.period_years` setting (5). The History page: all time, with its date filters |
| Floods and landslides | Resolving one links its record to every purok its shape overlaps (sharing only a border doesn't count) |

## Non-goals

- Publishing: the level floor when an officer publishes or edits (hazard-levels spec
  sections 4 and 5). Fires already take their level from history at approval.
- Official purok lines; sitios as groups of their puroks ("Sitio Laray" stays a label on
  Purok Sambag and others, not an area of its own).
- Backfilling old floods and landslides: there are none in the history today.
- The "Likely by month" view and its forecast.

## Design

### 1. Backend

**`GET /api/history/purok-levels/?types=Flood,Fire`** (public). As in the hazard-levels
spec: `{"thresholds": {"years", "moderate", "extreme"}, "results": [{"purok", "type",
"count", "level"}]}`, puroks with 0 left out, unknown type names ignored, every type
without `types`. Counted through `HistoricalRecord.puroks` in the period, one count per
(record, purok). The rule stays in `apps/history/purok_levels.py`.

**`GET /api/history/area/?barangay=<id>[&purok=<id>|none]&types=Fire`** (public). As in
the fire spec, in the period:

```
{ "count", "level", "thresholds",
  "purok": {"id", "name", "parent"},                        purok or none only, else null
  "puroks": [{"id", "name", "parent", "count", "level"}],   barangay only, count > 0
  "unplaced": 16,                                           barangay only: no purok
  "events": [{"id", "date", "type", "property_category", "property_subcategory",
              "alarm_level", "structures_affected", "puroks": [names]}] }
```

Staff (DRRMO Officer, System Admin) also get `location_text` and `damage_cost` per event.
`purok=none` returns only the records with no purok. `period=all` counts all time instead
of the period (the History page uses it). `level` is the purok's level in a purok view, the
highest among the barangay's puroks in a barangay view, and null for `purok=none`; each
type is counted on its own, so 2 fires and 2 floods are Low, not Moderate. A purok from another barangay → 400
*"That purok is not in Barangay X."* An unknown barangay → 404.

**History list (`GET /api/history/`)**: `?barangay=` uses the barangay rule above
(records whose `barangay` is it, or with a purok in it, `distinct`); new `?purok=<id>`
and `?purok=none` (needs `barangay`). The hazard panel's "Area disaster history" reads
this list, so it follows the same rule with no change of its own.

**Resolving a flood or landslide** (`HazardZoneDetailView.patch`, where it creates the
`HistoricalRecord`): set `record.puroks` to the puroks whose boundary overlaps the zone's
geometry (`ST_Intersects` and not `ST_Touches`). Fires keep their own close path.

**Removed**: `HistoricalHeatView` and its `heat/` route.

### 2. The map

- **Views**: Past hazards (default) and Likely by month. The Legend and the Layers
  panel's type checkboxes apply to Past hazards as they do today.
- **Purok fills** (new `components/Map/PurokHistoryLayer.jsx`): every purok with a level
  for the ticked types is filled in its colour, citywide, at every zoom, in a pane under
  the barangay lines. Hovering any filled purok (tap on a phone) names it and lists its
  counts: *"Purok Sambag · Sitio Laray, San Roque: 2 fires (Low)"*. The fills aren't
  clickable, as `PurokLayer` does today, so barangay clicks and the drawing tools keep
  working. Data: `/api/barangays/puroks/` (already loaded) plus `purok-levels`, refetched
  when the map refreshes its hazards.
- **Level helpers** (new `components/Map/purokLevels.js`): the three level colours and
  labels (moved out of `hazardLevels.js` for the legend), the highest level among the
  ticked types, and the hover text. Pure functions, tested with Jest.
- **Active hazards**: pins only, coloured by alert level, as fire pins are today. The
  `ImageOverlay` level pane, the zone outlines and their Layers toggle, and the public
  `CordonLayer` go. `CordonLayer`'s style helpers stay for the staff draft preview.
- **Selecting**: the first tap selects the barangay. While it is selected, a tap on one
  of its puroks selects that purok (and still moves the spot reading). A tap in another
  barangay selects that one. The selected purok gets a bold outline.
- **Legend**: the three colours with the thresholds, *"1–2 · 3–4 · 5+ past events in the
  last 5 years"*, and *"Pins: active hazards, coloured by alert level"*. The cordon row
  goes.
- **Removed from `hazardLevels.js`**: the live grading and the history heat
  (`useHazardLevelLayer` and what only it uses); `historyApi.heat`. The susceptibility
  data stays: the Layers panel and the spot reading read it.

### 3. The barangay panel

`BarangayPanel` keeps its active-hazards section and gains a history section (new
`components/Map/AreaHistory.jsx`) fed by `/api/history/area/` for the ticked types:

- **Barangay**: *"21 fires in the last 5 years"*, then each purok that has history, with
  its level colour, name and count, most first (ties by name); then *"Purok not recorded
  · 16"*; then the past events, newest first, five at a time with "Show more".
- **Purok** (from a row, or a map tap): *"‹ San Roque"*, the purok's name and level, its
  count, and its events. "Purok not recorded" opens the same view for `purok=none`.
- Loading and failure are shown in the section only; the active hazards above are
  unaffected.

### 4. The History page

Once a barangay is picked, a **Purok** dropdown appears: *All puroks (21)*, each purok
with a history count (*Purok Sambag (2)*), and *Purok not recorded (16)*. Picking one adds
`purok` to the list request. Changing the barangay resets it to All puroks. The counts
come from `/api/history/area/?barangay=<id>&period=all` for that barangay, all types,
ignoring the date filters; the list itself still honours them.

## Errors

- `purok-levels` fails → pins still show, with the small note *"Past-hazard colours
  couldn't load."*
- `area` fails → the panel's history section says *"Past records couldn't be loaded.
  Try again."* with a retry; the History page's Purok dropdown is hidden.
- No puroks loaded → no fills; the barangay panel shows the barangay totals with
  everything under "Purok not recorded".
- Settings unreadable or contradictory → the defaults (as `thresholds()` does today).

## Testing

- Backend (`backend/tests/`), in the style of the existing tests: `purok-levels` counts
  per type and leaves out zeros; `area` for a barangay (puroks, unplaced, a record both
  filed under the barangay and linked to one of its puroks counted once), for a purok,
  for `purok=none`, the other-barangay 400, staff-only fields; the list's barangay rule
  and `purok` filter; resolving a flood links the puroks it overlaps and not one it only
  touches.
- Frontend (Jest): highest level among ticked types, no fill at 0, the hover text, the
  panel switching between barangay and purok, the History page's Purok dropdown.
- The real app: the map signed out (fills match purok shapes, San Roque's panel and a
  purok in it) and the History page filter, checked against the counts in this doc.
