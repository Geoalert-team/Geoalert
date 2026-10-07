import React, { useState, useRef, useEffect } from "react";
import { Link, NavLink, useNavigate } from "react-router-dom";
import { useAuth } from "../../context/AuthContext";
import { useNotifications } from "../../hooks/useNotifications";
import logo from "../../assets/images/logo1.png";
import "./css/PublicNavbar.css";

// Shown to everyone who is NOT logged in (residents) — unchanged from before.
const PUBLIC_LINKS = [
  { to: "/", label: "Home" },
  { to: "/map", label: "Map" },
  { to: "/about", label: "About" },
  { to: "/contact", label: "Contact" },
  { to: "/what-to-do", label: "What to do" },
];

// Shown INSTEAD of the public links once a staff account is logged in.
// Barangay Personnel don't get History (matches the /app/history route gate).
const ROLE_LINKS = {
  System_Admin: [
    { to: "/app/dashboard", label: "Dashboard" },
    { to: "/map", label: "Map" },
    { to: "/app/history", label: "History" },
    { to: "/app/security", label: "Security" },
  ],
  DRRMO_Officer: [
    { to: "/app/dashboard", label: "Dashboard" },
    { to: "/map", label: "Map" },
    { to: "/app/history", label: "History" },
    { to: "/app/security", label: "Security" },
  ],
  Barangay_Personnel: [
    { to: "/app/dashboard", label: "Dashboard" },
    { to: "/map", label: "Map" },
    { to: "/app/security", label: "Security" },
  ],
};

export default function PublicNavbar() {
  const [menuOpen, setMenuOpen] = useState(false);
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const userMenuRef = useRef(null);

  // Notification bell. Only polls the backend while someone is logged in.
  const [bellOpen, setBellOpen] = useState(false);
  const bellRef = useRef(null);
  const { notifications, unreadCount, markRead, markAllRead } =
    useNotifications({ enabled: !!user });

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

  // Close the notification dropdown when clicking anywhere outside it
  useEffect(() => {
    if (!bellOpen) return;
    function handleClickOutside(e) {
      if (bellRef.current && !bellRef.current.contains(e.target)) {
        setBellOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [bellOpen]);

  async function handleLogout() {
    setUserMenuOpen(false);
    await logout();
    navigate("/");
  }

  const displayName = user?.full_name || user?.email;
  const roleName = user?.role?.name || user?.role;

  // Residents (no user) keep the exact links as before.
  // Logged-in staff see ONLY their role's links — public links are hidden.
  const links = user ? (ROLE_LINKS[roleName] || []) : PUBLIC_LINKS;
  const brandTo = user ? "/app/dashboard" : "/";

  return (
    <header className="pn-header">
      <div className="pn-inner">
        <Link to={brandTo} className="pn-brand" onClick={closeMenu}>
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
            {links.map((link) => (
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

          {user && (
            <div className="pn-bell" ref={bellRef}>
              <button
                type="button"
                className="pn-bell-btn"
                aria-expanded={bellOpen}
                aria-label={`Notifications${unreadCount ? `, ${unreadCount} unread` : ""}`}
                onClick={() => setBellOpen((open) => !open)}>
                <svg viewBox="0 0 24 24" aria-hidden="true">
                  <path d="M18 8a6 6 0 1 0-12 0c0 7-3 9-3 9h18s-3-2-3-9z" />
                  <path d="M13.7 21a2 2 0 0 1-3.4 0" />
                </svg>
                {unreadCount > 0 && (
                  <span className="pn-bell-badge">
                    {unreadCount > 99 ? "99+" : unreadCount}
                  </span>
                )}
              </button>

              {bellOpen && (
                <div className="pn-bell-dropdown">
                  <div className="pn-bell-header">
                    <span>Notifications</span>
                    {unreadCount > 0 && (
                      <button
                        type="button"
                        className="pn-bell-markall"
                        onClick={markAllRead}>
                        Mark all read
                      </button>
                    )}
                  </div>

                  {notifications.length === 0 ? (
                    <p className="pn-bell-empty">No notifications yet.</p>
                  ) : (
                    <ul className="pn-bell-list">
                      {notifications.slice(0, 20).map((n) => (
                        <li key={n.id}>
                          <button
                            type="button"
                            className={`pn-bell-item ${n.is_read ? "" : "is-unread"}`}
                            onClick={() => !n.is_read && markRead(n.id)}>
                            <span className="pn-bell-text">{n.content}</span>
                            <span className="pn-bell-time">
                              {new Date(n.sent_at).toLocaleString()}
                            </span>
                          </button>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              )}
            </div>
          )}

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