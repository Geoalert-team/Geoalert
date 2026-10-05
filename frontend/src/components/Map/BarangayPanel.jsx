import React, { useEffect, useRef } from 'react';
import { severityInfo, verificationInfo, hazardIconPath, hazardColor, SEVERITY_RANK } from './hazardInfo';

const PIN_PATH = 'M12 2a7 7 0 0 0-7 7c0 5.3 7 13 7 13s7-7.7 7-13a7 7 0 0 0-7-7z';

// Barangay-specific hazard information. Uses the same slide-in panel as HazardPanel.
export default function BarangayPanel({ barangay, hazards, open, onClose, onSelectHazard }) {
  const closeRef = useRef(null);

  useEffect(() => {
    if (open) closeRef.current?.focus({ preventScroll: true });
  }, [barangay?.id, open]);

  const sorted = [...hazards].sort(
    (a, b) => (SEVERITY_RANK[b.severity] || 0) - (SEVERITY_RANK[a.severity] || 0),
  );
  const highest = sorted[0] ? severityInfo(sorted[0].severity) : null;
  const unconfirmed = hazards.filter((h) => (h.verificationStatus || 'Pending') !== 'Confirmed').length;

  return (
    <aside className={`pm-panel ${open ? 'is-open' : ''}`} aria-label="Barangay details">
      {barangay && (
        <div className="pm-panel-inner">
          <div className="pm-panel-head">
            <div
              className="pm-panel-icon"
              style={{ background: highest?.tint || '#eef1f5', color: highest?.color || '#43516a' }}
              aria-hidden="true"
            >
              <svg viewBox="0 0 24 24"><path d={PIN_PATH} /></svg>
            </div>
            <div className="pm-panel-title">
              <h2>{barangay.name}</h2>
              <p>Barangay in {barangay.municipality || 'Talisay City'}</p>
            </div>
            <button ref={closeRef} type="button" className="pm-panel-close" onClick={onClose}>
              <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18" /></svg>
              <span className="pm-visually-hidden">Close details</span>
            </button>
          </div>

          {highest ? (
            <span className="pm-badge" style={{ background: highest.tint, color: highest.text }}>
              <span className="pm-badge-dot" style={{ background: highest.color }} />
              Highest level: {highest.label.toLowerCase()}
            </span>
          ) : (
            <span className="pm-badge" style={{ background: '#eef1f5', color: '#43516a' }}>
              <span className="pm-badge-dot" style={{ background: '#6a778d' }} />
              No active hazards
            </span>
          )}

          <div className="pm-tabpanel">
            <h3>{hazards.length === 1 ? '1 active hazard' : `${hazards.length} active hazards`}</h3>

            {hazards.length === 0 ? (
              <p className="pm-muted">
                The DRRMO hasn't published a hazard for this barangay. During heavy rain or
                other emergencies, check with your barangay officials for the latest conditions.
              </p>
            ) : (
              <ul className="pm-brgy-list">
                {sorted.map((h) => {
                  const sev = severityInfo(h.severity);
                  const ver = verificationInfo(h.verificationStatus);
                  return (
                    <li key={h.id}>
                      <button type="button" onClick={() => onSelectHazard(h)}>
                        <span className="pm-brgy-icon" style={{ background: sev.tint, color: hazardColor(h.type) }}>
                          <svg viewBox="0 0 24 24" aria-hidden="true"><path d={hazardIconPath(h.type)} /></svg>
                        </span>
                        <span>
                          <strong>{h.type}</strong>
                          <small>{sev.label}, {ver.short}</small>
                        </span>
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}

            {unconfirmed > 0 && (
              <p className="pm-muted">
                {unconfirmed === hazards.length
                  ? 'None of these zones have been confirmed on the ground yet.'
                  : `${unconfirmed} of these zones haven't been confirmed on the ground yet.`}{' '}
                On the map, pins with a green check have been confirmed.
              </p>
            )}
          </div>
        </div>
      )}
    </aside>
  );
}