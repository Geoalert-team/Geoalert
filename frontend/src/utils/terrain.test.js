import { decodeElevationPixels, decodeTerrainPixels, loadElevation, readSpot } from './terrain';
import { makeGrid } from './gridGeometry';

const px = (...rgba) => Uint8Array.from(rgba);

test('terrain pixels: hand in cm, city and sea marks', () => {
  const t = decodeTerrainPixels(px(1, 44, 255, 255, 0, 50, 200, 255, 0, 0, 0, 255), 3);
  expect([...t.hand]).toEqual([300, 50, 0]);
  expect([...t.inCity]).toEqual([1, 1, 0]);
  expect([...t.toSea]).toEqual([0, 1, 0]);
});

test('elevation pixels: decimetres and city mask', () => {
  const e = decodeElevationPixels(px(0, 90, 255, 255, 26, 38, 255, 255, 0, 0, 0, 255), 3);
  expect([...e.dm]).toEqual([90, 6694, 0]);
  expect([...e.inCity]).toEqual([1, 1, 0]);
});

// 2 x 2 grid; cell order: top-left, top-right, bottom-left, bottom-right
const grid = makeGrid([[10, 123], [10.002, 123.002]], 2, 2);
const elevation = {
  dm: Uint16Array.from([90, 6694, 0, 30]),
  inCity: Uint8Array.from([1, 1, 0, 1]),
  grid,
};
const terrain = {
  hand: Uint16Array.from([300, 1200, 0, 40]),
  inCity: Uint8Array.from([1, 1, 0, 1]),
  toSea: Uint8Array.from([0, 0, 0, 1]),
  grid,
  cellM: 100,
};

test('readSpot reads a city cell', () => {
  expect(readSpot(terrain, elevation, 10.0015, 123.0005))
    .toEqual({ inCity: true, elevationM: 9, handM: 3, drainsToSea: false });
});

test('readSpot: a cell the raster puts outside the city is not read', () => {
  expect(readSpot(terrain, elevation, 10.0005, 123.0005))
    .toEqual({ inCity: false, elevationM: null, handM: null, drainsToSea: null });
});

test('readSpot: off the grid, and without terrain', () => {
  expect(readSpot(terrain, elevation, 11, 124).inCity).toBe(false);
  expect(readSpot(null, elevation, 10.0005, 123.0015))
    .toEqual({ inCity: true, elevationM: 3, handM: null, drainsToSea: null });
});

test('readSpot: the sea mark comes through', () => {
  expect(readSpot(terrain, elevation, 10.0005, 123.0015).drainsToSea).toBe(true);
});

test('loadElevation without an elevation entry resolves null', async () => {
  await expect(loadElevation({ generated: 'x' })).resolves.toBeNull();
});
