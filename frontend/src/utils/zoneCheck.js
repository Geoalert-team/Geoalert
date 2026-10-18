/**
 * A second look at a drawn zone, against the susceptibility map, before it
 * is published. Two things a hand-drawn outline commonly gets wrong:
 *
 *   * it sits mostly on ground rated safe for this hazard (wrong spot, or
 *     drawn far too wide), and
 *   * it stops short: ground rated High or Very high runs on right past
 *     the edge, where the hazard most likely reaches too.
 *
 * Advice only. The officer saw the ground; the map did not. Nothing here
 * blocks a publish. Rule-based comparison with the layers, no AI.
 */

import { loadClassGrid } from '../components/Map/hazardLevels';
import { cellsInPolygon, makeGrid } from './gridGeometry';

const LAYER = { Flood: 'flood', Landslide: 'landslide', Fire: 'fire' };

// How far outside the outline to look for risky ground, in metres
const RING_M = 50;
// Warn when this share of the zone is on Very low / Low ground
const LOW_SHARE_WARN = 0.6;
// Warn when risky ground just outside is at least this share of the zone
const OUTSIDE_SHARE_WARN = 0.25;
const OUTSIDE_MIN_M2 = 500;

const cache = new Map(); // layer -> Promise<grid>

function classGrid(index, layer) {
  const key = `${layer}@${index.generated || ''}`;
  if (!cache.has(key)) cache.set(key, loadClassGrid(index, layer).catch(() => null));
  return cache.get(key);
}

/**
 * Resolves to { lowShare, outsideHighM2, areaM2, warnings: [string] }, or
 * null when this hazard type has no susceptibility layer.
 */
export async function checkZone(points, hazardTypeName, index) {
  const layer = LAYER[hazardTypeName];
  if (!layer || !index || points.length < 3) return null;
  const raster = await classGrid(index, layer);
  if (!raster) return null;

  const grid = makeGrid(index.bounds, raster.width, raster.height);
  const cellM = index.cellSizeM || 10;
  const inside = cellsInPolygon(points, grid);
  const counted = [...inside].filter((i) => raster.cls[i] > 0); // inside the city
  if (!counted.length) return null;

  const low = counted.filter((i) => raster.cls[i] <= 2).length;
  const lowShare = low / counted.length;

  // Risky ground in a band just outside the outline
  const r = Math.max(1, Math.round(RING_M / cellM));
  const outside = new Set();
  inside.forEach((i) => {
    const x = i % raster.width;
    const y = (i - x) / raster.width;
    for (let dy = -r; dy <= r; dy += 1) {
      for (let dx = -r; dx <= r; dx += 1) {
        if (dx * dx + dy * dy > r * r) continue;
        const nx = x + dx;
        const ny = y + dy;
        if (nx < 0 || ny < 0 || nx >= raster.width || ny >= raster.height) continue;
        const j = ny * raster.width + nx;
        if (!inside.has(j) && raster.cls[j] >= 4) outside.add(j);
      }
    }
  });

  const areaM2 = counted.length * cellM * cellM;
  const outsideHighM2 = outside.size * cellM * cellM;
  const word = hazardTypeName.toLowerCase();
  const warnings = [];
  if (lowShare >= LOW_SHARE_WARN) {
    warnings.push(
      `${Math.round(lowShare * 100)}% of this outline is on ground the map rates Low or Very low for ${word}s. `
      + 'Check it is in the right place and not drawn too wide.',
    );
  }
  if (outsideHighM2 >= OUTSIDE_MIN_M2 && outsideHighM2 >= areaM2 * OUTSIDE_SHARE_WARN) {
    warnings.push(
      `About ${formatM2(outsideHighM2)} of ground rated High or Very high for ${word}s lies within ${RING_M} m outside the edge. `
      + 'The hazard may reach further than drawn.',
    );
  }
  return { lowShare, outsideHighM2, areaM2, warnings };
}

function formatM2(m2) {
  return m2 >= 10000 ? `${(m2 / 10000).toFixed(1)} ha` : `${Math.round(m2 / 10) * 10} m²`;
}
