/**
 * Plain-language lines about one spot on the map: how high the ground is,
 * how far above the nearest place water drains to, the nearest named river
 * and the susceptibility there. Shared by the public "This spot" section
 * and the publish panel, so both always say the same thing.
 *
 * Heights are rounded so they never look more precise than the data
 * (Copernicus GLO-30, about 30 m detail, about 1 m off on flat ground).
 */

export const ACCURACY_NOTE = 'Heights come from satellite data (about 30 m detail) and can be off by about 1 m, more among buildings.';

// The drainage the height is measured against is often an unnamed drain or
// an elevation-derived channel, not a mapped river, so it is never named.
const WATERWAY = 'the nearest creek, drain or low channel';
const LEVEL_BELOW_M = 0.5;
const HALF_METRES_BELOW_M = 5;
const MAX_STATED_M = 10;
const M_PER_DEG_LAT = 111320;

const HAZARDS = [['flood', 'Flood'], ['landslide', 'Landslide'], ['fire', 'Fire']];

/**
 * { ground, waterway } for a readSpot() result; either is null when there
 * is nothing to say. No waterway line when the height is measured against
 * the sea: "above sea level" already says it.
 */
export function describeSpot({ elevationM, handM, drainsToSea }) {
  let ground = null;
  if (elevationM != null) {
    const m = Math.round(elevationM);
    ground = m <= 0 ? 'about at sea level' : `about ${m} m above sea level`;
  }

  let waterway = null;
  if (handM != null && !drainsToSea) {
    if (handM < LEVEL_BELOW_M) {
      waterway = `About level with ${WATERWAY}.`;
    } else if (handM > MAX_STATED_M) {
      waterway = `More than ${MAX_STATED_M} m above ${WATERWAY}.`;
    } else {
      const m = handM < HALF_METRES_BELOW_M ? Math.round(handM * 2) / 2 : Math.round(handM);
      waterway = `About ${m} m above ${WATERWAY}. Water would have to rise about that much to reach here.`;
    }
  }
  return { ground, waterway };
}

/**
 * "Susceptibility: Flood High · Landslide Low · Fire Very low" from class
 * numbers (1-5, 0 = no reading) and the index's class labels, or null.
 */
export function describeSusceptibility(classes, labels) {
  const parts = HAZARDS
    .filter(([key]) => classes?.[key] > 0 && labels?.[classes[key] - 1])
    .map(([key, name]) => `${name} ${labels[classes[key] - 1].label}`);
  return parts.length ? `Susceptibility: ${parts.join(' · ')}` : null;
}

// Distance from the origin to segment a-b, in the same units
function toSegment([ax, ay], [bx, by]) {
  const dx = bx - ax;
  const dy = by - ay;
  const len2 = dx * dx + dy * dy;
  const t = len2 ? Math.max(0, Math.min(1, -(ax * dx + ay * dy) / len2)) : 0;
  return Math.hypot(ax + t * dx, ay + t * dy);
}

/**
 * The closest river line with a name, as { name, distanceM }, or null when
 * none is within maxM. Distances are flat-earth metres around the spot,
 * which is plenty at city scale.
 */
export function nearestNamedRiver(rivers, lat, lng, maxM = 2000) {
  const mPerDegLng = M_PER_DEG_LAT * Math.cos((lat * Math.PI) / 180);
  let best = null;
  (rivers?.features || []).forEach((f) => {
    const name = (f?.properties?.name || '').trim();
    if (!name || f.geometry?.type !== 'LineString') return;
    const pts = f.geometry.coordinates.map(([x, y]) => [(x - lng) * mPerDegLng, (y - lat) * M_PER_DEG_LAT]);
    for (let i = 1; i < pts.length; i += 1) {
      const d = toSegment(pts[i - 1], pts[i]);
      if (!best || d < best.distanceM) best = { name, distanceM: d };
    }
  });
  return best && best.distanceM <= maxM ? best : null;
}

/** "10 m", "990 m", "1.2 km": tens of metres, kilometres from 1000 m. */
export function formatDistance(m) {
  const tens = Math.round(m / 10) * 10;
  return tens < 1000 ? `${tens} m` : `${(m / 1000).toFixed(1)} km`;
}
