/**
 * Geometry on the hazard-index raster grid (Web Mercator, north up), and a
 * few plain polygon helpers. Shared by the shape methods and the zone check.
 */

const mercY = (lat) => {
  const s = Math.sin((lat * Math.PI) / 180);
  return 0.5 - Math.log((1 + s) / (1 - s)) / (4 * Math.PI);
};

const latFromMercY = (y) => {
  const t = (0.5 - y) * 4 * Math.PI;
  return (Math.asin(Math.tanh(t / 2)) * 180) / Math.PI;
};

/**
 * Maps between [lat, lng] and fractional cell coordinates for a raster
 * covering `bounds` ([[south, west], [north, east]]) at width x height.
 */
export function makeGrid(bounds, width, height) {
  const [[south, west], [north, east]] = bounds;
  const y0 = mercY(north);
  const y1 = mercY(south);
  return {
    width,
    height,
    toCell: (lat, lng) => [((lng - west) / (east - west)) * width, ((mercY(lat) - y0) / (y1 - y0)) * height],
    toLatLng: (x, y) => [latFromMercY(y0 + (y / height) * (y1 - y0)), west + (x / width) * (east - west)],
  };
}

/** Ray-casting point-in-polygon on [x, y] pairs. */
export function insideRing(x, y, ring) {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i, i += 1) {
    const [xi, yi] = ring[i];
    const [xj, yj] = ring[j];
    if ((yi > y) !== (yj > y) && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}

/**
 * Cells whose centre lies inside the polygon of [lat, lng] corners, as a
 * Set of indexes (y * width + x). Only the polygon's bounding box is scanned.
 */
export function cellsInPolygon(points, grid) {
  const ring = points.map(([lat, lng]) => grid.toCell(lat, lng));
  const xs = ring.map((p) => p[0]);
  const ys = ring.map((p) => p[1]);
  const x0 = Math.max(0, Math.floor(Math.min(...xs)));
  const x1 = Math.min(grid.width - 1, Math.ceil(Math.max(...xs)));
  const y0 = Math.max(0, Math.floor(Math.min(...ys)));
  const y1 = Math.min(grid.height - 1, Math.ceil(Math.max(...ys)));
  const cells = new Set();
  for (let y = y0; y <= y1; y += 1) {
    for (let x = x0; x <= x1; x += 1) {
      if (insideRing(x + 0.5, y + 0.5, ring)) cells.add(y * grid.width + x);
    }
  }
  return cells;
}

// Clockwise from west, in screen coordinates (y grows downward)
const DIRS = [[-1, 0], [-1, -1], [0, -1], [1, -1], [1, 0], [1, 1], [0, 1], [-1, 1]];

/**
 * Outer boundary of one 8-connected region of cells, traced with Moore
 * neighbourhood tracing. Returns [x, y] cell coordinates in order. Holes
 * are not traced: a dry island inside a flood stays part of the zone,
 * which errs on the side of warning.
 */
export function traceBoundary(region, width) {
  let start = -1;
  region.forEach((i) => { if (start === -1 || i < start) start = i; }); // first in raster order
  if (start === -1) return [];
  const has = (x, y) => x >= 0 && y >= 0 && x < width && region.has(y * width + x);

  const sx = start % width;
  const sy = (start - sx) / width;
  const out = [[sx, sy]];
  let px = sx;
  let py = sy;
  let back = 0; // the cell west of the first one in raster order is outside
  let second = null;
  const limit = region.size * 4 + 16;

  for (let step = 0; step < limit; step += 1) {
    let moved = false;
    for (let k = 1; k <= 8; k += 1) {
      const d = (back + k) % 8;
      const qx = px + DIRS[d][0];
      const qy = py + DIRS[d][1];
      if (!has(qx, qy)) continue;
      // The neighbour checked just before q becomes q's backtrack
      const bx = px + DIRS[(d + 7) % 8][0];
      const by = py + DIRS[(d + 7) % 8][1];
      back = DIRS.findIndex(([dx, dy]) => dx === bx - qx && dy === by - qy);
      if (back < 0) back = 0;
      if (px === sx && py === sy && second && qx === second[0] && qy === second[1]) {
        return out.slice(0, -1); // back where it started, about to repeat
      }
      if (!second) second = [qx, qy];
      px = qx;
      py = qy;
      out.push([qx, qy]);
      moved = true;
      break;
    }
    if (!moved) break; // a single isolated cell
  }
  return out;
}

function perpendicular(p, a, b) {
  const dx = b[0] - a[0];
  const dy = b[1] - a[1];
  const len = Math.hypot(dx, dy);
  if (!len) return Math.hypot(p[0] - a[0], p[1] - a[1]);
  return Math.abs(dy * p[0] - dx * p[1] + b[0] * a[1] - b[1] * a[0]) / len;
}

/** Douglas-Peucker on an open polyline. */
export function simplifyLine(points, tolerance) {
  if (points.length < 3) return points.slice();
  let maxD = 0;
  let index = 0;
  for (let i = 1; i < points.length - 1; i += 1) {
    const d = perpendicular(points[i], points[0], points[points.length - 1]);
    if (d > maxD) { maxD = d; index = i; }
  }
  if (maxD <= tolerance) return [points[0], points[points.length - 1]];
  const left = simplifyLine(points.slice(0, index + 1), tolerance);
  const right = simplifyLine(points.slice(index), tolerance);
  return [...left.slice(0, -1), ...right];
}

/**
 * Simplify a closed ring to at most maxCorners, starting at `tolerance`
 * (in the ring's units) and loosening until it fits.
 */
export function simplifyRing(ring, tolerance, maxCorners = 60) {
  if (ring.length <= 3) return ring;
  // Split at the point farthest from the first, so both halves are open lines
  let far = 0;
  let farD = -1;
  ring.forEach((p, i) => {
    const d = Math.hypot(p[0] - ring[0][0], p[1] - ring[0][1]);
    if (d > farD) { farD = d; far = i; }
  });
  let tol = tolerance;
  let out = ring;
  for (let attempt = 0; attempt < 12; attempt += 1) {
    const a = simplifyLine(ring.slice(0, far + 1), tol);
    const b = simplifyLine([...ring.slice(far), ring[0]], tol);
    out = [...a.slice(0, -1), ...b.slice(0, -1)];
    if (out.length <= maxCorners && out.length >= 3) break;
    tol *= 1.6;
  }
  return out.length >= 3 ? out : ring;
}

/** Convex hull (monotone chain) of [x, y] points, counter-clockwise. */
export function convexHull(points) {
  const pts = [...points].sort((a, b) => a[0] - b[0] || a[1] - b[1]);
  if (pts.length < 3) return pts;
  const cross = (o, a, b) => (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]);
  const lower = [];
  pts.forEach((p) => {
    while (lower.length >= 2 && cross(lower[lower.length - 2], lower[lower.length - 1], p) <= 0) lower.pop();
    lower.push(p);
  });
  const upper = [];
  [...pts].reverse().forEach((p) => {
    while (upper.length >= 2 && cross(upper[upper.length - 2], upper[upper.length - 1], p) <= 0) upper.pop();
    upper.push(p);
  });
  return [...lower.slice(0, -1), ...upper.slice(0, -1)];
}

const M_PER_DEG_LAT = 111320;

/**
 * A shape around [lat, lng] points: each point grown into a circle of
 * `radiusM`, then wrapped in one convex outline. One point gives a circle,
 * two give a capsule, more give the hull around all of them.
 */
export function hullAround(points, radiusM, steps = 12) {
  if (!points.length) return [];
  const lat0 = points.reduce((s, p) => s + p[0], 0) / points.length;
  const mPerDegLng = M_PER_DEG_LAT * Math.cos((lat0 * Math.PI) / 180);
  const xy = [];
  points.forEach(([lat, lng]) => {
    for (let i = 0; i < steps; i += 1) {
      const a = (2 * Math.PI * i) / steps;
      xy.push([lng * mPerDegLng + Math.cos(a) * radiusM, lat * M_PER_DEG_LAT + Math.sin(a) * radiusM]);
    }
  });
  return convexHull(xy).map(([x, y]) => [y / M_PER_DEG_LAT, x / mPerDegLng]);
}

/** Approximate distance in metres between two [lat, lng] points. */
export function metresBetween(a, b) {
  const mPerDegLng = M_PER_DEG_LAT * Math.cos((((a[0] + b[0]) / 2) * Math.PI) / 180);
  return Math.hypot((a[0] - b[0]) * M_PER_DEG_LAT, (a[1] - b[1]) * mPerDegLng);
}
