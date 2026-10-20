import { withAlpha } from './color';

test('six- and three-digit hex to rgba', () => {
  expect(withAlpha('#1c2e4a', 0.14)).toBe('rgba(28,46,74,0.14)');
  expect(withAlpha('#fff', 0)).toBe('rgba(255,255,255,0)');
});
