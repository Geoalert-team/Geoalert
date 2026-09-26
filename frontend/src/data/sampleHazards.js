// SAMPLE DATA FOR DESIGN PREVIEW ONLY. These are NOT real hazards.
//
// The public map shows these pins only when the backend has no active hazards,
// and it labels them "Sample data" on screen. Once the DRRMO publishes real
// hazards, they replace these automatically.
//
// To turn samples off completely, set SHOW_SAMPLE_DATA to false.

export const SHOW_SAMPLE_DATA = true;

const daysAgo = (n) => new Date(Date.now() - n * 24 * 60 * 60 * 1000).toISOString();

export const SAMPLE_HAZARDS = [
  {
    id: 'sample-1',
    sample: true,
    location: 'Tabunok',
    type: 'Flood',
    severity: 'Red',
    status: 'Active',
    activatedAt: daysAgo(1),
    description: 'Low-lying streets near the river can flood quickly during heavy rain.',
    position: [10.2628, 123.838],
  },
  {
    id: 'sample-2',
    sample: true,
    location: 'Cansojong',
    type: 'Fire',
    severity: 'Red',
    status: 'Active',
    activatedAt: daysAgo(3),
    description: 'Closely built houses and narrow alleys make fire spread fast and slow down responders.',
    position: [10.249, 123.843],
  },
  {
    id: 'sample-3',
    sample: true,
    location: 'Lawaan II',
    type: 'Landslide',
    severity: 'Orange',
    status: 'Active',
    activatedAt: daysAgo(2),
    description: 'Slopes above the road can loosen after several days of rain.',
    position: [10.256, 123.825],
  },
  {
    id: 'sample-4',
    sample: true,
    location: 'Dumlog',
    type: 'Flood',
    severity: 'Orange',
    status: 'Active',
    activatedAt: daysAgo(5),
    description: 'Drainage along the main road backs up during long rainfall.',
    position: [10.247, 123.833],
  },
  {
    id: 'sample-5',
    sample: true,
    location: 'San Roque',
    type: 'Fire',
    severity: 'Green',
    status: 'Active',
    activatedAt: daysAgo(7),
    description: 'Standard fire monitoring is in place for this area.',
    position: [10.2555, 123.848],
  },
];