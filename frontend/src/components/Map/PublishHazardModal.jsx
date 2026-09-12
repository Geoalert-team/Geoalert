import React, { useState } from 'react';
import { hazardsApi } from '../../api/hazardsApi';

const SEVERITIES = [
  { code: 'Green', label: 'Low' },
  { code: 'Orange', label: 'Moderate' },
  { code: 'Red', label: 'Extreme' },
];

// Placeholder geometry: a small square around Talisay City's center.
// HazardZone.geometry is a required MultiPolygonField â€” swap this out once
// the map supports real polygon drawing (e.g. via leaflet-draw).
function placeholderGeometry(lng = 123.8473, lat = 10.2446, delta = 0.003) {
  const ring = [
    [lng - delta, lat - delta], [lng + delta, lat - delta],
    [lng + delta, lat + delta], [lng - delta, lat + delta],
    [lng - delta, lat - delta],
  ];
  return { type: 'MultiPolygon', coordinates: [[ring]] };
}

export default function PublishHazardModal({ hazardTypes, barangays, onClose, onCreated }) {
  const [barangay, setBarangay] = useState(barangays[0]?.properties.id || '');
  const [hazardType, setHazardType] = useState(hazardTypes[0]?.id || '');
  const [severity, setSeverity] = useState('Orange');
  const [description, setDescription] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  async function submit() {
    setBusy(true);
    setError('');
    try {
      await hazardsApi.create({
        barangay,
        hazard_type: hazardType,
        severity,
        description,
        geometry: placeholderGeometry(),
      });
      onCreated();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.55)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 20 }}>
      <div style={{ width: 420, background: 'var(--panel)', border: '1px solid var(--line)', padding: 22 }}>
        <h3 style={{ margin: '0 0 3px' }}>Publish hazard</h3>
        <p style={{ color: 'var(--text-muted)', fontSize: 12.5, margin: '0 0 16px' }}>POST /api/hazards/create/</p>

        <div className="field">
          <label>Barangay</label>
          <select value={barangay} onChange={(e) => setBarangay(e.target.value)}>
            {barangays.map((f) => <option key={f.properties.id} value={f.properties.id}>{f.properties.name}</option>)}
          </select>
        </div>

        <div className="field">
          <label>Hazard type</label>
          <select value={hazardType} onChange={(e) => setHazardType(e.target.value)}>
            {hazardTypes.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
          </select>
        </div>

        <div className="field">
          <label>Severity</label>
          <div style={{ display: 'flex', gap: 8 }}>
            {SEVERITIES.map((s) => (
              <button key={s.code} type="button"
                      className="btn" style={{ flex: 1, ...(severity === s.code ? { background: 'var(--accent)', color: '#04191A', borderColor: 'var(--accent)' } : {}) }}
                      onClick={() => setSeverity(s.code)}>
                {s.label}
              </button>
            ))}
          </div>
        </div>

        <div className="field">
          <label>Description</label>
          <textarea rows={3} value={description} onChange={(e) => setDescription(e.target.value)}
                     placeholder="What responders and residents need to know" />
        </div>

        <div className="error-text">{error}</div>

        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 8 }}>
          <button className="btn" onClick={onClose}>Cancel</button>
          <button className="btn primary" disabled={busy} onClick={submit}>
            {busy ? 'Publishingâ€¦' : 'Publish hazard'}
          </button>
        </div>
      </div>
    </div>
  );
}
