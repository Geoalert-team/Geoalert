/**
 * Purok colours from past hazards, on the public map's Past hazards view.
 *
 * The rule itself is the backend's (apps/history/purok_levels.py): each
 * hazard type is counted on its own over the history period, and the count
 * gives Low, Moderate or Extreme (thresholds in Admin › Settings). Here a
 * purok just takes the highest of its levels among the ticked types, in the
 * same green / orange / red as the pins. A purok with none isn't filled.
 */
import { SEVERITY } from './hazardInfo';
import { isContainer } from './purokStyle';

const RANK = { Green: 1, Orange: 2, Red: 3 };
const LABEL = { Green: 'Low', Orange: 'Moderate', Red: 'Extreme' };
const NOUNS = { Flood: 'flood', Landslide: 'landslide', Fire: 'fire' };

// Highest first, as the legend lists them
export const PUROK_LEVELS = ['Red', 'Orange', 'Green'].map((code) => ({
  code, label: LABEL[code], color: SEVERITY[code].color,
}));

const period = (years) => `in the last ${years === 1 ? 'year' : `${years} years`}`;

// /api/history/purok-levels/ results as purok id (string) → { type: { count, level } }
export function byPurok(results) {
  const levels = new Map();
  (results || []).forEach((r) => {
    const key = String(r.purok);
    if (!levels.has(key)) levels.set(key, {});
    levels.get(key)[r.type] = { count: r.count, level: r.level };
  });
  return levels;
}

// The highest level among the ticked types, or null for none
export function purokLevel(entry, types) {
  return types
    .map((t) => entry?.[t]?.level)
    .filter((lv) => RANK[lv])
    .reduce((top, lv) => (!top || RANK[lv] > RANK[top] ? lv : top), null);
}

// The puroks to fill, each with properties.level; null when there are none.
// A sitio's own past hazards happened somewhere in it, not in each of its
// puroks, so it fills only its part outside them (properties.leftover from
// the API): a purok inside it with none of its own stays clear, as its panel
// row and hover say.
export function filledPuroks(geo, levels, types) {
  if (!geo || !types.length) return null;
  const features = (geo.features || [])
    .map((f) => ({ f, level: purokLevel(levels?.get(String(f.id ?? f.properties?.id)), types) }))
    .filter(({ f, level }) => level && (!isContainer(f) || f.properties?.leftover))
    .map(({ f, level }) => ({
      ...f,
      ...(isContainer(f) ? { geometry: f.properties.leftover } : {}),
      properties: { ...f.properties, level },
    }));
  return features.length ? { type: 'FeatureCollection', features } : null;
}

// Filled sitios apart from filled puroks, so a sitio's colour can sit under its puroks' own
export function splitFills(filled) {
  const collect = (keep) => {
    const features = (filled?.features || []).filter(keep);
    return features.length ? { type: 'FeatureCollection', features } : null;
  };
  return { sitios: collect(isContainer), puroks: collect((f) => !isContainer(f)) };
}

export function purokFillStyle(feature) {
  const color = SEVERITY[feature?.properties?.level]?.color;
  return { stroke: true, color, weight: 1, opacity: 0.9, fillColor: color, fillOpacity: 0.45 };
}

// "fire" / "fires" for one type, "past hazard" / "past hazards" for several
export function typeNoun(types, n) {
  const one = types.length === 1 ? NOUNS[types[0]] || types[0].toLowerCase() : 'past hazard';
  return n === 1 ? one : `${one}s`;
}

// "Low" / "Moderate" / "Extreme", or '' for no level
export const levelLabel = (code) => LABEL[code] || '';

// What hovering a purok adds: "2 fires (Low), 4 floods (Moderate)". Only the
// ticked types: with only floods ticked, a purok with fires has "No floods",
// not "No past hazards"; with nothing ticked there is nothing to add.
export function historyLine(entry, types, years) {
  if (!types.length) return '';
  const parts = types
    .filter((t) => entry?.[t]?.count)
    .map((t) => `${entry[t].count} ${typeNoun([t], entry[t].count)} (${LABEL[entry[t].level]})`);
  return parts.length ? parts.join(', ') : `No ${typeNoun(types, 2)} ${period(years)}`;
}

// "1–2 · 3–4 · 5+ past events in the last 5 years"
export function thresholdText(t) {
  const span = (a, b) => (a === b ? `${a}` : `${a}–${b}`);
  return `${span(1, t.moderate - 1)} · ${span(t.moderate, t.extreme - 1)} · ${t.extreme}+ past events ${period(t.years)}`;
}

// The panel's summary: "21 fires in the last 5 years"
export function areaTitle(count, types, years) {
  return count
    ? `${count} ${typeNoun(types, count)} ${period(years)}`
    : `No ${typeNoun(types, 2)} ${period(years)}`;
}
