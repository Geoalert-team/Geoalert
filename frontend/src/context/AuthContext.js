import React, { createContext, useCallback, useContext, useEffect, useState } from "react";
import { authApi } from "../api/authApi";
import { primeCsrf } from "../api/axiosClient";

const AuthContext = createContext(null);

// A logout the server hasn't confirmed yet. Remembered so a reload can't sign
// someone back in because the database was unreachable when they logged out.
const LOGOUT_PENDING = "geoalert-logout-pending";

function setLogoutPending(pending) {
  try {
    if (pending) localStorage.setItem(LOGOUT_PENDING, "1");
    else localStorage.removeItem(LOGOUT_PENDING);
  } catch {
    // storage blocked; the logout request still goes out
  }
}

function isLogoutPending() {
  try {
    return localStorage.getItem(LOGOUT_PENDING) === "1";
  } catch {
    return false;
  }
}

// Ends the session on the server. 401/403 mean it is already gone, which is
// what we wanted; anything else leaves the logout pending for the next load.
async function endServerSession() {
  try {
    await authApi.logout();
    setLogoutPending(false);
  } catch (error) {
    if (error?.status === 401 || error?.status === 403) setLogoutPending(false);
    else console.warn("Logout not confirmed; retrying on the next load:", error);
  }
}

// Pauses before asking the server again who is signed in, in milliseconds.
const CHECK_RETRIES = [1000, 3000];

// Who is signed in. Only 401/403 mean nobody is. A server restarting or a
// database hiccup says nothing about the session, and reading it as "signed
// out" sent people to the login page with their session still alive.
async function checkSession() {
  for (let attempt = 0; ; attempt += 1) {
    try {
      return { me: await authApi.me(), unknown: false };
    } catch (error) {
      if (error?.status === 401 || error?.status === 403) return { me: null, unknown: false };
      if (attempt === CHECK_RETRIES.length) return { me: null, unknown: true };
      await new Promise((resolve) => setTimeout(resolve, CHECK_RETRIES[attempt]));
    }
  }
}

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [loggingOut, setLoggingOut] = useState(false);
  // The server couldn't be asked. Not the same as signed out: see Gate.
  const [sessionUnknown, setSessionUnknown] = useState(false);

  const recheckSession = useCallback(async () => {
    setLoading(true);
    const { me, unknown } = await checkSession();
    setUser(me);
    setSessionUnknown(unknown);
    setLoading(false);
  }, []);

  // The backend ends a session after 30 minutes idle or 12 hours in total.
  // Drop the user here so the route guard sends them to the login page,
  // and leave the reason for the login page to show.
  useEffect(() => {
    function onExpired(e) {
      try {
        sessionStorage.setItem('geoalert-signout-reason', e.detail || 'Your session ended. Sign in again.');
      } catch {
        // storage blocked; the login page just won't say why
      }
      setUser(null);
    }
    window.addEventListener('geoalert:session-expired', onExpired);
    return () => window.removeEventListener('geoalert:session-expired', onExpired);
  }, []);

  // The server says this account still has an admin-set password
  useEffect(() => {
    function onChangeRequired() {
      setUser((u) => (u ? { ...u, must_change_password: true } : u));
    }
    window.addEventListener('geoalert:password-change-required', onChangeRequired);
    return () => window.removeEventListener('geoalert:password-change-required', onChangeRequired);
  }, []);

  useEffect(() => {
    (async () => {
      // Only sets the CSRF cookie. If it fails (offline, or a parallel
      // request just ended the session) the sign-in check still has to run,
      // or every staff page waits on "Checking session…" for good.
      try {
        await primeCsrf();
      } catch {
        // the next request that needs the cookie gets it, or says what failed
      }

      if (isLogoutPending()) {
        await endServerSession();
        setUser(null);
        setLoading(false);
        return;
      }

      await recheckSession();
    })();
  }, [recheckSession]);

  // Step 1: email + password. Returns { require2fa: true } instead of
  // logging in, if the account has 2FA enabled.
  async function login(email, password) {
    const res = await authApi.login(email, password);
    if (res.require_2fa) {
      return { require2fa: true };
    }
    setLogoutPending(false);
    setSessionUnknown(false);
    setUser(res.user);
    return { require2fa: false };
  }

  // Step 2, only called when step 1 returned require2fa: true.
  async function verifyLoginCode(code) {
    const res = await authApi.verifyLoginCode(code);
    setLogoutPending(false);
    setSessionUnknown(false);
    setUser(res.user);
  }

  async function logout() {
    if (loggingOut) return; // ignore repeat taps while a logout is already in flight
    setLoggingOut(true);
    // Signed out on screen straight away: the request can hang for a minute
    // when the database is unreachable, and the button would look dead.
    setLogoutPending(true);
    setUser(null);
    await endServerSession();
    setLoggingOut(false);
  }

  const canPublish =
    user &&
    ["DRRMO_Officer", "System_Admin"].includes(user.role?.name || user.role);
  // Closing a fire with the BFP figures: DRRMO and admins, and BFP personnel,
  // who can do nothing else (the server keeps them to fires)
  const canCloseFires =
    user &&
    ["DRRMO_Officer", "System_Admin", "BFP_Personnel"].includes(user.role?.name || user.role);
  // Posting to the newsfeed: the same people (the server checks each post)
  const canPostNews = canCloseFires;

  return (
    <AuthContext.Provider
      value={{
        user,
        loading,
        sessionUnknown,
        recheckSession,
        login,
        verifyLoginCode,
        logout,
        canPublish,
        canCloseFires,
        canPostNews,
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