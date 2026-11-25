import * as levels from './forecastLevels';
import {
  FLOOD_WORD, FORECAST_DISCLAIMER, FORECAST_ONLY_NOTE, IN_TRAINING_NOTE, LANDSLIDE_WORD, NOT_ASSESSED, aboutChanceText,
  chanceText, floodLegend, floodTip, hazardsParam, isFireOnly, landslideLegend, landslideTip, levelLabel, likelyKey,
  LANDSLIDE_ON_MAP_NOTE, legendHeading, legendTitle, smallChanceText, susceptibilityNote, susceptibilityTip,
  unavailableNote,
} from './forecastLevels';
import { purokLevel } from '../Map/purokLevels';

// Fire and flood have prediction models (flood since 2026-11-24)
test('hazardsParam asks for the ticked predicted hazards', () => {
  expect(hazardsParam(new Set(['Landslide', 'Fire']))).toBe('Fire,Landslide');
  expect(hazardsParam(['Fire', 'Flood', 'Landslide'])).toBe('Fire,Flood,Landslide');
  expect(hazardsParam(['Flood'])).toBe('Flood');
  expect(hazardsParam(['Landslide'])).toBe('Landslide');
  expect(hazardsParam(['Tsunami'])).toBe('');
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

test('the disclaimer names recorded floods, not the survey', () => {
  expect(FORECAST_DISCLAIMER).toContain("from UP NOAH's flood maps and recorded floods");
  expect(FORECAST_DISCLAIMER).not.toContain('Mananga');
});

test('the exact copy', () => {
  expect(FORECAST_DISCLAIMER).toBe(
    // Flood's source is named without claiming a trained model: the NOAH fallback may be what ships
    'Fire chances come from a model trained on past fires. Flood levels show where floods tend to reach, from UP '
    + "NOAH's flood maps and recorded floods, and are the same in every month. Landslide levels show where "
    // Final review FM9 (ruling R48): in model mode UP NOAH is never an input, so its maps are the alternative source
    + "the ground tends to slide, from landslides mapped after past typhoons or from UP NOAH's landslide maps, and are "
    + 'the same in every month. '
    + 'It is a heads-up for preparing, not a warning that a hazard is coming. Live alerts come only from the DRRMO.',
  );
  expect(FORECAST_ONLY_NOTE).toBe('Pick fire, flood or landslide to see a prediction.');
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
  expect(levels.PUROK_CAVEAT).not.toMatch(/estimat/i);
});

// Flood susceptibility in "Likely by month" (plan Task 9)
const both = {
  purok_results: [{ purok_id: 4, barangay_id: 3, probability: 0.02, level: 'Orange', interval: [0.01, 0.03], limited_data: false }],
  flood_results: [
    { purok_id: 4, barangay_id: 3, level: null, uncertain: false, not_assessed_reason: 'Outside the surveyed floodplain', estimated_outline: false },
    { purok_id: 9, barangay_id: 3, level: 'Red', uncertain: true, not_assessed_reason: null, estimated_outline: true },
  ],
};

test('combined fill keeps the fire level when flood is not assessed', () => {
  const map = levels.purokLikelyLevels(both);
  expect(purokLevel(map.get('4'), ['Fire', 'Flood'])).toBe('Orange');
  expect(purokLevel(map.get('9'), ['Fire', 'Flood'])).toBe('Red');
  expect(purokLevel(map.get('9'), ['Fire'])).toBeNull();
  expect(floodTip(map.get('4').Flood, 'Purok A')).toBe('Purok A: Not assessed yet (Outside the surveyed floodplain)');
  expect(floodTip(map.get('9').Flood, 'Purok B')).toBe('Purok B: High flood susceptibility · Uncertain');
});

// Final review P6: an own-data fit marks the puroks it copied from UP NOAH's map (spec 6.3)
test('a flood row with a note shows it in the hover; one without is unchanged', () => {
  const NOTE = "From UP NOAH's map; outside the area GeoAlert's records cover";
  const map = levels.purokLikelyLevels({
    flood_results: [
      { purok_id: 5, barangay_id: 3, level: 'Red', uncertain: true, not_assessed_reason: null, estimated_outline: false, note: NOTE },
      { purok_id: 6, barangay_id: 3, level: 'Orange', uncertain: false, not_assessed_reason: null, estimated_outline: false, note: null },
    ],
  });
  expect(map.get('5').Flood.note).toBe(NOTE);
  expect(floodTip(map.get('5').Flood, 'Flood')).toBe(`Flood: High flood susceptibility · Uncertain. ${NOTE}.`);
  expect(floodTip(map.get('6').Flood, 'Flood')).toBe('Flood: Moderate flood susceptibility');
});

// Fix-wave re-review: the hover is HTML (Leaflet setContent), and a posted fit's note and
// not-assessed reason are free text, so both are escaped before they reach it
test('a flood row note or not-assessed reason with markup is escaped in the hover', () => {
  const map = levels.purokLikelyLevels({
    flood_results: [
      { purok_id: 7, barangay_id: 3, level: 'Red', uncertain: false, not_assessed_reason: null, estimated_outline: false, note: '<img src=x onerror=alert(1)>' },
      { purok_id: 8, barangay_id: 3, level: null, uncertain: false, not_assessed_reason: '<b>x</b>', estimated_outline: false, note: null },
    ],
  });
  expect(floodTip(map.get('7').Flood, 'Flood')).toBe('Flood: High flood susceptibility. &lt;img src=x onerror=alert(1)&gt;.');
  expect(floodTip(map.get('8').Flood, 'Flood')).toBe('Flood: Not assessed yet (&lt;b&gt;x&lt;/b&gt;)');
});

test('flood words, legend and the not-assessed label', () => {
  expect(FLOOD_WORD).toEqual({
    Red: 'High flood susceptibility', Orange: 'Moderate flood susceptibility',
    Green: 'Low flood susceptibility (within the assessed floodplain)',
  });
  expect(NOT_ASSESSED).toBe('Not assessed yet');
  expect(floodLegend('model')).toBe(
    'Flood: where floods tend to reach (from a machine-learning model; the same in every month, not a forecast of a flood)',
  );
  expect(floodLegend('noah')).toBe(
    "Flood: where floods tend to reach (from UP NOAH's 25-year flood model; the same in every month, not a forecast of a flood)",
  );
});

test('likelyKey changes when the flood classes change', () => {
  const other = { ...both, flood_results: [{ ...both.flood_results[1], level: 'Green' }] };
  expect(likelyKey(both)).not.toBe(likelyKey(other));
});

// Landslide susceptibility in "Likely by month" (plan Task 12)
test('hazardsParam asks for every ticked predicted hazard', () => {
  expect(hazardsParam(['Landslide', 'Fire'])).toBe('Fire,Landslide');
  expect(hazardsParam(['Fire', 'Flood', 'Landslide'])).toBe('Fire,Flood,Landslide');
});

test('three hazards: the highest level fills and each is named', () => {
  const map = levels.purokLikelyLevels({
    purok_results: [{ purok_id: 4, level: 'Orange', probability: 0.02 }],
    flood_results: [{ purok_id: 4, level: null, uncertain: false, not_assessed_reason: 'Outside the surveyed floodplain' }],
    landslide_results: [{ purok_id: 4, level: 'Red', uncertain: false, not_assessed_reason: '', estimated_outline: true }],
  });
  expect(purokLevel(map.get('4'), ['Fire', 'Flood', 'Landslide'])).toBe('Red');
  expect(purokLevel(map.get('4'), ['Fire', 'Flood'])).toBe('Orange');
  expect(map.get('4').Landslide).toEqual(expect.objectContaining({ level: 'Red', uncertain: false }));
  expect(map.get('4').Landslide).not.toHaveProperty('estimated_outline');  // no "estimated outline" anywhere (c0834ac)
  expect(landslideTip(map.get('4').Landslide, 'Landslide')).toBe('Landslide: High landslide susceptibility');
  expect(floodTip(map.get('4').Flood, 'Flood')).toBe('Flood: Not assessed yet (Outside the surveyed floodplain)');
  expect(purokLevel(map.get('4'), ['Landslide'])).toBe('Red');
});

test('landslide words, tips and legend', () => {
  expect(LANDSLIDE_WORD).toEqual({
    Red: 'High landslide susceptibility', Orange: 'Moderate landslide susceptibility', Green: 'Low landslide susceptibility',
  });
  expect(landslideTip({ level: 'Orange', uncertain: true }, 'Purok A')).toBe('Purok A: Moderate landslide susceptibility · Uncertain');
  expect(landslideTip({ level: null, not_assessed_reason: 'No buildings or roads in this area' }, 'Purok A'))
    .toBe('Purok A: Not assessed yet (No buildings or roads in this area)');
  expect(landslideTip({ level: null, not_assessed_reason: '<b>x</b>' }, 'L')).toBe('L: Not assessed yet (&lt;b&gt;x&lt;/b&gt;)');
  expect(susceptibilityTip({ level: 'Green' }, 'Flood', FLOOD_WORD))
    .toBe('Flood: Low flood susceptibility (within the assessed floodplain)');
  expect(landslideLegend('model')).toBe(
    'Landslide: where the ground tends to slide (from a machine-learning model; the same in every month, not a forecast of a landslide)');
  expect(landslideLegend('geoalert')).toBe(landslideLegend('model'));
  expect(landslideLegend('noah')).toBe(
    "Landslide: where the ground tends to slide (from UP NOAH's landslide hazard map; the same in every month, not a forecast of a landslide)");
});

test('each hazard block gives its own note, not the response top line', () => {
  const likely = {
    basis: { method: "Flood's basis sentence" },
    flood: { available: true, source: 'model', basis: "Flood's basis sentence" },
    landslide: { available: true, source: 'noah', basis: "Landslide's basis sentence" },
  };
  expect(susceptibilityNote(likely, 'Landslide')).toBe(landslideLegend('noah'));
  expect(susceptibilityNote(likely, 'Flood')).toBe(floodLegend('model'));
  expect(susceptibilityNote({ landslide: { available: false, reason: 'The landslide model has not been trained yet.' } }, 'Landslide'))
    .toBe('Landslide is unavailable right now: The landslide model has not been trained yet.');
  expect(susceptibilityNote({}, 'Landslide')).toBe('');
});

test('likelyKey changes with the landslide rows', () => {
  const a = { landslide: { model_version: 'v1' }, landslide_results: [{ purok_id: 1, level: 'Red', uncertain: false }] };
  const b = { landslide: { model_version: 'v1' }, landslide_results: [{ purok_id: 1, level: 'Green', uncertain: false }] };
  expect(likelyKey(a)).not.toBe(likelyKey(b));
});

test('the landslide pointer and the legend heading', () => {
  expect(LANDSLIDE_ON_MAP_NOTE).toBe('Landslide shows on the map\'s "Likely by month" view: where the ground tends to slide, the same in every month.');
  expect(legendHeading('past', ['Fire'])).toBe('Past hazard levels');
  expect(legendHeading('likely', [])).toBe('Likely fire levels');
  expect(legendHeading('likely', ['Fire'])).toBe('Likely fire levels');
  expect(legendHeading('likely', ['Fire', 'Flood'])).toBe('Likely fire and flood levels');
  expect(legendHeading('likely', ['Flood'])).toBe('Flood susceptibility');
  expect(legendHeading('likely', ['Landslide'])).toBe('Landslide susceptibility');
  // Final review FM8: hazard names lower-case mid-phrase, as in the fire heading
  expect(legendHeading('likely', ['Flood', 'Landslide'])).toBe('Flood and landslide susceptibility');
  expect(legendHeading('likely', ['Fire', 'Flood', 'Landslide'])).toBe('Likely fire, flood and landslide levels');
});

// Final review F3: the legend's line under the heading is built from the ticked hazards, so flood's
// wording before landslide (PublicMap at HEAD) comes back exactly and landslide reads in parallel
test("the legend line keeps flood's old wording and names landslide the same way", () => {
  // The old text, as PublicMap wrote it before landslide
  expect(legendTitle(['Fire'], 'June')).toBe("Likely in June: each purok's fire level");
  expect(legendTitle(['Fire', 'Flood'], 'June')).toBe("Likely in June: each purok's fire level; flood below");
  expect(legendTitle(['Flood'], 'June')).toBe("Each purok's flood susceptibility, the same in every month");
  // Landslide in parallel
  expect(legendTitle(['Fire', 'Landslide'], 'June 2027')).toBe("Likely in June 2027: each purok's fire level; landslide below");
  expect(legendTitle(['Fire', 'Flood', 'Landslide'], 'June')).toBe(
    "Likely in June: each purok's fire level; flood and landslide below",
  );
  expect(legendTitle(['Landslide'], 'June')).toBe("Each purok's landslide susceptibility, the same in every month");
  expect(legendTitle(['Flood', 'Landslide'], 'June')).toBe(
    "Each purok's flood and landslide susceptibility, the same in every month",
  );
});
