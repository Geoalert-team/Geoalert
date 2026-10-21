import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import ResetPassword from './ResetPassword';
import { authApi } from '../api/authApi';

jest.mock('../api/authApi', () => ({ authApi: { checkResetLink: jest.fn(), confirmPasswordReset: jest.fn() } }));

beforeAll(() => { global.IS_REACT_ACT_ENVIRONMENT = true; });
beforeEach(() => { jest.clearAllMocks(); });

const BAD_LINK = 'This link has expired or was already used.';

// Shows where the router is, so a test can see the token leave the address
function Where() {
  const { pathname } = useLocation();
  return <output data-testid="where">{pathname}</output>;
}

async function render() {
  const el = document.createElement('div');
  document.body.appendChild(el);
  await act(async () => {
    createRoot(el).render(
      <MemoryRouter initialEntries={['/reset-password/u1/t1']} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <Routes>
          <Route path="/reset-password/:uid/:token" element={<ResetPassword />} />
          <Route path="/reset-password" element={<ResetPassword />} />
        </Routes>
        <Where />
      </MemoryRouter>,
    );
  });
  return el;
}
async function type(input, value) {
  const setter = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(input), 'value').set;
  await act(async () => { setter.call(input, value); input.dispatchEvent(new Event('input', { bubbles: true })); });
}
async function save(el, first, second = first) {
  const [a, b] = el.querySelectorAll('input');
  await type(a, first);
  await type(b, second);
  await act(async () => { el.querySelector('button[type="submit"]').click(); });
}
const link = (el, text) => [...el.querySelectorAll('a')].find((a) => a.textContent === text);

test('a bad link says so and offers a new one', async () => {
  authApi.checkResetLink.mockResolvedValue({ valid: false });
  const el = await render();
  expect(authApi.checkResetLink).toHaveBeenCalledWith('u1', 't1');
  expect(el.textContent).toContain(BAD_LINK);
  expect(link(el, 'Send a new link').getAttribute('href')).toBe('/forgot-password');
  expect(el.querySelectorAll('input')).toHaveLength(0);
});

test('an unreachable server says so and offers to try again, not "expired"', async () => {
  const offline = "Can't reach the GeoAlert server. Check your internet connection, or that the backend is running.";
  authApi.checkResetLink.mockRejectedValueOnce(new Error(offline)).mockResolvedValueOnce({ valid: true });
  const el = await render();
  expect(el.textContent).toContain(offline);
  expect(el.textContent).not.toContain(BAD_LINK);
  const retry = [...el.querySelectorAll('button')].find((b) => b.textContent === 'Try again');
  await act(async () => { retry.click(); });
  expect(authApi.checkResetLink).toHaveBeenCalledTimes(2);
  expect(el.querySelectorAll('input')).toHaveLength(2); // the link was fine after all
});

test('too many attempts says so, not "expired"', async () => {
  authApi.checkResetLink.mockRejectedValue(Object.assign(new Error('Too many attempts. Try again in a little while.'), { status: 429 }));
  const el = await render();
  expect(el.textContent).toContain('Too many attempts. Try again in a little while.');
  expect(el.textContent).not.toContain(BAD_LINK);
});

test('the link leaves the address bar as soon as it is read, and still works', async () => {
  authApi.checkResetLink.mockResolvedValue({ valid: true });
  authApi.confirmPasswordReset.mockResolvedValue({ message: 'ok' });
  const el = await render();
  expect(el.querySelector('[data-testid="where"]').textContent).toBe('/reset-password');
  await save(el, 'Abc-12345678');
  expect(authApi.confirmPasswordReset).toHaveBeenCalledWith('u1', 't1', 'Abc-12345678');
});

test('mismatched passwords are refused before anything is sent', async () => {
  authApi.checkResetLink.mockResolvedValue({ valid: true });
  const el = await render();
  await save(el, 'Abc-12345678', 'Abc-12345679');
  expect(el.textContent).toContain("The passwords don't match.");
  expect(authApi.confirmPasswordReset).not.toHaveBeenCalled();
});

test('the server rules show as they come back', async () => {
  authApi.checkResetLink.mockResolvedValue({ valid: true });
  authApi.confirmPasswordReset.mockRejectedValue(Object.assign(new Error('This password is too common.'), { status: 400 }));
  const el = await render();
  await save(el, 'Password123');
  expect(el.textContent).toContain('This password is too common.');
});

test('success says so and links to log in', async () => {
  authApi.checkResetLink.mockResolvedValue({ valid: true });
  authApi.confirmPasswordReset.mockResolvedValue({ message: 'Password changed. Log in with your new password.' });
  const el = await render();
  await save(el, 'Abc-12345678');
  expect(authApi.confirmPasswordReset).toHaveBeenCalledWith('u1', 't1', 'Abc-12345678');
  expect(el.textContent).toContain('Password changed. Log in with your new password.');
  expect(link(el, 'Log in').getAttribute('href')).toBe('/login');
  expect(el.querySelectorAll('input')).toHaveLength(0);
});

test('an expired link found on save says so', async () => {
  authApi.checkResetLink.mockResolvedValue({ valid: true });
  authApi.confirmPasswordReset.mockRejectedValue(Object.assign(new Error(BAD_LINK), { status: 400 }));
  const el = await render();
  await save(el, 'Abc-12345678');
  expect(el.textContent).toContain(BAD_LINK);
  expect(link(el, 'Send a new link').getAttribute('href')).toBe('/forgot-password');
});
