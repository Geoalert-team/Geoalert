# Purok boundaries on the public map — design

Date: 2026-10-23
Status: draft for review
Branch: merge-scout

## Why

The map draws the 22 barangay outlines, but the city's own records locate hazards at the
purok and sitio level. The fire incident log for 2021–2026 (`Fire data 2021-2026.pdf`)
gives places like "Purok Sambag, Laray, Brgy San Roque" or "Sitio Tunga, Purok Mamsa,
Tangke". Official purok boundaries
have been requested from the Barangay Hall but have not arrived. Until they do, the map
should show estimated purok outlines inside each barangay, clearly marked as estimates,
built so the official lines replace them with one command.

Investigation (2026-10-23) found that no purok or sitio boundaries are published anywhere:
PSGC data, including altcoder/philippines-psgc-shapefiles, stops at barangay level (our
`talisay_barangays.geojson` already comes from it); OpenStreetMap maps sitios as points,
not areas, and has no admin_level 11 areas in Talisay; the city's 2003 barangay
administrative maps show barangay lines only. So the outlines have to be estimated, from
where puroks are and where people live.

## Decisions (agreed 2026-10-23)

- Purok, sitio, zone and named-subdivision areas all go on one flat layer. Where a purok
  is known to sit inside a sitio ("Purok Sambag, Laray"), the sitio is recorded as its parent.
- The fire log is used only as a list of place names to look up. No fire records are imported.
- Each area grows from a researched point; edges follow roads, creeks and ridges; each
  area holds about its share of the barangay's houses.
- Names that can't be placed are left off the map and listed for the Barangay Hall to pin.
- Names known only from a road list are split into individual areas, ordered by evidence
  (section 1, step 4), not drawn as one group.
- Purok boundaries live in the database, loaded from GeoJSON, like barangays.
- The layer is shown to everyone, on by default, labelled as estimated.

## Goals

- Every researched purok with a known position has its own outline inside its barangay.
- Outline edges follow features real purok borders follow: main roads, creeks, ridges and
  the gaps between house clusters.
- Purok sizes reflect the barangay's purok count and where its houses are.
- Every point records how it was placed and how confident that is, and the file is easy
  to correct by hand.
- Swapping in official boundaries, for one barangay or all, is one command, and reports
  how far the estimates were from the official lines.

## Non-goals

- Importing the fire records, or using puroks in alerts, analytics or forecasts (a follow-up
  can use PostGIS to put a hazard or fire in a purok once this exists).
- Correcting the barangay outlines themselves. The city's land areas differ from our
  outlines (Jaclupan 1,404 ha official vs 397 ha drawn; Camp IV 975 vs 545), so the
  Barangay Hall request should cover barangay borders too.
- Drawing a full two-level sitio/purok hierarchy. A parent sitio is drawn only when a real
  community outline exists for it; otherwise it only appears in its children's labels
  (section 2, step 5).
- A screen for editing points in the app. The CSV is edited by hand.

## Evidence behind the choices

**Purok and sitio names found: 276 across all 22 barangays.**

| Source | What it gave |
|---|---|
| Fire incident log 2021–2026 (supplied by the team) | ~150 names with barangay |
| City of Talisay 2010 Barangay Profiles (archived PDFs, talisaycitycebu.gov.ph via Wayback) | Official sitio counts for 8 barangays, land areas, households, a few names |
| Visayan Electric outage notices (148, 2024–2026) | ~130 names, each with barangay and the roads it lies along |
| Wikipedia revisions of 2017 barangay articles | Sitio lists for Cansojong (12) and Lawaan II (9) |
| DSWD DROMIC fire reports for Talisay (19) | 9 named sitios and puroks |
| Wikimapia (1,538 places, public API key) | 19 sitio outlines drawn by local users |
| OpenStreetMap | Place points, named subdivisions with outlines, 665 named streets, landmarks |
| PhilAtlas (PSA census) | Households 2015 and population 2020 for all 22 barangays |

**Official sitio counts (2010 profiles):** Cansojong 26, Tabunok 22, Lawaan II 14, Pooc 12,
Camp IV 9, Jaclupan 9, Maghaway 6, Candulawan 5. The median is about 175 households per
sitio (2015 households). The range runs from 76 (Camp IV, upland) to 272 (Maghaway).

**Placing the names:** about 25 match a Wikimapia or OSM place in the same barangay, and
11 match a street named after them (Galaxy St., Lahara St., Molave St., Salvador St.).
About 127 are known only from outage notices, which list several sitios against a few
roads. Of those, 82 appear in two or more notices: for 71 the notices narrow the road, and
for 75 the sitios listed alongside them change from notice to notice. That narrowing and
ordering (section 1, step 4) is what lets road-listed names be split individually.

**Houses:** OSM has about 6,300 buildings in Talisay against about 57,000 households (1–59%
per barangay), too uneven to size anything. Microsoft's Global ML Building Footprints have
about 30,700 (0.5–0.8 per household in most barangays; Jaclupan 0.21 under tree cover).
They are a sound guide to *where* houses are within a barangay, which is all the sizing
uses.

## Design

### 1. Research data, committed as hand-editable files

New folder `backend/apps/barangays/data/puroks/`:

- `purok_points.csv`: one row per name. Columns are barangay, name, kind
  (purok / sitio / zone / subdivision), parent, lat, lng, placed_by, confidence
  (high / medium / low), sources and note. Rows with a blank lat/lng are the "still to
  pin" list. A row whose placed_by is `manual` is never overwritten.
- `barangay_counts.csv`: one row per barangay. Columns are official_sitios,
  official_source, households_2015, purok_count and basis (the rule in section 2 that
  produced the count).
- `notices.json`: the Talisay-only Visayan Electric notices, reduced to url, date,
  barangays, roads and names. Notices that also cover another city are kept with
  `shared: true` and used only for road narrowing, never to assign a barangay.
- `community_outlines.geojson`: the Wikimapia sitio outlines and OSM subdivision
  outlines, with source and licence on each feature.
- `SOURCES.md`: every source, its URL, date accessed and licence.

The raw scraped pages are not committed, and the one-off research scripts are not part
of the app.

**Name cleanup.** Spelling variants merge into one name: Kamungay/Kamunggay,
Paglaom/Paglaum, Atisan/Antisan, Ibacan/Ebacan, Rattan/Ratan, Ughay/Ughai,
Candulawan/Cadulawan, Tabunok/Tabunoc. The same name in two barangays is two places
(Mahayahay is in four). Streets, roads, highways and single buildings are anchors, never
areas. Company names in the notices are dropped.

**Placement.** Each name takes the first step that places it. Its placed_by and
confidence are recorded.

1. **Its own place (high).** A Wikimapia or OSM place or outline with that name inside the
   barangay, or a landmark named after it ("Sitio Letmon Chapel", "Camp 8 Elementary
   School", "Sitio Balut Basketball Court").
2. **Its own street (medium).** A street named after it ("Galaxy St." for Sitio Galaxy), or
   the street in a fire-log or DROMIC address that names this place ("Rabaya St., Kimba").
   The point is the middle of that street's stretch inside the barangay.
3. **A clue in the name (medium).** "Upper X" is placed at the higher end of X's road, and
   "Lower X" at the lower end, using the elevation grid. "Proper" and "Centro" go near the
   barangay hall.
4. **Outage notices (low).**
   - *Narrow the road:* keep the roads that every Talisay-only notice listing the name
     agrees on, inside its barangay.
   - *Order along it:* two names are neighbours in proportion to how many small notices
     (5 names or fewer) list them together. The names sharing a road are put in the order
     that keeps neighbours next to each other (a greedy chain from the strongest pair).
   - *Snap to houses:* split the houses within 60 m of that road stretch into as many
     clusters as there are names, at the widest gaps, and give each name a cluster in
     order. Which end comes first is set by any name in the chain already placed by
     steps 1–3. If none is, by Upper/Lower. If neither applies, the row is flagged
     `order unknown`.
   - Names that never separate from each other are spaced evenly along the stretch and
     flagged `position along road approximate`.
5. **Not found.** No lat/lng, listed for pinning.

A point that lands outside its own barangay is a conflict. It is left blank and noted, for
example "Iba: fire log says Lawaan II, OSM puts it in Lagtang".

**Parents.** Where a source writes "Purok X, Sitio Y", X's parent is Y.

### 2. Building the estimated outlines (backend)

New command `python manage.py build_purok_estimates [--barangay NAME] [--refresh]`. It
writes `talisay_puroks_estimated.geojson` next to the CSVs. It reuses the hazard build's
grid and downloads from `apps/hazards/susceptibility.py` (Grid at zoom 14, about 9 m
cells; Copernicus elevation; OSM waterways and roads; DEM-derived streams; all cached in
`backend/.hazard_cache/`). It adds one download: the Microsoft footprints tile covering
Talisay (quadkey 132330002, about 31 MB), cached the same way. Only building centres are
kept.

**How many puroks each barangay has (N):** the official count where one exists, otherwise
households ÷ 175. It is never fewer than the leaf names found for that barangay (names
that are nobody's parent), placed or not. The basis is written to `barangay_counts.csv`.

**Per barangay, on its window of the grid:**

1. **Fixed areas first.** Community outlines in the barangay are rasterised and claimed by
   their own name. Nothing else may enter them.
2. **Crossing cost of each cell, as metres of walking:**
   - cells with houses, or on a minor street: 1×;
   - cells with no house within 50 m: 2×;
   - entering a main-road cell (OSM trunk, primary, secondary): +150 m;
   - entering a waterway cell (OSM rivers, streams, canals and DEM-derived streams): +200 m;
   - climbing: +10 m per metre of rise.

   These are starting values, named constants at the top of the module, to be tuned by eye
   and then against the first official barangay (section 4).
3. **Growth.** All placed points of the barangay grow at once, a multi-source Dijkstra over
   8-connected cells. Each cell goes to the point that reaches it most cheaply.
4. **Stopping.**
   - Each point stops once it holds its share of houses: the barangay's building count
     divided by N. Unplaced names count in N, so their share of houses stays unclaimed and
     blank.
   - A point also stops at 1.5 times its typical radius, √(barangay area ÷ N ÷ π), so
     upland puroks with few houses don't spread across a whole forest.
5. **Parents.**
   - A parent sitio with a community outline is a container: its child puroks grow only
     inside it, and the parent's outline is drawn too.
   - A parent without an outline gets no area of its own and isn't counted in N. Its
     children carry its name in their labels.
6. **Cells to polygons.**
   - Join each name's cells into polygons: rows of cells become rectangles, then GEOS union.
   - Smooth: buffer +8 m, then −8 m.
   - Simplify with a 4 m tolerance.
   - Clip to the barangay and subtract the fixed areas.
   - Drop pieces smaller than 0.1 ha. If a name ends up empty, it is reported, not silently
     lost.

The command prints, per barangay: N and its basis, names placed and unplaced, the share of
houses inside some outline, and any name that got no area.

### 3. Storing and serving (backend)

New `Purok` model in the barangays app, following the barangay naming:

| Field | Column | Type |
|---|---|---|
| id | `prk_id` | BigAutoField |
| barangay | `brgy_id` | FK Barangay, CASCADE |
| name | `prk_name` | CharField(100) |
| kind | `prk_kind` | CharField: purok / sitio / zone / subdivision |
| parent | `prk_parent` | CharField(100), blank |
| boundary | `prk_boundary` | MultiPolygonField(4326) |
| source | `prk_source` | CharField: estimated / community / official |
| confidence | `prk_confidence` | CharField: high / medium / low / blank for official |

The table is `purok`, with (barangay, name) unique.

**`python manage.py load_puroks --file F [--source official|estimated|community] [--dry-run]`:**
- *Input:* features need `barangay`, `name` and `kind` properties. `parent` and
  `confidence` are optional, and `source` defaults to the `--source` flag. A file missing
  a required property is refused before anything changes.
- *Name matching:* barangay names go through the alias table now in `load_barangays`
  (moved to a shared module so both commands use it).
- *Checks:* a shape with more than 90% of its area inside its barangay is trimmed to the
  barangay; anything less is refused with the overlap printed.
- *Replacing:* all puroks of every barangay named in the file are replaced in one
  transaction. Barangays not in the file keep theirs, so one barangay's official lines can
  go in on their own.
- *Comparing:* when official shapes replace estimated ones, the command prints, per purok
  matched by name, the overlap with the estimate (shared area ÷ combined area). It also
  prints the barangay average, plus names that are only in the estimate or only in the
  official file.

**`GET /api/barangays/puroks/`:** public, and a GeoJSON FeatureCollection like the barangay
list. Properties are id, name, kind, parent, barangay (id), barangay_name, source,
confidence and label_point (PostGIS `ST_PointOnSurface`, so labels sit inside odd shapes).

### 4. On the map (frontend)

- `barangaysApi.puroks()`. `PublicMap.jsx` loads it once alongside the barangay outlines.
  If it fails, the layer is simply absent.
- **Drawing:**
  - One `GeoJSON` layer placed before the barangay layer, so barangay outlines stay on top.
  - `interactive={false}`, so taps still reach barangays, hazards and the publish tools.
  - Style: no fill, colour `#7c3aed` (violet: clear of the hazard reds, oranges, yellows
    and greens and of the dark barangay line), weight 1.5.
  - Estimated and community outlines are dashed (`dashArray: '5 4'`); official outlines
    are solid.
- **Labels:** from zoom 15 up, a small permanent label at each label_point (class
  `pm-purok-label`). The text is the name, then its parent if any ("Purok Sambag · Laray"),
  plus "(est.)" unless official. Below zoom 15 there are no labels, so the city view isn't
  cluttered.
- **Toggle:** `LayerControl` gets a "Purok outlines" checkbox under "Zone outlines",
  ticked by default. While any purok is estimated it carries the note "Estimated until
  official boundaries arrive". The note disappears once all are official.
- **Attribution:** while the layer is shown, the map attribution adds "Purok estimates:
  OpenStreetMap, Wikimapia (CC BY-SA), Microsoft Building Footprints (ODbL), Visayan
  Electric notices".

### 5. Swapping in official boundaries

1. If the Barangay Hall's data is paper or PDF, trace it in QGIS or geojson.io with
   `barangay`, `name` and `kind` on each shape. The barangay outline should be the
   background, so the lines match.
2. `python manage.py load_puroks --file official_<barangay>.geojson --source official --dry-run`,
   read the checks and the overlap report, then run it without `--dry-run`.
3. If the overlap report shows the estimates are consistently off (say, edges on the wrong
   side of roads), retune the costs in section 2 and rebuild the barangays that are still
   estimated.

## Error handling

- A missing download (Microsoft tile, Overpass, Copernicus) fails the build before
  anything is written. The previous `talisay_puroks_estimated.geojson` stays.
- A barangay with no placed points gets no puroks, and the summary says so. It is not an
  error.
- `load_puroks` refuses the whole file on any refused shape or missing property, and
  prints every problem, not just the first.
- The API serves whatever is loaded. An empty table returns an empty FeatureCollection,
  and the map shows nothing.

## Testing

**Backend**, Django `TestCase` in `backend/tests/`, using PostGIS where geometry is checked
(as `test_barangay_cordon.py` does):

- *Growth* on a small synthetic grid:
  - the border between two points falls on a waterway line between them;
  - a point stops at its house share;
  - unclaimed cells stay unclaimed;
  - a fixed outline is never entered;
  - the radius cap holds.
- *Notice ordering:* synthetic notices (A+B, B+C, A+B+C+D) give the order A–B–C. Road
  narrowing keeps only the roads common to every notice. Names that never separate are
  flagged.
- *Name cleanup:* the spelling-variant merges listed above, and company names dropped.
- *Polygons:* the outputs lie inside the barangay, don't overlap, contain their own
  point, and pieces under 0.1 ha are dropped.
- *`load_puroks`:*
  - it replaces only the barangays in the file;
  - it refuses missing properties and big overhangs, and trims small ones;
  - `--dry-run` changes nothing;
  - the overlap report gives 1.0 for an identical shape and 0 for a disjoint one;
  - aliases resolve.
- *API:* a FeatureCollection with the listed properties, and public access.

**Frontend** (Jest):
- The label text helper adds "(est.)" except for official.
- The style helper gives dashed for estimated and community, solid for official.
- `LayerControl` shows the purok checkbox and note and calls its handler; the note is
  hidden when everything is official.

**Manual, in the running app:**
- Layer on by default, under the barangay lines.
- Taps still open barangays and hazards and still place publish corners.
- Labels appear at zoom 15 and up.
- Phone width works.
- Spot-check three barangays (San Roque, Tangke, Tapul) against satellite imagery and the
  Wikimapia outlines.

## Files touched

- Backend:
  - `apps/barangays/models.py`, plus a new migration;
  - `apps/barangays/serializers.py`, `views.py`, `urls.py`;
  - new `apps/barangays/aliases.py`;
  - `apps/barangays/management/commands/load_barangays.py` (imports the aliases);
  - new `management/commands/build_purok_estimates.py` and `load_puroks.py`;
  - new `apps/barangays/purok_estimate.py` (growth, ordering, polygons);
  - `apps/hazards/susceptibility.py` (expose the cached fetch for reuse, if needed);
  - new `tests/test_purok_estimate.py` and `tests/test_load_puroks.py`.
- Data: new `apps/barangays/data/puroks/` (the four data files, `SOURCES.md`, and the
  generated `talisay_puroks_estimated.geojson`).
- Frontend:
  - `api/barangaysApi.js`, `pages/PublicMap.jsx`, `components/Map/LayerControl.jsx`,
    `pages/css/PublicMapLayers.css`;
  - new `components/Map/purokStyle.js` and `purokStyle.test.js`.

## Noticed, separate

- The barangay outlines (OCHA/PSA 2023) disagree with the city's own land areas by a lot
  in the uplands. Purok outlines are clipped to them and inherit that error.
- `backend/.hazard_cache/` holds an SRTM-era `dem_z14_*.npy`, but the build now reads
  `dem_cop30_*`, so the first purok build downloads Copernicus elevation once.
