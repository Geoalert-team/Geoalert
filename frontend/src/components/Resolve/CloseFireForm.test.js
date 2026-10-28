import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import ResolveHazardForm from './ResolveHazardForm';
import { hazardsApi } from '../../api/hazardsApi';
import { historyApi } from '../../api/historyApi';
import { reportsApi } from '../../api/reportApi';

jest.mock('../../api/hazardsApi', () => ({ hazardsApi: { closeFire: jest.fn(), update: jest.fn() } }));
jest.mock('../../api/historyApi', () => ({ historyApi: { bfpOptions: jest.fn(), eventOptions: jest.fn() } }));
jest.mock('../../api/reportApi', () => ({ reportsApi: { forZone: jest.fn() } }));

beforeAll(() => { global.IS_REACT_ACT_ENVIRONMENT = true; });
beforeEach(() => {
  jest.clearAllMocks();
  historyApi.bfpOptions.mockResolvedValue({
    property_types: { RESIDENTIAL: ['SINGLE AND TWO FAMILY DWELLING'], TRANSPORT: ['TRICYCLE', 'TRUCK'] },
    alarm_levels: ['1ST ALARM', '2ND ALARM'],
  });
  historyApi.eventOptions.mockResolvedValue({ subcategories: { Flood: ['RIVER OVERFLOW'] } });
  reportsApi.forZone.mockResolvedValue([]);
});

async function render(hazardType, onResolved = jest.fn()) {
  const el = document.createElement('div');
  await act(async () => {
    createRoot(el).render(<ResolveHazardForm zoneId="z1" hazardType={hazardType} title="Fire · Lawaan I" onResolved={onResolved} />);
  });
  return el;
}

// React tracks input values itself; set them the way a typing user would
function type(el, selector, value) {
  const input = el.querySelector(selector);
  const proto = input.tagName === 'SELECT' ? HTMLSelectElement.prototype : HTMLInputElement.prototype;
  act(() => {
    Object.getOwnPropertyDescriptor(proto, 'value').set.call(input, value);
    input.dispatchEvent(new Event(input.tagName === 'SELECT' ? 'change' : 'input', { bubbles: true }));
  });
}
const click = (el, text) => act(() => {
  [...el.querySelectorAll('button')].find((b) => b.textContent === text).click();
});

test('a fire zone gets the BFP columns G-W; a flood gets the flood and landslide log', async () => {
  const fire = await render('Fire');
  expect(fire.querySelector('h3').textContent).toBe('Close the fire');
  expect([...fire.querySelectorAll('legend')].map((l) => l.textContent)).toEqual(['Injured', 'Fatalities']);
  expect(fire.querySelector('#db-bfp-alarm')).not.toBeNull();
  expect(fire.querySelector('textarea')).toBeNull(); // no "What happened?"
  const flood = await render('Flood');
  expect(flood.querySelector('h3').textContent).toBe('Resolve the flood');
  expect(flood.querySelector('#db-ev-sub')).not.toBeNull();
  expect(flood.querySelector('#db-bfp-alarm')).toBeNull();
});

test('totals add up as counts are typed, and stay blank until then', async () => {
  const el = await render('Fire');
  const totals = () => [...el.querySelectorAll('.db-bfp-total')].map((t) => t.textContent);
  expect(totals()).toEqual(['—', '—', '—', '—']);
  type(el, '#db-bfp-inj-injured_civ_male', '2');
  type(el, '#db-bfp-inj-injured_civ_female', '1');
  expect(totals()).toEqual(['—', '3', '—', '—']);
});

test('alarm and property type are required before closing', async () => {
  const el = await render('Fire');
  click(el, 'Close and file');
  expect(el.querySelector('.db-error').textContent).toMatch(/need fixing/);
  expect([...el.querySelectorAll('.db-bfp-err')].map((e) => e.textContent))
    .toEqual(['Choose the property type.', 'Choose the alarm level.']);
  expect(hazardsApi.closeFire).not.toHaveBeenCalled();
});

test('a complete form closes the fire with the figures, blanks as null', async () => {
  hazardsApi.closeFire.mockResolvedValue({ zone: { id: 'z1', status: 'Resolved' }, record_id: 'h1' });
  const onResolved = jest.fn();
  const el = await render('Fire', onResolved);
  type(el, '#db-bfp-category', 'RESIDENTIAL'); // its one sub category is picked for you
  expect(el.querySelector('#db-bfp-sub').value).toBe('SINGLE AND TWO FAMILY DWELLING');
  type(el, '#db-bfp-alarm', '2ND ALARM');
  type(el, '#db-bfp-damage', '625,000');
  type(el, '#db-bfp-structures', '76');
  type(el, '#db-bfp-fat-fatal_civ_male', '4');
  click(el, 'Close and file');
  await act(async () => { click(el, 'Yes, close it'); });
  expect(hazardsApi.closeFire).toHaveBeenCalledWith('z1', expect.objectContaining({
    property_category: 'RESIDENTIAL', property_subcategory: 'SINGLE AND TWO FAMILY DWELLING',
    alarm_level: '2ND ALARM', damage_cost: 625000, structures_affected: 76,
    fatal_civ_male: 4, injured_ff_male: null,
  }));
  expect(onResolved).toHaveBeenCalledWith({ id: 'z1', status: 'Resolved' });
});
