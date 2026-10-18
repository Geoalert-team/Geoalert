import React from "react";
import { BrowserRouter, Routes, Route, Navigate, useLocation } from "react-router-dom";
import { AuthProvider, useAuth } from "./context/AuthContext";
import Login from "./pages/Login";
import PublicHome from "./pages/PublicHome";
import PublicMap from "./pages/PublicMap";
import About from "./pages/About";
import Contact from "./pages/Contact";
import WhatToDo from "./pages/WhatToDo";
import Dashboard from "./pages/Dashboard";
import HistoricalData from "./pages/HistoricalData";
import Security from "./pages/Security";
import Reports from "./pages/Reports";
import Analytics from "./pages/Analytics";

function Gate({ children, roles }) {
  const { user, loading } = useAuth();
  const { pathname } = useLocation();
  if (loading) return <p style={{ padding: 24 }}>Checking session…</p>;
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

function AppRoutes() {
  return (
    <Routes>
      {/* Public, no login required */}
      <Route path="/" element={<PublicHome />} />
      <Route path="/map" element={<PublicMap />} />
      <Route path="/about" element={<About />} />
      <Route path="/contact" element={<Contact />} />
      <Route path="/what-to-do" element={<WhatToDo />} />
      <Route path="/login" element={<Login />} />
      <Route path="/app/security" element={<Gate><Security /></Gate>} />

      {/* Logged-in staff */}
      <Route path="/app/dashboard" element={<Gate><Dashboard /></Gate>} />
      <Route
        path="/app/history"
        element={
          <Gate roles={["System_Admin", "DRRMO_Officer"]}>
            <HistoricalData />
          </Gate>
        }
      />
      {/* F7: DRRMO and Admin only, matching the spec's permission check */}
      <Route
        path="/app/reports"
        element={
          <Gate roles={["System_Admin", "DRRMO_Officer"]}>
            <Reports />
          </Gate>
        }
      />

      {/* F7 analytics dashboard: DRRMO and Admin, like Reports */}
      <Route
        path="/app/analytics"
        element={
          <Gate roles={["System_Admin", "DRRMO_Officer"]}>
            <Analytics />
          </Gate>
        }
      />

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <AppRoutes />
      </BrowserRouter>
    </AuthProvider>
  );
}