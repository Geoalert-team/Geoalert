import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { MemoryRouter } from 'react-router-dom';
import BFPDashboard from './BFPDashboard';

jest.mock('../../components/Navbar/PublicNavbar', () => () => null);
jest.mock('../../components/Resolve/ActiveZonesCard', () => () => null);
jest.mock('../../components/History/RecordDetail', () => () => null);
jest.mock('../../api/hazardsApi', () => ({
  hazardsApi: {
    list: () => Promise.resolve({
      features: [
        { id: 'z1', properties: { hazard_type_name: 'Fire', severity: 'Orange' } },
        { id: 'z2', properties: { hazard_type_name: 'Flood', severity: 'Red' } },
      ],
    }),
  },
}));
jest.mock('../../api/historyApi', () => ({
  historyApi: { page: () => Promise.resolve({ count: 0, results: [] }) },
}));
jest.mock('../../api/reportApi', () => ({
  reportsApi: {
    list: () => Promise.resolve([
      { id: 'r1', status: 'Validated', hazard_zone: 'z1', description: 'House on fire',
        barangay_details: { name: 'Zone 12' }, created_at: '2026-10-29T08:00:00Z', puroks: [], photos: [] },
      { id: 'r2', status: 'Pending', hazard_zone: null, description: 'Smoke behind the market',
        barangay_details: { name: 'Tabunok' }, created_at: '2026-10-29T09:00:00Z', puroks: [], photos: [] },
    ]),
  },
}));

beforeAll(() => { global.IS_REACT_ACT_ENVIRONMENT = true; });

async function render() {
  const el = document.createElement('div');
  document.body.appendChild(el);
  await act(async () => {
    createRoot(el).render(<MemoryRouter><BFPDashboard /></MemoryRouter>);
  });
  return el;
}
const tab = (el, text) => [...el.querySelectorAll('[role="tab"]')].find((b) => b.textContent.startsWith(text));

test('fire reports waiting for DRRMO come first, read-only', async () => {
  const el = await render();
  const metric = [...el.querySelectorAll('.adm-metric')].find((m) => m.textContent.includes('Waiting for DRRMO'));
  expect(metric.querySelector('.adm-metric-value').textContent).toBe('1');
  const active = [...el.querySelectorAll('.adm-metric')].find((m) => m.textContent.includes('Active fires'));
  expect(active.querySelector('.adm-metric-value').textContent).toBe('1');

  const rows = el.querySelectorAll('.drm-report');
  expect(rows).toHaveLength(1);
  expect(rows[0].textContent).toContain('Smoke behind the market');
  expect(el.textContent).not.toMatch(/Validate|Reject/);
});

test('every fire report, newest first, with the map for one that is on it', async () => {
  const el = await render();
  await act(async () => { tab(el, 'All fire reports').click(); });
  const rows = [...el.querySelectorAll('.drm-report')];
  expect(rows.map((r) => r.querySelector('.drm-report-desc').textContent))
    .toEqual(['Smoke behind the market', 'House on fire']);
  expect(rows[1].querySelector('a').getAttribute('href')).toBe('/map?zone=z1');
  expect(rows[0].querySelector('a')).toBeNull();
});
