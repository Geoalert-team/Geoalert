import client from './axiosClient';

export const authApi = {
  login: (email, password) => client.post('/api/auth/login/', { email, password }).then((r) => r.data),
  verifyLoginCode: (code) => client.post('/api/auth/2fa/verify/', { code }).then((r) => r.data),
  logout: () => client.post('/api/auth/logout/').then((r) => r.data),
  me: () => client.get('/api/auth/me/').then((r) => r.data),

  setup2fa: () => client.post('/api/auth/2fa/setup/').then((r) => r.data),
  confirm2fa: (code) => client.post('/api/auth/2fa/confirm/', { code }).then((r) => r.data),
  disable2fa: (code) => client.post('/api/auth/2fa/disable/', { code }).then((r) => r.data),

  changePassword: ({ current_password, new_password }) =>
    client.post('/api/auth/change-password/', { current_password, new_password }).then((r) => r.data),

  // Forgot password: email a one-time, 1-hour link; check it; set the new password
  requestPasswordReset: (email) =>
    client.post('/api/auth/password-reset/', { email }).then((r) => r.data),
  checkResetLink: (uid, token) =>
    client.post('/api/auth/password-reset/check/', { uid, token }).then((r) => r.data),
  confirmPasswordReset: (uid, token, newPassword) =>
    client.post('/api/auth/password-reset/confirm/', { uid, token, new_password: newPassword }).then((r) => r.data),
};