import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import ReportsAnalytics from '../ReportsAnalytics';
import { reportsApi } from '../../api/reportApi';
import { historyApi } from '../../api/historyApi';
import { downloadCsv } from '../../utils/csv';

jest.mock('../../components/Navbar/PublicNavbar', () => () => null);
jest.mock('../../api/reportApi', () => ({
  reportsApi: { summary: jest.fn(), analytics: jest.fn(), printed: jest.fn() },
}));
jest.mock('../../api/hazardsApi', () => ({ hazardsApi: { types: () => Promise.resolve([{ id: 2, name: 'Flood' }]) } }));
jest.mock('../../api/barangaysApi', () => ({
  barangaysApi: { list: () => Promise.resolve({ features: [{ id: 7, properties: { name: 'Lagtang' } }] }) },
}));
jest.mock('../../utils/csv', () => ({ ...jest.requireActual('../../utils/csv'), downloadCsv: jest.fn() }));
jest.mock('../../components/Charts/CategoryBars', () => (p) => <div>{p.rows.map((r) => `${r.label}:${r.value}`).join('|')}</div>);
jest.mock('../../api/historyApi', () => ({
  historyApi: { forecastAccuracy: jest.fn(), forecastReadiness: jest.fn() },
}));

beforeAll(() => { global.IS_REACT_ACT_ENVIRONMENT = true; });

const SUMMARY = {
  range: { from: '2025-12-01', to: '2026-11-24', all_records: false },
  filters: { hazard_type: null, barangay: { id: 7, name: 'Lagtang' } },
  generated_at: '2026-11-24T08:00:00+08:00', generated_by: 'Officer',
  holdings: {
    archive: [{ hazard: 'Fire', records: 221, first: '2023-01-04', last: '2026-11-02' }],
    zones: { count: 11, first: '2026-11-09' }, alerts: { count: 11, first: '2026-11-09' }, notices: { count: 40 },
    incident_reports: { count: 2, first: '2026-11-10' }, barangays: 22, puroks: 300,
  },
  events: 4,
  impact: {
    deaths: { value: 3, recorded_on: 2, of: 4 }, injured: { value: 3, recorded_on: 2, of: 4 },
    families_affected: { value: null, recorded_on: 0, of: 4 }, persons_affected: { value: null, recorded_on: 0, of: 4 },
    structures_affected: { value: 3, recorded_on: 1, of: 4 }, damage_cost: { value: 50000, recorded_on: 1, of: 4 },
    unsplit_casualties: { value: 2, recorded_on: 1, of: 4 },
  },
  displaced: null,
  by_hazard: [{ hazard: 'Fire', events: 4, deaths: 3, injured: 3, families_affected: null, persons_affected: null,
    structures_affected: 3, damage_cost: 50000 }],
  by_barangay: [{ id: 7, name: 'Lagtang', events: 3, deaths: 3, injured: 3, families_affected: null,
    persons_affected: null, structures_affected: 3, damage_cost: 50000 },
  { id: null, name: 'Unspecified', events: 1, deaths: null, injured: null, families_affected: null,
    persons_affected: null, structures_affected: null, damage_cost: null }],
  by_purok: [{ id: 1, name: 'Purok 1', events: 2 }],
  severity: [{ severity: 'Red', count: 1 }, { severity: 'Orange', count: 0 }, { severity: 'Green', count: 3 }],
  fire: { property_category: [{ label: 'Residential', count: 3 }], alarm_level: [{ label: '1st Alarm', count: 2 }] },
  flood_landslide: null,
  completeness: [{ key: 'barangay', label: 'Filed under a barangay', count: 3, of: 4 }],
};

function Where() { return <output data-testid="where">{useLocation().pathname + useLocation().search}</output>; }

async function renderAt(url) {
  const el = document.createElement('div');
  document.body.appendChild(el);
  await act(async () => {
    createRoot(el).render(
      <MemoryRouter initialEntries={[url]} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <Routes>
          <Route path="/app/reports" element={<ReportsAnalytics />} />
          <Route path="/app/trends" element={<p>TRENDS PAGE</p>} />
        </Routes>
        <Where />
      </MemoryRouter>,
    );
  });
  return el;
}

const where = (el) => el.querySelector('[data-testid="where"]').textContent;
const tabs = (el) => [...el.querySelectorAll('[role="tab"]')];
const button = (el, text) => [...el.querySelectorAll('button')].find((b) => b.textContent === text);

beforeEach(() => {
  window.print = jest.fn();
  reportsApi.summary.mockResolvedValue(SUMMARY);
  reportsApi.analytics.mockResolvedValue({ range: { from: '2025-12-01', to: '2026-11-24' }, kpis: {}, zones_by_status: {},
    zones_by_type: [], zones_by_severity: [], barangays: [], hazard_type: null, barangay: null });
  reportsApi.printed.mockResolvedValue({ logged: true });
  historyApi.forecastAccuracy.mockResolvedValue({ hazards: [
    { hazard: 'Fire', status: 'in_use', model: { family: 'logistic_regression' },
      trained: { start: '2023-01', end: '2026-10', fires: 195 } },
  ] });
  historyApi.forecastReadiness.mockResolvedValue({
    flood_map: { available: true, source: 'noah' },
    own_spots: { n: 6, barangays: 3, needed: 100, barangays_needed: 5, enough: false },
  });
});

test('three sections; only the open one loads', async () => {
  const el = await renderAt('/app/reports');
  expect(el.querySelector('h1').textContent).toBe('Reports & Analytics');
  expect(tabs(el).map((t) => t.textContent)).toEqual(['Summary', 'Operations', 'Prediction models']);
  expect(reportsApi.summary).toHaveBeenCalledTimes(1);
  expect(reportsApi.summary).toHaveBeenCalledWith({ date_from: '2025-12-01', date_to: expect.any(String) });
  expect(reportsApi.analytics).not.toHaveBeenCalled();
  await act(async () => { tabs(el)[1].click(); });
  expect(reportsApi.analytics).toHaveBeenCalledTimes(1);
  expect(where(el)).toContain('section=operations');
});

test('Apply loads once for the new filters; nothing for unchanged ones', async () => {
  const el = await renderAt('/app/reports');
  expect(button(el, 'Apply').disabled).toBe(true);
  await act(async () => { button(el, '3 months').click(); });
  expect(reportsApi.summary).toHaveBeenCalledTimes(1); // still the first load
  await act(async () => { button(el, 'Apply').click(); });
  expect(reportsApi.summary).toHaveBeenCalledTimes(2);
  expect(where(el)).toContain('period=3m');
});

test('the summary shows impact with how many records carry it, and displaced as not recorded', async () => {
  const el = await renderAt('/app/reports');
  expect(el.textContent).toContain('recorded on 2 of 4 records');
  expect(el.textContent).toContain('Displaced');
  expect(el.textContent).toContain('Not recorded');
  expect(el.textContent).toContain('What GeoAlert holds');
  expect(el.textContent).toContain('Purok 1');
  expect(el.textContent).toContain('Residential');
});

test('export is logged first with the loaded answer\'s criteria', async () => {
  const el = await renderAt('/app/reports');
  await act(async () => { el.querySelector('.an-export > button').click(); });
  await act(async () => { button(el, 'Download CSV').click(); });
  expect(reportsApi.printed).toHaveBeenCalledWith(
    'hazard-summary', 'date_from=2025-12-01 date_to=2026-11-24 barangay=Lagtang hazard_type=all', 'csv',
  );
  expect(reportsApi.printed.mock.invocationCallOrder[0]).toBeLessThan(downloadCsv.mock.invocationCallOrder[0]);
  expect(downloadCsv.mock.calls[0][1]).toContain('Total displaced,Not recorded');
});

test('an operations export names the filters its figures were counted with', async () => {
  reportsApi.analytics.mockResolvedValue({ range: { from: '2025-12-01', to: '2026-11-24' }, kpis: {}, zones_by_status: {},
    zones_by_type: [], zones_by_severity: [], barangays: [], hazard_type: { id: 2, name: 'Flood' },
    barangay: { id: 7, name: 'Lagtang' },
    filters: { hazard_type: { id: 2, name: 'Flood' }, barangay: { id: 7, name: 'Lagtang' } } });
  const el = await renderAt('/app/reports?section=operations&hazard=2&barangay=7');
  expect(el.textContent).toContain('Flood · Lagtang');
  await act(async () => { el.querySelector('#ra-panel-operations .an-export > button').click(); });
  await act(async () => { button(el, 'Print').click(); });
  expect(reportsApi.printed).toHaveBeenCalledWith(
    'response-status', 'date_from=2025-12-01 date_to=2026-11-24 barangay=Lagtang hazard_type=Flood', 'print',
  );
});

test('casualties the BFP gave only as a total are shown as their own figure', async () => {
  const el = await renderAt('/app/reports');
  expect(el.textContent).toContain('Hurt or killed, not split');
});

test('prediction models explains the models, with the ones in use read live, and holds no data cards', async () => {
  const el = await renderAt('/app/reports?section=models');
  const panel = el.querySelector('#ra-panel-models');
  expect(panel.querySelector('h2').textContent).toBe('Prediction models');
  expect([...panel.querySelectorAll('h3')].map((h) => h.textContent)).toEqual([
    'The models in use',
    'Why flood and landslide start from outside data',
    'How a model is trained',
    'When a new model takes over',
    'Where retraining runs and how it goes live',
  ]);
  expect(panel.textContent).toContain('Logistic regression, trained on 195 fires from Jan 2023 to Oct 2026.');
  expect(panel.textContent).toContain("UP NOAH's 25-year flood map");
  expect(panel.textContent).toContain('Learns from outside data for now');
  expect(panel.textContent).toContain('Today: 6 of 100 located flood spots, in 3 of 5 barangays.');
  expect(panel.textContent).toContain('GitHub Actions');
  expect(panel.querySelector('table')).toBeNull();
  expect(reportsApi.summary).not.toHaveBeenCalled();
});

test('a failed check leaves the explanation in place', async () => {
  historyApi.forecastAccuracy.mockRejectedValue(new Error('down'));
  historyApi.forecastReadiness.mockRejectedValue(new Error('down'));
  const el = await renderAt('/app/reports?section=models');
  const panel = el.querySelector('#ra-panel-models');
  expect(panel.textContent).toContain('Not available right now.');
  expect(panel.textContent).toContain('How a model is trained');
});

test('once flood learns from our own records, the page says so', async () => {
  historyApi.forecastReadiness.mockResolvedValue({
    flood_map: { available: true, source: 'geoalert' },
    own_spots: { n: 140, barangays: 7, needed: 100, barangays_needed: 5, enough: true },
  });
  const el = await renderAt('/app/reports?section=models');
  const panel = el.querySelector('#ra-panel-models');
  expect(panel.textContent).toContain("A machine-learning model trained on GeoAlert's own located flood records.");
  expect(panel.textContent).not.toContain('Learns from outside data for now');
  expect(panel.textContent).toContain("In use now: the flood map learns from GeoAlert's own located flood records.");
});

test('old links: Trend Analysis moved to its own page; models land on their section', async () => {
  const trends = await renderAt('/app/reports?tab=analytics&hazard=2');
  expect(where(trends)).toBe('/app/trends?hazard=2');
  const view = await renderAt('/app/reports?view=trends');
  expect(where(view)).toBe('/app/trends');
  const models = await renderAt('/app/reports?tab=models');
  expect(where(models)).toBe('/app/reports?section=models');
  expect(models.textContent).toContain('How a model is trained');
});
