import client from './axiosClient';

export const barangaysApi = {
  list: () => client.get('/api/barangays/').then((r) => r.data),
  detail: (id) => client.get(`/api/barangays/${id}/`).then((r) => r.data),
  // Active zone ids affecting a barangay: { inside: [...] (ST_Within),
  // crossing: [...] (ST_Intersects, crosses its border) }
  hazards: (id) => client.get(`/api/barangays/${id}/hazards/`).then((r) => r.data),
};
