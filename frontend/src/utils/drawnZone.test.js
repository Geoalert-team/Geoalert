import { areaSqM, formatArea, middleOf, pointsToPolygon } from './drawnZone';

// About 100 m on each side at Talisay's latitude
const LAT = 10.2446;
const LNG = 123.8473;
const DLAT = 100 / 111320;
const DLNG = 100 / (111320 * Math.cos((LAT * Math.PI) / 180));
const SQUARE = [[LAT, LNG], [LAT, LNG + DLNG], [LAT + DLAT, LNG + DLNG], [LAT + DLAT, LNG]];

test('polygon is closed and in GeoJSON order', () => {
  const ring = pointsToPolygon(SQUARE).coordinates[0];
  expect(ring).toHaveLength(5);
  expect(ring[0]).toEqual([LNG, LAT]);
  expect(ring[4]).toEqual(ring[0]);
});

test('area of a 100 m square is about one hectare', () => {
  expect(areaSqM(SQUARE)).toBeGreaterThan(9900);
  expect(areaSqM(SQUARE)).toBeLessThan(10100);
});

test('area is the same whichever way the corners go round', () => {
  expect(areaSqM([...SQUARE].reverse())).toBeCloseTo(areaSqM(SQUARE), 3);
});

test('fewer than three corners has no area', () => {
  expect(areaSqM(SQUARE.slice(0, 2))).toBe(0);
});

test('formats area in sensible units', () => {
  expect(formatArea(850)).toBe('850 m²');
  expect(formatArea(32000)).toBe('3.2 ha');
  expect(formatArea(1400000)).toBe('1.40 km²');
});

test('middle is the average of the corners', () => {
  const [lat, lng] = middleOf(SQUARE);
  expect(lat).toBeCloseTo(LAT + DLAT / 2, 9);
  expect(lng).toBeCloseTo(LNG + DLNG / 2, 9);
});
