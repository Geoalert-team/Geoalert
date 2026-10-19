/**
 * Flood extent from one observed water depth.
 *
 * The officer stands somewhere, sees knee-deep water, and enters that. From
 * that spot the water is spread over the ground with two rules:
 *
 *   * Ground that rises above the spot uses up depth. Heights are measured
 *     as height above the nearest drainage (HAND), so the water follows
 *     creeks and low streets rather than one flat level for the city.
 *   * The water surface falls away from where it was seen, SURFACE_SLOPE
 *     metres per metre (4 m per km). Water is not a flat lake across a
 *     city; without this, knee-deep water on Talisay's coastal plain,
 *     which sits almost level with its drainage, floods hundreds of
 *     hectares.
 *
 * A cell floods when  rise above the spot + SURFACE_SLOPE x path distance
 * is less than the observed depth. So knee-deep water (0.5 m) reaches at
 * most about 125 m on flat ground, waist-deep about 250 m, and less where
 * the ground rises. Measured at 12 spots on the low plain (2026-10-19,
 * src/utils/floodReach.check.test.js) knee-deep water covers a median of
 * about 1.3 ha, mostly 1-3 ha, but only 0.1-0.6 ha in some dense built-up
 * blocks, where the elevation data partly reads rooftops as ground.
 *
 * Rule-based terrain arithmetic, no AI. Accuracy is limited by the
 * elevation data (Copernicus GLO-30, about 30 m, about 1 m off on flat
 * ground and more among buildings) and by the surface-slope assumption, so
 * the result is a starting shape the officer checks and edits, never a
 * survey.
 *
 * Data: hazard-index/terrain.png and elevation.png, written by
 *   manage.py build_hazard_index --terrain-only
 * terrain.png: HAND in cm = R * 256 + G; B = 0 outside the city, 255 inside
 * when the height is measured against a waterway, 200 against the sea.
 * elevation.png: height above sea level in dm = R * 256 + G; B = 255 inside.
 */

import { makeGrid, simplifyRing, traceBoundary } from './gridGeometry';

const BASE = `${process.env.PUBLIC_URL || ''}/hazard-index`;

// How fast the water surface falls away from where it was seen (4 m per km)
export const SURFACE_SLOPE = 0.004;
// Hard limit on how far a flood is grown, in metres, whatever the depth
export const MAX_FLOOD_REACH_M = 2000;

// Blue values below this (but inside the city) mark heights measured against the sea
const SEA_BLUE_BELOW = 228;

const cached = {}; // entry name -> { key, promise }

function loadImage(url) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = reject;
    img.src = url;
  });
}

/** RGBA pixels of a packed hazard-index PNG, as { width, height, data }. */
function loadPixels(url) {
  return loadImage(url).then((img) => {
    const canvas = document.createElement('canvas');
    canvas.width = img.width;
    canvas.height = img.height;
    const ctx = canvas.getContext('2d', { willReadFrequently: true });
    ctx.drawImage(img, 0, 0);
    return { width: img.width, height: img.height, data: ctx.getImageData(0, 0, img.width, img.height).data };
  });
}

/**
 * Loads one index entry ('terrain' or 'elevation') once and caches it.
 * Resolves to null when the index has no such entry (an older build) or
 * the image fails to load.
 */
function loadEntry(index, entry, decode) {
  const meta = index?.[entry];
  if (!meta?.file) return Promise.resolve(null);
  const key = `${meta.file}@${index.generated || ''}`;
  if (cached[entry]?.key === key) return cached[entry].promise;

  const promise = loadPixels(`${BASE}/${meta.file}?v=${encodeURIComponent(index.generated || '')}`)
    .then(({ width, height, data }) => ({
      ...decode(data, width * height),
      grid: makeGrid(meta.bounds || index.bounds, width, height),
      cellM: index.cellSizeM || 10,
    }))
    .catch(() => null);
  cached[entry] = { key, promise };
  return promise;
}

/** terrain.png pixels: HAND in cm, inside the city, measured against the sea. */
export function decodeTerrainPixels(rgba, n) {
  const hand = new Uint16Array(n); // centimetres
  const inCity = new Uint8Array(n);
  const toSea = new Uint8Array(n);
  for (let i = 0, p = 0; i < n; i += 1, p += 4) {
    hand[i] = (rgba[p] << 8) | rgba[p + 1];
    inCity[i] = rgba[p + 2] > 127 ? 1 : 0;
    toSea[i] = inCity[i] && rgba[p + 2] < SEA_BLUE_BELOW ? 1 : 0;
  }
  return { hand, inCity, toSea };
}

/** elevation.png pixels: height above sea level in dm, inside the city. */
export function decodeElevationPixels(rgba, n) {
  const dm = new Uint16Array(n);
  const inCity = new Uint8Array(n);
  for (let i = 0, p = 0; i < n; i += 1, p += 4) {
    dm[i] = (rgba[p] << 8) | rgba[p + 1];
    inCity[i] = rgba[p + 2] > 127 ? 1 : 0;
  }
  return { dm, inCity };
}

/**
 * The terrain grid for the susceptibility index, decoded once and cached.
 * Resolves to null when the index has no terrain (an older build).
 */
export function loadTerrain(index) {
  return loadEntry(index, 'terrain', decodeTerrainPixels);
}

/** Ground height above sea level, like loadTerrain. Null for an older build. */
export function loadElevation(index) {
  return loadEntry(index, 'elevation', decodeElevationPixels);
}

// Index of the cell under [lat, lng] on a decoded raster, or -1 off its grid
function cellAt(raster, lat, lng) {
  const [fx, fy] = raster.grid.toCell(lat, lng);
  const x = Math.floor(fx);
  const y = Math.floor(fy);
  if (x < 0 || y < 0 || x >= raster.grid.width || y >= raster.grid.height) return -1;
  return y * raster.grid.width + x;
}

/**
 * What the rasters say about one spot:
 * { inCity, elevationM, handM, drainsToSea }. Outside the city (or without
 * elevation data) every value is null; without terrain, only the height
 * above the waterway is.
 */
export function readSpot(terrain, elevation, lat, lng) {
  const none = { inCity: false, elevationM: null, handM: null, drainsToSea: null };
  const e = elevation ? cellAt(elevation, lat, lng) : -1;
  if (e < 0 || !elevation.inCity[e]) return none;
  const t = terrain ? cellAt(terrain, lat, lng) : -1;
  const onTerrain = t >= 0 && terrain.inCity[t];
  return {
    inCity: true,
    elevationM: elevation.dm[e] / 10,
    handM: onTerrain ? terrain.hand[t] / 100 : null,
    drainsToSea: onTerrain ? terrain.toSea[t] === 1 : null,
  };
}

const STEPS = [
  [1, 0, 1], [-1, 0, 1], [0, 1, 1], [0, -1, 1],
  [1, 1, Math.SQRT2], [1, -1, Math.SQRT2], [-1, 1, Math.SQRT2], [-1, -1, Math.SQRT2],
];

// Min-heap of [distance, cell] for the spread
class Heap {
  constructor() { this.d = []; this.c = []; }
  get size() { return this.d.length; }
  push(dist, cell) {
    const { d, c } = this;
    let k = d.length;
    d.push(dist); c.push(cell);
    while (k > 0) {
      const p = (k - 1) >> 1;
      if (d[p] <= dist) break;
      d[k] = d[p]; c[k] = c[p]; k = p;
    }
    d[k] = dist; c[k] = cell;
  }
  pop() {
    const { d, c } = this;
    const top = [d[0], c[0]];
    const ld = d.pop(); const lc = c.pop();
    if (d.length) {
      let k = 0;
      for (;;) {
        let ch = 2 * k + 1;
        if (ch >= d.length) break;
        if (ch + 1 < d.length && d[ch + 1] < d[ch]) ch += 1;
        if (d[ch] >= ld) break;
        d[k] = d[ch]; c[k] = c[ch]; k = ch;
      }
      d[k] = ld; c[k] = lc;
    }
    return top;
  }
}

/**
 * Corners of the flooded area around [lat, lng] for a water depth in
 * metres, as { corners, areaM2, note }, or { corners: null, note } with
 * the reason there is none.
 */
export function floodFromDepth(terrain, seed, depthM) {
  if (!terrain) return { corners: null, note: 'Terrain data is still loading.' };
  const { hand, inCity, grid, cellM } = terrain;
  const [fx, fy] = grid.toCell(seed[0], seed[1]);
  const sx = Math.floor(fx);
  const sy = Math.floor(fy);
  if (sx < 0 || sy < 0 || sx >= grid.width || sy >= grid.height) {
    return { corners: null, note: 'That spot is outside the mapped area.' };
  }
  const start = sy * grid.width + sx;
  if (!inCity[start]) return { corners: null, note: 'That spot is outside Talisay City.' };

  const depthCm = depthM * 100;
  const h0 = hand[start];
  const slopeCmPerCell = SURFACE_SLOPE * cellM * 100;
  const maxCells = MAX_FLOOD_REACH_M / cellM;

  const best = new Map([[start, 0]]); // cell -> path distance in cells
  const heap = new Heap();
  heap.push(0, start);
  let hitLimit = false;

  while (heap.size) {
    const [dist, i] = heap.pop();
    if (dist > best.get(i)) continue;
    const x = i % grid.width;
    const y = (i - x) / grid.width;
    for (let s = 0; s < STEPS.length; s += 1) {
      const nx = x + STEPS[s][0];
      const ny = y + STEPS[s][1];
      if (nx < 0 || ny < 0 || nx >= grid.width || ny >= grid.height) continue;
      const j = ny * grid.width + nx;
      if (!inCity[j]) continue;
      const nd = dist + STEPS[s][2];
      const rise = Math.max(0, hand[j] - h0);
      if (rise + slopeCmPerCell * nd > depthCm) continue;
      if (nd > maxCells) { hitLimit = true; continue; }
      if (nd >= (best.get(j) ?? Infinity)) continue;
      best.set(j, nd);
      heap.push(nd, j);
    }
  }

  const region = new Set(best.keys());
  const areaM2 = region.size * cellM * cellM;
  const ring = traceBoundary(region, grid.width);
  if (ring.length < 3) {
    // Too small to outline: a small square around the spot
    const h = 1.5;
    return {
      corners: [[fx - h, fy - h], [fx + h, fy - h], [fx + h, fy + h], [fx - h, fy + h]]
        .map(([x, y]) => grid.toLatLng(x, y)),
      areaM2,
      note: 'The ground rises right away from this spot, so the shape is just the spot. Draw by hand if the water spreads further.',
    };
  }
  const simple = simplifyRing(ring.map(([x, y]) => [x + 0.5, y + 0.5]), 1.2, 60);
  return {
    corners: simple.map(([x, y]) => grid.toLatLng(x, y)),
    areaM2,
    note: hitLimit
      ? `Stopped at ${MAX_FLOOD_REACH_M / 1000} km from the spot. Check the far edge.`
      : null,
  };
}
