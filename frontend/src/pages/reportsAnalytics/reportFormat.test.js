import { formatShare, operationsCsv, peso, recordedText, summaryCsv, withShares } from './reportFormat';

test('shares of the total, a dash when nothing was counted', () => {
  expect(withShares([{ n: 'A', count: 3 }, { n: 'B', count: 1 }], (r) => r.n)).toEqual([
    { label: 'A', count: 3, share: 0.75 }, { label: 'B', count: 1, share: 0.25 },
  ]);
  expect(withShares([{ n: 'A', count: 0 }], (r) => r.n)[0].share).toBeNull();
  expect(formatShare(null)).toBe('—');
  expect(formatShare(0.004)).toBe('<1%');
});

test('how many records carry a figure', () => {
  expect(recordedText({ recorded_on: 2, of: 4 })).toBe('recorded on 2 of 4 records');
  expect(recordedText({ recorded_on: 0, of: 4 })).toBe('not recorded in these 4 records');
  expect(peso(50000)).toBe('₱50,000');
  expect(peso(null)).toBe('—');
});

const SUMMARY = {
  generated_by: 'Officer', generated_at: null,
  holdings: { archive: [], zones: { count: 0, first: null }, alerts: { count: 0, first: null }, notices: { count: 0 },
    incident_reports: { count: 0, first: null }, barangays: 22, puroks: 0 },
  events: 2,
  impact: Object.fromEntries(['deaths', 'injured', 'families_affected', 'persons_affected', 'structures_affected',
    'damage_cost'].map((k) => [k, { value: k === 'deaths' ? 1 : null, recorded_on: k === 'deaths' ? 1 : 0, of: 2 }])),
  by_hazard: [], by_barangay: [{ id: 7, name: 'Lagtang', events: 2, deaths: 1 }], by_purok: [],
  severity: [{ severity: 'Red', count: 2 }], fire: null, flood_landslide: null,
  completeness: [{ key: 'barangay', label: 'Filed under a barangay', count: 2, of: 2 }],
};

test('Hazard Summary CSV: impact with records carrying it, displaced not recorded', () => {
  const csv = summaryCsv(SUMMARY, 'Dec 2025 – Nov 2026 · All hazards · All barangays');
  expect(csv).toContain('Report,Hazard Summary');
  expect(csv).toContain('Deaths,1,1,2');
  expect(csv).toContain('Injured,,0,2');
  expect(csv).toContain('Total displaced,Not recorded');
  expect(csv).toContain('Lagtang,2,100%,1');
  expect(csv).toContain('Filed under a barangay,2,2,100%');
});

test('Response Status CSV', () => {
  const csv = operationsCsv({ generated_by: 'Officer', kpis: { zones_published: 3, read_rate: 0.5, median_minutes_to_read: 12 },
    zones_by_status: { Active: 1, Resolved: 2, Archived: 0, Retracted: 1 } }, 'x');
  expect(csv).toContain('Withdrawn as published in error,1');
  expect(csv).toContain('Alert notices opened (%),50');
  expect(csv).toContain('Median time to open an alert,12 min');
});
