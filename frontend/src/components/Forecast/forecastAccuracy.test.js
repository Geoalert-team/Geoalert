import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import ForecastAccuracy, {
  FloodModelReport, ForecastAccuracyEntry, LandslideModelReport, UNDER_REVIEW, LANDSLIDE_UNDER_REVIEW,
} from './ForecastAccuracy';
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

test('no "being rebuilt" note for landslide any more, now that its model ships', async () => {
  historyApi.forecastAccuracy.mockResolvedValue({ hazards: [untrained] });
  const el = await render();
  expect(el.textContent).not.toContain('being rebuilt');
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

// ---- Landslide (backend landslide_run.run's report, with views.landslide_accuracy_entry's kind and status) ----
const BASIS_LANDSLIDE_MODEL = 'From a machine-learning model of where landslides started after Philippine typhoons '
  + "(mapped from satellite images), applied to Talisay's terrain, land cover and roads. It shows how prone an area is "
  + 'to sliding, not whether a landslide is coming, and it is the same in every month.';
const BASIS_LANDSLIDE_NOAH = "From UP NOAH's landslide hazard map, classed by where landslides started after Philippine "
  + 'typhoons. It shows how prone an area is to sliding, not whether a landslide is coming, and it is the same in every '
  + 'month.';
const VERSHEL = 'Landslide inventories: NASA Cooperative Open Online Landslide Repository, Vershel et al. (2025), Open '
  + 'inventories of rainfall-triggered landslides, Figshare doi 10.6084/m9.figshare.26972467 (CC BY 4.0)';
const L_GATES = {
  better_than_noah: true, talisay_test: true, not_everything_flagged: true, tests_seen_last: true,
};
const fold = (name, slides, auc, lo, hi) => ({ fold: name, slides, no_points: slides * 3, auc, lo, hi });
const landslideReport = {
  hazard: 'Landslide', kind: 'landslide_purok', status: 'in_use',
  version: 'neural_network@0123456789ab', source: 'model', built_at: '2026-11-26T10:00:00+08:00',
  basis: BASIS_LANDSLIDE_MODEL,
  training_set: {
    chosen: 'ph', rows: 9000, slides: 2250, landcover_ok: true, columns: [],
    events: [
      { event: 'egay', fold: 'egay', region: 'ph', slides: 400, no_points: 1200, weight: 1, used: true },
      { event: 'mangkhut', fold: 'mangkhut', region: 'ph', slides: 1101, no_points: 3303, weight: 1, used: true },
      { event: 'agaton', fold: 'agaton', region: 'ph', slides: 23, no_points: 69, weight: 1, used: true },
      // A world event's key as landslide_inventories builds it: the country, then the event date
      { event: 'south_africa_20220411', fold: 'world', region: 'world', slides: 300, no_points: 900, weight: 1, used: false },
    ],
    world: {
      joined: false, gain: 0.004, lo: -0.02, hi: 0.03, rule: 'World rule text.',
      verdict: 'The world events did not join: their AUC gain on held-out Philippine typhoons was 0.004 (95% interval '
        + '-0.020 to 0.030), not wholly above zero.',
    },
  },
  candidates: [
    { name: 'neural_network', auc: 0.81, lo: 0.77, hi: 0.85, folds: [fold('egay', 400, 0.8, 0.74, 0.86), fold('agaton', 23, 0.7, 0.52, 0.88)] },
    { name: 'logistic_regression', auc: 0.78, lo: 0.74, hi: 0.82, folds: [fold('egay', 400, 0.77, 0.7, 0.83)] },
    { name: 'xgboost', auc: 0.8, lo: 0.76, hi: 0.84, folds: [] },
    { name: 'noah_only', auc: 0.64, lo: 0.6, hi: 0.68, folds: [fold('egay', 400, 0.63, 0.57, 0.69)] },
  ],
  choice: {
    chosen: 'neural_network', rule: 'Rule 2 text.',
    verdict: 'Neural network kept: neither logistic regression nor XGBoost beat it clearly (the lower end of each AUC '
      + 'gain over it was not above zero).',
    comparisons: {},
  },
  acceptance: {
    adopted: true,
    gates: L_GATES,
    labels: {
      better_than_noah: "Better than UP NOAH's landslide map on its own",
      talisay_test: 'Talisay puroks with a located landslide in Red or Orange',
      not_everything_flagged: 'Red and Orange hold at most half of the in-range scoring points of assessed puroks',
      tests_seen_last: 'Test data seen last',
    },
    details: {
      better_than_noah: "AUC gain over UP NOAH's map alone 0.170 (95% interval 0.120 to 0.220) on the held-out "
        + 'Philippine typhoons',
      talisay_test: '2 of 2 in Red or Orange (2 needed)',
      not_everything_flagged: '31% of the in-range scoring points of assessed puroks in Red or Orange',
      tests_seen_last: 'The training set, the choice and the cut-offs were in the report before any Talisay test '
        + 'record or catalogue point was loaded.',
    },
    reasons: [],
  },
  talisay_test: {
    puroks: [
      { purok_id: 11, name: 'Purok 3', barangay: 'Manipis', level: 'Red', published_level: 'Red' },
      { purok_id: 12, name: 'Purok 5', barangay: 'Manipis', level: 'Orange', published_level: 'Orange' },
    ],
    barangay_check: {
      barangays: [{ barangay_id: 1, barangay: 'Manipis', records: 4, points: 800, red_orange: 520,
        share_red_orange: 0.65, published_share_red_orange: 0.65 }],
      rest: { points: 9000, red_orange: 2700, share_red_orange: 0.3, published_share_red_orange: 0.3 },
    },
    catalogue: [{ level: 'Red', published_level: 'Red' }, { level: 'Green', published_level: 'Green' },
      { level: null, published_level: null }],
  },
  in_range: {
    points: 12000, in_range: 11400, share: 0.95, unlike_puroks: 3, outside_by_column: {},
    clipped: { dist_road_m: 140, lc_built: 2210 }, clip_ranges: {},
  },
  classes: {
    levels: { Red: { puroks: 40, points: 3000 }, Orange: { puroks: 70, points: 5000 }, Green: { puroks: 500, points: 20000 } },
    not_assessed: { 'No buildings or roads in this area': 12, 'Its ground is unlike the areas the model learned from': 3 },
    assessed_puroks: 610, flagged_point_share: 0.31,
  },
  stability: { refits: 200, uncertain_puroks: 9 },
  road_check: {},
  limits: ['This is not a forecast: it is the same in every month and does not say a landslide is coming.'],
  credits: [VERSHEL, 'UP NOAH landslide hazard maps (ODbL), via the bettergovph mirror'],
  since_publishing: { n: 0, in_red_orange: 0, under_review: false, misses: [] },
};

test('the card shows the landslide verdict, the NN rule and credits', async () => {
  const el = await renderNode(<LandslideModelReport report={landslideReport} />);
  expect(el.querySelector('h3').textContent).toBe('Landslide: susceptibility by purok');
  expect(el.textContent).toContain('Neural network kept');
  expect(el.textContent).toContain('Vershel et al. (2025)');
  expect(el.textContent).toContain(BASIS_LANDSLIDE_MODEL);
  expect(el.textContent).not.toContain('Fire:');
});

test('the landslide card names the training set, the world verdict and the candidates with intervals', async () => {
  const el = await renderNode(<LandslideModelReport report={landslideReport} />);
  expect(el.textContent).toContain('The world events did not join');
  expect(el.textContent).toContain('Mangkhut');
  expect(el.textContent).toContain('1,101');
  const rows = el.querySelectorAll('table.fc-candidates tbody tr');
  expect(rows).toHaveLength(4);
  expect(rows[0].textContent).toContain('0.81 (0.77–0.85)');
  expect(rows[0].textContent).toContain('chosen');
  expect(rows[3].textContent).toContain("UP NOAH's map on its own (the benchmark)");
  expect(el.textContent).toContain('Agaton'); // a per-fold row
});

test('the landslide card shows each gate, the Talisay test, the in-range share and the classes', async () => {
  const el = await renderNode(<LandslideModelReport report={landslideReport} />);
  expect(el.textContent).toContain("AUC gain over UP NOAH's map alone 0.170");
  expect(el.textContent).toContain('2 of 2 in Red or Orange (2 needed)');
  expect(el.textContent).toContain('Manipis');
  expect(el.textContent).toContain('High landslide susceptibility');
  expect(el.textContent).toContain('Moderate landslide susceptibility');
  expect(el.textContent).toContain('95%'); // in range
  expect(el.textContent).toContain('2,210'); // clipped count
  expect(el.textContent).toContain('Its ground is unlike the areas the model learned from');
  expect(el.textContent).toContain('This is not a forecast');
  expect(el.textContent).not.toContain('flood');
});

test('under review is shown when monitoring flags it', async () => {
  const flagged = { ...landslideReport, since_publishing: { n: 12, in_red_orange: 8, under_review: true,
    misses: [{ day: '2027-02-03', purok: 'Purok 9', level: 'Green' }] } };
  const el = await renderNode(<LandslideModelReport report={flagged} />);
  expect(el.textContent).toContain('Under review: recent landslides fall outside the flagged areas');
  expect(LANDSLIDE_UNDER_REVIEW).toBe('Under review: recent landslides fall outside the flagged areas');
  expect(el.textContent).toContain('8 of 12 located landslides');
  expect(el.textContent).toContain('2027-02-03');
  const calm = await renderNode(<LandslideModelReport report={landslideReport} />);
  expect(calm.textContent).not.toContain('Under review');
});

test("a NOAH fallback uses UP NOAH's basis and shows the failed gate", async () => {
  const fallback = { ...landslideReport, source: 'noah', version: 'noah_fallback@abc', basis: BASIS_LANDSLIDE_NOAH,
    acceptance: { ...landslideReport.acceptance, adopted: false,
      gates: { ...L_GATES, better_than_noah: false },
      reasons: ["It did not clearly beat UP NOAH's landslide map on the held-out Philippine typhoons: the lower end "
        + 'of its AUC gain was -0.010, not above zero.'] } };
  const el = await renderNode(<LandslideModelReport report={fallback} />);
  expect(el.textContent).toContain(BASIS_LANDSLIDE_NOAH);
  expect(el.textContent).toContain('NOAH fallback');
  expect(el.textContent).toContain('not above zero');
  expect(el.textContent).toContain('failed');
});

test('a simpler model that won says why instead of "kept"', async () => {
  const simpler = { ...landslideReport, choice: { ...landslideReport.choice, chosen: 'logistic_regression',
    verdict: 'Logistic regression chosen: its AUC gain over the neural network was 0.030 (95% interval 0.010 to '
      + '0.050), wholly above zero.' } };
  const el = await renderNode(<LandslideModelReport report={simpler} />);
  expect(el.textContent).toContain('Logistic regression chosen');
  expect(el.textContent).not.toContain('Neural network kept');
});

test('an own-data landslide report names the held-back season', async () => {
  const own = { ...landslideReport, source: 'geoalert', own_spots: 34, season: 2026,
    temporal_test: { season: 2026, held_back: [{ purok_id: 11, level: 'Red' }, { purok_id: 12, level: null }] } };
  const el = await renderNode(<LandslideModelReport report={own} />);
  expect(el.textContent).toContain("GeoAlert's own located landslide");
  expect(el.textContent).toContain("The 2026 wet season's landslide spots, held back");
  expect(el.textContent).toContain('34');
});

test('landslide entries route to the landslide card, never to a Fire heading', async () => {
  const el = await renderNode(<ForecastAccuracyEntry entry={landslideReport} />);
  expect(el.textContent).toContain('Landslide: susceptibility by purok');
  expect(el.textContent).not.toContain('Fire:');
  expect(el.textContent).not.toContain('Fire risk model');
});

test('an unavailable landslide entry shows its reason', async () => {
  const el = await renderNode(<ForecastAccuracyEntry entry={{ hazard: 'Landslide', kind: 'landslide_purok',
    status: 'unavailable', reason: 'The landslide model has not been trained yet.' }} />);
  expect(el.textContent).toContain('Landslide: unavailable');
  expect(el.textContent).toContain('The landslide model has not been trained yet.');
});

test('the page shows the fire, flood and landslide entries', async () => {
  historyApi.forecastAccuracy.mockResolvedValue({ hazards: [untrained, floodReport, landslideReport] });
  const el = await render();
  expect(el.textContent).toContain('Fire: unavailable');
  expect(el.textContent).toContain('Flood: susceptibility by purok');
  expect(el.textContent).toContain('Landslide: susceptibility by purok');
});

// ---- Fix round 1 ----
test('an own-data report labels its own event as GeoAlert\'s own, not "elsewhere in the world"', async () => {
  const own = { ...landslideReport, source: 'geoalert', own_spots: 34,
    training_set: { ...landslideReport.training_set, events: [
      ...landslideReport.training_set.events,
      { event: 'talisay', fold: 'talisay', region: 'talisay', slides: 34, no_points: 102, weight: 10, used: true },
    ] } };
  const el = await renderNode(<LandslideModelReport report={own} />);
  const row = [...el.querySelectorAll('tr')].find((r) => r.textContent.startsWith('Talisay'));
  expect([...row.querySelectorAll('td')].map((td) => td.textContent).slice(0, 2))
    .toEqual(['Talisay', "GeoAlert's own located landslides"]);
});

test('under the NOAH fallback the range note and the catalogue line name the model not in use or the map in use', async () => {
  const fb = { ...landslideReport, source: 'noah', basis: BASIS_LANDSLIDE_NOAH,
    talisay_test: { ...landslideReport.talisay_test,
      catalogue: [{ level: 'Red', published_level: 'Green' }, { level: 'Red', published_level: 'Green' }] } };
  const el = await renderNode(<LandslideModelReport report={fb} />);
  expect(el.textContent).toContain('Ground like the training areas (the machine-learning model, not in use)');
  expect(el.textContent).toContain('by the level of their area on the map in use: Low landslide susceptibility 2');
  expect(el.textContent).not.toContain('High landslide susceptibility 2');
});

test('the basis comes from the entry, and no basis means no line', async () => {
  const el = await renderNode(<LandslideModelReport report={landslideReport} />);
  expect(el.textContent).toContain(BASIS_LANDSLIDE_MODEL);
  const none = await renderNode(<LandslideModelReport report={{ ...landslideReport, basis: undefined }} />);
  expect(none.textContent).not.toContain('From a machine-learning model of where landslides started');
});

test('puroks without an id do not collide, and a missing choice or version prints no "undefined"', async () => {
  const spy = jest.spyOn(console, 'error').mockImplementation(() => {});
  try {
    const bare = { ...landslideReport, version: undefined, choice: undefined,
      talisay_test: { ...landslideReport.talisay_test, puroks: [
        { purok_id: null, name: null, barangay: 'Manipis', level: 'Red', published_level: 'Red' },
        { purok_id: null, name: null, barangay: 'Manipis', level: 'Red', published_level: 'Red' },
      ] } };
    const el = await renderNode(<LandslideModelReport report={bare} />);
    expect(el.textContent).not.toContain('undefined');
    expect(el.textContent).toContain('In use: the machine-learning model.');
    // A null key warns 'unique "key"', not 'same key': match any key warning (final review M13.4)
    expect(spy.mock.calls.flat().join(' ')).not.toMatch(/key/);
  } finally {
    spy.mockRestore();
  }
});

test('the checks heading does not claim a fixed count that own mode exceeds', async () => {
  const el = await renderNode(<LandslideModelReport report={landslideReport} />);
  expect(el.textContent).toContain('The four checks');
  expect(el.textContent).not.toContain('all four must pass');
});

// ---- Final review fix wave ----
// F1: spec 3.3, "the card reports how many training rows kept the road clue" (landslide_run's report['road_check'])
const ROAD_CHECK = {
  talisay_steep_road_density: 2.1, steep_deg: 10, share: 0.1, threshold: 0.21, events: { egay: 1.2, paeng: 0.05 },
  rows: 9000, rows_with_road: 7800, events_without_road: ['paeng', 'south_africa_20220411'],
};

test('the card says how many training rows kept the road clue, and which events had none', async () => {
  const el = await renderNode(<LandslideModelReport report={{ ...landslideReport, road_check: ROAD_CHECK }} />);
  expect(el.textContent).toContain('7,800 of 9,000 training rows kept the road clue.');
  expect(el.textContent).toContain(
    "No road clue for the events whose mapped area has under a tenth of Talisay's road density on steep ground: "
    + 'Paeng; South Africa, 11 Apr 2022.',
  );
});

test('every row kept the road clue: no events line', async () => {
  const all = { ...ROAD_CHECK, rows_with_road: 9000, events_without_road: [] };
  const el = await renderNode(<LandslideModelReport report={{ ...landslideReport, road_check: all }} />);
  expect(el.textContent).toContain('9,000 of 9,000 training rows kept the road clue.');
  expect(el.textContent).not.toContain('No road clue');
});

test('a report without the road check keys shows no road line', async () => {
  const empty = await renderNode(<LandslideModelReport report={landslideReport} />); // road_check: {}
  expect(empty.textContent).not.toContain('road clue');
  const none = await renderNode(<LandslideModelReport report={{ ...landslideReport, road_check: undefined }} />);
  expect(none.textContent).not.toContain('road clue');
});

// F1: spec 5.2 step 5, "the card states the recall reached" (flood_rules.Cutoffs, as landslide_run writes it)
const CUT = { red: 0.71, orange: 0.38, red_recall: 0.52, orange_recall: 0.91, target_reached: true };
const RECALL = 'At the cut-offs in use, Red holds 52% of the held-out landslides, and Red and Orange together 91%.';

test('under the levels, the recall the cut-offs in use reach', async () => {
  const el = await renderNode(<LandslideModelReport report={{ ...landslideReport, cutoffs: CUT }} />);
  expect(el.textContent).toContain(RECALL);
  expect(el.textContent).not.toContain('was not reached');
  expect(el.textContent).not.toContain('ten times');
  // the line sits under "The levels"
  const heads = [...el.querySelectorAll('h4')].map((h) => h.textContent);
  const line = [...el.querySelectorAll('p.fc-note')].find((p) => p.textContent.includes('At the cut-offs in use'));
  expect(line.previousElementSibling.querySelector('table')).not.toBeNull();
  expect(heads.indexOf('The levels')).toBeGreaterThan(-1);
});

test('a 90% target the cut-offs could not reach is stated', async () => {
  const short = { ...CUT, orange_recall: 0.84, target_reached: false };
  const el = await renderNode(<LandslideModelReport report={{ ...landslideReport, cutoffs: short }} />);
  expect(el.textContent).toContain('Red holds 52% of the held-out landslides, and Red and Orange together 84%.');
  expect(el.textContent).toContain(
    'The 90% target for Red and Orange was not reached: the scores tie at the bottom, so Orange stops at the last '
    + 'distinct score.',
  );
});

test("under the NOAH fallback the recall is the fallback's cut-offs, not the unused model's", async () => {
  const fb = { ...landslideReport, source: 'noah', basis: BASIS_LANDSLIDE_NOAH, cutoffs: CUT,
    fallback: { cutoffs: { red: 1, orange: 0.67, red_recall: 0.6, orange_recall: 0.88, target_reached: false },
      flagged_share: 0.4, note: 'Fallback note.' } };
  const el = await renderNode(<LandslideModelReport report={fb} />);
  expect(el.textContent).toContain('Red holds 60% of the held-out landslides, and Red and Orange together 88%.');
  expect(el.textContent).toContain('The 90% target for Red and Orange was not reached');
  expect(el.textContent).not.toContain('Red holds 52%');
});

test("in own mode the recall line says GeoAlert's own landslides count ten times", async () => {
  const own = { ...landslideReport, source: 'geoalert', own_spots: 34, cutoffs: CUT };
  const el = await renderNode(<LandslideModelReport report={own} />);
  expect(el.textContent).toContain(`${RECALL} GeoAlert's own landslides count ten times in these shares.`);
});

// Follow-up round 1: a share just under the target must not round up to it and contradict the sentence
test('a Red and Orange share just under 90% never reads as 90% when the target was not reached', async () => {
  const short = { ...CUT, orange_recall: 0.8996, target_reached: false };
  const el = await renderNode(<LandslideModelReport report={{ ...landslideReport, cutoffs: short }} />);
  expect(el.textContent).toContain('Red holds 52% of the held-out landslides, and Red and Orange together 89%.');
  expect(el.textContent).not.toContain('together 90%');
  expect(el.textContent).toContain('The 90% target for Red and Orange was not reached');
  // a whole percent stays whole (0.57 * 100 is 56.99999999999999 in floating point)
  const whole = { ...CUT, orange_recall: 0.57, target_reached: false };
  const el2 = await renderNode(<LandslideModelReport report={{ ...landslideReport, cutoffs: whole }} />);
  expect(el2.textContent).toContain('Red and Orange together 57%.');
  // a reached target keeps today's rounding
  const reached = { ...CUT, orange_recall: 0.9996, target_reached: true };
  const el3 = await renderNode(<LandslideModelReport report={{ ...landslideReport, cutoffs: reached }} />);
  expect(el3.textContent).toContain('Red and Orange together 100%.');
});

// Follow-up round 1: in own mode the training set's count includes GeoAlert's own rows, and the intro says so
test("the training set intro names GeoAlert's own landslides in own mode only", async () => {
  const MODEL_INTRO = '2,250 landslides and the ground around them that did not slide (9,000 rows in all) that the '
    + 'chosen training set holds, from typhoons in the Philippines and, if they joined, events elsewhere in the world.';
  const el = await renderNode(<LandslideModelReport report={landslideReport} />);
  expect(el.textContent).toContain(MODEL_INTRO);
  const own = await renderNode(<LandslideModelReport report={{ ...landslideReport, source: 'geoalert', own_spots: 34 }} />);
  expect(own.textContent).toContain(
    '2,250 landslides and the ground around them that did not slide (9,000 rows in all) that the chosen training set '
    + "holds, from typhoons in the Philippines, GeoAlert's own landslides and, if they joined, events elsewhere in the "
    + 'world.',
  );
  expect(own.textContent).not.toContain(MODEL_INTRO);
});

test('no cut-offs, or cut-offs without their recall, show no recall line', async () => {
  const none = await renderNode(<LandslideModelReport report={landslideReport} />);
  expect(none.textContent).not.toContain('At the cut-offs in use');
  const bare = await renderNode(<LandslideModelReport report={{ ...landslideReport, cutoffs: { red: 0.7, orange: 0.4 } }} />);
  expect(bare.textContent).not.toContain('At the cut-offs in use');
  expect(bare.textContent).not.toContain('was not reached');
});

// F2: the catalogue the Talisay points come from is the test-only Global Landslide Catalog (spec 3.1, 3.4)
test("the catalogue line names NASA's Global Landslide Catalog", async () => {
  const el = await renderNode(<LandslideModelReport report={landslideReport} />);
  expect(el.textContent).toContain(
    "Landslides in NASA's Global Landslide Catalog inside Talisay, by the level of their area: High landslide "
    + 'susceptibility 1; Low landslide susceptibility 1; Not assessed yet 1.',
  );
  expect(el.textContent).not.toContain('NASA catalogue');
});

// FM6: a world event's key reads as its country and date
test('a world event reads as its country and date, not its raw key', async () => {
  const el = await renderNode(<LandslideModelReport report={landslideReport} />);
  const row = [...el.querySelectorAll('tr')].find((r) => r.textContent.includes('Elsewhere in the world'));
  expect(row.querySelector('td').textContent).toBe('South Africa, 11 Apr 2022');
  expect(el.textContent).not.toContain('South_africa');
  expect(el.textContent).not.toContain('20220411');
});

// FM7: in own mode the held-out folds include GeoAlert's own landslides, not only typhoons
test("the per-fold table names held-out events, and in own mode GeoAlert's own landslides", async () => {
  const el = await renderNode(<LandslideModelReport report={landslideReport} />);
  const caption = () => [...el.querySelectorAll('caption')].map((c) => c.textContent)
    .find((t) => t.startsWith('AUC on each'));
  expect(caption()).toBe('AUC on each held-out event (a Philippine typhoon)');
  expect(el.textContent).not.toContain("or GeoAlert's own landslides");
  const ownReport = { ...landslideReport, source: 'geoalert', own_spots: 34,
    candidates: [{ ...landslideReport.candidates[0], folds: [...landslideReport.candidates[0].folds,
      fold('talisay', 34, 0.75, 0.6, 0.9)] }] };
  const own = await renderNode(<LandslideModelReport report={ownReport} />);
  const ownCaption = [...own.querySelectorAll('caption')].map((c) => c.textContent).find((t) => t.startsWith('AUC on each'));
  expect(ownCaption).toBe("AUC on each held-out event (a Philippine typhoon or GeoAlert's own landslides)");
  expect(own.textContent).toContain(
    "Each candidate was scored on landslides it never saw, one held-out event at a time: a Philippine typhoon or "
    + "GeoAlert's own landslides.",
  );
  const table = [...own.querySelectorAll('table')].find((t) => t.querySelector('caption')?.textContent.startsWith('AUC on each'));
  expect([...table.querySelectorAll('th')].map((th) => th.textContent)).toEqual(['Model', 'Event', 'Landslides', 'AUC (95% interval)']);
  expect(own.textContent).not.toContain('held-out typhoon');
});