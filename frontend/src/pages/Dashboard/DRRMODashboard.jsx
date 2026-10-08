import React, { useCallback, useEffect, useState } from 'react';
import PublicNavbar from '../../components/Navbar/PublicNavbar';
import ActiveZonesCard from '../../components/Resolve/ActiveZonesCard';
import { hazardsApi } from '../../api/hazardsApi';
import { reportsApi } from '../../api/reportApi';
import '../css/Dashboard.css';

const STATUS_BADGE = { Pending: 'db-badge-pending', Validated: 'db-badge-validated', Rejected: 'db-badge-rejected' };

export default function DRRMODashboard() {
  const [activeCount, setActiveCount] = useState(null);
  const [resolvedCount, setResolvedCount] = useState(null);
  const [reports, setReports] = useState([]);
  const [selected, setSelected] = useState(null); // report shown in the full-report view

  // /api/hazards/ only ever returns Active zones, so the resolved total has
  // to come from /api/hazards/resolved/. Counting 'Resolved' in the active
  // list can only ever produce 0.
  const refreshCounts = useCallback(async () => {
    try {
      const geo = await hazardsApi.list();
      setActiveCount((geo.features || []).length);
    } catch {
      setActiveCount(null);
    }
    try {
      const res = await hazardsApi.resolved(1);
      setResolvedCount(res.count);
    } catch {
      setResolvedCount(null);
    }
  }, []);

  const refreshReports = useCallback(async () => {
    try {
      setReports(await reportsApi.list('Pending'));
    } catch {
      setReports([]);
    }
  }, []);

  useEffect(() => {
    refreshCounts();
    refreshReports();
  }, [refreshCounts, refreshReports]);

  async function review(id, status) {
    const note = status === 'Rejected' ? window.prompt('Reason for rejecting (optional):') || '' : '';
    await reportsApi.review(id, { status, review_note: note });
    setSelected(null);
    refreshReports();
  }

  // Close the full-report view with Esc
  useEffect(() => {
    if (!selected) return undefined;
    const onKey = (e) => { if (e.key === 'Escape') setSelected(null); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [selected]);

  const show = (v) => (v === null ? '—' : v);

  return (
    <div className="db">
      <PublicNavbar />
      <div className="db-wrap">
        <div className="db-header">
          <h1>DRRMO dashboard</h1>
          <p>Monitor active hazard zones, close them out, and review incident reports from barangay personnel.</p>
        </div>

        <div className="db-stats">
          <div className="db-stat">
            <div className="db-stat-value">{show(activeCount)}</div>
            <div className="db-stat-label">Active hazard zones</div>
          </div>
          <div className="db-stat">
            <div className="db-stat-value">{show(resolvedCount)}</div>
            <div className="db-stat-label">Resolved to date</div>
          </div>
          <div className="db-stat">
            <div className="db-stat-value">{reports.length}</div>
            <div className="db-stat-label">Reports pending review</div>
          </div>
        </div>

        {/* Lists the live zones and lets DRRMO resolve any of them. Tells us
            to refresh the tiles once a resolve goes through. */}
        <ActiveZonesCard onResolved={refreshCounts} />

        <div className="db-card">
          <h2>Reports awaiting validation</h2>
          {reports.length === 0 ? (
            <p className="db-empty">Nothing pending.</p>
          ) : (
            <div className="db-list">
              {reports.map((r) => (
                <div
                  key={r.id}
                  className="db-item db-item-clickable"
                  role="button"
                  tabIndex={0}
                  onClick={() => setSelected(r)}
                  onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setSelected(r); } }}
                >
                  <div className="db-item-head">
                    <span className="db-item-title">{r.hazard_type_details?.name} · {r.barangay_details?.name}</span>
                    <span className="db-item-meta">View full report ›</span>
                  </div>
                  <p style={{ fontSize: '.92rem', margin: '6px 0' }}>{r.description}</p>
                  <div className="db-chips">
                    <span className={`db-chip ${r.casualties_dead > 0 ? 'db-chip-danger' : ''}`}>Casualties: {r.casualties_dead ?? 0}</span>
                    <span className={`db-chip ${r.casualties_injured > 0 ? 'db-chip-warn' : ''}`}>Injured: {r.casualties_injured ?? 0}</span>
                    <span className="db-chip">Missing: {r.casualties_missing ?? 0}</span>
                  </div>
                  <div className="db-item-meta">
                    Reported by {r.submitted_by_name} · {new Date(r.created_at).toLocaleString()}
                  </div>
                  <div className="db-btn-row" style={{ marginTop: 12 }}>
                    <button className="db-btn db-btn-primary" onClick={(e) => { e.stopPropagation(); review(r.id, 'Validated'); }}>Validate</button>
                    <button className="db-btn db-btn-outline" onClick={(e) => { e.stopPropagation(); review(r.id, 'Rejected'); }}>Reject</button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        <p style={{ marginTop: 8, fontSize: '.9rem', color: 'var(--db-soft)' }}>
          To publish a new hazard zone, go to the Map page.
        </p>
      </div>
      {selected && (
        <div className="db-modal-backdrop" onClick={() => setSelected(null)}>
          <div
            className="db-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="report-modal-title"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="db-modal-head">
              <div>
                <h2 id="report-modal-title">{selected.hazard_type_details?.name || 'Incident'} report</h2>
                <p className="db-card-sub" style={{ marginBottom: 0 }}>
                  {selected.barangay_details?.name}{selected.barangay_details?.municipality ? `, ${selected.barangay_details.municipality}` : ''}
                </p>
              </div>
              <span className={`db-badge ${STATUS_BADGE[selected.status] || ''}`}>{selected.status}</span>
            </div>

            <div className="db-modal-section">
              <h3>What was reported</h3>
              <p style={{ whiteSpace: 'pre-wrap' }}>{selected.description}</p>
            </div>

            <div className="db-modal-section">
              <h3>Casualties &amp; injured</h3>
              <div className="db-stats" style={{ marginBottom: 0 }}>
                <div className="db-stat">
                  <div className="db-stat-value">{selected.casualties_dead ?? 0}</div>
                  <div className="db-stat-label">Casualties</div>
                </div>
                <div className="db-stat">
                  <div className="db-stat-value">{selected.casualties_injured ?? 0}</div>
                  <div className="db-stat-label">Injured</div>
                </div>
                <div className="db-stat">
                  <div className="db-stat-value">{selected.casualties_missing ?? 0}</div>
                  <div className="db-stat-label">Missing</div>
                </div>
                <div className="db-stat">
                  <div className="db-stat-value">{selected.displaced ?? 0}</div>
                  <div className="db-stat-label">Displaced</div>
                </div>
              </div>
            </div>

            <div className="db-modal-section">
              <h3>Submission details</h3>
              <dl className="db-dl">
                <dt>Reported by</dt><dd>{selected.reporter_name || selected.submitted_by_name || 'Unknown'}</dd>
                {selected.agency && (<><dt>Agency</dt><dd>{selected.agency}</dd></>)}
                {selected.position && (<><dt>Position</dt><dd>{selected.position}</dd></>)}
                {selected.severity_estimate && (<><dt>Severity estimate</dt><dd>{selected.severity_estimate}</dd></>)}
                <dt>Submitted</dt><dd>{new Date(selected.created_at).toLocaleString()}</dd>
                <dt>Report ID</dt><dd style={{ wordBreak: 'break-all' }}>{selected.id}</dd>
                {selected.reviewed_at && (<>
                  <dt>Reviewed by</dt><dd>{selected.reviewed_by_name || 'Unknown'}</dd>
                  <dt>Reviewed</dt><dd>{new Date(selected.reviewed_at).toLocaleString()}</dd>
                </>)}
                {selected.review_note && (<><dt>Review note</dt><dd>{selected.review_note}</dd></>)}
              </dl>
            </div>

            <div className="db-btn-row" style={{ marginTop: 20 }}>
              {selected.status === 'Pending' && (<>
                <button className="db-btn db-btn-primary" onClick={() => review(selected.id, 'Validated')}>Validate</button>
                <button className="db-btn db-btn-danger" onClick={() => review(selected.id, 'Rejected')}>Reject</button>
              </>)}
              <button className="db-btn db-btn-outline" onClick={() => setSelected(null)}>Close</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}