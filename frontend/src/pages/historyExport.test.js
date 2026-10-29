import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { MemoryRouter } from 'react-router-dom';
import HistoricalData from './HistoricalData';
import { exportFilename } from '../components/History/HistoryExport';
import { historyApi } from '../api/historyApi';
import { useAuth } from '../context/AuthContext';
import { downloadBlob } from '../utils/csv';

jest.mock('../components/Navbar/PublicNavbar', () => () => null);
jest.mock('../context/AuthContext', () => ({ useAuth: jest.fn() }));
jest.mock('../utils/csv', () => ({
  ...jest.requireActual('../utils/csv'),
  downloadBlob: jest.fn(),
}));
jest.mock('../api/historyApi', () => ({
  historyApi: { list: jest.fn(), area: jest.fn(), detail: jest.fn(), export: jest.fn() },
}));
jest.mock('../api/barangaysApi', () => ({
  barangaysApi: { list: () => Promise.resolve({ features: [{ id: 19, properties: { name: 'San Roque' } }] }) },
}));
jest.mock('../api/hazardsApi', () => ({
  hazardsApi: {
    types: () => Promise.resolve([{ id: 1, name: 'Flood' }, { id: 2, name: 'Fire' }, { id: 3, name: 'Landslide' }]),
  },
}));

const STAFF = { canPublish: true, user: { role: { name: 'DRRMO_Officer' } } };

beforeAll(() => { global.IS_REACT_ACT_ENVIRONMENT = true; });
beforeEach(() => {
  jest.clearAllMocks();
  useAuth.mockReturnValue(STAFF);
  historyApi.list.mockResolvedValue([]);
  historyApi.area.mockResolvedValue({ count: 0, unplaced: 0, puroks: [] });
  historyApi.export.mockResolvedValue(new Blob(['x']));
});

async function render() {
  const el = document.createElement('div');
  document.body.appendChild(el);
  await act(async () => {
    createRoot(el).render(<MemoryRouter><HistoricalData /></MemoryRouter>);
  });
  return el;
}
const button = (el, text) => [...el.querySelectorAll('button')].find((b) => b.textContent.trim() === text);
const check = (el, name) => [...el.querySelectorAll('.db-history-export label')]
  .find((l) => l.textContent.trim() === name).querySelector('input');
async function click(node) {
  await act(async () => { node.click(); });
}

test('the file is named after the types picked and the day', () => {
  const day = new Date(2026, 9, 29);
  expect(exportFilename(['Flood', 'Fire', 'Landslide'], true, 'xlsx', day)).toBe('history-2026-10-29.xlsx');
  expect(exportFilename(['Fire', 'Flood'], false, 'csv', day)).toBe('history-fire-flood-2026-10-29.csv');
});

test('only DRRMO staff see Export', async () => {
  useAuth.mockReturnValue({ canPublish: false, user: null });
  expect(button(await render(), 'Export')).toBeUndefined();
});

test('with every type ticked, the file asks for every type with the page filters', async () => {
  const el = await render();
  await act(async () => {
    const from = el.querySelector('input[type="date"]');
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(from, '2024-01-01');
    from.dispatchEvent(new Event('input', { bubbles: true }));
  });
  await click(button(el, 'Export'));
  expect(['Flood', 'Fire', 'Landslide'].map((n) => check(el, n).checked)).toEqual([true, true, true]);

  await click(button(el, 'Download'));
  expect(historyApi.export).toHaveBeenCalledWith({ date_from: '2024-01-01', file: 'xlsx' });
  expect(downloadBlob).toHaveBeenCalledWith(expect.stringMatching(/^history-\d{4}-\d\d-\d\d\.xlsx$/), expect.any(Blob));
  expect(el.querySelector('.db-history-export')).toBeNull();
});

test('a hazard tab ticks that type; more can be added, and CSV chosen', async () => {
  const el = await render();
  await click(button(el, 'Fire'));
  await click(button(el, 'Export'));
  expect(['Flood', 'Fire', 'Landslide'].map((n) => check(el, n).checked)).toEqual([false, true, false]);

  await click(check(el, 'Flood'));
  await click(check(el, 'CSV (.csv)'));
  await click(button(el, 'Download'));
  expect(historyApi.export).toHaveBeenCalledWith({ file: 'csv', types: 'Flood,Fire' });
  expect(downloadBlob).toHaveBeenCalledWith(expect.stringMatching(/^history-flood-fire-.*\.csv$/), expect.any(Blob));
});

test('nothing ticked, nothing to download; a failure is shown and the window stays', async () => {
  const el = await render();
  await click(button(el, 'Fire'));
  await click(button(el, 'Export'));
  await click(check(el, 'Fire'));
  expect(button(el, 'Download').disabled).toBe(true);

  await click(check(el, 'Landslide'));
  historyApi.export.mockRejectedValue(new Error('You do not have permission.'));
  await click(button(el, 'Download'));
  expect(el.querySelector('.db-history-export [role="alert"]').textContent).toBe('You do not have permission.');
  expect(downloadBlob).not.toHaveBeenCalled();
});
