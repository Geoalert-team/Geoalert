import axios from 'axios';
import { errorMessage } from './errorMessage';

const client = axios.create({
  baseURL: process.env.REACT_APP_API_URL || 'http://localhost:8000',
  withCredentials: true, // send/receive the Django session cookie
  headers: { 'Content-Type': 'application/json' },
});

function getCsrfToken() {
  const match = document.cookie.match(/csrftoken=([^;]+)/);
  return match ? match[1] : null;
}

// Django requires X-CSRFToken on every unsafe method, read fresh from the
// cookie each time (it rotates after login).
client.interceptors.request.use((config) => {
  if (config.method && config.method.toLowerCase() !== 'get') {
    const token = getCsrfToken();
    if (token) config.headers['X-CSRFToken'] = token;
  }
  return config;
});

// A timed poll (the bell, the approval card) isn't someone using the app,
// so it mustn't keep an idle session alive. The backend's 30-minute idle
// limit ignores requests carrying this header.
export const BACKGROUND = { headers: { 'X-GeoAlert-Background': '1' } };

// Normalize errors so callers can just do `catch (err) { err.message }`.
// errorMessage() turns whatever came back (a server message, a validation
// error, an HTML error page, or nothing at all) into a sentence to show.
const EXPIRED_MESSAGE = {
  idle: 'You were signed out after 30 minutes without activity. Sign in again to continue.',
  total: 'You were signed out because 12 hours have passed since you signed in. Sign in again to continue.',
};

client.interceptors.response.use(
  (res) => {
    // A public page (the map) still loads after the session ends, so the
    // server says so in a header rather than failing the request.
    const ended = res.headers?.['x-geoalert-session-expired'];
    if (ended) {
      window.dispatchEvent(new CustomEvent('geoalert:session-expired', { detail: EXPIRED_MESSAGE[ended] }));
    }
    return res;
  },
  (err) => {
    const data = err.response?.data;
    // Signed out for being idle or past the 12-hour limit: tell the app, so
    // it can go to the login page with the reason instead of failing quietly.
    if (err.response?.status === 401 && data?.code === 'session_expired') {
      window.dispatchEvent(new CustomEvent('geoalert:session-expired', { detail: data.error }));
    }
    return Promise.reject(Object.assign(new Error(errorMessage(err)), { status: err.response?.status, data }));
  }
);

// Call once on app load, before any login attempt, so the csrftoken
// cookie actually exists (Django only sets it once get_token() runs).
export async function primeCsrf() {
  await client.get('/api/auth/csrf/');
}

export default client;
