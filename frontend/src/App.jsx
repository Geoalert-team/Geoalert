import React, { useEffect } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider, useAuth } from './context/AuthContext';
import Login from './pages/Login';
import Home from './pages/Home';
import Security from './pages/Security';
import GuidanceLibrary from './pages/GuidanceLibrary';
import HistoricalData from './pages/HistoricalData';
import Dashboard from './pages/Dashboard';
import PublicMap from './pages/PublicMap';
import About from './pages/About';
import Contact from './pages/Contact';
import WhatToDo from './pages/WhatToDo';

// Sends "/" to the static homepage in public/homepage.html
function StaticHome() {
  useEffect(() => {
    window.location.replace('/homepage.html');
  }, []);
  return null;
}

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
      <Route path="/" element={<StaticHome />} />
      <Route path="/map" element={<PublicMap />} />
      <Route path="/about" element={<About />} />
      <Route path="/contact" element={<Contact />} />
      <Route path="/what-to-do" element={<WhatToDo />} />
      <Route path="/login" element={<Login />} />

      {/* Staff-only, behind login */}
      <Route path="/app" element={<Gate><Home /></Gate>} />
      <Route path="/app/dashboard" element={<Gate><Dashboard /></Gate>} />
      <Route path="/app/guidance" element={<Gate><GuidanceLibrary /></Gate>} />
      <Route path="/app/history" element={<Gate roles={['DRRMO_Officer', 'System_Admin']}><HistoricalData /></Gate>} />
      <Route path="/app/security" element={<Gate><Security /></Gate>} />

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