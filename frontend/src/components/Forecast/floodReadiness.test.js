import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import FloodReadiness from './FloodReadiness';
import { historyApi } from '../../api/historyApi';

jest.mock('../../api/historyApi', () => ({ historyApi: { forecastReadiness: jest.fn() } }));

beforeAll(() => { global.IS_REACT_ACT_ENVIRONMENT = true; });
beforeEach(() => { jest.clearAllMocks(); });

async function render() {
  const el = document.createElement('div');
  await act(async () => { createRoot(el).render(<FloodReadiness />); });
  return el;
}

// GET /api/history/forecast/readiness/ (backend flood_purok.readiness)
const ready = {
  located_flood_days: 6,
  forecast_days_needed: { min: 20, max: 30 },
  enough_for_forecasting: false,
  flood_map: {
    available: true, reason: null, version: 'noah_fallback@9aba6d331a4b', built_at: '2026-11-24T07:17:00+08:00',
    trained_on: '2017 UP Mananga flood survey', survey_spots: 105,
  },
  since_publishing: { n: 0, review_after: 10, under_review: false },
  own_spots: { n: 7, barangays: 3, needed: 100, barangays_needed: 5, enough: false },
};

test('shows the counts against the thresholds', async () => {
  historyApi.forecastReadiness.mockResolvedValue(ready);
  const el = await render();
  expect(el.querySelector('h2').textContent).toBe('Flood data readiness');
  expect(el.textContent).toContain(
    'Whether there is enough located flood data to improve the flood predictions. It only counts: nothing here '
    + 'changes a prediction.',
  );
  expect(el.textContent).toContain('Located flood days on record: 6. Flood forecasting needs about 20–30.');
  expect(el.textContent).toContain('Not enough located flood days to try flood forecasting yet.');
  expect(el.textContent).toContain('New located floods since the flood map was published: 0. The map is reviewed after 10.');
  expect(el.textContent).toContain(
    'The flood map comes from the 2017 UP Mananga flood survey (105 flood spots), not from these records. Built 2026-11-24.',
  );
});

test('enough days says a rebuild is worth asking for', async () => {
  historyApi.forecastReadiness.mockResolvedValue({ ...ready, located_flood_days: 22, enough_for_forecasting: true });
  const el = await render();
  expect(el.textContent).toContain(
    'There are enough located flood days to consider building a flood forecast. That needs a rebuild by a developer.',
  );
  expect(el.textContent).not.toContain('Not enough located flood days');
});

test('under review is shown', async () => {
  historyApi.forecastReadiness.mockResolvedValue({ ...ready, since_publishing: { n: 11, review_after: 10, under_review: true } });
  const el = await render();
  expect(el.textContent).toContain('Under review: recent floods fall outside the flagged areas');
});

test("shows the model's reason when there is no usable map", async () => {
  historyApi.forecastReadiness.mockResolvedValue({
    ...ready, flood_map: { available: false, reason: 'The flood model has not been trained yet.' }, since_publishing: null,
  });
  const el = await render();
  expect(el.textContent).toContain('The flood model has not been trained yet.');
  expect(el.textContent).toContain('Located flood days on record: 6.');
  expect(el.textContent).not.toContain('New located floods since');
  expect(el.textContent).not.toContain('The flood map comes from');
});

test('no reason and no map says none has been published', async () => {
  historyApi.forecastReadiness.mockResolvedValue({ ...ready, flood_map: { available: false, reason: null }, since_publishing: null });
  const el = await render();
  expect(el.textContent).toContain('No flood map has been published yet.');
});

test('the training line drops what it does not know', async () => {
  historyApi.forecastReadiness.mockResolvedValue({
    ...ready, flood_map: { ...ready.flood_map, survey_spots: null, built_at: null },
  });
  const el = await render();
  expect(el.textContent).toContain('The flood map comes from the 2017 UP Mananga flood survey, not from these records.');
  expect(el.textContent).not.toContain('(');
  expect(el.textContent).not.toContain('Built');
});

test('says so when it cannot load', async () => {
  historyApi.forecastReadiness.mockRejectedValue(new Error('down'));
  const el = await render();
  expect(el.textContent).toContain('The readiness check could not be loaded right now.');
});

test('the spots line', async () => {
  historyApi.forecastReadiness.mockResolvedValue(ready);
  const el = await render();
  expect(el.textContent).toContain('Located flood spots with a map point: 7 of 100, in 3 of 5 barangays.');
});

test('no spots line without own_spots', async () => {
  const old = { ...ready };
  delete old.own_spots;
  historyApi.forecastReadiness.mockResolvedValue(old);
  const el = await render();
  expect(el.textContent).not.toContain('Located flood spots with a map point');
});

test('the own-data training line', async () => {
  historyApi.forecastReadiness.mockResolvedValue({
    ...ready,
    flood_map: {
      ...ready.flood_map, source: 'geoalert', trained_on: "GeoAlert's located flood records",
      survey_spots: undefined, own_spots: 120, built_at: '2027-01-05T03:00:00+08:00',
    },
  });
  const el = await render();
  expect(el.textContent).toContain(
    "The flood map comes from GeoAlert's located flood records (120 flood spots). Built 2027-01-05.",
  );
  expect(el.textContent).not.toContain('not from these records');
});
