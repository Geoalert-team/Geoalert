import React, { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { severityInfo, hazardIconPath, guidanceFor, DRRMO_HOTLINE } from './hazardInfo';

const TABS = [
  { key: 'overview', label: 'Overview' },
  { key: 'todo', label: 'What to do' },
  { key: 'history', label: 'History' },
];

function formatDate(iso) {
  if (!iso) return 'Not recorded';
  return new Date(iso).toLocaleDateString('en-PH', { year: 'numeric', month: 'long', day: 'numeric' });
}

// Slides in from the left (desktop) or up from the bottom (mobile)
export default function HazardPanel({ item, open, onClose }) {
  const [tab, setTab] = useState('overview');
  const closeRef = useRef(null);

  // Go back to the Overview tab and move focus into the panel whenever a new pin is chosen
  useEffect(() => {
    setTab('overview');
    if (open) closeRef.current?.focus({ preventScroll: true });
  }, [item?.id, open]);

  const sev = item ? severityInfo(item.severity) : null;

  return (
    <aside className={`pm-panel ${open ? 'is-open' : ''}`} aria-label="Hazard details">
      {item && (
        <div className="pm-panel-inner">
          {/* ---------- Header ---------- */}
          <div className="pm-panel-head">
            <div className="pm-panel-icon" style={{ background: sev.tint, color: sev.color }} aria-hidden="true">
              <svg viewBox="0 0 24 24"><path d={hazardIconPath(item.type)} /></svg>
            </div>
            <div className="pm-panel-title">
              <h2>{item.location}</h2>
              <p>{item.type} hazard in Talisay City</p>
            </div>
            <button ref={closeRef} type="button" className="pm-panel-close" onClick={onClose}>
              <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18" /></svg>
              <span className="pm-visually-hidden">Close details</span>
            </button>
          </div>

          <span className="pm-badge" style={{ background: sev.tint, color: sev.text }}>
            <span className="pm-badge-dot" style={{ background: sev.color }} />
            {sev.label}
          </span>

          {item.sample && (
            <p className="pm-sample-note">Sample data for design preview. This is not a real hazard.</p>
          )}

          {/* ---------- Tabs ---------- */}
          <div className="pm-tabs" role="tablist" aria-label="Hazard information">
            {TABS.map((t) => (
              <button
                key={t.key}
                type="button"
                role="tab"
                id={`pm-tab-${t.key}`}
                aria-selected={tab === t.key}
                aria-controls={`pm-tabpanel-${t.key}`}
                className={`pm-tab ${tab === t.key ? 'is-active' : ''}`}
                onClick={() => setTab(t.key)}
              >
                {t.label}
              </button>
            ))}
          </div>

          <div
            className="pm-tabpanel"
            role="tabpanel"
            id={`pm-tabpanel-${tab}`}
            aria-labelledby={`pm-tab-${tab}`}
          >
            {tab === 'overview' && (
              <>
                <h3>{sev.label} {item.type.toLowerCase()} advisory</h3>
                <p>{item.description || 'No description has been added for this area yet.'}</p>
                <div className="pm-callout" style={{ background: sev.tint, borderColor: sev.color, color: sev.text }}>
                  <strong>{sev.label}:</strong> {sev.advice}
                </div>
                <dl className="pm-facts">
                  <div>
                    <dt>Status</dt>
                    <dd>{item.status || 'Active'}</dd>
                  </div>
                  <div>
                    <dt>Active since</dt>
                    <dd>{formatDate(item.activatedAt)}</dd>
                  </div>
                </dl>
              </>
            )}

            {tab === 'todo' && (
              <>
                <h3>What to do</h3>
                <ol className="pm-steps">
                  {guidanceFor(item.type).map((step) => (
                    <li key={step}>{step}</li>
                  ))}
                </ol>
                <div className="pm-panel-actions">
                  <a className="pm-btn pm-btn-primary" href={DRRMO_HOTLINE.tel}>
                    Call DRRMO {DRRMO_HOTLINE.label}
                  </a>
                  <Link className="pm-btn pm-btn-outline" to="/what-to-do">Full safety guide</Link>
                </div>
              </>
            )}

            {tab === 'history' && (
              <>
                <h3>History</h3>
                <ul className="pm-timeline">
                  <li>
                    <span className="pm-timeline-dot" style={{ background: sev.color }} />
                    <div>
                      <strong>Marked {sev.label.toLowerCase()}</strong>
                      <span>{formatDate(item.activatedAt)}</span>
                    </div>
                  </li>
                </ul>
                <p className="pm-muted">
                  Past incident records for this area will appear here once they are available.
                </p>
              </>
            )}
          </div>
        </div>
      )}
    </aside>
  );
}