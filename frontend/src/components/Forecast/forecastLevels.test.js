import {
  FORECAST_DISCLAIMER, IN_TRAINING_NOTE, RAIN_ATTRIBUTION, aboutChanceText, chanceText, combinedByBarangay, combinedText, likelyKey, rainYearsText, smallChanceText, hazardsParam, levelLabel, rangeText,
  combinedUnavailable, unavailableNote,
} from './forecastLevels';

test('hazardsParam orders and joins', () => expect(hazardsParam(new Set(['Landslide', 'Fire']))).toBe('Fire,Landslide'));

test('hazardsParam of nothing is empty', () => expect(hazardsParam([])).toBe(''));

test('combinedText lists each hazard with its chance', () =>
  expect(combinedText({ hazards: [{ hazard_type: 'Fire', probability: 0.08 }, { hazard_type: 'Flood', probability: 0.031 },
    { hazard_type: 'Landslide', probability: 0.3 }] })).toBe('Fire 8% · Flood 3% · Landslide 30%'));

test('combinedText says under 1% for a tiny chance, never 0%', () =>
  expect(combinedText({ hazards: [{ hazard_type: 'Fire', probability: 0.08 }, { hazard_type: 'Flood', probability: 0.004 },
    { hazard_type: 'Landslide', probability: 0.3 }, { hazard_type: 'Other', probability: null }] })).toBe('Fire 8% · Flood under 1% · Landslide 30%'));

test('combinedText names a missing hazard as unavailable, in the order of the row', () => {
  expect(combinedText({
    hazards: [{ hazard_type: 'Fire', probability: 0.19 }, { hazard_type: 'Flood', probability: null }, { hazard_type: 'Landslide', probability: 0.01 }],
    missing: ['Flood'],
  }, ['Flood'])).toBe('Fire 19% · Flood unavailable · Landslide 1%');
  expect(combinedText({
    hazards: [{ hazard_type: 'Flood', probability: null }, { hazard_type: 'Landslide', probability: null }],
    missing: ['Flood', 'Landslide'],
  }, new Set(['Flood', 'Landslide']))).toBe('Flood unavailable · Landslide unavailable');
});

test('combinedText leaves out a missing hazard the response does not call unavailable', () => {
  // a past period: fire is on counting and this barangay has no fire on record
  const noFire = {
    hazards: [{ hazard_type: 'Fire', probability: null }, { hazard_type: 'Flood', probability: 0.01 }, { hazard_type: 'Landslide', probability: 0.004 }],
    missing: ['Fire'],
  };
  expect(combinedText(noFire, [])).toBe('Flood 1% · Landslide under 1%');
  expect(combinedText(noFire)).toBe('Flood 1% · Landslide under 1%');
  expect(combinedText(noFire, null)).toBe('Flood 1% · Landslide under 1%');
  // only the hazards the response names read unavailable
  expect(combinedText({
    hazards: [{ hazard_type: 'Fire', probability: null }, { hazard_type: 'Flood', probability: null }, { hazard_type: 'Landslide', probability: 0.3 }],
    missing: ['Fire', 'Flood'],
  }, ['Flood'])).toBe('Flood unavailable · Landslide 30%');
});

test('combinedUnavailable: no chance because a hazard the response names is unavailable', () => {
  const row = (missing, probability = null) => ({ probability, missing });
  expect(combinedUnavailable(row(['Flood', 'Landslide']), ['Flood', 'Landslide'])).toBe(true);
  expect(combinedUnavailable(row(['Fire', 'Flood']), new Set(['Flood']))).toBe(true);
  // no fire on record is not unavailable
  expect(combinedUnavailable(row(['Fire']), [])).toBe(false);
  expect(combinedUnavailable(row(['Fire']))).toBe(false);
  expect(combinedUnavailable(row(['Fire']), ['Flood'])).toBe(false);
  // a row with a chance is never unavailable as a whole
  expect(combinedUnavailable(row(['Flood'], 0.19), ['Flood'])).toBe(false);
  expect(combinedUnavailable({ probability: null }, ['Flood'])).toBe(false);
});

test('unavailableNote names the shown hazards that are unavailable, in a fixed order', () => {
  const all = ['Fire', 'Flood', 'Landslide'];
  expect(unavailableNote({ unavailable_hazards: [] }, all)).toBe('');
  expect(unavailableNote({}, all)).toBe('');
  expect(unavailableNote(null, all)).toBe('');
  expect(unavailableNote({ unavailable_hazards: ['Flood'] }, all))
    .toBe('Unavailable right now in some or all barangays, and left out of their All hazards chance: Flood.');
  expect(unavailableNote({ unavailable_hazards: ['Landslide', 'Flood'] }, new Set(all)))
    .toBe('Unavailable right now in some or all barangays, and left out of their All hazards chance: Flood and Landslide.');
  expect(unavailableNote({ unavailable_hazards: ['Landslide', 'Fire', 'Flood'] }, all))
    .toBe('Unavailable right now in some or all barangays, and left out of their All hazards chance: Fire, Flood and Landslide.');
  // a hazard that is not shown is left out
  expect(unavailableNote({ unavailable_hazards: ['Flood', 'Landslide'] }, ['Fire', 'Landslide']))
    .toBe('Unavailable right now in some or all barangays, and left out of their All hazards chance: Landslide.');
  expect(unavailableNote({ unavailable_hazards: ['Flood'] }, new Set(['Fire']))).toBe('');
});

test('rainYearsText names the count and the years', () => {
  expect(rainYearsText([2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025])).toBe('8 past rain years (2018–2025)');
  expect(rainYearsText([2018, 2020, 2023])).toBe('3 past rain years (2018, 2020 and 2023)');
  expect(rainYearsText([2018, 2020])).toBe('2 past rain years (2018 and 2020)');
  expect(rainYearsText([2018])).toBe('1 past rain year (2018)');
  expect(rainYearsText([2020, 2018, 2019, 2018])).toBe('3 past rain years (2018–2020)');
  expect(rainYearsText([])).toBe('');
  expect(rainYearsText(null)).toBe('');
  expect(rainYearsText(undefined)).toBe('');
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

test('rangeText', () => {
  expect(rangeText({ range: [0.03, 0.41] })).toBe('3–41% across past rain years');
  // a positive end under 0.5% reads under 1%, never 0%
  expect(rangeText({ range: [0.0004, 0.04] })).toBe('under 1% to 4% across past rain years');
  expect(rangeText({ range: [0.0004, 0.004] })).toBe('under 1% across past rain years');
  // an exact 0 stays 0
  expect(rangeText({ range: [0, 0.04] })).toBe('0–4% across past rain years');
});

test('an unavailable row says so instead of None on record', () => {
  expect(levelLabel({ method: 'unavailable', level: 'None' })).toBe('Unavailable right now');
  expect(levelLabel({ method: 'model', level: 'Low' })).toBe('Low');
  expect(levelLabel({ level: 'None' })).toBe('None on record');
});

test('the exact copy', () => {
  expect(RAIN_ATTRIBUTION.text).toBe(
    'Rain data from NASA POWER (CC BY 4.0), processed into hazard chances by GeoAlert',
  );
  expect(RAIN_ATTRIBUTION.links).toEqual([
    { label: 'NASA POWER', href: 'https://power.larc.nasa.gov/' },
    { label: 'CC BY 4.0', href: 'https://creativecommons.org/licenses/by/4.0/' },
  ]);
  expect(FORECAST_DISCLAIMER).toBe(
    'Fire is estimated from past fires; flood and landslide from rain and terrain in past years. '
    + 'It is a heads-up for preparing, not a warning that a hazard is coming. Live alerts come only from the DRRMO.',
  );
  expect(IN_TRAINING_NOTE).toBe(
    'The model learned from this period; see the accuracy check for results on years it never saw.',
  );
});

test('combinedByBarangay keys combined rows by barangay id', () => {
  const rows = [{ barangay_id: 7, probability: 0.2 }, { barangay_id: 9, probability: null }];
  const m = combinedByBarangay({ combined: rows });
  expect(m.get('7')).toBe(rows[0]);
  expect(m.get('9').probability).toBeNull();
  expect(m.has('8')).toBe(false);
  expect(combinedByBarangay(null).size).toBe(0);
  expect(combinedByBarangay({ results: [] }).size).toBe(0);
});

test('likelyKey changes with a response even when the row counts are equal', () => {
  const flood = { combined: [{ barangay_id: 1, probability: 0.1, level: 'Low' }], results: [{ barangay_id: 1, hazard_type: 'Flood', method: 'model', level: 'Low', probability: 0.1 }] };
  const slide = { combined: [{ barangay_id: 1, probability: 0.3, level: 'High' }], results: [{ barangay_id: 1, hazard_type: 'Landslide', method: 'model', level: 'High', probability: 0.3 }] };
  expect(likelyKey(flood)).not.toBe(likelyKey(slide));
  expect(likelyKey(flood)).toBe(likelyKey({ ...flood }));
  expect(likelyKey(null)).toBe('none');
});
