import React from "react";
import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

// Staff pages: waits for the sign-in check, then sends anyone who may not
// be here somewhere they may.
export default function Gate({ children, roles }) {
  const { user, loading, sessionUnknown, recheckSession } = useAuth();
  const { pathname } = useLocation();
  if (loading) return <p style={{ padding: 24 }}>Checking session…</p>;
  // Not the login page: the session may be perfectly good, and signing in
  // again wouldn't help while the server can't be reached anyway.
  if (sessionUnknown) {
    return (
      <div style={{ padding: 24 }}>
        <p>We could not reach the server to check your sign-in. You have not been signed out.</p>
        <button type="button" className="ph-btn ph-btn-primary" onClick={recheckSession}>Try again</button>
      </div>
    );
  }
  if (!user) return <Navigate to="/login" replace />;
  // A password an administrator set has to be replaced first; the server
  // refuses everything else until it is.
  if (user.must_change_password && pathname !== "/app/security") {
    return <Navigate to="/app/security" replace />;
  }
  const roleName = user.role?.name || user.role;
  if (roles && !roles.includes(roleName)) return <Navigate to="/app/dashboard" replace />;
  return children;
}
