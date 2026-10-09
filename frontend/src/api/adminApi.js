import client from './axiosClient';

export const adminApi = {
  metrics: () =>
    client.get('/api/admin-dashboard/metrics/').then((r) => r.data),

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
};