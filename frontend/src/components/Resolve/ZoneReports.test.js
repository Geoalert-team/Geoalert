import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import ZoneReports from './ZoneReports';
import { reportsApi } from '../../api/reportApi';

jest.mock('../../api/reportApi', () => ({ reportsApi: { forZone: jest.fn() } }));

beforeAll(() => { global.IS_REACT_ACT_ENVIRONMENT = true; });

const REPORT = {
  id: 'r1',
  status: 'Validated',
  hazard_type_details: { name: 'Fire' },
  barangay_details: { name: 'Lawaan I', municipality: 'Talisay City', province: 'Cebu' },
  submitted_by_name: 'Axzyl D. Codera',
  position: 'BDRRM Officer',
  agency: 'BDRRM Committee',
  description: 'Residential fire observed along the main road.',
  created_at: '2026-10-26T05:34:00Z',
  started_at: '2026-10-26T05:20:00Z',
  puroks: [{ id: 444, name: 'Seaview Heights' }],
  photos: [{ id: 'p1', url: 'https://example.test/p1.jpg' }],
  review_note: 'Confirmed by phone',
};

async function render(answer) {
  reportsApi.forZone.mockImplementation(answer);
  const el = document.createElement('div');
  await act(async () => { createRoot(el).render(<ZoneReports zoneId="z1" />); });
  return el;
}
const facts = (el) => Object.fromEntries(
  [...el.querySelectorAll('.db-rz-facts dt')].map((dt) => [dt.textContent, dt.nextElementSibling.textContent]),
);

test("shows the zone's report: what, who, when, where and the photos", async () => {
  const el = await render(() => Promise.resolve([REPORT]));
  expect(reportsApi.forZone).toHaveBeenCalledWith('z1');
  expect(el.querySelector('.db-rz-report-title').textContent).toBe('Fire · Lawaan IValidated');
  expect(el.querySelector('.db-rz-meta').textContent).toMatch(/by Axzyl D\. Codera \(BDRRM Officer, BDRRM Committee\)$/);
  expect(el.querySelector('.db-rz-desc').textContent).toBe(REPORT.description);
  expect(el.querySelector('.db-rz-photos a').getAttribute('href')).toBe('https://example.test/p1.jpg');
  expect(facts(el)).toMatchObject({
    'Purok / Sitio': 'Seaview Heights',
    Where: 'Lawaan I, Talisay City, Cebu',
    'DRRMO note': 'Confirmed by phone',
  });
  expect(facts(el).Started).toBeTruthy();
});

test('several reports are all shown and counted', async () => {
  const el = await render(() => Promise.resolve([REPORT, { ...REPORT, id: 'r2', photos: [], puroks: [] }]));
  expect(el.querySelectorAll('.db-rz-report')).toHaveLength(2);
  expect(el.querySelector('.db-rz-count').textContent).toBe('2 reports');
});

test('a zone published from the office says it has no report', async () => {
  const el = await render(() => Promise.resolve([]));
  expect(el.querySelector('.db-hint').textContent).toMatch(/No barangay report is linked to this zone/);
});

test('a failed load says so and can be tried again', async () => {
  const el = await render(() => Promise.reject(new Error('offline')));
  expect(el.querySelector('.db-error').textContent).toMatch(/Couldn't load the barangay's report/);
  reportsApi.forZone.mockImplementation(() => Promise.resolve([REPORT]));
  await act(async () => { el.querySelector('.db-error button').click(); });
  expect(el.querySelectorAll('.db-rz-report')).toHaveLength(1);
});
