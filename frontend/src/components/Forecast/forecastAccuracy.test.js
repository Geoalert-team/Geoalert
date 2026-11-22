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

const NOT_TRAINED = 'The fire model has not been trained yet.';
// GET /api/history/forecast/accuracy/ before train_fire_model has run (backend views.fire_accuracy_entry)
const untrained = { hazard: 'Fire', kind: 'fire_purok', status: 'unavailable', reason: NOT_TRAINED };

test('an untrained fire model says so with its reason', async () => {
  historyApi.forecastAccuracy.mockResolvedValue({ hazards: [untrained] });
  const el = await render();
  expect(el.textContent).toContain('Fire: unavailable');
  expect(el.textContent).toContain(NOT_TRAINED);
  expect(el.querySelectorAll('table')).toHaveLength(0);
});

test('flood and landslide are named as being rebuilt', async () => {
  historyApi.forecastAccuracy.mockResolvedValue({ hazards: [untrained] });
  const el = await render();
  expect(el.textContent).toContain('Flood and landslide predictions are being rebuilt.');
});

test('no rain credit, combined note or counting benchmark wording any more', async () => {
  historyApi.forecastAccuracy.mockResolvedValue({ hazards: [untrained], combined_note: 'Built from the three tested models; not tested on its own.' });
  const el = await render();
  expect(el.textContent).not.toContain('NASA POWER');
  expect(el.textContent).not.toContain('Built from the three tested models');
  expect(el.textContent).not.toContain('Every hazard always uses its model');
});

test('nothing to test says so', async () => {
  historyApi.forecastAccuracy.mockResolvedValue({ hazards: [] });
  expect((await render()).textContent).toContain('No real records to test a model on yet.');
});

test('it says so when it cannot load', async () => {
  historyApi.forecastAccuracy.mockRejectedValue(new Error('down'));
  expect((await render()).textContent).toContain('The accuracy check could not be loaded right now.');
});
