# History-based hazard levels — design

Date: 2026-10-25
Status: draft for review
Branch: merge-scout

## Why

Today a DRRMO officer picks every alert's level by hand (Low, Moderate,
Extreme), and the public map shades two things at once: the inside of each
active hazard, graded by the ground like a Project NOAH map, and a "heat" built
from past events weighted by how severe and how recent they were. The levels
are a judgement call each time, and the map mixes live hazards with history.

The new rule: a place's level comes from how often it has been hit. Few past
events is green, more is orange, many is red. Active hazards are only pins.
When a hazard is resolved it becomes history and the colours update.

## Decisions (agreed 2026-10-25)

| Question | Choice |
|---|---|
| What stops being a manual choice | The alert level itself: it is set from history |
| Area that is counted | Purok |
| Hazard types | Counted separately (floods only count toward the flood level) |
| Thresholds | Last 5 years: 1–2 past events = Low, 3–4 = Moderate, 5+ = Extreme; 0 = no level. All three numbers adjustable by a System Admin in Settings |
| An area with little or no history | Starts at Low; the officer may raise the level, never lower it below what history says |
| A hazard covering several puroks | Counts toward every purok it overlaps; a new alert takes the highest level among them |
| An active hazard on the map | Pin only: no shading, no outline, no cordon hatching |
| Where the rule runs | Backend, counted on request (no new table) |

## Goals

- An alert's level can never be below what its puroks' history says, and the
  server enforces that, not just the publish panel.
- One place in the code holds the rule; the map, the publish panel and the
  server all use it.
- Resolving a hazard is all it takes for the purok colours to change.
- A System Admin can tune the period and the two thresholds without a deploy.

## Non-goals

- Changing what happens after publishing: second-officer approval for
  Extreme, notifications, reminders, cordons as data, the historical record
  fields and the reports that read them all stay as they are.
- Re-grading alerts that are already active when history changes.
- Official purok boundaries (the estimates in use today are kept).
- The "Likely by month" view and its forecast.
- Weighting events by severity or age within the period.

## Design

### 1. The rule (backend)

New module `backend/apps/history/purok_levels.py`, the only place the rule lives:

- `thresholds()` → `{'years': 5, 'moderate': 3, 'extreme': 5}` from the three
  settings below. If the stored values contradict each other (extreme ≤
  moderate), all three defaults are used.
- `level_for(count, t)` → `None` for 0, `'Green'` below `t['moderate']`,
  `'Orange'` below `t['extreme']`, otherwise `'Red'`. The values are the
  existing severity codes, so nothing downstream changes vocabulary.
- `purok_counts(types=None)` → `{(purok_id, type_name): count}`: historical
  records with `occurred_at` inside the period whose `hazard_zone.geometry`
  intersects the purok's boundary, one count per (record, purok) pair. A
  record whose zone has no geometry, or that has no zone, is not counted.
- `floor_for(geometry, hazard_type)` → `{'level': code, 'puroks': [{id, name,
  barangay, count, level}], 'thresholds': {...}}`: the puroks the drawn area
  intersects and the highest level among them; `'Green'` when none has any
  history (or the area touches no purok).

Only resolved hazards count, because only resolving creates a historical
record (`apps/hazards/views.py`, the PATCH that sets `Resolved`). Active,
awaiting-approval and retracted zones never count. That code is unchanged.

Ranking for "higher" and "lower": `Green < Orange < Red`, one helper
`rank(code)` in the same module.

### 2. Settings

Three entries added to `SETTINGS` in `backend/utils/system_settings.py`, so
they appear in Admin › Settings with the existing validation and caching:

| Key | Default | Range | Label |
|---|---|---|---|
| `history.period_years` | 5 | 1–20 years | History period for hazard levels |
| `history.moderate_at` | 3 | 2–50 events | Past events for orange (Moderate) |
| `history.extreme_at` | 5 | 3–100 events | Past events for red (Extreme) |

### 3. Endpoints

- `GET /api/history/purok-levels/?types=Flood,Fire` (public). Response:
  `{"thresholds": {...}, "results": [{"purok": id, "type": "Flood",
  "count": 3, "level": "Orange"}]}`. Puroks with 0 are left out. Without
  `types`, every type. Unknown type names are ignored.
- `POST /api/hazards/level-preview/` (DRRMO Officer and System Admin, the same
  permission as publishing). Body `{"hazard_type": id, "geometry": GeoJSON}`.
  Returns `floor_for(...)`. Invalid geometry → 400 with the same message the
  publish endpoint gives for it.

### 4. Publishing

- **Publish panel** (`frontend/src/components/Publish/PublishHazardPanel.jsx`):
  the Severity fieldset with three buttons is replaced by a "Level" block.
  Once a type is chosen and the area has at least a closed shape, the panel
  calls `level-preview` (debounced, ~400 ms after the last change) and shows:
  *"Moderate, from history: Purok Sambag, Laray had 3 floods in the last 5
  years."* With no history: *"Low: no floods recorded here in the last 5
  years."* Below it, "Raise level" offers only the levels above the floor (none
  when the floor is Extreme). While the preview loads, or if it fails, the
  panel says so and Publish waits; on failure it offers "Try again".
- **Create** (`HazardZone` create view, `apps/hazards/views.py`): the server
  computes the floor from the saved (city-clipped) geometry. No `severity` in
  the request → the floor. A `severity` below the floor → 400 *"Can't be lower
  than Moderate: this area's history sets it."* Equal or higher → used.
  Everything after (Extreme approval hold, notifications, cordon, audit) is
  unchanged and sees the final level.

### 5. Editing an active hazard

- **Change severity** (PATCH with `severity`): allowed above or down to the
  floor of the zone's current geometry; below it → the same 400. The
  existing hold for a raise to Extreme is unchanged.
- **Edit area** (PATCH with a new geometry): the floor is recomputed for the
  new shape. If it is above the current level, the level is raised to it in
  the same request, through the same path as an officer's raise, so a raise to
  Extreme is held for a second officer like any other.
- History changing (another hazard resolved nearby) does not touch active
  alerts.

### 6. The map (`frontend/src/pages/PublicMap.jsx`)

- **Views**: the switcher becomes **Past hazards** (default) and **Likely by
  month**. "Active hazards" and "History" go.
- **Past hazards**: every purok with a level is filled in its colour, citywide,
  for the hazard types that are ticked; with several ticked, the highest level
  among them. Hovering names the purok and lists its counts per type, e.g.
  *"Purok Sambag, Laray: 3 floods (Moderate), 1 fire (Low)"*. Puroks without
  history are not filled. Data: `/api/barangays/puroks/` (already used) plus
  `/api/history/purok-levels/`, refetched when the map refreshes its hazards.
- **Active hazards**: pins only, coloured by alert level; tapping a pin opens
  its panel as now. The public map no longer draws the graded live shading,
  the zone outlines or the cordon hatching. While a staff member is publishing
  or editing an area, the draft outline and cordon preview still show.
- **Legend**: the three colours with the current thresholds (*"1–2 · 3–4 · 5+
  past events in the last 5 years"*) and *"Pins: active hazards, coloured by
  alert level"*.
- **Removed**: the live grading and history heat in
  `components/Map/hazardLevels.js` (its `HAZARD_LEVELS` colours move to where
  the legend needs them), the `ImageOverlay` level pane, the public
  `CordonLayer` and zone-outline layers (the cordon style helpers stay for the
  draft preview), `historyApi.heat` and `HistoricalHeatView`
  (`/api/history/heat/`), which nothing else uses. The susceptibility rasters
  stay: the Layers panel and `seed_fake_hazards` read them.

## Errors

- Settings unreadable or contradictory → defaults (as every setting does).
- `purok-levels` fails → the map shows pins and a small note *"Past-hazard
  colours couldn't load."*; pins are unaffected.
- `level-preview` fails → Publish is disabled with *"Couldn't work out the
  level from history. Try again."*; the server check still applies on publish.
- No puroks loaded (empty table) → every floor is Low and the map has no
  fills; publishing still works.

## Testing

- Backend (`backend/tests/`), `SimpleTestCase` with the database patched out
  as the existing tests do: `level_for` at each boundary, `thresholds()`
  fallback on bad settings, `floor_for` taking the highest purok and Low with
  no history, the create view using the floor when no severity is sent and
  rejecting one below it, PATCH severity below the floor rejected, an area
  edit raising the level (and holding a raise to Extreme).
- The spatial count itself needs PostGIS, so it gets one test against a real
  query only if a throwaway database is available; otherwise it is checked by
  hand on the dev database with `seed_fake_hazards` data and the result
  written into the plan's notes.
- Frontend (Jest): the publish panel shows the preview text, offers only
  higher levels, and blocks Publish while loading or failed; the map's purok
  shading picks the highest level among ticked types and builds the tooltip.
- Screenshots of the map (signed out, and publishing as an officer) before
  handing over.

## Notes

- History is empty right now (cleared 2026-10-25), so after this ships every
  floor is Low and the map has pins only until hazards are resolved, or
  `seed_fake_hazards` is run to fill sample history.
