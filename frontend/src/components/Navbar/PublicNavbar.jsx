import React, { useState, useRef, useEffect } from "react";
import { Link, NavLink, useNavigate } from "react-router-dom";
import { useAuth } from "../../context/AuthContext";
import logo from "../../assets/images/logo1.png";
import "./css/PublicNavbar.css";

const PUBLIC_LINKS = [
  { to: "/", label: "Home" },
  { to: "/map", label: "Map" },
  { to: "/about", label: "About" },
  { to: "/contact", label: "Contact" },
  { to: "/what-to-do", label: "What to do" },
];

export default function PublicNavbar() {
  const [menuOpen, setMenuOpen] = useState(false);
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const userMenuRef = useRef(null);

  // Close the mobile menu after a link is tapped
  const closeMenu = () => setMenuOpen(false);

  // Close the user dropdown when clicking anywhere outside it
  useEffect(() => {
    if (!userMenuOpen) return;
    function handleClickOutside(e) {
      if (userMenuRef.current && !userMenuRef.current.contains(e.target)) {
        setUserMenuOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [userMenuOpen]);

  async function handleLogout() {
    setUserMenuOpen(false);
    await logout();
    navigate("/");
  }

  const displayName = user?.full_name || user?.email;

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
          onClick={() => setMenuOpen((open) => !open)}>
          <span className="pn-toggle-bar" />
          <span className="pn-toggle-bar" />
          <span className="pn-toggle-bar" />
          <span className="pn-visually-hidden">
            {menuOpen ? "Close menu" : "Open menu"}
          </span>
        </button>

        <nav
          id="pn-menu"
          className={`pn-menu ${menuOpen ? "is-open" : ""}`}
          aria-label="Main">
          <ul className="pn-links">
            {PUBLIC_LINKS.map((link) => (
              <li key={link.to}>
                <NavLink
                  to={link.to}
                  end={link.to === "/"}
                  className={({ isActive }) =>
                    `pn-link ${isActive ? "is-active" : ""}`
                  }
                  onClick={closeMenu}>
                  {link.label}
                </NavLink>
              </li>
            ))}
          </ul>

          {user ? (
            <div className="pn-user" ref={userMenuRef}>
              <button
                type="button"
                className="pn-user-btn"
                aria-expanded={userMenuOpen}
                onClick={() => setUserMenuOpen((open) => !open)}>
                <span className="pn-user-icon" aria-hidden="true">
                  <svg viewBox="0 0 24 24">
                    <path d="M12 12a4.5 4.5 0 1 0 0-9 4.5 4.5 0 0 0 0 9z" />
                    <path d="M4 20c1.5-4 4.5-6 8-6s6.5 2 8 6" />
                  </svg>
                </span>
                <span className="pn-user-name">{displayName}</span>
              </button>

              {userMenuOpen && (
                <div className="pn-user-dropdown">
                  <button
                    type="button"
                    className="pn-user-logout"
                    onClick={handleLogout}>
                    Logout
                  </button>
                </div>
              )}
            </div>
          ) : (
            <Link to="/login" className="pn-login" onClick={closeMenu}>
              Log in
            </Link>
          )}
        </nav>
      </div>
    </header>
  );
}
