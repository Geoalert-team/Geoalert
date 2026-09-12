import React from 'react';
import { useAuth } from '../../context/AuthContext';
import AdminDashboard from './AdminDashboard';
import DRRMODashboard from './DRRMODashboard';
import BarangayDashboard from './BarangayDashboard';

export default function Dashboard() {
  const { user } = useAuth();
  const roleName = user?.role?.name || user?.role;

  if (roleName === 'System_Admin') return <AdminDashboard />;
  if (roleName === 'DRRMO_Officer') return <DRRMODashboard />;
  return <BarangayDashboard />;
}
