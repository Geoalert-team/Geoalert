import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider, useAuth } from './context/AuthContext';
import Login from './pages/Login';
import Home from './pages/Home';
import Security from './pages/Security';
import GuidanceLibrary from './pages/GuidanceLibrary';
import HistoricalData from './pages/HistoricalData';
import Dashboard from './pages/Dashboard';

function Gate({ children, roles }) {
  const { user, loading } = useAuth();
  if (loading) return <p style={{ padding: 24 }}>Checking sessionâ€¦</p>;
  if (!user) return <Navigate to="/login" replace />;
  const roleName = user.role?.name || user.role;
  if (roles && !roles.includes(roleName)) return <Navigate to="/" replace />;
  return children;
}

function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/" element={<Gate><Home /></Gate>} />
      <Route path="/dashboard" element={<Gate><Dashboard /></Gate>} />
      <Route path="/guidance" element={<Gate><GuidanceLibrary /></Gate>} />
      <Route path="/history" element={<Gate roles={['DRRMO_Officer', 'System_Admin']}><HistoricalData /></Gate>} />
      <Route path="/security" element={<Gate><Security /></Gate>} />
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
