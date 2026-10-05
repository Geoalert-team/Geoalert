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

// ---------------------------------------------------------------------------
// TEST PINS: shown on top of the real hazards, for trying out the map.
// (The Poblacion flood and Bulacao fire tests already live in Supabase, so they're not repeated here.)
// They live only in this file (nothing is saved to the database), so you can
// add, move or delete them freely. Set SHOW_TEST_PINS to false before committing.
//
// Each pin needs: a unique id, type ('Flood' | 'Fire' | 'Landslide'),
// severity ('Red' = Extreme, 'Orange' = Moderate, 'Green' = Low) and a
// position [latitude, longitude]. Tip: right-click a spot in Google Maps to copy it.
// ---------------------------------------------------------------------------

export const SHOW_TEST_PINS = false;

export const TEST_HAZARDS = [
  {
    id: 'test-fire-gym',
    sample: true,
    location: 'Poblacion',
    type: 'Fire',
    severity: 'Red',
    status: 'Active',
    activatedAt: daysAgo(0),
    description: 'Test fire near Gymnasium 2, overlapping the Poblacion flood in Supabase.',
    verificationStatus: 'Pending',
    position: [10.2456, 123.8475],
  },
  {
    id: 'test-landslide-maghaway',
    sample: true,
    location: 'Maghaway',
    type: 'Landslide',
    severity: 'Red',
    status: 'Active',
    activatedAt: daysAgo(1),
    description: 'Test landslide on the upland slopes.',
    verificationStatus: 'Disputed',
    verificationNote: 'Test note: only minor soil movement seen on the road.',
    position: [10.2775, 123.8178],
  },
];