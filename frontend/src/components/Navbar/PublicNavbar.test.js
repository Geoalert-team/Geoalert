import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { MemoryRouter } from 'react-router-dom';
import PublicNavbar from './PublicNavbar';
import { useAuth } from '../../context/AuthContext';

jest.mock('../../context/AuthContext', () => ({ useAuth: jest.fn() }));
// The bell polls the API; only where it sits matters here
jest.mock('./NotificationBell', () => () => <div data-testid="bell" />);

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
  expect(el.querySelector('.pn-staff')).toBeNull();
  expect(el.querySelector('[data-testid="bell"]')).toBeNull();
});

// The wide bar keeps the role's pages behind the ☰ staff menu
function roleItems(el) {
  act(() => { el.querySelector('.pn-role-btn').click(); });
  return texts(el, '.pn-role-menu a');
}

test('DRRMO Officer: the same public links, staff pages in the ☰ menu, no Log in', () => {
  const el = render(staff('DRRMO_Officer'));
  expect(texts(el, '.pn-public-links a')).toEqual(PUBLIC);
  expect(el.querySelector('.pn-staff-links')).toBeNull(); // no row of staff buttons any more
  expect(roleItems(el)).toEqual(['Dashboard', 'History', 'Reports', 'Security']);
  expect(el.querySelector('.pn-role-menu a[href="/app/security"]')).not.toBeNull();
  expect(el.querySelector('.pn-login')).toBeNull();
  expect(el.querySelector('.pn-brand').getAttribute('href')).toBe('/');
});

test('System Admin gets the same staff tools as an officer', () => {
  const el = render(staff('System_Admin'));
  expect(roleItems(el)).toEqual(['Dashboard', 'History', 'Reports', 'Security']);
});

test('Barangay Personnel get Dashboard and Security only', () => {
  const el = render(staff('Barangay_Personnel'));
  expect(texts(el, '.pn-public-links a')).toEqual(PUBLIC);
  expect(roleItems(el)).toEqual(['Dashboard', 'Security']);
});

test('wide screen: the bell sits in the bar, beside the name', () => {
  const el = render(staff('DRRMO_Officer'));
  expect(el.querySelector('.pn-menu [data-testid="bell"]')).not.toBeNull();
  expect(el.querySelector('.pn-header').classList.contains('is-compact')).toBe(false);
});

test('narrow screen: the bar folds into the menu and the bell stays beside it', () => {
  const el = render(staff('DRRMO_Officer'), { narrow: true });
  expect(el.querySelector('.pn-header').classList.contains('is-compact')).toBe(true);
  expect(el.querySelector('.pn-compact-actions [data-testid="bell"]')).not.toBeNull();
  expect(el.querySelector('.pn-menu [data-testid="bell"]')).toBeNull();
  expect(el.querySelector('.pn-staff-heading').textContent).toBe('Staff');
  expect(texts(el, '.pn-staff-links a')).toEqual(['Dashboard', 'History', 'Reports', 'Security']);
  expect(el.querySelector('.pn-role-btn')).toBeNull(); // the folded menu already lists them
});

test('both bars fold below 960 px: the shared right-hand slot needs about 939 px of bar', () => {
  const queries = [];
  useAuth.mockReturnValue(staff('DRRMO_Officer'));
  window.matchMedia = (query) => { queries.push(query); return { matches: false, addEventListener() {}, removeEventListener() {} }; };
  const el = document.createElement('div');
  act(() => { createRoot(el).render(<MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}><PublicNavbar /></MemoryRouter>); });
  expect(queries).toContain('(max-width: 959px)');

  queries.length = 0;
  useAuth.mockReturnValue({ user: null, logout: jest.fn() });
  const el2 = document.createElement('div');
  act(() => { createRoot(el2).render(<MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}><PublicNavbar /></MemoryRouter>); });
  expect(queries).toContain('(max-width: 959px)');
});

const order = (el) => [...el.querySelector('.pn-menu').children].map((c) => {
  if (c.classList.contains('pn-public-links')) return 'public';
  if (c.classList.contains('pn-staff')) return 'staff';
  if (c.classList.contains('pn-user')) return 'name';
  if (c.classList.contains('pn-role')) return 'role';
  if (c.dataset.testid === 'bell') return 'bell';
  return c.className;
});

// The right-hand slot is the same box signed in or out, so the links never move
const slot = (el) => [...el.querySelector('.pn-menu > .pn-account').children].map((c) => {
  if (c.classList.contains('pn-login')) return 'login';
  if (c.classList.contains('pn-user')) return 'name';
  if (c.classList.contains('pn-role')) return 'role';
  if (c.dataset.testid === 'bell') return 'bell';
  return c.className;
});

test('wide screen: the public links, then one right-hand slot', () => {
  expect(order(render(staff('DRRMO_Officer')))).toEqual(['public', 'pn-account']);
  expect(order(render({ user: null, logout: jest.fn() }))).toEqual(['public', 'pn-account']);
});

test('signed out, the slot holds Log in; signed in, the bell, the name, then the ☰ right of the name', () => {
  expect(slot(render({ user: null, logout: jest.fn() }))).toEqual(['login']);
  expect(slot(render(staff('DRRMO_Officer')))).toEqual(['bell', 'name', 'role']);
});

test('folded menu: public links, then Staff, then the name at the bottom', () => {
  expect(order(render(staff('DRRMO_Officer'), { narrow: true }))).toEqual(['public', 'staff', 'name']);
});

test('signed in: the account button is named for screen readers, and its menu shows the name', () => {
  const el = render(staff('DRRMO_Officer'));
  const accountBtn = el.querySelector('.pn-user-btn');
  expect(accountBtn.getAttribute('aria-label')).toBe('Account: Juan Dela Cruz');
  act(() => { accountBtn.click(); });
  expect(el.querySelector('.pn-user-menu-name').textContent).toBe('Juan Dela Cruz');
  expect(el.querySelector('.pn-user-logout').textContent).toBe('Logout');
});

test('a long name in the account menu keeps its full text on hover', () => {
  const el = render({ user: { full_name: 'Maria Dolores Concepcion Villanueva-Santos', role: { name: 'DRRMO_Officer' } }, logout: jest.fn() });
  act(() => { el.querySelector('.pn-user-btn').click(); });
  expect(el.querySelector('.pn-user-menu-name').getAttribute('title')).toBe('Maria Dolores Concepcion Villanueva-Santos');
});
