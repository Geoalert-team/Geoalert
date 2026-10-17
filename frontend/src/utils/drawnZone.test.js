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

describe('reshaping helpers', () => {
  // eslint-disable-next-line global-require
  const { insertCorner, simplifyOutline, cornersOfZone } = require('./drawnZone');

  test('a new corner goes into the nearest edge, not the end', () => {
    const below = [LAT - DLAT * 0.2, LNG + DLNG / 2]; // just under the bottom edge
    const out = insertCorner(SQUARE, below);
    expect(out).toHaveLength(5);
    expect(out[1]).toEqual(below); // between corner 0 and corner 1
  });

  test('a long outline is thinned to a draggable number of corners', () => {
    const circle = Array.from({ length: 300 }, (_, i) => {
      const t = (2 * Math.PI * i) / 300;
      return [LAT + DLAT * Math.sin(t), LNG + DLNG * Math.cos(t)];
    });
    const out = simplifyOutline(circle, 40);
    expect(out.length).toBeLessThanOrEqual(40);
    expect(out.length).toBeGreaterThanOrEqual(8);
  });

  test('corners come from the drawn outline when there is one', () => {
    const ring = [[LNG, LAT], [LNG + DLNG, LAT], [LNG + DLNG, LAT + DLAT], [LNG, LAT]];
    const feature = { properties: { outline: { type: 'Polygon', coordinates: [ring] } }, geometry: null };
    expect(cornersOfZone(feature)).toEqual([[LAT, LNG], [LAT, LNG + DLNG], [LAT + DLAT, LNG + DLNG]]);
  });

  test('otherwise from the largest part of the saved shape', () => {
    const small = [[LNG, LAT], [LNG + DLNG / 10, LAT], [LNG, LAT + DLAT / 10], [LNG, LAT]];
    const big = [[LNG, LAT], [LNG + DLNG, LAT], [LNG + DLNG, LAT + DLAT], [LNG, LAT + DLAT], [LNG, LAT]];
    const feature = { properties: {}, geometry: { type: 'MultiPolygon', coordinates: [[small], [big]] } };
    expect(cornersOfZone(feature)).toHaveLength(4);
  });
});
