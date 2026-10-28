import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { MemoryRouter } from 'react-router-dom';
import Login from './Login';

const mockLogin = jest.fn();
jest.mock('../context/AuthContext', () => ({ useAuth: () => ({ login: mockLogin, verifyLoginCode: jest.fn() }) }));

beforeAll(() => { global.IS_REACT_ACT_ENVIRONMENT = true; });
beforeEach(() => { jest.clearAllMocks(); });

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

test('Back to login returns to the password step without sending the password again', async () => {
  mockLogin.mockResolvedValue({ require2fa: true });
  const el = await render(<Login />);
  await type(el.querySelector('#email'), 'juan@example.com');
  await type(el.querySelector('#password'), 'correct horse');
  await act(async () => { el.querySelector('button[type="submit"]').click(); });
  expect(el.textContent).toContain("Verify it's you");

  const back = [...el.querySelectorAll('button')].find((b) => b.textContent === 'Back to login');
  await act(async () => { back.click(); });
  expect(el.textContent).toContain('Welcome back');
  // A browser finishes a click after React has re-rendered, so a button
  // reused as "Log in" would submit the password form again.
  expect(back.isConnected).toBe(false);
  expect(el.querySelector('#email').value).toBe('juan@example.com');
  expect(el.querySelector('#password').value).toBe('');
  expect(mockLogin).toHaveBeenCalledTimes(1);
});
