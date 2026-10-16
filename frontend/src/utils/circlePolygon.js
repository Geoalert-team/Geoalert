/**
 * Turns a centre point and a radius in metres into a GeoJSON Polygon.
 *
 * HazardZone.geometry is a polygon field, so a hazard placed as "a point
 * with a radius" has to be written out as a ring of coordinates. 36 sides
 * reads as a smooth circle at any zoom the map allows while keeping the
 * stored geometry small.
 */

const EARTH_RADIUS = 6378137; // WGS84 equatorial radius, metres
const DEG = 180 / Math.PI;

/**
 * @param {[number, number]} center  [lat, lng] — Leaflet's order
 * @param {number} radiusMeters
 * @param {number} [sides=36]
 * @returns {{type: 'Polygon', coordinates: number[][][]}} GeoJSON, [lng, lat] order
 */
export function circleToPolygon(center, radiusMeters, sides = 36) {
  const [lat, lng] = center;
  const latRad = (lat * Math.PI) / 180;

  // Metres per degree shrinks with latitude for longitude but not for
  // latitude, so the two offsets are scaled differently. At Talisay's
  // latitude the difference is small but it keeps the shape a circle
  // rather than an ellipse.
  const coords = [];
  for (let i = 0; i <= sides; i += 1) {
    const theta = (2 * Math.PI * i) / sides;
    const dx = radiusMeters * Math.cos(theta);
    const dy = radiusMeters * Math.sin(theta);
    const dLat = (dy / EARTH_RADIUS) * DEG;
    const dLng = (dx / (EARTH_RADIUS * Math.cos(latRad))) * DEG;
    coords.push([lng + dLng, lat + dLat]);
  }

  // i === sides repeats i === 0, which closes the ring as GeoJSON requires.
  return { type: 'Polygon', coordinates: [coords] };
}

export default circleToPolygon;