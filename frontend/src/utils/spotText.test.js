import {
  ACCURACY_NOTE, describeSpot, describeSusceptibility, formatDistance, nearestNamedRiver,
} from './spotText';

const W = (h) => describeSpot({ elevationM: 5, handM: h, drainsToSea: false }).waterway;
const RISE = ' above the nearest creek, drain or low channel. Water would have to rise about that much to reach here.';

const line = (name, lat) => ({
  type: 'Feature',
  properties: { kind: 'river', name },
  geometry: { type: 'LineString', coordinates: [[123.000, lat], [123.010, lat]] },
});
// A is named; the two closer lines have no usable name; B is named but far away
const RIVERS = {
  type: 'FeatureCollection',
  features: [line('A', 10.000), line('', 10.0005), line('  ', 10.0008), line('B', 10.1)],
};

test('ground', () => {
  expect(describeSpot({ elevationM: 9.4, handM: null, drainsToSea: null }).ground).toBe('about 9 m above sea level');
  expect(describeSpot({ elevationM: 0.4, handM: null, drainsToSea: null }).ground).toBe('about at sea level');
  expect(describeSpot({ elevationM: null, handM: null, drainsToSea: null }).ground).toBeNull();
});

test('waterway bands', () => {
  expect(W(0.49)).toBe('About level with the nearest creek, drain or low channel.');
  expect(W(0.5)).toBe(`About 0.5 m${RISE}`);
  expect(W(1.26)).toBe(`About 1.5 m${RISE}`);
  expect(W(4.9)).toBe(`About 5 m${RISE}`);
  expect(W(5)).toBe(`About 5 m${RISE}`);
  expect(W(7.6)).toBe(`About 8 m${RISE}`);
  expect(W(10)).toBe(`About 10 m${RISE}`);
  expect(W(10.1)).toBe('More than 10 m above the nearest creek, drain or low channel.');
});

test('no waterway line against the sea or without data', () => {
  expect(describeSpot({ elevationM: 2, handM: 1.5, drainsToSea: true }).waterway).toBeNull();
  expect(describeSpot({ elevationM: 2, handM: null, drainsToSea: null }).waterway).toBeNull();
});

test('susceptibility line', () => {
  const L = ['Very low', 'Low', 'Moderate', 'High', 'Very high'].map((label) => ({ label }));
  expect(describeSusceptibility({ flood: 4, landslide: 2, fire: 1 }, L))
    .toBe('Susceptibility: Flood High · Landslide Low · Fire Very low');
  expect(describeSusceptibility({ flood: 5, landslide: 0, fire: 0 }, L)).toBe('Susceptibility: Flood Very high');
  expect(describeSusceptibility({ flood: 0, landslide: 0, fire: 0 }, L)).toBeNull();
});

test('nearest named river', () => {
  expect(nearestNamedRiver(RIVERS, 10.001, 123.005).name).toBe('A');
  expect(nearestNamedRiver(RIVERS, 10.001, 123.005).distanceM).toBeCloseTo(111.3, 0);
  expect(nearestNamedRiver(RIVERS, 10.03, 123.005)).toBeNull(); // more than 2 km from A and B
  expect(nearestNamedRiver(null, 10, 123)).toBeNull();
});

test('distances', () => {
  expect(formatDistance(14)).toBe('10 m');
  expect(formatDistance(994)).toBe('990 m');
  expect(formatDistance(996)).toBe('1.0 km');
  expect(formatDistance(1234)).toBe('1.2 km');
});

test('accuracy note is the fixed text', () => {
  expect(ACCURACY_NOTE).toBe(
    'Heights come from satellite data (about 30 m detail) and can be off by about 1 m, more among buildings.',
  );
});
