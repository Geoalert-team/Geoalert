import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import RainWatchCard from './RainWatchCard';
import { rainWatchApi } from '../../api/rainWatchApi';

jest.mock('../../api/rainWatchApi', () => ({
  rainWatchApi: { get: jest.fn(), createOverride: jest.fn(), cancelOverride: jest.fn() },
}));

beforeAll(() => { global.IS_REACT_ACT_ENVIRONMENT = true; });
beforeEach(() => { jest.clearAllMocks(); });

const P = (level, reasons = []) => ({ level, reasons });
const bar = (id, name, flood, landslide = null) => ({ id, name, flood, landslide });
const data = () => ({
  updated_at: new Date(Date.now() - 2 * 3600000).toISOString(),
  stale: false,
  days: [
    { key: 'today', date: '2026-11-18', less_certain: false, barangays: [
      bar(1, 'Bulacao', P('Yellow', ['Forecast 35 mm']), null),
      bar(2, 'Tapul', P('Red', ['Forecast 130 mm']), P('Green')),
      bar(3, 'Cansojong', P('Green'), null),
    ] },
    { key: 'tomorrow', date: '2026-11-19', less_certain: false, barangays: [
      bar(1, 'Bulacao', P('Green')), bar(2, 'Tapul', P('Orange', ['Forecast 70 mm']), P('Green')), bar(3, 'Cansojong', P('Green')),
    ] },
    { key: 'day_after', date: '2026-11-20', less_certain: true, barangays: [
      bar(1, 'Bulacao', P('Green')), bar(2, 'Tapul', P('Green'), P('Green')), bar(3, 'Cansojong', P('Green')),
    ] },
  ],
  pagasa_alerts: [{ identifier: 'a1', event: 'Thunderstorm Advisory', severity: 'Moderate', sent: '2026-11-18T01:00:00Z',
    expires: '2026-11-18T12:00:00Z', headline: 'Thunderstorm over Cebu', covers_talisay: true, applied: false, active: true }],
  overrides: [{ id: 7, hazard: 'Both', level: 'Orange', starts_at: '2026-11-18T01:00:00Z', ends_at: '2026-11-19T01:00:00Z',
    note: 'DRRMO note', created_by_name: 'Ana Cruz', cancelled_at: null }],
});

async function render() {
  const el = document.createElement('div');
  document.body.appendChild(el);
  await act(async () => { createRoot(el).render(<RainWatchCard />); });
  return el;
}
const button = (el, text) => [...el.querySelectorAll('button')].find((b) => b.textContent === text);
const click = (b) => act(async () => { b.click(); });

test('shows rows above Green, the rest as Green, the alerts and the overrides', async () => {
  rainWatchApi.get.mockResolvedValue(data());
  const el = await render();
  expect(el.querySelectorAll('tbody tr')).toHaveLength(2);
  expect(el.textContent).toContain('All other barangays: Green');
  expect(el.textContent).toContain('Not applied');
  expect(el.textContent).toContain('Thunderstorm over Cebu');
  expect(button(el, 'Cancel')).toBeTruthy();
  expect(button(el, 'Set a level by hand')).toBeTruthy();
  expect(el.querySelector('[title="Forecast 35 mm"]')).toBeTruthy();
});

test('says so in red when the forecast is out of date', async () => {
  rainWatchApi.get.mockResolvedValue({ ...data(), stale: true });
  const el = await render();
  expect(el.querySelector('.rw-stale').textContent).toContain('Out of date');
});

test('cancelling an override asks first, then cancels and reloads', async () => {
  rainWatchApi.get.mockResolvedValue(data());
  rainWatchApi.cancelOverride.mockResolvedValue({});
  const el = await render();
  await click(button(el, 'Cancel'));
  expect(rainWatchApi.cancelOverride).not.toHaveBeenCalled();
  const dialog = el.ownerDocument.querySelector('[role="dialog"]');
  await click([...dialog.querySelectorAll('button')].find((b) => b.textContent === 'Cancel override'));
  expect(rainWatchApi.cancelOverride).toHaveBeenCalledWith(7);
  expect(rainWatchApi.get).toHaveBeenCalledTimes(2);
});

test('shows each reason on screen, not only as a tooltip', async () => {
  rainWatchApi.get.mockResolvedValue(data());
  const el = await render();
  expect(el.querySelector('tbody').textContent).toContain('Forecast 35 mm');
  expect(el.querySelector('tbody').textContent).toContain('Forecast 130 mm');
});

test('when stale, a floored row still shows and the hidden-colours line replaces "All other"', async () => {
  const d = data();
  const unk = (b) => ({ ...b, flood: { level: 'unknown', reasons: ['Forecast out of date'] }, landslide: b.landslide && { level: 'unknown', reasons: [] } });
  d.stale = true;
  d.days = d.days.map((day) => ({ ...day, barangays: day.barangays.map((b) => (b.id === 2 && day.key === 'today'
    ? { ...b, flood: { level: 'Orange', reasons: ['Raised to Orange: PAGASA Flood Advisory'] } } : unk(b))) }));
  rainWatchApi.get.mockResolvedValue(d);
  const el = await render();
  expect(el.querySelectorAll('tbody tr')).toHaveLength(1);
  expect(el.querySelector('tbody').textContent).toContain('Raised to Orange: PAGASA Flood Advisory');
  expect(el.textContent).not.toContain('All other barangays: Green');
  expect(el.textContent).toContain('Forecast colours are hidden while the forecast is out of date.');
});

test('F6: each alert shows exactly one of four labels', async () => {
  const d = data();
  const a = (id, extra) => ({ ...d.pagasa_alerts[0], identifier: id, headline: id, ...extra });
  d.pagasa_alerts = [
    a('ok', { applied: true, covers_talisay: true, mapped: true }),
    a('elsewhere', { covers_talisay: false, mapped: true }),
    a('newkind', { covers_talisay: true, mapped: false }),
    a('plain', { covers_talisay: true, mapped: true }),
  ];
  rainWatchApi.get.mockResolvedValue(d);
  const el = await render();
  const labels = [...el.querySelectorAll('.rw-list li')].slice(0, 4).map((li) => li.querySelector('.rw-badge').textContent);
  expect(labels).toEqual(['Applied', 'Not for Talisay', 'New kind: please review', 'Not applied']);
});

test('F7: "All other barangays: Green" only when every remaining part is known', async () => {
  const d = data();
  d.days[2].barangays[2] = bar(3, 'Cansojong', P('unknown', ['Forecast out of date']), null);
  rainWatchApi.get.mockResolvedValue(d);
  const el = await render();
  expect(el.textContent).not.toContain('All other barangays: Green');
  expect(el.textContent).toContain('Other barangays: forecast out of date');
});

describe('F11: age and failures', () => {
  beforeEach(() => { jest.useFakeTimers(); });
  afterEach(() => { jest.useRealTimers(); });

  test('the age and the old-colours check move on every minute, and a failed poll says so', async () => {
    const start = new Date('2026-11-18T10:00:00Z');
    jest.setSystemTime(start);
    const d = { ...data(), updated_at: '2026-11-18T09:00:00Z' };
    rainWatchApi.get.mockResolvedValueOnce(d).mockRejectedValue(new Error('down'));
    const el = await render();
    expect(el.textContent).toContain('Updated 1 h ago');
    expect(el.textContent).not.toContain('Could not refresh');
    await act(async () => { jest.setSystemTime(new Date('2026-11-18T22:30:00Z')); jest.advanceTimersByTime(5 * 60 * 1000); });
    expect(el.textContent).toContain('Could not refresh. Trying again.');
    expect(el.textContent).toContain('Updated 13 h ago');
    expect([...el.querySelectorAll('.rw-stale')].map((n) => n.textContent).join('')).toContain('Out of date.');
  });
});
