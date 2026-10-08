import React, { createContext, useContext, useEffect, useState } from "react";
import { authApi } from "../api/authApi";
import { primeCsrf } from "../api/axiosClient";

const AuthContext = createContext(null);

// True the first time the app loads in a browser tab, false on refreshes.
function isFreshTab() {
  try {
    if (sessionStorage.getItem("geoalert-tab-started")) return false;
    sessionStorage.setItem("geoalert-tab-started", "1");
    return true;
  } catch {
    return false;
  }
}

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [loggingOut, setLoggingOut] = useState(false);

  useEffect(() => {
    (async () => {
      await primeCsrf();

      // Development only: every fresh browser tab (like the one `npm start`
      // opens) starts logged out. Refreshing the page keeps you logged in.
      if (process.env.NODE_ENV === "development" && isFreshTab()) {
        try {
          await authApi.logout();
        } catch {
          // Not logged in to begin with — nothing to do.
        }
        setUser(null);
        setLoading(false);
        return;
      }

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
    if (loggingOut) return; // ignore repeat taps while a logout is already in flight
    setLoggingOut(true);
    try {
      await authApi.logout();
    } catch (error) {
      // Session may already be gone server-side — that's fine,
      // we're logging out either way.
      console.warn(
        "Logout request failed (session likely already cleared):",
        error,
      );
    } finally {
      setUser(null);
      setLoggingOut(false);
    }
  }

  const canPublish =
    user &&
    ["DRRMO_Officer", "System_Admin"].includes(user.role?.name || user.role);

  return (
    <AuthContext.Provider
      value={{
        user,
        loading,
        login,
        verifyLoginCode,
        logout,
        canPublish,
        setUser,
        loggingOut,
      }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}