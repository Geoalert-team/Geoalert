import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import HistoryImport from './HistoryImport';
import { historyApi } from '../../api/historyApi';

jest.mock('../../api/historyApi', () => ({ historyApi: { importFile: jest.fn() } }));

const CHECK = {
  kind: 'fire', kind_label: 'BFP fire log', read: 5, new: 2, already: 2, linked: 1, barangay_only: 1,
  replaced: 0, problems: [{ label: 'Outside Talisay City', rows: ['row 9'] }],
  unlinked: [{ barangay: 'Dos Hermanas', place: 'Purok Mahogany', count: 1, close: ['Purok Mahugany'] }],
  to_check: [], saved: false,
};

beforeAll(() => { global.IS_REACT_ACT_ENVIRONMENT = true; });
beforeEach(() => jest.clearAllMocks());

async function render(props = {}) {
  const el = document.createElement('div');
  document.body.appendChild(el);
  await act(async () => { createRoot(el).render(<HistoryImport onClose={() => {}} {...props} />); });
  return el;
}
const button = (el, text) => [...el.querySelectorAll('button')].find((b) => b.textContent.trim().startsWith(text));

async function choose(el, file) {
  const input = el.querySelector('input[type="file"]');
  Object.defineProperty(input, 'files', { value: [file], configurable: true });
  await act(async () => { input.dispatchEvent(new Event('change', { bubbles: true })); });
}

test('choosing a file checks it, and Import sends the same file to be saved', async () => {
  historyApi.importFile.mockResolvedValueOnce(CHECK).mockResolvedValueOnce({ ...CHECK, saved: true });
  const onImported = jest.fn();
  const el = await render({ onImported });
  const file = new File(['x'], 'bfp.xlsx');
  await choose(el, file);

  expect(historyApi.importFile).toHaveBeenCalledWith(file, { save: false, includeWarnings: false });
  expect(el.textContent).toContain('BFP fire log · 5 rows read');
  expect(el.textContent).toContain('2 new records to add');
  expect(el.textContent).toContain('Outside Talisay City (1), left out');
  expect(el.textContent).toContain('Dos Hermanas: Purok Mahogany (1 fire) · close: Purok Mahugany');

  await act(async () => { button(el, 'Import 2 records').click(); });
  expect(historyApi.importFile).toHaveBeenLastCalledWith(file, { save: true, includeWarnings: false });
  expect(onImported).toHaveBeenCalledWith(expect.objectContaining({ new: 2, saved: true }));
  expect(el.textContent).toContain('Imported 2 records from the bfp fire log.');
});

test('the flood log offers its warnings, and asking for them checks again', async () => {
  historyApi.importFile.mockResolvedValue({ ...CHECK, kind: 'flood_landslide', kind_label: 'Flood and landslide log' });
  const el = await render();
  const file = new File(['x'], 'floods.xlsx');
  await choose(el, file);
  const box = el.querySelector('.db-import-check input[type="checkbox"]');
  await act(async () => { box.click(); });
  expect(historyApi.importFile).toHaveBeenLastCalledWith(file, { save: false, includeWarnings: true });
});

test('a file the server refuses says why, and nothing can be imported', async () => {
  historyApi.importFile.mockRejectedValue(Object.assign(new Error('Bad request'),
    { data: { file: 'This is not an Excel workbook (.xlsx).' } }));
  const el = await render();
  await choose(el, new File(['x'], 'notes.xlsx'));
  expect(el.querySelector('[role="alert"]').textContent).toBe('This is not an Excel workbook (.xlsx).');
  expect(button(el, 'Import').disabled).toBe(true);
});

test('nothing new means nothing to import', async () => {
  historyApi.importFile.mockResolvedValue({ ...CHECK, new: 0, already: 4, problems: [], unlinked: [] });
  const el = await render();
  await choose(el, new File(['x'], 'bfp.xlsx'));
  expect(el.textContent).toContain('Nothing new to add');
  expect(button(el, 'Import').disabled).toBe(true);
});
