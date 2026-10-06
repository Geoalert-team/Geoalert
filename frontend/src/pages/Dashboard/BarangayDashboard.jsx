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
  const [dead, setDead] = useState(0);
  const [injured, setInjured] = useState(0);
  const [missing, setMissing] = useState(0);
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
        casualties_dead: Number(dead) || 0,
        casualties_injured: Number(injured) || 0,
        casualties_missing: Number(missing) || 0,
      });
      setDescription('');
      setDead(0);
      setInjured(0);
      setMissing(0);
      refreshReports();
    } finally {
      setBusy(false);
    }
  }

  const pendingCount = reports.filter((r) => r.status === 'Pending').length;
  const validatedCount = reports.filter((r) => r.status === 'Validated').length;

  return (
    <div className="db">
      <PublicNavbar />
      <div className="db-wrap">
        <div className="db-header">
          <h1>Barangay dashboard</h1>
          <p>Submit incident reports for DRRMO validation.</p>
        </div>

        <div className="db-stats">
          <div className="db-stat">
            <div className="db-stat-value">{reports.length}</div>
            <div className="db-stat-label">Reports submitted</div>
          </div>
          <div className="db-stat">
            <div className="db-stat-value">{pendingCount}</div>
            <div className="db-stat-label">Awaiting review</div>
          </div>
          <div className="db-stat">
            <div className="db-stat-value">{validatedCount}</div>
            <div className="db-stat-label">Validated</div>
          </div>
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

            <fieldset className="db-fieldset">
              <legend>Casualties &amp; injured</legend>
              <div className="db-field-row db-field-row-3">
                <div className="field">
                  <label htmlFor="rep-dead">Casualties (dead)</label>
                  <input id="rep-dead" type="number" min="0" inputMode="numeric"
                    value={dead} onChange={(e) => setDead(e.target.value)} />
                </div>
                <div className="field">
                  <label htmlFor="rep-injured">Injured</label>
                  <input id="rep-injured" type="number" min="0" inputMode="numeric"
                    value={injured} onChange={(e) => setInjured(e.target.value)} />
                </div>
                <div className="field">
                  <label htmlFor="rep-missing">Missing</label>
                  <input id="rep-missing" type="number" min="0" inputMode="numeric"
                    value={missing} onChange={(e) => setMissing(e.target.value)} />
                </div>
              </div>
              <p className="db-hint">Enter 0 if no one was hurt.</p>
            </fieldset>

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
                      <span className="db-item-title">{r.hazard_type_details?.name} · {r.barangay_details?.name}</span>
                      <span className={`db-badge ${STATUS_BADGE[r.status] || ''}`}>{r.status}</span>
                    </div>
                    <p style={{ fontSize: '.92rem', margin: '6px 0' }}>{r.description}</p>
                    <div className="db-chips">
                      <span className={`db-chip ${r.casualties_dead > 0 ? 'db-chip-danger' : ''}`}>Casualties: {r.casualties_dead ?? 0}</span>
                      <span className={`db-chip ${r.casualties_injured > 0 ? 'db-chip-warn' : ''}`}>Injured: {r.casualties_injured ?? 0}</span>
                      <span className="db-chip">Missing: {r.casualties_missing ?? 0}</span>
                    </div>
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