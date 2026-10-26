import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { MemoryRouter } from 'react-router-dom';
import PublicNavbar from './PublicNavbar';
import { useAuth } from '../../context/AuthContext';

jest.mock('../../context/AuthContext', () => ({ useAuth: jest.fn() }));
// The bell polls the API; only where it sits matters here
jest.mock('./NotificationBell', () => () => <div data-testid="bell" />);
jest.mock('./ResidentAlertBell', () => () => <div data-testid="alerts" />);

beforeAll(() => { global.IS_REACT_ACT_ENVIRONMENT = true; });
afterEach(() => { delete window.matchMedia; });

const PUBLIC = ['Home', 'Map', 'About', 'Contact', 'What to do'];
const staff = (role) => ({ user: { full_name: 'Juan Dela Cruz', role: { name: role } }, logout: jest.fn() });

function render(auth, { narrow = false } = {}) {
  useAuth.mockReturnValue(auth);
  window.matchMedia = (query) => ({
    matches: narrow, media: query, addEventListener() {}, removeEventListener() {},
  });
  const el = document.createElement('div');
  act(() => {
    createRoot(el).render(
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}><PublicNavbar /></MemoryRouter>,
    );
  });
  return el;
}
const texts = (el, sel) => [...el.querySelectorAll(sel)].map((a) => a.textContent);

test('signed out: exactly the public bar, with Log in and no staff buttons', () => {
  const el = render({ user: null, logout: jest.fn() });
  expect(texts(el, '.pn-public-links a')).toEqual(PUBLIC);
  expect(texts(el, '.pn-login')).toEqual(['Log in']);
  expect(el.querySelector('.pn-acct-btn')).toBeNull();
  expect(el.querySelector('.pn-acct-links')).toBeNull();
  expect(el.querySelector('[data-testid="bell"]')).toBeNull();
  expect(el.querySelector('.pn-menu [data-testid="alerts"]')).not.toBeNull();
});

test('signed in, staff get their own bell and no resident alert bell', () => {
  const el = render(staff('DRRMO_Officer'));
  expect(el.querySelector('[data-testid="alerts"]')).toBeNull();
  expect(render(staff('DRRMO_Officer'), { narrow: true }).querySelector('[data-testid="alerts"]')).toBeNull();
});

test('narrow screen, signed out: the alert bell stays beside the ☰ button', () => {
  const el = render({ user: null, logout: jest.fn() }, { narrow: true });
  expect(el.querySelector('.pn-compact-actions [data-testid="alerts"]')).not.toBeNull();
  expect(el.querySelector('.pn-menu [data-testid="alerts"]')).toBeNull();
});

// The wide bar keeps the role's pages in the account menu
function accountItems(el) {
  act(() => { el.querySelector('.pn-acct-btn').click(); });
  return texts(el, '.pn-acct-links a');
}

test('DRRMO Officer: the same public links, staff pages in the account menu, no Log in', () => {
  const el = render(staff('DRRMO_Officer'));
  expect(texts(el, '.pn-public-links a')).toEqual(PUBLIC);
  expect(accountItems(el)).toEqual(['Dashboard', 'History', 'Reports', 'Security']);
  expect(el.querySelector('.pn-acct-links a[href="/app/security"]')).not.toBeNull();
  expect(el.querySelector('.pn-login')).toBeNull();
  expect(el.querySelector('.pn-brand').getAttribute('href')).toBe('/');
});

test('System Admin gets the same staff pages as an officer', () => {
  expect(accountItems(render(staff('System_Admin')))).toEqual(['Dashboard', 'History', 'Reports', 'Security']);
});

test('Barangay Personnel get Dashboard and Security only', () => {
  const el = render(staff('Barangay_Personnel'));
  expect(texts(el, '.pn-public-links a')).toEqual(PUBLIC);
  expect(accountItems(el)).toEqual(['Dashboard', 'Security']);
});

test('one account button: no separate staff ☰ button any more', () => {
  const el = render(staff('DRRMO_Officer'));
  expect(el.querySelectorAll('.pn-acct-btn')).toHaveLength(1);
  expect(el.querySelector('.pn-role-btn')).toBeNull();
});

test('wide screen: the bell sits in the bar, beside the account button', () => {
  const el = render(staff('DRRMO_Officer'));
  expect(el.querySelector('.pn-menu [data-testid="bell"]')).not.toBeNull();
  expect(el.querySelector('.pn-header').classList.contains('is-compact')).toBe(false);
});

test('narrow screen: the bar folds into the menu, the bell stays beside it, and the account panel is open inside', () => {
  const el = render(staff('DRRMO_Officer'), { narrow: true });
  expect(el.querySelector('.pn-header').classList.contains('is-compact')).toBe(true);
  expect(el.querySelector('.pn-compact-actions [data-testid="bell"]')).not.toBeNull();
  expect(el.querySelector('.pn-menu [data-testid="bell"]')).toBeNull();
  expect(el.querySelector('.pn-acct-btn')).toBeNull(); // nothing more to press inside the folded menu
  expect(el.querySelector('.pn-menu .pn-acct-name').textContent).toBe('Juan Dela Cruz');
  expect(texts(el, '.pn-menu .pn-acct-links a')).toEqual(['Dashboard', 'History', 'Reports', 'Security']);
});

test('both bars fold below 1100 px: signed in, the bar needs about 1060 px', () => {
  const queries = [];
  useAuth.mockReturnValue(staff('DRRMO_Officer'));
  window.matchMedia = (query) => { queries.push(query); return { matches: false, addEventListener() {}, removeEventListener() {} }; };
  const el = document.createElement('div');
  act(() => { createRoot(el).render(<MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}><PublicNavbar /></MemoryRouter>); });
  expect(queries).toContain('(max-width: 1099px)');

  queries.length = 0;
  useAuth.mockReturnValue({ user: null, logout: jest.fn() });
  const el2 = document.createElement('div');
  act(() => { createRoot(el2).render(<MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}><PublicNavbar /></MemoryRouter>); });
  expect(queries).toContain('(max-width: 1099px)');
});

const kind = (c) => {
  if (c.classList.contains('pn-public-links')) return 'public';
  if (c.classList.contains('pn-login')) return 'login';
  if (c.classList.contains('pn-acct')) return 'account';
  if (c.classList.contains('pn-acct-panel')) return 'account';
  if (c.dataset.testid === 'bell') return 'bell';
  if (c.dataset.testid === 'alerts') return 'alerts';
  return c.className;
};
const order = (el) => [...el.querySelector('.pn-menu').children].map(kind);
// The right-hand slot holds the same things in the same place signed in or out
const slot = (el) => [...el.querySelector('.pn-menu > .pn-account').children].map(kind);

test('wide screen: the public links, then one right-hand slot', () => {
  expect(order(render(staff('DRRMO_Officer')))).toEqual(['public', 'pn-account']);
  expect(order(render({ user: null, logout: jest.fn() }))).toEqual(['public', 'pn-account']);
});

test('signed out, the slot holds the alert bell then Log in; signed in, the bell then the account button', () => {
  expect(slot(render({ user: null, logout: jest.fn() }))).toEqual(['alerts', 'login']);
  expect(slot(render(staff('DRRMO_Officer')))).toEqual(['bell', 'account']);
});

test('folded menu: public links, then the account panel at the bottom', () => {
  expect(order(render(staff('DRRMO_Officer'), { narrow: true }))).toEqual(['public', 'account']);
  expect(order(render({ user: null, logout: jest.fn() }, { narrow: true }))).toEqual(['public', 'login']);
});

test('Log out signs out', async () => {
  const auth = staff('DRRMO_Officer');
  auth.logout.mockResolvedValue();
  const el = render(auth);
  act(() => { el.querySelector('.pn-acct-btn').click(); });
  await act(async () => { el.querySelector('.pn-acct-logout').click(); });
  expect(auth.logout).toHaveBeenCalledTimes(1);
});

