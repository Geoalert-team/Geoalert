import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import BarangayActivity from './BarangayActivity';
import { sortBarangays } from './barangaySort';

beforeAll(() => { global.IS_REACT_ACT_ENVIRONMENT = true; });

const rows = Array.from({ length: 12 }, (_, i) => ({ barangay: `B${String(i).padStart(2, '0')}`, zones: 12 - i, incidents: i }));

test('sorts by the chosen count, then the other, then name', () => {
  const r = [{ barangay: 'Linao', zones: 1, incidents: 0 }, { barangay: 'Dumlog', zones: 1, incidents: 0 }, { barangay: 'Pooc', zones: 1, incidents: 5 }];
  expect(sortBarangays(r, 'zones').map((x) => x.barangay)).toEqual(['Pooc', 'Dumlog', 'Linao']);
  expect(sortBarangays(r, 'incidents')[0].barangay).toBe('Pooc');
});

test('top 10 on screen, every row in the DOM for print, re-sorts on header click', () => {
  const el = document.createElement('div');
  act(() => { createRoot(el).render(<BarangayActivity rows={rows} />); });
  expect(el.querySelectorAll('tbody tr')).toHaveLength(12);
  expect(el.querySelectorAll('tbody tr.ba-more')).toHaveLength(2);
  expect(el.textContent).toContain('Show all 12 barangays');
  expect(el.querySelector('tbody tr td').textContent).toBe('B00');
  const incidents = [...el.querySelectorAll('th button')].find((b) => b.textContent.includes('Incident reports'));
  act(() => { incidents.click(); });
  expect(el.querySelector('tbody tr td').textContent).toBe('B11');
  expect(incidents.closest('th').getAttribute('aria-sort')).toBe('descending');
});

test('empty message when there are no rows', () => {
  const el = document.createElement('div');
  act(() => { createRoot(el).render(<BarangayActivity rows={[]} />); });
  expect(el.textContent).toBe('No zones or incident reports in this period.');
});
