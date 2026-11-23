import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import LikelyPuroks from './LikelyPuroks';

beforeAll(() => { global.IS_REACT_ACT_ENVIRONMENT = true; });

const rows = [0.01, 0.07, 0.003, 0.02, 0.05, 0.015, 0.03].map((p, i) => ({
  purok_id: i + 1,
  barangay_id: 3,
  probability: p,
  level: p >= 0.05 ? 'Red' : p >= 0.02 ? 'Orange' : 'Green',
  interval: [p / 2, p * 2],
  limited_data: i === 4,
}));
const purokNames = new Map(rows.map((r) => [String(r.purok_id), `Purok ${r.purok_id}`]));

async function render(props) {
  const el = document.createElement('div');
  await act(async () => { createRoot(el).render(<LikelyPuroks {...props} />); });
  return el;
}

test('LikelyPuroks shows top 5 then all', async () => {
  const el = await render({ rows, purokNames });
  const names = () => [...el.querySelectorAll('li strong')].map((s) => s.textContent);
  expect(names()).toEqual(['Purok 2', 'Purok 5', 'Purok 7', 'Purok 4', 'Purok 6']);
  expect(el.textContent).toContain('Extreme');
  expect(el.textContent).toContain('Limited data');
  const button = [...el.querySelectorAll('button')].find((b) => b.textContent.includes('Show all'));
  await act(async () => { button.click(); });
  expect(names()).toEqual(['Purok 2', 'Purok 5', 'Purok 7', 'Purok 4', 'Purok 6', 'Purok 1', 'Purok 3']);
  expect(el.textContent).toContain('under 1%');
});

test('LikelyPuroks with no rows says so', async () => {
  const el = await render({ rows: [], purokNames });
  expect(el.textContent).toContain('No purok figures');
  expect(el.querySelectorAll('button')).toHaveLength(0);
});

test('a purok missing from the names map still shows', async () => {
  const el = await render({ rows: rows.slice(0, 1), purokNames: new Map() });
  expect(el.textContent).toContain('Area 1');
});
