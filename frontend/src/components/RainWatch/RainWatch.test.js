import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import RainWatchDayPicker from './RainWatchDayPicker';
import RainWatchLegend from './RainWatchLegend';
import RainWatchBanner from './RainWatchBanner';
import { RAIN_WATCH_NOTE, RAIN_WATCH_CREDITS, bannerInfo, withClientStale } from './rainWatchLevels';

beforeAll(() => { global.IS_REACT_ACT_ENVIRONMENT = true; });

const NOW = Date.parse('2026-11-18T15:00:00Z');
const row = (level) => ({ id: 1, name: 'A', flood: { level, reasons: [] }, landslide: null });
const DATA = {
  updated_at: '2026-11-18T12:00:00Z',
  stale: false,
  days: [
    { key: 'today', date: '2026-11-18', less_certain: false, barangays: [row('none')] },
    { key: 'tomorrow', date: '2026-11-19', less_certain: false, barangays: [row('none')] },
    { key: 'day_after', date: '2026-11-20', less_certain: true, barangays: [row('Red')] },
  ],
};
const ALL = new Set(['Flood', 'Landslide']);

async function render(node) {
  const el = document.createElement('div');
  document.body.appendChild(el);
  await act(async () => { createRoot(el).render(node); });
  return el;
}

test('day picker: three pressed-state buttons, the third less certain, and a hint', async () => {
  const onChange = jest.fn();
  const el = await render(<RainWatchDayPicker data={DATA} value="today" onChange={onChange} activeTypes={ALL} />);
  const buttons = [...el.querySelectorAll('.rw-picker button')];
  expect(buttons.map((b) => b.textContent)).toEqual(['Today', 'Tomorrow', 'Fri (less certain)']);
  expect(buttons.map((b) => b.getAttribute('aria-pressed'))).toEqual(['true', 'false', 'false']);
  expect(el.querySelector('.rw-hint').textContent).toBe('Red expected Fri in 1 barangay → see Fri');
  await act(async () => { buttons[1].click(); });
  expect(onChange).toHaveBeenCalledWith('tomorrow');
  await act(async () => { el.querySelector('.rw-hint').click(); });
  expect(onChange).toHaveBeenCalledWith('day_after');
});

test('legend: note, credits and age', async () => {
  const el = await render(<RainWatchLegend data={DATA} now={NOW} />);
  expect(el.textContent).toContain(RAIN_WATCH_NOTE);
  expect(el.textContent).toContain(RAIN_WATCH_CREDITS);
  expect(el.textContent).toContain('Updated 3 h ago');
});

test('legend: stale and no runs', async () => {
  const stale = await render(<RainWatchLegend data={{ ...DATA, stale: true, updated_at: '2026-11-18T02:00:00Z' }} now={NOW} />);
  expect(stale.textContent).toContain('Out of date: last forecast 13 h ago');
  const none = await render(<RainWatchLegend data={{ updated_at: null, stale: true, days: [] }} now={NOW} />);
  expect(none.textContent).toContain('No forecast yet');
});

test('banner names the day and views it', async () => {
  const onView = jest.fn();
  const el = await render(<RainWatchBanner info={bannerInfo(DATA, ALL)} data={DATA} onView={onView} />);
  expect(el.textContent).toBe('Rain watch: Red expected Fri → view');
  await act(async () => { el.querySelector('button').click(); });
  expect(onView).toHaveBeenCalledWith('day_after');
});

test('legend: an answer 13 h old that is not marked stale reads as out of date', async () => {
  const old = withClientStale({ ...DATA, updated_at: '2026-11-18T02:00:00Z' }, NOW);
  const el = await render(<RainWatchLegend data={old} now={NOW} />);
  expect(el.textContent).toContain('Out of date: last forecast 13 h ago');
});

test('F8: a failed request says so; an answer with no runs says No forecast yet', async () => {
  const failed = await render(<RainWatchLegend data={null} failed now={NOW} />);
  expect(failed.textContent).toContain('Rain watch could not be loaded. Trying again.');
  expect(failed.textContent).not.toContain('No forecast yet');
  const none = await render(<RainWatchLegend data={{ updated_at: null, stale: true, days: [] }} failed={false} now={NOW} />);
  expect(none.textContent).toContain('No forecast yet');
  expect(none.textContent).not.toContain('could not be loaded');
});

test('F10: a Yellow row only when the answer contains Yellow', async () => {
  const rows = (el) => [...el.querySelectorAll('.rw-legend li')].map((li) => li.textContent);
  const plain = await render(<RainWatchLegend data={DATA} now={NOW} />);
  expect(rows(plain)).toEqual(['Red', 'Orange', 'No rain watch']);
  const staff = { ...DATA, days: [{ ...DATA.days[0], barangays: [row('Yellow')] }, ...DATA.days.slice(1)] };
  const withYellow = await render(<RainWatchLegend data={staff} now={NOW} />);
  expect(rows(withYellow)).toEqual(['Red', 'Orange', 'Yellow', 'No rain watch']);
});
