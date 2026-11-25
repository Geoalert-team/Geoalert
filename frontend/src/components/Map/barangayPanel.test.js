import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import BarangayPanel from './BarangayPanel';
import { landslideLegend } from '../Forecast/forecastLevels';

// The panel's own fetch and the past-hazards section are not what is tested here (a plain function:
// react-scripts resets jest.fn implementations before each test)
jest.mock('../../api/barangaysApi', () => ({
  barangaysApi: { hazards: () => Promise.resolve({ inside: [], crossing: [] }) },
}));
jest.mock('./AreaHistory', () => () => null);

beforeAll(() => { global.IS_REACT_ACT_ENVIRONMENT = true; });

// A barangay's landslide_results rows (GET /api/history/forecast/ with Landslide asked)
const rows = [
  { purok_id: 1, barangay_id: 9, level: 'Green', uncertain: false, not_assessed_reason: null, estimated_outline: false },
  { purok_id: 2, barangay_id: 9, level: 'Red', uncertain: true, not_assessed_reason: null, estimated_outline: false },
  { purok_id: 3, barangay_id: 9, level: 'Orange', uncertain: false, not_assessed_reason: null, estimated_outline: true },
  { purok_id: 4, barangay_id: 9, level: null, uncertain: false, not_assessed_reason: 'No buildings or roads in this area',
    estimated_outline: false },
];
const purokNames = new Map(rows.map((r) => [String(r.purok_id), `Purok ${r.purok_id}`]));
const barangay = { id: 9, name: 'Manipis', municipality: 'Talisay City' };

async function render(props) {
  const el = document.createElement('div');
  await act(async () => {
    createRoot(el).render(
      <BarangayPanel barangay={barangay} hazards={[]} open onClose={() => {}} onSelectHazard={() => {}}
        view="likely" purokNames={purokNames} {...props} />,
    );
  });
  return el;
}

const section = (el, title) => [...el.querySelectorAll('.pm-tabpanel')]
  .find((s) => s.querySelector('h3')?.textContent === title);

// Final review FM11: the landslide wiring of the barangay panel, rendered
test("with Landslide ticked the panel lists the barangay's puroks by landslide level, in landslide's words", async () => {
  const el = await render({
    likelyTypes: ['Landslide'], landslidePuroks: rows, landslideNote: landslideLegend('model'),
  });
  const part = section(el, 'Landslide susceptibility');
  expect(part).toBeTruthy();
  expect(part.querySelector('p.pm-muted').textContent).toBe(
    'Landslide: where the ground tends to slide (from a machine-learning model; the same in every month, not a '
    + 'forecast of a landslide)',
  );
  const items = [...part.querySelectorAll('.pm-likely-list li')];
  expect(items.map((li) => li.querySelector('strong').textContent)).toEqual(['Purok 2', 'Purok 3', 'Purok 1']);
  expect(items.map((li) => li.querySelector('.pm-likely-figure').textContent)).toEqual([
    'High landslide susceptibility', 'Moderate landslide susceptibility', 'Low landslide susceptibility',
  ]);
  expect(part.textContent).toContain('Uncertain');
  expect(part.textContent).toContain('Not assessed yet');
  expect(part.textContent).toContain('No buildings or roads in this area (1)');
  expect(part.textContent).not.toMatch(/flood/i);
  // Neither flood's section nor fire's: only Landslide is ticked
  expect(section(el, 'Flood susceptibility')).toBeUndefined();
  expect([...el.querySelectorAll('h3')].some((h) => h.textContent.startsWith('Likely fire'))).toBe(false);
});

test('an unavailable landslide model shows its reason and no list', async () => {
  const reason = 'Landslide is unavailable right now: The landslide model has not been trained yet.';
  const el = await render({
    likelyTypes: ['Landslide'], landslidePuroks: [], landslideNote: reason, landslideUnavailable: true,
  });
  const part = section(el, 'Landslide susceptibility');
  expect(part.querySelector('p.pm-muted').textContent).toBe(reason);
  expect(part.querySelector('.pm-likely-list')).toBeNull();
  expect(part.textContent).not.toContain('No landslide levels for this barangay.');
});

test('a barangay with no landslide rows says so in landslide words', async () => {
  const el = await render({ likelyTypes: ['Landslide'], landslidePuroks: [], landslideNote: landslideLegend('noah') });
  const part = section(el, 'Landslide susceptibility');
  expect(part.textContent).toContain("from UP NOAH's landslide hazard map");
  expect(part.textContent).toContain('No landslide levels for this barangay.');
});

test('flood and landslide ticked together each get their own section', async () => {
  const el = await render({
    likelyTypes: ['Flood', 'Landslide'], floodPuroks: [], floodNote: 'Flood note', landslidePuroks: rows,
    landslideNote: landslideLegend('model'),
  });
  expect(section(el, 'Flood susceptibility').textContent).toContain('No flood levels for this barangay.');
  expect(section(el, 'Landslide susceptibility').textContent).toContain('High landslide susceptibility');
  expect(section(el, 'Flood susceptibility').textContent).not.toContain('landslide');
});

test('outside the likely view there is no landslide section', async () => {
  const el = await render({ view: 'past', likelyTypes: ['Landslide'], landslidePuroks: rows });
  expect(section(el, 'Landslide susceptibility')).toBeUndefined();
});
