import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import ForecastAccuracy from './ForecastAccuracy';
import { historyApi } from '../../api/historyApi';

jest.mock('../../api/historyApi', () => ({ historyApi: { forecastAccuracy: jest.fn() } }));

beforeAll(() => { global.IS_REACT_ACT_ENVIRONMENT = true; });
beforeEach(() => { jest.clearAllMocks(); });

async function render() {
  const el = document.createElement('div');
  await act(async () => { createRoot(el).render(<ForecastAccuracy />); });
  return el;
}

const tested = {
  hazard: 'Fire',
  status: 'in_use',
  train: { start: '2023-01', end: '2025-12', events: 170 },
  test: { start: '2026-01', end: '2026-09', events: 47 },
  model: { deviance: 0.7755, brier: 0.1416, auc: 0.6541, top_share: 0.4681 },
  counting: { deviance: 1.1526, brier: 0.1798, auc: 0.6098, top_share: 0.4102 },
  levels: [
    { level: 'High', rows: 49, events: 19, chance: 0.309, happened: 0.286 },
    { level: 'Moderate', rows: 79, events: 20, chance: 0.199, happened: 0.203 },
    { level: 'Low', rows: 70, events: 8, chance: 0.102, happened: 0.086 },
  ],
};

const cells = (table) => [...table.querySelectorAll('tbody tr')].map((tr) => [...tr.children].map((td) => td.textContent));

test('a model in use shows what it trained on, what it was tested on and how it did', async () => {
  historyApi.forecastAccuracy.mockResolvedValue({ hazards: [tested] });
  const el = await render();
  expect(el.textContent).toContain('Fire: the model is in use');
  expect(el.textContent).toContain('Trained on Jan 2023 to Dec 2025 (170 events), tested on Jan 2026 to Sep 2026 (47 events it never saw)');
  const [scores, levels] = el.querySelectorAll('table');
  expect(cells(scores)).toEqual([
    ['Error in the chance (Brier, lower is better)', '0.142', '0.180'],
    ['Events in its top 5 barangays each month', '47%', '41%'],
    ['Ranking skill (AUC, 0.5 is guessing)', '0.65', '0.61'],
  ]);
  expect(cells(levels)[0]).toEqual(['High', '49', '31%', '29%', '19']);
});

test('a model that lost says it stays on counting, with the figures', async () => {
  historyApi.forecastAccuracy.mockResolvedValue({ hazards: [{ ...tested, status: 'not_better' }] });
  const el = await render();
  expect(el.textContent).toContain('Fire: stays on counting');
  expect(el.textContent).toContain('did not beat counting');
  expect(el.querySelectorAll('table')).toHaveLength(2);
});

test('too few records says so and shows no scores', async () => {
  historyApi.forecastAccuracy.mockResolvedValue({
    hazards: [{ hazard: 'Flood', status: 'too_few_records', train: { start: '2023-01', end: '2025-12', events: 12 }, test: { start: '2026-01', end: '2026-09', events: 3 } }],
  });
  const el = await render();
  expect(el.textContent).toContain('Flood: stays on counting');
  expect(el.textContent).toContain('too few records');
  expect(el.querySelector('table')).toBeNull();
});

test('a level with no barangay-months shows a dash, not NaN', async () => {
  const levels = tested.levels.map((l) => (l.level === 'High' ? { ...l, rows: 0, events: 0, chance: null, happened: null } : l));
  historyApi.forecastAccuracy.mockResolvedValue({ hazards: [{ ...tested, levels }] });
  const el = await render();
  expect(cells(el.querySelectorAll('table')[1])[0]).toEqual(['High', '0', '-', '-', '0']);
});

test('nothing to test says so', async () => {
  historyApi.forecastAccuracy.mockResolvedValue({ hazards: [] });
  expect((await render()).textContent).toContain('No real records to test a model on yet.');
});

test('it says so when it cannot load', async () => {
  historyApi.forecastAccuracy.mockRejectedValue(new Error('down'));
  expect((await render()).textContent).toContain('The accuracy check could not be loaded right now.');
});
