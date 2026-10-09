import React, { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { severityInfo, hazardIconPath, hazardColor, DRRMO_HOTLINE } from './hazardInfo';
import VerificationNotice from './VerificationNotice';
import GuidanceSteps from './GuidanceSteps';
import ResolveHazardForm from '../Resolve/ResolveHazardForm';
// The resolve form is built from db- classes; .db-scope below supplies the
// tokens so it looks right inside the map panel too.
import '../../pages/css/Dashboard.css';

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
export default function HazardPanel({ item, open, onClose, onVerified, onResolved, overlaps = [] }) {
  const [tab, setTab] = useState('overview');
  const [resolving, setResolving] = useState(false);
  const closeRef = useRef(null);
  const { canPublish } = useAuth();

  // Go back to the Overview tab and move focus into the panel whenever a new pin is chosen
  useEffect(() => {
    setTab('overview');
    setResolving(false);
    if (open) closeRef.current?.focus({ preventScroll: true });
  }, [item?.id, open]);

  const sev = item ? severityInfo(item.severity) : null;

  // Only DRRMO/Admin can close out a hazard, and only one that's still live.
  const canResolve =
    canPublish && item && !item.sample && (item.status || 'Active') === 'Active';

  return (
    <aside className={`pm-panel ${open ? 'is-open' : ''}`} aria-label="Hazard details">
      {item && (
        <div className="pm-panel-inner">
          {/* ---------- Header ---------- */}
          <div className="pm-panel-head">
            <div className="pm-panel-icon" style={{ background: sev.tint, color: hazardColor(item.type) }} aria-hidden="true">
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
                {overlaps.length > 0 && (
                  <div className="pm-overlap">
                    <strong>This area overlaps {overlaps.length === 1 ? 'another hazard zone' : `${overlaps.length} other hazard zones`}.</strong>
                    <ul>
                      {overlaps.map((other) => {
                        const osev = severityInfo(other.severity);
                        return (
                          <li key={other.id}>
                            <span className="pm-overlap-dot" style={{ background: osev.color }} />
                            {other.type} · {osev.label}
                          </li>
                        );
                      })}
                    </ul>
                    <p>Follow the most serious one.</p>
                  </div>
                )}

                <VerificationNotice item={item} onVerified={onVerified} />
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

                {/* ---------- DRRMO: close the hazard out ---------- */}
                {canResolve && (
                  <div className="db-scope db-embed">
                    {resolving ? (
                      <ResolveHazardForm
                        zoneId={item.id}
                        title={`${item.type} · ${item.location}`}
                        onCancel={() => setResolving(false)}
                        onResolved={(zone) => {
                          setResolving(false);
                          onResolved?.(zone);
                        }}
                      />
                    ) : (
                      <button type="button" className="db-btn db-btn-outline" onClick={() => setResolving(true)}>
                        Mark as resolved
                      </button>
                    )}
                  </div>
                )}
              </>
            )}

            {tab === 'todo' && (
              <>
                <h3>What to do</h3>
                <GuidanceSteps type={item.type} />
                <div className="pm-panel-actions">
                  <a className="pm-btn pm-btn-primary" href={DRRMO_HOTLINE.tel}>
                    Call DRRMO {DRRMO_HOTLINE.label}
                  </a>
                  {/* Carries the hazard through, so the guidance library opens on this
                      hazard instead of whatever it shows by default. */}
                  <Link
                    className="pm-btn pm-btn-outline"
                    to={`/what-to-do?hazard=${encodeURIComponent(item.type)}`}
                  >
                    Full safety guide
                  </Link>
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