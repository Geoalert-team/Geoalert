import React, { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useHazardAlerts } from "../../hooks/useHazardAlerts";
import { hazardIconPath, severityInfo } from "../Map/hazardInfo";
import { alertKey, placesText, unseenAlerts } from "../../utils/hazardAlerts";
import { timeAgo } from "../../utils/timeAgo";
import "./css/NotificationBell.css";

/**
 * The bell for residents, who browse without an account. It lists every
 * hazard on the public map, worst first, and opens each one on the map.
 *
 * There is no account to mark alerts read against, so this browser remembers
 * which alerts it has shown (localStorage). The badge counts the rest;
 * opening the panel clears it. A zone raised to a higher level counts as new
 * again. Without storage (private window, blocked site data) every active
 * alert simply counts as new.
 *
 * Looks like the staff bell (NotificationBell.jsx) and shares its panel
 * styles. Signed-in staff get that one instead; their hazard alerts arrive
 * as real notifications.
 */
const SEEN_KEY = "geoalert.seenHazardAlerts";

function readSeen() {
  try {
    const saved = JSON.parse(window.localStorage.getItem(SEEN_KEY));
    return Array.isArray(saved) ? saved : [];
  } catch {
    return [];
  }
}

function writeSeen(keys) {
  try {
    window.localStorage.setItem(SEEN_KEY, JSON.stringify(keys));
  } catch {
    // Storage unavailable: the badge just won't remember between visits
  }
}

const BELL = (
  <>
    <path d="M18 8a6 6 0 1 0-12 0c0 7-3 9-3 9h18s-3-2-3-9z" />
    <path d="M13.7 21a2 2 0 0 1-3.4 0" />
  </>
);

export default function ResidentAlertBell() {
  const [open, setOpen] = useState(false);
  const [seen, setSeen] = useState(readSeen);
  // The alerts that were new when the panel opened, so they stay marked
  // while it is open even though opening it has already cleared the badge
  const [freshIds, setFreshIds] = useState(() => new Set());
  const [ring, setRing] = useState(false);
  const ref = useRef(null);
  const lastUnseen = useRef(null);
  const navigate = useNavigate();
  const alerts = useHazardAlerts();

  const unseen = unseenAlerts(alerts || [], seen);
  const unseenCount = unseen.length;

  // Close on outside click or Escape
  useEffect(() => {
    if (!open) return undefined;
    function onDown(e) {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false);
    }
    function onKey(e) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  // Shake the bell when a new alert arrives, not on the first load
  useEffect(() => {
    if (alerts === null) return undefined;
    if (lastUnseen.current !== null && unseenCount > lastUnseen.current) {
      setRing(true);
      const t = setTimeout(() => setRing(false), 1200);
      lastUnseen.current = unseenCount;
      return () => clearTimeout(t);
    }
    lastUnseen.current = unseenCount;
    return undefined;
  }, [alerts, unseenCount]);

  // An alert that arrives while the panel is open has been seen too
  useEffect(() => {
    if (!open || !alerts || unseenCount === 0) return;
    setFreshIds((ids) => new Set([...ids, ...unseen.map((a) => a.id)]));
    markSeen(alerts);
  }, [open, alerts, unseenCount]);   // eslint-disable-line react-hooks/exhaustive-deps

  function markSeen(list) {
    // Only the alerts still active are kept, so the list never grows
    const keys = list.map(alertKey);
    setSeen(keys);
    writeSeen(keys);
  }

  function toggle() {
    if (!open) setFreshIds(new Set(unseen.map((a) => a.id)));
    setOpen((o) => !o);
  }

  function openAlert(alert) {
    setOpen(false);
    navigate(`/map?zone=${encodeURIComponent(alert.id)}`);
  }

  const freshCount = alerts ? alerts.filter((a) => freshIds.has(a.id)).length : 0;

  return (
    <div className="pn-bell nb" ref={ref}>
      <button
        type="button"
        className={`pn-bell-btn ${ring ? "nb-ring" : ""}`}
        aria-expanded={open}
        aria-haspopup="dialog"
        aria-label={`Hazard alerts${unseenCount ? `, ${unseenCount} new` : ""}`}
        onClick={toggle}
      >
        <svg viewBox="0 0 24 24" aria-hidden="true">{BELL}</svg>
        {unseenCount > 0 && <span className="pn-bell-badge">{unseenCount > 99 ? "99+" : unseenCount}</span>}
      </button>

      {open && (
        <div className="nb-panel" role="dialog" aria-label="Hazard alerts">
          <div className="nb-head nb-head-ruled">
            <div className="nb-head-title">
              <h2>Hazard alerts</h2>
              {freshCount > 0 && <span className="nb-count">{freshCount} new</span>}
            </div>
            <Link to="/map" className="nb-markall" onClick={() => setOpen(false)}>Open the map</Link>
          </div>

          <div className="nb-body">
            {alerts === null ? (
              <div className="nb-empty">
                <span className="nb-empty-icon"><svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{BELL}</svg></span>
                <strong>Checking for hazard alerts…</strong>
                <p>If this doesn't change, open the map to see the latest hazards.</p>
              </div>
            ) : alerts.length === 0 ? (
              <div className="nb-empty">
                <span className="nb-empty-icon nb-tone-good"><svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M20 6 9 17l-5-5" /></svg></span>
                <strong>No active hazard alerts</strong>
                <p>When the DRRMO warns of a flood, landslide or fire in Talisay City, it shows up here.</p>
              </div>
            ) : (
              <ul className="nb-list">
                {alerts.map((alert) => {
                  const sev = severityInfo(alert.severity);
                  const fresh = freshIds.has(alert.id);
                  return (
                    <li key={alert.id}>
                      <button
                        type="button"
                        className={`nb-item has-link ${fresh ? "is-unread" : ""}`}
                        onClick={() => openAlert(alert)}
                      >
                        <span className="nb-icon" style={{ background: sev.tint, color: sev.color }}>
                          <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                            <path d={hazardIconPath(alert.type)} />
                          </svg>
                        </span>
                        <span className="nb-item-text">
                          <span className="nb-item-title">{alert.type} alert · {sev.label}</span>
                          <span className="nb-item-content">In {placesText(alert.barangays)}. {sev.advice}</span>
                          {alert.activatedAt && (
                            <span className="nb-item-meta" title={new Date(alert.activatedAt).toLocaleString()}>
                              Issued {timeAgo(alert.activatedAt)}{alert.sample ? " · Sample data" : ""}
                            </span>
                          )}
                        </span>
                        {fresh && <span className="nb-dot" aria-label="New" />}
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
