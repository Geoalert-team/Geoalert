import React, { useEffect, useState } from 'react';
import { useAuth } from '../../context/AuthContext';
import { barangaysApi } from '../../api/barangaysApi';
import { reportsApi } from '../../api/reportApi';
import { guidanceApi } from '../../api/guidanceApi';
import { hazardsApi } from '../../api/hazardsApi';
import Navbar from '../../components/Navbar';

const STATUS_COLOR = { Pending: 'var(--sev-orange)', Validated: 'var(--sev-green)', Rejected: 'var(--sev-red)' };

export default function BarangayDashboard() {
  const { user } = useAuth();
  const [reports, setReports] = useState([]);
  const [barangays, setBarangays] = useState([]);
  const [hazardTypes, setHazardTypes] = useState([]);
  const [guidance, setGuidance] = useState([]);

  const [barangayId, setBarangayId] = useState('');
  const [hazardTypeId, setHazardTypeId] = useState('');
  const [description, setDescription] = useState('');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    refreshReports();
    barangaysApi.list()
      .then((geo) => setBarangays((geo.features || []).map((f) => ({ id: f.properties.id, name: f.properties.name }))))
      .catch(() => {});
    hazardsApi.types().then(setHazardTypes).catch(() => {});
    guidanceApi.list().then((all) => setGuidance(all.slice(0, 2))).catch(() => {});
  }, []);

  async function refreshReports() {
    try {
      setReports(await reportsApi.list());
    } catch {
      setReports([]);
    }
  }

  async function submitReport(e) {
    e.preventDefault();
    setBusy(true);
    try {
      await reportsApi.submit({
        barangay: barangayId || barangays[0]?.id,
        hazard_type: hazardTypeId || hazardTypes[0]?.id,
        description,
      });
      setDescription('');
      refreshReports();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <Navbar />
      <div style={{ flex: 1, overflowY: 'auto', padding: 24, maxWidth: 780, margin: '0 auto', width: '100%' }}>
        <h2 style={{ marginBottom: 4 }}>Barangay dashboard</h2>
        <p style={{ color: 'var(--text-muted)', fontSize: 13, marginBottom: 20 }}>
          Submit incident reports for DRRMO validation.
        </p>

        <form onSubmit={submitReport} style={{ border: '1px solid var(--line)', background: 'var(--panel)', padding: 18, marginBottom: 24 }}>
          <h3 style={{ marginTop: 0 }}>Submit a report</h3>
          <div className="field">
            <label>Barangay</label>
            <select value={barangayId} onChange={(e) => setBarangayId(Number(e.target.value))}>
              {barangays.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
            </select>
          </div>
          <div className="field">
            <label>Hazard type</label>
            <select value={hazardTypeId} onChange={(e) => setHazardTypeId(Number(e.target.value))}>
              {hazardTypes.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
            </select>
          </div>
          <div className="field">
            <label>What are you seeing?</label>
            <textarea rows={3} required value={description} onChange={(e) => setDescription(e.target.value)}
                      placeholder="Describe the situation — location detail, how bad it looks, anyone affected" />
          </div>
          <button className="btn primary" disabled={busy}>{busy ? 'Submitting…' : 'Submit report'}</button>
        </form>

        <h3>Your submitted reports</h3>
        {reports.length === 0 ? (
          <p style={{ color: 'var(--text-muted)' }}>No reports yet.</p>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginBottom: 24 }}>
            {reports.map((r) => (
              <div key={r.id} style={{ border: '1px solid var(--line)', background: 'var(--panel)', padding: 14 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6, flexWrap: 'wrap', gap: 6 }}>
                  <strong>{r.hazard_type_detail?.name} · {r.barangay_detail?.name}</strong>
                  <span style={{ color: STATUS_COLOR[r.status], fontSize: 12.5, fontWeight: 600 }}>{r.status}</span>
                </div>
                <p style={{ fontSize: 13, margin: '0 0 6px' }}>{r.description}</p>
                <div style={{ fontSize: 11.5, color: 'var(--text-muted)' }}>{new Date(r.created_at).toLocaleString()}</div>
                {r.review_note && (
                  <div style={{ fontSize: 11.5, color: 'var(--text-muted)', marginTop: 4 }}>Note: {r.review_note}</div>
                )}
              </div>
            ))}
          </div>
        )}

        <h3>Latest safety guidance</h3>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {guidance.map((g) => (
            <div key={g.id} style={{ border: '1px solid var(--line)', background: 'var(--panel)', padding: 12 }}>
              <strong>{g.title}</strong>
              <span style={{ marginLeft: 8, fontSize: 11.5, color: 'var(--accent)' }}>{g.hazard_type_detail?.name}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}