import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { AuthProvider, useAuth } from './AuthContext';
import { primeCsrf } from '../api/axiosClient';
import { authApi } from '../api/authApi';

jest.mock('../api/axiosClient', () => ({ __esModule: true, default: {}, primeCsrf: jest.fn() }));
jest.mock('../api/authApi', () => ({ authApi: { me: jest.fn(), logout: jest.fn() } }));

beforeAll(() => { global.IS_REACT_ACT_ENVIRONMENT = true; });

let auth;

function Probe() {
  auth = useAuth();
  const { loading, user, sessionUnknown } = auth;
  return <p>{loading ? 'loading' : `ready:${user ? user.email : 'none'}${sessionUnknown ? ':unknown' : ''}`}</p>;
}

const failure = (status) => Object.assign(new Error('failed'), { status });

beforeEach(() => {
  jest.useRealTimers();
  jest.clearAllMocks();
  primeCsrf.mockResolvedValue();
  localStorage.clear();
  sessionStorage.clear();
});

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

describe('the check at start-up', () => {
  // Long enough for every retry, a second at a time so each awaited step runs
  const settle = async () => {
    for (let i = 0; i < 6; i += 1) {
      // eslint-disable-next-line no-await-in-loop
      await act(async () => { jest.advanceTimersByTime(1000); await Promise.resolve(); });
    }
  };

  test('a server hiccup does not sign anyone out', async () => {
    jest.useFakeTimers();
    authApi.me.mockRejectedValueOnce(failure(503)).mockResolvedValue({ email: 'officer@geoalert.gov.ph' });
    const el = await render();
    await settle();
    expect(el.textContent).toBe('ready:officer@geoalert.gov.ph');
  });

  test('a server the app cannot reach leaves the session unknown, not signed out', async () => {
    jest.useFakeTimers();
    authApi.me.mockRejectedValue(failure(undefined));
    const el = await render();
    await settle();
    expect(el.textContent).toBe('ready:none:unknown');
  });

  test('trying again picks the session back up', async () => {
    jest.useFakeTimers();
    authApi.me.mockRejectedValue(failure(500));
    const el = await render();
    await settle();
    authApi.me.mockResolvedValue({ email: 'officer@geoalert.gov.ph' });
    await act(async () => { auth.recheckSession(); });
    await settle();
    expect(el.textContent).toBe('ready:officer@geoalert.gov.ph');
  });

  test('a 401 means signed out, with no retries', async () => {
    authApi.me.mockRejectedValue(failure(401));
    const el = await render();
    expect(el.textContent).toBe('ready:none');
    expect(authApi.me).toHaveBeenCalledTimes(1);
  });

  test('a new tab in development does not end the session', async () => {
    const was = process.env.NODE_ENV;
    process.env.NODE_ENV = 'development';
    try {
      authApi.me.mockResolvedValue({ email: 'officer@geoalert.gov.ph' });
      const el = await render();
      expect(el.textContent).toBe('ready:officer@geoalert.gov.ph');
      expect(authApi.logout).not.toHaveBeenCalled();
    } finally {
      process.env.NODE_ENV = was;
    }
  });
});
