import React, { useEffect, useState } from 'react';
import PublicNavbar from '../../components/Navbar/PublicNavbar';
import { hazardsApi } from '../../api/hazardsApi';
import { reportsApi } from '../../api/reportApi';
import '../css/Dashboard.css';

export default function DRRMODashboard() {
  const [hazards, setHazards] = useState(null);
  const [reports, setReports] = useState([]);

  useEffect(() => {
    hazardsApi.list().then(setHazards).catch(() => setHazards({ features: [] }));
    refreshReports();
  }, []);

  async function refreshReports() {
    try {
      setReports(await reportsApi.list('Pending'));
    } catch {
      setReports([]);
    }
  }

  async function review(id, status) {
    const note = status === 'Rejected' ? window.prompt('Reason for rejecting (optional):') || '' : '';
    await reportsApi.review(id, { status, review_note: note });
    refreshReports();
  }

  const features = hazards?.features || [];
  const resolvedCount = features.filter((f) => f.properties.status === 'Resolved').length;

  return (
    <div className="db">
      <PublicNavbar />
      <div className="db-wrap">
        <div className="db-header">
          <h1>DRRMO dashboard</h1>
          <p>Monitor active hazard zones and review incident reports from barangay personnel.</p>
        </div>

        <div className="db-stats">
          <div className="db-stat">
            <div className="db-stat-value">{features.length}</div>
            <div className="db-stat-label">Active hazard zones</div>
          </div>
          <div className="db-stat">
            <div className="db-stat-value">{resolvedCount}</div>
            <div className="db-stat-label">Resolved</div>
          </div>
          <div className="db-stat">
            <div className="db-stat-value">{reports.length}</div>
            <div className="db-stat-label">Reports pending review</div>
          </div>
        </div>

        <div className="db-card">
          <h2>Reports awaiting validation</h2>
          {reports.length === 0 ? (
            <p className="db-empty">Nothing pending.</p>
          ) : (
            <div className="db-list">
              {reports.map((r) => (
                <div key={r.id} className="db-item">
                  <div className="db-item-head">
                    <span className="db-item-title">{r.hazard_type_detail?.name} · {r.barangay_detail?.name}</span>
                  </div>
                  <p style={{ fontSize: '.92rem', margin: '6px 0' }}>{r.description}</p>
                  <div className="db-item-meta">
                    Reported by {r.submitted_by_name} · {new Date(r.created_at).toLocaleString()}
                  </div>
                  <div className="db-btn-row" style={{ marginTop: 12 }}>
                    <button className="db-btn db-btn-primary" onClick={() => review(r.id, 'Validated')}>Validate</button>
                    <button className="db-btn db-btn-outline" onClick={() => review(r.id, 'Rejected')}>Reject</button>
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
    </div>
  );
}