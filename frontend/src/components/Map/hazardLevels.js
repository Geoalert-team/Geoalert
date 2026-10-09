// Hazard levels on the public map, driven by active reports (pins).
//
// Nothing is colored until the DRRMO publishes a hazard. Each pin then spreads
// outward over the ground, but only as far as the terrain lets it: a flood
// creeps along low, flood-prone cells and stops at higher ground, a landslide
// follows steep slopes, a fire follows dense built-up blocks. Spread is limited
// by severity (a few hundred meters at most), so a report colors the streets
// that are actually at risk, not the whole barangay. Pins close together add
// up, so a cluster of reports turns the area red.

import { useEffect, useState } from 'react';
import { hazardKey } from './hazardInfo';

// Low / Medium / High, colored like Project NOAH
export const HAZARD_LEVELS = [
  { key: 'low', label: 'Low', color: '#f7c948' },
  { key: 'medium', label: 'Medium', color: '#f5923e' },
  { key: 'high', label: 'High', color: '#e5484d' },
];
const LEVEL_BREAKS = [0.25, 0.4, 0.68]; // score needed for Low, Medium, High (higher = less of that color)

// How strongly one report counts, by severity
const SEVERITY_WEIGHT = { Red: 1, Orange: 0.72, Green: 0.42 };

// Farthest a report can spread over the easiest ground, in meters
const MAX_SPREAD_M = {
  Flood: { Red: 250, Orange: 170, Green: 90 },
  Landslide: { Red: 200, Orange: 130, Green: 70 },
  Fire: { Red: 350, Orange: 250, Green: 130 },  // structure fires jump between houses; danger zone includes smoke and evacuation
};

// Cost of crossing one cell, by susceptibility class 1..5 (Infinity = the hazard stops here).
// Higher cost means the spread runs out sooner on that ground.
const SPREAD_COST = {
  Flood: [Infinity, Infinity, 8, 3, 1.5, 1],
  Landslide: [Infinity, Infinity, Infinity, 3, 1.5, 1],
  Fire: [Infinity, 3.5, 2, 1.4, 1.15, 1],         // never fully stops; open ground only slows it
};

// The pin's own spot always counts, whatever the ground (meters)
const PIN_SPOT_M = { Flood: 30, Landslide: 30, Fire: 80 };

// How much of a report's strength shows on each class of ground
const GROUND_FACTOR = {
  Flood: [0, 0.5, 0.65, 0.8, 0.9, 1],
  Landslide: [0, 0.5, 0.65, 0.8, 0.9, 1],
  Fire: [0, 0.8, 0.88, 0.94, 1, 1], // a burning block threatens its neighbors even where fewer buildings are mapped
};

const LAYER_FILE = { Flood: 'flood', Landslide: 'landslide', Fire: 'fire' };
const TYPES_FOR_LAYER = { all: ['Flood', 'Landslide', 'Fire'], flood: ['Flood'], landslide: ['Landslide'], fire: ['Fire'] };

const BASE = `${process.env.PUBLIC_URL || ''}/hazard-index`;

/* ---------- Raster helpers ---------- */

function hexToRgb(hex) {
  const n = parseInt(hex.slice(1), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}
const LEVEL_RGB = HAZARD_LEVELS.map((l) => hexToRgb(l.color));

const mercY = (lat) => {
  const s = Math.sin((lat * Math.PI) / 180);
  return 0.5 - Math.log((1 + s) / (1 - s)) / (4 * Math.PI);
};

// lat/lng -> pixel in the raster (the raster is aligned to Web Mercator)
function makeProjector(bounds, width, height) {
  const [[south, west], [north, east]] = bounds;
  const y0 = mercY(north);
  const y1 = mercY(south);
  return (lat, lng) => [((lng - west) / (east - west)) * width, ((mercY(lat) - y0) / (y1 - y0)) * height];
}

function loadImage(url) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = reject;
    img.src = url;
  });
}

// Reads one susceptibility PNG back into class numbers (0 = outside the city, 1..5)
async function loadClassGrid(index, layer) {
  const img = await loadImage(`${BASE}/${index.layers[layer]}?v=${encodeURIComponent(index.generated || '')}`);
  const canvas = document.createElement('canvas');
  canvas.width = img.width;
  canvas.height = img.height;
  const ctx = canvas.getContext('2d');
  ctx.drawImage(img, 0, 0);
  const { data } = ctx.getImageData(0, 0, img.width, img.height);

  const lookup = new Map(index.classes.map((c, i) => {
    const [r, g, b] = hexToRgb(c.color);
    return [(r << 16) | (g << 8) | b, i + 1];
  }));
  const cls = new Uint8Array(img.width * img.height);
  for (let i = 0, p = 0; i < cls.length; i += 1, p += 4) {
    if (data[p + 3] > 0) cls[i] = lookup.get((data[p] << 16) | (data[p + 1] << 8) | data[p + 2]) || 0;
  }
  return { width: img.width, height: img.height, cls };
}

/* ---------- The model ---------- */

// Min-heap of [cost, cellIndex] for the spread search
class Heap {
  constructor() { this.cost = []; this.cell = []; }
  get size() { return this.cost.length; }
  push(c, i) {
    const { cost, cell } = this;
    let k = cost.length;
    cost.push(c); cell.push(i);
    while (k > 0) {
      const parent = (k - 1) >> 1;
      if (cost[parent] <= c) break;
      cost[k] = cost[parent]; cell[k] = cell[parent];
      k = parent;
    }
    cost[k] = c; cell[k] = i;
  }
  pop() {
    const { cost, cell } = this;
    const top = [cost[0], cell[0]];
    const lastC = cost.pop(); const lastI = cell.pop();
    if (cost.length) {
      let k = 0;
      const n = cost.length;
      for (;;) {
        let child = 2 * k + 1;
        if (child >= n) break;
        if (child + 1 < n && cost[child + 1] < cost[child]) child += 1;
        if (cost[child] >= lastC) break;
        cost[k] = cost[child]; cell[k] = cell[child];
        k = child;
      }
      cost[k] = lastC; cell[k] = lastI;
    }
    return top;
  }
}

const STEPS = [[1, 0, 1], [-1, 0, 1], [0, 1, 1], [0, -1, 1], [1, 1, Math.SQRT2], [1, -1, Math.SQRT2], [-1, 1, Math.SQRT2], [-1, -1, Math.SQRT2]];

// Spreads one report over the ground from its pin; multiplies keep[] by (1 - strength)
function spreadPin(pin, type, cls, width, height, project, cell, keep) {
  const weight = SEVERITY_WEIGHT[pin.severity] ?? SEVERITY_WEIGHT.Green;
  const budget = (MAX_SPREAD_M[type][pin.severity] ?? MAX_SPREAD_M[type].Green) / cell; // in cells
  const costs = SPREAD_COST[type];
  const spot = PIN_SPOT_M[type] / cell;
  const ground = GROUND_FACTOR[type];

  const [fx, fy] = project(pin.position[0], pin.position[1]);
  const px = Math.floor(fx);
  const py = Math.floor(fy);
  if (px < 0 || py < 0 || px >= width || py >= height) return;

  const best = new Map(); // cell index -> cost so far
  const heap = new Heap();
  const start = py * width + px;
  best.set(start, 0);
  heap.push(0, start);

  while (heap.size) {
    const [c, i] = heap.pop();
    if (c > (best.get(i) ?? Infinity)) continue;
    const x = i % width;
    const y = (i - x) / width;

    const k = cls[i];
    if (k) {
      const strength = weight * Math.pow(1 - c / budget, 0.8) * ground[k];
      if (strength > 0.01) keep[i] *= 1 - strength;
    }

    for (let s = 0; s < STEPS.length; s += 1) {
      const nx = x + STEPS[s][0];
      const ny = y + STEPS[s][1];
      if (nx < 0 || ny < 0 || nx >= width || ny >= height) continue;
      const j = ny * width + nx;
      if (!cls[j]) continue; // outside the city
      const nearPin = Math.hypot(nx + 0.5 - fx, ny + 0.5 - fy) <= spot;
      const step = (nearPin ? 1 : costs[cls[j]]) * STEPS[s][2];
      const next = c + step;
      if (next >= budget || next >= (best.get(j) ?? Infinity)) continue;
      best.set(j, next);
      heap.push(next, j);
    }
  }
}

function computeLevels({ grids, index, hazards, types }) {
  const { width, height } = grids.flood;
  const project = makeProjector(index.bounds, width, height);
  const cell = index.cellSizeM || 10;
  const score = new Float32Array(width * height);
  let anything = false;

  (types && types.length ? types : TYPES_FOR_LAYER.all).forEach((type) => {
    const pins = hazards.filter((h) => hazardKey(h.type) === type && h.position);
    if (!pins.length) return;
    anything = true;

    // keep[i] = share of the cell NOT affected by any pin; nearby pins multiply up
    const keep = new Float32Array(width * height).fill(1);
    const { cls } = grids[LAYER_FILE[type]];
    pins.forEach((pin) => spreadPin(pin, type, cls, width, height, project, cell, keep));

    for (let i = 0; i < score.length; i += 1) {
      if (keep[i] === 1) continue;
      const s = 1 - keep[i];
      if (s > score[i]) score[i] = s;
    }
  });

  if (!anything) return null;

  const image = new ImageData(width, height);
  const px = image.data;
  let colored = 0;
  for (let i = 0, p = 0; i < score.length; i += 1, p += 4) {
    const s = score[i];
    let level = -1;
    if (s >= LEVEL_BREAKS[2]) level = 2;
    else if (s >= LEVEL_BREAKS[1]) level = 1;
    else if (s >= LEVEL_BREAKS[0]) level = 0;
    if (level < 0) continue;
    const [r, g, b] = LEVEL_RGB[level];
    px[p] = r;
    px[p + 1] = g;
    px[p + 2] = b;
    px[p + 3] = 255;
    colored += 1;
  }
  if (!colored) return null;

  // Soften the cell edges slightly
  const raw = document.createElement('canvas');
  raw.width = width;
  raw.height = height;
  raw.getContext('2d').putImageData(image, 0, 0);
  const out = document.createElement('canvas');
  out.width = width;
  out.height = height;
  const ctx = out.getContext('2d');
  ctx.filter = 'blur(0.5px)';
  ctx.drawImage(raw, 0, 0);
  return out.toDataURL('image/png');
}

// F6 turned the single-select filter into checkboxes, so this now takes a list
// of hazard types. The old single layer key ('all' | 'flood' | ...) still works.
function normaliseTypes(types) {
  if (!types) return TYPES_FOR_LAYER.all;
  if (typeof types === 'string') return TYPES_FOR_LAYER[types] || TYPES_FOR_LAYER.all;
  return Array.isArray(types) ? types : TYPES_FOR_LAYER.all;
}

/**
 * Image URL of the hazard-level layer for the current pins and visible hazard
 * types, or null when nothing should be colored. Pass an array of type names
 * (['Flood', 'Fire']) or the legacy layer key. Needs the susceptibility index
 * from useSusceptibility().
 */
export function useHazardLevelLayer(index, hazards, types) {
  const [grids, setGrids] = useState(null);
  const [url, setUrl] = useState(null);

  useEffect(() => {
    if (!index) return undefined;
    let cancelled = false;
    Promise.all(['flood', 'landslide', 'fire'].map((layer) => loadClassGrid(index, layer)))
      .then(([flood, landslide, fire]) => {
        if (!cancelled) setGrids({ flood, landslide, fire });
      })
      .catch(() => {
        if (!cancelled) setGrids(null);
      });
    return () => {
      cancelled = true;
    };
  }, [index]);

  // A plain array would be a new reference on every render and re-run the
  // model each time, so the effect keys off a stable string instead.
  const typeKey = normaliseTypes(types).slice().sort().join(',');

  useEffect(() => {
    if (!grids || !index) {
      setUrl(null);
      return;
    }
    const list = typeKey ? typeKey.split(',') : [];
    setUrl(list.length ? computeLevels({ grids, index, hazards, types: list }) : null);
  }, [grids, index, hazards, typeKey]);

  return url;
}