import React, { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { hazardsApi } from '../../api/hazardsApi';
import ResolveHazardForm from './ResolveHazardForm';
import RetractHazardForm from './RetractHazardForm';

const PAGE_SIZE = 5;

const CHIP = { Red: 'db-chip-danger', Orange: 'db-chip-warn', Green: 'db-chip-ok' };

function zoneLabel(props) {
  const type = zoneType(props);
  const where = props.barangay_name || props.barangay_details?.name || props.barangay_detail?.name || 'Talisay City';
  return `${type} · ${where}`;
}

function zoneType(props) {
  return props.hazard_type_name || props.hazard_type_details?.name || props.hazard_type_detail?.name || 'Hazard';
}

/**
 * Drop-in dashboard card: lists the hazard zones that are still active and
 * lets DRRMO resolve any of them. Fetches its own data and styles itself
 * with db- classes from Dashboard.css — no extra stylesheet.
 *
 * Props:
 *   onResolved()  optional — called after a successful resolve so the
 *                 parent dashboard can refresh its own counters
 *   fireOnly      the BFP dashboard's card: active fires only, resolved
 *                 with the BFP figures, and no withdrawing (DRRMO's call)
 */
export default function ActiveZonesCard({ onResolved, fireOnly = false }) {
  const [zones, setZones] = useState([]);
  const [resolvedTotal, setResolvedTotal] = useState(null);
  const [withdrawn, setWithdrawn] = useState(null); // { count, results } or null
  const [showWithdrawn, setShowWithdrawn] = useState(false);
  const [loading, setLoading] = useState(true);
  // The zone being closed out: { id, title, mode } where mode is 'resolve'
  // (it happened and is over) or 'retract' (it should never have gone out)
  const [target, setTarget] = useState(null);
  const [page, setPage] = useState(1);
  const [filter, setFilter] = useState('');
  const [hazardFilter, setHazardFilter] = useState('all');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const geo = await hazardsApi.list();
      const all = (geo.features || []).map((f) => ({
        id: f.id ?? f.properties?.id,
        ...f.properties,
      }));
      setZones(fireOnly ? all.filter((z) => zoneType(z).toLowerCase() === 'fire') : all);
    } catch {
      setZones([]);
    } finally {
      setLoading(false);
    }

    // The totals and the withdrawn list below are DRRMO's
    if (fireOnly) return;

    // Resolved zones never come back from /api/hazards/ (it filters to
    // Active), so the running total needs its own call.
    try {
      const res = await hazardsApi.resolved(1);
      setResolvedTotal(res.count);
    } catch {
      setResolvedTotal(null);
    }

    // Withdrawn zones are off the public map and out of the reports, so this
    // is the only place they are visible. Kept on the record on purpose: a
    // system where an inconvenient hazard can be made to have never existed
    // is not auditable.
    try {
      setWithdrawn(await hazardsApi.retracted(20));
    } catch {
      setWithdrawn(null);
    }
  }, [fireOnly]);

  useEffect(() => { load(); }, [load]);

  // Escape closes the resolve dialog
  useEffect(() => {
    if (!target) return undefined;
    const onKey = (e) => { if (e.key === 'Escape') setTarget(null); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [target]);

  // Both outcomes take the zone off the active list and change the totals,
  // so the card reloads either way and the dashboard refreshes its counters.
  function handleClosed() {
    setTarget(null);
    load();
    onResolved?.();
  }

  const query = filter.trim().toLocaleLowerCase();
  const filteredZones = zones.filter((z) => {
    const matchesType = hazardFilter === 'all' || zoneType(z).toLocaleLowerCase().includes(hazardFilter);
    const matchesSearch = !query || `${zoneLabel(z)} ${z.severity || ''}`.toLocaleLowerCase().includes(query);
    return matchesType && matchesSearch;
  });

  // Resolving the last zone on a page or narrowing the filter shrinks the list, so clamp.
  const pages = Math.max(1, Math.ceil(filteredZones.length / PAGE_SIZE));
  const currentPage = Math.min(page, pages);
  const pageZones = filteredZones.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE);

  return (
    <div className="db-card db-active-zones">
      <h2>{fireOnly ? 'Active fires' : 'Active hazard zones'}</h2>
      <p className="db-card-sub">
        {loading
          ? 'Loading…'
          : [
              `${zones.length} active`,
              resolvedTotal !== null ? `${resolvedTotal} resolved to date` : null,
              withdrawn?.count ? `${withdrawn.count} withdrawn` : null,
            ].filter(Boolean).join(' · ')}
      </p>

      {!loading && zones.length > 0 && (
        <div className="db-active-zones-filter">
          {!fireOnly && (
            <div className="db-active-zone-types" role="group" aria-label="Filter active zones by hazard type">
              {['all', 'flood', 'fire', 'landslide'].map((type) => (
                <button
                  key={type}
                  type="button"
                  className={`db-active-zone-type${hazardFilter === type ? ' is-active' : ''}`}
                  aria-pressed={hazardFilter === type}
                  onClick={() => { setHazardFilter(type); setPage(1); }}
                >
                  {type === 'all' ? 'All types' : `${type[0].toUpperCase()}${type.slice(1)}`}
                </button>
              ))}
            </div>
          )}
          <div className="db-active-zones-search-row">
            <label className="db-field">
              Search active zones
              <input
                type="search"
                value={filter}
                onChange={(e) => { setFilter(e.target.value); setPage(1); }}
                placeholder="Barangay or severity"
                aria-label="Search active hazard zones by barangay or severity"
              />
            </label>
            <span className="db-active-zones-count">
              {filteredZones.length} of {zones.length} active zone{zones.length === 1 ? '' : 's'}
            </span>
          </div>
        </div>
      )}

      {!loading && zones.length === 0 ? (
        <p className="db-empty">{fireOnly ? 'No fires are active right now.' : 'No hazard zones are active right now.'}</p>
      ) : !loading && filteredZones.length === 0 ? (
        <p className="db-empty">No active zones match the selected filters. Try another type or search.</p>
      ) : (
        <div className="db-list">
          {pageZones.map((z) => (
            <div key={z.id} className="db-item">
              <div className="db-item-head">
                <span className="db-item-title">{zoneLabel(z)}</span>
                <div className="db-btn-row">
                  <Link className="db-btn db-btn-outline db-btn-sm" to={`/map?zone=${z.id}`}>
                    View Map
                  </Link>
                  <button
                    type="button"
                    className="db-btn db-btn-outline db-btn-sm"
                    onClick={() => setTarget({ id: z.id, title: zoneLabel(z), type: zoneType(z), mode: 'resolve' })}
                  >
                    Resolve
                  </button>
                  {!fireOnly && (
                    <button
                      type="button"
                      className="db-btn db-btn-outline db-btn-sm"
                      onClick={() => setTarget({ id: z.id, title: zoneLabel(z), mode: 'retract' })}
                      title="Published by mistake — withdraw without filing a historical record"
                    >
                      Withdraw
                    </button>
                  )}
                </div>
              </div>
              <div className="db-item-meta">
                <span className={`db-chip ${CHIP[z.severity] || ''}`}>{z.severity}</span>
                {' '}Active since {z.activated_at ? new Date(z.activated_at).toLocaleDateString() : 'unknown'}
              </div>
            </div>
          ))}
        </div>
      )}

      {pages > 1 && (
        <div className="db-pager">
          <button type="button" className="db-btn db-btn-outline db-btn-sm" disabled={currentPage <= 1} onClick={() => setPage(currentPage - 1)}>
            Previous
          </button>
          <span>Page {currentPage} of {pages}</span>
          <button type="button" className="db-btn db-btn-outline db-btn-sm" disabled={currentPage >= pages} onClick={() => setPage(currentPage + 1)}>
            Next
          </button>
        </div>
      )}

      {/* Withdrawn zones, kept visible to DRRMO only. Collapsed by default:
          it is a record to check, not something to act on. */}
      {withdrawn?.count > 0 && (
        <div className="db-withdrawn">
          <button
            type="button"
            className="db-btn db-btn-outline db-btn-sm"
            aria-expanded={showWithdrawn}
            onClick={() => setShowWithdrawn((v) => !v)}
          >
            {showWithdrawn ? 'Hide' : 'Show'} {withdrawn.count} withdrawn
            {withdrawn.count === 1 ? ' zone' : ' zones'}
          </button>

          {showWithdrawn && (
            <>
              <p className="db-hint" style={{ marginTop: 10 }}>
                Published in error and withdrawn. No historical record was filed,
                so these are not counted as incidents — but the alerts they sent
                stay on the record.
              </p>
              <div className="db-list">
                {(withdrawn.results || []).map((z) => (
                  <div key={z.id} className="db-item">
                    <div className="db-item-head">
                      <span className="db-item-title">
                        {z.hazard_type?.name || 'Hazard'} · {z.barangay_name || 'Talisay City'}
                      </span>
                    </div>
                    <div className="db-item-meta">
                      Withdrawn{z.retracted_by_name ? ` by ${z.retracted_by_name}` : ''}
                      {z.retracted_at ? ` on ${new Date(z.retracted_at).toLocaleString()}` : ''}
                    </div>
                    {z.retraction_reason && (
                      <p className="db-item-note">“{z.retraction_reason}”</p>
                    )}
                  </div>
                ))}
              </div>
              {withdrawn.count > (withdrawn.results || []).length && (
                <p className="db-hint">
                  Showing the {(withdrawn.results || []).length} most recent of {withdrawn.count}.
                </p>
              )}
            </>
          )}
        </div>
      )}

      {target && (
        <div
          className="db-modal-backdrop"
          role="dialog"
          aria-modal="true"
          aria-label={target.mode === 'retract' ? 'Withdraw hazard zone' : 'Resolve hazard zone'}
          onClick={(e) => { if (e.target === e.currentTarget) setTarget(null); }}
        >
          <div className="db-modal">
            {target.mode === 'retract' ? (
              <RetractHazardForm
                zoneId={target.id}
                title={target.title}
                onCancel={() => setTarget(null)}
                onRetracted={handleClosed}
              />
            ) : (
              <ResolveHazardForm
                zoneId={target.id}
                hazardType={target.type}
                title={target.title}
                onCancel={() => setTarget(null)}
                onResolved={handleClosed}
              />
            )}
          </div>
        </div>
      )}
    </div>
  );
}
