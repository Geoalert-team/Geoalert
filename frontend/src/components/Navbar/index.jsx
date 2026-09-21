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

  const [loggingOut, setLoggingOut] = React.useState(false);

  async function handleLogout() {
    if (loggingOut) return;
    setLoggingOut(true);
    await logout();
    navigate('/login');
  }

  return (
    <header className="navbar">
      <div style={{ display: 'flex', alignItems: 'center', gap: 22, flexWrap: 'wrap' }}>
        <span className="brand">GeoAlert</span>
        <nav className="nav-links">
          {visible.map((l) => (
            <button
              key={l.to}
              className={`nav-link ${location.pathname === l.to ? 'active' : ''}`}
              onClick={() => navigate(l.to)}
            >
              {l.label}
              {l.badge && <AlertBadge scope={canPublish ? 'all' : 'mine'} email={user?.full_name || user?.email} />}
            </button>
          ))}
        </nav>
      </div>
      <div className="navbar-user">
        <span><strong>{user?.email}</strong> ({roleName})</span>
        <button className="btn" onClick={handleLogout} disabled={loggingOut}>
          {loggingOut ? 'Logging out…' : 'Log out'}
        </button>
      </div>
    </header>
  );
}