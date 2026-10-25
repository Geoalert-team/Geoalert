import React, { useEffect, useRef, useState } from "react";
import { NavLink, useLocation } from "react-router-dom";
import { Icon, initials, roleMeta } from "../../pages/Dashboard/admin/adminShared";

/**
 * Everything about the signed-in person in one place: who they are, their
 * role's pages (Dashboard, History, Reports, Security) and Log out.
 *
 * The avatar is the dashboards' one (initials in the role's colour), so the
 * bar and the staff pages read as the same app.
 *
 * AccountMenu is the wide bar's button and dropdown. It opens on a click
 * (like the bell); Escape, Tab past the last item, a click elsewhere or
 * choosing a page closes it. A disclosure of plain links, not an ARIA menu:
 * Tab moves through it as anywhere else. AccountPanel is the dropdown's
 * content on its own, shown already open at the bottom of the folded ☰ menu.
 *
 * Props:
 *   user      the signed-in user ({ full_name, email, role })
 *   links     [{ to, label, icon }] for the signed-in role
 *   onLogout  called after Log out is chosen
 */

const displayName = (user) => user?.full_name || user?.email || "";

// "Juan Dela Cruz" -> "Juan"; with no name, the part of the email before @
function firstName(user) {
  if (user?.full_name) return user.full_name.trim().split(/\s+/)[0];
  return (user?.email || "").split("@")[0];
}

function Avatar({ user, size }) {
  return (
    <span className={`pn-avatar pn-avatar-${size} pn-tone-${roleMeta(user?.role).tone}`} aria-hidden="true">
      {initials(user)}
    </span>
  );
}

export function AccountPanel({ user, links, onNavigate, onLogout }) {
  const name = displayName(user);
  const meta = roleMeta(user?.role);
  return (
    <div className="pn-acct-panel">
      <div className="pn-acct-head">
        <Avatar user={user} size="lg" />
        <div className="pn-acct-who">
          {/* One line; a very long name ends in "…" and shows in full on hover */}
          <p className="pn-acct-name" title={name}>{name}</p>
          <span className={`pn-acct-role pn-tone-${meta.tone}`}>{meta.short}</span>
          {user?.email && user.email !== name && (
            <p className="pn-acct-email" title={user.email}>{user.email}</p>
          )}
        </div>
      </div>

      {links.length > 0 && (
        <ul className="pn-acct-links">
          {links.map((link) => (
            <li key={link.to}>
              <NavLink
                to={link.to}
                className={({ isActive }) => `pn-acct-link ${isActive ? "is-active" : ""}`}
                onClick={onNavigate}>
                <Icon name={link.icon} size={17} />
                {link.label}
              </NavLink>
            </li>
          ))}
        </ul>
      )}

      <button type="button" className="pn-acct-logout" onClick={onLogout}>
        <Icon name="power" size={17} />
        Log out
      </button>
    </div>
  );
}

export default function AccountMenu({ user, links, onLogout }) {
  const [open, setOpen] = useState(false);
  const wrapRef = useRef(null);
  const buttonRef = useRef(null);
  const { pathname } = useLocation();
  const onStaffPage = links.some((l) => pathname === l.to || pathname.startsWith(`${l.to}/`));
  const name = displayName(user);

  // A click or tap anywhere else closes it
  useEffect(() => {
    if (!open) return undefined;
    function onDown(e) {
      if (wrapRef.current && !wrapRef.current.contains(e.target)) setOpen(false);
    }
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [open]);

  function onKeyDown(e) {
    if (e.key === "Escape" && open) {
      setOpen(false);
      buttonRef.current?.focus();
    }
  }

  // Tabbing out past the last item closes it
  function onBlur(e) {
    if (wrapRef.current && !wrapRef.current.contains(e.relatedTarget)) setOpen(false);
  }

  function logout() {
    setOpen(false);
    onLogout();
  }

  return (
    <div className="pn-acct" ref={wrapRef} onKeyDown={onKeyDown} onBlur={onBlur}>
      <button
        ref={buttonRef}
        type="button"
        className={`pn-acct-btn ${onStaffPage ? "is-active" : ""}`}
        aria-label={`Account: ${name}`}
        title={name}
        aria-expanded={open}
        aria-controls="pn-acct-menu"
        onClick={() => setOpen((o) => !o)}>
        <Avatar user={user} size="sm" />
        {/* A long first name ends in "…"; the menu shows the name in full */}
        <span className="pn-acct-first">{firstName(user)}</span>
        <Icon name="chevronDown" size={16} className="pn-acct-chevron" />
      </button>

      {open && (
        <div id="pn-acct-menu" className="pn-acct-menu">
          <AccountPanel user={user} links={links} onNavigate={() => setOpen(false)} onLogout={logout} />
        </div>
      )}
    </div>
  );
}
