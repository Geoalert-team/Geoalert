# Terrain and Elevation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show high and low ground on the public map (Terrain style + a "This spot" height readout) and switch the hazard index's elevation source from SRTM to Copernicus GLO-30.

**Architecture:** The offline build (`build_hazard_index`) range-reads Copernicus Cloud-Optimized GeoTIFF blocks, resamples them onto the existing 9.4 m Web Mercator grid, and writes a new `elevation.png` beside `terrain.png` (whose blue channel now also marks sea vs waterway references). The React map decodes both PNGs in the browser on first tap and turns them into plain-language lines through one pure wording module shared by the public panel and the publish panel. The Terrain style is an extra Esri hillshade basemap with the hazard pane blended by CSS.

**Tech Stack:** Django 4.2 management command, numpy 2.4.2, scipy 1.17.1, Pillow 10.3.0, tifffile, imagecodecs (backend venv: Python 3.11.9); React 18 + react-leaflet 4 + Leaflet 1.9, Jest via react-scripts 5.

**Spec:** `docs/superpowers/specs/2026-10-19-terrain-elevation-design.md`

## Global Constraints

- Backend venv is Python 3.11.9: pin `tifffile==2026.3.3` and `imagecodecs==2026.3.6` (newest releases supporting 3.11; later ones need 3.12).
- No new frontend dependencies.
- Backend tests: from `backend/`, `venv/Scripts/python.exe manage.py test tests.<module>` (Django `SimpleTestCase`, no database).
- Frontend tests: from `frontend/`, `CI=true npx react-scripts test --watchAll=false <file>`.
- Copernicus tile URL: `https://copernicus-dem-30m.s3.amazonaws.com/{name}/{name}.tif`, name `Copernicus_DSM_COG_10_{N|S}{lat:02d}_00_{E|W}{lng:03d}_00_DEM`, lat/lng = south-west corner (floor) of the 1° tile.
- Notice A (verbatim): `produced using Copernicus WorldDEM-30 © DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018 provided under COPERNICUS by the European Union and ESA; all rights reserved`
- Notice B (verbatim): `The organisations in charge of the Copernicus programme by law or by delegation do not incur any liability for any use of the Copernicus WorldDEM-30`
- `terrain.png`: RGB, no alpha, HAND cm = R × 256 + G; B = 0 outside the city, 255 inside measured against a waterway/channel, 200 inside measured against the sea.
- `elevation.png`: RGB, no alpha, height above sea level in decimetres = R × 256 + G (negative clipped to 0), B = 255 inside the city, 0 outside.
- Hillshade tiles: `https://server.arcgisonline.com/ArcGIS/rest/services/Elevation/World_Hillshade/MapServer/tile/{z}/{y}/{x}`, `nativeZoom: 16`. The map still opens on Streets.
- Public accuracy note (verbatim): `Heights come from satellite data (about 30 m detail) and can be off by about 1 m, more among buildings.`
- Publish accuracy note (verbatim): `Estimated from Copernicus elevation data (about 30 m detail). Heights can be off by about 1 m, more among buildings. Check the edge against what you see.`
- Commit on branch `merge-scout`; every commit message ends with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. A tap inside a barangay outline where the raster says "outside the city" (edge cells): no This spot section, never "about at sea level". Pinned in Task 4 (`readSpot` returns `inCity: false`, `elevationM: null`) and Task 8 (render rule).
2. A frontend served with an index built before this change (no `elevation` entry): the section is hidden and the panel is unchanged. Pinned in Task 4 (`loadElevation({})` resolves `null` without touching `Image`).
3. A second tap before the first reading has loaded: only the latest spot's reading is shown. Requirement in Task 8, checked in Task 10.
4. Copernicus voids (NaN or the −32767 nodata value): read as 0, never as a huge negative height that makes inland ground look like sea. Pinned in Task 2.
5. A GeoTIFF whose header is larger than the first range read: the reader fetches more and still parses. Pinned in Task 2.

---

### Task 1: Backend environment and PNG writers

**Files:**
- Modify: `backend/requirements/base.txt` (the "Only needed to rebuild the hazard map" block)
- Modify: `backend/apps/hazards/susceptibility.py` (constants near `TERRAIN_FILE`, `write_terrain_png`, `terrain_meta`; new `write_elevation_png`, `elevation_meta`)
- Create: `backend/tests/test_hazard_index.py`

**Interfaces:**
- Produces: `COPERNICUS_NOTICE` (Notice A), `COPERNICUS_LIABILITY` (Notice B), `ELEVATION_FILE = 'elevation.png'`, `TERRAIN_B_WATERWAY = 255`, `TERRAIN_B_SEA = 200`;
  `write_terrain_png(path, hand: ndarray[m], city_mask: ndarray[bool], drains_to_sea: ndarray[bool]) -> None`;
  `write_elevation_png(path, dem: ndarray[m], city_mask: ndarray[bool]) -> None`;
  `terrain_meta(grid) -> dict` (encoding text names the 0 / 200 / 255 blue values; `source` contains `COPERNICUS_NOTICE`);
  `elevation_meta(grid) -> dict` with keys `file`, `bounds`, `encoding`, `source`.

- [ ] **Step 1: Install the hazard-build dependencies into the venv**

Add `tifffile==2026.3.3` and `imagecodecs==2026.3.6` under the "Only needed to rebuild the hazard map" comment in `requirements/base.txt`, then from `backend/`:
Run: `venv/Scripts/python.exe -m pip install -r requirements/base.txt && venv/Scripts/python.exe -c "import numpy, scipy, requests, tifffile, imagecodecs; print('ok')"`
Expected: `ok`. (numpy, scipy and requests are already in `base.txt` but missing from the venv.) If pip cannot resolve, stop and report.

- [ ] **Step 2: Write the failing tests** in `backend/tests/test_hazard_index.py` (`SimpleTestCase`, files in a `tempfile.TemporaryDirectory`, `from apps.hazards import susceptibility as susc`):

```python
def test_terrain_png_marks_sea_and_waterway(self):
    hand = np.array([[1.0, 2.5], [0.0, 3.0]], np.float32)
    city = np.array([[True, True], [True, False]])
    sea = np.array([[False, True], [False, False]])
    susc.write_terrain_png(path, hand, city, sea)
    rgb = np.asarray(Image.open(path)).astype(int)
    assert Image.open(path).mode == 'RGB'
    assert (rgb[..., 0] * 256 + rgb[..., 1]).tolist() == [[100, 250], [0, 300]]
    assert rgb[..., 2].tolist() == [[255, 200], [255, 0]]

def test_elevation_png_is_decimetres_clipped_at_zero(self):
    dem = np.array([[12.34, -3.0], [669.4, 0.0]], np.float32)
    susc.write_elevation_png(path, dem, np.ones((2, 2), bool))
    rgb = np.asarray(Image.open(path)).astype(int)
    assert (rgb[..., 0] * 256 + rgb[..., 1]).tolist() == [[123, 0], [6694, 0]]
    assert rgb[..., 2].tolist() == [[255, 255], [255, 255]]

def test_metas_carry_the_notice(self):
    grid = susc.Grid(10.30, 123.80, 10.31, 123.81, 14)
    assert susc.elevation_meta(grid)['file'] == 'elevation.png'
    assert susc.COPERNICUS_NOTICE in susc.elevation_meta(grid)['source']
    assert susc.COPERNICUS_NOTICE in susc.terrain_meta(grid)['source']
    assert '200' in susc.terrain_meta(grid)['encoding']
```

- [ ] **Step 3: Run them to verify they fail**

Run: `venv/Scripts/python.exe manage.py test tests.test_hazard_index`
Expected: FAIL / ERROR (`write_elevation_png` missing, `write_terrain_png` takes 3 arguments).

- [ ] **Step 4: Implement** the constants, the new `write_terrain_png` signature (B from `city_mask` and `drains_to_sea`), `write_elevation_png` (decimetres = `np.clip(np.round(dem * 10), 0, 65535)`, packed like `terrain.png`, RGB without alpha), and both metas in `susceptibility.py`. `build()` still calls `write_terrain_png` with three arguments until Task 3, so pass `np.zeros_like(city_mask)` there for now.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `venv/Scripts/python.exe manage.py test tests.test_hazard_index tests.test_hazard_geometry`
Expected: all OK.

- [ ] **Step 6: Commit**

```bash
git add backend/requirements/base.txt backend/apps/hazards/susceptibility.py backend/tests/test_hazard_index.py
git commit -m "hazard index: elevation.png and sea/waterway marks in terrain.png"
```

### Task 2: Copernicus GLO-30 reader

**Files:**
- Modify: `backend/apps/hazards/susceptibility.py` (Downloads section)
- Test: `backend/tests/test_hazard_index.py`

**Interfaces:**
- Consumes: `Grid` (existing; `grid.bounds()`, `grid.px0/py0/width/height/zoom`, `px_to_lnglat`).
- Produces:
  `COPERNICUS_URL = 'https://copernicus-dem-30m.s3.amazonaws.com/{name}/{name}.tif'`;
  `copernicus_tile_name(lat0: int, lng0: int) -> str`;
  `http_range_fetcher(session, retries: int = 3, backoff_s: float = 2.0) -> Callable[[str, int, int], bytes | None]` — `fetch(url, start, length)` sends `Range: bytes={start}-{start+length-1}`; 200/206 returns the body; 403/404 returns `None` (tile does not exist: open sea); anything else, or a `requests.RequestException`, is retried with `time.sleep(backoff_s * attempt)`, and after `retries` attempts raises `RuntimeError(f'Elevation download failed: {url}')`;
  `fetch_copernicus(grid, fetch, log, header_bytes: int = 65536) -> np.ndarray` — float32 heights in metres, shape `grid.shape`, at grid cell centres.

- [ ] **Step 1: Write the failing tests.** Add a helper `make_cog(data, lat_top, lng_left, step, tile=16) -> bytes` that writes a tiled GeoTIFF to `io.BytesIO` with `tifffile.imwrite(..., tile=(tile, tile), compression='zlib', predictor=3, extratags=[(33550, 'd', 3, (step, step, 0.0), True), (33922, 'd', 6, (0, 0, 0, lng_left, lat_top, 0), True), (34735, 'H', 16, (1, 1, 0, 3, 1024, 0, 1, 2, 1025, 0, 1, 2, 2048, 0, 1, 4326), True)])` (PixelIsPoint), and a fake `fetch` that serves byte ranges from a `{tile name: bytes}` dict, records every `(url, start, length)`, and returns `None` for unknown names. Synthetic tiles are 1° at `step = 1/64` (64 × 64 px) with `data[r, c] = 100 + r + 0.5 * c`, so bilinear sampling is exact. Use `grid = susc.Grid(10.30, 123.80, 10.32, 123.82, 14)`.

```python
def test_tile_names(self):
    assert susc.copernicus_tile_name(10, 123) == 'Copernicus_DSM_COG_10_N10_00_E123_00_DEM'
    assert susc.copernicus_tile_name(-1, -75) == 'Copernicus_DSM_COG_10_S01_00_W075_00_DEM'

def test_reads_only_needed_blocks_and_places_values(self):
    dem = susc.fetch_copernicus(grid, fake, log)
    # expected value at each cell centre from its lat/lng: r = (11 - lat) * 64, c = (lng - 123) * 64
    np.testing.assert_allclose(dem, expected, atol=1e-3)
    block_reads = [c for c in fake.calls if c[1] != 0]
    assert 0 < len(block_reads) < 16          # 64x64 tile in 16 blocks; the grid needs only a few

def test_missing_tile_reads_as_zero(self):     # fake has no tiles
    assert not susc.fetch_copernicus(grid, empty_fake, log).any()

def test_voids_read_as_zero(self):            # Review Focus 4
    data[:] = -32767.0; data[0, 0] = np.nan
    dem = susc.fetch_copernicus(grid, fake_with(data), log)
    assert dem.min() >= 0

def test_small_first_header_read_still_parses(self):   # Review Focus 5
    dem = susc.fetch_copernicus(grid, fake, log, header_bytes=64)
    np.testing.assert_allclose(dem, expected, atol=1e-3)

def test_range_fetcher(self):
    # FakeSession(status, body).get(url, headers=..., timeout=...) appends headers to .headers
    # and returns an object with .status_code and .content
    ok = FakeSession(status=206, body=b'x' * 10)
    assert susc.http_range_fetcher(ok)('u', 10, 10) == b'x' * 10
    assert ok.headers[-1]['Range'] == 'bytes=10-19'
    assert susc.http_range_fetcher(FakeSession(status=404))('u', 0, 1) is None
    bad = FakeSession(status=500)
    with self.assertRaises(RuntimeError):
        susc.http_range_fetcher(bad, retries=3, backoff_s=0)('u', 0, 1)
    assert len(bad.headers) == 3
```

- [ ] **Step 2: Run them to verify they fail**

Run: `venv/Scripts/python.exe manage.py test tests.test_hazard_index`
Expected: the new tests ERROR (`copernicus_tile_name` / `fetch_copernicus` / `http_range_fetcher` not defined).

- [ ] **Step 3: Implement the three functions.** Approach for `fetch_copernicus`:
  - Tiles: every integer `(lat0, lng0)` with `floor(south) <= lat0 <= floor(north)` and the same for longitude, from `grid.bounds()`.
  - Header: `fetch(url, 0, header_bytes)`; `None` means the tile is missing (leave 0). Parse with `tifffile.TiffFile(io.BytesIO(head))`; if parsing or reading the tile offsets fails, double `header_bytes` and fetch again, up to 1 MiB, then raise.
  - Georeferencing comes from the file, not from the name: `ModelPixelScaleTag`, `ModelTiepointTag`, and `tf.geotiff_metadata['GTRasterTypeGeoKey']` (2 = PixelIsPoint: pixel (r, c) is centred on the tiepoint plus `(c * dx, -r * dy)`; otherwise add half a pixel).
  - Cell centres: `px_to_lnglat(grid.px0 + c + 0.5, grid.py0 + r + 0.5, grid.zoom)`. Only centres with `lat0 <= lat < lat0 + 1` and `lng0 <= lng < lng0 + 1` are filled from this tile.
  - Window: the pixel rows and columns those centres need, plus one pixel each side, clipped to the image. Fetch only the internal blocks that overlap it (`page.dataoffsets[i]`, `page.databytecounts[i]`) and decode each with `page.decode(raw, i)`.
  - Voids: set `NaN` and values `<= -1000` to 0 before sampling.
  - Sample with `scipy.ndimage.map_coordinates(window, ..., order=1, mode='nearest')`. Cells within half a pixel of a tile seam take the nearest pixel of their own tile; say so in a comment.
  - Log one line per tile: `f'  Elevation: {name}, {n} blocks'`, or `f'  Elevation: {name} not found, treated as sea'`.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `venv/Scripts/python.exe manage.py test tests.test_hazard_index`
Expected: OK.

- [ ] **Step 5: Commit**

```bash
git add backend/apps/hazards/susceptibility.py backend/tests/test_hazard_index.py
git commit -m "hazard index: read Copernicus GLO-30 blocks by range request"
```

### Task 3: The build uses Copernicus

**Files:**
- Modify: `backend/apps/hazards/susceptibility.py` (`TERRAIN_URL` and `fetch_dem` removed; `compute_factors`, `build`)
- Modify: `backend/apps/hazards/management/commands/build_hazard_index.py` (help texts)
- Test: `backend/tests/test_hazard_index.py`

**Interfaces:**
- Consumes: Task 1 writers and metas, Task 2 `fetch_copernicus` and `http_range_fetcher`.
- Produces: `compute_factors(...)` result gains `'drains_to_sea'` (`sea[ri, ci]`, bool, same shape). `build()` keeps its signature and writes `elevation.png`; `index.json` gains `elevation`, and `sources` becomes `['Elevation: ' + COPERNICUS_NOTICE, COPERNICUS_LIABILITY, 'Rivers, coastline, roads, buildings, land use, fire stations: (c) OpenStreetMap contributors']`. The DEM cache file is `dem_cop30_{tag}.npy`.

- [ ] **Step 1: Write the failing tests.** Call `build(polygons, names, extent, out, pad_m=0, dem=dem, osm=osm, log=lambda *a: None)` with `extent = (123.800, 10.300, 123.810, 10.310)`. The one barangay square covers only lng 123.803–123.810 (lat 10.300–10.310), so the west strip is outside the city: `compute_factors` only counts ground as sea when it is both at 0 m and outside the city. `dem` has the shape of `susc.Grid(10.300, 123.800, 10.310, 123.810, 14).shape` and is `np.maximum(0, np.linspace(-2, 20, width))` across the columns, giving 0 m in the west strip and rising to 20 m in the east. `osm` has every key empty except one river `{'kind': 'river', 'name': 'Test River', 'coords': [(123.807, 10.300), (123.807, 10.310)]}`.

```python
def test_build_writes_elevation_and_notice(self):
    index = json.loads((out / 'index.json').read_text())
    assert (out / 'elevation.png').exists()
    assert index['elevation']['file'] == 'elevation.png'
    assert susc.COPERNICUS_NOTICE in index['sources'][0]
    assert susc.COPERNICUS_LIABILITY in index['sources']
    b = np.asarray(Image.open(out / 'terrain.png'))[..., 2]
    assert (b == 200).any() and (b == 255).any()

def test_terrain_only_keeps_layers_and_adds_elevation(self):
    (out / 'index.json').write_text(json.dumps({'layers': {'flood': 'flood.png'}}))
    susc.build(..., terrain_only=True)
    index = json.loads((out / 'index.json').read_text())
    assert index['layers'] == {'flood': 'flood.png'}
    assert {'terrain', 'elevation'} <= index.keys()
    assert (out / 'elevation.png').exists()
```

- [ ] **Step 2: Run them to verify they fail**

Run: `venv/Scripts/python.exe manage.py test tests.test_hazard_index`
Expected: FAIL (no `elevation.png`; sources still name SRTM).

- [ ] **Step 3: Implement.** Remove `TERRAIN_URL` and `fetch_dem`. In `build()`, the DEM comes from `cache / f'dem_cop30_{tag}.npy'` or `fetch_copernicus(grid, http_range_fetcher(session), log)`. Write `terrain.png` with `factors['drains_to_sea']` and `elevation.png` from `factors['elevation']`, in both the full and the `terrain_only` paths (`terrain_only` also sets `index['elevation']`). Update `sources` as in Interfaces. In the command, the description says "from Copernicus elevation data and OpenStreetMap", and the `--terrain-only` help says "Only write terrain.png and elevation.png (heights for the map and for drawing floods from a water depth); leave the published susceptibility layers untouched."

- [ ] **Step 4: Run the tests to verify they pass**

Run: `venv/Scripts/python.exe manage.py test tests.test_hazard_index tests.test_hazard_geometry`
Expected: OK.

- [ ] **Step 5: Commit**

```bash
git add backend/apps/hazards/susceptibility.py backend/apps/hazards/management/commands/build_hazard_index.py backend/tests/test_hazard_index.py
git commit -m "hazard index: build from Copernicus GLO-30 instead of SRTM"
```

### Task 4: Decode the rasters and read a spot (frontend)

**Files:**
- Modify: `frontend/src/utils/terrain.js`
- Create: `frontend/src/utils/terrain.test.js`

**Interfaces:**
- Consumes: `makeGrid` from `./gridGeometry`.
- Produces:
  `decodeTerrainPixels(rgba: Uint8Array | Uint8ClampedArray, n: number) -> { hand: Uint16Array /*cm*/, inCity: Uint8Array, toSea: Uint8Array }` with `inCity = B > 127` and `toSea = inCity && B < 228`;
  `decodeElevationPixels(rgba, n) -> { dm: Uint16Array, inCity: Uint8Array }`;
  `loadTerrain(index)`, unchanged signature, now resolves `{ hand, inCity, toSea, grid, cellM }`;
  `loadElevation(index) -> Promise<{ dm, inCity, grid } | null>`, which resolves `null` when `index?.elevation?.file` is missing or the image fails, and caches like `loadTerrain` (key `${file}@${generated}`);
  `readSpot(terrain, elevation, lat, lng) -> { inCity: boolean, elevationM: number | null, handM: number | null, drainsToSea: boolean | null }`. `inCity` is false (with null values) when `elevation` is null, the point is off its grid, or `elevation.inCity` is 0 there. `handM` and `drainsToSea` are null when `terrain` is null; terrain uses its own grid.

- [ ] **Step 1: Write the failing tests**

```js
const px = (...rgba) => Uint8Array.from(rgba);

test('terrain pixels: hand in cm, city and sea marks', () => {
  const t = decodeTerrainPixels(px(1, 44, 255, 255, 0, 50, 200, 255, 0, 0, 0, 255), 3);
  expect([...t.hand]).toEqual([300, 50, 0]);
  expect([...t.inCity]).toEqual([1, 1, 0]);
  expect([...t.toSea]).toEqual([0, 1, 0]);
});

test('elevation pixels: decimetres and city mask', () => {
  const e = decodeElevationPixels(px(0, 90, 255, 255, 26, 38, 255, 255, 0, 0, 0, 255), 3);
  expect([...e.dm]).toEqual([90, 6694, 0]);
  expect([...e.inCity]).toEqual([1, 1, 0]);
});

// 2 x 2 grid over [[10, 123], [10.002, 123.002]]; cell order: top-left, top-right, bottom-left, bottom-right
// elevation dm [90, 6694, 0, 30], inCity [1, 1, 0, 1]; terrain hand [300, 1200, 0, 40], toSea [0, 0, 0, 1]
test('readSpot reads a city cell', () => {
  expect(readSpot(terrain, elevation, 10.0015, 123.0005))
    .toEqual({ inCity: true, elevationM: 9, handM: 3, drainsToSea: false });
});
test('readSpot: a cell the raster puts outside the city is not read', () => {   // Review Focus 1
  expect(readSpot(terrain, elevation, 10.0005, 123.0005))
    .toEqual({ inCity: false, elevationM: null, handM: null, drainsToSea: null });
});
test('readSpot: off the grid, and without terrain', () => {
  expect(readSpot(terrain, elevation, 11, 124).inCity).toBe(false);
  expect(readSpot(null, elevation, 10.0005, 123.0015))
    .toEqual({ inCity: true, elevationM: 3, handM: null, drainsToSea: null });
});
test('loadElevation without an elevation entry resolves null', async () => {    // Review Focus 2
  await expect(loadElevation({ generated: 'x' })).resolves.toBeNull();
});
```

- [ ] **Step 2: Run them to verify they fail**

Run: `CI=true npx react-scripts test --watchAll=false src/utils/terrain.test.js`
Expected: FAIL (functions not exported).

- [ ] **Step 3: Implement** the decoders, `loadElevation`, and `readSpot` in `terrain.js`. Share one image-to-pixels helper between `loadTerrain` and `loadElevation`. Update the header comment's Data paragraph to describe the 0 / 200 / 255 blue values; the SRTM wording and area figures change in Task 5.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `CI=true npx react-scripts test --watchAll=false src/utils/terrain.test.js src/utils/snap.test.js src/utils/drawnZone.test.js`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/utils/terrain.js frontend/src/utils/terrain.test.js
git commit -m "terrain.js: decode elevation and sea marks, read a spot"
```

### Task 5: Rebuild the hazard index and run the go / no-go check

**Files:**
- Regenerate: `frontend/public/hazard-index/` (all PNGs, `elevation.png`, `rivers.geojson`, `index.json`)
- Create: `frontend/src/utils/floodReach.check.test.js` (skipped unless `FLOOD_CHECK_DIR` is set)
- Modify: `frontend/src/utils/terrain.js` (header comment only)

**Interfaces:**
- Consumes: Task 3 build; Task 4 `decodeTerrainPixels`, `decodeElevationPixels`; existing `floodFromDepth`, `makeGrid`.

- [ ] **Step 1: Rebuild.** From `backend/` (needs network and the database's barangay boundaries):
Run: `venv/Scripts/python.exe manage.py build_hazard_index`
Expected: a line `Elevation: Copernicus_DSM_COG_10_N10_00_E123_00_DEM, <n> blocks`, then `Wrote 4 layers to ...` and `Hazard susceptibility maps built.`

- [ ] **Step 2: Dump pixels for the check.** Write a throwaway script outside the repository (for example in the system temp folder; it is not committed) that writes `<name>.rgba` (`Image.open(...).convert('RGBA').tobytes()`) and `meta.json` (`{name: {width, height, bounds, cellM}}`) to a scratch folder for three rasters: `old_terrain` (from `git show HEAD:frontend/public/hazard-index/terrain.png`, with bounds and `cellSizeM` from `git show HEAD:frontend/public/hazard-index/index.json`), `new_terrain`, and `new_elevation` (the new files and `index.json`).

- [ ] **Step 3: Write the check** `floodReach.check.test.js`. It uses `describe.skip` unless `process.env.FLOOD_CHECK_DIR` is set, and reads the dumps with `fs`. It builds terrain objects `{ ...decodeTerrainPixels(rgba, w * h), grid: makeGrid(bounds, w, h), cellM }`, then for each of the 12 spots runs `floodFromDepth(terrain, spot, 0.5)` on old and new data:
  - fixed: `[10.23752, 123.83510]`, `[10.24056, 123.83424]`, `[10.23541, 123.83158]`, `[10.25340, 123.83433]`;
  - lattice: the bounding box (in cells) of new-elevation cells with `inCity && dm < 100`; points at x fractions 0.125, 0.375, 0.625, 0.875 and y fractions 0.25, 0.75; for each, the nearest such cell (Euclidean in cells), converted to a lat/lng at the cell centre.

  It prints a `console.table` of spot, old ha, new ha and new collapsed (`note` starts with `'The ground rises right away'`), then asserts `1 <= median(new ha) <= 6` and `collapsed <= 2`.

- [ ] **Step 4: Run the check**

Run (from `frontend/`): `FLOOD_CHECK_DIR=<scratch folder> CI=true npx react-scripts test --watchAll=false src/utils/floodReach.check.test.js`
Expected: PASS, with the table printed. Save the table for Step 6.

- [ ] **Step 5: GATE.** If the check fails: **stop**. Do not commit the rebuilt data and do not start Task 6. Restore the old index with `git checkout -- frontend/public/hazard-index` and `git clean -f frontend/public/hazard-index` (it only removes the new `elevation.png`), then report the table and wait for a decision. Nothing gets tuned to make the check pass.

- [ ] **Step 6: Update the `terrain.js` header comment.** "SRTM, about 30 m" becomes "Copernicus GLO-30, about 30 m", and "roughly 2-4 ha for knee-deep water" becomes the measured median and range from the table.

- [ ] **Step 7: Confirm the plain run still skips the check**

Run: `CI=true npx react-scripts test --watchAll=false src/utils/floodReach.check.test.js`
Expected: 1 suite, all tests skipped, exit 0.

- [ ] **Step 8: Commit**

```bash
git add frontend/public/hazard-index frontend/src/utils/floodReach.check.test.js frontend/src/utils/terrain.js
git commit -m "hazard index: rebuild from Copernicus GLO-30 (knee-deep check passed)"
```

### Task 6: Spot wording

**Files:**
- Create: `frontend/src/utils/spotText.js`, `frontend/src/utils/spotText.test.js`

**Interfaces:**
- Consumes: `readSpot` result shape (Task 4).
- Produces:
  `ACCURACY_NOTE` (the public accuracy note, verbatim);
  `describeSpot({ elevationM, handM, drainsToSea }) -> { ground: string | null, waterway: string | null }`;
  `describeSusceptibility(classes: { flood: number, landslide: number, fire: number }, labels: Array<{ label: string }>) -> string | null` (class 1–5 indexes `labels`; 0 is left out; all 0 gives `null`);
  `nearestNamedRiver(rivers: GeoJSON | null, lat, lng, maxM = 2000) -> { name: string, distanceM: number } | null` (LineString features with a non-empty trimmed `name`; distance to the nearest segment, equirectangular, 111320 m per degree of latitude);
  `formatDistance(m: number) -> string`.

- [ ] **Step 1: Write the failing tests**

```js
const W = (h) => describeSpot({ elevationM: 5, handM: h, drainsToSea: false }).waterway;
const RISE = ' above the nearest creek, drain or low channel. Water would have to rise about that much to reach here.';

test('ground', () => {
  expect(describeSpot({ elevationM: 9.4, handM: null, drainsToSea: null }).ground).toBe('about 9 m above sea level');
  expect(describeSpot({ elevationM: 0.4, handM: null, drainsToSea: null }).ground).toBe('about at sea level');
  expect(describeSpot({ elevationM: null, handM: null, drainsToSea: null }).ground).toBeNull();
});
test('waterway bands', () => {
  expect(W(0.49)).toBe('About level with the nearest creek, drain or low channel.');
  expect(W(0.5)).toBe(`About 0.5 m${RISE}`);
  expect(W(1.26)).toBe(`About 1.5 m${RISE}`);
  expect(W(4.9)).toBe(`About 5 m${RISE}`);
  expect(W(5)).toBe(`About 5 m${RISE}`);
  expect(W(7.6)).toBe(`About 8 m${RISE}`);
  expect(W(10)).toBe(`About 10 m${RISE}`);
  expect(W(10.1)).toBe('More than 10 m above the nearest creek, drain or low channel.');
});
test('no waterway line against the sea or without data', () => {
  expect(describeSpot({ elevationM: 2, handM: 1.5, drainsToSea: true }).waterway).toBeNull();
  expect(describeSpot({ elevationM: 2, handM: null, drainsToSea: null }).waterway).toBeNull();
});
test('susceptibility line', () => {
  const L = ['Very low', 'Low', 'Moderate', 'High', 'Very high'].map((label) => ({ label }));
  expect(describeSusceptibility({ flood: 4, landslide: 2, fire: 1 }, L))
    .toBe('Susceptibility: Flood High · Landslide Low · Fire Very low');
  expect(describeSusceptibility({ flood: 5, landslide: 0, fire: 0 }, L)).toBe('Susceptibility: Flood Very high');
  expect(describeSusceptibility({ flood: 0, landslide: 0, fire: 0 }, L)).toBeNull();
});
test('nearest named river', () => {
  // A: named, along lat 10.000 from lng 123.000 to 123.010; an unnamed line at lat 10.0005; B: named, far away
  expect(nearestNamedRiver(RIVERS, 10.001, 123.005).name).toBe('A');
  expect(nearestNamedRiver(RIVERS, 10.001, 123.005).distanceM).toBeCloseTo(111.3, 0);
  expect(nearestNamedRiver(RIVERS, 10.03, 123.005)).toBeNull();   // > 2 km
  expect(nearestNamedRiver(null, 10, 123)).toBeNull();
});
test('distances', () => {
  expect(formatDistance(14)).toBe('10 m');
  expect(formatDistance(994)).toBe('990 m');
  expect(formatDistance(996)).toBe('1.0 km');
  expect(formatDistance(1234)).toBe('1.2 km');
});
```

- [ ] **Step 2: Run them to verify they fail**

Run: `CI=true npx react-scripts test --watchAll=false src/utils/spotText.test.js`
Expected: FAIL (module not found).

- [ ] **Step 3: Implement `spotText.js`.** Rounding: below 5 m, `Math.round(h * 2) / 2`; from 5 to 10 m, `Math.round(h)`; print numbers with `String(n)`. `formatDistance` rounds to tens of metres and switches to `(m / 1000).toFixed(1) + ' km'` once the rounded value reaches 1000.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `CI=true npx react-scripts test --watchAll=false src/utils/spotText.test.js`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/utils/spotText.js frontend/src/utils/spotText.test.js
git commit -m "spotText: plain-language height, waterway, river and susceptibility lines"
```

### Task 7: Terrain map style and the data notice in the legend

**Files:**
- Modify: `frontend/src/pages/PublicMap.jsx` (`BASEMAPS` at lines 37-54, the `pm-stage` className near line 989, the legend notes near lines 1404-1416)
- Modify: `frontend/src/pages/css/PublicMapGis.css`

**Interfaces:**
- Consumes: `susceptibility.index.sources` (array of strings; Task 3 puts the notices there).

- [ ] **Step 1: Add the `terrain` basemap** after `streets`: label `'Terrain'`, base = the hillshade URL, labels = the same `World_Light_Gray_Reference` URL as `map`, `attribution: 'Hillshade &copy; Esri, USGS, NASA and contributors · Heights: Copernicus WorldDEM-30'`, `nativeZoom: 16`, `layerOpacity: 0.7`. Leave the default `basemap` as `'streets'`.

- [ ] **Step 2: Blend the hazard colours over the relief.** Add `'is-terrain'` to the `pm-stage` class list when `basemap === 'terrain'`, and add to `PublicMapGis.css`:
```css
.pm-stage.is-terrain .leaflet-hazard-levels-pane { mix-blend-mode: multiply; }
.pm-legend-source { font-size: .7rem; }
```

- [ ] **Step 3: Legend lines.** In the `legendOpen` block, after "Susceptibility data as of…", add:
  - while `basemap === 'terrain'`: `<p className="pm-legend-note">Shading shows hills and valleys. Tap any spot for its height.</p>`;
  - every entry of `susceptibility.index?.sources` as `<p className="pm-legend-note pm-legend-source">`.

- [ ] **Step 4: Check it compiles and renders.** With `npm start` (or the dev server already running at localhost:3000): no compile errors or ESLint warnings in the terminal. Terrain shows hillshade with place names, the hazard colours let the relief through, the toggle shows three buttons, and the legend shows the Copernicus notices.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/PublicMap.jsx frontend/src/pages/css/PublicMapGis.css
git commit -m "public map: Terrain style and elevation data notice"
```

### Task 8: "This spot" in the barangay panel

**Files:**
- Create: `frontend/src/components/Map/SpotReading.jsx`
- Modify: `frontend/src/components/Map/BarangayPanel.jsx`, `frontend/src/pages/PublicMap.jsx` (`selectBarangay` at line 642, the barangay `GeoJSON` click handler near line 1077, the `BarangayPanel` element near line 1541, a dot inside `MapContainer`), `frontend/src/pages/css/PublicMapGis.css`

**Interfaces:**
- Consumes: `loadTerrain`, `loadElevation`, `readSpot` (Task 4); `describeSpot`, `describeSusceptibility`, `nearestNamedRiver`, `formatDistance`, `ACCURACY_NOTE` (Task 6); `loadClassGrid(index, layer)` from `components/Map/hazardLevels.js`; `makeGrid` from `utils/gridGeometry`.
- Produces: `<SpotReading spot={[lat, lng] | null} index={object | null} rivers={GeoJSON | null} />`; `BarangayPanel` gains props `spot`, `susceptibilityIndex`, `rivers`; the selection becomes `{ kind: 'barangay', id, spot: [lat, lng] | null }`.

- [ ] **Step 1: `SpotReading.jsx`.**
  - Renders nothing for a null `spot` or `index`.
  - On each new `spot`, shows "Reading the ground here…", then loads `loadElevation`, `loadTerrain` and the three class grids (`flood`, `landslide`, `fire`) in parallel. Each class grid is cached in a module-level `Map` keyed `${layer}@${index.generated}`, and each load is `.catch(() => null)`.
  - **A result for a spot that has since changed is discarded** (Review Focus 3).
  - Renders nothing when `elevation` is null or `readSpot(...).inCity` is false (Review Focus 1, 2).
  - Otherwise renders `<section className="pm-spot" aria-live="polite"><h3>This spot</h3>` with, in order: `Ground: {ground}`, the waterway line, `Nearest named river: {name}, {formatDistance(distanceM)} away`, the susceptibility line, and `<small>{ACCURACY_NOTE}</small>`. A line whose value is null is left out.
  - The class at the spot is `grid.cls[Math.floor(y) * grid.width + Math.floor(x)]` with `[x, y] = makeGrid(index.bounds, grid.width, grid.height).toCell(lat, lng)`, or 0 off the grid or when the grid is null.

- [ ] **Step 2: `BarangayPanel`.** Accept `spot`, `susceptibilityIndex` and `rivers`; render `<SpotReading spot={spot} index={susceptibilityIndex} rivers={rivers} />` directly after `.pm-panel-head`.

- [ ] **Step 3: `PublicMap`.**
  - `selectBarangay(barangay, spot = null)` stores `spot` in the selection. When the tapped barangay is already the open selection and `spot` is set, it only updates the selection: no `flyToBounds`, so tapping around one barangay doesn't re-zoom each time.
  - The barangay `GeoJSON` click passes `[e.latlng.lat, e.latlng.lng]`. Search keeps calling `selectBarangay(item)`, so there's no spot.
  - Pass `spot={selection?.spot ?? null}`, `susceptibilityIndex={susceptibility.index}` and `rivers={susceptibility.rivers}` to `BarangayPanel`.
  - While `panelOpen && selection?.kind === 'barangay' && selection.spot`, draw `<CircleMarker center={selection.spot} radius={6} interactive={false} />` (navy outline, white fill).

- [ ] **Step 4: Styles.** Add `.pm-spot` styles (a block under the panel head with small line spacing; `small` in the muted panel colour) to `PublicMapGis.css`.

- [ ] **Step 5: Check it in the app.** Tap a coastal spot, the Mananga riverbank and a hill in Cantabaco: the readings follow the spec's wording, with no waterway line where the reference is the sea. A search selection shows no section. Closing the panel removes the dot. No compile errors or ESLint warnings.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/Map/SpotReading.jsx frontend/src/components/Map/BarangayPanel.jsx frontend/src/pages/PublicMap.jsx frontend/src/pages/css/PublicMapGis.css
git commit -m "public map: tap a spot for its height, waterway, river and susceptibility"
```

### Task 9: Reading in the publish panel

**Files:**
- Modify: `frontend/src/components/Publish/PublishHazardPanel.jsx` (terrain effect at lines 286-292, the `FLOOD_DEPTH` block at lines 512-549)
- Modify: `frontend/src/components/Publish/css/PublishHazard.css`

**Interfaces:**
- Consumes: `loadElevation`, `readSpot` (Task 4); `describeSpot` (Task 6).

- [ ] **Step 1: Load the elevation.** Load it next to the terrain in the existing `method === FLOOD_DEPTH` effect (new state `elevation`), with the same cancellation pattern.

- [ ] **Step 2: Show the reading.** When `seed` is set and `readSpot(terrain, elevation, seed[0], seed[1]).inCity`, render above the size hint `<p className="pub-spot"><strong>Where you tapped</strong>` followed by `Ground: {ground}` and the waterway line (lines that are null are left out). Replace the hint text at lines 545-546 with the publish accuracy note, verbatim.

- [ ] **Step 3: Check it in the app.** As a DRRMO officer, publish a Flood "From water depth" and tap the plain: the reading appears and matches the public panel for the same spot. With no tap yet, there's no reading.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/Publish/PublishHazardPanel.jsx frontend/src/components/Publish/css/PublishHazard.css
git commit -m "publish panel: show the ground reading where the officer tapped"
```

### Task 10: Whole-feature check in the running app

- [ ] **Step 1: Run every automated test**

Run (from `backend/`): `venv/Scripts/python.exe manage.py test tests`, and (from `frontend/`): `CI=true npx react-scripts test --watchAll=false`
Expected: all pass (the flood check is skipped).

- [ ] **Step 2: Manual checks** (from the spec's manual list and Review Focus 3):
  - Terrain at zoom 13–18: hillshade stretched past 16, labels on top, blended colours.
  - This spot at a coastal spot, a riverbank and a hill.
  - Two quick taps in a row show only the second spot's reading.
  - Search selection shows no section.
  - The panel works at phone width (DevTools at 375 px).
  - The publish panel reading appears.
  - With the hillshade URL blocked in DevTools (request blocking), the map switches to another style and says so.

  Record the results in the final report.

### Task 11: Fix the browser tab title

**Files:**
- Modify: `frontend/public/index.html:6`

- [ ] **Step 1:** Replace the garbled title with `<title>GeoAlert — Talisay City</title>` and save the file as UTF-8.
- [ ] **Step 2:** Run `grep -c "â€" frontend/public/index.html`. Expected: `0`. Reload the app; the tab reads "GeoAlert — Talisay City".
- [ ] **Step 3: Commit**

```bash
git add frontend/public/index.html
git commit -m "index.html: fix mis-encoded page title"
```
