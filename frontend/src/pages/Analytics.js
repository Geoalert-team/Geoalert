import React, { useEffect, useState } from 'react';
import { api } from '../api/client';

export default function Analytics() {
  const [data, setData] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => {
    api.analytics().then(setData).catch((e) => setError(e.message));
  }, []);

  if (error) return <div className="feature-page"><h2>Analytics</h2><div className="error-text">{error}</div></div>;
  if (!data) return <div className="feature-page"><h2>Analytics</h2><p className="muted">Loading analyticsâ€¦</p></div>;

  const cards = [
    ['Total incidents', data.total_incidents ?? 0],
    ['Pending reports', data.pending_reports ?? 0],
    ['Active hazards', data.active_hazards ?? 0],
    ['Resolved hazards', data.resolved_hazards ?? 0],
  ];

  return (
    <div className="feature-page">
      <h2>Dashboard Analytics</h2>
      <p className="muted">Summary data for DRRMO monitoring and decision-making.</p>
      <div className="stats-grid">{cards.map(([label, value]) => <div className="stat-card" key={label}><span>{label}</span><strong>{value}</strong></div>)}</div>
      <div className="card">
        <h3>Hazards by type</h3>
        {Object.entries(data.hazards_by_type || {}).map(([name, value]) => <div className="list-row" key={name}><span>{name}</span><strong>{value}</strong></div>)}
      </div>
      <div className="card">
        <h3>Incidents by status</h3>
        {Object.entries(data.incidents_by_status || {}).map(([name, value]) => <div className="list-row" key={name}><span>{name}</span><strong>{value}</strong></div>)}
      </div>
    </div>
  );
}
