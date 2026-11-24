// A /api/reports/trends/ answer for the Trend Analysis tests
export const TRENDS = {
  range: { from: '2025-12-01', to: '2026-11-24', granularity: 'month', all_records: false },
  filters: { hazard_type: null, barangay: null },
  generated_at: '2026-11-24T08:00:00+08:00',
  generated_by: 'Officer',
  totals: {
    events: 41,
    casualties: 3,
    by_type: [{ hazard: 'Fire', count: 30 }, { hazard: 'Flood', count: 11 }],
    previous: { from: '2024-12-08', to: '2025-11-30', events: 37,
      by_type: [{ hazard: 'Fire', count: 26 }, { hazard: 'Flood', count: 11 }],
      barangays: [{ id: 7, name: 'Lagtang', total: 12 }, { id: null, name: 'Unspecified', total: 25 }] },
  },
  series: [
    { period: '2025-12', label: 'Dec 2025', partial: false, counts: { Fire: 3, Flood: 0 }, total: 3 },
    { period: '2026-01', label: 'Jan 2026', partial: false, counts: { Fire: 27, Flood: 11 }, total: 38 },
  ],
  month_of_year: Array.from({ length: 12 }, (_, i) => ({
    month: i + 1,
    label: ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'][i],
    counts: { Fire: i === 0 ? 27 : i === 11 ? 3 : 0, Flood: i === 0 ? 11 : 0 },
    total: i === 0 ? 38 : i === 11 ? 3 : 0,
  })),
  severity: [
    { hazard: 'Fire', counts: { Red: 2, Orange: 1, Green: 27 } },
    { hazard: 'Flood', counts: { Red: 0, Orange: 4, Green: 7 } },
  ],
  barangays: [
    { id: null, name: 'Unspecified', total: 20, counts: { Fire: 20 }, share: 0.488 },
    { id: 7, name: 'Lagtang', total: 15, counts: { Fire: 8, Flood: 7 }, share: 0.366 },
    { id: 3, name: 'Biasong', total: 6, counts: { Fire: 2, Flood: 4 }, share: 0.146 },
  ],
  calendar: [{ year: 2025, months: [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 3], total: 3 },
    { year: 2026, months: [38, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], total: 38 }],
  month_average: [{ hazard: 'Fire', years: 2, months: [13.5, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1.5] },
    { hazard: 'Flood', years: 1, months: [11, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0] }],
  weekday: ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'].map((label, i) => ({ day: i + 1, label,
    counts: { Fire: i === 0 ? 30 : 0, Flood: i === 1 ? 11 : 0 }, total: i === 0 ? 30 : i === 1 ? 11 : 0 })),
  severity_by_year: [{ year: 2025, counts: { Red: 0, Orange: 1, Green: 2 } }, { year: 2026, counts: { Red: 2, Orange: 4, Green: 32 } }],
  coverage: [
    { hazard: 'Fire', first: '2023-01-04', last: '2026-11-02', records: 221 },
    { hazard: 'Flood', first: '2021-07-10', last: '2026-09-01', records: 24 },
  ],
};

export const EMPTY_TRENDS = {
  ...TRENDS,
  totals: { events: 0, casualties: 0, by_type: [], previous: { from: '2024-12-08', to: '2025-11-30', events: 0 } },
  series: TRENDS.series.map((s) => ({ ...s, counts: {}, total: 0 })),
  month_of_year: TRENDS.month_of_year.map((m) => ({ ...m, counts: {}, total: 0 })),
  severity: [],
  barangays: [],
};
