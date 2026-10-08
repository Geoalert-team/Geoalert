import React, { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useNotifications } from "../../hooks/useNotifications";
import { hazardIconPath, severityInfo } from "../Map/hazardInfo";
import "./css/NotificationBell.css";

// Stroke icons (24x24) for the non-hazard categories
const ICONS = {
  report: (
    <>
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <path d="M14 2v6h6M8 13h8M8 17h5" />
    </>
  ),
  account: (
    <>
      <circle cx="12" cy="8" r="4" />
      <path d="M4 21v-1a6 6 0 0 1 6-6h4a6 6 0 0 1 6 6v1" />
    </>
  ),
  security: (
    <>
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
      <path d="M12 8v4M12 16h.01" />
    </>
  ),
  check: <path d="M20 6 9 17l-5-5" />,
  bell: (
    <>
      <path d="M18 8a6 6 0 1 0-12 0c0 7-3 9-3 9h18s-3-2-3-9z" />
      <path d="M13.7 21a2 2 0 0 1-3.4 0" />
    </>
  ),
};

const CATEGORY_LABEL = {
  hazard: "Hazard alert",
  report: "Incident report",
  account: "Account",
  security: "Security",
};

function StrokeIcon({ name, size = 18 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      {ICONS[name]}
    </svg>
  );
}

function title(n) {
  if (n.category === "hazard" && n.hazard) {
    const sev = severityInfo(n.hazard.severity);
    return `${n.hazard.type || "Hazard"} alert · ${sev.label}`;
  }
  if (n.category === "report") {
    if (/rejected/i.test(n.content)) return "Report rejected";
    if (/validated/i.test(n.content)) return "Report validated";
    return "New incident report";
  }
  if (n.category === "security") return "Security alert";
  return CATEGORY_LABEL[n.category] || "Notification";
}

function ItemIcon({ n }) {
  if (n.category === "hazard") {
    const sev = severityInfo(n.hazard?.severity);
    return (
      <span className="nb-icon" style={{ background: sev.tint, color: sev.color }}>
        <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
          <path d={hazardIconPath(n.hazard?.type || "")} />
        </svg>
      </span>
    );
  }
  const tone = n.category === "report"
    ? (/rejected/i.test(n.content) ? "bad" : /validated/i.test(n.content) ? "good" : "info")
    : n.category === "security" ? "warn" : "navy";
  return (
    <span className={`nb-icon nb-tone-${tone}`}>
      <StrokeIcon name={ICONS[n.category] ? n.category : "account"} />
    </span>
  );
}

function timeAgo(value) {
  const seconds = Math.round((Date.now() - new Date(value).getTime()) / 1000);
  if (seconds < 60) return "Just now";
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} hr${hours === 1 ? "" : "s"} ago`;
  const days = Math.round(hours / 24);
  if (days < 7) return `${days} day${days === 1 ? "" : "s"} ago`;
  return new Date(value).toLocaleDateString("en-PH", { month: "short", day: "numeric", year: "numeric" });
}

function dayGroup(value) {
  const d = new Date(value);
  const today = new Date();
  const start = (x) => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime();
  const diff = Math.round((start(today) - start(d)) / 86400000);
  if (diff <= 0) return "Today";
  if (diff === 1) return "Yesterday";
  return "Earlier";
}

export default function NotificationBell() {
  const [open, setOpen] = useState(false);
  const [filter, setFilter] = useState("all");
  const [ring, setRing] = useState(false);
  const ref = useRef(null);
  const lastUnread = useRef(null);
  const navigate = useNavigate();
  const { notifications, unreadCount, markRead, markAllRead } = useNotifications({ enabled: true });

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

  // Shake the bell briefly when a new notification arrives
  useEffect(() => {
    if (lastUnread.current !== null && unreadCount > lastUnread.current) {
      setRing(true);
      const t = setTimeout(() => setRing(false), 1200);
      lastUnread.current = unreadCount;
      return () => clearTimeout(t);
    }
    lastUnread.current = unreadCount;
    return undefined;
  }, [unreadCount]);

  const groups = useMemo(() => {
    const list = notifications.filter((n) => filter === "all" || !n.is_read).slice(0, 30);
    const out = [];
    list.forEach((n) => {
      const g = dayGroup(n.sent_at);
      if (!out.length || out[out.length - 1].label !== g) out.push({ label: g, items: [] });
      out[out.length - 1].items.push(n);
    });
    return out;
  }, [notifications, filter]);

  function openItem(n) {
    if (!n.is_read) markRead(n.id);
    if (n.link) {
      setOpen(false);
      navigate(n.link);
    }
  }

  return (
    <div className="pn-bell nb" ref={ref}>
      <button
        type="button"
        className={`pn-bell-btn ${ring ? "nb-ring" : ""}`}
        aria-expanded={open}
        aria-haspopup="dialog"
        aria-label={`Notifications${unreadCount ? `, ${unreadCount} unread` : ""}`}
        onClick={() => setOpen((o) => !o)}
      >
        <svg viewBox="0 0 24 24" aria-hidden="true">{ICONS.bell}</svg>
        {unreadCount > 0 && <span className="pn-bell-badge">{unreadCount > 99 ? "99+" : unreadCount}</span>}
      </button>

      {open && (
        <div className="nb-panel" role="dialog" aria-label="Notifications">
          <div className="nb-head">
            <div className="nb-head-title">
              <h2>Notifications</h2>
              {unreadCount > 0 && <span className="nb-count">{unreadCount} new</span>}
            </div>
            {unreadCount > 0 && (
              <button type="button" className="nb-markall" onClick={markAllRead}>
                <StrokeIcon name="check" size={15} />
                Mark all as read
              </button>
            )}
          </div>

          <div className="nb-tabs" role="tablist">
            {[["all", "All"], ["unread", "Unread"]].map(([key, label]) => (
              <button
                key={key}
                type="button"
                role="tab"
                aria-selected={filter === key}
                className={`nb-tab ${filter === key ? "is-active" : ""}`}
                onClick={() => setFilter(key)}
              >
                {label}
                {key === "unread" && unreadCount > 0 && <span>{unreadCount}</span>}
              </button>
            ))}
          </div>

          <div className="nb-body">
            {groups.length === 0 ? (
              <div className="nb-empty">
                <span className="nb-empty-icon"><StrokeIcon name={filter === "unread" ? "check" : "bell"} size={22} /></span>
                <strong>{filter === "unread" ? "You're all caught up" : "No notifications yet"}</strong>
                <p>{filter === "unread" ? "There's nothing new since you last checked." : "Hazard alerts and updates about your work will show up here."}</p>
              </div>
            ) : (
              groups.map((g) => (
                <section key={g.label} className="nb-group">
                  <h3>{g.label}</h3>
                  <ul>
                    {g.items.map((n) => (
                      <li key={n.id}>
                        <button
                          type="button"
                          className={`nb-item ${n.is_read ? "" : "is-unread"} ${n.link ? "has-link" : ""}`}
                          onClick={() => openItem(n)}
                        >
                          <ItemIcon n={n} />
                          <span className="nb-item-text">
                            <span className="nb-item-title">{title(n)}</span>
                            <span className="nb-item-content">{n.content}</span>
                            <span className="nb-item-meta" title={new Date(n.sent_at).toLocaleString()}>
                              {timeAgo(n.sent_at)} · {CATEGORY_LABEL[n.category] || "Notification"}
                            </span>
                          </span>
                          {!n.is_read && <span className="nb-dot" aria-label="Unread" />}
                        </button>
                      </li>
                    ))}
                  </ul>
                </section>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
}