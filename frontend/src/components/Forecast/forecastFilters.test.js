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

// Fire is the only hazard the forecast covers since 2026-11-22
const row = (i) => ({
  barangay_id: i, barangay: `B${i}`, hazard_type: 'Fire', level: 'Moderate',
  years_hit: 1, years_considered: 4, typical_severity: 'Orange',
});
const forecast = (n = 2) => ({
  results: Array.from({ length: n }, (_, i) => row(i)), years: [2023, 2024, 2025, 2026],
  basis: { records: 10, sample_records: 0 }, hazard_type: 'Fire',
  profile: [{ month: 11, month_name: 'November', level: 'Moderate', probability: 0.4, years_hit: 1, years_considered: 4 }],
});
const modelled = (extra = {}) => ({
  ...forecast(), model_hazards: ['Fire'], profile_method: 'model',
  results: [{ ...row(1), method: 'model', probability: 0.234 }], ...extra,
});
const NOT_TRAINED = 'The fire model has not been trained yet.';
const untrained = (n = 2) => ({
  ...forecast(n), unavailable_hazards: ['Fire'], profile_method: 'unavailable',
  basis: { records: 10, sample_records: 0, method: "Fire's prediction model is being rebuilt, so no chances are shown until it is trained. Flood and landslide predictions are being rebuilt too." },
  results: Array.from({ length: n }, (_, i) => ({
    ...row(i), method: 'unavailable', probability: null, expected_events: null, level: 'None', reason: NOT_TRAINED,
  })),
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
  expect(el.textContent).toContain('What past years brought, counted from the archive. Not a prediction: the likelihood below comes from the models.');
});

test('outlook says so when it cannot load', async () => {
  historyApi.list.mockRejectedValue(new Error('down'));
  const el = await render(<SeasonalOutlook hazardTypeId="" hazardName={null} includeSamples={false} />);
  expect(el.textContent).toContain('The seasonal outlook could not be loaded right now.');
});

test('likelihood asks for fire only and can leave samples out', async () => {
  historyApi.forecast.mockResolvedValue({ results: [], years: [], basis: { records: 0, sample_records: 0 } });
  const el = await render(<BarangayLikelihood excludeSamples />);
  expect(historyApi.forecast).toHaveBeenCalledWith(expect.objectContaining({
    hazard_type_name: 'Fire', exclude_samples: 'true',
  }));
  // The period picker only: what kind of period, and the month
  expect([...el.querySelectorAll('select')].map((s) => s.closest('label').querySelector('span').textContent))
    .toEqual(['Period', 'Month']);
});

test('a flood or landslide filter shows the fire-only note and asks for nothing', async () => {
  for (const hazard of ['Flood', 'Landslide']) {
    const el = await render(<BarangayLikelihood hazard={hazard} />);
    expect(el.textContent).toContain('Only fire has a prediction for now.');
    expect(el.querySelector('table')).toBeNull();
  }
  expect(historyApi.forecast).not.toHaveBeenCalled();
});

const pick = (el, label, value) => act(async () => {
  const field = [...el.querySelectorAll('label')].find((l) => l.textContent.startsWith(label));
  const input = field.querySelector('select, input');
  const setter = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(input), 'value').set;
  setter.call(input, value);
  input.dispatchEvent(new Event('change', { bubbles: true }));
});

test('an exact date asks for the week around it', async () => {
  historyApi.forecast.mockResolvedValue(forecast());
  const el = await render(<BarangayLikelihood hazard="Fire" />);
  await pick(el, 'Period', 'date');
  await pick(el, 'Date', '2027-11-15');
  expect(historyApi.forecast).toHaveBeenLastCalledWith({ date: '2027-11-15', hazard_type_name: 'Fire' });
  expect(el.querySelector('th:nth-child(4)').textContent).toBe('On record in past years, week of Nov 15');
});

test('a past month and year shows what happened beside the likelihood', async () => {
  historyApi.forecast.mockResolvedValue({
    ...forecast(), year: 2024, years: [2021, 2022, 2023], outcome: { complete: true, events: 3 },
    results: [{ ...row(1), actual: 3 }, { ...row(2), actual: 0 }],
  });
  const el = await render(<BarangayLikelihood />);
  await pick(el, 'Period', 'monthYear');
  await pick(el, 'Year', '2024');
  expect(historyApi.forecast).toHaveBeenLastCalledWith(expect.objectContaining({ year: 2024 }));
  expect([...el.querySelectorAll('th')].map((th) => th.textContent)).toContain('What happened');
  expect([...el.querySelectorAll('tbody tr')].map((tr) => tr.children[4].textContent)).toEqual(['3 events', 'None']);
  expect(el.textContent).toMatch(/[A-Z][a-z]+ 2024 is over: 3 events happened\./);
  // the figures come from the model, not from counting these years
  expect(el.textContent).not.toContain('2021–2023');
});

test('a period with nothing before it never says there is nothing to estimate from', async () => {
  historyApi.forecast.mockResolvedValue(modelled({ year: 2023, years: [], in_training: true,
    results: [{ ...row(1), method: 'model', probability: 0.36, in_training: true }] }));
  const el = await render(<BarangayLikelihood hazard="Fire" />);
  expect(el.textContent).not.toContain('Nothing on record before');
  expect(el.textContent).toContain('36%');
  expect(el.textContent).toContain('The model learned from this period');
});

test('the dashboard card sends the rest to Analytics, not History', async () => {
  historyApi.forecast.mockResolvedValue(forecast(7));
  const el = await render(<BarangayLikelihood compact limit={5} />);
  expect(el.querySelectorAll('tbody tr')).toHaveLength(5);
  const more = [...el.querySelectorAll('a')].find((a) => a.textContent.includes('2 more'));
  expect(more.textContent).toBe('2 more in Reports › Analytics');
  expect(more.getAttribute('href')).toBe('/app/reports?tab=analytics');
  expect(el.textContent).not.toContain('Historical Data');
});

test('a model row shows its chance beside the level', async () => {
  historyApi.forecast.mockResolvedValue(modelled());
  const el = await render(<BarangayLikelihood hazard="Fire" />);
  const heads = [...el.querySelectorAll('th')].map((th) => th.textContent);
  expect(heads).toContain('Chance');
  expect(el.querySelector('tbody tr').children[heads.indexOf('Chance')].textContent).toBe('23%');
});

test('rows with no method get no chance column', async () => {
  historyApi.forecast.mockResolvedValue(forecast());
  const el = await render(<BarangayLikelihood />);
  expect([...el.querySelectorAll('th')].map((th) => th.textContent)).not.toContain('Chance');
});

test('an untrained fire model shows its reason on each row and names fire under the table', async () => {
  historyApi.forecast.mockResolvedValue(untrained());
  const el = await render(<BarangayLikelihood />);
  const heads = [...el.querySelectorAll('th')].map((th) => th.textContent);
  const first = el.querySelector('tbody tr');
  expect(first.children[heads.indexOf('Likelihood')].textContent).toBe('Unavailable right now');
  expect(first.children[heads.indexOf('Chance')].textContent).toBe(NOT_TRAINED);
  expect(el.textContent).not.toContain('None on record');
  expect([...el.querySelectorAll('p.fc-note')].map((p) => p.textContent))
    .toContain(`Fire is unavailable right now: ${NOT_TRAINED}`);
});

test('the method shows the basis line and keeps the cut-offs', async () => {
  historyApi.forecast.mockResolvedValue(untrained());
  const el = await render(<BarangayLikelihood />);
  const method = el.querySelector('.db-method').textContent;
  expect(method).toContain("Fire's prediction model is being rebuilt");
  expect(method).toContain('25% or more is High');
  expect(method).not.toContain('counts the years');
  expect(method).not.toContain('daily rain');
  expect(method).not.toContain('All hazards');
});

test('the year chart says what its bars are', async () => {
  historyApi.forecast.mockResolvedValue(modelled());
  const el = await render(<BarangayLikelihood hazard="Fire" />);
  expect(el.querySelector('.fc-profile').textContent).toContain("average barangay's chance");
  historyApi.forecast.mockResolvedValue({ ...forecast(), profile_method: 'unavailable' });
  await el.rerender(<BarangayLikelihood hazard="Fire" excludeSamples />);
  expect(el.querySelector('.fc-profile').textContent).toContain('The model gives no chart for this period.');
  expect(el.querySelector('.fc-profile').textContent).not.toContain('share of past years');
});

test('a month on the chart is described by its chance, never a count of years', async () => {
  historyApi.forecast.mockResolvedValue(modelled({
    profile: [
      { month: 6, month_name: 'June', level: 'Moderate', probability: 0.206, years_hit: 4, years_considered: 6 },
      { month: 7, month_name: 'July', level: 'None', probability: null },
      { month: 12, month_name: 'December', level: 'Low', probability: 0.004 },
      { month: 1, month_name: 'January', level: 'Low', probability: 0 },
    ],
  }));
  const el = await render(<BarangayLikelihood hazard="Fire" />);
  expect([...el.querySelectorAll('.fc-months li')].map((li) => li.getAttribute('title')))
    .toEqual(['June: Moderate (21%)', 'July: no figure', 'December: Low (under 1%)', 'January: Low (0%)']);
});

test('short history is never called rough: every level comes from a model', async () => {
  historyApi.forecast.mockResolvedValue(modelled({ limited: true }));
  const el = await render(<BarangayLikelihood hazard="Fire" />);
  expect(el.textContent).not.toContain('levels are rough');
});

test('the full table points at the History archive for the records', async () => {
  historyApi.forecast.mockResolvedValue(forecast());
  const el = await render(<BarangayLikelihood />);
  expect(el.textContent).not.toContain('records below');
  expect(el.textContent).toContain('archived records on the History page');
});

test('the likelihood table scrolls inside its card on a narrow phone, not the page', async () => {
  historyApi.forecast.mockResolvedValue(forecast());
  const el = await render(<BarangayLikelihood />);
  expect(el.querySelector('.fc-table').parentElement.classList.contains('fc-table-wrap')).toBe(true);
});

test('no rain attribution or combined table any more', async () => {
  historyApi.forecast.mockResolvedValue(modelled());
  const el = await render(<BarangayLikelihood />);
  expect(el.querySelector('.fc-attribution')).toBeNull();
  expect(el.textContent).not.toContain('NASA POWER');
  expect([...el.querySelectorAll('th')].map((th) => th.textContent)).not.toContain('All hazards');
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

test('the outlook is titled as history, not prediction', async () => {
  historyApi.list.mockResolvedValue(records);
  const el = await render(<SeasonalOutlook hazardTypeId="" hazardName={null} includeSamples={false} />);
  expect(el.querySelector('h2').textContent).toBe('Seasons on record');
  expect(el.querySelector('.db-card-sub').textContent)
    .toBe('What past years brought, counted from the archive. Not a prediction: the likelihood below comes from the models.');
  expect(el.textContent).not.toContain('Seasonal outlook');
});
