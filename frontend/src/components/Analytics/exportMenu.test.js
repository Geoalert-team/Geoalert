import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import ExportMenu from './ExportMenu';

beforeAll(() => { global.IS_REACT_ACT_ENVIRONMENT = true; });

function mount(props) {
  const el = document.createElement('div');
  document.body.appendChild(el);
  act(() => { createRoot(el).render(<ExportMenu onExport={() => {}} {...props} />); });
  return el;
}
const button = (el, text) => [...el.querySelectorAll('button')].find((b) => b.textContent === text);

test('opens, exports the chosen way, closes', () => {
  const onExport = jest.fn();
  const el = mount({ onExport });
  act(() => { button(el, 'Export').click(); });
  expect(button(el, 'Export').getAttribute('aria-expanded')).toBe('true');
  act(() => { button(el, 'Save as PDF').click(); });
  expect(onExport).toHaveBeenCalledWith('pdf');
  expect(button(el, 'Save as PDF')).toBeUndefined();
});

test('Escape closes the menu', () => {
  const el = mount({});
  act(() => { button(el, 'Export').click(); });
  act(() => { document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true })); });
  expect(button(el, 'Print')).toBeUndefined();
});

test('disabled while busy', () => {
  expect(button(mount({ disabled: true }), 'Export').disabled).toBe(true);
});

test('a menu hidden while busy does not reopen by itself', () => {
  const el = document.createElement('div');
  document.body.appendChild(el);
  const root = createRoot(el);
  act(() => { root.render(<ExportMenu onExport={() => {}} />); });
  act(() => { button(el, 'Export').click(); });
  act(() => { root.render(<ExportMenu onExport={() => {}} disabled />); });
  act(() => { root.render(<ExportMenu onExport={() => {}} />); });
  expect(button(el, 'Print')).toBeUndefined();
  expect(button(el, 'Export').getAttribute('aria-expanded')).toBe('false');
});
