import { drawsShading, markerSpots } from './hazardPins';

test('a report-made fire is one marker per purok, no shading', () => {
  const fire = {
    id: 'z',
    position: [10, 123],
    pins: [{ lat: 10.1, lng: 123.1, purok_name: 'Purok Sambag' }, { lat: 10.2, lng: 123.2, purok_name: null }],
  };
  expect(markerSpots(fire)).toEqual([
    { key: 'z:0', position: [10.1, 123.1], purok: 'Purok Sambag' },
    { key: 'z:1', position: [10.2, 123.2], purok: null },
  ]);
  expect(drawsShading(fire)).toBe(false);
});

test('a drawn zone keeps one marker and its shading', () => {
  const flood = { id: 'f', position: [10, 123], pins: [] };
  expect(markerSpots(flood)).toEqual([{ key: 'f', position: [10, 123], purok: null }]);
  expect(drawsShading(flood)).toBe(true);
  expect(drawsShading({ id: 'g', position: [10, 123] })).toBe(true);
});
