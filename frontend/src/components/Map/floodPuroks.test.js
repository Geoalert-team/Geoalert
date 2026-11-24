import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import FloodPuroks from './FloodPuroks';
import { floodOverlayFeatures, floodOverlayStyle } from './floodMarks';

beforeAll(() => { global.IS_REACT_ACT_ENVIRONMENT = true; });

const rows = [
  { purok_id: 1, level: 'Green', uncertain: false, not_assessed_reason: null, estimated_outline: false },
  { purok_id: 2, level: 'Red', uncertain: true, not_assessed_reason: null, estimated_outline: false },
  { purok_id: 3, level: 'Orange', uncertain: false, not_assessed_reason: null, estimated_outline: true },
  { purok_id: 4, level: null, uncertain: false, not_assessed_reason: 'Outside the surveyed floodplain', estimated_outline: false },
  { purok_id: 5, level: null, uncertain: false, not_assessed_reason: 'Outside the surveyed floodplain', estimated_outline: false },
  { purok_id: 6, level: null, uncertain: false, not_assessed_reason: 'Outside the surveyed floodplain', estimated_outline: false },
  { purok_id: 7, level: null, uncertain: false, not_assessed_reason: 'No buildings in this area', estimated_outline: false },
];
const purokNames = new Map(rows.map((r) => [String(r.purok_id), `Purok ${r.purok_id}`]));

async function render(props) {
  const el = document.createElement('div');
  await act(async () => { createRoot(el).render(<FloodPuroks {...props} />); });
  return el;
}

test('FloodPuroks lists the assessed areas worst first, then groups the rest by reason', async () => {
  const el = await render({ rows, purokNames });
  expect([...el.querySelectorAll('li strong')].map((s) => s.textContent)).toEqual(['Purok 2', 'Purok 3', 'Purok 1']);
  expect(el.textContent).toContain('High flood susceptibility');
  expect(el.textContent).toContain('Uncertain');
  expect(el.textContent).toContain('Estimated outline');
  expect(el.textContent).toContain('Not assessed yet');
  expect(el.textContent).toContain('Outside the surveyed floodplain (3)');
  expect(el.textContent).toContain('No buildings in this area (1)');
});

test('FloodPuroks with no rows says so', async () => {
  const el = await render({ rows: [], purokNames });
  expect(el.textContent).toContain('No flood levels for this barangay.');
});

test('the overlay marks not-assessed areas grey and uncertain ones dashed', () => {
  const geo = {
    type: 'FeatureCollection',
    features: [2, 4, 1].map((id) => ({ type: 'Feature', id, properties: { id, barangay: 3 }, geometry: null })),
  };
  const levels = new Map(rows.map((r) => [String(r.purok_id), { Flood: r }]));
  const fc = floodOverlayFeatures(geo, levels);
  expect(fc.features.map((f) => [f.id, f.properties.flood])).toEqual([[2, 'uncertain'], [4, 'not_assessed']]);
  expect(floodOverlayStyle(fc.features[1])).toEqual(expect.objectContaining({ fillColor: '#c9c9c9', fillOpacity: 0.35, dashArray: '4 3' }));
  expect(floodOverlayStyle(fc.features[0])).toEqual(expect.objectContaining({ fillOpacity: 0, dashArray: '4 3' }));
  expect(floodOverlayFeatures(geo, new Map())).toBeNull();
});

test('with Fire also ticked, a not-assessed area keeps its fire colour: a dashed outline, no grey', () => {
  const geo = { type: 'FeatureCollection', features: [{ type: 'Feature', id: 4, properties: { id: 4 }, geometry: null }] };
  const notAssessed = { level: null, uncertain: false, not_assessed_reason: 'Outside the surveyed floodplain' };
  const withFire = new Map([['4', { Fire: { level: 'Orange', probability: 0.02 }, Flood: notAssessed }]]);
  const [mark] = floodOverlayFeatures(geo, withFire, ['Fire', 'Flood']).features;
  expect(floodOverlayStyle(mark)).toEqual(expect.objectContaining({ fillOpacity: 0, dashArray: '4 3' }));
  // Flood alone, or no fire level to show: grey as before
  const [floodOnly] = floodOverlayFeatures(geo, withFire, ['Flood']).features;
  expect(floodOverlayStyle(floodOnly)).toEqual(expect.objectContaining({ fillColor: '#c9c9c9', fillOpacity: 0.35 }));
  const noFire = new Map([['4', { Flood: notAssessed }]]);
  const [grey] = floodOverlayFeatures(geo, noFire, ['Fire', 'Flood']).features;
  expect(floodOverlayStyle(grey)).toEqual(expect.objectContaining({ fillColor: '#c9c9c9', fillOpacity: 0.35 }));
});

test('a sitio is marked only on its part outside its puroks, like the fills', () => {
  const whole = { type: 'Polygon', coordinates: [[[0, 0], [2, 0], [2, 2], [0, 2], [0, 0]]] };
  const own = { type: 'Polygon', coordinates: [[[1, 1], [2, 1], [2, 2], [1, 2], [1, 1]]] };
  const sitio = { type: 'Feature', id: 9, geometry: whole, properties: { id: 9, members: 2, leftover: own } };
  const levels = new Map([['9', { Flood: { level: null, uncertain: false, not_assessed_reason: 'No buildings in this area' } }]]);
  const [mark] = floodOverlayFeatures({ features: [sitio] }, levels, ['Flood']).features;
  expect(mark.geometry).toBe(own);
  const covered = { ...sitio, properties: { ...sitio.properties, leftover: null } };
  expect(floodOverlayFeatures({ features: [covered] }, levels, ['Flood'])).toBeNull();
});
