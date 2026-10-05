// fakeHistoryApi.js
// ---------------------------------------------------------------
// Stand-in for the real GET /api/history/ and /api/history/trends/
// endpoints, which exist on the backend (apps/history) but aren't wired
// up to the frontend yet. Generates realistic-looking fake
// HistoricalRecord rows with @faker-js/faker so the History page has
// something real-shaped to render in the meantime.
//
// Swap this for a real axios call in src/api/historyApi.js once the
// frontend is wired to the real endpoint â€” HistoricalData.jsx only
// needs its import changed, nothing else, since the shape matches.
// ---------------------------------------------------------------

import { faker } from '@faker-js/faker';

const BARANGAYS = [
  'Biasong', 'Bulacao', 'Cadulawan', 'Camp IV', 'Cansojong', 'Dumlog',
  'Jaclupan', 'Lagtang', 'Lawaan I', 'Lawaan II', 'Lawaan III', 'Linao',
  'Maghaway', 'Manipis', 'Mohon', 'Poblacion', 'Pooc', 'San Isidro',
  'San Roque', 'Tabunoc', 'Tangke', 'Tapul',
];

const HAZARD_TYPES = ['Flood', 'Fire', 'Landslide'];
const SEVERITIES = ['Red', 'Orange', 'Green'];

const DESCRIPTION_TEMPLATES = {
  Flood: [
    'Heavy rainfall caused waist-deep flooding along the main road.',
    'Flash flood from overflowing creek affected low-lying households.',
    'Storm surge combined with high tide flooded the coastal barangay.',
  ],
  Fire: [
    'Electrical fire spread through a row of residential structures.',
    'Fire broke out in a market stall area, contained within hours.',
    'Grass fire during dry season spread toward nearby homes.',
  ],
  Landslide: [
    'Soil erosion after prolonged rain triggered a slope collapse.',
    'Cracks in the hillside led to a landslide affecting upland homes.',
    'Heavy rainfall saturated the slope, causing a partial collapse.',
  ],
};

function randomRecord() {
  const hazard_type = faker.helpers.arrayElement(HAZARD_TYPES);
  // Most historical events are low/moderate severity; extreme ones are rarer.
  const severity = faker.helpers.weightedArrayElement([
    { weight: 5, value: 'Green' },
    { weight: 3, value: 'Orange' },
    { weight: 2, value: 'Red' },
  ]);
  // Most events have zero casualties; a small number have a few.
  const casualties = faker.helpers.weightedArrayElement([
    { weight: 8, value: 0 },
    { weight: 2, value: faker.number.int({ min: 1, max: 3 }) },
  ]);

  return {
    id: faker.string.uuid(),
    barangay_name: faker.helpers.arrayElement(BARANGAYS),
    hazard_type,
    severity,
    description: faker.helpers.arrayElement(DESCRIPTION_TEMPLATES[hazard_type]),
    casualties,
    displaced: faker.number.int({ min: 0, max: 480 }),
    occurred_at: faker.date.past({ years: 3 }).toISOString(),
  };
}

function delay(ms = 300) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

// Generate once per page load (stable for the session) rather than on
// every call, so the list doesn't reshuffle every time something re-renders.
let records = Array.from({ length: 28 }, randomRecord).sort(
  (a, b) => new Date(b.occurred_at) - new Date(a.occurred_at)
);

export const fakeHistoryApi = {
  list: async (filters = {}) => {
    await delay();
    let result = [...records];
    if (filters.barangay_name) result = result.filter((r) => r.barangay_name === filters.barangay_name);
    if (filters.hazard_type) result = result.filter((r) => r.hazard_type === filters.hazard_type);
    if (filters.severity) result = result.filter((r) => r.severity === filters.severity);
    return result;
  },

  trends: async () => {
    await delay();
    const byMonth = {};
    records.forEach((r) => {
      const month = r.occurred_at.slice(0, 7); // YYYY-MM
      byMonth[month] = (byMonth[month] || 0) + 1;
    });
    return Object.entries(byMonth)
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([month, count]) => ({ month, count }));
  },
};
