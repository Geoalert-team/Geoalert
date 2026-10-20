import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { MemoryRouter } from 'react-router-dom';
import SeasonalOutlook from './SeasonalOutlook';
import BarangayLikelihood from './BarangayLikelihood';
import { historyApi } from '../../api/historyApi';
import { buildRiskOutlook } from '../../utils/riskOutlook';

jest.mock('../../api/historyApi', () => ({
  historyApi: { list: jest.fn(), forecast: jest.fn() },
}));
jest.mock('../../utils/riskOutlook', () => ({ buildRiskOutlook: jest.fn(() => null) }));

beforeAll(() => { global.IS_REACT_ACT_ENVIRONMENT = true; });
beforeEach(() => { jest.clearAllMocks(); });

const records = [{ id: 1, is_sample: true }, { id: 2, is_sample: false }];

const FUTURE = { v7_startTransition: true, v7_relativeSplatPath: true };

async function render(node) {
  const el = document.createElement('div');
  const root = createRoot(el);
  await act(async () => { root.render(<MemoryRouter future={FUTURE}>{node}</MemoryRouter>); });
  el.rerender = (next) => act(async () => { root.render(<MemoryRouter future={FUTURE}>{next}</MemoryRouter>); });
  return el;
}

const row = (i) => ({
  barangay_id: i, barangay: `B${i}`, hazard_type: 'Flood', level: 'Moderate',
  years_hit: 1, years_considered: 4, typical_severity: 'Orange',
});
const forecast = (hazard, n = 2) => ({
  results: Array.from({ length: n }, (_, i) => row(i)), years: [2023, 2024, 2025, 2026],
  basis: { records: 10, sample_records: 0 }, hazard_type: hazard || null,
  profile: [{ month: 11, month_name: 'November', level: 'Moderate', probability: 0.4, years_hit: 1, years_considered: 4 }],
});

test('outlook reads one hazard type and leaves sample records out', async () => {
  historyApi.list.mockResolvedValue(records);
  await render(<SeasonalOutlook hazardTypeId="2" hazardName="Flood" includeSamples={false} />);
  expect(historyApi.list).toHaveBeenCalledWith({ hazard_type: '2' });
  expect(buildRiskOutlook).toHaveBeenLastCalledWith([{ id: 2, is_sample: false }]);
});

test('outlook keeps sample records when asked, and names the scope', async () => {
  historyApi.list.mockResolvedValue(records);
  const el = await render(<SeasonalOutlook hazardTypeId="" hazardName={null} includeSamples />);
  expect(historyApi.list).toHaveBeenCalledWith({});
  expect(buildRiskOutlook).toHaveBeenLastCalledWith(records);
  expect(el.textContent).toContain('From the whole archive for all hazard types. The period above does not apply.');
});

test('outlook says so when it cannot load', async () => {
  historyApi.list.mockRejectedValue(new Error('down'));
  const el = await render(<SeasonalOutlook hazardTypeId="" hazardName={null} includeSamples={false} />);
  expect(el.textContent).toContain('The seasonal outlook could not be loaded right now.');
});

test('likelihood takes its hazard from outside and can leave samples out', async () => {
  historyApi.forecast.mockResolvedValue({ results: [], years: [], basis: { records: 0, sample_records: 0 } });
  const el = await render(<BarangayLikelihood hazard="Flood" excludeSamples />);
  expect(historyApi.forecast).toHaveBeenCalledWith(expect.objectContaining({
    hazard_type_name: 'Flood', exclude_samples: 'true',
  }));
  expect(el.querySelectorAll('select')).toHaveLength(1); // the month picker only
});

test('the dashboard card sends the rest to Analytics, not History', async () => {
  historyApi.forecast.mockResolvedValue(forecast('', 7));
  const el = await render(<BarangayLikelihood compact limit={5} />);
  const more = [...el.querySelectorAll('a')].find((a) => a.textContent.includes('2 more'));
  expect(more.textContent).toBe('2 more in Reports › Analytics');
  expect(more.getAttribute('href')).toBe('/app/reports?tab=analytics');
  expect(el.textContent).not.toContain('Historical Data');
});

test('the full table points at the History archive for the records', async () => {
  historyApi.forecast.mockResolvedValue(forecast(''));
  const el = await render(<BarangayLikelihood />);
  expect(el.textContent).not.toContain('records below');
  expect(el.textContent).toContain('archived records on the History page');
});

test('the year profile keeps the label of the figures it shows while a new type loads', async () => {
  historyApi.forecast.mockResolvedValueOnce(forecast('Flood'));
  const el = await render(<BarangayLikelihood hazard="Flood" />);
  expect(el.querySelector('.fc-profile h3').textContent).toContain(', flood');
  historyApi.forecast.mockReturnValueOnce(new Promise(() => {}));
  await el.rerender(<BarangayLikelihood hazard="Fire" />);
  expect(el.querySelector('.fc-profile h3').textContent).toContain(', flood');
  expect(el.querySelector('.fc-profile h3').textContent).not.toContain('fire');
});

test('the outlook shows loading, not the last type\'s figures, while a new type loads', async () => {
  historyApi.list.mockResolvedValueOnce(records);
  const el = await render(<SeasonalOutlook hazardTypeId="1" hazardName="Flood" includeSamples={false} />);
  expect(el.textContent).toContain('No archived events match');
  historyApi.list.mockReturnValueOnce(new Promise(() => {}));
  await el.rerender(<SeasonalOutlook hazardTypeId="2" hazardName="Fire" includeSamples={false} />);
  expect(el.textContent).toContain('Loading the outlook…');
  expect(el.textContent).not.toContain('No archived events match');
});
