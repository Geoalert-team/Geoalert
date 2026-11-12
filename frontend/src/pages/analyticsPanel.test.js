import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { MemoryRouter } from 'react-router-dom';
import AnalyticsPanel from './Analytics';

// The panel's own wiring is under test; the canvases are not
jest.mock('../components/Charts/CategoryBars', () => () => null);
jest.mock('../components/Analytics/MonthlyMultiples', () => () => null);
jest.mock('../components/Charts/chartTheme', () => ({
  hazardSeriesColor: () => '#000', severitySeriesColor: () => '#000',
}));
jest.mock('../api/reportApi', () => ({ reportsApi: { analytics: jest.fn(), printed: jest.fn() } }));
jest.mock('../api/hazardsApi', () => ({ hazardsApi: { types: () => Promise.resolve([]) } }));
jest.mock('../api/historyApi', () => ({
  historyApi: {
    list: () => Promise.resolve([]),
    forecast: () => Promise.resolve({ results: [], years: [], basis: { records: 0, sample_records: 0 } }),
    forecastAccuracy: () => Promise.resolve({ hazards: [] }),
  },
}));
const { reportsApi } = require('../api/reportApi');

beforeAll(() => { global.IS_REACT_ACT_ENVIRONMENT = true; });

test('the outlook and likelihood load on their own when the figures fail', async () => {
  reportsApi.analytics.mockRejectedValue(new Error('down'));
  const el = document.createElement('div');
  await act(async () => {
    createRoot(el).render(
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}><AnalyticsPanel /></MemoryRouter>,
    );
  });
  expect(el.textContent).toContain('Analytics could not be loaded right now.');
  const headings = [...el.querySelectorAll('h2')].map((h) => h.textContent);
  expect(headings).toEqual(expect.arrayContaining(['Seasons on record', 'Likelihood by barangay', 'Model accuracy']));
  // the likelihood comes from the trained models, not from counting past records
  expect(el.textContent).toContain(
    'How likely each barangay is to be hit in a month, a month and year, or the week of a date, from each hazard’s trained model',
  );
  expect(el.textContent).not.toContain('date, from past records');
});
