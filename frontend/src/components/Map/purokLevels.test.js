import { byPurok, filledPuroks, historyLine, purokLevel, thresholdText, typeNoun, areaTitle } from './purokLevels';

const T = { years: 5, moderate: 3, extreme: 5 };
const RESULTS = [
  { purok: 7, type: 'Fire', count: 2, level: 'Green' },
  { purok: 7, type: 'Flood', count: 4, level: 'Orange' },
  { purok: 9, type: 'Fire', count: 6, level: 'Red' },
];
const feature = (id) => ({ type: 'Feature', id, properties: { id, name: `P${id}` }, geometry: null });

test('a purok takes the highest level among the ticked types', () => {
  const levels = byPurok(RESULTS);
  expect(purokLevel(levels.get('7'), ['Fire', 'Flood'])).toBe('Orange');
  expect(purokLevel(levels.get('7'), ['Fire'])).toBe('Green');
  expect(purokLevel(levels.get('7'), ['Landslide'])).toBeNull();
  expect(purokLevel(undefined, ['Fire'])).toBeNull();
});

test('only puroks with a level are filled', () => {
  const geo = { type: 'FeatureCollection', features: [feature(7), feature(8), feature(9)] };
  const filled = filledPuroks(geo, byPurok(RESULTS), ['Fire']);
  expect(filled.features.map((f) => [f.id, f.properties.level])).toEqual([[7, 'Green'], [9, 'Red']]);
  expect(filledPuroks(geo, byPurok(RESULTS), [])).toBeNull();
});

test('the hover line and the copy', () => {
  const levels = byPurok(RESULTS);
  expect(historyLine(levels.get('7'), ['Fire', 'Flood'], 5)).toBe('2 fires (Low), 4 floods (Moderate)');
  expect(historyLine(levels.get('7'), ['Landslide'], 5)).toBe('No past hazards in the last 5 years');
  expect(thresholdText(T)).toBe('1–2 · 3–4 · 5+ past events in the last 5 years');
  expect(thresholdText({ years: 3, moderate: 2, extreme: 3 })).toBe('1 · 2 · 3+ past events in the last 3 years');
  expect(typeNoun(['Fire'], 1)).toBe('fire');
  expect(typeNoun(['Fire', 'Flood'], 2)).toBe('past hazards');
  expect(areaTitle(21, ['Fire'], 5)).toBe('21 fires in the last 5 years');
  expect(areaTitle(0, ['Fire'], 5)).toBe('No fires in the last 5 years');
});
