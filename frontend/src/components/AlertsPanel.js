import React, { useEffect, useState } from 'react';
import { api } from '../api/client';

export default function AlertsPanel() {
  const [alerts, setAlerts] = useState([]);
  const [error, setError] = useState('');

  useEffect(() => {
    let active = true;

    async function load() {
      try {
        const data = await api.hazards();
        if (!active) return;
        const features = data?.features || [];
        setAlerts(features.filter(f => f.properties?.status === 'Active').map(f => f.properties));
        setError('');
      } catch (e) {
        if (active) setError(e.message);
      }
    }

    load();
    const timer = setInterval(load, 15000); // polling fallback for real-time alerts
    return () => { active = false; clearInterval(timer); };
  }, []);

  return (
    <div className="alerts-panel">
      <strong>Live alerts</strong>
      {error && <span className="muted"> {error}</span>}
      {alerts.length === 0 ? <span className="muted"> No active alerts</span> : alerts.slice(0, 5).map(a => (
        <div className="alert-item" key={a.id}>
          <b>{a.hazard_type_name || 'Hazard'}</b> â€” {a.severity} â€” {a.status}
        </div>
      ))}
    </div>
  );
}
