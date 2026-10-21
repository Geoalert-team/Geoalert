import React, { useState, useRef, useEffect } from "react";
import { Link, NavLink, useNavigate } from "react-router-dom";
import { useAuth } from "../../context/AuthContext";
import NotificationBell from "./NotificationBell";
import RoleMenu from "./RoleMenu";
import useMediaQuery from "./useMediaQuery";
import logo from "../../assets/images/logo1.png";
import "./css/PublicNavbar.css";

/**
 * The one navigation bar, on every page and for everyone.
 *
 * Everyone sees the public links. A signed-in staff member also gets the
 * bell, their avatar (name and Log out) and, at the far right, a ☰ staff
 * menu with their role's pages (RoleMenu.jsx); all of it disappears again
 * on logout. Map is a public link, so no role lists it again.
 */
const PUBLIC_LINKS = [
  { to: "/", label: "Home" },
  { to: "/map", label: "Map" },
  { to: "/about", label: "About" },
  { to: "/contact", label: "Contact" },
  { to: "/what-to-do", label: "What to do" },
];

// Barangay Personnel don't get History or Reports (matches the route gates
// in App.jsx). Analytics is a tab of Reports, not its own entry; the old
// /app/analytics link still resolves.
const STAFF_LINKS = {
  System_Admin: [
    { to: "/app/dashboard", label: "Dashboard" },
    { to: "/app/history", label: "History" },
    { to: "/app/reports", label: "Reports" },
    { to: "/app/security", label: "Security" },
  ],
  DRRMO_Officer: [
    { to: "/app/dashboard", label: "Dashboard" },
    { to: "/app/history", label: "History" },
    { to: "/app/reports", label: "Reports" },
    { to: "/app/security", label: "Security" },
  ],
  Barangay_Personnel: [
    { to: "/app/dashboard", label: "Dashboard" },
    { to: "/app/security", label: "Security" },
  ],
};

// Below this width the bar folds into the ☰ menu, signed in or out. The
// right-hand slot is the same width either way (so the links never move),
// and the whole bar needs about 939 px; folding below 960 leaves a margin.
const COMPACT = "(max-width: 959px)";

export default function PublicNavbar() {
  const [menuOpen, setMenuOpen] = useState(false);
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const userMenuRef = useRef(null);
  const compact = useMediaQuery(COMPACT);

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

  // A menu left open on a narrow screen should not reappear when the window
  // widens past the breakpoint and narrows again
  useEffect(() => {
    if (!compact) setMenuOpen(false);
  }, [compact]);

  async function handleLogout() {
    setUserMenuOpen(false);
    setMenuOpen(false);
    await logout();
    navigate("/");
  }

  const displayName = user?.full_name || user?.email;
  const roleName = user?.role?.name || user?.role;
  const staffLinks = user ? STAFF_LINKS[roleName] || [] : [];

  const renderLinks = (links, className) => (
    <ul className={`pn-links ${className}`}>
      {links.map((link) => (
        <li key={link.to}>
          <NavLink
            to={link.to}
            end={link.to === "/"}
            className={({ isActive }) => `pn-link ${isActive ? "is-active" : ""}`}
            onClick={closeMenu}>
            {link.label}
          </NavLink>
        </li>
      ))}
    </ul>
  );

  const staffGroup = staffLinks.length > 0 && (
    <div className="pn-staff">
      {/* Only shown in the folded menu, where the divider becomes a heading */}
      <span className="pn-staff-heading">Staff</span>
      {renderLinks(staffLinks, "pn-staff-links")}
    </div>
  );

  // The account button (name, then Log out in its menu), or Log in
  const account = user ? (
    <div className="pn-user" ref={userMenuRef}>
      <button
        type="button"
        className="pn-user-btn"
        aria-label={`Account: ${displayName}`}
        title={displayName}
        aria-expanded={userMenuOpen}
        onClick={() => setUserMenuOpen((open) => !open)}>
        <span className="pn-user-icon" aria-hidden="true">
          <svg viewBox="0 0 24 24">
            <path d="M12 12a4.5 4.5 0 1 0 0-9 4.5 4.5 0 0 0 0 9z" />
            <path d="M4 20c1.5-4 4.5-6 8-6s6.5 2 8 6" />
          </svg>
        </span>
        {/* A long name ends in "…" on the button; the menu shows it in full */}
        <span className="pn-user-name">{displayName}</span>
      </button>

      {userMenuOpen && (
        <div className="pn-user-dropdown">
          {/* One line; a very long name ends in "…" and shows in full on hover */}
          <p className="pn-user-menu-name" title={displayName}>{displayName}</p>
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
  );

  return (
    <header className={`pn-header ${compact ? "is-compact" : ""} ${user ? "is-staff" : ""}`}>
      <div className="pn-inner">
        <Link to="/" className="pn-brand" onClick={closeMenu}>
          <span className="pn-logo">
            <img src={logo} alt="" />
          </span>
          <span className="pn-brand-name">GeoAlert</span>
        </Link>

        {/* On a narrow screen the bell stays in sight, beside the ☰ button */}
        <div className="pn-compact-actions">
          {user && compact && <NotificationBell />}
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
        </div>

        <nav
          id="pn-menu"
          className={`pn-menu ${menuOpen ? "is-open" : ""}`}
          aria-label="Main">
          {renderLinks(PUBLIC_LINKS, "pn-public-links")}

          {compact ? (
            // Folded menu: the role's pages under a Staff heading, then the
            // name (or Log in) at the bottom
            <>
              {staffGroup}
              {account}
            </>
          ) : (
            // One right-hand slot, the same width signed in or out, so the
            // public links never move: Log in, or the bell, the name and the
            // ☰ staff menu right of the name
            <div className="pn-account">
              {/* Only mounted (and polling) while someone is logged in */}
              {user && <NotificationBell />}
              {account}
              {staffLinks.length > 0 && <RoleMenu links={staffLinks} />}
            </div>
          )}
        </nav>
      </div>
    </header>
  );
}
