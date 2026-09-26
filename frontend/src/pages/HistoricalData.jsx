import React, { useEffect, useState } from 'react';
import { historyApi } from '../api/historyApi';
import Navbar from '../components/Navbar';

const SEVERITY_COLOR = { Red: 'var(--sev-red)', Orange: 'var(--sev-orange)', Green: 'var(--sev-green)' };

export default function HistoricalData() {
  const [records, setRecords] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    historyApi.list()
      .then(setRecords)
      .catch(() => setRecords([]))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <Navbar />
      <div style={{ flex: 1, overflowY: 'auto', padding: 24, maxWidth: 780, margin: '0 auto', width: '100%' }}>
        <h2 style={{ marginBottom: 4 }}>Historical data</h2>
        <p style={{ color: 'var(--text-muted)', fontSize: 13, marginBottom: 20 }}>
          Archived hazard events for Talisay City, used for trend analysis and risk planning.
        </p>

        {loading ? (
          <p style={{ color: 'var(--text-muted)' }}>Loading…</p>
        ) : records.length === 0 ? (
          <p style={{ color: 'var(--text-muted)' }}>No historical records found.</p>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {records.map((r) => (
              <div key={r.id} style={{ border: '1px solid var(--line)', background: 'var(--panel)', padding: 14 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap', gap: 6 }}>
                  <strong>{r.hazard_type_detail?.name} · {r.barangay_detail?.name}</strong>
                  <span style={{ color: SEVERITY_COLOR[r.severity_level], fontSize: 12.5, fontWeight: 600 }}>
                    {r.severity_level}
                  </span>
                </div>
                <p style={{ fontSize: 13, margin: '6px 0' }}>{r.description}</p>
                <div style={{ fontSize: 11.5, color: 'var(--text-muted)' }}>
                  Occurred {new Date(r.occurred_at).toLocaleDateString()}
                  {r.total_displaced > 0 && ` · ${r.total_displaced} displaced`}
                  {r.total_casualties > 0 && ` · ${r.total_casualties} casualties`}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}