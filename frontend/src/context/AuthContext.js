import React, { createContext, useContext, useEffect, useState } from 'react';
import { authApi } from '../api/authApi';
import { primeCsrf } from '../api/axiosClient';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      await primeCsrf();
      try {
        const me = await authApi.me();
        setUser(me);
      } catch {
        setUser(null);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  // Step 1: email + password. Returns { require2fa: true } instead of
  // logging in, if the account has 2FA enabled.
  async function login(email, password) {
    const res = await authApi.login(email, password);
    if (res.require_2fa) {
      return { require2fa: true };
    }
    setUser(res.user);
    return { require2fa: false };
  }

  // Step 2, only called when step 1 returned require2fa: true.
  async function verifyLoginCode(code) {
    const res = await authApi.verifyLoginCode(code);
    setUser(res.user);
  }

  async function logout() {
    await authApi.logout();
    setUser(null);
  }

  const canPublish = user && ['DRRMO_Officer', 'System_Admin'].includes(user.role?.name || user.role);

  return (
    <AuthContext.Provider value={{ user, loading, login, verifyLoginCode, logout, canPublish, setUser }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
