import React, { act, useState } from 'react';
import { createRoot } from 'react-dom/client';
import FilterBar from './FilterBar';
import { DEFAULT_FILTERS } from './filters';

beforeAll(() => { global.IS_REACT_ACT_ENVIRONMENT = true; });

const today = new Date(2026, 10, 24);
const hazardTypes = [{ id: 1, name: 'Fire' }, { id: 2, name: 'Flood' }];
const barangays = [{ id: 7, name: 'Lagtang' }, { id: 3, name: 'Biasong' }];

async function render(ui) {
  const el = document.createElement('div');
  document.body.appendChild(el);
  await act(async () => { createRoot(el).render(ui); });
  return el;
}

// A parent that holds the filters, as the page does
function Harness({ onChange, start = DEFAULT_FILTERS }) {
  const [filters, setFilters] = useState(start);
  return (
    <FilterBar
      filters={filters}
      onChange={(patch) => { onChange(patch); setFilters((prev) => ({ ...prev, ...patch })); }}
      onReset={() => setFilters(DEFAULT_FILTERS)}
      hazardTypes={hazardTypes}
      barangays={barangays}
      today={today}
    />
  );
}

const button = (el, text) => [...el.querySelectorAll('button')].find((b) => b.textContent === text);

test('apply mode: choices wait for Apply, which sends them once', async () => {
  const onChange = jest.fn();
  const el = await render(
    <FilterBar filters={DEFAULT_FILTERS} onChange={onChange} onReset={jest.fn()} mode="apply"
      hazardTypes={hazardTypes} barangays={barangays} today={today} />,
  );
  expect(button(el, 'Apply').disabled).toBe(true); // nothing changed yet
  await act(async () => { button(el, '6 months').click(); });
  expect(onChange).not.toHaveBeenCalled();
  expect(el.textContent).toContain('Not applied yet');
  expect(button(el, 'Apply').disabled).toBe(false);
  await act(async () => { button(el, 'Apply').click(); });
  expect(onChange).toHaveBeenCalledTimes(1);
  expect(onChange).toHaveBeenCalledWith({ ...DEFAULT_FILTERS, period: '6m' });
});

test('apply mode: going to Custom and back leaves nothing to apply', async () => {
  const onChange = jest.fn();
  const el = await render(
    <FilterBar filters={DEFAULT_FILTERS} onChange={onChange} onReset={jest.fn()} mode="apply"
      hazardTypes={hazardTypes} barangays={barangays} today={today} />,
  );
  await act(async () => { button(el, 'Custom').click(); });
  await act(async () => { button(el, '12 months').click(); });
  expect(button(el, 'Apply').disabled).toBe(true);
  expect(el.textContent).not.toContain('Not applied yet');
});

test('live mode: a typed date is sent when the field is left, not on every keystroke', async () => {
  const onChange = jest.fn();
  const el = await render(
    <Harness onChange={onChange} start={{ ...DEFAULT_FILTERS, period: 'custom', from: '2026-01-01', to: '2026-03-01' }} />,
  );
  const from = el.querySelector('input[type="date"]');
  const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
  await act(async () => {
    setter.call(from, '0202-01-01');
    from.dispatchEvent(new Event('input', { bubbles: true }));
    setter.call(from, '2025-01-01');
    from.dispatchEvent(new Event('input', { bubbles: true }));
  });
  expect(onChange).not.toHaveBeenCalled();
  await act(async () => { from.dispatchEvent(new FocusEvent('focusout', { bubbles: true })); });
  expect(onChange).toHaveBeenCalledTimes(1);
  expect(onChange).toHaveBeenCalledWith({ from: '2025-01-01' });
});

test('trend presets on the trend page', async () => {
  const el = await render(
    <FilterBar filters={{ ...DEFAULT_FILTERS, period: 'all' }} onChange={jest.fn()} onReset={jest.fn()} kind="trends"
      hazardTypes={hazardTypes} barangays={barangays} today={today} />,
  );
  expect([...el.querySelectorAll('.ra-chip')].map((b) => b.textContent))
    .toEqual(['All records', '10 years', '5 years', '3 years', 'This year', 'Custom']);
});

test('a preset sends only the period', async () => {
  const onChange = jest.fn();
  const el = await render(<Harness onChange={onChange} />);
  expect(button(el, '12 months').getAttribute('aria-pressed')).toBe('true');
  await act(async () => { button(el, '6 months').click(); });
  expect(onChange).toHaveBeenCalledWith({ period: '6m' });
  expect(button(el, '6 months').getAttribute('aria-pressed')).toBe('true');
  expect(el.textContent).toContain('Showing: Jun 2026 – Nov 2026 · All hazards · All barangays');
});

test('custom shows two dates, starting from the range on screen', async () => {
  const onChange = jest.fn();
  const el = await render(<Harness onChange={onChange} />);
  expect(el.querySelectorAll('input[type="date"]')).toHaveLength(0);
  await act(async () => { button(el, 'Custom').click(); });
  expect(onChange).toHaveBeenCalledWith({ period: 'custom', from: '2025-12-01', to: '2026-11-24' });
  const dates = [...el.querySelectorAll('input[type="date"]')].map((i) => i.value);
  expect(dates).toEqual(['2025-12-01', '2026-11-24']);
});

test('a backwards custom range says so', async () => {
  const el = await render(
    <Harness onChange={jest.fn()} start={{ ...DEFAULT_FILTERS, period: 'custom', from: '2026-02-01', to: '2026-01-01' }} />,
  );
  expect(el.querySelector('[role="alert"]').textContent).toBe('The start date is after the end date.');
});

test('hazard and barangay lists, barangays by name, and Reset once something is picked', async () => {
  const onChange = jest.fn();
  const el = await render(<Harness onChange={onChange} />);
  const [hazard, barangay] = el.querySelectorAll('select');
  expect([...hazard.options].map((o) => o.textContent)).toEqual(['All hazards', 'Fire', 'Flood']);
  expect([...barangay.options].map((o) => o.textContent)).toEqual(['All barangays', 'Biasong', 'Lagtang']);
  expect(button(el, 'Reset')).toBeUndefined();

  const setter = Object.getOwnPropertyDescriptor(window.HTMLSelectElement.prototype, 'value').set;
  await act(async () => {
    setter.call(hazard, '2');
    hazard.dispatchEvent(new Event('change', { bubbles: true }));
  });
  expect(onChange).toHaveBeenCalledWith({ hazard: '2' });
  expect(el.textContent).toContain('· Flood ·');
  await act(async () => { button(el, 'Reset').click(); });
  expect(el.textContent).toContain('All hazards · All barangays');
});
