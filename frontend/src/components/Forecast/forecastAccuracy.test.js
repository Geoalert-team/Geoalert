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

test('a model that did not beat counting stays in use and says so, with the figures', async () => {
  historyApi.forecastAccuracy.mockResolvedValue({ hazards: [{ ...tested, status: 'in_use_not_better' }] });
  const el = await render();
  expect(el.textContent).toContain('Fire: in use');
  expect(el.textContent).toContain('The model did not beat counting on those months. It stays in use: no hazard is forecast by counting.');
  expect(el.textContent).not.toContain('stays on counting');
  expect(el.querySelectorAll('table')).toHaveLength(2);
});

test('too few records says the hazard is unavailable and shows no scores', async () => {
  historyApi.forecastAccuracy.mockResolvedValue({
    hazards: [{ hazard: 'Fire', status: 'too_few_records', train: { start: '2023-01', end: '2025-12', events: 12 }, test: { start: '2026-01', end: '2026-09', events: 3 } }],
  });
  const el = await render();
  expect(el.textContent).toContain('Fire: unavailable');
  expect(el.textContent).toContain('It has too few records to train and test a model yet (12 to train on, 3 to test on), so the likelihood shows it as unavailable.');
  expect(el.textContent).not.toContain('stays on counting');
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

// ---- flood and landslide: the version 2 entry ----
// Shapes follow what test_hazard_models writes: hazard_verdict.evaluate (tests, verdict, in_use), hazard_models.credits_for
// and report_limits, prediction_log.logged_summary, and accuracy_entries (kind, status, stale, study, tested_at).
const scores = (ll, brier, skillClim, skillRate, pr, noSkill = 0.0004) => ({
  log_loss: ll, brier, brier_skill_climatology: skillClim, brier_skill_rate: skillRate, pr_auc: pr, no_skill_pr_auc: noSkill,
  roc_auc: 0.9, calibration_slope: 1, rows: 40000, events: 30,
});
const model = (s, when, where) => ({
  scores: s, log_loss_interval: [0.002, 0.003], when, where, levels: [], per_year: [],
});
const eventModel = (hit, before, city, high) => ({ hit_chance: hit, hit_chance_before: before, city_chance: city, high_barangays: high });
const FLOOD_DAYS = [
  ['2021-08-01', 'Dante', 120.5, '100-200 mm'],
  ['2022-09-10', null, 60, '50-100 mm'],
  ['2023-10-02', 'Paeng', 80.25, '50-100 mm'],
  ['2024-07-15', null, 20, 'under 50 mm'],
  ['2025-08-18', 'Egay', 150, '100-200 mm'],
];
const eventRows = FLOOD_DAYS.map(([day, storm, rain, band], i) => ({
  day, subtypes: ['Flood'], storm, rain_1day: rain, rain_3day: rain * 2, band,
  models: {
    two_part: eventModel(0.31 - i * 0.01, i === 1 ? null : 0.05, 0.62, 4),
    logistic_regression: eventModel(0.02, 0.01, 0.2, 0),
  },
}));
const baseline = (s) => ({ scores: s, log_loss_interval: [0, 1], when: {}, where: {}, levels: [], per_year: [] });
const flood = {
  hazard: 'Flood',
  kind: 'rain_terrain',
  status: 'in_use',
  stale: false,
  study: { start: '2021-01-01', end: '2025-12-31' },
  tested_at: '2026-11-16T10:00:00+08:00',
  in_use: 'two_part',
  verdict: {
    adopted: true,
    rule: 'b',
    reasons: ['It was no worse on any event day.', 'The leakage check passed.'],
    leakage_checked: true,
  },
  rows: 40000,
  positives: 30,
  positive_days: 5,
  event_days: 5,
  tests: {
    loso: {
      rows: 40000, days: 1826, event_days: 5, hit_rows: 30, blocks: { event: 5, month: 60 }, reps: 2000,
      models: {
        two_part: model(scores(0.00243, 0.00041, 0.12, 0.08, 0.38),
          { auc: 0.853, log_loss: 0.01, days: 1826, event_days: 5 },
          { auc: 0.71, auc_days: 5, lift: 2.4, hit_rows: 30 }),
        logistic_regression: model(scores(0.00251, 0.00043, 0.05, 0.02, 0.3),
          { auc: 0.6, log_loss: 0.02, days: 1826, event_days: 5 },
          { auc: 0.56, auc_days: 5, lift: 1.1, hit_rows: 30 }),
        climatology: baseline(scores(0.0026, 0.00044, 0, null, 0.0004)),
        rate: baseline(scores(0.0027, 0.00045, -0.01, 0, null)),
        pagasa_bands: { unavailable: 'No training event.' },
      },
      differences: { 'two_part - logistic_regression': { difference: -0.0001, low: -0.0002, high: 0.0001 } },
      breakeven: [{ cutoff: 0.25, false_alarms_per_event: 3 }, { cutoff: 0.15, false_alarms_per_event: 5.6667 }],
    },
    yearly: {},
    events: eventRows,
    outside: null,
  },
  limits: ['First limit sentence.', 'Second limit sentence.', 'Third limit sentence.'],
  credits: [
    'Rain: NASA POWER (CC BY 4.0).',
    'Storm tracks: IBTrACS v04r01 (NOAA NCEI).',
    'Flood exposure: UP NOAH flood hazard maps (ODbL), via the bettergovph mirror.',
    'Buildings: Microsoft Global ML Building Footprints (ODbL).',
  ],
  excluded: [],
  logged: null,
};
const notAdopted = {
  ...flood,
  in_use: 'logistic_regression',
  verdict: {
    adopted: false,
    rule: null,
    reasons: ['It gave a lower chance to the hit barangays on 2025-08-18.', 'The leakage check passed.'],
    leakage_checked: true,
  },
};
const landslide = {
  ...flood,
  hazard: 'Landslide',
  credits: ['Rain: NASA POWER (CC BY 4.0).', 'Landslide timing also learned from NASA Global Landslide Catalog days near Talisay, 2007–2017.'],
  tests: {
    ...flood.tests,
    outside: {
      current: { auc: 0.62, observed: 14, expected: 9.5 },
      catalogue_to_geoalert: { auc: 0.7, slopes: {} },
      geoalert_to_catalogue: { auc: 0.55, slopes: {} },
    },
  },
};
const withEntry = async (entry, extra = {}) => {
  historyApi.forecastAccuracy.mockResolvedValue({ hazards: [tested, entry], combined_note: 'Built from the three tested models; not tested on its own.', ...extra });
  return render();
};
const tableOf = (el, caption) => [...el.querySelectorAll('table')].find((t) => t.querySelector('caption')?.textContent === caption);

test('an adopted two-part model says so with the rule', async () => {
  const el = await withEntry(flood);
  expect(el.textContent).toContain('Flood: two-part model (rain-day chance × barangay share), in use — adopted under rule (b).');
  expect(el.textContent).not.toContain('was tested and not adopted');
});

test('a model not adopted keeps a short heading and lists the reasons below it', async () => {
  const el = await withEntry(notAdopted);
  const heading = [...el.querySelectorAll('h3')].find((h) => h.textContent.startsWith('Flood'));
  expect(heading.textContent).toBe('Flood: pooled logistic regression, in use. The two-part model was tested and not adopted.');
  expect([...el.querySelectorAll('.fc-reasons li')].map((li) => li.textContent)).toEqual([
    'It gave a lower chance to the hit barangays on 2025-08-18.',
    'The leakage check passed.',
  ]);
  // an adopted model's heading says so with the rule and lists no reasons
  const adopted = await withEntry(flood);
  expect(adopted.querySelector('.fc-reasons')).toBeNull();
});

test('the event table lists the five flood days, each model with its four columns', async () => {
  const el = await withEntry(flood);
  const table = tableOf(el, 'Event by event');
  const heads = [...table.querySelectorAll('thead tr')].map((tr) => [...tr.children].map((th) => th.textContent));
  // spec 2.2: date, record subtypes, storm name, 1-day and 3-day rain, the PAGASA band of the 1-day rain
  expect(heads[0].slice(0, 6)).toEqual(['Date', 'Record type', 'Storm', '1-day rain', '3-day rain', 'PAGASA band']);
  expect(heads[1]).toEqual(Array(2).fill(["Hit barangays' chance", 'Day before', 'City chance', 'At High that month']).flat());
  const rows = cells(table);
  expect(rows).toHaveLength(5);
  expect(rows[0]).toEqual(['2021-08-01', 'Flood', 'Dante', '120.5 mm', '241 mm', '100-200 mm', '31.0%', '5.0%', '62.0%', '4', '2.0%', '1.0%', '20.0%', '0']);
  expect(rows[1][2]).toBe('–'); // no storm
  expect(rows[1][7]).toBe('–'); // no day before
});

test('the event table names the record subtypes and the 3-day rain of the real report', async () => {
  const el = await withEntry({
    ...realFlood,
    tests: { ...realFlood.tests, events: [{ ...realFlood.tests.events[0], subtypes: ['FLASH FLOOD', 'ROAD FLOODING'] }, ...realFlood.tests.events.slice(1)] },
  });
  const rows = cells(tableOf(el, 'Event by event'));
  expect(rows.map((r) => r.slice(0, 6))).toEqual([
    ['2025-08-12', 'FLASH FLOOD, ROAD FLOODING', '–', '17.81 mm', '29.52 mm', 'under 50 mm'],
    ['2025-10-07', 'FLASH FLOOD (ROAD)', '–', '9.35 mm', '18.05 mm', 'under 50 mm'],
    ['2025-11-04', 'RIVER OVERFLOW', 'KALMAEGI', '31.43 mm', '100.98 mm', 'under 50 mm'],
  ]);
});

test('the baselines table gives log score, both Brier skills and PR-AUC against no skill', async () => {
  const el = await withEntry(flood);
  const table = tableOf(el, 'Against the baselines');
  expect(table.querySelector('thead').textContent).toBe(
    'ModelLog scoreBrier skill vs overall rateBrier skill vs barangay ratePR-AUC (no skill)',
  );
  const rows = cells(table);
  expect(rows[0]).toEqual(['two-part model (rain-day chance × barangay share)', '0.00243', '0.12', '0.080', '0.38 (0.00040)']);
  expect(rows[1][0]).toBe('pooled logistic regression');
  expect(rows.map((r) => r[0])).toEqual(expect.arrayContaining(['overall rate', 'barangay rate']));
  // a baseline that could not be fitted says so rather than showing numbers
  expect(rows.find((r) => r[0] === 'PAGASA rain bands')).toEqual(['PAGASA rain bands', 'not available: No training event.']);
});

// The real report's sizes (backend/apps/history/data/hazard_model_report.json, flood, 2026-11-16): log scores near
// 0.004, Brier skills and PR-AUCs a few thousandths, hit-day chances down to a few in a million. The toy numbers above
// are hundreds of times larger, so this fixture keeps the card honest about the real ones.
const realScores = (ll, skillClim, skillRate, pr) => scores(ll, 0.00045, skillClim, skillRate, pr, 0.00044807328487503736);
const realEvent = (day, subtype, storm, rain1, rain3, twoPart, current) => ({
  day, subtypes: [subtype], storm, rain_1day: rain1, rain_3day: rain3, band: 'under 50 mm',
  models: { two_part: eventModel(...twoPart, 0), logistic_regression: eventModel(...current, 0) },
});
const realFlood = {
  ...notAdopted,
  verdict: {
    adopted: false,
    rule: null,
    reasons: [
      'The interval of the log-score difference does not lie wholly below zero (0.00016 to 0.000791).',
      'It gave a lower chance to the hit barangays on 2025-08-12.',
      'It gave a lower chance to the hit barangays on 2025-10-07.',
      'It gave the hit barangays a better log score on only 1 of the 5 event days, not more than half.',
      'The leakage check passed: every training day lay more than 14 days from the block it predicted.',
    ],
    leakage_checked: true,
  },
  tests: {
    ...flood.tests,
    loso: {
      ...flood.tests.loso,
      models: {
        two_part: model(realScores(0.0038646222054659236, -0.0014721684942675672, 0.0040107882793524174, 0.0014926076265758294),
          { auc: 0.7196, log_loss: 0.022, days: 1826, event_days: 5 }, { auc: 0.4356, auc_days: 5, lift: 1.2222, hit_rows: 18 }),
        logistic_regression: model(realScores(0.003379873756546659, -0.015227162574909414, -0.009668898628171663, 0.004659085925255327),
          { auc: 0.8201, log_loss: 0.0235, days: 1826, event_days: 5 }, { auc: 0.5673, auc_days: 5, lift: 1.7111, hit_rows: 18 }),
        climatology: baseline(realScores(0.004102978772293719, 0, 0.005474896803037144, 0.00031027748180987365)),
      },
    },
    events: [
      realEvent('2025-08-12', 'FLASH FLOOD', null, 17.81, 29.519999999999996,
        [6.927265354114641e-06, 5.603788093423339e-06, 0.010341047091655842],
        [2.840842809970212e-05, 5.739547392802358e-06, 0.0007687536150150498]),
      realEvent('2025-10-07', 'FLASH FLOOD (ROAD)', null, 9.35, 18.05,
        [3.817551667976775e-06, 1.5013121006373281e-06, 0.006082591481635258],
        [0.0003320796718201402, 0.0001041432177803503, 0.009782431387579393]),
      realEvent('2025-11-04', 'RIVER OVERFLOW', 'KALMAEGI', 31.43, 100.98,
        [0.0017714313072678387, 0.001313033872776064, 0.03579634543864718],
        [0.004346758084885709, 0.006614162957323352, 0.07661847427448687]),
    ],
  },
};

test('real-sized numbers stay readable: PR-AUC beside its no-skill value, small Brier skills and chances', async () => {
  const el = await withEntry(realFlood);
  expect(cells(tableOf(el, 'Against the baselines'))).toEqual([
    ['two-part model (rain-day chance × barangay share)', '0.00386', '-0.0015', '0.0040', '0.0015 (0.00045)'],
    ['pooled logistic regression', '0.00338', '-0.015', '-0.0097', '0.0047 (0.00045)'],
    ['overall rate', '0.00410', '0.0', '0.0055', '0.00031 (0.00045)'],
  ]);
  // the days the verdict names: each model's hit-day chance is a real number, so the reader sees which was lower
  const events = cells(tableOf(el, 'Event by event'));
  const chances = (row) => [row.slice(-8, -5), row.slice(-4, -1)];   // per model: hit, day before, city
  expect(chances(events[0])).toEqual([['0.00069%', '0.00056%', '1.0%'], ['0.0028%', '0.00057%', '0.077%']]);
  expect(chances(events[1])).toEqual([['0.00038%', '0.00015%', '0.61%'], ['0.033%', '0.010%', '0.98%']]);
  expect(chances(events[2])).toEqual([['0.18%', '0.13%', '3.6%'], ['0.43%', '0.66%', '7.7%']]);
  const shown = [...el.querySelectorAll('td')].map((td) => td.textContent);
  expect(shown).not.toContain('0.0%');
  expect(shown.filter((text) => /\de[+-]?\d/.test(text))).toEqual([]);   // never e-notation
  expect(el.textContent).toContain('wholly below zero (0.00016 to 0.000791).');
});

test('when, where and lift lines for each model', async () => {
  const el = await withEntry(flood);
  expect(el.textContent).toContain('When (reported flood days ranked above other days): AUC 0.85 for the two-part model, 0.60 for the pooled logistic regression.');
  expect(el.textContent).toContain('Where (hit barangays ranked above the rest on each reported flood day): AUC 0.71 for the two-part model, 0.56 for the pooled logistic regression.');
  expect(el.textContent).toContain('Lift (hit barangays among the top 5 of the day, against an even spread): 2.4 for the two-part model, 1.1 for the pooled logistic regression.');
});

test('the break-even sentence', async () => {
  const el = await withEntry(flood);
  expect(el.textContent).toContain('At these cut-offs a warning pays off only if acting on about 3 to 5.7 false alarms per real event is acceptable.');
});

test('landslide shows its outside test; flood does not', async () => {
  let el = await withEntry(landslide);
  expect(el.textContent).toContain('Outside the study years (NASA catalogue days): the pooled logistic regression ranked catalogue landslide days with AUC 0.62, and expected 9.5 landslide days against 14 observed.');
  expect(el.textContent).toContain('The two-part "when" model trained on the catalogue era and tested on GeoAlert days: AUC 0.70. Trained on GeoAlert days and tested on the catalogue era: AUC 0.55.');
  el = await withEntry(flood);
  expect(el.textContent).not.toContain('Outside the study years');
});

test('no "Since logging began" block when logged is null', async () => {
  const el = await withEntry(flood);
  expect(el.textContent).not.toContain('Since logging began');
});

test('"Since logging began" shows once rows are logged', async () => {
  const logged = {
    first: '2026-03-01',
    last: '2026-09-30',
    rows: 900,
    events: 3,
    expected: 1.2345,
    events_interval: [0.6, 8.8],
    new_events: [
      { day: '2026-08-02', barangay_id: 4, barangay: 'Bulacao', chance: 0.12, chance_before: 0.05, model_version: 'v2' },
      { day: '2026-08-02', barangay_id: 5, barangay: 'Tabunok', chance: 0.000031, chance_before: 0.00002, model_version: 'v2' },
      { day: '2026-08-09', barangay_id: 5, barangay: 'Tabunok', chance: null, chance_before: null, model_version: null },
    ],
  };
  const el = await withEntry({ ...flood, logged });
  expect(el.textContent).toContain('Since logging began');
  expect(el.textContent).toContain('From 2026-03-01 to 2026-09-30, 900 barangay-days were logged: 3 reported events against 1.23 expected (95% range 0.6 to 8.8).');
  const table = tableOf(el, 'Events since logging began');
  expect([...table.querySelectorAll('thead th')].map((th) => th.textContent)).toEqual(['Date', 'Barangay', 'Chance given', 'Day before']);
  // two barangays hit on the same day are told apart by name, and a small logged chance never reads 0.0%
  expect(cells(table)).toEqual([
    ['2026-08-02', 'Bulacao', '12.0%', '5.0%'],
    ['2026-08-02', 'Tabunok', '0.0031%', '0.0020%'],
    ['2026-08-09', 'Tabunok', 'not logged', 'not logged'],
  ]);
});

test('the credits and the limits show in order', async () => {
  const el = await withEntry(flood);
  expect([...el.querySelectorAll('.fc-credits li')].map((li) => li.textContent)).toEqual(flood.credits);
  expect([...el.querySelectorAll('.fc-limits li')].map((li) => li.textContent)).toEqual(flood.limits);
});

test('a stale report asks for the test to be run again', async () => {
  const el = await withEntry({ ...flood, stale: true });
  expect(el.textContent).toContain('Records have changed since this test was run; run manage.py test_hazard_models again.');
  expect((await withEntry(flood)).textContent).not.toContain('Records have changed');
});

test('an unavailable entry says so with its reason, REPORT_OLD included', async () => {
  const reason = 'The model report is from an older version; run manage.py test_hazard_models.';
  const el = await withEntry({ hazard: 'Landslide', kind: 'rain_terrain', status: 'unavailable', reason });
  expect(el.textContent).toContain('Landslide: rain and terrain model unavailable');
  expect(el.textContent).toContain(reason);
  expect(el.querySelectorAll('table')).toHaveLength(2);
});

test('the sub line and the combined note stay', async () => {
  const el = await withEntry(flood);
  expect(el.textContent).toContain('Every hazard always uses its model; counting is only the benchmark it is tested against, and this card says when a model does not beat it.');
  expect(el.textContent).toContain('Built from the three tested models; not tested on its own.');
});

// ---- fire contender ----
const fireScores = (log, cover) => ({ log_score: log, deviance: 0.7, brier: 0.14, auc: 0.65, top_share: 0.47, coverage80: cover, pit: [1, 2, 3] });
const candidate = {
  in_use: 'current',
  verdict: { adopted: false, reasons: ['Tested, not better: mean log-score difference 0.0123 per barangay-month, 95% interval -0.01 to 0.03, not wholly below zero.'] },
  window: { start: '2025-01', end: '2025-12' },
  models: { current: fireScores(0.5321, 0.8125), pooled_exposure: fireScores(0.5444, 0.7875) },
  difference: { mean: 0.0123, low: -0.01, high: 0.03, dm: { statistic: 0.9, p: 0.3812 } },
  secondary: null,
  dispersion: 1.234,
  dispersion_flag: true,
  morans_i: { i: 0.1234, p: 0.04, flag: true },
};

test('the fire card says the exposure model was tested and not better, with 80% coverage', async () => {
  historyApi.forecastAccuracy.mockResolvedValue({ hazards: [{ ...tested, candidate }] });
  const el = await render();
  expect(el.textContent).toContain('Poisson regression, in use. The pooled Poisson with building exposure was tested on Jan 2025 to Dec 2025.');
  expect(el.textContent).toContain('Tested, not better: mean log-score difference 0.0123');
  expect(cells(tableOf(el, 'Fire models side by side'))).toEqual([
    ['Poisson regression (in use)', '0.532', '81%'],
    ['pooled Poisson with building exposure', '0.544', '79%'],
  ]);
  expect(el.textContent).toContain('Diebold-Mariano test of the difference: p = 0.38.');
  expect(el.textContent).toContain('Counts spread wider than a Poisson (dispersion 1.23; 1 is a Poisson spread).');
  expect(el.textContent).toContain("Errors cluster in neighbouring barangays (Moran's I 0.12, p = 0.04).");
});

test('a fire comparison that did not run shows only its reason', async () => {
  const untested = {
    in_use: 'current',
    verdict: { adopted: false, reasons: ['Too few fires to compare.'] },
    window: null,
    models: { current: null, pooled_exposure: null },
    difference: null,
    secondary: null,
    dispersion: null,
    dispersion_flag: false,
    morans_i: null,
  };
  historyApi.forecastAccuracy.mockResolvedValue({ hazards: [{ ...tested, candidate: untested }] });
  const el = await render();
  expect(el.textContent).toContain('Too few fires to compare.');
  expect(tableOf(el, 'Fire models side by side')).toBeUndefined();
});

test('fire shows its logged block too', async () => {
  const logged = { first: '2026-01-01', last: '2026-03-01', rows: 66, events: 2, expected: 1.5, events_interval: [0.2, 7.2], new_events: [] };
  historyApi.forecastAccuracy.mockResolvedValue({ hazards: [{ ...tested, candidate, logged }] });
  expect((await render()).textContent).toContain('Since logging began');
});
