import client from './axiosClient';

export const adminApi = {
  metrics: () =>
    client.get('/api/admin-dashboard/metrics/').then((r) => r.data),

  // What the dashboard's status indicator reads. Answers 200 even when
  // checks fail — the body says which. A rejected promise means the server
  // or the database could not be reached at all, which is itself Down.
  health: () =>
    client.get('/api/admin-dashboard/health/').then((r) => r.data),

  roles: () =>
    client.get('/api/admin-dashboard/roles/').then((r) => r.data),

  users: {
    list: (params) =>
      client.get('/api/admin-dashboard/users/', { params }).then((r) => r.data),

    // data: first_name, middle_initial, last_name, suffix, email, phone,
    // employee_id, position, role_id, assigned_barangay_id
    create: (data) =>
      client.post('/api/admin-dashboard/users/', data).then((r) => r.data),

    update: (id, data) =>
      client.put(`/api/admin-dashboard/users/${id}/`, data).then((r) => r.data),

    deactivate: (id) =>
      client.delete(`/api/admin-dashboard/users/${id}/`).then((r) => r.data),

    resetPassword: (id) =>
      client.post(`/api/admin-dashboard/users/${id}/reset-password/`).then((r) => r.data),
  },

  logs: (params) =>
    client.get('/api/admin-dashboard/logs/', { params }).then((r) => r.data),

  // Notification and alert monitoring (WBS 3.8.5).
  // params: days (1-90), severity, page
  alerts: (params) =>
    client.get('/api/admin-dashboard/alerts/', { params }).then((r) => r.data),
};