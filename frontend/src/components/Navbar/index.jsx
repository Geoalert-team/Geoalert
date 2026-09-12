import React from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import AlertBadge from '../AlertBadge';

const LINKS = [
  { to: '/', label: 'Map', roles: null, badge: false },
  { to: '/dashboard', label: 'Dashboard', roles: null, badge: true },
  { to: '/guidance', label: 'Guidance Library', roles: null, badge: false },
  { to: '/history', label: 'Historical Data', roles: ['DRRMO_Officer', 'System_Admin'], badge: false },
  { to: '/security', label: 'Security', roles: null, badge: false },
];

export default function Navbar() {
  const { user, logout, canPublish } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const roleName = user?.role?.name || user?.role;

  const visible = LINKS.filter((l) => !l.roles || l.roles.includes(roleName));

  return (
    <header
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '10px 20px',
        borderBottom: '1px solid var(--line)',
        background: 'var(--panel)',
        flexWrap: 'wrap',
        gap: 10,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 18, flexWrap: 'wrap' }}>
        <strong style={{ fontSize: 16 }}>GeoAlert</strong>
        <nav style={{ display: 'flex', gap: 4 }}>
          {visible.map((l) => (
            <button
              key={l.to}
              className="btn"
              style={{
                fontSize: 12.5,
                borderColor: location.pathname === l.to ? 'var(--accent)' : 'var(--line)',
                color: location.pathname === l.to ? 'var(--accent)' : 'var(--text)',
              }}
              onClick={() => navigate(l.to)}
            >
              {l.label}
              {l.badge && <AlertBadge scope={canPublish ? 'all' : 'mine'} email={user?.full_name || user?.email} />}
            </button>
          ))}
        </nav>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <span style={{ fontSize: 12.5 }}>
          {user?.email} <span style={{ color: 'var(--text-muted)' }}>({roleName})</span>
        </span>
        <button className="btn" onClick={logout}>Log out</button>
      </div>
    </header>
  );
}
