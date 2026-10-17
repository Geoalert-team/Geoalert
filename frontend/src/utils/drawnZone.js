/**
 * Helpers for a hazard zone outlined by tapping corners on the map.
 *
 * Points are kept in Leaflet's [lat, lng] order while drawing and turned
 * into GeoJSON ([lng, lat]) only when publishing. The backend repairs a
 * self-crossing outline and cuts off anything outside Talisay City, so
 * nothing here has to be exact. It only needs to be honest enough to
 * preview.
 */

const EARTH_RADIUS = 6378137; // WGS84 equatorial radius, metres

/** Corners an outline needs before it encloses any area. */
export const MIN_CORNERS = 3;

/**
 * @param {[number, number][]} points  [lat, lng] corners, not closed
 * @returns {{type: 'Polygon', coordinates: number[][][]}} GeoJSON, ring closed
 */
export function pointsToPolygon(points) {
  const ring = points.map(([lat, lng]) => [lng, lat]);
  ring.push(ring[0]);
  return { type: 'Polygon', coordinates: [ring] };
}

/**
 * Approximate area in square metres. Projects onto a flat plane around the
 * outline's middle, which is well within a percent at city scale.
 */
export function areaSqM(points) {
  if (points.length < MIN_CORNERS) return 0;
  const lat0 = points.reduce((sum, p) => sum + p[0], 0) / points.length;
  const kx = (Math.PI / 180) * EARTH_RADIUS * Math.cos((lat0 * Math.PI) / 180);
  const ky = (Math.PI / 180) * EARTH_RADIUS;
  let twice = 0;
  for (let i = 0; i < points.length; i += 1) {
    const [aLat, aLng] = points[i];
    const [bLat, bLng] = points[(i + 1) % points.length];
    twice += aLng * kx * (bLat * ky) - bLng * kx * (aLat * ky);
  }
  return Math.abs(twice) / 2;
}

/** "850 m²", "3.2 ha", "1.40 km²" */
export function formatArea(sqm) {
  if (sqm < 10000) return `${Math.round(sqm)} m²`;
  if (sqm < 1000000) return `${(sqm / 10000).toFixed(1)} ha`;
  return `${(sqm / 1000000).toFixed(2)} km²`;
}

/** Average of the corners. Good enough to say roughly where the zone is. */
export function middleOf(points) {
  const n = points.length;
  return [
    points.reduce((sum, p) => sum + p[0], 0) / n,
    points.reduce((sum, p) => sum + p[1], 0) / n,
  ];
}

// Squared distance from p to segment a-b, in a flat local plane (metres-ish).
function segmentDistance2(p, a, b, kx) {
  const ax = a[1] * kx; const ay = a[0];
  const bx = b[1] * kx; const by = b[0];
  const px = p[1] * kx; const py = p[0];
  const dx = bx - ax; const dy = by - ay;
  const len2 = dx * dx + dy * dy;
  const t = len2 ? Math.max(0, Math.min(1, ((px - ax) * dx + (py - ay) * dy) / len2)) : 0;
  const cx = ax + t * dx; const cy = ay + t * dy;
  return (px - cx) ** 2 + (py - cy) ** 2;
}

/**
 * Add a corner to a closed outline on the edge nearest to it, rather than
 * at the end. Appending is right while drawing a new outline corner by
 * corner, but when reshaping an existing one it would cut a line straight
 * across the shape.
 */
export function insertCorner(points, p) {
  if (points.length < MIN_CORNERS) return [...points, p];
  const kx = Math.cos((p[0] * Math.PI) / 180);
  let best = 0;
  let bestD = Infinity;
  for (let i = 0; i < points.length; i += 1) {
    const d = segmentDistance2(p, points[i], points[(i + 1) % points.length], kx);
    if (d < bestD) { bestD = d; best = i; }
  }
  return [...points.slice(0, best + 1), p, ...points.slice(best + 1)];
}

function douglasPeucker(points, tolerance2, kx) {
  if (points.length < 3) return points;
  let index = 0;
  let maxD = 0;
  const last = points.length - 1;
  for (let i = 1; i < last; i += 1) {
    const d = segmentDistance2(points[i], points[0], points[last], kx);
    if (d > maxD) { maxD = d; index = i; }
  }
  if (maxD <= tolerance2) return [points[0], points[last]];
  const left = douglasPeucker(points.slice(0, index + 1), tolerance2, kx);
  const right = douglasPeucker(points.slice(index), tolerance2, kx);
  return [...left.slice(0, -1), ...right];
}

/**
 * Thin a long outline to at most maxCorners draggable corners while
 * keeping its shape. A zone clipped along the coastline can carry hundreds
 * of points; nobody can reshape that by hand.
 */
export function simplifyOutline(points, maxCorners = 24) {
  if (points.length <= maxCorners) return points;
  const kx = Math.cos((middleOf(points)[0] * Math.PI) / 180);
  let tolerance = 1e-6;
  let out = points;
  // Widen the tolerance until it fits; each step roughly halves the count
  while (out.length > maxCorners && tolerance < 1) {
    const closed = [...points, points[0]];
    out = douglasPeucker(closed, tolerance * tolerance, kx).slice(0, -1);
    tolerance *= 1.6;
  }
  return out.length >= MIN_CORNERS ? out : points.slice(0, maxCorners);
}

/**
 * The editable corners of a saved zone, from its GeoJSON feature: the
 * outline as drawn when there is one, otherwise the outer ring of the
 * largest part of the saved shape. [lat, lng] order, ring not closed.
 */
export function cornersOfZone(feature) {
  const props = feature?.properties || {};
  let ring = props.outline?.coordinates?.[0];
  if (!ring) {
    const g = feature?.geometry;
    const polys = g?.type === 'Polygon' ? [g.coordinates] : g?.type === 'MultiPolygon' ? g.coordinates : [];
    const largest = polys
      .map((rings) => rings[0])
      .sort((a, b) => areaSqM(b.map(([lng, lat]) => [lat, lng])) - areaSqM(a.map(([lng, lat]) => [lat, lng])))[0];
    ring = largest;
  }
  if (!ring || ring.length < 4) return [];
  const open = ring.slice(0, -1).map(([lng, lat]) => [lat, lng]);
  return simplifyOutline(open);
}
