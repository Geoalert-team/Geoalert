/**
 * Go / no-go check after rebuilding the hazard index (terrain spec,
 * "Verification after the rebuild"). Runs the real floodFromDepth for
 * knee-deep water at 12 low-plain spots on the old and the new terrain.png
 * and fails when the new data makes floods implausibly small.
 *
 * Skipped unless FLOOD_CHECK_DIR points at a folder of raw RGBA dumps:
 *   old_terrain.rgba, new_terrain.rgba, new_elevation.rgba and meta.json
 *   ({ name: { width, height, bounds, cellM } }).
 */
import fs from 'fs';
import path from 'path';
import { decodeElevationPixels, decodeTerrainPixels, floodFromDepth } from './terrain';
import { makeGrid } from './gridGeometry';

const DIR = process.env.FLOOD_CHECK_DIR;
const KNEE_M = 0.5;
const LOW_DM = 100; // ground below 10 m
const COLLAPSED = 'The ground rises right away';
const FIXED = [[10.23752, 123.83510], [10.24056, 123.83424], [10.23541, 123.83158], [10.25340, 123.83433]];
const LATTICE_X = [0.125, 0.375, 0.625, 0.875];
const LATTICE_Y = [0.25, 0.75];

function load(meta, name, decode) {
  const m = meta[name];
  const rgba = new Uint8Array(fs.readFileSync(path.join(DIR, `${name}.rgba`)));
  return { ...decode(rgba, m.width * m.height), grid: makeGrid(m.bounds, m.width, m.height), cellM: m.cellM };
}

// For each point of a 4 x 2 lattice over the low city cells' bounding box, the nearest low cell
function latticeSpots(elev) {
  const { width } = elev.grid;
  const low = [];
  elev.dm.forEach((dm, i) => {
    if (elev.inCity[i] && dm < LOW_DM) low.push([i % width, Math.floor(i / width)]);
  });
  const xs = low.map((c) => c[0]);
  const ys = low.map((c) => c[1]);
  const [x0, x1, y0, y1] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)];
  const spots = [];
  LATTICE_Y.forEach((fy) => LATTICE_X.forEach((fx) => {
    const tx = x0 + fx * (x1 - x0);
    const ty = y0 + fy * (y1 - y0);
    let best = low[0];
    let bestD = Infinity;
    low.forEach(([x, y]) => {
      const d = (x - tx) ** 2 + (y - ty) ** 2;
      if (d < bestD) { bestD = d; best = [x, y]; }
    });
    spots.push(elev.grid.toLatLng(best[0] + 0.5, best[1] + 0.5));
  }));
  return spots;
}

const median = (values) => {
  const s = [...values].sort((a, b) => a - b);
  const m = s.length >> 1;
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
};

const hectares = (r) => (r.corners ? r.areaM2 / 1e4 : 0);

(DIR ? describe : describe.skip)('knee-deep flood reach after a hazard-index rebuild', () => {
  test('median knee-deep area is 1-6 ha and at most 2 of 12 spots collapse', () => {
    const meta = JSON.parse(fs.readFileSync(path.join(DIR, 'meta.json'), 'utf8'));
    const oldTerrain = load(meta, 'old_terrain', decodeTerrainPixels);
    const newTerrain = load(meta, 'new_terrain', decodeTerrainPixels);
    const elevation = load(meta, 'new_elevation', decodeElevationPixels);

    const rows = [...FIXED, ...latticeSpots(elevation)].map((spot) => {
      const before = floodFromDepth(oldTerrain, spot, KNEE_M);
      const after = floodFromDepth(newTerrain, spot, KNEE_M);
      return {
        spot: spot.map((v) => v.toFixed(5)).join(', '),
        oldHa: hectares(before),
        newHa: hectares(after),
        collapsed: (after.note || '').startsWith(COLLAPSED),
        note: after.corners ? '' : (after.note || 'no shape'),
      };
    });

    // One log call, so Jest prints the table as one block
    console.log([
      'spot                    old ha  new ha  collapsed',
      ...rows.map((r) => `${r.spot.padEnd(22)} ${r.oldHa.toFixed(2).padStart(7)} ${r.newHa.toFixed(2).padStart(7)}  ${r.collapsed ? 'yes' : 'no'} ${r.note}`),
      `median: old ${median(rows.map((r) => r.oldHa)).toFixed(2)} ha, new ${median(rows.map((r) => r.newHa)).toFixed(2)} ha`,
    ].join('\n'));

    const newMedian = median(rows.map((r) => r.newHa));
    expect(newMedian).toBeGreaterThanOrEqual(1);
    expect(newMedian).toBeLessThanOrEqual(6);
    expect(rows.filter((r) => r.collapsed).length).toBeLessThanOrEqual(2);
  });
});
