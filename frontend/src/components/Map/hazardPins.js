// Where the public map puts a hazard's pins. A zone made from reports (a
// fire, flood or landslide pushed from the DRRMO dashboard) comes with
// `pins`: one per purok its reports name, and it is shown by those pins
// alone, with no shading or outline (its zone is only a few small circles,
// used to work out who to alert). A zone an officer drew keeps one pin at its
// middle.

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
