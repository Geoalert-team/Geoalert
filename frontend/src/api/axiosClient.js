import axios from 'axios';

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

// Normalize errors so callers can just do `catch (err) { err.message }`
client.interceptors.response.use(
  (res) => res,
  (err) => {
    const data = err.response?.data;
    const message = data?.error || data?.detail || err.message || 'Request failed';
    return Promise.reject(Object.assign(new Error(message), { status: err.response?.status, data }));
  }
);

// Call once on app load, before any login attempt, so the csrftoken
// cookie actually exists (Django only sets it once get_token() runs).
export async function primeCsrf() {
  await client.get('/api/auth/csrf/');
}

export default client;
