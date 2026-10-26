import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import RecordDetail from './RecordDetail';
import { historyApi } from '../../api/historyApi';
import { reportsApi } from '../../api/reportApi';

jest.mock('../../api/historyApi', () => ({ historyApi: { detail: jest.fn() } }));
jest.mock('../../api/reportApi', () => ({ reportsApi: { forZone: jest.fn() } }));

beforeAll(() => { global.IS_REACT_ACT_ENVIRONMENT = true; });
beforeEach(() => { jest.clearAllMocks(); reportsApi.forZone.mockResolvedValue([]); });

const FIRE = {
  id: 'h1', hazard_zone: 'z1', severity_level: 'Red', is_sample: false,
  hazard_type_detail: { name: 'Fire' },
  barangay_detail: { name: 'Lawaan I', municipality: 'Talisay City', province: 'Cebu' },
  description: 'BFP: RESIDENTIAL – SINGLE AND TWO FAMILY DWELLING, 2ND ALARM',
  occurred_at: '2026-10-26T05:33:00Z', archived_at: '2026-10-26T06:30:00Z',
  location_text: 'ROSEVILLE, BRGY LAWAAN I', puroks: ['Roseville'],
  property_category: 'RESIDENTIAL', property_subcategory: 'SINGLE AND TWO FAMILY DWELLING',
  injured_ff_male: null, injured_ff_female: null, injured_civ_male: 2, injured_civ_female: 1,
  fatal_ff_male: null, fatal_ff_female: null, fatal_civ_male: 4, fatal_civ_female: null,
  damage_cost: '625000.00', structures_affected: 76, alarm_level: '2ND ALARM',
  total_casualties: 7, total_displaced: null,
};

async function render(answer, onClose = jest.fn()) {
  historyApi.detail.mockImplementation(answer);
  const el = document.createElement('div');
  document.body.appendChild(el);
  await act(async () => { createRoot(el).render(<RecordDetail recordId="h1" onClose={onClose} />); });
  return el;
}
const dl = (section) => Object.fromEntries(
  [...section.querySelectorAll('dt')].map((dt) => [dt.textContent, dt.nextElementSibling.textContent]),
);
const section = (el, title) => [...el.querySelectorAll('.db-modal-section')]
  .find((s) => s.querySelector('h3')?.textContent === title);

test('a fire record shows the BFP figures, the place and the barangay report, and no severity', async () => {
  const el = await render(() => Promise.resolve(FIRE));
  expect(historyApi.detail).toHaveBeenCalledWith('h1');
  expect(el.querySelector('h2').textContent).toBe('Fire · Lawaan I');
  expect(dl(section(el, 'When and where'))).toMatchObject({
    Location: 'ROSEVILLE, BRGY LAWAAN I', 'City / Province': 'Talisay City, Cebu',
  });
  expect(dl(section(el, 'BFP fire figures'))).toEqual({
    'Property type': 'RESIDENTIAL – SINGLE AND TWO FAMILY DWELLING',
    Alarm: '2ND ALARM',
    Damage: '₱625,000.00',
    Structures: '76',
  });
  const rows = [...el.querySelectorAll('.db-bfp-table tbody tr')].map((tr) => tr.textContent);
  expect(rows).toEqual(['Firefighter———', 'Civilian213', 'Firefighter———', 'Civilian4—4']);
  expect(dl(section(el, 'Counts'))).toEqual({ Casualties: '7', Displaced: 'not counted' });
  expect(reportsApi.forZone).toHaveBeenCalledWith('z1');
  expect(el.textContent).not.toMatch(/Extreme|Moderate|Low risk/);
});

test('a flood record has no BFP section and no barangay report without a zone', async () => {
  const flood = {
    ...FIRE, hazard_type_detail: { name: 'Flood' }, hazard_zone: null, location_text: '', puroks: [],
    property_category: '', property_subcategory: '', alarm_level: '', damage_cost: null, structures_affected: null,
    injured_civ_male: null, injured_civ_female: null, fatal_civ_male: null, total_casualties: null,
  };
  const el = await render(() => Promise.resolve(flood));
  expect(section(el, 'BFP fire figures')).toBeUndefined();
  expect(dl(section(el, 'When and where')).Location).toBe('Lawaan I');
  expect(dl(section(el, 'Counts')).Casualties).toBe('not counted');
  expect(reportsApi.forZone).not.toHaveBeenCalled();
});

test('Escape and the close button close it; a failed load can be tried again', async () => {
  const onClose = jest.fn();
  const el = await render(() => Promise.reject(new Error('offline')), onClose);
  expect(el.querySelector('.db-error').textContent).toMatch(/Couldn't load this record/);
  act(() => { document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' })); });
  act(() => { el.querySelector('.db-modal-close').click(); });
  expect(onClose).toHaveBeenCalledTimes(2);
  historyApi.detail.mockResolvedValue(FIRE);
  await act(async () => { el.querySelector('.db-error button').click(); });
  expect(el.querySelector('h2').textContent).toBe('Fire · Lawaan I');
});
