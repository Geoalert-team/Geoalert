import client from './axiosClient';

export const historyApi = {
  list: (params) =>
    client.get('/api/history/', { params }).then((r) => r.data),

  detail: (id) =>
    client.get(`/api/history/${id}/`).then((r) => r.data),

  trends: (params) =>
    client.get('/api/history/trends/', { params }).then((r) => r.data),
};