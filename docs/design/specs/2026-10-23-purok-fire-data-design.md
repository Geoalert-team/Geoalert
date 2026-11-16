# BFP fire data at purok level, with estimated boundaries — design

Date: 2026-10-23
Status: draft for review
Branch: merge-scout

## Why

The BFP Talisay City Fire Station gave us its fire log (`Fire data 2021-2026.xlsx`). It
places each fire by a typed address, not coordinates, and the useful part of most
addresses is the purok or sitio. GeoAlert only knows barangay boundaries (the 22 PSGC
polygons in `apps/barangays/data/talisay_barangays.geojson`). There is no public purok
boundary data for Talisay: OpenStreetMap has about 50 named places inside the city,
almost all of them single points, and only one numbered purok ("Purok 5", Biasong).

The team is asking the LGU for real purok boundaries (CBMS household geotags, barangay
sketch maps). Until they arrive we want the fire log on the map at purok level using
estimated boundaries, built so each estimate can be swapped for the real outline later
without re-importing anything.

## What the BFP file holds (checked 2026-10-23)

- One sheet, three header rows (merged cells), 219 incidents from 26 Jan 2023 to 2026.
  The file name says 2021, but the rows start in 2023.
- Columns A–W: date, time of alarm, region, province, city, **exact location**, property
  category and sub-category, injured and fatalities (firefighter / civilian, male /
  female, totals), estimated damage (PHP), structures affected, alarm level.
- Dates are mostly Excel serial numbers. Rows 20–24 hold text instead
  (`JULY 16,2023`, time `1158H/16 JULY 2023`).
- Alarm values: `1ST ALARM`, `2ND ALARM`, `3RD ALARM`, `TF ALPHA`,
  `FIRE OUT UPON ARRIVAL`, `UNRESPONDED`.
- Casualty columns are filled inconsistently. The breakdown totals (K, N, Q) are always 0
  even when a male/female cell is 1, and column T ("civilian fatalities total" by the
  header) holds 1 whenever anyone at all was hurt. Column T is read as **total people
  hurt or killed**; this needs confirming with BFP (see Open questions).
- Exact location is free text, roughly `<place>[, <place>], <barangay>, Talisay City, Cebu`:

  | Kind of place named | Rows | Examples |
  |---|---|---|
  | "Purok …" | 42 | `PUROK SAMBAG, LARAY, BRGY SAN ROQUE` |
  | "Sitio …" | 36 | `Sitio Tabay, Pooc, Talisay City, Cebu` |
  | Name with no label | ~65 | `Laray, San Roque`, `Kimba, Cansojong`, `Lahara, Lagtang` |
  | Street or road | ~35 | `Rabaya St.`, `SRP`, `N. Bacalso Ave.` |
  | Subdivision or compound | ~14 | `Kishanta Subdivision`, `Deca Homes Phase 2` |
  | Barangay only | ~23 | `BRGY DUMLOG`, `Mohon, Talisay City Cebu` |

- The barangay can be read in 214 of 219 rows. It is spelled several ways (`Tabunok`,
  `Lawa-an 1`, `Camp 4`, `Candulawan`), and a few are misspelled (`Poblacio`, `Casojong`).
  The barangay is always the **last** barangay-like part: in
  `Purk Ilang-Ilang, San Roque, Linao` the barangay is Linao and San Roque is a sitio.
- Place names repeat across barangays (Purok Sambag is in both Camp IV and San Roque),
  so a place is only unique inside its barangay. Spellings vary (`Kamungay`/`Kamunggay`,
  `Paglaom`/`Paglaum`, `Ilang-Ilang`/`Ilan-ilang`).
- Some addresses include house, block and lot numbers. They are kept for staff but never
  shown on the public map.

The companion hydrant file (`Consolidated Status Fire Hydrant 2026.xlsx`) has coordinates,
but they are wrong (latitudes 10.25–12.36, longitudes 123.06–125.77; Talisay is about
10.23–10.34 N, 123.78–123.87 E). It is out of scope here.

## Goals

- Import the BFP log as fire `HistoricalRecord`s that link to a purok where the address
  allows, and to the barangay otherwise. Re-running the import adds only new rows.
- Barangay staff and DRRMO add their puroks and drop one pin each. Each barangay is then
  split into estimated purok areas automatically.
- Staff review the place names found in the fire log and link each one to a purok, mark
  it as another purok's spelling, or mark it as not an area (street, landmark).
- The public map shows purok areas with fire counts, clearly marked as estimated, and
  places past fires in their purok rather than at the barangay's middle.
- A real boundary replaces one purok's estimate at a time. The other estimates fill the
  rest of the barangay, and fire records stay linked throughout.

## Non-goals

- Geocoding individual addresses to exact points (streets, house numbers).
- The hydrant file.
- Changing the barangay-level forecast (`apps/history/forecast.py`), Analytics or
  Reports. They keep counting by barangay; purok breakdowns can come later.
- Trimming estimated areas to built-up land (considered, not chosen for now).
- Nesting puroks inside sitios. Both are treated as peer areas of a barangay.

## Decisions taken in review (2026-10-23)

| Question | Choice |
|---|---|
| What the data is | Past incidents (BFP log), not risk ratings |
| Where purok locations come from | Pinned in the app, one pin per purok |
| How estimates are drawn | Nearest-pin split of each barangay (Voronoi in PostGIS) |
| Names without a Purok/Sitio label | Review list for staff; those fires stay at barangay level until linked |
| Who edits puroks | Barangay personnel for their assigned barangay; DRRMO and admins for any |
| Public map | Shows estimated areas and fire counts, marked "estimated"; never raw addresses |

## Data model

New in `apps/barangays/models.py`:

```python
class Purok(models.Model):
    """A purok or sitio inside one barangay: one pin, and an area that is either
    estimated from the pins or a real boundary from the LGU."""
    KIND_CHOICES = [('Purok', 'Purok'), ('Sitio', 'Sitio'), ('Area', 'Subdivision or other area')]
    SOURCE_CHOICES = [
        ('Estimated', 'Estimated from pins'),  # rebuilt automatically, never edited by hand
        ('Drawn',     'Drawn by staff'),
        ('Official',  'From LGU data'),        # sketch map, CBMS, CPDO
    ]
    barangay        = FK(Barangay, CASCADE, related_name='puroks')
    name            = CharField(100)           # as staff want it shown: "Purok Sambag"
    kind            = CharField(choices=KIND_CHOICES, default='Purok')
    pin             = PointField(null=True)    # must fall inside the barangay
    boundary        = MultiPolygonField(null=True)
    boundary_source = CharField(choices=SOURCE_CHOICES, default='Estimated')
    boundary_note   = CharField(300, blank=True)  # "Brgy sketch map 2026-11", "CBMS 2024"
    updated_by, updated_at
    # unique (barangay, name)


class PlaceName(models.Model):
    """One spelling of a place, as it appears in the fire log, inside one barangay.
    Turns BFP text into a purok, or records that it isn't an area."""
    STATUS_CHOICES = [('Unreviewed', ...), ('Linked', ...), ('Not_An_Area', ...)]
    barangay   = FK(Barangay, CASCADE, related_name='place_names')
    key        = CharField(100)   # normalized: "SAMBAG", "ILANG ILANG"
    label      = CharField(10, blank=True)  # 'Purok' / 'Sitio' if the log said so
    example    = CharField(200)   # first spelling seen, for the review list
    status     = CharField(choices=STATUS_CHOICES, default='Unreviewed')
    purok      = FK(Purok, SET_NULL, null=True, related_name='place_names')
    # unique (barangay, key)
```

Every purok also gets a `PlaceName` for its own name, so typing a purok in the app and
finding it in the log meet at one row.

Added to `HistoricalRecord` (`apps/history/models.py`), all nullable so existing rows and
the sample data are unaffected:

| Field | What it holds |
|---|---|
| `purok` | FK to `Purok`, `SET_NULL`; most specific place found, else empty |
| `location_text` | The address as BFP typed it. Staff only |
| `property_type` | `RESIDENTIAL / SINGLE AND TWO FAMILY DWELLING` |
| `damage_cost` | Decimal, PHP |
| `structures_affected` | Integer |
| `alarm_level` | `1ST ALARM`, `TF ALPHA`, … as given |
| `source_ref` | Unique import key; null for records made in the app |

## Import: `manage.py import_bfp_fires <file.xlsx> [--dry-run]`

Reads the sheet with `openpyxl` (added to `requirements/base.txt`), starting below the
three header rows and skipping rows with no location.

- **Date and time.** Excel serials or text dates; time from `HHMM` numbers or the
  `HHMMH/…` text form; local time `Asia/Manila`. A row whose date can't be read is
  reported and skipped.
- **Severity** from alarm level: `FIRE OUT UPON ARRIVAL`, `UNRESPONDED` and `1ST ALARM` →
  Green (Low); `2ND ALARM` → Orange (Moderate); `3RD ALARM` and above, and every `TF …`
  task force alarm → Red (Extreme). Unknown values → Green, listed in the report.
- **Casualties**: the larger of column T and the sum of the male/female cells.
  `total_displaced` stays empty (not in the log).
- **Description**: `BFP: <property category> – <sub-category>, <alarm>`. No address.
- **`source_ref`**: `bfp:` + a hash of date, time and normalized location. An existing
  ref is skipped, so a later BFP file with the old rows in it only adds the new ones.
  If BFP corrects an address, the row comes in again as new (noted in the report).
- Each record is then linked (below). The command ends with counts: imported, skipped,
  linked to a purok, barangay only, no barangay, and the new review-list names per
  barangay.

## Linking an address to a purok

One function, `link_record(record)`, used on import and again whenever puroks or place
names change in a barangay. It reads only `location_text`, so it can be re-run any time.

1. Split on commas. Drop `Talisay City`, `Cebu` and blanks.
2. **Barangay** = the last part that matches a barangay name or alias. Aliases live in one
   table shared with `load_barangays` (`Tabunok`, `Camp 4`, `Lawa-an 1`, `Candulawan`, and
   the misspellings `Poblacio`, `Casojong`). A leading `BRGY`/`Barangay` is ignored. With no
   match the record keeps no barangay and is listed for review.
3. **Candidate places** = the parts before the barangay. Each is normalized: upper case;
   a leading `PUROK`/`PRK`/`PURK`/`SITIO` is removed and remembered as the label;
   punctuation and hyphens become spaces. Parts that are clearly not areas are dropped:
   block/lot/phase/cluster numbers, house numbers, and parts ending in `ST`, `AVE`, `RD`,
   `ROAD`, `HIGHWAY`, or equal to `SRP`.
4. Each remaining candidate finds or creates its `PlaceName` in that barangay. A new name
   the log labels Purok or Sitio also creates an unpinned `Purok` of that kind and is
   Linked to it, since the log already says what it is. A new name without a label
   stays Unreviewed.
5. The record's purok is the first candidate that resolves to a purok, **preferring
   Purok-labeled parts**: in `Sitio Libra, Purok Kamungay, Poblacion` the purok is
   Kamungay. If nothing resolves, `purok` is empty and the record counts at barangay
   level as it does today.

Merging spellings ("Kamunggay is the same as Kamungay") moves that `PlaceName` and its
fires to the kept purok and deletes the duplicate purok if it has no pin of its own.

## Estimating boundaries

`estimate_puroks(barangay)` runs inside the same transaction as any pin or boundary change
in that barangay, and from `manage.py estimate_purok_boundaries [--barangay NAME]`.

1. Take the barangay's puroks that have a pin and whose `boundary_source` is `Estimated`.
2. The free area = barangay boundary minus the union of its non-estimated (Drawn or
   Official) purok boundaries.
3. One pin: it gets the whole free area. Several: `ST_VoronoiPolygons` over all pins,
   extended to the barangay's envelope; each cell is intersected with the free area and
   given to the pin it contains.
4. Puroks with no pin keep no boundary. A purok whose cell comes out empty (its pin sits
   inside a real boundary) also gets none, and the pin screen warns about it.

Pins must fall inside their barangay, and two pins in one barangay must be at least 10 m
apart. Both are checked on save, with a plain message.

A barangay with one pinned purok is entirely that purok, which overstates it. The pin
screen says "Pin all of this barangay's puroks, including ones with no fires, or the
pinned ones will cover their neighbours' ground."

## Replacing estimates with real data

- **Drawn**: on the pin screen, staff outline one purok with the existing zone-drawing
  tools (`utils/drawnZone`, `utils/snap`). It is saved clipped to the barangay as
  `Drawn`, and the barangay is re-estimated around it.
- **Official, in bulk**: `manage.py load_purok_boundaries <file.geojson> --source-note "…"`.
  Each feature needs barangay and purok names in its properties. It matches existing
  puroks by `PlaceName` (so spellings in the LGU file resolve the same way), creates
  missing ones, sets `Official`, and re-estimates each barangay. `--dry-run` lists
  matches, new puroks and unmatched features. Shapefiles and KML are converted to GeoJSON
  first in QGIS.
- **Back to estimate**: removing a real boundary sets the purok to `Estimated` again.
- Fire records link to purok rows, never to shapes, so a boundary change needs no
  re-import. A record's place on the map moves with its purok.

## API

Public (`AllowAny`), like the barangay outlines:

- `GET /api/barangays/puroks/?years=5` → GeoJSON `FeatureCollection`, one feature per
  purok with a boundary. Properties: `id`, `name`, `kind`, `barangay`, `barangay_name`,
  `boundary_source`, `fire_count`, `last_fire_at`. No addresses and no records. Served
  through the existing map-version ETag (`utils/map_version.py`): any purok, place-name or
  fire import change bumps the version.

Staff (`Barangay_Personnel` for their `assigned_barangay`; `DRRMO_Officer`, `System_Admin`
for any):

- `GET /api/barangays/<id>/puroks/manage/`: puroks with pins, boundaries, source and fire
  counts, plus the Unreviewed place names with fire counts and up to three example
  addresses each.
- `POST /api/barangays/<id>/puroks/`: create (name, kind, pin).
- `PATCH /api/barangays/puroks/<pk>/`: rename, change kind, move the pin.
- `DELETE /api/barangays/puroks/<pk>/`: its fires fall back to barangay level, and its
  place names go back to Unreviewed.
- `PUT` / `DELETE /api/barangays/puroks/<pk>/boundary/`: set a Drawn boundary, or go back
  to Estimated.
- `POST /api/barangays/place-names/<pk>/resolve/` with `{"action": "link", "purok": id}`,
  `{"action": "new_purok", "kind": "Sitio", "pin": …}` or `{"action": "not_an_area"}`.

Each write re-links that barangay's fire records and re-estimates its boundaries, then
returns the barangay's updated purok list.

`GET /api/history/heat/` places a record, in order of preference: at its archived hazard
zone (unchanged); at its purok's area (`point_on_surface`, radius from the extent, at most
300 m); at its purok's pin when there is no area yet (100 m); at its barangay's middle
(150 m, unchanged).

## Screens

- **Puroks page**, `/app/puroks`, under `Gate`. Barangay personnel land on their own
  barangay; DRRMO and admins choose one. The barangay map has a draggable pin per purok
  and live estimated areas (dashed) or real ones (solid). Beside it: the purok list (name,
  kind, fires, boundary source, "Draw real boundary") and the "Names from the fire log"
  review list (name, fires, example addresses, and Link to… / New purok / Not an area). A
  banner names how many puroks are unpinned. Linked from the dashboard module navigation.
- **Public map**: a "Puroks" toggle in `LayerControl`, on by default from zoom 15. Dashed
  outlines for estimated areas, solid for real ones, and labels at zoom 16+. Tapping one
  shows "Purok Sambag · San Roque · 4 fires since 2023 · Estimated boundary". In History
  view, purok areas are shaded by fire count in the Fire colour. The barangay panel gains a
  "Puroks" list with fire counts and the same estimated note.

## Testing

Backend, with the existing PostGIS test database:

- Address parsing table test over the real address shapes listed above: barangay is the
  last match, aliases and misspellings resolve, labels are read, streets and lot numbers
  are dropped, and Purok-labeled parts win.
- Import: serial and text dates, alarm → severity, casualties rule, a re-run is idempotent,
  dry-run writes nothing. Uses a small generated `.xlsx` fixture, not the BFP file.
- Estimation: one pin covers the whole barangay; cells tile the barangay with no gaps or
  overlaps (area sums match); a Drawn boundary is carved out and the estimates fill the
  rest; a pin outside the barangay is refused.
- Resolve actions re-link records; deleting a purok drops records to barangay level.
- Permissions: barangay personnel can't edit another barangay; the public endpoint has no
  addresses in it.
- Heat endpoint uses purok area, then pin, then barangay.

Frontend: unit tests for the purok style rules (estimated vs real) and tooltip text, in
the style of `forecastFilters.test.js`.

## Order of work

1. Models, migrations, address linking, `import_bfp_fires`, estimation, tests. The BFP log
   can be imported and checked from the command line.
2. Staff API and the Puroks page. Barangays can start pinning.
3. Public map layer, barangay panel list, heat placement.
4. `load_purok_boundaries` and drawing a real boundary, ready for the LGU data.

## Open questions

- Column T in the BFP log: total people hurt or killed, or civilian deaths as the header
  says? This changes the casualty numbers and whether a fatality should raise severity.
- Should the seeded sample fires (`seed_fake_hazards`) be cleared once the real log is in,
  so History and the heat shading aren't mixed? `--clear` already removes all samples.
- Vehicle fires on roads (`TRANSPORT`, mostly on the SRP) are counted like house fires.
  Leave them in, or leave them off the purok fire counts?
- The 5 rows with no barangay (e.g. `Sitio Napo, Talisay City Cebu`) and the Deca Homes
  rows are listed for staff, not guessed.
