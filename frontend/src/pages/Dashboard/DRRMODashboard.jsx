import React, { useEffect, useState } from 'react';
import { hazardsApi } from '../../api/hazardsApi';
import { reportsApi } from '../../api/reportApi';
import Navbar from '../../components/Navbar';

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
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <Navbar />
      <div style={{ flex: 1, overflowY: 'auto', padding: 24, maxWidth: 880, margin: '0 auto', width: '100%' }}>
        <h2 style={{ marginBottom: 4 }}>DRRMO dashboard</h2>
        <p style={{ color: 'var(--text-muted)', fontSize: 13, marginBottom: 20 }}>
          Monitor active hazard zones and review incident reports from barangay personnel.
        </p>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: 10, marginBottom: 24 }}>
          {[
            ['Active hazard zones', features.length],
            ['Resolved', resolvedCount],
            ['Reports pending review', reports.length],
          ].map(([label, value]) => (
            <div key={label} style={{ border: '1px solid var(--line)', background: 'var(--panel)', padding: 14 }}>
              <div style={{ fontSize: 24, fontWeight: 700 }}>{value}</div>
              <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>{label}</div>
            </div>
          ))}
        </div>

        <h3>Reports awaiting validation</h3>
        {reports.length === 0 ? (
          <p style={{ color: 'var(--text-muted)' }}>Nothing pending.</p>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {reports.map((r) => (
              <div key={r.id} style={{ border: '1px solid var(--line)', background: 'var(--panel)', padding: 14 }}>
                <strong>{r.hazard_type_detail?.name} · {r.barangay_detail?.name}</strong>
                <p style={{ fontSize: 13, margin: '6px 0' }}>{r.description}</p>
                <div style={{ fontSize: 11.5, color: 'var(--text-muted)', marginBottom: 10 }}>
                  Reported by {r.submitted_by_name} · {new Date(r.created_at).toLocaleString()}
                </div>
                <div style={{ display: 'flex', gap: 8 }}>
                  <button className="btn primary" onClick={() => review(r.id, 'Validated')}>Validate</button>
                  <button className="btn" onClick={() => review(r.id, 'Rejected')}>Reject</button>
                </div>
              </div>
            ))}
          </div>
        )}

        <p style={{ marginTop: 24, fontSize: 12.5, color: 'var(--text-muted)' }}>
          To publish a new hazard zone, go to the Map page.
        </p>
      </div>
    </div>
  );
}