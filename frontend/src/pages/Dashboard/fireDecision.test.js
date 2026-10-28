import { canPush, hazardNoun, historyLine, levelLabel, reportPins, reportPurokShapes } from './fireDecision';

test('which reports can be pushed to the map, whatever their type', () => {
  for (const name of ['Fire', 'Flood', 'Landslide']) {
    const report = { hazard_type_details: { name } };
    expect(canPush({ ...report, status: 'Pending', hazard_zone: null })).toBe(true);
    // validated without being pushed
    expect(canPush({ ...report, status: 'Validated', hazard_zone: null })).toBe(true);
    expect(canPush({ ...report, status: 'Validated', hazard_zone: 'z' })).toBe(false);
    expect(canPush({ ...report, status: 'Rejected', hazard_zone: null })).toBe(false);
  }
});

test('the hazard in words', () => {
  expect(hazardNoun({ hazard_type_details: { name: 'Landslide' } })).toBe('landslide');
  expect(hazardNoun({})).toBe('hazard');
});

test('history line', () => {
  expect(historyLine({ name: 'Purok Sambag', count: 3, level: 'Orange' }, 5)).toBe('Purok Sambag: 3 fires in 5 years → Moderate');
  expect(historyLine({ name: 'Purok Lubi', count: 1, level: 'Green' }, 5)).toBe('Purok Lubi: 1 fire in 5 years → Low');
  expect(historyLine({ name: 'Purok Pinya', count: 0, level: null }, 5)).toBe('Purok Pinya: no fires in 5 years → Low');
  expect(historyLine({ name: 'Purok Lubi', count: 4, level: 'Orange' }, 5, 'flood')).toBe('Purok Lubi: 4 floods in 5 years → Moderate');
  expect(historyLine({ name: 'Purok Lubi', count: 0, level: null }, 5, 'landslide')).toBe('Purok Lubi: no landslides in 5 years → Low');
});

test('level labels', () => {
  expect(['Green', 'Orange', 'Red', 'x'].map(levelLabel)).toEqual(['Low', 'Moderate', 'Extreme', 'x']);
});

test('pins for a report: one per purok, else its own location', () => {
  expect(reportPins({ puroks: [{ id: 415, name: 'Purok Sambag', lat: 10.3, lng: 123.8 }], latitude: 1, longitude: 2 }))
    .toEqual([{ id: '415', name: 'Purok Sambag', lat: 10.3, lng: 123.8 }]);
  expect(reportPins({ puroks: [], latitude: 10.2, longitude: 123.9 })).toEqual([{ id: 'report', name: '', lat: 10.2, lng: 123.9 }]);
  expect(reportPins({ puroks: [], latitude: null, longitude: null })).toEqual([]);
});

test('outlines for a report: the puroks it names, from the purok layer', () => {
  const geo = { features: [{ id: 415, properties: { name: 'Purok Sambag' } }, { id: 7, properties: { name: 'Purok Lubi' } }] };
  expect(reportPurokShapes(geo, { puroks: [{ id: '415', name: 'Purok Sambag' }] })).toEqual([geo.features[0]]);
  expect(reportPurokShapes(geo, { puroks: [] })).toEqual([]);
  // Before the layer loads
  expect(reportPurokShapes(null, { puroks: [{ id: 415 }] })).toEqual([]);
});
