import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import ForecastAccuracy from './ForecastAccuracy';
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

test('flood and landslide are named as being rebuilt', async () => {
  historyApi.forecastAccuracy.mockResolvedValue({ hazards: [untrained] });
  const el = await render();
  expect(el.textContent).toContain('Flood and landslide predictions are being rebuilt.');
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
