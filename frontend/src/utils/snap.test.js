import { boundaryRings, snapPoint } from './snap';

// 1 unit of lat/lng = 1 pixel, y down like the screen
const project = ([lat, lng]) => ({ x: lng, y: -lat });
const unproject = ({ x, y }) => [-y, x];

// A square boundary from (0,0) to (100,100) in [lat, lng]
const RINGS = [[[0, 0], [0, 100], [100, 100], [100, 0], [0, 0]]];

test('a corner near an edge moves onto it', () => {
  const { point, snapped } = snapPoint([10, 50], RINGS, project, unproject);
  expect(snapped).toBe(true);
  expect(point[0]).toBeCloseTo(0);
  expect(point[1]).toBeCloseTo(50);
});

test('a vertex in reach wins over the edge', () => {
  const { point } = snapPoint([6, 4], RINGS, project, unproject);
  expect(point).toEqual([0, 0]);
});

test('a corner far from any boundary stays put', () => {
  const { point, snapped } = snapPoint([50, 50], RINGS, project, unproject);
  expect(snapped).toBe(false);
  expect(point).toEqual([50, 50]);
});

test('reach is measured in pixels', () => {
  expect(snapPoint([16, 50], RINGS, project, unproject).snapped).toBe(false);
  expect(snapPoint([14, 50], RINGS, project, unproject).snapped).toBe(true);
});

test('rings come from polygons and multipolygons, holes included', () => {
  const features = [
    { geometry: { type: 'Polygon', coordinates: [[[0, 0], [1, 0], [1, 1], [0, 0]], [[0.2, 0.2], [0.3, 0.2], [0.3, 0.3], [0.2, 0.2]]] } },
    { geometry: { type: 'MultiPolygon', coordinates: [[[[5, 5], [6, 5], [6, 6], [5, 5]]]] } },
  ];
  const rings = boundaryRings(features);
  expect(rings).toHaveLength(3);
  expect(rings[0][1]).toEqual([0, 1]); // [lat, lng]
});
