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
  historyApi.eventOptions.mockResolvedValue({
    subcategories: { Flood: ['RIVER OVERFLOW', 'FLASH FLOOD'], Landslide: ['ROAD LANDSLIDE'] },
  });
  reportsApi.forZone.mockResolvedValue([]);
});

async function render(hazardType, onResolved = jest.fn()) {
  const el = document.createElement('div');
  await act(async () => {
    createRoot(el).render(<ResolveHazardForm zoneId="z1" hazardType={hazardType} title="Flood · Mohon" onResolved={onResolved} />);
  });
  return el;
}

// React tracks input values itself; set them the way a typing user would
function type(el, selector, value) {
  const input = el.querySelector(selector);
  const proto = { SELECT: HTMLSelectElement, TEXTAREA: HTMLTextAreaElement }[input.tagName] || HTMLInputElement;
  act(() => {
    Object.getOwnPropertyDescriptor(proto.prototype, 'value').set.call(input, value);
    input.dispatchEvent(new Event(input.tagName === 'SELECT' ? 'change' : 'input', { bubbles: true }));
  });
}
const click = (el, text) => act(() => {
  [...el.querySelectorAll('button')].find((b) => b.textContent === text).click();
});

test('each type lists its own sub categories', async () => {
  const flood = await render('Flood');
  expect(flood.querySelector('#db-ev-category').value).toBe('FLOOD');
  expect([...flood.querySelectorAll('#db-ev-sub option')].map((o) => o.value)).toEqual(['', 'RIVER OVERFLOW', 'FLASH FLOOD']);
  const landslide = await render('Landslide');
  expect(landslide.querySelector('h3').textContent).toBe('Resolve the landslide');
  expect([...landslide.querySelectorAll('#db-ev-sub option')].map((o) => o.value)).toEqual(['', 'ROAD LANDSLIDE']);
});

test('the sub category is required before resolving', async () => {
  const el = await render('Flood');
  click(el, 'Resolve and file');
  expect(el.querySelector('.db-error').textContent).toMatch(/need fixing before the flood/);
  expect([...el.querySelectorAll('.db-bfp-err')].map((e) => e.textContent)).toEqual(['Choose the sub category.']);
  expect(hazardsApi.update).not.toHaveBeenCalled();
});

test('a complete form resolves the zone with the figures, blanks as null', async () => {
  hazardsApi.update.mockResolvedValue({ id: 'z1', status: 'Resolved' });
  const onResolved = jest.fn();
  const el = await render('Flood', onResolved);
  type(el, '#db-ev-sub', 'FLASH FLOOD');
  type(el, '#db-ev-cause', 'Heavy rain');
  type(el, '#db-ev-fatalities', '0');
  type(el, '#db-ev-families_affected', '70');
  type(el, '#db-ev-summary', 'Mud on the wharf road.');
  click(el, 'Resolve and file');
  await act(async () => { click(el, 'Yes, resolve it'); });
  expect(hazardsApi.update).toHaveBeenCalledWith('z1', {
    status: 'Resolved', hazard_subcategory: 'FLASH FLOOD', cause: 'Heavy rain',
    injured: null, fatalities: 0, families_affected: 70, persons_affected: null, summary: 'Mud on the wharf road.',
  });
  expect(onResolved).toHaveBeenCalledWith({ id: 'z1', status: 'Resolved' });
});

test("the server's field errors land on their fields", async () => {
  hazardsApi.update.mockRejectedValue(Object.assign(new Error('Bad request'), {
    data: { persons_affected: ['Enter a whole number, 0 or more.'] },
  }));
  const el = await render('Flood');
  type(el, '#db-ev-sub', 'RIVER OVERFLOW');
  click(el, 'Resolve and file');
  await act(async () => { click(el, 'Yes, resolve it'); });
  expect([...el.querySelectorAll('.db-bfp-err')].map((e) => e.textContent)).toEqual(['Enter a whole number, 0 or more.']);
});
