import React, { useEffect, useState } from 'react';
import PublicNavbar from '../../components/Navbar/PublicNavbar';
import { barangaysApi } from '../../api/barangaysApi';
import { reportsApi } from '../../api/reportApi';
import { guidanceApi } from '../../api/guidanceApi';
import { hazardsApi } from '../../api/hazardsApi';
import '../css/Dashboard.css';

const STATUS_BADGE = { Pending: 'db-badge-pending', Validated: 'db-badge-validated', Rejected: 'db-badge-rejected' };

export default function BarangayDashboard() {
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
    guidanceApi.list().then((data) => setGuidance((data.results || data).slice(0, 3))).catch(() => {});
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
    <div className="db">
      <PublicNavbar />
      <div className="db-wrap">
        <div className="db-header">
          <h1>Barangay dashboard</h1>
          <p>Submit incident reports for DRRMO validation.</p>
        </div>

        <div className="db-grid-2">
          <form onSubmit={submitReport} className="db-card">
            <h2>Submit a report</h2>
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

          <div className="db-card">
            <h2>Your submitted reports</h2>
            <p className="db-card-sub">{reports.length} report{reports.length === 1 ? '' : 's'}</p>
            {reports.length === 0 ? (
              <p className="db-empty">No reports yet.</p>
            ) : (
              <div className="db-list">
                {reports.map((r) => (
                  <div key={r.id} className="db-item">
                    <div className="db-item-head">
                      <span className="db-item-title">{r.hazard_type_detail?.name} · {r.barangay_detail?.name}</span>
                      <span className={`db-badge ${STATUS_BADGE[r.status] || ''}`}>{r.status}</span>
                    </div>
                    <p style={{ fontSize: '.92rem', margin: '6px 0' }}>{r.description}</p>
                    <div className="db-item-meta">{new Date(r.created_at).toLocaleString()}</div>
                    {r.review_note && <div className="db-item-meta" style={{ marginTop: 4 }}>Note: {r.review_note}</div>}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        <div className="db-card">
          <h2>Latest safety guidance</h2>
          <div className="db-list">
            {guidance.map((g) => (
              <div key={g.id} className="db-item">
                <div className="db-item-head">
                  <span className="db-item-title">{g.title}</span>
                  <span className="db-item-meta">{g.hazard_type_detail?.name}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}