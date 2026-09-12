import client from './axiosClient';

export const barangaysApi = {
  list: () => client.get('/api/barangays/').then((r) => r.data),
  detail: (id) => client.get(`/api/barangays/${id}/`).then((r) => r.data),
};
