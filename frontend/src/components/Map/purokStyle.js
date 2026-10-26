/**
 * How purok outlines are drawn on the public map.
 *
 * Purok lines show only inside the barangay that's selected, so the city view
 * stays clear; hovering a purok tints it and names it. Until the Barangay Hall
 * sends official lines the puroks are estimates (backend: manage.py
 * build_purok_estimates), drawn dashed; official lines are solid. Violet stays
 * clear of the hazard reds, oranges, yellows and greens and of the dark
 * barangay line.
 */

export const PUROK_COLOR = '#7c3aed';

export function purokStyle(feature) {
  const official = feature?.properties?.source === 'official';
  return {
    color: PUROK_COLOR,
    weight: 1.5,
    opacity: 0.9,
    dashArray: official ? null : '5 4',
    fill: false,
  };
}

// Laid over purokStyle for the purok under the pointer
export const PUROK_HOVER = { weight: 3, fill: true, fillColor: PUROK_COLOR, fillOpacity: 0.15 };

// Laid over purokStyle for the purok whose past hazards the panel shows
export const PUROK_SELECTED = { weight: 3.5, dashArray: null };

function inRing(lng, lat, ring) {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [xi, yi] = ring[i];
    const [xj, yj] = ring[j];
    if ((yi > lat) !== (yj > lat) && lng < ((xj - xi) * (lat - yi)) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}

/**
 * The purok under a point, or null. The lines aren't clickable, so nothing
 * else on the map (barangays, drawing tools) loses its clicks
 * to them; the map asks this instead when the pointer moves.
 */
export function purokAt(geo, lng, lat) {
  return (geo?.features || []).find((f) => {
    const g = f.geometry;
    const polygons = g?.type === 'Polygon' ? [g.coordinates] : g?.type === 'MultiPolygon' ? g.coordinates : [];
    return polygons.some(([outer, ...holes]) => inRing(lng, lat, outer) && !holes.some((h) => inRing(lng, lat, h)));
  }) || null;
}

// The selected barangay's puroks as a FeatureCollection, or null for none
export function puroksOf(geo, barangayId) {
  if (barangayId == null) return null;
  const features = (geo?.features || []).filter((f) => String(f.properties?.barangay) === String(barangayId));
  return features.length ? { type: 'FeatureCollection', features } : null;
}

const escape = (text) => String(text ?? '')
  .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');

// An estimate with no confidence is an area no purok name was found for: a
// purok nobody could place yet. Its name only says where it is ("Near Tapul
// Elementary School", "Along Burgos Street").
export const isUnidentified = (p) => p?.source === 'estimated' && !p?.confidence;

// What hovering a purok says: its name, where it is, and how sure the outline is.
export function purokTooltip(feature) {
  const p = feature?.properties || {};
  const where = [p.parent, p.barangay_name].filter(Boolean).map(escape).join(' · ');
  const note = p.source === 'official' ? ''
    : p.source === 'community' ? 'Not official'
      : isUnidentified(p) ? 'Purok not identified yet'
        : p.confidence === 'low' ? 'Estimated outline · location approximate'
          : 'Estimated outline';
  return `<strong>${escape(p.name)}</strong><br>${where}${note ? `<br>${note}` : ''}`;
}

// Credit for what the estimated outlines are built from, shown while the layer is
export const PUROK_ATTRIBUTION = 'Purok estimates: OpenStreetMap, Wikimapia (CC BY-SA), Overture Maps, '
  + 'Microsoft Building Footprints (ODbL), Visayan Electric notices';

export const hasEstimates = (geo) => (geo?.features || []).some((f) => f.properties?.source !== 'official');
