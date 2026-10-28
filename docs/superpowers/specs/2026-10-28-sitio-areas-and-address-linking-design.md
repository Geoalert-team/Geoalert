# Sitio areas and better address linking — design

Date: 2026-10-28
Status: draft for review
Branch: merge-scout

## Why

148 of the 255 history records (217 BFP fires, 26 floods, 12 landslides) link to no purok,
so they colour nothing on the map. Many of them do name a place:

| Records | Why they don't link today |
|---|---|
| 17 fires | They name a sitio that has puroks (Laray ×5, Kimba ×4, Tunga ×2, Calachuchi ×2, San Lucas, Molave, Ilang-Ilang, Pagtambayayong). The build hands a sitio's whole area to its puroks, so the sitio has no area of its own |
| 4 fires | They name a purok nobody has placed, whose sitio is placed (Purok Day Care → Greenville, Purok Alubati → Miramar, Bontory → Upper Mohon, Purok Pinya → Cambawog) |
| 3 fires | The address names no barangay (Sitio Napo; Sitio Iba, Purok Rambutan; Deca Homes Phase 3) |
| ~10 | They name a landmark (Mohon Barangay Hall, South Town Centre, Cebu South Medical Center, Lawaan 1 National High School, Evergreen Memorial Park, Mananga Bridge II) |
| ~35 | They name only a street (Nacario St., Uldog St., Burgos St.) |
| ~30 | They name a purok or sitio no source had placed. New research (below) places some of them |
| the rest | Barangay only ("BRGY LAGTANG") |

Research (2026-10-28) also showed how sitios lie on the ground. Addresses always nest:
"Purok Sambag, Sitio Laray", "Purok 7, Sitio Catican", "Purok Kamunggay, Lower
Mahayahay", and on Camp IV's own website "Purok Sambag, Sitio Proper". Laray's Wikimapia
outline (34 ha) holds all three of its mapped subdivisions. So a sitio is the larger
area and its puroks lie inside it.

## How this fits with the other specs

- **`2026-10-23-purok-boundaries-design.md`**: the estimated outlines, `purok_points.csv`
  and `load_puroks` stay as they are. This changes how the build treats a name that
  has a `parent`.
- **`2026-10-26-purok-history-map-design.md`**: its non-goal "sitios as groups of their
  puroks" is what this builds. Its colouring rule, panel and filters are unchanged. A
  sitio is one more area that past events can count in.
- **`2026-10-25-report-driven-fire-hazards-design.md`** and the BFP import (plan
  2026-10-25): the import and `--relink` keep their shape. Only the address linker gains
  rules.
- **The flood and landslide import** (teammate's, `apps/history/flood_landslide.py`): it
  uses the same linker (`split_address`, `find_purok`), so it gains the same rules. Its
  tests must keep passing unchanged.

None of these specs is edited. The only change to the teammate's code is one line in
`import_flood_landslide.py`: which file it loads the name index from.

## Decisions (agreed 2026-10-28)

| Question | Choice |
|---|---|
| Scope | Fires, floods and landslides that name a purok or sitio; landmarks; street-only addresses |
| Sitios | As on the ground: a sitio's outline goes around all of its puroks plus the part of it that no named purok covers |
| Names no source places | Search more. Where nothing places them, estimate from other clues (the subdivision or zone named in the same address, the roads in outage notices, neighbouring names) when the clue narrows it to about one area. Otherwise they stay at barangay level and go on the Barangay Hall list |
| Shared database and git | Nothing is loaded, relinked or committed until the user says so. The build runs locally, and how many records would link is shown from a dry run |

## Non-goals

- Official purok lines, which are still pending from the Barangay Hall.
- A database migration. Whether a sitio is a container is worked out from `Purok.parent`.
- Changing the colouring rule, the thresholds or the History page.
- The "Likely by month" view.

## Design

### 1. Research data

Edits to `backend/apps/barangays/data/puroks/`, using the confidence rules in `SOURCES.md`:

| Barangay | Name | Placed at | Confidence |
|---|---|---|---|
| Cadulawan | Purok Boongon | Candulawan Barangay Hall (OSM); CDN 2024 puts the hall in Purok Boongon | medium |
| Cadulawan | Sitio Mahayahay (new; parent of Upper and Lower Mahayahay) | Overture listing "Mahayahay, Candulawan", 90 m from the hall | medium |
| Cadulawan | Lower Mahayahay | Overture place "Mahayahay Manggahan", 200 m from its Purok Kamunggay | low |
| Bulacao | Sitio Kabanayan (new; parent of Upper and Lower Kabanayan) | Overture place "Cabanayan, Bulacao", with 5 more listings | medium |
| Bulacao | Lower Kabanayan (new) | Overture addresses (4) "Lower Kabanayan"; SunStar 2023 places it on Sta. Lucia Road | medium |
| Camp IV | Cambawog Upper | Overture listing "Cambawog, Camp 3" (the point lies in Camp IV) | low |
| Camp IV | Sitio Proper (new; parent of Purok Sambag) | Camp 4 Barangay Hall. "Proper" is the barangay centre, and camp4talisay.com puts the hanging bridge at "Purok Sambag, Sitio Proper" | low |
| Manipis | Camp 6 (new) | Manipis Elementary School, formerly Camp 6 Elementary School (OSM `old_name`, `addr:neighbourhood=Camp 6`) | high |
| Dumlog | Sitio Paglaom | Overture "Tulay sa Kinabuhi", Burgos St., "Sitio Paglaum, Dumlog" | low |
| Dumlog | Sitio Bahala (new) | Estimated: the Dumlog bank opposite Purok Isla Verde. Philstar 2025 names the two together as riverside communities; the flood log puts Bahala in Dumlog | low |
| San Roque | Sitio Ughay (moved) | Wikimapia place "Ughai Subdivision", with Overture "Ughai 2 Subdivision" and 4 listings | medium |

**New names with no place yet:** Manipis Sitio Langoyon (landslide log; ABS-CBN 2022;
CDN spells it Languyon), Camp IV Sitio Curba (landslide log; CDN 2021), Camp IV Purok
Saging, Cadulawan Purok Nangka (CDN 2024).

**New variants:**

| Barangay | Written as | Means |
|---|---|---|
| Dumlog | Sitio Paglaum | Sitio Paglaom |
| Poblacion | Marimar, Marimar Phase 2 | Sitio Miramar |
| Biasong | Joanna Homes | Palm River Subdivision (OSM "Joanna Legacy Homes", `alt_name` Palm River) |
| Tapul | Sitio Katikan | Sitio Catican (RPN 2026) |
| San Roque | Ughay 1, Ughai | Sitio Ughay |
| Manipis | Languyon | Sitio Langoyon |

**Barangay Hall list:** `needs_barangay_check.csv` keeps every name that is still unplaced,
along with what was searched.

### 2. The build: sitio first, then its puroks

`build_purok_estimates` splits each barangay in two passes.

1. **Sitio territory.** The barangay is split among its top-level names (names with no
   `parent`) and the unnamed areas, as today. A name with puroks grows from its own pin
   and all of its puroks' pins together, with a share sized for itself and all of them.
   It starts from its Wikimapia or OSM outline where one exists.
2. **Inside a sitio.** Its territory is split among its puroks (grown from their pins and
   outlines) and its own leftover (grown from its pin), sized by the houses in it. A
   purok that has puroks of its own repeats the step (Pagtambayayong → Cadicay → Grapes).

**Rough puroks.** A purok placed only from outage notices (`low`) whose pin lies outside
its sitio's outline is moved to the nearest point inside it. The outline is the better
evidence. A `medium` or `high` purok keeps its spot, and the sitio grows to take it in.

**Output.** The sitio's feature is its whole territory (`kind` from the CSV). Its puroks'
features lie inside it, with `parent` set as today. The leftover is not a feature of its
own: it is the part of the sitio that none of its puroks cover. The purok count rule
(official sitio count, else households ÷ 175) still counts the names that are nobody's
parent. A sitio's leftover takes one of the shares, which leaves one fewer unnamed area.

**No researched name is lost.** Today a pinned name can end up with "no area left"
(Molave, Lagtang). Every pinned name must come out with an area. When two names start on
the same spot, the rougher one moves to the nearest free house cluster.

**Place lookup.** The build also writes `place_areas.csv`
(`barangay,place,kind,area,share`) from the OSM data it already downloads:

- **landmarks** (schools, halls, hospitals, malls, churches, cemeteries, bridges): the
  area its point falls in
- **streets:** the area that holds the largest share of the street's length inside the
  barangay, with that share

It is generated, so nobody edits it by hand.

### 3. Linking an address

`apps/history/bfp_link.py`, in order:

1. **Splitting.** `;` separates places as `,` does. A leading house number is dropped
   ("100 Art Ville" → "Art Ville"). An "Upper"/"Lower" part that names a place in the
   barangay ("Upper Mohon", "Lower Kabanayan") stays a place and doesn't count as the
   barangay.
2. **Purok first,** as today: Purok-labelled parts first, then the others, through the
   variants.
3. **Unplaced → its sitio.** A part naming a researched name that has no area links to
   its nearest placed ancestor (from `purok_points.csv`'s `parent`). "Purok Macopa,
   Laray" → Sitio Laray; "Bontory, Upper Mohon" → Upper Mohon.
4. **Landmark.** A part naming a landmark in that barangay links to the area in
   `place_areas.csv`. "Barangay Hall, Mohon" means Mohon's barangay hall.
5. **Street.** An address that names only a street links to its area when that area holds
   at least ¾ of the street's length in the barangay. Otherwise it stays at barangay level.
6. **No barangay.** When no part names a barangay, the barangay is the only one that has
   one of the named places (Sitio Napo → Tapul; Sitio Iba is in two barangays but Purok
   Rambutan is only in Lawaan II → Lawaan II). If none or several do, the record is
   unplaced, as today.

The import report keeps listing what didn't link, and now says which rule linked each
record (purok, sitio, landmark, street).

### 4. The map and the counts

- **`GET /api/barangays/puroks/`** adds `members` to each feature: how many puroks name
  it as `parent`. 0 for an ordinary purok.
- **Purok lines:** a sitio with members gets a thicker line and no fill of its own.
  Hovering its leftover names it, and its tooltip says how many puroks it holds.
- **Past hazards:** a sitio's fill goes in a pane under the purok fills. The sitio's
  colour shows through wherever a purok inside it has none of its own.
- **Hover, click and pins** (`purokAt`): the smallest area under the point wins, so the
  purok wins and the sitio only shows on its leftover.
- **Barangay panel and History page:** a sitio is one row like any purok. It counts only
  the records linked to it, not its puroks' records.
- **Resolved flood and landslide zones** (`overlapping_puroks`): only areas with no
  members count, so a zone never counts twice through a sitio.
- **The report form's purok list** includes sitios, since a resident may know only "Laray".

### 5. Checks before anything is loaded

- Tests first for:
  - every linker rule
  - the two-pass split: a sitio's territory holds its puroks, and no pinned name is lost
  - `place_areas.csv`
  - `members` in the API
  - `purokAt`'s smallest-area rule and the fill order
- The existing backend and frontend tests pass, the flood/landslide import tests included.
- The build runs locally. Its log lists each barangay's named, sitio and unnamed areas,
  and any lost names (there should be none).
- A dry run gives, by rule, how many of the 148 records would link, read from the new
  GeoJSON and `place_areas.csv` instead of the database.
- Not done until the user says so: `load_puroks`, `import_bfp_fires --relink`, re-running
  the flood/landslide import, and any commit.
