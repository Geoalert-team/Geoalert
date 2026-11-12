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

const tested = {
  hazard: 'Fire',
  status: 'in_use',
  train: { start: '2023-01', end: '2025-12', events: 170 },
  test: { start: '2026-01', end: '2026-09', events: 47 },
  model: { deviance: 0.7755, brier: 0.1416, auc: 0.6541, top_share: 0.4681 },
  counting: { deviance: 1.1526, brier: 0.1798, auc: 0.6098, top_share: 0.4102 },
  levels: [
    { level: 'High', rows: 49, events: 19, chance: 0.309, happened: 0.286 },
    { level: 'Moderate', rows: 79, events: 20, chance: 0.199, happened: 0.203 },
    { level: 'Low', rows: 70, events: 8, chance: 0.102, happened: 0.086 },
  ],
};

const cells = (table) => [...table.querySelectorAll('tbody tr')].map((tr) => [...tr.children].map((td) => td.textContent));

test('a model in use shows what it trained on, what it was tested on and how it did', async () => {
  historyApi.forecastAccuracy.mockResolvedValue({ hazards: [tested] });
  const el = await render();
  expect(el.textContent).toContain('Fire: the model is in use');
  expect(el.textContent).toContain('Trained on Jan 2023 to Dec 2025 (170 events), tested on Jan 2026 to Sep 2026 (47 events it never saw)');
  const [scores, levels] = el.querySelectorAll('table');
  expect(cells(scores)).toEqual([
    ['Error in the chance (Brier, lower is better)', '0.142', '0.180'],
    ['Events in its top 5 barangays each month', '47%', '41%'],
    ['Ranking skill (AUC, 0.5 is guessing)', '0.65', '0.61'],
  ]);
  expect(cells(levels)[0]).toEqual(['High', '49', '31%', '29%', '19']);
});

test('a model that lost says it stays on counting, with the figures', async () => {
  historyApi.forecastAccuracy.mockResolvedValue({ hazards: [{ ...tested, status: 'not_better' }] });
  const el = await render();
  expect(el.textContent).toContain('Fire: stays on counting');
  expect(el.textContent).toContain('did not beat counting');
  expect(el.querySelectorAll('table')).toHaveLength(2);
});

test('too few records says so and shows no scores', async () => {
  historyApi.forecastAccuracy.mockResolvedValue({
    hazards: [{ hazard: 'Flood', status: 'too_few_records', train: { start: '2023-01', end: '2025-12', events: 12 }, test: { start: '2026-01', end: '2026-09', events: 3 } }],
  });
  const el = await render();
  expect(el.textContent).toContain('Flood: stays on counting');
  expect(el.textContent).toContain('too few records');
  expect(el.querySelector('table')).toBeNull();
});

test('a level with no barangay-months shows a dash, not NaN', async () => {
  const levels = tested.levels.map((l) => (l.level === 'High' ? { ...l, rows: 0, events: 0, chance: null, happened: null } : l));
  historyApi.forecastAccuracy.mockResolvedValue({ hazards: [{ ...tested, levels }] });
  const el = await render();
  expect(cells(el.querySelectorAll('table')[1])[0]).toEqual(['High', '0', '-', '-', '0']);
});

test('nothing to test says so', async () => {
  historyApi.forecastAccuracy.mockResolvedValue({ hazards: [] });
  expect((await render()).textContent).toContain('No real records to test a model on yet.');
});

test('it says so when it cannot load', async () => {
  historyApi.forecastAccuracy.mockRejectedValue(new Error('down'));
  expect((await render()).textContent).toContain('The accuracy check could not be loaded right now.');
});

// ---- rain and terrain models ----
const pooled = (ll, br, roc, pr) => ({ log_loss: ll, brier: br, roc_auc: roc, pr_auc: pr });
const yearRows = (lls) => [2023, 2024, 2025].map((year, i) => ({ year, positives: i + 1, log_loss: lls[i] }));
const rain = {
  hazard: 'Flood',
  kind: 'rain_terrain',
  status: 'in_use',
  stale: false,
  study: { start: '2021-01', end: '2025-12' },
  tested_at: '2026-11-12T00:00:00',
  winner: 'logistic_regression',
  rows: 40000,
  positives: 30,
  positive_days: 12,
  folds: [2023, 2024, 2025].map((y) => ({ test_year: y, train_years: [], train_positives: 1, train_positive_days: 1 })),
  candidates: {
    logistic_regression: { pooled: pooled(0.002433, 0.00041, 0.9284, 0.38), per_year: yearRows([0.0021, 0.0022, 0.0023]) },
    random_forest: { pooled: pooled(0.00246, 0.00042, null, 0.3), per_year: yearRows([0.1, 0.1, 0.1]) },
    xgboost: { pooled: pooled(0.0031, 0.0005, 0.5, 0.2), per_year: yearRows([0.1, 0.1, 0.1]) },
  },
  benchmark: { pooled: pooled(0.0026, 0.00043, 0.61, 0.1), per_year: yearRows([0.003, 0.004, 0.005]) },
  no_skill: { pooled: pooled(0.0027, 0.00044, 0.17, 0.05), per_year: yearRows([0, 0, 0]) },
  calibration: { per_year: [2023, 2024, 2025].map((year) => ({ year, observed: 1, expected: 1.3339 })) },
  monthly_levels: [
    { level: 'High', rows: 0, events: 0, chance: null, happened: null },
    { level: 'Moderate', rows: 50, events: 2, chance: 0.0456, happened: 0.04 },
    { level: 'Low', rows: 900, events: 3, chance: 0.0012, happened: 0.0033 },
  ],
  timing_auc: { auc: 0.853, days: 1096, event_days: 5 },
  place_auc: { mean: 0.56, per_day: [] },
  lobo_auc: { auc: 0.36, per_barangay: [] },
  camp_iv: null,
  sensitivity: null,
  limits: ['First limit sentence.', 'Second limit sentence.', 'Third limit sentence.'],
};
const withRain = async (entry, extra = {}) => {
  historyApi.forecastAccuracy.mockResolvedValue({ hazards: [tested, entry], combined_note: 'Built from the three tested models; not tested on its own.', ...extra });
  return render();
};

test('a rain and terrain model names itself and its test years', async () => {
  const el = await withRain(rain);
  expect(el.textContent).toContain('Flood: rain and terrain model (logistic regression), in use');
  expect(el.textContent).not.toContain('did not beat counting on the years it never saw');
  expect(el.textContent).toContain('Tested on 2023, 2024 and 2025, each year trained only on the years before it: 6 reported rows on 5 days in those years.');
  const tables = [...el.querySelectorAll('table')].slice(2);
  expect(tables).toHaveLength(3);
  tables.forEach((t) => expect(t.closest('.fc-table-wrap')).not.toBeNull());
  expect(cells(tables[0])[0]).toEqual(['logistic regression (in use)', '0.00243', '0.000410', '0.93', '0.38']);
  expect(cells(tables[0]).slice(-2).map((r) => r[0])).toEqual(['Counting benchmark', 'No skill']);
  expect(el.textContent).toContain("Pooled over the three test years. Each year's model has its own base rate, so even the no-skill row's pooled ROC-AUC is not 0.5.");
  expect(cells(tables[1])[0]).toEqual(['2023', '1', '1.33', '0.00210', '0.00300']);
  expect(cells(tables[2])[0]).toEqual(['High', '0', '–', '–']);
  expect(cells(tables[2])[1]).toEqual(['Moderate', '50', '4.6%', '4.0%']);
});

test('not beating counting is said plainly but the model stays', async () => {
  const el = await withRain({ ...rain, status: 'in_use_not_better' });
  expect(el.textContent).toContain('Flood: rain and terrain model (logistic regression), in use — did not beat counting on the years it never saw');
});

const NOT_DEFINED = '– not defined: no reported event in that set.';
const NO_MONTHS = '– no barangay-month was given this level.';
const footnotes = (el) => [...el.querySelectorAll('p.fc-note')].map((p) => p.textContent).filter((t) => t.startsWith('–'));

test('undefined metrics show as a dash with a footnote', async () => {
  const el = await withRain(rain);
  const table1 = [...el.querySelectorAll('table')][2];
  expect(cells(table1)[1][3]).toBe('–');
  // the fixture has both kinds of dash: an undefined ROC-AUC and a level no barangay-month was given
  expect(footnotes(el)).toEqual([NOT_DEFINED, NO_MONTHS]);
});

const allDefined = {
  ...rain,
  candidates: { ...rain.candidates, random_forest: { ...rain.candidates.random_forest, pooled: pooled(0.00246, 0.00042, 0.7, 0.3) } },
};
const everyLevelGiven = rain.monthly_levels.map((l) => (l.rows === 0 ? { ...l, rows: 4, events: 1, chance: 0.31, happened: 0.25 } : l));

test('a level no barangay-month was given has its own footnote, not "not defined"', async () => {
  const el = await withRain(allDefined);
  expect(cells([...el.querySelectorAll('table')][4])[0]).toEqual(['High', '0', '–', '–']);
  expect(footnotes(el)).toEqual([NO_MONTHS]);
});

test('an undefined metric gives only the not-defined footnote', async () => {
  let el = await withRain({ ...rain, monthly_levels: everyLevelGiven });
  expect(footnotes(el)).toEqual([NOT_DEFINED]);
  // an undefined figure in the per-year table counts too
  el = await withRain({ ...allDefined, monthly_levels: everyLevelGiven, calibration: { per_year: [] } });
  expect(cells([...el.querySelectorAll('table')][3])[0][2]).toBe('–');
  expect(footnotes(el)).toEqual([NOT_DEFINED]);
  // and with no dash at all, no footnote
  el = await withRain({ ...allDefined, monthly_levels: everyLevelGiven });
  expect(footnotes(el)).toEqual([]);
});

test('a stale report asks for the test to be run again', async () => {
  const el = await withRain({ ...rain, stale: true });
  expect(el.textContent).toContain('Records have changed since this test was run; run manage.py test_hazard_models again.');
  expect((await withRain(rain)).textContent).not.toContain('Records have changed');
});

test('an unavailable entry says so with its reason', async () => {
  const el = await withRain({ hazard: 'Landslide', kind: 'rain_terrain', status: 'unavailable', reason: 'No report has been made yet.' });
  expect(el.textContent).toContain('Landslide: rain and terrain model unavailable');
  expect(el.textContent).toContain('No report has been made yet.');
  expect(el.querySelectorAll('table')).toHaveLength(2);
});

test('AUC lines say below chance, about chance and not defined', async () => {
  const el = await withRain({ ...rain, lobo_auc: { auc: 0.36 }, place_auc: { mean: 0.56 }, timing_auc: { auc: null, days: 10, event_days: 0 } });
  expect(el.textContent).toContain('Barangays it never saw (each left out of training in turn), ranked by average chance: AUC 0.36 (0.5 is chance, 1 is perfect) — below chance.');
  expect(el.textContent).toContain('Where: hit barangays ranked above the rest on each reported flood day: AUC 0.56 (0.5 is chance, 1 is perfect) — about chance.');
  expect(el.textContent).toContain('When: reported flood days ranked above other days: not defined (it needs both outcomes).');
  expect(el.textContent).toContain('6 reported rows on 0 days');
  const good = await withRain(rain);
  expect(good.textContent).toContain('When: reported flood days ranked above other days: AUC 0.85 (0.5 is chance, 1 is perfect).');
});

test('camp_iv and sensitivity lines', async () => {
  const camp = [{ barangay_id: 4, day: '2025-08-25', chance: 0.002, percentile: 99.2528 }];
  let el = await withRain({ ...rain, hazard: 'Landslide', camp_iv: camp });
  expect(el.textContent).toContain("A landslide in a barangay never seen with one in training (2025-08-25) ranked above 99.3% of that year's barangay-days.");
  el = await withRain({ ...rain, hazard: 'Landslide', camp_iv: [] });
  expect(el.textContent).toContain('No landslide in the last test year fell in a barangay unseen in training.');
  el = await withRain(rain);
  expect(el.textContent).not.toContain('never seen with one in training');
  expect(el.textContent).not.toContain('unseen in training');
  el = await withRain({ ...rain, sensitivity: { log_loss: 0.0024048961, roc_auc: 0.9285, study_positives: 22 } });
  expect(el.textContent).toContain('With no records left out (22 reported barangay-days): log loss 0.00240, ROC-AUC 0.93.');
});

test('the card shows the new sub line, the combined note, the attribution and every limit in order', async () => {
  const el = await withRain(rain);
  expect(el.textContent).toContain('Fire uses its model only if it beats counting. Flood and landslide always use their rain and terrain model, and this card says when it does not beat counting.');
  expect(el.textContent).toContain('Built from the three tested models; not tested on its own.');
  expect(el.textContent).toContain('Rain data by Open-Meteo.com (CC BY 4.0), processed into hazard chances by GeoAlert');
  expect([...el.querySelectorAll('a')].map((a) => a.getAttribute('href'))).toEqual(['https://open-meteo.com/', 'https://creativecommons.org/licenses/by/4.0/']);
  expect([...el.querySelectorAll('.fc-limits li')].map((li) => li.textContent)).toEqual(rain.limits);
});

test('the fire block is unchanged next to a rain entry', async () => {
  const el = await withRain(rain);
  expect(el.textContent).toContain('Fire: the model is in use');
  expect(cells(el.querySelectorAll('table')[0])[2]).toEqual(['Ranking skill (AUC, 0.5 is guessing)', '0.65', '0.61']);
});
