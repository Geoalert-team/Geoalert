import {
  barangayLevel, laterDayHint, bannerInfo, updatedText, rainWatchTooltip, dayLabel, RAIN_LEVELS, mapLevel, withClientStale, rainLevel, rainWatchSignature,
} from './rainWatchLevels';

const b = (id, flood, landslide = null, name = `B${id}`) => ({
  id, name, flood: { level: flood, reasons: [] }, landslide: landslide && { level: landslide, reasons: [] },
});
const day = (key, date, barangays) => ({ key, date, less_certain: key === 'day_after', barangays });
const DATA = {
  updated_at: '2026-11-18T12:00:00Z',
  stale: false,
  days: [
    day('today', '2026-11-18', [b(1, 'none'), b(2, 'none', 'none')]),
    day('tomorrow', '2026-11-19', [b(1, 'Orange', 'none'), b(2, 'none', 'Red')]),
    day('day_after', '2026-11-20', [1, 2, 3, 4, 5, 6].map((i) => b(i, 'Red'))),
  ],
};
const ALL = new Set(['Flood', 'Landslide']);

test('barangayLevel takes the worse hazard, respects ticks and a null landslide', () => {
  expect(barangayLevel(b(1, 'Orange', 'Red'), ALL)).toBe('Red');
  expect(barangayLevel(b(1, 'Orange', 'Red'), new Set(['Flood']))).toBe('Orange');
  expect(barangayLevel(b(1, 'Orange', 'Red'), new Set(['Landslide']))).toBe('Red');
  expect(barangayLevel(b(1, 'Orange', null), ALL)).toBe('Orange');
  expect(barangayLevel(b(1, 'Orange', 'Red'), new Set())).toBe('none');
});

test('laterDayHint finds the first later day above Yellow', () => {
  expect(laterDayHint(DATA, ALL, 'tomorrow')).toEqual({ key: 'day_after', level: 'Red', count: 6 });
  expect(laterDayHint(DATA, ALL, 'day_after')).toBeNull();
  const quiet = { days: [day('today', 'x', [b(1, 'Yellow')]), day('tomorrow', 'y', [b(1, 'Yellow')])] };
  expect(laterDayHint(quiet, ALL, 'today')).toBeNull();
});

test('bannerInfo starts from today and ignores Yellow', () => {
  expect(bannerInfo(DATA, ALL)).toEqual({ key: 'tomorrow', level: 'Red', count: 1 });
  const yellow = { days: [day('today', 'x', [b(1, 'Yellow', 'Yellow')])] };
  expect(bannerInfo(yellow, ALL)).toBeNull();
});

test('a stale forecast is unknown and gives no banner', () => {
  const stale = { stale: true, days: [day('today', 'x', [b(1, 'unknown', 'unknown')])] };
  expect(barangayLevel(stale.days[0].barangays[0], ALL)).toBe('unknown');
  expect(bannerInfo(stale, ALL)).toBeNull();
  expect(RAIN_LEVELS.unknown.label).toBe('Out of date');
});

test('updatedText', () => {
  const now = Date.parse('2026-11-18T15:00:00Z');
  expect(updatedText(null, now)).toBe('No forecast yet');
  expect(updatedText('2026-11-18T12:00:00Z', now)).toBe('Updated 3 h ago');
  expect(updatedText('2026-11-18T14:50:00Z', now)).toBe('Updated just now');
});

test('dayLabel names the day after by its weekday', () => {
  expect(dayLabel(DATA.days[0], 0)).toBe('Today');
  expect(dayLabel(DATA.days[1], 1)).toBe('Tomorrow');
  expect(dayLabel(DATA.days[2], 2)).toBe('Fri');
});

test('rainWatchTooltip shows the strip and reasons, and escapes names', () => {
  const data = {
    days: [
      day('today', '2026-11-18', [b(1, 'none', 'none')]),
      day('tomorrow', '2026-11-19', [b(1, 'Orange', 'none')]),
      day('day_after', '2026-11-20', [{ ...b(1, 'Red'), flood: { level: 'Red', reasons: ['Forecast 140 mm'] } }]),
    ],
  };
  const html = rainWatchTooltip('<b>Bold</b>', 1, data, 'day_after', ALL);
  expect(html).not.toContain('<b>');
  expect(html).toContain('&lt;b&gt;Bold');
  expect(html).toContain('Today – · Tomorrow Orange · Fri Red');
  expect(html).toContain('Flood: Red. Forecast 140 mm');
});

test('mapLevel: no forecast yet, or no data for the day, is unknown (grey)', () => {
  expect(mapLevel({ updated_at: null, stale: true, days: [] }, 'today', 1, ALL)).toBe('unknown');
  expect(mapLevel(null, 'today', 1, ALL)).toBe('unknown');
  expect(mapLevel({ ...DATA, days: [] }, 'today', 1, ALL)).toBe('unknown');
  expect(mapLevel(DATA, 'day_after', 1, ALL)).toBe('Red');
  expect(mapLevel(DATA, 'today', 99, ALL)).toBe('none');
});

test('withClientStale greys forecast levels of an old answer, keeping floor-raised ones', () => {
  const old = {
    updated_at: '2026-11-18T02:00:00Z',
    stale: false,
    days: [day('today', '2026-11-18', [
      b(1, 'Red', 'Orange'),
      { ...b(2, 'Orange'), flood: { level: 'Orange', reasons: ['Raised to Orange: PAGASA General Flood Advisory'] } },
    ])],
  };
  const now = Date.parse('2026-11-18T15:00:00Z'); // 13 h old
  const out = withClientStale(old, now);
  expect(out.stale).toBe(true);
  expect(mapLevel(out, 'today', 1, ALL)).toBe('unknown');
  expect(mapLevel(out, 'today', 2, ALL)).toBe('Orange');
  expect(bannerInfo(out, ALL)).toEqual({ key: 'today', level: 'Orange', count: 1 });
  expect(withClientStale(old, Date.parse('2026-11-18T13:00:00Z'))).toBe(old);
});

test('F1: unknown beats none when neither part is Orange or Red; a null landslide is absent', () => {
  expect(barangayLevel(b(1, 'unknown', 'none'), ALL)).toBe('unknown');
  expect(barangayLevel(b(1, 'none', 'unknown'), ALL)).toBe('unknown');
  expect(barangayLevel(b(1, 'unknown', 'Yellow'), ALL)).toBe('unknown');
  expect(barangayLevel(b(1, 'unknown', 'Red'), ALL)).toBe('Red');
  expect(barangayLevel(b(1, 'Orange', 'unknown'), ALL)).toBe('Orange');
  expect(barangayLevel(b(1, 'none', null), ALL)).toBe('none');
  expect(barangayLevel(b(1, 'unknown', null), ALL)).toBe('unknown');
});

test('F3: with no runs a real level still shows, an unknown or empty part is grey', () => {
  const noRuns = (flood, landslide = null) => ({ updated_at: null, stale: true, days: [day('today', 'x', [b(1, flood, landslide)])] });
  expect(mapLevel(noRuns('Red'), 'today', 1, ALL)).toBe('Red');
  expect(mapLevel(noRuns('Yellow'), 'today', 1, ALL)).toBe('Yellow');
  expect(mapLevel(noRuns('unknown'), 'today', 1, ALL)).toBe('unknown');
  expect(mapLevel(noRuns('none'), 'today', 1, ALL)).toBe('unknown');
  expect(mapLevel(noRuns('unknown'), 'today', 99, ALL)).toBe('unknown');
  expect(bannerInfo(noRuns('Red'), ALL)).toEqual({ key: 'today', level: 'Red', count: 1 });
});

test('F4: the stale_hours of the answer is the limit, 12 when it is missing', () => {
  const old = { updated_at: '2026-11-18T10:00:00Z', stale: false, days: [day('today', 'x', [b(1, 'Red')])] };
  const now = Date.parse('2026-11-18T15:00:00Z'); // 5 h old
  expect(withClientStale({ ...old, stale_hours: 4 }, now).stale).toBe(true);
  expect(withClientStale({ ...old, stale_hours: 6 }, now).stale).toBe(false);
  expect(withClientStale(old, now).stale).toBe(false);
  expect(withClientStale(old, Date.parse('2026-11-18T23:00:00Z')).stale).toBe(true);
});

test('F9: an unexpected level string falls back instead of throwing', () => {
  expect(rainLevel('Purple')).toBe(RAIN_LEVELS.none);
  expect(rainLevel(undefined)).toBe(RAIN_LEVELS.none);
  expect(mapLevel({ ...DATA, days: [day('today', 'x', [b(1, 'Purple')])] }, 'today', 1, ALL)).toBe('Purple');
  expect(rainWatchTooltip('A', 1, { days: [day('today', 'x', [b(1, 'Purple')])] }, 'today', ALL)).toContain('Flood: No rain watch');
});

test('F10: a Green part reads as a dash in the tooltip strip', () => {
  const html = rainWatchTooltip('A', 1, { days: [day('today', 'x', [b(1, 'Green')])] }, 'today', ALL);
  expect(html).toContain('Today –');
});

test('F2: the signature changes with levels, reasons, floors and stale, and not otherwise', () => {
  const base = { ...DATA, floors: [{ source: 'PAGASA', hazard: 'Flood', level: 'Orange', until: 'u', text: 't' }] };
  const sig = rainWatchSignature(base);
  expect(rainWatchSignature(JSON.parse(JSON.stringify(base)))).toBe(sig);
  expect(rainWatchSignature({ ...base, stale: true })).not.toBe(sig);
  expect(rainWatchSignature({ ...base, floors: [] })).not.toBe(sig);
  expect(rainWatchSignature({ ...base, floors: [{ ...base.floors[0], text: 'other' }] })).not.toBe(sig);
  const changed = JSON.parse(JSON.stringify(base));
  changed.days[1].barangays[0].flood.level = 'Red';
  expect(rainWatchSignature(changed)).not.toBe(sig);
  const reason = JSON.parse(JSON.stringify(base));
  reason.days[0].barangays[0].flood.reasons = ['Raised by DRRMO: x'];
  expect(rainWatchSignature(reason)).not.toBe(sig);
  expect(rainWatchSignature(null)).toBe('');
});
