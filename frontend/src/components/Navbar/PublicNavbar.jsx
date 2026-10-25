import React, { useState, useEffect } from "react";
import { Link, NavLink, useNavigate } from "react-router-dom";
import { useAuth } from "../../context/AuthContext";
import NotificationBell from "./NotificationBell";
import AccountMenu, { AccountPanel } from "./AccountMenu";
import useMediaQuery from "./useMediaQuery";
import logo from "../../assets/images/logo1.png";
import "./css/PublicNavbar.css";

/**
 * The one navigation bar, on every page and for everyone.
 *
 * Everyone sees the public links. A signed-in staff member also gets the
 * bell and one account button (AccountMenu.jsx): their name and role, their
 * role's pages and Log out, all in its menu. All of it disappears again on
 * logout. Map is a public link, so no role lists it again.
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
// /app/analytics link still resolves. The icons are the dashboards' own.
const DASHBOARD = { to: "/app/dashboard", label: "Dashboard", icon: "grid" };
const HISTORY = { to: "/app/history", label: "History", icon: "clock" };
const REPORTS = { to: "/app/reports", label: "Reports", icon: "list" };
const SECURITY = { to: "/app/security", label: "Security", icon: "shield" };
const STAFF_LINKS = {
  System_Admin: [DASHBOARD, HISTORY, REPORTS, SECURITY],
  DRRMO_Officer: [DASHBOARD, HISTORY, REPORTS, SECURITY],
  Barangay_Personnel: [DASHBOARD, SECURITY],
};

// Below this width the bar folds into the ☰ menu, signed in or out. The
// right-hand slot is the same width either way (so the links never move),
// and the whole bar needs about 939 px; folding below 960 leaves a margin.
const COMPACT = "(max-width: 959px)";

export default function PublicNavbar() {
  const [menuOpen, setMenuOpen] = useState(false);
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const compact = useMediaQuery(COMPACT);

  // Close the mobile menu after a link is tapped
  const closeMenu = () => setMenuOpen(false);

  // A menu left open on a narrow screen should not reappear when the window
  // widens past the breakpoint and narrows again
  useEffect(() => {
    if (!compact) setMenuOpen(false);
  }, [compact]);

  async function handleLogout() {
    setMenuOpen(false);
    await logout();
    navigate("/");
  }

  const roleName = user?.role?.name || user?.role;
  const staffLinks = user ? STAFF_LINKS[roleName] || [] : [];

  const publicLinks = (
    <ul className="pn-links pn-public-links">
      {PUBLIC_LINKS.map((link) => (
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

  const login = (
    <Link to="/login" className="pn-login" onClick={closeMenu}>
      Log in
    </Link>
  );

  return (
    <header className={`pn-header ${compact ? "is-compact" : ""}`}>
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
          {publicLinks}

          {compact ? (
            // Folded menu: the account panel, already open (who you are,
            // your pages, Log out), or Log in, at the bottom
            user ? (
              <AccountPanel user={user} links={staffLinks} onNavigate={closeMenu} onLogout={handleLogout} />
            ) : login
          ) : (
            // One right-hand slot, the same width signed in or out, so the
            // public links never move: Log in, or the bell and the account
            // button
            <div className="pn-account">
              {/* Only mounted (and polling) while someone is logged in */}
              {user && <NotificationBell />}
              {user ? <AccountMenu user={user} links={staffLinks} onLogout={handleLogout} /> : login}
            </div>
          )}
        </nav>
      </div>
    </header>
  );
}
