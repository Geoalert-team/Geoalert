import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import ModelUpdates from './ModelUpdates';
import { historyApi } from '../../api/historyApi';

jest.mock('../../api/historyApi', () => ({ historyApi: { forecastUpdates: jest.fn() } }));

beforeAll(() => { global.IS_REACT_ACT_ENVIRONMENT = true; });
beforeEach(() => { jest.clearAllMocks(); });

async function render() {
  const el = document.createElement('div');
  await act(async () => { createRoot(el).render(<ModelUpdates />); });
  return el;
}

const day = (iso) => new Date(iso).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
const updates = [
  { hazard: 'fire', result: 'switched', reason: 'Scored 0.0300 vs 0.0310 on Feb 2026 to Jan 2027', version: 'v2',
    created_at: '2027-02-02T03:00:00+08:00', is_live: true },
  { hazard: 'flood', result: 'kept', reason: 'Too few new spots to test (4 of 10); tries again next January',
    version: 'v1', created_at: '2027-01-05T03:00:00+08:00', is_live: false },
];

test('renders each attempt', async () => {
  historyApi.forecastUpdates.mockResolvedValue({ updates });
  const el = await render();
  expect(el.querySelector('h2').textContent).toBe('Model updates');
  expect(el.textContent).toContain(
    'Each automatic retraining: when it ran, what it decided and why. A new model goes live only when it does at '
    + 'least as well as the one in use.',
  );
  const rows = el.querySelectorAll('tbody tr');
  expect(rows).toHaveLength(2);
  expect(rows[0].textContent).toContain('Fire');
  expect(rows[0].textContent).toContain(day('2027-02-02T03:00:00+08:00'));
  expect(rows[0].textContent).toContain('Scored 0.0300 vs 0.0310 on Feb 2026 to Jan 2027');
  expect(rows[1].textContent).toContain('Flood');
  expect(rows[1].textContent).toContain('Kept current');
  expect(rows[1].textContent).toContain('Too few new spots to test (4 of 10); tries again next January');
});

test('the live row says it is in use', async () => {
  historyApi.forecastUpdates.mockResolvedValue({ updates });
  const el = await render();
  expect(el.querySelectorAll('tbody tr')[0].textContent).toContain('Switched (in use)');
  expect(el.querySelectorAll('tbody tr')[1].textContent).not.toContain('(in use)');
});

test('every result has its label', async () => {
  const mk = (result) => ({
    hazard: 'fire', result, reason: 'r', version: 'v', created_at: '2027-02-02T03:00:00+08:00', is_live: false,
  });
  historyApi.forecastUpdates.mockResolvedValue({ updates: ['not_tried', 'skipped', 'failed'].map(mk) });
  const el = await render();
  const text = [...el.querySelectorAll('tbody tr')].map((r) => r.textContent).join('|');
  expect(text).toContain('Not tried');
  expect(text).toContain('Skipped');
  expect(text).toContain('Failed');
});

test('empty', async () => {
  historyApi.forecastUpdates.mockResolvedValue({ updates: [] });
  const el = await render();
  expect(el.textContent).toContain('No automatic retraining has run yet.');
});

test('loading', async () => {
  historyApi.forecastUpdates.mockReturnValue(new Promise(() => {}));
  const el = await render();
  expect(el.textContent).toContain('Loading model updates…');
});

test('error', async () => {
  historyApi.forecastUpdates.mockRejectedValue(new Error('down'));
  const el = await render();
  expect(el.textContent).toContain('Model updates could not be loaded right now.');
});

test('model updates name landslide rows', async () => {
  historyApi.forecastUpdates.mockResolvedValue({ updates: [{ hazard: 'landslide', result: 'not_tried',
    reason: '2 of 30 located landslide spots, 1 of 3 barangays', created_at: '2027-01-06T03:17:00+08:00', is_live: false }] });
  const el = await render();
  const cells = [...el.querySelectorAll('tbody tr td')].map((td) => td.textContent);
  expect(cells[0]).toBe('Landslide');
  expect(cells[2]).toBe('Not tried');
  expect(cells[3]).toBe('2 of 30 located landslide spots, 1 of 3 barangays');
});
