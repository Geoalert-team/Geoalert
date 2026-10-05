import React, { useEffect, useState } from 'react';
import PublicNavbar from '../components/Navbar/PublicNavbar';
import { fakeHistoryApi } from '../api/fakeHistoryApi';
import { severityColor, severityLabel } from '../utils/severityColor';
import './css/Dashboard.css';

const HAZARD_OPTIONS = ['Flood', 'Fire', 'Landslide'];

export default function HistoricalData() {
  const [records, setRecords] = useState([]);
  const [loading, setLoading] = useState(true);
  const [hazardFilter, setHazardFilter] = useState('');

  useEffect(() => {
    refresh();
  }, [hazardFilter]);

  async function refresh() {
    setLoading(true);
    const data = await fakeHistoryApi.list(hazardFilter ? { hazard_type: hazardFilter } : {});
    setRecords(data);
    setLoading(false);
  }

  return (
    <div className="db">
      <PublicNavbar />
      <div className="db-wrap">
        <div className="db-header">
          <h1>Historical data</h1>
          <p>
            Fake data generated with @faker-js/faker - stands in for the real GET /api/history/
            endpoint until the frontend is wired to it.
          </p>
        </div>

        <div className="db-tabs" role="tablist">
          <button
            type="button" role="tab" aria-selected={!hazardFilter}
            className={`db-tab ${!hazardFilter ? 'is-active' : ''}`}
            onClick={() => setHazardFilter('')}
          >
            All types
          </button>
          {HAZARD_OPTIONS.map((t) => (
            <button
              key={t} type="button" role="tab" aria-selected={hazardFilter === t}
              className={`db-tab ${hazardFilter === t ? 'is-active' : ''}`}
              onClick={() => setHazardFilter(t)}
            >
              {t}
            </button>
          ))}
        </div>

        <div className="db-card">
          <h2>Records</h2>
          <p className="db-card-sub">
            {records.length} historical record{records.length === 1 ? '' : 's'}
          </p>
          {loading ? (
            <p style={{ color: 'var(--db-soft)' }}>Loading...</p>
          ) : records.length === 0 ? (
            <p className="db-empty">No records match this filter.</p>
          ) : (
            <div className="db-list">
              {records.map((r) => (
                <div key={r.id} className="db-item">
                  <div className="db-item-head">
                    <span className="db-item-title">{r.hazard_type} - {r.barangay_name}</span>
                    <span className="db-item-meta" style={{ color: severityColor(r.severity), fontWeight: 600 }}>
                      {severityLabel(r.severity)}
                    </span>
                  </div>
                  <div className="db-item-meta">{r.description}</div>
                  <div className="db-item-meta">
                    {new Date(r.occurred_at).toLocaleDateString()} - {r.casualties} {r.casualties === 1 ? 'casualty' : 'casualties'} - {r.displaced.toLocaleString()} displaced
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}