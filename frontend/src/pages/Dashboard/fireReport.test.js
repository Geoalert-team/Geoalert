import {
  hazardSwitchErrors, isFireType, localNow, placeLabel, purokOptions, purokPins, reportPayload,
  validateReport, withBarangay, withHazardType,
} from './fireReport';

// label_point as the API sends it: [lng, lat], rounded to 6 decimals
const round6 = (n) => Number(n.toFixed(6));
const square = (id, name, barangay, x0, y0) => ({
  type: 'Feature',
  id,
  properties: { name, barangay, label_point: [round6(x0 + 0.005), round6(y0 + 0.005)] },
  geometry: {
    type: 'Polygon',
    coordinates: [[[x0, y0], [x0 + 0.01, y0], [x0 + 0.01, y0 + 0.01], [x0, y0 + 0.01], [x0, y0]]],
  },
});
const GEO = {
  type: 'FeatureCollection',
  features: [
    square(5, 'Unnamed area 10', 19, 123.80, 10.20), square(3, 'Purok Sambag', 19, 123.85, 10.25),
    square(4, 'Unnamed area 2', 19, 123.82, 10.20), square(6, 'Purok Agoho', 19, 123.86, 10.25),
    square(7, 'Kimba', 8, 123.90, 10.30),
  ],
};
const FIRE = {
  barangay: '19', hazard_type: '2', description: 'Smoke from a house near the chapel',
  started_at: '2026-10-25T13:00', started_at_edited: false, location: [10.255, 123.855],
  puroks: ['3', '6'], severity_estimate: '',
};
const NOW = new Date('2026-10-25T14:00');

test('options: named first A-Z, then unnamed areas by number', () => {
  expect(purokOptions(GEO, '19').map((o) => o.label)).toEqual(
    ['Purok Agoho', 'Purok Sambag', 'Unnamed area 2 (no name yet)', 'Unnamed area 10 (no name yet)'],
  );
});

test('options leave out puroks already chosen', () => {
  expect(purokOptions(GEO, '19', ['3']).map((o) => o.label))
    .toEqual(['Purok Agoho', 'Unnamed area 2 (no name yet)', 'Unnamed area 10 (no name yet)']);
});

test('pins sit at each chosen purok, in order', () => {
  expect(purokPins(GEO, ['6', '3'])).toEqual([
    { id: '6', name: 'Purok Agoho', lat: 10.255, lng: 123.865 },
    { id: '3', name: 'Purok Sambag', lat: 10.255, lng: 123.855 },
  ]);
});

test('choosing Fire refreshes a start time nobody touched', () => {
  const later = new Date(2026, 9, 25, 14, 0);
  expect(withHazardType({ ...FIRE, started_at: '2026-10-25T08:00' }, '2', { fire: true, now: later }).started_at)
    .toBe('2026-10-25T14:00');
  expect(withHazardType({ ...FIRE, started_at: '2026-10-25T08:00', started_at_edited: true }, '2',
    { fire: true, now: later }).started_at).toBe('2026-10-25T08:00');
  expect(withHazardType(FIRE, '1', { fire: false, now: later }).hazard_type).toBe('1');
});

test('changing barangay empties the puroks', () => {
  expect(withBarangay(FIRE, '8')).toMatchObject({ barangay: '8', puroks: [] });
});

test('switching hazard clears the fire errors', () => {
  expect(hazardSwitchErrors({ puroks: 'x', started_at: 'y', location: 'z', severity_estimate: 's', description: 'd' }))
    .toEqual({ description: 'd' });
});

test('fire report checks', () => {
  const opts = { fire: true, hasPuroks: true, purokStatus: 'ready', now: NOW };
  expect(validateReport(FIRE, opts)).toEqual({});
  expect(validateReport({ ...FIRE, location: null }, opts)).toEqual({}); // no pin needed
  expect(validateReport({ ...FIRE, puroks: [] }, opts).puroks).toBe('Choose the purok or sitio where the fire is.');
  expect(validateReport({ ...FIRE, puroks: Array.from({ length: 11 }, (_, i) => String(i)) }, opts).puroks)
    .toBe('Choose at most 10 puroks.');
  expect(validateReport({ ...FIRE, puroks: [] }, { ...opts, purokStatus: 'failed', hasPuroks: false }).puroks)
    .toBe("The purok list didn't load. Try again.");
  expect(validateReport({ ...FIRE, puroks: [] }, { ...opts, hasPuroks: false })).toEqual({});
  expect(validateReport({ ...FIRE, started_at: '2026-10-25T14:10' }, opts).started_at)
    .toBe("The start time can't be in the future.");
  // a phone clock a little fast is not the future
  expect(validateReport({ ...FIRE, started_at: '2026-10-25T14:02' }, opts)).toEqual({});
  expect(validateReport({ ...FIRE, started_at: '' }, opts).started_at).toBe('Say when the fire started.');
});

test('other hazards still ask how serious it is', () => {
  expect(validateReport({ ...FIRE, puroks: [] }, { fire: false, hasPuroks: true, purokStatus: 'ready', now: NOW }))
    .toEqual({ severity_estimate: 'Choose how serious it looks.' });
});

test('payload: fire sends puroks, no pin; other types keep the pin', () => {
  const fire = reportPayload(FIRE, { fire: true });
  expect(fire).toMatchObject({ barangay: 19, hazard_type: 2, puroks: [3, 6] });
  expect(fire.started_at).toBe(new Date('2026-10-25T13:00').toISOString());
  ['location', 'severity_estimate', 'purok', 'purok_other'].forEach((k) => expect(fire).not.toHaveProperty(k));
  const flood = reportPayload({ ...FIRE, severity_estimate: 'Moderate' }, { fire: false });
  expect(flood).toMatchObject({ severity_estimate: 'Moderate', location: [10.255, 123.855] });
  ['started_at', 'puroks'].forEach((k) => expect(flood).not.toHaveProperty(k));
});

test('place label lists the puroks', () => {
  expect(placeLabel({ puroks: [{ name: 'Purok Santol' }, { name: 'Purok Lubi' }] })).toBe('Purok Santol, Purok Lubi');
  expect(placeLabel({ puroks: [] })).toBeNull();
  expect(placeLabel({})).toBeNull();
});

test('only the Fire hazard type gets the fire form', () => {
  const types = [{ id: 1, name: 'Flood' }, { id: 2, name: 'Fire' }];
  expect(isFireType(types, '2')).toBe(true);
  expect(isFireType(types, 1)).toBe(false);
  expect(isFireType(types, '')).toBe(false);
  expect(isFireType(null, '2')).toBe(false);
});

test('localNow is a datetime-local value', () => {
  expect(localNow(new Date(2026, 9, 25, 9, 5))).toBe('2026-10-25T09:05');
});
