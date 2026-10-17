/**
 * Snapping a hazard-zone corner onto a barangay boundary.
 *
 * A zone meant to stop at a barangay line or the coast is hard to draw by
 * hand: a corner a few metres off either leaves a sliver of the next
 * barangay inside the zone (and notifies it) or leaves a gap. When a corner
 * lands close to a boundary on screen, it is moved onto it.
 *
 * Distances are measured in screen pixels, not metres, so the pull feels
 * the same at every zoom level. project/unproject convert between
 * [lat, lng] and {x, y} screen points (Leaflet's latLngToLayerPoint and
 * layerPointToLatLng in the app; plain functions in tests).
 */

export const SNAP_PX = 15;

/** Outer and inner rings of every barangay, as [lat, lng] lists. */
export function boundaryRings(features) {
  const rings = [];
  (features || []).forEach((f) => {
    const g = f?.geometry;
    const polys = g?.type === 'Polygon' ? [g.coordinates] : g?.type === 'MultiPolygon' ? g.coordinates : [];
    polys.forEach((poly) => poly.forEach((ring) => rings.push(ring.map(([lng, lat]) => [lat, lng]))));
  });
  return rings;
}

function nearestOnSegment(p, a, b) {
  const dx = b.x - a.x;
  const dy = b.y - a.y;
  const len2 = dx * dx + dy * dy;
  const t = len2 ? Math.max(0, Math.min(1, ((p.x - a.x) * dx + (p.y - a.y) * dy) / len2)) : 0;
  return { x: a.x + t * dx, y: a.y + t * dy, t };
}

/**
 * Where a corner should go. Returns { point: [lat, lng], snapped: bool }.
 *
 * A boundary vertex within reach wins over a point along an edge, so a
 * corner dropped near where three barangays meet lands exactly on that
 * junction instead of somewhere along one of the lines.
 */
export function snapPoint(point, rings, project, unproject, tolerance = SNAP_PX) {
  const p = project(point);
  const tol2 = tolerance * tolerance;
  let bestVertex = null;
  let bestVertexD = tol2;
  let bestEdge = null;
  let bestEdgeD = tol2;

  rings.forEach((ring) => {
    let prev = null;
    ring.forEach((ll) => {
      const q = project(ll);
      const dv = (q.x - p.x) ** 2 + (q.y - p.y) ** 2;
      if (dv <= bestVertexD) { bestVertexD = dv; bestVertex = ll; }
      if (prev) {
        // Cheap reject: both ends far away on the same side
        const minX = Math.min(prev.x, q.x) - tolerance;
        const maxX = Math.max(prev.x, q.x) + tolerance;
        const minY = Math.min(prev.y, q.y) - tolerance;
        const maxY = Math.max(prev.y, q.y) + tolerance;
        if (p.x >= minX && p.x <= maxX && p.y >= minY && p.y <= maxY) {
          const n = nearestOnSegment(p, prev, q);
          const de = (n.x - p.x) ** 2 + (n.y - p.y) ** 2;
          if (de <= bestEdgeD) { bestEdgeD = de; bestEdge = n; }
        }
      }
      prev = q;
    });
  });

  if (bestVertex) return { point: bestVertex, snapped: true };
  if (bestEdge) return { point: unproject(bestEdge), snapped: true };
  return { point, snapped: false };
}
