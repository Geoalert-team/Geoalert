import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { AuthProvider, useAuth } from './AuthContext';
import { primeCsrf } from '../api/axiosClient';
import { authApi } from '../api/authApi';

jest.mock('../api/axiosClient', () => ({ __esModule: true, default: {}, primeCsrf: jest.fn() }));
jest.mock('../api/authApi', () => ({ authApi: { me: jest.fn(), logout: jest.fn() } }));

beforeAll(() => { global.IS_REACT_ACT_ENVIRONMENT = true; });

function Probe() {
  const { loading, user } = useAuth();
  return <p>{loading ? 'loading' : `ready:${user ? user.email : 'none'}`}</p>;
}

async function render() {
  const el = document.createElement('div');
  document.body.appendChild(el);
  await act(async () => { createRoot(el).render(<AuthProvider><Probe /></AuthProvider>); });
  return el;
}

test('a failed CSRF request does not stop the sign-in check', async () => {
  // e.g. a 400 because a parallel request ended the session
  primeCsrf.mockRejectedValue(new Error('Some of the details were not accepted.'));
  authApi.me.mockResolvedValue({ email: 'officer@geoalert.gov.ph' });
  const el = await render();
  expect(el.textContent).toBe('ready:officer@geoalert.gov.ph');
});
