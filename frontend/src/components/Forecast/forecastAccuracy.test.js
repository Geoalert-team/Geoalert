import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import ForecastAccuracy, { FloodModelReport, ForecastAccuracyEntry, UNDER_REVIEW } from './ForecastAccuracy';
import { historyApi } from '../../api/historyApi';

jest.mock('../../api/historyApi', () => ({ historyApi: { forecastAccuracy: jest.fn() } }));

beforeAll(() => { global.IS_REACT_ACT_ENVIRONMENT = true; });
beforeEach(() => { jest.clearAllMocks(); });

async function render() {
  const el = document.createElement('div');
  await act(async () => { createRoot(el).render(<ForecastAccuracy />); });
  return el;
}

const NOT_TRAINED = 'The fire model has not been trained yet.';
// GET /api/history/forecast/accuracy/ before train_fire_model has run (backend views.fire_accuracy_entry)
const untrained = { hazard: 'Fire', kind: 'fire_purok', status: 'unavailable', reason: NOT_TRAINED };

test('an untrained fire model says so with its reason', async () => {
  historyApi.forecastAccuracy.mockResolvedValue({ hazards: [untrained] });
  const el = await render();
  expect(el.textContent).toContain('Fire: unavailable');
  expect(el.textContent).toContain(NOT_TRAINED);
  expect(el.querySelectorAll('table')).toHaveLength(0);
});

test('landslide is named as being rebuilt', async () => {
  historyApi.forecastAccuracy.mockResolvedValue({ hazards: [untrained] });
  const el = await render();
  expect(el.textContent).toContain('Landslide predictions are being rebuilt.');
  expect(el.textContent).not.toContain('Flood and landslide predictions are being rebuilt.');
});

test('no rain credit, combined note or counting benchmark wording any more', async () => {
  historyApi.forecastAccuracy.mockResolvedValue({ hazards: [untrained], combined_note: 'Built from the three tested models; not tested on its own.' });
  const el = await render();
  expect(el.textContent).not.toContain('NASA POWER');
  expect(el.textContent).not.toContain('Built from the three tested models');
  expect(el.textContent).not.toContain('Every hazard always uses its model');
});

test('nothing to test says so', async () => {
  historyApi.forecastAccuracy.mockResolvedValue({ hazards: [] });
  expect((await render()).textContent).toContain('No real records to test a model on yet.');
});

test('it says so when it cannot load', async () => {
  historyApi.forecastAccuracy.mockRejectedValue(new Error('down'));
  expect((await render()).textContent).toContain('The accuracy check could not be loaded right now.');
});

// The report train_fire_model writes, as /forecast/accuracy/ serves it (backend views.fire_accuracy_entry)
const CAVEAT = 'Purok-level scores from past fires are probably optimistic: 151 of the 670 areas were drawn because '
  + 'a fire address named them. Honest purok scores come from fires after the map was frozen (the prediction log).';
const score = (value) => ({ value, low: value * 0.8, high: value * 1.2 });
const scores = {
  log_loss: score(0.031),
  brier: score(0.006),
  roc_auc: score(0.68),
  pr_auc: score(0.02),
  calibration_intercept: score(0.1),
  calibration_slope: score(0.9),
  top10_share: score(0.25),
  top20_share: score(0.41),
  kappa_at_orange: score(0.03),
};
const inUse = {
  hazard: 'Fire',
  kind: 'fire_purok',
  status: 'in_use',
  version: 'logistic_regression@0123456789ab',
  credit: 'Adapted from the City of Pittsburgh Bureau of Fire / Carnegie Mellon Metro21 fire risk model '
    + '(github.com/CityofPittsburgh/fire_risk_analysis, MIT License, © 2017 mmadaio)',
  model: { family: 'logistic_regression', settings: { label: 'C=0.1' } },
  candidates: [
    { family: 'logistic_regression', label: 'C=0.1', log_loss: 0.0312, brier: 0.0061 },
    { family: 'xgboost', label: 'pittsburgh', log_loss: 0.0335, brier: 0.0062 },
    { family: 'neural_network', label: '8 hidden, decay 1', log_loss: 0.0318, brier: 0.0061 },
  ],
  verdict: {
    adopted: false,
    mean: 0.0006,
    low: -0.0002,
    high: 0.0013,
    reasons: ['neural network (8 hidden, decay 1) scored +0.00060 log loss: the simpler logistic regression is kept.'],
  },
  cutoffs: { orange: 0.004, red: 0.012, red_reason: null },
  trained: { start: '2023-01', end: '2026-10', fires: 197, unplaced: [{ date: '2025-03-02', barangay: 'Tabunok' }] },
  test: {
    window: { start: '2026-01', end: '2026-10' },
    rows: 6700,
    fires: 45,
    scores,
    levels: [
      { level: 'Red', rows: 670, share: 0.1, fires: 12, recall: 0.27, precision: 0.018, f1: 0.03, kappa: 0.02 },
      { level: 'Orange', rows: 3350, share: 0.5, fires: 24, recall: 0.8, precision: 0.009, f1: 0.02, kappa: 0.01 },
      { level: 'Green', rows: 2680, share: 0.4, fires: 9, recall: 1, precision: 0.007, f1: 0.01, kappa: null },
    ],
    green_fires: 9,
    comparison: {
      comparison_same_everywhere: scores,
      comparison_buildings: scores,
      comparison_historical_frequency: scores,
    },
  },
  barangay_check: { rows: 220, fires: 40, scores, comparison: { comparison_same_everywhere: scores } },
  sensitivity: { fire_log_named: scores, others: scores, named_areas: 151, other_areas: 519 },
  leave_one_barangay_out: scores,
  caveat: CAVEAT,
  unplaced: [{ date: '2025-03-02', barangay: 'Tabunok' }],
  logged: null,
};

test('FireModelReport renders candidates, verdict, caveat and credit', async () => {
  historyApi.forecastAccuracy.mockResolvedValue({ hazards: [inUse] });
  const el = await render();
  expect(el.textContent).toContain(CAVEAT);
  expect(el.textContent).toContain('City of Pittsburgh');
  expect(el.querySelectorAll('table.fc-candidates tbody tr')).toHaveLength(3);
  expect(el.textContent).toContain('the simpler logistic regression is kept');
  expect(el.textContent).toContain('151');
  expect(el.textContent).toContain('519');
  expect(el.textContent).toContain('9 of 45'); // fires the levels missed in the test
  expect(el.textContent).toContain('Tabunok'); // a fire that names no purok, left out
  expect(el.textContent).toContain('No month has been logged and scored yet');
});

test('FireModelReport shows not trained', async () => {
  historyApi.forecastAccuracy.mockResolvedValue({ hazards: [untrained] });
  const el = await render();
  expect(el.textContent).toContain('The fire model has not been trained yet.');
  expect(el.querySelectorAll('table.fc-candidates')).toHaveLength(0);
});

test('FireModelReport shows the prospective log once a month is scored', async () => {
  const logged = {
    first: '2026-12',
    last: '2027-02',
    rows: 2010,
    months: 3,
    fires_after: 14,
    expected: 12.3,
    scores: { log_loss: 0.03, brier: 0.006, roc_auc: 0.64 },
  };
  historyApi.forecastAccuracy.mockResolvedValue({ hazards: [{ ...inUse, logged }] });
  const el = await render();
  expect(el.textContent).toContain('14 fires');
  expect(el.textContent).toContain('2026-12');
});

// The flood entry: train_flood_model's report as /forecast/accuracy/ serves it (backend views.flood_accuracy_entry),
// shaped like the 2026-11-24 trial run (the NOAH fallback)
const BASIS_NOAH = "From UP NOAH's 25-year flood model, classed by where floods reached in the 2017 UP Mananga flood "
  + 'survey. It shows how flood-prone an area is, not whether a flood is coming, and it is the same in every month.';
const GATES = [
  { gate: "Better than UP NOAH's map on its own", passed: false,
    detail: 'AUC gain 0.028 (95% interval -0.002 to 0.069); Boyce gain -0.084 (-0.198 to 0.097), shown only' },
  { gate: 'GeoAlert Mananga flood points in Red or Orange', passed: true, detail: '4 of 4' },
  { gate: 'Red and Orange cover at most half the buildings', passed: false, detail: '71% of the floodplain buildings' },
  { gate: 'Test data seen last', passed: true,
    detail: 'The choice and the cut-offs were fixed before any test point was loaded.' },
];
const REASONS = [
  "It did not clearly beat UP NOAH's map on its own: the lower end of its AUC gain was -0.002, not above zero.",
  "Red and Orange would cover 71% of the floodplain's buildings, more than half.",
];
const MANANGA_CREDIT = 'Flood survey points: E. C. Paringit and R. S. Otadoy (eds.) (2017), LiDAR Surveys and Flood '
  + 'Mapping of Mananga River, UP Training Center for Applied Geodesy and Photogrammetry / University of San Carlos '
  + '(Phil-LiDAR 1), used for research and education with acknowledgement';
const floodReport = {
  hazard: 'Flood',
  kind: 'flood_purok',
  status: 'in_use',
  version: 'noah_fallback@166f7f69f8eb',
  source: 'noah',
  built_at: '2026-11-24T01:52:03+08:00',
  basis: BASIS_NOAH,
  candidates: [
    { name: 'logistic_regression', boyce: 0.9157, boyce_low: 0.7989, boyce_high: 0.9352, auc: 0.7063 },
    { name: 'maxent_hinge', boyce: 0.7853, boyce_low: 0.5615, boyce_high: 0.8592, auc: 0.6625 },
    { name: 'xgboost', boyce: 0.6916, boyce_low: 0.3463, boyce_high: 0.7773, auc: 0.677 },
    { name: 'neural_network', boyce: 0.7667, boyce_low: 0.6172, boyce_high: 0.8793, auc: 0.7047 },
    { name: 'noah_only', boyce: 1.0, boyce_low: 0.8, boyce_high: 1.0, auc: 0.6783 },
  ],
  choice: {
    chosen: 'logistic_regression',
    comparisons: [
      { candidate: 'maxent_hinge', against: 'logistic_regression', gain: -0.1304, low: -0.2924, high: -0.0167, adopted: false },
    ],
  },
  acceptance: { adopted: false, gates: GATES, reasons: REASONS },
  fallback: { note: "UP NOAH's map missed about a third of the survey's flood spots." },
  survey_spots: 105,
  dry_spots: 2,
  domain_buildings: 9987,
  valid_buildings: 9469,
  temporal_test: {
    mananga_points: [
      { day: '2021-06-12', barangay: 'Dumlog', purok_id: 820, level: 'Red', published_level: 'Red' },
      { day: '2025-11-04', barangay: 'San Isidro', purok_id: 558, level: 'Orange', published_level: 'Green' },
    ],
    elsewhere: [
      { day: '2025-08-12', barangay: 'Manipis', note: 'Not assessed: upland road runoff is a different kind of flood' },
    ],
    eosrs: { boyce: -0.1131, auc: 0.5584, flagged_buildings: 1454,
      note: 'The satellite map is preliminary and less reliable over built-up and vegetated ground.' },
    dry_spots: [
      { score: 0.4455, share_of_flood_spots_scoring_lower: 0.1524 },
      { score: 0.2249, share_of_flood_spots_scoring_lower: 0.019 },
    ],
  },
  barangay_check: [
    { barangay: 'Biasong', buildings: 1286, share_red_orange: 0.9145, tino_record: true, any_flood_record: true },
    { barangay: 'Tisa', buildings: 2140, share_red_orange: 0.02, tino_record: false, any_flood_record: false },
  ],
  classes: {
    levels: {
      Red: { puroks: 151, buildings: 8288, field_spots: 58 },
      Orange: { puroks: 187, buildings: 10964, field_spots: 37 },
      Green: { puroks: 271, buildings: 14684, field_spots: 10 },
    },
    not_assessed: { 'No NOAH flood model information here': 41, 'No buildings in this area': 20 },
  },
  limits: ['This is not a forecast: it is the same in every month and does not say a flood is coming.'],
  credits: [MANANGA_CREDIT, 'UP NOAH flood hazard maps (ODbL), via the bettergovph mirror'],
  since_publishing: { n: 0, in_red_orange: 0, under_review: false, misses: [] },
};

async function renderNode(node) {
  const el = document.createElement('div');
  await act(async () => { createRoot(el).render(node); });
  return el;
}

test('the card shows the flood verdict, gates and credits', async () => {
  const el = await renderNode(<FloodModelReport report={floodReport} />);
  expect(el.textContent).toContain('NOAH fallback');
  expect(el.textContent).toContain(BASIS_NOAH);
  expect(el.textContent).toContain("UP NOAH's map missed about a third of the survey's flood spots.");
  GATES.forEach((g) => expect(el.textContent).toContain(g.detail));
  REASONS.forEach((r) => expect(el.textContent).toContain(r));
  expect(el.querySelectorAll('table.fc-candidates tbody tr')).toHaveLength(5);
  expect(el.textContent).toContain('0.92 (0.80–0.94)'); // Boyce with its interval
  expect(el.textContent).toContain(MANANGA_CREDIT);
  expect(el.textContent).not.toContain(UNDER_REVIEW);
});

test('the flood card shows the temporal test, the barangay check and the classes', async () => {
  const el = await renderNode(<FloodModelReport report={floodReport} />);
  expect(el.textContent).toContain('2021-06-12');
  expect(el.textContent).toContain('San Isidro');
  expect(el.textContent).toContain('Moderate flood susceptibility');
  expect(el.textContent).toContain('upland road runoff is a different kind of flood');
  expect(el.textContent).toContain('1,454');
  expect(el.textContent).toContain('15%'); // a dry spot: flooded spots that scored lower
  expect(el.textContent).toContain('Tisa');
  expect(el.textContent).toContain('91%'); // Biasong's share in Red or Orange
  expect(el.textContent).toContain('8,288');
  expect(el.textContent).toContain('No NOAH flood model information here');
  expect(el.textContent).toContain('This is not a forecast');
});

test('under the NOAH fallback the tests are named as the unused model\'s, beside the map in use', async () => {
  const el = await renderNode(<FloodModelReport report={floodReport} />);
  expect(el.textContent).toContain('the machine-learning model, which is not in use');
  const [, row] = [...el.querySelectorAll('table')].find((t) => t.textContent.includes('San Isidro'))
    .querySelectorAll('tbody tr');
  expect([...row.querySelectorAll('td')].map((td) => td.textContent))
    .toEqual(['2025-11-04', 'San Isidro', 'Moderate flood susceptibility', 'Low flood susceptibility (within the assessed floodplain)']);
  expect(el.textContent).toContain('The barangay check (the machine-learning model, not in use)');
});

test('an adopted model says the model is in use, not the fallback', async () => {
  const adopted = { ...floodReport, source: 'model', version: 'logistic_regression@0123',
    acceptance: { adopted: true, gates: GATES.map((g) => ({ ...g, passed: true })), reasons: [] } };
  const el = await renderNode(<FloodModelReport report={adopted} />);
  expect(el.textContent).toContain('In use: the machine-learning model (Logistic regression)');
  expect(el.textContent).not.toContain('NOAH fallback');
  expect(el.textContent).not.toContain('not in use');
});

test('under review is shown when monitoring flags it', async () => {
  const flagged = { ...floodReport, since_publishing: { n: 11, in_red_orange: 8, under_review: true,
    misses: [{ day: '2027-01-05', purok: 'Purok 3', level: 'Green' }] } };
  const el = await renderNode(<FloodModelReport report={flagged} />);
  expect(el.textContent).toContain(UNDER_REVIEW);
  expect(el.textContent).toContain('8 of 11');
  expect(el.textContent).toContain('2027-01-05');
});

test('an unavailable flood entry shows its reason', async () => {
  const el = await renderNode(<ForecastAccuracyEntry entry={{ hazard: 'Flood', kind: 'flood_purok', status: 'unavailable',
    reason: 'The flood model has not been trained yet.' }} />);
  expect(el.textContent).toContain('Flood: unavailable');
  expect(el.textContent).toContain('The flood model has not been trained yet.');
});

test('the page shows the fire and the flood entries', async () => {
  historyApi.forecastAccuracy.mockResolvedValue({ hazards: [untrained, floodReport] });
  const el = await render();
  expect(el.textContent).toContain('Fire: unavailable');
  expect(el.textContent).toContain('NOAH fallback');
  expect(el.querySelectorAll('table.fc-candidates tbody tr')).toHaveLength(5);
});

// A flood report built on GeoAlert's own located flood records (train_flood_model --own)
const geoReport = {
  ...floodReport,
  source: 'geoalert',
  version: 'own@abc123',
  basis: "From a machine-learning model of where floods reached in GeoAlert's own located flood records, with UP NOAH "
    + 'flood depths and terrain. It shows how flood-prone an area is, not whether a flood is coming, and it is the same '
    + 'in every month.',
  survey_spots: undefined,
  own_spots: 120,
  fallback: undefined,
  acceptance: {
    adopted: true,
    gates: [{ gate: 'Held-back wet season spots in Red or Orange', passed: true, detail: '2 of 2' }],
    reasons: [],
  },
  credits: ['UP NOAH flood hazard maps (ODbL), via the bettergovph mirror'],
  temporal_test: {
    season: 2026,
    held_back: [
      { day: '2026-07-04', barangay: 'Dumlog', purok_id: 820, level: 'Red' },
      { day: '2026-09-18', barangay: 'San Isidro', purok_id: 558, level: 'Orange' },
    ],
    eosrs: floodReport.temporal_test.eosrs,
  },
};

test('a geoalert report holds back the wet season and names no survey', async () => {
  const el = await renderNode(<FloodModelReport report={geoReport} />);
  expect(el.textContent).toContain("The 2026 wet season's flood spots, held back");
  const rows = el.querySelectorAll('table:not(.fc-candidates) caption + thead + tbody tr');
  expect(rows).toHaveLength(2);
  expect(rows[0].textContent).toContain('2026-07-04');
  expect(rows[0].textContent).toContain('Dumlog');
  expect(rows[1].textContent).toContain('San Isidro');
  expect(rows[1].textContent).toContain('Moderate flood susceptibility');
  expect(el.textContent).toContain('120 flooded');
  expect(el.textContent).not.toContain('Mananga');
  expect(el.textContent).not.toMatch(/survey/i);
});

// Final review P7: two held-back spots can share a day and a purok
test('held-back spots on the same day in the same purok both show, with no key warning', async () => {
  const spy = jest.spyOn(console, 'error').mockImplementation(() => {});
  const spot = { day: '2026-07-04', barangay: 'Dumlog', purok_id: 820, level: 'Red' };
  const twice = { ...geoReport, temporal_test: { ...geoReport.temporal_test, held_back: [spot, { ...spot }] } };
  try {
    const el = await renderNode(<FloodModelReport report={twice} />);
    expect(el.querySelectorAll('table:not(.fc-candidates) caption + thead + tbody tr')).toHaveLength(2);
    expect(spy.mock.calls.flat().join(' ')).not.toMatch(/same key/);
  } finally {
    spy.mockRestore();
  }
});
