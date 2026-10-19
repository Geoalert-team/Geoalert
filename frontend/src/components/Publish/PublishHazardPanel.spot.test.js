import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import PublishHazardPanel from './PublishHazardPanel';

// The panel talks to the backend on mount; none of that matters here
jest.mock('../../api/hazardsApi', () => ({
  hazardsApi: {
    types: () => Promise.resolve([{ id: 1, name: 'Flood' }]),
    pastZones: () => Promise.resolve({ results: [] }),
  },
}));
jest.mock('../../api/reportApi', () => ({ reportsApi: { located: () => Promise.resolve([]) } }));
jest.mock('../../utils/zoneCheck', () => ({ checkZone: () => Promise.resolve({ warnings: [] }) }));

// Real readSpot and wording; only the PNG loading (canvas) is replaced, by a
// 2 x 2 city where the ground is 9 m above sea level and 3 m above a creek
jest.mock('../../utils/terrain', () => {
  const actual = jest.requireActual('../../utils/terrain');
  const { makeGrid } = jest.requireActual('../../utils/gridGeometry');
  const grid = makeGrid([[10, 123], [10.002, 123.002]], 2, 2);
  const all = (v, Type) => Type.from([v, v, v, v]);
  return {
    ...actual,
    // Plain functions: CRA's Jest config resets jest.fn implementations before each test
    loadTerrain: () => Promise.resolve({
      hand: all(300, Uint16Array), inCity: all(1, Uint8Array), toSea: all(0, Uint8Array), grid, cellM: 100,
    }),
    loadElevation: () => Promise.resolve({ dm: all(90, Uint16Array), inCity: all(1, Uint8Array), grid }),
  };
});

const INDEX = {
  generated: 'test',
  bounds: [[10, 123], [10.002, 123.002]],
  terrain: { file: 'terrain.png' },
  elevation: { file: 'elevation.png' },
};

let container;
let root;

beforeAll(() => { global.IS_REACT_ACT_ENVIRONMENT = true; });

beforeEach(() => {
  container = document.createElement('div');
  document.body.appendChild(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

async function renderPanel(seed) {
  await act(async () => {
    root.render(
      <PublishHazardPanel
        points={[]}
        onUndo={() => {}}
        onClear={() => {}}
        onCancel={() => {}}
        onReplacePoints={() => {}}
        onMethodChange={() => {}}
        seed={seed}
        susceptibilityIndex={INDEX}
      />,
    );
  });
  // Hazard types, then the method, then terrain and elevation each resolve a render later
  for (let i = 0; i < 5; i += 1) {
    // eslint-disable-next-line no-await-in-loop
    await act(async () => { await new Promise((r) => setTimeout(r, 0)); });
  }
}

test('shows the ground reading where the officer tapped', async () => {
  await renderPanel([10.0015, 123.0005]);
  const spot = container.querySelector('.pub-spot');
  expect(spot).not.toBeNull();
  expect(spot.textContent).toContain('Where you tapped');
  expect(spot.textContent).toContain('Ground: about 9 m above sea level');
  expect(spot.textContent).toContain('About 3 m above the nearest creek, drain or low channel.');
  expect(container.textContent).toContain(
    'Estimated from Copernicus elevation data (about 30 m detail). Heights can be off by about 1 m, '
    + 'more among buildings. Check the edge against what you see.',
  );
});

test('no reading before the officer taps', async () => {
  await renderPanel(null);
  expect(container.querySelector('.pub-depth')).not.toBeNull(); // the water-depth method is showing
  expect(container.querySelector('.pub-spot')).toBeNull();
});
