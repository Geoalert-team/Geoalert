import {
  DEFAULT_FILTERS, PRESETS, TREND_PRESETS, criteriaText, defaultFilters, describeFilters, filtersFromParams,
  filtersToParams, isDefault, namesFor, rangeError, requestParams, resolveRange,
} from './filters';

const today = new Date(2026, 10, 24); // 24 Nov 2026, local time
const f = (patch) => ({ ...DEFAULT_FILTERS, ...patch });

test('the presets, in order', () => {
  expect(PRESETS.map((p) => p.label))
    .toEqual(['3 months', '6 months', '12 months', 'This year', '5 years', 'All records', 'Custom']);
  expect(DEFAULT_FILTERS).toEqual({ period: '12m', from: '', to: '', hazard: '', barangay: '' });
});

test('the default is the last 12 months, counting this one', () => {
  expect(resolveRange(f(), today)).toEqual({ from: '2025-12-01', to: '2026-11-24' });
});

test('each preset resolves to a range ending today', () => {
  expect(resolveRange(f({ period: '3m' }), today)).toEqual({ from: '2026-09-01', to: '2026-11-24' });
  expect(resolveRange(f({ period: '6m' }), today).from).toBe('2026-06-01');
  expect(resolveRange(f({ period: 'year' }), today).from).toBe('2026-01-01');
  expect(resolveRange(f({ period: '5y' }), today).from).toBe('2021-12-01');
  expect(resolveRange(f({ period: 'all' }), today)).toEqual({ from: null, to: '2026-11-24' });
});

test('a custom range uses its own dates, open ends meaning everything or today', () => {
  expect(resolveRange(f({ period: 'custom', from: '2026-01-05', to: '2026-02-10' }), today))
    .toEqual({ from: '2026-01-05', to: '2026-02-10' });
  expect(resolveRange(f({ period: 'custom' }), today)).toEqual({ from: null, to: '2026-11-24' });
});

test('filters round-trip through the address and keep the view', () => {
  const custom = f({ period: 'custom', from: '2026-01-01', to: '2026-03-31', hazard: '2', barangay: '7' });
  const params = filtersToParams(custom, new URLSearchParams('view=trends'));
  expect(params.get('view')).toBe('trends');
  expect(filtersFromParams(params)).toEqual(custom);
});

test('defaults leave the address clean', () => {
  expect(filtersToParams(f(), new URLSearchParams('view=trends&period=6m')).toString()).toBe('view=trends');
  // dates only belong with a custom period
  expect(filtersToParams(f({ period: '6m', from: '2026-01-01' }), new URLSearchParams()).toString()).toBe('period=6m');
});

test('junk in the address falls back to the defaults', () => {
  expect(filtersFromParams(new URLSearchParams('period=week&hazard=fire&barangay=-1&from=x')))
    .toEqual(DEFAULT_FILTERS);
});

test('a backwards custom range is refused', () => {
  expect(rangeError(f({ period: 'custom', from: '2026-02-01', to: '2026-01-01' })))
    .toBe('The start date is after the end date.');
  expect(rangeError(f({ period: 'custom', from: '2026-01-01', to: '2026-02-01' }))).toBeNull();
  expect(rangeError(f())).toBeNull();
});

test('request parameters', () => {
  expect(requestParams(f({ hazard: '2', barangay: '7' }), today))
    .toEqual({ date_from: '2025-12-01', date_to: '2026-11-24', hazard_type: '2', barangay: '7' });
  expect(requestParams(f({ period: 'all' }), today)).toEqual({ date_to: '2026-11-24' });
});

test('names for the picked hazard and barangay', () => {
  const types = [{ id: 2, name: 'Flood' }];
  const brgys = [{ id: 7, name: 'Lagtang' }];
  expect(namesFor(f({ hazard: '2', barangay: '7' }), types, brgys)).toEqual({ hazardName: 'Flood', barangayName: 'Lagtang' });
  expect(namesFor(f({ hazard: '9' }), types, brgys)).toEqual({ hazardName: 'Unknown hazard type (#9)', barangayName: null });
});

test('the filters in words', () => {
  expect(describeFilters(f(), {}, today)).toBe('Dec 2025 – Nov 2026 · All hazards · All barangays');
  expect(describeFilters(f({ period: 'all' }), { hazardName: 'Flood', barangayName: 'Lagtang' }, today))
    .toBe('All records to Nov 2026 · Flood · Lagtang');
  expect(describeFilters(f({ period: 'custom', from: '2026-01-05', to: '2026-02-10' }), {}, today))
    .toBe('5 Jan 2026 – 10 Feb 2026 · All hazards · All barangays');
});

test('Trend Analysis has its own presets, all records by default, counted in calendar years', () => {
  expect(TREND_PRESETS.map((p) => p.label)).toEqual(['All records', '10 years', '5 years', '3 years', 'This year', 'Custom']);
  expect(defaultFilters('trends').period).toBe('all');
  expect(resolveRange({ ...defaultFilters('trends'), period: 'y5' }, today)).toEqual({ from: '2022-01-01', to: '2026-11-24' });
  expect(resolveRange({ ...defaultFilters('trends'), period: 'y3' }, today).from).toBe('2024-01-01');
  const params = filtersToParams(defaultFilters('trends'), new URLSearchParams(), 'trends');
  expect(params.toString()).toBe('');
  expect(filtersFromParams(new URLSearchParams('period=12m'), 'trends').period).toBe('all'); // not a trend preset
  expect(filtersFromParams(new URLSearchParams('period=y10'), 'trends').period).toBe('y10');
  expect(isDefault(defaultFilters('trends'), 'trends')).toBe(true);
});

test('an id the lists do not hold is named as such, never as "all"', () => {
  expect(namesFor(f({ barangay: '9' }), [], [{ id: 7, name: 'Lagtang' }]))
    .toEqual({ hazardName: null, barangayName: 'Unknown barangay (#9)' });
  expect(namesFor(f({ hazard: '4' }), [], [])).toEqual({ hazardName: 'Hazard type #4', barangayName: null });
});

test('a custom start in the future with no end is refused', () => {
  expect(rangeError(f({ period: 'custom', from: '2027-01-01' }), today)).toBe('The start date is in the future.');
  expect(rangeError(f({ period: 'custom', from: '2026-01-01' }), today)).toBeNull();
});

test('the filters in the audit log format', () => {
  expect(criteriaText(f(), { hazardName: 'Flood', barangayName: 'Lagtang' }, today))
    .toBe('date_from=2025-12-01 date_to=2026-11-24 barangay=Lagtang hazard_type=Flood');
  expect(criteriaText(f({ period: 'all' }), {}, today))
    .toBe('date_from=- date_to=2026-11-24 barangay=all hazard_type=all');
});
