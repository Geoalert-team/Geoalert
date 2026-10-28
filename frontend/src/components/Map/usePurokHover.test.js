import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import usePurokHover from './usePurokHover';

// A stand-in for the Leaflet map: just the container and where the pointer is
const mockBox = document.createElement('div');
const mockMap = {
  getContainer: () => mockBox,
  mouseEventToLatLng: jest.fn(),
  closeTooltip: jest.fn(),
  openTooltip: jest.fn(),
  hasLayer: () => false,
};
jest.mock('react-leaflet', () => ({ useMap: () => mockMap }));

beforeAll(() => { global.IS_REACT_ACT_ENVIRONMENT = true; });

const GEO = {
  type: 'FeatureCollection',
  features: [{
    type: 'Feature', id: 7, properties: { id: 7, name: 'Purok Sambag' },
    geometry: { type: 'Polygon', coordinates: [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]] },
  }],
};
const tip = (f) => f.properties.name;

function Probe({ hoverClass }) {
  usePurokHover(GEO, tip, hoverClass);
  return null;
}

async function move(lat, lng) {
  mockMap.mouseEventToLatLng.mockReturnValue({ lat, lng });
  await act(async () => { mockBox.dispatchEvent(new MouseEvent('mousemove', { bubbles: true })); });
}

test('while it names a purok the map says so, so the barangay tooltip can stand aside', async () => {
  const root = createRoot(document.createElement('div'));
  await act(async () => { root.render(<Probe hoverClass="pm-on-past-purok" />); });
  await move(0.5, 0.5);
  expect(mockMap.openTooltip).toHaveBeenCalled();
  expect(mockBox.classList.contains('pm-on-past-purok')).toBe(true);
  await move(5, 5);
  expect(mockBox.classList.contains('pm-on-past-purok')).toBe(false);
  await move(0.5, 0.5);
  await act(async () => { root.unmount(); });
  expect(mockBox.classList.contains('pm-on-past-purok')).toBe(false);
});
