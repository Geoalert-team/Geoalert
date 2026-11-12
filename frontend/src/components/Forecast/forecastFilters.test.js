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
  expect(el.textContent).toContain('What past years brought, counted from the archive. Not a prediction: the likelihood below comes from the models.');
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
  // The period picker only: what kind of period, and the month
  expect([...el.querySelectorAll('select')].map((s) => s.closest('label').querySelector('span').textContent))
    .toEqual(['Period', 'Month']);
});

const pick = (el, label, value) => act(async () => {
  const field = [...el.querySelectorAll('label')].find((l) => l.textContent.startsWith(label));
  const input = field.querySelector('select, input');
  const setter = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(input), 'value').set;
  setter.call(input, value);
  input.dispatchEvent(new Event('change', { bubbles: true }));
});

test('an exact date asks for the week around it', async () => {
  historyApi.forecast.mockResolvedValue(forecast('Flood'));
  const el = await render(<BarangayLikelihood hazard="Flood" />);
  await pick(el, 'Period', 'date');
  await pick(el, 'Date', '2027-11-15');
  expect(historyApi.forecast).toHaveBeenLastCalledWith({ date: '2027-11-15', hazard_type_name: 'Flood' });
  expect(el.querySelector('th:nth-child(4)').textContent).toBe('On record in past years, week of Nov 15');
});

test('a past month and year shows what happened beside the likelihood', async () => {
  historyApi.forecast.mockResolvedValue({
    ...forecast(''), year: 2024, years: [2021, 2022, 2023], outcome: { complete: true, events: 3 },
    results: [{ ...row(1), actual: 3 }, { ...row(2), actual: 0 }],
  });
  const el = await render(<BarangayLikelihood hazard="Flood" />);
  await pick(el, 'Period', 'monthYear');
  await pick(el, 'Year', '2024');
  expect(historyApi.forecast).toHaveBeenLastCalledWith(expect.objectContaining({ year: 2024 }));
  expect([...el.querySelectorAll('th')].map((th) => th.textContent)).toContain('What happened');
  expect([...el.querySelectorAll('tbody tr')].map((tr) => tr.children[4].textContent)).toEqual(['3 events', 'None']);
  expect(el.textContent).toMatch(/[A-Z][a-z]+ 2024 is over: 3 events happened\./);
  // the figures come from the models, not from counting these years
  expect(el.textContent).not.toContain('2021–2023');
});

test('a period with nothing before it never says there is nothing to estimate from', async () => {
  historyApi.forecast.mockResolvedValue(modelled({ year: 2023, years: [], in_training: true,
    results: [{ ...row(1), hazard_type: 'Fire', method: 'model', probability: 0.36, in_training: true }] }));
  const el = await render(<BarangayLikelihood hazard="Fire" />);
  expect(el.textContent).not.toContain('Nothing on record before');
  expect(el.textContent).toContain('36%');
  expect(el.textContent).toContain('The model learned from this period');
});

test('the dashboard card sends the rest to Analytics, not History', async () => {
  historyApi.forecast.mockResolvedValue(forecast('Flood', 7));
  const el = await render(<BarangayLikelihood compact limit={5} hazard="Flood" />);
  const more = [...el.querySelectorAll('a')].find((a) => a.textContent.includes('2 more'));
  expect(more.textContent).toBe('2 more in Reports › Analytics');
  expect(more.getAttribute('href')).toBe('/app/reports?tab=analytics');
  expect(el.textContent).not.toContain('Historical Data');
});

const modelled = (extra = {}) => ({
  ...forecast('Fire'), model_hazards: ['Fire'], profile_method: 'model',
  results: [{ ...row(1), hazard_type: 'Fire', method: 'model', probability: 0.234 }], ...extra,
});

test('a model row shows its chance beside the level', async () => {
  historyApi.forecast.mockResolvedValue(modelled());
  const el = await render(<BarangayLikelihood hazard="Fire" />);
  const heads = [...el.querySelectorAll('th')].map((th) => th.textContent);
  expect(heads).toContain('Chance');
  expect(el.querySelector('tbody tr').children[heads.indexOf('Chance')].textContent).toBe('23%');
});

test('counting rows get no chance column', async () => {
  historyApi.forecast.mockResolvedValue(forecast('Flood'));
  const el = await render(<BarangayLikelihood hazard="Flood" />);
  expect([...el.querySelectorAll('th')].map((th) => th.textContent)).not.toContain('Chance');
});

test('the method names the model and the hazard types it covers', async () => {
  historyApi.forecast.mockResolvedValue(modelled({ model_hazards: ['Fire', 'Flood', 'Landslide'] }));
  const el = await render(<BarangayLikelihood hazard="Fire" />);
  expect(el.querySelector('.db-method').textContent).toContain('Fire comes from a trained model');
  expect(el.querySelector('.db-method').textContent).not.toContain('no AI');
});

test('the method no longer describes counting, and keeps the cut-offs', async () => {
  historyApi.forecast.mockResolvedValue(modelled());
  const el = await render(<BarangayLikelihood hazard="Fire" />);
  const method = el.querySelector('.db-method').textContent;
  expect(method).not.toContain('counts the years');
  expect(method).not.toContain('plain counting');
  expect(method).toContain('25% or more is High');
});

test('the year chart says what its bars are', async () => {
  historyApi.forecast.mockResolvedValue(modelled());
  const el = await render(<BarangayLikelihood hazard="Fire" />);
  expect(el.querySelector('.fc-profile').textContent).toContain("average barangay's chance");
  historyApi.forecast.mockResolvedValue({ ...forecast('Flood'), profile_method: 'unavailable' });
  await el.rerender(<BarangayLikelihood hazard="Flood" />);
  expect(el.querySelector('.fc-profile').textContent).toContain('The model gives no chart for this period.');
  expect(el.querySelector('.fc-profile').textContent).not.toContain('share of past years');
});

test('a month on the chart is described by its chance, never a count of years', async () => {
  historyApi.forecast.mockResolvedValue(modelled({
    profile: [
      { month: 6, month_name: 'June', level: 'Moderate', probability: 0.206, years_hit: 4, years_considered: 6 },
      { month: 7, month_name: 'July', level: 'None', probability: null },
    ],
  }));
  const el = await render(<BarangayLikelihood hazard="Fire" />);
  expect([...el.querySelectorAll('.fc-months li')].map((li) => li.getAttribute('title')))
    .toEqual(['June: Moderate (21%)', 'July: no figure']);
});

test('short history is never called rough: every level comes from a model', async () => {
  historyApi.forecast.mockResolvedValue(modelled({ limited: true }));
  const el = await render(<BarangayLikelihood hazard="Fire" />);
  expect(el.textContent).not.toContain('levels are rough');
  historyApi.forecast.mockResolvedValue({ ...forecast('Flood'), limited: true });
  await el.rerender(<BarangayLikelihood hazard="Flood" />);
  expect(el.textContent).not.toContain('levels are rough');
});

test('the method says what fire uses when too few fires came before the period', async () => {
  historyApi.forecast.mockResolvedValue(modelled());
  const el = await render(<BarangayLikelihood hazard="Fire" />);
  expect(el.querySelector('.db-method').textContent).toContain(
    'When fewer than 100 fires came before it, the model trained on every record is used, and the table says it learned from that period.',
  );
});

test('the full table points at the History archive for the records', async () => {
  historyApi.forecast.mockResolvedValue(forecast(''));
  const el = await render(<BarangayLikelihood hazard="Flood" />);
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

test('the likelihood table scrolls inside its card on a narrow phone, not the page', async () => {
  historyApi.forecast.mockResolvedValue(allHazards());
  const el = await render(<BarangayLikelihood />);
  expect(el.querySelector('.fc-table').parentElement.classList.contains('fc-table-wrap')).toBe(true);
});

const combinedRow = (i, extra = {}) => ({
  barangay_id: i, barangay: `B${i}`, probability: 0.3, expected_events: 0.35, level: 'High', top_hazard: 'Landslide',
  hazards: [{ hazard_type: 'Fire', probability: 0.08, level: 'Low' }, { hazard_type: 'Flood', probability: 0.031, level: 'Low' },
    { hazard_type: 'Landslide', probability: 0.3, level: 'High' }],
  missing: [], ...extra,
});
const modelRow = (i, hazard, extra = {}) => ({
  ...row(i), hazard_type: hazard, method: 'model', model: 'logistic_regression', probability: 0.031, level: 'Low',
  range: [0.03, 0.41], rain_years: [2021, 2022, 2023], ...extra,
});
const allHazards = (n = 2) => ({
  ...forecast('', n), hazards_included: ['Fire', 'Flood', 'Landslide'], model_hazards: ['Fire', 'Flood', 'Landslide'],
  profile_method: 'model', combined: Array.from({ length: n }, (_, i) => combinedRow(i)),
  results: Array.from({ length: n }, (_, i) => modelRow(i, 'Flood')),
});

test('all hazard types shows the combined table with each hazard', async () => {
  historyApi.forecast.mockResolvedValue(allHazards());
  const el = await render(<BarangayLikelihood />);
  expect([...el.querySelectorAll('th')].map((th) => th.textContent))
    .toEqual(['Barangay', 'All hazards', 'Chance', 'Biggest share', 'Each hazard']);
  const cells = [...el.querySelector('tbody tr').children].map((td) => td.textContent);
  expect(cells).toEqual(['B0', 'High', '30%', 'Landslide', 'Fire 8% · Flood 3% · Landslide 30%']);
});

test('the combined table adds what happened once a period has started', async () => {
  historyApi.forecast.mockResolvedValue({
    ...allHazards(), year: 2024, years: [2021, 2022, 2023], outcome: { complete: true, events: 3 },
    results: [modelRow(0, 'Flood', { actual: 2 }), modelRow(0, 'Fire', { actual: 1 }), modelRow(1, 'Flood', { actual: 0 })],
  });
  const el = await render(<BarangayLikelihood />);
  const heads = [...el.querySelectorAll('th')].map((th) => th.textContent);
  expect(heads[heads.length - 1]).toBe('What happened');
  expect([...el.querySelectorAll('tbody tr')].map((tr) => tr.lastChild.textContent)).toEqual(['3 events', 'None']);
});

test('one hazard shows its range, rain so far and the in-training note', async () => {
  historyApi.forecast.mockResolvedValue({
    ...forecast('Flood'), model_hazards: ['Fire', 'Flood', 'Landslide'], profile_method: 'model',
    results: [
      modelRow(0, 'Flood', { recorded_rain_probability: 0.12, in_training: true }),
      { ...row(1), method: 'unavailable', probability: null, expected_events: null, level: 'None', reason: 'no rain years before this period' },
    ],
  });
  const el = await render(<BarangayLikelihood hazard="Flood" />);
  const heads = [...el.querySelectorAll('th')].map((th) => th.textContent);
  const [first, second] = [...el.querySelectorAll('tbody tr')];
  const chance = heads.indexOf('Chance');
  expect(first.children[chance].textContent).toContain('3%');
  expect(first.children[chance].textContent).toContain('3–41% across past rain years');
  expect(first.children[chance].textContent).toContain('With rain so far: 12%');
  expect(el.textContent).toContain('The model learned from this period; see the accuracy check for results on years it never saw.');
  expect(second.textContent).toContain('Unavailable right now');
  expect(second.textContent).not.toContain('None on record');
  expect(second.textContent).not.toMatch(/\d%/);
  expect(el.querySelector('.db-method').textContent).toContain('logistic regression');
  expect(el.querySelector('.db-method').textContent).not.toContain('counts the years');
});

test('a tiny flood chance reads under 1%, not 0%, and fire is unchanged', async () => {
  historyApi.forecast.mockResolvedValue({
    ...forecast('Flood'), model_hazards: ['Fire', 'Flood', 'Landslide'], profile_method: 'model',
    results: [modelRow(0, 'Flood', { probability: 0.004, recorded_rain_probability: 0.004 })],
  });
  let el = await render(<BarangayLikelihood hazard="Flood" />);
  let heads = [...el.querySelectorAll('th')].map((th) => th.textContent);
  let cell = el.querySelector('tbody tr').children[heads.indexOf('Chance')].textContent;
  expect(cell).toContain('under 1%');
  expect(cell).toContain('With rain so far: under 1%');
  expect(cell).not.toMatch(/(^|[^\d])0%/);

  historyApi.forecast.mockResolvedValue({
    ...forecast('Fire'), model_hazards: ['Fire', 'Flood', 'Landslide'], profile_method: 'model',
    results: [modelRow(0, 'Fire', { probability: 0.004 })],
  });
  el = await render(<BarangayLikelihood hazard="Fire" />);
  heads = [...el.querySelectorAll('th')].map((th) => th.textContent);
  cell = el.querySelector('tbody tr').children[heads.indexOf('Chance')].textContent;
  expect(cell).toContain('0%');
  expect(cell).not.toContain('under 1%');
});

const UNAVAILABLE_FLOOD = 'Unavailable right now in some or all barangays, and left out of their All hazards chance: Flood.';

test('the combined table names an unavailable hazard and says it is left out', async () => {
  const response = {
    ...allHazards(), unavailable_hazards: ['Flood'],
    combined: [combinedRow(0, {
      probability: 0.19, level: 'Moderate', top_hazard: 'Fire', missing: ['Flood'],
      hazards: [{ hazard_type: 'Fire', probability: 0.19, level: 'Moderate' }, { hazard_type: 'Flood', probability: null, level: 'None' },
        { hazard_type: 'Landslide', probability: 0.01, level: 'Low' }],
    }), combinedRow(1)],
  };
  historyApi.forecast.mockResolvedValue(response);
  const el = await render(<BarangayLikelihood />);
  const [first, second] = [...el.querySelectorAll('tbody tr')].map((tr) => [...tr.children].map((td) => td.textContent));
  expect(first).toEqual(['B0', 'Moderate', '19%', 'Fire', 'Fire 19% · Flood unavailable · Landslide 1%']);
  expect(second[4]).toBe('Fire 8% · Flood 3% · Landslide 30%');
  // under the table, before the disclaimer
  const notes = [...el.querySelectorAll('p.fc-note')].map((p) => p.textContent);
  expect(notes).toContain(UNAVAILABLE_FLOOD);
  expect(notes.indexOf(UNAVAILABLE_FLOOD)).toBeLessThan(notes.findIndex((t) => t.startsWith('Fire is estimated from past fires')));
  expect(el.querySelector('.fc-table-wrap').nextElementSibling.textContent).toBe(UNAVAILABLE_FLOOD);
  // and on the dashboard card
  const card = await render(<BarangayLikelihood compact limit={5} />);
  expect([...card.querySelectorAll('p.fc-note')].map((p) => p.textContent)).toContain(UNAVAILABLE_FLOOD);
});

test('no unavailable note when every hazard has its figure', async () => {
  historyApi.forecast.mockResolvedValue({ ...allHazards(), unavailable_hazards: [] });
  const el = await render(<BarangayLikelihood />);
  expect(el.textContent).not.toContain('Unavailable right now');
});

test('a combined row with no chance because its hazards are unavailable says so', async () => {
  historyApi.forecast.mockResolvedValue({
    ...allHazards(), hazards_included: ['Flood', 'Landslide'], unavailable_hazards: ['Flood', 'Landslide'],
    combined: [combinedRow(0, {
      probability: null, expected_events: null, level: 'None', top_hazard: null, missing: ['Flood', 'Landslide'],
      hazards: [{ hazard_type: 'Flood', probability: null, level: 'None' }, { hazard_type: 'Landslide', probability: null, level: 'None' }],
    })],
  });
  const el = await render(<BarangayLikelihood />);
  const row = el.querySelector('tbody tr');
  expect([...row.children].map((td) => td.textContent))
    .toEqual(['B0', 'Unavailable right now', '-', '-', 'Flood unavailable · Landslide unavailable']);
  expect(el.textContent).not.toContain('None on record');
  // the None styling is kept
  expect(row.querySelector('.fc-dot').style.background).toBe('rgb(154, 163, 178)');
  expect(el.textContent).toContain('Unavailable right now in some or all barangays, and left out of their All hazards chance: Flood and Landslide.');
});

// A past period: fire is on counting, so a barangay with no fire on record has Fire in `missing`, and nothing is unavailable
test('no fire on record is left out of the breakdown, never called unavailable', async () => {
  historyApi.forecast.mockResolvedValue({
    ...allHazards(), unavailable_hazards: [],
    combined: [combinedRow(0, {
      probability: 0.32, missing: ['Fire'],
      hazards: [{ hazard_type: 'Fire', probability: null, level: 'None' }, { hazard_type: 'Flood', probability: 0.031, level: 'Low' },
        { hazard_type: 'Landslide', probability: 0.3, level: 'High' }],
    }), combinedRow(1)],
  });
  const el = await render(<BarangayLikelihood />);
  const [first] = [...el.querySelectorAll('tbody tr')].map((tr) => [...tr.children].map((td) => td.textContent));
  expect(first).toEqual(['B0', 'High', '32%', 'Landslide', 'Flood 3% · Landslide 30%']);
  expect(el.textContent).not.toContain('Fire unavailable');
  expect(el.textContent).not.toContain('Unavailable right now');
});

test('a combined row with no chance and no fire on record reads None on record', async () => {
  historyApi.forecast.mockResolvedValue({
    ...allHazards(), hazards_included: ['Fire'], unavailable_hazards: [],
    combined: [combinedRow(0, {
      probability: null, expected_events: null, level: 'None', top_hazard: null, missing: ['Fire'],
      hazards: [{ hazard_type: 'Fire', probability: null, level: 'None' }],
    })],
  });
  const el = await render(<BarangayLikelihood />);
  expect([...el.querySelector('tbody tr').children].map((td) => td.textContent))
    .toEqual(['B0', 'None on record', '-', '-', '-']);
  expect(el.textContent).not.toContain('Unavailable right now');
  expect(el.textContent).not.toContain('Fire unavailable');
});

test('a model month in the year chart says under 1% for a tiny chance, never 0%', async () => {
  historyApi.forecast.mockResolvedValue({
    ...allHazards(),
    profile: [
      { month: 11, month_name: 'November', level: 'Moderate', probability: 0.234 },
      { month: 12, month_name: 'December', level: 'Low', probability: 0.004 },
      { month: 1, month_name: 'January', level: 'Low', probability: 0 },
      { month: 2, month_name: 'February', level: 'Low', probability: 0.004, years_hit: 1, years_considered: 4 },
    ],
  });
  const el = await render(<BarangayLikelihood />);
  expect([...el.querySelectorAll('.fc-months li')].map((li) => li.getAttribute('title'))).toEqual([
    // a month's counting fields, if any were ever sent, are never shown: the chance is
    'November: Moderate (23%)', 'December: Low (under 1%)', 'January: Low (0%)', 'February: Low (under 1%)',
  ]);
});

test('the combined table says under 1% for a tiny chance', async () => {
  historyApi.forecast.mockResolvedValue({ ...allHazards(), combined: [combinedRow(0, { probability: 0.004 })] });
  const el = await render(<BarangayLikelihood />);
  const cells = [...el.querySelector('tbody tr').children].map((td) => td.textContent);
  expect(cells[2]).toBe('under 1%');
});

test('the rain attribution sits under the card with both links', async () => {
  historyApi.forecast.mockResolvedValue(allHazards());
  const el = await render(<BarangayLikelihood />);
  const note = el.querySelector('.fc-attribution');
  expect(note.textContent).toBe('Rain data by Open-Meteo.com (CC BY 4.0), processed into hazard chances by GeoAlert');
  expect([...note.querySelectorAll('a')].map((a) => [a.textContent, a.getAttribute('href')])).toEqual([
    ['Open-Meteo.com', 'https://open-meteo.com/'], ['CC BY 4.0', 'https://creativecommons.org/licenses/by/4.0/'],
  ]);
});

test('fire alone carries no rain attribution', async () => {
  historyApi.forecast.mockResolvedValue(modelled());
  const el = await render(<BarangayLikelihood hazard="Fire" />);
  expect(el.querySelector('.fc-attribution')).toBeNull();
});

test('the dashboard card shows the top 5 combined rows', async () => {
  historyApi.forecast.mockResolvedValue(allHazards(7));
  const el = await render(<BarangayLikelihood compact limit={5} />);
  expect(el.querySelectorAll('tbody tr')).toHaveLength(5);
  const more = [...el.querySelectorAll('a')].find((a) => a.textContent.includes('2 more'));
  expect(more.textContent).toBe('2 more in Reports › Analytics');
});

test('the outlook is titled as history, not prediction', async () => {
  historyApi.list.mockResolvedValue(records);
  const el = await render(<SeasonalOutlook hazardTypeId="" hazardName={null} includeSamples={false} />);
  expect(el.querySelector('h2').textContent).toBe('Seasons on record');
  expect(el.querySelector('.db-card-sub').textContent)
    .toBe('What past years brought, counted from the archive. Not a prediction: the likelihood below comes from the models.');
  expect(el.textContent).not.toContain('Seasonal outlook');
});
