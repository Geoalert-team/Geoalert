import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import ResetPassword from './ResetPassword';
import { authApi } from '../api/authApi';

jest.mock('../api/authApi', () => ({ authApi: { checkResetLink: jest.fn(), confirmPasswordReset: jest.fn() } }));

beforeAll(() => { global.IS_REACT_ACT_ENVIRONMENT = true; });
beforeEach(() => { jest.clearAllMocks(); });

const BAD_LINK = 'This link has expired or was already used.';

async function render() {
  const el = document.createElement('div');
  document.body.appendChild(el);
  await act(async () => {
    createRoot(el).render(
      <MemoryRouter initialEntries={['/reset-password/u1/t1']} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <Routes><Route path="/reset-password/:uid/:token" element={<ResetPassword />} /></Routes>
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

test('a link that cannot be checked counts as a bad link', async () => {
  authApi.checkResetLink.mockRejectedValue(new Error('Network Error'));
  const el = await render();
  expect(el.textContent).toContain(BAD_LINK);
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
