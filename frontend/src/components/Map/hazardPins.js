// Where the public map puts a hazard's pins, and the puroks it outlines. A
// zone made from reports (a fire, flood or landslide pushed from the DRRMO
// dashboard) comes with `pins`: one per purok its reports name, and no
// shading (its zone is only a few small circles, used to work out who to
// alert); the puroks it is in are outlined instead. A seeded zone keeps one
// pin at its middle.

import { SEVERITY_RANK } from './hazardInfo';
import { purokAt } from './purokStyle';

export function markerSpots(item) {
  const pins = item.pins || [];
  if (!pins.length) return [{ key: item.id, position: item.position, purok: null }];
  return pins.map((p, i) => ({ key: `${item.id}:${i}`, position: [p.lat, p.lng], purok: p.purok_name ?? null }));
}

export function drawsShading(item) {
  return !(item.pins && item.pins.length);
}

/**
 * The puroks a hazard is in, for the map to outline while its panel is
 * open: the ones its reports name, else the purok under each of its pins
 * (a report pinned on the map, or a drawn zone's one pin). A
 * FeatureCollection from `geo` (barangaysApi.puroks()), each purok once, or
 * null when there is none or the puroks haven't loaded.
 */
export function hazardPuroks(item, geo) {
  if (!item || !geo?.features?.length) return null;
  const byId = new Map(geo.features.map((f) => [String(f.id), f]));
  const found = new Map();
  markerSpots(item).forEach((spot, i) => {
    const named = item.pins?.[i]?.purok_id;
    const purok = named != null ? byId.get(String(named)) : purokAt(geo, spot.position[1], spot.position[0]);
    if (purok) found.set(String(purok.id), purok);
  });
  return found.size ? { type: 'FeatureCollection', features: [...found.values()] } : null;
}

/**
 * Every hazard's puroks at once, for the map to outline lightly before
 * anything is tapped: a FeatureCollection with each purok once, its
 * `hazards` property the hazards it is in, most serious first. Null when
 * there is none or the puroks haven't loaded.
 */
export function hazardAreas(hazards, geo) {
  const byPurok = new Map();
  (hazards || []).forEach((h) => {
    (hazardPuroks(h, geo)?.features || []).forEach((f) => {
      const entry = byPurok.get(String(f.id)) || { feature: f, hazards: [] };
      entry.hazards.push(h);
      byPurok.set(String(f.id), entry);
    });
  });
  if (!byPurok.size) return null;
  const rank = (h) => SEVERITY_RANK[h.severity] || 0;
  return {
    type: 'FeatureCollection',
    features: [...byPurok.values()].map(({ feature, hazards: here }) => ({
      ...feature,
      properties: { ...feature.properties, hazards: [...here].sort((a, b) => rank(b) - rank(a)) },
    })),
  };
}

// The most serious hazard whose purok is under this spot, or null
export function hazardAt(areas, lng, lat) {
  const purok = areas ? purokAt(areas, lng, lat) : null;
  return purok ? purok.properties.hazards[0] : null;
}
