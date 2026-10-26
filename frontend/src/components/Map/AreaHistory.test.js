import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import AreaHistory from './AreaHistory';
import { historyApi } from '../../api/historyApi';

jest.mock('../../api/historyApi', () => ({ historyApi: { area: jest.fn() } }));

beforeAll(() => { global.IS_REACT_ACT_ENVIRONMENT = true; });
beforeEach(() => { jest.clearAllMocks(); });

const BARANGAY = { id: 19, name: 'San Roque' };
const T = { years: 5, moderate: 3, extreme: 5 };
const EVENTS = Array.from({ length: 7 }, (_, i) => ({
  id: `e${i}`, date: `2026-03-0${i + 1}T08:00:00Z`, type: 'Fire', alarm_level: '1ST ALARM',
  property_category: 'RESIDENTIAL', property_subcategory: '', structures_affected: 1, puroks: ['Purok Sambag'],
}));
const AREA = {
  count: 21, level: 'Green', thresholds: T, purok: null, unplaced: 16,
  puroks: [{ id: 7, name: 'Purok Sambag', parent: 'Sitio Laray', count: 2, level: 'Green' }],
  events: EVENTS,
};
const SAMBAG = {
  count: 2, level: 'Green', thresholds: T, purok: { id: 7, name: 'Purok Sambag', parent: 'Sitio Laray' },
  unplaced: 0, puroks: [], events: EVENTS.slice(0, 2),
};

async function render(props) {
  const el = document.createElement('div');
  document.body.appendChild(el);
  const root = createRoot(el);
  const all = { barangay: BARANGAY, purokId: null, types: ['Fire'], onPickPurok: jest.fn(), ...props };
  await act(async () => { root.render(<AreaHistory {...all} />); });
  return { el, root, props: all };
}
const button = (el, text) => [...el.querySelectorAll('button')].find((b) => b.textContent.includes(text));
const events = (el) => el.querySelectorAll('.pm-history-list li');

test('the barangay view lists its puroks, the unplaced and five events', async () => {
  historyApi.area.mockResolvedValue(AREA);
  const { el } = await render();
  expect(historyApi.area).toHaveBeenCalledWith({ barangay: 19, types: 'Fire' });
  expect(el.textContent).toContain('21 fires in the last 5 years');
  expect(button(el, 'Purok Sambag').textContent).toContain('2');
  // The level in words, not only its colour
  expect(button(el, 'Purok Sambag').textContent).toContain('Low');
  expect(button(el, 'Purok not recorded').textContent).toContain('16');
  expect(events(el)).toHaveLength(5);
  await act(async () => { button(el, 'Show more').click(); });
  expect(events(el)).toHaveLength(7);
  expect(button(el, 'Show more')).toBeUndefined();
});

test('picking a row calls onPickPurok with its id, and the unplaced row with "none"', async () => {
  historyApi.area.mockResolvedValue(AREA);
  const { el, props } = await render();
  await act(async () => { button(el, 'Purok Sambag').click(); });
  expect(props.onPickPurok).toHaveBeenLastCalledWith(7);
  await act(async () => { button(el, 'Purok not recorded').click(); });
  expect(props.onPickPurok).toHaveBeenLastCalledWith('none');
});

test('the purok view has a way back', async () => {
  historyApi.area.mockResolvedValue(SAMBAG);
  const { el, props } = await render({ purokId: 7 });
  expect(historyApi.area).toHaveBeenCalledWith({ barangay: 19, purok: 7, types: 'Fire' });
  expect(el.querySelector('.pm-area-title').textContent).toContain('Purok Sambag');
  expect(el.querySelector('.pm-area-title').textContent).toContain('Low');
  expect(el.textContent).toContain('2 fires in the last 5 years');
  expect(events(el)).toHaveLength(2);
  await act(async () => { button(el, '‹ San Roque').click(); });
  expect(props.onPickPurok).toHaveBeenLastCalledWith(null);
});

test('a new barangay starts on its whole history', async () => {
  historyApi.area.mockResolvedValue(SAMBAG);
  const { root, props } = await render({ purokId: 7 });
  historyApi.area.mockResolvedValue({ ...AREA, count: 3, puroks: [], unplaced: 3 });
  await act(async () => {
    root.render(<AreaHistory {...props} barangay={{ id: 5, name: 'Cansojong' }} purokId={null} />);
  });
  expect(historyApi.area).toHaveBeenLastCalledWith({ barangay: 5, types: 'Fire' });
});

test('asks for a ticked type when none is', async () => {
  const { el } = await render({ types: [] });
  expect(el.textContent).toContain('Tick a hazard type in Layers to see its history.');
  expect(historyApi.area).not.toHaveBeenCalled();
});

test('a failed load says so and retries', async () => {
  historyApi.area.mockRejectedValueOnce(new Error('down')).mockResolvedValue(AREA);
  const { el } = await render();
  expect(el.textContent).toContain("Past records couldn't be loaded. Try again.");
  await act(async () => { button(el, 'Try again').click(); });
  expect(historyApi.area).toHaveBeenCalledTimes(2);
  expect(el.textContent).toContain('21 fires in the last 5 years');
});
