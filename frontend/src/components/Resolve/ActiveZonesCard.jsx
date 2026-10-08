import React, { useCallback, useEffect, useState } from 'react';
import { hazardsApi } from '../../api/hazardsApi';
import ResolveHazardForm from './ResolveHazardForm';

const CHIP = { Red: 'db-chip-danger', Orange: 'db-chip-warn', Green: 'db-chip-ok' };

function zoneLabel(props) {
  const type = props.hazard_type_name || props.hazard_type_details?.name || props.hazard_type_detail?.name || 'Hazard';
  const where = props.barangay_name || props.barangay_details?.name || props.barangay_detail?.name || 'Talisay City';
  return `${type} · ${where}`;
}

/**
 * Drop-in dashboard card: lists the hazard zones that are still active and
 * lets DRRMO resolve any of them. Fetches its own data and styles itself
 * with db- classes from Dashboard.css — no extra stylesheet.
 *
 * Props:
 *   onResolved()  optional — called after a successful resolve so the
 *                 parent dashboard can refresh its own counters
 */
export default function ActiveZonesCard({ onResolved }) {
  const [zones, setZones] = useState([]);
  const [resolvedTotal, setResolvedTotal] = useState(null);
  const [loading, setLoading] = useState(true);
  const [target, setTarget] = useState(null); // { id, title } of the zone being resolved

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const geo = await hazardsApi.list();
      setZones(
        (geo.features || []).map((f) => ({
          id: f.id ?? f.properties?.id,
          ...f.properties,
        }))
      );
    } catch {
      setZones([]);
    } finally {
      setLoading(false);
    }

    // Resolved zones never come back from /api/hazards/ (it filters to
    // Active), so the running total needs its own call.
    try {
      const res = await hazardsApi.resolved(1);
      setResolvedTotal(res.count);
    } catch {
      setResolvedTotal(null);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  // Escape closes the resolve dialog
  useEffect(() => {
    if (!target) return undefined;
    const onKey = (e) => { if (e.key === 'Escape') setTarget(null); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [target]);

  function handleResolved() {
    setTarget(null);
    load();
    onResolved?.();
  }

  return (
    <div className="db-card">
      <h2>Active hazard zones</h2>
      <p className="db-card-sub">
        {loading
          ? 'Loading…'
          : `${zones.length} active${resolvedTotal !== null ? ` · ${resolvedTotal} resolved to date` : ''}`}
      </p>

      {!loading && zones.length === 0 ? (
        <p className="db-empty">No hazard zones are active right now.</p>
      ) : (
        <div className="db-list">
          {zones.map((z) => (
            <div key={z.id} className="db-item">
              <div className="db-item-head">
                <span className="db-item-title">{zoneLabel(z)}</span>
                <button
                  type="button"
                  className="db-btn db-btn-outline db-btn-sm"
                  onClick={() => setTarget({ id: z.id, title: zoneLabel(z) })}
                >
                  Resolve
                </button>
              </div>
              <div className="db-item-meta">
                <span className={`db-chip ${CHIP[z.severity] || ''}`}>{z.severity}</span>
                {' '}Active since {z.activated_at ? new Date(z.activated_at).toLocaleDateString() : 'unknown'}
              </div>
            </div>
          ))}
        </div>
      )}

      {target && (
        <div
          className="db-modal-backdrop"
          role="dialog"
          aria-modal="true"
          aria-label="Resolve hazard zone"
          onClick={(e) => { if (e.target === e.currentTarget) setTarget(null); }}
        >
          <div className="db-modal">
            <ResolveHazardForm
              zoneId={target.id}
              title={target.title}
              onCancel={() => setTarget(null)}
              onResolved={handleResolved}
            />
          </div>
        </div>
      )}
    </div>
  );
}