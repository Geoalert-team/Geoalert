import React, { useEffect, useState } from 'react';
import { useAuth } from '../../context/AuthContext';
import { barangaysApi } from '../../api/barangaysApi';
import { reportsApi, guidanceApi } from '../../api/mockApi';
import Navbar from '../../components/Navbar';

const HAZARD_OPTIONS = ['Flood', 'Fire', 'Landslide'];
const STATUS_COLOR = { Pending: 'var(--sev-orange)', Validated: 'var(--sev-green)', Rejected: 'var(--sev-red)' };

export default function BarangayDashboard() {
  const { user } = useAuth();
  const [reports, setReports] = useState([]);
  const [barangayNames, setBarangayNames] = useState([]);
  const [guidance, setGuidance] = useState([]);

  const [barangayName, setBarangayName] = useState('');
  const [hazardType, setHazardType] = useState(HAZARD_OPTIONS[0]);
  const [description, setDescription] = useState('');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    refreshReports();
    barangaysApi.list().then((geo) => setBarangayNames((geo.features || []).map((f) => f.properties.name))).catch(() => {});
    guidanceApi.list().then((all) => setGuidance(all.slice(0, 2)));
  }, []);

  async function refreshReports() {
    const all = await reportsApi.list();
    setReports(all.filter((r) => r.reported_by === (user?.full_name || user?.email)));
  }

  async function submitReport(e) {
    e.preventDefault();
    setBusy(true);
    await reportsApi.submit({
      barangay_name: barangayName || barangayNames[0] || 'Poblacion',
      hazard_type: hazardType,
      description,
      reported_by: user?.full_name || user?.email,
    });
    setDescription('');
    setBusy(false);
    refreshReports();
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <Navbar />
      <div style={{ flex: 1, overflowY: 'auto', padding: 24, maxWidth: 780, margin: '0 auto', width: '100%' }}>
        <h2 style={{ marginBottom: 4 }}>Barangay dashboard</h2>
        <p style={{ color: 'var(--text-muted)', fontSize: 13, marginBottom: 20 }}>
          Mock data â€” apps/reports has no backend yet.
        </p>

        <form onSubmit={submitReport} style={{ border: '1px solid var(--line)', background: 'var(--panel)', padding: 18, marginBottom: 24 }}>
          <h3 style={{ marginTop: 0 }}>Submit a report</h3>
          <div className="field">
            <label>Barangay</label>
            <select value={barangayName} onChange={(e) => setBarangayName(e.target.value)}>
              {(barangayNames.length ? barangayNames : ['Poblacion']).map((b) => <option key={b} value={b}>{b}</option>)}
            </select>
          </div>
          <div className="field">
            <label>Hazard type</label>
            <select value={hazardType} onChange={(e) => setHazardType(e.target.value)}>
              {HAZARD_OPTIONS.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
          </div>
          <div className="field">
            <label>What are you seeing?</label>
            <textarea rows={3} required value={description} onChange={(e) => setDescription(e.target.value)}
                      placeholder="Describe the situation â€” location detail, how bad it looks, anyone affected" />
          </div>
          <button className="btn primary" disabled={busy}>{busy ? 'Submittingâ€¦' : 'Submit report'}</button>
        </form>

        <h3>Your submitted reports</h3>
        {reports.length === 0 ? (
          <p style={{ color: 'var(--text-muted)' }}>No reports yet.</p>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginBottom: 24 }}>
            {reports.map((r) => (
              <div key={r.id} style={{ border: '1px solid var(--line)', background: 'var(--panel)', padding: 14 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6, flexWrap: 'wrap', gap: 6 }}>
                  <strong>{r.hazard_type} Â· {r.barangay_name}</strong>
                  <span style={{ color: STATUS_COLOR[r.status], fontSize: 12.5, fontWeight: 600 }}>{r.status}</span>
                </div>
                <p style={{ fontSize: 13, margin: '0 0 6px' }}>{r.description}</p>
                <div style={{ fontSize: 11.5, color: 'var(--text-muted)' }}>{new Date(r.created_at).toLocaleString()}</div>
              </div>
            ))}
          </div>
        )}

        <h3>Latest safety guidance</h3>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {guidance.map((g) => (
            <div key={g.id} style={{ border: '1px solid var(--line)', background: 'var(--panel)', padding: 12 }}>
              <strong>{g.title}</strong>
              <span style={{ marginLeft: 8, fontSize: 11.5, color: 'var(--accent)' }}>{g.hazard_type}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
