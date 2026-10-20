import { sparkPoints, sparkSummary } from './Sparkline';
import { meterPercent } from './Meter';

test('spark points span the box, top is the highest value', () => {
  expect(sparkPoints([0, 10], 100, 20, 0)).toBe('0,20 100,0');
  expect(sparkPoints([5], 100, 20)).toBe('');
});

test('a flat series sits at mid-height', () => {
  expect(sparkPoints([3, 3, 3], 100, 20, 0)).toBe('0,10 50,10 100,10');
});

test('summary names the low and high months', () => {
  const pts = [{ label: 'Nov 2025', value: 10 }, { label: 'Jan 2026', value: 2 }, { label: 'Feb 2026', value: 2 }];
  expect(sparkSummary(pts)).toBe('lowest 2 in Jan 2026, highest 10 in Nov 2025');
});

test('meter percent is null-safe and clamped', () => {
  expect(meterPercent(null)).toBeNull();
  expect(meterPercent(undefined)).toBeNull();
  expect(meterPercent(NaN)).toBeNull();
  expect(meterPercent(0.644)).toBe(64);
  expect(meterPercent(1.2)).toBe(100);
});
