import React, { useEffect, useState } from 'react';
import { useAuth } from '../context/AuthContext';
import { hazardsApi } from '../api/hazardsApi';
import { barangaysApi } from '../api/barangaysApi';
import Map from '../components/Map';
import PublishHazardModal from '../components/Map/PublishHazardModal';
import Navbar from '../components/Navbar';
import SeverityBadge from '../components/SeverityBadge';

export default function Home() {
  const { canPublish } = useAuth();
  const [hazardTypes, setHazardTypes] = useState([]);
  const [barangays, setBarangays] = useState([]);
  const [selectedHazard, setSelectedHazard] = useState(null);
  const [showPublish, setShowPublish] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    hazardsApi.types().then(setHazardTypes).catch(() => {});
    barangaysApi.list().then((geo) => setBarangays(geo.features || [])).catch(() => {});
  }, []);

  async function handleSelectHazard(id) {
    try {
      const detail = await hazardsApi.detail(id);
      setSelectedHazard(detail);
    } catch {
      // ignore fetch errors for now
    }
  }

  async function resolveSelected() {
    if (!selectedHazard) return;
    const updated = await hazardsApi.update(selectedHazard.id, { status: 'Resolved' });
    setSelectedHazard(updated);
    setRefreshKey((k) => k + 1);
  }

  return (
    <div className="app-shell">
      <Navbar />

      <div className="content-row">
        <aside className="sidebar">
          <div className="section">
            <h2>Hazard types</h2>
            <div className="chip-row">
              {hazardTypes.map((t) => <span key={t.id} className="chip">{t.name}</span>)}
            </div>
          </div>

          <button
            className="btn primary"
            style={{ width: '100%', marginBottom: 24 }}
            disabled={!canPublish}
            onClick={() => setShowPublish(true)}
            title={canPublish ? '' : 'DRRMO Officer or System Admin only'}
          >
            Publish hazard
          </button>

          <div className="section">
            <h2>Barangays ({barangays.length})</h2>
            <div className="barangay-list">
              {barangays.map((f) => (
                <div key={f.properties.id} className="barangay-item">
                  {f.properties.name}
                </div>
              ))}
            </div>
          </div>

          {selectedHazard && (
            <div className="hazard-detail">
              <div className="title">{selectedHazard.hazard_type_name}</div>
              <div style={{ marginBottom: 6 }}>
                <SeverityBadge severity={selectedHazard.severity} />
              </div>
              <div className="meta">
                {selectedHazard.status} · since {new Date(selectedHazard.activated_at).toLocaleDateString()}
              </div>
              <p>{selectedHazard.description}</p>
              {canPublish && selectedHazard.status === 'Active' && (
                <button className="btn primary" style={{ width: '100%' }} onClick={resolveSelected}>Mark resolved</button>
              )}
            </div>
          )}
        </aside>

        <main className="map-pane">
          <div className="map-inner">
            <Map onSelectHazard={handleSelectHazard} refreshKey={refreshKey} />
          </div>
        </main>
      </div>

      {showPublish && (
        <PublishHazardModal
          hazardTypes={hazardTypes}
          barangays={barangays}
          onClose={() => setShowPublish(false)}
          onCreated={() => { setShowPublish(false); setRefreshKey((k) => k + 1); }}
        />
      )}
    </div>
  );
}