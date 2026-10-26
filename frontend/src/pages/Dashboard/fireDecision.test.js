import { canDecide, historyLine, levelLabel, reportPins } from './fireDecision';

test('which reports the fire decision takes', () => {
  const fire = { hazard_type_details: { name: 'Fire' } };
  expect(canDecide({ ...fire, status: 'Pending', hazard_zone: null })).toBe(true);
  // validated before this flow and never put on the map
  expect(canDecide({ ...fire, status: 'Validated', hazard_zone: null })).toBe(true);
  expect(canDecide({ ...fire, status: 'Validated', hazard_zone: 'z' })).toBe(false);
  expect(canDecide({ ...fire, status: 'Rejected', hazard_zone: null })).toBe(false);
  expect(canDecide({ hazard_type_details: { name: 'Flood' }, status: 'Pending' })).toBe(false);
});

test('history line', () => {
  expect(historyLine({ name: 'Purok Sambag', count: 3, level: 'Orange' }, 5)).toBe('Purok Sambag: 3 fires in 5 years → Moderate');
  expect(historyLine({ name: 'Purok Lubi', count: 1, level: 'Green' }, 5)).toBe('Purok Lubi: 1 fire in 5 years → Low');
  expect(historyLine({ name: 'Purok Pinya', count: 0, level: null }, 5)).toBe('Purok Pinya: no fires in 5 years → Low');
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
