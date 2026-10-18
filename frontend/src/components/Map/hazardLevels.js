// Hazard levels on the public map, shaded like a Project NOAH hazard map.
//
// Two layers are combined into one Low / Moderate / High picture:
//
// 1. Past events. Every archived hazard (historical records) warms the area
//    where it happened, weighted by how severe and how recent it was. Places
//    hit again and again add up and turn orange, then red. Places with no
//    record stay clear. History only shades the map; it never creates a
//    hazard, which stays the DRRMO's call.
//
// 2. Live hazards, graded the way Project NOAH grades a flood map. Each
//    published hazard is shaded inside the polygon the officer drew, and
//    nowhere outside it. Inside, the level varies with the ground: the
//    published severity is the WORST level, shown where the terrain is most
//    exposed (the lowest ground for a flood, the steepest slope for a
//    landslide, the densest block for a fire), and less exposed parts step
//    down. A Moderate flood is Moderate along the creek and Low on the
//    higher streets; an Extreme one runs High, Moderate, Low. Every cell
//    inside is at least Low, because the officer declared the whole area
//    affected. Nothing is ever shaded above the published level, so the map
//    never contradicts the alert; overlapping zones show the higher of the
//    two, not a sum.
//
//    It used to shade the whole polygon at the published level, which said
//    nothing about which part was worse, and before that spread out from
//    the pin in a circle whatever shape was drawn.

import { useEffect, useState } from 'react';
import { hazardKey } from './hazardInfo';

// Low / Moderate / High, in the same green / orange / red as the pin severities.
// 'Moderate' matches the pins and the F6 spec (low, moderate, high); the key
// stays 'medium' so nothing that stores it changes.
export const HAZARD_LEVELS = [
  { key: 'low', label: 'Low', color: '#1f9d55' },
  { key: 'medium', label: 'Moderate', color: '#d99a00' },
  { key: 'high', label: 'High', color: '#d64545' },
];

// How much one past event counts, by severity, before it fades with age
const HISTORY_SEVERITY = { Red: 1, Orange: 0.6, Green: 0.3 };
const HISTORY_HALF_LIFE_YEARS = 3; // an event from 3 years ago counts half as much
const HISTORY_BUFFER_M = 50;       // reach a little past the zone that was drawn at the time

// Heat needed for Low, Moderate, High. One recent Extreme event scores about 1 at
// its centre. Floods cover wide areas and return to the same lowlands, so it
// takes repeat floods to turn red; fires and landslides rarely hit the same
// spot twice, so one serious recent one is already enough.
const HISTORY_BREAKS = {
  Flood: [0.15, 0.6, 1.2],
  Landslide: [0.15, 0.4, 0.8],
  Fire: [0.15, 0.4, 0.8],
};
const YEAR_MS = 365.25 * 24 * 3600 * 1000;
const LEVEL_BREAKS = [0.25, 0.4, 0.68]; // score needed for Low, Moderate, High (higher = less of that color)

// How strongly one report counts, by severity
const SEVERITY_WEIGHT = { Red: 1, Orange: 0.72, Green: 0.42 };

// Farthest a report can spread over the easiest ground, in meters. Only used
// when a pin carries no drawn zone; otherwise the zone's own radius is the limit.
const MAX_SPREAD_M = {
  Flood: { Red: 250, Orange: 170, Green: 90 },
  Landslide: { Red: 200, Orange: 130, Green: 70 },
  Fire: { Red: 80, Orange: 40, Green: 15 },  // burned block plus cordon; even a 250-house fire is ~100 m across
};

// Cost of crossing one cell, by susceptibility class 1..5 (Infinity = the hazard stops here).
// Higher cost means the spread runs out sooner on that ground.
const SPREAD_COST = {
  Flood: [Infinity, Infinity, 8, 3, 1.5, 1],
  Landslide: [Infinity, Infinity, Infinity, 3, 1.5, 1],
  Fire: [Infinity, 1.4, 1.2, 1.1, 1, 1],          // the drawn zone is the measured burn, so ground only trims it
};

// The pin's own spot always counts, whatever the ground (meters)
const PIN_SPOT_M = { Flood: 30, Landslide: 20, Fire: 20 };

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

// Spreads one event over the ground from [lat, lng], at most reachM meters and
// only as far as the terrain lets it; calls apply(cellIndex, strength) per cell.
function spreadFrom(position, type, weight, reachM, cls, width, height, project, cell, apply) {
  // At least a cell and a half, so even a kitchen fire shows as a dot
  const budget = Math.max(reachM / cell, 1.5); // in cells
  const costs = SPREAD_COST[type];
  const spot = Math.min(PIN_SPOT_M[type], reachM) / cell;
  const ground = GROUND_FACTOR[type];

  const [fx, fy] = project(position[0], position[1]);
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
      if (strength > 0.01) apply(i, strength);
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

// Cells of the raster inside a zone's drawn polygon, as a Set of cell
// indexes, or null when the zone has no polygon. Rasterised on a canvas
// sized to the polygon's own box, not the whole city, so many zones stay cheap.
function zoneCells(feature, project, width, height) {
  const g = feature?.geometry;
  const polys = g?.type === 'Polygon' ? [g.coordinates] : g?.type === 'MultiPolygon' ? g.coordinates : [];
  if (!polys.length) return null;

  const rings = polys.map((rings_) => rings_.map((ring) => ring.map(([lng, lat]) => project(lat, lng))));
  let minX = Infinity; let minY = Infinity; let maxX = -Infinity; let maxY = -Infinity;
  rings.forEach((poly) => poly[0].forEach(([x, y]) => {
    minX = Math.min(minX, x); minY = Math.min(minY, y); maxX = Math.max(maxX, x); maxY = Math.max(maxY, y);
  }));
  const x0 = Math.max(0, Math.floor(minX));
  const y0 = Math.max(0, Math.floor(minY));
  const x1 = Math.min(width, Math.ceil(maxX) + 1);
  const y1 = Math.min(height, Math.ceil(maxY) + 1);
  if (x1 <= x0 || y1 <= y0) return new Set();

  const canvas = document.createElement('canvas');
  canvas.width = x1 - x0;
  canvas.height = y1 - y0;
  const ctx = canvas.getContext('2d');
  ctx.fillStyle = '#000';
  ctx.beginPath();
  rings.forEach((poly) => poly.forEach((ring) => {
    ring.forEach(([x, y], k) => (k ? ctx.lineTo(x - x0, y - y0) : ctx.moveTo(x - x0, y - y0)));
    ctx.closePath();
  }));
  ctx.fill('evenodd'); // holes stay empty
  const { data } = ctx.getImageData(0, 0, canvas.width, canvas.height);

  const cells = new Set();
  for (let y = 0; y < canvas.height; y += 1) {
    for (let x = 0; x < canvas.width; x += 1) {
      if (data[(y * canvas.width + x) * 4 + 3] > 127) cells.add((y + y0) * width + (x + x0));
    }
  }
  // A zone smaller than one cell still shows as a dot
  if (!cells.size) {
    const [cx, cy] = [Math.floor((minX + maxX) / 2), Math.floor((minY + maxY) / 2)];
    if (cx >= 0 && cy >= 0 && cx < width && cy < height) cells.add(cy * width + cx);
  }
  return cells;
}

// The published severity as a map level: the most a zone can show
const SEVERITY_LEVEL = { Green: 1, Orange: 2, Red: 3 };

// How exposed a cell must be, relative to the most and least exposed ground
// in its own zone (0..1), to keep each level below the published one. An
// Extreme zone shows High on its most exposed 40%-or-so of ground range,
// Moderate in the middle, Low on the safest; a Moderate zone splits into
// Moderate and Low; a Low zone is Low throughout.
const STEP_DOWN_AT = { 3: [0.6, 0.25], 2: [0.4], 1: [] };

// How far round each cell the ground is averaged, in cells. Wide enough
// that the change from the most to the least exposed ground passes through
// the middle level, as on a NOAH map, instead of jumping High to Low.
const SMOOTH_CELLS = 2;

// A cell's susceptibility class averaged with its neighbours inside the
// zone, so the grading follows the lie of the land instead of speckling
// cell by cell. 0 when the cell is outside the city.
function smoothedClass(cls, i, width, height, inside) {
  if (!cls[i]) return 0;
  const x = i % width;
  const y = (i - x) / width;
  let sum = 0;
  let n = 0;
  for (let dy = -SMOOTH_CELLS; dy <= SMOOTH_CELLS; dy += 1) {
    for (let dx = -SMOOTH_CELLS; dx <= SMOOTH_CELLS; dx += 1) {
      const nx = x + dx;
      const ny = y + dy;
      if (nx < 0 || ny < 0 || nx >= width || ny >= height) continue;
      const j = ny * width + nx;
      if (!cls[j] || !inside.has(j)) continue;
      sum += cls[j];
      n += 1;
    }
  }
  return n ? sum / n : cls[i];
}

function levelForExposure(rank, cap) {
  let level = cap;
  for (const t of STEP_DOWN_AT[cap] || []) {
    if (rank >= t) break;
    level -= 1;
  }
  return Math.max(level, 1);
}

// A live hazard: writes its graded level into live[], keeping the higher
// level where zones overlap.
function gradePin(pin, type, cls, width, height, project, cell, live) {
  const cap = SEVERITY_LEVEL[pin.severity] ?? 1;
  const inside = zoneCells(pin.feature, project, width, height);

  if (!inside) {
    // No drawn polygon (older data): spread from the pin over the ground,
    // still never above the published level
    const weight = SEVERITY_WEIGHT[pin.severity] ?? SEVERITY_WEIGHT.Green;
    const reachM = pin.radius || MAX_SPREAD_M[type][pin.severity] || MAX_SPREAD_M[type].Green;
    spreadFrom(pin.position, type, weight, reachM, cls, width, height, project, cell, (i, s) => {
      const level = s >= LEVEL_BREAKS[2] ? 3 : s >= LEVEL_BREAKS[1] ? 2 : s >= LEVEL_BREAKS[0] ? 1 : 0;
      const capped = Math.min(level, cap);
      if (capped > live[i]) live[i] = capped;
    });
    return;
  }

  // Exposure of every cell in the zone, then where each sits between the
  // zone's own least and most exposed ground
  const exposure = new Map();
  let lo = Infinity;
  let hi = -Infinity;
  inside.forEach((i) => {
    const e = smoothedClass(cls, i, width, height, inside);
    if (!e) return; // outside the city
    exposure.set(i, e);
    if (e < lo) lo = e;
    if (e > hi) hi = e;
  });
  const span = hi - lo;

  exposure.forEach((e, i) => {
    // Flat ground all through: nothing to tell apart, the whole zone is at
    // the published level
    const rank = span > 0.25 ? (e - lo) / span : 1;
    const level = levelForExposure(rank, cap);
    if (level > live[i]) live[i] = level;
  });
}

// A past event: heat adds up, so places hit repeatedly climb the levels
function spreadPast(spot, type, now, cls, width, height, project, cell, heat) {
  const ageYears = Math.max(0, (now - new Date(spot.occurred_at).getTime()) / YEAR_MS);
  const weight = (HISTORY_SEVERITY[spot.severity] ?? HISTORY_SEVERITY.Green)
    * Math.pow(0.5, ageYears / HISTORY_HALF_LIFE_YEARS);
  const reachM = (spot.radius || 100) + HISTORY_BUFFER_M;
  spreadFrom([spot.lat, spot.lng], type, weight, reachM, cls, width, height, project, cell, (i, strength) => {
    heat[i] += strength;
  });
}

function computeLevels({ grids, index, hazards, history, types }) {
  const { width, height } = grids.flood;
  const project = makeProjector(index.bounds, width, height);
  const cell = index.cellSizeM || 10;
  const base = new Uint8Array(width * height); // level from past events, 0..3
  const live = new Uint8Array(width * height); // graded level of live hazards, 0..3
  const now = Date.now();

  (types && types.length ? types : TYPES_FOR_LAYER.all).forEach((type) => {
    const { cls } = grids[LAYER_FILE[type]];

    const past = (history || []).filter((h) => hazardKey(h.type) === type);
    if (past.length) {
      const heat = new Float32Array(width * height);
      past.forEach((spot) => spreadPast(spot, type, now, cls, width, height, project, cell, heat));
      const [low, medium, high] = HISTORY_BREAKS[type];
      for (let i = 0; i < heat.length; i += 1) {
        const h = heat[i];
        const l = h >= high ? 3 : h >= medium ? 2 : h >= low ? 1 : 0;
        if (l > base[i]) base[i] = l;
      }
    }

    hazards
      .filter((h) => hazardKey(h.type) === type && h.position)
      .forEach((pin) => gradePin(pin, type, cls, width, height, project, cell, live));
  });

  const image = new ImageData(width, height);
  const px = image.data;
  let colored = 0;
  for (let i = 0, p = 0; i < live.length; i += 1, p += 4) {
    // Past events and live hazards are separate facts; show the worse.
    // A live zone is never pushed above its own graded level.
    const level = Math.max(base[i], live[i]);
    if (!level) continue;

    const [r, g, b] = LEVEL_RGB[level - 1];
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
 * Image URL of the hazard-level layer (past events plus live hazards) for the
 * visible hazard types, or null when nothing should be colored. history is the
 * spots list from GET /api/history/heat/. Pass an array of type names
 * (['Flood', 'Fire']) or the legacy layer key. Needs the susceptibility index
 * from useSusceptibility().
 */
export function useHazardLevelLayer(index, hazards, types, history) {
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
    setUrl(list.length ? computeLevels({ grids, index, hazards, history, types: list }) : null);
  }, [grids, index, hazards, history, typeKey]);

  return url;
}