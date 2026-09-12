import client from './axiosClient';

export const authApi = {
  login: (email, password) => client.post('/api/auth/login/', { email, password }).then((r) => r.data),
  verifyLoginCode: (code) => client.post('/api/auth/2fa/verify/', { code }).then((r) => r.data),
  logout: () => client.post('/api/auth/logout/').then((r) => r.data),
  me: () => client.get('/api/auth/me/').then((r) => r.data),

  setup2fa: () => client.post('/api/auth/2fa/setup/').then((r) => r.data),
  confirm2fa: (code) => client.post('/api/auth/2fa/confirm/', { code }).then((r) => r.data),
  disable2fa: (code) => client.post('/api/auth/2fa/disable/', { code }).then((r) => r.data),
};
