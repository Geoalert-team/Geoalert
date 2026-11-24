import { hazardsIn, sortHazards } from './trendShapes';
import { TRENDS } from './trendFixture';
import { changeLine, howOften, mostCommon, peakLines, plainSentence, stoodOut } from './trendWords';

test('hazards in the answer, in the usual order', () => {
  expect(hazardsIn(TRENDS)).toEqual(['Fire', 'Flood']);
  expect(hazardsIn({ series: [{ counts: { Unspecified: 1, Landslide: 0, Flood: 2 } }] }))
    .toEqual(['Flood', 'Landslide', 'Unspecified']);
  expect(sortHazards(['Storm surge', 'Unspecified', 'Fire'])).toEqual(['Fire', 'Storm surge', 'Unspecified']);
});

test('a direction is named only when the server found one', () => {
  const base = { hazard: 'Fire', complete_years: 3, slope: 2, quiet_since: null };
  expect(plainSentence({ ...base, verdict: 'too_few_years' }))
    .toBe('We need at least 5 full years of records to tell whether the number of fire events is changing; there are 3 so far.');
  expect(plainSentence({ ...base, verdict: 'gaps' })).not.toMatch(/up|down/);
  expect(plainSentence({ ...base, complete_years: 6, verdict: 'increasing' }))
    .toBe('Over 6 full years the number has gone up steadily, by about 2 a year.');
  expect(plainSentence({ ...base, complete_years: 6, verdict: 'no_clear_trend' }))
    .toBe('Over 6 full years the number goes up and down without a steady change.');
  expect(plainSentence({ ...base, verdict: 'too_few_years', quiet_since: 2022 }))
    .toContain('No records since 2022; this may be missing data.');
});

test('the last full year against the years before', () => {
  expect(changeLine({ latest: 55, earlier_mean: 59, pct: -7 })).toBe('7% fewer than the years before (59 a year)');
  expect(changeLine({ latest: 60, earlier_mean: 59, pct: 2 })).toBe('About the same as the years before (59 a year)');
  expect(changeLine({ latest: 3, earlier_mean: 0, pct: null })).toBeNull();
});

test('months, peaks and places in words', () => {
  expect(stoodOut({ hazard: 'Fire', year: 2025, month: 4, count: 14, baseline_min: 3, baseline_max: 8 }))
    .toBe('April 2025: 14 fire events. April usually has 3 to 8.');
  expect(stoodOut({ hazard: 'Flood', year: 2026, month: 9, count: 3, baseline_min: 0, baseline_max: 0 }))
    .toBe('September 2026: 3 flood events. September usually has 0.');
  expect(peakLines([{ hazard: 'Fire', months: [13.5, null, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1.5] }, { hazard: 'Flood', months: Array(12).fill(null) }]))
    .toEqual(['Fire: most often in January (13.5 a year on average)']);
  expect(howOften({ recurrence: 'every_year', years_with_events: 5 }, 5)).toBe('Every year (5 of 5 years)');
  expect(howOften({ recurrence: 'none', years_with_events: 0 }, 5)).toBe('None');
  expect(mostCommon({ Fire: 8, Flood: 7 })).toBe('Fire');
  expect(mostCommon({})).toBe('—');
});
