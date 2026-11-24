import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { MemoryRouter } from 'react-router-dom';
import TrendAnalysis from '../TrendAnalysis';
import { reportsApi } from '../../api/reportApi';
import { downloadCsv } from '../../utils/csv';
import { TRENDS } from './trendFixture';

jest.mock('../../components/Navbar/PublicNavbar', () => () => null);
jest.mock('../../api/reportApi', () => ({
  reportsApi: { trends: jest.fn(), trendPatterns: jest.fn(), trendPlaces: jest.fn(), printed: jest.fn() },
}));
jest.mock('../../api/hazardsApi', () => ({ hazardsApi: { types: () => Promise.resolve([{ id: 2, name: 'Flood' }]) } }));
jest.mock('../../api/barangaysApi', () => ({
  barangaysApi: { list: () => Promise.resolve({ features: [{ id: 7, properties: { name: 'Lagtang' }, geometry: null }] }) },
}));
jest.mock('../../utils/csv', () => ({ ...jest.requireActual('../../utils/csv'), downloadCsv: jest.fn() }));
// Canvas charts and the Leaflet map are stand-ins that show what they were given
jest.mock('../../components/Charts/StackedBars', () => (p) => (
  <div data-chart="stacked">{p.labels.join('|')} / {p.datasets.map((d) => d.label).join('|')}</div>
));
jest.mock('./PlacesMap', () => (p) => <div data-chart="map">{p.rows.length} barangays</div>);

beforeAll(() => { global.IS_REACT_ACT_ENVIRONMENT = true; });

const PATTERNS = {
  range: { from: '2021-01-01', to: '2026-11-24', all_records: true, complete_years: [2021, 2022, 2023, 2024, 2025] },
  filters: { hazard_type: null, barangay: null },
  hazards: [
    { hazard: 'Fire', first: '2023-01-04', last: '2026-11-02', years: [{ year: 2023, count: 50 }, { year: 2024, count: 68 },
      { year: 2025, count: 55 }], complete_years: 3, verdict: 'too_few_years', slope: 2.5, p: 0.6,
    change: { latest: 55, earlier_mean: 59, pct: -7 }, so_far: { year: 2026, count: 48, through: '2026-11-24' },
    quiet_since: null, sentence: 'technical' },
    { hazard: 'Flood', first: '2021-07-10', last: '2026-09-01', years: [2021, 2022, 2023, 2024, 2025].map((y, i) => ({
      year: y, count: [9, 7, 5, 3, 1][i] })), complete_years: 5, verdict: 'decreasing', slope: -2, p: 0.03,
    change: { latest: 1, earlier_mean: 6, pct: -83 }, so_far: null, quiet_since: null, sentence: 'technical' },
    { hazard: 'Landslide', first: '2021-07-09', last: '2022-08-01', years: [2021, 2022, 2023, 2024, 2025].map((y, i) => ({
      year: y, count: [2, 1, 0, 0, 0][i] })), complete_years: 5, verdict: 'too_few_years', slope: 0, p: 1,
    change: { latest: 1, earlier_mean: 2, pct: -50 }, so_far: null, quiet_since: 2022, sentence: 'technical' },
  ],
  unusual_months: [{ hazard: 'Fire', year: 2025, month: 4, label: 'Apr 2025', count: 14, baseline_mean: 5.5,
    baseline_min: 3, baseline_max: 8, baseline_years: 3 }],
};

const PLACES = {
  range: { from: '2021-01-01', to: '2026-11-24', all_records: true },
  filters: { hazard_type: null, barangay: null },
  years: [2021, 2022, 2023, 2024, 2025, 2026].map((y) => ({ year: y, complete: y < 2026 })),
  barangays: [
    { id: 7, name: 'Lagtang', area_km2: 2.5, total: 15, per_km2: 6, years: [1, 2, 3, 4, 5, 0], years_with_events: 5,
      recurrence: 'every_year', change: { latest: 5, earlier_mean: 2.5, pct: 100 } },
    { id: 3, name: 'Biasong', area_km2: null, total: 0, per_km2: null, years: [0, 0, 0, 0, 0, 0], years_with_events: 0,
      recurrence: 'none', change: { latest: 0, earlier_mean: 0, pct: null } },
  ],
  unspecified: { total: 20 },
  selected: null,
};

async function render(url = '/app/trends') {
  const el = document.createElement('div');
  document.body.appendChild(el);
  await act(async () => {
    createRoot(el).render(
      <MemoryRouter initialEntries={[url]} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <TrendAnalysis />
      </MemoryRouter>,
    );
  });
  return el;
}

const section = (el, title) => [...el.querySelectorAll('section.ra-band')]
  .find((s) => s.querySelector('h2')?.textContent === title);
const button = (root, text) => [...root.querySelectorAll('button')].find((b) => b.textContent === text);
// What a reader sees without opening "How we worked this out"
const plainText = (root) => {
  const copy = root.cloneNode(true);
  copy.querySelectorAll('details').forEach((d) => d.remove());
  return copy.textContent;
};

beforeEach(() => {
  window.print = jest.fn();
  reportsApi.trends.mockResolvedValue(TRENDS);
  reportsApi.trendPatterns.mockResolvedValue(PATTERNS);
  reportsApi.trendPlaces.mockResolvedValue(PLACES);
  reportsApi.printed.mockResolvedValue({ logged: true });
});

test('four plain sections, all records by default, no statistics jargon on view', async () => {
  const el = await render();
  expect(el.querySelector('h1').textContent).toBe('Trend Analysis');
  expect([...el.querySelectorAll('section.ra-band > .ra-band-head h2')].map((h) => h.textContent))
    .toEqual(['At a glance', 'Year by year', 'Busiest months', 'Where it happens']);
  expect(reportsApi.trendPatterns).toHaveBeenCalledWith({ date_to: expect.any(String) });
  const seen = plainText(el.querySelector('.ta-body'));
  ['Mann', 'p =', 'Sen', 'standard deviation', 'per km²'].forEach((word) => expect(seen).not.toContain(word));
});

test('at a glance: a plain word per hazard, never a direction without enough years', async () => {
  const el = await render();
  const cards = [...section(el, 'At a glance').querySelectorAll('.ta-hazard')];
  expect(cards.map((c) => c.querySelector('.ta-verdict').textContent))
    .toEqual(['Not enough years yet', 'Going down', 'Not enough years yet']);
  expect(cards[0].textContent).not.toMatch(/Going up|Going down|rising|falling/i);
  expect(cards[0].textContent).toContain('55 events in 2025');
  expect(cards[0].textContent).toContain('7% fewer than the years before');
  expect(cards[0].textContent).toContain('2026 so far: 48');
  expect(cards[0].textContent).toContain('We need at least 5 full years');
  expect(cards[2].textContent).toContain('No records since 2022');
});

test('months that stood out, in words', async () => {
  const el = await render();
  expect(section(el, 'At a glance').textContent).toContain('April 2025: 14 fire events. April usually has 3 to 8.');
});

test('year by year: by year at first, by month on request, part periods labelled', async () => {
  const partial = { ...TRENDS, series: [{ ...TRENDS.series[0], partial: true }, TRENDS.series[1]] };
  reportsApi.trends.mockResolvedValue(partial);
  const el = await render();
  expect(reportsApi.trends).toHaveBeenCalledWith(expect.objectContaining({ granularity: 'year' }));
  const years = section(el, 'Year by year');
  expect(years.querySelector('[data-chart="stacked"]').textContent).toContain('Dec 2025 (part)|Jan 2026');
  await act(async () => { button(years, 'By month').click(); });
  expect(reportsApi.trends).toHaveBeenLastCalledWith(expect.objectContaining({ granularity: 'month' }));
  expect(reportsApi.trendPatterns).toHaveBeenCalledTimes(1); // the step changes this chart only
});

test('busiest months: the peak in words and the rainfall limit said plainly', async () => {
  const el = await render();
  const months = section(el, 'Busiest months');
  expect(months.textContent).toContain('Fire: most often in January');
  expect(months.textContent).toContain('GeoAlert has no rainfall records');
});

test('where it happens: the map and a short table in words', async () => {
  const el = await render();
  const where = section(el, 'Where it happens');
  expect(where.querySelector('[data-chart="map"]').textContent).toBe('2 barangays');
  const rows = [...where.querySelectorAll('tbody tr')].map((r) => r.textContent);
  expect(rows[0]).toContain('Lagtang');
  expect(rows[0]).toContain('Every year');
  expect(rows[0]).toContain('Fire'); // most common, from the hazard mix
  expect(where.textContent).toContain('20 records have no barangay');
});

test('export is logged first with the loaded answer\'s criteria, then the CSV of what is on screen', async () => {
  const el = await render();
  await act(async () => { el.querySelector('.an-export > button').click(); });
  await act(async () => { button(el, 'Download CSV').click(); });
  expect(reportsApi.printed).toHaveBeenCalledWith('analytics', expect.stringMatching(/^date_from=2025-12-01 date_to=2026-11-24/), 'csv');
  expect(reportsApi.printed.mock.invocationCallOrder[0]).toBeLessThan(downloadCsv.mock.invocationCallOrder[0]);
  const csv = downloadCsv.mock.calls[0][1];
  ['At a glance', 'Months that stood out', 'Year by year', 'Busiest months', 'Where it happens', 'Not enough years yet']
    .forEach((t) => expect(csv).toContain(t));
});
