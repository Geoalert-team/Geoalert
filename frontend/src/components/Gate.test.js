import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import Gate from './Gate';
import { useAuth } from '../context/AuthContext';

jest.mock('../context/AuthContext', () => ({ useAuth: jest.fn() }));

beforeAll(() => { global.IS_REACT_ACT_ENVIRONMENT = true; });

async function render() {
  const el = document.createElement('div');
  document.body.appendChild(el);
  await act(async () => {
    createRoot(el).render(
      <MemoryRouter initialEntries={['/app/dashboard']}>
        <Routes>
          <Route path="/login" element={<p>login page</p>} />
          <Route path="/app/dashboard" element={<Gate><p>dashboard</p></Gate>} />
        </Routes>
      </MemoryRouter>,
    );
  });
  return el;
}

test('signed out goes to the login page', async () => {
  useAuth.mockReturnValue({ loading: false, user: null, sessionUnknown: false });
  expect((await render()).textContent).toBe('login page');
});

test('a signed-in user sees the page', async () => {
  useAuth.mockReturnValue({ loading: false, user: { role: { name: 'DRRMO_Officer' } }, sessionUnknown: false });
  expect((await render()).textContent).toBe('dashboard');
});

test('when the session could not be checked it offers a retry instead of the login page', async () => {
  const recheckSession = jest.fn();
  useAuth.mockReturnValue({ loading: false, user: null, sessionUnknown: true, recheckSession });
  const el = await render();
  expect(el.textContent).not.toContain('login page');
  expect(el.textContent).toContain('could not reach the server');
  await act(async () => { el.querySelector('button').click(); });
  expect(recheckSession).toHaveBeenCalledTimes(1);
});
