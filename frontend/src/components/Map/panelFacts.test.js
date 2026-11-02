import { activeFor, placeLine, startedParts } from './panelFacts';

test('the place line names each purok once, in order', () => {
  const item = { pins: [
    { purok_name: 'Sitio Libo' }, { purok_name: 'Purok Santol' }, { purok_name: 'Sitio Libo' }, { purok_name: null },
  ] };
  expect(placeLine(item)).toBe('Sitio Libo, Purok Santol');
});

test('a zone with no purok pins is placed in the city', () => {
  expect(placeLine({ pins: [] })).toBe('Talisay City');
  expect(placeLine({ pins: [{ purok_name: null }] })).toBe('Talisay City');
  expect(placeLine({})).toBe('Talisay City');
});

test('active for counts hours, then days', () => {
  const now = new Date('2026-10-28T21:00:00+08:00');
  expect(activeFor('2026-10-28T20:30:00+08:00', now)).toBe('Under an hour');
  expect(activeFor('2026-10-28T20:00:00+08:00', now)).toBe('1 hour');
  expect(activeFor('2026-10-28T08:00:00+08:00', now)).toBe('13 hours');
  expect(activeFor('2026-10-27T13:59:00+08:00', now)).toBe('1 day');
  expect(activeFor('2026-10-25T09:00:00+08:00', now)).toBe('3 days');
  expect(activeFor(null, now)).toBe('Not recorded');
});

test('the start time is a day and a time, the year only when it is not this one', () => {
  const now = new Date(2026, 10, 2, 14, 0);
  const at = (...parts) => new Date(...parts).toISOString();
  expect(startedParts(at(2026, 10, 2, 13, 31), now).day).toBe('Today');
  expect(startedParts(at(2026, 10, 2, 13, 31), now).time).toMatch(/^1:31\s?PM$/i);
  expect(startedParts(at(2026, 10, 1, 23, 5), now).day).toBe('Yesterday');
  expect(startedParts(at(2026, 9, 27, 9, 0), now).day).toBe('Oct 27');
  expect(startedParts(at(2025, 10, 2, 9, 0), now).day).toMatch(/Nov 2, 2025/);
  expect(startedParts(null, now)).toBeNull();
});
