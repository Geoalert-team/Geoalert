import client from './axiosClient';

export const hazardsApi = {
  types: () => client.get('/api/hazards/types/').then((r) => r.data),
  list: (bbox, extraParams = {}) =>
    client
      .get('/api/hazards/', { params: { ...(bbox ? { bbox } : {}), ...extraParams } })
      .then((r) => r.data),
  byBarangay: (barangayId) =>
    client.get('/api/hazards/', { params: { barangay: barangayId } }).then((r) => r.data),
  detail: (id) => client.get(`/api/hazards/${id}/`).then((r) => r.data),
  create: (payload) => client.post('/api/hazards/create/', payload).then((r) => r.data),
  update: (id, payload) => client.patch(`/api/hazards/${id}/`, payload).then((r) => r.data),
  // payload: { verification_status: 'Confirmed' | 'Disputed', verification_note?: string }
  verify: (id, payload) => client.post(`/api/hazards/${id}/verify/`, payload).then((r) => r.data),
};