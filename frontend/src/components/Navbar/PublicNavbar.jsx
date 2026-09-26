import React, { useState } from 'react';
import { Link, NavLink } from 'react-router-dom';
import logo from '../../assets/images/logo1.png';
import './css/PublicNavbar.css';

const PUBLIC_LINKS = [
  { to: '/', label: 'Home' },
  { to: '/map', label: 'Map' },
  { to: '/about', label: 'About' },
  { to: '/contact', label: 'Contact' },
  { to: '/what-to-do', label: 'What to do' },
];

export default function PublicNavbar() {
  const [menuOpen, setMenuOpen] = useState(false);

  // Close the mobile menu after a link is tapped
  const closeMenu = () => setMenuOpen(false);

  return (
    <header className="pn-header">
      <div className="pn-inner">
        <Link to="/" className="pn-brand" onClick={closeMenu}>
          <span className="pn-logo">
            <img src={logo} alt="" />
          </span>
          <span className="pn-brand-name">GeoAlert</span>
        </Link>

        {/* Hamburger button, only visible on small screens */}
        <button
          type="button"
          className="pn-toggle"
          aria-expanded={menuOpen}
          aria-controls="pn-menu"
          onClick={() => setMenuOpen((open) => !open)}
        >
          <span className="pn-toggle-bar" />
          <span className="pn-toggle-bar" />
          <span className="pn-toggle-bar" />
          <span className="pn-visually-hidden">{menuOpen ? 'Close menu' : 'Open menu'}</span>
        </button>

        <nav id="pn-menu" className={`pn-menu ${menuOpen ? 'is-open' : ''}`} aria-label="Main">
          <ul className="pn-links">
            {PUBLIC_LINKS.map((link) => (
              <li key={link.to}>
                <NavLink
                  to={link.to}
                  end={link.to === '/'}
                  className={({ isActive }) => `pn-link ${isActive ? 'is-active' : ''}`}
                  onClick={closeMenu}
                >
                  {link.label}
                </NavLink>
              </li>
            ))}
          </ul>
          <Link to="/login" className="pn-login" onClick={closeMenu}>
            Log in
          </Link>
        </nav>
      </div>
    </header>
  );
}