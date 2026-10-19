import React, { useEffect, useRef, useState } from 'react';
import { barangaysApi } from '../../api/barangaysApi';
import { severityInfo, hazardIconPath, hazardColor, SEVERITY_RANK } from './hazardInfo';
import SpotReading from './SpotReading';

const PIN_PATH = 'M12 2a7 7 0 0 0-7 7c0 5.3 7 13 7 13s7-7.7 7-13a7 7 0 0 0-7-7z';

const bySeverity = (a, b) => (SEVERITY_RANK[b.severity] || 0) - (SEVERITY_RANK[a.severity] || 0);

function HazardList({ items, onSelectHazard }) {
  return (
    <ul className="pm-brgy-list">
      {items.map((h) => {
        const sev = severityInfo(h.severity);
        return (
          <li key={h.id}>
            <button type="button" onClick={() => onSelectHazard(h)}>
              <span className="pm-brgy-icon" style={{ background: sev.tint, color: hazardColor(h.type) }}>
                <svg viewBox="0 0 24 24" aria-hidden="true"><path d={hazardIconPath(h.type)} /></svg>
              </span>
              <span>
                <strong>{h.type}</strong>
                <small>{sev.label}</small>
              </span>
            </button>
          </li>
        );
      })}
    </ul>
  );
}

// Barangay-specific hazard information. Uses the same slide-in panel as HazardPanel.
//
// hazards     the fallback: hazards whose pin is inside the barangay
// allHazards  every hazard on the map, to look up the ids the server returns
//
// The server answers with PostGIS which zones lie entirely inside the
// barangay (ST_Within) and which cross its border (ST_Intersects). Going by
// pins missed a zone reaching in from a neighbouring barangay.
//
// spot, susceptibilityIndex, rivers  the tapped point and the data to read
// it with, for the "This spot" section (no spot when chosen from search)
export default function BarangayPanel({
  barangay, hazards, allHazards = [], open, onClose, onSelectHazard,
  spot = null, susceptibilityIndex = null, rivers = null,
}) {
  const closeRef = useRef(null);
  const [split, setSplit] = useState(null); // { inside: [ids], crossing: [ids] } or null

  useEffect(() => {
    if (open) closeRef.current?.focus({ preventScroll: true });
  }, [barangay?.id, open]);

  useEffect(() => {
    setSplit(null);
    if (!barangay?.id || !open) return undefined;
    let live = true;
    barangaysApi.hazards(barangay.id)
      .then((data) => { if (live) setSplit(data); })
      .catch(() => { /* keep the pin-based list */ });
    return () => { live = false; };
  }, [barangay?.id, open]);

  const lookup = (ids) => ids
    .map((id) => allHazards.find((h) => String(h.id) === String(id)))
    .filter(Boolean)
    .sort(bySeverity);
  const inside = split ? lookup(split.inside) : [];
  const crossing = split ? lookup(split.crossing) : [];
  const shown = split ? [...inside, ...crossing] : hazards;

  const sorted = [...shown].sort(bySeverity);
  const highest = sorted[0] ? severityInfo(sorted[0].severity) : null;

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

          <SpotReading spot={spot} index={susceptibilityIndex} rivers={rivers} />

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
            <h3>{shown.length === 1 ? '1 active hazard' : `${shown.length} active hazards`}</h3>

            {shown.length === 0 ? (
              <p className="pm-muted">
                The DRRMO hasn't published a hazard for this barangay. During heavy rain or
                other emergencies, check with your barangay officials for the latest conditions.
              </p>
            ) : split ? (
              <>
                {inside.length > 0 && (
                  <>
                    <p className="pm-brgy-group">Entirely inside {barangay.name}</p>
                    <HazardList items={inside} onSelectHazard={onSelectHazard} />
                  </>
                )}
                {crossing.length > 0 && (
                  <>
                    <p className="pm-brgy-group">Crossing into {barangay.name} from a neighbouring barangay</p>
                    <HazardList items={crossing} onSelectHazard={onSelectHazard} />
                  </>
                )}
              </>
            ) : (
              <HazardList items={sorted} onSelectHazard={onSelectHazard} />
            )}
          </div>
        </div>
      )}
    </aside>
  );
}