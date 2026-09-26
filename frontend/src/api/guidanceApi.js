import client from './axiosClient';

export const guidanceApi = {
  list: (params) =>
    client.get('/api/guidance/', { params }).then((r) => r.data),

  detail: (id) =>
    client.get(`/api/guidance/${id}/`).then((r) => r.data),

  create: ({ hazard_type, title, body, timeline_phase }) =>
    client.post('/api/guidance/', { hazard_type, title, body, timeline_phase }).then((r) => r.data),

  update: (id, data) =>
    client.put(`/api/guidance/${id}/`, data).then((r) => r.data),

  remove: (id) =>
    client.delete(`/api/guidance/${id}/`).then((r) => r.data),
};