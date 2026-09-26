import React from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider, useAuth } from "./context/AuthContext";
import Login from "./pages/Login";
import PublicHome from "./pages/PublicHome";
import PublicMap from "./pages/PublicMap";
import About from "./pages/About";
import Contact from "./pages/Contact";
import WhatToDo from "./pages/WhatToDo";

function Gate({ children, roles }) {
  const { user, loading } = useAuth();
  if (loading) return <p style={{ padding: 24 }}>Checking session…</p>;
  if (!user) return <Navigate to="/login" replace />;
  const roleName = user.role?.name || user.role;
  if (roles && !roles.includes(roleName)) return <Navigate to="/app" replace />;
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

      {/* Logged-in users land on the same PublicHome */}
      <Route
        path="/app"
        element={
          <Gate>
            <PublicHome />
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
