import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { MemoryRouter } from 'react-router-dom';
import RoleMenu, { CLOSE_DELAY } from './RoleMenu';

beforeAll(() => { global.IS_REACT_ACT_ENVIRONMENT = true; });
beforeEach(() => { jest.useFakeTimers(); });
afterEach(() => { jest.useRealTimers(); });

const LINKS = [
  { to: '/app/dashboard', label: 'Dashboard' },
  { to: '/app/history', label: 'History' },
  { to: '/app/reports', label: 'Reports' },
  { to: '/app/security', label: 'Security' },
];

function render(path = '/') {
  const el = document.createElement('div');
  document.body.appendChild(el);
  act(() => {
    createRoot(el).render(
      <MemoryRouter initialEntries={[path]} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <RoleMenu links={LINKS} />
      </MemoryRouter>,
    );
  });
  return el;
}
const btn = (el) => el.querySelector('.pn-role-btn');
const items = (el) => [...el.querySelectorAll('.pn-role-menu a')].map((a) => a.textContent);
// React's onPointerEnter/onPointerLeave listen for pointerover/pointerout with
// a relatedTarget; jsdom has no PointerEvent, so pointerType is set by hand
function pointer(node, type, pointerType) {
  const e = new MouseEvent(type, { bubbles: true, relatedTarget: document.body });
  Object.defineProperty(e, 'pointerType', { value: pointerType });
  act(() => { node.dispatchEvent(e); });
}
const hover = (node, kind = 'mouse') => pointer(node, 'pointerover', kind);
const unhover = (node, kind = 'mouse') => pointer(node, 'pointerout', kind);

test('closed at first, and named for screen readers', () => {
  const el = render();
  expect(items(el)).toEqual([]);
  expect(btn(el).getAttribute('aria-expanded')).toBe('false');
  expect(btn(el).getAttribute('aria-label')).toBe('Staff menu');
});

test('hovering opens it; leaving closes it after a short grace period', () => {
  const el = render();
  hover(btn(el));
  expect(items(el)).toEqual(['Dashboard', 'History', 'Reports', 'Security']);
  unhover(el.querySelector('.pn-role'));
  expect(items(el)).toHaveLength(4); // not yet: the pointer may be on its way into the menu
  act(() => { jest.advanceTimersByTime(CLOSE_DELAY + 10); });
  expect(items(el)).toEqual([]);
});

test('moving back in during the grace period keeps it open', () => {
  const el = render();
  hover(btn(el));
  unhover(el.querySelector('.pn-role'));
  hover(el.querySelector('.pn-role-menu'));
  act(() => { jest.advanceTimersByTime(CLOSE_DELAY + 10); });
  expect(items(el)).toHaveLength(4);
});

test('click opens and closes it (touch screens have no hover)', () => {
  const el = render();
  act(() => { btn(el).click(); });
  expect(btn(el).getAttribute('aria-expanded')).toBe('true');
  act(() => { btn(el).click(); });
  expect(items(el)).toEqual([]);
});

test('Escape closes it and puts focus back on the icon', () => {
  const el = render();
  act(() => { btn(el).click(); });
  act(() => { el.querySelector('.pn-role-menu a').focus(); });
  act(() => { el.querySelector('.pn-role-menu a').dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true })); });
  expect(items(el)).toEqual([]);
  expect(document.activeElement).toBe(btn(el));
});

test('choosing a page closes it', () => {
  const el = render();
  act(() => { btn(el).click(); });
  act(() => { el.querySelector('.pn-role-menu a').click(); });
  expect(items(el)).toEqual([]);
});

test('on a staff page the icon is highlighted and the page marked inside', () => {
  const el = render('/app/history');
  expect(btn(el).classList.contains('is-active')).toBe(true);
  act(() => { btn(el).click(); });
  expect(el.querySelector('.pn-role-menu a.is-active').textContent).toBe('History');
});

test('on a public page the icon is not highlighted', () => {
  expect(btn(render('/what-to-do')).classList.contains('is-active')).toBe(false);
});

test('a tap opens it and it stays open (a tap sends a fake hover before its click)', () => {
  const el = render();
  hover(btn(el), 'touch');
  act(() => { btn(el).click(); });
  expect(items(el)).toHaveLength(4);
});

test('a click after hovering pins it open; leaving no longer closes it; a second click does', () => {
  const el = render();
  hover(btn(el));
  act(() => { btn(el).click(); });
  unhover(el.querySelector('.pn-role'));
  act(() => { jest.advanceTimersByTime(CLOSE_DELAY + 10); });
  expect(items(el)).toHaveLength(4);
  act(() => { btn(el).click(); });
  expect(items(el)).toEqual([]);
});
