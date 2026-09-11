import React, { useState, useEffect } from 'react';
import { api } from '../api/client';

export default function PublishHazardModal({ hazardTypes = [], barangays = [], onClose, onCreated }) {
  const [types, setTypes] = useState(hazardTypes);
  const [areas, setAreas] = useState(barangays);
  const [barangay, setBarangay] = useState('');
  const [hazardType, setHazardType] = useState('');
  const [severity, setSeverity] = useState('Orange');
  const [description, setDescription] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!types.length) api.hazardTypes().then(setTypes).catch(e => setError(e.message));
    if (!areas.length) api.barangays().then(d => setAreas(d.features || [])).catch(e => setError(e.message));
  }, [types.length, areas.length]);

  useEffect(() => {
    if (!barangay && areas[0]) setBarangay(areas[0].properties?.id || areas[0].id || '');
    if (!hazardType && types[0]) setHazardType(types[0].id);
  }, [areas, types, barangay, hazardType]);

  async function submit() {
    setBusy(true); setError('');
    try {
      await api.createHazard({
        barangay, hazard_type: hazardType, severity, description,
        geometry: { type: 'MultiPolygon', coordinates: [[[
          [123.8443,10.2416],[123.8503,10.2416],[123.8503,10.2476],[123.8443,10.2476],[123.8443,10.2416]
        ]]]},
      });
      onCreated();
    } catch (e) { setError(e.message); } finally { setBusy(false); }
  }

  return (
    <div className="modal-backdrop">
      <div className="modal-box">
        <h3>Publish hazard</h3>
        <div className="field"><label>Barangay</label><select value={barangay} onChange={e => setBarangay(e.target.value)}>{areas.map(f => <option key={f.properties?.id || f.id} value={f.properties?.id || f.id}>{f.properties?.name || f.name}</option>)}</select></div>
        <div className="field"><label>Hazard type</label><select value={hazardType} onChange={e => setHazardType(e.target.value)}>{types.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}</select></div>
        <div className="field"><label>Severity</label><select value={severity} onChange={e => setSeverity(e.target.value)}><option value="Green">Low</option><option value="Orange">Moderate</option><option value="Red">Extreme</option></select></div>
        <div className="field"><label>Description</label><textarea rows="4" value={description} onChange={e => setDescription(e.target.value)} required /></div>
        <div className="error-text">{error}</div>
        <div className="modal-actions"><button className="btn" onClick={onClose}>Cancel</button><button className="btn primary" disabled={busy} onClick={submit}>{busy ? 'Publishingâ€¦' : 'Publish hazard'}</button></div>
      </div>
    </div>
  );
}
