import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import PredictiveModelsPanel from './PredictiveModels';
import { historyApi } from '../api/historyApi';

jest.mock('../api/historyApi', () => ({
  historyApi: { forecastReadiness: jest.fn(), forecastAccuracy: jest.fn(), forecastUpdates: jest.fn() },
}));

beforeAll(() => { global.IS_REACT_ACT_ENVIRONMENT = true; });

async function render() {
  const el = document.createElement('div');
  await act(async () => { createRoot(el).render(<PredictiveModelsPanel />); });
  return el;
}

test('a failed readiness check leaves Model accuracy working', async () => {
  historyApi.forecastReadiness.mockRejectedValue(new Error('down'));
  historyApi.forecastAccuracy.mockResolvedValue({ hazards: [] });
  historyApi.forecastUpdates.mockResolvedValue({ updates: [] });
  const el = await render();
  expect(el.textContent).toContain('The readiness check could not be loaded right now.');
  expect([...el.querySelectorAll('h2')].map((h) => h.textContent)).toEqual(['Flood data readiness', 'Model updates', 'Model accuracy']);
  expect(el.textContent).toContain('No real records to test a model on yet.'); // the accuracy card loaded
});

test('a failed updates request leaves the other cards working', async () => {
  historyApi.forecastReadiness.mockResolvedValue({
    located_flood_days: 6, forecast_days_needed: { min: 20, max: 30 }, enough_for_forecasting: false,
    flood_map: { available: false, reason: null }, since_publishing: null,
  });
  historyApi.forecastAccuracy.mockResolvedValue({ hazards: [] });
  historyApi.forecastUpdates.mockRejectedValue(new Error('down'));
  const el = await render();
  expect(el.textContent).toContain('Model updates could not be loaded right now.');
  expect(el.textContent).toContain('Located flood days on record: 6.');
  expect(el.textContent).toContain('No real records to test a model on yet.');
});
