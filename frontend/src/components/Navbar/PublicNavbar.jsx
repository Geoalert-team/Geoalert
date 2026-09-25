import React from 'react';
import { useNavigate, useLocation } from 'react-router-dom';

const PUBLIC_LINKS = [
  { to: '/', label: 'Home' },
  { to: '/map', label: 'Map' },
  { to: '/about', label: 'About' },
  { to: '/contact', label: 'Contact' },
  { to: '/what-to-do', label: 'What To Do' },
  // { to: '/post-report', label: 'Post Report' },
];

export default function PublicNavbar() {
  const navigate = useNavigate();
  const location = useLocation();

  return (
    <header className="public-navbar">
      <div className="public-navbar-brand" onClick={() => navigate('/')}>
        <span>GeoAlert</span>
      </div>
      <nav className="public-nav-links">
        {PUBLIC_LINKS.map((l) => (
          <button
            key={l.to}
            className={`public-nav-link ${location.pathname === l.to ? 'active' : ''}`}
            onClick={() => navigate(l.to)}
          >
            {l.label}
          </button>
        ))}
      </nav>
      <button className="public-login-btn" onClick={() => navigate('/login')}>Login</button>
    </header>
  );
}