import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { MemoryRouter } from 'react-router-dom';
import ForgotPassword from './ForgotPassword';
import Login from './Login';
import { authApi } from '../api/authApi';

jest.mock('../api/authApi', () => ({ authApi: { requestPasswordReset: jest.fn() } }));
jest.mock('../context/AuthContext', () => ({ useAuth: () => ({ login: jest.fn(), verifyLoginCode: jest.fn() }) }));

beforeAll(() => { global.IS_REACT_ACT_ENVIRONMENT = true; });
beforeEach(() => { jest.clearAllMocks(); });

const GENERIC = "If an account with that email exists, we've sent a link to reset its password. It works for 1 hour.";

async function render(node) {
  const el = document.createElement('div');
  document.body.appendChild(el);
  await act(async () => {
    createRoot(el).render(<MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>{node}</MemoryRouter>);
  });
  return el;
}
async function type(input, value) {
  const setter = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(input), 'value').set;
  await act(async () => { setter.call(input, value); input.dispatchEvent(new Event('input', { bubbles: true })); });
}
async function send(el, email = 'juan@example.com') {
  await type(el.querySelector('input[type="email"]'), email);
  await act(async () => { el.querySelector('button[type="submit"]').click(); });
}

test('the login page links to Forgot password', async () => {
  const el = await render(<Login />);
  const link = [...el.querySelectorAll('a')].find((a) => a.textContent === 'Forgot password?');
  expect(link.getAttribute('href')).toBe('/forgot-password');
});

test('sending shows the same reply whatever the email', async () => {
  authApi.requestPasswordReset.mockResolvedValue({ message: GENERIC });
  const el = await render(<ForgotPassword />);
  await send(el);
  expect(authApi.requestPasswordReset).toHaveBeenCalledWith('juan@example.com');
  expect(el.textContent).toContain(GENERIC);
  const back = [...el.querySelectorAll('a')].find((a) => a.textContent === 'Back to log in');
  expect(back.getAttribute('href')).toBe('/login');
});

test('too many requests says so', async () => {
  authApi.requestPasswordReset.mockRejectedValue(Object.assign(new Error('x'), { status: 429 }));
  const el = await render(<ForgotPassword />);
  await send(el);
  expect(el.textContent).toContain('Too many reset requests. Try again in a little while.');
});

test('a server that cannot be reached says so, instead of claiming an email was sent', async () => {
  const offline = "Can't reach the GeoAlert Talisay server. Check your internet connection, or that the backend is running.";
  authApi.requestPasswordReset.mockRejectedValue(new Error(offline)); // no status: no reply at all
  const el = await render(<ForgotPassword />);
  await send(el);
  expect(el.textContent).toContain(offline);
  expect(el.textContent).not.toContain(GENERIC);
  expect(el.querySelector('button[type="submit"]').disabled).toBe(false); // can try again
});

test('a server error still gets the generic reply, so nothing about the account leaks', async () => {
  authApi.requestPasswordReset.mockRejectedValue(Object.assign(new Error('Something went wrong'), { status: 500 }));
  const el = await render(<ForgotPassword />);
  await send(el);
  expect(el.textContent).toContain(GENERIC);
});

test('the button waits while sending', async () => {
  authApi.requestPasswordReset.mockReturnValue(new Promise(() => {}));
  const el = await render(<ForgotPassword />);
  await send(el);
  const button = el.querySelector('button[type="submit"]');
  expect(button.disabled).toBe(true);
  expect(button.textContent).toBe('Sending…');
});
