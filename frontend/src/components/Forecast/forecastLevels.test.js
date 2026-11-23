import * as levels from './forecastLevels';
import {
  FIRE_ONLY_NOTE, FORECAST_DISCLAIMER, IN_TRAINING_NOTE, aboutChanceText, chanceText, hazardsParam, isFireOnly,
  levelLabel, likelyKey, smallChanceText, unavailableNote,
} from './forecastLevels';

// Fire is the only hazard with a prediction model since 2026-11-22
test('hazardsParam asks for fire whenever fire is ticked, and for nothing otherwise', () => {
  expect(hazardsParam(new Set(['Landslide', 'Fire']))).toBe('Fire');
  expect(hazardsParam(['Fire', 'Flood', 'Landslide'])).toBe('Fire');
  expect(hazardsParam(['Flood'])).toBe('');
  expect(hazardsParam([])).toBe('');
});

test('isFireOnly: no filter or a fire filter shows fire; flood and landslide show the note', () => {
  expect(isFireOnly('')).toBe(true);
  expect(isFireOnly(undefined)).toBe(true);
  expect(isFireOnly('Fire')).toBe(true);
  expect(isFireOnly('Flood')).toBe(false);
  expect(isFireOnly('Landslide')).toBe(false);
});

test('unavailableNote names fire with the reason its rows give', () => {
  const rows = [{ hazard_type: 'Fire', method: 'unavailable', reason: 'The fire model has not been trained yet.' }];
  expect(unavailableNote({ unavailable_hazards: ['Fire'], results: rows }))
    .toBe('Fire is unavailable right now: The fire model has not been trained yet.');
  expect(unavailableNote({ unavailable_hazards: ['Fire'], results: [] })).toBe('Fire is unavailable right now.');
  expect(unavailableNote({ unavailable_hazards: [], results: rows })).toBe('');
  expect(unavailableNote({})).toBe('');
  expect(unavailableNote(null)).toBe('');
});

test('smallChanceText', () => {
  expect(smallChanceText(0.004)).toBe('under 1%');
  expect(smallChanceText(0)).toBe('0%');
  expect(smallChanceText(0)).toBe(chanceText({ method: 'model', probability: 0 }));
  expect(smallChanceText(0.005)).toBe('1%');
  expect(smallChanceText(0.031)).toBe('3%');
  expect(smallChanceText(null)).toBe('');
  expect(smallChanceText(undefined)).toBe('');
});

test('aboutChanceText', () => {
  expect(aboutChanceText(0.004)).toBe('under 1%');
  expect(aboutChanceText(0.031)).toBe('about 3%');
  expect(aboutChanceText(0)).toBe('about 0%');
  expect(aboutChanceText(null)).toBe('');
});

test('an unavailable row says so instead of None on record', () => {
  expect(levelLabel({ method: 'unavailable', level: 'None' })).toBe('Unavailable right now');
  expect(levelLabel({ method: 'model', level: 'Low' })).toBe('Low');
  expect(levelLabel({ level: 'None' })).toBe('None on record');
});

test('the exact copy', () => {
  expect(FORECAST_DISCLAIMER).toBe(
    'Fire chances come from a model trained on past fires; flood and landslide predictions are being rebuilt. '
    + 'It is a heads-up for preparing, not a warning that a hazard is coming. Live alerts come only from the DRRMO.',
  );
  expect(FIRE_ONLY_NOTE).toBe('Only fire has a prediction for now.');
  expect(IN_TRAINING_NOTE).toBe(
    'The model learned from this period; see the accuracy check for results on years it never saw.',
  );
});

test('likelyKey changes with a response even when the row counts are equal', () => {
  const low = { results: [{ barangay_id: 1, hazard_type: 'Fire', method: 'model', level: 'Low', probability: 0.1 }] };
  const high = { results: [{ barangay_id: 1, hazard_type: 'Fire', method: 'model', level: 'High', probability: 0.3 }] };
  expect(likelyKey(low)).not.toBe(likelyKey(high));
  expect(likelyKey(low)).toBe(likelyKey({ ...low }));
  expect(likelyKey(null)).toBe('none');
});

test('the flood, landslide and rain helpers are gone', () => {
  ['combinedByBarangay', 'combinedText', 'combinedUnavailable', 'rangeText', 'rainYearsText', 'RAIN_ATTRIBUTION',
    'FLOOD_LANDSLIDE_MONTHLY_NOTE', 'MODEL_LABELS'].forEach((name) => expect(levels[name]).toBeUndefined());
});

// Purok fills and tooltips in "Likely by month" (plan Task B7)
const purokRows = {
  purok_results: [
    { purok_id: 12, barangay_id: 3, probability: 0.06, level: 'Red', interval: [0.04, 0.09], limited_data: false },
    { purok_id: 15, barangay_id: 3, probability: 0.004, level: 'Green', interval: [0.002, 0.01], limited_data: true },
  ],
};

test('purokLikelyLevels maps rows by purok id', () => {
  const map = levels.purokLikelyLevels(purokRows);
  expect(map.size).toBe(2);
  expect(map.get('12').Fire.level).toBe('Red');
  expect(map.get('12').Fire.probability).toBe(0.06);
  expect(map.get('15').Fire.limited_data).toBe(true);
  expect(levels.purokLikelyLevels(null).size).toBe(0);
  expect(levels.purokLikelyLevels({ error: true }).size).toBe(0);
});

test('purokLikelyTip shows limited data', () => {
  expect(levels.purokLikelyTip({ level: 'Red', probability: 0.02, limited_data: true }, 'Purok Sambag'))
    .toBe('Purok Sambag: Extreme, about 2% this month · Limited data');
  expect(levels.purokLikelyTip({ level: 'Green', probability: 0.003, limited_data: false }, 'Fire', 'in June'))
    .toBe('Fire: Low, under 1% in June');
});

test('likelyKey changes when the purok figures change', () => {
  const other = { purok_results: [{ ...purokRows.purok_results[0], level: 'Orange' }] };
  expect(likelyKey(purokRows)).not.toBe(likelyKey(other));
});

test('the fire model is credited to Pittsburgh', () => {
  expect(levels.FIRE_CREDIT).toContain('City of Pittsburgh');
  expect(levels.FIRE_CREDIT).toContain('MIT');
  expect(levels.FIRE_MODEL_LABEL).toContain('Pittsburgh');
  expect(levels.PUROK_CAVEAT).toMatch(/estimate/i);
});
