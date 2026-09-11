import React, { useEffect, useState } from 'react';
import { api } from '../api/client';

export default function IncidentReports() {
  const [reports, setReports] = useState([]);
  const [form, setForm] = useState({
    title: '', hazard_type: '', barangay: '', description: '', latitude: '', longitude: ''
  });
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const load = () => api.incidentReports()
    .then((data) => setReports(data.results || data || []))
    .catch((e) => setError(e.message));

  useEffect(() => { load(); }, []);

  function change(e) {
    setForm({ ...form, [e.target.name]: e.target.value });
  }

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError('');
    try {
      await api.createIncidentReport({
        ...form,
        latitude: form.latitude ? Number(form.latitude) : null,
        longitude: form.longitude ? Number(form.longitude) : null,
      });
      setForm({ title: '', hazard_type: '', barangay: '', description: '', latitude: '', longitude: '' });
      await load();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="feature-page">
      <h2>Incident Reports</h2>
      <p className="muted">Barangay Personnel can submit incidents for DRRMO validation.</p>

      <form onSubmit={submit} className="card form-grid">
        <div className="field"><label>Title</label><input name="title" value={form.title} onChange={change} required /></div>
        <div className="field"><label>Hazard type</label><input name="hazard_type" value={form.hazard_type} onChange={change} placeholder="Flood, Fire, Landslide..." required /></div>
        <div className="field"><label>Barangay</label><input name="barangay" value={form.barangay} onChange={change} required /></div>
        <div className="field"><label>Latitude</label><input name="latitude" type="number" step="any" value={form.latitude} onChange={change} /></div>
        <div className="field"><label>Longitude</label><input name="longitude" type="number" step="any" value={form.longitude} onChange={change} /></div>
        <div className="field full"><label>Description</label><textarea name="description" rows="4" value={form.description} onChange={change} required /></div>
        <div className="full"><div className="error-text">{error}</div><button className="btn primary" disabled={busy}>{busy ? 'Submittingâ€¦' : 'Submit incident report'}</button></div>
      </form>

      <div className="card">
        <h3>Submitted reports</h3>
        {reports.length === 0 ? <p className="muted">No incident reports yet.</p> : (
          <div className="list">
            {reports.map((r) => (
              <div className="list-row" key={r.id}>
                <div><strong>{r.title || r.hazard_type_name || 'Incident report'}</strong><div className="muted">{r.barangay_name || r.barangay} Â· {r.status || 'Pending'}</div></div>
                <span className="badge">{r.status || 'Pending'}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
