import React, { useEffect, useState } from 'react';
import { reportsApi } from '../api/mockApi';
import Navbar from '../components/Navbar';

const STATUS_COLOR = { Validated: 'var(--sev-green)', Rejected: 'var(--sev-red)', Pending: 'var(--sev-orange)' };

export default function HistoricalData() {
  const [reports, setReports] = useState([]);

  useEffect(() => { reportsApi.list().then(setReports); }, []);

  const resolved = reports.filter((r) => r.status !== 'Pending');

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <Navbar />
      <div style={{ flex: 1, overflowY: 'auto', padding: 24, maxWidth: 780, margin: '0 auto', width: '100%' }}>
        <h2 style={{ marginBottom: 4 }}>Historical data</h2>
        <p style={{ color: 'var(--text-muted)', fontSize: 13, marginBottom: 20 }}>
          Mock data â€” apps/history has no backend yet. Shows incident reports that have already
          been reviewed (validated or rejected).
        </p>

        {resolved.length === 0 ? (
          <p style={{ color: 'var(--text-muted)' }}>Nothing reviewed yet.</p>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {resolved.map((r) => (
              <div key={r.id} style={{ border: '1px solid var(--line)', background: 'var(--panel)', padding: 14 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap', gap: 6 }}>
                  <strong>{r.hazard_type} Â· {r.barangay_name}</strong>
                  <span style={{ color: STATUS_COLOR[r.status], fontSize: 12.5, fontWeight: 600 }}>{r.status}</span>
                </div>
                <p style={{ fontSize: 13, margin: '6px 0' }}>{r.description}</p>
                <div style={{ fontSize: 11.5, color: 'var(--text-muted)' }}>
                  Reported {new Date(r.created_at).toLocaleString()} Â· Reviewed by {r.reviewed_by} on{' '}
                  {new Date(r.reviewed_at).toLocaleString()}
                  {r.review_note && ` â€” "${r.review_note}"`}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
