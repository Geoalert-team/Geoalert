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
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <Navbar />

      <div style={{ flex: 1, display: 'flex', minHeight: 0 }}>
        <aside style={{ width: 300, borderRight: '1px solid var(--line)', background: 'var(--panel)', padding: 16, overflowY: 'auto' }}>
          <h2 style={{ fontSize: 13, color: 'var(--text-muted)' }}>Hazard types</h2>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 20 }}>
            {hazardTypes.map((t) => <span key={t.id} className="btn" style={{ fontSize: 12 }}>{t.name}</span>)}
          </div>

          <button className="btn primary" style={{ width: '100%', marginBottom: 20 }}
                  disabled={!canPublish} onClick={() => setShowPublish(true)}
                  title={canPublish ? '' : 'DRRMO Officer or System Admin only'}>
            Publish hazard
          </button>

          <h2 style={{ fontSize: 13, color: 'var(--text-muted)' }}>Barangays ({barangays.length})</h2>
          <div style={{ maxHeight: 260, overflowY: 'auto', border: '1px solid var(--line)' }}>
            {barangays.map((f) => (
              <div key={f.properties.id} style={{ padding: '8px 10px', borderBottom: '1px solid var(--line)', fontSize: 13 }}>
                {f.properties.name}
              </div>
            ))}
          </div>

          {selectedHazard && (
            <div style={{ marginTop: 20, border: '1px solid var(--line)', padding: 12 }}>
              <div style={{ marginBottom: 6 }}>
                <strong>{selectedHazard.hazard_type_name}</strong>
              </div>
              <div style={{ marginBottom: 6 }}>
                <SeverityBadge severity={selectedHazard.severity} />
              </div>
              <div style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 8 }}>
                {selectedHazard.status} Â· since {new Date(selectedHazard.activated_at).toLocaleDateString()}
              </div>
              <p style={{ fontSize: 12.5 }}>{selectedHazard.description}</p>
              {canPublish && selectedHazard.status === 'Active' && (
                <button className="btn primary" style={{ width: '100%' }} onClick={resolveSelected}>Mark resolved</button>
              )}
            </div>
          )}
        </aside>

        <main style={{ flex: 1 }}>
          <Map onSelectHazard={handleSelectHazard} refreshKey={refreshKey} />
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
