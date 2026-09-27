import React from 'react';
import { useAuth } from '../../context/AuthContext';
import AdminDashboard from './AdminDashboard';
import BarangayDashboard from './BarangayDashboard';
import DRRMODashboard from './DRRMODashboard';

export default function Dashboard() {
  const { user } = useAuth();
  const roleName = user?.role?.name || user?.role;

  if (roleName === 'System_Admin') return <AdminDashboard />;
  if (roleName === 'DRRMO_Officer') return <DRRMODashboard />;
  if (roleName === 'Barangay_Personnel') return <BarangayDashboard />;

  return <p style={{ padding: 24 }}>Your account role isn't recognized. Contact an administrator.</p>;
}