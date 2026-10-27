import { drawsShading, hazardPuroks, markerSpots } from './hazardPins';

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

// Two square puroks side by side: Sambag 0-1, Lubi 1-2 (lng), both lat 0-1
const square = (id, x0, name) => ({
  type: 'Feature',
  id,
  properties: { name },
  geometry: { type: 'Polygon', coordinates: [[[x0, 0], [x0 + 1, 0], [x0 + 1, 1], [x0, 1], [x0, 0]]] },
});
const GEO = { type: 'FeatureCollection', features: [square(7, 0, 'Purok Sambag'), square(8, 1, 'Purok Lubi')] };
const names = (geo) => geo?.features.map((f) => f.properties.name);

test("a hazard's puroks: the ones its reports name", () => {
  const fire = { id: 'z', position: [0.5, 0.5], pins: [{ lat: 0.5, lng: 1.5, purok_id: 8, purok_name: 'Purok Lubi' }] };
  expect(names(hazardPuroks(fire, GEO))).toEqual(['Purok Lubi']);
});

test("a hazard's puroks: the one under a pin that names none", () => {
  const pinned = { id: 'p', position: [0.5, 0.5], pins: [{ lat: 0.5, lng: 0.5, purok_id: null, purok_name: null }] };
  expect(names(hazardPuroks(pinned, GEO))).toEqual(['Purok Sambag']);
  // A drawn zone: the purok under its one pin
  expect(names(hazardPuroks({ id: 'f', position: [0.5, 1.5], pins: [] }, GEO))).toEqual(['Purok Lubi']);
});

test("a hazard's puroks: none outside every purok, or before they load", () => {
  expect(hazardPuroks({ id: 'f', position: [5, 5], pins: [] }, GEO)).toBeNull();
  expect(hazardPuroks({ id: 'f', position: [0.5, 0.5], pins: [] }, null)).toBeNull();
  // Each purok once, however many pins sit in it
  const twice = { id: 'z', position: [0.5, 0.5], pins: [{ lat: 0.5, lng: 0.5, purok_id: 7 }, { lat: 0.6, lng: 0.6, purok_id: null }] };
  expect(names(hazardPuroks(twice, GEO))).toEqual(['Purok Sambag']);
});
