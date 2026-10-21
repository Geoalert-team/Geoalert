import React, { useEffect, useRef, useState } from "react";
import { NavLink, useLocation } from "react-router-dom";

// How long the menu waits before closing once the pointer leaves, so it
// doesn't snap shut while the pointer crosses the gap into it
export const CLOSE_DELAY = 150;

/**
 * The staff pages (Dashboard, History, Reports, Security) behind one ☰
 * icon at the right of the navigation bar, so the bar stays as uncluttered
 * as the public one.
 *
 * It opens on hover, and also on click or tap (touch screens have no hover)
 * and from the keyboard (it is a button). Escape, Tab past the last item,
 * a click elsewhere or choosing a page closes it. A disclosure of plain
 * links, not an ARIA menu: Tab moves through the pages as anywhere else.
 *
 * Props:
 *   links  [{ to, label }] for the signed-in role
 */
export default function RoleMenu({ links }) {
  const [open, setOpen] = useState(false);
  // Opened (or kept open) by a click: leaving with the pointer no longer
  // closes it, only another click, Escape, Tab or a click elsewhere
  const [pinned, setPinned] = useState(false);
  const wrapRef = useRef(null);
  const buttonRef = useRef(null);
  const closeTimer = useRef(null);
  const { pathname } = useLocation();
  const onStaffPage = links.some((l) => pathname === l.to || pathname.startsWith(`${l.to}/`));

  const cancelClose = () => clearTimeout(closeTimer.current);
  const openNow = () => { cancelClose(); setOpen(true); };
  const closeSoon = () => { cancelClose(); closeTimer.current = setTimeout(() => setOpen(false), CLOSE_DELAY); };
  const closeNow = () => { cancelClose(); setOpen(false); setPinned(false); };

  // Hover only for a real mouse: a tap sends a fake hover just before its
  // click, which would open the menu and then close it again at once
  const onPointerEnter = (e) => { if (e.pointerType === "mouse") openNow(); };
  const onPointerLeave = (e) => { if (e.pointerType === "mouse" && !pinned) closeSoon(); };

  function onClick() {
    if (open && pinned) {
      closeNow();
    } else {
      openNow(); // closed: open it; open from hovering: keep it open
      setPinned(true);
    }
  }

  useEffect(() => () => clearTimeout(closeTimer.current), []);

  // A click or tap anywhere else closes a menu opened by clicking
  useEffect(() => {
    if (!open) return undefined;
    function onDown(e) {
      if (wrapRef.current && !wrapRef.current.contains(e.target)) closeNow();
    }
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [open]);

  function onKeyDown(e) {
    if (e.key === "Escape" && open) {
      closeNow();
      buttonRef.current?.focus();
    }
  }

  // Tabbing out past the last page closes it
  function onBlur(e) {
    if (wrapRef.current && !wrapRef.current.contains(e.relatedTarget)) closeNow();
  }

  return (
    <div
      className="pn-role"
      ref={wrapRef}
      onPointerEnter={onPointerEnter}
      onPointerLeave={onPointerLeave}
      onKeyDown={onKeyDown}
      onBlur={onBlur}>
      <button
        ref={buttonRef}
        type="button"
        className={`pn-role-btn ${onStaffPage ? "is-active" : ""}`}
        aria-label="Staff menu"
        aria-haspopup="true"
        aria-expanded={open}
        aria-controls="pn-role-menu"
        onClick={onClick}>
        <span className="pn-role-bars" aria-hidden="true">
          <span />
          <span />
          <span />
        </span>
      </button>

      {open && (
        <ul id="pn-role-menu" className="pn-role-menu">
          {links.map((link) => (
            <li key={link.to}>
              <NavLink
                to={link.to}
                className={({ isActive }) => `pn-role-link ${isActive ? "is-active" : ""}`}
                onClick={closeNow}>
                {link.label}
              </NavLink>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
