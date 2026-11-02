/**
 * The ground at a spot on the map: height above the nearest drainage (HAND)
 * and height above sea level, read from the hazard index rasters. Shown by
 * the map's spot reading (components/Map/SpotReading.jsx).
 *
 * Accuracy is limited by the elevation data (Copernicus GLO-30, about 30 m,
 * about 1 m off on flat ground and more among buildings).
 *
 * Data: hazard-index/terrain.png and elevation.png, written by
 *   manage.py build_hazard_index --terrain-only
 * terrain.png: HAND in cm = R * 256 + G; B = 0 outside the city, 255 inside
 * when the height is measured against a waterway, 200 against the sea.
 * elevation.png: height above sea level in dm = R * 256 + G; B = 255 inside.
 */

import { makeGrid } from './gridGeometry';

const BASE = `${process.env.PUBLIC_URL || ''}/hazard-index`;

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
    .catch(() => {
      // Forget a failed load, so the next tap tries again instead of the
      // feature staying off until the page is reloaded
      if (cached[entry]?.promise === promise) delete cached[entry];
      return null;
    });
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
