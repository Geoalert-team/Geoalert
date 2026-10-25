import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { MemoryRouter } from 'react-router-dom';
import AccountMenu, { AccountPanel } from './AccountMenu';

beforeAll(() => { global.IS_REACT_ACT_ENVIRONMENT = true; });

const LINKS = [
  { to: '/app/dashboard', label: 'Dashboard', icon: 'grid' },
  { to: '/app/history', label: 'History', icon: 'clock' },
  { to: '/app/reports', label: 'Reports', icon: 'list' },
  { to: '/app/security', label: 'Security', icon: 'shield' },
];
const JUAN = { full_name: 'Juan Dela Cruz', email: 'juan@gmail.com', role: { name: 'DRRMO_Officer' } };

function render({ path = '/', user = JUAN, onLogout = jest.fn(), Component = AccountMenu } = {}) {
  const el = document.createElement('div');
  document.body.appendChild(el);
  act(() => {
    createRoot(el).render(
      <MemoryRouter initialEntries={[path]} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <Component user={user} links={LINKS} onLogout={onLogout} />
      </MemoryRouter>,
    );
  });
  return el;
}
const btn = (el) => el.querySelector('.pn-acct-btn');
const items = (el) => [...el.querySelectorAll('.pn-acct-links a')].map((a) => a.textContent);
const open = (el) => act(() => { btn(el).click(); });

test('closed at first: initials and first name on the button, named in full for screen readers', () => {
  const el = render();
  expect(items(el)).toEqual([]);
  expect(btn(el).getAttribute('aria-expanded')).toBe('false');
  expect(btn(el).getAttribute('aria-label')).toBe('Account: Juan Dela Cruz');
  expect(btn(el).querySelector('.pn-avatar').textContent).toBe('JC');
  expect(btn(el).querySelector('.pn-acct-first').textContent).toBe('Juan');
});

test('the avatar takes the role colour the dashboards use', () => {
  expect(btn(render()).querySelector('.pn-avatar').classList.contains('pn-tone-drrmo')).toBe(true);
  const admin = render({ user: { ...JUAN, role: { name: 'System_Admin' } } });
  expect(btn(admin).querySelector('.pn-avatar').classList.contains('pn-tone-admin')).toBe(true);
  const brgy = render({ user: { ...JUAN, role: { name: 'Barangay_Personnel' } } });
  expect(btn(brgy).querySelector('.pn-avatar').classList.contains('pn-tone-brgy')).toBe(true);
});

test('a click opens it: who you are, your pages, then Log out; a second click closes it', () => {
  const el = render();
  open(el);
  expect(btn(el).getAttribute('aria-expanded')).toBe('true');
  expect(el.querySelector('.pn-acct-name').textContent).toBe('Juan Dela Cruz');
  expect(el.querySelector('.pn-acct-role').textContent).toBe('DRRMO Officer');
  expect(el.querySelector('.pn-acct-email').textContent).toBe('juan@gmail.com');
  expect(items(el)).toEqual(['Dashboard', 'History', 'Reports', 'Security']);
  expect(el.querySelector('.pn-acct-logout').textContent).toBe('Log out');
  open(el);
  expect(items(el)).toEqual([]);
});

test('a long name keeps its full text on hover', () => {
  const long = 'Maria Dolores Concepcion Villanueva-Santos';
  const el = render({ user: { ...JUAN, full_name: long } });
  open(el);
  expect(el.querySelector('.pn-acct-name').getAttribute('title')).toBe(long);
});

test('without a name, the email stands in once and is not repeated', () => {
  const el = render({ user: { email: 'juan@gmail.com', role: { name: 'DRRMO_Officer' } } });
  expect(btn(el).getAttribute('aria-label')).toBe('Account: juan@gmail.com');
  expect(btn(el).querySelector('.pn-acct-first').textContent).toBe('juan');
  open(el);
  expect(el.querySelector('.pn-acct-name').textContent).toBe('juan@gmail.com');
  expect(el.querySelector('.pn-acct-email')).toBeNull();
});

test('Escape closes it and puts focus back on the button', () => {
  const el = render();
  open(el);
  const first = el.querySelector('.pn-acct-links a');
  act(() => { first.focus(); });
  act(() => { first.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true })); });
  expect(items(el)).toEqual([]);
  expect(document.activeElement).toBe(btn(el));
});

test('a click elsewhere closes it', () => {
  const el = render();
  open(el);
  act(() => { document.body.dispatchEvent(new MouseEvent('mousedown', { bubbles: true })); });
  expect(items(el)).toEqual([]);
});

test('tabbing out past the last item closes it', () => {
  const el = render();
  open(el);
  const logout = el.querySelector('.pn-acct-logout');
  act(() => { logout.focus(); });
  act(() => { logout.dispatchEvent(new FocusEvent('focusout', { bubbles: true, relatedTarget: document.body })); });
  expect(items(el)).toEqual([]);
});

test('choosing a page closes it', () => {
  const el = render();
  open(el);
  act(() => { el.querySelector('.pn-acct-links a').click(); });
  expect(items(el)).toEqual([]);
});

test('Log out closes it and signs out', () => {
  const onLogout = jest.fn();
  const el = render({ onLogout });
  open(el);
  act(() => { el.querySelector('.pn-acct-logout').click(); });
  expect(onLogout).toHaveBeenCalledTimes(1);
  expect(items(el)).toEqual([]);
});

test('on a staff page the button is highlighted and the page marked inside', () => {
  const el = render({ path: '/app/history' });
  expect(btn(el).classList.contains('is-active')).toBe(true);
  open(el);
  expect(el.querySelector('.pn-acct-links a.is-active').textContent).toBe('History');
});

test('on a public page the button is not highlighted', () => {
  expect(btn(render({ path: '/what-to-do' })).classList.contains('is-active')).toBe(false);
});

test('the folded menu shows the same panel open, with no button to press', () => {
  const onLogout = jest.fn();
  const el = render({ Component: AccountPanel, onLogout });
  expect(btn(el)).toBeNull();
  expect(el.querySelector('.pn-acct-name').textContent).toBe('Juan Dela Cruz');
  expect(items(el)).toEqual(['Dashboard', 'History', 'Reports', 'Security']);
  act(() => { el.querySelector('.pn-acct-logout').click(); });
  expect(onLogout).toHaveBeenCalledTimes(1);
});
