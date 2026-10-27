import {
  defaultPeriod, periodIn, periodLabel, periodMonth, periodParams, periodPastHeader, periodYearsText, withMonth,
} from './forecastLevels';

const MONTH = { mode: 'month', month: 11, year: 2027, date: '2027-11-15' };
const MONTH_YEAR = { ...MONTH, mode: 'monthYear' };
const DATE = { ...MONTH, mode: 'date' };

test('it opens on next month, with this year and today ready for the other modes', () => {
  expect(defaultPeriod(new Date(2026, 9, 27))).toEqual({ mode: 'month', month: 11, year: 2026, date: '2026-10-27' });
  // In December, next month is next year's January
  expect(defaultPeriod(new Date(2026, 11, 5))).toMatchObject({ month: 1, year: 2027, date: '2026-12-05' });
});

test('each mode asks the server for its own period', () => {
  expect(periodParams(MONTH)).toEqual({ month: 11 });
  expect(periodParams(MONTH_YEAR)).toEqual({ month: 11, year: 2027 });
  expect(periodParams(DATE)).toEqual({ date: '2027-11-15' });
});

test('labels for each mode', () => {
  expect([MONTH, MONTH_YEAR, DATE].map(periodLabel)).toEqual(['November', 'November 2027', 'November 15, 2027']);
  expect(periodIn(DATE)).toBe('the week of Nov 15');
  expect([MONTH, DATE].map(periodPastHeader)).toEqual(['Past Novembers', 'Past years, week of Nov 15']);
  const row = { years_hit: 3, years_considered: 4 };
  expect([MONTH_YEAR, DATE].map((p) => periodYearsText(row, p))).toEqual(['3 of 4 past Novembers', '3 of 4 past years']);
});

test('moving to another month keeps the mode, and a date its day where it can', () => {
  expect(withMonth(MONTH_YEAR, 3)).toEqual({ ...MONTH_YEAR, month: 3 });
  expect(withMonth(DATE, 3).date).toBe('2027-03-15');
  expect(withMonth({ ...DATE, date: '2027-01-31' }, 2).date).toBe('2027-02-28');
  expect(periodMonth(withMonth(DATE, 3))).toBe(3);
});
