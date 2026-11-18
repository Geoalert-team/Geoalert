import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import RainWatchOverrideForm from './RainWatchOverrideForm';
import { rainWatchApi } from '../../api/rainWatchApi';

jest.mock('../../api/rainWatchApi', () => ({
  rainWatchApi: { createOverride: jest.fn() },
}));

beforeAll(() => { global.IS_REACT_ACT_ENVIRONMENT = true; });
beforeEach(() => { jest.clearAllMocks(); });

async function render(props) {
  const el = document.createElement('div');
  document.body.appendChild(el);
  await act(async () => { createRoot(el).render(<RainWatchOverrideForm {...props} />); });
  return el;
}
async function type(input, value) {
  const setter = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(input), 'value').set;
  await act(async () => { setter.call(input, value); input.dispatchEvent(new Event('input', { bubbles: true })); });
}
const submit = (el) => act(async () => { el.querySelector('form').dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })); });

test('a blank note is refused and the API is not called', async () => {
  const el = await render({ onSaved: jest.fn(), onCancel: jest.fn() });
  expect(el.querySelector('textarea').placeholder).toBe('e.g. PAGASA Visayas heavy rainfall warning #3, Orange');
  await submit(el);
  expect(el.textContent).toContain('Add a note saying where the warning came from.');
  expect(rainWatchApi.createOverride).not.toHaveBeenCalled();
});

test('a valid submit sends the ISO end time, about 12 hours ahead', async () => {
  rainWatchApi.createOverride.mockResolvedValue({ id: 1 });
  const onSaved = jest.fn();
  const el = await render({ onSaved, onCancel: jest.fn() });
  await type(el.querySelector('textarea'), 'PAGASA warning #3');
  await submit(el);
  expect(rainWatchApi.createOverride).toHaveBeenCalledTimes(1);
  const arg = rainWatchApi.createOverride.mock.calls[0][0];
  expect(arg).toMatchObject({ hazard: 'Both', level: 'Orange', note: 'PAGASA warning #3' });
  expect(arg.endsAt).toMatch(/^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z$/);
  const hours = (new Date(arg.endsAt) - Date.now()) / 3600000;
  expect(hours).toBeGreaterThan(11.9);
  expect(hours).toBeLessThan(12.1);
  expect(onSaved).toHaveBeenCalled();
});

test("shows the server's note message on a 400", async () => {
  const err = new Error('bad'); err.data = { note: ['Too long for the server.'] };
  rainWatchApi.createOverride.mockRejectedValue(err);
  const onSaved = jest.fn();
  const el = await render({ onSaved, onCancel: jest.fn() });
  await type(el.querySelector('textarea'), 'x');
  await submit(el);
  expect(el.textContent).toContain('Too long for the server.');
  expect(onSaved).not.toHaveBeenCalled();
});

const local = (ms) => {
  const d = new Date(ms); const p = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`;
};

test('an end time more than 72 hours ahead is refused with a message', async () => {
  const el = await render({ onSaved: jest.fn(), onCancel: jest.fn() });
  await type(el.querySelector('textarea'), 'note');
  await type(el.querySelector('input[type="datetime-local"]'), local(Date.now() + 80 * 3600000));
  await submit(el);
  expect(el.textContent).toContain('Choose a time within the next 72 hours.');
  expect(rainWatchApi.createOverride).not.toHaveBeenCalled();
});

test('an end time in the past is refused with a message', async () => {
  const el = await render({ onSaved: jest.fn(), onCancel: jest.fn() });
  await type(el.querySelector('textarea'), 'note');
  await type(el.querySelector('input[type="datetime-local"]'), local(Date.now() - 3600000));
  await submit(el);
  expect(el.textContent).toContain('Choose a time in the future.');
  expect(rainWatchApi.createOverride).not.toHaveBeenCalled();
});

test('F5: says residents see the note when the level is Orange or Red', async () => {
  const el = await render({ onSaved: jest.fn(), onCancel: jest.fn() });
  expect(el.textContent).toContain('Residents see this note when the level is Orange or Red.');
});
