# Terrain and elevation on the public map — design

Date: 2026-10-19
Status: draft for review
Branch: merge-scout

## Why

The map draws its flood, landslide and fire layers from elevation data, but nothing on
the map shows that the ground has height. Talisay runs from sea level to about 670 m and
half the city sits above 100 m, yet both base maps (Esri light gray, OpenStreetMap) look
flat. Officers publishing a flood "from water depth" cannot see why the shape stops where
it does, and residents cannot tell high ground from low.

Investigation (2026-10-19) found no code bug: `terrain.png` decodes correctly, lines up
exactly with the map grid (1207 x 1339 cells, same bounds), and the flood fill reads it
consistently. Two real causes:

1. **Elevation is never shown.** SRTM heights are used only inside the offline build.
   `terrain.png` stores height above the nearest drainage (HAND), not height above sea
   level, and no map layer shows relief.
2. **The data is noisier than the water depths officers enter.** On ground below 10 m
   (20% of the city, where floods happen), SRTM varies about 0.8 m (std) from its 100 m
   neighbourhood; 1 cell in 10 is off by more than 1.3 m. A knee-deep flood is 0.5 m.

## Goals

- Everyone can see high and low ground on the map (a Terrain map style).
- Anyone can tap a spot and read, in plain words: ground height above sea level, height
  above the nearest creek, drain or low channel, the nearest named river, and the flood,
  landslide and fire susceptibility there.
- Officers publishing a flood see the same reading for the spot they tapped.
- Heights come from better open data than SRTM.
- Modelled on Project NOAH's presentation (terrain-looking map, tap a place to read its
  hazard levels), not its data: NOAH's LiDAR (LiPAD) licence forbids posting it on a
  public web map with geospatial information.

## Non-goals

- Contour lines (wiggly and misleading on the noisy low plain).
- A hillshade built from our own data (30 m source looks blocky at street zoom).
- LiDAR or FABDEM data (licence: LiPAD forbids public web use; FABDEM's terms are unclear).
- Changing the flood-fill algorithm or its constants.
- NOAH-style rainfall return-period scenarios, storm surge.
- Saying whether a tapped spot is inside a live hazard zone (possible follow-up).

## Evidence behind the choices

| Low coastal plain (ground < 10 m) | SRTM (today) | Copernicus GLO-30 |
|---|---|---|
| Std. deviation from the 100 m neighbourhood | 0.79 m | 0.69 m |
| 1 cell in 10 differs by more than | 1.27 m | 1.11 m |
| Captured | 2000 | 2011–2015 |
| Mean difference from SRTM on the plain | — | +2.5 m (picks up rooftops more) |

Copernicus is about 13% less noisy, newer, and licensed for public redistribution with
attribution. Neither dataset is bare ground. It is a modest improvement, not a fix, so
the readout states the accuracy plainly and a check after the rebuild guards the flood
tool (see Verification).

A test of the readout on seven real spots (coast, riverbank, plain, hills, hilltop)
shaped the wording rules in section 3: the sea is the drainage reference for 17% of the
low plain, three quarters of references are elevation-derived channels rather than
mapped creeks, and hill values like "64.5 m above the nearest creek" claim false precision.

## Design

### 1. Elevation data in the build (backend)

`build_hazard_index` reads **Copernicus GLO-30** instead of the AWS Terrarium SRTM
tiles. The Terrarium fetcher is removed (no fallback: if Copernicus is unreachable the
build fails before writing anything, the published layers stay as they are, and the
build is retried later; a fallback would let a rebuild silently change what every
height means).

**Fetching.** Copernicus 1° tiles are Cloud-Optimized GeoTIFFs on AWS
(`https://copernicus-dem-30m.s3.amazonaws.com/{name}/{name}.tif`, name like
`Copernicus_DSM_COG_10_N10_00_E123_00_DEM`). For each 1° tile overlapping the grid, the
build range-reads the header, then range-reads only the internal blocks that cover the
grid (about 3.4 MB for Talisay instead of 31 MB). Each block request retries 3 times with
backoff. A tile that does not exist (open sea) is treated as elevation 0.
Blocks are decoded with `tifffile` (deflate + floating-point predictor, which needs
`imagecodecs`). Both are pinned in `requirements/base.txt`.

**Resampling.** Bilinear onto the existing 9.4 m Web Mercator grid at zoom 14. Pixel
registration comes from the file's `GTRasterTypeGeoKey`; Copernicus uses PixelIsPoint
(pixel (r, c) centred on 11 − r/3600 N, 123 + c/3600 E for tile N10 E123), verified
2026-10-19.

**Cache.** Saved as `.hazard_cache/dem_cop30_{tag}.npy`. The new name means an old SRTM
cache file can never be reused by mistake.

**Outputs** (all in `frontend/public/hazard-index/`):

- `terrain.png` — same layout as today (RGB, no alpha; HAND in cm = R × 256 + G), but the
  blue channel now also says what the height is measured against:
  `B = 0` outside the city, `B = 255` inside and measured against a waterway or
  elevation-derived channel, `B = 200` inside and measured against the sea.
  The existing decode `inCity = B > 127` keeps working unchanged.
  `compute_factors` returns the extra mask (`drains_to_sea = sea[ri, ci]`) for this.
- `elevation.png` — new. Ground height above sea level in decimetres
  (R × 256 + G, negative values clipped to 0), `B = 255` inside the city, 0 outside.
  RGB without alpha for the same reason as `terrain.png` (browsers premultiply alpha).
- `index.json` — gains an `elevation` entry (`file`, `bounds`, `encoding`, `source`), the
  `terrain` entry's `encoding` text describes the new blue values, and `sources[0]` carries
  the Copernicus notice below.
- `--terrain-only` writes both `terrain.png` and `elevation.png` and updates both entries.

**Full rebuild.** All susceptibility layers are regenerated from Copernicus, so flood
and landslide colours will shift somewhat. There is no local `.hazard_cache`, so the
rebuild also re-downloads OpenStreetMap (counts may change). It needs the barangay
boundaries in the database, as today.

**Licence notice.** Because the data are resampled and derived from, the Copernicus
licence (Article 6 b, c) requires, verbatim:

> produced using Copernicus WorldDEM-30 © DLR e.V. 2010-2014 and © Airbus Defence and
> Space GmbH 2014-2018 provided under COPERNICUS by the European Union and ESA; all
> rights reserved

and, in the notice covering public distribution:

> The organisations in charge of the Copernicus programme by law or by delegation do not
> incur any liability for any use of the Copernicus WorldDEM-30

Both go into `index.json` `sources` and into the map legend's data note (section 2).

### 2. Terrain map style (public map, everyone)

A third entry in `BASEMAPS` in `PublicMap.jsx`, after Map and Streets:

- **Base:** Esri World Hillshade,
  `https://server.arcgisonline.com/ArcGIS/rest/services/Elevation/World_Hillshade/MapServer/tile/{z}/{y}/{x}`,
  `nativeZoom: 16` (real detail over Talisay stops at 16; 17+ is a placeholder tile,
  checked 2026-10-19). Same provider and terms as the existing Map style.
- **Labels:** Esri World Light Gray Reference above the hazard colours, as in the Map style.
- **Blending:** while Terrain is active, the `hazard-levels` pane uses
  `mix-blend-mode: multiply`, so slopes stay visible through the Low / Moderate / High
  shading. Without it the colours would cover the relief.
- **Attribution:** Esri hillshade sources, plus a short "Heights: Copernicus WorldDEM-30".
- **Legend:** while Terrain is active, one extra line: "Shading shows hills and valleys.
  Tap any spot for its height." The legend's data note (already showing "Susceptibility
  data as of …") adds the two Copernicus notices from section 1 in every style, because
  the susceptibility layers are derived from the same data.
- The map still opens on Streets. Hillshade has no streets; barangay outlines and rivers
  are already drawn on top. The existing failed-tile handling switches away from Terrain
  if its tiles fail, with no new code.

### 3. "This spot": tapping the map (everyone, any style)

Tapping inside a barangay still opens that barangay's panel. The tapped point is now
kept as well: a small dot marks it, and a **This spot** section appears at the top of
`BarangayPanel`. Each new tap moves the dot and updates the reading; closing the panel
removes the dot. Choosing a barangay from search shows the panel without the section (no
point). Tapping outside the city behaves as today (it closes any open panel). Example:

> **This spot**
> Ground: about 9 m above sea level
> About level with the nearest creek, drain or low channel.
> Nearest named river: Mananga River, 10 m away
> Susceptibility: Flood High · Landslide Low · Fire Very low
> *Heights come from satellite data (about 30 m detail) and can be off by about 1 m,
> more among buildings.*

**Wording rules** (one pure function, shared with section 4):

- Ground: whole metres, "about N m above sea level"; 0 m reads "about at sea level".
- Waterway line, only when the reference is not the sea (`B = 255`):
  - HAND < 0.5 m: "About level with the nearest creek, drain or low channel."
  - 0.5 m ≤ HAND < 5 m, rounded to the nearest 0.5 m, and 5 m ≤ HAND ≤ 10 m, rounded to
    whole metres: "About N m above the nearest creek, drain or low channel. Water would
    have to rise about that much to reach here."
  - HAND > 10 m: "More than 10 m above the nearest creek, drain or low channel."
- When the reference is the sea (`B = 200`) the waterway line is left out; "above sea
  level" already says it.
- Nearest named river: the closest line with a non-empty `name` in `rivers.geojson`
  (already loaded by the map), if within 2 km: "Nearest named river: NAME, D away", with D
  in tens of metres below 1 km and "1.2 km" style above. Otherwise the line is omitted. It
  is worded separately because the HAND reference is often an unnamed drain, not that river.
- Susceptibility: the class at the spot in the flood, landslide and fire layers, read with
  the existing `loadClassGrid` and labelled with `index.classes`.
- The accuracy footnote is fixed text.

**Data loading.** `elevation.png` and `terrain.png` (about 2 MB each) load on the first
tap and are cached, keyed on `index.generated` like `loadTerrain` today. While loading
the section reads "Reading the ground here…".

**Code shape.**

- `utils/terrain.js`: pure decode functions for both PNG layouts (testable without a
  canvas), `loadElevation(index)` beside `loadTerrain(index)`, and
  `readSpot(terrain, elevation, lat, lng)` returning
  `{ inCity, elevationM, handM, drainsToSea }`.
- `utils/spotText.js` (new): `describeSpot(reading)` (the wording rules) and
  `nearestNamedRiver(rivers, lat, lng, maxM)`.
- `components/Map/SpotReading.jsx` (new): the section; `BarangayPanel` gets a `spot` prop.
- `PublicMap.jsx`: keeps the tapped point in the barangay selection and draws the dot.

### 4. Officers publishing a flood

In `PublishHazardPanel`, under "From water depth", once the officer has tapped a spot the
panel shows the same reading from `describeSpot`: "Where you tapped: ground about 3 m
above sea level, about 0.5 m above the nearest creek, drain or low channel." The accuracy
note changes to "Estimated from Copernicus elevation data (about 30 m detail). Heights can
be off by about 1 m, more among buildings. Check the edge against what you see."

The flood fill (`floodFromDepth`, `SURFACE_SLOPE`, `MAX_FLOOD_REACH_M`) is unchanged. The
`terrain.js` header comment is updated to name Copernicus and the re-measured knee-deep
areas from the verification below. The Terrain style can be used while publishing via
the same toggle (hidden on mobile while the panel is open, as today).

## Error handling

- **Build:** a block request retries 3 times, then the build fails with the existing
  "Build failed: …" message. Downloads happen before any file is written, so a failed
  build changes nothing.
- **Map:** if `elevation.png` is missing (older build) or fails to load, the This spot
  section is hidden and the panel works as before. If only `terrain.png` fails, the
  waterway line is omitted; if `rivers.geojson` is missing, the river line; if a layer
  fails, the susceptibility line. The publish panel's reading follows the same rules.
- Hillshade tile failures are covered by the existing basemap fallback.

## Testing

**Backend** (`backend/tests/test_hazard_index.py`, Django `SimpleTestCase`, run with pytest):

- `elevation.png` and `terrain.png` round-trip: write known arrays, read the PNGs back,
  check decimetres / centimetres and the 0 / 200 / 255 blue values.
- Copernicus reader on a small synthetic COG written with `tifffile` (tiled, deflate,
  floating-point predictor, PixelIsPoint), served by an injected fetch function: checks
  that only the needed blocks are requested and that values land on the right cells.
- A missing tile reads as 0; a block that keeps failing raises after 3 tries.
- `build()` with injected `dem` and `osm` writes `elevation.png` and the new `index.json`
  entries, including the notice in `sources`.

**Frontend** (Jest, beside `snap.test.js`):

- `describeSpot`: every rounding band and boundary (0.49 / 0.5, 4.9 / 5, 10 / 10.1),
  the sea case, sea-level ground.
- `nearestNamedRiver`: nearest by segment distance, unnamed lines skipped, 2 km cutoff,
  m / km formatting.
- Both pure PNG decoders, including the blue-channel cases.

**Manual, in the running app:** Terrain style renders with blended colours and labels at
zoom 13–18; This spot readings at a coastal spot, a riverbank, a hill; search selection
shows no section; panel at phone width; the publish panel reading after a tap; hillshade
failure falls back to another style.

## Verification after the rebuild (go / no-go)

Copernicus changed HAND a lot at some plain spots in the design test (one went from
1.4 m to 7.5 m; that test lacked OSM drains, so part of the gap is the test). Before the
new index is committed, a check script runs the real `floodFromDepth` from `terrain.js`
for knee-deep water (0.5 m) on both the old (SRTM, from git) and new `terrain.png`, and
prints the areas side by side, at 12 fixed low-plain spots:

- the four plain spots from the design test: 10.23752, 123.83510 · 10.24056, 123.83424 ·
  10.23541, 123.83158 · 10.25340, 123.83433;
- eight more: for each point of a 4 × 2 grid spanning the bounding box of city cells
  below 10 m (new data), the nearest city cell below 10 m. The script prints the
  coordinates it used so the run can be repeated.

It passes when, with Copernicus, the median knee-deep area is between 1 and 6 ha
(today's documented figure is 2–4 ha) and at most 2 of the 12 spots collapse to the
"ground rises right away" fallback. If it fails, work stops and the result goes back for
a decision (keep SRTM, or rethink the data); nothing is tuned to make it pass.

## Files touched

- Backend: `apps/hazards/susceptibility.py`,
  `apps/hazards/management/commands/build_hazard_index.py`, `requirements/base.txt`,
  new `tests/test_hazard_index.py`.
- Frontend: `pages/PublicMap.jsx`, `pages/css/PublicMapGis.css` (three-button toggle),
  `components/Map/BarangayPanel.jsx`, new `components/Map/SpotReading.jsx`,
  `utils/terrain.js`, new `utils/spotText.js` and `utils/spotText.test.js`,
  `components/Publish/PublishHazardPanel.jsx`.
- Data: rebuilt `frontend/public/hazard-index/` (all layers, `terrain.png`, new
  `elevation.png`, `index.json`).

## Noticed, separate

`frontend/public/index.html` line 6 contains a mis-encoded title ("GeoAlert â€” Talisay
City" instead of an em dash), which shows in the browser tab. One-line fix, outside this
work.
