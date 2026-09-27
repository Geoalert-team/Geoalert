import React, { useEffect, useState } from 'react';
import PublicNavbar from '../components/Navbar/PublicNavbar';
import { historyApi } from '../api/historyApi';
import './css/Dashboard.css';

export default function HistoricalData() {
  const [records, setRecords] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    historyApi.list()
      .then((data) => setRecords(data.results || data))
      .catch(() => setRecords([]))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="db">
      <PublicNavbar />
      <div className="db-wrap">
        <div className="db-header">
          <h1>Historical records</h1>
          <p>Past hazard events recorded for Talisay City.</p>
        </div>

        <div className="db-card">
          {loading ? (
            <p className="db-empty">Loading…</p>
          ) : records.length === 0 ? (
            <p className="db-empty">No historical records yet.</p>
          ) : (
            <div className="db-list">
              {records.map((r) => (
                <div key={r.id} className="db-item">
                  <div className="db-item-head">
                    <span className="db-item-title">
                      {r.hazard_type?.name || r.hazard_type_name} · {r.barangay?.name || r.barangay_name}
                    </span>
                    <span className="db-item-meta">{new Date(r.occurred_at).toLocaleDateString()}</span>
                  </div>
                  {(r.total_casualties || r.total_displaced) && (
                    <div className="db-item-meta">
                      {r.total_casualties ? `${r.total_casualties} casualties` : ''}
                      {r.total_casualties && r.total_displaced ? ' · ' : ''}
                      {r.total_displaced ? `${r.total_displaced} displaced` : ''}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}