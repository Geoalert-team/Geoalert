import {
  NOT_LISTED, isFireType, localNow, placeLabel, purokAtPin, purokOptions, reportPayload, validateReport,
} from './fireReport';

const square = (id, name, barangay, x0, y0) => ({
  type: 'Feature',
  id,
  properties: { name, barangay },
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
  started_at: '2026-10-25T13:00', location: [10.255, 123.855], purok: '3', purok_other: '', severity_estimate: '',
};
const NOW = new Date('2026-10-25T14:00');

test('purok options: named first A-Z, then unnamed areas by number', () => {
  expect(purokOptions(GEO, '19').map((o) => o.label)).toEqual(
    ['Purok Agoho', 'Purok Sambag', 'Unnamed area 2 (no name yet)', 'Unnamed area 10 (no name yet)'],
  );
});

test('the pin picks its purok, only in the right barangay', () => {
  expect(purokAtPin(GEO, '19', [10.255, 123.855])).toBe('3');
  expect(purokAtPin(GEO, '19', [10.305, 123.905])).toBeNull();
  expect(purokAtPin(GEO, '19', null)).toBeNull();
});

test('a complete fire report passes; each missing part is named', () => {
  const opts = { fire: true, hasPuroks: true, now: NOW };
  expect(validateReport(FIRE, opts)).toEqual({});
  expect(validateReport({ ...FIRE, location: null }, opts).location).toBe('Drop a pin where the fire is.');
  expect(validateReport({ ...FIRE, started_at: '2026-10-25T14:10' }, opts).started_at)
    .toBe("The start time can't be in the future.");
  // a phone clock a little fast is not the future
  expect(validateReport({ ...FIRE, started_at: '2026-10-25T14:02' }, opts)).toEqual({});
  expect(validateReport({ ...FIRE, purok: NOT_LISTED, purok_other: ' ' }, opts).purok)
    .toBe("Choose the purok or sitio, or pick 'Not on the list' and type its name.");
  expect(validateReport({ ...FIRE, purok: '' }, { ...opts, hasPuroks: false })).toEqual({});
  expect(validateReport(FIRE, opts).severity_estimate).toBeUndefined();
});

test('other hazards still ask how serious it is', () => {
  expect(validateReport({ ...FIRE, location: null }, { fire: false, hasPuroks: true, now: NOW }))
    .toEqual({ severity_estimate: 'Choose how serious it looks.' });
});

test('payload: fire sends start time and place; other types send neither', () => {
  const fire = reportPayload({ ...FIRE, purok: NOT_LISTED, purok_other: ' Purok Boongon ' }, { fire: true });
  expect(fire).toMatchObject({ barangay: 19, hazard_type: 2, purok_other: 'Purok Boongon', location: [10.255, 123.855] });
  expect(fire.started_at).toBe(new Date('2026-10-25T13:00').toISOString());
  expect(fire).not.toHaveProperty('purok');
  expect(fire).not.toHaveProperty('severity_estimate');
  expect(reportPayload(FIRE, { fire: true }).purok).toBe(3);
  const flood = reportPayload({ ...FIRE, severity_estimate: 'Moderate' }, { fire: false });
  expect(flood.severity_estimate).toBe('Moderate');
  ['started_at', 'purok', 'purok_other'].forEach((k) => expect(flood).not.toHaveProperty(k));
});

test('place label', () => {
  expect(placeLabel({ purok_name: 'Purok Sambag', purok_other: '' })).toBe('Purok Sambag');
  expect(placeLabel({ purok_name: null, purok_other: 'Purok Boongon' })).toBe('Purok Boongon (not on the list)');
  expect(placeLabel({ purok_name: null, purok_other: '' })).toBeNull();
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
