import React, { createContext, useContext, useEffect, useState } from 'react';
import { api, primeCsrf } from './client';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      await primeCsrf();
      try {
        const me = await api.me();
        setUser(me);
      } catch {
        setUser(null);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  async function login(email, password) {
    const res = await api.login(email, password);
    setUser(res.user);
    return res;
  }

  async function logout() {
    await api.logout();
    setUser(null);
  }

  const canPublish = user && ['DRRMO_Officer', 'System_Admin'].includes(user.role?.name || user.role);

  return (
    <AuthContext.Provider value={{ user, loading, login, logout, canPublish }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
