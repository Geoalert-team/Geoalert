import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import ResetPassword from './ResetPassword';
import { authApi } from '../api/authApi';

jest.mock('../api/authApi', () => ({
  authApi: { checkInvite: jest.fn(), acceptInvite: jest.fn(), checkResetLink: jest.fn(), confirmPasswordReset: jest.fn() },
}));

beforeAll(() => { global.IS_REACT_ACT_ENVIRONMENT = true; });
beforeEach(() => { jest.clearAllMocks(); });

const BAD_INVITE = 'This invite link has expired or was already used.';

function Where() {
  const { pathname } = useLocation();
  return <output data-testid="where">{pathname}</output>;
}

async function render() {
  const el = document.createElement('div');
  document.body.appendChild(el);
  await act(async () => {
    createRoot(el).render(
      <MemoryRouter initialEntries={['/set-password/u1/t1']} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <Routes>
          <Route path="/set-password/:uid/:token" element={<ResetPassword invite />} />
          <Route path="/set-password" element={<ResetPassword invite />} />
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
const link = (el, text) => [...el.querySelectorAll('a')].find((a) => a.textContent === text);

test('an invite link is checked as an invite, leaves the address, and sets the first password', async () => {
  authApi.checkInvite.mockResolvedValue({ valid: true });
  authApi.acceptInvite.mockResolvedValue({ message: 'ok' });
  const el = await render();
  expect(authApi.checkInvite).toHaveBeenCalledWith('u1', 't1');
  expect(authApi.checkResetLink).not.toHaveBeenCalled();
  expect(el.querySelector('[data-testid="where"]').textContent).toBe('/set-password');
  expect(el.querySelector('h1').textContent).toBe('Set up your account');

  const [a, b] = el.querySelectorAll('input');
  await type(a, 'Fresh-Harbor-2026');
  await type(b, 'Fresh-Harbor-2026');
  const submit = el.querySelector('button[type="submit"]');
  expect(submit.textContent).toBe('Set password');
  await act(async () => { submit.click(); });

  expect(authApi.acceptInvite).toHaveBeenCalledWith('u1', 't1', 'Fresh-Harbor-2026');
  expect(authApi.confirmPasswordReset).not.toHaveBeenCalled();
  expect(el.textContent).toContain('Your password is set. Log in with your email and new password.');
  expect(link(el, 'Log in').getAttribute('href')).toBe('/login');
});

test('a used or expired invite points to log in and the administrator, not to forgot password', async () => {
  authApi.checkInvite.mockResolvedValue({ valid: false });
  const el = await render();
  expect(el.textContent).toContain(BAD_INVITE);
  expect(el.textContent).toContain('ask your system administrator to send you a new invite');
  expect(link(el, 'Go to log in').getAttribute('href')).toBe('/login');
  expect(link(el, 'Send a new link')).toBeUndefined();
  expect(el.querySelectorAll('input')).toHaveLength(0);
});

test('an invite that expires while the form is open says so', async () => {
  authApi.checkInvite.mockResolvedValue({ valid: true });
  authApi.acceptInvite.mockRejectedValue(new Error(BAD_INVITE));
  const el = await render();
  const [a, b] = el.querySelectorAll('input');
  await type(a, 'Fresh-Harbor-2026');
  await type(b, 'Fresh-Harbor-2026');
  await act(async () => { el.querySelector('button[type="submit"]').click(); });
  expect(el.textContent).toContain(BAD_INVITE);
  expect(link(el, 'Go to log in')).toBeDefined();
});
