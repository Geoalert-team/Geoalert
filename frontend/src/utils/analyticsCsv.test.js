import { analyticsCsv } from './analyticsCsv';
import { inSeverityOrder } from './severity';

const base = {
  months: 12, since: '2025-11-01', generated_at: '2026-10-20T08:00:00Z', generated_by: 'Officer',
  includes_samples: false, hazard_type: { id: 1, name: 'Flood' },
  kpis: {}, monthly: [{ month: '2026-10', zones: 1, alerts: 2, incidents: 3, events: 4 }],
  zones_by_type: [], zones_by_severity: [{ severity: 'Green', count: 2 }, { severity: 'Red', count: 1 }],
  barangays: [{ barangay: 'Tabunok', zones: 14, incidents: 28 }, { barangay: 'Pooc', zones: 0, incidents: 3 }],
};
const lines = (d) => analyticsCsv(d).split('\r\n');

test('names the hazard type, or all types', () => {
  expect(lines(base)).toContain('Hazard type,Flood');
  expect(lines({ ...base, hazard_type: null })).toContain('Hazard type,All types');
});

test('one barangay activity section with every row', () => {
  const l = lines(base);
  const at = l.indexOf('Barangay activity');
  expect(l.slice(at + 1, at + 4)).toEqual(['Barangay,Zones,Incident reports', 'Tabunok,14,28', 'Pooc,0,3']);
  expect(l.some((x) => x.includes('top 10'))).toBe(false);
});

test('severity rows run Extreme, Moderate, Low with zeros', () => {
  const l = lines(base);
  const at = l.indexOf('Zones by severity');
  expect(l.slice(at + 2, at + 5)).toEqual(['Extreme,1', 'Moderate,0', 'Low,2']);
});

test('inSeverityOrder keeps unknown codes at the end', () => {
  expect(inSeverityOrder([{ severity: 'Blue', count: 1 }]).map((r) => r.severity)).toEqual(['Red', 'Orange', 'Green', 'Blue']);
});
