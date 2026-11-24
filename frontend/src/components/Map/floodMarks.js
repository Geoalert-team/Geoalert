// The flood model's two marks on top of the "Likely by month" fills: areas
// not assessed (grey, dashed: no flood evidence there yet) and areas whose
// level is uncertain (a dashed outline over their colour). The colours
// themselves come from the shared purok fills (PurokHistoryLayer).
//
// With Fire also ticked, an area not assessed for flood that has a fire
// level keeps its fire colour: it gets the dashed outline only, no grey. A
// sitio is marked only on its part outside its puroks (properties.leftover),
// as the fills do, so it never covers an assessed purok inside it.

import { isContainer } from './purokStyle';

const GREY = '#c9c9c9';

/**
 * The puroks to mark, each with properties.flood 'not_assessed' (grey),
 * 'not_assessed_outline' (dashed outline over a fire colour) or 'uncertain';
 * null when there are none. levels: purokLikelyLevels() output; types: the
 * ticked predicted hazards.
 */
export function floodOverlayFeatures(geo, levels, types = ['Flood']) {
  const fireShown = types.includes('Fire');
  const features = (geo?.features || []).flatMap((f) => {
    const entry = levels?.get(String(f.id ?? f.properties?.id));
    const row = entry?.Flood;
    if (!row) return [];
    let mark = null;
    if (!row.level) mark = fireShown && entry.Fire?.level ? 'not_assessed_outline' : 'not_assessed';
    else if (row.uncertain) mark = 'uncertain';
    if (!mark) return [];
    if (isContainer(f) && !f.properties?.leftover) return [];
    return [{
      ...f,
      ...(isContainer(f) ? { geometry: f.properties.leftover } : {}),
      properties: { ...f.properties, flood: mark },
    }];
  });
  return features.length ? { type: 'FeatureCollection', features } : null;
}

export function floodOverlayStyle(feature) {
  const mark = feature?.properties?.flood;
  if (mark === 'not_assessed') {
    return { stroke: true, color: '#8a8a8a', weight: 1, opacity: 0.9, dashArray: '4 3', fillColor: GREY, fillOpacity: 0.35 };
  }
  if (mark === 'not_assessed_outline') {
    return { stroke: true, color: '#8a8a8a', weight: 1, opacity: 0.9, dashArray: '4 3', fillOpacity: 0 };
  }
  return { stroke: true, color: '#333333', weight: 1.5, opacity: 0.9, dashArray: '4 3', fillOpacity: 0 };
}
