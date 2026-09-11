const BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';

function getCsrfToken() {
  const match = document.cookie.match(/csrftoken=([^;]+)/);
  return match ? match[1] : null;
}

export async function primeCsrf() {
  await fetch(`${BASE_URL}/api/auth/csrf/`, { credentials: 'include' });
}

async function request(path, { method = 'GET', body } = {}) {
  const headers = { 'Content-Type': 'application/json' };
  if (method !== 'GET') {
    const token = getCsrfToken();
    if (token) headers['X-CSRFToken'] = token;
  }

  const res = await fetch(`${BASE_URL}${path}`, {
    method,
    headers,
    credentials: 'include',
    body: body ? JSON.stringify(body) : undefined,
  });

  let data = null;
  try { data = await res.json(); } catch {}

  if (!res.ok) {
    const error = new Error(data?.error || data?.detail || `Request failed (${res.status})`);
    error.status = res.status;
    error.data = data;
    throw error;
  }
  return data;
}

export const api = {
  login: (email, password) => request('/api/auth/login/', { method: 'POST', body: { email, password } }),
  logout: () => request('/api/auth/logout/', { method: 'POST' }),
  me: () => request('/api/auth/me/'),

  hazardTypes: () => request('/api/hazards/types/'),
  hazards: (bbox) => request(`/api/hazards/${bbox ? `?bbox=${bbox}` : ''}`),
  hazardDetail: (id) => request(`/api/hazards/${id}/`),
  createHazard: (payload) => request('/api/hazards/create/', { method: 'POST', body: payload }),
  updateHazard: (id, payload) => request(`/api/hazards/${id}/`, { method: 'PATCH', body: payload }),

  barangays: () => request('/api/barangays/'),
  barangay: (id) => request(`/api/barangays/${id}/`),

  // Incident reports â€” Barangay Personnel / DRRMO
  incidentReports: () => request('/api/reports/'),
  incidentReport: (id) => request(`/api/reports/${id}/`),
  createIncidentReport: (payload) => request('/api/reports/create/', { method: 'POST', body: payload }),
  updateIncidentReport: (id, payload) => request(`/api/reports/${id}/`, { method: 'PATCH', body: payload }),

  // Safety guidance â€” DRRMO Officer
  guidance: () => request('/api/guidance/'),
  guidanceDetail: (id) => request(`/api/guidance/${id}/`),
  createGuidance: (payload) => request('/api/guidance/create/', { method: 'POST', body: payload }),
  updateGuidance: (id, payload) => request(`/api/guidance/${id}/`, { method: 'PATCH', body: payload }),
  deleteGuidance: (id) => request(`/api/guidance/${id}/`, { method: 'DELETE' }),

  // Dashboard / reporting / analytics
  analytics: () => request('/api/reports/analytics/'),
  generatedReport: (params = '') => request(`/api/reports/generate/${params ? `?${params}` : ''}`),

  // System Administrator
  users: () => request('/api/admin/users/'),
  createUser: (payload) => request('/api/admin/users/', { method: 'POST', body: payload }),
  updateUser: (id, payload) => request(`/api/admin/users/${id}/`, { method: 'PATCH', body: payload }),
  deactivateUser: (id) => request(`/api/admin/users/${id}/`, { method: 'PATCH', body: { is_active: false } }),

  systemSettings: () => request('/api/admin/settings/'),
  updateSystemSettings: (payload) => request('/api/admin/settings/', { method: 'PATCH', body: payload }),
  systemLogs: () => request('/api/admin/logs/'),
  systemPerformance: () => request('/api/admin/performance/'),
};
