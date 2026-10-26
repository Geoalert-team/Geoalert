import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { MemoryRouter } from 'react-router-dom';
import HistoricalData from './HistoricalData';
import { historyApi } from '../api/historyApi';

jest.mock('../components/Navbar/PublicNavbar', () => () => null);
jest.mock('../api/historyApi', () => ({ historyApi: { list: jest.fn(), area: jest.fn(), detail: jest.fn() } }));
jest.mock('../api/barangaysApi', () => ({
  barangaysApi: {
    list: () => Promise.resolve({ features: [
      { id: 19, properties: { name: 'San Roque' } },
      { id: 5, properties: { name: 'Cansojong' } },
    ] }),
  },
}));
jest.mock('../api/hazardsApi', () => ({ hazardsApi: { types: () => Promise.resolve([{ id: 3, name: 'Fire' }]) } }));

beforeAll(() => { global.IS_REACT_ACT_ENVIRONMENT = true; });
beforeEach(() => {
  jest.clearAllMocks();
  historyApi.list.mockResolvedValue([]);
  historyApi.area.mockResolvedValue({
    count: 21, unplaced: 16, puroks: [{ id: 7, name: 'Purok Sambag', parent: 'Sitio Laray', count: 2, level: 'Green' }],
  });
});

async function render() {
  const el = document.createElement('div');
  document.body.appendChild(el);
  await act(async () => {
    createRoot(el).render(<MemoryRouter><HistoricalData /></MemoryRouter>);
  });
  return el;
}
const field = (el, label) => [...el.querySelectorAll('label.db-field')]
  .find((l) => l.firstChild?.textContent?.trim() === label)?.querySelector('select') || null;
async function choose(select, value) {
  await act(async () => {
    select.value = value;
    select.dispatchEvent(new Event('change', { bubbles: true }));
  });
}
const lastListParams = () => historyApi.list.mock.calls[historyApi.list.mock.calls.length - 1][0];

test('the Purok dropdown appears once a barangay is picked, with counts', async () => {
  const el = await render();
  expect(field(el, 'Purok')).toBeNull();
  await choose(field(el, 'Barangay'), '19');
  expect(historyApi.area).toHaveBeenCalledWith({ barangay: '19', period: 'all' });
  expect([...field(el, 'Purok').options].map((o) => o.textContent))
    .toEqual(['All puroks (21)', 'Purok Sambag (2)', 'Purok not recorded (16)']);
});

test('picking a purok filters the list, and a new barangay resets it', async () => {
  const el = await render();
  await choose(field(el, 'Barangay'), '19');
  await choose(field(el, 'Purok'), '7');
  expect(lastListParams()).toEqual(expect.objectContaining({ barangay: '19', purok: '7' }));
  await choose(field(el, 'Barangay'), '5');
  expect(field(el, 'Purok').value).toBe('');
  expect(lastListParams()).toEqual({ barangay: '5' });
});

test('no dropdown when the counts fail to load', async () => {
  historyApi.area.mockRejectedValue(new Error('down'));
  const el = await render();
  await choose(field(el, 'Barangay'), '19');
  expect(field(el, 'Purok')).toBeNull();
});
