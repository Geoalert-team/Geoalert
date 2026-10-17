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
